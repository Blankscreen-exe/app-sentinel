# App Sentinel

An **agentic mobile-application security assessment platform**. You give it an Android
APK you own or are authorized to assess; it analyzes the app, maps the backend it talks
to, and — only within an authorized scope — runs safe, evidence-based checks against that
backend, producing findings it can prove.

It is built around one idea:

> **The LLM proposes. Deterministic code decides and proves.**

The AI reasons about what to test next, but a plain, testable **scope gate** authorizes
every action and a separate **verifier** judges the real result. The model can't grant
itself permission, and it can't be talked out of the rules by a prompt injection hidden in
an app — because the security decisions never read the model's output.

> ⚠️ Local, single-operator prototype. Only assess applications and backends you own or are
> explicitly authorized to test. A completed assessment does **not** mean an app is secure.

---

## What it does

```
APK upload
  → validate (real-zip, sha256, zip-bomb / path-traversal guards)
  → sandboxed static analysis (androguard; no code execution)       [isolated, no network]
  → attack-surface model (endpoints, keys, tables; all "unapproved")
  → bounded agent loop:
        observe → DECIDE (LLM) → validate → SCOPE GATE → execute → VERIFY → update
  → evidence-backed findings → downloadable report (JSON / HTML / PDF)
```

The agent reaches the backend only through **registered tools** with hard limits
(read-only, tiny row caps, data minimization). Supported checks today, against a Supabase
(PostgREST) backend:

- **Config + key classification** — a public `publishable`/anon key is labelled *not a
  secret*; real secrets are redacted.
- **Check B — anonymous access**: can a logged-out client read a table it shouldn't?
- **Check C — authenticated cross-tenant**: can a logged-in user read another tenant's rows?
- **Check D — admin RLS review**: with authorized admin access, is Row Level Security on?
- **Firebase — open-rules read**: is a Firebase Realtime Database node readable without auth?
- **Generic REST — unauthenticated read**: does an endpoint return data without auth? (reported
  as a *candidate* for human review — a 200 cannot prove the data should be private)

Backends without an installed module are mapped but honestly reported as **not assessed**.

## Architecture (trust zones)

Credentials and hostile files never share a zone.

```
 Zone 1: APK SANDBOX            Zone 2: ORCHESTRATOR            Zone 3: LLM GATEWAY
 sandbox-worker, sandbox-db     api, worker, main-db           llm-gateway
 - decompiles hostile APKs      - agent loop, scope gate,      - holds Claude credential
 - no internet, no creds          verifier, tools, findings    - prompt in, JSON out
 - own throwaway DB             - only service on both nets    - all its tools disabled
```

Details: [`docs/architecture.md`](docs/architecture.md). Every design choice, with the
alternatives rejected, is in [`DECISIONS.md`](DECISIONS.md) (15 ADRs).

## Tech stack

Python 3.12 · FastAPI · PostgreSQL · SQLAlchemy 2 + Alembic · Procrastinate (Postgres-backed
jobs) · Jinja + Tailwind-style CSS + SSE · Docker Compose. Static analysis: androguard.
LLM: the local Claude Code CLI behind a provider-independent gateway (swappable for an API
key or a local model). No heavyweight agent framework — the control loop is hand-written
and fully tested ([ADR-013](DECISIONS.md)).

## Quickstart

Requirements: Docker + Docker Compose. (A current Claude login is needed only for a *live*
AI-driven run; everything else works without it.)

```bash
cp .env.example .env
docker compose up -d          # api, worker, sandbox-worker, two Postgres, llm-gateway
# dashboard: http://127.0.0.1:8000   ·   health: http://127.0.0.1:8000/health
```

Upload an APK from the dashboard to see validation + static analysis (no AI required).

### See a full assessment

**Fastest — the offline recording (no AI, no lab, no network):**

```bash
docker compose exec worker python demo/load_recorded_demo.py
# open the printed /assessments/... URL  (clearly banners itself as RECORDED)
```

**Live, against the local lab:**

```bash
# 1. start the deliberately-misconfigured lab and pick a mode
cd lab && docker compose -f docker-compose.lab.yml up -d && ./mode.sh broken && cd ..
bash lab/connect-worker.sh                       # let the worker reach the lab target
python3 lab/build_sample_apk.py sample.apk       # a synthetic app pointing at the lab

# 2. for a REAL Claude-driven run, set credentials in .env (gateway zone only):
#    LLM_MODE=gateway
#    HOST_CLAUDE_DIR=/home/<you>/.claude     (or CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY)
docker compose up -d --force-recreate llm-gateway worker && bash lab/connect-worker.sh

# 3. upload sample.apk in the dashboard → Analyze → Run assessment → watch the live trace
```

Without credentials the agent runs in `stub`/`disabled` mode (static analysis + attack
surface only). The lab's `broken` mode has known planted bugs; `correct` is locked down.

## Evaluation

Measured against the known-answer lab (the honest way to judge a security tool):

```bash
python3 eval/run_eval.py
```

Latest: **precision 1.00 · recall 1.00 · false-positive rate 0.00** (2 TP, 6 TN, 0 FP, 0 FN).
This validates the control plane on a small known-answer set — not a claim of general
accuracy. See [`eval/README.md`](eval/README.md).

## Tests

```bash
docker compose run --rm --no-deps -e MAIN_DATABASE_URL=postgresql://u:p@db/x api \
  sh -c "pip install -q pytest && python -m pytest -q"
```

37 unit tests (validation, scope gate, verifier, ingest, LLM client, config) plus live
lab/agent integration checks in `backend/tests/live_*.py`.

## Security posture & honesty

- **Default-deny**: active testing is off until the scope authorizes it; discovered
  resources start *unapproved*. `authorized_hosts` matches exactly or by bounded suffix
  wildcard (`*.supabase.co`); a bare `*` is never honored.
- **SSRF / DNS-rebinding**: the network guard refuses private/loopback/reserved addresses
  unless an explicit lab target is authorized.
- **Data minimization**: read-only, tiny row caps, evidence limited to status + counts +
  column names (and tenant ids for isolation), never bulk data; secrets redacted.
- **Prompt-injection resistant**: app content and API responses are untrusted data; policy
  lives outside the model. (Demonstrated: a planted "ignore scope" instruction changes
  nothing.)
- **No invented results**: findings come only from verified evidence; no numeric security
  score; "no findings" is never "secure".

## Limitations (deliberate, for this prototype)

- Local single-operator; not multi-user or internet-exposed as-is.
- Android APKs only; backend modules cover Supabase/PostgREST, Firebase RTDB, and generic REST.
- JADX decompiles compiled DEX so real Kotlin/Java apps yield code-level findings
  (bounded by a timeout; large apps scan partial output). Active-check modules still
  cover Supabase only.
- The committed lab uses a **synthetic** schema; it is not any real client's data.

## Documentation

- [`docs/explain-simple.md`](docs/explain-simple.md) — the whole build in plain language.
- [`docs/architecture.md`](docs/architecture.md) — components, trust zones, data model.
- [`docs/roadmap.md`](docs/roadmap.md) — what's done, verified, and deferred.
- [`DECISIONS.md`](DECISIONS.md) — 15 architecture decision records.
- [`lab/README.md`](lab/README.md) · [`llm-gateway/README.md`](llm-gateway/README.md) ·
  [`eval/README.md`](eval/README.md) · [`backend/demo/README.md`](backend/demo/README.md)
