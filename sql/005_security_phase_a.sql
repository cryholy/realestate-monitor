-- Phase A: Supabase Security Advisor 경고 즉시 해결
-- anon/service_role 키 사용 영향 없이 5건의 경고 해소.
--
-- 적용 후 Security Advisor 결과:
--   Errors  7 → 5 (Security Definer View 2건 해결)
--   Warnings 5 → 0 (Function search_path 3건 + MV in API 2건 해결)
--
-- 남은 5 Errors는 RLS Disabled — Phase B에서 처리 예정.

-- 1. Function search_path 고정 — SQL injection via search_path 변조 방어
ALTER FUNCTION public.median_sale_price(text, text, integer)    SET search_path = pg_catalog, public;
ALTER FUNCTION public.median_jeonse_deposit(text, text, integer) SET search_path = pg_catalog, public;
ALTER FUNCTION public.refresh_monthly_stats()                    SET search_path = pg_catalog, public;

-- 2. View security_invoker (PostgreSQL 15+) — view가 호출자 권한으로 실행
ALTER VIEW public.v_complexes          SET (security_invoker = true);
ALTER VIEW public.v_alert_rules_check  SET (security_invoker = true);

-- 3. Materialized View — anon/authenticated 역할의 PostgREST API 접근 차단
--    (collector는 service_role로 접근하므로 영향 없음)
REVOKE ALL ON public.mv_monthly_sale_stats FROM anon, authenticated;
REVOKE ALL ON public.mv_monthly_rent_stats FROM anon, authenticated;
