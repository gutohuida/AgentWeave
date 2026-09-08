# Tasks — an agent without MCP is not told it has nothing

Implementation is a later window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task.

**This change is Hub-Python-only.** No UI file is modified, so the committed bundle in
`hub/hub/static/ui` is not rebuilt and the TypeScript lint set is not required — say so in the log
rather than passing over it in silence.

**Three decisions — in §2, §3 and §4 — are deliberately open** (`design.md` D5, D7). The delta requires the rule,
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
- [ ] 2.2 Pass the run's access path into the render, so the notice and the description cannot
  disagree about the same turn. **Rewritten by the third review, 2026-09-08: this task had the
  ordering backwards.** It said the path *"is already resolved for the run at
  `agent_trigger.py:1006`"* and that the materialisation *"must receive it"* — but the
  materialisation happens **46 lines earlier**, at `agent_trigger.py:960`
  (`rendered_context = await _render_hub_agent_context(...)`), and `resolve_access_path` is not
  called until `:1006`. There is nothing to receive at `:960`; the value does not exist yet. What
  to do instead:
  - **Hoist `resolve_access_path` above the materialisation.** Its three arguments are all bound far
    earlier — `config` at `agent_trigger.py:640`, `probe` at `:647`, `runner` at `:648` — so the call
    can move above `:960` and its single value be reused at `:1006`. Nothing reads `access_path`
    before `:1006` today, so the hoist is safe; verify that on the checkout rather than trusting it.
  - **Give `_render_hub_agent_context` (`agents.py:1073`) an `access_path` parameter defaulting to
    the MCP rendering**, exactly as 2.1 does for `_tool_surface_lines`, and thread it to the
    injection site at `agents.py:1543` (`lines.extend(_tool_surface_lines(...))`).
  - **Say what the other two production callers pass.** `_render_hub_agent_context` has three, not
    one: `agents.py:1769`, `agents.py:2143` and `agent_trigger.py:960`. 2.1 protects its call sites
    with a default and this task said nothing equivalent. A `GET .../context` route left rendering
    MCP wording for an agent whose next run takes the HTTP path reintroduces precisely the
    disagreement this task exists to prevent — decide whether those two resolve the path themselves
    or deliberately keep the default, and write the reason down.
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
- [ ] 3.5 **Waiting — and read `design.md` D6 before starting, because round 2 cut this task
  down.** Ordering, the decline/expiry distinction, the deadline stamp and the task park are already
  the routes' (`hub/hub/api/v1/agent_actions.py:440-529`, `hub/hub/schemas/questions.py:65-77`), and
  an unreported wait is swept at the run boundary (`hub/hub/run_divergence.py:644`). Do **not**
  reimplement any of that. What is missing is two things: the contract offers no way to wait, and it
  never discloses the deadline it stamps. Mechanism open (`design.md` D5) — a long-held request, or
  a documented poll-and-report protocol that §2's HTTP rendering states explicitly and that
  `ask_user` is then re-expressed over.
- [ ] 3.6 **Disclose `wait_expires_at`.** It is written at `hub/hub/api/v1/agent_actions.py:496`
  and is on no response schema, so the caller is judged against a deadline it was never shown
  (`hub/hub/run_task_binding.py:817` is the judgement). Put it on the question response. Then
  consider whether `mcp_server.QUESTION_ANSWER_TIMEOUT` (`:891`) should read the Hub's stamp instead
  of recomputing its own copy of `QUESTION_WAIT_DEFAULT` (`agent_trigger.py:501`) — two literals
  reading `240` in two modules that may not import each other is the same duplication this change is
  about, one layer down. Not required by the delta; note the decision either way.
- [ ] 3.7 The wait-ended report is load-bearing: without it a parked task goes on claiming somebody
  is waiting until the run ends. `hub/hub/mcp_server.py` sends it for expired questions only,
  deliberately — a decline is a decision the operator handed back, not silence. Keep that
  distinction wherever the rule lands.
- [ ] 3.8 Tests that reach the routes **directly**, without the adapter, and assert both rules hold.
  A test that exercises the MCP tool proves nothing here — the defect is that the tool is where the
  rule lives. `hub/tests/test_agent_actions_governed.py` already reaches them this way with a bearer
  run token; extend it rather than starting a new file.
- [ ] 3.9 **`test_agent_actions_governed.py:137-140` has to change, and read why before changing
  it.** It archives over HTTP with only the standing allowance and asserts `200`, under a comment
  stating that archiving is governed by the same allowance as every other job mutation — the exact
  opposite of what `archive_job`'s docstring and design D18 say. It is not a stale assertion; it is
  the other side of a live disagreement (`proposal.md`, "One thing this proposal does not decide").
  Do not flip it silently. If the operator's answer is D18, change the assertion **and** the comment,
  and say in the log that a green test was asserting the behaviour this change removes. If the
  operator's answer is the allowance, this task and §3.1–§3.4 collapse into deleting
  `mcp_server.py:815` instead.

## 4. The access path a run is told about is one it actually has

Added by round 2 (`design.md` D7). Without this section the change corrects a notice on the one
path the operator's own deployment never takes.

**Round 3 added §4.7–§4.9 and a constraint on §4.1, not a fourth open decision.** The access path
decides the run's permission posture as well as its notice (`design.md` D9), so the mechanism chosen
here moves containment whether or not anyone means it to. Choose it knowing that.

- [ ] 4.1 `resolve_access_path` (`hub/hub/launchability.py:237-245`) returns `"mcp"` unconditionally
  for every runner in `MCP_INJECTABLE_RUNNERS`. Give it grounds. Three mechanisms are laid out in
  `design.md` D7 — re-aim the probe, make `hub_client` operator-visible and authoritative, or
  describe both paths — and the delta requires the property, not the mechanism. Choose against a
  running Hub and record why.
- [ ] 4.2 If the probe is chosen, `probe_mcp_registered` (`:207-234`) is still there and still
  unused. It shells `<cli> mcp list`; **verify what that actually reports on a harness whose MCP is
  disabled by policy before relying on it** — a probe that reports "registered" for a server the
  harness will refuse to start is the current bug with a subprocess in front of it. **Round 3 found
  a reason to expect it fails on a permitted harness too, before that check ever runs**
  (`design.md` D10): it runs a *separate* process with no `--mcp-config`, so it cannot see the
  server the Hub injects on the turn's own command line, and a `False` from it resolves the path to
  `cli` — which stops the injection it was asked about. Do not restore it unchanged; if a probe is
  wanted it must ask whether the harness will honour an injected server, which `mcp list` does not
  answer.
- [ ] 4.3 Whatever is chosen must keep an explicit operator statement authoritative: an operator who
  says `cli` gets `cli` without being probed out of it.
- [ ] 4.4 **`hub/tests/conftest.py:496-507`.** Its autouse fixture patches `probe_mcp_registered`
  to `False` under a docstring claiming every test therefore gets the `cli` access path. That has
  been false since `d279d22`. Correct the docstring, and check whether any test was written
  believing it — a test that meant to exercise the `cli` path has been exercising `mcp` instead.
- [ ] 4.5 **`hub/tests/test_agent_trigger.py:793-830`.** It patches the probe to raise and asserts
  an explicit `hub_client: "mcp"` yields the MCP notice. Nothing probes, so the raise cannot fire,
  and with no override the outcome is identical — the assertion cannot distinguish the branch it
  names. Either make it distinguish (assert the *absence* of the MCP notice for a run with no
  grounds) or delete it, and say which in the log. Do not leave it green and meaningless; that is
  `F190` again.
- [ ] 4.6 A test that a run with no grounds for MCP is told the HTTP form — the mirror of §1.5, and
  the one that actually covers the operator's deployment.

- [ ] 4.7 **`hub/tests/test_launchability.py:390-429`, the third file round 2 did not count.** Its
  `TestAccessPath` docstring states the path "is probed per runner rather than assumed"; nothing
  probes. `test_explicit_override_wins_without_probing` (`:406-413`) guards against a call that
  cannot happen for any input, and `test_auto_override_is_treated_as_unset_and_probes` (`:421-423`)
  passes identically with the probe patched `True` or `False`. Fix the docstring; make both tests
  distinguish the branch they name, or delete them. Keep
  `test_injectable_runner_needs_no_global_registration` (`:424-429`) — it is the only place the
  current unconditional behaviour is pinned, and whatever §4.1 chooses must update it deliberately.
- [ ] 4.8 **Whichever mechanism §4.1 chooses, decide the permission posture separately and say so.**
  `mcp_command` is set if and only if the access path is `"mcp"`
  (`hub/hub/api/v1/agent_trigger.py:1025-1028`), and `_build_claude_command` reads it to choose
  between `--permission-mode manual` plus `--permission-prompt-tool` and a bare
  `--permission-mode acceptEdits` (`hub/hub/runner_commands.py:219-222`, `:244-254`). Measured, in
  `design.md` D9. So moving a run to the `cli` path removes the workspace check on its file and
  shell actions. Do not let a change about honest notices become a change about containment by
  accident; the delta's "A truer description does not silently widen permission" scenario is this
  task's test.
- [ ] 4.9 **The approver flag names an MCP tool, and the mirror deployment cannot provide it.** With
  `hub_client` unset and a `claude` runner, the path resolves to `"mcp"`, so the Hub emits
  `--permission-prompt-tool mcp__agentweave__approve_tool_call` into a harness whose MCP is blocked.
  `hub/hub/runner_commands.py:245-248` states what that does: "naming an approver that will not be
  there makes every tool call fail". If that is right, the mirror defect is not a false sentence —
  it is a run that cannot act. Establish it on a real harness (§6.5) before choosing a mechanism,
  because a fix that only corrects the notice would leave such a run broken in the same way.

## 5. Docs

- [ ] 5.1 `docs/architecture/overview.md:18-19` claims three adapters (HTTP, MCP, agent CLI). Two
  exist. Correct it to two and, since HTTP is now genuinely agent-reachable, elaborate the HTTP half
  — it is currently true and explained nowhere.
- [ ] 5.2 Do **not** touch `.claude/skills/copilot-test-setup/SKILL.md` in this change. It describes
  a watchdog architecture deleted on 2026-08-03 and needs deleting or rewriting, but it belongs to
  the Copilot change; doing it here would mix the two changes this proposal separated on purpose.

## 6. Verification — including the two things no round could check

- [ ] 6.1 `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`, `mypy src/`. Tests under `py -3.11`, never bare `python`. Say in the log that
  the TypeScript set was not required and why (no UI file changed).
- [ ] 6.2 `pytest hub/tests/ -v`.
- [ ] 6.3 **Drive it.** `proposal.md` names two claims that are source readings and nothing more,
  because this window could not start a Hub. First: that a request to `/api/v1/agent-actions/*`
  carrying `AW_RUN_TOKEN` as a bearer token succeeds **from inside a spawned run's own environment**
  — a real child process, over a real socket, with the `HUB_URL` the Hub computed for it at
  `agent_trigger.py:1090-1114`. The in-process ASGI tests
  (`hub/tests/test_agent_actions_governed.py:20-34` mints a run row and sends
  `Authorization: Bearer`) already establish that the *route and its auth* work, so that half is
  covered and this task is not re-proving it. What no test covers is the two things only a spawn
  exercises: that `HUB_URL` names an address the child can actually reach, and that the token in the
  child's environment is the one whose digest the run row holds.
- [ ] 6.4 Then drive the product, not the argument: start a real run on the `cli` access path
  (`hub_client: "cli"` — per `proposal.md` that is the only way to reach this branch today), give it
  work that needs the plane, and read what it does. The question is not whether the notice renders.
  It is whether a model that reads it goes on to make a successful request. Cheap models are the
  standing rule for drives.
- [ ] 6.5 **Drive the mirror too** (§4). The check that matters for the deployment this change was
  written for is a run whose harness will not honour the injected MCP config: it must be told the
  HTTP form, not told to call tools that are not there. If that harness cannot be produced on this
  machine, say so in the log and record what was substituted — a `claude` run launched with the
  injected server config removed is the nearest honest approximation, and it is not the same thing.
  **Read the run's tool calls, not only its prose.** Round 3's open question (§4.9, `design.md` D9)
  is whether such a run can act at all: the Hub emits `--permission-prompt-tool` naming an MCP tool
  the harness cannot provide, and `runner_commands.py:245-248` predicts every tool call then fails.
  That prediction is the repository's own and has never been driven. Record what actually happens —
  it decides whether the mirror is a wording defect or a broken run.
- [ ] 6.6 Record the drive as a finding in `scripts/drive/FINDINGS.md` whether it worked or not. A
  drive that confirms the change is as much evidence as one that breaks it, and this repository's
  dominant failure mode is a change that passes its tests and cannot fire in production.
