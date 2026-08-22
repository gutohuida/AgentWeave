# Handoff 0071: Playwright verification and browser-discovered UI fixes

**Date:** 2026-08-21T18:41:00+01:00 · **Branch:** `master` · **HEAD:** `4b6adc7`
**Model:** gpt-5.6-sol
**Agent:** Codex in T3 Code
**Iteration commits:** `264a299..4b6adc7`
**Previous handoff:** `handoff-0070-2026-08-21-1624-driving-the-hub-found-seven-defects-and-a-change-to-hold-them.md`
**Status:** chunk complete

## Goal

Finish the existing implementation cycle: test everything that can be tested, fix defects exposed by real use, merge completed work to `master`, clean disposable state, archive only genuinely complete specs, and leave the repository oriented for the next development cycle. This chunk specifically automated every objective “human-only” check that Playwright could settle and fixed the two UI defects those checks exposed.

## Current state

`master` is clean, matches `origin/master`, and ends at `4b6adc7`. The Playwright work used a copied disposable SQLite database and a Hub on port 8010; both the Hub and `.tmp-playwright-db/` were removed afterward. Port 8000 and the operator's real beta database were not touched.

The adopted-corpus browser suite passes 9/9. Direct Playwright checks proved the Spec home narrative and six areas, map navigation, direct offline `file://` rendering with all 40 local links resolving, the dependency board's picker/review/collapse/read-only behavior, honest broken-loop state, actionable unbound-runner messaging, and no conversation creation across three genuinely stalled firings.

Two browser-discovered defects are fixed and live-tested: an off-board dependency reference now switches to its owning document board, and the Jobs page archives through `POST /jobs/{id}/archive` instead of presenting a DELETE action the server always refuses. Archiving a loop-backed job disabled and archived the job, archived its loop, removed the card, and preserved the loop purpose.

OpenSpec status after the pass: `diagnose-and-clear-a-broken-loop` 44/48; `task-dependencies` 83/86; `corpus-aware-documents` 49/55; `agent-created-documents` 27/35; `loop-notices-and-reacts` 0/44; `loop-becomes-a-flow` 0/60. Objective Playwright-proven items were checked off; subjective taste checks and checks requiring a real runnable agent remain open.

## Files touched

- `hub/ui/src/components/tasks/DependencyBoard.tsx` — off-board prerequisites became buttons that can select their owning board. Finished.
- `hub/ui/src/components/tasks/DependencyBoardView.tsx` — wires owning-board selection into the board picker. Finished.
- `hub/ui/src/__tests__/dependencyBoard.test.tsx` — regression test for following a foreign prerequisite. Finished.
- `hub/ui/src/api/jobs.ts` — replaced the DELETE mutation with `useArchiveJob` calling the archive endpoint. Finished.
- `hub/ui/src/components/jobs/JobsPage.tsx` — uses archive mutation and archive-specific errors. Finished.
- `hub/ui/src/components/jobs/JobCard.tsx` — honest Archive action, icon, confirmation, and callback names. Finished.
- `hub/ui/src/__tests__/jobCard.test.tsx` — regression test for the archive workflow and absence of Delete. Finished.
- `hub/hub/static/ui/index.html` — rebuilt dashboard entrypoint. Finished.
- `hub/hub/static/ui/ui-build-stamp.json` — refreshed production bundle stamp. Finished.
- `hub/hub/static/ui/assets/index-DGHd6K6D.js` — prior generated bundle removed by the rebuild. Finished.
- `hub/hub/static/ui/assets/index-B0vugjq-.js` — current generated bundle. Finished.
- `openspec/changes/corpus-aware-documents/tasks.md` — recorded Playwright evidence for 8.1, 8.2, 8.3, and 8.7. Finished for those checks.
- `openspec/changes/task-dependencies/tasks.md` — recorded Playwright evidence for 11.2 and 11.5–11.8. Finished for those checks.
- `openspec/changes/diagnose-and-clear-a-broken-loop/tasks.md` — checked 9.1–9.4 after live disposable-fixture verification. Finished for those checks.

## Key decisions

1. A cross-document blocker opens its owning dependency board rather than navigating to the Spec tab. The prerequisite payload has the owning document ID but no stable document path, and staying in the board makes the blocker immediately reachable. Rejected: leaving the named reference as a non-interactive span, which failed the spec's reachability requirement.
2. The Jobs page archives rather than deletes. The server intentionally refuses DELETE and already exposes the correct archive lifecycle route. Rejected: retaining a misleading Delete button and surfacing the refusal as normal UX.
3. Only objective browser-verifiable parts of “human-only” sections were marked complete. Visual taste, acceptable review cost, and real-agent behavior were left open. Rejected: treating a green browser assertion as a substitute for subjective operator judgment.
4. All live mutation tests used a copied database on port 8010. Rejected: mutating the operator's beta database merely to complete verification.

## Constraints and user directives (verbatim)

- “Let's test everything that we need to test, fix what we need to fix, merge what we need to merge, clean the branches, archive specs and reorient ourselves to develop again”
- “Do any of the humans test possible using playwright that is installed”
- “Execute the playwright ones”
- “$handoff”

Standing repository constraints still in force: this checkout is AgentWeave source, not an AgentWeave project; do not create root `.agentweave/`, `agentweave.yml`, or `spec/`; planning lives under `openspec/`; never touch port 8000; use `testbed/` or disposable copied state for product exercise; stage paths explicitly rather than `git add -A`; rebuild and refresh the committed UI bundle after dashboard changes.

## Dead ends

- The existing loop browser fixtures referenced stale beta IDs, so those tests timed out for fixture drift rather than product behavior. Disposable equivalent fixtures were seeded into a copied database instead.
- The first foreign-reference check opened the default AgentWeave board, where the reference cannot exist. Selecting the Agents and execution board first exposed the cross-document reference correctly.
- Several first attempts scoped the Jobs card through incorrect DOM ancestry. The decisive issue was earlier than the locator: the page was still showing “Loading jobs…”, and the seeded job's actual title was `Broken Playwright Loop`, not `Playwright broken loop`.
- The verification query initially used a nonexistent `jobs` table; the model table is `ai_jobs`.
- A firing queued to an unbound agent can still legitimately create a conversation; it is not the “genuinely stalled” case. Adding a blocked loop task proved the intended property: three stalled Run actions created zero conversations.
- Expanded Jobs cards cannot currently prove `diagnose-and-clear-a-broken-loop` 9.6 because the jobs collection response carries `history: null`; that check remains open rather than being inferred.

## Verification

Ran and passed:

- `cd hub && AW_HUB_URL=http://127.0.0.1:8010 AW_HUB_PROJECT_ID=proj-5e960453 py -3.11 -m pytest tests/browser/test_adopted_corpus.py -q` — 9 passed.
- Direct Python Playwright against the disposable live Hub — Spec narrative/six areas, home→area→capability→area→home, dependency picker counts, review stall wording, terminal collapse/expand, no edit affordances, cross-document board switching, broken-loop inactive state, actionable runner remedy, three stalled firings creating no conversations, and job archive UI/data invariants all passed.
- Direct Playwright against `file:///.../spec/agentweave.html` — rendered offline; all 40 local links resolved.
- `cd hub/ui && npx vitest run` — 121 test files, 1,216 tests passed.
- `cd hub/ui && npm run lint` — passed with zero warnings.
- `cd hub/ui && npx tsc --noEmit` — passed.
- `cd hub/ui && npm run build` followed by `py -3.11 scripts/refresh_ui_bundle.py` — passed; production bundle refreshed.
- `npx openspec validate task-dependencies --strict` — valid.
- `npx openspec validate diagnose-and-clear-a-broken-loop --strict` — valid.
- `npx openspec validate corpus-aware-documents --strict` — valid.
- `git diff --check` — passed before commit.

Not tested:

- `diagnose-and-clear-a-broken-loop` 9.6, because the Jobs collection does not provide run history to the card.
- `task-dependencies` 11.3, because it needs a real agent attempting a gated transition.
- Subjective checks: corpus 8.6; dependency-board 11.1 and 11.4; any visual/taste portion not reducible to an objective assertion.
- `agent-created-documents` human checks, which need a real document-producing agent/provider.
- The full Python CLI and Hub suites were not rerun in this final browser chunk; the implementation changed only UI source/static assets and OpenSpec task bookkeeping.

## Git state

- Branch: `master`.
- HEAD: `4b6adc7381c62e339c03ae30edb003c56b0d2b25` (`fix(ui): close browser-discovered workflow gaps`).
- Working tree: clean before this ignored handoff file was written.
- Upstream: `origin/master` is at the same commit; zero unpushed commits.
- This chunk's final commit: `4b6adc7 fix(ui): close browser-discovered workflow gaps`.
- Broader resumed iteration boundary: `264a299..4b6adc7`; it includes the completed loop fixes, verification records, completed-document archival, dependency-board work, and final Playwright fixes listed by `git log`.
- Local auxiliary worktree branches remain (`agentweave/Architect`, `agentweave/Developer`, `agentweave/Tester`, `agentweave/teste`, and snapshots). They were not deleted because linked worktrees and unrelated dirty/user-owned state require deliberate inspection before branch removal.

## Corrections to the previous handoff

- The previous handoff's active branch and dirty concurrent-run state are obsolete. Work is now integrated on clean `master`, and `master` matches `origin/master` at `4b6adc7`.
- The previous instruction “do not push master” no longer describes current state; the integration was completed and pushed during the resumed closeout.
- `diagnose-and-clear-a-broken-loop` is now 44/48, not a two-task proposal: the implementation and most live verification landed.
- Browser verification is no longer absent; the objective Playwright-capable checks described above were executed.

## Next steps

1. Open `openspec/changes/diagnose-and-clear-a-broken-loop/tasks.md` and inspect its four remaining unchecked tasks; decide whether 9.6 warrants making job history available in the Jobs collection/card or should stay an explicit live-agent operator check.
2. Inspect each linked `.agentweave/worktrees/*` worktree with `git status --short` before deleting or retaining its branch; do not remove linked or dirty worktrees blindly.
3. Decide which incomplete change begins the new development cycle. `loop-notices-and-reacts` is the nearest implemented-loop follow-up; `loop-becomes-a-flow` remains a larger unstarted 60-task change.
4. Run the remaining real-agent checks for `agent-created-documents` and task-dependencies 11.3 when a provider-bound agent is available.
5. Archive an OpenSpec change only after every required task is complete or explicitly waived with evidence; none of the six listed active changes is mechanically complete today.

## Open questions for the user

- Should the next development cycle start with `loop-notices-and-reacts`, `loop-becomes-a-flow`, or a smaller newly proposed change?
- Should Jobs fetch/render run history so broken-loop check 9.6 can be completed from the UI?
- Which linked AgentWeave worktrees are intentionally retained versus safe to retire after inspection?

## Read on resume

- `openspec/changes/diagnose-and-clear-a-broken-loop/tasks.md` — four remaining checks and the closest candidate for completion.
- `openspec/changes/task-dependencies/tasks.md` — three remaining human checks and recorded Playwright evidence.
- `openspec/changes/corpus-aware-documents/tasks.md` — six remaining checks, including subjective and write-bound tests.
- `openspec/changes/loop-notices-and-reacts/tasks.md` — likely next implementation-sized change.
- `openspec/changes/loop-becomes-a-flow/tasks.md` — larger unstarted alternative for the next cycle.
- `.claude/handoffs/handoff-0070-2026-08-21-1624-driving-the-hub-found-seven-defects-and-a-change-to-hold-them.md` — previous state and measured defect provenance.
