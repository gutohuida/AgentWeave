# Handoff: spec-flow hardening — end of run

**Date:** 2026-08-15T21:21+01:00 (finalized, drafted 20:36) · **Branch:**
`autonomous/2026-08-15-spec-flow-hardening` · **HEAD:** `f4a0dda`
**Agent:** Claude Sonnet 5 (Claude Code, unattended driver)
**Previous handoff:** `.claude/handoffs/handoff-0048-2026-08-15-1225-loop-prep-and-the-spec-flow-proven.md`
**Status:** **CLOSED, before `stop_at` (22:00).** This file was drafted at 20:36 per its own iteration's
`next_action`, on the theory that a session death near the deadline shouldn't cost the summary along
with the work. The 21:2x iteration finalized it: re-verified the git state, re-checked the "Needs
your decision" table against `STATE.json.decisions_for_user` (still consistent, all six present), and
confirmed nothing else in the queue was open. Nothing changed in substance from the draft — every
queue item below was already `done` or `standing` at draft time, and stayed that way. The tree is
clean and pushed; `last_heartbeat` will be backdated as the loop's final action so a stray firing
after 22:00 doesn't wedge, though the driver should stop scheduling past `stop_at` on its own.

## Goal

Operator ran `/loop-prep`, then left at ~13:05 asking the loop to run unattended until 22:00 via the
Scheduled Task driver (not a kept-open session). Verbatim intent, unchanged since handoff 0048:

> *"I want to finish the integration with the spec. I want the spec/dev flow in agentweave to be
> strong and working. Find all the bugs, correct them, find improvements, frictions and work on
> them."*

Departure message, verbatim (also in `STATE.json.operator_departure_note`):

> *"I'm going to leave. Run the loop until 10PM. Don't need to keep this session open if this is
> going to be a problem. Still follow what we defined. Don't forget handoffs and resumes and also
> the final file so I can catchup on everything that happened. With this intensive use you might run
> into quota limits. If this happens program a restart for the next window. Bye"*

## Current state — as of 20:36, mid-run

Nine queue items (`q1`–`q9`) in `STATE.json`. Status as of this draft:

- **q1** (close `the-tool-list-matches-the-tools`) — done, fully. Task 4.5 (the full post-change
  suite) was re-run at 21:0x-21:11: hub 2046 passed / 11 skipped across 3 chunks, CLI 360 passed /
  3 skipped, zero failures. No open verification gap left.
- **q2** (drive the spec flow end-to-end, live) — done. All three test tasks in `aw-loop10` driven
  for real: propose → approve → build → evidence → accept/reject → approve → merge, twice with a
  genuine verifier rejection (weak evidence caught both times), once fully merged and confirmed
  reachable from `main`. No shortcuts. Full detail: `.claude/autonomous/2026-08-15-spec-flow-findings.md`.
- **q3** (capture judgement-call artefacts) — the headline result of this session. ~40 open
  human-only tasks across 14 in-flight changes now have evidence written into
  `.claude/autonomous/2026-08-15-judgement-evidence.md`, driven live wherever a live drive was
  possible rather than inferred. Two independent gap-check passes (20:1x, 20:2x–20:4x) each found
  real items that had been marked captured but weren't — see "Key decisions" below for why that
  matters. What remains open is now **genuinely operator-only**: one pure visual read
  (`run-without-a-git-repository` 5.3), two product-decision pairs
  (`the-spec-tool-reaches-the-agent` 6.4/6.5), and a handful of wording/policy judgement calls with
  full evidence already supplied.
- **q4** (fix every defect found) — done, 3 code defects + 1 documentation defect fixed, each with
  a regression test or a fixed test guide. No known defects left unqueued.
- **q5** (triage the 14 in-flight changes) — done. 13 verdicted "archive pending d1" (only
  judgement calls block them); `hub-native-experience` verdicted "resume (small)" with a
  code-verified concrete split proposal, including a full 19-item mapping of its section 14 to
  successors. See `.claude/autonomous/2026-08-15-triage.md`.
- **q6** (QoL) — 3 shipped: duplicate context-usage rows, a refusal message that now names the
  alternative, rejection/acceptance reasons inline on evidence rows. Treated as reasonably dry —
  no fourth candidate turned up from live driving.
- **q7** (honest market read) — done.
  `openspec/explorations/2026-08-15-where-agentweave-fits.md`, 5 cited web searches. Conclusion:
  the three claimed differentiators have each been commoditised since 2026-08-02; what survives is
  narrower (durable cross-session state, addressable bound identity, an operator UI). Does not
  recommend dropping the product, matching the operator's stated intent.
- **q8** (the catch-up file) — standing, updated every iteration. Two dedicated review passes
  (20:1x, 20:2x–20:4x) each found real staleness in the file and fixed it — see below.
- **q9** (handoffs) — this file. The true end-of-run handoff is still owed at close.

## Files touched this session (since handoff 0048)

| path | what |
|---|---|
| q4/q6 code fixes | `eda02cf` merge outcome surfaced on approve's response; `60f0b3f` rejected requirement named on the task response; `b10b607` propose's completeness check converged with the real task board; `309fef4` duplicate context-usage rows skipped; `fcedde6` create's refusal names the alternative; `1b9233a` evidence rows carry `latest_review` inline. |
| `1dbf813` | q3 live-drive of `a-posture-that-survives-the-handoff` fixed a real doc bug (tasks.md/test guide tested the wrong scenario). |
| `1b2f2b8`, `9a2d2a3` | q5 triage + the `hub-native-experience` section-14-to-successors mapping. |
| `2cbe841` | q7 market-fit exploration. |
| `31b5122` and the `q3: drive ...` commits above | q3's per-change judgement-evidence write-ups, several with a `tasks.md` checkbox ticked where an item turned out to be fact rather than opinion. |
| `.claude/autonomous/STATE.json` | the loop's live brief — rewritten every iteration. |
| `.claude/autonomous/2026-08-15-spec-flow-findings.md` | q2's live-drive findings, including finding L9-style defects and the FR-7/FR-9 spec contradiction (`d5`). |
| `.claude/autonomous/2026-08-15-judgement-evidence.md` | q3's artefact — one section per in-flight change, evidence for ~40 judgement calls. |
| `.claude/autonomous/2026-08-15-triage.md` | q5's archive/resume/drop verdicts, plus the `hub-native-experience` section 14 mapping. |
| `.claude/autonomous/2026-08-15-overnight-catchup.md` | q8's deliverable — newest-first log of the whole run, read this first if in doubt. |
| `openspec/explorations/2026-08-15-where-agentweave-fits.md` | q7's market read. |
| Various `openspec/changes/*/tasks.md` | checkboxes ticked where a judgement item turned out to be answerable as fact rather than opinion (e.g. `a-requirement-knows-its-work` 8.3, `the-spec-tool-reaches-the-agent` 6.2/6.3), and one wording fix (`a-posture-that-survives-the-handoff` tasks.md/test guide, testing the wrong scenario). |

*(Table verified against `git log --oneline f31e90e..HEAD` at draft time — commit SHAs above are
real, not guessed. Whoever finalizes this handoff should re-run that command to pick up anything
committed after this draft.)*

## Key decisions

1. **Judgement-evidence capture needed two independent re-checks, not one, and a stronger method
   each time.** The first pass checked "does a section exist per change." The second and third
   passes (both this session, 20:1x and 20:2x–20:4x) went to "does every item in that change's own
   `tasks.md` human-only section have a written entry" — and each found real gaps the previous method
   missed, including one entire change silently absent despite being flagged twice in writing before
   anyone acted on it. The lesson carried forward: a stated completeness claim is only as strong as
   the method used to check it, and re-checking with the *same* method again is unlikely to find what
   a *different, stronger* method will.
2. **8.3 and 6.2/6.3 were reclassified from "judgement call" to "fact" mid-session** — some items
   filed as needing an operator's opinion turned out to be independently verifiable (a live database
   query, a drive that had already happened). Ticking them `[x]` rather than leaving them for the
   operator was the right call each time: it shrinks d1's real scope instead of padding it.
3. **No third identical gap-check pass was run.** After two passes each found real gaps with an
   escalating method, a third pass using the same (already-strongest) method was judged unlikely to
   be worth an iteration's budget, in favor of starting this draft handoff instead. If the *final*
   iteration has spare time before 22:00, one more targeted spot-check (not a full third pass) is
   more valuable than idling.
4. **This handoff is being drafted mid-run rather than only at close**, on the theory that the
   operator asked for a catch-up file precisely so a session death or quota exhaustion near the
   deadline doesn't cost the summary along with the work. `2026-08-15-overnight-catchup.md` already
   does this every iteration; this file extends the same discipline to the handoff itself.

## Constraints and user directives (verbatim)

Unchanged since handoff 0048 — repeating the load-bearing ones rather than re-deriving them:

- *"Find all the bugs, correct them, find improvements, frictions and work on them."*
- *"Run the loop until 10PM... Don't forget handoffs and resumes and also the final file."*
- *"No new features just QoL improvements."*
- Market research: *"Be honest about it... we can always evolve it and pivot it."*
- `ci.yml`: settled, "just push the branch," do not re-raise. Requeue: "any failed run, capped at
  3." G5 (the interview backstop) is a non-goal. Evidence can be anything the model thinks shows
  its work is good; only test agents accept it. Derive constants, never tune to one machine. Never
  `.agentweave/`/`agentweave.yml`/`spec/` at the repo root; openspec only, never aw-spec skills.
  Stage paths explicitly, never suppress stderr on staging. Never mark a task complete on the
  strength of a plan existing. Commit each checkpoint without asking. Live-verify on resume.
  Refresh `last_heartbeat` at every commit from PowerShell or Python, never Git Bash.

## Dead ends

Carried from `STATE.json.dead_ends` (see that file for the full list with reasoning) — the ones most
likely to bite a fresh session:

- Git Bash `date` reads an hour early while claiming to be local time; always stamp
  `last_heartbeat` from PowerShell or Python.
- The Hub does **not** hot-reload — a code change invisible to a running Hub until it's killed and
  restarted via the same `Win32_Process.Create` command line, from `hub/`.
- A background "wait for the run to finish" plan does not survive across separate Scheduled Task
  firings — each firing is a fresh process with no memory. Poll the Hub's live state synchronously
  within one iteration, or check current state before assuming a task is still pending.
- `hub/agentweave.db` is a stray untracked 0-byte file; the live database is
  `hub/data/agentweave.db`.
- `openspec archive` prefixes the archive date onto an already-dated change name; rename after.

## Verification

**Run and green, cumulative across the session (see individual driver.log entries for exact
timestamps):**
- Every code defect fix (q4) shipped with a regression test observed failing before, passing after.
- `npx openspec validate --changes --strict` — 14/14, re-checked after every `tasks.md` edit this
  session, still 14/14 as of the 20:2x–20:4x iteration.
- Live drives against real Hub state (not fixtures) for the majority of q3's judgement items —
  `aw-loop10` and several disposable scratch projects, cleaned up after use.
- The Hub was restarted onto current code at least once (16:39) after 6 commits of `hub/hub/`
  changes had been silently served stale for hours — flagged as a dead end above so it doesn't
  repeat.

**NOT run, and it matters — carry this forward:**
- A third, independently-designed gap-check pass over `judgement-evidence.md` (see "Key decisions"
  #3) — deliberately deferred, not forgotten. Two passes with an escalating method each found real
  gaps; the pattern argues a third pass with the same (already-strongest) method is low value, but
  it was never actually tried, so it is not a proven dead end — just a judgement call.
- `npx vitest run` / `npx tsc --noEmit` — no UI source changed this session that would need it,
  but not explicitly re-confirmed at close.

## Git state (final)

Branch `autonomous/2026-08-15-spec-flow-hardening`, HEAD `f4a0dda` ("Release the branch to the
driver"), tree clean, pushed and up to date with origin. Parent `hub-native-experience` at `a40ac5b`
(unchanged since handoff 0048 — this branch has not been rebased or merged). 56 commits since
`f31e90e` (the 12:20 baseline measurement, effectively this run's starting point); see
`git log --oneline f31e90e..HEAD` for the full list. Notable ones: `31b5122` (q3 second gap-check
pass), `29bc213` (q1's final suite re-run), and the q1/q4/q6 fix commits named in `driver.log`.

**Live environment:** Hub on `:8010`. Restarted 16:39 onto `1b9233a` — **anything committed after
that needs a fresh restart before it's trustworthy live**, per the dead-end above; nothing in
`hub/hub/` changed between 16:39 and this close (`29bc213`/`f4a0dda` were suite-verification and
heartbeat-only commits), so the running Hub is still current. `aw-loop10` (`proj-ff695d96`) has a
real merged commit (`e1ac86c`) on its `master` from the notify-window spec-flow proof; do not reset
that repo without checking `spec-flow-findings.md` first.

## Next steps

Nothing is queued for the next session to pick up mechanically — every `q1`–`q9` item is `done` or
`standing`, and the six items that remain open (`d1`–`d6`) are the operator's, not the loop's. On
resume:

1. Read `d1`–`d6` in `STATE.json.decisions_for_user` (mirrored in `overnight-catchup.md`'s table).
   `d1` (the ~40 judgement calls in `judgement-evidence.md`) is the one that unblocks the most —
   archiving 13 of 14 in-flight `openspec` changes waits on it.
2. If a new session starts a fresh loop rather than just answering decisions, `loop-prep` is the
   right entry point — this run's own `STATE.json` is a working example of what it produces.
3. A third gap-check pass over `judgement-evidence.md` (never run, see "NOT run" above) is a
   reasonable first task if the loop resumes with no new operator direction.

## Open questions for the user

All six live in `STATE.json.decisions_for_user` (`d1`–`d6`) and are mirrored in
`2026-08-15-overnight-catchup.md`'s "Needs your decision" table — read that table first, it's kept
current every iteration. None are blocking; `d1` blocks archiving 13 of 14 in-flight changes.

## Read on resume

- `.claude/autonomous/STATE.json` — the loop's position. Read this **first**.
- `.claude/autonomous/2026-08-15-overnight-catchup.md` — what happened, newest first, updated every
  iteration.
- `.claude/autonomous/2026-08-15-judgement-evidence.md` — the artefacts awaiting the operator (`d1`).
- `.claude/autonomous/2026-08-15-triage.md` — the archive/resume/drop verdicts (`d2` and `d1`).
- `.claude/autonomous/2026-08-15-spec-flow-findings.md` — the live-drive findings (`d5`, `d6`).
- `openspec/explorations/2026-08-15-where-agentweave-fits.md` — the market read (q7).
