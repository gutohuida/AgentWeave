# Tasks

**Cite symbols, not line numbers.** A legacy-annotation pass was editing
`hub/hub/launchability.py` in this tree on 2026-09-20 and has already moved the target string once.

> **R2 (2026-09-20) reworked groups 1, 2, 3 and 4.** Two product files are now in scope, not one
> (`hub/hub/api/v1/agents.py` joins `hub/hub/launchability.py`; see proposal Impact and design D6).
> Group 1's sweep has been **done** by R2 and its results are written in below, so the implementer
> verifies rather than discovers. Task 3.2 was a task that would have ticked green having proved
> nothing and now names the specific test to extend. Group 6's guard list gained the second file.

## 1. Establish the blast radius before editing anything

> **R2 ran 1.1 and 1.2 and recorded the answers.** Re-run them to confirm nothing moved — the tree
> has another agent editing `hub/hub/` — but do not treat finding what is written here as new work.

- [ ] 1.1 `grep -rn "no MCP tools this turn" .` across the **whole repository** (excluding
  `node_modules/`, `.git/`, `hub/hub/static/ui/`) and confirm the list below. Docs, skill templates
  and charter text count — the clause may be quoted where no test runs.

  **R2's result — one product occurrence, two test occurrences, and no doc, skill or charter quotes
  the clause.** Product: `hub/hub/launchability.py` (`access_path_notice`). Tests:
  `hub/tests/test_agent_trigger.py` ×2. Everything else is a *record* of the defect and must not be
  edited: `spec-queue/DECISIONS.md`, `spec-queue/APPROVALS.md`, `spec-queue/BACKLOG.html`,
  `spec-queue/review/review-2026-09-09.html`, `spec-queue/observations/2026-09-14-LoopEngine.md`,
  `scripts/drive/FINDINGS.md`, `.claude/autonomous/2026-09-09-day-log.md`, and this change's own
  four documents.

- [ ] 1.1b **R2 added.** Repeat the sweep for the *second* string,
  `grep -rn "No AgentWeave tools are injected this turn" .`. Product: `hub/hub/api/v1/agents.py`
  (`_tool_surface_lines`). Non-test consumer that will **silently go stale**, since nothing fails
  when it is missed: `scripts/drive/t_d1_0909_together.py`, whose detector is
  `injected = "No AgentWeave tools are injected this turn" in text`. Everything else is a stale
  fixture under `testbed/scratch/`, `.agentweave/tasks/` or a captured context file — leave them.

- [ ] 1.2 Read all four test files that reference `access_path_notice` —
  `hub/tests/test_agent_trigger.py`, `hub/tests/test_agent_facing_text.py`,
  `hub/tests/test_launchability.py`, `hub/tests/test_tool_surface_matches_server.py` — and confirm
  R2's reading below. The question is what each test would still prove after the edit.

  **R2's result.** `test_agent_trigger.py` — the only file pinning the clause, twice, in
  `test_trigger_injects_identity_env_and_tells_agent_the_access_path` and
  `test_a_run_without_mcp_is_described_the_operations_it_can_actually_perform`; **both leave
  `hub_client` unset**, so both sit on the no-grounds path with the server still injected, and the
  first asserts the injection three lines below the denial. `test_launchability.py` — pins the HTTP
  fields (`HUB_URL`, `AW_RUN_TOKEN`, `Authorization: Bearer`, `/api/v1/agent-actions`) and the
  *older* denial wordings, **not this clause**; see 3.2. `test_agent_facing_text.py` — pins neither;
  no edit expected. `test_tool_surface_matches_server.py` — asserts on the rendered context text and
  is where the `agents.py` assertion belongs; does not pin the preamble today.

- [ ] 1.3 Record the current no-MCP notice string **and the current `_tool_surface_lines` non-MCP
  preamble** verbatim in this file, so every later round can diff against what was actually there
  rather than against a remembered version.

## 2. The notice stops asserting

- [ ] 2.1 In `access_path_notice` (`hub/hub/launchability.py`), no-MCP branch: remove the clause
  claiming the run has no MCP tools this turn. Keep the base address, the route prefix, the
  credential variable name, its `Authorization: Bearer` presentation, the read-from-your-own-
  environment instruction, and the inbound-content sentence — each is required by the spec.
- [ ] 2.2 Leave the comment above that branch in place, including the paragraph prohibiting
  interpolation of the credential value. It explains a constraint the spec still carries.
- [ ] 2.3 Do not touch the MCP branch, `described_access_path`, `harness_has_honoured_mcp`,
  `resolve_access_path`, or anything in `agent_trigger.py`. **R2: `git diff --stat` must show
  exactly two product files — `hub/hub/launchability.py` and `hub/hub/api/v1/agents.py` — not the
  one R1 wrote here.**

- [ ] 2.4 **R2 added — the canonical context stops asserting too.** In `_tool_surface_lines`
  (`hub/hub/api/v1/agents.py`), the `else` (non-MCP) `preamble`: remove the claim that no
  AgentWeave tools are injected this turn, and restate the sentence positively rather than
  truncating it — *"so each capability below is one HTTP request instead"* has no subject once the
  clause is gone (design D6). Keep the `HUB_URL` address, the `Authorization: Bearer $AW_RUN_TOKEN`
  header, the read-both-values-out-of-your-own-process-environment instruction, the `*`-required and
  `{...}`-substitute conventions, and the JSON-and-`detail`-refusal sentence.

- [ ] 2.5 **R2 added.** Leave the comment above that `else` branch in place, including the paragraph
  on never interpolating credential values — it is the same prohibition 2.2 preserves in
  `launchability.py` and the spec still carries it. Do not touch `over_mcp`, the `if` branch,
  `_http_lines`, `_mcp_lines`, `_operations()`, or the `access_path: str = "mcp"` default.

- [ ] 2.6 **R2 added.** Update `scripts/drive/t_d1_0909_together.py`'s detector
  (`injected = "No AgentWeave tools are injected this turn" in text`) to match the new preamble, or
  rewrite it to key on something the change does not move. Nothing fails if this is skipped, which
  is exactly why it is a task: the script would report the opposite of the truth on the next drive.

## 3. The tests assert the absence of a claim

- [ ] 3.1 Restage `hub/tests/test_agent_trigger.py`'s two assertions (each currently
  `assert "no MCP tools this turn" in ...`) so each pairs a **negative** — no availability claim in
  the built prompt — with a **positive** on the plane content the requirement demands. Per design
  D5, a bare `not in` assertion passes against an empty prompt and is not acceptable.
- [ ] 3.2 **Rewritten by R2, because as written this task would have ticked green having proved
  nothing.** 1.2 establishes that **none** of the other three test files pins the removed clause, so
  "restage anything that pins it" finds nothing and closes. The real gap is the inverse: extend
  `hub/tests/test_launchability.py::test_a_run_without_mcp_is_not_told_it_cannot_act` — a test
  written to stop exactly this class of sentence, which the current clause walked past because it
  only checks the *older* denial wordings (`"no AgentWeave tool surface is available"`, `"cannot
  send messages"`). Add the current clause to what it refuses. Finding nothing to restage elsewhere
  is the correct outcome and should be written here as such, not left ambiguous.
- [ ] 3.3 Add one test that fails on the defect itself: a turn built for an agent with **no prior
  run carrying `mcp_adapter_online_at`**, asserting the prompt makes no claim that the tool surface
  is unavailable. This is the scenario `A run holding the tools is not told it is empty`. **R2
  checked: no test in `hub/tests/` today asserts on `mcp_adapter_online_at` together with the notice
  text, so this is genuinely absent rather than duplicated.** The existing
  `test_an_observed_harness_earns_the_mcp_description_for_the_next_run` sets the column and is the
  fixture to model the new test on.
- [ ] 3.3b **R2 added — the context side of 3.3, which the spec now names explicitly.** Assert that
  the same fresh-agent turn's **rendered canonical context** makes no claim that the tool surface is
  unavailable, paired with a positive on the HTTP content it must still carry. This is the
  scenario's `AND` clause about the canonical context, and
  `hub/tests/test_tool_surface_matches_server.py` already asserts on that text. Without this, the
  `agents.py` edit from 2.4 ships untested.
- [ ] 3.4 **Mutation check — R2 extended it to both files.** Restore the removed clause in
  `access_path_notice`, run the tests from 3.1, 3.2 and 3.3, and record here that they fail, with
  the count. **Then, separately, restore the removed clause in `_tool_surface_lines`' non-MCP
  preamble and confirm 3.3b fails, with the count** — a mutation on one file proves nothing about
  the other, and the `agents.py` edit is the half with no existing test pinning it. Revert both and
  confirm `git diff` over `hub/hub/launchability.py` and `hub/hub/api/v1/agents.py` shows only the
  intended edits. A test that passes both ways proves nothing.

## 4. The corpus

- [ ] 4.1 Apply the delta's two MODIFIED requirements to
  `openspec/specs/agent-capability-plane/spec.md` (via the normal sync at archive time, not by hand
  now). Confirm `openspec validate a-first-turn-is-not-told-it-has-nothing --strict` passes after
  every edit to the change.
- [ ] 4.2 Confirm the F301 prose correction carries **only** the mechanism, and that the
  requirement's conclusion (unreachable by the agent's own tools on the `cli` path) is unchanged and
  its SHALL is byte-identical to today's. `DECISIONS.md` 1d mandates the correction; it does not
  authorise reopening the conclusion. **R2 verified both: the second requirement's SHALL line
  diffs clean against `openspec/specs/`, and the live conclusion clause survives, relocated into
  the corrected paragraph as "The conclusion is unchanged: unreachable by the agent's own tools on
  the `cli` path."**
- [ ] 4.2b **R2 added.** `DECISIONS.md` 1d carries a *second* live verdict about this same notice —
  *"change the notice to instruct the `python -c` shape now"* — which this change does not carry.
  Confirm in the ledger edit that it is **superseded, not skipped**: 1d chose `python -c` because
  it was then the only shape `_decide` allowed, and the durable half of that verdict has since
  shipped, so the `curl` shape the notice already instructs is now allowed in both dialects (the
  measurement is in the proposal's **Why**, and R2 re-ran it at `d7f2694`). Do not silently drop it.
- [ ] 4.3 Update **F302**'s entry in `scripts/drive/FINDINGS.md` to `fixed <sha>` only once 2.1,
  **2.4**, 3.1 and 3.3 have all landed, and say in the same edit that `harness_has_honoured_mcp`'s
  permanent-positive latch (**F340**) is untouched. **R2: state what was fixed precisely — both
  false sentences were removed from the first turn. Do not write that the measured behaviour is
  closed.** The Architect kept to `curl` for ten runs *after* the notice healed, so removing the
  falsehood is necessary and is not shown to be sufficient; design D2's R2 dissent is the record of
  that, and claiming more here is the kind of tick this repo's discipline exists to prevent.

## 5. Quality gates, over CI's exact paths

- [ ] 5.1 `ruff check src/ hub/ tests/` — clean.
- [ ] 5.2 `black --check src/ hub/hub/ hub/tests/ tests/ --target-version py311` — clean.
- [ ] 5.3 `mypy src/` — clean. (No `src/` file changes here; run it anyway, because CI does.)
- [ ] 5.4 `hub/ui` is not built or linted, because nothing under `hub/ui/` is touched. Confirm that
  claim with `git diff --name-only` rather than asserting it.

## 6. What must not move

> **R2 caution on every `git diff` in this group.** On 2026-09-20 another agent held uncommitted
> edits in this same working tree to `hub/hub/launchability.py`, `hub/hub/runner_commands.py` and
> five files under `src/agentweave/`. A bare `git diff` will therefore show work that is not this
> change's, and 6.3's "byte-identical to `master`" will read as a violation when it is not. Diff
> named paths, and establish the pre-existing modifications before starting so they can be told
> apart from anything this change causes.

- [ ] 6.1 `py -3.11 -m pytest hub/tests/test_launchability.py hub/tests/test_agent_trigger.py
  hub/tests/test_agent_facing_text.py hub/tests/test_tool_surface_matches_server.py -q` — **write
  the pass/fail counts inline in this task.**
- [ ] 6.2 `py -3.11 -m pytest hub/tests/ -q` in full — **write the actual counts and the duration
  inline in this task.** Per **F392**, a tick on this line citing a log entry that does not exist is
  the exact process defect that let a three-test regression reach `master`; if the number is not
  written here, this task is not done.
- [ ] 6.3 Confirm no permission posture changed: `grep -n "acceptEdits\|permission-prompt-tool"` in
  `hub/hub/runner_commands.py` is byte-identical to `master`, and `git diff` touches neither
  `runner_commands.py` nor `mcp_server.py`. The spec scenario *"A truer description does not
  silently widen permission"* is the requirement this guards. **R2: `agent_trigger.py` must also be
  absent from the diff — it holds both `access_path` and `described_path`, and the whole change
  rests on those two staying separate. And within `hub/hub/api/v1/agents.py`, confirm the diff is
  the one `preamble` string: `git diff hub/hub/api/v1/agents.py` must show no change to `over_mcp`,
  `_http_lines`, `_mcp_lines`, `_operations()` or any route handler.**
- [ ] 6.4 Confirm nothing under `hub/ui/src/` or `hub/hub/static/ui/` is in the diff, so no bundle
  refresh is owed and nothing reaches the operator's live app on its next reload.

## 7. The measurement the operator's D2 decision depends on

> **Added 2026-09-20 on the operator's decision** (design D2, *"ship this shape, then measure"*).
> **This group runs after groups 1-6 have landed**, because the falsehood is a competing cause that
> has to be removed before the question can be asked at all.
>
> **The change is not archived until 7.4 carries a recorded result.** R2's dissent is held open on
> this measurement; a "decide after measuring" that never measures is the F392 defect wearing a
> different hat, and this group exists so that cannot happen quietly.
>
> **The question, stated so it cannot drift:** with no false sentence in front of it, does a fresh
> agent's **first turn** use the `agentweave` MCP tools, or does it still shell out to `curl`? R2
> reads the LoopEngine record as the positive HTTP steer causing the `curl` habit; the competing
> reading is that the Architect simply kept a working method it had already paid for. **Only a
> first turn separates them**, because it is the one moment the steer acts with no learned method
> behind it.

- [ ] 7.1 On a **throwaway Hub** — never `:8000`, never the operator's database; a scratch profile
  under `testbed/scratch/` per `.claude/reference/hubs.md` — create a **brand-new agent** whose
  `Run.mcp_adapter_online_at` has never been set, so `described_access_path` takes the no-grounds
  branch while `resolve_access_path` still injects the server. Confirm that state in the database
  before the turn rather than assuming it; an agent that has already earned grounds measures
  nothing.
- [ ] 7.2 Give it **one** instruction that requires a capability-plane operation it cannot fake —
  creating a task, or sending a message — and let it take exactly one turn. **Bind Haiku**
  (standing directive: real agent turns in a drive always bind a cheap model). Record the run id.
- [ ] 7.3 Repeat 7.1-7.2 with **at least three** distinct fresh agents. One turn is one sample and
  the behaviour is stochastic; a single run settles nothing in either direction and must not be
  written up as if it did.
- [ ] 7.4 For each run, record inline here: the run id, whether the first turn called an
  `mcp__agentweave__*` tool or shelled out, and the transcript line that shows which. **Write the
  counts, not a conclusion** — e.g. "3 of 3 first turns called `create_task` over MCP".
- [ ] 7.5 State the verdict against the **pre-change baseline**, which is the 2026-09-14 LoopEngine
  observation: **4 of 4 agents took the HTTP path on their first turn**
  (`openspec/explorations/2026-09-14-the-first-turn-has-its-tools.md`).
  - **Fresh agents now use the MCP tools** → the falsehood was the cause, the conditional text is
    unnecessary, and D2's declined alternative closes. Say so in `DECISIONS.md` under a dated
    heading, and only then may F302 be marked `fixed` without qualification.
  - **Fresh agents still shell out** → the positive HTTP steer is the cause, R2's dissent is
    vindicated, and the conditional text becomes a live proposal. **File it as a new finding rather
    than widening this change**, which will already be archived.
  - **Mixed** → record the split and leave D2 open. Do not round a mixed result to either verdict.
- [ ] 7.6 Whatever the outcome, append the measurement to **F302**'s entry in
  `scripts/drive/FINDINGS.md`, and correct the 2026-09-14 exploration's "the notice heals on turn
  two; the agent does not" line if 7.5 shows that framing was about a learned method rather than
  the steer. An exploration that keeps a superseded reading is how the next round inherits it.
