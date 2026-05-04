"""부동산 실거래가·전월세 모니터링."""
import json
import os
import time
import xml.etree.ElementTree as ET

import requests

REQUIRED_CONFIG_KEYS = {
    "complexes",
    "size_ranges",
    "max_price_만원",
    "rent_lookback_days",
    "rent_min_samples",
    "include_월세",
    "telegram_chat_id",
}


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    missing = REQUIRED_CONFIG_KEYS - set(cfg.keys())
    if missing:
        raise ValueError(f"config.json에 필수 키 누락: {sorted(missing)}")

    return cfg


def parse_xml(xml_text: str, kind: str) -> list[dict]:
    """국토부 실거래가 API 응답 파싱.

    kind: "sale" | "rent"
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"XML 파싱 실패: {e}") from e

    items = root.findall(".//item")
    records = []
    for item in items:
        if kind == "sale":
            records.append(_parse_sale_item(item))
        elif kind == "rent":
            records.append(_parse_rent_item(item))
        else:
            raise ValueError(f"알 수 없는 kind: {kind}")
    return records


def _text(item, tag: str) -> str:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else ""


def _parse_sale_item(item) -> dict:
    year = _text(item, "거래년도")
    month = _text(item, "거래월").zfill(2)
    day = _text(item, "거래일").zfill(2)
    price_raw = _text(item, "거래금액").replace(",", "").replace(" ", "")
    return {
        "아파트": _text(item, "아파트"),
        "법정동": _text(item, "법정동"),
        "전용면적": float(_text(item, "전용면적")),
        "거래금액": int(price_raw) if price_raw else 0,
        "거래일": f"{year}-{month}-{day}",
        "층": int(_text(item, "층") or 0),
        "지역코드": _text(item, "지역코드"),
        "건축년도": _text(item, "건축년도"),
    }


def _parse_rent_item(item) -> dict:
    date_raw = _text(item, "계약년월일")
    deal_date = (
        f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}" if len(date_raw) == 8 else ""
    )
    deposit_raw = _text(item, "보증금액").replace(",", "").replace(" ", "")
    monthly_raw = _text(item, "월세금액").replace(",", "").replace(" ", "")
    return {
        "아파트": _text(item, "아파트"),
        "법정동": _text(item, "법정동"),
        "전용면적": float(_text(item, "전용면적")),
        "보증금": int(deposit_raw) if deposit_raw else 0,
        "월세": int(monthly_raw) if monthly_raw else 0,
        "계약일": deal_date,
        "계약구분": _text(item, "계약구분"),
        "층": int(_text(item, "층") or 0),
        "지역코드": _text(item, "지역코드"),
    }


SALE_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
RENT_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

API_TIMEOUT = 15
API_RETRY_BACKOFFS = [1, 3, 10]


def _api_get(url: str, params: dict) -> str:
    last_exc = None
    for delay in [0] + API_RETRY_BACKOFFS:
        if delay:
            time.sleep(delay)
        try:
            resp = requests.get(url, params=params, timeout=API_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            last_exc = e
            continue
    raise RuntimeError(f"API 호출 실패 (4회 시도): {url} — {last_exc}")


def fetch_sales(lawd_cd: str, ymd: str, service_key: str) -> list[dict]:
    """매매 거래 조회. ymd: YYYYMM."""
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": ymd,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    xml_text = _api_get(SALE_ENDPOINT, params)
    return parse_xml(xml_text, kind="sale")


def fetch_rents(lawd_cd: str, ymd: str, service_key: str) -> list[dict]:
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": ymd,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    xml_text = _api_get(RENT_ENDPOINT, params)
    return parse_xml(xml_text, kind="rent")
