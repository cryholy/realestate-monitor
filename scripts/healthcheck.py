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
import time
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

# run을 한 건만 받으면 그 한 건이 정말 최신인지 검증할 방법이 없다. 창을 두고 max를
# 취하면 정렬이 깨진 응답에 면역이고, 무엇보다 받은 창 전체를 로그로 남길 수 있다.
# 2026-09-29 그 로그가 오탐의 실체를 밝혔다 — 정렬이 깨진 게 아니라 '부분 결과'였다
# (아래 BAD_VERDICT_RETRIES 참조). 10건이면 일 1회 cadence로 10일치.
RUNS_WINDOW = 10

# 나쁜 소식(ok가 아닌 판정)은 알리기 전에 재조회로 확인한다. 근거는 assess_health 참조.
# ponytail: 2회×10초는 관측 표본이 적어 잡은 값이다. 워크플로 timeout은 5분이라
# 여유가 크다 — 오탐이 남으면 먼저 이 두 값을 올린다.
BAD_VERDICT_RETRIES = 2
BAD_VERDICT_RETRY_DELAY_S = 10


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

    API가 created_at 내림차순으로 준다고 신뢰하지 않는다 — RUNS_WINDOW건을 받아
    max를 취한다. 근거는 RUNS_WINDOW 주석 참조.
    """
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs"
        f"?event=schedule&per_page={RUNS_WINDOW}"
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
    parsed = []
    for r in body.get("workflow_runs", []):
        try:
            parsed.append({
                "created_at": datetime.fromisoformat(
                    r["created_at"].replace("Z", "+00:00")),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
            })
        except Exception as e:
            # 손상된 한 건을 격리한다(collector._fetch_batch와 같은 방침). 여기서
            # 예외로 죽으면 main()이 send_telegram에 도달하지 못해 알림이 한 건도
            # 나가지 않는다 — 감시 장치가 조용히 죽는 최악의 실패다. 창을 10건으로
            # 넓히면서 이 노출면도 10배가 됐으므로 격리가 필수다.
            print(f"run 파싱 실패, 건너뜀: {e!r}")
    if not parsed:
        return None
    latest = max(parsed, key=lambda p: p["created_at"])
    # 진단용. 부분 결과가 얼마나 자주·어떤 모양으로 오는지는 이 로그로만 알 수 있다.
    # 정상이면 연속된 일자가 나오고, 부분 결과면 구간이 통째로 빠진 채 내림차순만
    # 지켜진 창이 나온다. 재조회 로그와 같이 보면 빈도까지 집계된다. 지우지 말 것.
    print(
        f"window({len(parsed)}) "
        f"{[p['created_at'].strftime('%Y-%m-%d %H:%M') for p in parsed]} "
        f"→ latest={latest['created_at'].isoformat()}"
    )
    return latest


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


def assess_health(
    *,
    repo: str,
    token: str,
    fetch=fetch_latest_scheduled_run,
    now_fn=None,
    sleep=time.sleep,
) -> tuple[dict | None, str, float | None]:
    """조회 → 판정. ok가 아니면 재조회로 확인한 뒤 최종 판정을 돌려준다.

    GitHub이 run 목록을 '부분 결과'로 돌려주는 일이 있다(2026-09-23·28·29 관측).
    정렬도 필드도 정상이고 일부 구간만 통째로 빠져 있어, 응답만 보고는 진짜 트리거
    누락과 구분할 방법이 없다. 다만 요청 단위로 발생해서 — 같은 코드·토큰으로
    2시간 간격 두 번 중 한 번만 재현됐다 — 재조회하면 대개 해소된다.

    정상 경로에는 비용이 0이고, 진짜 장애 감지는 최대 RETRIES×DELAY초 늦어질 뿐이다.

    반환: (latest, verdict, delta_h)
    """
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    for attempt in range(BAD_VERDICT_RETRIES + 1):
        if attempt:
            sleep(BAD_VERDICT_RETRY_DELAY_S)
        latest = fetch(repo=repo, token=token)
        verdict, delta_h = evaluate_health(
            latest, now=now_fn(), threshold_hours=STALE_THRESHOLD_HOURS)
        if verdict == "ok":
            if attempt:
                print(f"재조회 {attempt}회 만에 정상 — 직전 판정은 부분 응답이었다")
            return latest, verdict, delta_h
        if attempt < BAD_VERDICT_RETRIES:
            print(f"판정={verdict} — 알리기 전 재조회 {attempt + 1}/{BAD_VERDICT_RETRIES}")
    return latest, verdict, delta_h


def build_alert_text(verdict: str, latest: dict | None, delta_h: float | None, *, now: datetime, repo: str) -> str:
    """verdict별 텔레그램 알림 문구."""
    now_kst = now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    manual = f"▶︎ 수동 실행: gh workflow run monitor.yml --repo {repo}"

    if verdict == "never":
        return (
            "🚨 부동산 데이터 자동 수집이 한 번도 동작하지 않았어요\n\n"
            "매일 18:00경 실행되도록 cron이 설정되어 있지만,\n"
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
            "매일 18:00경 돌아야 할 자동 수집이 멈춘 상태입니다.\n"
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

    latest, verdict, delta_h = assess_health(repo=repo, token=gh_token)
    now = datetime.now(timezone.utc)

    if verdict == "ok":
        print(f"OK latest={latest} delta_h={delta_h} threshold={STALE_THRESHOLD_HOURS}")
        return 0

    alert_text = build_alert_text(verdict, latest, delta_h, now=now, repo=repo)
    send_telegram(token=bot_token, chat_id=chat_id, text=alert_text)
    print(f"ALERT verdict={verdict} latest={latest} delta_h={delta_h}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
