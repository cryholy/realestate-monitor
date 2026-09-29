"""healthcheck 판정 로직 — GitHub Actions 스케줄 지연(수 시간)에 강건해야 한다.

핵심: '최신 success가 30분 이내인가'라는 단일·과민 검사 대신
  ① 최신 스케줄 run이 staleness 임계값 내 존재하는가 (트리거 누락 감지)
  ② 그 run이 끝났다면 conclusion == success 인가 (취소/실패 즉시 감지)
로 분리한다. ②는 스케줄 지연과 무관하게 정확하므로 오탐의 주범인 ①의 임계값을
넉넉히(>1일) 둬도 실제 실패를 당일에 잡는다.
"""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from scripts import healthcheck
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


class _FakeResponse:
    """urlopen의 컨텍스트 매니저 응답 대역."""

    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_fetch_picks_newest_even_when_response_is_unsorted(monkeypatch):
    """2026-09-23·09-28 러너 오탐 재현.

    두 날 모두 응답 0번이 2026-09-14 run이었고 코드가 그걸 '최신'으로 믿어
    verdict=stale 오탐을 냈다. API의 정렬을 신뢰하지 말고 항상 max를 취해야 한다.
    """
    payload = {
        "workflow_runs": [
            {"created_at": "2026-09-14T15:20:35Z", "status": "completed",
             "conclusion": "success"},
            {"created_at": "2026-09-28T17:06:58Z", "status": "completed",
             "conclusion": "success"},
        ]
    }
    monkeypatch.setattr(
        healthcheck.urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResponse(payload),
    )

    latest = healthcheck.fetch_latest_scheduled_run(repo="o/r", token="t")

    assert latest["created_at"] == datetime(2026, 9, 28, 17, 6, 58, tzinfo=UTC)


def test_fetch_requests_a_window_not_a_single_run(monkeypatch):
    """per_page=1이면 max()의 대상이 1건뿐이라 정렬 방어가 무효가 된다.

    누군가 창 크기를 1로 되돌리면 위 테스트는 여전히 통과하지만 프로덕션 방어는
    사라진다. 그 조용한 퇴행을 막기 위해 창 크기 자체를 잠근다.
    """
    seen = {}

    def _fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _FakeResponse({"workflow_runs": []})

    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _fake_urlopen)

    healthcheck.fetch_latest_scheduled_run(repo="o/r", token="t")

    per_page = int(parse_qs(urlparse(seen["url"]).query)["per_page"][0])
    assert per_page > 1


def test_fetch_survives_a_malformed_run_in_the_window(monkeypatch):
    """창 안의 손상된 항목 하나가 감시 장치 전체를 죽이면 안 된다.

    파싱에서 예외가 나면 main()이 send_telegram에 도달하지 못해 알림이 한 건도
    나가지 않는다 — 감시 장치가 조용히 죽는, 가장 나쁜 방향의 실패다.
    창을 1건에서 10건으로 넓히면서 이 노출면도 10배가 됐다.
    """
    payload = {
        "workflow_runs": [
            {"status": "completed", "conclusion": "success"},  # created_at 없음
            {"created_at": None, "status": "completed", "conclusion": "success"},
            {"created_at": "not-a-timestamp", "status": "completed",
             "conclusion": "success"},
            {"created_at": "2026-09-28T17:06:58Z", "status": "completed",
             "conclusion": "success"},
        ]
    }
    monkeypatch.setattr(
        healthcheck.urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResponse(payload),
    )

    latest = healthcheck.fetch_latest_scheduled_run(repo="o/r", token="t")

    assert latest["created_at"] == datetime(2026, 9, 28, 17, 6, 58, tzinfo=UTC)
