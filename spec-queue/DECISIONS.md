# Decisions waiting for the operator

The backlog of questions the unattended windows could not answer for themselves. Written by the
windows, cleared by the operator, and **durable** — before 2026-09-01 these lived only in
`STATE-night.json`, which each window rewrites, so the list survived by being copied forward by
hand and had drifted into duplicates.

Contract, matching `APPROVALS.md`: **the status token is the authority.** One row per decision.

```
- OPEN      <id>  the question
- DECIDED   <id>  what was decided, and when
- DEFERRED  <id>  why, and what would reopen it
```

A window may **add** rows and may sharpen an OPEN row's evidence. A window may never mark one
DECIDED. Absence is not consent.

---

## Open

### F489-fix: how should the Hub learn a Copilot turn's failure cannot succeed on retry? -- 2026-10-06 night, DECIDED 2026-10-06

- DECIDED   f489-retry-signal  **(a): a Copilot-only `retryable: Optional[bool] = None` on
  `copilot_acp.TurnOutcome`, set `False` for an `authentication` or `quota` `errorType`, threaded
  through the one app-server call site; the entry is withdrawn at once with its own
  `abandoned_reason`** (operator, 2026-10-06, as recommended in the morning briefing). Every other
  failure keeps today's retry behaviour; Codex's `TurnOutcome` is untouched; no new hold variant.
  The question was: how the no-retry signal reaches `return_run_entries`, and what
  "waits for the operator" means when there is no reset time to wait for.

F489 (`scripts/drive/FINDINGS.md`) names the direction but not the design: a turn that failed with
a root `session.error` whose `errorType` is `authentication` (or `quota`) should not be retried.
Traced the retry seam before touching code, per tonight's `next_action` instruction to stop rather
than guess if it needed more than a one-sentence choice. It does:

- The one caller of `return_run_entries` (`hub/hub/inbound_queue.py:297`) that has a `TurnOutcome`
  for Copilot's ACP path is the app-server executor's finalize block
  (`hub/hub/api/v1/agent_trigger.py:4029`) — the PTY/exec path's own call (`:3029`, Claude's
  `_execute_run`) never sees a Copilot `errorType` at all, so only one call site is in scope.
- `TurnOutcome.error` (`hub/hub/copilot_acp.py:1953`) carries only the rendered message string.
  The normalized `kind` Copilot's `_session_error` derives from `errorType`
  (`hub/hub/copilot_acp.py:1323-1328`, e.g. `copilot.authentication`) exists only inside the
  `error_event(code=f"copilot.{kind}", ...)` it builds, which becomes a `RunEvent`
  (`hub/hub/runner_events.py:319`) persisted as agent output — never threaded onto `TurnOutcome`,
  `Run`, or anywhere `return_run_entries` or its caller reads today.
- `error_event` already takes a `retryable: bool = False` parameter
  (`hub/hub/runner_events.py:324`) that no call site anywhere sets `True` on, and nothing reads —
  it is decorative today. Wiring the retry decision through it would make every existing error
  non-retryable by default unless every other call site is also audited and given `retryable=True`
  explicitly — a much bigger blast radius than F489 asks for.
- There are two structurally-identical but unrelated `TurnOutcome` dataclasses
  (`hub/hub/codex_appserver.py:905` and `hub/hub/copilot_acp.py:1947`, duck-typed, no shared base).
  Adding a field means deciding whether it lives on both (generalizing to Codex, which has its own
  failure shapes and no `errorType`) or only Copilot's.
- "The entry waits for the operator, as an allowance hold does" is ambiguous between (a) the
  existing `DELIVERY_ATTEMPT_LIMIT` withdrawal (`hub/hub/inbound_queue.py:354-362`), just triggered
  on the first failure instead of the third, with no resumption path except a fresh operator
  message, and (b) a real hold like `provider_allowance.py`'s `ProviderHold`/`arm_allowance_wake`,
  which needs a `resets_at` an authentication failure never has.

**Candidate options**, no recommendation forced:

(a) Add `retryable: Optional[bool] = None` to `copilot_acp.TurnOutcome` only (`None` = today's
behaviour, unchanged for every other failure); set `False` when `_session_error`'s `kind` is
`authentication` or Copilot's own `quota` (captured alongside `root_error`, not derived from its
message text); thread it through the one app-server call site as
`return_run_entries(db, run_id, refusal=refusal, retryable=outcome.retryable)`; when `retryable is
False`, withdraw the entry immediately — skip `RESUME_RETRY_LIMIT`/`DELIVERY_ATTEMPT_LIMIT` — with
its own `abandoned_reason` naming the failure.

(b) Same signal, but instead of immediate withdrawal, hold the agent's queue the way `ProviderHold`
does, with no `resets_at` (held until the operator sends a new message or rebinds) — a new,
narrower hold variant alongside the existing one; more code, more surface, and a second kind of
"held" for the status route and UI to describe correctly.

(c) Skip `TurnOutcome` entirely: after the commit, have `return_run_entries`'s caller read the
run's own persisted `error` `RunEvent` by `run_id` and check its `code`/`retryable` there, instead
of carrying a new field through the dataclass. Avoids touching `TurnOutcome` but adds a DB read on
every failed-run finalize and a new dependency from the queue module on the agent-output storage
format.

Blocks `f489-impl` only; the night queue tonight was otherwise finished before this item, so
nothing else is held up by it.

### `the-shell-judge-reads-a-word-whole` task 2.3 names a file list that no longer exists -- 2026-10-04 night, DECIDED 2026-10-04

- DECIDED   shell-judge-2-3-eight-files  **(c): rewrite task 2.3 to name its files, chosen by (a)'s measurement** (operator, 2026-10-04, as recommended): run the whole `hub/tests/` suite at the commit before the change and at the tip; every test whose outcome moved must be one of task 1.8's rows or a new row. The dead "eight files" back-reference is dropped, not recovered. The question was: Task 2.3 (`tasks.md`) reads "Run the eight files named
  in design D2 plus the new file; expected moves are exactly task 1.8's rows plus the new rows."
  Re-derived fresh against `design.md`'s own D2 section (lines 239-332) before building, per the
  round discipline: D2 describes rule 6's mechanics in full and never names eight specific files
  anywhere in its own text. The only "eight test files" sentence in the whole document (line 352,
  "R1's prototype measurement (D2-D5, no D1), over eight test files: 9 failed, 445 passed, 1
  skipped") is a pass/fail count from an early prototype measurement run via a `testbed/scratch/`
  script, which is gitignored by policy and not present on disk or findable in git history (checked
  `git log --all --diff-filter=A` for a committed prototype/measure script predating the
  gitignore; found nothing that names eight files). `hub/tests/` today holds 19 files plausibly in
  scope for a permission/workspace move-count (`test_permission_approver.py`,
  `test_the_shell_judge_reads_a_word_whole.py`, and 17 others); nothing in `tasks.md`, `design.md`
  or `proposal.md` picks exactly eight of them by name.

  **The question: what does "the eight files named in design D2" now refer to?** Candidates: (a)
  re-run the R1-era measurement script's intent against today's full `hub/tests/` suite and report
  the move counts for whichever files actually move (the "eight" may simply be stale once D1 was
  added on top of D2-D5's original prototype); (b) the operator recalls or can find the original
  eight (if the prototype script or its file list survives somewhere off this repo); (c) rewrite
  task 2.3 to name its files explicitly rather than by a now-broken back-reference. No
  recommendation yet -- this surfaced an hour before this row was written and has not been explored
  beyond the two greps above. Blocks task 2.3 only; 2.4 and 2.5 have no such ambiguity and can be
  built directly.

### `a-copilot-one-shot-records-its-credits` is ready for approval -- 2026-10-03 night, DECIDED 2026-10-04

R1, R2 and R3 are done (iters 21-23). The adversarial Opus review
(`spec-queue/tracks/reviews/copilot-oneshot-credits-2026-10-03.md`) confirmed seven problems, and
all seven fixes are applied. The change's `design.md` round log lists them. No code is written.
The change does what `copilot-oneshot-credits` (DECIDED 2026-10-02) asked for. A Copilot
checkpoint call, and its probe, would record the AI credits and premium requests from the last
`session.usage_checkpoint` in the one-shot's output into `worker_invocations`. Today both columns
are NULL for every Copilot worker call. No screen shows them yet, because no route reads them
(D5). Its code reaches `:8000`'s agents on the operator's next restart.

- DECIDED   copilot-oneshot-credits-approve  **Approved for `-impl`** (operator, 2026-10-04, as recommended), as R3 plus the Opus review's seven fixes left it, D2's shared `2**53 - 1` helper included. The question was: **Approve the change for implementation, or send it
  back?** The decision that matters most is design D2. One shared helper reads a checkpoint's two
  figures for both the one-shot and the Copilot run ledger. It refuses any figure that is
  negative, boolean, non-numeric, non-finite, or above `2**53 - 1`. That last bound came from the
  review. It found that R3's column-sized bound (`2**63 - 1`) would let one bad run checkpoint
  make SQLite's `sum()` raise `integer overflow` on that project's accounting routes, a lasting
  500 (measured). The new bound leaves a residual: it takes 1025 rows at the ceiling to overflow a
  sum. The same helper also changes a **run's** behaviour. Today a malformed checkpoint makes a
  completed Copilot run be recorded `failed` (read from the code, not driven). After the change,
  that run's session credit total is unknown and the run stays completed. The spec delta
  MODIFIES the run requirement to say so. Credits on a non-zero exit stay unread (D4), as no
  failing one-shot has ever been captured. The drive (task 3.1) spends at most two Copilot
  Free-plan calls on `:8010`.
- DECIDED   copilot-oneshot-credits-oq1  **Yes, a real task** (operator, 2026-10-04, as recommended): `worker-spend-counts-against-the-budget`'s next round gains a task, a test and a spec-delta line for the per-`workers`-line credit sums, carrying D2's sum-overflow hazard. The question was: **Should `worker-spend-counts-against-the-budget`'s next
  round gain a real task, a test and a spec-delta line for the per-`workers`-line credit sums,
  carrying D2's sum-overflow hazard (design Open question 1, F486)?** The archived
  `a-copilot-run-shows-its-credits` assigned those sums to that change (its D12 and task 6.4). The
  change's own files never mention them. The recommendation is **yes**, as a real task rather
  than a round-log note: a note is not a task, and that gap is how F486 arose. Your D7 answer on
  that change does not affect this, because every D7 branch keeps the `workers` lines.

### `a-copilot-agent-uses-hooks-and-its-own-agents` task 1.1: the explore agent didn't dispatch as a subagent -- 2026-10-03 night, DECIDED 2026-10-04

- DECIDED   ghcp-s5-subagent-capture  **Group A proceeds in full, subagent scenarios kept** (operator, 2026-10-04: "Do we need to upgrade the copilot version? Try upgrading it and running it again. If it fails again, try A and read the documentation. If it does not work let's go with B."). Driven interactively the same morning, in that order:
  1. **Upgrade.** Copilot had already auto-updated 1.0.90 -> 1.0.91 (2026-10-03 18:57, after 7.1/7.7 ran on 1.0.90); the Hub spawns with `--no-auto-update`, so its runs use 1.0.91. Re-ran 7.1's exact prompt on `:8010` (`run-0bb0b8f3d0db`): `task` with `agent_type: "Explore"` and no `model` failed `Model 'sonnet' is not available`; no `subagent.*`. **The upgrade alone does not fix it.**
  2. **(a), with the dispatch spelled correctly.** `agent_type: "explore"` (the built-in's real id) and `model: "claude-haiku-4.5"` (on the Free plan): **succeeded** on `:8010` (`run-d77553067285`, result `README.md`, `is_error: false`, the subagent's own `read`/`shell` calls nested in it). The raw capture (`testbed/copilot-capture/capture.py`'s harness, same prompt) **delivered `subagent.started` and `subagent.completed`**, sharing the `task` call's `toolCallId`, in this wire order: `tool.execution_start`(task) -> `subagent.started` -> the subagent's tool events, each with `parentToolCallId` -> `subagent.completed` -> `tool.execution_complete`(task). It replaces `hub/tests/fixtures/copilot/subagent.jsonl` (redacted; no test read the old one). A second capture isolated the two variables: `"Explore"` + haiku fails cleanly (`Unknown agent_type: Explore. Valid types are: explore, ...`), and **`code-review` + haiku dispatches and emits `subagent.started`/`completed` with `agentName: "code-review"`** -- so D8's review dispatch can work.
  3. **Documentation.** The `custom_agent_prompt` error 7.1 hit is upstream bug github/copilot-cli#5030 (ACP mode: `task` cannot launch custom agents since 1.0.89; open; workaround `--prefer-version 1.0.88`). In 1.0.90-1.0.92-3 the ACP host-effect bridge calls `runServerHostEffect`, which has no `custom_agent_prompt` case (read in `app.js`). Built-in agents called by exact id with an available model do not take that path. `explore.agent.yaml` lists only GPT models; where `sonnet` came from on `:8010` is **unverified** (inferred: `cp5` runs in this repo's worktree, whose instruction files mention Sonnet, and 1.0.81+ lets subagent launches take a model preference from instruction files; the scratch-cwd captures never hit it).
  (b) was not needed. **Consequences for the build:** group A's tasks 1.2-1.6 and 2.1-2.8 are unblocked; `subagent.failed` has no real capture yet (synthesize it in 1.2, or capture it from a dispatch that fails after starting). **D8 needs a follow-up:** its review-turn bullet should name the exact agent id and a model the runner can use, or a Free-plan agent's dispatch fails before starting -- and F484 (the false "the code-review agent agreed" claim) stands either way. Side observation: in `run-d77553067285` the subagent's `read` was `Denied by preToolUse hook from "repo settings" (hook errored)`; not investigated. The original question was: **Real capture (task 1.1, 2026-10-03) found `subagent.started`/
  `subagent.completed`/`subagent.failed` not delivered**, the one part of design D1's six-type claim
  this capture could not confirm. `session.compaction_start`, `session.compaction_complete` and
  `session.error` all held, real, over ACP (fixtures: `hub/tests/fixtures/copilot/
  {compaction,error}.jsonl`). For `subagent.*`, run (b) prompted `Use the explore agent to name one
  file in this directory, then stop.` on the Free plan's Auto model (routed to `mai-code-1.1-flash`)
  against an empty scratch workspace. The model called `list_agents` (a background-job listing,
  unrelated), then did the `glob` itself and answered — it never dispatched a subagent, even though
  a built-in `explore.agent.yaml` exists in the installed 1.0.90 package and the prompt named it by
  name. `subagent.jsonl` was saved anyway (the `tool_call`/`tool.execution_start` pairs from that
  run, no `subagent.*` event in it). Per task 1.1's own instruction ("if a type is not delivered,
  stop group A, tell the operator"), group A (tasks 1.2-1.6, 2.1-2.8) has **not** been started.
  Full capture detail: design.md Round log, *Task 1.1, real capture, 2026-10-03*.

  **The question: how to proceed with group A.** Options, not mutually exclusive:
  (a) retry the capture with a bigger exploration task and a non-empty scratch workspace (a few
  more Free-plan calls — the operator's budget note for 1.1 was "~5 calls", already spent by runs
  a-c; a retry needs fresh authorization for however many more it costs);
  (b) drop the three `subagent.*` scenarios from `agent-stream-events` and tasks 2.2/2.3, and build
  group A's compaction+error mapping only (1.2's first and second bullets, 1.3, not 1.2's
  `subagent.jsonl` bullet);
  (c) leave group A stopped and move to groups C/B/D (already the night queue's order) until the
  operator has time to look at this.
  Recommendation: (c) now, (a) or (b) when the operator is next interactive — this is exactly the
  kind of real-capture surprise the round discipline exists to surface, not something to guess
  past unattended.

  **Addendum, 2026-10-03 night, task 7.1's real capture on the trial Hub `:8010`** (design.md
  Round log, *Task 7.1, real capture, 2026-10-03*): the same prompt, this time through the Hub's
  own `agent/trigger` path rather than a scratch harness, got the model to *try* dispatching a
  subagent via the `task` tool (`agent_type: "Explore"`) twice — unlike run (b), which never tried.
  Both attempts errored before any subagent session opened: first on an unavailable default model
  (`'sonnet'`), then, retried with `model: "auto"`, on `host interaction call failed: Error:
  Unsupported native sessions host effect 'custom_agent_prompt'`. No `subagent.*` event of any kind
  reached the timeline or chat either way.

  **This narrows the question.** It is no longer "does the model try" (sometimes it does) but
  "can this Copilot CLI version's native-session dispatch path succeed at all" — and on this one
  real attempt, it could not, on a host effect the session apparently does not support. That makes
  option (a) above (a bigger exploration task) look unlikely to help by itself, since the failure
  is mechanical, not a matter of the model declining. Still OPEN pending the operator — this is
  more precise evidence for the same open call, not a new recommendation; (a) might still be worth
  one more attempt with `model` passed from the start (both failures here came from an initial
  call that omitted it), but that is itself a guess, not something driven this iteration.

  **Addendum, 2026-10-03 night, task 7.2 (the compaction backstop)** (design.md Round log, *Task
  7.2, real mapping, 2026-10-03*): ran the captured `compaction.jsonl` through the production
  `CopilotEventMapper` directly, before touching the trial Hub. It emits **zero** events for either
  `session.compaction_start` or `session.compaction_complete` — `on_raw_event` only branches on
  `session.error`/`warning`/`info`, the two MCP-server-status types, and the three model-resolution
  types; compaction falls through to `return []`. Task 2.3 (the mapper's compaction branch) and
  task 2.4 (`consider_from_compaction`, `checkpoint_trigger.py`) are both unwritten — grepping all
  of `hub/hub/*.py` for `"compacted"` found zero matches. Task 7.2 cannot be completed as written:
  there is nothing for its one-off script to map or `POST` that would produce a `compacted` card,
  because the code that would create one does not exist. This is the same blocked range this row
  already names (*"group A (tasks 1.2-1.6, 2.1-2.8) has not been started"*), now confirmed against
  a second drive task rather than just task 1.1's. `tasks.md` 7.2 left unchecked, marked blocked.

  **Addendum, 2026-10-03 night, task 7.3 (error once)** (design.md Round log, *Task 7.3, real
  drive, 2026-10-03*): restarted the trial Hub `:8010` with `MY_ANTHROPIC_KEY=invalid` in its
  process environment (the only way a provider runner's `api_key_var` reaches an already-running
  Hub, since `os.environ` is read live at spawn — `hub/hub/runner_provider.py:268`), built a group
  C BYOK runner naming that variable, and ran `cp5` for real. The real timeline (`GET
  /agent/cp5/chat`, not the admin `/agents/{name}/timeline` 7.1/7.2 used — that one is EventLog-only
  and never carries an `AgentOutput`-kind error) shows **three** `error` entries, one per retried
  attempt, each `payload.code == "copilot_session_error"` — the literal string `_notice_event`
  hardcodes for a root `session.error` (`hub/hub/copilot_acp.py:1125-1134`) — never
  `copilot.<errorType>`, and no `facts`/`status_code`/`remediation`. Task 1.3 (the
  `copilot.<errorType>` + `facts` shape) sits inside this row's already-named unstarted range
  (1.2-1.6); the triplication is a dedup gap the same unstarted range would need to add. A third
  confirmation of the same blocker, by a third independent drive task. `tasks.md` 7.3 left
  unchecked, marked blocked with the full captured entry inline. `cp5` restored to its original
  non-BYOK runner afterward.

  **Addendum, 2026-10-03 night, task 7.7 (a fourth way, and a new finding)** (design.md Round log,
  *Task 7.7, real drive, 2026-10-03*): set `cp5.copilot_review_agents = ["code-review"]`, recorded
  real operator evidence on `task-ceea0a23940f` at commit `817a4aa775dce442b57b7423113fc945af5d677d`
  (merge-base with `master` is `72b95db33864f21f73a66649f71cd596358b4bcf`), and dispatched a real
  review turn (`POST .../agent/trigger` with `review_task_id`). The rendered context file
  (`.agentweave/reviews/cp5/.agentweave/context/cp5.md:15`) carried design D8's bullet verbatim,
  naming the real range: *"Before your verdict, run Copilot's `code-review` agent as a subagent on
  the changes from `72b95db33864f21f73a66649f71cd596358b4bcf` to
  `817a4aa775dce442b57b7423113fc945af5d677d`."* The first attempt (`run-8d29230e8279`) ran 22
  commits/53 files' worth of its own ad hoc test suites (`hub/tests`, dashboard Vitest, lint,
  type-check) for the full 600 s and was killed: `"Copilot did not finish the turn within 600 s"`.
  The Hub auto-resumed it as `run-c1339b044701`, which continued the same ad hoc verification, found
  a real defect (below), and called `update_task` with `status: "revision_needed"` — confirmed by
  the matched `tool_use`/`tool_result` pair on `agentweave-update_task` at 17:41:30, and the task's
  own `assignee` and `status` fields afterward.

  **Open question 7 did not get answered, because `code-review` was never dispatched.** The full
  `GET /agent/cp5/chat` timeline for both runs (`run-8d29230e8279` and `run-c1339b044701`) uses
  exactly four tools across its whole length — `rg`, `shell`, `edit`, `agentweave-update_task` — and
  zero `subagent_started`/`subagent_completed`/`subagent_failed` events appear in the project's
  `EventLog` for `cp5` at all (checked by event type, each query empty). There is no tool call that
  could be a `code-review` (or any) subagent dispatch anywhere in the conversation. This is the same
  shape this row already names for `explore` (task 1.1) and for the attempted-but-mechanically-failed
  dispatch (task 7.1's addendum) — a fourth independent confirmation that this Copilot CLI version's
  models do not reliably dispatch a named built-in subagent from `AgentWeave`'s per-turn context,
  now including the one built-in (`code-review`) a shipped design feature (D8) depends on.

  **New and more serious: `cp5` then asserted a dispatch that never happened, inside the permanent
  verdict record.** Its own `.reviews/review-0001-2026-10-03-1836.md` (written by its own `edit`
  tool call, not a subagent) states *"The independent code-review agent identified the same
  event-boundary weakness"*, and the `update_task` notes — the one field design D8 and the review
  flow both treat as the durable account of what happened — repeat it: *"The independent code-review
  agent independently flagged the same event-boundary weakness."* Nothing in the transcript supports
  either sentence; `cp5` reviewed its own finding and then attributed it to a second reviewer it
  never ran. Filed as finding F484 (`scripts/drive/FINDINGS.md`) rather than folded only into this
  row, because it is a correctness defect in the review record itself (a false corroboration claim),
  not only more evidence for the open subagent-dispatch question.

  **The real defect `cp5` did find, on its own, stands regardless of the above.** `revision_needed`,
  with a concrete, reproduced finding: `hub/hub/output_recording.py:41-42` scrubs each output event's
  secret independently, and `CopilotEventMapper` flushes message/thought blocks separately on a type
  transition (`hub/hub/copilot_acp.py:969-975` per `cp5`'s citation), so a registered run secret split
  across two events — reproduced with `plainproxykey123` as `plainproxy` + `key123` — passes
  per-event scrubbing in each event and reconstructs whole once both are persisted/broadcast. This is
  outside task 7.7's own scope (it asks about `code-review`'s range, not about scrub correctness) but
  is real, evidenced, and actionable, and is carried into F484 alongside the fabrication finding.

  `tasks.md` 7.7 left **unchecked**: its own first bullet ("the context file contains the D8 bullet
  with `<base>..<commit>`") is met, but its second ("the timeline shows a `code-review` subagent") is
  not — the timeline shows no subagent of any kind. Allowance: one operator trigger call, which the
  Hub's own retry-on-timeout resumed once internally (two underlying Copilot CLI sessions, no second
  operator call). Task `task-ceea0a23940f` and evidence `ev-9ce973c8c18e` left in place as the
  reproducible artifact.

### `a-run-reaches-the-hub-without-mcp` task 10.1 needs the operator on the work PC -- 2026-10-01 night, DECIDED 2026-10-02

- DECIDED   a-run-reaches-hub-10.1  **Waived on the work-PC evidence** (operator, 2026-10-02, as recommended):
  no available machine blocks MCP for the Hub-launched Copilot, and the shim passed at home with MCP disabled by
  flag (group 9). Step 8 stays unanswered; it moves to the detect-and-degrade follow-up as its first question
  rather than its trigger. 10.2 is still held by 9.10 (F478). The question was: **Do the human-only checks in this change's `test-guide.md`,
  or explicitly waive them, so task 10.2 (archive) can proceed.** The change is at 55/58 tasks:
  group 9 is done (9.9 footed F340/F301/F299's outcomes into `FINDINGS.md`; 9.10 is separately
  blocked, below). Task 10.1 names step 8's answer -- whether Copilot's shell sessions persist
  between a run's commands on the work PC, and whether any run activated a venv, imported a
  module or set `ComSpec` before an `aw-tool` call -- as the trigger for a follow-up
  detect-and-degrade change (design open question 7, decided (a) now / (c) as a follow-up,
  2026-09-28). Nothing in this window can run that check; it is scoped to the operator's own
  machine. Waive it, or do it and record the answer in the Round log, and 10.2 (strict validate,
  then archive) can run.
- **2026-10-02, work PC (interactive):** the checks were begun and stopped after item 2 at the operator's
  call. **MCP is not blocked there for the Hub-launched Copilot**: the run connected (`connected`/`mcp`) and
  created the task through the MCP tool, with no managed-settings file or HKLM policy present. The shim path, and
  so step 8's persistent-shell answer, was not exercised. Remaining choice: waive 10.1 on that evidence, or force
  the shim there with `--disable-mcp-server agentweave` and finish items 3 to 6 and 8. Round log, "Work PC, task
  10.1".

### `a-copilot-run-shows-its-credits` task 5.4: a Copilot one-shot's credits -- 2026-10-02 interactive, DECIDED

- DECIDED   copilot-oneshot-credits  **Yes: read the one-shot's `session.usage_checkpoint`** (operator, 2026-10-02, as recommended). A follow-up change, not this one. The question was: **Should a Copilot worker call (`copilot -p`) record its credits
  from the stream it does emit?** Task 5.4 said to read `session.shutdown {totalNanoAiu,
  totalPremiumRequests}` only if the captured stream contains it. It does not
  (`hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl`), so `worker_invocations.ai_nano_aiu` and
  `premium_requests` stay NULL for Copilot. The same capture does carry a `session.usage_checkpoint`
  (`totalNanoAiu`, `totalPremiumRequests`) and the `result` line's `usage.premiumRequests`. A
  one-shot is one process and one session, so the checkpoint is that call's whole charge. Reading
  it is a small parser change plus a test against the capture. Recommendation: yes, read the
  checkpoint (the same figure the ledger trusts for agent runs, D4). Leaving it NULL is also safe:
  it under-reports worker credits, it never misreports them.

### `an-arguments-file-written-from-powershell-is-the-hubs-own` (F478) is ready for approval -- 2026-10-02 night, DECIDED 2026-10-02

R1, R2 and R3 are done. The adversarial Opus review (`spec-queue/tracks/reviews/F478-2026-10-02.md`) approved it with
fixes, and all nine fixes are applied (the change's design.md round log lists them). No code is written. The change
gives one exact PowerShell `Set-Content -Path '<calls file>' -Value '<json>' -Encoding utf8` command the same
standing as a file-tool write of the arguments file. That unblocks slice 3's task 9.10, and it also makes the notice
spell that form out.

- DECIDED   F478-approve  **Approved** (operator, 2026-10-02 interactive: *"Option A. Approve."*); built
  interactively on master. The question was: **Approve the change for implementation, or send it back.** The one security-relevant
  grant is in design D2. Read its "Nothing joined to any part" and "The path's character set is a safety rule"
  bullets: the review measured that text joined to any part of the command runs code on PowerShell 5.1, and the
  grammar now refuses every such form. Its code (`mcp_server.py`) reaches `:8000`'s agents on their next run.
- DECIDED   F478-oq1-bash  **Left out, as recommended** (operator, 2026-10-02). The question was: **Leave out a bash form of the write (design Open question 1)?** R1, R2, R3 and the
  reviewer all recommend leaving it out. No drive has ever produced a bash arguments-file write (R2 swept nine
  profiles), and a bash grammar brings its own trap classes (`$'…'`, redirection forms, `echo`/`printf`
  interpretation). After `the-shell-judge-reads-a-word-whole` ships, such a write is carded under "Ask me", not
  refused.
- DECIDED   F478-oq2-location  **Accepted, as recommended** (operator, 2026-10-02). The question was: **Accept the location residual (design Open question 2)?** After an earlier allowed
  location change, a relative `-Path` can land in another workspace's existing calls directory. The likeliest case
  is a sibling agent's worktree in the same project, two `Split-Path` steps away. That allows a timed overwrite of
  that agent's arguments file, under "Ask me", after you approved the location change. Under "Workspace only" it
  adds nothing, because the judge already allows any relative write after a run-time `cd`. The recommendation is
  to accept it. Closing it by requiring an absolute path would stop the fix firing for the relative form 9.10
  actually wrote. If you want it closed later, per-run arguments-file names in slice 3 would remove the collision.

### The MISREPORT ratchet measures a decayed table -- 2026-09-21 night, DECIDED 2026-10-03

- DECIDED   F396-rekey  **Closed as already done** (operator, 2026-10-03 interactive, as recommended):
  the 2026-09-22 interactive fix answered all three parts the way the row proposed -- (1) rows are
  keyed by `(path, hook, occurrence)`, (2) the ceiling was re-measured deliberately (52 -> 55, then
  53 after two real repairs on 2026-09-23), (3) all 18 unclassified sites were triaged in that
  change -- and a stale row or an unclassified site is now a test failure (F396's FIXED section).
  Re-measured 2026-10-03 on master `108a99b`: 97 unhandled, 53 MISREPORT = `MISREPORT_CEILING`,
  0 stale, 0 unclassified; `test_surface_ceilings.py` 6 passed. The row had stayed OPEN only because
  nobody flipped it, so every window carried it forward. The question was: **How should `RENDERS` be re-anchored, and who triages the 18 sites that
  now carry no classification at all?** Measured tonight (F396 in `scripts/drive/FINDINGS.md`):
  `n11_query_error_surface.RENDERS` is keyed by `(file, line)`, **8** of its 57 `MISREPORT`
  classifications match no live call site, and the ceiling `MISREPORT_CEILING = 52` was **already
  holding 5 dead keys on the day it was measured** (`6484de4`, 2026-09-10) -- so the current count
  of 49 is decay, not repair, and zero surfaces were actually fixed. The window did not change
  anything, because the repair is a change and the night window does not write proposals.

  **Three parts; only the operator should answer the second and third:** (1) re-anchor the key to
  something a line shift cannot move -- `(file, hook)` is the obvious candidate and is already in
  every site record; (2) whether to re-measure the ceiling from the re-anchored table, which will
  jump back up toward 57 and must not be read as a regression; (3) whether the **18** currently
  `UNCLASSIFIED` live sites get hand-triaged in the same change or a later one -- six are
  recoverable from the dead keys' recorded `why` strings, twelve have never been classified at all.

  **What must not happen meanwhile:** lowering `MISREPORT_CEILING` to 49. `_ratchet`'s warning text
  asks for exactly that on every run, and this window's own iteration 8 wrote it down as a chore.

**No row is open as of 2026-10-03 (F396-rekey, immediately above, was closed then). The two rows below it are discharged, and both were
verified so on 2026-09-19.**
They are kept in place, not deleted, because each carries the reasoning and the measurements behind
a decision the corpus still relies on — and a decision log that is silently rewritten stops being
evidence. **Read them as history. Neither is work waiting on the operator.**

- **`a-quote-can-spell-a-slash` / F332-rule — fully discharged.** The row reads *"REVISING — take the
  night's candidate correction through one more verification round, then build"*. That happened:
  **F332's status is `fixed 0e52ad4`**, and the change is archived at
  `openspec/changes/archive/2026-09-15-a-quote-can-spell-a-slash`. The blocked night-queue items it
  names (`f332-s4`…`s7`) survive only inside `.agentweave/tasks/`, which is gitignored scratch, not
  the corpus.
- **F352-free — decided, and the decision shipped.** *"Reject (d), go with (f), already shipped"*,
  2026-09-15; `4b59ee0` (`a-task-nothing-will-move-holds-nobody`) is archived. **What is still live
  is a finding, not a decision:** F352 reads *"open for the visibility half; the definition half is
  fixed `4b59ee0`"*. The visibility half belongs in `FINDINGS.md`, where it is, and needs no
  decision from the operator to be queued.

**If a future row is genuinely open, put it above this banner**, so this section keeps meaning what
its name says.

### a-quote-can-spell-a-slash stopped at §2 — 2026-09-13 night, DECIDED 2026-09-15

- DECIDED    F332-rule  **REVISING — take the night's candidate correction (below) through one
  more verification round, then build.** Decided 2026-09-15, by the operator, in an interactive
  session. *Rejected:* the blunter "refuse every codepoint escape above 0xFF on Windows" option —
  it needs a new `_UNCHECKED` reason string, which §2.3 forbids, so it is not actually cheaper, it
  just moves the cost onto a different rule.

**What was found.** The rule was built exactly as tasks §2.2 states (not committed), then measured
through `_decide` and real Git Bash. It **allows two writes outside the workspace that today's lexer
refuses**, on Windows only. The cause is in design D1's invariant, "safe iff it never emits *fewer*
separators than bash". That is half of it. A backslash the decoder keeps but bash does not is a
phantom directory level on Windows, and a later `..` climbs out of it:
`mkdir A; echo hi > $'A\Uffffffff/../../x'` writes outside in every locale (bash emits nothing for
`\U` ≥ 0x80000000), and `$'A\u0100/../../x'` does the same under a UTF-8 `LANG`. Evidence, the
measured rendering table and the reproductions are under F332's *Night note* in
`scripts/drive/FINDINGS.md` and at the top of the change's tasks §2.

**The night's candidate correction, for the day window to re-derive, not to adopt as written.**
The invariant becomes *reproduce bash's separator structure exactly, and judge every reading
where it depends on the locale*:
- `\u`/`\U` from 0x100 to 0x7FFFFFFF: two readings, the C-locale literal (backslash kept) and the
  UTF-8 one (a non-separator character). Refuse if either refuses. One way to build it is a flag on
  `_lex` and one `_read_command` pass per reading, the way `_decide` already reads an unknown tool
  in both dialects.
- `\U` ≥ 0x80000000: nothing, which is what bash emits in every locale. This moves **N3**
  (`$'\Uffffffffx'`) to *allow* on Windows, since bash writes `x` inside, and D2's N3 row with it.
- `\cX`: the control character of X's first UTF-8 byte (`\c` + é is `03 a9`), per tasks §2.2's "any
  real body character". The night briefly restricted it to ASCII X, which re-created the phantom
  level. Measured, then dropped.
- New D2 rows pinning both escapes above (Windows deny *outside*), plus a mutation that keeps the
  backslash for `\U` ≥ 0x80000000 and one that renders only the C reading.
- `$$'…'`: bash reads `$$` as a pair (the PID), so what follows is an ordinary `'` quote, not
  ANSI-C, but the lexer as built opens ANSI-C at the second `$`. Worked by hand and **not
  measured**: it can only over-refuse, because the extra `$` already sends any such word that
  holds a separator to rule 3, *cannot be checked*. The revision should say which way it goes
  and pin a row for it.

The other option is to refuse every word holding a codepoint escape above 0xFF on Windows as
*cannot be checked*. It is simpler, but the `_UNCHECKED` wording names variables, `~` and
substitutions, so it would need a new reason string, which §2.3 forbids.

**What stays.** `1ebff15` (§1, tests only, green: 182 passed, 1 skipped, 16 xfailed on Windows)
stays on the branch. Its N3 *after* answer on Windows is wrong under the correction; the revision
changes that row. The night queue's f332-s4…s7 are blocked on this row. Its CI XFAIL half of 7.1
is collected: run `34786122094`, `hub-test` job `103801807485`, green with 11 xfailed. The 11 are
G1–G10 and D1, the same set WSL measured.

### F352-free — what "free" means for review staffing, raised 2026-09-14 by REV, DECIDED 2026-09-15

- DECIDED    F352-free  **Reject (d). Go with (f), already shipped.** Decided 2026-09-15, by the
  operator, in an interactive session, after the Opus validation below. **The five-option frame
  (a)-(e) put to the operator was stale.** The
  2026-09-15 night shipped `4b59ee0` (`a-task-nothing-will-move-holds-nobody`, archived), which
  replaces D4's blanket "any active task holds" rule with **option (f), reachability**:
  `hub/hub/scheduler.py:1138`, `loop_id in live or (task_id, assignee) in queued` — a holding counts
  only if a live loop still walks it or a queued turn names it. (f) was not one of the five options
  put to the operator; it answers a different, narrower question (unreachable phantom holdings) than
  D4's "should review use a looser rule than new work" — but it resolves the LoopEngine snapshot
  that motivated the question: the eight NULL-`loop_id` holdings on `dev`/`dev_2` are now reachable-
  free, proven by `hub/tests/test_a_task_nothing_will_move_holds_nobody.py:307`
  (`test_the_loopengine_shape_staffs_its_review`). Architect and tester correctly stay held — their
  tasks are in-loop, real queued work.
  An independent Opus adversarial review (2026-09-15), asked to validate (d) against this corrected
  premise, **rejects (d) in favour of (f)**: (d)'s "not already reviewing another `under_review`
  task" throttles concurrency, not sequence, so an agent with five in-loop `pending` tasks stays
  permanently review-eligible under (d) — D4's pile-up recreated under (f) wouldn't arise, since a
  real in-loop holding still counts. (d) also offers reviews into an unresolved worktree-collision
  gap (`hub/tests/test_task_worktrees.py:434`,
  `test_two_tasks_held_by_one_agent_conflict_as_two_workspaces`) that (f) cannot reach, because (f)
  still holds an agent with a real in-progress in-loop task. Verdict text and citations verified
  directly against the code and commit by this session, not taken on the subagent's word alone.
  **Decided:** REJECT (d); build the F353 half (`F352-split`, already approved above) now;
  re-derive the rung-3 naming half against **(f)**, not the stale (e) the change was written
  against (`proposal.md:187`, *"the rung-3 half is written against (e) today, and the answer
  re-derives it"*). This closes `F352-free`.

### `the-shell-judge-reads-a-word-whole` task 1.7c's two escape rows conflict with a shipped guarantee -- 2026-10-04 night, DECIDED 2026-10-04

- DECIDED   shell-judge-escape-scope-1-7c  **(b): accept the POSIX-only scope** (operator, 2026-10-04, as recommended): mark task 1.7c's second and third bullets `(POSIX CI)` like its first, and correct design D7's "harmless readings" claim to name F487's drive-letter-host case. (a), the `_LITERAL_BACKSLASH` sentinel, is its own change if ever wanted; (c) is rejected. The question was: **F487 (`scripts/drive/FINDINGS.md`) found, and
  iteration 58's fresh re-derivation of task 1.7c confirmed again, directly against `_decide` on
  this drive-letter dev machine: task 1.7c's second and third bullets ask that
  `bash -c 'cp n .\./x'` (both the Bash and the PowerShell tool) and
  `bash -c 'bash -c "cp n .\\./x"'` (Bash tool) refuse **unconditionally**, with no platform
  qualifier -- unlike the task's own first bullet, explicitly marked `(POSIX CI)`. Building that
  unconditionally (running D7's backslash-escape-removed-level reading on a drive-letter host, not
  only gated `not _DRIVE_LETTERS` as it shipped in iteration 55) regresses an already-shipped,
  already-green test: `test_a_quote_is_judged_by_what_it_decodes_to[P5a/P5b/P5c]` in
  `test_permission_approver.py` (measured both ways via `git stash`: `allow=True`, correct, before
  the escape-level code existed; `allow=False`, wrong, with it unconditional; `allow=True` again
  once gated POSIX-only). The conflict is structural: on a drive-letter host a backslash in a word
  has two simultaneously-true readings -- "this is a path separator" and "this might be an escape
  an inner shell would remove" -- and nothing in the word's final text says which one a given `\`
  actually is; `_ansi_c_escape`'s kept-literal backslash and a genuinely unescaped one produce
  identical decoded text. No sentinel threading that provenance through `_SEPARATORS` exists yet
  (the codebase's own precedent, `_LITERAL_DOLLAR`, marks the analogous case for `$`, but nothing
  equivalent exists for `\`).

  **The question: which of F487's three fix candidates, or leave it as shipped?**
  (a) Build a `_LITERAL_BACKSLASH` sentinel emitted by `_ansi_c_escape` wherever it returns a
  literal `\`, read as a real separator by every `_SEPARATORS`/`os.path` site but skipped by
  `_escape_removed_levels`'s regex -- the structurally complete fix, but F487 names it larger than
  one iteration's slice (touches every separator site in the file);
  (b) accept the POSIX-only scope permanently: correct task 1.7c's own two bullets (drop the
  "both tools"/no-qualifier framing, add `(POSIX CI)` matching the first bullet) and design D7's
  "every path spelled with `\` gains harmless readings" claim (F487's own `A\x/../../y1` case
  disproves it on a drive-letter host) to say so explicitly;
  (c) something narrower, scoped to only the two rows 1.7c names, not built in for every word.
  Recommendation: (b) -- it matches what already shipped and needs no further code, only a spec
  correction; (a) is real but should be its own change if the operator wants the stronger
  guarantee, not a one-iteration slice of this one. Blocks task 1.7c and, through its own "Run
  1.7b, 1.7c and 1.7d" instruction, task 2.2a.

The morning triage folded 32 raw entries into 8 rows. An evening pass compared all eight **against
the code** rather than against each other, and six of them turned out not to be decisions.

Two structural faults caused most of it.

**One token cannot answer ten questions.** D-7 absorbed ten entries and D-8 seven. The contract at
the top of this file says one row per decision and the status token is the authority — so there was
no answer the operator could give that made either token true. Answer two of D-7's ten and it stays
`OPEN`, and the answered parts get re-asked. Both were unclosable by construction, which is why
both sat. **D-1 is the only row that ever closed, and it is the only one that was a single
question.** Grouping is good for reading and fatal for tokens: from here, group in prose, tokenise
per question.

**A label can block work it does not describe.** D-7 was named "response-shape and API-surface calls"
and justified as "each changes a contract an existing caller depends on". Measured against the code,
**one of its ten entries** actually does. Three are purely additive — `GET /tasks/{id}/transitions`
is a new route with nothing to break (verified: no route and no MCP tool exists, the thirteen code
references are all writes), and `F212` adds a `document_id` the same response already carries. Those
sat parked behind a rationale that was never true of them.

### Where every earlier row went

| Was | Now | Why |
|---|---|---|
| **D-1** fastmcp ceiling | **stays, DECIDED** | Ratified in session 2026-09-01. Kept below as history. |
| **D-2** pin fastapi | **→ R-1** | The path that actually bit is already closed; what remains is an instance of the unwritten ceiling rule. |
| **D-3** refusals with no surface | **→ R-1** | "One convention or eleven fixes?" is R-1's question, and this is its best-evidenced instance. |
| **D-4** standing rules vs instances | **→ R-1**, three rows dropped | Measured: three of its four sweeps are 2-9 sites. Only the fourth needs deciding. |
| **D-5** sweep vs repair | **→ queue** | Overtaken: two of its three severity-A items now have approved changes. |
| **D-6(a)** archive collision | **→ R-2** | A genuine tooling call, unrelated to (b). |
| **D-6(b)** corpus ahead of code | **→ R-1** | "May a task tick on backend evidence alone?" is a rule question. |
| **D-7** API-surface calls | **→ R-3 + queue + R-1** | Splits three ways; see below. |
| **D-8** stale rows | **→ queue** | A bring-forward list, not a decision — and it rests on a figure this file already disproved. |

Nothing is lost: every original entry number is still named by whichever row now carries it.

---

### R-1 — Does this repo enforce conventions, or repair instances?

**DECIDED 2026-09-08 00:30 — ENFORCE, AS A RATCHET. By the operator, in session.** Absorbs D-2,
D-3, D-4, D-6(b), and behind them entries 3, 5, 8, 10, 11, 13, 15, 16, 20, 27, plus F169, F173,
F178, F179, F180, F187, F190, F195, F197, F201.

**The decision.** When this repo learns a rule it **writes a check** — and the check freezes today's
count as a ceiling that may shrink and may never grow. It does **not** repair every existing
instance before the check may go green.

**Why the question sat a week: both readings of it cost about twenty nights.** Repairing 35 routes
and 51 misreports one at a time is more than twenty. Enforcing *as a sweep* — write the check, then
fix everything it flags before it can pass — is the same cost arriving all at once. Neither fits a
one-person, nights-only operation, so neither got taken.

**The reframe that resolved it: the repo already does all three things, and the third is a ratchet.**

- It already **enforces**, thirteen times: `test_tool_surface_matches_server.py`,
  `test_fastmcp_api_contract.py`, `test_mcp_server_stdio_surface.py`, `test_mcp_body_contract.py`,
  `test_ui_build_stamp.py`, `test_ui_staleness.py`, `test_requirement_drift.py`,
  `test_conversation_contract.py`, `test_briefing_names_its_contract.py`,
  `test_timestamp_serialization.py`, `test_evidence_restamp.py`,
  `test_agent_tool_surface_phase7.py`, `test_session_sync.py`. So "does this repo enforce?" was
  never the open question — it enforces, and has for weeks.
- It already **ratchets**: `.claude/autonomous/mypy-baseline.txt` is 172 lines of frozen known
  failures that must not grow, and `test_ui_build_stamp.py` gates its stricter
  bundle-matches-source assertion behind `AW_CHECK_UI_BUNDLE=1` for the same reason.

A ratchet is therefore this codebase's convention rather than this decision's taste — the same
argument round 3 used to approve `2026-09-06-an-unread-editor-cannot-overwrite`.

**What this buys.** ~20 findings stop being backlog and become *bounded and non-growing*. You do not
finish 51 misreports; you stop the 52nd and pay the rest down as you touch the files.

**What it costs, stated plainly.** The 35 client-less routes and the 51 operator-reachable
misreports **stay wrong, indefinitely, with a passing test blessing them.** That is the trade and it
was taken knowingly. Any single one of them that is a real operator-facing defect comes *out* of the
allowlist and gets fixed on its own merits — that is a per-instance call and R-1 does not pre-empt
it.

**The three checks this authorises**, sized against the tree at `a6f67af` and re-measured
2026-09-08 00:20 (both scripts reproduce their 2026-09-02 figures exactly):

| Check | Promote from | Frozen ceiling | Covers |
|---|---|---|---|
| route reachability | `scripts/drive/n10_route_reachability.py` | **35** routes with no client (33 distinct paths); 6 more whose hook nothing renders | F169, F187, F260 |
| query error surface | `scripts/drive/n11_query_error_surface.py` | **51** MISREPORT sites an operator can reach, of 107 call sites, 7 of which bind the error | F173, F178, F179, F180, F195, F197, F201 |
| dependency ceilings agree | new, small | the three `fastmcp>=2.0,<4` declarations in `pyproject.toml`, and `starlette<2.0` | old D-2, entry 31 |

**Both measurement scripts already exist and both ran clean.** The work is promoting them from
`scripts/drive/` into `hub/tests/` with a frozen baseline, which is why this is one window and not
twenty. **It is Stage 6 of `ROADMAP.md`, not the next thing built** — the four approved changes and
the F292 instrument repair come first.

**Consequences elsewhere, settled by this and needing no further decision:** the old **D-2**
(FastAPI's own major) is an instance of the ceiling rule and is covered by check 3. **D-6(b)** —
may a task tick on backend evidence alone? — is answered *no*: a rule that cannot be checked is not
enforced, so a requirement with an unbuilt UI half does not tick. Three of D-4's four sweeps were
already measured at 2–9 sites and drop into the queue as ordinary instances.

**Not settled by this:** F190's payload-ordering rule. CLAUDE.md records that only the instance it
was learned from is checked and no sweep has been run over the other payload-shaped consumers.
Whether that rule gets a fourth ratchet is a separate, later call — it needs a way to enumerate
payload-shaped consumers first, and nothing does that today.

---

#### The evidence this was decided on, retained in full

Everything from here to `### R-2` is the case as it stood while R-1 was OPEN. It is kept because it
is the justification for the ceilings above, and because the two scripts it names are the ones being
promoted to tests. **Read it as the basis for a decision already taken, not as an open question.**

The question in one line: **when the repo learns a rule, does it write a check that enforces it, or
does it fix the instance and rely on remembering?**

**The repo already answers this two ways at once, which is the tell.** `fastmcp>=2.0,<4` and
`starlette<2.0` are the *same move* — a defensive ceiling so a major needs a conscious bump — taken
twice, months apart, each with the reasoning written into a comment beside it. That is a standing
rule in practice that no file states and no check enforces. Meanwhile the same defect class gets
re-filed: *the Hub computes a sentence for an operator and no file under `hub/ui/src` reads it* has
been filed **six times across two nights**.

**The evidence, verified against the tree 2026-09-01:**

- `ChartersPage.tsx:191` is `createCharter.mutate(values, { onSuccess: … })` — **no `onError`**. The
  refusal is a plain 422 the mutation already holds. Nothing needed computing, wiring or designing,
  which is what makes this a missing convention rather than a refactor.
- `GET /documents/{path}/rigor-history` exists (`hub/hub/api/v1/spec.py:535`) and returns **zero
  hits** across `hub/ui/src`. Ten more operator-only routes are 0-hit in both the source and the
  served bundle. `spec_rigor.py`'s own docstring justifies allowing demotion *on the grounds that
  the audit trail exists* — and no screen shows it.
- The old D-2 is closed at the point it actually bit: `starlette<2.0` is pinned nineteen lines below
  `fastapi>=0.110`, and its comment names the exact incident — *"an unbounded fastapi>=0.110 once
  let pip silently resolve starlette 1.6.0 in CI while dev ran 0.52.1."* Both CI failures were
  Starlette crossings. What is left is FastAPI's own major: real, unrealised, and a *third* instance
  of the same unwritten rule.
- `runner-registry/spec.md:72-73` is a shipped requirement whose UI half was never built — ticked on
  backend evidence alone and archived. The approved `runner-model-is-chosen-from-the-catalog`
  repairs that instance; whether a task may tick on backend evidence alone is the rule question.
  *(Pointer corrected 2026-09-02, night window: that requirement now starts at
  `openspec/specs/runner-registry/spec.md:67`, because the change's delta was synced into it on
  2026-09-02, and it is **no longer unbuilt** — the picker shipped and was driven against the
  served bundle. The instance is closed; the rule question the bullet raises is not, which is why
  the bullet stays.)*

**The "ten more", enumerated — measured 2026-09-02 by the night window.**

The second bullet above has asserted *"ten more operator-only routes are 0-hit in both the source
and the served bundle"* since 2026-08-31 without the list ever being written down. Here it is, and
**the figure is not eleven — it is 35.**

Reproduce with `py -3.11 scripts/drive/n10_route_reachability.py`. Routes are read from
`hub.main:app`'s own route table rather than from decorators, so an include-time prefix cannot be
mis-transcribed; UI call sites are the `/api/v1…` literals `client.ts`'s helpers require, with the
HTTP verb taken from which helper carries each one.

| | |
|---|---|
| declared `/api/v1` route+method pairs | **187** |
| under `/api/v1/agent-actions` (the agent API, operator-invisible by construction) | 32 |
| everything else | **155** |
| reached from `hub/ui/src` with a matching verb | 110 |
| not reached from the UI | **45** |
| — of those, called by the CLI's `HttpTransport` instead | 10 |
| — **of those, called by no client anywhere in this repo** | **35** (33 distinct paths) |

**Verb matters and path-only sweeps get this wrong.** `GET /projects/{id}/charters/{charter_id}`,
`DELETE /projects/{id}/jobs/{job_id}` and `POST /projects/{id}/agents/{name}/output` all sit on
paths the UI *does* call — with a different verb. A sweep that compares paths reports 40 unreached
and calls those three reached; comparing (verb, path) reports 45 and is right.

**The CLI is a second client, and its ten are not operator gaps.** `HttpTransport._request` takes a
path *relative* to one of three prefixes (`transport/http.py:145-149`), so its calls never contain
the string `/api/v1` and any repo-wide grep for the literal misses every one: `POST …/agents/{name}/
heartbeat`, `/output`, `/context-usage`, `POST …/logs`, `POST …/messages`, `POST …/questions`,
`GET …/questions/{id}`, `POST …/session/sync`, `POST …/tasks`, `DELETE …/jobs/{job_id}`.

**The 35 with no client at all**, grouped by the file that declares them:

| Area | Routes |
|---|---|
| `spec.py` — 17 | `GET …/project/documents/{path}/rigor-history` · `PUT …/project/documents/{path}/content` · `POST …/project/documents/{path}/merge` · `POST …/project/documents/adopt` · `POST …/project/spec/adopt` · `POST …/project/spec/documents/arrange` · `POST …/project/spec/reindex` · `GET …/project/spec/requirements` · `GET …/project/spec/requirements/{identifier}` · `GET …/project/spec/drift` · `POST …/project/spec/drift/detect` · `POST …/project/spec/drift/{drift_id}/resolve` · `GET …/project/spec/evidence` · `POST …/project/spec/evidence` · `POST …/project/spec/evidence/{evidence_id}/decision` · `GET …/project/spec/evidence/{evidence_id}/reviews` · `PUT …/project/spec/evidence-retention` |
| `agents.py` — 5 | `GET …/agents/agent-context` · `GET …/agents/configured` · `GET …/agents/context` · `POST …/agents/register` · `POST …/agents/request` |
| `events.py` — 3 | `GET /api/v1/events/ticket` · `GET …/events` · `GET …/events/ticket` |
| `tasks.py` — 2 | `POST …/tasks/{task_id}/dependencies` · `DELETE …/tasks/{task_id}/dependencies/{depends_on}` |
| `inbound_queue.py` — 2 | `GET …/queue/settings` · `PATCH …/queue/settings` |
| `loops.py` — 2 | `POST …/loops/{loop_id}/archive` · `POST …/loops/{loop_id}/control` |
| four singletons | `GET …/projects/{project_id}` · `GET …/charters/{charter_id}` · `GET …/checkpoints/{checkpoint_id}/rendered` · `GET …/worktrees/conflicts` |

Each is 0 in the served bundle too, probed by string literal rather than by symbol name — Vite
renames every local, so an absent hook name proves nothing, while template literals survive intact
(``/api/v1/projects/${n}/loops/${e}`` is in `index-x3nWU-L2.js` verbatim). Five fragments that
*must* be present are probed alongside as controls; all five are.

**The second class the bullet did not separate: a client exists, and nothing renders it.** Six more
routes have a working hook in `hub/ui/src/api/` that no component outside its own file imports —
`requestCompact` (`POST …/agents/{name}/compact`), `requestNewSession` (`…/new-session`), `useJob`
(`GET …/jobs/{job_id}`), `useRunnerLaunchability` (`GET …/runners/launchability`),
`useAgentLaunchability` (`GET …/agents/launchability`) and `useDivergences`
(`GET …/tasks/divergences/recent`). This is F260's shape, and it is worse than it reads: **the
bundler tree-shakes them, so all six paths are 0 in the shipped bundle** — measured with the
terminating backtick, because `runners/launchability` *is* in there as the prefix of
`runners/launchability-by-provider`, which is the variant that ships. The client code exists,
passes its unit tests (`useAgentLaunchability` is named by nine test files) and is not in the
product. `useUpdateJob` is orphaned the same way but its route is not, because `usePauseJob` and
`useResumeJob` `PATCH` the same path.

**What the eleven was probably counting: unknown, and no subset of the measurement lands on it.**
The nearest natural groupings are both 17 — the `spec.py` routes, and the `GET`s among the 35. The
figure looks like an estimate that was never enumerated, which is the whole reason this item
existed.

**110 is an upper bound, not a count of what an operator can reach.** The unrendered-hook pass is
depth-1: it asks whether any *file* outside the hook's own names it, so a hook imported by a
component that is itself imported by nothing reads as consumed. F260 is exactly that — `useMessages`,
`useMessageHistory` and `useMarkRead` are all imported, by `MessagesFeed`, which nothing imports and
which is absent from the bundle. So `GET …/messages` and `PATCH …/messages/{id}/read` are counted
in the 110 here and are unreachable in the shipped app. Sizing that class properly needs a reachability
walk from `App.tsx`, not a symbol grep; this measurement does not attempt one, and the 35 and the 6
are both floors.

**Limits, stated rather than left implied.** A static sweep can show that no caller *in this repo*
names a route; it cannot show the route is dead, and an external client is out of scope. The bundle
probe is path-level, so a bundle hit does not distinguish verbs — it is used here only to confirm
absences. Nine matches were ambiguous because the UI computes a segment (``/projects/${action}``
could be `create`, `open` or `{project_id}`); each was resolved by reading the line and is recorded
with its line number in the script's `HAND_RESOLVED`. Two more are composed by
`agentChat.ts:213`'s `conversationPath()` helper rather than written at the call site, which the
literal scan cannot see; both are in fact called. The unrendered-hook pass names exported symbols,
which would miscount a hook re-exported through a barrel — `hub/ui/src/api/` has no barrel and no
`export *`, checked.

**This block adds evidence only.** R-1's two halves, (a) and (b) below, are untouched and remain
the operator's to answer.

**What the old D-4 got wrong, measured.** It presented four findings as symmetric, each naming "a
grep that would say how big it is". The greps were never run. They are:

| From | Measured sweep |
|---|---|
| **F190** | **2** functions — and both are deleted by the change approved 2026-09-01 |
| **F195** | 21 `subprocess.run`/`Popen` sites, **13 already pass `cwd`** → ~8 |
| **F201** | **9** `model_validator`s under `hub/hub/schemas/` |
| **F197** | **133** `useQuery` declarations; 62 of 97 component files never mention `error` |

At 2, 8 and 9 sites the rule-or-instance question is academic — do both, in an afternoon. Those
three rows are **queue work, not decisions**, and are moved below. Only **F197** is large enough to
need an answer, and its real question is not the one D-4 asked: it is whether an unrendered query
error is a defect *at all* in every case, since a background poll's failure may be correctly
invisible. (133 is an order-of-magnitude grep, not a defect count.)

**One of R-1's instances has now answered "enforce", and the answer is half-done on purpose
(2026-09-02 night window, task 5.3 of `a-turn-says-how-it-ended`).** The rule F190 taught —
*a test for code that consumes an API payload uses the ordering that route actually returns, and
some test fails if the route's order is reversed* — is now **written down in two places a reviewer
meets**: as a requirement, *Payload-shaped model functions are tested against real route ordering*
(`agent-stream-events`), and as a line in `CLAUDE.md`'s Critical Rules.

**Stating it is not enforcing it, and this row should not be read as if it were.** What exists is
the rule plus a check on the single instance it was learned from: `test_a_turn_says_how_it_ended.py`
asserts the timeline route returns newest-first and that its truncation keeps the newest fifty —
both mutation-checked by actually reversing `agents.py`'s sort — and `timelineRunFacts.test.tsx`
asserts the client's read of the run-facts map survives a shuffled input. **No sweep has been run
over the repo's other payload-shaped consumers, and no automated check prevents the next one.**

So R-1's question is untouched: this is one convention written by hand, in the middle of the change
that needed it, with the general case still open. It is offered as evidence of what "enforce" costs
when taken seriously — a spec requirement, a `CLAUDE.md` line, two mutation-checked test sites — not
as a decision the operator has been spared.

**Pointer note.** Task 5.3 names this file's *D-4*. D-4 was dissolved by the 2026-09-01 evening
re-triage; its F190 sweep row is the table above and its queue entry is under *Not decisions* below.
This block is where the note belongs now, and `tasks.md` records the correction.

**F197 sized, 2026-09-02 (night window, N-11).** The row above is now superseded by a count.
Harness: `scripts/drive/n11_query_error_surface.py`, one command, no product code touched. The
write-up with the quotes is in `scripts/drive/FINDINGS.md` under *"F197 sized, 2026-09-02"*.

**133 was the wrong unit and does not reconstruct.** There are **57** `useQuery` declarations in
`hub/ui/src/api/`, in 56 exported hooks. `useQuery` appears on 138 lines and 114 outside imports;
no natural grep of this tree lands on 133. The `62 of 97` half does reconstruct — 97 `.tsx` files
under `components/`, 61 with no `error` in them today — but a file is not a defect count either: a
hook called by three components is three chances to render an error, and a file that never says
`error` is one missing chance, not one per query it runs.

**The unit that is a defect is a call site.** There are **107** outside `api/`, in 48 files. **6**
bind the query's `error`/`isError` and render it. **101** do not — and 3 of those could not have,
because two hooks (`useAgentOutput`, `useLogs`) destructure `useQuery` internally and return a
narrower object with no error field, so no component fix reaches them.

| What the 101 render when the fetch fails | |
|---|---|
| **MISREPORT** — a false statement reaches the screen | **60** |
| — on a surface an operator can reach | **57** (3 sit in `MessagesFeed`, F260's dead component) |
| — of those 57, an empty picker rather than a sentence | 13 |
| — a sentence, a number, or a terminal skeleton | **44** |
| **SUPPRESSED** — an alert or affordance silently does not render | 16 |
| **BLANK** — a decoration or lookup is missing; nothing is claimed | 24 |
| **NAMED** — says the data is unavailable without binding `error` | 1 |

The rule was written before it was applied and is at the top of the script; every one of the 101
is classified individually in `CLASSIFIED`, each naming the line it was read off. The mechanical
part is the 107/6/101 split and the poll flags — which of the four labels a site earns is a
reading, and disputable per row rather than in aggregate.

**The rule gained two labels while it was applied, which the brief asked it not to.** `SUPPRESSED` was split out of `BLANK` (a blocked run's approval card not rendering is not a missing avatar colour) and `NAMED` did not exist at all until `RunnersPage.tsx:198` turned up. Both narrow `MISREPORT` rather than widen it, so neither inflates the headline; both are recorded in the script's docstring.

**The question this row existed to answer — how many are background polls whose errors are
correctly invisible — has a hard answer: at most four, and none of them misreports.** Exactly two
of the 56 hooks poll (`usePendingPermissionRequests` and `useQuestions`, 3s), reaching 4 of the 101
sites; three are `SUPPRESSED` and one `BLANK`. The Hub pushes SSE rather than polling (8 of 22 api
files invalidate on an event), and an SSE-invalidated query that fails its **first** load does not
retry until the next event arrives. Even the four are pardoned only after a first success — a poll
that fails cold renders the same false empty as any other query. So the "much of this is correctly
invisible" reading of the 133 does not survive: on this tree it accounts for 4 sites, not a
fraction of the whole.

**What is on the screen, from the 44.** *"No agents connected. Run `agentweave start` to connect
agents"* (`OverviewPage.tsx:79` — it also instructs the operator to do the wrong thing);
*"Everything here is archived"* (`SpecPage.tsx:35`); *"No quality governance configured"* and
*"All reviewed tasks clear"* (`QualityHealthPanel.tsx:25-26`); *"This agent is no longer in the
roster"* (`AgentSettingsPage.tsx:42`); four `?? 0` counts in the status bar. The sharpest is not a
display defect at all: `InstructionsPage.tsx:9` seeds its editor from `if (data) setContent(...)`,
so a failed load leaves an **empty textarea with Save enabled**, and a save writes `''` over the
stored instructions. Static read, not driven.

**Two facts that bear directly on (b), stated as evidence and not as an answer.** First, the repo
already contains the worked pattern *and* its rationale: `QuestionsPanel.tsx:86` renders its error
only `if (isError && unanswered === undefined)` — *"A failed fetch used to fall through to 'No
pending questions' — an error rendered as reassurance, on the one screen where 'nothing is waiting
on you' is the most expensive thing to say wrongly"* — and deliberately does **not** replace a
screen of real questions when its 3s poll blips. Second, a check phrased as *"the site binds
`error`"* would misfire in both directions: it would call `RunnersPage.tsx:198` a defect, which
renders *"The model catalog is unavailable — this runner will use the provider's default"* from
`!!catalog` and binds nothing, and it would pass any site that binds `error` and drops it.
`JobCard.tsx:146` shows the near-miss the other way: a comment that reasons the claim must not be
made before the answer arrives, guarded on `isLoading`, which is false after an error.

**Falsified rather than asserted: none of the 60 has an error branch elsewhere in its file.** Every
`MISREPORT` site's file was re-read for any `error`/`isError` token outside the call site. 34 of the
60 have one — and all 34 are a *mutation's* error, a local `useState` error, a severity enum, a
`console.error`, or a **different** query's (`TasksBoard.tsx:57` handles `useTasks` and not
`useAllowedTransitions` one line below). Not one is a branch that would cover the query in question.
`ProjectSettingsPanel.tsx:84` is the original F197 sentence restated by the pass: `const error =
update.error ?? relocate.error` — two mutations, never the query.

**Which is the asymmetry worth carrying into (b).** The UI renders mutation failures routinely — 18
`readableApiError(...)` call sites across 13 component files, every one of them fed by a mutation or
a handler's `err` — and query failures 6 times in 107. It is not that this codebase does not handle
errors. It handles the ones it caused and not the ones it merely observed.

**Blind spot, N-10's again.** Sites are found by symbol, one level deep, so a site in a component
nothing imports counts as live; 3 of the 60 are exactly that, and were caught only because F260
had already named `MessagesFeed`. 57 and 101 are therefore upper bounds on what an operator can
reach.

**Blind spot closed, 2026-09-02 (day window, D-5).** Harness:
`scripts/drive/d5_reachability_walk.py`, which imports the two night scripts rather than
reimplementing them, so its numbers differ from theirs by the module filter and by nothing else.
The write-up is in `scripts/drive/FINDINGS.md` under *"What D-5 measured, 2026-09-02"*.

Of 170 source files under `hub/ui/src`, **157 are reachable from `main.tsx` and 13 are not** —
and 12 of the 13 have every literal that occurs nowhere else in `src/` absent from the shipped
bundle, with a dozen reachable files probed as controls and every one of their literals present.
The thirteenth, `badgeVariants.ts`, is reached only by an `import type`, which the compiler erases.
The choice of entry point does not matter: `App.tsx` alone reaches 155, the two extra being
`main.tsx` and `ErrorBoundary.tsx`.

| Figure | Depth-1 | Reachable only | What moved |
|---|---|---|---|
| routes reached from the UI | 110 | **106** | 4 pairs are reached only from dead code |
| operator routes with no live client | 45 | **49** | 35 no client + 10 CLI-only + these 4 |
| query call sites outside `api/` | 107 | **99** | 8 in dead code, of which N-11 knew 3 |
| unhandled sites | 101 | **93** | |
| MISREPORT | 60 | **54** | N-11's "57 an operator can reach" is **54** |
| SUPPRESSED | 16 | **14** | |

**The four routes are a category (a) did not have.** `GET /messages`,
`PATCH /messages/{id}/read`, `POST …/compact` and `POST …/new-session` are not *"no client was ever
written"* — a client exists, in `api/context.ts` and `api/messages.ts`, and its screens were
removed. When (a) asks whether the operator-only routes are en route to a screen, deliberately
API-only, or dead, this is a fourth answer: **the screen was there and went away**, leaving the
route and its client behind. Whatever standing rule (a) settles on has to say what happens to these.

**One line of the evidence above is wrong and is corrected here.** *"What is on the screen, from
the 44"* lists *"four `?? 0` counts in the status bar"* (`StatusBar.tsx:15`). `StatusBar.tsx` is
imported by nothing and is not in the bundle, so those four counts are on no screen —
`Sidebar.tsx:112` says as much in passing. F259, whose headline is built on the same chip, is
amended in `FINDINGS.md` for the same reason; its substance (nothing marks a message read; the
scheduler depends on the flag) is untouched.

**And the count was never the interesting number.** F271 — filed the same day, severity A — is one
of these unhandled sites, and dozens of the others are cosmetic. What separates them is whether a
failed load can be **written back**: does the query's data seed component state, does the file
write, and is there an early return that stops the write rendering while the fetch is failing. Of
the 54 MISREPORT sites, **2** seed state and write it back with no guard (`InstructionsPage.tsx:9`,
which is F271, and `AgentOutputPanel.tsx:207`), 2 do so behind a guard, 23 write without seeding,
and 27 do not write at all. If (b) becomes a repo check, that ordering — not the total — is what it
should be built on: a check that fires on all 54 equally will be turned off.

**Still evidence only.** Nothing here answers (a) or (b), nothing is marked `DECIDED`, and no
recommendation is offered.

**The decision has two halves, unchanged from D-3 and still the right two:**

**(a)** Are the eleven operator-only routes en route to a screen, deliberately API-only, or dead? A
standing answer settles the sweep's remaining rows too.
**(b)** Should a repo check assert that a server-side refusal string is grep-able somewhere in the
UI, and that a mutation whose failure an operator must see carries an `onError`?

**Why this one first.** Answering it settles the old D-2 and D-6(b) for free, empties three of
D-4's rows into the queue, and supplies the missing axis for what an unattended window may take —
see *The axis that actually predicts it* below.

---

### R-2 — Should `openspec archive` refuse a colliding delta?

**DECIDED 2026-09-08 — a repo script. By the operator, in session.** The full verdict, its rejected
alternatives and its stated weakness are under `## Decided` below (*"R-2 — a repo script"*). This
copy is kept for the question it states; **it is not the authority and no longer says OPEN.** Was
D-6(a). Absorbs entry 18. A tooling call, unrelated to R-1.

Applying a delta against the current corpus warns about nothing when two changes both carry a
`## MODIFIED` block for the same requirement. Archiving the second **reverted the first**, dropping
a qualification that had just landed. Caught only because the diff was read before committing;
repaired, and the other six were swept — exactly one collision in a batch of seven. **Two changes in
flight against one requirement is not rare here.**

Should archiving be gated on a collision check, and does that belong in a repo script, in the
`openspec-archive-change` skill, or upstream?

---

### R-3 — Four small product calls

**DECIDED 2026-09-08 — all four answered. By the operator, in session.** The verdicts are under
`## Decided` below (*"R-3 — the four small product calls, all four answered"*): thread F209's
`reason` through; **remove** `PATCH /queue/settings`; a bare `uvicorn hub.main:app` from `hub/` must
**refuse to start**; check the model catalog with a `scripts/` tool, not a CI-skipped test. This copy
is kept for the four questions it states; **it is not the authority and no longer says OPEN.**

Each was one question with two defensible answers and closable in a sentence. These are
what is left of D-7 once the additive work and the already-answered rows are removed. Absorbs
entries 1, 6, 19, 21.

- **F209** — `accept` declares a 2000-character `reason` and **stores nothing**; `reject`, three
  functions away, keeps it. Thread it through, or delete the field. The current state promises
  something it discards.
- **F196 + F198** — should `PATCH /queue/settings` exist at all? It writes four columns
  `PUT /projects/{id}/settings` already owns, with a weaker contract on both ends, and the UI never
  calls it.
- **Entry 19** — should a bare `uvicorn hub.main:app` from `hub/` **refuse to start** on the
  relative default rather than silently opening a second database beside the one everything else
  uses? This has cost time twice.
- **Entry 21** — `model_catalog.py` names `~/.codex/models_cache.json` as its source of truth and
  nothing re-checks it; it has drifted. Per-machine and absent in CI, so it can only be a
  skip-if-missing check or a `scripts/` tool. *Doing nothing is defensible; doing nothing silently
  is what let a phantom default model sit in the catalog for four weeks.*

---

## The axis that actually predicts what a window may take alone

D-7 asked *which kinds of change need the operator*, and answered "response-shape ones". Measured,
that answer was wrong about nine of its own ten entries. The property that actually separates them
is not the kind of change:

```
        is the right answer already written down?
                    │
        ┌───────────┴────────────┐
       YES                      NO
        │                        │
     REPAIR                  DECISION
   a window takes it        needs the operator
        │
        └── ...but wide or irreversible?
                    │
              REPAIR + GATE
        observe first, verify after
```

The gate arm is not theoretical: `a-turn-says-how-it-ended` was approved 2026-09-01 as a **BREAKING**
response-shape envelope — precisely D-7's blocked class — and what made it safe was not a signature
but a condition. Its phase 0 stops any builder until the defect has been observed live, and its
phase 7 puts verification in a different sitting than implementation. Authorization queues on a
person; evidence queues on a check.

**R-1 is this axis restated.** Deciding whether the repo enforces conventions is deciding whether
answers get written down — which is what moves work from the right branch to the left.

---

## Not decisions — moved to the queue

These were carried as decisions and are not. Each is work with a known answer, or a scheduling call
already made.

**From D-7 — additive, nothing to break, window-takeable:**

- **F203** — `task_transitions` is append-only, carries actor/run/policy, has a reader, and no route
  or MCP tool exposes it; drives have had to open sqlite. Verified 2026-09-01: **no GET route and no
  MCP tool exist** — the thirteen code references are all writes. `GET /tasks/{id}/transitions` is a
  new route with no existing caller to break.
- **F212** — `GET /spec/coverage` projects `unserved` to bare identifiers, which are minted per
  document, so 34 entries all read `FR-1` and feeding one back answers **422**. The same response's
  `requirements` array already carries `document_id`. Additive.
- **F202** — `GET /projects/{id}/tasks` defaults to `limit=100` with no `total`/`has_more`/`next`,
  so at 241 tasks the Overview says "100 tasks". Part two is independently fixable: `list_tasks` in
  `mcp_server.py` has no limit or offset at all. Both additive.

**From D-7 — already answered by something already written down:**

- **F185 + F181** — agent queries with no lifecycle filter. D-7 itself named clearing the bindings
  on archive as "cleanest, closes both at source", and the operator's standing directive is that the
  cleanest solution wins and "more work" is never the objection. Apply it; note that `unarchive`
  must then say the bindings are gone.
- **F193** — what archiving an agent means for its open threads. **The product already made that
  three-way choice explicitly** for archiving a conversation with a live run. Follow the precedent
  unless it is wrong.

**From D-4 — sweeps small enough that the meta-question is moot:** F190 (2 sites, already in an
approved change), F195 (~8), F201 (9). Do the narrow fix and the sweep together.

**From D-5 — overtaken by events.** Its recommendation was to spend a window on F173, F188 and F190
rather than on coverage row 9c. Since it was written, **F173** has an approved change
(`runner-model-is-chosen-from-the-catalog`) and **F190** has one approved conditionally
(`a-turn-says-how-it-ended`). Verified 2026-09-01: **F188 has no change and no design** — nothing
under `openspec/changes/` references it. What is left is not a prioritisation decision but one queue
entry: *F188 is the last unspecced severity-A.* Its cited ledger size of 219 headings is now 289.

**From D-8 — a bring-forward list.** Absorbs entries 22-26, 28, 29. Re-queue or close, per row; none
needs a decision from the operator except by being scheduled. ~~One correction: the row claims the
Hub suite runs "~25 minutes". **This file already disproves that** — `hub/tests/` was measured at
**14:39** on 2026-09-01.~~ **Withdrawn 2026-09-03: the correction was wrong, and this is a better
example of the failure it was trying to name than the thing it corrected.** One measurement does not
disprove a range. Re-measured 2026-09-03 in a DECIDE session: **3850 passed, 84 skipped, 1 xpassed
in 24:50** — with the UI suite and the CI lint set running alongside it, where the 14:39 run had the
machine to itself. Both are real; the suite is **15–25 minutes and load-dependent**, which is what
both playbooks now say. The "~25 minutes" figure was never disproven, and two days were spent with
this file asserting it had been.

**Widened again 2026-09-08 by the night window's baseline green check: 3972 passed, 86 skipped in
46:41** (`py -3.11 -m pytest hub/tests/ -q`, started 23:00:59, exit 0). That is **1.9x the stated
ceiling**, and it is the third distinct figure from three runs, so the honest statement is
**15–47 minutes and load-dependent** — which is what both playbooks now say. Two stray `python`
processes from earlier windows (started 2026-09-07 20:15 and 21:55) were resident throughout and are
the most likely contention, but that is inferred, not measured. The point the 2026-09-03 entry makes
survives intact and is reinforced: no single run is *the* figure, and a window that sizes a firing
against one of them loses the iteration. Also still live there: F47/F120's
categorical third-actor prohibition, F77 (an agent has no way to address the operator), F53/F65
never queued, five findings queued 2026-08-29 and dropped from three runs, and the 8010 trial Hub
serving four-day-old code.

---

## Decided

### 2026-10-01 — `each-runner-cli-is-one-adapter` builds `CopilotAdapter` (F471)

- DECIDED   f471-copilot-adapter  **Build `CopilotAdapter` in this change, now.** The night of
  2026-09-30 finished the change's groups 1–3 with three conformance tests red: design D1 built
  a two-row `ADAPTERS` on the premise that slice 2 (`a-copilot-agent-runs-over-acp`) would add
  Copilot's adapter, but slice 2 landed first, without one, and had already widened `RUNNER_CLIS`,
  `CATALOG` and `WRITE_TOOLS` to Copilot. No queued change would ever add the adapter. Put to the
  operator in the morning-briefing session with three options: pin the gap as a strict, named
  exception and file a follow-up (recommended); build the adapter now; or `xfail` the three tests.
  The operator chose to build it now. Done as task 3.7, with each member delegating to the function
  slice 2 ships, so a Copilot run is unchanged and every `runner == "copilot"` carve-out (F473) is
  gone. Design amended at *What is verified*.

### 2026-09-24 — a pending proposal can be withdrawn: W3 (recorded 2026-09-30)

- DECIDED   f213-w3  **W3: de-duplicate at submission and give the operator a withdraw.** A repeat
  from the same proposer creates nothing, a revision (or a retraction) supersedes the proposer's
  earlier pending proposal, and a pending proposal can be withdrawn without a judgement. Answered in
  the operator's 2026-09-24 approval of `a-pending-proposal-can-be-withdrawn` (APPROVALS 2026-09-24:
  *"W3. Review fixes: a MODIFIED delta on the gating requirement; a retraction supersedes; a
  row-count-checked `UPDATE … WHERE status='pending'` for every status change."*). Written here when
  the change was built, as its task 0.3 asks.

### 2026-08-29 — self-registration leaves the product (recorded 2026-09-30)

- DECIDED   self-registration  **Delete it.** The operator, 2026-08-29: *"No it does not belong
  in the product … I think it's a legacy thing"* (untracked handoff
  `handoff-0099-2026-08-29-1250-merged-decided-drove-and-armed.md`, decision 2; FINDINGS F111,
  *"The decision, 2026-08-29"*). Approved as `agents-no-longer-register-themselves` on 2026-09-24
  with the Opus review's fixes, including its open question 2: `project_sessions` and
  `POST /session/sync` stay, and retiring them is a separate follow-on. Written here on
  2026-09-30, when the change was built, because it had lived only inside F111 (task 0.3).

### 2026-09-28 — ghcp slices 2–5: five answers after the Opus review

**DECIDED by the operator in an interactive session, 2026-09-28**, answering *"yes"* to every
recommendation put to them after the slices' R2, R3 and Opus adversarial review
(`spec-queue/tracks/reviews/ghcp-s2..s5-2026-09-28.md`). Each option was explained with its
background and cost before the answer. Applied to the designs the same evening.

- DECIDED   ghcp-a-spec-turn-full-access  **(c): a spec turn is judged as Workspace, even under Full
  access.** Its non-`edit` requests are judged by the `workspace` posture; the Hub never answers
  them ALLOW on its own authority. A spec turn never asks Copilot for allow-all, so it cannot learn
  whether managed policy withheld it, and ALLOW would grant through the Hub what the organisation
  withheld. Rejected: (a) ALLOW every non-edit; (b) probe allow-all, read it back, then decide.
  Slice 2 Q13, slice 3 Q11.
- DECIDED   ghcp-b-ceiling  **(b): the percent ceiling for every runner, the token ceilings only
  below 95.** A configured percent threshold past the final-warning point is lowered for every
  runner (a Claude 93–99 becomes 92, said on screen). The token-mode threshold and notes ceilings
  apply only when the runner compacts below 95%, because token mode exists for windows the Hub
  cannot trust and an early firing bills a checkpoint in automatic mode. Claude token mode is
  unchanged. Rejected: (a) uniform; (c) nothing for Claude. Slice 4 Q7.
- DECIDED   ghcp-c-quota-hold  **Keep the month-long hold**, and the notice states the reset date
  and the way out (rebind the agent to another runner, then message it). Slice 4 Q6.
- DECIDED   ghcp-d-slice5  **Slice 5's seven items, all as recommended:** no Copilot hooks; Azure
  and OpenAI BYOK deferred; the BYOK drive uses a dedicated, spend-capped Anthropic key set only in
  the trial Hub's launch environment, revoked afterwards, and only after review findings 2, 3 and
  10 are built; the key in the run's shell environment is accepted; no "compacted" banner for now;
  the GitHub-unavailable diagnostic may be removed if task 1.1 shows no MCP status event. Slice 5
  open question 8.
- DECIDED   ghcp-e-aw-tool-shell  **(a) now, (c) as a follow-up.** `aw-tool`'s standing approval
  under "Ask me" ships with the persistent-shell residual stated. Detect-and-degrade becomes a
  follow-up change if the work-PC drive shows persistent sessions in use. Rejected: (b) the `.exe`
  launcher; (d) a card per call. Slice 3 Q7.

### 2026-09-27 — GitHub Copilot CLI as a full runner: six answers after the exploration

**DECIDED by the operator in an interactive session, 2026-09-27**, answering D1–D6 of
`openspec/explorations/2026-09-27-copilot-as-a-full-runner.md` (size L chosen: a runner seam first,
then Copilot on it; MCP stays the primary channel, and a run must still reach the Hub when MCP is
blocked by company policy).

- DECIDED   ghcp-d1-instructions  **A Copilot custom agent file.** The agent's stable context
  (profile, charter, tools, model, effort) is rendered as `<COPILOT_HOME>/agents/<agent>.agent.md`.
  Per-turn material (turn notices, spec phase, team state) stays in the prompt, as for the other
  runners. Selection over ACP (the `agent` config option) is code-read, not measured: the R1 of
  slice 2 probes it, and falls back to an embedded resource on the prompt if it does not hold.
- DECIDED   ghcp-d2-native-files  **Copilot-native files are created when a Copilot agent is
  created.** The Hub writes that agent's Copilot files: custom agent, hooks, MCP config, and
  instructions. It writes them into a Hub-owned `COPILOT_HOME`, not the repository. The repo's own
  `CLAUDE.md`/`.claude/` still load (they cannot be switched off under ACP). The rendered context
  says it takes precedence where they conflict.
- DECIDED   ghcp-d3-credits  **Show credits as information.** Tokens stay the accounting unit.
  AI credits (`nanoAiu`) and premium requests are recorded and shown beside them, and do not drive
  the budget.
- DECIDED   ghcp-d4-test-account  **Drive on the Copilot Free plan for now** (Auto model only, small
  monthly allowance, 2 concurrent subagents). The "drive on Haiku" rule cannot be honoured on Free.
  A Claude Max subscription cannot be used as Copilot's model provider: Copilot's BYOK takes an
  Anthropic *API key*. The Max plan authenticates Claude Code and claude.ai by OAuth, and routing
  it through another harness is not a supported use.
- DECIDED   ghcp-d5-order  **Parity first:** slices 1 → 2 → 3 → 4 → 5 (seam; Copilot over ACP;
  reaching the Hub without MCP; spend; native agents and hooks). All come after the 2026-09-27
  night queue lands.
- DECIDED   ghcp-d6-correct-f299  **The 2026-09-21 `f299-f301` row's reopen trigger is corrected.**
  It read *"reopen when a runner that cannot take MCP — GHCP — is implemented"*. Copilot *can* take
  MCP: `--additional-mcp-config` stdio was verified on 1.0.88. The real trigger is **a run on a
  machine whose policy blocks MCP servers**. Copilot on the operator's work PC is the first such
  deployment. Slice 3 (`a-run-reaches-the-hub-without-mcp`) is where F299, F301 and F340 are
  answered for Copilot. The four findings' Status lines carry the correction.

### 2026-09-25 — request R1's two changes: four answers after R3

**DECIDED by the operator in an interactive session, 2026-09-25**, after R1 (an interactive explore),
R2 and R3 of `a-flow-is-configured-from-its-own-tab` and
`a-document-says-how-it-will-be-built-and-approval-starts-it`. Neither change has an APPROVED row yet.

- DECIDED   R1-stale-replace  **At approval the operator may pick a replacement agent, or no flow, for a
  stale delivery** (change 2, D5b). The replacement applies to that flow only. The document is not
  edited, and the approval report records the choice.
- DECIDED   R1-agent-operator-only  **Only the operator changes which agent a job names.** An agent's run
  is refused 403 (change 1, D2; task 0.1a).
- DECIDED   R1-ended-flow-report  **Re-approval that finds an ended, unarchived flow only reports it**, and
  says to archive it and start a new one. Approval never archives on its own (change 2, D6).
- DECIDED   R1-bugs-inside  **The two defects R3 found are fixed inside change 1**, not filed separately:
  a changed agent resuming the old agent's session, and `_do_fire_job`'s except path reading
  `acting_agent` before it is set.
- DECIDED   R1-past-stop-no-flow  **A `stop_at` already past at approval creates no flow**, and the
  report says so (R2's choice, accepted after the Opus review).
- DECIDED   R1-flow-link-agent-view  **The Spec page's Flow link opens the loop agent's view with no
  document attached**, and Back returns to the document (R3's choice, accepted).
- DECIDED   R1-control-resets  **An applied change of default agent resets the loop's `control` to the
  operator** (Opus review, change 1, finding 5, option b): a delegation to A is not a delegation to B.
  The creator stays "the agent the job names", as the code already measures it.
- DECIDED   R1-no-empty-flow  **An approval that would give the new flow no open task creates no flow**
  and reports it (Opus review, change 2, finding 2). This covers a failed board and a board whose
  every entry was already served.
- The Opus review (`spec-queue/tracks/reviews/R1-2026-09-25.md`) returned APPROVE WITH FIXES on both.
  Every fix was applied, and both changes were APPROVED the same day (`APPROVALS.md` 2026-09-25).

### 2026-09-24 — F378: what `request_agent` models a new agent on (recorded 2026-09-29)

**DECIDED by the operator on 2026-09-24** in the B3 daily review
(`spec-queue/tracks/reviews/B3-2026-09-24.md` §2); written here on 2026-09-29, when
`request-agent-models-the-new-agent-on-one-the-operator-made` was implemented, to close its task 0.3.

- DECIDED   F378-template  **A template is an existing open agent of the project**, named exactly
  (not a registry, not deleting the tool). The new agent takes its runner, charter and config, less
  `principal`, `yolo` and **`hub_client`** (operator: least authority) and less
  `AW_QUESTION_TIMEOUT`; no grant, posture or per-agent override is copied.

### 2026-09-24 — two decisions already made, now written down

**DECIDED by the operator; recorded 2026-09-24 in an interactive session** ("Record both"). Both
were decided earlier and were missing from this file. The B3 and B1 bundle rounds found the gaps
(`spec-queue/tracks/B3.md`, `B1.md`).

- DECIDED   D3-self-registration  **Agents no longer register themselves.** Self-registration is
  deleted along with `contact_mode` and its sibling columns. The operator decided this on 2026-08-29
  (handoff-0099, decision 2: *"No it does not belong in the product … I think it's a legacy thing"*;
  FINDINGS F111 *"The decision, 2026-08-29"*; `openspec/explorations/2026-08-30-release-roadmap.md:78`).
  It is carried out by the parked change `agents-no-longer-register-themselves` (B3), which is not
  yet approved.
- DECIDED   F327-scope-b  **Option (b): the dispatch, not the flow, stages `under_review`.** The
  operator chose this on 2026-09-23 (`ROUNDS.md` S13), and it **supersedes `F327-scope` option (a)
  of 2026-09-12** below. It is carried out by the parked change `a-flow-stages-its-review-in-the-dispatch`
  (B1), which is not yet approved.

### 2026-09-24 afternoon — the security REVISING rounds (B4, F409)

**DECIDED 2026-09-24, by the operator, in an interactive session** (AskUserQuestion), after R4 and
R5 on `the-shell-judge-reads-a-word-whole`, `a-drive-or-a-home-variable-names-a-directory-by-itself`
(`spec-queue/tracks/B4.md` `## R4`, `## R5`) and `an-at-mention-an-agent-wrote-reads-no-file`
(its design.md `## Round log`). All three stay REVISING until the Opus pre-approval review.

- DECIDED   B4-drive-exists  **On Windows, a one-letter-plus-colon word is judged as a drive only
  when that drive exists** (a wrapped `os.path.exists`). R5 measured the unconditional rule refusing
  873 of 42,860 of this repo's transcript commands (2.0%: `as e:`, jq `{a: .x}`, `Plan A:`).
  Rejected: keep the rule and accept 2%; drop the bash drive reading (reopens `c:$HOMEPATH`).
- DECIDED   B4-dep-links  **Build as written and file a finding** (F444) for globs and bare names
  through a worktree's shared dependency links (`node_modules`, `.venv`, `venv`), which point outside
  the workspace. The finding must be fixed before a JavaScript project is registered. Rejected:
  folding a read-through exemption into change 1 now.
- DECIDED   B4-residuals  **R4's and R5's three recommendations are accepted**: the `case`-arm
  residual stays (it can run a file outside, not write one; closing it refuses regex
  back-references); all four device names stay exempt (`/dev/null`, `/dev/stdin`, `/dev/stdout`,
  `/dev/stderr`), accepting the inner-PowerShell `> /dev/null` residual; change 2 builds after
  change 1, both in one night window.
- DECIDED   F409-Q4  **The composer-picker fix (D10) stays in `an-at-mention-an-agent-wrote-reads-no-file`.**
  It is the same F409 route and the only way agent text reaches what the operator types; the
  typed-answer exemption depends on it. Rejected: splitting it out, which would leave a measured
  bypass open until the split landed.
- DECIDED   B4-link-dotdot  **A `..` after a link is judged physically, in change 1.** The second
  pre-approval review (`spec-queue/tracks/reviews/B4-2026-09-24-second.md`) measured `cp n sub/l/../y`
  writing outside through the Bash tool on Windows today, and `sub/l*/..` allowed after the change.
  Change 1 adds the physical reading to D8's walk and to `_where`, with tests, so its restated
  "Traversal and links cannot escape" holds. Rejected: a separate finding with the delta qualified.
  Both B4 changes stay REVISING; the operator runs R6 in a later session, after a handoff.
- DECIDED   F409-approve  **`an-at-mention-an-agent-wrote-reads-no-file` is approved once the
  second review's seven fixes are applied** (`spec-queue/tracks/reviews/F409-2026-09-24-second.md`),
  including the two cross-change notes written into B5's `evidence-is-decided-after-the-run-that-recorded-it`
  and B7's `worker-spend-counts-against-the-budget`, and F445 filed for the in-workspace link that
  lists an outside file.
- DECIDED   B4-temp-dialect  **`Temp:` counts as a drive only in the PowerShell dialect** (R6's
  wording in `a-drive-or-a-home-variable-names-a-directory-by-itself`). In bash, `temp:` is ordinary
  text, such as a YAML key in a heredoc. The accepted residual: `pwsh -c '…Temp:'` sent from the
  Bash tool stays allowed. Windows PowerShell 5.1 has no `Temp:` drive at all; only PowerShell 7
  does. Rejected: both dialects.
- DECIDED   B4-approve  **Both B4 changes are approved as R8 left them** (`the-shell-judge-reads-a-word-whole`, `a-drive-or-a-home-variable-names-a-directory-by-itself`). The third
  Opus review (`spec-queue/tracks/reviews/B4-2026-09-24-third.md`) returned APPROVE WITH FIXES with one
  blocking HIGH (a non-plain word's value was never judged as a path). The operator chose "R8 fix, then
  approve" over a further check round, then approved R8's three measured departures from the review's
  text: on a drive-letter host the value is judged between its colons (ntpath reads `x:` as a drive;
  judged whole, 44 of 26,038 transcript words were falsely refused); bracket expressions fnmatch cannot
  read (`^`, `!`, `[`, `\`, backtick) loosen to `?`; `_glob_links` does not re-judge its own base.
  Accepted residual: a directory whose name holds a colon (only Git Bash can make one) with a link
  behind it, refused today by its tail and allowed after. R8's out-of-scope false refusal
  (`rg foo src/a:1`) is filed as F446. Rejected: close the colon gap first; hold for a check round.

### 2026-09-24 — the daily review of the twelve bundles

**DECIDED 2026-09-24, by the operator, in an interactive session** (DECIDE). Each bundle's
recommended answers were taken as recommended unless noted below. The per-change record is in
`APPROVALS.md` `## 2026-09-24`, and each change's `design.md` opens with `## Operator review,
2026-09-24`. Only the rows that are decisions rather than approvals are listed here.

- DECIDED   F42-by-design  **F42 is closed as by design** (B2 D11). A run bound to a task at
  `-> in_progress` may reach `completed` without completion evidence. Requiring evidence there
  deadlocks the ordinary path, and the residue is one attributable task per run, reviewed by someone
  else. Do not re-file.
- DECIDED   F291-F273-run-facts  **An undelivered message says how its last attempt ended, read from
  the run's own facts, never derived from the output stream alone** (B2 D11). F291: the run facts map
  gains `error` (`RunFacts.error`, fitted to 500 characters), and the abandoned turn renders it beneath
  the Hub's reason. F273's premise (the persisted status line is the only record of a run's outcome) is
  obsolete — the run's row and the facts map already carry status and exit code — so the requirement is
  amended to match what the code does; no product change for F273 itself. Built as
  `an-undelivered-message-says-how-its-last-attempt-ended`.
- DECIDED   B2-follow-ups  **The 2026-08-21 decision ("failed at once, no new vocabulary") stands for
  now.** Revisiting it, together with the reaper's no-runner case, is queued as `REQUESTS.md` R7 for
  its own spec loop. History rows naming their agent is R8.
- DECIDED   B8-D6-final-warning  **A reopened, handed-over conversation keeps its free final
  compaction warning.** Only the billed steps decline (amends B8's D6).
- DECIDED   B10-stale-stop  **A stop on a loop that has already ended is refused (409)** and its
  record is left as it was. `end_loop` is write-once.
- DECIDED   B9-Q1  **The app keeps no runtime event allowlist.** The Hub's event vocabulary
  (`sse_events.py`) is generated into a TypeScript type, so a handler for a kind that is never sent
  fails `npm run build` (option B; `every-event-the-hub-sends-reaches-the-app`).
- DECIDED   B9-Q2  **F251's UI bundle is committed only after the operator restarts `:8000` onto
  F335's fix** (task 0.5 of the same change).
- DECIDED   B11-all  **B11's 22 answers are taken as recommended** (`spec-queue/tracks/B11.md` Final),
  including: pin the tool server; F177 lists in creation order (`rowid`); run F21's six-turn Haiku probe;
  an adopted in-progress task keeps its assignee; runner names join the uniqueness rule; build F389's
  count; a failed refusal withdrawal still answers 500. After the review: charter and runner names are
  unique by exact match; a find-or-create runner collision takes a suffixed name; one window profile
  per `--profile`; the tool-server pin lives under `~/.agentweave/hub/tool-server/`; F349 also covers
  the firing path and retries transient errors only; F248 is reserved at create time only (REVISING).
- DECIDED   F307-initial-focus  **A confirmation dialog opens with focus on Cancel**, and other dialogs
  focus the element with the explicit mark. The four hand-built dialogs that lacked the hook (Charters
  form, JobForm, Runners form, SetupModal) join it in the same change.
- DECIDED   B3-hub-client  **`request_agent` does not copy `hub_client`** from its template (least
  authority: the new agent runs MCP plus workspace).
- DECIDED   B3-D8  **A job's moves are recorded as `operator` with `origin="job"` and `job_id`**. A
  divergence-restaffed review staged late stays "You moved"; a manual Run press reads "Loop X moved";
  the 38 existing rows are not rewritten.
- DECIDED   B3-all  **B3's recommendations are taken** (`spec-queue/tracks/B3.md` Final). Self-registration is deleted (`D3-self-registration`, plus the design's Open Question 2 as recommended). `request_agent` templates are an existing open agent, with no grants or posture copied, and no `yolo`, `hub_client` or question-wait overrides. F77: a refusal only, with the retired "unasked question" requirements removed in the same change. F139: full `mcp__agentweave__…` names, and the host `SendMessage` stays. F366: agents write status, notes and requirement links, and the operator writes holder, priority, description and title. F125: the operator may rename a task. F276: closed as decided. The pause (F15) is REVISING (see APPROVALS).
- DECIDED   0923-changes  **The 2026-09-23 day window's two changes were approved with their defaults.** `pressing-run-names-the-reason-that-held`: F411, F412 and F413 stay separate findings, and the proposed scope-clause wording stands. `an-at-mention-an-agent-wrote-reads-no-file`: Q1 (a hand-typed `@path` in a job prompt no longer expands), Q2 (`a\@b.com`) and Q3 (Start work keeps the title, escaped) are accepted. The review then sent it to REVISING over the label-answer bypass.
- DECIDED   B12-F278-revise  **F278's change goes back for a round** (REVISING): base64 key segments
  and short tokens inside paths.

### 2026-09-22 afternoon — F119: `doctor`'s secret filter stays broad; R9-5 reconfirmed

**DECIDED 2026-09-22, by the operator, in an interactive session.**

- DECIDED   f119-doctor-redaction  **The CLI's `doctor` keeps its broad catch-all** (`[A-Za-z0-9_=-]{32,}`,
  `src/agentweave/diagnostics.py`); it is not narrowed to the Hub's post-F31 rule. `doctor` prints env and
  config values, where a long unbroken string is far more likely a real key than an identifier. Over-redacting
  there costs a few blanked words, while under-redacting leaks a credential into a pasted report. F31's
  measurement was of transcripts and does not transfer. This closes F119, the only question it ended on.
- DECIDED   unstaffed-r9-5-reconfirmed  **R9-5 "dropped" meant accepted as is**, as recorded above; the
  operator confirmed it when asked, before tonight's arm. No APPROVALS change.

### 2026-09-22 — `an-unstaffed-review-names-its-holders` groups 2, 5, 6 approved; R9-5 dropped

**DECIDED 2026-09-22, by the operator, in an interactive session** ("Great, approve.", then "yes
dropp it"). This follows the Round 9 that the 2026-09-21 late-night `unstaffed-r8-review` decision
asked for. It ran in the 2026-09-22 day window (`design.md` `## Round 9`): R8-1..R8-5 hold, three
LOW text fixes were applied, and F407 was filed and fixed the same day.

- DECIDED   unstaffed-approve  **Groups 2, 5 and 6 are approved** (group 1 is already built). They are
  queued for the night of 2026-09-22, after F388's change. The `unstaffed-bundle` rule stands: group
  5's bundle is committed only if 5.3's served-bundle drive passed.
- DECIDED   unstaffed-r9-5  **R9-5 is dropped: accepted as is**, with neither cure (a) nor (b)
  applied. A sentence over 500 characters may end with the REJECT remedy even when no booked clause
  survived the fit. The remedy is still true, and the delta's SHALLs are met. Round 9 recommended (b),
  but each cure changes the fit's arithmetic, and three earlier rounds shipped fixes to that
  arithmetic that a later round found broken. Revisit only if it is seen live.

### 2026-09-21 late night — `an-unstaffed-review`'s three questions answered; `examples/` deleted

**DECIDED 2026-09-21 ~21:40, by the operator, in an interactive session** ("delete. yes"). The
three questions had been carried since handoff 0135.

- DECIDED   unstaffed-booked  **`an-unstaffed-review-names-its-holders`: the holdings clause reads
  `is booked for`** (R8-2), and R8's clause order stands: excluded, no runner, held, booked, running.
- DECIDED   unstaffed-bundle  **A night window may commit group 5's UI bundle.** The rule is still
  task 5.4's: commit only if 5.3's served-bundle drive passed. The operator accepts that a committed
  bundle reaches `:8000`'s live app on its next reload.
- DECIDED   unstaffed-r8-review  **Before anything is built, a short review of Round 8 only runs in
  the day window of 2026-09-22** (`DIRECTION.md` `## 2026-09-22`). It checks R8-1 to R8-5's fixes
  against the tree, not the whole change. **This decision is not an approval**: groups 2, 5 and 6
  still carry no token. If the review returns clean, that day's DECIDE session may add the row.
- DECIDED   examples-delete  **`examples/` is deleted whole**, and `CONTRIBUTING.md`'s tree line
  with it. Without `cli_session.sh`/`.bat`, whose commands no longer exist, only a README saying
  nothing there works would have been left (F405).

### 2026-09-21 night — F388's change approved after R4 and a second Opus pass

**DECIDED 2026-09-21 ~21:30, by the operator, in an interactive session** ("yes approve"). This came
after R4 on `a-hub-that-was-not-told-which-database-refuses-to-open-one` (`da19eb5`), which answered
the 2026-09-20 Opus DO NOT APPROVE. The standing adversarial Opus pass then ran over R4 and returned
APPROVE WITH FIXES, with one blocking item (the `agentweave-hub` console script and
`docs/reference/env-variables.md`). All of its items were applied in `b14342b`.

- DECIDED   f388-approve  **The change is approved, all groups (1-6).** It is queued for the night of
  2026-09-22 in `APPROVALS.md` `## 2026-09-22`, not tonight: tonight's ORDER was already full.
- DECIDED   f388-8000  **The `:8000` effect is accepted as measured.** `:8000` is a CLI-started, told
  launch (R4, corrected by the Opus pass), so (a) does not refuse it. On the operator's next restart
  it runs the new `config.py`/`main.py` with no migration and no UI bundle. Group 2's startup line
  goes to `DEVNULL` there, and that is a known limit, not a defect.
- DECIDED   f388-unreviewed  **The Opus pass's fixes are not re-reviewed**, the same call as F375. The
  build's own tests and the group 6 drive are the check. If a task disagrees with the code, the task
  is the more likely thing to be wrong.

### 2026-09-21 late evening — F375's change approved after three rounds

**DECIDED 2026-09-21 ~19:50, by the operator, in an interactive session** ("approve"), after the
spec loop on `a-word-without-a-separator-can-still-leave` (R1 `38c243a`, R2 `55ae8e7`, R3 `4f87390`)
and a summary of its five open questions with a recommendation on each. Approved as recommended:

- DECIDED   f375-tilde  **R3's narrowed `~` check** (design Open Question 5): refuse only the shapes a
  shell substitutes (`~`, `~+`, `~-`, `~name`); `~N` and `~30%` stand.
- DECIDED   f375-d7  **Option-joined values stay in scope** (Open Question 3), with R3's widening of
  the colon form to both dialects and `--name:`.
- DECIDED   f375-d9  **Archived `a-url-is-not-a-path` D9 is superseded** (Open Question 4) for R8
  (`cd ..`), R9 (`git -C ..`) and its two PowerShell residuals.
- DECIDED   f375-findings  **File D5, D6 and brace expansion as findings** (Open Question 1): F401,
  F402, F403, all (B).
- DECIDED   f375-8000  **Task 0.4 is satisfied by this approval**: the operator was told, before
  approving, that editing `mcp_server.py` changes `:8000`'s next run, committed or not.
- Noted, not waived by name: the standing Opus review before approval was offered (R3's fixes are
  unreviewed) and the operator approved without it. The build's own tests (tasks 1.x, 2.3) are the
  check on R3's text.

### 2026-09-21 evening — the week's scorecard asks for decisions, and four are made

**DECIDED 2026-09-21 ~17:30, by the operator, in an interactive session** reviewing the week
scorecard (O4: severity A 8 → 2; O5: ≤ 2 open changes / ≤ 40 tasks). The day window had finished
its whole queue by 10:08 because every open change was gated on spec work or on the operator, and
the drain rule stopped it doing the spec work.

- DECIDED   f299-f301  **Triage: won't build now.** F299 + F301, with F339 and F340 grouped in
  (the 2026-09-13 afternoon shapes (i)/(ii)/(iii) stay parked). Both creatable runners take MCP
  (`RUNNER_CLIS = ("claude", "codex")`, both in `MCP_INJECTABLE_RUNNERS`), `hub_client` has no UI
  control, and shape (ii) buys editing only. **Reopen when a runner that cannot take MCP — GHCP —
  is implemented.** *(Corrected 2026-09-27, `ghcp-d6-correct-f299`: GHCP can take MCP; the trigger is a run on a machine whose policy blocks MCP servers.)* Each finding's Status line now carries this; they stay counted as open.
- DECIDED   f325  **Keep open.** The operator declined to retire it, although Codex is cancelled as
  undrivable (2026-08-29). It remains an open severity A nobody can currently drive.
- DECIDED   loop-staffs-s5  **Move §5 out of `a-loop-staffs-the-agent-it-names` as a finding (F400),
  drive §7 and archive the rest.** §5 was never approved (its `:1471` requirement was rewritten in R4
  and never re-rounded). The change's delta is trimmed to what the built groups do before archive,
  so archiving syncs nothing the code does not meet.
- DECIDED   unstaffed-review  **One verification round now, then build if it comes back clean.**
  First put to the operator on a false premise — a stale "STOPPED 2026-09-14" banner in `tasks.md`
  was read as the change's state — and corrected before acting: `proposal.md` records R5/R6
  re-derived it against (f) on 2026-09-19, group 1 is built (`f663898`), and groups 2/5/6 are
  F352's visibility half, the only proposal for that severity A. The operator's first answer
  ("reject") was given on the false premise and is **void**.
- DECIDED   tonight-order  **Tonight's `ORDER:`** — archive `a-first-turn-is-not-told-it-has-nothing`;
  F380 as a no-spec repair; F292 fix-or-quarantine; `a-loop-staffs-the-agent-it-names` §7 then
  archive. Written into `APPROVALS.md`'s `## 2026-09-21`.

### 2026-09-20 evening — F302 reaches R2, and its one dissent is answered with a measurement

**DECIDED 2026-09-20 evening, by the operator, in the same interactive session.** F302's 2026-09-09
verdict was found decided-but-unbuilt; the operator directed it into openspec under the **full**
R1/R2/R3 discipline rather than a single verification round. R1 and R2 have run, R2 as a fresh
process with no access to R1's reasoning. R3 is still owed.

- DECIDED   f302-d2-dissent  **Ship the decided shape, then measure — the conditional text is
  neither adopted nor closed.** R2 dissented from design D2: it argued the declined one-text
  alternative (*"the `agentweave` tools are available if they appear in your tool list; otherwise
  the same operations are HTTP requests"*) is the better change, because the Architect kept to
  `curl` for **ten runs after the notice healed**, so what persisted was the positive HTTP steer
  this change keeps rather than the falsehood it removes. **What decided it: that evidence is
  confounded and the confound cannot be resolved from the observation it rests on.** By the time
  the notice healed the Architect had already learned a working method — payload shapes derived
  from two 422s, a file-plus-`curl` routine that worked. "The steer keeps pointing it at `curl`"
  and "it kept a method it had already paid for" both fit that record, and one agent that had
  already invested cannot separate them. **Only a fresh agent's first turn can**, and that turn
  cannot be observed until the falsehood — a competing cause — is gone. So: land the change, then
  measure, then decide. Recorded as **tasks group 7**, with the change barred from archive until
  7.4 carries counts, because a "decide after measuring" that never measures is **F392** in a new
  coat. *Rejected:* **keeping the decided shape and closing the question**, which would bank an
  unproven claim that the behaviour is fixed; **switching to the conditional text now**, which
  would overturn the 2026-09-09 verdict on confounded evidence and rework a delta that has passed
  two rounds.
- DECIDED   f302-home  **openspec, not the trial Hub, and the full three rounds.** The change edits
  a shipped requirement in `agent-capability-plane`, and the corpus is openspec's. *Rejected:*
  authoring it in the trial Hub, which would have needed hand reconciliation back into
  `openspec/specs/`; and the single verification round CLAUDE.md allows an already-proposed change,
  because the verdict predated both the approver fix and F393's correction of the runner registries.

**What R2 found, recorded here because it is the argument for not collapsing the rounds.** R1's
premise, its independent `_decide` measurement and its spec fidelity all survived. But
`_tool_surface_lines` (`hub/hub/api/v1/agents.py`) renders the *same* false denial from the *same*
`described_path`, reaching the model as `--append-system-prompt-file`, and R1's Impact had
explicitly excluded that file — so the change would have shipped **violating its own new scenario**.
`hub/tests/test_launchability.py::test_a_run_without_mcp_is_not_told_it_cannot_act` exists to stop
exactly this class of sentence and checks only three *older* wordings, which the live clause walks
past. R1 had also silently narrowed a MODIFIED SHALL, dropping the HTTP-form obligation in the one
world where HTTP is the run's only path, and had described the 2026-09-09 verdict as conditional
when it is flat.

### 2026-09-21 — F302 group 7 measured: 3 of 3 fresh first turns reached for MCP

**MEASURED 2026-09-21**, tasks 7.1-7.5c of `a-first-turn-is-not-told-it-has-nothing`. Throwaway Hub
(`:8091`, scratch profile `testbed/scratch/f302_measure/`), three brand-new agents, Haiku
(`claude-haiku-4-5-20251001`), one capability-plane instruction each ("create a task..."), one turn,
no charter, peers present in the roster. Preconditions confirmed against the scratch db before
triggering: no session-wide or per-agent `hub_client` override, runner `cli=claude` (MCP-injectable),
zero prior runs with `mcp_adapter_online_at` set for all three agents.

- DECIDED   f302-d2-measurement  **All three sampled first turns called `mcp__agentweave__create_task`
  directly, with no HTTP shellout anywhere in any transcript** (run-3e7497554e98, run-63c923499c5d,
  run-9ddb13b6dfeb; full transcripts quoted in `scripts/drive/FINDINGS.md` F302). Per tasks.md 7.5c's
  first branch: **the positive HTTP steer does not dominate a fresh turn**, which weakens R2's
  f302-d2-dissent substantially. **This does not close D2** — n=3, one model (Haiku only), one
  instruction shape, one throwaway project, and the confounds in 7.5b (model, task shape, surrounding
  text) are unaddressed by this sample. F302 is marked **fixed, measured** in `scripts/drive/FINDINGS.md`
  — not fixed without qualification. *Not decided here:* whether the conditional text R2 preferred is
  still worth building; this measurement answers only whether the shipped shape's own first turn
  reaches for MCP, and on this sample it does.

### 2026-09-20 — archival's blast radius, and an approval taken without the adversarial pass

**DECIDED 2026-09-20 afternoon, by the operator, in the interactive session that resumed handoff
0132.** The day window had already hit the weekly usage limit, so this did not come from a window.

- DECIDED   archived-agent-blast-radius  **API plus a persisted, broadcast archival event — the
  middle of the three shapes offered.** The change `an-archived-agent-holds-nothing-and-is-offered-nowhere`
  carried exactly one question through three rounds: how far past the API does it go. Chosen because
  `persist_event` and `sse_manager.broadcast` are both server-side, so the rider's *recording* half
  is discharged with nothing under `hub/ui/src` and nothing reaching the live `:8000` app on reload —
  the cost that made the third option expensive. *Rejected:* **API only as R3 left it**, which leaves
  the released charter's identity existing solely in a response body that `useArchiveAgent`'s
  argument-less `onSuccess` discards, so the fact dies with the request. *Rejected:* **accepting the
  bundle refresh**, which would close the display gap properly but commits `hub/ui/src` and
  `hub/hub/static/ui` together and reaches the operator's live app. Carried as **group 2b**;
  `design.md` D10 holds the full reasoning. **Not decided, and still open: the display half.**
  `useSSE.ts:31`/`:460` do not know the new kinds, so an operator still sees nothing.
- DECIDED   archived-agent-group-5  **Build it.** The trim to `DIRECTION.md`'s three files was
  offered — R1 had marked group 5 (`runners.py`, F390) as the one part safe to cut — and declined.
- DECIDED   archived-agent-opus-pass  **Skip the standing adversarial Opus review for this one
  change.** The operator's own standing rule (`feedback_opus_review_before_approval`) asks for an
  adversarial pass before any `- APPROVED` row; they instructed otherwise here, on the grounds that
  R1, R2 and R3 ran as three independent processes and each corrected the last — unlike
  `a-loop-staffs-the-agent-it-names`, where two of three rounds shared a session and a later
  adversarial pass returned eight blocking findings. **Recorded because its absence is otherwise
  indistinguishable from an oversight**, and because the consequence is specific: D10 and group 2b
  are R3-and-later work that nothing has re-derived. *This decision is about one change, not about
  the rule.*

### 2026-09-19, second sitting — two severities rated, and tomorrow's second spec loop named

**DECIDED 2026-09-19 afternoon, by the operator, in the interactive session that resumed handoff
0131.** Two of these close a question carried in the handoff chain eight times.

**The question itself was wrong as carried.** It read *"five open findings with no severity (F77,
F130, F132, F165, F167) can never be reached by the night window's A-before-B-before-C queue"*.
Three of the five do declare a severity — F77 is C, F165 and F167 are both B — and
`backlog_page.py` simply could not read the spelling they used. Fixing the parser (`3918fa9`) also
found **F166 (C) and F168 (B), which had never appeared on the backlog page at all.** So the real
decision was over two findings, not five.

- DECIDED   F130-severity  **B.** Not A: it needs an operator action to trigger — pressing
  Checkpoint twice with no turn between — and nothing is lost or blocked when it fires. Not C: once
  tripped it is permanent and unbounded, because nothing ever re-establishes a non-NULL
  `covers_through`, and the observed damage was a checkpoint whose prose said the work was not done
  while its own file list named the file it had created. *Rejected:* **A**, argued on the grounds
  that it hands a worker a false record rather than merely a bill, and that worker tokens are now a
  real constraint under the weekly window — refused because severity measures what the product does,
  and here it keeps working, over-widely. *Rejected:* **C**, which would have left it unreachable in
  practice, since 89 C's are open and the queue has never reached that far.
- DECIDED   F132-severity  **C.** The trap cannot spring: the same missing UI that cannot clear a
  drift candidate cannot raise one, and no MCP tool or agent route reaches `/spec/drift` either, so
  nothing in the product can put a requirement into `DRIFTING`. A half-built feature, not a
  misbehaving one. *Rejected:* **B**, argued on consequence rather than probability — one call to
  `POST /spec/drift/detect` makes a `gate`-rigor requirement permanently un-approvable through the
  app, with no escape. **That argument was accepted as correct and deferred, not dismissed:** the
  finding now records that it becomes B the day any drift caller ships, and that whoever builds one
  owns raising it in the same change. *Rejected:* folding F132 into F129 and retiring it, which
  would have stopped tracking the gate's unactionable remedy anywhere.
- DECIDED   day-2026-09-20-loop-2  **`F388` (A) — a Hub started from source silently opens the
  operator's live database.** Named in `spec-queue/DIRECTION.md` so the window does not choose for
  itself. It is the only open severity-A that is already decided (a+b+d) and has no change
  directory, and it is a hazard on this machine specifically. Its blast radius shares no file with
  loop 1 (`charters.py`, `agent_lifecycle.py`, `agents.py`) or with either approved-and-unbuilt
  change. *Rejected:* **F299+F301** as one change, whose runner/transport blast radius would have
  cost R1 a round just to establish the boundary between them; **F347**, a first-run barrier but a B
  while eight A's are open; **F168**, which is a missing feature rather than a defect, so a round on
  it would be product design rather than repair.

### 2026-09-19 — six decisions in one sitting: the gate, the day's shape, and four findings

**DECIDED 2026-09-19 afternoon, by the operator, in an interactive DECIDE session**, after being
driven through each one with its consequences. Several had been carried unanswered for four to five
days. The operator's framing that governs two of them:

> *"The daily windows is for driving the app on a e2e process finding problems and doing spec round
> for me to just read and approve for the night run."*

- DECIDED   merge-gate-cadence  **The gate runs at window close, not iteration 1.** Move it to the
  window's final firing, after the last commit, and let it wait for CI to conclude at `HEAD`.
  Nothing commits behind it, so the ~13-minute clock finishes instead of being restarted by the
  next iteration's own commit. Costs the tail of the window; keeps the CI condition intact; needs
  no extra firing. *Rejected:* waiting at iteration 1 up to a budget (the next firing commits
  anyway, so it only works if the budget exceeds a full CI run); a firing whose only job is the
  gate (it still arrives after a committing firing); dropping condition 3 (`master` stops being
  CI-verified at merge time, and `master` is what `:8000` eventually runs). Closes a question
  carried on the 09-16, 09-17, 09-18 and 09-19 review pages.
- DECIDED   day-window-spec-gate  **Gate on undecided, not unbuilt.** The drain count that decides
  whether a spec loop runs counts only changes waiting on the **operator** — an `APPROVED` change
  waiting on a night no longer suppresses tomorrow's proposal. This is the real defect: all four
  starved days were gated by proposals awaiting an operator token, not by night capacity, so the
  window stopped producing the one thing the operator opens it for. *Rejected:* dropping the gate
  entirely (restores the 2026-09-08 pile-up it was added to stop: 129 tasks, 2 ticked); raising the
  threshold to 3 (arbitrary, and still counts the wrong thing); leaving it (the starvation was not
  self-releasing — it ran four days).
- DECIDED   F388-fix  **Refuse the implicit default, log the resolved path, fix the docstring**
  (options a + b + d). Direct `uvicorn hub.main:app` with no `DATABASE_URL` fails to boot with a
  message naming the two ways to set it; every startup logs the resolved absolute database path and
  whether the file pre-existed, at INFO, as its first line; `config.py:12-15`'s docstring stops
  claiming the default "never fires" for the exact invocation `CLAUDE.md` prescribes. (a) alone
  would have prevented the 2026-09-19 incident. *Rejected:* logging only (prevents nothing); the
  primary-profile sentinel (c) (strongest, but needs a migration installed **against the operator's
  live database**, which is the thing being protected).
- DECIDED   F387-fix  **The sort goes in `list_questions`' `order_by`**
  (`hub/hub/api/v1/questions.py:318`), not in the card. Blocking first, then newest, so every reader
  gets a correct floor at once — the Overview card, the conversation tray (`F381`), and any surface
  added later. *Rejected:* the card alone (narrower blast radius, but leaves every other reader on
  oldest-first); both (duplication without a named failure it prevents).
- DECIDED   F374-fix  **A gate-refused approval is not "no verdict", and no operator-only refusal
  re-staffs.** Any 409 naming a remedy only the operator can apply ends the review and surfaces the
  gate's own sentence to the operator, rather than re-staffing to a second reviewer who meets the
  identical refusal. Deliberately broader than F374 measured, so it covers `F352`'s and `F316`'s
  seams in the same repair. *Rejected:* keeping the re-staff and only correcting the false staffing
  message (still pays a second review turn on a refusal no reviewer can clear, in the week the
  rate-limit window counts); scoping it to the evidence gate alone.
- DECIDED   F128-fix  **The free list becomes loop-scoped.** A loop staffs only the agents it names;
  a flow staffs its roster, so design D12's width survives where D12 meant it. This restores the
  invariant `_agents_that_are_free`'s own docstring already claims. **F127's 500 must be fixed in
  the same change** — the busy-guard becomes reachable again, and that is exactly the corner where
  it answers 500. Accepted cost: a loop pinned to a busy agent now waits, including on `:8000`,
  where loops that currently keep moving by substituting will start idling. What decided it: an
  agent is not only a name — `charter_id` (`models.py:219`), `runner_id` (`:216`) and the three
  authority flags `can_read_checkpoints`/`can_recall`/`can_accept_evidence` (`:254-268`) all live on
  the `Agent` row, so a substitution silently swaps the behaviour text, the runner **and the
  permissions the operator selected that agent for**. *Rejected:* UI/API honesty alone (leaves the
  authority hole — a UI that correctly reports you have no control); a per-job opt-in width flag
  (a **flow** already is the width case, so the flag re-implements an existing concept at the cost
  of a migration and a control — struck under the standing "cleanest solution wins" preference).

**Correction, 2026-09-20 (night window, `alsn-closeout`).** The row above's sentence *"F127's 500
must be fixed in the same change"* was stale when written on 2026-09-19 afternoon: F127 was already
fixed five days earlier, by `c8e3bbd` on 2026-09-14 (`a-spent-allowance-holds-the-queue` design D11,
archived), not by this change. `a-loop-staffs-the-agent-it-names` made that existing fix's busy-guard
reachable again in the multi-agent shape F128 used to hide it in — driven live and confirmed in
`scripts/drive/FINDINGS.md`'s `D-4, 2026-09-20` — but it did not fix F127 itself. Appended per this
change's own task 8.4 instruction not to edit the row.

**Also settled, as queueing rather than deciding:** `F185` + `F181` share one root cause
(`agent_lifecycle.archive` leaves `charter_id` bound) and their remedy was already decided at
`DECISIONS.md:536` and `:586`. They become **one change, taken by the next day-window spec loop** —
which the `day-window-spec-gate` decision above now permits to run.

**Three carried questions closed as stale in the same sitting**, verified before closing: `F356` is
**fixed** (`d16a76a`, `a-late-answer-is-delivered`, 2026-09-15, driven live 22/22); `F188` was
**retired** 2026-09-04, so the night playbook's "last severity-A finding with no change" line points
at nothing; `F185`/`F181` needed a change directory, not a decision.

Decided entries from 2026-09-15 and earlier, and `## Closed by measurement, 2026-09-01`, are in
`archive/DECISIONS-to-2026-09-15.md` (moved 2026-10-04). A citation like "`DECISIONS.md`, `### 2026-09-15`" resolves there.
