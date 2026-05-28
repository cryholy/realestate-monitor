"""GHA cron이 사용할 다음 월요일 날짜 계산 (KST 기준).

stdout에 YYYY-MM-DD를 출력. workflow에서 `REPORT_DATE=$(python3 scripts/resolve_report_date.py)`로 사용.
"""
from datetime import datetime, timedelta, timezone


def main() -> None:
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(timezone.utc).astimezone(kst)
    days_until_monday = (7 - now_kst.weekday()) % 7 or 7
    next_monday = (now_kst + timedelta(days=days_until_monday)).date()
    print(next_monday.isoformat())


if __name__ == "__main__":
    main()
