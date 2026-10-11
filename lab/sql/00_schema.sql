-- Lab base schema: SYNTHETIC multi-tenant data (publishable; not a client schema).
-- Evokes the shape of a real SaaS (tenants, profiles, trips, invoices) so the agent has
-- realistic targets. Re-runnable: drops and recreates the public schema each time.

DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

-- PostgREST roles: `authenticator` logs in and SET ROLEs to `anon`/`authenticated`
-- based on the request JWT. These are created once at cluster init (outside this file);
-- here we only (re)grant schema access.

CREATE TABLE public.tenants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL
);

CREATE TABLE public.profiles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES public.tenants(id),
    email       text NOT NULL,
    full_name   text NOT NULL
);

CREATE TABLE public.trips (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL REFERENCES public.tenants(id),
    owner_email  text NOT NULL,
    origin       text NOT NULL,
    destination  text NOT NULL,
    cost         numeric(10,2) NOT NULL,
    notes        text
);

CREATE TABLE public.invoices (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES public.tenants(id),
    customer    text NOT NULL,
    amount      numeric(10,2) NOT NULL,
    status      text NOT NULL DEFAULT 'unpaid'
);

-- Synthetic seed: two tenants, a few rows each. No real data.
INSERT INTO public.tenants (id, name) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Acme Co'),
    ('22222222-2222-2222-2222-222222222222', 'Globex');

INSERT INTO public.profiles (tenant_id, email, full_name) VALUES
    ('11111111-1111-1111-1111-111111111111', 'ana@acme.test',  'Ana Acme'),
    ('22222222-2222-2222-2222-222222222222', 'glen@globex.test','Glen Globex');

INSERT INTO public.trips (tenant_id, owner_email, origin, destination, cost, notes) VALUES
    ('11111111-1111-1111-1111-111111111111', 'ana@acme.test',  'Lisbon', 'Porto',  120.00, 'client visit'),
    ('11111111-1111-1111-1111-111111111111', 'ana@acme.test',  'Porto',  'Madrid', 340.50, 'conference'),
    ('22222222-2222-2222-2222-222222222222', 'glen@globex.test','Berlin','Prague', 210.00, 'audit');

INSERT INTO public.invoices (tenant_id, customer, amount, status) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Wayne LLC', 1999.00, 'unpaid'),
    ('22222222-2222-2222-2222-222222222222', 'Stark Inc',  499.00, 'paid');

-- PostgREST data-API roles need to reach the schema and tables. RLS (configured by the
-- mode overlay) is what actually governs row visibility.
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO anon, authenticated;
