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

## Step 2 — Artifact intake + static analysis 🔨

Goal: upload a real APK and get honest, provenance-tagged analysis, with no LLM involved.

- ✅ Upload endpoint + page; stream to storage under an internal (content-addressed) key.
  Verified 2026-10-11.
- ✅ Artifact validation: streaming size limit, real-zip sniff (magic bytes), sha256,
  decompression ceiling (zip-bomb guard), path-traversal rejection, manifest-presence
  APK check; reject malformed; never trust extension. Rejected files are not stored.
  9 unit tests + end-to-end good/malicious/non-zip upload verified.
- ⬜ Sandbox handoff via outbox pattern (ADR-005); idempotent sandbox job.
- ⬜ `sandbox-worker`: androguard (manifest, permissions, cert, strings) + JADX
  (decompile for code/line evidence). Pinned versions; no network.
- ⬜ Analyzers: manifest facts, permissions, exported components, cleartext/debuggable,
  embedded URLs/keys/SDK refs, table/bucket references — each with file+location,
  detection method, confidence.
- ⬜ Secret classification + redaction (a public key is labelled as such, not a "secret").
- ⬜ Persist validated results into main-db; render an analysis page.

**Acceptance:** a valid sample APK uploads and analyzes; invalid artifacts are rejected;
limits enforced; every discovery carries provenance; works with no LLM key.

---

## Step 3 — Test lab + agent loop + Supabase checks ⬜

Goal: the core demo. The agent reasons over the attack surface and safely confirms a real
issue while refusing to over-claim.

### 3a. Test lab (ADR-009)
- ⬜ `lab/`: local Supabase (trimmed), schema-only load, synthetic multi-tenant seed data.
- ⬜ `as-is` and `broken` modes; one reset command; known-answer bugs in `broken`.
- ⬜ Small sample Android app whose embedded config points at the local lab; build script.

### 3b. Attack-surface model
- ⬜ Resource/technology/relationship entities with provenance and confidence.
- ⬜ Discovered resources start **unapproved**; distinguish discovered/inferred/verified.

### 3c. LLM gateway (ADR-002, ADR-003)
- ⬜ `llm-gateway` container: Claude CLI, tools hardcoded off, schema-validated JSON out,
  usage/cost logging, concurrency cap + timeout.
- ⬜ Provider-independent client in the worker; versioned prompts + Pydantic schemas.

### 3d. Agent loop
- ⬜ Observe → decide → validate → scope gate → execute → verify → update.
- ⬜ Deterministic **scope gate** (default deny) and **network scope** (SSRF/rebinding,
  lab exception). Leash enforcement (ADR-011), reading settings (ADR-012).
- ⬜ Registered tool interface; Supabase tools: classify key, config discovery, scoped
  anonymous read; deterministic **verifier** with the distinct outcome classes.
- ⬜ Finding lifecycle with evidence strength / impact / confidence; provenance to
  execution + evidence.
- ⬜ Persisted steps; resumable; cancellable; honest stop reasons.

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
