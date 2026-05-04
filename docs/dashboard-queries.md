# Supabase Studio Reports — 대시보드 쿼리 모음

대시보드 차트 SQL 6개. Supabase Studio → Reports → New Report에서 차례로 복붙.

## 셋업 절차

1. https://supabase.com/dashboard/project/flsbxpjywjuhylfwnrby 접속
2. 좌측 메뉴 → **Reports** → **+ New report** → 이름 `realestate-monitor`
3. **+ Add chart** → 아래 SQL을 차트마다 복붙
4. 차트 타입 선택 (각 SQL 위 "차트 타입" 참고)

---

## 차트 1. 관심 매물 현황 (테이블)

**차트 타입**: Table
**용도**: 매일 보는 화면 — 어느 매물이 임계값 근처인지 한눈에

```sql
SELECT
  ar.display_name AS 단지,
  ar.size_label || '㎡' AS 평형,
  (ar.max_price_만원 / 10000.0)::numeric(10,1) AS 매매_임계_억,
  ar.min_jeonse_ratio AS 전세가율_임계,
  ROUND((s.median_price_now / 10000.0)::numeric, 1) AS 현재_매매_중위_억,
  ROUND((r.median_deposit_now / 10000.0)::numeric, 1) AS 현재_전세_중위_억,
  CASE WHEN s.median_price_now > 0 AND r.median_deposit_now IS NOT NULL
       THEN ROUND((r.median_deposit_now::numeric / s.median_price_now::numeric), 3)
       ELSE NULL END AS 현재_전세가율,
  CASE WHEN s.median_price_now IS NOT NULL AND r.median_deposit_now IS NOT NULL
       THEN ROUND(((s.median_price_now - r.median_deposit_now) / 10000.0)::numeric, 1)
       ELSE NULL END AS 현재_갭_억,
  CASE
    WHEN s.median_price_now IS NULL THEN '— 매매 데이터 부족'
    WHEN s.median_price_now < ar.max_price_만원 THEN '🔥 매매 임계값 미만'
    WHEN r.median_deposit_now IS NOT NULL
         AND r.median_deposit_now::numeric / s.median_price_now::numeric >= ar.min_jeonse_ratio THEN '🔥 전세가율 도달'
    ELSE '⏸ 대기'
  END AS 상태
FROM alert_rules ar
LEFT JOIN LATERAL (
  SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS median_price_now
  FROM sale_records
  WHERE apt_seq = ar.apt_seq
    AND (ar.size_label = 'any' OR size_label = ar.size_label)
    AND deal_date >= CURRENT_DATE - 90
) s ON TRUE
LEFT JOIN LATERAL (
  SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_만원) AS median_deposit_now
  FROM rent_records
  WHERE apt_seq = ar.apt_seq
    AND (ar.size_label = 'any' OR size_label = ar.size_label)
    AND monthly_rent_만원 = 0
    AND contract_date >= CURRENT_DATE - 90
) r ON TRUE
WHERE ar.enabled
ORDER BY 상태 DESC, 단지, 평형;
```

---

## 차트 2. 매매 시세 + 사이클 시그널 (3M MA vs 12M MA)

**차트 타입**: Line (x축: month, y축: 월별_중위_억 / MA3M_억 / MA12M_억)
**용도**: 사이클 전환 감지 — 3M이 12M을 아래로 교차하면 하락 사이클

```sql
WITH monthly AS (
  SELECT
    apt_seq, apt_name, size_label,
    DATE_TRUNC('month', deal_date)::date AS month,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS median_price
  FROM sale_records
  WHERE apt_seq IN (SELECT DISTINCT apt_seq FROM alert_rules WHERE enabled)
    AND size_label IN ('59', '84', 'mid')
  GROUP BY apt_seq, apt_name, size_label, DATE_TRUNC('month', deal_date)
),
with_ma AS (
  SELECT *,
    AVG(median_price) OVER (PARTITION BY apt_seq, size_label ORDER BY month
                            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS ma_3m,
    AVG(median_price) OVER (PARTITION BY apt_seq, size_label ORDER BY month
                            ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS ma_12m
  FROM monthly
)
SELECT
  month,
  apt_name || ' ' || size_label || '㎡' AS 매물,
  ROUND((median_price / 10000.0)::numeric, 1) AS 월별_중위_억,
  ROUND((ma_3m / 10000.0)::numeric, 1) AS MA3M_억,
  ROUND((ma_12m / 10000.0)::numeric, 1) AS MA12M_억
FROM with_ma
WHERE month >= CURRENT_DATE - INTERVAL '12 months'
ORDER BY 매물, month;
```

> **차트 설정 팁**: 매물별 series 분리되도록 group by `매물` 설정. 라인 색상은 매물별 자동 부여.

---

## 차트 3. 갭 + 전세가율 추이

**차트 타입**: Line (좌축: 갭_억, 우축: 전세가율) — Supabase Studio가 dual axis 미지원 시 두 차트로 분리
**용도**: 전세가율 임계값(예: 0.65) 가로선 비교

```sql
WITH monthly_sale AS (
  SELECT apt_seq, apt_name, size_label,
         DATE_TRUNC('month', deal_date)::date AS month,
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS median_sale
  FROM sale_records
  WHERE apt_seq IN (SELECT DISTINCT apt_seq FROM alert_rules WHERE enabled)
  GROUP BY apt_seq, apt_name, size_label, DATE_TRUNC('month', deal_date)
),
monthly_rent AS (
  SELECT apt_seq, size_label,
         DATE_TRUNC('month', contract_date)::date AS month,
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_만원) AS median_jeonse
  FROM rent_records
  WHERE apt_seq IN (SELECT DISTINCT apt_seq FROM alert_rules WHERE enabled)
    AND monthly_rent_만원 = 0
  GROUP BY apt_seq, size_label, DATE_TRUNC('month', contract_date)
)
SELECT
  s.month,
  s.apt_name || ' ' || s.size_label || '㎡' AS 매물,
  ROUND((s.median_sale / 10000.0)::numeric, 1) AS 매매_중위_억,
  ROUND((r.median_jeonse / 10000.0)::numeric, 1) AS 전세_중위_억,
  ROUND(((s.median_sale - r.median_jeonse) / 10000.0)::numeric, 1) AS 갭_억,
  ROUND((r.median_jeonse::numeric / s.median_sale::numeric), 3) AS 전세가율
FROM monthly_sale s
LEFT JOIN monthly_rent r USING (apt_seq, size_label, month)
WHERE s.month >= CURRENT_DATE - INTERVAL '12 months'
  AND s.size_label IN ('59','84','mid')
ORDER BY 매물, s.month;
```

---

## 차트 4. 9개 구 거래량 추이 (매매·전월세 구분)

**차트 타입**: Line / Bar (x축: month, y축: 매매수 / 전월세수 두 series, filter: 구)
**용도**: 구별 매매·전월세 거래량 비교. 두 시장의 활동성 함께 추적.

```sql
WITH s AS (
  SELECT DATE_TRUNC('month', s.deal_date)::date AS month, d.name AS 구, COUNT(*) AS sale_count
  FROM sale_records s
  LEFT JOIN districts d ON s.sgg_cd = d.sgg_cd
  WHERE s.deal_date >= CURRENT_DATE - INTERVAL '12 months'
  GROUP BY 1, 2
),
r AS (
  SELECT DATE_TRUNC('month', r.contract_date)::date AS month, d.name AS 구, COUNT(*) AS rent_count
  FROM rent_records r
  LEFT JOIN districts d ON r.sgg_cd = d.sgg_cd
  WHERE r.contract_date >= CURRENT_DATE - INTERVAL '12 months'
  GROUP BY 1, 2
)
SELECT
  COALESCE(s.month, r.month) AS month,
  COALESCE(s.구, r.구) AS 구,
  COALESCE(s.sale_count, 0) AS 매매수,
  COALESCE(r.rent_count, 0) AS 전월세수,
  COALESCE(s.sale_count, 0) + COALESCE(r.rent_count, 0) AS 전체거래수
FROM s
FULL OUTER JOIN r USING (month, 구)
ORDER BY month, 구;
```

> **차트 구성 팁**:
> - **Wide format** — Studio Reports에서 매매수와 전월세수를 각각 다른 색깔의 라인/막대로 동시 표시. 구는 filter로 선택.
> - **Stacked area** 원하면: x=month, y1=매매수, y2=전월세수 (구는 한 번에 하나만 보거나 SUM)
> - 단지 정렬 (구 단위 비교) 시 `GROUP BY 구` 추가하여 누적 표시 가능

### 차트 4-대안. Long format (Stacked area / Group bar 차트용)

매매·전월세를 series로 stack/grouped 비교하고 싶으면 long 포맷 사용:

```sql
SELECT
  month,
  구,
  거래유형,
  COUNT(*) AS 거래수
FROM (
  SELECT
    DATE_TRUNC('month', s.deal_date)::date AS month,
    d.name AS 구,
    '매매' AS 거래유형
  FROM sale_records s
  LEFT JOIN districts d ON s.sgg_cd = d.sgg_cd
  WHERE s.deal_date >= CURRENT_DATE - INTERVAL '12 months'

  UNION ALL

  SELECT
    DATE_TRUNC('month', r.contract_date)::date,
    d.name,
    '전월세'
  FROM rent_records r
  LEFT JOIN districts d ON r.sgg_cd = d.sgg_cd
  WHERE r.contract_date >= CURRENT_DATE - INTERVAL '12 months'
) t
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
```

---

## 차트 5. 평형별 중위 시세 — 구별 구분

**차트 타입**: Line (x축: month, color: 구 또는 size_label, filter: 다른 한 차원)
**용도**: 구·평형별 시세 추이 비교. 강남/송파 vs 그 외 구의 가격대·변동성 차이 가시화.

```sql
SELECT
  DATE_TRUNC('month', s.deal_date)::date AS month,
  d.name AS 구,
  s.size_label,
  ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.price_만원) / 10000.0)::numeric, 1) AS 중위_억,
  COUNT(*) AS 거래수
FROM sale_records s
LEFT JOIN districts d ON s.sgg_cd = d.sgg_cd
WHERE s.size_label IN ('59', 'mid', '84')
  AND s.deal_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
```

> **차트 활용 팁**:
> - **size_label 고정 + 구별 비교** (예: 84㎡): filter `size_label = '84'` → 9개 구 × 12개월 라인. 강남·서초 vs 마포·동작 가격 차이 한눈.
> - **구 고정 + 평형별 비교** (예: 송파): filter `구 = '송파'` → 59/mid/84 3개 라인. 단일 구 안에서 평형별 시세 차이.
> - **거래수 컬럼**: 표본 수 — 노이즈 많은 시점(거래 0~2건) 식별용. tooltip에 함께 표시 권장.

---

## 차트 6. 알림 발송 이력

**차트 타입**: Table 또는 Number (count)

```sql
SELECT
  ar.display_name || ' ' || ar.size_label || '㎡' AS 매물,
  als.alert_type AS 알림타입,
  als.dedup_key AS 키,
  als.sent_at AS 발송일시
FROM alerts_sent als
JOIN alert_rules ar ON als.rule_id = ar.id
ORDER BY als.sent_at DESC
LIMIT 50;
```

---

## 차트 7. 갱신 인상률 분포 (선택)

**차트 타입**: Histogram / Bar
**용도**: 5%룰 사용 비중 + 시장 인상률 추이 분석

```sql
SELECT
  DATE_TRUNC('month', contract_date)::date AS month,
  ROUND(
    AVG((deposit_만원 - pre_deposit_만원)::numeric / NULLIF(pre_deposit_만원, 0) * 100),
    2
  ) AS 평균_인상률_pct,
  COUNT(*) FILTER (WHERE used_renewal_right) AS 갱신권_사용수,
  COUNT(*) AS 갱신_총수
FROM rent_records
WHERE contract_type = '갱신'
  AND pre_deposit_만원 IS NOT NULL
  AND pre_deposit_만원 > 0
  AND contract_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY 1
ORDER BY 1;
```

---

## 차트 8. 직거래 비율 (선택)

```sql
SELECT
  DATE_TRUNC('month', deal_date)::date AS month,
  COUNT(*) FILTER (WHERE dealing_type = '직거래') AS 직거래수,
  COUNT(*) FILTER (WHERE dealing_type = '중개거래') AS 중개거래수,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE dealing_type = '직거래') / NULLIF(COUNT(*), 0),
    1
  ) AS 직거래_pct
FROM sale_records
WHERE deal_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY 1
ORDER BY 1;
```

---

## 사용 팁

- **저장**: Studio Reports에서 "Save"하면 즉시 공유 가능 (URL 발급)
- **새로고침**: 매일 cron이 데이터 적재 → MV refresh되므로 최신 데이터 자동 반영
- **추가 차트**: alert_rules 추가 시 차트 1·2·3은 자동으로 새 단지 포함
- **차트 변경**: SQL을 수정 후 Save하면 즉시 반영
