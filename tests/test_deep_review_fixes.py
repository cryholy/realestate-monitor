"""deep-review CONFIRMED 결함 배치의 변별 테스트 (정상 구현 vs 버그 구현이 발산).

각 테스트는 수정 전 코드에서 실패(RED)하고 수정 후 통과(GREEN)한다.
M1 보안 / M2 가용성 / M3 기능 / M4 정확성 / m5 풋건 / m6 표시 / m7 청킹.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from lib.api import _http_get
from lib.db import dedup_check, upsert_records
from lib.notifier import format_won
from lib.triggers import evaluate_price_threshold
import collector as C

PROJECT_ROOT = Path(__file__).parent.parent
SQL_007 = PROJECT_ROOT / "sql" / "007_cancel_filter_and_any_size.sql"


# ── M1 보안: serviceKey 마스킹 ────────────────────────────────────────────
def test_m1_mask_service_key_removes_key():
    from lib.api import _mask_service_key  # 수정 전엔 미존재 → RED

    enc_key = "abc%2Bdef%2Fghi%3D%3D"
    raw_key = "abc+def/ghi=="

    masked_enc = _mask_service_key(
        f"ConnectionError: https://apis.data.go.kr/x?serviceKey={enc_key}&LAWD_CD=11710"
    )
    assert enc_key not in masked_enc
    assert "[REDACTED]" in masked_enc

    masked_raw = _mask_service_key(f"url=https://x?serviceKey={raw_key}&a=1")
    assert raw_key not in masked_raw


@patch("lib.api.time.sleep", lambda *_: None)
@patch("lib.api.requests.get")
def test_m1_http_get_error_masks_service_key(mock_get):
    """_http_get가 예외를 RuntimeError로 감쌀 때 serviceKey 값이 새지 않는다."""
    key = "SECRETKEY%2Babc%3Dxyz"

    def boom(url, params=None, timeout=None):
        raise requests.exceptions.ConnectionError(
            f"HTTPSConnectionPool: {url}?serviceKey={params['serviceKey']}&LAWD_CD=11710"
        )

    mock_get.side_effect = boom

    with pytest.raises(RuntimeError) as exc:
        _http_get("https://apis.data.go.kr/x", {"serviceKey": key, "LAWD_CD": "11710"})

    assert key not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)


# ── M2 가용성: price<=0 후보가 크래시 없이 제외 ──────────────────────────
def test_m2_zero_price_no_candidate():
    """price_만원=0 레코드는 매수 후보에서 제외되어 하류 ZeroDivision을 막는다."""
    record = {"id": "z0", "apt_seq": "11000-0001", "size_label": "84",
              "price_만원": 0, "deal_date": "2026-06-01", "floor": 10}
    rule = {"id": "r1", "apt_seq": "11000-0001", "size_label": "84",
            "max_price_만원": 200000, "enabled": True, "display_name": "X"}

    assert evaluate_price_threshold([record], [rule]) == []


# ── M3 기능: 'any' size_label median 조회 경로 (SQL 파일 diff) ────────────
def test_m3_migration_median_supports_any_size():
    """007 마이그레이션의 median RPC가 p_size_label='any'를 지원한다."""
    sql = SQL_007.read_text(encoding="utf-8").lower()
    norm = " ".join(sql.split())

    assert "median_sale_price" in norm
    assert "median_jeonse_deposit" in norm
    # 'any'면 size_label 필터를 생략하는 분기가 두 함수 모두에 있어야 한다.
    assert norm.count("p_size_label = 'any'") >= 2


# ── M4 정확성: 취소거래 제외 ─────────────────────────────────────────────
def test_m4_cancelled_trade_no_price_candidate():
    """cancel_date가 설정된 취소거래는 매수 알림 후보에서 제외된다."""
    record = {"id": "c1", "apt_seq": "11000-0001", "size_label": "84",
              "price_만원": 100000, "deal_date": "2026-06-01", "floor": 10,
              "cancel_date": "2026-06-10"}
    rule = {"id": "r1", "apt_seq": "11000-0001", "size_label": "84",
            "max_price_만원": 200000, "enabled": True, "display_name": "X"}

    assert evaluate_price_threshold([record], [rule]) == []


def test_m4_migration_median_filters_cancelled():
    """007 마이그레이션의 매매 median RPC/MV가 취소거래를 제외한다."""
    sql = SQL_007.read_text(encoding="utf-8").lower()
    norm = " ".join(sql.split())
    assert "cancel_date is null" in norm


# ── 007 회귀 방지: CREATE OR REPLACE / DROP+CREATE가 005·004 하드닝을 되돌리지 않는지 ──
def test_007_functions_repin_search_path():
    """005의 search_path 하드닝(proconfig)을 007 함수 재정의가 재명시해 유지한다."""
    norm = " ".join(SQL_007.read_text(encoding="utf-8").lower().split())
    # median_sale_price·median_jeonse_deposit 두 함수 모두 SET search_path 절을 가져야 한다.
    assert norm.count("set search_path = pg_catalog, public") >= 2


def test_007_sale_mv_keeps_sgg_name_and_revoke():
    """007이 매매 MV를 DROP+CREATE할 때 004의 sgg_name/인덱스와 005의 REVOKE를 유지한다."""
    norm = " ".join(SQL_007.read_text(encoding="utf-8").lower().split())
    assert "sgg_name" in norm                                       # 004 컬럼 유지
    assert "idx_mv_monthly_sale_sgg" in norm                        # 004 인덱스 유지
    assert "left join districts" in norm                            # sgg_name 소스 조인
    assert "mv_monthly_sale_stats from anon, authenticated" in norm  # 005 REVOKE 재적용


def test_m4_upsert_reflects_cancellation():
    """재수집 시 취소 상태가 반영되도록 upsert가 DO NOTHING(ignore)이 아니어야 한다."""
    mock = MagicMock()
    records = [{"id": "x", "cancel_date": "2026-06-10"}]
    mock.table.return_value.upsert.return_value.execute.return_value.data = records

    upsert_records(mock, "sale_records", records)

    _, kwargs = mock.table.return_value.upsert.call_args
    assert kwargs.get("ignore_duplicates") is not True


# ── m5 풋건: dry-run 부작용 프리 ─────────────────────────────────────────
def _run_main(dry: bool):
    argv = ["collector.py", "--backfill-months", "1"]
    if dry:
        argv.append("--dry-run")

    sale = {"id": "s1", "apt_seq": "11000-0001", "size_label": "84",
            "price_만원": 100000, "deal_date": "2026-06-01", "floor": 10}

    def fake_collect(service_key, months, *, persist=None, **kw):
        if persist is not None:
            persist("sale_records", [sale])
            persist("rent_records", [])
        return [sale], [], False

    env = {
        "MOLIT_SERVICE_KEY": "k", "TELEGRAM_BOT_TOKEN": "t",
        "TELEGRAM_CHAT_ID": "c", "SUPABASE_URL": "u",
        "SUPABASE_SERVICE_ROLE_KEY": "s",
    }

    with (
        patch.object(C, "load_dotenv", lambda *a, **k: None),
        patch.object(C, "get_client", lambda *a, **k: MagicMock()),
        patch.object(C, "collect_records", fake_collect),
        patch.object(C, "find_new_records", lambda c, t, r: r),
        patch.object(C, "load_alert_rules", lambda c: []),
        patch.object(C, "send_telegram", lambda **k: None),
        patch.object(C, "upsert_records") as up,
        patch.object(C, "refresh_materialized_views") as rf,
        patch.dict(os.environ, env),
        patch.object(sys, "argv", argv),
    ):
        rc = C.main()

    return up.call_count, rf.call_count, rc


def test_m5_dry_run_skips_upsert_and_refresh():
    up, rf, rc = _run_main(dry=True)
    assert rc == 0
    assert up == 0, "dry-run이 DB upsert를 호출했다"
    assert rf == 0, "dry-run이 MV refresh를 호출했다"


def test_m5_normal_run_does_upsert_and_refresh():
    up, rf, rc = _run_main(dry=False)
    assert rc == 0
    assert up > 0
    assert rf == 1


# ── m6 표시버그: 음수 format_won ─────────────────────────────────────────
def test_m6_format_won_negative():
    assert format_won(-5000) == "-5,000"
    assert format_won(-100) == "-100"
    assert format_won(-15000) == "-1억 5,000"
    assert format_won(-198000) == "-19억 8,000"
    assert format_won(-200000) == "-20억"


# ── m7 청킹: dedup_check 배치 분할 ───────────────────────────────────────
def test_m7_dedup_check_chunks_over_limit():
    """후보가 청크 임계(100)를 넘으면 여러 in_ 쿼리로 분할 조회한다."""
    mock = MagicMock()
    mock.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []
    candidates = [{"rule_id": "r1", "dedup_key": f"sale:{i}"} for i in range(150)]

    dedup_check(mock, candidates)

    assert mock.table.return_value.select.return_value.in_.call_count == 2
