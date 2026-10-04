# Decisions — archive, decided on or before 2026-09-15

Moved out of `spec-queue/DECISIONS.md` on 2026-10-04. Every entry is DECIDED or closed; none is OPEN.

### 2026-09-15 — the windows are routed, metered, and trimmed rather than capped

**DECIDED 2026-09-15 ~09:20, by the operator, in an interactive session** (the day window was
disabled for the day at their request). The operator's words:

> *"With the promo I wans using everything right on the weekly window so it fit me perfectly but now
> it's not going to be enought at all. So we need to be more deliberate and find a better way to
> execute our autonomous windows. The windows are working perfectly so I want to keep using them."*

Measured first (09-14 transcripts, list-price weights): every window call ran on `claude-opus-5` at
effort `high` — day $222 incl. $32 of Opus subagents, night $92; LoopEngine's agents $153 that day;
~60% of cost is cache reads, so context size is the budget. The weekly bar read 49% on the Tuesday
morning of a week resetting Sunday. Three decisions, chosen from options put to the operator:

- DECIDED   window-model-routing  **Spec rounds on Opus, build on Sonnet.** R1–R3 and REV stay on
  Opus/high (the round discipline is untouched); `-impl` runs on Sonnet/high; drives, gates,
  archives, ledger, compose and read-and-sort items on Sonnet/medium; unrecognised ids default to
  Opus/high. Encoded in `.claude/loops/usage-policy.json`, read by `run-iteration.ps1` per firing
  from STATE's `current`; an item's own `model`/`effort` overrides. *Rejected:* only mechanical items
  on Sonnet (~15–20% saving); Sonnet everywhere but REV (weakens R2/R3).
- DECIDED   meter-before-cap  **Meter for a week, then set caps.** Every iteration writes one row
  to `.claude/autonomous/usage-ledger.jsonl` from its own `--output-format json` result; the
  statusline persists the plan's real 5-hour/weekly percentages to `~/.claude/usage-snapshot.json`
  and `usage-history.jsonl`; `.claude/loops/usage_report.py` joins them into $ per 1% of weekly.
  No window cap until then — only a per-iteration runaway guard (`--max-budget-usd 40`) and a
  60-minute pause after a usage-limit refusal. **Revisit ~2026-09-22** with a week of calibration.
  *Rejected:* a 50% or 70% share now, set blind.
- DECIDED   claude-md-slim  **Slim CLAUDE.md for every session.** 33 KB → 11 KB; runbooks moved to
  `.claude/reference/`, recipes to path-scoped `.claude/rules/` (verified to load only when a
  matching file is read). An independent review found three dropped constraints; all restored.

This closes `weekly-window-care` below: the throttle is routing + trimming now, and a cap after
calibration.

### 2026-09-15, later — the build queue: F332-rule and the review-staffing split

**DECIDED 2026-09-15, by the operator, in an interactive session**, with no daily window running
that day.

- DECIDED   F332-rule  See the row under `## Open` above, now flipped: revise, one more
  verification round, then build.
- DECIDED   split-unstaffed-review  **Approved REV's split of
  `an-unstaffed-review-names-its-holders`, and executed** (`cba4ae2`). The F353 half (task groups
  3 and 4, 2.5, 2.5b, 2.12 and 2.13 — the refusals' remedies, F334's wording, F365's once-per-task
  record, the `error_summary` fit F367 needs) now lives at
  `openspec/changes/a-refusal-names-a-remedy-that-works/`, renumbered, ready for its one
  verification round, and does not wait on `F352-free`. The rung-3 naming half (D1, D2, D3, D6,
  task 2.14) stays in `an-unstaffed-review-names-its-holders`, annotated stale against `F352-free`
  (below), and needs its own re-derivation round against (f) before it can build.

`F352-free` itself was decided the same day: see its own row below, **REJECT (d), go with (f)**.

### 2026-09-14 afternoon — LoopEngine stays parked, and the weekly rate-limit window needs care

**DECIDED 2026-09-14 ~14:50, by the operator, in an interactive session** (not the day window),
after the session reported LoopEngine stalled since 07:02 on the `review_unstaffed` staffing gate
(F352), with 498 consecutive no-staff ticks and nothing moved since 06:41. The operator's words:

> *"Let's leave it parked while we fix the issues and since anthropic ended the 50% promotion we
> have to be more carefully about our weekly window"*

- DECIDED   LoopEngine-parked  **LoopEngine is left exactly as found.** No manual intervention to
  restaff its stuck reviews, unstick its queue, or otherwise touch `:8000` outside today's existing
  `mode=ro` read. It stays parked until the fixes already in flight (f355, then the F352 operator
  question, then f356–f364) ship through the normal spec loop and, separately, the operator
  restarts it. This extends the day's existing "`:8000` is read, never touched" rule to cover
  LoopEngine's *product* state, not only its database.
- DECIDED   weekly-window-care  **The 50%-off promotion on the Anthropic account this repo's
  autonomous loops and LoopEngine's agents both run under has ended**, so the shared weekly
  rate-limit window is now a real cost/availability constraint rather than a cushioned one. The
  concrete throttling (which sessions moderate usage, and how) is **not yet decided** — asked back
  to the operator in the same session. **Answered 2026-09-15** (section above): routing, metering
  and trimming now; a cap after a week's calibration.

### 2026-09-14 — a day that reads LoopEngine and builds what it finds

**DECIDED 2026-09-13 ~23:05, by the operator, in session**, for the 2026-09-14 day window only. The
operator's words:

> *"I want to change the daily run for tomorrow. I have a project running in hub 8000. I want to
> push the window to 11:00 and from 9 to 11 we're doing a different run. We're going to read every
> conversation, interaction and log running on the project loopengine in the port 8000 in agentweave
> and pick up everything that happened. All the issues and improvements that we can find. The
> development life cicle, the interaction between agents propose the fixes and improvements. For
> each fix then the afternoon window will do a spec loop and implement it. For each imrpovement it
> will just generate a short specification so I can evaluate the improvement. The window will run
> until 19 then."*

- DECIDED   2026-09-14-hours  **09:00–11:00 is a read-only review of LoopEngine on `:8000`, and the
  building half runs 11:00–19:00.** It is delivered as **one** armed day window, 09:00–19:00, whose
  first phase is the review (`day-window.md`, `## O`) and which moves to the building half at 11:00.
  It is not delivered as two windows, because both would own the same tree and cycle branch, and
  the windows must never overlap (`.claude/loops/README.md`, State). Two windows would also need a
  second arming task, which someone has to remember to remove. The hours come from a `DAY WINDOW:`
  line in `DIRECTION.md`'s dated section, which `arm-cycle.ps1` reads and which expires with the
  day.
- DECIDED   2026-09-14-build  **A build day.** This is the first use of `day-window.md`'s
  `## A day that builds`.
  - **Each fix** the review finds is taken through R1, R2 and R3, an adversarial review (`REV`),
    implementation and a drive, then archived by the day window. That covers new findings and
    existing ones the review re-observes on LoopEngine. Higher severity goes first.
  - **Each improvement** gets a short brief the operator evaluates. It is not specced into
    `openspec/changes/`, and it is not built.
  - **A fix that does not finish** stays specced, with no `APPROVED` row. The night builds it only if
    the operator approves it that evening.
- DECIDED   2026-09-14-privacy  **Cite, don't quote.** This repository is public, and the window pushes
  every iteration. Findings and briefs cite run, entry, task and conversation ids, and paraphrase.
  Only AgentWeave's own output is quoted verbatim. LoopEngine's code, task and conversation text, and
  the operator's messages stay out of the repository. Credentials are always redacted. Rejected:
  **quote freely**, and **raw notes kept outside the repository**.
- DECIDED   2026-09-14-plan  **The LoopEngine work replaces the day's plan.** If its queue empties
  before the review page's slot, the window continues with F327's spec loop (R1–R3 only, with no
  build, since this row does not cover F327). Everything else in the plan it replaced is carried to
  2026-09-15 unchanged: the F332 drive, F215's loop, and the access-path exploration. Rejected:
  **replace with no fallback**, and **keep the F332 drive at 09:00**, which would push the review
  later.
- DECIDED   2026-09-14-ui  **A UI fix's bundle is committed only if it is compatible with what `:8000`
  is running.** The bundle must be driven in a browser, and it must need nothing from Python newer
  than the `:8000` process's start time. Otherwise the fix is specced and left for the night, pending
  approval. Rejected: **no UI fixes by day**, and **allow every UI fix**.
- DECIDED   2026-09-14-read  **`:8000` is read, never touched.** Its database is opened only through a
  `mode=ro` SQLite URI. The project's files and transcripts are read, never written, and the Hub's
  API is never called. `arm-cycle.ps1`'s `:8000` limit is narrowed from *"must never be touched"* to
  exactly this exception, and nothing else about `:8000` changes.

### F347, decided 2026-09-13 evening — and `:8000` running this checkout is intended

**DECIDED 2026-09-13 ~22:45, by the operator, in session**, on a RESUME session's recommendations.
Both questions had been raised that afternoon and left unanswered.

- DECIDED   F347  **Option (a): refuse the turn with a sentence that names the repair.** For
  example: *"<project> is a git repository with no commit yet. Make a first commit, and the turn
  will start."* The Hub creates no commit and provisions no orphan branch, which keeps
  `repo_hygiene.py`'s stance that the Hub does not write commits into the operator's repository.
  The sentence is written in `worktrees.py`, which that module's docstring names as the place
  operator-facing sentences are written, and it replaces git's `fatal: invalid reference: HEAD`.
  Rejected: **(b)**, an orphan worktree. The turn would run, but the Hub would then own a branch
  with no shared history with anything the operator later commits, and nothing says how that work
  lands. **Left to R1:** the finding's last sentence, that the refusing pass should not hold the
  operator's own message silently behind a condition only the operator can clear.
- DECIDED   port-8000  **The operator's `:8000` Hub runs this checkout's editable install on
  purpose.** `CLAUDE.md`'s paragraph is rewritten to say so, with the consequences: a committed UI
  bundle reaches the live app on reload, and a restart runs this checkout's migrations on the
  operator's database. Rejected: repointing the shortcut at `agentweave-live` (PyPI 1.1.0, head
  `0081`), which is far behind the database `:8000` now holds. **This does not widen what a window
  may do.** `:8000`'s process, database and credential stay out of bounds, as the 2026-09-08
  trial-key verdict below already says.
- DECIDED   chain  Two items carried for 3 and 6 handoffs are dropped: whether the ledger's *"shape
  of a fix"* lists are labelled as unverified sketches (new ones already are), and `continuity-kit`.

### 2026-09-13 afternoon — F299's 1b handed back, the roadmap widened, and the gate may re-run a flake

**DECIDED 2026-09-13 ~14:20, by the operator, in session.** Each was put with a recommendation, and
the operator took all four recommendations.

- DECIDED   F299-1b  **Option (b): 1b is handed back, and `an-absent-approver-is-not-named` is
  `REJECTED` and archived unbuilt.** This answers the OPERATOR QUESTION at the top of that change's
  `proposal.md`. On `claude` 2.1.269 the run already ends at its first approval-needing call, and
  what it shows is the harness's own true error naming the blocked server. As written, 1b swaps that
  for a turn that survives the refusal, and whose model asks the operator to approve a prompt no
  surface shows. Option (a) repairs the wording, but still leaves a run that cannot write, and pays a
  migration and 24 tasks for it. **The deciding input is F339.** 1b rejected `acceptEdits` on no
  grounds *"by removing the path check entirely"* (1b above, *"Rejected: also drop to
  `acceptEdits`"*). The 2026-09-13 day window reproduced that claim as false on 2.1.269: `acceptEdits`
  confines writes to the workspace, and the harness refuses the rest. A mechanism built on 1b would
  be built on a reason that no longer holds. Rejected: **(a)**, and **1b as written**. The rounds'
  measurements are kept in the archived change's `design.md` and `evidence/`, and they are inputs to
  the question below.
- DECIDED   roadmap  **The second daily spec loop takes release/usability work, and the first keeps
  draining.** Loop 1 drains decided A and B findings, in `DIRECTION.md`'s order. Loop 2 takes the
  work-lands arc of `openspec/explorations/2026-08-30-release-roadmap.md`: **F215 first** (the
  evidence screen, over an API that already works), **then F124** (a loop's work never reaches
  `main`). Neither has a verdict, so R1 for each writes the options into an OPERATOR QUESTION rather
  than choosing one. The operator also takes the recommendation to use AgentWeave day to day **on
  another project**, as the best source of usability findings. This widens `### The scope of the
  drain` below and does not replace it. The reasoning and the capability assessment are in
  `ROADMAP.md` `## 2026-09-13 — the objective widens`. *(An earlier version of this row said the
  `:8000` instance runs PyPI 1.1.0. That was wrong: it runs this checkout's editable install, per
  DEAD-ENDS 2026-09-13. Whether that is intended is the open question, not an update.)*
- DECIDED   gate-rerun  **The day window's merge gate may re-run a failed CI run once, when every
  failure is F292's or F314's signature and nothing else.** The exact rule is in
  `.claude/loops/day-window.md` step 1, condition 3, with the requirement to write nothing until
  `HEAD`'s run concludes. This answers the night's `decisions_for_user` item 4 and the day window's
  item 1 of 2026-09-13. Rejected: **raising F292/F314 into `DIRECTION.md`'s order now**, which is
  still open as a separate priority call; and **accepting about two mornings in five that do not
  land**.
- DONE   merge  `master` was fast-forwarded to `ab7cf72` by the DECIDE session, with the operator's
  agreement, 2026-09-13 14:25. All four gate conditions were re-measured immediately before the
  push. That landed the 2026-09-12 and 2026-09-13 cycles, 54 commits.

**OPEN, not decided: the access path on a harness that blocks MCP (F299, F301, F339, F340), as one
question.** What should a `claude` run do when its harness refuses the Hub's tool server? The four
findings are one mechanism seen from four sides:
- **F299** is a run killed at its first write.
- **F301** is the `cli` path with nothing to answer an approval (1c).
- **F339** is `acceptEdits` confined after all.
- **F340** is grounds that are positive-only and permanent, while `init` reports the server's state
  on every run.

Shapes already on the table, none chosen:
- **(i)** today's behaviour, plus a Hub-authored sentence in place of the harness's two raw lines
  (F340, research candidate 3);
- **(ii)** on refuted grounds, spawn with no approver under `acceptEdits`, so the run can edit inside
  its workspace, and record the harness's `permission_denials`;
- **(iii)** 1b's shape with option (a)'s flag.

(ii) trades the operator's approval of each command for the harness's own workspace check. That
trade is the operator's, per `agent-capability-plane`, and it is the question. It needs an
exploration that lays the shapes against the archived change's measurements before anyone proposes.
`DIRECTION.md` queues that exploration.

### F319 + F320, decided 2026-09-12 afternoon — a refused review leaves nothing behind

**DECIDED 2026-09-12 ~15:30, by the operator, in session.** The session recommended it and the
operator agreed. F319 became severity A that morning (day window D-1, driven live), and F320 was
filed beside it in the same drive. Neither had a verdict.

- DECIDED   F319  **A refused review dispatch leaves the task exactly as it was before the dispatch,
  and the operator is told.** No assignee, status change or transition row survives a refusal,
  whichever refusal it is and whichever path (the route, or the scheduler) reached it.
- DECIDED   F320  **A scheduling pass that abandons a refused queue head moves on to the next
  entry.** Abandonment exists *"so a permanently wrong entry stops wedging the whole queue"*, and
  the pass that abandons it is today the last pass anything makes (`agent_trigger.py:2433`,
  *"There is no tick"*).
- DECIDED   F319+F320  **One change, not two.** Both live in `turn_scheduler.py`'s refusal branch.
  The commit that persists the staging is at `:349`, and the `return` after abandonment is at
  `~:512`. Two proposals would edit the same lines.

**Left to R1, deliberately.** R1 chooses the mechanism: undo the staging on refusal, or ask the
repository-reading refusals (`review_turn.py` commit-present, git-repo, checkout-path) before
`enter_selected_task` stages anything. Neither is decided here. R1 also answers whether the
waiting-reason write at `:349` can keep recording the refusal's words without committing the
staged assignee.

**Why it goes first, ahead of F299.** It breaks the review path the loop and flows use every day,
while F299 needs a harness that blocks MCP servers, which this machine's is not. It is silent: the
board shows an ordinary `Under Review · Idle` card, and the next reviewer is refused by D9. And
the 2026-09-11 night's F306 fix widened it. As the session reads the code and the D-1 log, leg A's
refusal comes from the §3.4 entry-guard fallback added at `4929ea0`, and before that commit the
same sequence ended in a self-review. The fix is right, and it left a stall where the self-review
was.

- DECIDED   F327-scope  **[Superseded 2026-09-24 by `F327-scope-b`.] Option (a): `a-refused-review-leaves-nothing-behind` ships as scoped, and
  F327 stays open.** The operator decided it in session, 2026-09-12 ~19:20, answering R2's OPERATOR
  QUESTION. The change fixes the dispatch's own staging, on the route and the scheduler, and F320.
  A review a flow (or a divergence restaff) staffed *before* its dispatch, and which the dispatch
  then refuses, is **F327 (B)** and waits for its own spec loop. R3 measured that every row of
  F327's table is unchanged on the fixed tree, so the change makes no flow worse. R3 also scoped the
  delta's scenarios so they no longer reach flows. Rejected: **(b)**, moving the flow's staging
  into the dispatch, which is unexamined by any round and, per R3, larger than R2 estimated,
  because the divergence restaff collides with D9. **(c)**, a compensating `under_review ->
  completed` edge, because it leaves transition rows the verdict forbids. **(d)**, exempting flows
  in the main requirement, because it would define the verdict's intent away.

- DECIDED   F354  **Pin the tool server at Hub start (D5 option a), under
  `~/.agentweave/hub/tool-server/<digest>/`** (0700; old digests pruned after 7 idle days), not in
  the shared temp directory. The operator approved it 2026-09-24 (`APPROVALS.md`, B11; review
  `spec-queue/tracks/reviews/B11-2026-09-24.md`). Recorded 2026-09-25 at archive of
  `an-agents-tool-server-is-the-one-its-hub-loaded`.
- DECIDED   F149-D1b  **A `JobRun` id in an event is renamed `run_id` → `job_run_id` outright, with no
  dual emission** (`run-id-in-an-event-always-names-a-run` D1, second half). The operator approved it
  2026-09-24 (`APPROVALS.md`, B2: "the Opus review approved it as it stands"). Recorded 2026-09-25 at
  archive.
- DECIDED   B3-D8  **A flow's own moves carry a recorded cause, not a third actor kind**
  (`a-flows-own-moves-are-recorded-as-the-flows` D8): a manual Run press reads "Loop X moved"; a review
  staged late by a divergence restaff stays "You moved"; old rows are unchanged. Operator, 2026-09-24
  (`spec-queue/tracks/reviews/B3-2026-09-24.md`). Recorded 2026-09-25 at archive.
- DECIDED   B2-D1a  **A `JobRun` row is a dispatch: one agent's share of one firing, not a firing
  itself** (`a-firing-is-counted-once-however-many-agents-it-starts` D1, first half — the same D1
  whose rename half was recorded above as `F149-D1b`). `run_count` counts firings that queued work
  for at least one agent, once per firing regardless of how many agents it started; the per-agent
  increment in `scheduler.py`'s `_stage_selection` is removed. The operator approved it 2026-09-24
  (`APPROVALS.md`, B2: "the Opus review approved it as it stands"), the same approval `F149-D1b`
  cites for the rename half of the identical D1. Recorded 2026-09-28 at this change's
  implementation, closing task 0.3.

### F306 and F312, decided 2026-09-10 evening — and the scope verdict's mechanism, amended

**DECIDED 2026-09-10 ~18:50, by the operator, in session**, after a code exploration of both
findings. These were the last two open severity-A findings with no verdict.

#### F306 — an agent may not review work it recorded evidence for

**DECIDED: repair BOTH defences, and count EVERY evidence row regardless of `review_state`.**

`agents_that_may_have_authored` (`hub/hub/task_transition_service.py:253-283`) unions exactly three
records — transitions, `assignee`, runs bound to the task. A fourth exists and is not a source:
`requirement_evidence.actor`. In the measured run all three legitimate sources were empty, the
ladder got `exclude=set()`, and the agent approved its own work — `under_review → approved`,
`actor_kind='run'`, nothing refused it.

**The function's own docstring decides this**, which is why the verdict is not a close call: *"a
record associating an agent with a task is sufficient to exclude it, and a source's silence is not
evidence that the agent did not work it."* That principle was applied to three of four sources, and
by its own standard the missing one is the **strongest** — the other three are circumstantial
(moved it / holds it / ran about it), while an `implementation` evidence row is the agent asserting
*"this is my implementation of this task"*, carrying the commit the reviewer is handed.

**Both defences, not just the ladder.** `_guard_author_is_not_reviewer` (`:286-311`) compares
`agent_that_completed`, which is `NULL` on an operator completion, so it has nothing to compare and
permits. Repairing only the ladder leaves the **silent** failure standing: a ladder that cannot
staff reports *"no reviewer available"* and the operator sees it; a guard that permits a
self-approval is seen by nobody. The guard falls back to the evidence actors when there is no
completer.

**Every evidence row, not only `ACCEPTED`.** Rejected: filtering on `review_state == ACCEPTED`.
An agent whose evidence was rejected, or whose evidence is still awaiting review, still **authored
the work** — that is what the row records. Filtering by decision would reintroduce the gap one
status value further along, and it would make the exclusion depend on a review outcome that the
review being staffed is supposed to produce.

**The cost, accepted knowingly and already priced by the code:** *"the cost of excluding an agent
that did nothing is a review the flow reports it could not staff, which the operator sees and
resolves; the cost of including an agent that wrote the work is a self-approval nobody sees."* This
verdict buys more of the first to eliminate the second.

**Blast radius, measured before deciding:** two call sites (`scheduler.py:625`, `:1574`) and one
test file (`hub/tests/test_a_flow_names_what_it_cannot_staff.py`). `RequirementEvidence` already
carries `task_id`, `actor` and `actor_kind`, so the fourth source mirrors
`agents_of_runs_bound_to` exactly and needs no migration.

**Open and NOT decided here** — flagged so a round picks it up rather than assuming: **whether the
reviewer ladder picks deterministically** when several agents are eligible. In the measured run the
pool was two and it chose the author. That is unverified either way and is a question for R1.

#### F312 — the workspace posture and URLs

**DECIDED: allow the run's own Hub URL, and deny every other URL with a reason that names network
access rather than the filesystem.** This is option C of three, and it composes with — rather than
replaces — the F300 verdict above.

**What settled it is a measurement, not a preference.** `python -c` reading `os.environ` makes the
**identical** request to the **identical** address and is **allowed** today, because it puts no
absolute path in the command text for `_ABSOLUTE_PATH_RE` to find. So the current behaviour is **not
containment — it is a syntax filter.** It stops the agent that writes a URL plainly and no other,
and it reports that as `'p://127.0.0.1:9/…' is outside your workspace`, sending the model and the
operator to debug a filesystem.

Rejected: **allow all URLs** — honest about what is enforceable at this layer, but it grants shell
egress under the *default* posture, and a porous boundary is not a reason to open it deliberately;
that is a capability decision, and it is not forced by this defect. Rejected: **deny every URL with
a true reason** — zero widening and it does fix the message, but it leaves F300's mandatory-path
failure standing and keeps a filter any `python -c` walks past.

**Not claimed by this verdict:** that egress is now contained. `_decide`'s own docstring says it is
*"a boundary, not a sandbox"*. Actually containing network access needs a different layer entirely
and **is not authorised here**. If the operator later wants real egress control, that is a new
decision and a much larger one.

**F300 and F312 are one change.** Both are edits to the same regex-and-`_decide` path, they must
agree on what a URL is, and shipping either alone leaves the other's message or capability wrong.
Whoever writes R1 writes one proposal covering both.

#### The scope verdict's mechanism — amended

**The 2026-09-10 morning verdict *"drain A and B, ratchet C and D"* cites R-1's model, and R-1's
model cannot express what it was asked to.** A ratchet freezes *a count of one homogeneous,
countable population* — 35 clientless routes, 52 MISREPORT surfaces, 100 unhandled query sites, the
dependency ceilings. The 88 open C, D and unlabelled findings are heterogeneous: there is no single
number, and no check can assert them.

**DECIDED: the citation is dropped and the verdict says what it does — those findings are NOT
PROPOSED AGAINST.** They stay in `scripts/drive/FINDINGS.md` as recorded history. There is no check,
no ceiling, and nothing stopping the population growing, and **that is now stated rather than
implied by a citation that promised otherwise.**

Rejected: **freeze the open C/D count as a ceiling.** It is buildable, but it would go red whenever
a drive files a new low-severity finding — and filing them is behaviour worth keeping, not
suppressing. A gate that punishes honest reporting gets worked around. Rejected: **two named
mechanisms** (ratchet the countable classes, leave the rest unscheduled) — accurate, and rejected as
more structure than the distinction earns now that it is written down plainly.

**The cost is unchanged and stands:** **35 of the 75** low-severity findings read on 2026-09-09 are
named nowhere outside `FINDINGS.md`. Under this verdict *unscheduled* is very close to *forgotten*,
and that was accepted with the wording in front of the operator.

### The access path, re-decided 2026-09-10 — one verdict reached one of its three findings

**DECIDED 2026-09-10, by the operator, in session**, after the three findings were read together
against the spawn path and after a four-shape measurement run for this decision. It **narrows** the
2026-09-09 verdict rather than replacing it, and adds two verdicts that verdict could not reach.

**Why this was re-put.** The 2026-09-09 verdict is titled *"F299 / F300 / F301"* and its mechanism —
teach `_decide` about the run's own Hub address — **can only fire in F300's configuration.** `_decide`
lives behind `approve_tool_call` in `mcp_server.py`, a process spawned only when the Hub emits
`--mcp-config` *and* the harness honours it. F299 is a harness that ignores it; F301 sets
`hub_client: "cli"` so it is never emitted. This is the same class as entry 19 and as `F305`: a
verdict that reads as settled and cannot do what it says.

#### 1a. F300 — the verdict stands, narrowed to this finding

Unchanged and now better evidenced. On `workspace` there **is** an answerer, so `_decide` is the only
thing between the instructed command and the network — measured below, the harness does not refuse
that command shape statically. Teaching `_decide` the run's own Hub base URL makes the instructed
request execute. The 2026-09-09 constraint still binds: **not permissive about URLs in general**, the
run's *own* Hub base URL only.

#### 1b. F299 — no grounds, no approver flag

> **HANDED BACK 2026-09-13 by the operator.** See `### 2026-09-13 afternoon` under `## Decided`. The
> spec loop that took this verdict found that the installed harness no longer behaves as this
> section's drive recorded. Its *"Rejected: also drop to `acceptEdits`"* rests on a claim F339
> reproduced false. This section is kept as history, and is no longer an instruction.

**DECIDED: when there are no grounds that the harness honours MCP, do not emit
`--permission-prompt-tool`.**

The Hub already measures this and already trusts the measurement for a different purpose.
`harness_has_honoured_mcp` (`hub/hub/launchability.py:232`) is a per-agent, positive-only read of
`Run.mcp_adapter_online_at`, and `described_access_path` uses it to choose what a run is **told**. It
does not reach `_build_claude_command`, which decides what a run is **given**. This verdict connects
the two: same signal, same grain, same conservative direction.

**What it changes, exactly.** From the second run of an agent whose adapter has never come online,
the run is spawned without an approver flag naming a tool nothing serves. That is F299's own
**condition C**, which it drove: the model then says *"I need permission to write the file"* instead
of *"contact your system administrator to resolve this."* **The denials are identical.** Nothing is
widened — a flag is removed, not a permission granted.

**What it does not do, stated so nobody expects it.** It does **not** restore the run's ability to
work. On a harness that blocks MCP there may be no posture that gives both containment and
capability, and this verdict does not pretend otherwise; it stops the run lying about whose fault it
is. The remaining trade is `hub_client: "cli"`, and **nothing in the UI says what that costs.**

**Corrects the 2026-09-09 verdict's closing note**, which told whoever specs it that *"the Hub cannot
today detect that a harness blocks MCP."* It cannot detect it **before the first spawn**. From the
second run it demonstrably can, by the mechanism above — which shipped in the same change that filed
these three findings.

**Rejected: also drop to `acceptEdits` on no grounds.** That restores capability by removing the path
check entirely, reversing the 2026-09-09 rejection of the same option. Rejected again for the same
reason: `agent-capability-plane` reserves containment to the operator.

#### 1c. F301 — the `cli` path has no answerer, and that is the whole finding

**DECIDED after measurement, 2026-09-10.** F301 records fifteen attempts and five refusal classes and
attributes four of them to the harness's *static* command analyser, concluding that the notice
instructs a shape the harness refuses outright. **The measurement says otherwise.** Four shapes were
run twice, once under `acceptEdits` headless and once with the approval gate removed
(`testbed/scratch/f301shapes/`, Haiku, every request aimed at `127.0.0.1:9` where nothing listens, so
a connection error proves execution):

| shape | `acceptEdits` headless | approval gate removed | `_decide` |
|---|---|---|---|
| `python -c` reading `os.environ` | denied | **executed** | **allow** |
| PowerShell `curl.exe "$env:HUB_URL/…"` | denied ×4 | **executed** | deny |
| Bash `curl "$HUB_URL/…"` | denied | **executed** | deny |
| **control** — literal URL, no variable | **denied** | **executed** | deny |

**Remove the approval gate and every refusal class disappears.** They are the harness's reasons a
command **needs approval**, not reasons it is forbidden — and on the `cli` path nothing answers, so
needing approval *is* denial. **The control proves it:** a bare literal `curl` with no variable
anywhere is denied identically. F301 is one sentence, not five rows, and
`runner_commands.py:58-60` predicted it on 2026-08-13: *"it still prompts for `Bash`, and headless
there is nothing to answer that prompt either."*

**So F301 needs no containment decision.** It is F299's problem seen on the other path, and it is
closed by telling the truth rather than by widening anything. What it does establish is that the
notice's HTTP branch is **unusable on the `cli` path by construction**, and the notice should stop
implying otherwise.

#### 1d. The remedy for F300 — both, notice first

**DECIDED: change the notice to instruct the `python -c` shape now, and keep 1a's `_decide` fix as
the durable half.**

The measurement found a remedy nobody had considered: **`python -c` reading `os.environ` is the one
shape of the four that `_decide` already allows**, because it puts no absolute path in the command
text for `_ABSOLUTE_PATH_RE` to find. That is a **prose-only** fix — no code, no containment change,
works today on `workspace`.

**Why both and not one.** The notice change is shippable immediately and costs nothing; the `_decide`
change is what makes the plane reachable when an agent improvises a shape rather than following the
notice literally, which is the ordinary case. Rejected: **notice only** (leaves the obvious `curl`
form denied, with the false filesystem reason); **`_decide` only** (correct but needs the full round
discipline before anything improves, and the free half is free).

**Ordering is part of this verdict**: the notice first, because it needs no approver change and is
therefore the smaller and safer of the two.

> **CORRECTED within the hour, 2026-09-10, by checking the carve-out I had just invoked.** The line
> above originally read *"and therefore no proposal round"* — **wrong.** `day-window.md`'s D-6
> carve-out requires that the change *"touches no requirement in `openspec/specs/` — grep the
> capability before believing this."* The notice **is** specified, by
> `agent-capability-plane`'s *"A run whose harness cannot use MCP is told how to reach the plane"*,
> whose scenarios pin what the text must identify — including **how the credential is presented on
> a request**, which is exactly what changing the instructed shape changes. **So the notice change
> needs R1/R2/R3 like anything else**; what it does not need is the approver change. Filed against
> myself rather than left: a verdict that waives the round discipline on a specced capability is the
> same defect as a verdict whose mechanism cannot fire, one paragraph later.

**And the requirement itself now carries a false mechanism**, inherited from F301 and shipped into
the corpus on 2026-09-09: *"the `cli` path's `acceptEdits` has no approver to overrule a harness that
**statically refuses** an interpolated credential (F301)."* The measurement in 1c says the harness
does not statically refuse it — with the approval gate removed, that exact command executes. The
requirement's **conclusion** holds (unreachable on `cli`, and for the reason the sentence's first
half gives), so this is a wording repair, not a reopened requirement. It must be corrected in the
same delta that carries the notice change, and **not by the day window on its own** — the corpus is
openspec's and a spec edit is the spec loop's.

#### 1e. The general form is a new finding, not part of any of these

The control row denies a plain `curl http://127.0.0.1:9/...` under the repo's **default** posture,
with the reason `'p://127.0.0.1:9/…' is outside your workspace` — `_ABSOLUTE_PATH_RE` eating the URL
scheme. **No agent on the default posture can make any network request from a shell command, and is
told a filesystem reason for it.** `pip install` from a URL, `gh api`, fetching a schema: all denied
the same way.

**DECIDED: file it as a new severity-A finding.** It is a capability hole in the product's default,
measured, with a one-line reproduction, and it lands inside the A+B scope decided this morning.
Rejected: **folding it into F300** (risks the general claim being closed when F300's narrow fix
ships — and 1a's verdict explicitly forbids general URL permissiveness, so F300's fix *cannot* close
it); **filing it as B**; **not filing** on the grounds that denying egress is intended — the posture
may well be entitled to forbid egress, but it is not entitled to forbid it by accident and report it
as a filesystem escape.

### The scope of the drain — A and B are drained, C and D are ratcheted

**DECIDED 2026-09-10, by the operator, in session**, on the finding-shaped arithmetic in
`ROADMAP.md` `## Honest arithmetic`. This is the first verdict in this file about **how much of the
ledger is in scope at all**, and it governs where every day window points its proposals from now on.

**DECIDED: drain severity A and severity B. Ratchet C, D and the unlabelled under R-1's model.**

> **AMENDED the same evening, 2026-09-10 — the second sentence's mechanism was wrong and is
> withdrawn.** R-1's model freezes *a count of one homogeneous population*; the 88 open C, D and
> unlabelled findings have no such number and no check can assert them. **Read that clause as: those
> findings are not proposed against, and stay in `FINDINGS.md` as recorded history.** There is no
> ceiling and nothing stops the population growing. The first sentence — drain A and B — is
> unaffected and is what this verdict is for. Full reasoning and the two rejected alternatives are
> in `### F306 and F312, decided 2026-09-10 evening`, above.

As measured 2026-09-10 by `py -3.11 scripts/classify_findings.py` — **run it again rather than
quoting these; they move daily** — the ledger holds **308 sections, 147 open**: 4 A, 59 B, 68 C,
14 D, 2 unlabelled, plus 8 in `CONFLICT`.

> **The counts below moved twice the same day; the verdict did not.** By late morning the ledger
> read **313 sections, 157 open** — 6 A, 63 B, 72 C, 14 D, 2 unlabelled — so *in scope* is **69**
> and *ratcheted* is **88**. Three of the seven new ones were filed that morning; the rest moved
> because `dee508c` **repaired the classifier**, which re-bucketed the ledger and returned
> `UNCLASSIFIED` to 5. **This verdict is severity-based, not count-based** — it says *A and B are
> drained, C and D are ratcheted* — so a moving census resizes the work it implies and changes
> nothing about the decision. The figures above are kept as they stood when it was made.

- **In scope: the 63 open A and B findings.** At the measured rate of one proposal per day window,
  ~9 weeks of unbroken daily cycles. Proposals come from this population and from nowhere else.
- **Out of scope: the 84 open C, D and unlabelled findings.** They get **R-1's already-decided
  treatment** (`### R-1 — Enforce, as a ratchet`, 2026-09-08): freeze today's count as a ceiling that
  may shrink and may never grow. **Existing instances are not repaired before the check may pass.**

**Why this option.** It is the only one of the three that reuses a decision already made rather than
inventing a second policy for the same problem. R-1 settled *conventions are enforced, instances are
not repaired* for the ratchet checks; the low-severity tail is the same question at a larger scale,
and answering it differently would leave the repo with two philosophies about the same ledger.

**The cost, taken knowingly and stated so nobody rediscovers it as a surprise:** those 84 findings
stay wrong, with a passing check blessing them, until something touches them on its own merits. **35
of the 75 read on 2026-09-09 are named nowhere outside `FINDINGS.md`** — for those the ledger is the
only copy, so ratcheting them is the point at which they stop being tracked work and become recorded
history. That is the trade; it was not made by accident.

**Rejected: drain everything open.** ~5 months of daily cycles, and dishonest unless the source term
is accepted — Stage 2 closed two severity-A findings and filed three more, a **net drain of minus
one**. A five-month plan whose input grows as it runs is not a plan.

**Rejected: drain A, then re-measure.** Cheapest, and it defers the same question by about a week
while the day windows keep proposing from wherever the ledger happens to be read from.

**What this does not decide.** ~~It does not schedule the ratchet checks — those are still Stage 6
work with no owner~~ — **corrected 2026-09-10: all three were built on the night of 2026-09-09**
(`6484de4`, `hub/tests/test_surface_ceilings.py` and `test_dependency_ceilings.py`). It does not
touch the `CONFLICT` findings, which need a hand read regardless of severity. And it does
not re-open the drain gate's own rule: `.claude/loops/day-window.md` step 6 still governs *whether*
a day proposes, while this verdict governs *what from*.

> **OPEN — raised 2026-09-10, after the verdict, and it is about this verdict's own mechanism.**
> **"Ratchet C and D" cites R-1's model, and R-1's model cannot carry these 88 findings.** A ratchet
> freezes *a count of one homogeneous, countable population* — 35 clientless routes, 52 MISREPORT
> surfaces, 100 unhandled query sites, the dependency ceilings. Each is a single number that may
> shrink and may never grow. **The 88 open C, D and unlabelled findings are heterogeneous**: there is
> no one number to freeze, and no check can assert them.
>
> So as built, this verdict means **"stop scheduling them"**, not **"hold a line under them"**. Those
> are different promises and only the first is currently kept. It may well be the one intended — but
> the verdict cites R-1, and R-1 promises the second. **The operator should say which**, because the
> difference decides whether anything at all stops that population growing. The cost noted above
> lands harder under the first reading: **35 of the 75 read on 2026-09-09 are named nowhere outside
> `FINDINGS.md`**, so "unscheduled" is very close to "forgotten".

> **FOOTNOTE — DECIDED 2026-09-22 by the operator, in session:** *"the draining of the others is
> manual execution guided by me."* The C and D findings are no longer only recorded history: they
> are drained, but **only by interactive sessions the operator directs**, following
> `spec-queue/ROUNDS.md`. **For the unattended windows nothing changes.** The FILL window still
> proposes from A and B alone, and the FIX window builds only what `APPROVALS.md` names. A C or D
> finding reaches a window only if the operator puts it into an ORDER by name. This also answers the
> OPEN note above in practice: what stops the C/D population being forgotten is the operator-guided
> rounds, not a ratchet.

### The day window's two, 2026-09-09 evening — and one it asked that was already answered

**DECIDED 2026-09-09 ~17:45, by the operator, in session**, from
`spec-queue/review/review-2026-09-09.html`. That page raised three decisions. **`DAY-3` was not
one** — it is the `F299` posture question the operator answered at **08:51 the same morning**,
recorded in the section below, and re-published as open at 10:55. Filed as **`F305` (B, harness)**:
the windows carry `decisions_for_user` in their `STATE-*.json` and nothing reconciles it against
this file, so an answered question is re-asked indefinitely. **The verdict below stands and needs no
restating** — the earlier section is the authority for it.

#### DAY-1 — a dev constraints file, not a pin

**DECIDED: keep `hub/pyproject.toml`'s published range as it is, and add a development
constraints file pinned to CI's resolution.**

The problem measured today: `hub/pyproject.toml` constrains only `starlette<2.0` and
`fastapi>=0.110`, so CI resolved **starlette 1.6.0 / fastapi 0.141.1** against this machine's
**0.52.1 / 0.136.3**. `{r.path for r in create_app().routes}` yields **161 paths here and 7 on CI**
— which is why a test that could never pass on CI and never fail locally survived **thirteen
commits**.

**Why this option.** It is the only one that keeps both halves. Local and CI agree, so this class of
failure reproduces before a push; and the published range stays loose, so upstream incompatibilities
still surface early — which is exactly what happened today and is worth keeping. Rejected: **pinning
`pyproject.toml`**, which buys agreement by freezing the Hub on a version and converting upstream
drift into an upgrade nobody is prompted to do; and **changing nothing**, which leaves any test that
reads a framework data structure unverifiable locally by default.

**Two constraints on whoever builds it.** The constraints file is **not** a second source of truth
for what the Hub supports — `pyproject.toml` remains that, and the file must be documented as
development-only. And it is worth nothing if it is not used: the CI job and `CLAUDE.md`'s documented
local commands must both install through it, or local and CI drift apart again silently, which is
the whole defect.

**This does not close the related gap, deliberately.** The review page records that there is still
**no guard against a fourth occurrence** of the `app.routes` mistake — a grep-based test would
false-positive on the three files whose comments document the trap, `_routing.py` included. That is
unbuilt and unowned, and this verdict does not cover it.

#### DAY-2 / F302 — the notice stops asserting, and does not start trusting

**DECIDED: drop the `no MCP tools this turn` sentence. Do not give a fresh agent the MCP rendering
on trust.**

The requirement the notice shipped against asks only that the HTTP form be described and that tools
not be claimed. **It never asked for the denial** — that sentence is a positive claim about the
run's tool list, made on no evidence, and it is false: a probe agent called
`mcp__agentweave__create_task` on exactly the turn it was told it had nothing, and the row exists.

**Why not the other direction.** Granting the MCP rendering on trust asserts *presence* with no
observable ground — the same disease pointed the other way — and would be wrong on precisely the
harness the notice exists for. Describing without claiming is the only branch that states nothing it
cannot know.

**What makes this cheaper than it was this morning.** The `F299` verdict below has the workspace
approver learn to recognise the run's own Hub URL, so the HTTP form the notice steers a fresh agent
toward is one the agent can actually use. Before that verdict, removing the denial would have left
a first turn pointed at a path `F300`/`F301` measured it could not take.

Rejected: leaving it. It is bounded — one turn per agent, healing on the second, with
`hub_client: "mcp"` fixing turn 1 today — but it is a falsehood in the first thing every new agent
is told, and the fix is a wording change inside a requirement that never asked for the words.

### Four verdicts, 2026-09-09 morning — and three of them are second answers

**DECIDED 2026-09-09 ~08:55, by the operator, in session**, on a RESUME session's reading of the
night window's result and of the verification pass immediately below.

**Three of these four had already been decided once.** Each was re-put because checking the verdict
against the code found something the verdict did not know — which is the verification pass working
as designed, and the reason a decided-but-unbuilt item is not the same as a closed one.

#### 1. ~~F299 / F300 / F301~~ **F300 only** — the workspace approver learns to recognise a URL

> **NARROWED 2026-09-10, by the operator.** This verdict is correct and stays — **for F300 alone.**
> It **cannot fire for F299 or F301**, because in both of those configurations the MCP server that
> hosts `_decide` never starts: `_decide` is reachable only through `approve_tool_call`, an
> `@mcp.tool()` in `mcp_server.py`, which is spawned only when `_build_claude_command` emits
> `--mcp-config` *and* the harness honours it (`runner_commands.py:236-241`). F299 is a harness that
> ignores the flag; F301 sets `hub_client: "cli"`, so the flag is never emitted at all. Teaching a
> function about URLs does nothing in a process that does not exist. **The title carried three
> finding numbers and the mechanism reached one.** See `### The access path, re-decided 2026-09-10`
> for F299's and F301's own verdicts, and for a measurement that corrects this one's closing note.

**DECIDED: teach `_decide` that the run's own Hub address is not a filesystem path.** Raised by the
night window at iteration 12 and **enlarged the same night** by the `c2-verify` drives, which
established there is **no posture on this machine on which a `claude` run can use the HTTP form of
the capability plane under its own power.**

The mechanism, verified in code this morning: `_ABSOLUTE_PATH_RE` (`hub/hub/mcp_server.py:936`)
matches `(?:[A-Za-z]:[\\/]|/)[^\s"'|;&><)]*`, so the `//127.0.0.1:8010/...` inside a URL is captured
as an absolute path, checked against the run's workspace, and denied for being outside it. That is
why `hub_client: "cli"` — documented at `src/agentweave/config.py:714` as *"uncomment if MCP is
blocked by company policy"* — **restores writes and not access.**

**Why this option and not the other two.** It is the only one that widens nothing: filesystem
containment is untouched, and what changes is a *misclassification*, not a policy. The rejected
alternatives, both defensible:

- **Fall back to `acceptEdits` when the plane is unreachable.** It has a rationale already in the
  code — `DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER = "acceptEdits"`
  (`hub/hub/runner_commands.py:73`), whose comment says naming an absent approver *"would refuse
  everything, which is precisely the failure `acceptEdits` was introduced to end."* Rejected because
  `acceptEdits` **has no path check at all**, so it answers a reachability problem by widening
  filesystem containment, and `agent-capability-plane` reserves containment to the operator.
- **Leave the posture and document the workaround.** Rejected: it leaves F299 open and still gives
  the run no way to reach the plane.

**What the implementing change must not do:** it must not make the approver permissive about URLs in
general. The recognised case is the run's *own* Hub base URL, which the Hub knows because it minted
the run's credential. Anything broader is a second decision and is not covered by this verdict.

**Note for whoever specs it.** The Hub cannot today detect that a harness blocks MCP — the config
declares MCP available and the code believes it. This verdict deliberately does **not** ask for that
detection; it makes the declared-and-blocked case survivable instead.

#### 2. Entry 19 — re-decided, narrowed to the hazard that still exists

**DECIDED: refuse to start when no profile is named, not when a relative default is used.** The
original verdict (2026-09-08) was taken against a world repaired by `44a1ae5` on **2026-08-17** —
`_default_database_url()` has been absolute for three weeks and `hub/data/` does not exist. See the
verification pass below for the full evidence.

What survives: a bare `uvicorn hub.main:app` with **`DATABASE_URL` unset** still opens
`~/.agentweave/hub/data/agentweave.db` rather than the profile database everything else uses. Fixed,
not cwd-dependent, so it can no longer produce a different database per launch directory — a much
smaller defect, and still one that has cost time. `CLAUDE.md` already treats a reappearing
`hub/data/` as *"a symptom, not a database to preserve"*, which is this defect leaving a trace.

**The binding constraint on any implementation:** `CLAUDE.md`'s own documented trial-Hub start
command **is** a bare `uvicorn hub.main:app` from `hub/`, with `DATABASE_URL` set explicitly. The
refusal must key on the variable being unset and must leave that command working. A change that
breaks the documented start command has implemented the retired verdict, not this one.

#### 3. `PATCH /queue/settings` — move the reschedule into the PUT, then remove the route

**DECIDED: close the gap first, then delete.** The 2026-09-08 verdict said *remove*; the
verification pass found the route also re-schedules every queued agent (`inbound_queue.py:104-107`),
and `schedule_agent` appears **0 times** in `projects.py`. So `PUT /projects/{id}/settings` writes
the same four columns and **does not reschedule** — a real gap that exists today, independent of
this route and independent of whether it is removed.

Order matters and is part of the verdict: **the reschedule moves into the PUT before the route
goes.** Removing first and porting later leaves a window in which neither path reschedules.

Rejected: dropping route and side effect together. It is defensible — the UI never calls the route,
confirmed independently by `n10`'s no-client-anywhere list — but it would delete a behaviour the
surviving endpoint lacks, and the operator's standing preference is the cleanest design rather than
the least work.

#### 4. The overseer artifacts — the logs stay, the OV review page goes

**DECIDED: keep `.claude/autonomous/2026-09-07-overseer-log.md` and `STATE-overseer.json`; delete
`2026-09-07-sidequest-review.html`.** Raised on 2026-09-08 and unanswered until now.

The split is by *subject*, not by file type. The overseer log and its state are records of a window
run of **this** repository's own loop, the same class as the day and night logs that stay tracked.
The sidequest review page is `OV-` content, and the `OV-` series left this repo on 2026-09-08 under
*"I want only things for agentweave here in this repo."*

### Verification pass, 2026-09-08 — do the 2026-09-08 verdicts still hold?

At the operator's instruction, *"review all of those works to make sure they still hold."* Every
decided-but-unbuilt item re-checked **against the code**, not against the entry that describes it.
**Seven of eight hold. One was decided on a premise that had already been repaired three weeks
earlier.**

| Item | Verdict | Evidence |
|---|---|---|
| **R-3.1 — F209's `reason`** | **HOLDS, exactly** | `spec.py:615 accept_proposal_route` passes `expected_digest=` and **no `reason=`**; `reject_proposal_route` at `:665` passes `reason=body.reason`. Both take the same body carrying `reason: str = Field(default="", max_length=2000)` (`:607`). |
| **R-3.2 — remove `PATCH /queue/settings`** | **HOLDS, with one thing the verdict missed** | Route is real at `inbound_queue.py:81`, writes exactly the four columns (`hop_budget`, `turn_delivery_cap`, `agent_budget`, `allow_agent_jobs`) that `ProjectSettingsUpdate` (`projects.py:76-80`) also owns, and **the UI never calls it** — independently confirmed by `n10`, which lists `/queue/settings` under *no client anywhere*. **But it also re-schedules every queued agent** (`schedule_agent` per queued agent, `:105-108`), and `schedule_agent` appears **0 times** in `projects.py`. Removing the route deletes that side effect. It is already unreachable from the UI, so nothing an operator does today depends on it — but an agent or script calling the route would notice. **Either drop it knowingly or move the reschedule into the PUT; do not remove it without deciding which.** |
| **R-3.3 — entry 19, bare `uvicorn` must refuse to start** | **PREMISE IS STALE** | See below. |
| **R-3.4 — entry 21, the model catalog** | **HOLDS** | `model_catalog.py` contains **no runtime read** of `~/.codex/models_cache.json` — the only mention is in the module docstring (`:34`), describing how the literal was *derived*. It is a compile-time literal, as F267 says. The cache file exists and was last written **2026-08-29**, ten days ago. Nothing re-checks it. |
| **R-2 — archive collision check** | **HOLDS — not built** | No script, no skill hook. Its recorded weakness (it only fires if whoever archives remembers to run it) is unchanged. |
| **R-1a — route reachability ceiling 35** | **REPRODUCES EXACTLY** | Re-run 2026-09-08: **187** declared `/api/v1` route+method pairs, **35** with no client anywhere. |
| **R-1b — query error surface ceiling 51** | **REPRODUCES EXACTLY** | Re-run 2026-09-08: 54 MISREPORT total, **51 on a surface an operator can reach** (12 an empty picker, 39 a sentence/number/terminal skeleton). |
| **R-1c — dependency ceilings** | **HOLDS** | Exactly **three** `fastmcp>=2.0,<4` declarations — `pyproject.toml:47`, `pyproject.toml:71`, `hub/pyproject.toml:24` — and `starlette<2.0` at `hub/pyproject.toml:32`. The count the check would freeze is correct. |

**Entry 19 is the one that did not survive, and it is the day's pattern again.** The verdict asks
whether a bare `uvicorn hub.main:app` from `hub/` should refuse to start *"on the relative default
rather than silently opening a second database beside the one everything else uses."*
**There is no relative default.** `_default_database_url()` (`hub/hub/config.py:9-17`) returns
`Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"` — absolute, and its own docstring
says *"Same absolute, home-relative path native mode (cli.py's HUB_DIR) already computes."* It was
fixed by **`44a1ae5`, 2026-08-17** — *"fix config.py's database_url default (D1)"* — **three weeks
before the decision was taken.** `hub/data/` does not exist on disk.

**What survives of it, narrowed.** The default is still not the *trial profile* database
(`~/.agentweave/hub/profiles/trial/agentweave.db`), so a bare `uvicorn` without `DATABASE_URL` still
opens a database nobody meant — but a **fixed** one, not a cwd-dependent one, so it can no longer
produce a different database per launch directory. That is a much smaller defect than the verdict
describes. **And any refusal must not break `CLAUDE.md`'s own documented trial-Hub start command,
which is a bare `uvicorn hub.main:app` from `hub/` with `DATABASE_URL` set explicitly.** Re-decide
the narrowed question or drop it; do not build the verdict as written.

**The two overseer items that were in this list are gone from this repo**, along with the rest of
the `OV-` series — they were decisions about a separate repository. Their verification finding
travelled with them to `witness/DECISIONS.md`: that work is **reconciliation, not implementation**,
because the code there predates the verdicts. Nothing about it is AgentWeave's to schedule.

### Trial-profile key rotation — the loop may do it itself

**DECIDED 2026-09-08 ~09:55, by the operator, in session.** The day window raised this on
2026-09-08 (`decisions_for_user` entry `day1`) and rotating the one disclosed key closed the
*instance* without closing the *policy*. Asked as a standing rule for the next one.

**Operator's words:** *"No problem with keys on trial hubs I regularly destroy and create new
ones."*

**So: an unattended window may rotate a trial-profile Hub key without asking, and need not stop or
raise a decision to do it.** The reasoning is the operator's own and is about what the credential
protects: trial profiles are destroyed and recreated as a matter of routine, so a trial key
guards nothing durable and the cost of a rotation is a file rewrite.

**The boundary this does not move.** The `live` profile on port 8000 is the operator's real usage
(`C:\Users\huida\agentweave-live`), and nothing here authorises a window to touch its credential,
its database or its process. This decision is scoped to *trial* profiles by its own wording.

Rejected: *every rotation is the operator's* — it re-raises the same block on each disclosure and
costs a window to answer something the operator has now said they do not care about at this scope.
Also rejected: *rotate, then surface it as a decision anyway* — that is the same interruption with
extra steps, and the operator's answer was that there is no problem to surface.

**Supersedes** the open half of `day1`. That entry is now closed in both halves.

### Delete the merged remote branches — done

**DECIDED 2026-09-08 ~09:55, by the operator, in session** (*"Delete the 13 merged"*), and executed
the same minute. **The count was 12, not 13** — re-measured with `git branch -r --merged master`
after a `--prune` fetch; one of 0116's 13 had already gone. Deleted, with their tips recorded in the
commit message so any of them can be resurrected by SHA:

`2026-08-24-stress-test-remediation` `bef90ff` · `2026-08-26-drive-everything-and-fix-it` `3c3e851` ·
`2026-08-27-fix-and-drive` `25469ac` · `2026-08-27-the-rest-of-the-work` `4f5db93` ·
`2026-08-30-decided-work-and-drive` `0d3974c` · `2026-08-31-the-flow-lands-its-work` `1b46110` ·
`2026-08-31-the-turn-must-end-first` `a4b2833` · `2026-09-04-daily` `9fd9853` · `2026-09-07-daily`
`3c918b9` · `2026-09-07-sidequest` `c54b2d2` · `fix/2026-08-23-design-audit-remediation` `969b7b9` ·
`panel-shell/2026-08-18-tab-store` `8d52a93`

**Kept:** `autonomous/2026-08-19-project-portability` and `autonomous/2026-08-27-build-everything-decided`
(both genuinely unmerged and carrying work `master` does not have), and
`autonomous/2026-09-08-daily`, which is today's live cycle branch.

### F140 + F142 — split them; the decision they were waiting for did not exist

**DECIDED 2026-09-08 01:50, by the operator, in session**, after the code was measured rather than
the plan re-read. `ROADMAP.md` Stage 4 held these as *"one decision, not two"* — F142 changes which
of F140's two defensible repairs is worth building — and both as blocked on the operator.

**Neither was.** F140's repair 1 shipped `1b4c730` (2026-08-30) and was **driven live 2026-08-31**,
before the choice was ever put to anyone: both Haiku agents made the `update_task(...,
status="completed")` call unprompted, both tasks reached `approved`, both commits verified ancestors
of `master`. `_briefing_completion_lines` is byte-identical to the driven version. That makes F142's
"which repair" premise moot, and the coupling with it.

**The decision taken: treat them separately, because their evidence differs.** F140 **retired** on
the 2026-08-31 drive. F142 **stays open** with its reason narrowed from *awaiting an operator
decision* to *awaiting a drive* — its fix shipped `f3a778f` (2026-08-31) and its own change document
says group 7 was *"written, compiled, and not driven"*, deferred to `DRIVE-1`, which has not
happened. One drive closes it: `t_row12_review_leg.py` with `AW_COMPLETE_BY=operator`, plus its
uncovered row four.

**Rejected: retire all four on the shipped code.** It would have taken the severity-A count from six
to two in one move, and it would have retired an A on *the tests pass* — the failure mode this
repository is worst at, and the reason the 2026-09-03 banners exist at all. **Also rejected:
re-drive F140 too.** A drive of byte-identical code buys nothing that the 2026-08-31 run has not
already bought.

**Settles nothing about F154 and F155.** They carry the same 2026-09-03 banner and have **not** been
re-checked the way F140 was. Do that search before believing them.

**Also corrected, not decided: F14 and F60.** Stage 4 listed F60 as blocked on F14's *"undecided fix
shape"*. Both are `FIXED 2026-08-30`, shipped together in `a-task-waits-while-its-run-waits`, and
`FINDINGS.md` had said so for nine days. Verified in code this session. No decision was needed and
none was taken.

---

### day1 — the disclosed key is rotated; the general question is still unanswered

**CLOSED 2026-09-08 09:20 by the operator, in session: *"forget that key. It's rotated as well."***
Raised by the day window at iteration 1 this morning, and it did not block anything — the window had
already carved ROADMAP 6.3 out of its queue rather than waiting.

**What the window actually asked is broader than the key, and remains open:** *"Say whether the loop
may rotate trial-profile keys itself, or whether every rotation is yours."* Its reasoning was sound
and is worth keeping — rotating a credential invalidates whatever still holds the old one, and the
holder most likely to matter is the operator's live instance on port 8000, which every unattended
window is forbidden to touch. **This closure answers the instance, not the policy.** If a window
meets another disclosed credential it will ask again, correctly.

**Residual, recorded rather than reopened.** 18 real-shaped 32-character `aw_live_` literals survive
in **16 tracked files** — `hub/.env.example`, `hub/hub/db/engine.py`, two under `hub/tests/`, eight
drive harnesses under `scripts/drive/`, and four documents including `FINDINGS.md` itself. Every one
is dead against a rotated key. Classified by shape, without any value being printed or quoted.

**The point of noting it is the practice, not these strings.** A rotation is final only if nothing
commits a live key again, and this repository has produced the situation twice — the disclosed key
in public history, and the two trial-Hub keys that rode the tracked half of `.claude/handoffs/`
until 2026-09-04, which is why that directory is now ignored in full. Drive harnesses reading a key
from the environment rather than carrying a literal would remove the largest bucket of the sixteen.
**Not queued** — it is a hygiene sweep nobody has asked for, and it is worth exactly one decision
from the operator before anyone spends a window on it.

---

### R-3 — the four small product calls, all four answered

**DECIDED 2026-09-08 02:15, by the operator, in session.** Each was one question with two defensible
answers, open since 2026-09-01. **None is implemented** — these are verdicts, and the work is
ordinary product work that still has to be queued.

- **F209 — thread the `reason` through.** `accept` declares a 2000-character `reason` and stores
  nothing while `reject`, three functions away, keeps it. Storing it makes the pair symmetric, and
  an accepted-with-reasons record is what an operator wants when re-reading why evidence was let
  through. Rejected: deleting the field, which would leave `accept` the only decision in the pair
  with no recorded rationale.
- **F196 + F198 — remove `PATCH /queue/settings`.** It writes four columns
  `PUT /projects/{id}/settings` already owns, with a weaker contract on both ends, and the UI never
  calls it. One owner for those columns. **Check for external callers before deleting** — the UI
  not calling it is not the same as nothing calling it.
- **Entry 19 — a bare `uvicorn hub.main:app` from `hub/` must refuse to start.** No `DATABASE_URL`
  and no named profile currently falls through to `config.py`'s relative default and silently opens
  a second database beside the one everything else uses; it has cost time twice, and `hub/data/`
  reappearing is the documented symptom. Exit with a message naming the candidates instead.
  Rejected: warn-and-start, which leaves the divergence possible.
- **Entry 21 — a `scripts/` tool, not a test.** `model_catalog.py` names
  `~/.codex/models_cache.json` as its source of truth, nothing re-checks it, and it has drifted. A
  command that diffs catalog against cache has nothing to skip in CI and is the shape that actually
  gets run when someone suspects the catalog is wrong. Rejected: a skip-if-missing test, which is
  invisible in CI — exactly where a green suite would most misleadingly bless a drifted catalog.

**Note the shape of entry 19's answer against `R-1`.** Refusing to start is an *enforcement* call,
consistent with R-1's ratchet decision of the same week, and it is the only one of these four that
changes whether a command works. It is also the one whose blast radius is any script relying on the
default — find those before building it.

---

### R-2 — a repo script

**DECIDED 2026-09-08 02:15, by the operator, in session.** Open since 2026-09-01. A collision check
under `scripts/`, run before archiving: applying a delta warns about nothing when two changes both
carry a `## MODIFIED` block for the same requirement, and archiving the second **reverted the
first**, dropping a qualification that had just landed. One collision in a batch of seven, and two
changes in flight against one requirement is not rare here.

**The known weakness of this answer, recorded because it will be the next finding if it bites.** A
script only fires if whoever archives remembers to run it — which is the same weakness the missing
check already had. Rejected alternatives that do not share it: the `openspec-archive-change` skill
(fires for every window and session following the documented path, but does nothing for a bare
`openspec archive`) and upstream openspec (the correct home, since the tool applying the delta is
the only thing that sees both blocks, but on someone else's release cycle). **If the script is
written and then not run, that is evidence for moving it into the skill, not for writing a second
script.**

---

### The `OV-` overseer decisions — MOVED OUT of this repository, 2026-09-08

**All six `OV-` verdicts now live in `C:\Users\huida\Documents\projects\witness\DECISIONS.md`.**
Moved at the operator's instruction — *"take all of those OVs ones out of this repo and leave at
that other one. That is separate work"*, and *"I want only things for agentweave here in this
repo."*

They were operator decisions about **`witness`**, a separate sibling repository, and were recorded
here only because the spec loop that raised them ran in this checkout. Five are answered (OV-1 yes,
OV-2 redact at write, OV-3 split out, OV-4 the operator only, OV-6 a command); **OV-5, the name
collision check, is still open** and is tracked there now, not here.

**One outcome of OV-3 did land in this repository and stays**, because it is AgentWeave's:
`scripts/snapshot-corpus.ps1` and the `ClaudeCorpusSnapshot` scheduled task. The retention half was
deliberately moved *outside* Witness to a plain file copy, which is why OV-6 and OV-3 were split
rather than chosen between.

---

### F295 task 1.6 — left to the night window, deliberately

**DECIDED 2026-09-08 02:05, by the operator, in session: no override.** The `close_detached` gap —
write the two-line listener so the delta's *"every path"* is literally true, or narrow the
requirement to the paths the pool dispatches `close` for — was offered and declined in favour of
letting tonight's FIX window choose. The task states both options with the measurement attached
(`grep -rn "\.detach()" hub/hub/` returns nothing; a probe's `close_detached` counter fired zero
times), and `APPROVALS.md` records that either satisfies the approval.

**Recorded so tomorrow reads this as a choice, not an oversight.** Check what the window picked; if
it wrote the listener, confirm it carried the deliberately-unreachable comment task 1.6 asks for.

---

### The day window stops proposing while the night is behind — a self-releasing gate

**DECIDED 2026-09-08 01:40, by the operator, in session.** Changes a **standing default**, not one
day's queue: `.claude/loops/day-window.md` step 6 now counts unbuilt specced changes before it
composes anything, and at **2 or more there is no spec loop** — no D-2/D-3/D-4, no new proposal.
At 0 or 1 the spec loop runs as it always has.

**The arithmetic it exists for.** FILL writes one change a day; FIX builds one per one-to-two
nights. Those rates diverge, and by 2026-09-08 the divergence was four fully specced changes, three
rounds each, **129 tasks with two ticked, neither an implementation.** Stage 0.1 of `ROADMAP.md`
cancelled the mismatch for 2026-09-08 with a dated `DIRECTION.md` section; that fix expired at
midnight and reverted the window to proposing.

**Rejected alternative: date a `DIRECTION.md` section per day through the drain.** It keeps the
default intact and is reversible per day, but every day nobody remembers to write one silently
reverts to proposing — the failure mode is invisible and the cost is a day. The gate needs no
operator action in either direction and releases itself when the nights catch up.

A dated `DIRECTION.md` section still overrides the gate **both ways**; that file outranks the
playbook, as it always has.

---

### R-1 — Enforce, as a ratchet

**DECIDED 2026-09-08 00:30, by the operator, in session.** Written up in full at `### R-1` above,
which stays where it is because its evidence is the justification for the three frozen ceilings.

In one line: **the repo writes a check, and the check freezes today's count as a ceiling that may
shrink and may never grow.** Existing instances are not repaired before the check may pass. Three
checks authorised — route reachability (ceiling 35), query error surface (ceiling 51), dependency
ceilings agree — all three promoting scripts that already exist. Scheduled as Stage 6 of
`ROADMAP.md`, behind the four approved changes and the F292 instrument repair.

Settles the old **D-2** and answers **D-6(b)** *no*. Does **not** settle F190's payload-ordering
rule; that needs a way to enumerate payload-shaped consumers, and nothing does that today.

---

### D-1 — Ratify or widen the `fastmcp <4` bound

**DECIDED 2026-09-01 — RATIFIED by the operator, in session.** The bound stands as taken. Absorbs entries 17, 31. Severity: low, reversible in one line.

FastMCP 4.0.0 reached PyPI 2026-08-31T18:20:31Z. This repo declared `fastmcp>=2.0` **unbounded** in
three places, and CI resolves fresh with no lockfile — so CI and this machine had already diverged
on the process that starts every agent turn (`pip index versions fastmcp`: LATEST 4.0.0, INSTALLED
3.1.0). The night bounded it to `>=2.0,<4` unattended and added
`hub/tests/test_fastmcp_api_contract.py` (6 tests, verified passing again 2026-09-01 08:09).

**Nothing was measured broken.** The research probed all four FastMCP APIs `mcp_server.py` uses
against 4.0.0 and all four survive. The bound was taken because v4 additionally pulls
`pydantic>=2.12`, `FastAPI>=0.133.0` and `httpx2` — a transitive set this suite has never run
against.

**Recommendation: ratify.** The cost of the bound is a deliberate upgrade later; the cost of no
bound is an unannounced major crossing under the agent runtime. If you widen it instead, run the
contract test first and read what it says.

**Coupling:** fastmcp 4 requires `FastAPI>=0.133.0`. The old D-2 tracked that; it is now part
of **R-1**, since `fastmcp<4` and `starlette<2.0` are the same unwritten rule applied twice.

---

## Closed by measurement, 2026-09-01

- **Entry 32 — "the hub suite has not run on this branch."** Answered by measurement, not decided.
  Run in the 2026-09-01 morning session before merging:

  | Suite | Result |
  |---|---|
  | `hub/tests/` | **3831 passed, 84 skipped, 1 xpassed** in 14:39 |
  | `tests/` | **440 passed, 3 skipped** |
  | `ruff` / `black --target-version py311` / `mypy src/` | clean over CI's own path lists |
  | `hub/ui` | **not run, and not needed** — the branch's product-code diff is three files (`pyproject.toml`, `hub/pyproject.toml`, `hub/tests/test_fastmcp_api_contract.py`); `hub/ui` is untouched. Measured with `git diff --name-only`, not inferred. |

  The baseline at `9fa4c4b` was 3,825 / 84 / 1, so **+6 is exactly the six new contract tests**.
  CI was also confirmed green on `master@ad60b7b`, the merge base.
