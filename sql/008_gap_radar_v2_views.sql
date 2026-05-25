-- 서울 한강권 대표단지 갭 레이더 v2
-- 변경점: 직거래 제외, 평형 mid 추가, 신규/갱신 전세 분리, 갱신 압력 신호 추가.

-- 1) 정제 base
CREATE OR REPLACE VIEW v_sale_clean_v2
WITH (security_invoker = true) AS
SELECT *
FROM sale_records
WHERE dealing_type = '중개거래'
  AND cancel_date IS NULL
  AND price_만원 > 0
  AND apt_seq IS NOT NULL AND apt_seq <> ''
  AND size_label IN ('59', '84', 'mid');

CREATE OR REPLACE VIEW v_jeonse_new_v2
WITH (security_invoker = true) AS
SELECT *
FROM rent_records
WHERE contract_type = '신규'
  AND monthly_rent_만원 = 0
  AND deposit_만원 > 0
  AND apt_seq IS NOT NULL AND apt_seq <> ''
  AND size_label IN ('59', '84', 'mid');

CREATE OR REPLACE VIEW v_jeonse_renewal_v2
WITH (security_invoker = true) AS
SELECT *
FROM rent_records
WHERE contract_type = '갱신'
  AND monthly_rent_만원 = 0
  AND deposit_만원 > 0
  AND pre_deposit_만원 > 0
  AND apt_seq IS NOT NULL AND apt_seq <> ''
  AND size_label IN ('59', '84', 'mid');

-- 2) 12개월 집계 (단지+평형)
CREATE OR REPLACE VIEW v_gap_radar_sale_12m_v2
WITH (security_invoker = true) AS
SELECT
  s.apt_seq,
  s.apt_name,
  s.sgg_cd,
  d.name AS district_name,
  CASE
    WHEN d.name IN ('강남', '강남구', '서초', '서초구', '송파', '송파구') THEN '강남권'
    WHEN d.name IN ('마포', '마포구', '용산', '용산구', '성동', '성동구', '광진', '광진구') THEN '마용성/동부권'
    WHEN d.name IN ('동작', '동작구', '강동', '강동구') THEN '상대가치권'
    ELSE '기타'
  END AS lifestyle_area,
  s.size_label,
  COUNT(*) AS sale_count_12m,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.price_만원)::integer AS sale_median_12m
FROM v_sale_clean_v2 s
LEFT JOIN districts d ON s.sgg_cd = d.sgg_cd
WHERE s.deal_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY s.apt_seq, s.apt_name, s.sgg_cd, d.name, s.size_label;

CREATE OR REPLACE VIEW v_gap_radar_jeonse_new_12m_v2
WITH (security_invoker = true) AS
SELECT
  r.apt_seq,
  r.size_label,
  COUNT(*) AS jeonse_new_count_12m,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.deposit_만원)::integer AS jeonse_new_median_12m
FROM v_jeonse_new_v2 r
WHERE r.contract_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY r.apt_seq, r.size_label;

-- 3) 대표성 점수
CREATE OR REPLACE VIEW v_gap_radar_candidate_scores_v2
WITH (security_invoker = true) AS
WITH joined AS (
  SELECT
    s.apt_seq, s.apt_name, s.sgg_cd, s.district_name, s.lifestyle_area, s.size_label,
    s.sale_count_12m, s.sale_median_12m,
    COALESCE(r.jeonse_new_count_12m, 0) AS jeonse_new_count_12m,
    r.jeonse_new_median_12m
  FROM v_gap_radar_sale_12m_v2 s
  LEFT JOIN v_gap_radar_jeonse_new_12m_v2 r
    ON r.apt_seq = s.apt_seq AND r.size_label = s.size_label
),
scored AS (
  SELECT
    *,
    CUME_DIST() OVER (PARTITION BY sgg_cd ORDER BY sale_count_12m) AS sale_liquidity_pct,
    CUME_DIST() OVER (PARTITION BY sgg_cd ORDER BY sale_median_12m) AS price_level_pct,
    CUME_DIST() OVER (PARTITION BY sgg_cd ORDER BY jeonse_new_count_12m) AS jeonse_new_liquidity_pct
  FROM joined
  WHERE sale_count_12m >= 2
)
SELECT
  apt_seq, apt_name, sgg_cd, district_name, lifestyle_area, size_label,
  sale_count_12m, sale_median_12m, jeonse_new_count_12m, jeonse_new_median_12m,
  ROUND((sale_liquidity_pct * 50 + price_level_pct * 30 + jeonse_new_liquidity_pct * 20)::numeric, 2) AS representative_score
FROM scored;

-- 4) 구별 Top 10
CREATE OR REPLACE VIEW v_gap_radar_representative_items_v2
WITH (security_invoker = true) AS
SELECT *
FROM (
  SELECT
    c.*,
    ROW_NUMBER() OVER (
      PARTITION BY c.sgg_cd
      ORDER BY c.representative_score DESC, c.sale_count_12m DESC, c.sale_median_12m DESC, c.apt_name, c.size_label
    ) AS district_rank
  FROM v_gap_radar_candidate_scores_v2 c
) ranked
WHERE district_rank <= 10;

-- 5) 최종 리포트 행
CREATE OR REPLACE VIEW v_gap_radar_weekly_rows_v2
WITH (security_invoker = true) AS
WITH sale_90 AS (
  SELECT s.apt_seq, s.size_label,
    COUNT(*) AS sale_count_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.price_만원)::integer AS sale_median_90d
  FROM v_sale_clean_v2 s
  WHERE s.deal_date >= CURRENT_DATE - INTERVAL '90 days'
  GROUP BY s.apt_seq, s.size_label
),
sale_prev_90 AS (
  SELECT s.apt_seq, s.size_label,
    COUNT(*) AS sale_count_prev_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.price_만원)::integer AS sale_median_prev_90d
  FROM v_sale_clean_v2 s
  WHERE s.deal_date >= CURRENT_DATE - INTERVAL '180 days'
    AND s.deal_date < CURRENT_DATE - INTERVAL '90 days'
  GROUP BY s.apt_seq, s.size_label
),
jeonse_new_90 AS (
  SELECT r.apt_seq, r.size_label,
    COUNT(*) AS jeonse_new_count_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.deposit_만원)::integer AS jeonse_new_median_90d
  FROM v_jeonse_new_v2 r
  WHERE r.contract_date >= CURRENT_DATE - INTERVAL '90 days'
  GROUP BY r.apt_seq, r.size_label
),
jeonse_new_prev_90 AS (
  SELECT r.apt_seq, r.size_label,
    COUNT(*) AS jeonse_new_count_prev_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.deposit_만원)::integer AS jeonse_new_median_prev_90d
  FROM v_jeonse_new_v2 r
  WHERE r.contract_date >= CURRENT_DATE - INTERVAL '180 days'
    AND r.contract_date < CURRENT_DATE - INTERVAL '90 days'
  GROUP BY r.apt_seq, r.size_label
),
jeonse_renewal_90 AS (
  SELECT r.apt_seq, r.size_label,
    COUNT(*) AS jeonse_renewal_count_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.deposit_만원)::integer AS jeonse_renewal_median_90d,
    SUM(CASE WHEN r.used_renewal_right IS TRUE THEN 1 ELSE 0 END)::numeric
      / NULLIF(COUNT(*), 0) AS renewal_right_use_rate_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
      ORDER BY (r.deposit_만원::numeric - r.pre_deposit_만원::numeric) / NULLIF(r.pre_deposit_만원, 0)
    ) AS renewal_pct_change_median_90d
  FROM v_jeonse_renewal_v2 r
  WHERE r.contract_date >= CURRENT_DATE - INTERVAL '90 days'
  GROUP BY r.apt_seq, r.size_label
),
jeonse_renewal_prev_90 AS (
  SELECT r.apt_seq, r.size_label,
    COUNT(*) AS jeonse_renewal_count_prev_90d,
    SUM(CASE WHEN r.used_renewal_right IS TRUE THEN 1 ELSE 0 END)::numeric
      / NULLIF(COUNT(*), 0) AS renewal_right_use_rate_prev_90d
  FROM v_jeonse_renewal_v2 r
  WHERE r.contract_date >= CURRENT_DATE - INTERVAL '180 days'
    AND r.contract_date < CURRENT_DATE - INTERVAL '90 days'
  GROUP BY r.apt_seq, r.size_label
)
SELECT
  rep.district_rank, rep.representative_score,
  rep.apt_seq, rep.apt_name, rep.sgg_cd, rep.district_name, rep.lifestyle_area, rep.size_label,
  rep.sale_count_12m, rep.jeonse_new_count_12m, rep.sale_median_12m, rep.jeonse_new_median_12m,
  sale_90.sale_count_90d, sale_90.sale_median_90d,
  jeonse_new_90.jeonse_new_count_90d, jeonse_new_90.jeonse_new_median_90d,
  CASE
    WHEN sale_90.sale_median_90d IS NOT NULL AND jeonse_new_90.jeonse_new_median_90d IS NOT NULL
    THEN sale_90.sale_median_90d - jeonse_new_90.jeonse_new_median_90d ELSE NULL END AS gap_90d,
  CASE
    WHEN sale_90.sale_median_90d IS NOT NULL AND sale_90.sale_median_90d > 0
     AND jeonse_new_90.jeonse_new_median_90d IS NOT NULL
    THEN ROUND((jeonse_new_90.jeonse_new_median_90d::numeric / sale_90.sale_median_90d::numeric), 4)
    ELSE NULL END AS jeonse_ratio_90d,
  jeonse_renewal_90.jeonse_renewal_count_90d,
  jeonse_renewal_90.jeonse_renewal_median_90d,
  ROUND(jeonse_renewal_90.renewal_right_use_rate_90d::numeric, 4) AS renewal_right_use_rate_90d,
  ROUND(jeonse_renewal_90.renewal_pct_change_median_90d::numeric, 4) AS renewal_pct_change_median_90d,
  CASE
    WHEN jeonse_new_90.jeonse_new_median_90d IS NOT NULL
     AND jeonse_renewal_90.jeonse_renewal_median_90d IS NOT NULL
    THEN jeonse_new_90.jeonse_new_median_90d - jeonse_renewal_90.jeonse_renewal_median_90d
    ELSE NULL END AS new_minus_renewal_gap_90d,
  sale_prev_90.sale_count_prev_90d, sale_prev_90.sale_median_prev_90d,
  jeonse_new_prev_90.jeonse_new_count_prev_90d, jeonse_new_prev_90.jeonse_new_median_prev_90d,
  CASE
    WHEN sale_prev_90.sale_median_prev_90d IS NOT NULL AND jeonse_new_prev_90.jeonse_new_median_prev_90d IS NOT NULL
    THEN sale_prev_90.sale_median_prev_90d - jeonse_new_prev_90.jeonse_new_median_prev_90d ELSE NULL END AS gap_prev_90d,
  CASE
    WHEN sale_prev_90.sale_median_prev_90d IS NOT NULL AND sale_prev_90.sale_median_prev_90d > 0
     AND jeonse_new_prev_90.jeonse_new_median_prev_90d IS NOT NULL
    THEN ROUND((jeonse_new_prev_90.jeonse_new_median_prev_90d::numeric / sale_prev_90.sale_median_prev_90d::numeric), 4)
    ELSE NULL END AS jeonse_ratio_prev_90d,
  ROUND(jeonse_renewal_prev_90.renewal_right_use_rate_prev_90d::numeric, 4) AS renewal_right_use_rate_prev_90d,
  CASE
    WHEN COALESCE(sale_90.sale_count_90d, 0) >= 5
     AND COALESCE(jeonse_new_90.jeonse_new_count_90d, 0) >= 5 THEN '신뢰도 높음'
    WHEN COALESCE(sale_90.sale_count_90d, 0) = 0
      OR COALESCE(jeonse_new_90.jeonse_new_count_90d, 0) = 0 THEN '데이터 부족'
    ELSE '주의'
  END AS reliability_label,
  CASE
    WHEN COALESCE(sale_90.sale_count_90d, 0) >= 5
     AND COALESCE(jeonse_new_90.jeonse_new_count_90d, 0) >= 5 THEN 1.0
    WHEN COALESCE(sale_90.sale_count_90d, 0) = 0
      OR COALESCE(jeonse_new_90.jeonse_new_count_90d, 0) = 0 THEN 0.0
    ELSE 0.5
  END AS reliability_weight
FROM v_gap_radar_representative_items_v2 rep
LEFT JOIN sale_90 ON sale_90.apt_seq = rep.apt_seq AND sale_90.size_label = rep.size_label
LEFT JOIN sale_prev_90 ON sale_prev_90.apt_seq = rep.apt_seq AND sale_prev_90.size_label = rep.size_label
LEFT JOIN jeonse_new_90 ON jeonse_new_90.apt_seq = rep.apt_seq AND jeonse_new_90.size_label = rep.size_label
LEFT JOIN jeonse_new_prev_90 ON jeonse_new_prev_90.apt_seq = rep.apt_seq AND jeonse_new_prev_90.size_label = rep.size_label
LEFT JOIN jeonse_renewal_90 ON jeonse_renewal_90.apt_seq = rep.apt_seq AND jeonse_renewal_90.size_label = rep.size_label
LEFT JOIN jeonse_renewal_prev_90 ON jeonse_renewal_prev_90.apt_seq = rep.apt_seq AND jeonse_renewal_prev_90.size_label = rep.size_label;
