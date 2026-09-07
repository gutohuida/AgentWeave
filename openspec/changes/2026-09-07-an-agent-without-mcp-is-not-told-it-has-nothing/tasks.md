# Tasks — an agent without MCP is not told it has nothing

Implementation is a later window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task.

**This change is Hub-Python-only.** No UI file is modified, so the committed bundle in
`hub/hub/static/ui` is not rebuilt and the TypeScript lint set is not required — say so in the log
rather than passing over it in silence.

**Two decisions in §2 and §3 are deliberately open** (`design.md` D5). The delta requires the rule,
not the mechanism. Choose the mechanism against a running Hub and record which and why; do not
treat the open choice as permission to skip the requirement.

## 1. The notice tells the truth

- [ ] 1.1 Replace the non-MCP branch of `access_path_notice` (`hub/hub/launchability.py:325-330`).
  It currently states that no AgentWeave tool surface is available. The replacement states that the
  capability plane is reachable over HTTP and names four things: the base address (from `HUB_URL`),
  the environment variable holding the credential (`AW_RUN_TOKEN`), the `Authorization: Bearer`
  shape, and the route prefix `/api/v1/agent-actions`.
- [ ] 1.2 **Name the variables; never interpolate their values.** `design.md` D4 and the delta's
  "The credential is named and not disclosed" scenario. The notice is prepended to the turn prompt
  at `hub/hub/api/v1/agent_trigger.py:1006-1007` and the prompt is durable. The difference between
  correct and a leak is one f-string.
- [ ] 1.3 Keep the two true sentences the current branch already carries — that inbound content is
  already in the turn and needs no retrieval. They were right; only the denial was wrong.
- [ ] 1.4 Delete the comment at `hub/hub/launchability.py:321-324` or rewrite it. It explains why
  the branch names no CLI commands, which stays true, but it currently reads as the justification
  for the branch being empty. Leave the history, drop the implication.
- [ ] 1.5 Test in `hub/tests/` asserting the non-MCP notice names `AW_RUN_TOKEN` and
  `/api/v1/agent-actions`, and — the half that actually catches the leak — that a notice rendered
  with a known token value does **not** contain that value.

## 2. The operations are described for this access path

- [ ] 2.1 Extend `_tool_surface_lines` (`hub/hub/api/v1/agents.py:884`) to render for an access
  path, defaulting to the MCP rendering so no existing call site changes meaning. One source, two
  renderings (`design.md` D3) — do **not** write a second list, and do not reuse
  `src/agentweave/tool_surface.py`, which has zero importers and lives in the other package.
- [ ] 2.2 Pass the run's access path through at the injection site,
  `hub/hub/api/v1/agents.py:1543`. The path is already resolved for the run at
  `agent_trigger.py:1006`; the context materialisation must receive it rather than re-derive it, or
  the notice and the description can disagree about the same turn.
- [ ] 2.3 Extend `test_tool_surface_matches_server.py` to run its existing agreement check against
  **both** renderings. This is the whole reason `_tool_surface_lines` was chosen as the home; a
  rendering not covered by that test drifts the first time a tool is added, silently.
- [ ] 2.4 The HTTP rendering names method, path and the required body fields for each operation it
  describes. It does not restate validation rules — those come back as typed failures, and
  duplicating them here would create the second source of truth §2.1 exists to avoid.

## 3. The two adapter-only rules move into the contract

- [ ] 3.1 **Archiving.** `POST /jobs/{job_id}/archive`
  (`hub/hub/api/v1/agent_actions.py:764-777`) currently asks the operator nothing; the always-ask
  rule is in `hub/hub/mcp_server.py:815` alone. Move it to the route. Mechanism open (`design.md`
  D5): block on the operator's answer, or return a typed "direction required" failure carrying a
  request id the caller polls, matching how `/permission-requests`
  (`hub/hub/api/v1/agent_actions.py:887-954`) already works.
- [ ] 3.2 Whichever mechanism §3.1 chooses, `mcp_server.archive_job` stops holding the rule itself.
  Two independent confirmations for one archive is a worse product than none, and leaving both is
  how the rule silently diverges later.
- [ ] 3.3 Preserve the rule's actual content, not just a prompt: the confirmation is required
  **regardless of the run's permission posture**, and a standing `project.allow_agent_jobs`
  allowance does not satisfy it. That distinction is the entire point of design D18 and is easy to
  lose in a move.
- [ ] 3.4 Preserve the loop refusal — a job with a loop is archived by the operator only, never an
  agent. It is stated in `archive_job`'s docstring; confirm where it is actually enforced before
  assuming the route already has it.
- [ ] 3.5 **Waiting.** The contract must give an HTTP caller what `ask_user`
  (`hub/hub/mcp_server.py:306-472`) gives an MCP caller: a way to wait, answers in the order asked,
  *declined* distinguished from *expired*, and a way to report the wait ended. Mechanism open
  (`design.md` D5) — a long-held request, or a documented poll-and-report protocol that §2's HTTP
  rendering states explicitly and that `ask_user` is then re-expressed over.
- [ ] 3.6 The wait-ended report is load-bearing and is the easiest of the four to drop: without it a
  parked task goes on claiming somebody is waiting. `hub/hub/mcp_server.py` sends it for expired
  questions only, deliberately — a decline is a decision the operator handed back, not silence.
  Keep that distinction wherever the rule lands.
- [ ] 3.7 Tests that reach the routes **directly**, without the adapter, and assert both rules hold.
  A test that exercises the MCP tool proves nothing here — the defect is that the tool is where the
  rule lives. `hub/tests/test_agent_actions_governed.py` already reaches them this way with a bearer
  run token; extend it rather than starting a new file.
- [ ] 3.8 **`test_agent_actions_governed.py:137-140` has to change, and read why before changing
  it.** It archives over HTTP with only the standing allowance and asserts `200`, under a comment
  stating that archiving is governed by the same allowance as every other job mutation — the exact
  opposite of what `archive_job`'s docstring and design D18 say. It is not a stale assertion; it is
  the other side of a live disagreement (`proposal.md`, "One thing this proposal does not decide").
  Do not flip it silently. If the operator's answer is D18, change the assertion **and** the comment,
  and say in the log that a green test was asserting the behaviour this change removes. If the
  operator's answer is the allowance, this task and §3.1–§3.4 collapse into deleting
  `mcp_server.py:815` instead.

## 4. Docs

- [ ] 4.1 `docs/architecture/overview.md:18-19` claims three adapters (HTTP, MCP, agent CLI). Two
  exist. Correct it to two and, since HTTP is now genuinely agent-reachable, elaborate the HTTP half
  — it is currently true and explained nowhere.
- [ ] 4.2 Do **not** touch `.claude/skills/copilot-test-setup/SKILL.md` in this change. It describes
  a watchdog architecture deleted on 2026-08-03 and needs deleting or rewriting, but it belongs to
  the Copilot change; doing it here would mix the two changes this proposal separated on purpose.

## 5. Verification — including the two things no round could check

- [ ] 5.1 `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`, `mypy src/`. Tests under `py -3.11`, never bare `python`. Say in the log that
  the TypeScript set was not required and why (no UI file changed).
- [ ] 5.2 `pytest hub/tests/ -v`.
- [ ] 5.3 **Drive it.** `proposal.md` names two claims that are source readings and nothing more,
  because this window could not start a Hub. First: that a request to `/api/v1/agent-actions/*`
  carrying `AW_RUN_TOKEN` as a bearer token succeeds **from inside a spawned run's own environment**
  — a real child process, over a real socket, with the `HUB_URL` the Hub computed for it at
  `agent_trigger.py:1090-1114`. The in-process ASGI tests
  (`hub/tests/test_agent_actions_governed.py:20-34` mints a run row and sends
  `Authorization: Bearer`) already establish that the *route and its auth* work, so that half is
  covered and this task is not re-proving it. What no test covers is the two things only a spawn
  exercises: that `HUB_URL` names an address the child can actually reach, and that the token in the
  child's environment is the one whose digest the run row holds.
- [ ] 5.4 Then drive the product, not the argument: start a real run on the `cli` access path
  (`hub_client: "cli"` — per `proposal.md` that is the only way to reach this branch today), give it
  work that needs the plane, and read what it does. The question is not whether the notice renders.
  It is whether a model that reads it goes on to make a successful request. Cheap models are the
  standing rule for drives.
- [ ] 5.5 Record the drive as a finding in `scripts/drive/FINDINGS.md` whether it worked or not. A
  drive that confirms the change is as much evidence as one that breaks it, and this repository's
  dominant failure mode is a change that passes its tests and cannot fire in production.
