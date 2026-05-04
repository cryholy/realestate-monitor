# 부동산 실거래가·전월세 모니터링 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 7개 단지의 매매가가 20억 미만으로 등록되면 갭(매매−전세) 정보와 함께 텔레그램으로 자동 알림을 보내는 단일 Python 스크립트를 구축한다.

**Architecture:** `monitor.py` 단일 파일에 모든 로직을 두고 `config.json`/`state.json`/`.env`로 설정·상태·시크릿을 분리한다. Claude 원격 에이전트(`schedule` 스킬)가 매일 09:00·18:00 KST에 스크립트를 실행한다. 외부 호출은 국토부 실거래가 API(매매·전월세) 2종과 Telegram Bot API.

**Tech Stack:** Python 3.11+, requests, python-dotenv, xml.etree.ElementTree(stdlib), pytest

---

## File Structure

```
labs/realestate_monitor/
├── monitor.py                     # 메인 스크립트 (전체 로직)
├── config.json                    # 단지·임계값·텔레그램 chat_id
├── state.json                     # dedup 상태 (gitignored)
├── .env                           # 시크릿 (gitignored)
├── .env.example                   # .env 템플릿
├── .gitignore
├── requirements.txt
├── README.md
├── docs/
│   ├── 2026-05-04-design.md       # 기존
│   └── 2026-05-04-implementation-plan.md  # 본 문서
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # pytest fixtures
│   ├── test_config.py
│   ├── test_api.py
│   ├── test_matcher.py
│   ├── test_filter.py
│   ├── test_gap.py
│   ├── test_state.py
│   ├── test_notifier.py
│   └── fixtures/
│       ├── sale_response.xml
│       ├── rent_response.xml
│       └── empty_response.xml
└── logs/                          # gitignored, 런타임 생성
```

`monitor.py` 내부는 다음 함수 그룹으로 구성한다 (한 파일 내 논리적 분리).

| 그룹 | 함수 |
|---|---|
| Config | `load_config(path)` |
| API | `fetch_sales(lawd_cd, ymd)`, `fetch_rents(lawd_cd, ymd)`, `parse_xml(xml_text, kind)` |
| Match | `normalize(name)`, `match_complex(record, complexes)` |
| Filter | `filter_size(record, size_ranges)`, `filter_price(record, max_price)` |
| Gap | `compute_gap(complex_key, size_label, sale_price, rent_records, lookback_days)` |
| State | `load_state(path)`, `save_state(path, state)`, `is_duplicate(record, state)`, `add_to_state(record, state)`, `cleanup_old_alerts(state, days)`, `make_record_id(record)` |
| Notify | `format_message(match, gap_info)`, `send_telegram(token, chat_id, text)` |
| Error | `should_send_error_alert(state)`, `mark_error_alert_sent(state)` |
| Logging | `setup_logging(log_dir)` |
| Main | `run(args)`, `main()` |

---

## Task 1: 프로젝트 스켈레톤

**Files:**
- Create: `labs/realestate_monitor/.gitignore`
- Create: `labs/realestate_monitor/.env.example`
- Create: `labs/realestate_monitor/requirements.txt`
- Create: `labs/realestate_monitor/tests/__init__.py`
- Create: `labs/realestate_monitor/tests/conftest.py`

- [ ] **Step 1: .gitignore 작성**

```
.env
state.json
logs/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: .env.example 작성**

```
# 공공데이터포털 서비스 키 (https://www.data.go.kr/)
MOLIT_SERVICE_KEY=your_service_key_here

# 텔레그램 봇 토큰 (BotFather에서 발급)
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
```

- [ ] **Step 3: requirements.txt 작성**

```
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=7.4.0
```

- [ ] **Step 4: tests/__init__.py 빈 파일 생성**

```python
```

- [ ] **Step 5: tests/conftest.py 작성**

```python
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
```

- [ ] **Step 6: 디렉토리 생성 + commit**

```bash
mkdir -p labs/realestate_monitor/tests/fixtures
mkdir -p labs/realestate_monitor/logs
git add labs/realestate_monitor/.gitignore \
        labs/realestate_monitor/.env.example \
        labs/realestate_monitor/requirements.txt \
        labs/realestate_monitor/tests/__init__.py \
        labs/realestate_monitor/tests/conftest.py
git commit -m "feat(realestate_monitor): 프로젝트 스켈레톤"
```

---

## Task 2: API 응답 fixture 작성

**Files:**
- Create: `labs/realestate_monitor/tests/fixtures/sale_response.xml`
- Create: `labs/realestate_monitor/tests/fixtures/rent_response.xml`
- Create: `labs/realestate_monitor/tests/fixtures/empty_response.xml`

- [ ] **Step 1: sale_response.xml 작성** (실제 국토부 API 스키마 기반)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL_SERVICE</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <거래금액> 198,000</거래금액>
        <거래년도>2026</거래년도>
        <거래월>04</거래월>
        <거래일>28</거래일>
        <건축년도>2003</건축년도>
        <법정동> 성수동1가</법정동>
        <아파트>서울숲푸르지오</아파트>
        <전용면적>84.92</전용면적>
        <지번>668</지번>
        <지역코드>11200</지역코드>
        <층>15</층>
      </item>
      <item>
        <거래금액> 175,000</거래금액>
        <거래년도>2026</거래년도>
        <거래월>04</거래월>
        <거래일>15</거래일>
        <건축년도>2003</건축년도>
        <법정동> 성수동1가</법정동>
        <아파트>서울숲푸르지오</아파트>
        <전용면적>59.97</전용면적>
        <지번>668</지번>
        <지역코드>11200</지역코드>
        <층>8</층>
      </item>
      <item>
        <거래금액> 250,000</거래금액>
        <거래년도>2026</거래년도>
        <거래월>04</거래월>
        <거래일>10</거래일>
        <건축년도>2003</건축년도>
        <법정동> 성수동1가</법정동>
        <아파트>서울숲푸르지오시티</아파트>
        <전용면적>84.50</전용면적>
        <지번>668</지번>
        <지역코드>11200</지역코드>
        <층>20</층>
      </item>
    </items>
    <numOfRows>1000</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>3</totalCount>
  </body>
</response>
```

- [ ] **Step 2: rent_response.xml 작성**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL_SERVICE</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <보증금액> 125,000</보증금액>
        <월세금액> 0</월세금액>
        <계약구분>신규</계약구분>
        <계약년월일>20260315</계약년월일>
        <건축년도>2003</건축년도>
        <법정동> 성수동1가</법정동>
        <아파트>서울숲푸르지오</아파트>
        <전용면적>84.92</전용면적>
        <지번>668</지번>
        <지역코드>11200</지역코드>
        <층>10</층>
      </item>
      <item>
        <보증금액> 130,000</보증금액>
        <월세금액> 0</월세금액>
        <계약구분>갱신</계약구분>
        <계약년월일>20260328</계약년월일>
        <건축년도>2003</건축년도>
        <법정동> 성수동1가</법정동>
        <아파트>서울숲푸르지오</아파트>
        <전용면적>84.92</전용면적>
        <지번>668</지번>
        <지역코드>11200</지역코드>
        <층>14</층>
      </item>
      <item>
        <보증금액> 50,000</보증금액>
        <월세금액> 200</월세금액>
        <계약구분>신규</계약구분>
        <계약년월일>20260320</계약년월일>
        <건축년도>2003</건축년도>
        <법정동> 성수동1가</법정동>
        <아파트>서울숲푸르지오</아파트>
        <전용면적>84.92</전용면적>
        <지번>668</지번>
        <지역코드>11200</지역코드>
        <층>5</층>
      </item>
    </items>
    <numOfRows>1000</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>3</totalCount>
  </body>
</response>
```

- [ ] **Step 3: empty_response.xml 작성**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL_SERVICE</resultMsg>
  </header>
  <body>
    <items></items>
    <numOfRows>1000</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>0</totalCount>
  </body>
</response>
```

- [ ] **Step 4: Commit**

```bash
git add labs/realestate_monitor/tests/fixtures/
git commit -m "test(realestate_monitor): API 응답 fixture 추가"
```

---

## Task 3: Config 로딩

**Files:**
- Create: `labs/realestate_monitor/tests/test_config.py`
- Create/Modify: `labs/realestate_monitor/monitor.py`
- Create: `labs/realestate_monitor/config.json`

- [ ] **Step 1: 실패하는 테스트 작성**

`labs/realestate_monitor/tests/test_config.py`:

```python
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
cd labs/realestate_monitor
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ImportError: No module named 'monitor'` 또는 `cannot import name 'load_config'`

- [ ] **Step 3: monitor.py에 load_config 구현**

```python
"""부동산 실거래가·전월세 모니터링."""
import json

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
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 2 passed

- [ ] **Step 5: 실제 config.json 작성**

`labs/realestate_monitor/config.json`:

```json
{
  "complexes": [
    {
      "key": "seoulsupp_1",
      "display_name": "서울숲푸르지오",
      "lawd_cd": "11200",
      "법정동": "성수동1가",
      "name_patterns": ["서울숲푸르지오"],
      "exclude_patterns": ["2차", "Ⅱ", "시티"]
    },
    {
      "key": "seoulsupp_2",
      "display_name": "서울숲푸르지오 2차",
      "lawd_cd": "11200",
      "법정동": "성수동1가",
      "name_patterns": ["서울숲푸르지오2차", "서울숲푸르지오Ⅱ"],
      "exclude_patterns": []
    },
    {
      "key": "guui_lottecastle_eastpole",
      "display_name": "구의롯데캐슬이스트폴",
      "lawd_cd": "11215",
      "법정동": "구의동",
      "name_patterns": ["구의롯데캐슬이스트폴", "롯데캐슬이스트폴"],
      "exclude_patterns": []
    },
    {
      "key": "jayang_hanyang",
      "display_name": "자양 한양",
      "lawd_cd": "11215",
      "법정동": "자양동",
      "name_patterns": ["자양한양", "한양"],
      "exclude_patterns": ["현대", "수자인", "프라임", "리버"]
    },
    {
      "key": "kwangjang_geukdong_1",
      "display_name": "광장 극동 1차",
      "lawd_cd": "11215",
      "법정동": "광장동",
      "name_patterns": ["극동1차", "극동(1차)", "극동 1"],
      "exclude_patterns": ["2차", "Ⅱ"]
    },
    {
      "key": "kwangjang_geukdong_2",
      "display_name": "광장 극동 2차",
      "lawd_cd": "11215",
      "법정동": "광장동",
      "name_patterns": ["극동2차", "극동(2차)", "극동 2", "극동Ⅱ"],
      "exclude_patterns": []
    },
    {
      "key": "oksu_heights",
      "display_name": "옥수하이츠",
      "lawd_cd": "11200",
      "법정동": "옥수동",
      "name_patterns": ["옥수하이츠"],
      "exclude_patterns": []
    }
  ],
  "size_ranges": {
    "59": [58.0, 60.5],
    "84": [83.0, 85.5]
  },
  "max_price_만원": 200000,
  "rent_lookback_days": 90,
  "rent_min_samples": 5,
  "rent_extended_lookback_days": 180,
  "include_월세": false,
  "rent_conversion_rate": 100,
  "telegram_chat_id": "REPLACE_WITH_YOUR_CHAT_ID"
}
```

- [ ] **Step 6: Commit**

```bash
git add labs/realestate_monitor/monitor.py \
        labs/realestate_monitor/config.json \
        labs/realestate_monitor/tests/test_config.py
git commit -m "feat(realestate_monitor): config 로딩 + 단지 정의"
```

---

## Task 4: API 클라이언트 (매매)

**Files:**
- Create: `labs/realestate_monitor/tests/test_api.py`
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: parse_xml 실패 테스트 작성**

`labs/realestate_monitor/tests/test_api.py`:

```python
import pytest
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
python -m pytest tests/test_api.py::test_parse_xml_sale -v
```

Expected: FAIL — `cannot import name 'parse_xml'`

- [ ] **Step 3: parse_xml 구현**

`monitor.py`에 추가:

```python
import xml.etree.ElementTree as ET


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
```

- [ ] **Step 4: parse_xml 테스트 통과 확인**

```bash
python -m pytest tests/test_api.py::test_parse_xml_sale tests/test_api.py::test_parse_xml_empty tests/test_api.py::test_parse_xml_invalid_raises -v
```

Expected: 3 passed

- [ ] **Step 5: rent 파싱 테스트 추가**

`tests/test_api.py`에 추가:

```python
def test_parse_xml_rent(rent_xml):
    records = parse_xml(rent_xml, kind="rent")

    assert len(records) == 3
    pure_jeonse = [r for r in records if r["월세"] == 0]
    assert len(pure_jeonse) == 2
    assert pure_jeonse[0]["보증금"] == 125000
    assert pure_jeonse[0]["계약일"] == "2026-03-15"
    assert pure_jeonse[0]["계약구분"] == "신규"
```

- [ ] **Step 6: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_api.py -v
```

Expected: 4 passed

- [ ] **Step 7: fetch_sales 구현 (HTTP requests + retry)**

`monitor.py`에 추가:

```python
import os
import time

import requests

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
```

- [ ] **Step 8: fetch_sales 테스트 (HTTP mock)**

`tests/test_api.py`에 추가:

```python
from unittest.mock import patch


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
```

- [ ] **Step 9: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_api.py -v
```

Expected: 5 passed

- [ ] **Step 10: Commit**

```bash
git add labs/realestate_monitor/monitor.py labs/realestate_monitor/tests/test_api.py
git commit -m "feat(realestate_monitor): 국토부 API 클라이언트 + XML 파싱 + 재시도"
```

---

## Task 5: 단지 매칭 로직

**Files:**
- Create: `labs/realestate_monitor/tests/test_matcher.py`
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_matcher.py`:

```python
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
python -m pytest tests/test_matcher.py -v
```

Expected: FAIL — `cannot import name 'normalize'`

- [ ] **Step 3: 구현 추가**

`monitor.py`에 추가:

```python
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
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_matcher.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add labs/realestate_monitor/monitor.py labs/realestate_monitor/tests/test_matcher.py
git commit -m "feat(realestate_monitor): 단지 매칭 (정규화 + 패턴 + exclude)"
```

---

## Task 6: 면적·가격 필터

**Files:**
- Create: `labs/realestate_monitor/tests/test_filter.py`
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_filter.py`:

```python
from monitor import filter_size, filter_price


SIZE_RANGES = {"59": [58.0, 60.5], "84": [83.0, 85.5]}


def test_filter_size_84_inclusive():
    assert filter_size({"전용면적": 84.92}, SIZE_RANGES) == "84"
    assert filter_size({"전용면적": 83.0}, SIZE_RANGES) == "84"
    assert filter_size({"전용면적": 85.5}, SIZE_RANGES) == "84"


def test_filter_size_59():
    assert filter_size({"전용면적": 59.97}, SIZE_RANGES) == "59"


def test_filter_size_out_of_range():
    assert filter_size({"전용면적": 75.0}, SIZE_RANGES) is None
    assert filter_size({"전용면적": 100.0}, SIZE_RANGES) is None


def test_filter_price_under():
    assert filter_price({"거래금액": 198000}, 200000) is True


def test_filter_price_at_threshold():
    """20억 정확히는 임계값 미만이 아니므로 제외 (< 20억)."""
    assert filter_price({"거래금액": 200000}, 200000) is False


def test_filter_price_over():
    assert filter_price({"거래금액": 250000}, 200000) is False
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
python -m pytest tests/test_filter.py -v
```

Expected: FAIL — `cannot import name 'filter_size'`

- [ ] **Step 3: 구현 추가**

`monitor.py`에 추가:

```python
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
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_filter.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add labs/realestate_monitor/monitor.py labs/realestate_monitor/tests/test_filter.py
git commit -m "feat(realestate_monitor): 면적·가격 필터"
```

---

## Task 7: 갭 계산

**Files:**
- Create: `labs/realestate_monitor/tests/test_gap.py`
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_gap.py`:

```python
from monitor import compute_gap


def make_rent(deposit, days_ago, area=84.92, monthly=0):
    """days_ago일 전 전세 거래 레코드."""
    from datetime import datetime, timedelta
    d = (datetime(2026, 5, 4) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return {
        "아파트": "서울숲푸르지오",
        "법정동": "성수동1가",
        "전용면적": area,
        "보증금": deposit,
        "월세": monthly,
        "계약일": d,
    }


def test_compute_gap_basic():
    sale_price = 198000  # 19억 8천 만원
    rents = [
        make_rent(120000, 10),
        make_rent(125000, 30),
        make_rent(130000, 60),
        make_rent(115000, 80),
        make_rent(135000, 5),
    ]
    info = compute_gap(
        complex_key="seoulsupp_1",
        size_label="84",
        size_range=(83.0, 85.5),
        sale_price=sale_price,
        rent_records=rents,
        lookback_days=90,
        extended_lookback_days=180,
        min_samples=5,
        today="2026-05-04",
    )

    assert info["sample_count"] == 5
    assert info["median_보증금"] == 125000
    assert info["min_보증금"] == 115000
    assert info["max_보증금"] == 135000
    assert info["gap"] == 198000 - 125000
    assert info["used_extended"] is False


def test_compute_gap_uses_extended_when_few_samples():
    rents = [
        make_rent(120000, 10),
        make_rent(125000, 30),
        make_rent(130000, 100),  # 90일 밖
        make_rent(115000, 150),  # 90일 밖
        make_rent(135000, 170),  # 90일 밖
    ]
    info = compute_gap(
        complex_key="seoulsupp_1",
        size_label="84",
        size_range=(83.0, 85.5),
        sale_price=198000,
        rent_records=rents,
        lookback_days=90,
        extended_lookback_days=180,
        min_samples=5,
        today="2026-05-04",
    )
    assert info["used_extended"] is True
    assert info["sample_count"] == 5


def test_compute_gap_insufficient_samples():
    rents = [make_rent(120000, 10)]
    info = compute_gap(
        complex_key="seoulsupp_1",
        size_label="84",
        size_range=(83.0, 85.5),
        sale_price=198000,
        rent_records=rents,
        lookback_days=90,
        extended_lookback_days=180,
        min_samples=5,
        today="2026-05-04",
    )
    assert info["sample_count"] < 5
    assert info["median_보증금"] is None
    assert info["gap"] is None


def test_compute_gap_excludes_월세():
    rents = [
        make_rent(50000, 10, monthly=200),  # 월세 → 제외
        make_rent(120000, 12),
        make_rent(125000, 30),
        make_rent(130000, 60),
        make_rent(115000, 80),
        make_rent(135000, 5),
    ]
    info = compute_gap(
        complex_key="seoulsupp_1",
        size_label="84",
        size_range=(83.0, 85.5),
        sale_price=198000,
        rent_records=rents,
        lookback_days=90,
        extended_lookback_days=180,
        min_samples=5,
        today="2026-05-04",
    )
    assert info["sample_count"] == 5  # 월세 제외 5건
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
python -m pytest tests/test_gap.py -v
```

Expected: FAIL — `cannot import name 'compute_gap'`

- [ ] **Step 3: 구현 추가**

`monitor.py`에 추가:

```python
import statistics
from datetime import datetime, timedelta


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
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_gap.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add labs/realestate_monitor/monitor.py labs/realestate_monitor/tests/test_gap.py
git commit -m "feat(realestate_monitor): 갭 계산 (직전 90일 전세 중위값, 표본 부족 시 180일 확장)"
```

---

## Task 8: 상태 관리 (load/save/dedup/atomic/cleanup)

**Files:**
- Create: `labs/realestate_monitor/tests/test_state.py`
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_state.py`:

```python
import json
from datetime import datetime, timedelta, timezone

import pytest

from monitor import (
    load_state,
    save_state,
    make_record_id,
    is_duplicate,
    add_to_state,
    cleanup_old_alerts,
)


def test_load_state_creates_empty_when_missing(tmp_path):
    state_path = tmp_path / "state.json"
    state = load_state(str(state_path))
    assert state == {"last_run": None, "last_error_notified_at": None, "alerted_sales": []}


def test_save_then_load_roundtrip(tmp_path):
    state_path = tmp_path / "state.json"
    state = {"last_run": "2026-05-04T09:00:00+09:00", "last_error_notified_at": None, "alerted_sales": []}
    save_state(str(state_path), state)

    loaded = load_state(str(state_path))
    assert loaded == state


def test_save_state_is_atomic(tmp_path):
    """save_state는 tmp 파일 후 rename으로 동작 — 부분 쓰기 시에도 기존 파일 유지."""
    state_path = tmp_path / "state.json"
    save_state(str(state_path), {"last_run": "old", "last_error_notified_at": None, "alerted_sales": []})

    tmp_files_before = list(tmp_path.iterdir())
    save_state(str(state_path), {"last_run": "new", "last_error_notified_at": None, "alerted_sales": []})
    tmp_files_after = list(tmp_path.iterdir())

    # 새 임시 파일이 남아있으면 안됨 (rename 후 정리)
    assert len(tmp_files_after) == 1
    assert load_state(str(state_path))["last_run"] == "new"


def test_make_record_id_deterministic():
    record = {
        "아파트": "서울숲푸르지오",
        "법정동": "성수동1가",
        "전용면적": 84.92,
        "거래일": "2026-04-28",
        "층": 15,
        "거래금액": 198000,
    }
    id1 = make_record_id(record)
    id2 = make_record_id(record)
    assert id1 == id2
    assert len(id1) == 40  # sha1 hex

    record2 = dict(record, 층=14)
    assert make_record_id(record2) != id1


def test_is_duplicate_and_add():
    state = {"last_run": None, "last_error_notified_at": None, "alerted_sales": []}
    record = {
        "아파트": "서울숲푸르지오",
        "법정동": "성수동1가",
        "전용면적": 84.92,
        "거래일": "2026-04-28",
        "층": 15,
        "거래금액": 198000,
    }
    assert is_duplicate(record, state) is False

    add_to_state(record, state, complex_key="seoulsupp_1", now="2026-05-04T09:00:00+09:00")
    assert len(state["alerted_sales"]) == 1
    assert is_duplicate(record, state) is True


def test_cleanup_removes_old_alerts():
    now = datetime(2026, 5, 4, tzinfo=timezone.utc)
    old = (now - timedelta(days=200)).isoformat()
    recent = (now - timedelta(days=50)).isoformat()

    state = {
        "last_run": None,
        "last_error_notified_at": None,
        "alerted_sales": [
            {"id": "a" * 40, "complex_key": "x", "deal_date": "2025-10-01", "alerted_at": old},
            {"id": "b" * 40, "complex_key": "y", "deal_date": "2026-03-01", "alerted_at": recent},
        ],
    }
    cleanup_old_alerts(state, days=180, now=now)
    assert len(state["alerted_sales"]) == 1
    assert state["alerted_sales"][0]["id"] == "b" * 40
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
python -m pytest tests/test_state.py -v
```

Expected: FAIL — `cannot import name 'load_state'`

- [ ] **Step 3: 구현 추가**

`monitor.py`에 추가:

```python
import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


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
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_state.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add labs/realestate_monitor/monitor.py labs/realestate_monitor/tests/test_state.py
git commit -m "feat(realestate_monitor): 상태 관리 (atomic 쓰기, dedup, 180일 cleanup)"
```

---

## Task 9: 메시지 포맷 + 텔레그램 발송

**Files:**
- Create: `labs/realestate_monitor/tests/test_notifier.py`
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_notifier.py`:

```python
from unittest.mock import patch

import pytest

from monitor import format_message, send_telegram


def test_format_message_with_gap():
    match = {
        "complex_display": "서울숲푸르지오",
        "size_label": "84",
        "거래금액": 198000,
        "층": 15,
        "거래일": "2026-04-28",
    }
    gap_info = {
        "sample_count": 12,
        "median_보증금": 125000,
        "min_보증금": 115000,
        "max_보증금": 138000,
        "gap": 73000,
        "used_extended": False,
        "lookback_days_actual": 90,
    }
    msg = format_message(match, gap_info)

    assert "서울숲푸르지오 84㎡" in msg
    assert "19억 8,000" in msg
    assert "15층" in msg
    assert "2026-04-28" in msg
    assert "12억 5,000" in msg  # median
    assert "11억 5,000" in msg  # min
    assert "13억 8,000" in msg  # max
    assert "7억 3,000" in msg   # gap


def test_format_message_insufficient_rent_samples():
    match = {
        "complex_display": "옥수하이츠",
        "size_label": "84",
        "거래금액": 195000,
        "층": 10,
        "거래일": "2026-04-20",
    }
    gap_info = {
        "sample_count": 1,
        "median_보증금": None,
        "min_보증금": None,
        "max_보증금": None,
        "gap": None,
        "used_extended": True,
        "lookback_days_actual": 180,
    }
    msg = format_message(match, gap_info)
    assert "전세 데이터 부족" in msg
    assert "갭 계산 불가" in msg


@patch("monitor.requests.post")
def test_send_telegram_calls_bot_api(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"ok": True}

    send_telegram("DUMMY_TOKEN", "12345", "테스트 메시지")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "DUMMY_TOKEN" in args[0]
    assert kwargs["json"]["chat_id"] == "12345"
    assert kwargs["json"]["text"] == "테스트 메시지"


@patch("monitor.requests.post")
def test_send_telegram_raises_on_failure(mock_post):
    mock_post.return_value.status_code = 500
    mock_post.return_value.text = "Internal Server Error"

    with pytest.raises(RuntimeError, match="텔레그램"):
        send_telegram("DUMMY_TOKEN", "12345", "테스트")
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
python -m pytest tests/test_notifier.py -v
```

Expected: FAIL — `cannot import name 'format_message'`

- [ ] **Step 3: 구현 추가**

`monitor.py`에 추가:

```python
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
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_notifier.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add labs/realestate_monitor/monitor.py labs/realestate_monitor/tests/test_notifier.py
git commit -m "feat(realestate_monitor): 메시지 포맷 + 텔레그램 발송"
```

---

## Task 10: 메인 오케스트레이션 + CLI

**Files:**
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: 통합 흐름 함수 작성**

`monitor.py` 끝에 추가:

```python
import argparse
import logging
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

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
    complex_def = next(c for c in config["complexes"] if c["key"] == same_complex_key)
    same_complex_rents = [
        r for r in rents
        if normalize(r["아파트"]).startswith(normalize(complex_def["name_patterns"][0])[:6])
        and r["법정동"] == complex_def["법정동"]
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
```

- [ ] **Step 2: import 정리**

`monitor.py` 상단의 import를 정리해 다음과 같이 둔다:

```python
"""부동산 실거래가·전월세 모니터링."""
import argparse
import hashlib
import json
import logging
import os
import statistics
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
```

- [ ] **Step 3: import 동작 확인**

```bash
cd labs/realestate_monitor
python -c "import monitor; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 전체 테스트 다시 실행**

```bash
python -m pytest tests/ -v
```

Expected: 모든 기존 테스트 PASS

- [ ] **Step 5: Commit**

```bash
git add labs/realestate_monitor/monitor.py
git commit -m "feat(realestate_monitor): 메인 오케스트레이션 + CLI 인자"
```

---

## Task 11: 에러 알림 (1일 1회)

**Files:**
- Modify: `labs/realestate_monitor/tests/test_state.py`
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_state.py` 끝에 추가:

```python
from monitor import should_send_error_alert, mark_error_alert_sent


def test_should_send_error_alert_when_never_sent():
    state = {"last_error_notified_at": None, "alerted_sales": []}
    assert should_send_error_alert(state) is True


def test_should_send_error_alert_when_within_24h():
    now = datetime.now(timezone.utc)
    state = {"last_error_notified_at": (now - timedelta(hours=2)).isoformat(), "alerted_sales": []}
    assert should_send_error_alert(state) is False


def test_should_send_error_alert_when_over_24h():
    now = datetime.now(timezone.utc)
    state = {"last_error_notified_at": (now - timedelta(hours=25)).isoformat(), "alerted_sales": []}
    assert should_send_error_alert(state) is True


def test_mark_error_alert_sent_updates_timestamp():
    state = {"last_error_notified_at": None, "alerted_sales": []}
    mark_error_alert_sent(state)
    assert state["last_error_notified_at"] is not None
    parsed = datetime.fromisoformat(state["last_error_notified_at"])
    assert (datetime.now(timezone.utc) - parsed).total_seconds() < 5
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
python -m pytest tests/test_state.py -v
```

Expected: FAIL — `cannot import name 'should_send_error_alert'`

- [ ] **Step 3: 구현 추가**

`monitor.py`에 추가:

```python
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


def _try_error_alert(token: str, chat_id: str, msg: str, state: dict) -> None:
    """1일 1회 제한 운영 알림 발송. 실패는 조용히 흡수."""
    try:
        send_telegram(token, chat_id, f"⚠️ realestate_monitor 운영 알림\n{msg[:500]}")
        mark_error_alert_sent(state)
    except Exception as e:
        logger.error("운영 알림 발송 실패: %s", e)
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
python -m pytest tests/test_state.py -v
```

Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add labs/realestate_monitor/monitor.py labs/realestate_monitor/tests/test_state.py
git commit -m "feat(realestate_monitor): 운영 알림 1일 1회 제한"
```

---

## Task 12: 로깅 셋업

**Files:**
- Modify: `labs/realestate_monitor/monitor.py`

- [ ] **Step 1: setup_logging 구현**

`monitor.py`에 추가:

```python
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
```

- [ ] **Step 2: 동작 확인 (수동)**

```bash
cd labs/realestate_monitor
python -c "
from pathlib import Path
from monitor import setup_logging, logger
setup_logging(Path('logs'))
logger.info('테스트 로그')
logger.error('테스트 에러')
print('확인:')
print(open('logs/run-' + __import__('datetime').date.today().isoformat() + '.log').read())
"
```

Expected: 로그 파일에 INFO + ERROR 양쪽 모두 기록.

- [ ] **Step 3: Commit**

```bash
git add labs/realestate_monitor/monitor.py
git commit -m "feat(realestate_monitor): 로깅 셋업 (일별 run.log + error.log + 90일 cleanup)"
```

---

## Task 13: README + 사전 준비 가이드

**Files:**
- Create: `labs/realestate_monitor/README.md`

- [ ] **Step 1: README 작성**

```markdown
# realestate_monitor

7개 단지(성동·광진구)의 매매가가 20억 미만으로 신고되면 직전 90일 전세 갭 정보와
함께 텔레그램으로 자동 알림을 보낸다. Claude 원격 에이전트(`schedule` 스킬)가
매일 09:00·18:00 KST에 실행한다.

## 사전 준비

### 1. 공공데이터포털 API 활용신청

- 사이트: https://www.data.go.kr/
- 신청할 API 2종:
  - 국토교통부_아파트매매 실거래가 상세 자료
  - 국토교통부_아파트 전월세 자료
- 두 API가 같은 서비스 키로 통하는 경우가 일반적이지만, 별도 신청이 필요할 수 있음.

### 2. 텔레그램 봇

이미 워크스페이스에 텔레그램 봇이 연결되어 있다면 같은 봇 토큰을 재사용할 수 있다.
새로 만드는 경우 BotFather(@BotFather)에서 `/newbot` 으로 생성.

#### chat_id 확인 방법

```bash
TOKEN="YOUR_BOT_TOKEN"
# 봇과 1:1 대화창에서 /start 또는 임의의 메시지 1회 전송 후
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | python -m json.tool
# 응답의 result[].message.chat.id 가 본인 chat_id
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
# .env 편집해서 MOLIT_SERVICE_KEY, TELEGRAM_BOT_TOKEN 입력
```

### 4. config.json 편집

`telegram_chat_id`를 본인 값으로 교체.

### 5. 의존성 설치

```bash
cd labs/realestate_monitor
python -m pip install -r requirements.txt
```

## 운영 전 검증 (필수, 1회성)

직전 6개월 데이터로 단지 매칭 패턴이 제대로 잡히는지 확인.

```bash
python monitor.py --backfill-months 6 --dry-run --report
```

출력에서 단지별 매칭 건수를 확인하고, 매칭 0건 또는 의심 매칭이 있으면
`config.json`의 `name_patterns` / `exclude_patterns`를 보정한다.

## 수동 실행

```bash
# 알림 발송 없이 매칭 결과만 콘솔 출력
python monitor.py --dry-run

# state 무시하고 강제 재발송 (디버그)
python monitor.py --no-dedup --dry-run

# 직전 N개월 백필
python monitor.py --backfill-months 6

# 운영 모드 (스케줄 에이전트가 실행)
python monitor.py --notify-on-error
```

## 스케줄 등록 (Claude 원격 에이전트)

`schedule` 스킬로 다음과 같이 등록:

```
이름     : realestate-monitor
cron     : 0 9,18 * * *
타임존   : Asia/Seoul
프롬프트 : cd /Users/joel/Claude/labs/realestate_monitor && python monitor.py --notify-on-error
```

## 단지·임계값 변경

`config.json` 직접 편집. 단지 추가 시:

```json
{
  "key": "<unique_key>",
  "display_name": "표시명",
  "lawd_cd": "5자리 시군구 코드",
  "법정동": "정확한 법정동명 (API 응답과 일치)",
  "name_patterns": ["매칭할 단지명들"],
  "exclude_patterns": ["배제할 키워드"]
}
```

추가 후 `--report` 실행으로 매칭 검증.

## 테스트

```bash
python -m pytest tests/ -v
```

## 로그 위치

- `logs/run-YYYY-MM-DD.log` — 실행 요약
- `logs/error.log` — 스택 트레이스
- 90일 이상 경과 `run-*.log` 자동 삭제
```

- [ ] **Step 2: Commit**

```bash
git add labs/realestate_monitor/README.md
git commit -m "docs(realestate_monitor): README + 사전 준비 가이드"
```

---

## Task 14: 통합 검증

**Files:** (없음 — 검증만 수행)

- [ ] **Step 1: .env 작성 (사용자가 직접)**

```bash
cd labs/realestate_monitor
cp .env.example .env
# 편집기에서 .env 열어서 실제 키 입력
```

값:
- `MOLIT_SERVICE_KEY` = 사용자가 받은 공공데이터 키
- `TELEGRAM_BOT_TOKEN` = 사용자가 발급받은 봇 토큰

- [ ] **Step 2: chat_id 확인 후 config.json에 입력**

봇에 메시지 한 번 보낸 후:

```bash
TOKEN=$(grep TELEGRAM_BOT_TOKEN .env | cut -d= -f2)
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | python -m json.tool
```

응답에서 `chat.id` 값을 `config.json`의 `telegram_chat_id`에 입력.

- [ ] **Step 3: 매칭 검증 실행**

```bash
python monitor.py --backfill-months 6 --dry-run --report
```

- 7개 단지 모두 "✅"로 매매·전월세 거래가 잡히는지 확인.
- "⚠️ 0건"인 단지가 있으면 `name_patterns` 또는 `법정동` 보정.
- 의심 매칭 (예: 다른 단지가 잡힘)이 있으면 `exclude_patterns` 추가.

- [ ] **Step 4: 1회 dry-run 발송**

```bash
python monitor.py --backfill-months 2 --dry-run
```

매칭이 있으면 콘솔에 텔레그램 메시지 형태가 출력된다. 메시지 가독성 확인.

- [ ] **Step 5: 1회 실제 발송 (디버그용)**

매칭이 한 건이라도 있다면:

```bash
python monitor.py --no-dedup
```

텔레그램 메시지가 실제로 도착하는지 확인. (state.json에 기록되어 두 번째 실행에서는 발송 안 됨)

- [ ] **Step 6: 단위 테스트 모두 통과 확인**

```bash
python -m pytest tests/ -v
```

Expected: 모든 테스트 PASS.

---

## Task 15: 스케줄 등록

**Files:** (Claude 워크스페이스의 schedule 스킬을 통해 등록 — 코드 변경 없음)

- [ ] **Step 1: schedule 스킬 호출 + 라우틴 등록**

Claude 대화창에서:

```
/schedule create realestate-monitor "cd /Users/joel/Claude/labs/realestate_monitor && python monitor.py --notify-on-error" --cron "0 9,18 * * *" --tz Asia/Seoul
```

(정확한 인자명은 schedule 스킬 도움말로 확인)

- [ ] **Step 2: 등록된 라우틴 목록 확인**

```
/schedule list
```

- [ ] **Step 3: 1회 수동 실행 테스트**

```
/schedule run realestate-monitor
```

원격 에이전트가 정상적으로 스크립트를 실행하는지 확인. 텔레그램에 (매칭이 있으면) 메시지가 도착하면 성공.

- [ ] **Step 4: 첫 1주 카나리 모니터링**

운영 시작 후 첫 7일은 다음 사항을 매일 점검:

- 09:00 / 18:00 정시에 텔레그램 알림 또는 (매칭 없음) 로그가 발생하는지
- `logs/run-YYYY-MM-DD.log` 확인 (수집 N건, 매칭 M건, 발송 K건)
- 의도하지 않은 매칭/발송 누락이 있으면 config 보정

7일 무사 통과하면 정상 운영으로 전환.

---

## Self-Review

### Spec coverage

| 스펙 섹션 | 구현 Task |
|---|---|
| 2.1 모니터링 대상 | Task 3 (config.json 단지 정의) |
| 2.2 알림 조건 (트리거) | Task 6 (가격 필터), Task 10 (오케스트레이션) |
| 2.2 갭 분석 | Task 7 (compute_gap) |
| 2.3 채널·빈도 | Task 9 (텔레그램), Task 15 (스케줄) |
| 3.1 시스템 구성 | Task 10, 15 |
| 3.2 디렉토리 | Task 1 |
| 3.3 핵심 함수 | Tasks 3-9, 11-12 |
| 4. 데이터 소스 | Task 4 |
| 5. 단지 매칭 | Task 5 |
| 6. 데이터 흐름 | Task 10 |
| 7. 메시지 형식 | Task 9 |
| 8. state.json | Task 8, 11 |
| 9. 에러 처리 | Task 4 (재시도), Task 11 (1일 1회) |
| 10. 로깅 | Task 12 |
| 11. 수동 실행 모드 | Task 10 (CLI 인자) |
| 12. 스케줄링 | Task 15 |
| 13. 테스트 전략 | Tasks 3-9, 11 (단위), Task 14 (검증) |
| 14. 사전 준비 | Task 13 (README) |

빠짐 없음.

### Placeholder scan

- 모든 step에 실제 코드/명령 포함됨
- "TBD"/"TODO"/"적절히" 등 모호 표현 없음
- 모든 함수 시그니처가 사용처와 일치

### Type consistency

- `match_complex` 반환: `str | None` — Task 5 정의, Task 10 사용 일치
- `compute_gap` 반환 dict 키: `sample_count`, `median_보증금`, `min_보증금`, `max_보증금`, `gap`, `used_extended`, `lookback_days_actual` — Task 7 정의, Task 9 (format_message) 사용 일치
- `state` 구조: `last_run`, `last_error_notified_at`, `alerted_sales[]` — Task 8 정의, Task 11/10 사용 일치
- `make_record_id` 입력 키: `아파트`, `법정동`, `전용면적`, `거래일`, `층`, `거래금액` — Task 8 정의, Task 4 (parse_xml)에서 동일 키 생성

일관성 OK.
