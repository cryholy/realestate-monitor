-- Phase B: 5개 public 테이블에 RLS 활성화 + service_role bypass policy
-- 적용 전 .env / GitHub Secret의 SUPABASE_SERVICE_ROLE_KEY가
-- service_role JWT여야 함 (anon key 사용 시 모든 작업 차단됨).
--
-- 적용 후 Security Advisor 결과:
--   Errors  5 → 0 (RLS Disabled 5건 모두 해결)
--   Warnings 0 (Phase A에서 해결됨)

-- 1. RLS 활성화
ALTER TABLE public.sale_records  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rent_records  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alert_rules   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts_sent   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.districts     ENABLE ROW LEVEL SECURITY;

-- 2. service_role 정책 — 모든 작업 허용
-- (service_role JWT는 RLS bypass되지만 명시적 policy도 함께 두어 의도를 코드로 표현)
CREATE POLICY service_role_all_sale_records ON public.sale_records
  AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all_rent_records ON public.rent_records
  AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all_alert_rules ON public.alert_rules
  AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all_alerts_sent ON public.alerts_sent
  AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all_districts ON public.districts
  AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 3. anon/authenticated 역할은 정책 없음 → 모든 작업 차단됨 (의도)
-- 미래에 read-only public dashboard가 필요하면 그때 SELECT 정책만 추가:
-- CREATE POLICY public_read_sale_records ON sale_records
--   AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
