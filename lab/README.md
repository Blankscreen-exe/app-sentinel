# Local assessment lab

A deliberately misconfigurable backend for exercising the assessment pipeline against
**known-answer** cases. Everything here is **synthetic and lab-only** (ADR-010, ADR-014):
the schema, data, JWT secret, and anon key are all fake and public by design — never
reuse them anywhere real.

## What it is

The minimal Supabase **data-API surface**: PostgreSQL + PostgREST, with `anon` /
`authenticated` roles, a JWT secret, and Row Level Security — which is what Supabase's
REST API is underneath. (Full Supabase CLI stack is an optional upgrade; see ADR-014.)

## Run it

```bash
cd lab
docker compose -f docker-compose.lab.yml up -d      # start Postgres + PostgREST
./mode.sh broken                                    # load schema + the misconfigured overlay
# ...or:
./mode.sh correct                                   # load schema + the locked-down overlay
```

REST API: `http://127.0.0.1:3001` (host). In-cluster: `http://lab-rest:3000`.
Anon key (a role-scoped JWT, like a Supabase legacy anon key): `python3 mint_anon_key.py`.

## Known-answer behaviour (anonymous reads)

| Table | `broken` | `correct` | Why |
|---|---|---|---|
| `trips` | **leaks** | denied `[]` | broken: RLS disabled |
| `invoices` | **leaks** | denied `[]` | broken: permissive `USING(true)` anon policy |
| `profiles` | denied `[]` | denied `[]` | always locked — a true negative (must NOT be flagged) |
| `v_public_trips` | **leaks** | removed | broken: a view that bypasses table RLS (subtle) |

Quick check:
```bash
A=$(python3 mint_anon_key.py)
curl -s "http://127.0.0.1:3001/trips?select=origin" -H "apikey: $A" -H "Authorization: Bearer $A"
```

## Sample app

`python3 build_sample_apk.py sample-lab-app.apk` builds a synthetic APK whose embedded
config points at the lab (URL + anon key + `from("trips"/"invoices"/"profiles")`). Upload
it to the platform to drive an end-to-end assessment.


## Firebase RTDB lab

A mock Firebase Realtime Database for the Firebase open-rules check (faithful to the RTDB
`GET /<path>.json` REST contract; synthetic data). Started with the lab stack on
`127.0.0.1:9000`.

```bash
./firebase-mode.sh broken    # open read rules (leaks)
./firebase-mode.sh correct   # locked rules (Permission denied)
curl -s http://127.0.0.1:9000/users.json
```
