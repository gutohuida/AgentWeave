# Proposal — agents no longer register themselves

**Round 1, 2026-09-24** (bundle B3, spec track S9, decision D3). Findings **F111 (B)**, **F136 (B)**
and **F3 (C)**, which share one root: the self-registration route and the watchdog-era contact
vocabulary around it. All three re-verified on HEAD `404c7d5`. **Nothing here is implemented yet.**

## Why

The operator decided on 2026-08-29 that self-registration leaves the product (FINDINGS F111,
*"The decision, 2026-08-29"*; the operator's words are quoted in the untracked handoff
`handoff-0099-2026-08-29-1250-merged-decided-drove-and-armed.md`, decision 2: *"No it does not belong
in the product … I think it's a legacy thing"*, and the roadmap
`openspec/explorations/2026-08-30-release-roadmap.md:78` lists it *"Decided 2026-08-29, queued"*).
`spec-queue/DECISIONS.md` has no entry for it. The deletion was queued as a spec loop and never built, so all three
findings still reproduce from source:

- **F111 / F136 — an unbound self-registered agent is told to install a binary named after
  itself.** `launchability.get_agent_config` gives the unbound case its honest name only when
  `not agent_row.self_registered` (`hub/hub/launchability.py:507`). A self-registered agent with no
  runner falls through to `cli = RUNNER_CLI.get(runner) or name`, so the probe, the queue status and
  the composer all read *"Runner CLI '<agent>' was not found in PATH."* The shipped requirement
  `agent-configuration` *"An agent with no way to be launched SHALL say so, and SHALL NOT name a CLI
  after itself"* is violated for exactly that population.
- **F3 — every agent is born `contact_mode="watchdog-spawn"`.** Operator creation
  (`hub/hub/api/v1/agents.py:735`) and `request_agent` (`:2203`) write the literal; the watchdog it
  names was deleted, and `CLAUDE.md` forbids recreating it. `_CONTACT_MODES` (`:84`) still offers it,
  so `POST /agents/register` and `PATCH /agents/{name}` answer `Invalid contact_mode … Valid: poll,
  mcp-push, watchdog-spawn` (`:2285`, `:2601`). The field's only behavioural reader is
  `scheduler.py:250` (`self_registered and contact_mode == "poll"`), which no agent that exists can
  satisfy.

**Measured today, read-only:** the operator's real database (`~/.agentweave/hub/data/agentweave.db`,
`mode=ro`) holds **8 agents, all `self_registered=0`, all `watchdog-spawn`**; the trial Hub's holds 3,
the same. **`project_sessions` is empty on both.** No shipped client calls `POST /agents/register`
(the CLI, the UI and `mcp_server.py` do not; FINDINGS F111). The population the wrong sentence is
written for exists only in tests and drive harnesses.

## What Changes

- **Delete `POST /projects/{p}/agents/register`** (`agents.py:2261-2324`) and the poll-agent skip in
  the scheduler (`_job_agent_skip_reason`, `scheduler.py:229-252`, called at `:3078`, whose only
  condition needs a self-registered row).
- **Drop the watchdog-era agent columns** `contact_mode`, `self_registered`, `mcp_endpoint`,
  `spawn_cmd` in one migration. Models, `_CONTACT_MODES`, the PATCH allowlist
  (`_PATCH_AGENT_FIELDS`, `agents.py:2518-2521`), the PATCH handler (`:2596-2603`), and every response
  that echoes them go with them: `OperatorAgentResponse` (`:129-130`), the agent detail
  (`:2699-2700`), `AgentSummary.self_registered` and the heartbeat-derived `liveness` computed only
  for self-registered agents (`agents.py:567-577`, `schemas/agents.py:91`).
- **Remove the `self_registered` guard in launchability** (`launchability.py:507` becomes
  `elif "runner" not in meta:`), so every agent with no runner anywhere is reported unbound — which
  closes F136 for any row that survives.
- **UI:** remove `self_registered`/`contact_mode`/`liveness` from `hub/ui/src/api/agents.ts` and the
  `EXT` badge in `AgentCard.tsx:65` (a component no screen mounts — see B10/D6). One bundle refresh.
- **CLI dead code:** `get_agent_registration` (`src/agentweave/transport/http.py:586`, declared abstract at
  `transport/base.py:98`) and `CONTACT_MODES` (`src/agentweave/constants.py:321`, already marked DEAD
  at `:315`) have no callers; delete them.
- **Tests:** one shared fixture creates an agent row directly (the pattern
  `test_a_task_waits_while_its_run_waits.py:71` already uses), replacing the 31 register call sites
  in 19 files outside `test_agents_self_registered.py`, which is deleted with the route it tests.
- **Specs:** `runner-registry` and `agent-configuration` lose the self-registered carve-outs;
  `runtime-diagnostics` stops listing self-registered agents as a filter source.

Not in scope: the `project_sessions` table and `POST /session/sync` (still a test fixture and still
read by `launchability.py:469` and `_get_session_data`); retiring them is a larger cleanup and is
named as a follow-on in design Open Question 2.

## Capabilities

### Modified Capabilities

- `runner-registry` — launchability no longer carries a self-registered exemption.
- `agent-configuration` — the "no CLI named after itself" rule holds for every agent.
- `runtime-diagnostics` — the log filter's sources no longer include self-registered agents.

## Impact

- **Migration** (next free number at IMPL time; `0106` today): drops four columns from `agents`.
  Reaches the operator's `:8000` on their next restart. No row there uses any of them
  meaningfully (measured above).
- **Response shape:** four agent fields disappear from three responses. The UI declares them and
  renders one of them in a component nothing mounts.
- **Harnesses:** 9 `scripts/drive/` files, `.claude/skills/e2e-loop/e2e.py`, and
  `docs/reference/hub-api.md` call or document the route. Drive harnesses are updated or marked
  retired; the docs row is deleted.
