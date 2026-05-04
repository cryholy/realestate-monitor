import pytest
from monitor import normalize, match_complex


def test_normalize_strips_whitespace_and_lowercases():
    assert normalize("서울숲 푸르지오 ") == "서울숲푸르지오"
    assert normalize("LOTTE Castle") == "lottecastle"


@pytest.fixture
def complexes():
    return [
        {
            "key": "seoulsupp_1",
            "lawd_cd": "11200",
            "법정동": "성수동1가",
            "name_patterns": ["서울숲푸르지오"],
            "exclude_patterns": ["2차", "Ⅱ", "시티"],
        },
        {
            "key": "seoulsupp_2",
            "lawd_cd": "11200",
            "법정동": "성수동1가",
            "name_patterns": ["서울숲푸르지오2차", "서울숲푸르지오Ⅱ"],
            "exclude_patterns": [],
        },
    ]


def test_match_basic(complexes):
    record = {"아파트": "서울숲푸르지오", "법정동": "성수동1가"}
    assert match_complex(record, complexes) == "seoulsupp_1"


def test_match_with_whitespace(complexes):
    record = {"아파트": "서울숲 푸르지오", "법정동": "성수동1가"}
    assert match_complex(record, complexes) == "seoulsupp_1"


def test_match_excludes_2차(complexes):
    record = {"아파트": "서울숲푸르지오2차", "법정동": "성수동1가"}
    assert match_complex(record, complexes) == "seoulsupp_2"


def test_match_excludes_시티(complexes):
    record = {"아파트": "서울숲푸르지오시티", "법정동": "성수동1가"}
    assert match_complex(record, complexes) is None


def test_match_wrong_법정동(complexes):
    record = {"아파트": "서울숲푸르지오", "법정동": "성수동2가"}
    assert match_complex(record, complexes) is None
