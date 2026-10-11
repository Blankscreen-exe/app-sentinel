# Architecture Decision Log

Each entry records the options considered, the choice made, and why.
Status values: `accepted`, `superseded`, `proposed`.

---

## ADR-001: Deployment model

- **Date:** 2026-10-09
- **Status:** accepted

### Context

The platform processes untrusted APKs and, when authorized, sends active requests
to backend services. Where it runs determines the security posture, legal exposure,
cost, and how much multi-tenant machinery must exist before the core idea works.

### Options considered

| Option | Summary | Main drawback |
|---|---|---|
| A. Local only | Docker Compose on the operator's machine | Not publicly reachable for demos |
| B. Local-first, deployable single-operator | Same stack, deployable to a VPS behind auth, multi-tenant-ready schema | Slightly more config/auth work |
| C. Public hosted SaaS | Open signup, anyone can scan | Operator's infrastructure would send requests to targets chosen by strangers; ownership verification is unsolved; untrusted APKs on shared infra; open-ended LLM cost |
| D. Hosted dashboard + local runner | Cloud UI, scans run on user machines | Too much distributed plumbing for v1 |

### Decision

**Option A: local only.** (Revised 2026-10-09; initially "B, operated as A first".)

- Runs only on the operator's machine via Docker Compose. No server deployment is planned.
- No public sign-up, no public scanning, no hosted demo.

### Consequences

- Single trusted operator. We do not claim multi-user security.
- Ownership columns (`owner_id`) and API ownership checks are still kept: they are cheap,
  and they keep the data model honest. Full multi-tenancy is out of scope.
- The public demonstration is a reproducible local test lab (sample app + deliberately
  insecure and correctly configured local backends), not a hosted scanner.
- Local lab backends live on loopback/private addresses, which the network scope policy
  blocks by default. An explicit, per-assessment "authorized lab target" exception is
  required (to be detailed in the security model).
- Using the operator's Claude subscription (ADR-002) stays within personal local use.

---

## ADR-002: LLM provider strategy

- **Date:** 2026-10-09
- **Status:** accepted (connection mechanism: see ADR-003)

### Context

The spec requires a provider-independent LLM interface with structured output,
timeouts, retries, token/cost tracking and prompt versioning. Deterministic static
analysis must work with no LLM configured.

### Options considered

- Cloud API first (Anthropic/OpenAI SDK with API key)
- Local open model first (Ollama)
- Both from day one
- Cloud first, local later
- **Local Claude Code CLI in headless mode**, using the operator's existing login

### Decision

**First adapter: local Claude Code CLI** (`claude -p` with `--json-schema`),
validated by [Spike 001](docs/spikes/001-claude-code-cli-as-llm.md).

### Consequences

- The adapter must always pass `--tools ""`, `--strict-mcp-config`,
  `--setting-sources ""`, `--no-session-persistence` and run in an empty temp dir.
  These are hardcoded, not configurable.
- Latency is ~15–20 s per call; LLM calls must be few and targeted.
- Subscription login is for the operator's personal local use (ADR-001: local only).
  If others ever run it, they use their own login or an API-key adapter. Verify
  Anthropic's current terms before publishing.
- Model output never authorizes anything; scope enforcement stays deterministic.

---

## ADR-003: Connecting the Claude Code CLI to the Docker stack

- **Date:** 2026-10-09
- **Status:** accepted

### Context

ADR-001 (local only, Docker Compose) and ADR-002 (Claude Code CLI as the LLM) leave a
gap: the CLI login lives on the host, the worker runs in a container, and the
containers that process hostile APKs must never hold credentials.

### Trust zones

1. **APK sandbox**: unzip/decompile/parse hostile files. No network, no credentials.
2. **Orchestrator**: API, worker, database. Runs the agent loop, scope gate, tool registry.
3. **LLM gateway** ("Claude box"): holds the Claude credential; text in, JSON out.

Rule: credentials and hostile files never share a zone.

### Options considered

1. Gateway container with a long-lived token from `claude setup-token`
2. Host-side bridge over a Unix socket mounted into the worker
3. Host-side bridge over HTTP via `host.docker.internal`
4. Host-side runner pulling LLM jobs from the queue
- Rejected: mounting `~/.claude` or the Docker socket into containers; letting
  Claude Code's own tools drive the analysis.

### Decision

**Option 1: an `llm-gateway` container in Docker Compose.**

- The token from `claude setup-token` is provided only to this container (Docker secret).
- Reachable only by the worker over an internal Compose network.
- Accepts only `{prompt_id, prompt_version, input_data, json_schema}`; builds the
  `claude` command itself with tool-disabling flags hardcoded; sends the prompt via stdin.
- Concurrency cap (1-2) and hard timeout per call.
- Validates output against the schema; malformed output is returned as an error, never repaired.
- Logs usage, cost and duration; never prompt contents.

### Consequences

- One command (`docker compose up`) starts everything.
- The token is long-lived; if leaked it must be revoked manually in Claude account settings.
- The CLI version in the gateway image must be pinned and updated deliberately.
- Switching to an API key or a local model replaces the gateway's backend only.

---

## ADR-004: Core technology stack

- **Date:** 2026-10-09
- **Status:** accepted

### Adopted from the spec without change

Python 3.12, FastAPI, Pydantic, PostgreSQL, SQLAlchemy 2.x, Alembic, Docker Compose.
Python tooling: uv, ruff, pytest, mypy.

### 4a. Background jobs: Procrastinate (Postgres-backed)

- Considered: Celery + Redis, Dramatiq + Redis, Procrastinate.
- Chosen because jobs live in PostgreSQL: a job can be enqueued in the **same
  transaction** that updates assessment state, which removes the "state says running
  but no job exists" class of crash bugs. It also removes Redis as a required service.
- Redis is not part of the stack until a concrete need appears.
- Per-step timeouts are enforced by our own code (subprocess/HTTP timeouts), not
  assumed from the queue library.

### 4b. Frontend: server-rendered Jinja + compiled Tailwind (deviation from spec)

- Superseded the earlier React+Vite choice (2026-10-10).
- The spec suggests Next.js/React. For a local-only single-operator dashboard (ADR-001),
  FastAPI renders Jinja templates directly: no separate frontend container, no Node
  build step, no typed-API-client layer. Fewer moving parts to run and explain.
- Tailwind is compiled once to a static CSS file (via the standalone CLI, no Node runtime
  dependency at serve time).
- The one interactive requirement, the live agent trace, uses server-sent events plus
  htmx (small, no build step) to append trace steps as they arrive.
- Accepted loss: no React/TypeScript SPA or generated typed client. Acceptable for a
  local prototype; revisit if the UI grows complex.

### 4c. Artifact and evidence storage: bind-mounted host directory

- Stored in a host directory (e.g. `./data/`) bind-mounted into the containers that
  need it, so files are directly reachable on the host.
- Accessed only through a storage interface (`put`, `get`, `delete`, `exists` by
  internal key) so an S3/MinIO backend can be added later without touching callers.
- Files are stored under internal keys, never their original filenames.
- `./data/` is git-ignored. Uploaded APKs are hostile input: never open or run them on
  the host outside the sandbox.
- Containers run as non-root; host UID/GID are passed in so bind-mount permissions work on Linux.

### 4d. APK sandbox: dedicated sandbox worker

- A separate worker process/container consumes only artifact-analysis jobs.
- It sits on an internal Compose network that reaches PostgreSQL (job queue) only;
  no internet egress, no LLM credentials.
- It has access to the artifact storage it needs.
- Rejected: having the main worker spawn per-job containers, which requires the
  Docker socket (effectively host root).

---

## ADR-005: Separate database for the APK sandbox

- **Date:** 2026-10-10
- **Status:** accepted
- **Refines:** ADR-004d

### Context

ADR-004d gave the sandbox worker access to PostgreSQL for its job queue. A sandbox
escape (e.g. a parser exploit in JADX) would then have a path to all platform data.

### Options considered

- Same database, restricted Postgres role (queue tables + an inbox table only).
  Protection depends on Postgres privilege enforcement.
- **Separate Postgres container (`sandbox-db`)** on the sandbox's internal network.
  The main database is not network-reachable from the sandbox at all.
- File-based handoff through the shared volume (no database for the sandbox).

### Decision

**A separate `sandbox-db` container.** (Proposed by the operator.)

- Networks: `sandbox-net` (internal, no egress) contains only `sandbox-worker` and
  `sandbox-db`. The main `worker` is the only service attached to both networks.
- `sandbox-db` holds only the sandbox job queue and raw analysis output. Nothing in
  it is trusted or important.

### Consequences

- ADR-004a's single-transaction enqueue no longer spans the boundary. Handoff uses
  an outbox pattern:
  1. In `main-db`, one transaction records "analysis requested" and enqueues a
     main-db handoff job.
  2. The handoff job enqueues the sandbox job in `sandbox-db`, keyed by artifact ID,
     so re-running after a crash creates no duplicate (idempotent).
  3. The worker reads raw results from `sandbox-db`, validates them as untrusted
     input, and only then writes them to `main-db`.
- One extra container to run; negligible for local use.
- The sandbox's storage access is limited to what it needs (read
  artifacts, write analysis output).

---

## ADR-006: Prototype scope

- **Date:** 2026-10-10
- **Status:** accepted

### Context

The prototype will be shown and explained in a follow-up interview, and later posted
publicly. Explainability and a reliable demo matter more than breadth.

### Decision

Build, in order, stopping at step 4 before deciding on polish:

1. Foundation, APK upload and deterministic static analysis (works without an LLM).
2. Local test lab: sample Android app, a deliberately misconfigured Supabase backend
   and a correctly configured one, with synthetic data only.
3. Bounded agent loop with Claude, deterministic scope gate and independent verifier,
   with Supabase anonymous-access checks.
4. Agent trace view: for each step, what the agent knew, what it decided and why,
   the scope gate verdict, the raw tool result and the verifier's conclusion.

Deferred until after step 4: polished reports (HTML/PDF), full dashboard, evaluation
metrics, authenticated-user and admin-metadata Supabase checks, iOS, recorded backup run.

### Consequences

- Each step ends in a demoable, honest state.
- `docs/design-walkthrough.md` is written alongside the build as the interview narrative.

---

## ADR-007: No user authentication (local single operator)

- **Date:** 2026-10-10
- **Status:** accepted

### Options considered

- No login; rely on binding to localhost.
- One operator account from `.env` with a session cookie.
- Full user system with sign-up and roles.

### Decision

**No login.** The platform runs only on the operator's machine (ADR-001).

### Consequences

- Services publish ports on `127.0.0.1` only, never `0.0.0.0`.
- Binding to localhost is not enough: any website open in the operator's browser can
  send requests to localhost. Required mitigations:
  - **Host header allowlist** (`localhost`, `127.0.0.1`) to block DNS rebinding.
  - **Strict CORS**: only the frontend origin is allowed.
  - **State-changing requests require JSON plus a custom header** (e.g.
    `X-App-Sentinel: 1`), which a cross-site form or simple request cannot send,
    blocking CSRF.
- No ownership model in the schema. Adding users later means adding an owner column
  and checks; this is an accepted trade-off.
- The prototype must not be described as multi-user or deployable as-is.

---

## ADR-008: APK static analysis tools

- **Date:** 2026-10-10
- **Status:** accepted

### Options considered

- androguard (Python): manifest, permissions, certificates, resources, DEX strings.
- JADX (Java): decompiles DEX to readable Java for code search with file/line evidence.
- apktool (Java): resource decoding; largely overlaps androguard for our needs.

### Decision

**androguard + JADX**, both run only inside the sandbox (ADR-004d, ADR-005).
apktool is deferred.

### Consequences

- The sandbox image needs a Java runtime; versions of JADX and androguard are pinned.
- Evidence can point to decompiled file and line, which is central to the demo.
- JADX output for obfuscated apps may have unreadable names; findings must still
  cite the location honestly.

---

## ADR-009: Test lab design

- **Date:** 2026-10-10
- **Status:** accepted

### Context

The demo needs a realistic backend and a mobile artifact whose embedded config points
at that backend (so active tests stay in-scope and on infrastructure we control).

### Decisions

**Backend:** one local Supabase (containers), loaded with the *schema only* of a
realistic app. Never production/client data. Seeded with synthetic data for a few
fake tenants so cross-tenant access can be tested honestly. Two modes:
- `as-is`: the schema unchanged.
- `broken`: the same schema plus a lab-only migration planting known-answer bugs
  (RLS disabled on a table; a permissive `using (true)` policy; an RLS-bypassing view).
Switched with a single reset command; only one Supabase runs at a time.

**Target app:** a small, purpose-built sample Android app we control, whose embedded
configuration points at the local Supabase (URL + publishable key + a few
`from("table")` calls + an exported activity). It must *contain* realistic artifacts to
discover, not be a functional product. A random ready-made APK is rejected: its backend
is third-party and out of scope to test.

**Portability:** entire lab is Docker Compose + `.env`; runs on a higher-spec machine
unchanged. Trim Supabase (no Studio/realtime/email) to fit ~4 GB free RAM.

### Consequences

- The lab does not depend on any real app's frontend.
- Known-answer bugs give measurable precision/recall later.

---

## ADR-010: Separation of client-audit use from public portfolio use

- **Date:** 2026-10-10
- **Status:** accepted

### Context

The realistic schema comes from a client-provided app under an audit engagement. The
project is also intended to be published and to tag the company from the interview.
Auditing the app and publishing a portfolio tool are distinct uses with different
permission boundaries.

### Decision

- Developing/testing the tool privately against the client app locally: permitted as
  part of the audit.
- Any public artifact (post, repo, screenshots, demo recording) must NOT expose the
  client app's schema, table names, data, or findings without the client's written
  authorization.
- The published demo uses a synthetic app/schema, or a client-approved redacted subset.
- Confirm the engagement's confidentiality and data-handling terms before publishing.

### Update (2026-10-10): client authorization

The client verbally authorized use of the app, stating it was a Lovable experiment he
alone used for testing, with no real data. This is sufficient for private development.
Caveat: the authorization is verbal; obtain a one-line written confirmation before any
public use of the client schema/details.

### Consequences

- Private development against the client app is authorized.
- Before publishing anything derived from the client app, secure written sign-off;
  otherwise publish with a synthetic schema.

---

## ADR-011: Agent budget and stop conditions

- **Date:** 2026-10-10
- **Status:** accepted

### Context

The agent chooses its own next step, so it needs hard bounds. On a Claude subscription
(ADR-002) there is no per-call dollar charge, so "budget" here is a leash and a safety
limit, not a cost control. It enforces termination, respects subscription rate limits,
and honors data minimization.

### Decision

Per assessment, enforced deterministically by our code (not the LLM). Values are
runtime-configurable (see ADR-012); `.env` only seeds the initial defaults:

- **Max agent steps:** 15 (guarantees termination; bounds subscription usage).
- **Max active requests to the target:** 30 (data-minimization ceiling; a safety limit
  independent of cost).
- **Per-step timeouts:** 60s for an LLM decision, 30s for a tool call.
- **Dollar cap:** omitted while on subscription; token usage is still logged for
  observability. Reinstated if an API-key adapter is used.

### Consequences

- Every assessment terminates by step cap even if the LLM keeps proposing actions.
- Exceeding any limit is a clean stop with a recorded reason, never a crash or a
  silently-"completed" assessment.
- Numbers are config, raised freely on a higher-spec machine.

---

## ADR-012: Runtime settings table (UI-editable)

- **Date:** 2026-10-10
- **Status:** accepted

### Context

The agent leash (ADR-011) and similar operational tunables should be changeable from
the UI without editing `.env` or restarting containers.

### Decision

A `settings` key-value table in the main database, editable from a settings page.

**Precedence (lowest to highest):**
1. `.env` seeds initial defaults on first boot.
2. `settings` table = global defaults, UI-editable, override `.env`.
3. A per-assessment `scope_configuration` may override the global default for that run.

**Rules:**
- Typed, validated writes (e.g. positive integers, sane min/max ceilings). The UI
  cannot set nonsensical values (0, absurdly large).
- Scope: operational *limits* only (step cap, request cap, timeouts). NOT authorization.
  What a given assessment is allowed to touch stays in its `scope_configuration` and is
  enforced by the scope gate. A global setting must never be able to widen scope.
- Each change is recorded (who/when/old→new) for the audit trail.

### Consequences

- Live-tunable leash; good for demos and for the higher-spec machine.
- Clear split between tunable limits (settings) and authorization (scope config).

---

## ADR-013: No agent framework (LangChain / LlamaIndex / CrewAI)

- **Date:** 2026-10-11
- **Status:** accepted

### Context

Judged as a production security tool (not against the project spec, which was
AI-generated and not authoritative). This system sends real traffic at real backends
when authorized and produces claims people act on. The security-critical path — deciding
whether an action is in scope, and classifying the real result — must be deterministic,
minimal, auditable, and testable in isolation.

### Options considered

- **LangChain** for the agent loop / tool orchestration.
- **CrewAI** for multi-agent orchestration.
- **LlamaIndex** for retrieval.
- **Hand-written orchestration**, model reached via our own gateway.

### Decision

**Hand-write the orchestration loop. Adopt no agent framework.**

Reasoning (production terms, not spec compliance):
- **Control must stay outside the model and the framework.** LangChain's agent executor
  owns the loop; we'd fight it to insert our scope gate and verifier between proposal and
  action. The gate/verifier are the security-critical path and must be plain, auditable code.
- **Trusted-core minimalism.** A large, fast-moving dependency in the hot path is attack
  surface, supply-chain risk, and audit burden. Our loop is small; a framework would own
  the exact part we most need to own.
- **CrewAI** adds nondeterminism and failure modes (multiple autonomous agents) for no
  benefit; one bounded actor is safer and cheaper to audit.
- **Structured output** — the main thing LangChain would provide — we already get from the
  model via `--json-schema` (Spike 001).

### Consequences

- The agent loop is a hand-written Python state machine; the LLM is one schema-validated
  request to the gateway (ADR-002/003); tools use our own small registry.
- **LlamaIndex remains a candidate later, scoped to code retrieval only**, if plain text
  search over decompiled sources stops scaling. It would be a component in the retrieval
  step, never an orchestration backbone.

---

## ADR-014: Lab backend — minimal PostgREST stack first

- **Date:** 2026-10-11
- **Status:** accepted
- **Refines:** ADR-009

### Context

ADR-009 said "real local Supabase." Implementing step 3, the only attack surface the
agent actually exercises for the MVP is the anonymous/authenticated REST data API plus
RLS. The full Supabase CLI stack (~10 containers) is heavy on the 13 GB laptop.

### Decision

Start the lab with a **minimal stack: Postgres + PostgREST + GoTrue** (anon/authenticated
roles, JWT keys, RLS) — this is exactly what Supabase's data API is underneath, so
anonymous-read and RLS checks are authentic. Prototype slice 3.1 on it, then **revisit
before the demo** whether to upgrade to the full Supabase CLI stack for authenticity.

### Consequences

- Lighter, faster lab; runs comfortably during a live demo.
- Caveat to disclose: "the lab runs Supabase's underlying data API (PostgREST+GoTrue+
  Postgres), not the full product." Upgrade path to the full stack kept open.
- The agent's Supabase tools target the REST API + key formats, which are identical in
  both, so the control plane does not change if we upgrade later.

---

## ADR-015: Gateway credentials — runtime injection, never baked into the image

- **Date:** 2026-10-11
- **Status:** accepted
- **Refines:** ADR-003

### Context

The gateway (Zone 3) is the only component that may hold LLM credentials. How the
credential reaches it must not expose it in the image, git, logs, or other zones.

### Decision

The credential is **injected at runtime into the gateway container only**, never built
into the image. Supported forms, cheapest to strongest:

1. **Local Claude CLI (default for this prototype):** mount the operator's `~/.claude`
   **read-only into the gateway only** (not the worker/sandbox). Consistent with the
   trust-zone rule — the gateway is the designated credential zone.
2. **API key via git-ignored `.env`** passed only to the gateway service (fine for a
   single-operator local tool; visible to `docker inspect`, so not for shared hosts).
3. **Docker secret** (`/run/secrets/...`) — not in image, env listing, or `docker inspect`.
4. **Secrets manager** (Vault / cloud KMS) — production; fetched at startup via a
   short-lived identity.

### Invariants (all methods)

- Never in the image, git, or logs; never sent inside an LLM prompt; never in any zone
  other than the gateway.
- Swapping Claude-CLI ↔ API key ↔ local model changes only the gateway's backend; no
  other component sees the credential.
