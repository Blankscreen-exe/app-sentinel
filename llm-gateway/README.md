# LLM gateway (the "Claude box")

The only component that holds LLM credentials (ADR-003/015). Prompt in → schema-validated
JSON decision out. It shells out to the Claude CLI with all built-in tools hardcoded OFF,
from an empty working directory, so a prompt-injection in the input can never reach a
shell, the filesystem, or the network.

## Contract

```
POST /decide  {system, prompt, json_schema, model?}
  -> 200 {ok:true, decision, usage, cost_usd, duration_ms}
  -> 4xx/5xx {ok:false, error, category}   # bad_request | timeout | busy | llm_error
GET  /health -> {status, role, model}
```

Never logs prompt contents — only metadata (usage, cost, duration).

## Authentication (choose one; injected at runtime, gateway only — ADR-015)

The platform runs fine with **no** credentials in `LLM_MODE=stub` or `disabled`
(deterministic static analysis and the control plane do not need an LLM). To enable real
Claude decisions (`LLM_MODE=gateway`), provide ONE of:

1. **`claude setup-token`** (recommended): run it on the host, then put the result in
   `.env` as `CLAUDE_CODE_OAUTH_TOKEN=...`.
2. **`ANTHROPIC_API_KEY=...`** in `.env`.
3. **Mount `~/.claude`** via `HOST_CLAUDE_DIR` — works only if the login is stored as
   files in that directory. On hosts that keep it in the OS keyring, use (1) or (2).

> Note: an **unauthenticated** gateway call with `--json-schema` causes the CLI to hang
> until the per-call timeout (a CLI quirk). This only happens if `LLM_MODE=gateway` is set
> without valid credentials. Keep the default (`disabled`/`stub`) until a token is set.

## Status

Built and verified mechanically: image, CLI install, `/health`, command construction,
error envelope, concurrency cap, timeout. Real end-to-end Claude decisions were validated
headless in `docs/spikes/001-claude-code-cli-as-llm.md`; in-container they require the
one-time credential setup above.
