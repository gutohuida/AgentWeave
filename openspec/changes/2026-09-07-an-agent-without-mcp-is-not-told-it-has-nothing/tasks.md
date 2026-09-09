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

- [x] 1.1 Replace the non-MCP branch of `access_path_notice` (`hub/hub/launchability.py:325-330`).
  It currently states that no AgentWeave tool surface is available. The replacement states that the
  capability plane is reachable over HTTP and names four things: the base address (from `HUB_URL`),
  the environment variable holding the credential (`AW_RUN_TOKEN`), the `Authorization: Bearer`
  shape, and the route prefix `/api/v1/agent-actions`.
- [x] 1.2 **Name the variables; never interpolate their values.** `design.md` D4 and the delta's
  "The credential is named and not disclosed" scenario. The notice is prepended to the turn prompt
  at `hub/hub/api/v1/agent_trigger.py:1006-1007` and the prompt is durable. The difference between
  correct and a leak is one f-string.
- [x] 1.3 Keep the two true sentences the current branch already carries — that inbound content is
  already in the turn and needs no retrieval. They were right; only the denial was wrong.
- [x] 1.4 Delete the comment at `hub/hub/launchability.py:321-324` or rewrite it. It explains why
  the branch names no CLI commands, which stays true, but it currently reads as the justification
  for the branch being empty. Leave the history, drop the implication.
- [x] 1.5 Test in `hub/tests/` asserting the non-MCP notice names `AW_RUN_TOKEN` and
  `/api/v1/agent-actions`, and — the half that actually catches the leak — that a notice rendered
  with a known token value does **not** contain that value.

## 2. The operations are described for this access path

- [x] 2.1 Extend `_tool_surface_lines` (`hub/hub/api/v1/agents.py:884`) to render for an access
  path, defaulting to the MCP rendering so no existing call site changes meaning. One source, two
  renderings (`design.md` D3) — do **not** write a second list, and do not reuse
  `src/agentweave/tool_surface.py`, which has zero importers and lives in the other package.
- [x] 2.2 Pass the run's access path into the render, so the notice and the description cannot
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
- [x] 2.3 Extend `test_tool_surface_matches_server.py` to run its existing agreement check against
  **both** renderings. This is the whole reason `_tool_surface_lines` was chosen as the home; a
  rendering not covered by that test drifts the first time a tool is added, silently.
- [x] 2.4 The HTTP rendering names method, path and the required body fields for each operation it
  describes. It does not restate validation rules — those come back as typed failures, and
  duplicating them here would create the second source of truth §2.1 exists to avoid.

## 3. The two adapter-only rules move into the contract

- [x] 3.1 **Archiving.** `POST /jobs/{job_id}/archive`
  (`hub/hub/api/v1/agent_actions.py:764-777`) currently asks the operator nothing; the always-ask
  rule is in `hub/hub/mcp_server.py:815` alone. Move it to the route. Mechanism open (`design.md`
  D5): block on the operator's answer, or return a typed "direction required" failure carrying a
  request id the caller polls, matching how `/permission-requests`
  (`hub/hub/api/v1/agent_actions.py:887-954`) already works.
- [x] 3.2 Whichever mechanism §3.1 chooses, `mcp_server.archive_job` stops holding the rule itself.
  Two independent confirmations for one archive is a worse product than none, and leaving both is
  how the rule silently diverges later.
- [x] 3.3 Preserve the rule's actual content, not just a prompt: the confirmation is required
  **regardless of the run's permission posture**, and a standing `project.allow_agent_jobs`
  allowance does not satisfy it. That distinction is the entire point of design D18 and is easy to
  lose in a move.
- [x] 3.4 Preserve the loop refusal — a job with a loop is archived by the operator only, never an
  agent. It is stated in `archive_job`'s docstring; confirm where it is actually enforced before
  assuming the route already has it.
- [x] 3.5 **Waiting — and read `design.md` D6 before starting, because round 2 cut this task
  down.** Ordering, the decline/expiry distinction, the deadline stamp and the task park are already
  the routes' (`hub/hub/api/v1/agent_actions.py:440-529`, `hub/hub/schemas/questions.py:65-77`), and
  an unreported wait is swept at the run boundary (`hub/hub/run_divergence.py:644`). Do **not**
  reimplement any of that. What is missing is two things: the contract offers no way to wait, and it
  never discloses the deadline it stamps. Mechanism open (`design.md` D5) — a long-held request, or
  a documented poll-and-report protocol that §2's HTTP rendering states explicitly and that
  `ask_user` is then re-expressed over.
- [x] 3.6 **Disclose `wait_expires_at`.** It is written at `hub/hub/api/v1/agent_actions.py:496`
  and is on no response schema, so the caller is judged against a deadline it was never shown
  (`hub/hub/run_task_binding.py:817` is the judgement). Put it on the question response. Then
  consider whether `mcp_server.QUESTION_ANSWER_TIMEOUT` (`:891`) should read the Hub's stamp instead
  of recomputing its own copy of `QUESTION_WAIT_DEFAULT` (`agent_trigger.py:501`) — two literals
  reading `240` in two modules that may not import each other is the same duplication this change is
  about, one layer down. Not required by the delta; note the decision either way.
- [x] 3.7 The wait-ended report is load-bearing: without it a parked task goes on claiming somebody
  is waiting until the run ends. `hub/hub/mcp_server.py` sends it for expired questions only,
  deliberately — a decline is a decision the operator handed back, not silence. Keep that
  distinction wherever the rule lands.
- [x] 3.8 Tests that reach the routes **directly**, without the adapter, and assert both rules hold.
  A test that exercises the MCP tool proves nothing here — the defect is that the tool is where the
  rule lives. `hub/tests/test_agent_actions_governed.py` already reaches them this way with a bearer
  run token; extend it rather than starting a new file.
- [x] 3.9 **`test_agent_actions_governed.py:137-140` has to change, and read why before changing
  it.** It archives over HTTP with only the standing allowance and asserts `200`, under a comment
  stating that archiving is governed by the same allowance as every other job mutation — the exact
  opposite of what `archive_job`'s docstring and design D18 say. It is not a stale assertion; it is
  the other side of a live disagreement (`proposal.md`, "One thing this proposal does not decide").
  Do not flip it silently. If the operator's answer is D18, change the assertion **and** the comment,
  and say in the log that a green test was asserting the behaviour this change removes. If the
  operator's answer is the allowance, this task and §3.1–§3.4 collapse into deleting
  `mcp_server.py:815` instead.

### What §3 decided, and why — written 2026-09-09 by the implementing window

**The mechanism (`design.md` D5, archiving).** The route returns a typed failure and the caller
polls; it does not block on the operator. Three reasons, in `hub/hub/operator_direction.py`'s own
docstring: `/permission-requests` already works this way and the adapter's `_ask_operator` is
already a poll loop over it, so this is one protocol on the plane rather than two and the operator's
card is the shipped one; a blocking route would hold an `AsyncSession`, and so a pooled connection,
for the whole operator budget, which on SQLite is the pool F295 is about; and the waiting then
belongs to the caller, which is the point — an HTTP agent performs what the injected tool performs
for an MCP one, from the description §2 renders.

The refusal is `409` with `code: operator_direction_required`, a `permission_request_id` and a
`poll` address. `409` rather than `403` deliberately: nothing has been denied, and the state that
blocks the request is one the operator can change. A denial afterwards **is** `403`
(`code: operator_refused`).

**Where the rule landed.** In `jobs.archive_job` itself, not in the agent-actions adapter route,
which delegates to it. That makes the rule reach every caller of the contract by the same code, and
it puts the gate *after* the existence, already-archived and loop checks — so a card is only ever
opened for an archive that would otherwise have happened. Asking a person to authorise a 404 is
asking them to read something meaningless.

**§3.6's second half, decided and not done.** `mcp_server.QUESTION_ANSWER_TIMEOUT` keeps computing
its own monotonic deadline from `AW_QUESTION_TIMEOUT` and does **not** read the Hub's stamp. Reading
it would convert an absolute instant from another process into a local monotonic deadline, which is
exactly the cross-process clock comparison `_record_the_wait_and_park`'s docstring says the design
avoids — and the tool's deadline being *later* than the Hub's stamp is what makes the `wait-ended`
refusal able to reject a forged early report and never a genuine one. The duplication that remains
is the literal `240`, and it is already pinned: `test_question_wait_resolution.py:39` asserts the two
agree. Disclosure was for the caller that has neither copy, which is the HTTP one.

**§3.9's answer: D18.** The operator settled it by approving a proposal that states the position in
its own text and a delta that states it as a scenario — *"Archiving scheduled work is directed, on
either path"*. So `test_agent_actions_governed.py`'s archive block was flipped, comment and all, and
a green test was asserting the behaviour this change removes. It is not collapsed into deleting
`mcp_server.py:815`.

**Eleven mutations, eleven named victims** (`testbed/scratch/mutate_c2_contract.py`, uncommitted;
every file md5-restored and the tree's shape re-checked after each). Every test written or changed
here is named by at least one. The one worth keeping: relabelling the archive's `http_note` as
`detail` named nobody, correctly — `_http_lines` renders `detail` too, so the text was still there
on the HTTP path. The mutation was replaced with one that removes the note.

## 4. The access path a run is told about is one it actually has

Added by round 2 (`design.md` D7). Without this section the change corrects a notice on the one
path the operator's own deployment never takes.

**Round 3 added §4.7–§4.9 and a constraint on §4.1, not a fourth open decision.** The access path
decides the run's permission posture as well as its notice (`design.md` D9), so the mechanism chosen
here moves containment whether or not anyone means it to. Choose it knowing that.

**The mechanism, chosen 2026-09-09 against a real harness, and why.** None of `design.md` D7's
three. A fourth: **the Hub separates what a run is *given* from what it is *told*, and the second
follows grounds while the first stays the operator's.**

- `resolve_access_path(runner, override)` — what the run is **given**. Unchanged behaviour:
  unconditional `"mcp"` for an injectable runner, moved only by `hub_client`. It decides
  `mcp_command`, and through that the permission posture (D9).
- `described_access_path(access_path, override=…, harness_honoured_mcp=…)` — what the run is
  **told**. Asserts the tool surface only on grounds: the operator said `mcp`, or the harness has
  been *seen* honouring an injected server.
- The observation is `Run.mcp_adapter_online_at` (migration `0102`), stamped by
  `POST /api/v1/agent-actions/mcp-adapter-online`, which `hub/hub/mcp_server.py` posts **before it
  serves**. This process existing is the measurement. Read per agent, per project, positive
  evidence only — there is no negative form, because a harness that ignores the configuration is
  silent, and silence is exactly what "no grounds" means.

Why not D7's three. **The probe** answers the wrong question and is self-defeating (D10) — deleted
rather than re-aimed, along with `_probe_cache` and `PROBEABLE_RUNNERS`. **`hub_client` made
operator-visible** is a UI change in an otherwise Hub-Python-only change, and D9 shows it would make
a control that says nothing about permissions widen them. **Describing both paths** does not satisfy
the requirement at all: it still asserts a tool surface with no grounds, which is the sentence the
delta forbids.

Why the split is the answer to D9's condition rather than a way around it. A **declaration** by the
operator moves containment, because it is theirs to move and it is declared. An **inference** by the
Hub moves only the wording. The delta's scenario is then satisfied literally and is testable as a
difference between two runs, which §4.8 is.

The bootstrap cost is one turn: a fresh agent on a permitted harness reads the HTTP form on its
first run while the server is in fact injected, and earns the MCP wording from the second. That is
why the evidence is gathered at adapter startup rather than from a tool call — a model told to use
HTTP may never reach for a tool, and tool-call evidence would leave a good harness undescribed
forever.

- [x] 4.1 `resolve_access_path` (`hub/hub/launchability.py`) returned `"mcp"` unconditionally for
  every runner in `MCP_INJECTABLE_RUNNERS`. It still does — that is what the run is *given* — and
  `described_access_path` now decides what it is *told*, on the grounds above. Chosen against a
  real `claude` harness (§4.9, `F299`) rather than on paper.
- [x] 4.2 The probe was not restored. `probe_mcp_registered`, `_probe_cache`, `_PROBE_TTL_SECONDS`
  and the `PROBEABLE_RUNNERS` alias are **deleted**, and `test_the_probe_is_gone_and_stays_gone`
  asserts they cannot come back unnoticed. D10's argument was not tested against a policy-blocked
  harness because it does not need to be: `mcp list` runs a process that was never given the
  config, so it answers the wrong question on both kinds of machine. The reasoning is now in
  `launchability.py`'s access-path comment, where the next person to reach for a subprocess reads
  it.
- [x] 4.3 An explicit statement stays authoritative in both directions and neither is inferred
  away: `hub_client: "cli"` gets `cli` (`test_an_explicit_cli_statement_is_what_the_run_is_given`),
  and `hub_client: "mcp"` is grounds on its own with nothing observed
  (`test_an_explicit_mcp_statement_is_grounds_on_its_own`, and the trigger-level
  `test_trigger_honours_an_explicit_mcp_statement_with_nothing_observed`).
- [x] 4.4 `hub/tests/conftest.py`'s autouse `_no_real_mcp_probe` is **removed**, not corrected — the
  probe it patched no longer exists. A comment stands where it was saying what it claimed and why
  that was false from `d279d22`. **The answer to "did any test believe it": no test path called the
  probe, so no test was exercising the `cli` path because of this fixture.** What the fixture
  actually did was patch a function nothing reached while telling every reader the opposite. Three
  tests *named* the probe and are dealt with in §4.5 and §4.7.
- [x] 4.5 `test_trigger_respects_explicit_mcp_override_without_probing` is **replaced, not
  deleted** — the behaviour it meant to guard is real, and now distinguishable. It became
  `test_trigger_honours_an_explicit_mcp_statement_with_nothing_observed`, whose negative half is
  §4.6's test: same agent shape, no override, and the MCP sentence is absent.
- [x] 4.6 `test_trigger_tells_a_run_with_no_grounds_the_http_form` — a `claude` agent, `hub_client`
  unset, nothing observed, asserted on the prompt the trigger actually builds. The mirror of §1.5
  and the one that covers the operator's deployment.
- [x] 4.7 `TestAccessPath` rewritten. Its docstring said the path "is probed per runner"; it now
  states the two questions and the two functions.
  `test_explicit_override_wins_without_probing` and `test_auto_override_is_treated_as_unset_and_probes`
  both guarded a call that could not happen for any input; each is replaced by one that asserts a
  *difference* (`auto` with and without grounds; an `mcp` statement against no statement).
  `test_injectable_runner_needs_no_global_registration` is **kept and updated deliberately**: the
  injection is still unconditional, and the second assertion is what §4 added — the same value no
  longer also asserts the tools are there.
- [x] 4.8 Decided separately and stated: **the inference does not move the posture.** A run with no
  grounds still gets `--mcp-config`, still gets `--permission-prompt-tool`, and still runs under
  `manual`; only the wording changed.
  `test_a_truer_description_does_not_widen_the_runs_permission` asserts it on the built argv, not on
  `mcp_command`, because the posture is decided two functions away from the flag it reads.
- [x] 4.9 **Driven, and the prediction holds — filed as `F299`.** Three real `claude` runs on Haiku:
  with `--permission-prompt-tool` naming an absent MCP tool, a `Read` succeeds and **every mutating
  call is denied** (`Write`, `PowerShell` and `Bash` all three), and the model reports it as *"a
  workspace establishment issue … contact your system administrator"*. The same denial without the
  approver flag produces *"I need permission to write the file"*. So the mirror is a **run that
  cannot act**, not a false sentence — and it blames the operator's machine.
  **The remedy is not this change's to choose.** Resolving to `cli` on an inference gives every
  unstated `claude` run `acceptEdits`, which has no path check at all; keeping `manual` without an
  approver denies everything anyway with nobody headless to ask. There is no non-widening,
  non-breaking option, and the delta says containment is the operator's. It is in
  `STATE-night.json`'s `decisions_for_user` with the drive attached. `hub_client: "cli"` is the
  one-line workaround that exists today, and what it silently buys is `acceptEdits`.

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
