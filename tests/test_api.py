from unittest.mock import patch

import pytest

from lib.api import parse_xml, fetch_sales, fetch_rents, make_record_id


def test_parse_xml_sale(sale_xml):
    records = parse_xml(sale_xml, kind="sale")

    assert len(records) == 2

    r0 = records[0]
    assert r0["apt_seq"] == "11710-2412"
    assert r0["apt_name"] == "헬리오시티"
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
    assert r0["apt_seq"] == "11710-2412"
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
        "apt_seq": "11710-2412",
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
        "apt_seq": "11710-2412",
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
    url, params = args[0], args[1]
    assert "getRTMSDataSvcAptRent" in url
    assert len(records) == 3
