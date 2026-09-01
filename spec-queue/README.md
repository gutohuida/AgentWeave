# `spec-queue/` — where the daily loop and the operator meet

Three processes read and write this directory, and only one of them is a person. The contract below
is what keeps them from misreading each other.

Design: `openspec/explorations/2026-09-01-a-daily-research-spec-and-build-loop.md`.

## The cycle

```
09:00 - 17:00   FILL      AgentWeaveDayLoop      writes research/ and review/
17:00 - 23:00   DECIDE    the operator           writes APPROVALS.md
23:00 - 07:00   FIX       AgentWeaveNightLoop    reads APPROVALS.md, builds
07:00 - 09:00   margin    (07:57 is ClaudeAIDigest, unrelated and untouched)
```

## The files

| Path | Written by | Read by |
|---|---|---|
| `APPROVALS.md` | the DECIDE session | the FIX window, and nothing else |
| `DIRECTION.md` | the operator, or a DECIDE session on their behalf | the FILL window, and nothing else |
| `DECISIONS.md` | both windows *add* rows; only the operator marks one DECIDED | the DECIDE session, and any window deciding what it may take alone |
| `research/YYYY-MM-DD.md` | the FILL window | the DECIDE session, and tomorrow's FILL |
| `review/review-YYYY-MM-DD.html` | the FILL window | the operator, via an Artifact published in the DECIDE session |

`DIRECTION.md` exists because `APPROVALS.md` steers only the night. Until 2026-09-01 the day
window had no operator channel at all, so steering a day meant editing the loop's own standing
instructions and remembering to un-edit them. Same contract as `APPROVALS.md`: newest day first,
only the newest section is read, and absence means "compose as usual" rather than "stop".

`DECISIONS.md` exists because the backlog used to live only in `STATE-night.json`, which each window
rewrites — so it survived by being copied forward by hand, and by 2026-09-01 had drifted into 32
entries containing duplicates and answered rows. A window that finds a question it may not answer
alone appends a row there instead of growing its own state file.

## The `APPROVALS.md` contract

**One line per change. The status token is the authority.** There is deliberately no checkbox: a
file where `[x]` and `REJECTED` can disagree is a file that will eventually disagree, at 23:00, with
nobody awake to resolve it.

```
- APPROVED  <change-name>   optional note
- REVISING  <change-name>   what needs to change
- REJECTED  <change-name>   why
```

`<change-name>` is the directory name under `openspec/changes/`, exactly.

**The FIX window builds `APPROVED` rows and nothing else.** `REVISING` means the FILL window should
take another round at it tomorrow. `REJECTED` means archive the proposal unbuilt.

Two optional directives, each on its own line under the day's heading:

```
ORDER: <change-name>, <change-name>, F156
NOTHING TONIGHT
```

`ORDER` overrides the default queue for that night only. `NOTHING TONIGHT` stops the FIX window
before it spends a model invocation — use it when the tree is in a state you would rather nobody
touched.

**Absence is not rejection.** A change with no row is simply undecided; it stays in
`openspec/changes/` and reappears in tomorrow's review page. An empty section, or no section for
today at all, means the FIX window spends the whole window on the backlog. That is the correct
behaviour on a day the operator never sat down, and it needs no special case.

## The default queue, when nothing overrides it

Decided 2026-09-01: **backlog first.** In order —

1. Unarchived changes in `openspec/changes/` that are implemented and only need archiving. Read
   `a-conflict-refusal-names-what-clears-it`'s task 6.4a first: its ordering constraint is real.
2. Open findings in `scripts/drive/FINDINGS.md`, severity A before B before C.
3. `APPROVED` rows from `APPROVALS.md`.

The rejected alternative was approved-first, which gives faster feedback on the new pipeline but
would have let 8 unarchived changes and 173 findings rot while the loop shipped new ideas.

## What is not in here

- **Specs.** They live in `openspec/changes/<name>/`, decided 2026-09-01. Never in both systems.
- **The loop's own logs and position.** Those are `.claude/autonomous/STATE-day.json`,
  `STATE-night.json` and the per-window logs beside them.
- **Findings.** `scripts/drive/FINDINGS.md`, as always.
