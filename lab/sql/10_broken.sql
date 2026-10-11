-- BROKEN mode: deliberately misconfigured, with known-answer bugs for the assessment.
--   1. trips: RLS left DISABLED  -> anonymous reads every row (the headline bug).
--   2. invoices: RLS enabled but a permissive `USING (true)` policy for anon -> leaks too.
--   3. profiles: correctly locked (RLS on, no anon policy) -> control / true-negative.
--   4. v_public_trips: a view that bypasses RLS -> subtle leak even if trips were fixed.

-- 1. trips wide open.
ALTER TABLE public.trips DISABLE ROW LEVEL SECURITY;

-- 2. invoices: RLS on, but a permissive anon policy (a classic misconfiguration).
ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS invoices_anon_read ON public.invoices;
CREATE POLICY invoices_anon_read ON public.invoices FOR SELECT TO anon USING (true);

-- 3. profiles: locked down (RLS on, no anon policy) -> should deny anon. True negative.
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS profiles_anon_read ON public.profiles;

ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;

-- 4. Subtle: a view owned by a privileged role bypasses the underlying table RLS.
DROP VIEW IF EXISTS public.v_public_trips;
CREATE VIEW public.v_public_trips AS SELECT origin, destination, cost FROM public.trips;
GRANT SELECT ON public.v_public_trips TO anon;
