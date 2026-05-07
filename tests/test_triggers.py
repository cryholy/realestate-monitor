from lib.triggers import (
    evaluate_price_threshold,
    evaluate_jeonse_ratio,
    PriceCandidate,
    JeonseCandidate,
)


def test_evaluate_price_below_threshold():
    record = {"id": "abc123", "apt_seq": "11000-0001", "size_label": "84",
              "price_만원": 198000, "deal_date": "2026-04-28", "floor": 15}
    rule = {"id": "rule1", "apt_seq": "11000-0001", "size_label": "84",
            "max_price_만원": 200000, "enabled": True, "display_name": "예시단지A"}

    cands = evaluate_price_threshold([record], [rule])

    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, PriceCandidate)
    assert c.rule_id == "rule1"
    assert c.dedup_key == "sale:abc123"
    assert c.record == record
    assert c.rule == rule


def test_evaluate_price_above_threshold():
    record = {"id": "abc", "apt_seq": "11000-0001", "size_label": "84",
              "price_만원": 220000, "deal_date": "2026-04-28", "floor": 15}
    rule = {"id": "r1", "apt_seq": "11000-0001", "size_label": "84",
            "max_price_만원": 200000, "enabled": True, "display_name": "X"}

    assert evaluate_price_threshold([record], [rule]) == []


def test_evaluate_price_skipped_when_max_price_null():
    record = {"id": "abc", "apt_seq": "11000-0001", "size_label": "84",
              "price_만원": 100000, "deal_date": "2026-04-28", "floor": 15}
    rule = {"id": "r1", "apt_seq": "11000-0001", "size_label": "84",
            "max_price_만원": None, "enabled": True, "display_name": "X"}

    assert evaluate_price_threshold([record], [rule]) == []


def test_evaluate_jeonse_ratio_above_threshold():
    rule = {"id": "r1", "apt_seq": "11000-0001", "size_label": "84",
            "min_jeonse_ratio": 0.65, "enabled": True, "display_name": "예시단지A"}

    cands = evaluate_jeonse_ratio(
        rules=[rule],
        median_sale_fn=lambda **kw: (200000, 8),
        median_jeonse_fn=lambda **kw: (132000, 14),
        today="2026-05-04",
    )

    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, JeonseCandidate)
    assert c.rule_id == "r1"
    assert c.dedup_key == "jeonse:2026-05"
    assert c.ratio == 0.66
    assert c.median_sale == 200000
    assert c.median_jeonse == 132000


def test_evaluate_jeonse_ratio_below_threshold():
    rule = {"id": "r1", "apt_seq": "11000-0001", "size_label": "84",
            "min_jeonse_ratio": 0.65, "enabled": True, "display_name": "X"}

    cands = evaluate_jeonse_ratio(
        rules=[rule],
        median_sale_fn=lambda **kw: (200000, 8),
        median_jeonse_fn=lambda **kw: (120000, 10),
        today="2026-05-04",
    )

    assert cands == []


def test_evaluate_jeonse_ratio_insufficient_samples():
    rule = {"id": "r1", "apt_seq": "11000-0001", "size_label": "84",
            "min_jeonse_ratio": 0.65, "enabled": True, "display_name": "X"}

    cands = evaluate_jeonse_ratio(
        rules=[rule],
        median_sale_fn=lambda **kw: (200000, 3),
        median_jeonse_fn=lambda **kw: (132000, 14),
        today="2026-05-04",
    )

    assert cands == []


def test_evaluate_jeonse_ratio_skipped_when_min_null():
    rule = {"id": "r1", "apt_seq": "11000-0001", "size_label": "84",
            "min_jeonse_ratio": None, "enabled": True, "display_name": "X"}

    cands = evaluate_jeonse_ratio(
        rules=[rule],
        median_sale_fn=lambda **kw: (200000, 8),
        median_jeonse_fn=lambda **kw: (132000, 14),
        today="2026-05-04",
    )

    assert cands == []
