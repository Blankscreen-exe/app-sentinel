-- CORRECT mode: RLS enabled everywhere; anonymous requests get nothing.
-- Only the `authenticated` role may read, and (for a real app) policies would further
-- scope by tenant. For the anonymous-access assessment, the key property is: anon = 0 rows.

ALTER TABLE public.trips     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoices  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenants   ENABLE ROW LEVEL SECURITY;

-- Authenticated users may read ONLY their own tenant's rows (proper tenant isolation).
-- The tenant is taken from the request JWT claim. anon has no policy -> denied.
DROP POLICY IF EXISTS trips_auth_read    ON public.trips;
DROP POLICY IF EXISTS invoices_auth_read ON public.invoices;
DROP POLICY IF EXISTS profiles_auth_read ON public.profiles;

CREATE POLICY trips_auth_read ON public.trips FOR SELECT TO authenticated
  USING (tenant_id = (current_setting('request.jwt.claims', true)::json ->> 'tenant_id')::uuid);
CREATE POLICY invoices_auth_read ON public.invoices FOR SELECT TO authenticated
  USING (tenant_id = (current_setting('request.jwt.claims', true)::json ->> 'tenant_id')::uuid);
CREATE POLICY profiles_auth_read ON public.profiles FOR SELECT TO authenticated
  USING (tenant_id = (current_setting('request.jwt.claims', true)::json ->> 'tenant_id')::uuid);

-- Remove any lab-only bypass view that the broken mode may have created.
DROP VIEW IF EXISTS public.v_public_trips;
