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
