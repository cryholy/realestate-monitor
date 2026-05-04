"""부동산 실거래가·전월세 모니터링."""
import argparse
import json
import logging
import os
import statistics
import sys
import time
import xml.etree.ElementTree as ET
import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

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

    resultCode가 "00"이 아니면 RuntimeError 발생 (silent failure 방지).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"XML 파싱 실패: {e}") from e

    # 게이트웨이 에러 (잘못된 키 등) — 응답 root가 OpenAPI_ServiceResponse
    reason_el = root.find(".//returnReasonCode")
    if reason_el is not None and reason_el.text:
        auth_el = root.find(".//returnAuthMsg")
        err_el = root.find(".//errMsg")
        msg = (auth_el.text if auth_el is not None and auth_el.text else "") or (
            err_el.text if err_el is not None and err_el.text else ""
        )
        raise RuntimeError(f"API 게이트웨이 오류 reasonCode={reason_el.text.strip()} ({msg})")

    # 서비스 레벨 에러 (한도 초과 등) — resultCode != "00"
    code_el = root.find(".//resultCode")
    if code_el is not None and code_el.text and code_el.text.strip() != "00":
        msg_el = root.find(".//resultMsg")
        msg = msg_el.text.strip() if msg_el is not None and msg_el.text else ""
        raise RuntimeError(f"API 오류 resultCode={code_el.text.strip()} ({msg})")

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


def normalize(name: str) -> str:
    return "".join(name.split()).lower()


def match_complex(record: dict, complexes: list[dict]) -> str | None:
    """매칭되는 단지의 key 반환, 없으면 None.

    동일 record가 두 단지 정의 모두에 매칭되면 더 구체적인(=2차 같은) 정의가 우선되도록
    name_patterns 길이가 긴 정의를 먼저 평가한다.
    """
    name_norm = normalize(record["아파트"])
    법정동 = record["법정동"].strip()

    sorted_complexes = sorted(
        complexes,
        key=lambda c: -max((len(p) for p in c.get("name_patterns", [])), default=0),
    )

    for complex_def in sorted_complexes:
        if complex_def["법정동"] != 법정동:
            continue
        patterns = [normalize(p) for p in complex_def.get("name_patterns", [])]
        excludes = [normalize(p) for p in complex_def.get("exclude_patterns", [])]
        if not any(p in name_norm for p in patterns):
            continue
        if any(e in name_norm for e in excludes):
            continue
        return complex_def["key"]
    return None


def filter_size(record: dict, size_ranges: dict) -> str | None:
    """전용면적이 어느 라벨(예: '84')에 속하는지 반환, 없으면 None."""
    area = record["전용면적"]
    for label, (lo, hi) in size_ranges.items():
        if lo <= area <= hi:
            return label
    return None


def filter_price(record: dict, max_price_만원: int) -> bool:
    """거래금액이 임계값 미만이면 True."""
    return record["거래금액"] < max_price_만원


def compute_gap(
    *,
    complex_key: str,
    size_label: str,
    size_range: tuple[float, float],
    sale_price: int,
    rent_records: list[dict],
    lookback_days: int,
    extended_lookback_days: int,
    min_samples: int,
    today: str,
) -> dict:
    """매매가 대비 직전 90일 전세 보증금 중위값 + 갭 정보 반환."""
    today_dt = datetime.fromisoformat(today)

    def _filter(records, days):
        cutoff = today_dt - timedelta(days=days)
        return [
            r for r in records
            if r.get("월세", 0) == 0
            and size_range[0] <= r["전용면적"] <= size_range[1]
            and r.get("계약일")
            and datetime.fromisoformat(r["계약일"]) >= cutoff
        ]

    pool = _filter(rent_records, lookback_days)
    used_extended = False
    if len(pool) < min_samples:
        pool = _filter(rent_records, extended_lookback_days)
        used_extended = True

    if len(pool) < min_samples:
        return {
            "sample_count": len(pool),
            "median_보증금": None,
            "min_보증금": None,
            "max_보증금": None,
            "gap": None,
            "used_extended": used_extended,
            "lookback_days_actual": extended_lookback_days if used_extended else lookback_days,
        }

    deposits = [r["보증금"] for r in pool]
    median = int(statistics.median(deposits))
    return {
        "sample_count": len(pool),
        "median_보증금": median,
        "min_보증금": min(deposits),
        "max_보증금": max(deposits),
        "gap": sale_price - median,
        "used_extended": used_extended,
        "lookback_days_actual": extended_lookback_days if used_extended else lookback_days,
    }


def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"last_run": None, "last_error_notified_at": None, "alerted_sales": []}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, state: dict) -> None:
    """Atomic write: tmp 파일에 쓰고 rename."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, str(p))
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def make_record_id(record: dict) -> str:
    key = "|".join([
        record["아파트"],
        record["법정동"],
        f"{record['전용면적']:.2f}",
        record["거래일"],
        str(record["층"]),
        str(record["거래금액"]),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def is_duplicate(record: dict, state: dict) -> bool:
    rid = make_record_id(record)
    return any(item["id"] == rid for item in state.get("alerted_sales", []))


def add_to_state(record: dict, state: dict, *, complex_key: str, now: str) -> None:
    state["alerted_sales"].append({
        "id": make_record_id(record),
        "complex_key": complex_key,
        "deal_date": record["거래일"],
        "alerted_at": now,
    })


def cleanup_old_alerts(state: dict, *, days: int, now: datetime) -> None:
    cutoff = now - timedelta(days=days)
    kept = []
    for item in state.get("alerted_sales", []):
        try:
            t = datetime.fromisoformat(item["alerted_at"])
        except ValueError:
            continue
        if t >= cutoff:
            kept.append(item)
    state["alerted_sales"] = kept


TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _format_won(만원: int) -> str:
    """198000 만원 → '19억 8,000'."""
    억 = 만원 // 10000
    rest = 만원 % 10000
    if 억 == 0:
        return f"{rest:,}"
    if rest == 0:
        return f"{억}억"
    return f"{억}억 {rest:,}"


def format_message(match: dict, gap_info: dict) -> str:
    head = (
        f"🏠 새로운 매매 거래 ({match['complex_display']} {match['size_label']}㎡)\n\n"
        f"💰 매매가  {_format_won(match['거래금액'])} "
        f"({match['층']}층, {match['거래일']} 신고)"
    )
    if gap_info["median_보증금"] is None:
        body = (
            f"\n📊 전세 데이터 부족 (직전 {gap_info['lookback_days_actual']}일 "
            f"{gap_info['sample_count']}건)\n"
            f"🔻 갭 계산 불가"
        )
    else:
        body = (
            f"\n📊 직전 {gap_info['lookback_days_actual']}일 전세 시세 "
            f"({match['size_label']}㎡, {gap_info['sample_count']}건)\n"
            f"   • 중위값  {_format_won(gap_info['median_보증금'])}\n"
            f"   • 최저~최고  {_format_won(gap_info['min_보증금'])} ~ "
            f"{_format_won(gap_info['max_보증금'])}\n"
            f"🔻 갭 (매매 − 전세 중위값)\n"
            f"   약 {_format_won(gap_info['gap'])}"
        )
    tail = "\n\n[국토부 실거래가 보기 ↗](https://rt.molit.go.kr)"
    return head + body + tail


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = TELEGRAM_API.format(token=token)
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"텔레그램 발송 실패 ({resp.status_code}): {resp.text[:200]}")


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(KST).date().isoformat()
    run_log = log_dir / f"run-{today}.log"
    error_log = log_dir / "error.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    run_handler = logging.FileHandler(run_log, encoding="utf-8")
    run_handler.setLevel(logging.INFO)
    run_handler.setFormatter(fmt)

    error_handler = logging.FileHandler(error_log, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.handlers = []
    logger.setLevel(logging.INFO)
    logger.addHandler(run_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    # 90일 이상 경과 로그 정리
    cutoff = datetime.now(KST) - timedelta(days=90)
    for f in log_dir.glob("run-*.log"):
        try:
            d = datetime.strptime(f.stem.split("-", 1)[1], "%Y-%m-%d").replace(tzinfo=KST)
            if d < cutoff:
                f.unlink()
        except (ValueError, IndexError):
            continue


def should_send_error_alert(state: dict) -> bool:
    last = state.get("last_error_notified_at")
    if not last:
        return True
    try:
        t = datetime.fromisoformat(last)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - t) >= timedelta(hours=24)


def mark_error_alert_sent(state: dict) -> None:
    state["last_error_notified_at"] = datetime.now(timezone.utc).isoformat()


KST = timezone(timedelta(hours=9))

logger = logging.getLogger("realestate_monitor")


def _ymd_list(months_back: int) -> list[str]:
    """오늘 기준 직전 N개월 (이번 달 포함) YYYYMM 리스트, 최신부터."""
    today = datetime.now(KST)
    out = []
    y, m = today.year, today.month
    for _ in range(months_back):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def _collect_records(config: dict, service_key: str, months: int) -> tuple[list[dict], list[dict]]:
    """모든 시군구 × 모든 월의 매매·전월세 레코드 수집."""
    lawd_cds = sorted({c["lawd_cd"] for c in config["complexes"]})
    sales: list[dict] = []
    rents: list[dict] = []
    for ymd in _ymd_list(months):
        for cd in lawd_cds:
            try:
                sales.extend(fetch_sales(cd, ymd, service_key))
            except Exception as e:
                logger.error("매매 fetch 실패 lawd=%s ymd=%s: %s", cd, ymd, e)
            try:
                rents.extend(fetch_rents(cd, ymd, service_key))
            except Exception as e:
                logger.error("전월세 fetch 실패 lawd=%s ymd=%s: %s", cd, ymd, e)
    return sales, rents


def _find_matches(sales: list[dict], config: dict) -> list[dict]:
    """단지·면적·가격 조건을 모두 만족하는 매매 매칭 리스트."""
    matches = []
    complex_lookup = {c["key"]: c for c in config["complexes"]}
    for record in sales:
        complex_key = match_complex(record, config["complexes"])
        if not complex_key:
            continue
        size_label = filter_size(record, config["size_ranges"])
        if not size_label:
            continue
        if not filter_price(record, config["max_price_만원"]):
            continue
        matches.append({
            **record,
            "complex_key": complex_key,
            "complex_display": complex_lookup[complex_key]["display_name"],
            "size_label": size_label,
        })
    return matches


def _build_gap(match: dict, rents: list[dict], config: dict) -> dict:
    same_complex_key = match["complex_key"]
    same_complex_rents = [
        r for r in rents if match_complex(r, config["complexes"]) == same_complex_key
    ]
    size_range = config["size_ranges"][match["size_label"]]
    return compute_gap(
        complex_key=same_complex_key,
        size_label=match["size_label"],
        size_range=tuple(size_range),
        sale_price=match["거래금액"],
        rent_records=same_complex_rents,
        lookback_days=config["rent_lookback_days"],
        extended_lookback_days=config.get("rent_extended_lookback_days", 180),
        min_samples=config["rent_min_samples"],
        today=datetime.now(KST).date().isoformat(),
    )


def _try_error_alert(token: str, chat_id: str, msg: str, state: dict) -> None:
    """운영 알림 발송 + 발송 시각 기록 (1일 1회 제한은 호출 전 should_send_error_alert로 확인)."""
    try:
        send_telegram(token, chat_id, f"⚠️ realestate_monitor 운영 알림\n{msg[:500]}")
        mark_error_alert_sent(state)
    except Exception as e:
        logger.error("운영 알림 발송 실패: %s", e)


def run(args) -> int:
    load_dotenv(dotenv_path=Path(args.base_dir) / ".env")
    service_key = os.environ.get("MOLIT_SERVICE_KEY", "").strip()
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not service_key:
        logger.error("MOLIT_SERVICE_KEY 미설정")
        return 2
    if not bot_token and not args.dry_run:
        logger.error("TELEGRAM_BOT_TOKEN 미설정")
        return 2

    config = load_config(str(Path(args.base_dir) / "config.json"))
    state_path = str(Path(args.base_dir) / "state.json")
    state = load_state(state_path)

    months = args.backfill_months if args.backfill_months else 2
    logger.info("데이터 수집 (직전 %d개월)", months)
    sales, rents = _collect_records(config, service_key, months)
    logger.info("수집 완료: 매매 %d건, 전월세 %d건", len(sales), len(rents))

    matches = _find_matches(sales, config)
    logger.info("필터 후 매칭 매매 %d건", len(matches))

    if not args.no_dedup:
        matches = [m for m in matches if not is_duplicate(m, state)]
        logger.info("dedup 후 매칭 %d건", len(matches))

    if args.report:
        _print_report(sales, rents, matches, config)
        return 0

    if not matches:
        logger.info("신규 매칭 없음")
        state["last_run"] = datetime.now(KST).isoformat()
        cleanup_old_alerts(state, days=180, now=datetime.now(timezone.utc))
        save_state(state_path, state)
        return 0

    sent = []
    for match in matches:
        gap_info = _build_gap(match, rents, config)
        text = format_message(match, gap_info)
        if args.dry_run:
            print("=== DRY RUN ===")
            print(text)
            continue
        try:
            send_telegram(bot_token, config["telegram_chat_id"], text)
            sent.append(match)
        except Exception as e:
            logger.error("텔레그램 발송 실패: %s", e)
            if args.notify_on_error and should_send_error_alert(state):
                _try_error_alert(bot_token, config["telegram_chat_id"], str(e), state)

    if not args.dry_run:
        for match in sent:
            add_to_state(match, state, complex_key=match["complex_key"], now=datetime.now(KST).isoformat())

    state["last_run"] = datetime.now(KST).isoformat()
    cleanup_old_alerts(state, days=180, now=datetime.now(timezone.utc))
    save_state(state_path, state)
    logger.info("발송 완료: %d건", len(sent))
    return 0


def _print_report(sales, rents, matches, config):
    print("=== 단지별 매칭 검증 ===\n")
    by_complex = {c["key"]: {"display": c["display_name"], "sales": 0, "rents": 0} for c in config["complexes"]}
    for r in sales:
        k = match_complex(r, config["complexes"])
        if k and filter_size(r, config["size_ranges"]):
            by_complex[k]["sales"] += 1
    for r in rents:
        k = match_complex(r, config["complexes"])
        if k and filter_size(r, config["size_ranges"]):
            by_complex[k]["rents"] += 1
    for key, info in by_complex.items():
        marker = "✅" if info["sales"] + info["rents"] > 0 else "⚠️"
        print(f"{marker} {info['display']}  매매 {info['sales']}건 / 전월세 {info['rents']}건")
    print(f"\n=== 가격 임계값 통과 매칭: {len(matches)}건 ===")
    for m in matches:
        print(f"  - {m['complex_display']} {m['size_label']}㎡  {_format_won(m['거래금액'])}  ({m['거래일']}, {m['층']}층)")


def main():
    parser = argparse.ArgumentParser(description="부동산 실거래가·전월세 모니터링")
    parser.add_argument("--base-dir", default=str(Path(__file__).parent), help="프로젝트 루트")
    parser.add_argument("--dry-run", action="store_true", help="알림 발송 없이 콘솔 출력")
    parser.add_argument("--no-dedup", action="store_true", help="state 무시하고 전체 발송")
    parser.add_argument("--backfill-months", type=int, default=0, help="직전 N개월 백필")
    parser.add_argument("--report", action="store_true", help="단지별 매칭 검증 리포트")
    parser.add_argument("--notify-on-error", action="store_true", help="치명적 오류 시 운영 알림")
    args = parser.parse_args()

    setup_logging(Path(args.base_dir) / "logs")

    try:
        return run(args)
    except Exception as e:
        logger.exception("치명적 오류: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
