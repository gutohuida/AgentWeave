# Autonomous run — Archive, the Hub app, and what's next

**Branch:** `autonomous/2026-08-17-archive-and-hub-app` from `master` @ `5e63004`
**Window:** 19:35 → 22:00, 2026-08-17
**Driver:** Windows Scheduled Task running headless `claude -p`, one iteration per firing.

Newest entry at the bottom.

---

## 19:35 — Set up, by the interactive session

The operator left at ~19:08 asking for a run to 22:00 with four objectives, in order: push a
version with the session's changes, implement the Archive change, work on the Hub app, and if time
allows draft a roadmap.

**Objective 1 was done here, on `master`, not handed to the loop.** Two reasons, and the second is
the important one:

1. It is outward-facing and irreversible — a PyPI publish cannot be taken back — and this skill's
   own limits forbid exactly that unattended. The operator's instruction overrode the limit, but
   the safer reading of "be careful" is to keep the irreversible step attended rather than to hand
   a release to a headless process.
2. It needed the context. The five pieces of work in 1.0.1 were built over the afternoon with the
   operator; the commit messages explaining *why* each exists could not have been written from the
   diff alone.

What landed on master, four commits plus a fix:

| | |
|---|---|
| `1ac0c4d` | Spec renderer colours by meaning — phase, unresolved questions, evidence limits, and a summary line above the fold |
| `6aa600f` | A turn no longer ends with its cost; the figure still reaches the accounting tables |
| `23fbf75` | Work block, ticket and command palette — the legibility work |
| `0f6bcc3` | Release 1.0.1 — both `pyproject.toml` versions and a CHANGELOG entry |
| `5e63004` | Moved the edit-diff parse out of the component file |

**A failure worth recording.** `0f6bcc3` went red on CI. `ui-test` runs `npm run lint` at
`--max-warnings 0`, and I had only run `npm test` — 957 passing tests and a red build. Exporting
`editDiffStat` from `ToolEditDiff.tsx` broke `react-refresh/only-export-components`. The rule was
right and the parse moved to `@/lib/editDiff` rather than the warning being suppressed. **This is
now a standing limit in `STATE.json`: run lint before pushing UI work.** It is the cheapest lesson
in this file and the easiest to repeat.

**Not verified at the time of writing:** CI on `5e63004` was still running when this branch was
cut. The tag and release are gated on it being green; if it is red, there is no v1.0.1 and the
first iteration should say so rather than assume.

**Left for the loop:** A1 Archive confirmation, A2 archived-is-visible, A3 the Hub app
(`2026-08-16-one-hub-and-a-window-of-its-own`, 0/34), A4 a roadmap if time remains.

**Fixture note.** `spec/changes/quiet-hours-for-agent-notifications/spec.html` exists untracked at
the repo root — a document seeded this afternoon for the taste pass, in the otherwise-empty
`AgentWeave` project. It is there deliberately for A2 to archive. `CLAUDE.md` forbids committing
`spec/` at the root; leave it untracked. `aw-loop10` is the operator's real trial data and is not
to be touched.

---

## 19:45 — Objective 1 is done: v1.0.1 is released and verified

CI went fully green on `5e63004` (`hub-test` included), so the tag was created on the commit CI
actually tested rather than on whatever `master` happened to be.

- Tag `v1.0.1` → `5e63004`, release published.
- `Publish to PyPI` green, and the ordering held: `publish-hub` finished 18:21:39Z, `publish`
  started 18:21:42Z, so the dependency was on the index before the dependent was uploaded.
- `Publish Hub Docker image` green.
- **Verified as an artefact, not as a green tick**: a clean venv installed `agentweave-ai==1.0.1`
  from real PyPI and `agentweave --version` reports 1.0.1.

**A defect found by that verification, recorded as D4 and deliberately NOT fixed here.** The clean
install pulled `agentweave-hub` **1.0.0**, not 1.0.1, and pip was satisfied: `pyproject.toml` pins
`agentweave-hub>=1.0.0`. Almost everything in 1.0.1 — the UI bundle, `spec_render.py`,
`runner_parsing.py` — ships in the *hub* package, so `pip install --upgrade agentweave-ai` can
leave an upgrader running 1.0.0's Hub with none of the release. Both are on the index now, so a
fresh install today is fine; the exposure is upgraders. Fixing it means another release, which is
outward-facing and therefore not this run's to make.

The index also lagged again, exactly as it did for 1.0.0: the JSON API and the simple index both
served the old version for a minute or so after a successful upload. Worth knowing before
concluding a publish failed.

**Handing over now.** The driver is installed and armed; `last_heartbeat` is backdated so the first
firing takes the branch rather than standing down. A1 is next.

---

## 19:27 — Iteration 1: A1, and a real-time collision with the tail of the handover

**A1 done.** `SpecPhaseBar.tsx`'s Archive button (approved-only, confirmed present already) now
opens `ArchiveConfirmDialog.tsx` — a new component, modelled on `DeleteProjectDialog.tsx`'s modal
shape (`useDialogFocus`, `role="dialog"`, scrim) but with a single Confirm click rather than
type-to-confirm, since archiving one document is a lighter action than deleting a project's entire
history. The dialog names the document by title and states plainly that archiving cannot be undone.
Cancel leaves the phase untouched — `setPhase.mutate` is now called only from the dialog's Confirm,
never from the Archive button directly. Updated the one existing test that assumed a direct archive
and added two more (cancel leaves phase untouched; confirm calls the phase route). Ran, in CI's own
order: `npm run lint` (clean), `npx tsc --noEmit` (clean), `npm test` (959/959, the two "Error: boom"
lines are `ErrorBoundary.test.tsx` deliberately throwing). Rebuilt the UI bundle and committed
`hub/ui/src` and `hub/hub/static/ui` together, as required.

**A real-time collision with the tail of the interactive session's handover, caught and fixed
before anything shipped wrong.** This iteration started at 19:17:40, essentially the same instant
the entry above says the interactive session was "handing over" — and that session's actual final
commit (`5d8c7af`, 19:25:42) landed *during* this iteration's work, not before it. Two consequences,
both caught:

1. **The branch briefly moved to `master` mid-turn**, invisible to me because nothing I ran issued
   a checkout — reflog shows the switch at 19:20:12, which is inside the window the other session
   was tagging and verifying `v1.0.1` on `master`. My own `git commit` for A1 landed on `master` as
   a result (visible only after the fact, since the commit succeeded silently). Caught immediately
   by checking `git branch --show-current` right after the commit instead of trusting the check from
   the top of the turn: cherry-picked the commit onto this branch (`510e21e`), then force-moved the
   local `master` ref back to `origin/master` (a local-only correction — `master` had not been
   pushed with the stray commit, confirmed via `git fetch` before touching it).
2. **The UI build stamp recorded the wrong `src_commit`** (`5e63004`, `master`'s tip at that instant)
   because `refresh_ui_bundle.py` shells out to `git rev-parse HEAD` at write time, and HEAD had
   already moved by the time it ran — even though the copied bundle assets were themselves correct
   (verified byte-identical on rebuild). Re-ran the script once HEAD was confirmed back on this
   branch and committed the corrected stamp (`6f87eff`).

Both fixes pushed clean, `refresh_ui_bundle.py --check` now passes. No data was lost and nothing
shipped wrong — the underlying cause was two processes (this loop and the interactive session's own
tail end) sharing one working directory during a handover window, not a bug in the archive-confirm
work itself. Worth a driver-level fix if this repeats: a Bash tool call to `git checkout` or
`git commit` should re-verify the branch immediately beforehand rather than relying on a check from
the top of the turn, and this is now standing practice for every iteration after this one.

**A2 is next** — the queue's own item, unstarted this iteration.
