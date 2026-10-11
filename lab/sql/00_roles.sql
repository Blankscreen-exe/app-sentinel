-- Runs once at cluster init (docker-entrypoint-initdb.d). Creates the PostgREST roles.
-- `authenticator` is the login role PostgREST connects as; per request it SET ROLEs to
-- `anon` (no JWT) or `authenticated` (valid JWT with role=authenticated).

CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'labpass';
GRANT anon, authenticated TO authenticator;
