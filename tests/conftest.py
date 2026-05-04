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
def error_xml():
    return (FIXTURES_DIR / "error_response.xml").read_text(encoding="utf-8")
