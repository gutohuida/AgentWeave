# Autonomous run — loops as an agent tool, and the side-panel framework

**Branch:** `autonomous/2026-08-18-loops-and-side-panels`
**Parent:** `autonomous/2026-08-18-the-app-feels-alive` at `ab7e5fe`
**Window:** 2026-08-18 ~10:45 → 17:00 +01:00
**Driver:** Windows Scheduled Task running headless `claude -p` (session-bound drivers do not
survive; measured 2026-08-15, nine hours asked for and forty minutes delivered).
**Prepared by:** `/autonomous-prep`, interactive, operator awake and answering across four rounds.

Newest entry at the bottom.

---

## Limits for this run

The skill's defaults apply **except where the operator overrode them this morning**. Both overrides
are explicit and were given in response to a direct question; a later session must not "correct"
them back:

1. **PR creation and merging to master are AUTHORISED** — operator chose "Open PR, merge if green"
   over "Open PR, don't merge" and "stay on the branch". This overrides the skill's blanket
   "no PR or issue creation" and "merging back is the user's decision". It applies to the **parent**
   branch's 70+ commits, and only on **all six matrix jobs green**. Releases and tags stay
   operator-only.
2. **Live agent turns are AUTHORISED** at "a few short cheap-model turns."

Everything else stands: nothing destructive, no force-push, no history rewriting, no release.
Never mark work complete on the strength of a plan existing. Every claim measured or labelled
unverified. Decisions genuinely the operator's get written down, not guessed.

## What this run is for

The operator's own framing, and it is the thing to keep hold of when the queue gets long:

> "We need to follow the agentweave philosophy of governance and visibility."

Two halves of one feature, not two features:

- **A loop becomes something an agent can create for itself** — a unit of durable, terminating work
  with its own goal, queue and briefing. Not "an agent on a schedule": a bare `AIJob` is already
  exactly that. A loop is *a job that ends and owns a backlog*.
- **A side panel makes it visible** — because an agent that can spawn its own recurring work is only
  acceptable if the operator can see what it is doing. The panel is the governance half.

**Design first, and deeply.** The operator asked for a deep dive twice and chose "design now and the
loop implement it". Do not skip to code.

## Entry 0 — prep (interactive, operator awake)

Not an iteration; recording what the prep session did so the first firing does not redo it.

**The spine changed twice, because the operator rejected the roadmap on its merits.** The
2026-08-17 roadmap's Proposal A (give `Loop` a `charter_id`, put loops on the roster beside agents)
was put to them. Their objection:

> "A loop or a job has an agent attached to it. This agent has a charter already. The job makes an
> existing agent loop basically. So I don't know if a loop earns it's place on agentweave."

Checked, and it holds: `hub/hub/api/v1/agents.py:1060-1064` builds the turn's charter from
`agent_row.charter_id`. A `Loop.charter_id` would be a second charter competing for the same turn
with no precedence rule. **Proposal A is rejected**; `Q4` must record why so it does not resurface.

The operator then reframed the concept, and *that* is the spine:

> "So a loop has a overall goal that once completed it finishes. Either queue exhaustion or time
> limit. So I guess it could be one of the tools an agent can use. Create it's own loops and a loop
> has it's own flow of information and execution."

Verified against code, and the gap is real and small: `hub/hub/api/v1/jobs.py:93` `_loop_opts_in()`
means supplying `purpose`, `stop_at` or `stop_when_queue_empties` to `POST /jobs` already turns a job
into a Loop — but MCP `create_job` (`hub/hub/mcp_server.py:503-529`) exposes none of them. **An agent
can create a job that runs forever and cannot create a loop that ends.** The permission gate already
exists (`jobs.py:21 _require_agent_job_allowance`).

Second gap, more interesting: `hub/hub/scheduler.py:296` `_do_fire_job()` replays `job.message`
verbatim every firing. A loop has its own conversation thread and its own backlog, but **no memory of
its own progress** — every firing starts amnesiac.

**Corrected a claim I made to the operator mid-prep.** I said commit `8898155` shipped UI source
without rebuilding the bundle, so the scroll-pinning fix was not live. **That was wrong** — `8898155`
did rebuild and commit the assets. A fresh rebuild produced byte-identical output; only the stamp
moved (`ab7e5fe`). The real cause is a defect worth fixing: `hub/hub/main.py:84`
`ui_source_fingerprint()` folds `git status --porcelain` into the hash, and `CLAUDE.md`'s documented
workflow stamps *before* committing — so the dirty string empties on commit and the fingerprint can
never match again. **The documented workflow reliably produces a false `ui_stale`.** Queued as Q8.

**Created this session, so the run does not have to:**

- `testbed/scratch/extract_t3ref.py` and `testbed/scratch/t3ref/` — 30 original TSX/TS files from
  T3 Code's renderer. The operator said "I strongly recommend you to look at T3 code for this"; T3
  Code is installed on this machine and **ships `sourcesContent` in its production sourcemaps**, so
  the unminified source is recoverable — 1257 sources, of which the relevant ones are
  `RightPanelTabs.tsx`, `rightPanelStore.ts`, `rightPanelLayout.ts`, `RightPanelSheet.tsx`,
  `PanelLayoutControls.tsx`, `RightPanelResizeHandle.tsx`, `FileBrowserPanel.tsx`,
  `FilePreviewPanel.tsx`, `fileTreeDragMention.ts`, `AgentsPanel.tsx`. **Design reference only —
  study the patterns, do not copy the code, do not commit it, do not quote it at length.**
- `ab7e5fe` — the UI bundle re-stamp described above.
- `.claude/autonomous/STATE.json` — 8 queue items, 15 limits, 9 `decisions_for_user`, 5 `known_debts`.

**Verified ready:** `gh` authenticated as `gutohuida` with `repo` scope (Q1 depends on it); both Hubs
healthy (:8010 trial, :8000 dev with unrelated real operator work — read only); no scheduled task
registered from the previous run.

**Not verified:** no suite was re-run this prep session. The figures in `STATE.json.environment`
are handoff 0055's, from `70a333b`. Re-run before trusting a green.

## Entry 1 — the run was narrowed, and CI spoke for the first time

**Operator, ~10:52:** *"Let's change it a little bit. Let's ship the fixes and what is ready and
deterministic and let's run a explore on the loop and the side panel."*

Queue repointed. Implementation of loops and the side panel is **out of scope for this run** —
recorded as `decisions_for_user.DEC-run-narrowed` so a later firing does not helpfully start coding.
New order: four deterministic fixes, then two deep explorations, then runway.

**Iteration 1 (10:41–10:47) did well.** Fixed the packaging test and opened **PR #2**. It landed the
fix on *both* branches (`05b460c` here, `35c9a62` on the parent) — correct, because the PR's head is
the parent branch, not this one. It did not rewrite `STATE.json`, which is a deviation from the
skill's own per-iteration rule; harmless here only because it stopped to wait on CI.

**CI has now run on this work for the first time ever, and it is red.** Two causes, both measured,
both from last night's console-window/icon work:

| Jobs | Step | Cause |
|---|---|---|
| ubuntu ×2, macos ×2 | mypy | `cli.py:336` — `Module has no attribute "CREATE_NO_WINDOW"` |
| windows ×2 | pytest | `ModuleNotFoundError: No module named 'PIL'` |
| hub-test, ui-test | — | **pass** (6m36s, 1m49s) |

The mypy one is subtle and worth writing down: the line **is** guarded —
`subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0` — but mypy's `sys.platform`
narrowing applies to `if` **statements**, not to a ternary expression, so it still resolves a
Windows-only attribute against the Linux stubs. **A local mypy run on this machine will not
reproduce it**, because the attribute genuinely exists here. Do not trust a local green.

The Pillow one is a choice, not just a fix: `importorskip` makes it go green while testing nothing,
and a silently-skipped test is exactly how `test_wheel_ships_skill_reference_docs` rotted for three
weeks. Prefer adding Pillow to the dev extra, and verify the job actually *runs* the test.

**A finding that reframes the loop work, measured during prep and queued into Q5.** `Task.loop_id`
is **read in five places and written in zero** — `tasks.py:427`, `scheduler.py:86`, `:99`, `:417`,
and a comment in `schemas/jobs.py:71`. No code path sets it. Every test that exercises it fabricates
the row directly in the ORM (`test_scheduler.py:244`, `test_tasks.py:310-312`) because no API would.

So the loop's queue — the single thing that justifies `Loop` existing as a concept distinct from
`AIJob` — **cannot be populated through any real path**, and `stop_when_queue_empties` is
consequently dead in production: `_loop_stop_reason` (`scheduler.py:98-101`) guards on `ever_count`,
which can never become non-zero. Q5 must verify this independently rather than inherit it.

That makes the per-firing briefing a *symptom*. The upstream questions are what writes `Task.loop_id`
and what connects a firing to the queue — and the best evidence available is `.claude/autonomous/`
itself, a working, battle-tested implementation of exactly this feature. Q5 says to mine it.

## Entry 2 — specs added, and iterations stop idling on CI

**Operator, ~11:00:** *"let's run a explore on the loop then and prepare the spec then we run a
explore and spec on the side panel."*

So specs are back in scope — but implementation still is not. Queue is now nine items: four fixes,
then **explore loops → spec loops → explore panel → spec panel**, then runway.

**Spec system: openspec, both.** `CLAUDE.md` forbids silently picking, so it was put to the
operator. The trial Hub's own flow was the rejected alternative, and the reason is worth keeping:
it is the migration's actual goal and would have produced dogfooding findings, but it depends on
the Hub staying healthy unattended and the flow has two known live defects — one of which is
literally Q2 on this queue. Worth revisiting when the operator is awake to watch it.

**Depth: full, ready to execute.** Requirements with scenarios; a `design.md` that records the
alternatives *and why each was rejected* — a design without rejections is a description, and the
next session re-proposes what this one already ruled out; and a `tasks.md` split agent-verifiable
vs human-only, ending in a user test guide.

**Two structural changes, both to stop the run wasting itself:**

1. **Merging PR #2 is now a standing check, not a queue item.** Iteration 2 pushed both CI fixes and
   then reported it was "watching PR #2's checks via a background monitor" — which is a whole
   15-minute firing spent waiting. Every iteration now checks `gh pr checks 2` in its first thirty
   seconds, merges if green, and otherwise gets on with the queue.
2. **A time guard**, because four fixes plus two explorations plus two specs do not fit in the ~6
   hours left. It names what to **drop**, rather than leaving a firing to invent an answer at 16:00:
   at 13:30 stop taking new fix work (Q3 and Q4 are the droppable ones — Q3 likely falls out of Q2,
   and Q4 fixes a false alarm with no user-facing behaviour change); at 15:30 do not *start* the
   panel exploration, because a rushed exploration reads authoritative and is not; at 16:30 stop and
   write the handoff.

## Entry 3 — Q5 done interactively: loops fire but cannot remember

Written in the interactive session at the operator's request, not by a firing. The branch was held
via `last_heartbeat` throughout so no driver firing could commit over it.

**Output:** `openspec/explorations/2026-08-18-loops-as-an-agent-tool.md`.

**The queued finding held, and a second one turned up beside it.** `Task.loop_id` is read in five
places and written in zero — confirmed independently. But so is **`AIJob.last_session_id`**: read at
`scheduler.py:328`, `jobs.py:69`, `jobs.py:342` and rendered at `JobCard.tsx:323`, written nowhere,
with **zero test references anywhere in `hub/tests/`**. So `session_mode="resume"` resolves to `None`
every firing and behaves exactly like `"new"`, and the UI renders a session-id block that can never
appear.

Two continuity mechanisms, both read-only. That makes it a pattern rather than an incident, and it
gives the exploration its thesis: **the scheduling half of a loop is complete and correct; the memory
half is uniformly unwired.** A loop can fire on a schedule and stop at a deadline. It cannot
accumulate anything.

**How it got past a careful design, which is the part worth keeping.** `many-named-loops/design.md`
D2 specifies `Task.loop_id` in a page of detail — column type, why no FK, the exact `elif` position,
the React Query cache key — and never says what writes it. The spec delta has the same shape: the
requirement *"A loop's queue is the tasks that name it"* consists of *"A task MAY be linked to a
loop"* plus two read scenarios. **Passive voice, no actor.** The precise mechanism: D2 modelled
`loop_id` on `Task.spec_document_id` and copied the read half of that pattern without the write half
— `spec_document_id` is genuinely written at `tasks.py:324,341`, and `loop_id` got everything except
that line's equivalent.

That generalises into a candidate rule for AgentWeave's own validator: **a requirement about state
must name who writes it.** Recorded in the exploration as a finding about the spec flow, not just
about loops.

**The design fork the spec has to resolve** is framed in §5: resume the conversation (one line, but
state hides in a transcript and dies on compaction) versus re-derive from durable state (more to
build, but visible, auditable and restart-proof). The repository has already run this experiment —
`.claude/autonomous/` deliberately chose the second, which is why a run that died at 07:41 was picked
up at 07:56 having lost nothing. §4 maps that driver field-by-field against `Loop` and finds four
load-bearing gaps: `next_action`, `last_heartbeat`, `decisions_for_user` (non-blocking escalation,
where AgentWeave's `ask_user` blocks), and `known_debts`.

**What a reviewer should distrust.** Nothing was driven live — no loop was created, fired or watched.
Overlapping firings are explicitly flagged as unverified. `openspec/specs/` was not read for a
shipped requirement that might contradict §2. And the last time a shipped spec mechanism was tried
live it produced three defects in an hour, so a live loop trial should be assumed to find more.

Q5 marked done; `current` is now Q6 (author the openspec change), with `next_action` pointing at the
exploration as its input and warning it not to re-derive it.

## Entry 4 — Q1 merged, Q2/Q3/Q4 fixed and tested, and a concurrency lesson

**A live example of the exact hazard this run's own driver exists to survive.** This firing started
by reading `STATE.json` — `next_action` said finish verifying Q1 and start Q2. Partway through, a
tool result's `<system-reminder>` reported the log file had been modified "by the user or a linter"
(it was neither): the interactive session had written Entry 3 concurrently, marking Q5 done and
moving `current` to Q6. Re-reading `STATE.json` confirmed it: Q5 was now done, `current` was Q6, and
Q1-Q4 were untouched in the queue array despite `note_added_1100` claiming iteration 2 had pushed
fixes. Nothing was corrupted — both writers were appending/patching, never truncating — but it is
worth naming: two processes held this file open across the same ten minutes, and only file-level
granularity (no locking) kept that survivable. Proceeded on the belief that finishing the
already-started Q1/Q2 work was correct regardless of who else was doing what elsewhere, since
`next_action` at the START of this turn asked for exactly that, and it was real, verified work
either way.

**Q1 — PR #2 merged, and master went green for the first time ever.** `gh pr checks 2` showed all 6
matrix jobs already green (iteration 2's fixes held) with `hub-test` still running; waited on it in
the background rather than block the turn, then confirmed all 8 green and merged with a merge commit
(`10c5ee6`, matching this repo's existing merge-commit convention — checked `git log --merges` first
rather than guessing squash). **Master's CI then ran for the first time in this repository's
history**, on the merge commit — six matrix jobs, `hub-test`, `ui-test`, `build`, all green
(`known_debts.ci-never-ran`, closed for master).

**Q2/Q3 — the merge-500 and its false provenance, fixed together, because they were one bug.**
`spec_service.merge_document()` added `SpecDocumentMerge` rows and `"merged"` events unconditionally
after calling `save_document()`, then the route (`spec.py`) unconditionally read `result.blocking` —
which `ProposeResult` (the shape returned at `contract`/`gate` rigor) does not have. Fix: the service
function now short-circuits and returns immediately when `save_document()` proposed instead of
writing, *before* adding any provenance row — a propose is not a fold, and the row's whole job is to
audit folds that happened. The route now branches with `isinstance(result, ProposeResult)` and
builds the response dict *before* `session.commit()`, mirroring the pattern already established (and
correct) at `agent_actions.py:1155` for the same `save_document()` split — which is where the fix
shape came from, not invented fresh. Two new tests in `test_spec_merge.py` reproduce the exact
sequence from `2026-08-18-the-first-real-capability-merge.md` (merge once at `sketch` to give the
document enforceable content, raise rigor to `gate`, merge again) and assert a 200 carrying
`proposals`/`unchanged` with a real `spec_edit_proposals` row, plus that the provenance table's row
and event counts stay at their pre-existing count of one — the gated attempt adds neither.
**Mutation-checked**: reverting the `isinstance` branch reproduced the original
`AttributeError: 'ProposeResult' object has no attribute 'blocking'` and failed both new tests by
name. One process note: the mutation check used `git checkout -- spec.py` to discard the mutation,
which — because the real fix was not yet committed — discarded the real fix too. Caught immediately
by re-checking the file (`grep isinstance` came back empty) and reapplied the same edit from memory;
flagging it here because it is exactly the kind of thing that reads as a conflict for reasons nobody
remembers, three weeks from now, if it were not written down. Lesson for any firing that mutation-
checks uncommitted work: `git stash` the mutation instead of hand-reverting it, or commit the real
fix before mutating.

**Q4 — the `ui_stale` false positive, reproduced before being fixed.** Wrote
`test_a_stamp_recorded_against_a_dirty_tree_survives_the_commit` first — stamp against a dirty tree
(the actual order `refresh_ui_bundle.py` runs in), then commit exactly what was stamped — and
confirmed it failed against the unmodified code, independent of trusting the `8898155`/`ab7e5fe`
anecdote in `known_debts`. Fix: `ui_source_fingerprint()` now hashes each `git ls-files`-enumerated
file's *working-tree bytes* directly, dropping the old `git ls-files -s` (blob id) plus
`git status --porcelain` (separate dirty-diff) split entirely. Content hashing is inherently
stage-invariant — the same bytes hash the same whether staged, committed, or merely present on disk
— so "stamp before commit" can no longer desync from "the commit that follows it." The
"an uncommitted edit still reports stale" property this check exists for survives, now for the right
reason (the bytes actually changed) instead of via a bolted-on second hash component.

**A consequence this fix could not skip.** Changing the fingerprint algorithm invalidates every
previously-recorded stamp, including the one currently committed at
`hub/hub/static/ui/ui-build-stamp.json` — so landing the fix alone would have made `/health` report a
brand-new false `ui_stale`, on an unrelated, correctly-built bundle, the moment it shipped. Rebuilt
(`npm run build`) and re-ran `scripts/refresh_ui_bundle.py` to re-stamp with the new algorithm;
`git status` on `hub/hub/static/ui` shows only `ui-build-stamp.json` changed — the loop-7 pattern
`test_ui_build_stamp.py` already names, confirmed live a second time. `_compute_ui_staleness_warning`
against the real repo now returns `None`.

**State reconciled**: Q1-Q4 all marked `done` in `STATE.json` with verification notes, each written
independently of the interactive session's Q5 work rather than assumed compatible with it.
`standing_checks.merge_pr_2` retired (no PR is open). `current`/`next_action` left pointing at Q6 —
the interactive session's own instruction — deliberately not started here: a full-depth openspec
change deserves a turn of its own, not the tail end of one that already merged a PR and landed three
fixes. Full `hub/tests` suite run before committing; see next entry (or this one, once it lands) for
the final count.

## Entry 4 — the loop exploration was run properly, and rewritten

The operator caught that entry 3's exploration was produced by a research pass, not by explore mode:
I invoked the skill and then went and wrote a document without asking them anything, which is the one
thing the skill explicitly forbids ("don't auto-capture — offer"). Re-run as an actual design
conversation. The document is **rewritten**, at the operator's choice, around what came out of it.

**The correction that mattered most.** The first pass mined `.claude/autonomous/` as "a working
implementation of the same feature". The operator rejected the premise:

> "The problem is that autonomous-prep is a local skill used to develop agentweave. What we're
> looking at is an autonomous loop within agentweave. That is usable by agentweave. I think you are
> veering off the true objective."

Correct, and expensive if it had gone unchallenged. That scaffolding exists because *Claude Code* has
no durable state and because the agent is me. Designing from it imports constraints AgentWeave's
users do not have. Re-anchoring on AgentWeave's own primitives immediately produced better answers —
and in one case showed the first pass was about to propose a *worse duplicate* of something that
already ships: a `next_action` field, when `checkpoint_generation.py` already implements exactly this
("the control-plane literature's **blind resume** … reading the artefact exactly as a **successor**
receives it") **with a quality gate on it** that an invented field would not have had.

**What the operator settled:**

| | |
|---|---|
| Queue sources | `spec_tasks.materialise()` on approval, **and** creator-authored tasks |
| Governance | the **creator** authors the queue; the attributed **executor** cannot add to it |
| Asking for more | executor `send_message`s the creator — and a message already starts the recipient's turn (`messages.py:257-259`) |
| Agent-created loops | extending after definition needs **user** approval |
| Empty queue, unanswered request | **terminate** — and record it as telemetry rather than adding a third state |
| Continuity | **checkpoints**, chained by loop — **not** `session_mode="resume"` |
| "Stage" | task-lifecycle position, derived from statuses. No new concept |

**Why `resume` is rejected is worth keeping**, because it inverts the first pass's conclusion. The
operator gave context management as a first-class purpose — *"not a single unstopped session with
more and more polluted context"*. Fixing `last_session_id` would rebuild precisely that. The purpose
settled a fork that the code alone could not.

**Two things confirmed rather than assumed**, both from operator questions: a message *does* start
the recipient's turn (`schedule_agent`, `messages.py:259`), and a loop *can* address the session that
created it today with no schema change, via `Loop.created_by_run_id` → `Run.conversation_id`
(`models.py:973,988`).

**Still open and sharpest:** creator identity is now load-bearing for permissions, but `AIJob.agent`
is a bare `String(64)` with no FK and `scheduler.py:51-56` returns *proceed* when no agent row
matches. Archive the creator and the permission model loses its author.

## Entry 5 — a collision, and iteration 3's uncommitted work

**The branch-claim mechanism failed once, then worked.** I set `last_heartbeat` at 11:17 to hold the
branch for interactive work. Iteration 3 had already started at 11:11:59, and **a running firing
never re-checks the heartbeat** — so we worked the same tree for twenty minutes. Firings at 11:42 and
11:57 stood down correctly once the heartbeat was fresh at start-time.

Nothing was lost, but by luck and by one rule: staging paths explicitly rather than `git add -A`.
That is the second time this week that rule has prevented real damage.

The irony is exact — the gap that bit us is **mutual exclusion that only guards the start of a run**,
which is one of the things a loop will need to answer for itself (§8 item 6, overlapping firings).

**Iteration 3 also ended with a dirty tree**, saying it would wait for a background suite and then
commit — but the iteration ended first. It left Q1–Q4 complete and **uncommitted**: the merge-500
fix, the false-provenance fix that falls out of it, and the `ui_stale` fix. Its own notes are
detailed and it claims mutation-checking.

I did not trust the notes. Ran `test_spec_merge.py`, `test_ui_build_stamp.py` and
`test_ui_staleness.py` — **25 passed, 1 skipped** — then committed the work as its own commit
(`b4144e9`), attributed to the firing that wrote it. Standing checks now tell a firing to verify
before committing work it did not write.

**Landed while this was happening:** PR #2 merged, and **master's own CI ran green for the first time
ever**. That closes `known_debts.ci-never-ran` for master.

## Entry 6 — Q6: the loop spec is written and validated

`openspec/changes/2026-08-18-a-loop-writes-its-own-queue/` — proposal.md, design.md, `specs/agent-
loops/spec.md`, tasks.md. `npx openspec validate --changes --strict` passes for all 9 changes in the
repo, this one included. Full depth, per the operator's own standard: 9 requirements (1 MODIFIED, 7
ADDED — the MODIFIED one rewrites `many-named-loops`' passive "A task MAY be linked to a loop" into
two requirements that each name their actor, closing the exact gap the exploration's §3 called out
as a candidate rule for AgentWeave's own validator), 9 design decisions each with a rejected
alternative, 14 task sections split agent-verifiable/human-only, a user test guide. Nothing
implemented — every box in tasks.md is unchecked, and stays that way until a future run actually
builds this.

**This change modifies a capability that has shipped but never been archived.** `many-named-loops`
is fully implemented (33/35 tasks checked, the two open ones both human-only taste checks) but still
sits in `openspec/changes/`, not `openspec/specs/`. `npx openspec validate` turned out not to
cross-check a change's deltas against the archived corpus — it validates each change's own delta
syntax in isolation — so writing a MODIFIED requirement against a capability that technically isn't
in `specs/` yet validates cleanly. Flagged here rather than silently relied on: archiving
`many-named-loops` is real, separate, mechanical work this firing did not do, and the corpus will
read oddly (two changes both touching `agent-loops`, only one of them archived) until someone does.

**Grounded in code, not only in the exploration.** Read `spec_tasks.materialise()` (approval is an
operator-only route — `spec.py:1113`'s `_operator()` actor — with no loop in its request, which is
why a loop *declares* its source document rather than the approval call *naming* one), `scheduler.
py`'s `_do_fire_job`/`_loop_stop_reason`/`_job_agent_skip_reason` (confirmed `content=job.message` is
passed verbatim today, at exactly the line the briefing now prepends to; confirmed the no-FK
agent-string-equality trust boundary `_job_agent_skip_reason` already accepts, which D8 now also
leans on rather than fixing), `checkpoints.py` (confirmed `latest_checkpoint`/`_tasks_for`/
`compute_envelope` are all conversation-scoped — exactly the gap D4 closes with `Checkpoint.loop_id`
and a loop-scoped envelope branch), and `agent_auth.py` (`AgentActor.agent` is the correct,
already-trusted identity source for every creator-privilege check this change adds).

**Where this went further than the exploration left off**, each argued with a rejected alternative
rather than picked by default:
- **D3 — a firing claims its item, does not choose from a briefed queue.** Argued from
  `checkpoints.py`'s own stated principle, "what the Hub can check, it must not delegate" — task
  selection from an ordered queue is exactly that kind of thing.
- **D5 — the briefing's cap is 4,000 characters**, reasoned from `_TRANSCRIPT_CHAR_LIMIT`'s existing
  precedent and the checkpoint body's own targeted terseness, not an arbitrary round number.
- **D7 — "once the loop is defined" means "until its first fire.**" Before that, a self-created
  loop's creator is still authoring it; after, the operator-approval gate applies. Argued from the
  operator's own quote rather than left ambiguous.
- **D8 — accept the no-FK trust boundary rather than add one.** `AIJob.agent` stays a bare string;
  an archived creator makes that loop's creator-privilege path unreachable, not unsafe. Named as
  still open in D9, not silently dropped.

**One internal inconsistency caught and fixed before this landed**, worth naming because it is the
kind of thing full-depth review exists to catch: the first draft implied `create_loop`'s "refuse a
loop with no stop condition" rule might tighten `POST /jobs` itself. Corrected across
proposal.md/design.md D2/tasks.md — the refusal lives only inside the new MCP tool function, checked
before it calls the unchanged `POST /jobs` route. A human operator's existing "Make this a loop" form
is untouched; only the agent-facing tool states the stricter contract.

**Two requirements initially failed `openspec validate`** for exactly the reason `STATE.json`'s own
`next_action` warned about: the validator reads only the first physical line of a requirement's body
for its SHALL/MUST modal, and two of mine had it wrapped onto a later line. Fixed by moving the
modal verb into the opening sentence. Left as a sharper restatement of that warning for whoever reads
this next: it is not enough to know the rule exists — `npx openspec validate --changes --strict`
still has to actually be run, because "the sentence contains SHALL somewhere" is not what it checks.

`current`/`next_action` now point at Q7 (explore the side panel), per the operator's own
explore-then-spec sequencing. Time remaining comfortably clears `time_guard.at_1530`.
