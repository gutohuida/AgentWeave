# Handoff: loop 8's two changes landed and were proven live; the overnight loop died at 40 minutes and a skill now exists to stop that

**Date:** 2026-08-15T10:40+0100 · **Branch:** hub-native-experience · **HEAD:** `4711af5`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0045-2026-08-14-2241-loop8-found-it-the-plan-fixes-it.md`
**Status:** **chunk complete.** Everything committed and pushed, 0 unpushed, tree clean apart from
one pre-existing stray file. Nothing is half-done in the working tree. Loop 9 is paused mid-cycle
in a live project, deliberately.

## Goal

Implement the two openspec changes the loop-8 exploration called for, prove them against a real
Hub rather than only against tests, and — after the operator asked for an unattended overnight run
— make autonomous work survivable.

The *why*, for judgment calls later: the previous four sessions built the evidence→integration
pipeline, made it agent-drivable, fixed six seams loop 7 found, and then loop 8 proved the
**failure** paths around them were unwired. A runtime dying mid-turn silently ate the operator's
input. That is the class of defect this whole line of work exists to close, and it is invisible to
the 2028-test suite because it lives between two features.

## Current state

### Shipped and verified

Both changes are implemented, tested, merged and pushed on `hub-native-experience`:

- **`2026-08-14-a-failed-run-does-not-eat-its-input`** — a failed run hands its input back on the
  *normal* completion path for both transports; divergence is skipped when input was re-handed; the
  re-delivered turn names the attempt; both pre-spawn branches schedule their own retry.
- **`2026-08-14-what-a-failure-tells-the-operator`** — skip text points at the retry that works;
  `runtime_exit_code` beside the synthetic `exit_code`; `4294967295` renders `-1`; `stderr_tail`
  delivered on both paths; `ui_stale` names `refresh_ui_bundle.py`; identifiers sort naturally.

Both `tasks.md` files have their agent-verifiable **and** human-only sections checked off with real
measurements, not claims. Only genuine operator judgement calls remain unchecked (A 7.4, 7.5;
B 9.1, 9.2, 9.4).

### The one carve-out that was not in the approved plan

**A binding conflict does not requeue** (`and binding_conflict is None` at both sites). Found by two
existing test files failing, not reasoned out in advance. Two reasons: the turn already ran, so the
input was processed rather than lost; and retrying would clear the provider session at
`RESUME_RETRY_LIMIT` and let the refused session bind on the third attempt, defeating the check that
raised the failure. **The operator chose this** from three options. Recorded as design decision D2a.

### Loop 9 — paused on purpose, live

`aw-loop9` (`proj-9eb82406`) at `C:\Users\huida\Documents\aw-loop9`. A 17-requirement spec for a
fortnightly shift-roster fairness library, approved, seven tasks created.

- `task-6de550a5` "Define JSON-compatible API" is **`under_review`**.
- Its three pieces of evidence are all **`rejected`**: `ev-33215918` (FR-1), `ev-3a88bacc` (FR-6),
  `ev-3e6e20ba` (FR-12) — the verifier's reasoning is that the public callable raises
  `NotImplementedError`, so no requirement is actually exercised. That is a correct rejection.
- The other six tasks are `pending`.
- Agents: `architect` (codex/Spec Author), `builder` (claude/Developer), `verifier` (codex/Verifier,
  `can_accept_evidence=true`).
- **The approve→merge half was never exercised.** That is where loops 5–7 found their integration
  defects, and it is the most valuable unrun thing in this handoff.

**Hub is running** on `:8010`, started detached via WMI, on current code. Verified `200` at 10:40.

### The overnight run, and what it actually did

The operator asked for autonomous work from 00:40 to 10:00 on a branch. **It ran 00:40–01:18 —
four iterations, ~40 minutes.** Diagnosed rather than guessed: the machine never slept and never
rebooted (`Kernel-Power` shows only session transitions; last boot 2026-08-13), and the Hub
survived. `ScheduleWakeup` is **bound to the interactive session**; when that ended, every future
wakeup ended with it. Nothing was lost because every iteration had already committed and pushed.

`autonomous_work` has been **merged into `hub-native-experience`** (`00d612c`) at the operator's
request and its five commits are in the history.

## Files touched

`git status --short` shows only `?? hub/agentweave.db` — a stray empty SQLite file **already
untracked at session start**, named in the last five handoffs. Not the live database; that is
`hub/data/agentweave.db`. Left alone deliberately. `git diff --stat HEAD` is empty.

| path | what |
|---|---|
| `hub/hub/api/v1/agent_trigger.py` | Change A's four sites (return input on both normal paths, divergence guard, both pre-spawn `schedule_agent` calls, binding-conflict carve-out) **and** Change B's `_runtime_failure_fields` (new) + `_transport_failure_fields` + `readable_exit_code` import. Finished. |
| `hub/hub/inbound_queue.py` | `format_turn_prompt` renders the re-delivery note per entry. Finished. |
| `hub/hub/codex_appserver.py` | `readable_exit_code()` (new), used in `AppServerError.__init__`; `TurnOutcome.stderr_tail` filled from `session.stderr_tail()`. Finished. |
| `hub/hub/task_integration.py` | `CHECKOUT_DIRTY` / `CHECKOUT_ELSEWHERE` reworded to point at the retry. Finished. |
| `hub/hub/main.py` | `ui_stale` names `python scripts/refresh_ui_bundle.py` first, `make ui` second. Finished. |
| `hub/hub/api/v1/tasks.py` | `import re`, `_natural` sort key, applied to each task's links. Finished. |
| `hub/tests/test_failed_run_returns_input.py` | **new**, 17 tests. Finished. |
| `hub/tests/test_failure_reporting.py` | **new**, 12 tests. Finished. |
| `hub/tests/test_agent_trigger.py` | `_fake_pty` hands back a fresh session per call; four tests updated for the retry rule; `DELIVERY_ATTEMPT_LIMIT` imported. Finished. |
| `hub/tests/test_conversation_contract.py` | `_fake_pty` same fresh-session fix. Finished. |
| `hub/tests/test_task_integration.py` | new `test_a_dirty_checkout_skip_points_at_the_retry_not_at_approving_again`. Finished. |
| `hub/tests/test_task_requirement_ids_readable.py` | new `make_numbered_document` + `test_identifiers_are_ordered_by_number_not_as_text`. Finished. |
| `hub/tests/test_ui_build_stamp.py` | extended `test_a_stamp_naming_other_source_still_warns`. Finished. |
| `hub/tests/test_task_integration_retry.py` | black reformat only, no semantic change. |
| `openspec/changes/2026-08-14-a-failed-run-does-not-eat-its-input/` | **new**: `proposal.md`, `design.md` (incl. D2a), `tasks.md`, `specs/agent-conversation-workspace/spec.md`. |
| `openspec/changes/2026-08-14-what-a-failure-tells-the-operator/` | **new**: `proposal.md`, `design.md` (D3 corrected for L9-1), `tasks.md`, `specs/runtime-diagnostics/spec.md`, `specs/task-lifecycle-governance/spec.md`. |
| `.claude/autonomous/2026-08-15-overnight-log.md` | **new** — the overnight record with evidence. |
| `.claude/skills/autonomous-session/SKILL.md` | **new** — the skill. |
| `.claude/skills/autonomous-session/scripts/install-driver.ps1` | **new** — Scheduled Task installer. Syntax-checked, **never executed**. |
| `.claude/skills/autonomous-session/scripts/run-iteration.ps1` | **new** — one iteration via `claude -p`. Syntax-checked, **never executed**. |

## Key decisions

1. **The requeue rule is "any failed run, capped at 3"** — the operator's explicit choice over my
   recommended narrow `outcome.exit_code is not None`. **Do not re-propose the narrow one.**
2. **Binding conflict is carved out** (D2a). Operator chose "Don't requeue a binding conflict" over
   "requeue but never clear the binding" and "leave it as is". The rejected middle option would have
   threaded a flag into `return_run_entries`; it was judged more machinery than the case warrants.
3. **`exit_code` was not repurposed; `runtime_exit_code` was added beside it.** `AgentOutputPanel.tsx`
   reads the synthetic 0/1 for handoff detection.
4. **Rendering happens at every surface a person reads**, not only in the composed message — this was
   *wrong first*, shipped, and corrected as finding L9-1. `TurnOutcome.exit_code` and
   `AppServerError.exit_code` keep the raw platform value.
5. **Findings 8 and 9 were left out of scope** — operator chose "leave them recorded, decide later".
6. **The autonomous driver is an OS Scheduled Task running `claude -p`**, not a cloud schedule.
   Cloud survives session death but cannot reach a local Hub, local runtimes or the local checkout.
   Rejected alternatives are in the skill's trade-off table.
7. **Test-suite performance was deferred** — operator chose "yes, but as separate work later". The
   suite is ~7 minutes, not the ~20 I first estimated; see Dead ends.

## Constraints and user directives (verbatim)

**From this session:**
- **"Implement both, A first (Recommended)"**
- **"Leave them recorded, decide later"** — on findings 8 and 9.
- **"Don't requeue a binding conflict (Recommended)"**
- **"Yes, but as separate work later (Recommended)"** — on suite performance.
- **"I'm going to sleep but I want you to work on agentweave until 10 AM tomorrow… open a branch of
  this branch called autonomous_work and work on whatever you feel is necessary… I give you full
  autonomy on this branch."**
- **"The test suit is reaally slow. Should we take a look at them as well? Maybe we don't need that
  many tests... or something is wrong"**
- **"Can you create a skill for this? Try and find solutions for what broke and in the skill it
  should ask the tasks it should work on. (We can decide to work on whatever the AI wants.) Also
  always work on a autonomous branch."**

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- **G5 (the interview backstop) is a non-goal** — *"actually that's okay because this is a AI test.
  The AI should answer or not deliberately based on the test."* **Do not re-propose it.** Loop 9
  re-observed it a **fourth** time (`select count(*) from questions where project_id='proj-9eb82406'`
  → 0). Observation only.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Evidence: *"The evidence can be anything… Whatever the model thinks it's necessary to show that
  his work is good."* · *"only test agents can accept the evidence… If no tester agent then all
  defers to the operator."*
- On narrowing command execution: *"That would be the work for hooks. Which are not implemented yet."*
- Handoff cadence: only when asked, or when an openspec change is done.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; **never mark a task complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.
- Session directive: **do not call the Agent tool, and do not use workflows or deep-research, unless
  the user requests it.**

## Dead ends

**New this session, and expensive:**

- **A green suite agreed with broken behaviour three times.** (a) Two of my own new tests patched
  `hub.turn_scheduler.schedule_agent` with a bare `AsyncMock` — which also stubs the call
  `POST /agent/trigger` uses to start its run (`agent_trigger.py:819-821`), so no run ever happened
  and the assertions held over nothing. Fixed with a pass-through spy that lets the **first** call
  through. (b) Three tests patched `hub.codex_appserver.run_turn`, but `agent_trigger` imports it at
  module level as `codex_run_turn` (`:50`), so the patch bound nothing and the app-server tests drove
  a real spawn. (c) Finding L9-1: 75 unit tests passed **both** before and after the fix.
  **Mutation-check everything.**
- **A failed run now retries, and single-use mock sessions hang the run loop.** `read.side_effect`
  exhausts on the second spawn and the `StopIteration` raised inside the executor **hangs rather than
  fails**. This stalled two full-suite runs at 7% and 25% before diagnosis. Three files had it;
  `_fake_pty` in `test_agent_trigger.py` and `test_conversation_contract.py` now build a fresh
  session per call.
- **The suite is ~7 minutes, not ~20.** I estimated 20 from a per-test setup figure measured *while
  the hangs were distorting it*. Real: 2028 passed in 425s across three file chunks, ~0.21s/test,
  which matches `create_app` + `init_db` almost exactly. The fixture rebuild is essentially the whole
  cost, but the total is unremarkable. **Do not repeat the 20-minute claim.**
- **`pytest hub/tests/` exceeds the 600s Bash cap.** Run in three chunks:
  `ls tests/test_*.py | head -48`, `sed -n '49,96p'`, `sed -n '97,144p'`.
- **`black --target-version py311` produces parenthesized `with` statements**, which `ruff` rejects
  because it lints the repo at the CLI's py38 floor. Use plain `black` (the repo config lists
  py38–py312) and, for many context managers, an `ExitStack` helper.
- **PowerShell 5.1 reads BOM-less UTF-8 as ANSI**, so an em dash inside a double-quoted string in a
  `.ps1` breaks parsing — with an error pointing several tokens away. Keep `.ps1` ASCII-only.
- **`pip install -e .` leaks between agents** (finding L9-3). It installs into the shared interpreter
  every agent uses. I contaminated the verifier mid-review this way; uninstalled afterwards.
- **The composed turn prompt is not persisted anywhere.** To verify the re-delivery note, load the
  real `inbound_queue_entries` row and run it through `format_turn_prompt` directly.
- **Background `pytest` runs get orphaned across session boundaries** with no completion record. Run
  long suites in foreground chunks when the result matters.

**Tooling quirks, re-confirmed:**
- **Start the Hub via WMI** so it survives session teardown (command in `CLAUDE.md` and the
  autonomous-session skill). This was the one thing that survived the night.
- **The Bash tool's cwd persists** after a `cd` in a compound command — it does *not* always reset.
  Check with `pwd` before assuming.
- `git commit -F -` with a heredoc; `@'…'@` is PowerShell syntax.
- **`npx openspec new change` rejects a name starting with a digit** — create by hand.
- **The openspec validator reads only a requirement's FIRST PHYSICAL LINE** for SHALL/MUST.
- The Hub API key is `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (`hub/.env`).
- Event rows are in **`event_logs`** (columns `id, project_id, event_type, agent, data, severity,
  timestamp`) — not `event_log`, and the payload column is `data`.

## Verification

**Ran, with real output:**
- `pytest hub/tests/` in three chunks: **631 + 685 + 712 = 2028 passed, 11 skipped**, 425s.
- `pytest tests/` (CLI): **360 passed, 3 skipped.**
- `npx vitest run`: **864 passed**, 90 files. `npx tsc --noEmit`: clean. `ruff check hub/ src/`: clean.
- `npx openspec validate --changes --strict`: **20 passed, 0 failed.**
- Post-merge re-run of the seven affected test files: **105 passed.**
- **Six mutation checks, all caught**: deleting `return_run_entries` at either normal-path site;
  deleting either new `schedule_agent`; removing the `if not returned:` guard; dropping
  `and binding_conflict is None` (fails both my new test *and*
  `test_conversation_contract.py::test_provider_binding_conflict_leaves_conversation_untouched_and_fails_run`).
- **Live against a real Hub:** one kill → entry returned at `delivery_attempts=1`, `run-b61a9ee9`
  started **on its own** 18s later and completed. Three kills → entry `withdrawn` at 3 attempts with
  reason "delivery failed 3 times; the Hub stopped retrying", `provider_session_id` cleared,
  `queue_entry_abandoned` at `warn`, agent back to `idle`.
- **An unprovoked failure self-healed:** `run-90edbaa2` died on `thread/resume`; attempts at
  23:53:46 → :48 → :50, the third on a fresh session, completed. Nobody touched anything.
- **L9-1 before/after in the same table:** consecutive `run_failed` rows read
  `runtime_exit_code=4294967295` then `-1`.
- **B6 live:** `task-7872c5d0` reports `FR-1 … FR-17` in numeric order.
- Both `.ps1` scripts parse clean via `[Parser]::ParseFile`.

**NOT run, and it matters:**
- **Neither `.ps1` driver script has ever been executed.** `install-driver.ps1` has never registered
  a Scheduled Task and `run-iteration.ps1` has never been fired. The whole durability claim of the
  autonomous-session skill is **unproven**.
- **The autonomous-session skill has never been invoked.**
- **Loop 9's approve→merge half was never exercised** — no `task-set approved`, no integration
  attempt, no merge to the project's main branch.
- The full `pytest hub/tests/` has **not** been re-run since the skill commit (`4711af5`), but that
  commit touches only `.claude/skills/`, so no Python behaviour changed.
- `make ui` still has never been executed anywhere — `make` does not exist on this machine.

## Git state

Branch `hub-native-experience`, HEAD **`4711af5`**, working tree **clean** except
`?? hub/agentweave.db` (pre-existing stray, not the live DB), **0 unpushed commits**.

`autonomous_work` exists at `96865e3`, pushed, and is **fully merged** into `hub-native-experience`
via `00d612c`. It can be deleted or kept as a record; nothing depends on it.

**Live environment:** Hub on `:8010`, started detached via WMI, on current code, `200` at 10:40.
Re-find the PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen` rather than trusting a
number.

**Projects in the database:** `aw-testbed`, `newtest`, `test2`, `aw-loop-4`, `aw-e2e`, `aw-loop5`,
`aw-loop6` (`proj-c28f08df`), `aw-loop7` (`proj-e6c1de74`), `aw-loop8` (`proj-94f3f169`), and
**`aw-loop9` (`proj-9eb82406`)**.

**Keep `aw-loop6`, `aw-loop7`, `aw-loop8`, `aw-loop9`.** Loop 6 holds a hand-minted credential
`run-ev6` / `aw_run_loop6_evidence` — **delete that row if ever shared.** Loop 9 is paused mid-cycle
and is the live continuation point.

## Next steps

1. **Write the L9-2 exploration.** Create
   `openspec/explorations/2026-08-15-nothing-asks-whether-the-artefact-is-usable.md`. Content is
   already gathered: loop 8's finding 9 plus tonight's second reproduction — a fresh `git clone` of
   `C:\Users\huida\Documents\aw-loop9\.agentweave\worktrees\builder` fails with
   `ModuleNotFoundError: No module named 'roster_fairness'`; after `pip install -e .` it is
   `59 passed`; `pyproject.toml` has `[tool.pytest.ini_options] testpaths` but no
   `pythonpath = ["src"]`. The point is **not** the missing line — it is that the operator explicitly
   asked for a clean-checkout run, the builder's claim was conditional on an install step and
   literally true, and the verifier said *"I'll treat packaging separately from test correctness"*.
   Every actor behaved correctly and the artefact still cannot be cloned and run.
2. **Then L9-3**, in the same or an adjacent exploration: agents are isolated by worktree, not by
   environment; a builder running `pip install -e .` changes what its own reviewer imports. Evidence
   is the verifier's own words in `run-89e044c4`.
3. **Prove the autonomous driver before relying on it.** Run
   `powershell -File .claude/skills/autonomous-session/scripts/install-driver.ps1 -EveryMinutes 15
   -UntilHHmm "<time>"` with a trivial `STATE.json`, confirm a Scheduled Task fires `claude -p` and
   produces a commit, then unregister. Until this is done the skill's central claim is untested.
4. **Finish loop 9** if the operator wants the integration half exercised: send the verifier's three
   rejections back to `builder` on `task-6de550a5`, re-verify, approve, and watch the merge.

## Open questions for the user

1. **Which of the four next steps first?** My recommendation was L9-2 + L9-3 together — they are the
   same gap seen from opposite directions — but the operator has not chosen.
2. **Should the six outstanding openspec changes be archived?** The ordering constraint between them
   is getting hard to hold in one head. Full order: `2026-08-13-approved-means-it-is-in-the-product`,
   `2026-08-14-what-the-product-actually-built`, `2026-08-14-the-loop-agents-can-drive`,
   `2026-08-14-the-seams-loop7-found`, `2026-08-14-a-failed-run-does-not-eat-its-input`,
   `2026-08-14-what-a-failure-tells-the-operator`.
3. **Delete the `autonomous_work` branch?** It is fully merged.
4. Carried, still unanswered: should `.claude/handoffs/` stay tracked (**now 132 files**)?

## Read on resume

- `.claude/autonomous/2026-08-15-overnight-log.md` — the overnight record: every finding with its
  evidence, including where I contaminated my own test. Read before acting on L9-2 or L9-3.
- `.claude/skills/autonomous-session/SKILL.md` — the new skill, and the post-mortem of why the loop
  died. Its "What this skill learned" section is the condensed version of this session's dead ends.
- `openspec/changes/2026-08-14-a-failed-run-does-not-eat-its-input/design.md` — D2a is the
  binding-conflict carve-out and the reasoning the operator approved.
- `openspec/changes/2026-08-14-what-a-failure-tells-the-operator/design.md` — D3 carries the L9-1
  correction and the rule "surface a person reads vs. value held in memory".
- `hub/hub/api/v1/agent_trigger.py` — where both changes live; the four Change A sites and
  `_runtime_failure_fields`.
- `openspec/explorations/2026-08-14-loop8-a-dead-runtime-eats-the-message.md` — findings 8 and 9 in
  their original form, which step 1 builds on.
