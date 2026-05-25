"""서울 한강권 대표단지 갭 레이더 Notion용 리포트 파일 생성.

--version v1 (legacy): v_gap_radar_weekly_rows + render_markdown_report
--version v2 (default): v_gap_radar_weekly_rows_v2 + render_markdown_report_v2
"""
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
from lib.gap_radar import (  # noqa: E402
    RadarRow,
    RadarRowV2,
    render_csv,
    render_csv_v2,
    render_markdown_report,
    render_markdown_report_v2,
    summarize_v2_counts,
)


def fetch_rows_v1(client) -> list[RadarRow]:
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


def fetch_rows_v2(client) -> list[RadarRowV2]:
    resp = (
        client
        .table("v_gap_radar_weekly_rows_v2")
        .select("*")
        .order("lifestyle_area")
        .order("district_name")
        .order("district_rank")
        .execute()
    )
    return [RadarRowV2.from_db(row) for row in (resp.data or [])]


def write_report_v1(rows: list[RadarRow], *, report_date: str, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"{report_date}.md"
    csv_path = output_dir / f"{report_date}.csv"
    markdown_path.write_text(render_markdown_report(rows, report_date=report_date), encoding="utf-8")
    csv_path.write_text(render_csv(rows), encoding="utf-8")
    return markdown_path, csv_path


def write_report_v2(rows: list[RadarRowV2], *, report_date: str, output_dir: Path) -> tuple[Path, Path]:
    """v2 산출물.

    - Markdown은 `output_dir/{date}-v2.md` (내부 식별용, v2 suffix 유지)
    - CSV는 `output_dir/r/{date}.csv` — Supabase Storage 객체 키 `r/{date}.csv` 와 1:1 매핑
    """
    markdown_path = output_dir / f"{report_date}-v2.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "r" / f"{report_date}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown_report_v2(rows, report_date=report_date), encoding="utf-8")
    csv_path.write_text(render_csv_v2(rows), encoding="utf-8")
    return markdown_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(), help="리포트 날짜. YYYY-MM-DD 형식")
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "gap-radar"))
    parser.add_argument("--version", choices=["v1", "v2"], default="v2",
                        help="리포트 버전. 기본 v2 (legacy v1은 비교/롤백용)")
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

    if args.version == "v1":
        rows = fetch_rows_v1(client)
        if not rows:
            print("v_gap_radar_weekly_rows 결과가 없습니다. v1 SQL view와 데이터 적재 상태를 확인하세요.", file=sys.stderr)
            return 1
        markdown_path, csv_path = write_report_v1(rows, report_date=args.date, output_dir=output_dir)
        print(f"Version: {args.version}")
        print(f"Markdown: {markdown_path}")
        print(f"CSV: {csv_path}")
        print(f"Rows: {len(rows)}")
    else:
        rows = fetch_rows_v2(client)
        if not rows:
            print("v_gap_radar_weekly_rows_v2 결과가 없습니다. v2 SQL view와 데이터 적재 상태를 확인하세요.", file=sys.stderr)
            return 1
        markdown_path, csv_path = write_report_v2(rows, report_date=args.date, output_dir=output_dir)
        counts = summarize_v2_counts(rows)
        print(f"Version: {args.version}")
        print(f"Markdown: {markdown_path}")
        print(f"CSV: {csv_path}")
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
