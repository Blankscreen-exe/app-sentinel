# Roadmap

Tracks what is built, in progress, planned, and deliberately deferred. Kept honest:
nothing is marked done until it has been run and verified.

Status key: ✅ done · 🔨 in progress · ⬜ planned · ⏸️ deferred

Last updated: 2026-10-10

---

## Scope for this prototype (ADR-006)

Build steps 1–4 below, each ending in a demoable, honest state. Everything under
"Deferred" waits until after step 4, when we decide how much polish to add.

---

## Phase 0 — Design ✅

- ✅ Inspect repo and the (AI-generated, non-authoritative) idea list in `proj_desc.md`.
- ✅ Decisions recorded as ADR-001..012 in `DECISIONS.md`.
- ✅ Spike: Claude Code CLI as a constrained structured-output LLM
  (`docs/spikes/001-claude-code-cli-as-llm.md`).
- ✅ `docs/architecture.md`.
- ✅ `docs/roadmap.md` (this file).
- ⬜ `docs/design-walkthrough.md` (interview narrative) — written alongside the build.

---

## Step 1 — Foundation ✅

Goal: the skeleton boots and is runnable before any feature exists.
Verified 2026-10-11 via `docker compose build && up` + curl + container checks.

- ✅ Repo layout: `backend/`, `sandbox/`, `llm-gateway/`, `docs/`. (`lab/`, `data/` arrive with the features that need them.)
- ✅ `docker-compose.yml`: api, worker, sandbox-worker, main-db, sandbox-db, llm-gateway,
  with the two-network split (ADR-005) and `127.0.0.1` port binds. Verified: sandbox has
  no internet egress and cannot reach main-db; reaches sandbox-db only.
- ✅ Python project (uv), ruff + mypy + pytest config.
- ✅ FastAPI app with a real `/health` (checks DB + queue; returns 503 when degraded —
  it correctly caught a broken queue during the build).
- ✅ SQLAlchemy models + first Alembic migration on a clean DB (project, artifact,
  assessment, setting).
- ✅ Procrastinate wired to main-db; trivial `ping` job enqueued via API and executed by
  the worker, trace id flowing through logs.
- ✅ Jinja base layout + one page served by the API.
- ✅ Structured JSON logging with a trace id.
- ✅ `.env.example`; config loader fails clearly (pydantic ValidationError) on missing OR
  empty required DSN. 3 unit tests pass.
- ✅ Local posture (ADR-007): Host-header allowlist and `X-App-Sentinel` header on
  state-changing requests, both verified (foreign host → 400, missing header → 403).

**Deferred within step 1 (honest note):** the Tailwind *standalone build pipeline*
(ADR-004b) is not yet wired; the foundation ships a small hand-authored
`static/app.css` placeholder so boot needs no build-time download. To be replaced by
compiled Tailwind output in a later step.

**Acceptance — met:** `docker compose up` starts all six services; migrations apply on a
clean DB; `/health` returns real status; the page renders; a queued job runs end to end;
missing/empty config gives a clear error.

---

## Step 2 — Artifact intake + static analysis ✅ (JADX deferred)

Goal: upload a real APK and get honest, provenance-tagged analysis, with no LLM involved.

- ✅ Upload endpoint + page; stream to storage under an internal (content-addressed) key.
  Verified 2026-10-11.
- ✅ Artifact validation: streaming size limit, real-zip sniff (magic bytes), sha256,
  decompression ceiling (zip-bomb guard), path-traversal rejection, manifest-presence
  APK check; reject malformed; never trust extension. Rejected files are not stored.
  9 unit tests + end-to-end good/malicious/non-zip upload verified.
- ✅ Sandbox handoff via outbox pattern (ADR-005); idempotent sandbox job (queueing lock)
  and idempotent re-analysis. Verified 2026-10-11 end to end across both databases.
- ✅ `sandbox-worker`: real Procrastinate worker on sandbox-db running androguard
  (manifest, permissions, exported components, flags). Pinned; isolated (confirmed it
  cannot resolve/reach main-db). JADX decompilation deferred to slice 2.3.
- ✅ Analyzers: manifest facts (androguard) + content scan of text resources/assets for
  Supabase URLs, client keys, SDK markers, endpoints, cleartext HTTP, and table/bucket
  refs — each with entry+line provenance. Verified end to end 2026-10-11.
- ⏸️ JADX decompilation (decompiled-Java scanning) deferred: needs a Java runtime in the
  sandbox image and a real compiled APK to verify honestly; will be added and verified
  against the lab app in step 3. The content scanner already covers Capacitor/RN-style
  apps where config lives in assets/JS.
- ✅ Secret classification + redaction, done inside the sandbox so secrets never leave it:
  `sb_publishable_`/anon → labelled public client key (kept, redacted); `sb_secret_`/
  service-role → sensitive, redacted to prefix+hash. Verified no raw secret is stored.
- ✅ Persist validated results into main-db (untrusted payload validated via Pydantic);
  analysis shown on the artifact page with provenance. Dedicated results page = slice 2.4.

**Acceptance (slice 2.2):** a real sample APK uploads, hands off to the isolated sandbox,
androguard extracts manifest facts, and provenance-tagged discoveries are validated back
into main-db; re-analysis does not duplicate; sandbox cannot reach main-db; works with no
LLM key. 12 unit tests pass (config, validation, ingest).

---

## Step 3 — Test lab + agent loop + Supabase checks ⬜

Goal: the core demo. The agent reasons over the attack surface and safely confirms a real
issue while refusing to over-claim.

### 3a. Test lab (ADR-009, ADR-014) ✅ (slice 3.1, verified 2026-10-11)
- ✅ `lab/`: minimal Supabase data-API surface (Postgres + PostgREST), SYNTHETIC
  multi-tenant schema + seed (publishable; not the client schema, per ADR-010).
- ✅ `broken` / `correct` modes via `mode.sh`; re-applies base schema + RLS overlay and
  reloads PostgREST. Known-answer bugs: RLS-off table, permissive anon policy, bypass
  view, plus a locked true-negative table. All four verified by anonymous curl.
- ✅ Sample APK (`build_sample_apk.py`) embedding the lab URL + anon JWT + table refs;
  verified the scanner extracts them.

### 3b. Attack-surface model + scope gate ✅ (slice 3.2, verified 2026-10-11)
- ✅ `AttackSurfaceResource` (migration 0003) built from discoveries with provenance;
  every resource starts **unapproved**, state `discovered`. Build is idempotent.
- ✅ `ScopeConfig` (authoritative, operator-set, default-deny for active testing).
- ✅ Deterministic **scope gate** + **network guard** (SSRF/DNS-rebinding: refuses
  private/loopback/reserved IPs unless an authorized lab target). 12 unit tests cover
  default-deny, host/resource authorization, lab exception, scheme, budget, method,
  approval. No LLM involved — the control plane is testable on its own.

### 3c. LLM gateway (ADR-002/003/015) ✅ (slice 3.4, verified 2026-10-11)
- ✅ `llm-gateway` container: Claude CLI, tool-disabling flags hardcoded, empty workdir,
  schema-validated JSON out, usage/cost logging, concurrency cap + timeout, clean error
  envelope. Verified mechanically (health, command build, error handling).
- ✅ Provider-independent client in the backend (`GatewayLLMClient` + `StubLLMClient`),
  versioned planner prompt + Pydantic `AgentDecision` schema (action enum constrained to
  registered tools + 'stop'). 3 LLM unit tests (37 total).
- ⏳ Real in-container Claude decisions require a one-time credential (`claude setup-token`
  → `.env`, or `ANTHROPIC_API_KEY`); headless Claude itself was validated in Spike 001.
  Default `LLM_MODE=stub/disabled` keeps everything runnable without credentials.

### 3c-tools. Registered tools + Supabase checks + verifier ✅ (slice 3.3, verified 2026-10-11)
- ✅ Tool registry + normalized `ToolResult` (no raw terminal output).
- ✅ Scope-safe HTTP (no auto-redirects; every hop re-validated by the gate; capped body).
- ✅ Supabase tools: `classify_client_key` (offline), `test_scoped_anonymous_read`
  (read-only, anonymous, data-minimized — row cap 2, columns-only evidence).
- ✅ Deterministic **verifier**: unauthorized_access / access_denied / empty /
  network_error / tool_failure / inconclusive. LLM assertion is never the proof.
- ✅ Live lab integration check (both modes): broken → trips+invoices = unauthorized_access
  findings, profiles safe; correct → nothing; gate blocks unauthorized host. 34 unit tests.

### 3d. Agent loop ✅ (slice 3.5, verified 2026-10-11)
- ✅ Bounded loop: observe → decide (LLM) → validate → scope gate → execute → verify →
  update. LLM proposes; code decides and proves.
- ✅ `ToolExecution` (every step, including gate-denied/invalid/failed — auditable) and
  `Finding` persistence with evidence + provenance (migration 0004).
- ✅ Leash: step cap + active-request cap; honest stop reasons (planner_stop /
  budget_exhausted / step_cap / llm_error).
- ✅ `run_assessment` task + API (`/artifacts/{id}/assess`, `/assessments/{id}`) + page.
- ✅ Scanner refined: public keys (publishable / anon JWT) kept (needed to test), secrets
  (sb_secret_ / service_role JWT) redacted.
- ✅ **Live end-to-end agent check** (scripted stub planner + real tools/lab):
  broken → confirmed findings on trips+invoices, profiles NOT flagged; correct → zero
  findings; out-of-scope target → gate-denied, zero findings. 37 unit tests.

**Step 3 acceptance — met:** public key alone ⇒ no confirmed vuln; out-of-scope target
blocked; unregistered tool refused (loop validation); tool failure ⇒ not a finding;
broken-mode misconfig ⇒ confirmed evidence-backed finding (minimal data); correct ⇒ none;
budget/step caps stop cleanly; works without an LLM key (surface-only).

**Acceptance:** public key alone ⇒ no confirmed vuln; out-of-scope target blocked;
unregistered tool refused; injected instruction ignored by policy; tool failure ⇒
inconclusive, not vuln; a `broken`-mode misconfig ⇒ a confirmed, evidence-backed finding
with minimal data; `as-is` mode ⇒ no false finding; budget exhaustion ⇒ clean stop.

---

## Step 4 — Agent trace view ⬜

Goal: the app shows its reasoning — the most valuable thing to demo.

- ⬜ Per-step trace: what the agent knew, its decision + rationale, the scope-gate verdict,
  the raw tool result, the verifier's conclusion.
- ⬜ Live updates via SSE + htmx; safe reconnect (fetch current state on reconnect).
- ⬜ Clear visual separation of scope denials, tool failures, and findings.
- ⬜ Live prompt-injection demo: plant an instruction in the sample APK, show the gate
  block the action.

**Acceptance:** trace reflects persisted backend state; the injection demo visibly fails
to change behavior; a finding links to its evidence and execution.

---

## Deferred until after step 4 ⏸️

- ⏸️ Polished reports (HTML/PDF export), downloadable JSON.
- ⏸️ Full dashboard polish and filtering.
- ⏸️ Evaluation metrics (precision/recall/false-positive rate) against known-answer lab.
- ⏸️ Authenticated-user and admin-metadata Supabase checks (Checks C & D).
- ⏸️ Recorded backup run for offline demo.
- ⏸️ API-key LLM adapter / local-model adapter; dollar budget cap.
- ⏸️ iOS/IPA support.
- ⏸️ Multi-tenancy and authentication.
- ⏸️ apktool; embeddings-based code retrieval; object storage (S3/MinIO) backend.

---

## Known risks (carried from design)

- Client-app migrations may not apply cleanly to a fresh local Supabase (Lovable projects
  can assume cloud-only setup) — test early, fall back to a table subset if needed.
- RAM pressure from Supabase + stack + JADX — trim Supabase; higher-spec machine available.
- Public use of the client schema needs written sign-off (ADR-010).
- Claude CLI behavior on schema-violating output / timeouts / auth expiry — harden in the
  gateway during step 3.
