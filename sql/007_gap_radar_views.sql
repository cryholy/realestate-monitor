-- 서울 한강권 대표단지 갭 레이더
-- 대표 단지+평형 선정과 주간 리포트 지표 계산.

CREATE OR REPLACE VIEW v_gap_radar_sale_12m
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
FROM sale_records s
LEFT JOIN districts d ON s.sgg_cd = d.sgg_cd
WHERE s.deal_date >= CURRENT_DATE - INTERVAL '12 months'
  AND s.size_label IN ('59', '84')
  AND s.cancel_date IS NULL
  AND s.price_만원 > 0
  AND s.apt_seq IS NOT NULL
  AND s.apt_seq <> ''
GROUP BY s.apt_seq, s.apt_name, s.sgg_cd, d.name, s.size_label;

CREATE OR REPLACE VIEW v_gap_radar_rent_12m
WITH (security_invoker = true) AS
SELECT
  r.apt_seq,
  r.size_label,
  COUNT(*) AS jeonse_count_12m,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.deposit_만원)::integer AS jeonse_median_12m
FROM rent_records r
WHERE r.contract_date >= CURRENT_DATE - INTERVAL '12 months'
  AND r.size_label IN ('59', '84')
  AND r.monthly_rent_만원 = 0
  AND r.deposit_만원 > 0
  AND r.apt_seq IS NOT NULL
  AND r.apt_seq <> ''
GROUP BY r.apt_seq, r.size_label;

CREATE OR REPLACE VIEW v_gap_radar_candidate_scores
WITH (security_invoker = true) AS
WITH joined AS (
  SELECT
    s.apt_seq,
    s.apt_name,
    s.sgg_cd,
    s.district_name,
    s.lifestyle_area,
    s.size_label,
    s.sale_count_12m,
    s.sale_median_12m,
    COALESCE(r.jeonse_count_12m, 0) AS jeonse_count_12m,
    r.jeonse_median_12m
  FROM v_gap_radar_sale_12m s
  LEFT JOIN v_gap_radar_rent_12m r
    ON r.apt_seq = s.apt_seq
   AND r.size_label = s.size_label
),
scored AS (
  SELECT
    *,
    CUME_DIST() OVER (PARTITION BY sgg_cd ORDER BY sale_count_12m) AS sale_liquidity_pct,
    CUME_DIST() OVER (PARTITION BY sgg_cd ORDER BY sale_median_12m) AS price_level_pct,
    CUME_DIST() OVER (PARTITION BY sgg_cd ORDER BY jeonse_count_12m) AS jeonse_liquidity_pct
  FROM joined
  WHERE sale_count_12m >= 2
)
SELECT
  apt_seq,
  apt_name,
  sgg_cd,
  district_name,
  lifestyle_area,
  size_label,
  sale_count_12m,
  sale_median_12m,
  jeonse_count_12m,
  jeonse_median_12m,
  ROUND((sale_liquidity_pct * 50 + price_level_pct * 30 + jeonse_liquidity_pct * 20)::numeric, 2) AS representative_score
FROM scored;

CREATE OR REPLACE VIEW v_gap_radar_representative_items
WITH (security_invoker = true) AS
SELECT *
FROM (
  SELECT
    c.*,
    ROW_NUMBER() OVER (
      PARTITION BY c.sgg_cd
      ORDER BY c.representative_score DESC, c.sale_count_12m DESC, c.sale_median_12m DESC, c.apt_name, c.size_label
    ) AS district_rank
  FROM v_gap_radar_candidate_scores c
) ranked
WHERE district_rank <= 10;

CREATE OR REPLACE VIEW v_gap_radar_weekly_rows
WITH (security_invoker = true) AS
WITH sale_90 AS (
  SELECT
    s.apt_seq,
    s.size_label,
    COUNT(*) AS sale_count_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.price_만원)::integer AS sale_median_90d
  FROM sale_records s
  WHERE s.deal_date >= CURRENT_DATE - INTERVAL '90 days'
    AND s.size_label IN ('59', '84')
    AND s.cancel_date IS NULL
    AND s.price_만원 > 0
  GROUP BY s.apt_seq, s.size_label
),
sale_prev_90 AS (
  SELECT
    s.apt_seq,
    s.size_label,
    COUNT(*) AS sale_count_prev_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.price_만원)::integer AS sale_median_prev_90d
  FROM sale_records s
  WHERE s.deal_date >= CURRENT_DATE - INTERVAL '180 days'
    AND s.deal_date < CURRENT_DATE - INTERVAL '90 days'
    AND s.size_label IN ('59', '84')
    AND s.cancel_date IS NULL
    AND s.price_만원 > 0
  GROUP BY s.apt_seq, s.size_label
),
rent_90 AS (
  SELECT
    r.apt_seq,
    r.size_label,
    COUNT(*) AS jeonse_count_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.deposit_만원)::integer AS jeonse_median_90d
  FROM rent_records r
  WHERE r.contract_date >= CURRENT_DATE - INTERVAL '90 days'
    AND r.size_label IN ('59', '84')
    AND r.monthly_rent_만원 = 0
    AND r.deposit_만원 > 0
  GROUP BY r.apt_seq, r.size_label
),
rent_prev_90 AS (
  SELECT
    r.apt_seq,
    r.size_label,
    COUNT(*) AS jeonse_count_prev_90d,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.deposit_만원)::integer AS jeonse_median_prev_90d
  FROM rent_records r
  WHERE r.contract_date >= CURRENT_DATE - INTERVAL '180 days'
    AND r.contract_date < CURRENT_DATE - INTERVAL '90 days'
    AND r.size_label IN ('59', '84')
    AND r.monthly_rent_만원 = 0
    AND r.deposit_만원 > 0
  GROUP BY r.apt_seq, r.size_label
)
SELECT
  rep.district_rank,
  rep.representative_score,
  rep.apt_seq,
  rep.apt_name,
  rep.sgg_cd,
  rep.district_name,
  rep.lifestyle_area,
  rep.size_label,
  rep.sale_count_12m,
  rep.jeonse_count_12m,
  rep.sale_median_12m,
  rep.jeonse_median_12m,
  sale_90.sale_count_90d,
  sale_90.sale_median_90d,
  rent_90.jeonse_count_90d,
  rent_90.jeonse_median_90d,
  CASE
    WHEN sale_90.sale_median_90d IS NOT NULL AND rent_90.jeonse_median_90d IS NOT NULL
    THEN sale_90.sale_median_90d - rent_90.jeonse_median_90d
    ELSE NULL
  END AS gap_90d,
  CASE
    WHEN sale_90.sale_median_90d IS NOT NULL
     AND sale_90.sale_median_90d > 0
     AND rent_90.jeonse_median_90d IS NOT NULL
    THEN ROUND((rent_90.jeonse_median_90d::numeric / sale_90.sale_median_90d::numeric), 4)
    ELSE NULL
  END AS jeonse_ratio_90d,
  sale_prev_90.sale_count_prev_90d,
  sale_prev_90.sale_median_prev_90d,
  rent_prev_90.jeonse_count_prev_90d,
  rent_prev_90.jeonse_median_prev_90d,
  CASE
    WHEN sale_prev_90.sale_median_prev_90d IS NOT NULL AND rent_prev_90.jeonse_median_prev_90d IS NOT NULL
    THEN sale_prev_90.sale_median_prev_90d - rent_prev_90.jeonse_median_prev_90d
    ELSE NULL
  END AS gap_prev_90d,
  CASE
    WHEN sale_prev_90.sale_median_prev_90d IS NOT NULL
     AND sale_prev_90.sale_median_prev_90d > 0
     AND rent_prev_90.jeonse_median_prev_90d IS NOT NULL
    THEN ROUND((rent_prev_90.jeonse_median_prev_90d::numeric / sale_prev_90.sale_median_prev_90d::numeric), 4)
    ELSE NULL
  END AS jeonse_ratio_prev_90d
FROM v_gap_radar_representative_items rep
LEFT JOIN sale_90
  ON sale_90.apt_seq = rep.apt_seq
 AND sale_90.size_label = rep.size_label
LEFT JOIN rent_90
  ON rent_90.apt_seq = rep.apt_seq
 AND rent_90.size_label = rep.size_label
LEFT JOIN sale_prev_90
  ON sale_prev_90.apt_seq = rep.apt_seq
 AND sale_prev_90.size_label = rep.size_label
LEFT JOIN rent_prev_90
  ON rent_prev_90.apt_seq = rep.apt_seq
 AND rent_prev_90.size_label = rep.size_label;
