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

- [x] 1.1 `grep -rn "no MCP tools this turn" .` across the **whole repository** (excluding
  `node_modules/`, `.git/`, `hub/hub/static/ui/`) and confirm the list below. Docs, skill templates
  and charter text count — the clause may be quoted where no test runs.

  **R2's result — one product occurrence, two test occurrences, and no doc, skill or charter quotes
  the clause.** Product: `hub/hub/launchability.py` (`access_path_notice`). Tests:
  `hub/tests/test_agent_trigger.py` ×2. Everything else is a *record* of the defect and must not be
  edited: `spec-queue/DECISIONS.md`, `spec-queue/APPROVALS.md`, `spec-queue/BACKLOG.html`,
  `spec-queue/review/review-2026-09-09.html`, `spec-queue/observations/2026-09-14-LoopEngine.md`,
  `scripts/drive/FINDINGS.md`, `.claude/autonomous/2026-09-09-day-log.md`, and this change's own
  four documents.

- [x] 1.1b **R2 added.** Repeat the sweep for the *second* string,
  `grep -rn "No AgentWeave tools are injected this turn" .`. Product: `hub/hub/api/v1/agents.py`
  (`_tool_surface_lines`). Non-test consumer that will **silently go stale**, since nothing fails
  when it is missed: `scripts/drive/t_d1_0909_together.py`, whose detector is
  `injected = "No AgentWeave tools are injected this turn" in text`. Everything else is a stale
  fixture under `testbed/scratch/`, `.agentweave/tasks/` or a captured context file — leave them.

- [x] 1.2 Read all four test files that reference `access_path_notice` —
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

- [x] 1.3 Record the current no-MCP notice string **and the current `_tool_surface_lines` non-MCP
  preamble** verbatim in this file, so every later round can diff against what was actually there
  rather than against a remembered version.

  **Confirmed at `82106af`. Both sweeps returned exactly R2's inventory**, with every other hit a
  record, a gitignored scratch copy under `.agentweave/tasks/` or `testbed/scratch/`, or this
  change's own documents. Nothing had moved.

  **`access_path_notice`, non-MCP branch, as it stood:**

  > `[AgentWeave] Tool access: no MCP tools this turn — but the AgentWeave capability plane is
  > reachable over HTTP, and this run is already authenticated for it. Its base address is the
  > value of the \`HUB_URL\` environment variable, and its operations live under the route prefix
  > \`/api/v1/agent-actions\`, so a request goes to \`$HUB_URL/api/v1/agent-actions/...\`.
  > Authenticate every request with the run credential in the \`AW_RUN_TOKEN\` environment
  > variable, presented as the header \`Authorization: Bearer $AW_RUN_TOKEN\`. Read both values
  > from your own process environment; they are deliberately not written here. Inbound content is
  > already included in this turn; no retrieval is needed.`

  **`_tool_surface_lines`, non-MCP `preamble`, as it stood:**

  > `No AgentWeave tools are injected this turn, so each capability below is one HTTP request
  > instead. Send it to the address in the \`HUB_URL\` environment variable, with the header
  > \`Authorization: Bearer $AW_RUN_TOKEN\` — read both values out of your own process
  > environment. A field marked \`*\` is required, and \`{...}\` in a path is a value you
  > substitute. Requests and responses are JSON, and a refusal comes back as an HTTP status with a
  > \`detail\` saying why.`

## 2. The notice stops asserting

> **Implemented 2026-09-20. The two product strings now read:**
> - notice — *"[AgentWeave] Tool access: the AgentWeave capability plane is reachable over HTTP,
>   and this run is already authenticated for it. …"* (the clause and its `— but` hinge removed;
>   every required field kept).
> - context preamble — *"Each capability below is one HTTP request. Send it to the address in the
>   `HUB_URL` environment variable, …"* (restated positively per D6, not truncated: `so each
>   capability below is one HTTP request instead` had no subject once the claim was gone).

- [x] 2.1 In `access_path_notice` (`hub/hub/launchability.py`), no-MCP branch: remove the clause
  claiming the run has no MCP tools this turn. Keep the base address, the route prefix, the
  credential variable name, its `Authorization: Bearer` presentation, the read-from-your-own-
  environment instruction, and the inbound-content sentence — each is required by the spec.
- [x] 2.2 Leave the comment above that branch in place, including the paragraph prohibiting
  interpolation of the credential value. It explains a constraint the spec still carries.
- [x] 2.3 Do not touch the MCP branch, `described_access_path`, `harness_has_honoured_mcp`,
  `resolve_access_path`, or anything in `agent_trigger.py`. **R2: `git diff --stat` must show
  exactly two product files — `hub/hub/launchability.py` and `hub/hub/api/v1/agents.py` — not the
  one R1 wrote here.**

- [x] 2.4 **R2 added — the canonical context stops asserting too.** In `_tool_surface_lines`
  (`hub/hub/api/v1/agents.py`), the `else` (non-MCP) `preamble`: remove the claim that no
  AgentWeave tools are injected this turn, and restate the sentence positively rather than
  truncating it — *"so each capability below is one HTTP request instead"* has no subject once the
  clause is gone (design D6). Keep the `HUB_URL` address, the `Authorization: Bearer $AW_RUN_TOKEN`
  header, the read-both-values-out-of-your-own-process-environment instruction, the `*`-required and
  `{...}`-substitute conventions, and the JSON-and-`detail`-refusal sentence.

- [x] 2.5 **R2 added.** Leave the comment above that `else` branch in place, including the paragraph
  on never interpolating credential values — it is the same prohibition 2.2 preserves in
  `launchability.py` and the spec still carries it. Do not touch `over_mcp`, the `if` branch,
  `_http_lines`, `_mcp_lines`, `_operations()`, or the `access_path: str = "mcp"` default.

- [x] 2.6 **R2 added.** Update `scripts/drive/t_d1_0909_together.py`'s detector
  (`injected = "No AgentWeave tools are injected this turn" in text`) to match the new preamble, or
  rewrite it to key on something the change does not move. Nothing fails if this is skipped, which
  is exactly why it is a task: the script would report the opposite of the truth on the next drive.

  **Done by the second route.** Keyed on `"/api/v1/agent-actions" in text`, which `_http_lines`
  renders per operation rather than the preamble carrying once, so it survives any later rewording
  of the prose. The field is renamed `http-rendering=` from `says-not-injected=`, because the old
  label would have been a lie about what is now measured.

## 3. The tests assert the absence of a claim

- [x] 3.1 Restage `hub/tests/test_agent_trigger.py`'s two assertions (each currently
  `assert "no MCP tools this turn" in ...`) so each pairs a **negative** — no availability claim in
  the built prompt — with a **positive** on the plane content the requirement demands. Per design
  D5, a bare `not in` assertion passes against an empty prompt and is not acceptable.
- [x] 3.2 **Rewritten by R2, because as written this task would have ticked green having proved
  nothing.** 1.2 establishes that **none** of the other three test files pins the removed clause, so
  "restage anything that pins it" finds nothing and closes. The real gap is the inverse: extend
  `hub/tests/test_launchability.py::test_a_run_without_mcp_is_not_told_it_cannot_act` — a test
  written to stop exactly this class of sentence, which the current clause walked past because it
  only checks the *older* denial wordings (`"no AgentWeave tool surface is available"`, `"cannot
  send messages"`). Add the current clause to what it refuses. Finding nothing to restage elsewhere
  is the correct outcome and should be written here as such, not left ambiguous.
- [x] 3.3 Add one test that fails on the defect itself: a turn built for an agent with **no prior
  run carrying `mcp_adapter_online_at`**, asserting the prompt makes no claim that the tool surface
  is unavailable **and still carries the plane content the requirement demands** — `HUB_URL`,
  `AW_RUN_TOKEN`, `Authorization: Bearer`, `/api/v1/agent-actions`. *(R3 added the second half. D5's
  own stated trap — "a bare `not in` assertion passes against an empty prompt" — is written into
  3.1 and into 3.3b but was missing from 3.3, which is the task that carries the change's
  headline scenario. A negative-only 3.3 would pass against a prompt that lost the notice
  entirely.)* This is the scenario `A run holding the tools is not told it is empty`. **R2
  checked: no test in `hub/tests/` today asserts on `mcp_adapter_online_at` together with the notice
  text, so this is genuinely absent rather than duplicated. R3 re-checked and confirms it: the only
  `mcp_adapter_online_at` writes in `hub/tests/` are `test_agent_trigger.py` (the positive fixture),
  `test_mcp_adapter_online.py` (the route) and `test_migrations.py` (the column).** The existing
  `test_an_observed_harness_earns_the_mcp_description_for_the_next_run` sets the column and is the
  fixture to model the new test on.
- [x] 3.3b **R2 added — the context side of 3.3, which the spec now names explicitly.** Assert that
  the same fresh-agent turn's **rendered canonical context** makes no claim that the tool surface is
  unavailable, paired with a positive on the HTTP content it must still carry. This is the
  scenario's `AND` clause about the canonical context. Without this, the `agents.py` edit from 2.4
  ships untested.

  **R3 corrected the home.** R2 pointed this at `hub/tests/test_tool_surface_matches_server.py`,
  which calls `_tool_surface_lines(access_path=HTTP_PATH)` **directly, with no turn behind it** — it
  would prove the string changed, not that a fresh agent's turn stops carrying it. The scenario is
  about *a turn*. The right home already exists and already does exactly this shape:
  **`hub/tests/test_agent_trigger.py::test_a_run_without_mcp_is_described_the_operations_it_can_actually_perform`**,
  which triggers a real turn with `hub_client` unset and then asserts on *both* halves — the
  rendered `context` (`"POST /api/v1/agent-actions/messages" in context`,
  `"Authorization: Bearer $AW_RUN_TOKEN" in context`, `"prefixed `mcp__agentweave__`" not in
  context`) **and** the same turn's prompt, under the comment *"The notice in the turn prompt agrees
  with the description in the same turn's context."* That test is the one place both sites of this
  change are already captured from one trigger, so put the paired assertion there. Adding a
  string-level assertion in `test_tool_surface_matches_server.py` as well is fine and cheap, but it
  is not what satisfies the scenario.

  **Done in R3's home.** The paired assertion went into
  `test_a_run_without_mcp_is_described_the_operations_it_can_actually_perform`, beside the context
  positives it already carried: `"No AgentWeave tools are injected this turn" not in context`. The
  separate string-level assertion in `test_tool_surface_matches_server.py` was **not** added —
  3.4's second mutation proves the `agents.py` edit is pinned without it.

  **3.1's result, for the record:** both assertions flipped from `in` to `not in` and each gained
  positives (`$HUB_URL/api/v1/agent-actions/...`, `Authorization: Bearer $AW_RUN_TOKEN`), so
  neither survives a prompt that lost the notice. **3.2's result:** exactly as R2 predicted —
  nothing elsewhere pinned the clause, so the work was the inverse, adding `"no mcp tools this
  turn"` to `test_a_run_without_mcp_is_not_told_it_cannot_act`'s refusal list. **3.3's result:**
  new test `test_a_run_holding_the_tools_is_not_told_it_is_empty`, which asserts the no-grounds
  condition against the database, asserts `mcp_command` was still injected, and then asserts
  neither claim is made.
- [x] 3.4 **Mutation check — R2 extended it to both files.** Restore the removed clause in
  `access_path_notice`, run the tests from 3.1, 3.2 and 3.3, and record here that they fail, with
  the count. **Then, separately, restore the removed clause in `_tool_surface_lines`' non-MCP
  preamble and confirm 3.3b fails, with the count** — a mutation on one file proves nothing about
  the other, and the `agents.py` edit is the half with no existing test pinning it. Revert both and
  confirm `git diff` over `hub/hub/launchability.py` and `hub/hub/api/v1/agents.py` shows only the
  intended edits. A test that passes both ways proves nothing.

  **Both mutations ran, separately, and both bit.**

  | mutation | command | result |
  |---|---|---|
  | clause restored in `access_path_notice` | `pytest hub/tests/test_launchability.py hub/tests/test_agent_trigger.py -q` | **4 failed, 92 passed** |
  | clause restored in `_tool_surface_lines` (notice already reverted) | `pytest hub/tests/test_agent_trigger.py -q` | **1 failed, 53 passed** |

  The four are `test_a_run_without_mcp_is_not_told_it_cannot_act` (3.2),
  `test_trigger_injects_identity_env_and_tells_agent_the_access_path` (3.1),
  `test_a_run_holding_the_tools_is_not_told_it_is_empty` (3.3) and
  `test_a_run_without_mcp_is_described_the_operations_it_can_actually_perform` (3.1/3.3b). The one
  is that last test alone — **which is the point of running the second mutation separately**: the
  `agents.py` edit is pinned by a test that fails when only `agents.py` regresses, so neither half
  of this change can be reverted silently. Both mutations reverted; `git diff 82106af` over the two
  product files shows only the two intended strings.

## 4. The corpus

- [x] 4.1 Apply the delta's two MODIFIED requirements to
  `openspec/specs/agent-capability-plane/spec.md` (via the normal sync at archive time, not by hand
  now). Confirm `openspec validate a-first-turn-is-not-told-it-has-nothing --strict` passes after
  every edit to the change. **Not hand-applied — the sync is archive-time work and stays there.
  `--strict` green after every edit in this session.**
- [x] 4.2 Confirm the F301 prose correction carries **only** the mechanism, and that the
  requirement's conclusion (unreachable by the agent's own tools on the `cli` path) is unchanged and
  its SHALL is byte-identical to today's. `DECISIONS.md` 1d mandates the correction; it does not
  authorise reopening the conclusion. **R2 verified both: the second requirement's SHALL line
  diffs clean against `openspec/specs/`, and the live conclusion clause survives, relocated into
  the corrected paragraph as "The conclusion is unchanged: unreachable by the agent's own tools on
  the `cli` path."**
- [x] 4.2b **R2 added.** `DECISIONS.md` 1d carries a *second* live verdict about this same notice —
  *"change the notice to instruct the `python -c` shape now"* — which this change does not carry.
  Confirm in the ledger edit that it is **superseded, not skipped**: 1d chose `python -c` because
  it was then the only shape `_decide` allowed, and the durable half of that verdict has since
  shipped, so the `curl` shape the notice already instructs is now allowed in both dialects (the
  measurement is in the proposal's **Why**, and R2 re-ran it at `d7f2694`). Do not silently drop it.
- [x] 4.3 Update **F302**'s entry in `scripts/drive/FINDINGS.md` to `fixed <sha>` only once 2.1,
  **2.4**, 3.1 and 3.3 have all landed, and say in the same edit that `harness_has_honoured_mcp`'s
  permanent-positive latch (**F340**) is untouched. **R2: state what was fixed precisely — both
  false sentences were removed from the first turn. Do not write that the measured behaviour is
  closed.** The Architect kept to `curl` for ten runs *after* the notice healed, so removing the
  falsehood is necessary and is not shown to be sufficient; design D2's R2 dissent is the record of
  that, and claiming more here is the kind of tick this repo's discipline exists to prevent.
  **Done. F302's status is now `fixed 802a8c7`.** The entry carries: the two-site table (both
  strings, was → is); the mutation counts pinning each half separately; an explicit *"the measured
  behaviour is NOT closed"* paragraph naming the ten post-fix `curl` runs and correcting the
  baseline to **n=1**; the bar on archiving until 7.4 has counts; *"`harness_has_honoured_mcp`'s
  permanent-positive latch (F340) is untouched"*; and 4.2b's superseded-not-skipped paragraph, in
  the same edit.

## 5. Quality gates, over CI's exact paths

- [x] 5.1 `py -3.11 -m ruff check src/ hub/ tests/` → **All checks passed!**
- [x] 5.2 `py -3.11 -m black --check src/ hub/hub/ hub/tests/ tests/ --target-version py311` →
  **581 files unchanged.** First run wanted one reformat (the new test's `select(...).where(...)`
  fitted on one line); applied, re-run clean.
- [x] 5.3 `py -3.11 -m mypy src/` → **Success: no issues found in 22 source files.** (No `src/`
  file changed; run because CI runs it.) **Note:** the three tools are not on PATH in this shell —
  `ruff`/`black`/`mypy` return `command not found` and must be invoked as `py -3.11 -m <tool>`.
- [x] 5.4 `hub/ui` is not built or linted, because nothing under `hub/ui/` is touched. Confirmed
  with `git diff 82106af --name-only`: five files, none under `hub/ui/` or `hub/hub/static/ui/` —
  `hub/hub/api/v1/agents.py`, `hub/hub/launchability.py`, `hub/tests/test_agent_trigger.py`,
  `hub/tests/test_launchability.py`, `scripts/drive/t_d1_0909_together.py`. **No bundle refresh is
  owed and nothing reaches the operator's live app on reload.**

## 6. What must not move

> **R3 (2026-09-20) replaced R2's caution here, because the situation it described has changed and
> the guard it warned about is now actually broken.** R2 wrote that another agent held *uncommitted*
> edits to `hub/hub/launchability.py`, `hub/hub/runner_commands.py` and five files under
> `src/agentweave/`. Those edits have since been committed as **`4bd966e` ("dead-code: annotate 36
> legacy paths")**, and `git status` is clean. The hazard is no longer a dirty tree — it is that
> **`4bd966e` is on this branch and not on `master`**, so `master` is the wrong baseline for any
> "unchanged" guard:
>
> ```
> $ git diff master --stat -- hub/hub/runner_commands.py hub/hub/launchability.py hub/hub/api/v1/agents.py
>  hub/hub/api/v1/agents.py   |  8 ++++++++
>  hub/hub/launchability.py   | 18 ++++++++++++++++++
>  hub/hub/runner_commands.py | 15 +++++++++++++++
> ```
>
> **The correct baseline for every guard in this group is the commit this change is implemented on
> top of** (`git rev-parse HEAD` before the first edit — record it in 6.0), not `master`.

- [x] 6.0 **R3 added.** Before editing anything, record the implementation baseline here:
  `git rev-parse HEAD` → **`82106afde36922331ea3d4feb65152ff98eb2007`** (`82106af`, R3's own commit),
  and `git status --short` was **empty** — both confirmed before the first edit. Every "unchanged"
  guard below diffs against that sha. Diffing against `master` is wrong on this branch and will
  report `4bd966e`'s annotation pass as this change's work. **This governs every bare `git diff` in
  this file** — 2.3's `--stat`, 5.4's `--name-only`, 6.3 and 6.4 — each means `git diff <6.0-sha>`.
  With a clean tree at 6.0 a bare `git diff` happens to agree, which is exactly why it must be
  written down: the next agent to touch this tree makes it disagree again without telling anyone.

- [x] 6.1 `py -3.11 -m pytest hub/tests/test_launchability.py hub/tests/test_agent_trigger.py
  hub/tests/test_agent_facing_text.py hub/tests/test_tool_surface_matches_server.py -q` →
  **157 passed, 0 failed, 6 warnings, 43.75s.** The six warnings are pre-existing aiosqlite
  teardown noise (`RuntimeError: Event loop is closed`), present on the baseline and unrelated.
- [x] 6.2 `py -3.11 -m pytest hub/tests/ -q` in full — **write the actual counts and the duration
  inline in this task.** Per **F392**, a tick on this line citing a log entry that does not exist is
  the exact process defect that let a three-test regression reach `master`; if the number is not
  written here, this task is not done.
  **→ 4460 passed, 86 skipped, 0 failed, 267 warnings, 2007.94s (33m27s).** Run on the tree at
  `802a8c7` (started by the previous session at ~20:15Z, read at 20:49Z by the session that resumed
  it). **Two caveats, recorded rather than smoothed over:**
  (a) it overlapped a second full-suite run for its last ~13 minutes, so it is not a clean-machine
  measurement — it passed anyway, and contention is the direction that would have *caused* a
  failure, not hidden one;
  (b) the local totals do not match CI's and are not supposed to — **CI at `802a8c7` reports
  `4451 passed, 20 skipped`** (run `35535926320`, `hub-test` green in 12m13s). The 66-skip gap is
  machine-dependent collection (`claude` is on PATH here and is not on a runner — see
  `DEAD-ENDS.md`), which is why neither number alone is the gate.
  **Both signals are green at the implementation sha**, which is the claim this task exists to
  support. Note the local run is *not* evidence about **F292**: that lock has never reproduced on
  this machine.
- [x] 6.3 Confirm no permission posture changed. **R3 rewrote this task's first clause: as R2 left
  it, it was already false against the tree and would have fired a false alarm at implementation
  time.** It read *"`grep -n "acceptEdits\|permission-prompt-tool"` in `hub/hub/runner_commands.py`
  is byte-identical to `master`"*. Two things are wrong with that. **(a) `-n` prints line numbers,
  so the guard compares positions, not content** — and `4bd966e` has already moved every one of
  them. **(b) `master` is the wrong baseline** (see 6.0). R3 measured both halves:

  ```
  # text of the matched lines, master vs working tree:  IDENTICAL
  # the same grep WITH -n:                              DIFFERS (57→65, 63→71, 71→79, 73→81, 75→83, 254→269)
  ```

  The guard means *"the permission posture's code is unchanged"*, so express it that way: compare
  the matched lines' **text** with no `-n`, against the **6.0 baseline sha**, and require an empty
  diff —

  ```
  diff <(git show <6.0-sha>:hub/hub/runner_commands.py | grep "acceptEdits\|permission-prompt-tool") \
       <(grep "acceptEdits\|permission-prompt-tool" hub/hub/runner_commands.py)
  ```

  — and confirm `git diff <6.0-sha> --name-only` names neither
  `runner_commands.py` nor `mcp_server.py`. The spec scenario *"A truer description does not
  silently widen permission"* is the requirement this guards.

  **Run as R3 re-expressed it, against `82106af` and without `-n`:** the `diff` of the matched
  lines' text is **empty** — the permission-posture code is byte-identical. `git diff 82106af
  --name-only` names five files and **none of them is `runner_commands.py`, `mcp_server.py` or
  `agent_trigger.py`**. Within `hub/hub/api/v1/agents.py` the diff is two lines, both inside the
  non-MCP `preamble`: `over_mcp`, `_http_lines`, `_mcp_lines`, `_operations()` and every route
  handler are untouched. *(R3's correction earned its place — the original `grep -n` guard would
  have reported a false alarm here, since `4bd966e` moved all six line numbers.)* **R2: `agent_trigger.py` must also be
  absent from the diff — it holds both `access_path` and `described_path`, and the whole change
  rests on those two staying separate. And within `hub/hub/api/v1/agents.py`, confirm the diff is
  the one `preamble` string: `git diff <6.0-sha> -- hub/hub/api/v1/agents.py` must show no change to
  `over_mcp`, `_http_lines`, `_mcp_lines`, `_operations()` or any route handler.** *(R3: baseline
  sha substituted for R2's bare `git diff`, for the reason in 6.0.)*
- [x] 6.4 Confirm nothing under `hub/ui/src/` or `hub/hub/static/ui/` is in the diff, so no bundle
  refresh is owed and nothing reaches the operator's live app on its next reload. **Confirmed
  against `82106af` — see 5.4 for the five-file list.**

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

> ### R3 (2026-09-20) audited this group. The experiment is the right one; its **baseline is not
> what the cited source says**, and as written the comparison in 7.5 could not have been made
> honestly. Corrections are inline below. This group had had no verification pass before now.

- [x] 7.1 **Done 2026-09-21.** Throwaway Hub on `:8091` (never `:8000`, never `:8010`), scratch
  profile `testbed/scratch/f302_measure/` (its own sqlite `agentweave.db`, `DATABASE_URL` pointed
  at it, started from `hub/` via `py -3.11 -m uvicorn hub.main:app --port 8091`, never the
  installed console script), project `proj-c3039d3069b2`. Three brand-new agents created —
  `f302agent1`/`f302agent2`/`f302agent3`, runner `haiku-f302` (`runner-ea4085e0bd6c`,
  `cli="claude"`, `model="claude-haiku-4-5-20251001"`). Confirmed by direct sqlite read of the
  scratch db **before** any turn: `runs` had zero rows for all three agents with
  `mcp_adapter_online_at IS NOT NULL` (trivially true — brand new — confirmed rather than assumed).

- [x] 7.1b **Done 2026-09-21, all three preconditions confirmed before triggering, by direct read
  of `testbed/scratch/f302_measure/agentweave.db`:**
  - `hub_client` unset: `project_sessions` had **no row** for `proj-c3039d3069b2` (no session-wide
    default), and each of the three agents' `agents.config` was the literal `{}` (no per-agent
    override). Neither the CLI override path nor a session-wide default was set anywhere.
  - Bound runner `cli` is `"claude"` — in `MCP_INJECTABLE_RUNNERS`.
  - `SELECT COUNT(*) FROM runs WHERE agent=? AND project_id=? AND mcp_adapter_online_at IS NOT NULL`
    was `0` for `f302agent1`, `f302agent2`, `f302agent3` — confirmed, not assumed.

  Post-turn, all three runs' own `mcp_adapter_online_at` stamped **during** the run (timestamps
  ~30-40s after trigger, run start had no grounds) — confirming the no-grounds-but-injected
  condition actually held for the turn being measured, exactly as 7.1b describes.

- [x] 7.2 / [x] 7.3 **Done 2026-09-21.** Same instruction, all three, bound to
  `claude-haiku-4-5-20251001`, `session_mode=new`, one turn each:
  > Create a task titled "F302 probe task" with description "measurement probe" in this project,
  > then stop.

  | agent | run id | model | peers? | charter bound? |
  |---|---|---|---|---|
  | f302agent1 | `run-3e7497554e98` | claude-haiku-4-5-20251001 | yes (2 other agents in roster) | no (`charter_id` null) |
  | f302agent2 | `run-63c923499c5d` | claude-haiku-4-5-20251001 | yes | no |
  | f302agent3 | `run-9ddb13b6dfeb` | claude-haiku-4-5-20251001 | yes | no |

  All three runs `status=completed`, `exit_code=0`.

- [x] 7.4 **Done 2026-09-21.** Read each run's `agent_outputs` directly from the scratch db (full
  dump preserved at `testbed/scratch/f302_measure/transcript_dump.txt`). All three:
  - `run-3e7497554e98` (f302agent1) — **MCP.** seq=2 `ToolSearch` for
    `select:mcp__agentweave__create_task`, seq=4 calls `mcp__agentweave__create_task` directly with
    `{"description": "measurement probe", "title": "F302 probe task"}`. No `curl`/`python -c`/
    `Invoke-WebRequest` anywhere in the transcript.
  - `run-63c923499c5d` (f302agent2) — **MCP**, identical shape (`ToolSearch` then
    `mcp__agentweave__create_task`, no HTTP).
  - `run-9ddb13b6dfeb` (f302agent3) — **MCP**, identical shape.

  **Counts: 3 MCP, 0 HTTP, 0 both, 0 neither.** No replacement runs were needed — every sampled
  turn was usable.

  **R3 replaced R2's binary here.** It read *"whether the first turn called an `mcp__agentweave__*`
  tool or shelled out"*, which assumes every run lands in one of two buckets. It cannot: a turn may
  do **both** (the LoopEngine Architect did exactly that across its session — `curl` for drafts,
  MCP for `ask_user`), and a Haiku turn may do **neither**. Record one of:
  - **MCP** — called an `mcp__agentweave__*` tool and did not shell out for a plane operation;
  - **HTTP** — shelled out (`curl`, `python -c`, `Invoke-WebRequest`, …) to `/api/v1/agent-actions`;
  - **both** — did each at least once, in which case record which came *first*, since the question
    is what the turn reaches for;
  - **neither** — the turn failed, was refused by the approver, ended in prose, or asked a question
    without performing the operation. **A `neither` run is not a sample**: it says nothing about
    which surface the agent prefers. Replace it and record that it was replaced, with why. Do not
    let replacements run until three agree — if more than about half the runs land in `neither`,
    the instruction in 7.2 is the problem and must be fixed before the counts mean anything.

- [ ] 7.5 **BASELINE — R3 corrected this, and it was the most load-bearing error in the group.**
  R2 wrote the pre-change baseline as *"**4 of 4 agents took the HTTP path on their first turn**
  (`openspec/explorations/2026-09-14-the-first-turn-has-its-tools.md`)"*. **The source does not say
  that, and cannot.** What it and
  `spec-queue/observations/2026-09-14-LoopEngine.md` establish is:
  - **4 of 4 agents were *told* the false sentence** — "All four of LoopEngine's agents opened
    their first turn with *'Tool access: no MCP tools this turn'*"; the observation repeats it as
    "**All three first turns were told there were no MCP tools**" for `dev_2`, `dev` and `tester`.
    *Told*, not *took*.
  - **1 of 1 agents whose behaviour was actually read took HTTP** — the Architect
    (`run-2445bbbe1d6d`), and it kept to `curl` for ten runs.
  - The other three agents' behaviour was **never read**. The observation says so explicitly, under
    *"What went unread for these three"*: "**Transcripts.** Their `agent_outputs` rows, their
    thinking blocks and any sidechains."

  **So the honest baseline is n=1, not n=4.** Write it that way and nowhere write "4 of 4 took
  HTTP". A three-run result compared against a four-run baseline that was never measured is the
  defect this repo's round discipline exists to catch — a number that is green while the thing it
  counts could not have been counted.

- [x] 7.5 **Confirmed 2026-09-21** — baseline stated as n=1 throughout this measurement's writeup
  (`scripts/drive/FINDINGS.md`, `DECISIONS.md`, this file). Nowhere is "4 of 4 took HTTP" written.

- [ ] 7.5b **R3 added — the confounds, recorded before the runs, so the writeup cannot quietly
  assume comparability.** The baseline and 7.1-7.3 differ in at least three ways that each
  plausibly move the outcome. State each in the writeup:
  - **Model.** The baseline agents were **Opus 5** (`Architect`, `tester`) and **Sonnet 5** (`dev`,
    `dev_2`) — `2026-09-14-LoopEngine.md`'s agent table. 7.2 binds **Haiku**. Whether a model
    reaches for an injected tool or for `curl` is exactly the kind of thing that differs by model.
  - **Task shape.** The Architect's first turn opened a **spec interview** with a charter bound, on
    a live multi-agent project, in a session that then resumed for ten runs. 7.2 is one
    self-contained instruction on a throwaway. The habit the exploration describes forms *because*
    the session continues; a single turn cannot form it.
  - **Surrounding text.** The baseline turns carried **both** false sentences. 7.1-7.3 carry
    neither, and also carry whatever `has_peers` and the charter change in the context file.

  None of these voids the experiment. They mean its result is **about 7.1-7.3's own condition**,
  and the 2026-09-14 record is context rather than a control.

  **Confirmed present in this run, 2026-09-21:** model was Haiku (`claude-haiku-4-5-20251001`), not
  Opus/Sonnet; task shape was one self-contained instruction on a throwaway project, no resumed
  session, no charter; surrounding text carried neither false sentence (the fix already merged at
  `802a8c7`) but did carry `has_peers=true` (2 other agents existed in the same project's roster for
  each of the three).

- [x] 7.5c **The verdict — R3 restructured it as an absolute measurement, which is what three fresh
  runs can actually carry, rather than as a comparison against a baseline that does not exist.**
  The question from the group header is unchanged: *with no false sentence in front of it, does a
  fresh agent's first turn use the MCP tools, or does it still shell out?* Answer it directly.
  - **Every sampled first turn reached for MCP** → the positive HTTP steer does not dominate a
    fresh turn. This weakens R2's dissent substantially. It does **not** close D2 on three runs:
    record it, say so in `DECISIONS.md` under a dated heading, and mark F302 `fixed` with the
    counts beside it. *(R3 narrowed this bullet: R2's version licensed marking F302 "fixed
    **without qualification**" off 3 samples. Three runs do not support an unqualified claim, and
    an unqualified tick is the F392 defect this group exists to prevent.)*
  - **No sampled first turn reached for MCP** → the steer plausibly dominates and R2's dissent is
    supported. **File the conditional text as a new finding rather than widening this change**,
    which will already be archived.
  - **Split** → record the split with its counts and leave D2 open. Do not round it.
  - **Fewer than three usable samples** (too many `neither` runs) → **the measurement did not
    happen.** Say so plainly, leave D2 open, and do not write a verdict. This outcome was missing
    from R2's three and is the one most likely on Haiku.

  In every branch, write the counts and the condition (model, instruction, peers, charter) beside
  the verdict, so the next reader can tell what was measured from what was concluded.

  **Done 2026-09-21. Counts: 3 MCP / 0 HTTP / 0 both / 0 neither** (see 7.4). **This is the first
  branch — every sampled first turn reached for MCP.** Condition: Haiku, one-shot task-creation
  instruction, throwaway project, no charter, peers present (2 other agents in the roster). Recorded
  in `DECISIONS.md` under `### 2026-09-21 — F302 group 7 measured: 3 of 3 fresh first turns reached
  for MCP`, and F302 marked **fixed, measured** (not fixed without qualification) in
  `scripts/drive/FINDINGS.md`. D2 is **not** closed by this: n=3, one model, one instruction shape,
  one throwaway project — the confounds in 7.5b are unaddressed by this sample and are stated
  alongside the verdict in both files.

- [x] 7.6 **Done 2026-09-21.** Measurement appended to F302's entry in `scripts/drive/FINDINGS.md`
  (new `2026-09-21` blockquote, after the `2026-09-20, implemented` block). **The "the notice heals
  on turn two; the agent does not" line was left unchanged, deliberately — 7.5c's outcome does not
  trigger the correction this task's condition is written for.** That line, read carefully, already
  attributes *turn 2 onward* persistence to a learned method (the Architect's already-paid-for
  `curl` routine), not to the notice's continued presence — the notice being healed by turn 2 is
  precisely what the sentence says. This run's result — a genuinely fresh first turn, no false
  sentence in front of it, no learned method yet possible (it is the first turn) — went to MCP in
  3/3 samples. That is consistent with, not contrary to, the existing framing: it suggests the
  false sentence on the *original* first turn was what set the Architect's HTTP habit in the first
  place, and the habit's later persistence past a healed notice is exactly the learned-method
  reading the line already states. Correcting it would overstate what 3 Haiku samples on a
  throwaway project can say about one Opus agent's ten-run session. No edit made to that line for
  this reason, recorded here rather than silently skipped.
- [x] 7.7 **Done 2026-09-21.** Edited `openspec/explorations/2026-09-14-the-first-turn-has-its-tools.md`'s
  "What we saw" section: the four-bullet list is now explicitly labelled as who was *told* the false
  sentence, with an inline note that only the Architect's behaviour was actually read (transcript,
  thinking blocks, sidechains) and the other three are listed only because the log shows they were
  told the same sentence. Cross-references this file's own 2026-09-20 "4 of 4 agents took the HTTP
  path" line (task 7.5, above, since corrected by R3) as the overreach the fix stops the next reader
  from inheriting.
