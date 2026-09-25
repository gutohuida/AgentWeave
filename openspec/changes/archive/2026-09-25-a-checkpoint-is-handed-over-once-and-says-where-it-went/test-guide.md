# Test guide — a checkpoint is handed over once, and says where it went

## Agent-verifiable

1. **Reopening does not re-arm a checkpoint (F293).** Task 1.1 fails before the fix and passes
   after it. The row counts are the evidence: one `handoff` successor and one checkpoint entry.
2. **Two simultaneous presses give one successor (F294).** Task 1.2 fails before the fix and passes
   after it. Exactly one success and one `CutoverRefusedError`. Any other exception type means the
   locking argument in design D3 is wrong. Stop and report; do not widen the catch. The suite runs
   SQLite in WAL mode, but production uses the rollback journal. Task 1.11 runs the same two races
   on an engine with production's defaults and must give the same outcome.
3. **A different checkpoint cannot fork the line (D2).** Tasks 1.3 and 1.4 fail before and pass
   after.
4. **Each guard is load-bearing.** The mutation pair in 1.4 shows which guard catches which race.
   Removing the index fails 1.4 only. Replacing the compare-and-set fails 1.2 only.
5. **Where the checkpoint went is readable.** Task 1.5 checks the model. Task 1.10 checks the route,
   picking the row by id.
6. **Nothing legitimate is refused.** Controls 1.6 (a two-hop chain) and 1.7 (archived by hand,
   reopened, handed over) pass before and after.
7. **The automatic path keeps its checkpoint.** Task 1.12 makes the trigger lose a race to an
   operator's cutover of another checkpoint. Afterwards the generated checkpoint row still exists,
   `cutover_refused` names the successor, and `consider` returns that checkpoint's id rather than
   raising. The rollback expires the session's instances, so reading `checkpoint.id` afterwards
   raises `MissingGreenlet`. Reverting task 2.6 must fail 1.12. A sequential refusal cannot show
   this, because it happens before any write.
7a. **The trigger does not pay for a handover it cannot make (D6).** Task 1.8: a reopened,
   handed-over conversation past its threshold spawns no CLI, writes no checkpoint, requests no
   notes and sends no `due` warning. Task 1.13 (control): the same conversation with a dismissed
   warning still gets the free final warning near the window. Moving the decline above the
   backstop must fail 1.13.
8. **The migration is safe on real data.** Tasks 3.4–3.7. A database that already holds a fork
   still upgrades, and the F329 parity test passes.
9. **Live, on a trial Hub.** Task 4.4 re-drives `t_d2_cutover_guard.py`. Record the verdict counts.

## Human-only

1. **In the app, after the operator's next `:8000` restart** (which applies `0106`): open an
   agent's conversation, use **Handoff**, and confirm that a successor opens as before. Then, in the
   navigation tree, unarchive the old conversation and try the handoff again from it. No second
   *"Continued: …"* conversation may open. Handoff still takes a new checkpoint before it is refused
   (design D6's note); one wasted generation per press is expected. The UI's handoff (`checkpointOperationStore.writeCheckpoint`)
   takes a **new** checkpoint and then cuts over, so this is design D2's case. Note what the app
   shows for the 409. This change does not alter how the UI renders the refusal. If the app shows
   nothing, file that as a finding; it does not fail this change.
2. **Startup log on that restart**, if the migration's log line is visible: the `0106` backfill
   should report `0 set, 0 skipped` (measured read-only on 2026-09-24: no cutover has ever happened
   on that database). Any other number means the database changed since R1. Report it; it does not
   by itself mean a failure.
