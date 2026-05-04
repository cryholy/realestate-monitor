# 부동산 실거래·전월세 클라우드 모니터링 시스템 설계

작성일: 2026-05-04
대상: `/Users/joel/Claude/labs/realestate_monitor/` (전면 재작성)

목적이 단순 알림에서 **9개 구 데이터 누적 + 분석 대시보드 + 갭 알림**으로 확장되었다. 기존 로컬 코드(`monitor.py`, `state.json`, `config.json`, `com.joel.realestate-monitor.plist`)는 **삭제하고 신규 작성**한다. 기존 docs (`2026-05-04-design.md`, `2026-05-04-implementation-plan.md`, `2026-05-04-future-cloud-migration.md`)는 역사 기록으로 유지.

---

## 0. 요약 (한 페이지)

| 항목 | 결정 |
|---|---|
| 모니터링 구 | **9개 구**: 성동·광진·마포·서초·강남·송파·용산·동작·강동 |
| 데이터 소스 | 국토부 매매 + 전월세 API (분석 가치 있는 모든 필드 누적) |
| 백필 | 1년 (1회성 수동 실행) + 일일 누적 |
| 백필 알림 | **없음** — `alerts_sent`에 dedup 키 미리 채워 폭격 방지 |
| 알림 룰 관리 | **Supabase `alert_rules` 테이블** (Studio UI에서 편집) |
| 알림 트리거 | (1) 가격 임계값 도달, (2) 전세가율 임계값 도달 — **edge** 한 번만 |
| 사이클 분석 | 대시보드 (Metabase) — 알림 X, 시각화 only |
| 인프라 | GitHub Actions (private repo) + Supabase + Metabase + Telegram |
| 비용 | 0원 (모든 무료 한도 내) |
| 단지 식별 | **`apt_seq`** (단지 고유 ID 기반 정확 매칭) |

---

## 1. 아키텍처 & 인프라

### 1.1 시스템 구성

```
┌─────────────────────────────────────────────────┐
│ GitHub Actions  (private repo)                  │
│ cron: 0 0,9 * * *  (UTC) = 09:00 / 18:00 KST    │
└──────────────┬──────────────────────────────────┘
               │ runner spawn (Ubuntu)
               ▼
   ┌──────────────────────────────────┐
   │ python3.11 collector.py          │
   │  ├─ 국토부 API (9개 구 × 매매·전세) │
   │  ├─ XML 파싱 + 분석 필드 전체 추출 │
   │  ├─ Supabase UPSERT               │
   │  ├─ alert_rules 조회              │
   │  ├─ edge 트리거 판정 (임계값 도달) │
   │  └─ 텔레그램 알림 + dedup 기록    │
   └──┬───────────────────────────┬───┘
      │                           │
      ▼                           ▼
┌──────────────┐           ┌──────────────┐
│  Supabase    │           │   Telegram   │
│  PostgreSQL  │           │     Bot      │
└──────┬───────┘           └──────────────┘
       │ SQL (read-only)
       ▼
┌──────────────┐
│  Metabase    │
│  Cloud       │ ← 사이클 추세, 갭 추이, 거래량 등 분석
└──────────────┘
```

### 1.2 컴포넌트 책임

| 컴포넌트 | 책임 | 비용 |
|---|---|---|
| GitHub Actions | cron 트리거, Python 실행, secrets 관리 | 무료 (월 2,000분, 우리 사용 ~30분) |
| GitHub repo (private) | 코드, sql 마이그레이션, 워크플로 | 무료 |
| Supabase | Postgres DB, Studio UI(alert_rules 편집), REST API | 무료 (500 MB, 5 GB 송수신) |
| Metabase Cloud | 대시보드, SQL 쿼리, 차트 | 무료 |
| Telegram Bot | 알림 전달 | 무료 |

### 1.3 디렉토리 구조

신규 시스템 시작 시 기존 코드/설정 파일은 일괄 삭제하고 아래 구조로 새로 작성한다.

**삭제 대상** (구현 첫 단계에서 제거):
- `monitor.py`, `state.json`, `config.json`
- `com.joel.realestate-monitor.plist` (launchd 해제 후)
- `tests/` 하위 기존 파일 (fixture 포함, 신규 모듈에 맞게 재작성)
- `.env.example`, `requirements.txt`도 신규 모듈에 맞춰 재작성

**유지**:
- `docs/2026-05-04-design.md`, `2026-05-04-implementation-plan.md`, `2026-05-04-future-cloud-migration.md` — 역사 기록
- `docs/2026-05-04-system-design.md` — 본 설계 문서

**신규 구조**:
```
labs/realestate_monitor/
├── collector.py                # 메인 엔트리 (cron 호출)
├── lib/
│   ├── __init__.py
│   ├── api.py                  # 국토부 API + 전체 필드 파싱
│   ├── matcher.py              # 단지 매칭 (apt_seq 기반)
│   ├── notifier.py             # 텔레그램 + 메시지 포맷
│   ├── db.py                   # Supabase client (UPSERT/쿼리)
│   └── triggers.py             # edge 트리거 판정 로직
├── sql/
│   ├── 001_initial_schema.sql  # 4개 테이블 + 인덱스
│   ├── 002_views.sql           # view + MV
│   └── seed_districts.sql      # 9개 구 LAWD_CD seed
├── scripts/
│   ├── backfill.py             # 1년 백필 1회성
│   └── seed_alerts_sent.py     # 백필 후 dedup 키 미리 채우기
├── .github/workflows/
│   └── monitor.yml             # cron + secrets
├── tests/
│   ├── test_api.py             # XML 파싱 + 전체 필드
│   ├── test_matcher.py
│   ├── test_triggers.py
│   ├── test_db.py              # mock Supabase client
│   ├── test_notifier.py
│   └── fixtures/
│       ├── sale_response.xml
│       ├── rent_response.xml
│       └── error_response.xml
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── docs/
    ├── 2026-05-04-design.md                  (역사)
    ├── 2026-05-04-implementation-plan.md     (역사)
    ├── 2026-05-04-future-cloud-migration.md  (역사)
    └── 2026-05-04-system-design.md           (← 본 설계, 활성)
```

### 1.4 보안·시크릿

| 시크릿 | 저장 위치 |
|---|---|
| `MOLIT_SERVICE_KEY` | GitHub Secrets |
| `TELEGRAM_BOT_TOKEN` | GitHub Secrets |
| `SUPABASE_URL` | GitHub Secrets |
| `SUPABASE_SERVICE_ROLE_KEY` | GitHub Secrets (서버 전용 키) |
| `TELEGRAM_CHAT_ID` | 환경변수 또는 `alert_rules.chat_id` |

GitHub repo는 **private**.

---

## 2. 데이터 모델

### 2.1 테이블 구성

| 테이블 / view | 목적 | 누가 쓰는가 |
|---|---|---|
| `sale_records` | 매매 거래 raw 데이터 누적 | collector(write), Metabase(read), trigger(read) |
| `rent_records` | 전월세 거래 raw 데이터 누적 | 동일 |
| `alert_rules` | 사용자 관심 매물 + 임계값 (Studio 편집) | 사용자(write), collector(read) |
| `alerts_sent` | dedup 발송 이력 | collector(read+write) |
| `v_complexes` (view) | apt_seq 찾기 helper | 사용자(read) |
| `v_alert_rules_check` (view) | alert_rules 검증 도구 | 사용자(read) |
| `mv_monthly_sale_stats` (MV) | 대시보드 성능 (월별 집계) | Metabase(read) |
| `mv_monthly_rent_stats` (MV) | 동일 | Metabase(read) |

### 2.2 `sale_records` (매매)

```sql
CREATE TABLE sale_records (
  id              text PRIMARY KEY,           -- sha1(apt_seq+date+floor+price+area)

  -- 단지·위치
  apt_seq         text NOT NULL,
  apt_name        text,
  법정동          text,
  umd_cd          text,
  sgg_cd          text NOT NULL,
  jibun           text,
  road_address    text,

  -- 거래 본문
  deal_date       date NOT NULL,
  price_만원      integer NOT NULL,
  area            numeric(6,2) NOT NULL,
  size_label      text,                       -- '59' / '84' / 'mid' / 'other'
  floor           integer,
  build_year      integer,

  -- 거래 유형 (분석용)
  dealing_type    text,                       -- 중개거래/직거래
  buyer_type      text,                       -- 개인/법인/공공기관
  seller_type     text,
  agent_sgg_name  text,
  is_land_lease   boolean,

  -- 취소·등기
  cancel_date     date,
  cancel_type     text,
  register_date   date,

  fetched_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_sale_apt_seq_date ON sale_records (apt_seq, deal_date DESC);
CREATE INDEX idx_sale_sgg_date     ON sale_records (sgg_cd, deal_date DESC);
CREATE INDEX idx_sale_size_price   ON sale_records (size_label, price_만원);
```

### 2.3 `rent_records` (전월세)

```sql
CREATE TABLE rent_records (
  id                    text PRIMARY KEY,
  
  apt_seq               text NOT NULL,
  apt_name              text,
  법정동                text,
  sgg_cd                text NOT NULL,

  contract_date         date NOT NULL,
  deposit_만원          integer NOT NULL,
  monthly_rent_만원     integer NOT NULL,    -- 0이면 순수 전세
  area                  numeric(6,2) NOT NULL,
  size_label            text,
  floor                 integer,
  build_year            integer,

  -- 신규/갱신 분석
  contract_type         text,
  contract_term         text,
  pre_deposit_만원      integer,
  pre_monthly_rent_만원 integer,
  used_renewal_right    boolean,

  fetched_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_rent_apt_seq_date ON rent_records (apt_seq, contract_date DESC);
CREATE INDEX idx_rent_sgg_date     ON rent_records (sgg_cd, contract_date DESC);
```

### 2.4 `alert_rules` (사용자 관심 매물)

```sql
CREATE TABLE alert_rules (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  apt_seq           text NOT NULL,
  display_name      text NOT NULL,
  size_label        text NOT NULL,            -- '59' / '84' / 'mid' / 'any'
  max_price_만원    integer,                  -- null = 가격 알림 비활성
  min_jeonse_ratio  numeric(4,3),             -- 0.65 = 65%, null = 갭 알림 비활성
  enabled           boolean DEFAULT true,
  notes             text,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now(),
  UNIQUE (apt_seq, size_label)
);

CREATE INDEX idx_alert_rules_enabled ON alert_rules (enabled) WHERE enabled = true;
```

**size_label 정의**:
| 라벨 | 면적 범위 | 의미 |
|---|---|---|
| `59` | 58.0 ~ 60.5㎡ | 25평형 |
| `84` | 83.0 ~ 85.5㎡ | 34평형 |
| `mid` | 60.5 ~ 83.0㎡ | 사이 평형대 |
| `any` | (룰 전용 — 모든 record와 매칭) | record에는 없는 값. 룰의 size_label='any'면 그 단지의 모든 평형 record가 알림 대상. |

### 2.5 `alerts_sent` (dedup)

```sql
CREATE TABLE alerts_sent (
  rule_id     uuid NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
  dedup_key   text NOT NULL,
  alert_type  text NOT NULL,                  -- 'price_threshold' / 'jeonse_ratio'
  sent_at     timestamptz DEFAULT now(),
  PRIMARY KEY (rule_id, dedup_key)
);
```

**dedup_key 규칙**:
- price → `'sale:' || sale_records.id`
- jeonse → `'jeonse:' || YYYY-MM` (월 단위 dedup, 한 달에 한 번만)

### 2.6 view + MV

```sql
-- alert_rules 작성 시 단지 검색 helper
CREATE VIEW v_complexes AS
SELECT DISTINCT
  apt_seq, apt_name, sgg_cd, 법정동, build_year,
  COUNT(*) OVER (PARTITION BY apt_seq) AS sale_records_count,
  MIN(deal_date) OVER (PARTITION BY apt_seq) AS earliest_deal,
  MAX(deal_date) OVER (PARTITION BY apt_seq) AS latest_deal
FROM sale_records;

-- 룰 검증
CREATE VIEW v_alert_rules_check AS
SELECT
  ar.*,
  vc.apt_name AS actual_apt_name,
  vc.sgg_cd AS actual_sgg_cd,
  CASE
    WHEN vc.apt_seq IS NULL THEN '⚠️ apt_seq 미존재'
    WHEN ar.display_name != vc.apt_name THEN '⚠️ display_name 불일치'
    ELSE '✅ OK'
  END AS validation
FROM alert_rules ar
LEFT JOIN v_complexes vc ON ar.apt_seq = vc.apt_seq;

-- 대시보드용 월별 집계 (성능)
CREATE MATERIALIZED VIEW mv_monthly_sale_stats AS
SELECT
  apt_seq, apt_name, sgg_cd, size_label,
  DATE_TRUNC('month', deal_date) AS month,
  COUNT(*) AS deals,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS median_price,
  MIN(price_만원) AS min_price,
  MAX(price_만원) AS max_price
FROM sale_records
GROUP BY apt_seq, apt_name, sgg_cd, size_label, DATE_TRUNC('month', deal_date);

CREATE INDEX idx_mv_monthly_sale ON mv_monthly_sale_stats (apt_seq, size_label, month);

-- rent도 동일
CREATE MATERIALIZED VIEW mv_monthly_rent_stats AS
SELECT
  apt_seq, apt_name, sgg_cd, size_label,
  DATE_TRUNC('month', contract_date) AS month,
  COUNT(*) AS contracts,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_만원) FILTER (WHERE monthly_rent_만원 = 0) AS median_jeonse,
  MIN(deposit_만원) FILTER (WHERE monthly_rent_만원 = 0) AS min_jeonse,
  MAX(deposit_만원) FILTER (WHERE monthly_rent_만원 = 0) AS max_jeonse
FROM rent_records
GROUP BY apt_seq, apt_name, sgg_cd, size_label, DATE_TRUNC('month', contract_date);

CREATE INDEX idx_mv_monthly_rent ON mv_monthly_rent_stats (apt_seq, size_label, month);
```

### 2.7 데이터량 추산

| 테이블 | 1년 row | 평균 row | 1년 누적 |
|---|---|---|---|
| sale_records | ~24K | ~1.5KB | ~36MB |
| rent_records | ~120K | ~1.5KB | ~180MB |
| alert_rules | ~50 | ~500B | < 1MB |
| alerts_sent | ~수백 | ~200B | < 1MB |
| MV 2개 | ~10K | ~300B | ~3MB |
| **합계** | | | **~220MB** (한도 44%) |

---

## 3. 데이터 흐름

### 3.1 백필 (1회성)

```
[python3.11 scripts/backfill.py --months 12]

for ymd in [202504..202405]:
  for sgg_cd in [11200, 11215, 11440, 11650, 11680, 11710, 11170, 11590, 11740]:
    fetch_sales(sgg_cd, ymd)  → UPSERT sale_records
    fetch_rents(sgg_cd, ymd)  → UPSERT rent_records
    sleep(0.5)

= 12 × 9 × 2 = 216 API 호출, ~5분
= ~144K rows = ~220MB
```

이후 사용자가 `alert_rules` INSERT → `seed_alerts_sent.py` 실행 → GitHub Actions enabled.

### 3.2 일일 운영 (cron)

```
[GitHub Actions cron: 0 0,9 * * * UTC = 09:00 / 18:00 KST]
        ↓
runner spawn → git checkout → pip install
        ↓
collector.py
  ├─ STEP 1: Fetch 최근 2개월 (신고 시차 30일 고려)
  │   = 9개 구 × 매매·전세 × 2개월 = 36 API 호출
  ├─ STEP 2: UPSERT
  │   INSERT ... ON CONFLICT (id) DO NOTHING
  │   → 신규 INSERT된 row만 다음 단계 후보
  ├─ STEP 3-1: Price threshold 트리거 평가 (3.3)
  ├─ STEP 3-2: Jeonse ratio 트리거 평가 (3.4)
  └─ STEP 4: REFRESH MATERIALIZED VIEW CONCURRENTLY
```

### 3.3 Price threshold 트리거

```
for r in 이번 실행에서 신규 INSERT된 sale_records:
    for rule in alert_rules WHERE enabled
                            AND apt_seq = r.apt_seq
                            AND size_label IN (r.size_label, 'any'):
        if rule.max_price_만원 IS NULL: continue
        if r.price_만원 >= rule.max_price_만원: continue
        
        dedup_key = 'sale:' || r.id
        if EXISTS in alerts_sent (rule_id, dedup_key): continue
        
        send_telegram_price(rule, r, gap_info)
        INSERT alerts_sent (rule_id, dedup_key, 'price_threshold')
```

### 3.4 Jeonse ratio 트리거

```
month_key = today.strftime('%Y-%m')

for rule in alert_rules WHERE enabled AND min_jeonse_ratio IS NOT NULL:
    median_sale = SELECT PERCENTILE_CONT(0.5) ... FROM sale_records
                  WHERE apt_seq = rule.apt_seq AND size_label = rule.size_label
                    AND deal_date >= today - 90;
    median_jeonse = SELECT PERCENTILE_CONT(0.5) ... FROM rent_records
                    WHERE apt_seq = rule.apt_seq AND size_label = rule.size_label
                      AND monthly_rent_만원 = 0
                      AND contract_date >= today - 90;
    
    if 매매 표본 < 5건 OR 전세 표본 < 5건: continue
    
    ratio = median_jeonse / median_sale
    if ratio < rule.min_jeonse_ratio: continue
    
    dedup_key = 'jeonse:' || month_key
    if EXISTS in alerts_sent (rule_id, dedup_key): continue
    
    send_telegram_jeonse(rule, ratio, median_sale, median_jeonse)
    INSERT alerts_sent (rule_id, dedup_key, 'jeonse_ratio')
```

### 3.5 메시지 형식

#### Price threshold

```
🏠 매매가 임계값 도달 (헬리오시티 84㎡)

💰 매매가  19억 8,000 (15층, 2026-05-04 신고)
📊 직전 90일 전세 시세 (84㎡, 12건)
   • 중위값  12억 5,000
   • 최저~최고  11억 5,000 ~ 13억 8,000
🔻 갭 (매매 − 전세 중위값)  약 7억 3,000
📈 전세가율  63.1%
```

#### Jeonse ratio

```
📈 전세가율 임계값 도달 (헬리오시티 84㎡, 65% ↑)

📊 직전 90일 중위값
   • 매매  19억 5,000
   • 전세  12억 8,000
🔻 갭  약 6억 7,000
📈 전세가율  65.6%  (임계값 65.0%)

표본: 매매 8건 / 전세 14건
2026-05 신호 — 이 달은 추가 알림 없음
```

### 3.6 백필→운영 위험 대비

| 위험 | 대비 |
|---|---|
| 백필 후 alerts_sent 누락 → 폭격 | seed_alerts_sent.py 자동 실행 가이드 |
| API 일시 장애로 백필 부분 실패 | INSERT ON CONFLICT DO NOTHING이라 재실행 안전 |
| 사용자가 alert_rules 작성 전 운영 시작 | 무해. 룰 추가 후 다음 cron부터 동작 |
| jeonse 알림 발송 후 임계값 변경 | 변경 후 그 달은 이미 발송됨. 즉시 재발송 원하면 alerts_sent에서 해당 row 수동 삭제 |

---

## 4. 단지 식별 (apt_seq 기반)

### 4.1 설계 원칙

국토부 API 응답에 포함된 `aptSeq` (단지 고유 ID, 예: `11710-2412`)를 단지 식별의 PK로 사용한다.

- **장점**: 표기 흔들림(공백·괄호·차수 표기 등)에 영향 없음. PK 비교 한 줄로 매칭 끝.
- **사용자 작업**: 단지 추가 시 v_complexes view에서 apt_seq를 검색해 alert_rules에 INSERT.
- **신축 단지**: 첫 거래 발생 후 v_complexes에 자동 등장. 그 후 alert_rules 추가.
- **재명명·분할**: 매우 드물지만 발생 시 alert_rules에 row 2개 등록(여러 apt_seq 모두 enabled).

### 4.2 사용자 단지 추가 절차

#### 1단계: 단지 검색 (Supabase Studio SQL Editor)

```sql
SELECT * FROM v_complexes
WHERE apt_name LIKE '%헬리오시티%'
  AND sgg_cd = '11710'
ORDER BY sale_records_count DESC;
```

#### 2단계: alert_rules에 INSERT

| 컬럼 | 입력 |
|---|---|
| apt_seq | `11710-2412` |
| display_name | `헬리오시티` |
| size_label | `84` |
| max_price_만원 | `200000` |
| min_jeonse_ratio | `0.65` |
| enabled | `true` |

#### 3단계: 검증 (선택)

```sql
SELECT * FROM v_alert_rules_check WHERE display_name = '헬리오시티';
-- validation 컬럼이 ✅ OK인지 확인
```

### 4.3 size_label 계산 (collector.py)

```python
SIZE_LABELS = [
    ("59",  58.0, 60.5),
    ("mid", 60.5, 83.0),
    ("84",  83.0, 85.5),
]

def compute_size_label(area: float) -> str:
    for label, lo, hi in SIZE_LABELS:
        if lo <= area <= hi:
            return label
    return "other"
```

INSERT 시점에 미리 계산.

### 4.4 매칭 코드

```python
def match_alert_rules(record: dict, rules: list[dict]) -> list[dict]:
    return [
        r for r in rules
        if r["apt_seq"] == record["apt_seq"]
        and r["size_label"] in (record["size_label"], "any")
    ]
```

---

## 5. 대시보드 (Metabase)

### 5.1 대시보드 구성

| 대시보드 | 목적 | 핵심 차트 |
|---|---|---|
| 1. 관심 매물 모니터 | 매일 보는 화면 | 시세·갭 추이, 사이클 시그널 |
| 2. 시장 개요 | 주 1회 시장 흐름 | 9개 구 거래량·시세 |
| 3. 상세 분석 | 가끔 드릴다운 | 직거래·갱신·법인 매수 등 |

### 5.2 차트 1-1: 관심 매물 현황 (테이블)

```sql
SELECT
  ar.display_name AS 단지,
  ar.size_label || '㎡' AS 평형,
  ar.max_price_만원 / 10000.0 AS 매매_임계_억,
  ar.min_jeonse_ratio AS 전세가율_임계,
  s.median_price_now / 10000.0 AS 현재_매매_중위_억,
  r.median_deposit_now / 10000.0 AS 현재_전세_중위_억,
  ROUND(r.median_deposit_now::numeric / s.median_price_now, 3) AS 현재_전세가율,
  s.median_price_now - r.median_deposit_now AS 현재_갭_만원,
  CASE
    WHEN s.median_price_now < ar.max_price_만원 THEN '🔥 임계값 미만'
    WHEN r.median_deposit_now::numeric / s.median_price_now >= ar.min_jeonse_ratio THEN '🔥 갭 도달'
    ELSE '⏸ 대기'
  END AS 상태
FROM alert_rules ar
LEFT JOIN LATERAL (
  SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS median_price_now
  FROM sale_records
  WHERE apt_seq = ar.apt_seq AND size_label = ar.size_label
    AND deal_date >= NOW() - INTERVAL '90 days'
) s ON TRUE
LEFT JOIN LATERAL (
  SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_만원) AS median_deposit_now
  FROM rent_records
  WHERE apt_seq = ar.apt_seq AND size_label = ar.size_label
    AND monthly_rent_만원 = 0
    AND contract_date >= NOW() - INTERVAL '90 days'
) r ON TRUE
WHERE ar.enabled
ORDER BY 상태, 단지;
```

### 5.3 차트 1-2: 매매 시세 + 사이클 시그널 (3M MA vs 12M MA)

```sql
WITH monthly AS (
  SELECT
    apt_seq, apt_name, size_label,
    DATE_TRUNC('month', deal_date) AS month,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS median_price
  FROM sale_records
  WHERE apt_seq IN (SELECT apt_seq FROM alert_rules WHERE enabled)
    AND size_label IN ('59', '84', 'mid')
  GROUP BY apt_seq, apt_name, size_label, DATE_TRUNC('month', deal_date)
),
with_ma AS (
  SELECT *,
    AVG(median_price) OVER (
      PARTITION BY apt_seq, size_label ORDER BY month
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS ma_3m,
    AVG(median_price) OVER (
      PARTITION BY apt_seq, size_label ORDER BY month
      ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
    ) AS ma_12m
  FROM monthly
)
SELECT
  month,
  apt_name || ' ' || size_label || '㎡' AS 매물,
  median_price / 10000.0 AS 월별_중위_억,
  ma_3m / 10000.0 AS MA3M_억,
  ma_12m / 10000.0 AS MA12M_억,
  CASE
    WHEN ma_3m < ma_12m THEN '🔻 하락 사이클'
    WHEN ma_3m > ma_12m THEN '🔺 상승 사이클'
    ELSE '─ 횡보'
  END AS 사이클_상태
FROM with_ma
WHERE month >= NOW() - INTERVAL '12 months'
ORDER BY 매물, month;
```

→ 라인 차트로 시각화. 3M이 12M을 아래로 교차하면 = 하락 사이클 진입.

### 5.4 차트 1-3: 갭(전세가율) 추이

```sql
WITH monthly_sale AS (
  SELECT apt_seq, size_label,
         DATE_TRUNC('month', deal_date) AS month,
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS median_sale
  FROM sale_records
  WHERE apt_seq IN (SELECT apt_seq FROM alert_rules WHERE enabled)
  GROUP BY apt_seq, size_label, DATE_TRUNC('month', deal_date)
),
monthly_rent AS (
  SELECT apt_seq, size_label,
         DATE_TRUNC('month', contract_date) AS month,
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_만원) AS median_jeonse
  FROM rent_records
  WHERE apt_seq IN (SELECT apt_seq FROM alert_rules WHERE enabled)
    AND monthly_rent_만원 = 0
  GROUP BY apt_seq, size_label, DATE_TRUNC('month', contract_date)
)
SELECT
  s.month,
  s.apt_seq, s.size_label,
  s.median_sale / 10000.0 AS 매매_중위_억,
  r.median_jeonse / 10000.0 AS 전세_중위_억,
  (s.median_sale - r.median_jeonse) / 10000.0 AS 갭_억,
  ROUND(r.median_jeonse::numeric / s.median_sale, 3) AS 전세가율
FROM monthly_sale s
LEFT JOIN monthly_rent r USING (apt_seq, size_label, month)
WHERE s.month >= NOW() - INTERVAL '12 months'
ORDER BY apt_seq, size_label, month;
```

→ 듀얼축 차트. 전세가율 라인에 임계값(예: 65%) 가로선 — 알림 시점 시각적 대조.

### 5.5 대시보드 2/3 차트

생략. SQL은 단순 GROUP BY 또는 PERCENTILE/COUNT. 운영 후 분석 욕구 발생 시 추가.

### 5.6 알림-대시보드 일관성

같은 `min_jeonse_ratio` 임계값이 알림(collector)과 대시보드(차트 1-3)에 모두 사용 → "왜 알림 왔지?"가 차트에서 즉시 확인.

---

## 6. 셋업 단계 + 운영

### 6.1 셋업 순서 (14단계)

| # | 단계 | 누가 | 소요 |
|---|---|---|---|
| 0 | 기존 launchd 해제 + 기존 코드 삭제 (`monitor.py`, `state.json`, `config.json`, `tests/*` legacy fixture, `.plist`) | 자동 | 2분 |
| 1 | GitHub 가입 + 2FA + private repo `realestate-monitor` 생성 | 사용자 | 5분 |
| 2 | GitHub PAT 발급 (repo + workflow scope) → `~/.zshrc`에 `GITHUB_TOKEN` 등록 | 사용자 | 3분 |
| 3 | Supabase 가입 + 프로젝트 생성 + DB 비밀번호 저장 | 사용자 | 5분 |
| 4 | Supabase Service Role Key + URL 확인 (Settings → API) | 사용자 | 1분 |
| 5 | 신규 코드 작성 (collector.py + lib/ + sql/ + scripts/ + workflows + tests) | 자동 (구현 단계) | 2~3시간 |
| 6 | 코드 GitHub repo로 push | 자동 | 2분 |
| 7 | Supabase에 SQL 마이그레이션 적용 (Supabase MCP) | 자동 | 1분 |
| 8 | `python3.11 scripts/backfill.py --months 12` 로컬 실행 | 자동 | 5분 |
| 9 | Supabase Studio에서 `alert_rules` INSERT (관심 매물) | 사용자 | 10분 |
| 10 | `python3.11 scripts/seed_alerts_sent.py` 실행 (백필 거래에 dedup 키 미리 채움 — 폭격 방지) | 자동 | 1분 |
| 11 | GitHub Secrets 4개 등록 (`MOLIT_SERVICE_KEY`, `TELEGRAM_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) | 사용자 또는 `gh secret set` | 3분 |
| 12 | `.github/workflows/monitor.yml` push → 수동 실행(`workflow_dispatch`) → 로그·DB 검증 | 자동 | 5분 |
| 13 | Metabase Cloud 가입 → Supabase 연결 → 대시보드 3개 구성 | 사용자 + 자동(쿼리 제공) | 30분 |

### 6.2 첫 가동 검증

병행 운영 없이 **직접 전환**한다 (기존 launchd는 6.1 단계 0에서 이미 해제).

- 첫 cron 실행(다음 09:00 또는 18:00 KST) 또는 수동 트리거(`workflow_dispatch`) 후 다음 항목 즉시 점검:
  1. **로그**: GitHub Actions 워크플로 로그에 에러 없음, "수집 N건 / 매칭 K건 / 발송 M건" 요약 정상.
  2. **DB**: `SELECT COUNT(*), MAX(fetched_at) FROM sale_records;` — fetched_at가 방금 시각, count가 백필+α.
  3. **알림**: 백필 dedup이 정상 작동했다면 첫 실행에서 알림 0~극소량. 폭격 발생 시 즉시 워크플로 disable.
  4. **대시보드**: 차트 1-1 (관심 매물 현황)이 정상 렌더링.
- 첫 24시간 동안 매 cron 실행마다 위 4개 점검. 이상 없으면 정착.

### 6.3 비용·한도 모니터링

| 자원 | 한도 | 사용 추산 |
|---|---|---|
| GitHub Actions | 월 2,000분 | ~30분 |
| Supabase DB | 500 MB | ~250 MB (1년 후) |
| Supabase 송수신 | 월 5 GB | ~50 MB |
| Metabase Cloud | 무료 한도 | 대시보드 3개 |
| Telegram | 무제한 | ~수십 메시지/월 |

12개월 후 한도 근접 시:
- A. Supabase Pro 플랜 ($25/월) → 8 GB
- B. 18개월 이전 raw 삭제 (MV 유지)
- C. 모니터링 구 축소

### 6.4 운영 시작 후 1개월

```
Day 1     : 첫 cron 검증 (6.2의 4개 점검) + 폭격 모니터링
Week 1    : 알림 누락·오발송·중복 점검 (alerts_sent vs 텔레그램 메시지)
Week 2-4  : 대시보드 사용성 검증, 추가 룰 등록 시도
1개월 후  : 한도 점검 + 분석 인사이트 도출 시작
```

### 6.5 향후 확장 (이번 범위 외)

- 추가 구 확장 (노원·강서 등)
- 사이클 알림 정교화 (3M/12M MA cross 발생 시 일회성 알림)
- 신축 단지 자동 감지 (신규 apt_seq 등장 알림)
- 갱신 인상률 알림 (`pre_deposit_만원` 활용)
- 호가 데이터 통합 (현재는 합법적 API 부재로 보류)
