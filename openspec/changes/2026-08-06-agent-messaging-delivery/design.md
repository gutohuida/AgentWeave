# Design — agent messaging delivery

## Reproduction of record

Everything below was observed on 2026-08-06 against a local Hub on `127.0.0.1:8010`, project
`proj-d9b5ed67` ("Two Codex Mini"), agents `codex-mini-1` / `codex-mini-2`, runner
`runner-f787147b` (`cli: codex`, `model: gpt-5.4-mini`), Codex CLI `0.146.0` on Windows 11.

| Run | Agent config | Observed |
|---|---|---|
| 1 | default (`yolo` unset) | 3× `agentweave.send_message: user cancelled MCP tool call` |
| 2 | `config.yolo = true` | `agentweave.send_message completed` → `Hub API error 405: Method Not Allowed` |

Run 2's 405 was traced to `POST http://127.0.0.1:8000/api/v1/agent-actions/messages`. Port 8000 was
held by a Docker-hosted older Hub (`curl http://127.0.0.1:8000/` returned an HTML shell with
`data-theme="cosmic"`, a theme system removed in `2026-08-04-hub-charcoal-visual-refresh`). The
route table of the *correct* Hub on 8010 confirms `POST /api/v1/agent-actions/messages` exists and
accepts POST, so the 405 could only have come from a different process.

## Decision 1 — how Codex approval is resolved

Three options were considered.

**Rejected: set `yolo` by default.** `--dangerously-bypass-approvals-and-sandbox` disables the
filesystem sandbox as well as approvals. Collaboration would then be purchased with the sandbox,
which is the trade the proposal exists to remove.

**Rejected: instruct the model not to need approval.** Prompt text cannot change an approval policy
evaluated by the CLI.

**Chosen: configure approval for the MCP server specifically, via `-c` overrides on the `codex exec`
invocation the Hub already constructs.** The Hub already writes
`mcp_servers.agentweave.command`, `.args`, and `.env_vars` this way; approval configuration belongs
in the same block, applied to the one server the Hub installed and to nothing else.

The precise key is **deliberately not fixed by this design**. Codex config keys are version-specific
(`codex exec --help` on 0.146.0 exposes `--strict-config`, which errors on unrecognised keys), and
the local `~/.codex/config.toml` carries `approvals_reviewer = "user"`, which is a strong candidate
for the cause but was not confirmed by reading Codex's source. Implementation task 1.1 is to
determine the correct key empirically against the installed CLI before writing any of it into the
command builder, and to record what was verified. **A key that has not been shown to work against a
real `codex exec` run MUST NOT be committed.**

Whatever key is chosen, the sandbox flag selection (`--sandbox workspace-write` vs
`--dangerously-bypass-approvals-and-sandbox`) stays exactly as it is today. Approval and sandboxing
become independent.

### Fallback if no such key exists

If task 1.1 establishes that this Codex version cannot grant non-interactive MCP approval by
configuration, the Hub SHALL detect the condition at spawn time and record a diagnostic naming it,
rather than starting a run whose tool surface it knows to be inert. Requirement
"A tool surface the agent cannot invoke is a failure, not a configuration" is written to be
satisfiable either way — by making the call work, or by refusing to pretend it will.

## Decision 2 — the Hub's own address

`settings.aw_port` describes *intent*; the bound socket describes *fact*. Uvicorn can be told a port
by CLI argument, by env var, by programmatic `run()`, or be given `port=0`, and only one of those
paths flows through `settings`.

The Hub SHALL capture its actually-bound address during startup — from the running server's socket,
in the lifespan hook — and every agent callback URL SHALL be derived from that captured value.

`HUB_URL`, when explicitly set in the Hub's own environment, remains an intentional operator
override and keeps precedence: a reverse proxy or container publishing a different external address
is a real deployment. What is removed is the *silent* fallback to a configured default. If neither
an explicit `HUB_URL` nor a captured bound address is available, starting a run is an error.

## Decision 3 — run credentials are instance-scoped

Fixing the URL removes the reproduction but not the class of failure. Any future path that sends an
agent action to the wrong Hub should fail closed.

A run token is minted by one Hub instance and recorded in one database. The receiving Hub already
looks the run up; today a token from another instance simply fails to resolve, which is correct but
indistinguishable from an expired token. The instance identity SHALL be carried and checked
explicitly so the rejection reason is diagnosable, and so a future shared-database deployment cannot
turn a mis-delivery into a successful cross-instance write.

## Decision 4 — failure visibility

`hub/hub/mcp_server.py` raises `HubAPIError` / `RuntimeError` into the agent's transcript and
nowhere else. Two changes:

1. The MCP adapter's error text SHALL name the endpoint it attempted, so a mis-delivered call is
   diagnosable from the transcript alone. The current text (`Hub API error 405: Method Not Allowed`)
   omits the one fact that mattered.
2. A tool call the Hub *can* observe failing SHALL be recorded as a run event and surfaced on the
   agent timeline. A call denied before leaving the agent's process (Defect 1) is by construction
   not observable Hub-side; this is why Decision 1 must fix that case rather than report it.

## Decision 5 — runner name mojibake

`GET /runners` returns `"Codex CLI â€” GPT-5.4-Mini"`. That is a UTF-8 em dash (`—`, `E2 80 94`)
decoded as Latin-1 and re-encoded. The auto-provisioning path in `hub/hub/api/v1/agents.py` builds
this name. Implementation must first establish **where** the double-encoding happens — name
construction, DB write, or response serialisation — because the fix differs, and any already-stored
name needs repairing or regenerating, not just the new ones.

This is bundled here rather than in the UI change because it is a data-correctness bug in the same
provisioning path, not a visual one.

## Risks

- **The Codex approval key may differ across Codex versions.** Mitigation: task 1.1 verifies against
  the installed CLI, and the fallback in Decision 1 keeps the failure loud instead of silent.
- **Capturing the bound address is uvicorn-shaped.** Mitigation: prefer the ASGI lifespan's view of
  the server over reaching into uvicorn internals; if the address genuinely cannot be observed,
  Decision 2's "refuse rather than guess" rule applies.
- **Stale Hub instances on neighbouring ports are an operator-environment hazard**, not only a code
  bug. The instance-scoped credential check (Decision 3) is what makes the environment hazard
  harmless.
