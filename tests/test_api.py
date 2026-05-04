import pytest
from unittest.mock import patch

from monitor import parse_xml, fetch_sales


def test_parse_xml_sale(sale_xml):
    records = parse_xml(sale_xml, kind="sale")

    assert len(records) == 3
    first = records[0]
    assert first["아파트"] == "서울숲푸르지오"
    assert first["법정동"] == "성수동1가"
    assert first["전용면적"] == 84.92
    assert first["거래금액"] == 198000  # 만원, 콤마 제거 + int
    assert first["거래일"] == "2026-04-28"
    assert first["층"] == 15


def test_parse_xml_empty(empty_xml):
    records = parse_xml(empty_xml, kind="sale")
    assert records == []


def test_parse_xml_invalid_raises():
    with pytest.raises(ValueError, match="XML"):
        parse_xml("not xml at all", kind="sale")


def test_parse_xml_rent(rent_xml):
    records = parse_xml(rent_xml, kind="rent")

    assert len(records) == 3
    pure_jeonse = [r for r in records if r["월세"] == 0]
    assert len(pure_jeonse) == 2
    assert pure_jeonse[0]["보증금"] == 125000
    assert pure_jeonse[0]["계약일"] == "2026-03-15"
    assert pure_jeonse[0]["계약구분"] == "신규"


def test_parse_xml_raises_on_gateway_error():
    """API 게이트웨이 에러 (잘못된 키) — OpenAPI_ServiceResponse 형식."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<OpenAPI_ServiceResponse>
  <cmmMsgHeader>
    <errMsg>SERVICE ERROR</errMsg>
    <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
    <returnReasonCode>30</returnReasonCode>
  </cmmMsgHeader>
</OpenAPI_ServiceResponse>"""
    with pytest.raises(RuntimeError, match="게이트웨이"):
        parse_xml(xml, kind="sale")


def test_parse_xml_raises_on_service_error():
    """서비스 레벨 에러 — resultCode != 00."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>22</resultCode>
    <resultMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_HOUR</resultMsg>
  </header>
  <body><items></items></body>
</response>"""
    with pytest.raises(RuntimeError, match="resultCode=22"):
        parse_xml(xml, kind="sale")


@patch("monitor._api_get")
def test_fetch_sales_calls_endpoint(mock_get, sale_xml):
    mock_get.return_value = sale_xml

    records = fetch_sales("11200", "202604", "DUMMY_KEY")

    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0].endswith("getRTMSDataSvcAptTradeDev")
    assert args[1]["LAWD_CD"] == "11200"
    assert args[1]["DEAL_YMD"] == "202604"
    assert args[1]["serviceKey"] == "DUMMY_KEY"
    assert len(records) == 3
