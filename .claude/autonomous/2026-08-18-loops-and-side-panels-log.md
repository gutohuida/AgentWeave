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
