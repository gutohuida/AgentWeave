# AgentWeave codebase survey — running notes

Session started 2026-08-23. Branch `fix/2026-08-23-design-audit-remediation` @ 17e33eb.
Purpose: map every path/feature/flow; flag code-read suspicions; design a stress test that
proves or kills each one.

## Scale (measured)

| | |
|---|---|
| Hub Python | 46,080 lines, ~75 modules |
| Hub UI (ts/tsx) | 53,073 lines, 23 component dirs |
| CLI | 7,997 lines, 5 commands |
| REST routes | **172** across 28 router modules |
| MCP tools | 21 (`mcp_server.py`) |
| DB migrations | 85 (head `0085_conversation_lineage`) |
| DB tables | 46 |
| Hub tests | 180 files |
| UI tests | 136 files, 1,356 assertions |

## Feature inventory (from the route surface)

1. **Projects** — create/open/relocate/delete, settings, main-branch suggestion, fs browse, native dialog
2. **Runners** — CRUD, launchability probing (per-runner and per-provider), model catalog
3. **Agents** — roster CRUD, archive/unarchive, bindings, charters, canonical context, timeline, launchability
4. **Charters** — CRUD, 9 seeded starters
5. **Runs** — trigger, stop, sessions, reconciliation, divergence, task binding
6. **Conversations** — list, rename, release-task, chat history, lineage, titles (worker-generated)
7. **Inbound queue** — per-agent durable queue, hop budget, turn delivery cap, withdraw
8. **Tasks** — CRUD, board(s), transitions (declared machine), dependencies + gate, integrations, divergences
9. **Spec flow** — documents (create/adopt/rename/arrange/merge/phase), lifecycle, rigor, proposals, requirements, coverage, evidence + decisions + reviews, drift detect/resolve, reindex, corpus adopt
10. **Jobs + Loops** — cron jobs, history, manual run, archive; loops (purpose/stop_at/stop_when_queue_empties), control, archive
11. **Questions** — ask/answer/decline (`ask_user`)
12. **Permissions** — request/decide/dismiss (Claude `--permission-prompt-tool`, Codex `decide_approval`)
13. **Checkpoints** — list, render, continue, cutover, dismiss-warning; worker-generated
14. **Accounting** — per-project + per-conversation usage, budget
15. **Worktrees** — per-agent isolation, conflicts
16. **Logs / Events / SSE** — event history, ticketed SSE stream
17. **Messages** — agent-to-agent peer mail

## Architecture notes worth carrying

- **Single choke point for spawning.** `trigger_agent_directly` has exactly one non-test caller:
  `turn_scheduler.schedule_agent`, which holds a per-`(project, agent)` `asyncio.Lock`. So the
  "one run per agent" invariant is not TOCTOU-vulnerable. Good.
- **Identity is never accepted from the caller.** `AW_AGENT_IDENTITY` / `AW_RUN_ID` / `AW_RUN_TOKEN`
  are stamped into the child env; `HUB_API_KEY`, `HUB_PROJECT_ID`, `DATABASE_URL`,
  `AW_BOOTSTRAP_API_KEY`, `AW_TICKET_SECRET` are explicitly popped. Genuinely careful.
- **The task lifecycle is a declared machine** with per-edge actor permissions, entry statuses, and
  no forced-move override. Author/reviewer separation compares *agent*, not run id.
- **Two independent gates** on `-> in_progress`: `dependency_gate` and `requirement_gate`, both
  called inside `apply_transition` rather than by each caller.
- Code quality is unusually high: nearly every non-obvious line carries a comment saying what
  broke last time. Several comments record live-driven defects and their fixes.

---

## Code-read suspicions (UNVERIFIED — each needs a live test)

Numbering is stable; the test plan refers to these IDs.

### S1 — Hop budget is admission-only, not delivery-enforced *(likely real, medium)*
`turn_scheduler.py:50-65`. `can_start` returns true if **any** entry is within budget, then
`selected` takes **every** entry in that conversation with no `hop_depth` filter. So an entry at
depth 50 rides along on a turn admitted by a depth-0 operator message.
Worse: `turn_depth=min(entry.hop_depth for entry in selected)` (line 91), and
`agents.py:1400` computes the next hop as `source_run.turn_depth + 1`. So batching a depth-0
operator entry with a depth-6 agent entry produces a turn at depth 0, whose outbound messages are
depth 1 — **the runaway guard resets downward**. Test: T-HOP.

### S2 — 32-bit IDs on unbounded tables *(likely real, high at scale)*
`utils.short_id()` = `str(uuid4())[:8]` = 32 bits. Used as the **primary key** for 38 entity kinds,
including `event_logs` and `agent_outputs` — the two highest-volume tables, and the only two with
**no pruning anywhere in the codebase** (`_prune_job_history` keeps 100 JobRuns; evidence retention
covers evidence). Birthday bound: ~50% chance of a collision at 77k rows, near-certain by 200k.
`record_agent_output` (`output_recording.py:80-93`) does `db.add(); await db.commit()` with no
IntegrityError handling. Trial DB today: 806 event_logs, 665 agent_outputs — far from it, but a
single verbose run emits hundreds of output rows and nothing ever deletes one. Test: T-ID.

### S3 — One DB transaction per output line *(performance, needs measurement)*
`record_agent_output` commits per row, and `persist_event` also commits. A verbose agent turn
therefore does one fsync-ish commit per streamed chunk. Test: T-THROUGHPUT.

### S4 — Cron read two ways in one file *(confirmed by reading; UI impact to verify)*
`scheduler.py:677-684` builds an APScheduler `CronTrigger`, which **ANDs** a restricted
day-of-month with day-of-week. `scheduler.py:803-804` computes `job.next_run` with `croniter`,
which **ORs** them. Same cron string, two live readings, ~130 lines apart. Only diverges when both
DOM and DOW are restricted (e.g. `0 0 1 * 1`). Test: T-CRON.

### S5 — Scheduler pinned to UTC, UI says "server time" *(confirmed in code)*
`scheduler.py:626` and `:683` both pass `timezone="UTC"`. Verify the UI copy. Test: T-CRON.

### S6 — A loop claim is recorded as an operator action *(honesty, low)*
`scheduler.py:978`: `apply_transition(session, claimed_task, "assigned", operator())`. The loop —
not a person — claimed it, but the transition history will say the operator did. The whole point of
the transition machine is that "every recorded history describes a legal sequence" worth reading.
Test: T-LOOP (read `task_transitions` after a firing).

### S7 — A stopped loop sets `job.enabled = False` permanently *(design, verify recovery)*
`scheduler.py:878` + `remove_job`. If an operator re-enables a job whose loop already stopped
(`ending_state` set, `stopped_at` set), does it immediately stop again, resume, or spin?
Test: T-LOOP-RESTART.

### S8 — `_agent_locks` never evicts
`turn_scheduler.py:19,30`. Unbounded dict keyed by `(project, agent)`. Trivial leak; noted, not
worth a test.

### S9 — `LoopSummary` cannot distinguish "paused" from "waiting to fire"
Known and documented at `loopCounts.ts:15-17`. The new `idle` bucket collapses both. Operator
question #2 from handoff 0076. Test: T-LOOP (observe the badge in all four states).

### S10 — Skipped firings still count as runs
`scheduler.py:796-797` increments `job.run_count` and sets `job.last_run` before any skip branch.
So "ran 40 times" can mean "was skipped 40 times". The `Last 5` run-health dots read JobRun rows,
which do carry `status`, so the dots may be honest while the count is not. Test: T-LOOP.

### S11 — No delete path for a spec document *(known, carried from handoff 0076)*
No DELETE route; `archived` reachable only from `approved`; `approved` unreachable with no
requirements. A document created by mistake is permanent. Sandbox has one already:
`spec/changes/emerald-thunderbird/spec.html`.

### S12 — `worker_dir_context.cleanup()` is not in a `finally`
`worker.py:463`. If `_interpret` raises, the temp dir leaks. Low.

---

## Still to survey

- `codex_appserver.py` (1016) — the Codex JSON-RPC transport + approval path
- `spec_service.py` (891), `requirement_evidence.py` (793), `spec_documents.py` (557)
- `run_task_binding.py` (497), `run_divergence.py` (383), `run_reconciliation.py`
- `checkpoint_*` cluster (~1600 lines total)
- `worktrees.py` (460), `project_workspace.py` (265)
- `agent_auth.py`, `auth.py`, `permission_requests.py`
- `mcp_server.py` (1193) — the agent-facing tool surface
- UI: OverviewPage, SpecPage/PanelShell, TasksBoard, DependencyBoard, ConversationView
