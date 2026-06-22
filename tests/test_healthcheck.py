"""healthcheck 판정 로직 — GitHub Actions 스케줄 지연(수 시간)에 강건해야 한다.

핵심: '최신 success가 30분 이내인가'라는 단일·과민 검사 대신
  ① 최신 스케줄 run이 staleness 임계값 내 존재하는가 (트리거 누락 감지)
  ② 그 run이 끝났다면 conclusion == success 인가 (취소/실패 즉시 감지)
로 분리한다. ②는 스케줄 지연과 무관하게 정확하므로 오탐의 주범인 ①의 임계값을
넉넉히(>1일) 둬도 실제 실패를 당일에 잡는다.
"""
from datetime import datetime, timedelta, timezone

from scripts.healthcheck import evaluate_health

UTC = timezone.utc
NOW = datetime(2026, 6, 16, 9, 30, tzinfo=UTC)


def _run(hours_ago, *, status="completed", conclusion="success"):
    return {
        "created_at": NOW - timedelta(hours=hours_ago),
        "status": status,
        "conclusion": conclusion,
    }


def test_ok_when_recent_success():
    verdict, _ = evaluate_health(_run(0.4), now=NOW, threshold_hours=36)
    assert verdict == "ok"


def test_ok_despite_hours_of_schedule_jitter():
    # cron이 어제 정시에 돌고 healthcheck가 11시간 지각 → 35h 경과지만 정상이어야 한다.
    verdict, _ = evaluate_health(_run(35), now=NOW, threshold_hours=36)
    assert verdict == "ok"


def test_stale_when_no_run_within_threshold():
    verdict, delta_h = evaluate_health(_run(40), now=NOW, threshold_hours=36)
    assert verdict == "stale"
    assert round(delta_h) == 40


def test_failed_when_latest_run_cancelled_recently():
    # 06-15/06-16처럼 cron이 타임아웃 취소된 경우: run은 최근이지만 success가 아니다.
    verdict, _ = evaluate_health(
        _run(0.4, conclusion="cancelled"), now=NOW, threshold_hours=36
    )
    assert verdict == "failed"


def test_ok_when_latest_run_still_in_progress():
    # healthcheck가 cron 완료 전에 떴을 때(레이스) conclusion=None → 오탐 금지.
    verdict, _ = evaluate_health(
        _run(0.1, status="in_progress", conclusion=None), now=NOW, threshold_hours=36
    )
    assert verdict == "ok"


def test_never_when_no_run_at_all():
    verdict, delta_h = evaluate_health(None, now=NOW, threshold_hours=36)
    assert verdict == "never"
    assert delta_h is None
