-- 007: 취소거래 제외 + size_label='any' 지원
--
-- 002_views.sql의 median RPC / 매매 MV를 대체한다.
-- 배경 (deep-review CONFIRMED):
--   M3) median RPC가 size_label을 exact match해 rule.size_label='any'면 표본 0 → 항상 skip.
--       매매 가격경로 matcher는 'any'를 지원하는데 median 경로만 비대칭이었다.
--   M4) 취소거래 제외 필터가 RPC/MV 전무 → 신고가후취소가 median을 오염.
--       취소 신호는 cancel_type='O'로 판정한다. cancel_date는 MOLIT cdealDay 형식이
--       8자리 YYYYMMDD가 아니라 항상 null이라 신뢰 불가(DB 347건 취소거래 검증).
--       (취소 상태가 재수집 시 반영되려면 upsert가 DO UPDATE여야 함 — lib/db.py 참고)
-- rent_records에는 취소 개념이 없으므로 전세 경로엔 취소 필터를 넣지 않는다.
--
-- ✅ 적용됨: 2026-07-15 프로덕션(flsbxpjywjuhylfwnrby)에 마이그레이션
--    'cancel_filter_and_any_size_median'으로 적용 완료. 재적용 불필요.
--    (신규 셋업 재현용으로 파일은 유지 — 라이브 정의와 일치하도록 동기화됨.)

-- ⚠️ CREATE OR REPLACE / DROP+CREATE는 소유권·권한만 승계하고 나머지 속성은
--    명령이 지시한 값으로 재설정한다. 005의 search_path 하드닝(proconfig)과 MV의
--    anon/authenticated REVOKE, 004의 sgg_name 컬럼·인덱스가 조용히 사라지므로
--    아래에서 모두 재명시한다(005/006 적용된 라이브 DB에 007 적용 시 회귀 방지).

-- ── 매매 median RPC: 'any' 지원 + 취소거래 제외 ──────────────────────────
CREATE OR REPLACE FUNCTION median_sale_price(
  p_apt_seq text,
  p_size_label text,
  p_days integer
) RETURNS TABLE(median_price integer, sample_count integer)
LANGUAGE sql STABLE
SET search_path = pg_catalog, public
AS $$
  SELECT
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원)::integer AS median_price,
    COUNT(*)::integer AS sample_count
  FROM sale_records
  WHERE apt_seq = p_apt_seq
    AND (p_size_label = 'any' OR size_label = p_size_label)
    AND cancel_type IS DISTINCT FROM 'O'
    AND deal_date >= CURRENT_DATE - p_days;
$$;

-- ── 전세 median RPC: 'any' 지원 (rent엔 cancel_date 없음) ─────────────────
CREATE OR REPLACE FUNCTION median_jeonse_deposit(
  p_apt_seq text,
  p_size_label text,
  p_days integer
) RETURNS TABLE(median_deposit integer, sample_count integer)
LANGUAGE sql STABLE
SET search_path = pg_catalog, public
AS $$
  SELECT
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_만원)::integer AS median_deposit,
    COUNT(*)::integer AS sample_count
  FROM rent_records
  WHERE apt_seq = p_apt_seq
    AND (p_size_label = 'any' OR size_label = p_size_label)
    AND monthly_rent_만원 = 0
    AND contract_date >= CURRENT_DATE - p_days;
$$;

-- ── 매매 월별 MV: 취소거래 제외 (MV는 CREATE OR REPLACE 불가 → DROP 후 재생성) ──
--    004의 districts LEFT JOIN·sgg_name·양 인덱스를 유지한 채 취소거래만 추가로 제외.
-- month 컬럼 타입(timestamptz)·percentile 캐스트는 라이브 MV 정의를 그대로 복제해
-- 신규 셋업과 프로덕션이 드리프트하지 않게 한다(취소거래 제외 WHERE만 추가).
DROP MATERIALIZED VIEW IF EXISTS mv_monthly_sale_stats;
CREATE MATERIALIZED VIEW mv_monthly_sale_stats AS
 SELECT s.apt_seq,
    s.apt_name,
    s.sgg_cd,
    d.name AS sgg_name,
    s.size_label,
    date_trunc('month'::text, (s.deal_date)::timestamp with time zone) AS month,
    count(*) AS deals,
    percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((s."price_만원")::double precision)) AS median_price,
    min(s."price_만원") AS min_price,
    max(s."price_만원") AS max_price
   FROM (sale_records s
     LEFT JOIN districts d ON ((s.sgg_cd = d.sgg_cd)))
  WHERE s.cancel_type IS DISTINCT FROM 'O'
  GROUP BY s.apt_seq, s.apt_name, s.sgg_cd, d.name, s.size_label, (date_trunc('month'::text, (s.deal_date)::timestamp with time zone));

CREATE INDEX IF NOT EXISTS idx_mv_monthly_sale ON mv_monthly_sale_stats (apt_seq, size_label, month);
CREATE INDEX IF NOT EXISTS idx_mv_monthly_sale_sgg ON mv_monthly_sale_stats (sgg_name, month);

-- 005의 MV API 노출 차단(REVOKE)은 DROP+CREATE로 리셋되므로 재적용.
REVOKE ALL ON public.mv_monthly_sale_stats FROM anon, authenticated;
