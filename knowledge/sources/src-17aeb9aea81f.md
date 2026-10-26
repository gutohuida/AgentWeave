# Retrospective: the slow flow of 2026-10-25 and the performance overhaul

Written 2026-10-26 by Claude Code at the operator's request. It covers why the AgentWeave flow
`loop-df5f74816122` ("The app stays responsive while agents run", document `spdoc-ccf9b922a958`)
was slow, what the overhaul then built outside AgentWeave in one Claude Code session, what the
comparison teaches, and what to improve. It supersedes the Architect's draft of 2026-10-25
(`.agentweave/worktrees/Architect/.agentweave/vault-drafts/2026-10-25-why-the-responsiveness-slice-was-slow.md`,
never added to the vault because the tool server timed out), and keeps everything it found.

Sources: read-only queries of the operator's `:8000` database (`task_transitions`, `runs`,
`task_check_runs`, `agent_outputs`, `turn_usage`); process and memory readings taken on the machine
on 2026-10-25 around 21:36 UTC; the acceptance drives `scripts/drive/perf_*.py`; and the commits on
master from `c3cea95` to `afa5bf4`.

## 1. The flow, in numbers

- It started at 14:10 UTC. At 21:36, after 7 h 26 min, 4 of its 6 tasks were approved; `b9bf0f`
  was back in revision and `0759b1` was stuck.
- 48 agent runs: QA 24 runs (295 min), Developer 9 (122 min), DeveloperOpus 3 (182 min), mender 11,
  Architect 1 (54 min). 16 check-gate runs, about 147 min in total. 9 send-backs. 7
  `review_unstaffed` stalls.
- About $52 API-equivalent, $19.50 of it on QA's turns.

## 2. Where the time went, largest cost first

1. **One reviewer for everything.** QA was busy about 80% of the time after the first review.
   Finished work waited about 3.3 h in total for review (`b9bf0f` 37 and 43 min, `000ad5` 34 min,
   `76f78d` 27 min). From 16:15 four tasks were built in parallel and all drained through QA, whose
   turns ran 10–33 min because they re-ran tests and then waited on the gate. QA2 was created
   afterwards, but the flow's `delivery.reviewer: "QA"` is a single declared name, and the
   reviewer ladder never substitutes for a declared reviewer, so QA2 could not have helped.
2. **The drive task ran alone for 2 h 04 min.** Four tasks depended on "Acceptance drive, written
   and failing first". It took three review rounds, and both send-backs were real (the drive wrote
   into the real repository; its evidence did not match the code).
3. **About half the send-backs were not about the code.** Real defects: the drive (twice); `000ad5`
   (stream events handled twice); `76f78d` (two state changes with no stream event). Caused by the
   Hub instead:
   - *Prerequisite merges invalidated accepted evidence* (`task-5cae616b4bd4`): the Hub's own "Bring
     in approved prerequisite work" merge moved the branch head past the evidence's commit, and
     approval refused with 409. Three times on `0759b1`.
   - *Branches missing prerequisite commits, or conflicting with them* (`000ad5` once, `b9bf0f`
     twice), once in the generated UI bundle.
4. **The check gate was slow and flaky.** hub-tests (~8,900 tests) took 5–12 min a run and ran
   again on every approval attempt and every main move. A result counted only for the exact
   (main commit, branch commit) pair. 4 of 13 finished runs failed only on flaky tests the work
   did not touch (`test_a_run_main_moved_past_is_superseded_and_replaced`,
   `test_a_started_hub_prints_the_path_of_the_tool_server_it_pinned`,
   `test_the_continuation_uses_the_remaining_deadline`). `0759b1` alone lost about 1.5 h to them.
   One gate run hung for 83 min after an xdist worker crashed, because the suite had no per-test
   timeout.
5. **The database lock blocked approvals.** QA's approvals failed 8+ times with 503 "database is
   busy (locked >30s)". The database ran a rollback journal, so every commit blocked every reader;
   approval also held its write transaction across git merge-tree, the merge into main and a
   snapshot (`task_transition_service.py:816–924`).
6. **The flow staffed agents it should not.** It gave a build task (`0759b1`) to the mender, and a
   builder task (`59aa8e`) to the Architect.
7. **A deadlock with no exit.** The mender re-recorded evidence on `0759b1`, so the Hub counted it
   as the author. The task sat in `completed` held by the mender: the author may not move it to
   review (403), QA could not move a task the mender held, `completed → approved` is not allowed
   (409), and `mend_reset_task` refused too. Three sensible rules combined into a dead end.
8. **Every hand-off waited for the 5-minute tick.** `completed → under_review` and
   `revision_needed → in_progress` happened only when the flow fired; about 20 hand-offs, roughly
   40 min.
9. **The machine was saturated.** At 21:36 there were 55 Python processes holding 15 GB, with 2.2 GB
   of 32 GB free: four drive Hubs left over from 10-20 to 10-24 (ports 8130, 8116, 8117, 8019), a
   pytest from 10-22, an orphaned pytest from a stopped run, and the gate's `-n auto` (about 40
   workers) beside a second gate run and the agents' own suites. That load is what made the timing
   tests flake. Killing the leftovers freed 17 GB.
10. **The Hub itself was CPU-bound.** `:8000` had used 3.7 CPU-hours in 11.5 h on one event loop;
    git ran on the loop (turn start 1.0 s average, up to 20.8 s; approval 4.2 s). The mender's and
    the Architect's tool servers timed out connecting (30 s), and so did this session's.
11. **The fixes never reached the Hub that needed them.** `:8000` runs this checkout and was last
    started at 10:07. The four tasks the flow approved were merged into master, but their code and
    migration `0144` (the indexes for the list routes) did not take effect until a restart. The
    flow kept fighting slowness it had already fixed.
12. **Nobody could see why it was slow.** It took an Architect turn and then a Claude Code session,
    both writing SQL against the operator's database, to find where the time went.

## 3. What was built afterwards (Claude Code, 2026-10-25/26, all on master and pushed)

Five agents in isolated worktrees, one integrator merging, rebuilding the UI bundle once, and
running the full suites at the end (Hub 9,010 passed, 0 failed; CLI 577 passed after a stale skill
mirror was re-synced; UI 2,352 passed; ruff, black and mypy clean).

| Work | Result |
|---|---|
| Slice 1 finished: the flow's open branches `0759b1`, `b9bf0f`, `146c7b`, `ca661c` merged | Lists 22/24/18 ms against 60 ms; 50 open streams no longer exhaust the pool |
| Drive fix: the responsiveness drive now migrates its copy to head | It had measured without `0144`, so lists read 687–999 ms |
| Slice 2: WAL with full sync, consistent backups, 14-day trace retention, daily ANALYZE, migrations `0145`/`0146` | Read p90 under writes 2,430 → 90 ms; 20/20 drive checks |
| Slice 3: git, filesystem and spawns off the event loop, SHA-keyed git fact cache, batched line writes, cached spec lists | Loop stall at turn start 4.1 s → 14 ms, at approval 3.1 s → 14 ms; loop CPU per line 6.2 → 0.9 ms; `GET /loops` 10 → 2 git processes; 24/24 drive checks |
| Slice 4: first open coalesced, screens code-split, timeline memoized | 43 → 14 requests on open, 1.5 MB → 565 KB script, 4.8 → 2.9 s at 6x throttle; dropped frames while streaming 98% → 9% |
| Check gate | A pass is reused on an identical merged tree; a failure is re-run once before it counts; `-n auto` is a third of the CPUs; five flaky tests fixed; a failing suite keeps its traceback |
| Flow lifecycle | Evidence survives clean prerequisite merges; the mender is never staffed; the mender can hand finished work to review; flows advance on transitions (3 s debounce), with the tick as backstop |
| Flaky tests raised to the operator | The Overview lists the gate's flakes per test, with "Create a fix task" and "Dismiss"; a test that flakes again comes back |

## 4. Why the Claude Code session did better, and why that is not the whole story

The two runs were not a fair race. The flow started cold and wrote its acceptance drive first; the
Claude Code session started from a finished post-mortem, specs authored in AgentWeave, and the
flow's own finished branches. More importantly, the Claude Code session verified less: it trusted
each agent's report, ran targeted tests, and ran the full suites once at the end, with no
independent reviewer. QA in the flow caught four real defects; that step was skipped.

What genuinely made the difference:

- **Fewer, coarser hand-offs.** Each agent took a whole slice, and the integration cost was paid
  once per workstream. The flow cut one slice into six tasks with a dependency chain, and paid a
  tick, a reviewer wait and a full gate run roughly twenty times.
- **One owner with the whole picture.** The integrator saw that the drive measured an unmigrated
  copy, that `/loops` spent its time in git and not SQL, and that the worktrees were cut from an
  old commit, and re-planned around each. In the flow every agent saw only its own task; the
  mender and QA passed `0759b1` back and forth for 20 runs because neither could change the rule
  that blocked it.
- **No server in the way.** Claude Code had no Hub to choke on its own lock, no tick, and no gate.

## 5. What to improve in AgentWeave, by impact

1. **A lead (integrator) role with judgment.** Today's winning pattern was coarse work units,
   parallel builders, and one agent that merges, resolves conflicts, re-plans and runs the full
   gate once per batch. The mender is a reduced version of this that can reset but not decide.
2. **Gate per batch, not per approval attempt.** A merge queue: approved tasks queue, the full suite
   runs once on the batch, and a failure is bisected. This keeps the operator's "approval runs the
   full suite" while paying it once per batch.
3. **Coarser tasks by default.** One builder per slice, with commits inside it, and review per
   slice.
4. **A reviewer pool.** `reviewer` accepts a list; the ladder prefers an idle reviewer and queues on
   the least busy. A schema change to the delivery payload and its editor (Tier 1).
5. **A state-machine invariant test.** Every non-terminal task state always has some actor who can
   move it. That test would have caught the author deadlock before it happened.
6. **A flow health view.** Per task: time building, waiting for a reviewer, gating, waiting for the
   tick. The post-mortem in section 2 should be one screen, not SQL.
7. **Don't let the orchestrating Hub run the code it is editing.** Run AgentWeave's own development
   from a pinned release or a second checkout, and restart deliberately to pick up merged work.
8. **The Hub looks after the machine.** Reap the Hubs and test runs it spawned; size concurrency to
   CPU and memory; give the gate's suite a per-test timeout so a hang is a named failure.
9. **Approval should not hold the write lock across git.** Evaluate and integrate before writing the
   evidence decisions, or commit in stages.
10. **Keep the Architect off build work explicitly.** There is no "spec author only" concept; a
    `builders` list in the delivery, or another explicit marker, would do it (not charter names).

## 6. Why use AgentWeave at all

For interactive work on one repository, on a strong machine, with the operator at the keyboard,
Claude Code directly is better today, and AgentWeave cannot win that case by being a slower Claude
Code. AgentWeave earns its place where Claude Code has no answer:

- **Work that runs without the operator**, overnight and across days, with durable state, so a
  finished task cannot die with a session.
- **The work VDI**: Copilot (and later Codex) as runners behind one interface.
- **Independent verification**: author separate from reviewer, evidence tied to requirements, and
  the gate. That is what caught the flow's four real defects.
- **An auditable record**: specs, tasks, evidence, traces and this vault, rather than commits and
  an agent's word for what was checked.
- **Several projects from one dashboard.**

The lesson of 2026-10-25: AgentWeave's guarantees are worth having, but it pays for them per task
when it should pay per batch, and nobody in the middle exercises judgment. Build the lead role and
the merge queue, restart `:8000` onto the overhaul, then re-run a slice-sized job in AgentWeave and
compare wall time and real defects caught. That comparison is the evidence for keeping it.

## 7. Open after the overhaul (2026-10-26)

- `GET /loops` is about 200 ms against its 80 ms budget (was 2.5 s) and issues 38 statements against
  25: per-evidence footprint lookups (`task_integration.py:941`) and the remaining git
  (`task-3c9e187a57c3`).
- F787 (a new agent's first trigger held the write lock over 30 s) is probably gone with WAL and
  slice 3, but has not been re-driven.
- The gate records a test that fails only through another test's shared state as `flaky` when re-run
  alone. That is visible on the Overview, not blocking; confirming by re-running the whole check
  would cost one full run per real failure. An operator decision.
- In the app: stop the flow; approve `0759b1`, `b9bf0f`, `146c7b`, `ca661c` (their work is on
  master); close `07bd6f` and `5cae616` as fixed; approve then archive the slice 2 and slice 3
  documents; archive slice 1 and the roadmap; set the hub-tests command to
  `py -3.11 -m pytest hub/tests -q -p no:cacheprovider -n auto --timeout=600`.
- The next `:8000` restart converts the database to WAL and runs migrations `0144`–`0146`. Traces
  older than 14 days are swept 30 s after start; the data begins 10-21, so nothing is deleted before
  11-04.
