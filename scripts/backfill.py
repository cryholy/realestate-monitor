"""1년 백필 — 1회성 수동 실행.

사용:
  python3.11 scripts/backfill.py --months 12
  python3.11 scripts/backfill.py --months 12 --dry-run
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# 부모 디렉토리를 path에 추가하여 lib/* 임포트 가능하게
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from collector import (
    DISTRICT_LAWD_CDS,
    collect_records,
    setup_logging,
)
from lib.db import get_client, upsert_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=12, help="백필 개월 수")
    parser.add_argument("--dry-run", action="store_true", help="DB UPSERT 안 함")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("backfill")

    here = Path(__file__).parent.parent
    if (here / ".env").exists():
        load_dotenv(here / ".env")

    service_key = os.environ.get("MOLIT_SERVICE_KEY", "").strip()
    if not service_key:
        logger.error("MOLIT_SERVICE_KEY 미설정")
        return 2

    client = None
    if not args.dry_run:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            logger.error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정")
            return 2
        client = get_client(url, key)

    logger.info("백필 시작: %d개월 × 9개 구 × 매매·전세", args.months)
    sales, rents = collect_records(service_key, args.months)
    logger.info("수집: 매매 %d건, 전세 %d건", len(sales), len(rents))

    if args.dry_run:
        logger.info("[DRY-RUN] UPSERT skip — 첫 5개 매매 sample:")
        for r in sales[:5]:
            logger.info("  %s %s %s %s만원 %s㎡",
                        r.get("apt_name"), r.get("size_label"),
                        r.get("deal_date"), r.get("price_만원"), r.get("area"))
        return 0

    # 500건씩 batch UPSERT (Supabase 한 번에 크게 보내면 timeout 가능)
    BATCH = 100
    total_sale = len(sales)
    for i in range(0, total_sale, BATCH):
        upsert_records(client, "sale_records", sales[i:i+BATCH])
        if (i // BATCH) % 10 == 0:
            logger.info("매매 UPSERT 진행: %d/%d", min(i+BATCH, total_sale), total_sale)

    total_rent = len(rents)
    for i in range(0, total_rent, BATCH):
        upsert_records(client, "rent_records", rents[i:i+BATCH])
        if (i // BATCH) % 10 == 0:
            logger.info("전월세 UPSERT 진행: %d/%d", min(i+BATCH, total_rent), total_rent)

    logger.info("백필 완료: 매매 %d / 전세 %d UPSERT", total_sale, total_rent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
