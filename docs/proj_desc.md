# Project Specification: Agentic Mobile Application Security Assessment Platform

## 1. Your Role

Act as a principal security engineer, senior AI engineer, application security researcher, and staff-level full-stack engineer.

Your task is to design and implement a production-oriented, agentic mobile application security assessment platform.

Do not build a generic chatbot that calls security tools. Build a structured system capable of inspecting mobile applications, discovering their backend dependencies, developing evidence-based security hypotheses, executing authorized security checks, validating findings, and producing reproducible security reports.

You are responsible for the architecture, implementation, testing, documentation, and engineering decisions required to turn this into a functional product.

Prioritize correctness, security, maintainability, explainability, and reproducibility over flashy UI, unnecessary abstractions, or premature multi-agent architecture.

Do not pretend a capability exists when it has not been implemented. Do not report simulated results as real findings.

---

# 2. Product Vision

Build an agentic security assessment platform that helps developers, security engineers, and organizations understand the security posture of their mobile applications and the backend systems those applications interact with.

The initial use case is:

A user uploads an Android APK that they own or are explicitly authorized to assess. The platform analyzes the application, identifies technologies and backend services, constructs an attack-surface model, identifies potential security weaknesses, validates appropriate hypotheses using controlled security checks, and produces an evidence-backed assessment report.

For example, an Android application may use Supabase as its backend.

Static analysis could discover:

* A Supabase project URL.
* A client-side Supabase key.
* References to database tables or application entities.
* Authentication and authorization code.
* API endpoints and storage bucket references.
* Application workflows that suggest access to sensitive data.

The agent should understand that a client-side Supabase publishable key is not inherently a vulnerability.

It should investigate whether the backend's actual authorization controls permit access that should be restricted.

If an authorized, non-destructive test establishes that sensitive records can be read without authentication, the system should identify the issue, validate the evidence, explain its impact, and recommend remediation.

This is the central product principle:

**Discover through analysis, investigate through reasoning, validate through controlled experiments, and report only what the evidence supports.**

The long-term objective is to support multiple mobile platforms, backend providers, vulnerability classes, and testing methodologies through a modular architecture.

Do not attempt to implement every possible capability in the initial release.

---

# 3. Product Goals

The platform must eventually be capable of:

1. Accepting mobile application artifacts and assessment configuration.
2. Performing static application analysis.
3. Identifying technologies, embedded configuration, endpoints, SDKs, and likely backend services.
4. Building a structured model of the application's attack surface.
5. Identifying potential security weaknesses and uncertainties.
6. Planning assessment steps based on available evidence.
7. Executing approved security checks through deterministic tools.
8. Verifying observations independently of the LLM's assertions.
9. Managing test execution state, evidence, failures, and retries.
10. Producing structured findings with reproducible evidence.
11. Explaining why a finding matters and how to remediate it.
12. Tracking assessment coverage and confidence.
13. Supporting human review and approval for sensitive operations.
14. Providing an extensible framework for additional security checks and backend providers.

## Non-goals for the initial release

Do not initially attempt to:

* Automatically exploit arbitrary vulnerabilities.
* Support every Android and iOS application format.
* Reverse engineer every obfuscation technique.
* Automatically bypass authentication, MFA, anti-tamper controls, or security boundaries.
* Perform unrestricted internet-wide reconnaissance.
* Extract entire production databases to demonstrate exposure.
* Modify production security policies automatically.
* Run destructive tests against production systems.
* Claim comprehensive security merely because an assessment completed.
* Replace experienced security researchers or penetration testers.

Build a reliable foundation first.

---

# 4. Initial Scope and Assumptions

## 4.1 Initial supported platform

Start with Android APK files.

The architecture must allow iOS IPA support later without requiring a rewrite of the entire platform.

For the MVP, an APK may be:

* A debug build.
* A release build.
* A build with obfuscated code.
* An application with embedded configuration and SDK references.
* An application using a third-party backend.

Static analysis must work without requiring the application to run.

Dynamic analysis is a separate capability and must not be falsely implied when only static analysis has been performed.

## 4.2 Initial backend provider

Implement Supabase as the first specialized backend integration.

Potential checks include:

* Identification of Supabase project configuration.
* Classification of client-side keys.
* Discovery of likely exposed data resources.
* Authentication-state-aware access-control checks.
* Safe evaluation of table and view accessibility.
* Review of applicable PostgreSQL grants and Row Level Security configuration when authorized administrative metadata is available.
* Review of relevant policies and exposed functions when the assessment has sufficient authorized access.
* Identification of storage exposure where supported.
* Evidence collection and remediation guidance.

The system must distinguish between what can be inferred from the APK and what requires backend access or runtime testing.

A missing RLS policy in the source code or a suspected table name is not sufficient evidence that a production vulnerability exists.

## 4.3 Explicit authorization model

The platform must be designed for applications and backend environments the user owns or has explicit authorization to assess.

Every assessment must have a defined scope.

At minimum, scope configuration should support:

* Assessment owner.
* Application artifact.
* Authorized target domains and project identifiers.
* Permitted testing methods.
* Environment classification: local, staging, or production.
* Authentication configuration.
* Time and request budgets.
* Prohibited operations.
* Whether active network validation is permitted.
* Approval requirements for sensitive actions.

An uploaded APK does not automatically authorize testing every backend or domain referenced within it.

Discovered external services must remain unapproved until explicitly included in the assessment scope.

---

# 5. Preferred Technology Stack

Use the following stack unless repository constraints or a well-supported engineering reason justify a change.

Explain any major deviation before implementing it.

## Backend

* Python 3.12 or a compatible currently supported version.
* FastAPI.
* Pydantic for schemas and validation.
* SQLAlchemy 2.x.
* Alembic for database migrations.
* PostgreSQL for persistent application data.
* Redis where useful for caching, coordination, and transient execution state.
* A background task queue or worker system for long-running assessments.

Choose a task execution solution that supports retries, cancellation, timeouts, and persistent task state.

Do not introduce multiple orchestration frameworks without a clear need.

## Frontend

* React.
* TypeScript.
* Next.js, unless the existing repository already establishes a different frontend architecture.
* A clean, responsive dashboard suitable for desktop-first security workflows.
* A typed API client generated from or aligned with the backend schemas.

The UI must communicate real assessment states, findings, progress, and errors.

Do not hardcode mock findings into the production assessment interface.

## AI integration

Create a provider-independent LLM interface supporting:

* Structured output.
* Tool calling.
* Configurable models.
* Timeouts.
* Retry limits.
* Token and cost tracking.
* Prompt versioning.
* Error handling.

The initial provider can be configured through environment variables.

Do not couple the core reasoning engine to a single LLM vendor.

The application must remain usable for deterministic static analysis when no LLM API key is configured.

## Static analysis tools

Evaluate and integrate appropriate tools such as:

* JADX for Android DEX decompilation.
* apktool for Android resource and manifest analysis.
* Python libraries for ZIP inspection and artifact metadata.
* Semgrep or equivalent rule-based scanning where appropriate.
* MobSF as an optional integration if its deployment and interface fit the architecture.

Do not shell out to tools using unsanitized user-controlled strings.

Use pinned or controlled tool versions and document installation requirements.

## Runtime and deployment

* Docker and Docker Compose for local development.
* Separate API, worker, database, and frontend services where appropriate.
* Structured JSON logs.
* Health checks.
* Database migrations.
* Environment-based configuration.
* Reproducible development setup.
* Optional object storage for artifacts and evidence.

Do not require Kubernetes for the MVP.

---

# 6. High-Level Architecture

Use a modular architecture with clear boundaries.

The main components should be:

1. Web dashboard.
2. API service.
3. Assessment orchestrator.
4. Static analysis subsystem.
5. Technology and backend detection subsystem.
6. Application knowledge model.
7. Agent reasoning and planning engine.
8. Security check registry.
9. Controlled execution environment.
10. Evidence collection subsystem.
11. Finding verification and classification subsystem.
12. Report generation subsystem.
13. Persistent storage.
14. Audit logging and security controls.

A conceptual assessment pipeline:

```
APK Upload
    |
    v
Artifact Validation
    |
    v
Static Analysis
    |
    v
Technology and Endpoint Discovery
    |
    v
Attack-Surface Model
    |
    v
Candidate Security Hypotheses
    |
    v
Agent Planner
    |
    v
Scope and Permission Gate
    |
    v
Approved Security Checks
    |
    v
Independent Verification
    |
    v
Evidence and Findings
    |
    v
Security Assessment Report
```

The orchestration layer must track each stage as a persistent state.

A process crash must not silently mark an assessment as successful.

The design must support resuming interrupted work when safe, cancelling assessments, recording failures, and avoiding duplicate side effects.

---

# 7. Core Agent Design

This is the most important component of the project.

Do not implement an unrestricted LLM loop that repeatedly generates arbitrary shell commands.

Build a bounded agent that operates through registered tools and structured decisions.

## 7.1 Reasoning loop

Implement the following lifecycle:

### A. Observe

Collect current evidence, including:

* Static analysis results.
* Manifest information.
* SDK and dependency inventory.
* Discovered endpoints.
* Embedded configuration.
* Candidate backend resources.
* Previous test results.
* Existing findings.
* Assessment scope and permissions.
* Remaining execution budget.

### B. Interpret

The LLM may interpret the evidence to identify:

* Likely technologies.
* Potential trust boundaries.
* Suspected authorization weaknesses.
* Missing information.
* Relevant security checks.
* Alternative explanations.
* Confidence and uncertainty.

The LLM must distinguish direct observations from assumptions.

### C. Form a hypothesis

Represent each hypothesis as structured data.

For example:

```
Hypothesis:
  id: hypothesis-123
  category: authorization
  target: discovered_supabase_resource
  claim: anonymous access may be permitted
  evidence:
    - public project configuration discovered
    - resource reference discovered in application
  missing_information:
    - actual anonymous access result
  proposed_check:
    - bounded read-only authorization test
  risk: medium
  status: unverified
```

The presence of a public client key must never automatically create a confirmed vulnerability.

### D. Plan

The planner chooses a permitted next step based on:

* Potential security impact.
* Relevance to discovered evidence.
* Information gain.
* Execution cost.
* Expected coverage improvement.
* Risk of unintended side effects.
* Current assessment budget.
* Previously attempted checks.

Prefer the simplest deterministic check capable of resolving the uncertainty.

Do not ask an LLM to repeatedly rediscover information that is already available in structured state.

### E. Authorize

Before execution, validate the proposed action against:

* Assessment scope.
* Registered tool permissions.
* Allowed target resources.
* Network policy.
* Request limits.
* Data access policy.
* Human approval requirements.

The LLM must not be allowed to grant itself permissions.

### F. Execute

Run the selected registered tool in the appropriate isolated execution environment.

Every action must have:

* A unique action ID.
* An assessment ID.
* A hypothesis or test objective.
* Validated arguments.
* Start and completion timestamps.
* A timeout.
* A recorded outcome.
* Relevant evidence references.

### G. Verify

A separate verification component evaluates the actual tool output.

Use deterministic assertions whenever possible.

For example, distinguish:

* Connection failure.
* Authentication failure.
* Authorization denial.
* Successful access to a permitted resource.
* Successful access to a resource expected to be restricted.
* Inconclusive response.
* Tool failure.
* Insufficient evidence.

Do not let the same LLM assertion that initiated a test serve as the sole proof that the test succeeded.

### H. Update

Update the application model, hypothesis status, findings, coverage metrics, and remaining unknowns.

The planner can then select the next check or terminate the assessment.

## 7.2 Stop conditions

The agent must stop when:

* The budget is exhausted.
* The assessment is cancelled.
* A required approval is unavailable.
* The target is outside scope.
* A critical infrastructure failure prevents safe execution.
* No relevant checks remain.
* Additional exploration has insufficient expected value.
* The assessment deadline has been reached.

A completed assessment means the configured assessment process finished, not that the application is secure.

---

# 8. Structured Tool Interface

Create a registered tool system.

The LLM must never receive arbitrary unrestricted execution capabilities.

Tools should have explicit input and output schemas.

Example interface:

```
class SecurityTool:
    name: str
    description: str
    input_schema: dict
    required_permissions: list
    risk_level: str

    def validate_scope(self, context): ...
    def validate_arguments(self, arguments): ...
    def execute(self, context, arguments): ...
    def normalize_result(self, raw_result): ...
```

Adapt the interface to idiomatic Python and proper typing.

Example tool categories:

## Artifact tools

* inspect_apk_metadata
* inspect_android_manifest
* enumerate_apk_files
* extract_resource_references
* inspect_permissions
* identify_dependencies

## Static analysis tools

* search_embedded_configuration
* identify_backend_sdks
* extract_endpoint_references
* inspect_authentication_references
* search_for_suspicious_patterns
* run_static_security_rules

## Assessment model tools

* get_attack_surface
* get_hypotheses
* get_previous_results
* get_remaining_budget
* identify_unexplored_resources

## Supabase assessment tools

* validate_supabase_project_reference
* classify_client_key
* inspect_authorized_supabase_metadata
* test_scoped_anonymous_read_access
* compare_access_results_by_authentication_state
* review_authorized_rls_configuration
* review_authorized_grants
* review_authorized_storage_configuration

These names are proposed capabilities, not permission to implement unsafe behavior indiscriminately.

Every tool must enforce scope and permissions independently of the planner.

The tools must return normalized results rather than unstructured terminal output whenever possible.

---

# 9. Static APK Analysis

Implement a robust initial static analysis pipeline.

## 9.1 Artifact validation

Before processing:

* Validate the uploaded file format.
* Check file size limits.
* Calculate a SHA-256 hash.
* Store the original filename separately from the internal storage key.
* Detect malformed or suspicious archives.
* Enforce decompression limits.
* Reject path traversal entries.
* Prevent archive bombs and excessive resource consumption.
* Record artifact metadata.
* Never trust the file extension alone.

## 9.2 Android manifest analysis

Extract, where available:

* Package identifier.
* Version information.
* Minimum and target SDK.
* Declared permissions.
* Exported activities.
* Exported services.
* Exported broadcast receivers.
* Exported content providers.
* Deep links and intent filters.
* Network security configuration references.
* Debuggable status.
* Backup-related configuration.
* Cleartext traffic configuration.
* Signing certificate metadata where available.

Apply version-aware rules and avoid labeling a configuration as vulnerable without considering relevant platform behavior.

## 9.3 Resource and code analysis

Search the application for:

* Backend project URLs.
* API endpoints.
* SDK initialization.
* Public client configuration.
* Authentication flow references.
* Storage bucket references.
* Database table and entity names.
* GraphQL endpoint references.
* WebSocket endpoints.
* Hardcoded passwords or tokens that may actually be sensitive.
* Insecure HTTP references.
* Certificate validation weaknesses.
* Suspicious dynamic code loading.
* Insecure WebView configuration.
* Debug or test configuration accidentally shipped in the application.

Classify each discovered value.

Do not label all strings matching token-like patterns as secrets. A value's context, intended visibility, scope, and privileges matter.

For each discovery, record:

* File or code location.
* Evidence snippet or safe reference.
* Detection method.
* Confidence.
* Relevant security rule.
* Whether runtime validation is needed.

Redact actual secrets from normal logs and reports unless explicitly necessary and authorized.

---

# 10. Backend Discovery and Attack-Surface Model

Build a normalized model of the resources the application appears to interact with.

Suggested entities:

* ApplicationArtifact.
* Technology.
* BackendService.
* Endpoint.
* Resource.
* AuthenticationMechanism.
* TrustBoundary.
* SecurityHypothesis.
* TestCase.
* ToolExecution.
* Evidence.
* Finding.

A resource could represent:

* A REST endpoint.
* A Supabase table or view.
* A storage bucket.
* A callable function.
* An authentication endpoint.
* A third-party API.

Represent relationships explicitly.

For example:

```
AndroidApplication
    -> initializes Supabase SDK
    -> references Supabase project
    -> references trip-related resource
    -> may interact with data API
```

This graph represents discovered relationships, not verified vulnerabilities.

Track provenance so every relationship can be traced back to a source file, static analysis rule, runtime observation, or authorized metadata query.

Store confidence and evidence quality separately.

Do not introduce a graph database until the actual data model and query patterns justify it. A relational schema is sufficient initially.

---

# 11. Supabase Security Assessment Module

Supabase is the first specialized backend integration and should be implemented carefully.

## 11.1 Important security model

A Supabase URL and public client key can legitimately appear in a client application.

Their presence alone is not a security finding.

The assessment must investigate what permissions the client has and whether the backend enforces the intended authorization boundaries.

Relevant concepts include:

* Publishable and legacy anonymous keys.
* Authenticated and anonymous request contexts.
* PostgreSQL privileges.
* Row Level Security.
* RLS policies.
* Exposed schemas.
* Tables and views.
* Database functions.
* Storage policies.
* API exposure configuration.

Do not assume that all Supabase projects use identical key formats or authorization configurations.

Use current official documentation and supported interfaces when implementing this module.

## 11.2 Check categories

Implement these checks incrementally.

### Check A: Configuration discovery

Determine whether the APK references a Supabase project.

Collect:

* Project URL.
* Client SDK references.
* Client-key classification where possible.
* Relevant resource names.
* Evidence locations.

Do not attempt to infer privileged backend credentials from a public client key.

### Check B: Anonymous access assessment

Only after the project is explicitly within scope and active testing is authorized:

* Determine whether the configured endpoint is reachable.
* Use the intended unauthenticated client context.
* Test only approved resources.
* Use minimal read-only requests.
* Record response status and relevant authorization behavior.
* Distinguish an empty response from a denied request.
* Distinguish expected public access from potentially unauthorized access.
* Avoid broad queries and bulk retrieval.

A successful HTTP response alone does not prove a vulnerability.

The agent must determine what resource was accessed and whether the response supports the security claim.

### Check C: Authenticated access assessment

When authorized test accounts are supplied:

* Test with dedicated test identities.
* Compare access for appropriate roles.
* Verify resource-level and row-level boundaries using synthetic test records when possible.
* Check that one test user cannot access another user's restricted data.
* Verify that the results are consistent with the intended access policy.

Never use unrelated real users' records as test fixtures.

### Check D: Administrative configuration review

When the user provides authorized administrative access, use supported metadata interfaces to review:

* RLS enabled status.
* Policies and their applicable roles.
* PostgreSQL table and schema grants.
* Exposed schema configuration.
* Relevant views and functions.
* Storage bucket and object policies.
* Privileges that may undermine intended RLS protections.

Do not assume that administrative metadata is available from the mobile application.

If the assessment lacks administrative access, mark these checks as unavailable or not assessed rather than inferring the configuration.

### Check E: Remediation guidance

Generate remediation guidance based on the actual evidence.

For example:

* Enable RLS where appropriate.
* Define restrictive policies for authenticated users.
* Verify PostgreSQL grants.
* Review views and functions separately.
* Check storage policies.
* Re-test with anonymous and authenticated contexts.
* Add regression tests.

The generic advice to enable RLS is not sufficient to fix every access-control issue. The agent must explain the policy and permission changes that are relevant to the finding, while leaving actual production changes to an authorized operator.

---

# 12. Safe Assessment and Execution Infrastructure

Security testing must be isolated from the main application.

Treat uploaded APKs, extracted files, decompiled code, remote responses, and application metadata as untrusted input.

## 12.1 Isolation

Use a dedicated worker environment for risky processing.

Apply:

* CPU limits.
* Memory limits.
* Execution timeouts.
* Disk quotas.
* Non-root execution.
* Restricted filesystem access.
* Restricted network egress.
* Controlled tool installations.
* Disposable workspaces.
* Cleanup of temporary files.

Do not execute extracted scripts or binaries merely because they were present in the APK.

Static analysis should not require running the uploaded application.

## 12.2 Network scope enforcement

Implement a central scope policy.

Every active network tool must validate:

* Scheme.
* Hostname.
* Resolved destination address.
* Redirect destination.
* Permitted port.
* Assessment scope.
* Request budget.

Mitigate SSRF and DNS rebinding risks. Block loopback, private, link-local, and other prohibited destinations unless the assessment explicitly authorizes a controlled internal lab target.

Do not rely solely on validating a hostname before redirects or DNS resolution.

Do not permit an LLM to bypass scope validation by constructing an alternate URL or invoking a shell command.

## 12.3 Data minimization

The platform must not download entire production datasets to prove an access-control issue.

Prefer:

* Synthetic records.
* Dedicated test accounts.
* Minimal record counts.
* Redacted responses.
* Hashes or metadata where useful.
* Evidence limited to the smallest amount necessary.

Avoid retaining sensitive response bodies when a status code, resource identifier, and redacted sample are sufficient.

## 12.4 Approval gates

Require explicit approval for:

* Active testing against production systems.
* Potentially destructive checks.
* Data mutation.
* Account creation or deletion.
* Sensitive authentication workflows.
* Operations with external side effects.

The default must be deny unless the relevant operation is within the assessment's approved scope.

---

# 13. Finding Verification and Confidence

Build a dedicated finding lifecycle.

Suggested statuses:

* `candidate`
* `planned`
* `testing`
* `confirmed`
* `not_reproducible`
* `false_positive`
* `inconclusive`
* `not_assessed`
* `remediated`

Do not use the LLM's confidence score as the sole basis for confirming a finding.

Track at least three distinct dimensions:

1. **Evidence strength:** How directly does the evidence support the claim?
2. **Impact:** What is the likely security consequence if the claim is true?
3. **Confidence:** How certain is the classification given the evidence and alternative explanations?

An example finding:

```
Title:
  Potential unauthorized access to a restricted resource

Affected resource:
  Authorized Supabase project and resource

Observation:
  An unauthenticated read request returned records.

Evidence:
  Sanitized request metadata, response classification,
  timestamp, and test execution reference.

Expected behavior:
  Access should be restricted according to the approved
  assessment requirements.

Assessment:
  Confirmed only if the evidence establishes the access
  violation. Otherwise, classify as candidate or inconclusive.

Impact:
  Explain the type of information exposed without
  inventing record counts or affected users.

Remediation:
  Review the applicable RLS policies, PostgreSQL grants,
  and resource exposure configuration.

Reproduction:
  Provide a safe, minimal, in-scope reproduction procedure.
```

A finding must include provenance linking it to the tool execution and original evidence.

If the LLM generates a claim unsupported by collected evidence, the report generator must reject or downgrade that claim.

---

# 14. Security Report

Generate reports in the dashboard and provide downloadable JSON and HTML reports. Add PDF export if practical without delaying the MVP.

A report should contain:

## Executive summary

* Application identifier.
* Artifact hash.
* Assessment scope.
* Assessment date.
* Assessment type.
* Summary of confirmed findings.
* Important limitations.
* Overall coverage and incomplete checks.

## Technical findings

For each finding:

* Unique finding ID.
* Title.
* Severity.
* Affected component.
* Vulnerability category.
* Description.
* Evidence.
* Impact.
* Preconditions.
* Reproduction steps.
* Confidence and evidence quality.
* Remediation.
* Verification status.
* References to applicable security standards where justified.

## Assessment coverage

Report:

* Checks completed.
* Checks failed due to tool errors.
* Checks blocked by permissions.
* Checks skipped.
* Checks that were inconclusive.
* Resources discovered.
* Resources actually assessed.
* Known blind spots.

Do not equate "no findings" with "secure."

Do not calculate a numerical security score unless the scoring method is explicitly defined, documented, and supported by evidence.

---

# 15. Data Model

Design a normalized relational schema with migrations.

At minimum, consider these entities:

### User

* id
* email
* authentication fields
* role
* created_at

### Project

* id
* owner_id
* name
* description
* created_at

### ApplicationArtifact

* id
* project_id
* filename
* internal_storage_key
* sha256
* file_size
* platform
* package_identifier
* version
* upload_status
* created_at

### Assessment

* id
* project_id
* artifact_id
* scope_configuration
* assessment_type
* status
* current_stage
* started_at
* completed_at
* cancelled_at
* failure_reason

### Technology

* id
* name
* category
* version
* confidence

### AttackSurfaceResource

* id
* assessment_id
* resource_type
* identifier
* source_location
* discovery_method
* confidence
* authorization_status
* metadata

### Hypothesis

* id
* assessment_id
* title
* description
* supporting_evidence_ids
* missing_information
* status
* priority
* created_at

### TestCase

* id
* assessment_id
* hypothesis_id
* name
* test_type
* preconditions
* expected_behavior
* status

### ToolExecution

* id
* assessment_id
* test_case_id
* tool_name
* validated_arguments
* status
* started_at
* completed_at
* normalized_result
* error_category

Do not persist secrets in `validated_arguments` without explicit need and encryption.

### Evidence

* id
* assessment_id
* execution_id
* evidence_type
* storage_key
* sanitized_metadata
* content_hash
* created_at
* retention_policy

### Finding

* id
* assessment_id
* title
* description
* severity
* status
* confidence
* evidence_quality
* impact
* remediation
* created_at
* updated_at

Add appropriate indexes, foreign keys, uniqueness constraints, timestamps, and ownership enforcement.

Treat the schema above as a starting point, not a reason to create unnecessary tables.

Keep large artifacts and binary evidence outside PostgreSQL, storing only metadata and secure references in the database.

---

# 16. API Design

Implement a documented REST API through FastAPI.

Proposed endpoints:

```
POST   /api/v1/projects
GET    /api/v1/projects
GET    /api/v1/projects/{project_id}

POST   /api/v1/artifacts
GET    /api/v1/artifacts/{artifact_id}

POST   /api/v1/assessments
GET    /api/v1/assessments/{assessment_id}
POST   /api/v1/assessments/{assessment_id}/start
POST   /api/v1/assessments/{assessment_id}/cancel
GET    /api/v1/assessments/{assessment_id}/events
GET    /api/v1/assessments/{assessment_id}/attack-surface
GET    /api/v1/assessments/{assessment_id}/hypotheses
GET    /api/v1/assessments/{assessment_id}/findings

GET    /api/v1/findings/{finding_id}
GET    /api/v1/assessments/{assessment_id}/report
```

Adapt the endpoints as needed.

Requirements:

* Pydantic request and response models.
* Consistent error formats.
* Authentication and authorization.
* Pagination.
* Input validation.
* Rate limits where appropriate.
* Idempotency for assessment creation and execution requests.
* Correct HTTP status codes.
* OpenAPI documentation.
* No exposure of internal filesystem paths or raw secrets.

Do not implement the entire API as one enormous router.

---

# 17. Frontend Requirements

Build a professional security assessment dashboard.

The UI should prioritize information density, readability, and clear evidence.

## Main pages

### Dashboard

Display:

* Projects.
* Recent assessments.
* Assessment status.
* Confirmed findings.
* Assessments requiring review.
* Recent activity.

Do not show fabricated security metrics.

### Project details

Display:

* Uploaded artifacts.
* Artifact metadata.
* Assessment history.
* Configured scope.
* Available assessment capabilities.

### Upload flow

Allow users to:

* Upload an APK.
* See file validation results.
* Review extracted metadata.
* Configure the assessment.
* Review the proposed target scope.
* Explicitly authorize active testing where required.
* Start the assessment.

### Assessment detail

Display the assessment lifecycle:

* Queued.
* Validating.
* Static analysis.
* Technology discovery.
* Attack-surface modeling.
* Planning.
* Security checks.
* Verification.
* Reporting.
* Completed, failed, or cancelled.

Show live progress from real backend events.

### Attack-surface explorer

Display discovered technologies, endpoints, backend services, resources, and relationships.

Make it easy to distinguish:

* Discovered.
* Inferred.
* Verified.
* Not assessed.

### Findings

Provide filtering by:

* Severity.
* Status.
* Category.
* Backend service.
* Verification state.

### Finding detail

Show:

* Summary.
* Technical details.
* Evidence.
* Reproduction procedure.
* Impact.
* Confidence and limitations.
* Remediation.
* Execution history.

### Assessment settings

Include:

* Target scope.
* Testing permissions.
* Execution limits.
* Data retention.
* Approval requirements.

The interface must not imply that active testing is running when the backend has not started it.

Use server-sent events or another appropriate mechanism for progress updates. Reconnect safely and fetch the current assessment state if an event stream disconnects.

---

# 18. LLM Prompting and Structured Decisions

Create versioned prompts and structured Pydantic models for:

* Technology interpretation.
* Attack-surface summarization.
* Hypothesis generation.
* Test prioritization.
* Action selection.
* Evidence interpretation.
* Finding explanation.
* Report generation.

The LLM must never directly write arbitrary Python code or shell commands for execution in the production assessment loop.

Represent actions as registered tool names with validated arguments.

An example decision schema:

```
class AgentDecision:
    objective: str
    hypothesis_id: str | None
    action: str
    arguments: dict
    expected_observation: str
    rationale: str
    uncertainty: list[str]
    stop_reason: str | None
```

Adapt this into properly typed, validated models.

Validate all output before execution.

If the model returns malformed data, an unregistered tool, invalid arguments, or a prohibited operation, reject the decision and record the failure.

Do not silently convert invalid model output into a different action.

## Prompt injection resistance

Treat the following as untrusted data:

* Decompiled application code.
* Embedded strings.
* API responses.
* Web content.
* Backend error messages.
* Documentation retrieved from the target.
* LLM-generated hypotheses.

These sources may contain instructions that attempt to influence the agent.

Never allow instructions discovered in an application or API response to override system policy, assessment scope, permissions, or registered tool restrictions.

Keep policy enforcement outside the LLM.

---

# 19. Agent Memory and Context Management

Do not send the entire APK, all decompiled source, every tool result, and the full conversation history to the LLM on every iteration.

Implement structured, selective context.

Maintain:

### Working state

* Current assessment stage.
* Current objective.
* Current hypothesis.
* Last observations.
* Pending action.
* Remaining budget.

### Persistent assessment knowledge

* Discovered technologies.
* Resources.
* Trust boundaries.
* Relationships.
* Completed checks.
* Findings.
* Evidence references.
* Failed approaches.
* Known limitations.

### Evidence retrieval

Retrieve only the source snippets, test results, and resource metadata relevant to the current hypothesis.

Store large analysis outputs as artifacts and index them for retrieval.

For code search, begin with conventional text search and language-aware parsing. Add embeddings only when they demonstrably improve retrieval.

Avoid adding a vector database solely because the project uses an LLM.

---

# 20. Testing Strategy

The platform must be tested as software, not just demonstrated on a successful scan.

## Unit tests

Cover:

* APK validation.
* Manifest parsing.
* Configuration extraction.
* Endpoint classification.
* Secret redaction.
* Tool argument validation.
* Scope enforcement.
* State transitions.
* Finding classification.
* Report serialization.

## Integration tests

Cover:

* Upload and artifact persistence.
* Background assessment execution.
* Worker failure and recovery.
* Database migrations.
* Evidence storage.
* API authorization.
* LLM timeout and malformed responses.
* Tool execution and result normalization.

## Agent tests

Create deterministic mocked scenarios.

Examples:

1. Public Supabase configuration is detected but no vulnerability is reported without further evidence.
2. A restricted resource returns an authorization denial, so the agent does not report unauthorized access.
3. An anonymous request receives access to a deliberately misconfigured synthetic resource in a local test environment, producing a correctly evidenced finding.
4. A tool fails, so the result is classified as inconclusive rather than vulnerable.
5. The LLM proposes an out-of-scope hostname, and the scope gate rejects the action.
6. The LLM proposes an unregistered tool, and execution is refused.
7. An API response contains prompt-injection text, and the agent does not change its policy.
8. The execution budget is exhausted, and the assessment terminates safely.
9. The worker crashes, and the assessment does not become falsely marked as completed.
10. A report contains only claims supported by stored evidence.

## End-to-end evaluation

Build a local test lab containing:

* A sample Android application.
* A deliberately insecure test backend.
* A correctly configured test backend.
* Synthetic test accounts and records.
* Known expected findings.
* Known false positives.
* Documented assessment limitations.

Never use real production customer data for evaluation.

Measure:

* Precision of confirmed findings.
* Recall against the known test cases.
* False-positive rate.
* False-negative rate.
* Resource and transition coverage.
* Assessment completion rate.
* Average execution time.
* LLM cost per assessment.
* Reproducibility of findings.

Do not optimize only for the number of vulnerabilities discovered.

---

# 21. Observability and Operations

Implement structured logs and metrics.

Track:

* Assessment ID.
* Tool execution ID.
* Agent iteration.
* Model provider and model identifier.
* Prompt version.
* Input/output token counts where available.
* Tool execution duration.
* Retry count.
* Failure category.
* Assessment budget consumption.
* Findings produced.
* Evidence references.

Do not log passwords, access tokens, complete sensitive responses, or raw secrets.

Use trace IDs across API requests and worker execution.

Provide a clear distinction between:

* Application errors.
* Infrastructure errors.
* LLM errors.
* Tool errors.
* Scope denials.
* Assessment findings.

A security finding is not the same thing as a failed tool execution.

---

# 22. Authentication and Multi-Tenancy

Build basic user authentication and enforce project-level authorization.

At minimum:

* Users must only access their own projects and assessments.
* Every API endpoint must verify ownership or an explicit permission.
* Artifact access must be authorized.
* Download URLs must not be guessable.
* Background workers must preserve tenant context.
* Evidence references must not permit cross-tenant access.
* Secrets must be encrypted at rest when stored.
* Sensitive credentials must be masked in the UI.
* Audit logs must record sensitive actions.

If the MVP is deployed for a single trusted operator, preserve a clean path to multi-tenancy without pretending that a local single-user mode provides production-grade multi-user security.

---

# 23. Configuration and Secrets

Provide a documented `.env.example`.

Include appropriate configuration for:

* Database.
* Redis, if used.
* LLM provider and model.
* API settings.
* Artifact storage.
* Upload size limits.
* Worker concurrency.
* Assessment timeout.
* Request budget.
* Network scope policy.
* Logging.
* Authentication.
* Evidence retention.

Never commit actual credentials.

Do not include real secrets in examples, tests, screenshots, fixtures, or seed data.

Fail clearly when a required configuration is missing.

Optional LLM functionality should degrade gracefully: deterministic analysis must remain available without an LLM key.

---

# 24. Repository and Code Quality Requirements

Follow clear engineering conventions.

* Use type hints throughout the Python codebase.
* Prefer small, cohesive modules.
* Separate domain logic from infrastructure.
* Keep LLM provider integration behind an interface.
* Keep security tools independently testable.
* Use database migrations.
* Use structured exceptions.
* Avoid broad exception handling that hides failures.
* Avoid duplicated authorization logic.
* Do not introduce unnecessary abstractions.
* Do not build enormous files containing unrelated functionality.
* Keep dependencies minimal and pinned appropriately.
* Provide linting and formatting configuration.
* Provide automated tests.
* Document significant architectural decisions.
* Keep comments focused on non-obvious behavior.

Do not use hardcoded fake results to make the interface appear functional.

If a feature is not implemented, label it as unavailable or not implemented.

---

# 25. Development Workflow and Deliverables

Work incrementally.

Do not attempt to generate the entire system in one enormous code-writing operation.

## Phase 0: Repository inspection and design

Before modifying files:

1. Inspect the existing repository.
2. Identify the existing stack and constraints.
3. Determine which components already exist.
4. Identify dependencies and environmental requirements.
5. Produce a proposed architecture.
6. Create a prioritized implementation plan.
7. Identify security risks and architectural trade-offs.
8. Define the MVP acceptance criteria.

If the repository is empty, scaffold the project according to this specification.

If the repository already contains code, preserve working functionality unless a change is justified.

Do not overwrite existing work without understanding it.

## Phase 1: Foundation

Implement:

* Repository structure.
* Development configuration.
* Docker Compose.
* Database models and migrations.
* FastAPI application.
* React frontend.
* Health checks.
* Authentication foundation.
* Structured logging.
* Automated test setup.

Acceptance criteria:

* The project starts using documented commands.
* Database migrations work on a clean database.
* Health checks return real status.
* API and frontend communicate successfully.
* Configuration errors are understandable.

## Phase 2: Artifact intake and static analysis

Implement:

* Secure APK upload.
* Artifact validation.
* Hashing.
* Android manifest inspection.
* Resource extraction.
* Backend and SDK identification.
* Endpoint discovery.
* Structured analysis results.

Acceptance criteria:

* A valid sample APK can be uploaded and analyzed.
* Invalid artifacts are rejected.
* File size and extraction limits are enforced.
* Findings include provenance.
* Analysis works without an LLM API key.

## Phase 3: Attack-surface model

Implement:

* Resource and technology entities.
* Relationships.
* Hypothesis storage.
* Evidence references.
* Confidence and status tracking.
* Attack-surface API.
* Dashboard visualization.

Acceptance criteria:

* A user can inspect what was discovered.
* Each important discovery can be traced to evidence.
* Inferred relationships are distinguishable from verified facts.

## Phase 4: Agent reasoning engine

Implement:

* LLM provider interface.
* Structured decision schemas.
* Hypothesis generation.
* Action planning.
* Registered tool execution.
* Persistent state.
* Budget enforcement.
* Retry and recovery behavior.
* Stop conditions.

Acceptance criteria:

* The agent selects only registered tools.
* Invalid decisions are rejected.
* Assessment state survives worker restarts where safe.
* Every execution has an auditable result.
* A missing LLM configuration does not disable deterministic analysis.

## Phase 5: Supabase checks

Implement the first specialized backend module.

Start with configuration discovery and then introduce bounded, authorized access-control checks.

Add administrative configuration review only where appropriate authorized access is available.

Acceptance criteria:

* Public client configuration alone does not create a confirmed vulnerability.
* Out-of-scope projects cannot be actively tested.
* Anonymous and authenticated contexts are distinguished.
* Tool failures are not reported as vulnerabilities.
* Confirmed findings include reproducible, minimal evidence.
* No bulk production data extraction occurs.
* Findings include appropriate remediation guidance.

## Phase 6: Reporting and dashboard completion

Implement:

* Assessment lifecycle UI.
* Findings management.
* Evidence views.
* Report generation.
* Cancellation and failure states.
* Coverage and limitations.
* Downloadable reports.

Acceptance criteria:

* The UI reflects persisted backend state.
* Reports distinguish confirmed, candidate, and inconclusive results.
* Findings link to evidence.
* An assessment with no findings is not labeled secure merely because it completed.

## Phase 7: Evaluation and hardening

Implement the local test lab and adversarial tests.

Test:

* Scope enforcement.
* Prompt injection.
* Tool misuse.
* Worker failures.
* Invalid artifacts.
* Excessive resource consumption.
* Sensitive-data redaction.
* Cross-tenant authorization.
* Report correctness.

Do not call the system production-ready until critical acceptance criteria pass.

---

# 26. Required Documentation

Create and maintain:

* `README.md`: setup, features, usage and limitations.
* `docs/architecture.md`: architecture and component boundaries.
* `docs/agent-design.md`: reasoning loop, state model, memory and tools.
* `docs/security-model.md`: scope, isolation, permissions and threat model.
* `docs/supabase-assessment.md`: implemented checks, required access and limitations.
* `docs/testing.md`: unit, integration and evaluation procedures.
* `docs/deployment.md`: deployment and configuration.
* `docs/roadmap.md`: completed, planned and deferred functionality.
* `.env.example`: placeholder configuration.
* `docker-compose.yml`: local development environment.
* `DECISIONS.md` or ADR documents for significant architectural decisions.

Documentation must describe the implementation that actually exists, not the entire aspirational roadmap as if it were finished.

---

# 27. Definition of Done

A feature is complete only when:

1. The implementation exists.
2. Input validation is implemented.
3. Appropriate authorization and scope checks are present.
4. Errors are handled explicitly.
5. Tests cover expected behavior and important failure cases.
6. Logs do not leak sensitive information.
7. The feature is documented.
8. The frontend reflects real backend behavior if applicable.
9. The implementation has been run and verified.
10. Limitations are documented.

Never claim tests passed without executing them.

Never claim an assessment detected a real vulnerability when the result came from a fixture or mocked response.

Clearly identify any tests that could not be executed because of missing dependencies or environment restrictions.

---

# 28. How You Should Work With Me

I will use Claude Code to build and evolve this system.

Follow these rules throughout the development process:

1. Inspect the existing repository before proposing file changes.
2. Start by explaining the architecture and creating a prioritized plan.
3. Do not ask me to make every minor technical decision. Make sensible engineering choices and explain consequential trade-offs.
4. Ask questions only when a missing decision materially changes the architecture, security posture, or product behavior.
5. Implement a vertical slice at a time.
6. After each phase, run the relevant tests and report the actual results.
7. Keep the repository runnable throughout development.
8. Do not silently replace a working implementation with a simpler mock.
9. Do not implement dangerous capabilities merely because an LLM proposes them.
10. Keep security policy enforcement deterministic and outside the model.
11. Do not invent test results, scan results, evidence, or supported features.
12. When a requirement is ambiguous, record the assumption and choose the safest reasonable behavior.
13. Prefer the smallest reliable implementation that satisfies the current acceptance criteria.
14. Maintain a checklist of completed, partially completed, blocked, and unimplemented capabilities.
15. Update the architecture and roadmap documentation as the implementation evolves.

When you encounter a technical limitation, explain it and propose a concrete alternative instead of silently omitting the capability.

If a tool or library has changed, verify its current interface using its official documentation before relying on remembered APIs.

Do not introduce a complex framework unless it provides a clear benefit over a simpler implementation.

---

# 29. Your First Task

Do not start by writing all the code.

Begin with Phase 0.

Inspect the repository and provide:

1. A concise understanding of the product.
2. A proposed architecture with component responsibilities.
3. A repository directory structure.
4. A data model and key relationships.
5. The agent reasoning and execution lifecycle.
6. A security threat model covering uploaded artifacts, the LLM, tool execution, network access, credentials, and sensitive evidence.
7. The recommended implementation order.
8. A prioritized MVP backlog with acceptance criteria.
9. The major technical risks and trade-offs.
10. Any assumptions that need to be recorded.

Then create the architecture and roadmap documents in the repository.

After that, implement Phase 1 and verify it before proceeding.

The goal is a working, evidence-driven agentic security assessment platform, not a proof-of-concept that merely looks autonomous.
