from monitor import filter_size, filter_price


SIZE_RANGES = {"59": [58.0, 60.5], "84": [83.0, 85.5]}


def test_filter_size_84_inclusive():
    assert filter_size({"전용면적": 84.92}, SIZE_RANGES) == "84"
    assert filter_size({"전용면적": 83.0}, SIZE_RANGES) == "84"
    assert filter_size({"전용면적": 85.5}, SIZE_RANGES) == "84"


def test_filter_size_59():
    assert filter_size({"전용면적": 59.97}, SIZE_RANGES) == "59"


def test_filter_size_out_of_range():
    assert filter_size({"전용면적": 75.0}, SIZE_RANGES) is None
    assert filter_size({"전용면적": 100.0}, SIZE_RANGES) is None


def test_filter_price_under():
    assert filter_price({"거래금액": 198000}, 200000) is True


def test_filter_price_at_threshold():
    """20억 정확히는 임계값 미만이 아니므로 제외 (< 20억)."""
    assert filter_price({"거래금액": 200000}, 200000) is False


def test_filter_price_over():
    assert filter_price({"거래금액": 250000}, 200000) is False
