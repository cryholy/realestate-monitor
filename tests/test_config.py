import json
import pytest

from monitor import load_config


def test_load_config_returns_dict(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "complexes": [],
        "size_ranges": {"84": [83.0, 85.5]},
        "max_price_만원": 200000,
        "rent_lookback_days": 90,
        "rent_min_samples": 5,
        "include_월세": False,
        "telegram_chat_id": "1",
    }), encoding="utf-8")

    cfg = load_config(str(cfg_file))

    assert cfg["max_price_만원"] == 200000
    assert cfg["size_ranges"]["84"] == [83.0, 85.5]


def test_load_config_missing_required_key_raises(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"complexes": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="필수 키"):
        load_config(str(cfg_file))
