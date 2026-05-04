"""백필된 데이터 중 사용자 alert_rules의 임계값을 이미 충족한 거래에 대해
alerts_sent에 dedup 키를 미리 채워, 운영 시작 첫 실행에서 알림 폭격을 방지한다.

알림 메시지는 발송하지 않고, alerts_sent에만 INSERT.

사용:
  python3.11 scripts/seed_alerts_sent.py
  python3.11 scripts/seed_alerts_sent.py --dry-run
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from collector import setup_logging
from lib.db import (
    get_client,
    load_alert_rules,
    mark_alert_sent,
    query_median_sale_price,
    query_median_jeonse_deposit,
)
from lib.triggers import evaluate_jeonse_ratio

KST = timezone(timedelta(hours=9))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("seed_alerts_sent")

    here = Path(__file__).parent.parent
    if (here / ".env").exists():
        load_dotenv(here / ".env")

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        logger.error("Supabase 환경변수 누락")
        return 2

    client = get_client(url, key)
    rules = load_alert_rules(client)
    logger.info("활성 룰 %d개에 대해 seed 진행", len(rules))

    today_iso = datetime.now(KST).date().isoformat()

    # 1) Price threshold seed
    seeded_price = 0
    for rule in rules:
        if rule.get("max_price_만원") is None:
            continue
        q = client.table("sale_records").select("*") \
            .eq("apt_seq", rule["apt_seq"])
        if rule["size_label"] != "any":
            q = q.eq("size_label", rule["size_label"])
        q = q.lt("price_만원", rule["max_price_만원"])
        sales = q.execute().data or []

        for s in sales:
            dedup_key = f"sale:{s['id']}"
            try:
                if not args.dry_run:
                    mark_alert_sent(client, rule_id=rule["id"], dedup_key=dedup_key,
                                    alert_type="price_threshold")
                seeded_price += 1
            except Exception:
                # 이미 PK 있으면 무시 (중복 실행 안전성)
                pass
        logger.info("rule=%s (%s %s): seed %d개", rule["id"], rule["display_name"], rule["size_label"], len(sales))

    # 2) Jeonse ratio seed — 현재 임계값 충족 시 이번 달 키 미리 등록
    cands = evaluate_jeonse_ratio(
        rules=rules,
        median_sale_fn=partial(query_median_sale_price, client),
        median_jeonse_fn=partial(query_median_jeonse_deposit, client),
        today=today_iso,
    )
    seeded_jeonse = 0
    for c in cands:
        try:
            if not args.dry_run:
                mark_alert_sent(client, rule_id=c.rule_id, dedup_key=c.dedup_key,
                                alert_type="jeonse_ratio")
            seeded_jeonse += 1
        except Exception:
            pass

    logger.info("seed 완료: price %d개, jeonse %d개", seeded_price, seeded_jeonse)
    return 0


if __name__ == "__main__":
    sys.exit(main())
