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

### 4b. Frontend: React + Vite + TypeScript (deviation from spec)

- The spec suggests Next.js. For a local-only dashboard (ADR-001) that talks only to
  FastAPI, Next.js adds a second server for SSR/SEO features we don't need.
- A single-page app built with Vite is simpler to run and reason about.

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

### Consequences

- Public-facing lab assets will be built from a synthetic schema if client sign-off is
  not obtained, kept separate from the private client work.
