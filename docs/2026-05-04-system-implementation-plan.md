# Cloud Real Estate Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 9개 구(성동·광진·마포·서초·강남·송파·용산·동작·강동)의 매매·전월세 거래를 매일 Supabase에 누적하고, `alert_rules` 테이블에 등록된 관심 매물의 가격 임계값/전세가율 임계값 도달 시 텔레그램 알림을 발송하며, Metabase로 사이클·갭 분석을 시각화한다.

**Architecture:** GitHub Actions cron(매일 18:00 KST) → Python collector → 국토부 API → Supabase Postgres UPSERT → edge 트리거 평가 → Telegram. 단지 식별은 `apt_seq` 정확 매칭. dedup은 Supabase `alerts_sent` 테이블.

**Tech Stack:** Python 3.11+, requests, python-dotenv, supabase-py, pytest, PostgreSQL 15 (Supabase), Metabase Cloud, GitHub Actions, Telegram Bot API.

---

## File Structure

```
labs/realestate_monitor/
├── collector.py                 # 메인 엔트리 (cron 호출)
├── lib/
│   ├── __init__.py
│   ├── api.py                   # 국토부 API + XML 파싱 (전체 분석 필드)
│   ├── matcher.py               # apt_seq 매칭 + size_label 계산
│   ├── notifier.py              # 텔레그램 + 메시지 포맷
│   ├── db.py                    # Supabase client (UPSERT/쿼리)
│   └── triggers.py              # price + jeonse_ratio edge 트리거
├── sql/
│   ├── 001_initial_schema.sql   # 4 테이블 + 인덱스
│   ├── 002_views.sql            # v_complexes, v_alert_rules_check, MV 2개
│   └── seed_districts.sql       # 9개 구 LAWD_CD seed (참고용 — 실 코드는 collector에서 사용)
├── scripts/
│   ├── backfill.py              # 1년 백필 1회성
│   └── seed_alerts_sent.py      # 백필 후 dedup 키 미리 채우기
├── .github/workflows/
│   └── monitor.yml              # cron + secrets + 환경
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_matcher.py
│   ├── test_triggers.py
│   ├── test_db.py
│   ├── test_notifier.py
│   └── fixtures/
│       ├── sale_response.xml
│       ├── rent_response.xml
│       └── error_response.xml
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── docs/                        (기존 4개 문서 유지, 본 plan 추가)
```

총 task 23개. T0(기존 정리) → T1~T13(신규 코드 작성) → T14~T22(외부 셋업 + 가동).

---

## Task 0: 기존 코드/설정 일괄 삭제

**Files:**
- Delete: `labs/realestate_monitor/monitor.py`
- Delete: `labs/realestate_monitor/state.json` (있을 수 있음)
- Delete: `labs/realestate_monitor/config.json`
- Delete: `labs/realestate_monitor/.env.example`
- Delete: `labs/realestate_monitor/.gitignore`
- Delete: `labs/realestate_monitor/requirements.txt`
- Delete: `labs/realestate_monitor/README.md`
- Delete: `labs/realestate_monitor/com.joel.realestate-monitor.plist`
- Delete: `labs/realestate_monitor/tests/__init__.py`
- Delete: `labs/realestate_monitor/tests/conftest.py`
- Delete: `labs/realestate_monitor/tests/test_*.py` (test_api.py, test_config.py, test_filter.py, test_gap.py, test_matcher.py, test_notifier.py, test_state.py)
- Delete: `labs/realestate_monitor/tests/fixtures/*.xml`
- Delete: `labs/realestate_monitor/logs/*` (gitignored이지만 정리)
- Delete: `labs/realestate_monitor/.env` (gitignored, 안전하게 삭제 — 새 시스템에서 재작성)

- [ ] **Step 1: launchd unload**

```bash
launchctl unload ~/Library/LaunchAgents/com.joel.realestate-monitor.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.joel.realestate-monitor.plist
launchctl list | grep realestate
```

Expected: `realestate` 관련 출력 없음.

- [ ] **Step 2: 기존 파일 삭제**

```bash
cd /Users/joel/Claude/labs/realestate_monitor
rm -f monitor.py state.json config.json .env .env.example .gitignore requirements.txt README.md com.joel.realestate-monitor.plist
rm -rf tests/__pycache__ tests/__init__.py tests/conftest.py
rm -f tests/test_api.py tests/test_config.py tests/test_filter.py tests/test_gap.py tests/test_matcher.py tests/test_notifier.py tests/test_state.py
rm -f tests/fixtures/sale_response.xml tests/fixtures/rent_response.xml tests/fixtures/empty_response.xml
rm -rf logs/* __pycache__ .pytest_cache
ls
```

Expected: `docs/` 와 빈 `tests/fixtures/` 만 남음.

- [ ] **Step 3: Commit**

```bash
cd /Users/joel/Claude
git add -A labs/realestate_monitor/
git commit -m "chore(realestate_monitor): 기존 로컬 시스템 코드·설정 삭제 (신규 클라우드 시스템 재작성)"
```

---

## Task 1: 프로젝트 스켈레톤

**Files:**
- Create: `labs/realestate_monitor/.gitignore`
- Create: `labs/realestate_monitor/.env.example`
- Create: `labs/realestate_monitor/requirements.txt`
- Create: `labs/realestate_monitor/tests/__init__.py`
- Create: `labs/realestate_monitor/tests/conftest.py`
- Create: `labs/realestate_monitor/lib/__init__.py`

- [ ] **Step 1: .gitignore**

```
.env
logs/
__pycache__/
*.pyc
.pytest_cache/
.DS_Store
```

- [ ] **Step 2: .env.example**

```
# 공공데이터포털 서비스 키 (https://www.data.go.kr/)
MOLIT_SERVICE_KEY=

# 텔레그램 봇 토큰 (BotFather 발급)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Supabase 프로젝트
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```

- [ ] **Step 3: requirements.txt**

```
requests>=2.31.0
python-dotenv>=1.0.0
supabase>=2.7.0
pytest>=8.0.0
```

- [ ] **Step 4: lib/__init__.py** (빈 파일)

```python
```

- [ ] **Step 5: tests/__init__.py** (빈 파일)

```python
```

- [ ] **Step 6: tests/conftest.py**

```python
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
```

- [ ] **Step 7: pip install**

```bash
cd /Users/joel/Claude/labs/realestate_monitor
python3.11 -m pip install --user -r requirements.txt
```

Expected: 4개 패키지 설치 (requests, python-dotenv, supabase, pytest).

- [ ] **Step 8: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/.gitignore labs/realestate_monitor/.env.example labs/realestate_monitor/requirements.txt labs/realestate_monitor/lib/__init__.py labs/realestate_monitor/tests/__init__.py labs/realestate_monitor/tests/conftest.py
git commit -m "feat(realestate_monitor): 신규 시스템 스켈레톤 (lib/ + tests/ + 의존성)"
```

---

## Task 2: API 응답 fixture XML

**Files:**
- Create: `labs/realestate_monitor/tests/fixtures/sale_response.xml`
- Create: `labs/realestate_monitor/tests/fixtures/rent_response.xml`
- Create: `labs/realestate_monitor/tests/fixtures/error_response.xml`

실제 국토부 API 스키마(영문 camelCase, resultCode "000") 기반.

- [ ] **Step 1: sale_response.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>000</resultCode>
    <resultMsg>OK</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <aptDong></aptDong>
        <aptNm>헬리오시티</aptNm>
        <aptSeq>11710-2412</aptSeq>
        <bonbun>0001</bonbun>
        <bubun>0000</bubun>
        <buildYear>2018</buildYear>
        <buyerGbn>개인</buyerGbn>
        <cdealDay></cdealDay>
        <cdealType></cdealType>
        <dealAmount> 198,000</dealAmount>
        <dealDay>28</dealDay>
        <dealMonth>4</dealMonth>
        <dealYear>2026</dealYear>
        <dealingGbn>중개거래</dealingGbn>
        <estateAgentSggNm>서울 송파구</estateAgentSggNm>
        <excluUseAr>84.92</excluUseAr>
        <floor>15</floor>
        <jibun>1</jibun>
        <landCd>1</landCd>
        <landLeaseholdGbn>N</landLeaseholdGbn>
        <rgstDate></rgstDate>
        <roadNm>송파대로</roadNm>
        <roadNmBonbun>00345</roadNmBonbun>
        <roadNmBubun>00000</roadNmBubun>
        <roadNmCd>4109367</roadNmCd>
        <roadNmSeq>01</roadNmSeq>
        <roadNmSggCd>11710</roadNmSggCd>
        <roadNmbCd>0</roadNmbCd>
        <sggCd>11710</sggCd>
        <slerGbn>개인</slerGbn>
        <umdCd>11500</umdCd>
        <umdNm>가락동</umdNm>
      </item>
      <item>
        <aptNm>헬리오시티</aptNm>
        <aptSeq>11710-2412</aptSeq>
        <buildYear>2018</buildYear>
        <buyerGbn>법인</buyerGbn>
        <dealAmount> 175,000</dealAmount>
        <dealDay>15</dealDay>
        <dealMonth>4</dealMonth>
        <dealYear>2026</dealYear>
        <dealingGbn>직거래</dealingGbn>
        <excluUseAr>59.97</excluUseAr>
        <floor>8</floor>
        <sggCd>11710</sggCd>
        <slerGbn>개인</slerGbn>
        <umdNm>가락동</umdNm>
      </item>
    </items>
    <numOfRows>1000</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>2</totalCount>
  </body>
</response>
```

- [ ] **Step 2: rent_response.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>000</resultCode>
    <resultMsg>OK</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <aptNm>헬리오시티</aptNm>
        <aptSeq>11710-2412</aptSeq>
        <buildYear>2018</buildYear>
        <contractTerm>202504~202704</contractTerm>
        <contractType>신규</contractType>
        <dealDay>15</dealDay>
        <dealMonth>3</dealMonth>
        <dealYear>2026</dealYear>
        <deposit> 125,000</deposit>
        <excluUseAr>84.92</excluUseAr>
        <floor>10</floor>
        <jibun>1</jibun>
        <monthlyRent> 0</monthlyRent>
        <preDeposit></preDeposit>
        <preMonthlyRent></preMonthlyRent>
        <sggCd>11710</sggCd>
        <umdNm>가락동</umdNm>
        <useRRRight></useRRRight>
      </item>
      <item>
        <aptNm>헬리오시티</aptNm>
        <aptSeq>11710-2412</aptSeq>
        <buildYear>2018</buildYear>
        <contractType>갱신</contractType>
        <dealDay>28</dealDay>
        <dealMonth>3</dealMonth>
        <dealYear>2026</dealYear>
        <deposit> 130,000</deposit>
        <excluUseAr>84.92</excluUseAr>
        <floor>14</floor>
        <monthlyRent> 0</monthlyRent>
        <preDeposit> 120,000</preDeposit>
        <preMonthlyRent> 0</preMonthlyRent>
        <sggCd>11710</sggCd>
        <umdNm>가락동</umdNm>
        <useRRRight>사용</useRRRight>
      </item>
      <item>
        <aptNm>헬리오시티</aptNm>
        <aptSeq>11710-2412</aptSeq>
        <buildYear>2018</buildYear>
        <contractType>신규</contractType>
        <dealDay>20</dealDay>
        <dealMonth>3</dealMonth>
        <dealYear>2026</dealYear>
        <deposit> 50,000</deposit>
        <excluUseAr>84.92</excluUseAr>
        <floor>5</floor>
        <monthlyRent> 200</monthlyRent>
        <sggCd>11710</sggCd>
        <umdNm>가락동</umdNm>
      </item>
    </items>
    <numOfRows>1000</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>3</totalCount>
  </body>
</response>
```

- [ ] **Step 3: error_response.xml** (게이트웨이 인증 실패)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<OpenAPI_ServiceResponse>
  <cmmMsgHeader>
    <errMsg>SERVICE ERROR</errMsg>
    <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
    <returnReasonCode>30</returnReasonCode>
  </cmmMsgHeader>
</OpenAPI_ServiceResponse>
```

- [ ] **Step 4: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/tests/fixtures/
git commit -m "test(realestate_monitor): API fixture (실제 스키마, 분석 필드 포함)"
```

---

## Task 3: lib/api.py — XML 파싱 + HTTP 클라이언트

**Files:**
- Create: `labs/realestate_monitor/tests/test_api.py`
- Create: `labs/realestate_monitor/lib/api.py`

`compute_size_label`은 다음 task(matcher.py)에서 만들지만, api 파싱 결과에 size_label을 채우려면 미리 생성해야 한다. 이 task에서 api.py가 matcher.py의 `compute_size_label`을 import하도록 설계한다 — 즉 Task 4를 먼저 만들어야 함.

**Task 3 → Task 4 순서를 바꿔서 matcher.py를 먼저 만든다.**

(다음 Task 4가 matcher, Task 5가 api로 재배치)

**이 Task 3은 compute_size_label만 우선 만든다.**

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_matcher.py` 신규

```python
from lib.matcher import compute_size_label, SIZE_LABELS


def test_size_label_59():
    assert compute_size_label(58.0) == "59"
    assert compute_size_label(59.97) == "59"
    assert compute_size_label(60.5) == "59"


def test_size_label_84():
    assert compute_size_label(83.0) == "84"
    assert compute_size_label(84.92) == "84"
    assert compute_size_label(85.5) == "84"


def test_size_label_mid():
    assert compute_size_label(60.6) == "mid"
    assert compute_size_label(75.0) == "mid"
    assert compute_size_label(82.99) == "mid"


def test_size_label_other():
    assert compute_size_label(50.0) == "other"
    assert compute_size_label(100.0) == "other"
    assert compute_size_label(85.6) == "other"
```

- [ ] **Step 2: Run → fail**

```bash
cd /Users/joel/Claude/labs/realestate_monitor
python3.11 -m pytest tests/test_matcher.py -v
```

Expected: FAIL — `cannot import name 'compute_size_label'`.

- [ ] **Step 3: Implement** — `lib/matcher.py` 신규

```python
"""단지 매칭 + 평형 라벨 계산."""

# (label, low, high) — 면적 범위 inclusive
SIZE_LABELS = [
    ("59", 58.0, 60.5),
    ("mid", 60.500001, 82.999999),  # 60.5 < x < 83.0
    ("84", 83.0, 85.5),
]


def compute_size_label(area: float) -> str:
    """전용면적(㎡) → '59' / 'mid' / '84' / 'other'.

    경계값 처리: 60.5는 '59', 83.0은 '84'.
    """
    if 58.0 <= area <= 60.5:
        return "59"
    if 60.5 < area < 83.0:
        return "mid"
    if 83.0 <= area <= 85.5:
        return "84"
    return "other"
```

(`SIZE_LABELS` 상수는 다른 모듈 참조용이지만 함수 내부에서는 명시적 if/elif 사용 — 경계 inclusive/exclusive 의도 명확화.)

- [ ] **Step 4: Run → pass**

```bash
python3.11 -m pytest tests/test_matcher.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/lib/matcher.py labs/realestate_monitor/tests/test_matcher.py
git commit -m "feat(realestate_monitor): compute_size_label (59/mid/84/other 분류)"
```

---

## Task 4: lib/matcher.py — 알림 룰 매칭

**Files:**
- Modify: `labs/realestate_monitor/tests/test_matcher.py` (APPEND)
- Modify: `labs/realestate_monitor/lib/matcher.py` (APPEND)

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_matcher.py` 끝에 추가:

```python
from lib.matcher import match_alert_rules


def test_match_apt_seq_and_size():
    record = {"apt_seq": "11710-2412", "size_label": "84"}
    rules = [
        {"id": "r1", "apt_seq": "11710-2412", "size_label": "84", "enabled": True},
        {"id": "r2", "apt_seq": "11710-2412", "size_label": "59", "enabled": True},
        {"id": "r3", "apt_seq": "11200-81",   "size_label": "84", "enabled": True},
    ]
    assert [r["id"] for r in match_alert_rules(record, rules)] == ["r1"]


def test_match_any_size():
    record = {"apt_seq": "11710-2412", "size_label": "other"}
    rules = [
        {"id": "rA", "apt_seq": "11710-2412", "size_label": "any", "enabled": True},
        {"id": "rB", "apt_seq": "11710-2412", "size_label": "84",  "enabled": True},
    ]
    assert [r["id"] for r in match_alert_rules(record, rules)] == ["rA"]


def test_match_disabled_rule_skipped():
    record = {"apt_seq": "11710-2412", "size_label": "84"}
    rules = [
        {"id": "r1", "apt_seq": "11710-2412", "size_label": "84", "enabled": False},
    ]
    assert match_alert_rules(record, rules) == []


def test_match_no_apt_seq_match():
    record = {"apt_seq": "11999-0001", "size_label": "84"}
    rules = [
        {"id": "r1", "apt_seq": "11710-2412", "size_label": "84", "enabled": True},
    ]
    assert match_alert_rules(record, rules) == []
```

- [ ] **Step 2: Run → fail**

```bash
python3.11 -m pytest tests/test_matcher.py::test_match_apt_seq_and_size -v
```

Expected: FAIL — `cannot import name 'match_alert_rules'`.

- [ ] **Step 3: Implement**

`lib/matcher.py` 끝에 추가:

```python
def match_alert_rules(record: dict, rules: list[dict]) -> list[dict]:
    """record(매매 또는 전월세 거래)에 매칭되는 활성 alert_rules 리스트.

    매칭 조건:
    - rule.enabled == True
    - rule.apt_seq == record.apt_seq
    - rule.size_label == record.size_label  OR  rule.size_label == 'any'
    """
    matched = []
    for r in rules:
        if not r.get("enabled", True):
            continue
        if r["apt_seq"] != record["apt_seq"]:
            continue
        if r["size_label"] != record["size_label"] and r["size_label"] != "any":
            continue
        matched.append(r)
    return matched
```

- [ ] **Step 4: Run → pass**

```bash
python3.11 -m pytest tests/test_matcher.py -v
```

Expected: 8 passed (4 size_label + 4 match_alert_rules).

- [ ] **Step 5: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/lib/matcher.py labs/realestate_monitor/tests/test_matcher.py
git commit -m "feat(realestate_monitor): match_alert_rules (apt_seq + size_label, any 룰 지원)"
```

---

## Task 5: lib/api.py — 국토부 API 클라이언트 + XML 파싱

**Files:**
- Create: `labs/realestate_monitor/tests/test_api.py`
- Create: `labs/realestate_monitor/lib/api.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_api.py`:

```python
import hashlib
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
```

- [ ] **Step 2: Run → fail**

```bash
python3.11 -m pytest tests/test_api.py -v
```

Expected: collection error or import error.

- [ ] **Step 3: Implement** — `lib/api.py`

```python
"""국토교통부 실거래가 API 클라이언트 (매매 + 전월세)."""
import hashlib
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

from lib.matcher import compute_size_label

SALE_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
RENT_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

API_TIMEOUT = 15
API_RETRY_BACKOFFS = [1, 3, 10]


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else ""


def _int_or_none(s: str) -> Optional[int]:
    s = s.replace(",", "").replace(" ", "")
    return int(s) if s else None


def _parse_sale_item(item: ET.Element) -> dict:
    year = _text(item, "dealYear")
    month = _text(item, "dealMonth").zfill(2)
    day = _text(item, "dealDay").zfill(2)
    deal_date = f"{year}-{month}-{day}" if year else None

    cancel_year_month_day = _text(item, "cdealDay")
    cancel_date = None
    if cancel_year_month_day and len(cancel_year_month_day) == 8:
        cancel_date = f"{cancel_year_month_day[:4]}-{cancel_year_month_day[4:6]}-{cancel_year_month_day[6:8]}"

    rgst = _text(item, "rgstDate")
    register_date = None
    if rgst and len(rgst) == 8:
        register_date = f"{rgst[:4]}-{rgst[4:6]}-{rgst[6:8]}"

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
    year = _text(item, "dealYear")
    month = _text(item, "dealMonth").zfill(2)
    day = _text(item, "dealDay").zfill(2)
    contract_date = f"{year}-{month}-{day}" if year else None
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

    parser = _parse_sale_item if kind == "sale" else _parse_rent_item if kind == "rent" else None
    if parser is None:
        raise ValueError(f"알 수 없는 kind: {kind}")

    return [parser(item) for item in root.findall(".//item")]


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
```

- [ ] **Step 4: Run → pass**

```bash
python3.11 -m pytest tests/test_api.py -v
```

Expected: 9 passed.

- [ ] **Step 5: 전체 테스트 확인**

```bash
python3.11 -m pytest tests/ -v
```

Expected: 17 passed (8 matcher + 9 api).

- [ ] **Step 6: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/lib/api.py labs/realestate_monitor/tests/test_api.py
git commit -m "feat(realestate_monitor): 국토부 API 클라이언트 + XML 파싱 (전체 분석 필드)"
```

---

## Task 6: lib/db.py — Supabase 클라이언트 래퍼

**Files:**
- Create: `labs/realestate_monitor/tests/test_db.py`
- Create: `labs/realestate_monitor/lib/db.py`

Supabase Python SDK는 thin wrapper로 두고, 단위 테스트는 mock으로 처리.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_db.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from lib.db import upsert_records, load_alert_rules, dedup_check, mark_alert_sent


@pytest.fixture
def mock_supabase():
    """Supabase client mock — table().upsert/select/insert chain 패턴."""
    client = MagicMock()
    return client


def test_upsert_records_calls_upsert_with_ignore(mock_supabase):
    records = [
        {"id": "abc", "apt_seq": "11710-2412", "price_만원": 198000},
        {"id": "def", "apt_seq": "11710-2412", "price_만원": 175000},
    ]
    mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = records
    
    upsert_records(mock_supabase, "sale_records", records)
    
    mock_supabase.table.assert_called_with("sale_records")
    mock_supabase.table.return_value.upsert.assert_called_once()
    args, kwargs = mock_supabase.table.return_value.upsert.call_args
    assert args[0] == records
    assert kwargs.get("on_conflict") == "id"


def test_load_alert_rules_filters_enabled(mock_supabase):
    rules = [
        {"id": "r1", "apt_seq": "11710-2412", "enabled": True},
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = rules
    
    result = load_alert_rules(mock_supabase)
    
    mock_supabase.table.assert_called_with("alert_rules")
    mock_supabase.table.return_value.select.assert_called_with("*")
    mock_supabase.table.return_value.select.return_value.eq.assert_called_with("enabled", True)
    assert result == rules


def test_dedup_check_returns_existing_keys(mock_supabase):
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"rule_id": "r1", "dedup_key": "sale:abc"},
        {"rule_id": "r1", "dedup_key": "sale:def"},
    ]
    
    candidates = [
        {"rule_id": "r1", "dedup_key": "sale:abc"},
        {"rule_id": "r1", "dedup_key": "sale:def"},
        {"rule_id": "r1", "dedup_key": "sale:ghi"},
    ]
    
    new_alerts = dedup_check(mock_supabase, candidates)
    
    assert len(new_alerts) == 1
    assert new_alerts[0]["dedup_key"] == "sale:ghi"


def test_mark_alert_sent_inserts_row(mock_supabase):
    mark_alert_sent(mock_supabase, rule_id="r1", dedup_key="sale:xyz", alert_type="price_threshold")
    
    mock_supabase.table.assert_called_with("alerts_sent")
    mock_supabase.table.return_value.insert.assert_called_once()
    args, _ = mock_supabase.table.return_value.insert.call_args
    payload = args[0]
    assert payload["rule_id"] == "r1"
    assert payload["dedup_key"] == "sale:xyz"
    assert payload["alert_type"] == "price_threshold"


def test_dedup_check_empty_candidates(mock_supabase):
    assert dedup_check(mock_supabase, []) == []
    mock_supabase.table.assert_not_called()
```

- [ ] **Step 2: Run → fail**

```bash
python3.11 -m pytest tests/test_db.py -v
```

Expected: FAIL — `cannot import name 'upsert_records'`.

- [ ] **Step 3: Implement** — `lib/db.py`

```python
"""Supabase Postgres 클라이언트 래퍼."""
from typing import Iterable

from supabase import Client, create_client


def get_client(url: str, service_role_key: str) -> Client:
    """Supabase service_role client 생성 (서버 전용, RLS 우회)."""
    return create_client(url, service_role_key)


def upsert_records(client: Client, table: str, records: list[dict]) -> None:
    """sale_records / rent_records UPSERT (id 충돌 시 무시).

    Supabase의 upsert는 PK 기준 upsert, 우리는 ON CONFLICT DO NOTHING이 필요해서
    ignore_duplicates 옵션을 활용. 실제 supabase-py upsert는 default upsert(=update)이므로
    on_conflict='id'로 PK 명시 + ignore_duplicates=True 필요.
    """
    if not records:
        return
    client.table(table).upsert(
        records,
        on_conflict="id",
        ignore_duplicates=True,
    ).execute()


def load_alert_rules(client: Client) -> list[dict]:
    """enabled = True인 alert_rules 모두 조회."""
    resp = client.table("alert_rules").select("*").eq("enabled", True).execute()
    return resp.data or []


def dedup_check(client: Client, candidates: list[dict]) -> list[dict]:
    """candidates: [{rule_id, dedup_key, ...}, ...]
    
    이미 alerts_sent에 존재하는 (rule_id, dedup_key) 조합을 제외한 신규 후보만 반환.
    """
    if not candidates:
        return []
    
    keys = [c["dedup_key"] for c in candidates]
    resp = client.table("alerts_sent").select("rule_id,dedup_key").in_("dedup_key", keys).execute()
    existing = {(row["rule_id"], row["dedup_key"]) for row in (resp.data or [])}
    
    return [c for c in candidates if (c["rule_id"], c["dedup_key"]) not in existing]


def mark_alert_sent(client: Client, *, rule_id: str, dedup_key: str, alert_type: str) -> None:
    """alerts_sent에 발송 이력 INSERT."""
    client.table("alerts_sent").insert({
        "rule_id": rule_id,
        "dedup_key": dedup_key,
        "alert_type": alert_type,
    }).execute()


def query_median_sale_price(client: Client, *, apt_seq: str, size_label: str, days: int) -> tuple[Optional[int], int]:
    """직전 N일 매매 보증금 중위값과 표본 수 반환."""
    resp = client.rpc("median_sale_price", {
        "p_apt_seq": apt_seq,
        "p_size_label": size_label,
        "p_days": days,
    }).execute()
    if not resp.data:
        return (None, 0)
    row = resp.data[0] if isinstance(resp.data, list) else resp.data
    return (row.get("median_price"), row.get("sample_count", 0))


def query_median_jeonse_deposit(client: Client, *, apt_seq: str, size_label: str, days: int) -> tuple[Optional[int], int]:
    """직전 N일 순수 전세 보증금 중위값과 표본 수 반환."""
    resp = client.rpc("median_jeonse_deposit", {
        "p_apt_seq": apt_seq,
        "p_size_label": size_label,
        "p_days": days,
    }).execute()
    if not resp.data:
        return (None, 0)
    row = resp.data[0] if isinstance(resp.data, list) else resp.data
    return (row.get("median_deposit"), row.get("sample_count", 0))
```

상단 import에 `Optional` 추가:

```python
from typing import Iterable, Optional
```

`query_median_*` 함수는 SQL RPC를 호출 — 002_views.sql에서 이 함수들을 정의 (Task 9).

- [ ] **Step 4: Run → pass**

```bash
python3.11 -m pytest tests/test_db.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/lib/db.py labs/realestate_monitor/tests/test_db.py
git commit -m "feat(realestate_monitor): Supabase 클라이언트 래퍼 (upsert/load_rules/dedup/mark_sent + RPC)"
```

---

## Task 7: lib/triggers.py — edge 트리거 판정

**Files:**
- Create: `labs/realestate_monitor/tests/test_triggers.py`
- Create: `labs/realestate_monitor/lib/triggers.py`

순수 함수만 다루고, DB 호출은 mock.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_triggers.py`:

```python
from unittest.mock import MagicMock

from lib.triggers import (
    evaluate_price_threshold,
    evaluate_jeonse_ratio,
    PriceCandidate,
    JeonseCandidate,
)


def test_evaluate_price_below_threshold():
    record = {"id": "abc123", "apt_seq": "11710-2412", "size_label": "84",
              "price_만원": 198000, "deal_date": "2026-04-28", "floor": 15}
    rule = {"id": "rule1", "apt_seq": "11710-2412", "size_label": "84",
            "max_price_만원": 200000, "enabled": True, "display_name": "헬리오시티"}
    
    cands = evaluate_price_threshold([record], [rule])
    
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, PriceCandidate)
    assert c.rule_id == "rule1"
    assert c.dedup_key == "sale:abc123"
    assert c.record == record
    assert c.rule == rule


def test_evaluate_price_above_threshold():
    record = {"id": "abc", "apt_seq": "11710-2412", "size_label": "84",
              "price_만원": 220000, "deal_date": "2026-04-28", "floor": 15}
    rule = {"id": "r1", "apt_seq": "11710-2412", "size_label": "84",
            "max_price_만원": 200000, "enabled": True, "display_name": "X"}
    
    assert evaluate_price_threshold([record], [rule]) == []


def test_evaluate_price_skipped_when_max_price_null():
    record = {"id": "abc", "apt_seq": "11710-2412", "size_label": "84",
              "price_만원": 100000, "deal_date": "2026-04-28", "floor": 15}
    rule = {"id": "r1", "apt_seq": "11710-2412", "size_label": "84",
            "max_price_만원": None, "enabled": True, "display_name": "X"}
    
    assert evaluate_price_threshold([record], [rule]) == []


def test_evaluate_jeonse_ratio_above_threshold():
    rule = {"id": "r1", "apt_seq": "11710-2412", "size_label": "84",
            "min_jeonse_ratio": 0.65, "enabled": True, "display_name": "헬리오시티"}
    
    cands = evaluate_jeonse_ratio(
        rules=[rule],
        median_sale_fn=lambda **kw: (200000, 8),   # 매매 중위 20억
        median_jeonse_fn=lambda **kw: (132000, 14),  # 전세 중위 13.2억 → 비율 0.66
        today="2026-05-04",
    )
    
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, JeonseCandidate)
    assert c.rule_id == "r1"
    assert c.dedup_key == "jeonse:2026-05"
    assert c.ratio == 0.66
    assert c.median_sale == 200000
    assert c.median_jeonse == 132000


def test_evaluate_jeonse_ratio_below_threshold():
    rule = {"id": "r1", "apt_seq": "11710-2412", "size_label": "84",
            "min_jeonse_ratio": 0.65, "enabled": True, "display_name": "X"}
    
    cands = evaluate_jeonse_ratio(
        rules=[rule],
        median_sale_fn=lambda **kw: (200000, 8),
        median_jeonse_fn=lambda **kw: (120000, 10),  # 0.60
        today="2026-05-04",
    )
    
    assert cands == []


def test_evaluate_jeonse_ratio_insufficient_samples():
    rule = {"id": "r1", "apt_seq": "11710-2412", "size_label": "84",
            "min_jeonse_ratio": 0.65, "enabled": True, "display_name": "X"}
    
    cands = evaluate_jeonse_ratio(
        rules=[rule],
        median_sale_fn=lambda **kw: (200000, 3),   # 표본 < 5
        median_jeonse_fn=lambda **kw: (132000, 14),
        today="2026-05-04",
    )
    
    assert cands == []


def test_evaluate_jeonse_ratio_skipped_when_min_null():
    rule = {"id": "r1", "apt_seq": "11710-2412", "size_label": "84",
            "min_jeonse_ratio": None, "enabled": True, "display_name": "X"}
    
    cands = evaluate_jeonse_ratio(
        rules=[rule],
        median_sale_fn=lambda **kw: (200000, 8),
        median_jeonse_fn=lambda **kw: (132000, 14),
        today="2026-05-04",
    )
    
    assert cands == []
```

- [ ] **Step 2: Run → fail**

```bash
python3.11 -m pytest tests/test_triggers.py -v
```

Expected: FAIL — `cannot import name 'evaluate_price_threshold'`.

- [ ] **Step 3: Implement** — `lib/triggers.py`

```python
"""edge 트리거 판정 — 가격 임계값 + 전세가율 임계값."""
from dataclasses import dataclass
from typing import Callable, Optional

from lib.matcher import match_alert_rules


@dataclass
class PriceCandidate:
    rule_id: str
    rule: dict
    record: dict
    dedup_key: str          # 'sale:<record.id>'
    alert_type: str = "price_threshold"


@dataclass
class JeonseCandidate:
    rule_id: str
    rule: dict
    dedup_key: str          # 'jeonse:YYYY-MM'
    ratio: float
    median_sale: int
    median_jeonse: int
    sample_count_sale: int
    sample_count_jeonse: int
    alert_type: str = "jeonse_ratio"


def evaluate_price_threshold(
    new_sale_records: list[dict],
    rules: list[dict],
) -> list[PriceCandidate]:
    """신규 매매 거래 × 룰 → 가격 임계값 도달 후보 리스트.

    매칭: rule.apt_seq == record.apt_seq AND rule.size_label IN (record.size_label, 'any')
    트리거: rule.max_price_만원 is not None AND record.price_만원 < rule.max_price_만원
    """
    candidates: list[PriceCandidate] = []
    for record in new_sale_records:
        matching_rules = match_alert_rules(record, rules)
        for rule in matching_rules:
            if rule.get("max_price_만원") is None:
                continue
            if record["price_만원"] >= rule["max_price_만원"]:
                continue
            candidates.append(PriceCandidate(
                rule_id=rule["id"],
                rule=rule,
                record=record,
                dedup_key=f"sale:{record['id']}",
            ))
    return candidates


def evaluate_jeonse_ratio(
    *,
    rules: list[dict],
    median_sale_fn: Callable,
    median_jeonse_fn: Callable,
    today: str,
    min_samples: int = 5,
    lookback_days: int = 90,
) -> list[JeonseCandidate]:
    """alert_rules 중 min_jeonse_ratio 설정된 룰을 평가.

    각 룰마다:
    - median_sale_fn / median_jeonse_fn 호출 → (median 값, 표본 수) 튜플
    - 표본 < min_samples면 skip
    - 전세가율 = median_jeonse / median_sale
    - 임계값 미달이면 skip
    - 그 외에는 후보 생성 (dedup_key = 'jeonse:YYYY-MM')

    호출자(collector.py)는 `partial(query_median_*, client)`로 client를 미리 주입.
    """
    month_key = today[:7]
    candidates: list[JeonseCandidate] = []
    
    for rule in rules:
        if rule.get("min_jeonse_ratio") is None:
            continue
        if not rule.get("enabled", True):
            continue
        
        median_sale, n_sale = median_sale_fn(
            apt_seq=rule["apt_seq"], size_label=rule["size_label"], days=lookback_days,
        )
        median_jeonse, n_jeonse = median_jeonse_fn(
            apt_seq=rule["apt_seq"], size_label=rule["size_label"], days=lookback_days,
        )
        
        if n_sale < min_samples or n_jeonse < min_samples:
            continue
        if not median_sale or median_jeonse is None:
            continue
        
        ratio = round(median_jeonse / median_sale, 4)
        if ratio < rule["min_jeonse_ratio"]:
            continue
        
        candidates.append(JeonseCandidate(
            rule_id=rule["id"], rule=rule,
            dedup_key=f"jeonse:{month_key}",
            ratio=ratio,
            median_sale=median_sale,
            median_jeonse=median_jeonse,
            sample_count_sale=n_sale,
            sample_count_jeonse=n_jeonse,
        ))
    
    return candidates
```

- [ ] **Step 4: Run → pass**

```bash
python3.11 -m pytest tests/test_triggers.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/lib/triggers.py labs/realestate_monitor/tests/test_triggers.py
git commit -m "feat(realestate_monitor): edge 트리거 (price + jeonse_ratio, 표본 부족 skip)"
```

---

## Task 8: lib/notifier.py — 텔레그램 알림 + 메시지 포맷

**Files:**
- Create: `labs/realestate_monitor/tests/test_notifier.py`
- Create: `labs/realestate_monitor/lib/notifier.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_notifier.py`:

```python
from unittest.mock import patch

import pytest

from lib.notifier import (
    format_won,
    format_price_message,
    format_jeonse_message,
    send_telegram,
)


def test_format_won_basic():
    assert format_won(198000) == "19억 8,000"
    assert format_won(200000) == "20억"
    assert format_won(7300) == "7,300"
    assert format_won(75000) == "7억 5,000"


def test_format_won_zero():
    assert format_won(0) == "0"


def test_format_price_message_includes_all_fields():
    rule = {"display_name": "헬리오시티", "size_label": "84", "max_price_만원": 200000}
    record = {"price_만원": 198000, "floor": 15, "deal_date": "2026-04-28",
              "dealing_type": "중개거래"}
    msg = format_price_message(rule, record, median_sale=198000, median_jeonse=125000,
                                sample_count_jeonse=12)
    
    assert "헬리오시티 84㎡" in msg
    assert "19억 8,000" in msg
    assert "15층" in msg
    assert "2026-04-28" in msg
    assert "12억 5,000" in msg
    assert "전세가율" in msg
    assert "63" in msg   # ratio 63.1% 포함


def test_format_price_message_when_no_jeonse_data():
    rule = {"display_name": "옥수하이츠", "size_label": "84"}
    record = {"price_만원": 195000, "floor": 10, "deal_date": "2026-04-20"}
    msg = format_price_message(rule, record, median_sale=195000, median_jeonse=None,
                                sample_count_jeonse=0)
    
    assert "전세 데이터 부족" in msg


def test_format_jeonse_message():
    rule = {"display_name": "헬리오시티", "size_label": "84", "min_jeonse_ratio": 0.65}
    msg = format_jeonse_message(rule, ratio=0.656, median_sale=195000, median_jeonse=128000,
                                 sample_count_sale=8, sample_count_jeonse=14, month_key="2026-05")
    
    assert "전세가율 임계값 도달" in msg
    assert "헬리오시티 84㎡" in msg
    assert "65" in msg
    assert "19억 5,000" in msg
    assert "12억 8,000" in msg
    assert "2026-05" in msg


@patch("lib.notifier.requests.post")
def test_send_telegram_success(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"ok": True}
    
    send_telegram(token="DUMMY_TOKEN", chat_id="12345", text="hello")
    
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "DUMMY_TOKEN" in args[0]
    assert kwargs["json"]["chat_id"] == "12345"
    assert kwargs["json"]["text"] == "hello"


@patch("lib.notifier.requests.post")
def test_send_telegram_failure_raises(mock_post):
    mock_post.return_value.status_code = 500
    mock_post.return_value.text = "Server Error"
    
    with pytest.raises(RuntimeError, match="텔레그램"):
        send_telegram(token="X", chat_id="1", text="hi")
```

- [ ] **Step 2: Run → fail**

```bash
python3.11 -m pytest tests/test_notifier.py -v
```

- [ ] **Step 3: Implement** — `lib/notifier.py`

```python
"""텔레그램 알림 + 메시지 포맷."""
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def format_won(만원: int) -> str:
    """198000 만원 → '19억 8,000'."""
    if 만원 == 0:
        return "0"
    억 = 만원 // 10000
    rest = 만원 % 10000
    if 억 == 0:
        return f"{rest:,}"
    if rest == 0:
        return f"{억}억"
    return f"{억}억 {rest:,}"


def format_price_message(
    rule: dict,
    record: dict,
    *,
    median_sale: int,
    median_jeonse: int | None,
    sample_count_jeonse: int,
) -> str:
    """가격 임계값 도달 알림 메시지."""
    head = (
        f"🏠 매매가 임계값 도달 ({rule['display_name']} {rule['size_label']}㎡)\n\n"
        f"💰 매매가  {format_won(record['price_만원'])} "
        f"({record.get('floor')}층, {record['deal_date']} 신고)"
    )
    if record.get("dealing_type"):
        head += f" · {record['dealing_type']}"
    
    if median_jeonse is None:
        body = f"\n📊 전세 데이터 부족 (최근 90일 {sample_count_jeonse}건)"
        body += "\n🔻 갭 계산 불가"
    else:
        gap = record["price_만원"] - median_jeonse
        ratio = median_jeonse / record["price_만원"]
        body = (
            f"\n📊 직전 90일 전세 시세 ({rule['size_label']}㎡, {sample_count_jeonse}건)\n"
            f"   • 중위값  {format_won(median_jeonse)}\n"
            f"🔻 갭 (매매 − 전세 중위값)  약 {format_won(gap)}\n"
            f"📈 전세가율  {ratio*100:.1f}%"
        )
    return head + body


def format_jeonse_message(
    rule: dict,
    *,
    ratio: float,
    median_sale: int,
    median_jeonse: int,
    sample_count_sale: int,
    sample_count_jeonse: int,
    month_key: str,
) -> str:
    """전세가율 임계값 도달 알림 메시지."""
    threshold_pct = rule['min_jeonse_ratio'] * 100
    gap = median_sale - median_jeonse
    return (
        f"📈 전세가율 임계값 도달 ({rule['display_name']} {rule['size_label']}㎡, "
        f"{threshold_pct:.0f}% ↑)\n\n"
        f"📊 직전 90일 중위값\n"
        f"   • 매매  {format_won(median_sale)}\n"
        f"   • 전세  {format_won(median_jeonse)}\n"
        f"🔻 갭  약 {format_won(gap)}\n"
        f"📈 전세가율  {ratio*100:.1f}%  (임계값 {threshold_pct:.1f}%)\n\n"
        f"표본: 매매 {sample_count_sale}건 / 전세 {sample_count_jeonse}건\n"
        f"{month_key} 신호 — 이 달은 추가 알림 없음"
    )


def send_telegram(*, token: str, chat_id: str, text: str) -> None:
    """텔레그램 봇 메시지 전송. 실패 시 RuntimeError."""
    url = TELEGRAM_API.format(token=token)
    resp = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"텔레그램 발송 실패 ({resp.status_code}): {resp.text[:200]}")
```

- [ ] **Step 4: Run → pass**

```bash
python3.11 -m pytest tests/test_notifier.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/lib/notifier.py labs/realestate_monitor/tests/test_notifier.py
git commit -m "feat(realestate_monitor): 텔레그램 알림 + 메시지 포맷 (price + jeonse 두 종류)"
```

---

## Task 9: SQL 마이그레이션 파일

**Files:**
- Create: `labs/realestate_monitor/sql/001_initial_schema.sql`
- Create: `labs/realestate_monitor/sql/002_views.sql`
- Create: `labs/realestate_monitor/sql/seed_districts.sql`

이 task는 Supabase에 직접 적용하지 않는다 (T16에서 적용). 파일만 생성·commit.

- [ ] **Step 1: 001_initial_schema.sql**

```sql
-- 부동산 매매·전월세 모니터링 시스템
-- 4 테이블: sale_records, rent_records, alert_rules, alerts_sent

CREATE TABLE IF NOT EXISTS sale_records (
  id              text PRIMARY KEY,
  apt_seq         text NOT NULL,
  apt_name        text,
  umd_nm          text,
  umd_cd          text,
  sgg_cd          text NOT NULL,
  jibun           text,
  road_address    text,
  deal_date       date NOT NULL,
  price_만원      integer NOT NULL,
  area            numeric(6,2) NOT NULL,
  size_label      text,
  floor           integer,
  build_year      integer,
  dealing_type    text,
  buyer_type      text,
  seller_type     text,
  agent_sgg_name  text,
  is_land_lease   boolean,
  cancel_date     date,
  cancel_type     text,
  register_date   date,
  fetched_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sale_apt_seq_date ON sale_records (apt_seq, deal_date DESC);
CREATE INDEX IF NOT EXISTS idx_sale_sgg_date     ON sale_records (sgg_cd, deal_date DESC);
CREATE INDEX IF NOT EXISTS idx_sale_size_price   ON sale_records (size_label, price_만원);

CREATE TABLE IF NOT EXISTS rent_records (
  id                    text PRIMARY KEY,
  apt_seq               text NOT NULL,
  apt_name              text,
  umd_nm                text,
  sgg_cd                text NOT NULL,
  contract_date         date NOT NULL,
  deposit_만원          integer NOT NULL,
  monthly_rent_만원     integer NOT NULL,
  area                  numeric(6,2) NOT NULL,
  size_label            text,
  floor                 integer,
  build_year            integer,
  contract_type         text,
  contract_term         text,
  pre_deposit_만원      integer,
  pre_monthly_rent_만원 integer,
  used_renewal_right    boolean,
  fetched_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rent_apt_seq_date ON rent_records (apt_seq, contract_date DESC);
CREATE INDEX IF NOT EXISTS idx_rent_sgg_date     ON rent_records (sgg_cd, contract_date DESC);

CREATE TABLE IF NOT EXISTS alert_rules (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  apt_seq           text NOT NULL,
  display_name      text NOT NULL,
  size_label        text NOT NULL,
  max_price_만원    integer,
  min_jeonse_ratio  numeric(4,3),
  enabled           boolean DEFAULT true,
  notes             text,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now(),
  CONSTRAINT alert_rules_apt_size_unique UNIQUE (apt_seq, size_label)
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules (enabled) WHERE enabled = true;

CREATE TABLE IF NOT EXISTS alerts_sent (
  rule_id     uuid NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
  dedup_key   text NOT NULL,
  alert_type  text NOT NULL,
  sent_at     timestamptz DEFAULT now(),
  PRIMARY KEY (rule_id, dedup_key)
);
```

- [ ] **Step 2: 002_views.sql**

```sql
-- 단지 검색용 view (alert_rules 작성 시)
CREATE OR REPLACE VIEW v_complexes AS
SELECT DISTINCT
  apt_seq,
  apt_name,
  sgg_cd,
  umd_nm,
  build_year,
  COUNT(*) OVER (PARTITION BY apt_seq) AS sale_records_count,
  MIN(deal_date) OVER (PARTITION BY apt_seq) AS earliest_deal,
  MAX(deal_date) OVER (PARTITION BY apt_seq) AS latest_deal
FROM sale_records;

-- 룰 검증 view
CREATE OR REPLACE VIEW v_alert_rules_check AS
SELECT
  ar.id,
  ar.apt_seq,
  ar.display_name,
  ar.size_label,
  ar.max_price_만원,
  ar.min_jeonse_ratio,
  ar.enabled,
  vc.apt_name AS actual_apt_name,
  vc.sgg_cd AS actual_sgg_cd,
  CASE
    WHEN vc.apt_seq IS NULL THEN '⚠️ apt_seq 미존재'
    WHEN ar.display_name != vc.apt_name THEN '⚠️ display_name 불일치'
    ELSE '✅ OK'
  END AS validation
FROM alert_rules ar
LEFT JOIN (SELECT DISTINCT apt_seq, apt_name, sgg_cd FROM sale_records) vc
  ON ar.apt_seq = vc.apt_seq;

-- 월별 집계 MV (대시보드 성능)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_monthly_sale_stats AS
SELECT
  apt_seq, apt_name, sgg_cd, size_label,
  DATE_TRUNC('month', deal_date) AS month,
  COUNT(*) AS deals,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS median_price,
  MIN(price_만원) AS min_price,
  MAX(price_만원) AS max_price
FROM sale_records
GROUP BY apt_seq, apt_name, sgg_cd, size_label, DATE_TRUNC('month', deal_date);

CREATE INDEX IF NOT EXISTS idx_mv_monthly_sale ON mv_monthly_sale_stats (apt_seq, size_label, month);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_monthly_rent_stats AS
SELECT
  apt_seq, apt_name, sgg_cd, size_label,
  DATE_TRUNC('month', contract_date) AS month,
  COUNT(*) AS contracts,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_만원) FILTER (WHERE monthly_rent_만원 = 0) AS median_jeonse,
  MIN(deposit_만원) FILTER (WHERE monthly_rent_만원 = 0) AS min_jeonse,
  MAX(deposit_만원) FILTER (WHERE monthly_rent_만원 = 0) AS max_jeonse
FROM rent_records
GROUP BY apt_seq, apt_name, sgg_cd, size_label, DATE_TRUNC('month', contract_date);

CREATE INDEX IF NOT EXISTS idx_mv_monthly_rent ON mv_monthly_rent_stats (apt_seq, size_label, month);

-- triggers.py가 호출하는 RPC
CREATE OR REPLACE FUNCTION median_sale_price(
  p_apt_seq text,
  p_size_label text,
  p_days integer
) RETURNS TABLE(median_price integer, sample_count integer)
LANGUAGE sql STABLE AS $$
  SELECT
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원)::integer AS median_price,
    COUNT(*)::integer AS sample_count
  FROM sale_records
  WHERE apt_seq = p_apt_seq
    AND size_label = p_size_label
    AND deal_date >= CURRENT_DATE - p_days;
$$;

CREATE OR REPLACE FUNCTION median_jeonse_deposit(
  p_apt_seq text,
  p_size_label text,
  p_days integer
) RETURNS TABLE(median_deposit integer, sample_count integer)
LANGUAGE sql STABLE AS $$
  SELECT
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_만원)::integer AS median_deposit,
    COUNT(*)::integer AS sample_count
  FROM rent_records
  WHERE apt_seq = p_apt_seq
    AND size_label = p_size_label
    AND monthly_rent_만원 = 0
    AND contract_date >= CURRENT_DATE - p_days;
$$;
```

- [ ] **Step 3: seed_districts.sql** (참고용 — 실 코드는 collector에서 사용)

```sql
-- 9개 구 LAWD_CD 매핑 (참고용 주석 — 실 코드는 collector.py의 DISTRICT_LAWD_CDS)
--   11200 = 성동구
--   11215 = 광진구
--   11440 = 마포구
--   11650 = 서초구
--   11680 = 강남구
--   11710 = 송파구
--   11170 = 용산구
--   11590 = 동작구
--   11740 = 강동구
-- collector.py의 DISTRICT_LAWD_CDS에서 동일 값 사용.
```

- [ ] **Step 4: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/sql/
git commit -m "feat(realestate_monitor): SQL 마이그레이션 (4 테이블 + 2 view + 2 MV + 2 RPC)"
```

---

## Task 10: collector.py — 메인 오케스트레이션

**Files:**
- Create: `labs/realestate_monitor/collector.py`

이 task는 lib/* 모듈을 조립하는 entry point. 단위 테스트 없음 (간단 import 체크만). 실제 실행 검증은 T21에서 GitHub Actions로.

- [ ] **Step 1: collector.py 작성**

```python
"""부동산 매매·전월세 일일 수집·트리거·알림 메인 엔트리.

GitHub Actions cron이 호출. 또는 로컬에서 수동 실행:
  python3.11 collector.py
  python3.11 collector.py --dry-run
  python3.11 collector.py --backfill-months 12
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from lib.api import fetch_sales, fetch_rents, make_record_id
from lib.db import (
    get_client,
    upsert_records,
    load_alert_rules,
    dedup_check,
    mark_alert_sent,
    query_median_sale_price,
    query_median_jeonse_deposit,
)
from lib.notifier import (
    format_price_message,
    format_jeonse_message,
    send_telegram,
)
from lib.triggers import (
    PriceCandidate,
    JeonseCandidate,
    evaluate_price_threshold,
    evaluate_jeonse_ratio,
)

KST = timezone(timedelta(hours=9))

DISTRICT_LAWD_CDS = [
    ("11200", "성동구"),
    ("11215", "광진구"),
    ("11440", "마포구"),
    ("11650", "서초구"),
    ("11680", "강남구"),
    ("11710", "송파구"),
    ("11170", "용산구"),
    ("11590", "동작구"),
    ("11740", "강동구"),
]

logger = logging.getLogger("collector")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def ymd_list(months_back: int) -> list[str]:
    """오늘 기준 직전 N개월 (이번달 포함) YYYYMM 리스트, 최신 먼저."""
    today = datetime.now(KST)
    out = []
    y, m = today.year, today.month
    for _ in range(months_back):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out


def collect_records(service_key: str, months: int) -> tuple[list[dict], list[dict]]:
    """9개 구 × 매매·전월세 × N개월 수집. 각 record에 id 부착."""
    sales: list[dict] = []
    rents: list[dict] = []
    
    for ymd in ymd_list(months):
        for lawd_cd, district_name in DISTRICT_LAWD_CDS:
            try:
                for r in fetch_sales(lawd_cd=lawd_cd, ymd=ymd, service_key=service_key):
                    r["id"] = make_record_id(r, kind="sale")
                    sales.append(r)
            except Exception as e:
                logger.error("매매 fetch 실패 lawd=%s ymd=%s: %s", lawd_cd, ymd, e)
            
            try:
                for r in fetch_rents(lawd_cd=lawd_cd, ymd=ymd, service_key=service_key):
                    r["id"] = make_record_id(r, kind="rent")
                    rents.append(r)
            except Exception as e:
                logger.error("전월세 fetch 실패 lawd=%s ymd=%s: %s", lawd_cd, ymd, e)
            
            time.sleep(0.5)   # rate limit 안전 margin
    
    return sales, rents


def find_new_records(client, table: str, candidate_records: list[dict]) -> list[dict]:
    """UPSERT 전 후보 record 중 DB에 없는 신규만 식별.

    UPSERT는 ON CONFLICT DO NOTHING이라 모두 INSERT 시도하지만, 트리거 평가는
    "방금 새로 들어온 row만" 대상으로 해야 한다. 따라서 UPSERT 전 또는 후에
    in-DB 여부를 구분해야 함.

    구현: 후보 record id 목록 → DB에 이미 있는 id를 SELECT로 조회 → 차집합.
    """
    if not candidate_records:
        return []
    
    ids = [r["id"] for r in candidate_records]
    # Supabase python: in_ 필터로 한 번에 조회
    resp = client.table(table).select("id").in_("id", ids).execute()
    existing = {row["id"] for row in (resp.data or [])}
    
    return [r for r in candidate_records if r["id"] not in existing]


def process_price_alerts(
    client,
    bot_token: str,
    chat_id: str,
    new_sales: list[dict],
    rules: list[dict],
    dry_run: bool,
) -> int:
    """가격 임계값 도달 후보 평가 → dedup → 발송."""
    candidates = evaluate_price_threshold(new_sales, rules)
    if not candidates:
        return 0
    
    # dedup_check는 dict 입력이므로 변환
    cand_dicts = [{"rule_id": c.rule_id, "dedup_key": c.dedup_key} for c in candidates]
    new_keys = {(d["rule_id"], d["dedup_key"]) for d in dedup_check(client, cand_dicts)}
    
    sent_count = 0
    for c in candidates:
        if (c.rule_id, c.dedup_key) not in new_keys:
            continue
        
        # 갭 컨텍스트: 직전 90일 전세 중위
        median_jeonse, n_jeonse = query_median_jeonse_deposit(
            client, apt_seq=c.record["apt_seq"], size_label=c.record["size_label"], days=90,
        )
        
        msg = format_price_message(
            c.rule, c.record,
            median_sale=c.record["price_만원"],
            median_jeonse=median_jeonse,
            sample_count_jeonse=n_jeonse,
        )
        candidate_log = (
            f"[CANDIDATE] type=price_threshold rule_id={c.rule_id} "
            f"apt_seq={c.record['apt_seq']} deal_date={c.record['deal_date']} "
            f"price={c.record['price_만원']}"
        )
        logger.info(candidate_log)
        
        if dry_run:
            logger.info("[DRY-RUN] would send: %s", msg.replace("\n", " | "))
            continue
        
        try:
            send_telegram(token=bot_token, chat_id=chat_id, text=msg)
            mark_alert_sent(client, rule_id=c.rule_id, dedup_key=c.dedup_key, alert_type=c.alert_type)
            sent_count += 1
        except Exception as e:
            logger.error("price 알림 발송 실패 (재시도는 다음 cron): %s", e)
    
    return sent_count


def process_jeonse_alerts(
    client,
    bot_token: str,
    chat_id: str,
    rules: list[dict],
    today: str,
    dry_run: bool,
) -> int:
    """전세가율 임계값 도달 후보 평가 → dedup → 발송."""
    candidates = evaluate_jeonse_ratio(
        rules=rules,
        median_sale_fn=partial(query_median_sale_price, client),
        median_jeonse_fn=partial(query_median_jeonse_deposit, client),
        today=today,
    )
    if not candidates:
        return 0
    
    cand_dicts = [{"rule_id": c.rule_id, "dedup_key": c.dedup_key} for c in candidates]
    new_keys = {(d["rule_id"], d["dedup_key"]) for d in dedup_check(client, cand_dicts)}
    
    sent_count = 0
    for c in candidates:
        if (c.rule_id, c.dedup_key) not in new_keys:
            continue
        
        msg = format_jeonse_message(
            c.rule,
            ratio=c.ratio,
            median_sale=c.median_sale,
            median_jeonse=c.median_jeonse,
            sample_count_sale=c.sample_count_sale,
            sample_count_jeonse=c.sample_count_jeonse,
            month_key=c.dedup_key.split(":")[1],
        )
        candidate_log = (
            f"[CANDIDATE] type=jeonse_ratio rule_id={c.rule_id} "
            f"apt_seq={c.rule['apt_seq']} ratio={c.ratio} "
            f"median_sale={c.median_sale} median_jeonse={c.median_jeonse}"
        )
        logger.info(candidate_log)
        
        if dry_run:
            logger.info("[DRY-RUN] would send: %s", msg.replace("\n", " | "))
            continue
        
        try:
            send_telegram(token=bot_token, chat_id=chat_id, text=msg)
            mark_alert_sent(client, rule_id=c.rule_id, dedup_key=c.dedup_key, alert_type=c.alert_type)
            sent_count += 1
        except Exception as e:
            logger.error("jeonse 알림 발송 실패: %s", e)
    
    return sent_count


def refresh_materialized_views(client) -> None:
    """대시보드용 MV 새로고침. CONCURRENTLY는 PK가 없으면 안 되므로 일반 REFRESH."""
    try:
        client.rpc("execute_refresh_mv").execute()
    except Exception as e:
        logger.warning("MV refresh 실패 (대시보드만 영향): %s", e)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="알림 발송 X, 후보만 로그")
    parser.add_argument("--backfill-months", type=int, default=2,
                        help="N개월 fetch (기본 2: 이번 달 + 직전 달)")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="API fetch skip (DB 트리거만 평가, 디버그용)")
    args = parser.parse_args()
    
    setup_logging()
    
    # 환경 변수 로드 (.env가 있으면 로컬, 없으면 GitHub Actions secrets)
    here = Path(__file__).parent
    if (here / ".env").exists():
        load_dotenv(here / ".env")
    
    service_key = os.environ.get("MOLIT_SERVICE_KEY", "").strip()
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    
    missing = [k for k, v in [
        ("MOLIT_SERVICE_KEY", service_key),
        ("TELEGRAM_BOT_TOKEN", bot_token),
        ("TELEGRAM_CHAT_ID", chat_id),
        ("SUPABASE_URL", supabase_url),
        ("SUPABASE_SERVICE_ROLE_KEY", supabase_key),
    ] if not v]
    if missing:
        logger.error("필수 환경변수 누락: %s", missing)
        return 2
    
    client = get_client(supabase_url, supabase_key)
    today_iso = datetime.now(KST).date().isoformat()
    
    new_sales: list[dict] = []
    new_rents: list[dict] = []
    
    if not args.skip_fetch:
        logger.info("데이터 수집 시작 (직전 %d개월, %d개 구)", args.backfill_months, len(DISTRICT_LAWD_CDS))
        sales, rents = collect_records(service_key, args.backfill_months)
        logger.info("수집 완료: 매매 %d건, 전월세 %d건", len(sales), len(rents))
        
        new_sales = find_new_records(client, "sale_records", sales)
        new_rents = find_new_records(client, "rent_records", rents)
        logger.info("DB 신규: 매매 %d건, 전월세 %d건", len(new_sales), len(new_rents))
        
        upsert_records(client, "sale_records", sales)
        upsert_records(client, "rent_records", rents)
    
    rules = load_alert_rules(client)
    logger.info("활성 알림 룰: %d개", len(rules))
    
    price_sent = process_price_alerts(client, bot_token, chat_id, new_sales, rules, args.dry_run)
    jeonse_sent = process_jeonse_alerts(client, bot_token, chat_id, rules, today_iso, args.dry_run)
    
    logger.info("발송 완료: price %d건, jeonse %d건", price_sent, jeonse_sent)
    
    refresh_materialized_views(client)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: import sanity 체크**

```bash
cd /Users/joel/Claude/labs/realestate_monitor
python3.11 -c "import collector; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: argparse help 확인**

```bash
python3.11 collector.py --help
```

Expected: `--dry-run`, `--backfill-months`, `--skip-fetch` 옵션 표시.

- [ ] **Step 4: 모든 기존 테스트 재실행 (regression 방지)**

```bash
python3.11 -m pytest tests/ -v
```

Expected: 모든 단위 테스트 PASS (Tasks 3-8 누적).

- [ ] **Step 5: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/collector.py
git commit -m "feat(realestate_monitor): collector.py 메인 오케스트레이션 (수집·트리거·알림·MV refresh)"
```

---

## Task 11: scripts/backfill.py — 1년 백필 스크립트

**Files:**
- Create: `labs/realestate_monitor/scripts/__init__.py`
- Create: `labs/realestate_monitor/scripts/backfill.py`

- [ ] **Step 1: scripts/__init__.py** (빈 파일)

```python
```

- [ ] **Step 2: scripts/backfill.py**

```python
"""1년 백필 — 1회성 수동 실행.

사용:
  python3.11 scripts/backfill.py --months 12
  python3.11 scripts/backfill.py --months 12 --dry-run
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# 부모 디렉토리를 path에 추가하여 lib/* 임포트 가능하게
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from collector import (
    DISTRICT_LAWD_CDS,
    collect_records,
    setup_logging,
)
from lib.db import get_client, upsert_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=12, help="백필 개월 수")
    parser.add_argument("--dry-run", action="store_true", help="DB UPSERT 안 함")
    args = parser.parse_args()
    
    setup_logging()
    logger = logging.getLogger("backfill")
    
    here = Path(__file__).parent.parent
    if (here / ".env").exists():
        load_dotenv(here / ".env")
    
    service_key = os.environ.get("MOLIT_SERVICE_KEY", "").strip()
    if not service_key:
        logger.error("MOLIT_SERVICE_KEY 미설정")
        return 2
    
    if not args.dry_run:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            logger.error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정")
            return 2
        client = get_client(url, key)
    
    logger.info("백필 시작: %d개월 × 9개 구 × 매매·전세", args.months)
    sales, rents = collect_records(service_key, args.months)
    logger.info("수집: 매매 %d건, 전세 %d건", len(sales), len(rents))
    
    if args.dry_run:
        logger.info("[DRY-RUN] UPSERT skip — 첫 5개 매매 sample:")
        for r in sales[:5]:
            logger.info("  %s %s %s %s만원 %s㎡",
                        r.get("apt_name"), r.get("size_label"),
                        r.get("deal_date"), r.get("price_만원"), r.get("area"))
        return 0
    
    # 1000건씩 batch UPSERT (Supabase 한 번에 크게 보내면 timeout 가능)
    BATCH = 500
    for i in range(0, len(sales), BATCH):
        upsert_records(client, "sale_records", sales[i:i+BATCH])
    for i in range(0, len(rents), BATCH):
        upsert_records(client, "rent_records", rents[i:i+BATCH])
    
    logger.info("백필 완료: 매매 %d / 전세 %d UPSERT", len(sales), len(rents))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: import 체크**

```bash
cd /Users/joel/Claude/labs/realestate_monitor
python3.11 scripts/backfill.py --help
```

Expected: `--months`, `--dry-run` 표시.

- [ ] **Step 4: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/scripts/
git commit -m "feat(realestate_monitor): backfill.py 1년 백필 스크립트 (배치 UPSERT)"
```

---

## Task 12: scripts/seed_alerts_sent.py — 백필 후 dedup 키 미리 채우기

**Files:**
- Create: `labs/realestate_monitor/scripts/seed_alerts_sent.py`

- [ ] **Step 1: 작성**

```python
"""백필된 데이터 중 사용자 alert_rules의 임계값을 이미 충족한 거래에 대해
alerts_sent에 dedup 키를 미리 채워, 운영 시작 첫 실행에서 알림 폭격을 방지한다.

알림 메시지는 발송하지 않고, 'seed' 표시로 alerts_sent에만 INSERT.

사용:
  python3.11 scripts/seed_alerts_sent.py
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from collector import setup_logging
from lib.db import (
    get_client,
    load_alert_rules,
    mark_alert_sent,
    query_median_sale_price,
    query_median_jeonse_deposit,
)
from lib.triggers import (
    evaluate_price_threshold,
    evaluate_jeonse_ratio,
)

KST = timezone(timedelta(hours=9))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    setup_logging()
    logger = logging.getLogger("seed_alerts_sent")
    
    here = Path(__file__).parent.parent
    if (here / ".env").exists():
        load_dotenv(here / ".env")
    
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        logger.error("Supabase 환경변수 누락")
        return 2
    
    client = get_client(url, key)
    rules = load_alert_rules(client)
    logger.info("활성 룰 %d개에 대해 seed 진행", len(rules))
    
    today_iso = datetime.now(KST).date().isoformat()
    
    # 1) Price threshold seed
    # alert_rules에 매칭되는 모든 sale_records를 PostgREST로 조회 → evaluate
    seeded_price = 0
    for rule in rules:
        if rule.get("max_price_만원") is None:
            continue
        # 해당 단지·평형·임계값 미만 거래 모두
        q = client.table("sale_records").select("*") \
            .eq("apt_seq", rule["apt_seq"])
        if rule["size_label"] != "any":
            q = q.eq("size_label", rule["size_label"])
        q = q.lt("price_만원", rule["max_price_만원"])
        sales = q.execute().data or []
        
        for s in sales:
            dedup_key = f"sale:{s['id']}"
            try:
                if not args.dry_run:
                    mark_alert_sent(client, rule_id=rule["id"], dedup_key=dedup_key,
                                    alert_type="price_threshold")
                seeded_price += 1
            except Exception:
                # 이미 PK 있으면 무시
                pass
        logger.info("rule=%s (%s %s): seed %d개", rule["id"], rule["display_name"], rule["size_label"], len(sales))
    
    # 2) Jeonse ratio seed — 현재 임계값 충족 시 이번 달 키 미리 등록
    cands = evaluate_jeonse_ratio(
        rules=rules,
        median_sale_fn=partial(query_median_sale_price, client),
        median_jeonse_fn=partial(query_median_jeonse_deposit, client),
        today=today_iso,
    )
    seeded_jeonse = 0
    for c in cands:
        try:
            if not args.dry_run:
                mark_alert_sent(client, rule_id=c.rule_id, dedup_key=c.dedup_key,
                                alert_type="jeonse_ratio")
            seeded_jeonse += 1
        except Exception:
            pass
    
    logger.info("seed 완료: price %d개, jeonse %d개", seeded_price, seeded_jeonse)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: import 체크**

```bash
python3.11 scripts/seed_alerts_sent.py --help
```

Expected: `--dry-run` 옵션 표시.

- [ ] **Step 3: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/scripts/seed_alerts_sent.py
git commit -m "feat(realestate_monitor): seed_alerts_sent.py — 백필 거래에 dedup 키 미리 채워 폭격 방지"
```

---

## Task 13: GitHub Actions workflow

**Files:**
- Create: `labs/realestate_monitor/.github/workflows/monitor.yml`

> 주: GitHub Actions workflow 파일은 보통 repo root의 `.github/workflows/`에 둔다. 우리는 monorepo 안의 sub-project이므로 push 시점에 root로 옮겨야 한다 (Task 14에서 안내).

이번 Task는 일단 **labs/realestate_monitor/ 내부**에 두고, push 시점에 적절히 위치 조정.

- [ ] **Step 1: monitor.yml 작성**

```yaml
name: realestate_monitor cron

on:
  schedule:
    # 매일 18:00 KST = 09:00 UTC
    - cron: "0 9 * * *"
  workflow_dispatch:
    inputs:
      dry_run:
        description: "dry-run mode (no alerts)"
        type: boolean
        default: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      
      - name: Run collector
        env:
          MOLIT_SERVICE_KEY: ${{ secrets.MOLIT_SERVICE_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: |
          ARGS=""
          if [ "${{ github.event.inputs.dry_run }}" = "true" ]; then
            ARGS="--dry-run"
          fi
          python collector.py $ARGS
```

- [ ] **Step 2: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/.github/
git commit -m "feat(realestate_monitor): GitHub Actions cron workflow (09/18시 KST + workflow_dispatch)"
```

---

## Task 14: README

**Files:**
- Create: `labs/realestate_monitor/README.md`

- [ ] **Step 1: README 작성**

```markdown
# realestate_monitor

서울 9개 구(성동·광진·마포·서초·강남·송파·용산·동작·강동) 아파트 매매·전월세 거래를 매일 Supabase에 누적하고, 관심 매물의 가격·전세가율 임계값 도달 시 텔레그램으로 알림을 보낸다. 사이클·갭 분석은 Supabase Studio Reports에서 시각화.

## 인프라

- **GitHub Actions** (cron 매일 18:00 KST 1회, private repo)
- **Supabase** (PostgreSQL, 무료 500MB)
- **Metabase Cloud** (대시보드, 무료)
- **Telegram Bot** (알림)

비용: 0원.

## 셋업

### 1. 외부 계정 (사용자)

| 서비스 | 작업 | 메모 |
|---|---|---|
| 공공데이터포털 | 국토부 매매·전월세 API 활용신청 | service key 발급 |
| Telegram | BotFather에서 봇 생성 → token + chat_id | |
| GitHub | private repo `realestate-monitor` 생성 + 2FA | PAT 발급(`repo`, `workflow` scope) |
| Supabase | 새 프로젝트 + DB 비밀번호 + Service Role Key | |

### 2. 로컬 .env 작성

```bash
cp .env.example .env
# 편집: 5개 키 모두 입력
```

### 3. SQL 마이그레이션 적용 (Supabase MCP 또는 Studio)

```bash
# Supabase Studio → SQL Editor에서 순서대로 실행:
sql/001_initial_schema.sql
sql/002_views.sql
```

또는 Supabase MCP 도구로 자동 적용.

### 4. 로컬 의존성

```bash
python3.11 -m pip install --user -r requirements.txt
```

### 5. 백필 (1회성)

```bash
python3.11 scripts/backfill.py --months 12
# ~5분 소요, 9개 구 × 12개월 × 매매·전세 = 216 API 호출
```

### 6. 관심 매물 등록 (Supabase Studio)

```sql
-- 단지 검색
SELECT * FROM v_complexes WHERE apt_name LIKE '%헬리오시티%' AND sgg_cd = '11710';

-- alert_rules INSERT
INSERT INTO alert_rules (apt_seq, display_name, size_label, max_price_만원, min_jeonse_ratio)
VALUES ('11710-2412', '헬리오시티', '84', 200000, 0.65);

-- 검증
SELECT * FROM v_alert_rules_check;
```

### 7. 백필된 거래에 dedup 키 미리 채우기 (폭격 방지)

```bash
python3.11 scripts/seed_alerts_sent.py
```

### 8. GitHub Secrets 등록

```bash
gh secret set MOLIT_SERVICE_KEY -b "..."
gh secret set TELEGRAM_BOT_TOKEN -b "..."
gh secret set TELEGRAM_CHAT_ID -b "..."
gh secret set SUPABASE_URL -b "..."
gh secret set SUPABASE_SERVICE_ROLE_KEY -b "..."
```

또는 GitHub repo → Settings → Secrets에서 수동 등록.

### 9. 수동 첫 실행

```bash
gh workflow run monitor.yml -f dry_run=true
gh run watch
```

로그·DB 검증 후 `dry_run=false`로 정식 가동.

### 10. Metabase 가동

```
1. metabase.com/cloud 가입
2. New Database → PostgreSQL → Supabase 연결
3. 대시보드 생성 (쿼리는 docs/2026-05-04-system-design.md 5절 참조)
```

## 운영

```bash
# 수동 실행
python3.11 collector.py --dry-run

# 단지 추가
# Supabase Studio → alert_rules 테이블에 row INSERT

# 워크플로 manual trigger
gh workflow run monitor.yml
```

## 테스트

```bash
python3.11 -m pytest tests/ -v
```

## 디렉토리

- `collector.py` — 메인
- `lib/` — 모듈 (api, matcher, db, triggers, notifier)
- `sql/` — 스키마·view·MV·RPC
- `scripts/` — 백필·seed
- `.github/workflows/` — cron
- `tests/` — 단위 테스트
- `docs/` — 설계·plan 문서
```

- [ ] **Step 2: Commit**

```bash
cd /Users/joel/Claude
git add labs/realestate_monitor/README.md
git commit -m "docs(realestate_monitor): README — 셋업·운영·디렉토리 가이드"
```

---

## Task 15: GitHub repo 생성 + 코드 push (사용자 협업)

**사용자가 직접 또는 gh CLI로 진행**.

- [ ] **Step 1: GitHub PAT 발급 및 환경변수 등록 (사용자)**

1. https://github.com/settings/tokens → Generate new token (classic)
2. scope: `repo`, `workflow`
3. expiry: 90일 (or longer)
4. 발급 후 token 복사
5. `~/.zshrc` 끝에 추가:
   ```bash
   export GITHUB_TOKEN="ghp_..."
   ```
6. 새 셸: `source ~/.zshrc`

- [ ] **Step 2: 빈 private repo 생성 (gh CLI)**

```bash
gh repo create realestate-monitor --private --description "Seoul 8-district real estate monitor"
```

또는 https://github.com/new 에서 수동.

- [ ] **Step 3: 로컬 sub-directory를 별도 repo로 push**

```bash
cd /Users/joel/Claude/labs/realestate_monitor

# repo init (이미 부모 워크스페이스가 git이라 별도 작업 필요)
git init
git add .
git commit -m "Initial: cloud realestate monitor system"
git remote add origin https://github.com/<USERNAME>/realestate-monitor.git
git branch -M main
git push -u origin main
```

> 주의: `.github/workflows/monitor.yml` 경로 그대로 push되어야 함. 위 init 명령은 `labs/realestate_monitor/` 안에서 실행했으므로 워크플로 경로가 `/labs/realestate_monitor/.github/workflows/monitor.yml`이 아니라 `/.github/workflows/monitor.yml`이 됨 — 이게 맞음.

- [ ] **Step 4: push 검증**

```bash
gh repo view <USERNAME>/realestate-monitor --web
```

브라우저에서 코드 + workflow 표시 확인.

---

## Task 16: Supabase SQL 마이그레이션 적용

**Files:** (외부 시스템 — Supabase)

Supabase MCP가 연결되어 있으니 자동 적용 가능.

- [ ] **Step 1: Supabase 프로젝트 ID 확인**

Supabase MCP로 `mcp__plugin_supabase_supabase__list_projects` 호출.

- [ ] **Step 2: 001_initial_schema.sql 적용**

`mcp__plugin_supabase_supabase__apply_migration`:
- `name`: `001_initial_schema`
- `query`: `sql/001_initial_schema.sql` 전체 내용

- [ ] **Step 3: 002_views.sql 적용**

`mcp__plugin_supabase_supabase__apply_migration`:
- `name`: `002_views`
- `query`: `sql/002_views.sql` 전체 내용

- [ ] **Step 4: 검증**

`mcp__plugin_supabase_supabase__list_tables` → `sale_records`, `rent_records`, `alert_rules`, `alerts_sent` 4개 확인.

`mcp__plugin_supabase_supabase__execute_sql`:
```sql
SELECT count(*) FROM sale_records;   -- 0
SELECT count(*) FROM v_complexes;    -- 0
```

---

## Task 17: 백필 실행 (로컬)

- [ ] **Step 1: .env에 Supabase 정보 추가 (사용자)**

```
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...
```

- [ ] **Step 2: 백필 실행**

```bash
cd /Users/joel/Claude/labs/realestate_monitor
python3.11 scripts/backfill.py --months 12
```

Expected: ~5분, "매매 X건 / 전세 Y건 UPSERT" 로그.

- [ ] **Step 3: DB 확인**

Supabase MCP `execute_sql`:
```sql
SELECT count(*) FROM sale_records;
SELECT count(*) FROM rent_records;
SELECT sgg_cd, count(*) FROM sale_records GROUP BY sgg_cd ORDER BY 1;
```

9개 구 모두 데이터 존재 확인.

---

## Task 18: alert_rules INSERT (사용자)

- [ ] **Step 1: 단지 검색 (Supabase Studio SQL Editor)**

사용자가 자기 관심 매물의 apt_seq를 검색:
```sql
SELECT * FROM v_complexes WHERE apt_name LIKE '%헬리오시티%' AND sgg_cd = '11710';
SELECT * FROM v_complexes WHERE apt_name LIKE '%서울숲푸르지오%' AND sgg_cd = '11200';
-- 등
```

- [ ] **Step 2: alert_rules에 INSERT**

각 관심 매물마다:
```sql
INSERT INTO alert_rules (apt_seq, display_name, size_label, max_price_만원, min_jeonse_ratio, enabled)
VALUES
  ('11710-2412', '헬리오시티', '84', 200000, 0.65, true),
  ('11710-2412', '헬리오시티', '59', 150000, 0.65, true);
-- 등
```

- [ ] **Step 3: 검증**

```sql
SELECT * FROM v_alert_rules_check;
```

`validation` 컬럼 모두 ✅ OK인지 확인.

---

## Task 19: seed_alerts_sent 실행

- [ ] **Step 1: dry-run 먼저**

```bash
python3.11 scripts/seed_alerts_sent.py --dry-run
```

로그에서 "rule=... seed N개" 확인. 너무 많으면 임계값을 낮추거나 룰을 좁혀서 재조정.

- [ ] **Step 2: 정식 실행**

```bash
python3.11 scripts/seed_alerts_sent.py
```

- [ ] **Step 3: DB 확인**

```sql
SELECT alert_type, count(*) FROM alerts_sent GROUP BY 1;
```

price + jeonse 두 종류로 누적되어야 함.

---

## Task 20: GitHub Secrets 등록

- [ ] **Step 1: gh CLI로 5개 secrets 등록**

```bash
cd /Users/joel/Claude/labs/realestate_monitor   # repo 디렉토리
gh secret set MOLIT_SERVICE_KEY                  # 값 직접 입력
gh secret set TELEGRAM_BOT_TOKEN
gh secret set TELEGRAM_CHAT_ID
gh secret set SUPABASE_URL
gh secret set SUPABASE_SERVICE_ROLE_KEY
```

- [ ] **Step 2: 검증**

```bash
gh secret list
```

5개 모두 등록되어 있는지 확인.

---

## Task 21: 첫 워크플로 수동 실행 + 검증

- [ ] **Step 1: dry-run 수동 트리거**

```bash
gh workflow run monitor.yml -f dry_run=true
gh run list --limit 5
gh run watch <run_id>
```

- [ ] **Step 2: 로그 검증**

```bash
gh run view <run_id> --log
```

확인 항목:
- "데이터 수집 시작..." → "수집 완료: 매매 X건..."
- "DB 신규: ..."
- "발송 완료: price 0건, jeonse 0건" (백필 + seed 직후라 0건 정상)
- 에러 없음

- [ ] **Step 3: dry-run OFF로 정식 가동**

다음 cron(18:00 KST)을 기다리거나 수동 트리거:
```bash
gh workflow run monitor.yml -f dry_run=false
```

- [ ] **Step 4: 24시간 close monitoring**

다음 cron 2회(아침·저녁) 모두 정상 실행되는지 확인:
- GitHub Actions 로그
- Supabase `sale_records.fetched_at` 최신화
- 텔레그램 폭격 없음 (소량 정상 알림은 OK)

---

## Task 22: Metabase 가입 + 대시보드 셋업

- [ ] **Step 1: Metabase Cloud 가입 (사용자)**

https://metabase.com/cloud → free trial → 가입.

- [ ] **Step 2: Supabase 연결**

```
Admin → Databases → Add database → PostgreSQL
  Host: <project>.supabase.co
  Port: 5432
  Database: postgres
  Username: postgres
  Password: <DB password from Supabase Settings>
  SSL: enable
```

- [ ] **Step 3: 대시보드 1 (관심 매물 모니터) 생성**

새 dashboard "관심 매물 모니터" 생성. SQL Question 3개 추가:
- 차트 1-1 (관심 매물 현황 — 테이블)
- 차트 1-2 (매매 시세 + MA — 라인)
- 차트 1-3 (갭 추이 — 듀얼축)

각 SQL은 `docs/2026-05-04-system-design.md` 5장에서 복사.

- [ ] **Step 4: 대시보드 2 (시장 개요) 생성**

차트 2-1 (9개 구 거래량), 2-2 (평형별 시세).

- [ ] **Step 5: 대시보드 3 (상세 분석)**

선택. 운영 후 분석 욕구 발생 시 추가.

---

## Self-Review

### 1. Spec coverage

| Spec 섹션 | 구현 Task |
|---|---|
| 1. 아키텍처 | T13 (workflow), T15 (push), T16 (Supabase) |
| 2.2 sale_records | T9 (SQL), T5 (parsing) |
| 2.3 rent_records | T9, T5 |
| 2.4 alert_rules | T9, T18 (INSERT) |
| 2.5 alerts_sent | T9, T6 (db.py) |
| 2.6 view + MV | T9 |
| 3.1 백필 | T11, T17 |
| 3.2 일일 운영 | T10 (collector), T13 (workflow) |
| 3.3 Price 트리거 | T7, T10 |
| 3.4 Jeonse 트리거 | T7, T10 |
| 3.5 메시지 형식 | T8 |
| 3.6 위험 대비 | T12 (seed_alerts_sent) |
| 4. apt_seq 매칭 | T3, T4 |
| 5. Metabase | T22 |
| 6. 셋업 단계 | T0~T22 (각 단계가 셋업 단계의 한 단계에 매핑) |

빠짐 없음.

### 2. Placeholder scan

- 모든 step에 실제 코드/명령 포함됨
- "TBD"/"TODO"/"적절히" 등 모호 표현 없음
- T15의 `<USERNAME>`은 사용자 입력 필요한 placeholder — 문맥상 명확
- T20의 `gh secret set` 명령어가 실제로 prompt로 값 입력 받는 패턴 — 의도된 동작

### 3. Type consistency

- `make_record_id(record, kind)` — Task 5에서 정의, Task 10에서 동일 시그니처 호출
- `evaluate_price_threshold(records, rules) -> list[PriceCandidate]` — Task 7 정의, Task 10 사용
- `evaluate_jeonse_ratio(*, rules, median_sale_fn, median_jeonse_fn, today, ...)` — Task 7 정의, Task 10·12 사용
- `query_median_sale_price(client, *, apt_seq, size_label, days)` — Task 6 정의, Task 10·12에서 partial로 client 주입 후 호출
- DB 컬럼명 일관: `sale_records`의 `id`, `apt_seq`, `price_만원`, `size_label`, `deal_date`, `floor` 등이 SQL(T9)·parser(T5)·trigger(T7)·collector(T10)에서 모두 동일 사용
- `alert_rules.apt_seq` (text) vs `record["apt_seq"]` (str) — 일치
- `alerts_sent` 컬럼: `rule_id` (uuid), `dedup_key` (text), `alert_type` (text) — Task 9 SQL과 Task 6/7 코드 모두 일치
