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
