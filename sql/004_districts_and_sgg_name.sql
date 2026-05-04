-- districts lookup 테이블 + MV/View에 sgg_name 컬럼 추가
-- 목적: 5자리 sgg_cd 대신 한글 구 이름으로 직접 조회 가능

CREATE TABLE IF NOT EXISTS districts (
  sgg_cd  text PRIMARY KEY,
  name    text NOT NULL
);

INSERT INTO districts (sgg_cd, name) VALUES
  ('11200', '성동'),
  ('11215', '광진'),
  ('11440', '마포'),
  ('11650', '서초'),
  ('11680', '강남'),
  ('11710', '송파'),
  ('11170', '용산'),
  ('11590', '동작'),
  ('11740', '강동')
ON CONFLICT (sgg_cd) DO UPDATE SET name = EXCLUDED.name;

-- v_alert_rules_check가 v_complexes 의존이라 먼저 DROP
DROP VIEW IF EXISTS v_alert_rules_check;
DROP VIEW IF EXISTS v_complexes;

CREATE VIEW v_complexes AS
SELECT DISTINCT
  s.apt_seq,
  s.apt_name,
  s.sgg_cd,
  d.name AS sgg_name,
  s.umd_nm,
  s.build_year,
  COUNT(*) OVER (PARTITION BY s.apt_seq) AS sale_records_count,
  MIN(s.deal_date) OVER (PARTITION BY s.apt_seq) AS earliest_deal,
  MAX(s.deal_date) OVER (PARTITION BY s.apt_seq) AS latest_deal
FROM sale_records s
LEFT JOIN districts d ON s.sgg_cd = d.sgg_cd;

CREATE VIEW v_alert_rules_check AS
SELECT
  ar.id, ar.apt_seq, ar.display_name, ar.size_label,
  ar.max_price_만원, ar.min_jeonse_ratio, ar.enabled,
  vc.apt_name AS actual_apt_name,
  vc.sgg_cd AS actual_sgg_cd,
  vc.sgg_name AS actual_sgg_name,
  CASE
    WHEN vc.apt_seq IS NULL THEN '⚠️ apt_seq 미존재'
    WHEN ar.display_name != vc.apt_name THEN '⚠️ display_name 불일치'
    ELSE '✅ OK'
  END AS validation
FROM alert_rules ar
LEFT JOIN (SELECT DISTINCT apt_seq, apt_name, sgg_cd, sgg_name FROM v_complexes) vc
  ON ar.apt_seq = vc.apt_seq;

-- mv_monthly_sale_stats 재생성 (sgg_name 추가)
DROP MATERIALIZED VIEW IF EXISTS mv_monthly_sale_stats;
CREATE MATERIALIZED VIEW mv_monthly_sale_stats AS
SELECT
  s.apt_seq, s.apt_name, s.sgg_cd, d.name AS sgg_name, s.size_label,
  DATE_TRUNC('month', s.deal_date) AS month,
  COUNT(*) AS deals,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.price_만원) AS median_price,
  MIN(s.price_만원) AS min_price,
  MAX(s.price_만원) AS max_price
FROM sale_records s
LEFT JOIN districts d ON s.sgg_cd = d.sgg_cd
GROUP BY s.apt_seq, s.apt_name, s.sgg_cd, d.name, s.size_label, DATE_TRUNC('month', s.deal_date);

CREATE INDEX IF NOT EXISTS idx_mv_monthly_sale ON mv_monthly_sale_stats (apt_seq, size_label, month);
CREATE INDEX IF NOT EXISTS idx_mv_monthly_sale_sgg ON mv_monthly_sale_stats (sgg_name, month);

-- mv_monthly_rent_stats 재생성 (sgg_name 추가)
DROP MATERIALIZED VIEW IF EXISTS mv_monthly_rent_stats;
CREATE MATERIALIZED VIEW mv_monthly_rent_stats AS
SELECT
  r.apt_seq, r.apt_name, r.sgg_cd, d.name AS sgg_name, r.size_label,
  DATE_TRUNC('month', r.contract_date) AS month,
  COUNT(*) AS contracts,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.deposit_만원) FILTER (WHERE r.monthly_rent_만원 = 0) AS median_jeonse,
  MIN(r.deposit_만원) FILTER (WHERE r.monthly_rent_만원 = 0) AS min_jeonse,
  MAX(r.deposit_만원) FILTER (WHERE r.monthly_rent_만원 = 0) AS max_jeonse
FROM rent_records r
LEFT JOIN districts d ON r.sgg_cd = d.sgg_cd
GROUP BY r.apt_seq, r.apt_name, r.sgg_cd, d.name, r.size_label, DATE_TRUNC('month', r.contract_date);

CREATE INDEX IF NOT EXISTS idx_mv_monthly_rent ON mv_monthly_rent_stats (apt_seq, size_label, month);
CREATE INDEX IF NOT EXISTS idx_mv_monthly_rent_sgg ON mv_monthly_rent_stats (sgg_name, month);
