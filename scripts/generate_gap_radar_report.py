"""서울 한강권 대표단지 갭 레이더 Notion용 리포트 파일 생성."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.db import get_client  # noqa: E402
from lib.gap_radar import RadarRow, render_csv, render_markdown_report  # noqa: E402


def fetch_rows(client) -> list[RadarRow]:
    resp = (
        client
        .table("v_gap_radar_weekly_rows")
        .select("*")
        .order("lifestyle_area")
        .order("district_name")
        .order("district_rank")
        .execute()
    )
    return [RadarRow.from_db(row) for row in (resp.data or [])]


def write_report(rows: list[RadarRow], *, report_date: str, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"{report_date}.md"
    csv_path = output_dir / f"{report_date}.csv"

    markdown_path.write_text(render_markdown_report(rows, report_date=report_date), encoding="utf-8")
    csv_path.write_text(render_csv(rows), encoding="utf-8")
    return markdown_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(), help="리포트 날짜. YYYY-MM-DD 형식")
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "gap-radar"))
    args = parser.parse_args()

    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    missing = [name for name, value in [
        ("SUPABASE_URL", supabase_url),
        ("SUPABASE_SERVICE_ROLE_KEY", supabase_key),
    ] if not value]
    if missing:
        print(f"필수 환경변수 누락: {', '.join(missing)}", file=sys.stderr)
        return 2

    client = get_client(supabase_url, supabase_key)
    rows = fetch_rows(client)
    if not rows:
        print("v_gap_radar_weekly_rows 결과가 없습니다. SQL view 적용과 데이터 적재 상태를 확인하세요.", file=sys.stderr)
        return 1

    markdown_path, csv_path = write_report(rows, report_date=args.date, output_dir=Path(args.output_dir))
    print(f"Markdown: {markdown_path}")
    print(f"CSV: {csv_path}")
    print(f"Rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
