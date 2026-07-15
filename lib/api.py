"""국토교통부 실거래가 API 클라이언트 (매매 + 전월세)."""
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional

import requests

# serviceKey 값(인코딩/비인코딩 모두)을 로그·예외에서 마스킹. GH secret 마스킹은
# %2B/%2F/%3D로 인코딩된 키를 놓치므로 파이썬 레벨에서 직접 제거한다.
_SERVICE_KEY_RE = re.compile(r"(serviceKey=)[^&\s'\"()]*", re.IGNORECASE)


def _mask_service_key(text: str) -> str:
    return _SERVICE_KEY_RE.sub(r"\1[REDACTED]", text)

from lib.matcher import compute_size_label

SALE_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
RENT_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

API_TIMEOUT = 15
# 4회→3회 시도로 축소. 최장 10초 백오프 꼬리를 제거해 fetch 1건당 최악 소요를
# 74초→52초로 낮춘다(서킷 브레이커와 함께 cron 타임아웃 취소를 방지). read timeout(15s)은
# '느리지만 동작하는' 정부 API를 끊지 않도록 유지.
API_RETRY_BACKOFFS = [2, 5]


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else ""


def _int_or_none(s: str) -> Optional[int]:
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _ymd_or_none(year: str, month: str, day: str) -> Optional[str]:
    """y/m/d 문자열 → 'YYYY-MM-DD' 또는 None (달력상 실재하는 날짜만 통과).

    date()가 2026-02-30·2026-04-31 등 Postgres `date` 컬럼이 거부할 무효 날짜를
    걸러낸다. deal_date·contract_date·cancel_date·register_date 네 컬럼이 모두
    이 지점을 경유하므로 여기 한 곳만 막으면 전 date 컬럼이 방어된다.
    """
    try:
        y, m, d = int(year), int(month), int(day)
        if not (1900 <= y <= 2100):
            return None
        return date(y, m, d).isoformat()
    except (ValueError, TypeError):
        return None


def _yyyymmdd_or_none(s: str) -> Optional[str]:
    """8자리 YYYYMMDD 문자열 → 'YYYY-MM-DD' 또는 None."""
    if not s or len(s) != 8 or not s.isdigit():
        return None
    return _ymd_or_none(s[:4], s[4:6], s[6:8])


def _parse_sale_item(item: ET.Element) -> dict:
    deal_date = _ymd_or_none(
        _text(item, "dealYear"),
        _text(item, "dealMonth"),
        _text(item, "dealDay"),
    )

    cancel_date = _yyyymmdd_or_none(_text(item, "cdealDay"))
    register_date = _yyyymmdd_or_none(_text(item, "rgstDate"))

    road_bonbun = _text(item, "roadNmBonbun").lstrip("0") or "0"
    road_bubun = _text(item, "roadNmBubun").lstrip("0")
    road_nm = _text(item, "roadNm")
    if road_nm:
        road_address = f"{road_nm} {road_bonbun}"
        if road_bubun:
            road_address += f"-{road_bubun}"
    else:
        road_address = None

    area = float(_text(item, "excluUseAr") or 0)

    return {
        "apt_seq":         _text(item, "aptSeq"),
        "apt_name":        _text(item, "aptNm"),
        "umd_nm":          _text(item, "umdNm"),
        "umd_cd":          _text(item, "umdCd") or None,
        "sgg_cd":          _text(item, "sggCd"),
        "jibun":           _text(item, "jibun") or None,
        "road_address":    road_address,
        "deal_date":       deal_date,
        "price_만원":       _int_or_none(_text(item, "dealAmount")) or 0,
        "area":            area,
        "size_label":      compute_size_label(area),
        "floor":           _int_or_none(_text(item, "floor")),
        "build_year":      _int_or_none(_text(item, "buildYear")),
        "dealing_type":    _text(item, "dealingGbn") or None,
        "buyer_type":      _text(item, "buyerGbn") or None,
        "seller_type":     _text(item, "slerGbn") or None,
        "agent_sgg_name":  _text(item, "estateAgentSggNm") or None,
        "is_land_lease":   _text(item, "landLeaseholdGbn") == "Y",
        "cancel_date":     cancel_date,
        "cancel_type":     _text(item, "cdealType") or None,
        "register_date":   register_date,
    }


def _parse_rent_item(item: ET.Element) -> dict:
    contract_date = _ymd_or_none(
        _text(item, "dealYear"),
        _text(item, "dealMonth"),
        _text(item, "dealDay"),
    )
    area = float(_text(item, "excluUseAr") or 0)

    return {
        "apt_seq":              _text(item, "aptSeq"),
        "apt_name":             _text(item, "aptNm"),
        "umd_nm":               _text(item, "umdNm"),
        "sgg_cd":               _text(item, "sggCd"),
        "contract_date":        contract_date,
        "deposit_만원":          _int_or_none(_text(item, "deposit")) or 0,
        "monthly_rent_만원":     _int_or_none(_text(item, "monthlyRent")) or 0,
        "area":                 area,
        "size_label":           compute_size_label(area),
        "floor":                _int_or_none(_text(item, "floor")),
        "build_year":           _int_or_none(_text(item, "buildYear")),
        "contract_type":        _text(item, "contractType") or None,
        "contract_term":        _text(item, "contractTerm") or None,
        "pre_deposit_만원":      _int_or_none(_text(item, "preDeposit")),
        "pre_monthly_rent_만원": _int_or_none(_text(item, "preMonthlyRent")),
        "used_renewal_right":   _text(item, "useRRRight") == "사용",
    }


def parse_xml(xml_text: str, kind: str) -> list[dict]:
    """국토부 API 응답 파싱.

    kind: 'sale' | 'rent'

    오류 응답:
    - 게이트웨이 에러 (returnReasonCode) → RuntimeError
    - 서비스 에러 (resultCode != 0) → RuntimeError
    - XML parse 실패 → ValueError
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"XML 파싱 실패: {e}") from e

    reason_el = root.find(".//returnReasonCode")
    if reason_el is not None and reason_el.text:
        auth = root.findtext(".//returnAuthMsg") or ""
        err = root.findtext(".//errMsg") or ""
        msg = auth.strip() or err.strip()
        raise RuntimeError(f"API 게이트웨이 오류 reasonCode={reason_el.text.strip()} ({msg})")

    code_el = root.find(".//resultCode")
    if code_el is not None and code_el.text:
        code = code_el.text.strip()
        if code.lstrip("0") != "":
            msg = (root.findtext(".//resultMsg") or "").strip()
            raise RuntimeError(f"API 오류 resultCode={code} ({msg})")

    if kind == "sale":
        parser = _parse_sale_item
        date_field = "deal_date"
    elif kind == "rent":
        parser = _parse_rent_item
        date_field = "contract_date"
    else:
        raise ValueError(f"알 수 없는 kind: {kind}")

    # date 파싱 실패한 record는 DB INSERT 불가 (NOT NULL) → 필터링
    return [r for r in (parser(item) for item in root.findall(".//item")) if r.get(date_field)]


def make_record_id(record: dict, kind: str) -> str:
    """record의 결정적 sha1 ID. UPSERT의 PK로 사용."""
    if kind == "sale":
        key = "|".join([
            "sale",
            record["apt_seq"] or "",
            record["deal_date"] or "",
            str(record.get("floor") or 0),
            str(record["price_만원"]),
            f"{record['area']:.2f}",
        ])
    elif kind == "rent":
        key = "|".join([
            "rent",
            record["apt_seq"] or "",
            record["contract_date"] or "",
            str(record.get("floor") or 0),
            str(record["deposit_만원"]),
            str(record["monthly_rent_만원"]),
            f"{record['area']:.2f}",
        ])
    else:
        raise ValueError(f"알 수 없는 kind: {kind}")
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _http_get(url: str, params: dict) -> str:
    delays = [0] + API_RETRY_BACKOFFS
    last_exc = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            resp = requests.get(url, params=params, timeout=API_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            last_exc = e
            continue
    raise RuntimeError(_mask_service_key(f"API 호출 실패 ({len(delays)}회 시도): {url} — {last_exc}"))


def fetch_sales(*, lawd_cd: str, ymd: str, service_key: str) -> list[dict]:
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": ymd,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    xml_text = _http_get(SALE_ENDPOINT, params)
    return parse_xml(xml_text, kind="sale")


def fetch_rents(*, lawd_cd: str, ymd: str, service_key: str) -> list[dict]:
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": ymd,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    xml_text = _http_get(RENT_ENDPOINT, params)
    return parse_xml(xml_text, kind="rent")
