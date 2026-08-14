# What a failure tells the operator

## Why

Loop 8 (`openspec/explorations/2026-08-14-loop8-a-dead-runtime-eats-the-message.md`) drove the
product from zero to a merged library. Alongside the data loss that
`2026-08-14-a-failed-run-does-not-eat-its-input` fixes, it found five smaller defects with one thing
in common: **the system knows the fact and does not say it, or says something that is not true.**
None changes control flow; all of them cost the operator time.

**A skip instructs the operator to do the one thing that cannot work.** `CHECKOUT_DIRTY` says
*"commit or stash them and the next approval will merge"*. The task is already `approved` by the time
anyone reads that, and restating a status is a deliberate no-op. Verified: committed the dirt,
re-approved → 200, status `approved`, no new attempt, `master` unmoved. The retry route added by
`2026-08-14-the-seams-loop7-found` then merged it immediately — so the remedy exists, and the message
points away from it. `CHECKOUT_ELSEWHERE` carries the same wording.

**One death reports two exit codes.** `runs.error` said `exit 4294967295`; the `run_failed` payload
said `exit_code: 1`. The first is `0xFFFFFFFF`, the unsigned reading of Windows' `-1` from a forced
termination; the second is the synthetic 0/1 the output panel reads. Both are defensible alone and
together they are a puzzle.

**`stderr_tail` never reaches anyone.** `2026-08-14-the-seams-loop7-found` set out to report three
facts about a dead runtime — exit code, in-flight method, stderr tail. `_transport_failure_fields`
(`agent_trigger.py:1013-1018`) has no `stderr_tail` key at all, and `TurnOutcome` does not carry one,
so the tail can only surface by being composed into `str(exc)`. It was empty on all four real
failures in loop 8. **Only `method` arrived** — and it arrived well, which is what makes the gap
worth closing rather than redesigning.

**`ui_stale` names a command that does not exist here.** It says *"Run `make ui`"*. `make` is on PATH
in neither Git Bash nor PowerShell on this machine; `CLAUDE.md` already records that and names
`python scripts/refresh_ui_bundle.py` instead. A warning whose instruction cannot be followed teaches
the operator to ignore it.

**`requirement_ids` sorts lexicographically** — `FR-1, FR-11, FR-2, FR-3` on a task card. The data is
right and the order reads as a bug, which costs a diagnosis every time someone checks whether a task
is linked to what they think it is.

## What changes

1. **The dirty-checkout and wrong-branch skips point at the retry that works**, not at an approval
   that is a no-op.
2. **A failed run reports the runtime's own exit status** as `runtime_exit_code`, alongside the
   existing synthetic `exit_code` rather than replacing it.
3. **An exit status a person can read.** A value above `2**31` is rendered in its signed form, so a
   forced termination reports `-1` rather than `4294967295`.
4. **The stderr tail is delivered** — added to the transport-failure fields, carried on
   `TurnOutcome`, and included in the normal path's failure broadcast.
5. **`ui_stale` names a command that exists on this machine.**
6. **Requirement identifiers sort naturally**, so `FR-2` precedes `FR-11`.

## Archive ordering

Every requirement below is **added** by changes that have not reached the main spec yet. Applied out
of order the modifications have nothing to modify. Full order for the six now outstanding:

1. `2026-08-13-approved-means-it-is-in-the-product`
2. `2026-08-14-what-the-product-actually-built`
3. `2026-08-14-the-loop-agents-can-drive`
4. `2026-08-14-the-seams-loop7-found`
5. `2026-08-14-a-failed-run-does-not-eat-its-input`
6. this change

This change is last because it is the only one with no behavioural risk; it must not be what a
revert of the earlier ones has to be untangled from.

## Non-goals

- **Repurposing `exit_code`.** `AgentOutputPanel.tsx` detects a handoff by reading the synthetic 0/1,
  and the "Run {status} (exit {code})" status line derives from it. Changing its meaning would break
  a working feature silently, which is exactly the class of defect this change exists to remove.
- **Normalising exit codes anywhere but at the point of display.** The raw value is what the OS
  reported and stays available.
- **Finding 8** — a spec document asserting "Open questions: None outstanding" about an area the
  operator never addressed. Recorded in the exploration; a question about what a spec may claim, not
  a defect in this code.
- **Finding 9** — nothing in the chain asks whether the merged artefact is usable. The widest of the
  findings and the one most likely to want an exploration of its own.
