-- 단지 검색 view (alert_rules 작성용)
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

-- 월별 집계 MV
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
