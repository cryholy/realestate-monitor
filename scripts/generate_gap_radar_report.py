"""서울 한강권 대표단지 갭 레이더 — Markdown/CSV/Summary JSON 생성 CLI."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.db import get_client  # noqa: E402
from lib.gap_radar import (  # noqa: E402
    RadarRow,
    build_weekly_headline,
    render_csv,
    render_markdown_report,
    summarize_counts,
)


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


def write_report(rows: list[RadarRow], *, report_date: str, output_dir: Path) -> tuple[Path, Path, Path]:
    """산출물 3종.

    - Markdown: `output_dir/{date}.md`
    - CSV: `output_dir/r/{date}.csv` — Storage 객체 키 `r/{date}.csv`와 1:1 매핑. UTF-8 BOM 포함.
    - Summary: `output_dir/{date}-summary.json` — counts + headline.
    """
    markdown_path = output_dir / f"{report_date}.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "r" / f"{report_date}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"{report_date}-summary.json"

    markdown_path.write_text(render_markdown_report(rows, report_date=report_date), encoding="utf-8")
    csv_path.write_text(render_csv(rows), encoding="utf-8-sig")
    summary_path.write_text(
        json.dumps(
            {
                "report_date": report_date,
                "counts": summarize_counts(rows),
                "headline": build_weekly_headline(rows),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return markdown_path, csv_path, summary_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(), help="리포트 날짜. YYYY-MM-DD")
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
    output_dir = Path(args.output_dir)

    rows = fetch_rows(client)
    if not rows:
        print("v_gap_radar_weekly_rows 결과가 없습니다. SQL view 적용과 데이터 적재 상태를 확인하세요.", file=sys.stderr)
        return 1

    markdown_path, csv_path, summary_path = write_report(rows, report_date=args.date, output_dir=output_dir)
    counts = summarize_counts(rows)
    print(f"Markdown: {markdown_path}")
    print(f"CSV: {csv_path}")
    print(f"Summary: {summary_path}")
    print(f"Rows: {len(rows)}")
    print(
        "COUNTS "
        f"total_rows={counts['total_rows']} "
        f"high_reliability={counts['high_reliability']} "
        f"ratio_up={counts['ratio_up']} "
        f"gap_down={counts['gap_down']} "
        f"use_rate_up={counts['use_rate_up']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
