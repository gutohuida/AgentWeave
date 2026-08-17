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
