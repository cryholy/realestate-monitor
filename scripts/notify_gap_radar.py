"""갭 레이더 cron 결과 텔레그램 알림.

lib/notifier.py의 send_telegram을 재사용한다. cron이 이 스크립트를 두 가지 모드로 호출:
  --mode success: 비공개 페이지 URL + 핵심 숫자 알림
  --mode failure: 실패 사유 알림
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

from lib.notifier import send_telegram  # noqa: E402


def build_success_message(
    *,
    report_date: str,
    page_url: str,
    total_rows: int,
    high_reliability: int,
    ratio_up: int,
    gap_down: int,
    use_rate_up: int,
) -> str:
    return (
        f"📊 갭 레이더 {report_date} 초안 작성 완료\n"
        f"\n"
        f"분석 항목 {total_rows}개\n"
        f"신뢰도 높음 {high_reliability}개\n"
        f"전세가율 상승 {ratio_up}개\n"
        f"갭 축소 {gap_down}개\n"
        f"갱신권 사용률 상승 {use_rate_up}개\n"
        f"\n"
        f"검수 URL: {page_url}\n"
        f"\n"
        f"월요일 아침 검수 후 페이지를 공개 부모로 이동시키고 메인 페이지 영역을 갱신해 공개해 주세요."
    )


def build_failure_message(*, report_date: str, reason: str) -> str:
    return (
        f"⚠️ 갭 레이더 {report_date} 발행 실패\n"
        f"\n"
        f"사유: {reason}\n"
        f"\n"
        f"GitHub Actions 로그를 확인해 주세요."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["success", "failure"], required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--page-url", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--total-rows", type=int, default=0)
    parser.add_argument("--high-reliability", type=int, default=0)
    parser.add_argument("--ratio-up", type=int, default=0)
    parser.add_argument("--gap-down", type=int, default=0)
    parser.add_argument("--use-rate-up", type=int, default=0)
    args = parser.parse_args()

    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 비어 있습니다.", file=sys.stderr)
        return 2

    if args.mode == "success":
        if not args.page_url:
            print("success 모드에는 --page-url 이 필요합니다.", file=sys.stderr)
            return 2
        text = build_success_message(
            report_date=args.date,
            page_url=args.page_url,
            total_rows=args.total_rows,
            high_reliability=args.high_reliability,
            ratio_up=args.ratio_up,
            gap_down=args.gap_down,
            use_rate_up=args.use_rate_up,
        )
    else:
        text = build_failure_message(report_date=args.date, reason=args.reason or "사유 미상")

    send_telegram(token=token, chat_id=chat_id, text=text)
    print("notified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
