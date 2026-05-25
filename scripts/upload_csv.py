"""갭 레이더 주간 CSV를 Supabase Storage(public bucket `reports`)로 업로드.

객체 키 패턴: `r/YYYY-MM-DD.csv`. 공개 URL을 stdout으로 출력해서 cron이 후속 단계에서
Notion 본문에 삽입할 수 있게 한다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.db import get_client  # noqa: E402


BUCKET = "reports"


def build_storage_key(report_date: str) -> str:
    return f"r/{report_date}.csv"


def upload(*, client, storage_key: str, csv_bytes: bytes) -> str:
    client.storage.from_(BUCKET).upload(
        path=storage_key,
        file=csv_bytes,
        file_options={"content-type": "text/csv; charset=utf-8", "upsert": "true"},
    )
    return client.storage.from_(BUCKET).get_public_url(storage_key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="리포트 날짜. YYYY-MM-DD")
    parser.add_argument("--csv", required=True, help="업로드할 CSV 파일 경로")
    args = parser.parse_args()

    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("필수 환경변수 누락: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 2

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV 파일을 찾을 수 없습니다: {csv_path}", file=sys.stderr)
        return 2

    client = get_client(url, key)
    storage_key = build_storage_key(args.date)
    public_url = upload(client=client, storage_key=storage_key, csv_bytes=csv_path.read_bytes())

    print(f"Key: {storage_key}")
    print(f"URL: {public_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
