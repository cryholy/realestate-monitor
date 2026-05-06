"""monitor.yml schedule 누락 감지.

자기 repo의 monitor.yml 마지막 schedule 이벤트 성공 시각을 GitHub API로 조회하고,
임계값보다 오래되었으면 텔레그램 알림 + exit 1.

(주의) DB의 fetched_at은 신규 거래가 0건이면 갱신되지 않으므로 워크플로우 실행 신호로
사용할 수 없다. 자동화 누락 감지에는 GitHub Actions run history가 단일 진실 원천.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.notifier import send_telegram  # noqa: E402


WORKFLOW_FILE = "monitor.yml"
KST = timezone(timedelta(hours=9))


def humanize_delta(delta_h: float) -> str:
    """0.5 → '30분', 24.5 → '24시간 30분'."""
    total_min = int(delta_h * 60)
    hours, mins = divmod(total_min, 60)
    if hours == 0:
        return f"{mins}분"
    if mins == 0:
        return f"{hours}시간"
    return f"{hours}시간 {mins}분"


def latest_scheduled_success(*, repo: str, token: str) -> datetime | None:
    """monitor.yml의 schedule 이벤트 중 가장 최근 success run의 created_at."""
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs"
        f"?event=schedule&status=success&per_page=1"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    runs = body.get("workflow_runs", [])
    if not runs:
        return None
    ts = runs[0]["created_at"]
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    gh_token = os.environ["GH_TOKEN"]
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    last = latest_scheduled_success(repo=repo, token=gh_token)
    now = datetime.now(timezone.utc)

    # main cron 18:00 KST → healthcheck 18:30 KST (30분 후).
    # 30분 안에 schedule 이벤트가 잡히지 않으면 누락으로 판정.
    threshold_hours = 0.5
    alert_on_never_run = True

    if last is None:
        delta_h = None
        is_stale = bool(alert_on_never_run)
    else:
        delta_h = (now - last).total_seconds() / 3600
        is_stale = delta_h > threshold_hours

    if not is_stale:
        print(f"OK last_schedule={last} delta_h={delta_h} threshold={threshold_hours}")
        return 0

    now_kst = now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    threshold_str = humanize_delta(threshold_hours)
    if last is None:
        alert_text = (
            "🚨 부동산 데이터 자동 수집이 한 번도 동작하지 않았어요\n\n"
            "매일 18:00에 자동 실행되도록 cron이 설정되어 있지만,\n"
            "실제로 자동 트리거된 기록이 없습니다.\n"
            f"(수동 실행은 별개. 확인 시각: {now_kst})\n\n"
            "▶︎ 점검\n"
            f"  • GitHub Actions에서 monitor.yml 활성 상태인지\n"
            f"  • 임시로 수동 실행:\n"
            f"    gh workflow run monitor.yml --repo {repo}"
        )
    else:
        last_kst = last.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
        delay_str = humanize_delta(delta_h)
        alert_text = (
            f"🚨 부동산 데이터 수집이 {delay_str}째 동작하지 않았어요\n\n"
            "매일 18:00에 돌아야 할 자동 수집이 멈춘 상태입니다.\n"
            f"(허용 지연: {threshold_str})\n\n"
            f"마지막 수집  {last_kst}\n"
            f"현재         {now_kst}\n\n"
            f"▶︎ 수동 실행: gh workflow run monitor.yml --repo {repo}"
        )

    send_telegram(token=bot_token, chat_id=chat_id, text=alert_text)
    print(f"ALERT last={last} delta_h={delta_h}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
