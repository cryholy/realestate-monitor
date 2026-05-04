from monitor import compute_gap


def make_rent(deposit, days_ago, area=84.92, monthly=0):
    """days_ago일 전 전세 거래 레코드."""
    from datetime import datetime, timedelta
    d = (datetime(2026, 5, 4) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return {
        "아파트": "서울숲푸르지오",
        "법정동": "성수동1가",
        "전용면적": area,
        "보증금": deposit,
        "월세": monthly,
        "계약일": d,
    }


def test_compute_gap_basic():
    sale_price = 198000  # 19억 8천 만원
    rents = [
        make_rent(120000, 10),
        make_rent(125000, 30),
        make_rent(130000, 60),
        make_rent(115000, 80),
        make_rent(135000, 5),
    ]
    info = compute_gap(
        complex_key="seoulsupp_1",
        size_label="84",
        size_range=(83.0, 85.5),
        sale_price=sale_price,
        rent_records=rents,
        lookback_days=90,
        extended_lookback_days=180,
        min_samples=5,
        today="2026-05-04",
    )

    assert info["sample_count"] == 5
    assert info["median_보증금"] == 125000
    assert info["min_보증금"] == 115000
    assert info["max_보증금"] == 135000
    assert info["gap"] == 198000 - 125000
    assert info["used_extended"] is False


def test_compute_gap_uses_extended_when_few_samples():
    rents = [
        make_rent(120000, 10),
        make_rent(125000, 30),
        make_rent(130000, 100),  # 90일 밖
        make_rent(115000, 150),  # 90일 밖
        make_rent(135000, 170),  # 90일 밖
    ]
    info = compute_gap(
        complex_key="seoulsupp_1",
        size_label="84",
        size_range=(83.0, 85.5),
        sale_price=198000,
        rent_records=rents,
        lookback_days=90,
        extended_lookback_days=180,
        min_samples=5,
        today="2026-05-04",
    )
    assert info["used_extended"] is True
    assert info["sample_count"] == 5


def test_compute_gap_insufficient_samples():
    rents = [make_rent(120000, 10)]
    info = compute_gap(
        complex_key="seoulsupp_1",
        size_label="84",
        size_range=(83.0, 85.5),
        sale_price=198000,
        rent_records=rents,
        lookback_days=90,
        extended_lookback_days=180,
        min_samples=5,
        today="2026-05-04",
    )
    assert info["sample_count"] < 5
    assert info["median_보증금"] is None
    assert info["gap"] is None


def test_compute_gap_excludes_월세():
    rents = [
        make_rent(50000, 10, monthly=200),  # 월세 → 제외
        make_rent(120000, 12),
        make_rent(125000, 30),
        make_rent(130000, 60),
        make_rent(115000, 80),
        make_rent(135000, 5),
    ]
    info = compute_gap(
        complex_key="seoulsupp_1",
        size_label="84",
        size_range=(83.0, 85.5),
        sale_price=198000,
        rent_records=rents,
        lookback_days=90,
        extended_lookback_days=180,
        min_samples=5,
        today="2026-05-04",
    )
    assert info["sample_count"] == 5  # 월세 제외 5건
