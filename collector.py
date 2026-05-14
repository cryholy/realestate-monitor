"""부동산 매매·전월세 일일 수집·트리거·알림 메인 엔트리.

GitHub Actions cron이 호출. 또는 로컬에서 수동 실행:
  python3.11 collector.py
  python3.11 collector.py --dry-run
  python3.11 collector.py --backfill-months 12
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from dotenv import load_dotenv

from lib.api import fetch_sales, fetch_rents, make_record_id
from lib.db import (
    get_client,
    upsert_records,
    load_alert_rules,
    dedup_check,
    mark_alert_sent,
    query_median_sale_price,
    query_median_jeonse_deposit,
)
from lib.notifier import (
    format_price_message,
    format_jeonse_message,
    format_summary_message,
    send_telegram,
)
from lib.triggers import (
    PriceCandidate,
    JeonseCandidate,
    evaluate_price_threshold,
    evaluate_jeonse_ratio,
)

KST = timezone(timedelta(hours=9))

DISTRICT_LAWD_CDS = [
    ("11200", "성동구"),
    ("11215", "광진구"),
    ("11440", "마포구"),
    ("11650", "서초구"),
    ("11680", "강남구"),
    ("11710", "송파구"),
    ("11170", "용산구"),
    ("11590", "동작구"),
    ("11740", "강동구"),
]

logger = logging.getLogger("collector")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def ymd_list(months_back: int) -> list[str]:
    """오늘 기준 직전 N개월 (이번달 포함) YYYYMM 리스트, 최신 먼저."""
    today = datetime.now(KST)
    out = []
    y, m = today.year, today.month
    for _ in range(months_back):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out


def collect_records(service_key: str, months: int) -> tuple[list[dict], list[dict]]:
    """9개 구 × 매매·전월세 × N개월 수집. 각 record에 id 부착."""
    sales: list[dict] = []
    rents: list[dict] = []

    for ymd in ymd_list(months):
        for lawd_cd, district_name in DISTRICT_LAWD_CDS:
            try:
                for r in fetch_sales(lawd_cd=lawd_cd, ymd=ymd, service_key=service_key):
                    r["id"] = make_record_id(r, kind="sale")
                    sales.append(r)
            except Exception as e:
                logger.error("매매 fetch 실패 lawd=%s ymd=%s: %s", lawd_cd, ymd, e)

            try:
                for r in fetch_rents(lawd_cd=lawd_cd, ymd=ymd, service_key=service_key):
                    r["id"] = make_record_id(r, kind="rent")
                    rents.append(r)
            except Exception as e:
                logger.error("전월세 fetch 실패 lawd=%s ymd=%s: %s", lawd_cd, ymd, e)

            time.sleep(0.5)   # rate limit safety margin

    return sales, rents


def find_new_records(client, table: str, candidate_records: list[dict]) -> list[dict]:
    """후보 record 중 DB에 없는 신규만 식별 (UPSERT 전 사전 조회).

    PostgREST IN 쿼리는 URL query string으로 직렬화되어 URL 길이 한도(~8KB)에 걸리므로
    100건씩 chunk로 나눠 조회.
    """
    if not candidate_records:
        return []

    ids = [r["id"] for r in candidate_records]
    BATCH = 100
    existing: set[str] = set()
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i+BATCH]
        resp = client.table(table).select("id").in_("id", chunk).execute()
        existing.update(row["id"] for row in (resp.data or []))

    return [r for r in candidate_records if r["id"] not in existing]


def process_price_alerts(
    client,
    bot_token: str,
    chat_id: str,
    new_sales: list[dict],
    rules: list[dict],
    dry_run: bool,
) -> int:
    """가격 임계값 도달 후보 평가 → dedup → 발송."""
    candidates = evaluate_price_threshold(new_sales, rules)
    if not candidates:
        return 0

    cand_dicts = [{"rule_id": c.rule_id, "dedup_key": c.dedup_key} for c in candidates]
    new_keys = {(d["rule_id"], d["dedup_key"]) for d in dedup_check(client, cand_dicts)}

    sent_count = 0
    for c in candidates:
        if (c.rule_id, c.dedup_key) not in new_keys:
            continue

        median_jeonse, n_jeonse = query_median_jeonse_deposit(
            client, apt_seq=c.record["apt_seq"], size_label=c.record["size_label"], days=90,
        )

        msg = format_price_message(
            c.rule, c.record,
            median_sale=c.record["price_만원"],
            median_jeonse=median_jeonse,
            sample_count_jeonse=n_jeonse,
        )
        candidate_log = (
            f"[CANDIDATE] type=price_threshold rule_id={c.rule_id} "
            f"apt_seq={c.record['apt_seq']} deal_date={c.record['deal_date']} "
            f"price={c.record['price_만원']}"
        )
        logger.info(candidate_log)

        if dry_run:
            logger.info("[DRY-RUN] would send: %s", msg.replace("\n", " | "))
            continue

        try:
            send_telegram(token=bot_token, chat_id=chat_id, text=msg)
            mark_alert_sent(client, rule_id=c.rule_id, dedup_key=c.dedup_key, alert_type=c.alert_type)
            sent_count += 1
        except Exception as e:
            logger.error("price 알림 발송 실패 (재시도는 다음 cron): %s", e)

    return sent_count


def process_jeonse_alerts(
    client,
    bot_token: str,
    chat_id: str,
    rules: list[dict],
    today: str,
    dry_run: bool,
) -> int:
    """전세가율 임계값 도달 후보 평가 → dedup → 발송."""
    candidates = evaluate_jeonse_ratio(
        rules=rules,
        median_sale_fn=partial(query_median_sale_price, client),
        median_jeonse_fn=partial(query_median_jeonse_deposit, client),
        today=today,
    )
    if not candidates:
        return 0

    cand_dicts = [{"rule_id": c.rule_id, "dedup_key": c.dedup_key} for c in candidates]
    new_keys = {(d["rule_id"], d["dedup_key"]) for d in dedup_check(client, cand_dicts)}

    sent_count = 0
    for c in candidates:
        if (c.rule_id, c.dedup_key) not in new_keys:
            continue

        msg = format_jeonse_message(
            c.rule,
            ratio=c.ratio,
            median_sale=c.median_sale,
            median_jeonse=c.median_jeonse,
            sample_count_sale=c.sample_count_sale,
            sample_count_jeonse=c.sample_count_jeonse,
            month_key=c.dedup_key.split(":")[1],
        )
        candidate_log = (
            f"[CANDIDATE] type=jeonse_ratio rule_id={c.rule_id} "
            f"apt_seq={c.rule['apt_seq']} ratio={c.ratio} "
            f"median_sale={c.median_sale} median_jeonse={c.median_jeonse}"
        )
        logger.info(candidate_log)

        if dry_run:
            logger.info("[DRY-RUN] would send: %s", msg.replace("\n", " | "))
            continue

        try:
            send_telegram(token=bot_token, chat_id=chat_id, text=msg)
            mark_alert_sent(client, rule_id=c.rule_id, dedup_key=c.dedup_key, alert_type=c.alert_type)
            sent_count += 1
        except Exception as e:
            logger.error("jeonse 알림 발송 실패: %s", e)

    return sent_count


def refresh_materialized_views(client) -> None:
    """대시보드용 MV 새로고침. PostgreSQL 직접 실행이 어려우므로 SQL 한 번에."""
    try:
        # Supabase에 저장된 wrapper RPC가 없으면 그냥 무시 (대시보드만 영향)
        client.rpc("refresh_monthly_stats").execute()
    except Exception as e:
        logger.warning("MV refresh 실패 (대시보드만 영향): %s", e)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="알림 발송 X, 후보만 로그")
    parser.add_argument("--backfill-months", type=int, default=2,
                        help="N개월 fetch (기본 2: 이번달 + 직전달)")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="API fetch skip (DB 트리거만 평가, 디버그용)")
    args = parser.parse_args()

    setup_logging()

    here = Path(__file__).parent
    if (here / ".env").exists():
        load_dotenv(here / ".env")

    service_key = os.environ.get("MOLIT_SERVICE_KEY", "").strip()
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    missing = [k for k, v in [
        ("MOLIT_SERVICE_KEY", service_key),
        ("TELEGRAM_BOT_TOKEN", bot_token),
        ("TELEGRAM_CHAT_ID", chat_id),
        ("SUPABASE_URL", supabase_url),
        ("SUPABASE_SERVICE_ROLE_KEY", supabase_key),
    ] if not v]
    if missing:
        logger.error("필수 환경변수 누락: %s", missing)
        return 2

    client = get_client(supabase_url, supabase_key)
    run_started_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    today_iso = datetime.now(KST).date().isoformat()

    new_sales: list[dict] = []
    new_rents: list[dict] = []
    sales: list[dict] = []
    rents: list[dict] = []

    if not args.skip_fetch:
        logger.info("데이터 수집 시작 (직전 %d개월, %d개 구)", args.backfill_months, len(DISTRICT_LAWD_CDS))
        sales, rents = collect_records(service_key, args.backfill_months)
        logger.info("수집 완료: 매매 %d건, 전월세 %d건", len(sales), len(rents))

        new_sales = find_new_records(client, "sale_records", sales)
        new_rents = find_new_records(client, "rent_records", rents)
        logger.info("DB 신규: 매매 %d건, 전월세 %d건", len(new_sales), len(new_rents))

        upsert_records(client, "sale_records", sales)
        upsert_records(client, "rent_records", rents)

    rules = load_alert_rules(client)
    logger.info("활성 알림 룰: %d개", len(rules))

    price_sent = process_price_alerts(client, bot_token, chat_id, new_sales, rules, args.dry_run)
    jeonse_sent = process_jeonse_alerts(client, bot_token, chat_id, rules, today_iso, args.dry_run)

    logger.info("발송 완료: price %d건, jeonse %d건", price_sent, jeonse_sent)

    summary = format_summary_message(
        run_started_at=run_started_at,
        months=args.backfill_months,
        districts=len(DISTRICT_LAWD_CDS),
        sales_total=len(sales),
        sales_new=len(new_sales),
        rents_total=len(rents),
        rents_new=len(new_rents),
        rules_active=len(rules),
        price_alerts_sent=price_sent,
        jeonse_alerts_sent=jeonse_sent,
    )
    if args.dry_run:
        logger.info("[DRY-RUN] would send summary: %s", summary.replace("\n", " | "))
    else:
        try:
            send_telegram(token=bot_token, chat_id=chat_id, text=summary)
        except Exception as e:
            logger.error("요약 알림 발송 실패: %s", e)

    refresh_materialized_views(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
