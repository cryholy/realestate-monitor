import json
from datetime import datetime, timedelta, timezone

import pytest

from monitor import (
    load_state,
    save_state,
    make_record_id,
    is_duplicate,
    add_to_state,
    cleanup_old_alerts,
)


def test_load_state_creates_empty_when_missing(tmp_path):
    state_path = tmp_path / "state.json"
    state = load_state(str(state_path))
    assert state == {"last_run": None, "last_error_notified_at": None, "alerted_sales": []}


def test_save_then_load_roundtrip(tmp_path):
    state_path = tmp_path / "state.json"
    state = {"last_run": "2026-05-04T09:00:00+09:00", "last_error_notified_at": None, "alerted_sales": []}
    save_state(str(state_path), state)

    loaded = load_state(str(state_path))
    assert loaded == state


def test_save_state_is_atomic(tmp_path):
    """save_state는 tmp 파일 후 rename으로 동작 — 부분 쓰기 시에도 기존 파일 유지."""
    state_path = tmp_path / "state.json"
    save_state(str(state_path), {"last_run": "old", "last_error_notified_at": None, "alerted_sales": []})

    tmp_files_before = list(tmp_path.iterdir())
    save_state(str(state_path), {"last_run": "new", "last_error_notified_at": None, "alerted_sales": []})
    tmp_files_after = list(tmp_path.iterdir())

    # 새 임시 파일이 남아있으면 안됨 (rename 후 정리)
    assert len(tmp_files_after) == 1
    assert load_state(str(state_path))["last_run"] == "new"


def test_make_record_id_deterministic():
    record = {
        "아파트": "서울숲푸르지오",
        "법정동": "성수동1가",
        "전용면적": 84.92,
        "거래일": "2026-04-28",
        "층": 15,
        "거래금액": 198000,
    }
    id1 = make_record_id(record)
    id2 = make_record_id(record)
    assert id1 == id2
    assert len(id1) == 40  # sha1 hex

    record2 = dict(record, 층=14)
    assert make_record_id(record2) != id1


def test_is_duplicate_and_add():
    state = {"last_run": None, "last_error_notified_at": None, "alerted_sales": []}
    record = {
        "아파트": "서울숲푸르지오",
        "법정동": "성수동1가",
        "전용면적": 84.92,
        "거래일": "2026-04-28",
        "층": 15,
        "거래금액": 198000,
    }
    assert is_duplicate(record, state) is False

    add_to_state(record, state, complex_key="seoulsupp_1", now="2026-05-04T09:00:00+09:00")
    assert len(state["alerted_sales"]) == 1
    assert is_duplicate(record, state) is True


def test_cleanup_removes_old_alerts():
    now = datetime(2026, 5, 4, tzinfo=timezone.utc)
    old = (now - timedelta(days=200)).isoformat()
    recent = (now - timedelta(days=50)).isoformat()

    state = {
        "last_run": None,
        "last_error_notified_at": None,
        "alerted_sales": [
            {"id": "a" * 40, "complex_key": "x", "deal_date": "2025-10-01", "alerted_at": old},
            {"id": "b" * 40, "complex_key": "y", "deal_date": "2026-03-01", "alerted_at": recent},
        ],
    }
    cleanup_old_alerts(state, days=180, now=now)
    assert len(state["alerted_sales"]) == 1
    assert state["alerted_sales"][0]["id"] == "b" * 40
