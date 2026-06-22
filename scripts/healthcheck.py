"""monitor.yml 자동 수집 누락/실패 감지.

자기 repo의 monitor.yml 최신 schedule run을 GitHub API로 조회해 두 가지를 판정한다.
  ① 최신 run이 staleness 임계값 내에 존재하는가  → 없으면 트리거 자체가 누락
  ② 그 run이 끝났다면 conclusion == success 인가 → 아니면 실행은 됐으나 실패/취소

GitHub Actions의 schedule은 정시 보장이 없어 매 실행이 수 시간씩 지연된다. 따라서
'최신 success가 N분 이내'식 과민 임계값은 오탐을 양산한다. ②는 지연과 무관하게
정확하므로 ①의 임계값은 넉넉히(>1일) 두고, 실제 run 실패는 ②로 당일에 잡는다.

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

# 일 1회(24h) cadence + GitHub schedule 지터 여유(~12h). 이 안에 schedule run이
# 하나도 없으면 트리거 누락으로 본다. 실제 run 실패는 conclusion 검사가 당일에 잡으므로
# 이 값은 오탐 방지를 위해 넉넉히 둔다.
STALE_THRESHOLD_HOURS = 36


def humanize_delta(delta_h: float) -> str:
    """0.5 → '30분', 24.5 → '24시간 30분'."""
    total_min = int(delta_h * 60)
    hours, mins = divmod(total_min, 60)
    if hours == 0:
        return f"{mins}분"
    if mins == 0:
        return f"{hours}시간"
    return f"{hours}시간 {mins}분"


def fetch_latest_scheduled_run(*, repo: str, token: str) -> dict | None:
    """monitor.yml의 schedule 이벤트 중 가장 최근 run 1건.

    status 필터를 걸지 않아 in_progress / 실패 / 취소 run도 포함한다(최신 상태를
    그대로 봐야 conclusion을 판정할 수 있다). 반환: {created_at, status, conclusion}
    또는 run이 없으면 None.
    """
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs"
        f"?event=schedule&per_page=1"
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
    run = runs[0]
    return {
        "created_at": datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
    }


def evaluate_health(
    latest: dict | None,
    *,
    now: datetime,
    threshold_hours: float,
) -> tuple[str, float | None]:
    """최신 schedule run 상태 → (verdict, delta_h).

    verdict:
      "never"  최신 run 자체가 없음 (한 번도 트리거 안 됨)
      "stale"  최신 run이 threshold_hours보다 오래됨 (트리거 누락)
      "failed" run은 최근이고 끝났으나 conclusion != success (실패/취소)
      "ok"     최근 success, 또는 아직 진행 중(in_progress)
    """
    if latest is None:
        return ("never", None)

    delta_h = (now - latest["created_at"]).total_seconds() / 3600
    if delta_h > threshold_hours:
        return ("stale", delta_h)

    if latest.get("status") == "completed" and latest.get("conclusion") != "success":
        return ("failed", delta_h)

    return ("ok", delta_h)


def build_alert_text(verdict: str, latest: dict | None, delta_h: float | None, *, now: datetime, repo: str) -> str:
    """verdict별 텔레그램 알림 문구."""
    now_kst = now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    manual = f"▶︎ 수동 실행: gh workflow run monitor.yml --repo {repo}"

    if verdict == "never":
        return (
            "🚨 부동산 데이터 자동 수집이 한 번도 동작하지 않았어요\n\n"
            "매일 18:00에 자동 실행되도록 cron이 설정되어 있지만,\n"
            "실제로 자동 트리거된 기록이 없습니다.\n"
            f"(수동 실행은 별개. 확인 시각: {now_kst})\n\n"
            "▶︎ 점검\n"
            "  • GitHub Actions에서 monitor.yml 활성 상태인지\n"
            f"  • {manual}"
        )

    last_kst = latest["created_at"].astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    if verdict == "stale":
        delay_str = humanize_delta(delta_h)
        return (
            f"🚨 부동산 데이터 수집이 {delay_str}째 트리거되지 않았어요\n\n"
            "매일 18:00에 돌아야 할 자동 수집이 멈춘 상태입니다.\n"
            f"(허용 지연: {humanize_delta(STALE_THRESHOLD_HOURS)})\n\n"
            f"마지막 실행  {last_kst}\n"
            f"현재         {now_kst}\n\n"
            f"{manual}"
        )

    # verdict == "failed": 트리거는 됐으나 success가 아님 (타임아웃 취소·예외 등)
    conclusion = latest.get("conclusion") or "미완료/취소"
    return (
        f"🚨 부동산 데이터 수집이 실패했어요 (결과: {conclusion})\n\n"
        "자동 실행은 트리거됐지만 정상 종료하지 못했습니다.\n"
        "(예: 외부 API 지연으로 인한 타임아웃 취소)\n\n"
        f"실행 시각  {last_kst}\n"
        f"확인 시각  {now_kst}\n\n"
        "▶︎ 점검: GitHub Actions에서 monitor.yml 최근 run 로그 확인\n"
        f"{manual}"
    )


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    gh_token = os.environ["GH_TOKEN"]
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    latest = fetch_latest_scheduled_run(repo=repo, token=gh_token)
    now = datetime.now(timezone.utc)

    verdict, delta_h = evaluate_health(latest, now=now, threshold_hours=STALE_THRESHOLD_HOURS)

    if verdict == "ok":
        print(f"OK latest={latest} delta_h={delta_h} threshold={STALE_THRESHOLD_HOURS}")
        return 0

    alert_text = build_alert_text(verdict, latest, delta_h, now=now, repo=repo)
    send_telegram(token=bot_token, chat_id=chat_id, text=alert_text)
    print(f"ALERT verdict={verdict} latest={latest} delta_h={delta_h}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
