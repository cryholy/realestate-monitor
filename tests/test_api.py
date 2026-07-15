from unittest.mock import patch

import pytest
import requests

from lib.api import (
    parse_xml,
    fetch_sales,
    fetch_rents,
    make_record_id,
    _http_get,
    API_RETRY_BACKOFFS,
)


@patch("lib.api.time.sleep", lambda *_: None)
@patch("lib.api.requests.get")
def test_http_get_retries_bounded_then_raises(mock_get):
    """API가 계속 죽으면 (백오프 수 + 1)회만 시도하고 RuntimeError를 던진다.

    cron 타임아웃의 근본 원인이 '재시도 누적 시간'이므로 시도 횟수를 잠근다.
    """
    mock_get.side_effect = requests.exceptions.ReadTimeout("timed out")

    with pytest.raises(RuntimeError) as exc:
        _http_get("https://example.com", {"a": 1})

    attempts = len(API_RETRY_BACKOFFS) + 1
    assert mock_get.call_count == attempts
    assert f"{attempts}회 시도" in str(exc.value)


def test_parse_xml_sale(sale_xml):
    records = parse_xml(sale_xml, kind="sale")

    assert len(records) == 2

    r0 = records[0]
    assert r0["apt_seq"] == "11000-0001"
    assert r0["apt_name"] == "예시단지A"
    assert r0["umd_nm"] == "가락동"
    assert r0["sgg_cd"] == "11710"
    assert r0["umd_cd"] == "11500"
    assert r0["price_만원"] == 198000
    assert r0["area"] == 84.92
    assert r0["size_label"] == "84"
    assert r0["floor"] == 15
    assert r0["build_year"] == 2018
    assert r0["deal_date"] == "2026-04-28"
    assert r0["dealing_type"] == "중개거래"
    assert r0["buyer_type"] == "개인"
    assert r0["seller_type"] == "개인"
    assert r0["agent_sgg_name"] == "서울 송파구"
    assert r0["is_land_lease"] is False
    assert r0["cancel_date"] is None
    assert r0["road_address"] == "송파대로 345"

    r1 = records[1]
    assert r1["price_만원"] == 175000
    assert r1["size_label"] == "59"
    assert r1["dealing_type"] == "직거래"
    assert r1["buyer_type"] == "법인"


def test_parse_xml_rent(rent_xml):
    records = parse_xml(rent_xml, kind="rent")

    assert len(records) == 3

    r0 = records[0]
    assert r0["apt_seq"] == "11000-0001"
    assert r0["deposit_만원"] == 125000
    assert r0["monthly_rent_만원"] == 0
    assert r0["contract_date"] == "2026-03-15"
    assert r0["contract_type"] == "신규"
    assert r0["contract_term"] == "202504~202704"
    assert r0["pre_deposit_만원"] is None
    assert r0["used_renewal_right"] is False

    r1 = records[1]
    assert r1["contract_type"] == "갱신"
    assert r1["pre_deposit_만원"] == 120000
    assert r1["used_renewal_right"] is True

    r2 = records[2]
    assert r2["monthly_rent_만원"] == 200


def test_ymd_rejects_invalid_calendar_dates():
    """달력상 없는 날짜(2026-02-30·2026-04-31)는 None → Postgres date 거부(INSERT 크래시) 방어.

    deal_date뿐 아니라 cancel_date/register_date도 _yyyymmdd_or_none 경유로 같은 게이트를 탄다.
    """
    from lib.api import _ymd_or_none, _yyyymmdd_or_none

    assert _ymd_or_none("2026", "02", "30") is None
    assert _ymd_or_none("2026", "04", "31") is None
    assert _ymd_or_none("2026", "13", "01") is None
    assert _ymd_or_none("2026", "02", "28") == "2026-02-28"   # 실재하는 날짜는 통과
    assert _ymd_or_none("2024", "02", "29") == "2024-02-29"   # 윤년
    assert _yyyymmdd_or_none("20260230") is None              # cancel/register 경로
    assert _yyyymmdd_or_none("20260610") == "2026-06-10"


def test_parse_xml_sale_drops_invalid_deal_date():
    """무효 달력 날짜 record는 parse_xml에서 필터링돼 DB로 넘어가지 않는다."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode></header><body><items>
  <item><aptSeq>11000-0001</aptSeq><sggCd>11710</sggCd><excluUseAr>84.9</excluUseAr>
        <dealYear>2026</dealYear><dealMonth>2</dealMonth><dealDay>30</dealDay>
        <dealAmount>198,000</dealAmount></item>
</items></body></response>"""
    assert parse_xml(xml, kind="sale") == []


def test_parse_xml_invalid_xml():
    with pytest.raises(ValueError, match="XML"):
        parse_xml("not xml", kind="sale")


def test_parse_xml_gateway_error(error_xml):
    with pytest.raises(RuntimeError, match="게이트웨이"):
        parse_xml(error_xml, kind="sale")


def test_parse_xml_service_error():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>22</resultCode><resultMsg>LIMIT</resultMsg></header><body><items></items></body></response>"""
    with pytest.raises(RuntimeError, match="resultCode=22"):
        parse_xml(xml, kind="sale")


def test_make_record_id_deterministic():
    rec = {
        "apt_seq": "11000-0001",
        "deal_date": "2026-04-28",
        "floor": 15,
        "price_만원": 198000,
        "area": 84.92,
    }
    h1 = make_record_id(rec, kind="sale")
    h2 = make_record_id(rec, kind="sale")
    assert h1 == h2
    assert len(h1) == 40   # sha1 hex


def test_make_record_id_differs_by_kind():
    rec = {
        "apt_seq": "11000-0001",
        "deal_date": "2026-04-28",
        "contract_date": "2026-04-28",
        "floor": 15,
        "price_만원": 198000,
        "deposit_만원": 198000,
        "monthly_rent_만원": 0,
        "area": 84.92,
    }
    sale_id = make_record_id(rec, kind="sale")
    rent_id = make_record_id(rec, kind="rent")
    assert sale_id != rent_id


@patch("lib.api._http_get")
def test_fetch_sales_calls_endpoint(mock_get, sale_xml):
    mock_get.return_value = sale_xml
    records = fetch_sales(lawd_cd="11710", ymd="202604", service_key="DUMMY")

    assert mock_get.call_count == 1
    args, _ = mock_get.call_args
    url, params = args[0], args[1]
    assert "getRTMSDataSvcAptTradeDev" in url
    assert params["LAWD_CD"] == "11710"
    assert params["DEAL_YMD"] == "202604"
    assert params["serviceKey"] == "DUMMY"
    assert len(records) == 2


@patch("lib.api._http_get")
def test_fetch_rents_calls_endpoint(mock_get, rent_xml):
    mock_get.return_value = rent_xml
    records = fetch_rents(lawd_cd="11710", ymd="202603", service_key="DUMMY")

    args, _ = mock_get.call_args
    url = args[0]
    assert "getRTMSDataSvcAptRent" in url
    assert len(records) == 3
