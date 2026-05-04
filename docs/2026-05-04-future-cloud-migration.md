# 클라우드 마이그레이션 계획 (Phase 2)

작성일: 2026-05-04
상태: **계획 — 실제 마이그레이션은 launchd 운영 검증 후**

---

## 배경

현재(Phase 1)는 macOS launchd 기반 로컬 운영. 노트북 ON 시에만 동작.
laptop-independent 운영이 필요해지면 GitHub Actions + 클라우드 DB로 전환.

전환 시점에 데이터를 단지별로 누적하여 **대시보드 분석**까지 가능하도록 한다.

## 추천 스택

| 레이어 | 도구 | 비용 |
|---|---|---|
| 데이터 수집 | GitHub Actions (cron 09:00·18:00 KST) | 무료 (월 2000분 한도) |
| 데이터 저장 | Supabase (PostgreSQL 500MB) | 무료 |
| 대시보드 | Metabase Cloud 또는 Grafana Cloud | 무료 |
| 알림 | 텔레그램 (현재와 동일) | 무료 |
| 시크릿 | GitHub Actions secrets | 무료 |

전체 비용 0원, 신용카드 등록 불요.

## DB에 추가로 누적할 필드

현재(Phase 1)는 알림 발송에 필요한 최소 필드만 사용. Phase 2에서는 분석에 가치 있는 필드를 함께 누적한다.

### 매매 (`sale_records` 테이블)

| 필드 (API) | 우리 키 | 분석 가치 |
|---|---|---|
| `aptSeq` | `apt_seq` | **단지 고유 ID — 향후 단지 매칭은 이 값으로 (name_patterns 폐기)** |
| `aptNm` | `apt_name` | 표시용 |
| `umdNm` | `법정동` | 위치 |
| `umdCd` | `umd_cd` | 법정동 코드 (조인용) |
| `sggCd` | `sgg_cd` | 시군구 코드 |
| `excluUseAr` | `area` | 면적 |
| `dealAmount` | `price_만원` | 거래가 |
| `dealYear/Month/Day` | `deal_date` | 거래일 |
| `floor` | `floor` | 층 |
| `buildYear` | `build_year` | 건축연도 |
| **`dealingGbn`** | `dealing_type` | **중개거래 / 직거래 — 직거래 가격 비교 분석** |
| **`buyerGbn`** | `buyer_type` | **개인 / 법인 — 법인 매수 비중 추세** |
| **`slerGbn`** | `seller_type` | **매도자 유형** |
| **`cdealDay`** | `cancel_date` | **계약 해제일 — 신고가 후 취소 추적** |
| **`cdealType`** | `cancel_type` | **해제 유형** |
| `rgstDate` | `register_date` | 등기일 (미등기 거래 식별) |
| `landLeaseholdGbn` | `is_land_leasehold` | 토지임차 여부 |
| `roadNm` + `roadNmBonbun`/`Bubun` | `road_address` | 도로명 주소 (조합) |
| `jibun` | `jibun` | 지번 |

### 전월세 (`rent_records` 테이블)

| 필드 (API) | 우리 키 | 분석 가치 |
|---|---|---|
| `aptSeq` | `apt_seq` | 단지 고유 ID |
| `aptNm` | `apt_name` | 표시용 |
| `umdNm`/`sggCd` | `법정동`/`sgg_cd` | 위치 |
| `excluUseAr`/`floor`/`buildYear` | `area`/`floor`/`build_year` | 기본 정보 |
| `deposit` | `deposit_만원` | 보증금 |
| `monthlyRent` | `monthly_rent_만원` | 월세 |
| `dealYear/Month/Day` | `contract_date` | 계약일 |
| **`contractType`** | `contract_type` | **신규 / 갱신 — 신규만 추리면 진짜 시세** |
| **`contractTerm`** | `contract_term` | **계약기간 (예: 202504~202704) — 만기 모니터링** |
| **`preDeposit`** | `pre_deposit_만원` | **갱신 시 이전 보증금 — 인상률 계산** |
| **`preMonthlyRent`** | `pre_monthly_rent_만원` | **갱신 시 이전 월세** |
| **`useRRRight`** | `used_renewal_right` | **갱신요구권(5%룰) 사용 여부** |

### 공통 메타 필드

| 필드 | 의미 |
|---|---|
| `id` | sha1 (record_id) — Primary Key |
| `complex_key` | config.json의 단지 키 매핑 |
| `size_label` | '59' / '84' / null |
| `fetched_at` | API 조회 시각 (timestamptz) |

## 분석 시나리오 (대시보드)

수집한 필드로 가능한 분석.

1. **단지별 시세 추이** — 매매가 월별 중위/평균 라인 차트.
2. **갭 추이** — 매매 중위값 − 전세 중위값을 월별 누적.
3. **신규 vs 갱신 가격 차이** — `contractType`별 보증금 분포 비교.
4. **갱신 인상률 분포** — `(deposit − preDeposit) / preDeposit` 히스토그램.
5. **법인 매수 비중** — `buyerGbn = 법인` 거래 비중 월별 추세.
6. **직거래 가격 차이** — `dealingGbn = 직거래` 거래의 시세 대비 디스카운트.
7. **계약 해제율** — `cdealDay` not null 거래 비율.
8. **5%룰 사용 비중** — `useRRRight = 사용` 거래 비중.
9. **임계값 도달 매물 리스트** — 현재 알림 조건과 동일.

## 단지 매칭 개선

현재(Phase 1)는 `name_patterns` + `exclude_patterns` 문자열 매칭. Phase 2에서는 `aptSeq` 기반으로 전환.

**Before** (`config.json`):
```json
{
  "name_patterns": ["서울숲푸르지오"],
  "exclude_patterns": ["2차", "Ⅱ", "시티", "행당"]
}
```

**After**:
```json
{
  "apt_seq": "11200-12345"
}
```

운영 데이터로 7개 단지의 aptSeq를 한 번 확인해두면, 이후 매칭 로직은 `record["aptSeq"] == complex["apt_seq"]` 한 줄로 끝.

## 마이그레이션 단계 (실행 시)

1. **GitHub 가입 + private repo 생성** (사용자)
2. **로컬 코드 push**
3. **Supabase 가입 + 프로젝트 생성** (사용자)
4. **DB 스키마 작성** (`sale_records`, `rent_records`, `alerts_sent` 테이블)
5. **monitor.py에 DB 어댑터 추가** — `state.json` 대신 `INSERT ... ON CONFLICT DO NOTHING`
6. **확장 필드 파싱 추가** — 위 표의 모든 필드를 `_parse_sale_item`/`_parse_rent_item`에 추가
7. **단지 매칭 `aptSeq` 기반으로 전환** — 운영 데이터에서 단지별 aptSeq 추출 후 config 업데이트
8. **GitHub Secrets에 키 등록** (`MOLIT_SERVICE_KEY`, `TELEGRAM_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`)
9. **`.github/workflows/monitor.yml` 작성** — cron `0 0,9 * * *` UTC
10. **백필** — 직전 6개월 데이터 1회성 push
11. **Metabase Cloud 가입 → Supabase 연결 → 대시보드 구성**
12. **launchd 비활성화** — `launchctl unload ~/Library/LaunchAgents/com.joel.realestate-monitor.plist`

## 트리거 시점

다음 중 하나 발생 시 마이그레이션 검토:

- 노트북 OFF로 인한 알림 누락이 누적
- "지난 1년 추이를 보고 싶다" 같은 분석 욕구 발생
- 단지 추가/삭제 시 매칭 패턴 보정이 잦아져 `aptSeq` 기반으로 단순화하고 싶을 때
- 갭·시세 추이를 그래프로 보고 싶을 때
