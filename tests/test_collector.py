"""collect_records — 외부 API 장애 내성.

cron 타임아웃 취소의 근본 원인: API가 죽어도 36개 fetch를 전부 풀 재시도로 시도해
누적 시간이 10분 job 타임아웃을 넘긴다. 대책:
  ① 서킷 브레이커 — 연속 N개 구가 통째로 실패하면 'API 다운'으로 보고 조기 종료
  ② 점진 저장 — 구 단위로 즉시 persist 해 중간 취소돼도 받은 만큼 보존
"""
from collector import collect_records, DISTRICT_LAWD_CDS


def _sale(lawd_cd):
    return {"apt_seq": lawd_cd, "deal_date": "2026-06-01", "price_만원": 1, "area": 1.0}


def _rent(lawd_cd):
    return {"apt_seq": lawd_cd, "contract_date": "2026-06-01",
            "deposit_만원": 1, "monthly_rent_만원": 0, "area": 1.0}


def test_aborts_after_consecutive_district_failures():
    attempted = []

    def failing(*, lawd_cd, ymd, service_key):
        attempted.append(lawd_cd)
        raise RuntimeError("API down")

    sales, rents, aborted = collect_records(
        "KEY", months=1,
        max_consecutive_failures=3,
        fetch_sales=failing, fetch_rents=failing,
        sleep=lambda *_: None,
    )

    assert aborted is True
    assert sales == [] and rents == []
    # 9개 구 전부가 아니라 연속 3개 구에서 멈춰야 한다.
    assert len(set(attempted)) == 3


def test_persists_each_district_incrementally():
    persisted = []

    sales, rents, aborted = collect_records(
        "KEY", months=1,
        persist=lambda table, recs: persisted.append((table, len(recs))),
        fetch_sales=lambda *, lawd_cd, ymd, service_key: [_sale(lawd_cd)],
        fetch_rents=lambda *, lawd_cd, ymd, service_key: [_rent(lawd_cd)],
        sleep=lambda *_: None,
    )

    assert aborted is False
    n = len(DISTRICT_LAWD_CDS)
    # 루프 종료 후 한 번이 아니라, 구마다 sale/rent 각각 즉시 저장돼야 한다.
    assert persisted.count(("sale_records", 1)) == n
    assert persisted.count(("rent_records", 1)) == n
    assert len(sales) == n and len(rents) == n


def test_persist_failure_isolated_per_district():
    # 한 구의 persist가 던져도(upsert 재시도 소진 등) 전체가 죽지 않고 나머지 구는 계속 저장.
    ok_saves = []

    def persist(table, recs):
        if recs[0]["apt_seq"] == DISTRICT_LAWD_CDS[0][0]:
            raise RuntimeError("DB rejected batch (bad row)")
        ok_saves.append((table, recs[0]["apt_seq"]))

    sales, rents, aborted = collect_records(
        "KEY", months=1,
        persist=persist,
        fetch_sales=lambda *, lawd_cd, ymd, service_key: [_sale(lawd_cd)],
        fetch_rents=lambda *, lawd_cd, ymd, service_key: [_rent(lawd_cd)],
        sleep=lambda *_: None,
    )

    assert aborted is False   # 한 배치 실패가 크래시로 번지지 않는다(요약 하트비트 생존)
    # 첫 구(sale·rent 둘 다)만 실패, 나머지 8개 구는 sale/rent 각각 저장됐다.
    n = len(DISTRICT_LAWD_CDS)
    assert len(ok_saves) == (n - 1) * 2
    assert len(sales) == n and len(rents) == n   # 수집 자체(메모리 누적)는 전량


def test_does_not_abort_when_failures_not_consecutive():
    # sale은 항상 성공, rent만 실패 → 구마다 부분 성공이라 연속-실패 카운터가 리셋된다.
    def fail_rent(*, lawd_cd, ymd, service_key):
        raise RuntimeError("rent down")

    sales, rents, aborted = collect_records(
        "KEY", months=1,
        max_consecutive_failures=3,
        fetch_sales=lambda *, lawd_cd, ymd, service_key: [_sale(lawd_cd)],
        fetch_rents=fail_rent,
        sleep=lambda *_: None,
    )

    assert aborted is False
    assert len(sales) == len(DISTRICT_LAWD_CDS)   # 모든 구를 시도했다


def test_log_egress_ip_swallows_failure(monkeypatch):
    """진단용 IP 조회 실패가 수집 본체를 죽이지 않는다.

    log_egress_ip는 main() 최상단에서 돌기 때문에, 여기서 예외가 새면
    수집·알림 전체가 시작조차 못 한다. 부가 진단이 본체보다 중요해질 일은 없다.
    """
    import collector

    def boom(*a, **k):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(collector.requests, "get", boom)
    collector.log_egress_ip()   # 예외가 새어나오면 테스트 실패


def test_log_egress_ip_logs_the_ip(monkeypatch, caplog):
    """정상 조회 시 IP가 로그에 남는다 (성공/실패 run 대조의 근거)."""
    import logging
    import collector

    class _Resp:
        text = " 20.1.2.3 \n"

    monkeypatch.setattr(collector.requests, "get", lambda *a, **k: _Resp())
    with caplog.at_level(logging.INFO, logger="collector"):
        collector.log_egress_ip()

    assert "20.1.2.3" in caplog.text
