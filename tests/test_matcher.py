from lib.matcher import compute_size_label, SIZE_LABELS


def test_size_label_59():
    assert compute_size_label(58.0) == "59"
    assert compute_size_label(59.97) == "59"
    assert compute_size_label(60.5) == "59"


def test_size_label_84():
    assert compute_size_label(83.0) == "84"
    assert compute_size_label(84.92) == "84"
    assert compute_size_label(85.5) == "84"


def test_size_label_mid():
    assert compute_size_label(60.6) == "mid"
    assert compute_size_label(75.0) == "mid"
    assert compute_size_label(82.99) == "mid"


def test_size_label_other():
    assert compute_size_label(50.0) == "other"
    assert compute_size_label(100.0) == "other"
    assert compute_size_label(85.6) == "other"


from lib.matcher import match_alert_rules


def test_match_apt_seq_and_size():
    record = {"apt_seq": "11000-0001", "size_label": "84"}
    rules = [
        {"id": "r1", "apt_seq": "11000-0001", "size_label": "84", "enabled": True},
        {"id": "r2", "apt_seq": "11000-0001", "size_label": "59", "enabled": True},
        {"id": "r3", "apt_seq": "11200-81",   "size_label": "84", "enabled": True},
    ]
    assert [r["id"] for r in match_alert_rules(record, rules)] == ["r1"]


def test_match_any_size():
    record = {"apt_seq": "11000-0001", "size_label": "other"}
    rules = [
        {"id": "rA", "apt_seq": "11000-0001", "size_label": "any", "enabled": True},
        {"id": "rB", "apt_seq": "11000-0001", "size_label": "84",  "enabled": True},
    ]
    assert [r["id"] for r in match_alert_rules(record, rules)] == ["rA"]


def test_match_disabled_rule_skipped():
    record = {"apt_seq": "11000-0001", "size_label": "84"}
    rules = [
        {"id": "r1", "apt_seq": "11000-0001", "size_label": "84", "enabled": False},
    ]
    assert match_alert_rules(record, rules) == []


def test_match_no_apt_seq_match():
    record = {"apt_seq": "11999-0001", "size_label": "84"}
    rules = [
        {"id": "r1", "apt_seq": "11000-0001", "size_label": "84", "enabled": True},
    ]
    assert match_alert_rules(record, rules) == []
