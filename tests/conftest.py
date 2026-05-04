import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sale_xml():
    return (FIXTURES_DIR / "sale_response.xml").read_text(encoding="utf-8")


@pytest.fixture
def rent_xml():
    return (FIXTURES_DIR / "rent_response.xml").read_text(encoding="utf-8")


@pytest.fixture
def empty_xml():
    return (FIXTURES_DIR / "empty_response.xml").read_text(encoding="utf-8")


@pytest.fixture
def sample_config():
    return {
        "complexes": [
            {
                "key": "seoulsupp_1",
                "display_name": "서울숲푸르지오",
                "lawd_cd": "11200",
                "법정동": "성수동1가",
                "name_patterns": ["서울숲푸르지오"],
                "exclude_patterns": ["2차", "Ⅱ", "시티"],
            },
        ],
        "size_ranges": {"59": [58.0, 60.5], "84": [83.0, 85.5]},
        "max_price_만원": 200000,
        "rent_lookback_days": 90,
        "rent_min_samples": 5,
        "include_월세": False,
        "telegram_chat_id": "12345",
    }
