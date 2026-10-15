# Test guide — Stop closes the tool card it interrupted

## Agent-verifiable

1. **Stop closes the open call.** Task 1.1 fails before (the rows are `thinking`, `tool_use`,
   `status`, the drive's own sequence) and passes after (a closing `tool_result` with
   `payload.status: "interrupted"` sits between the `tool_use` and the status row).
2. **A failed run closes it too.** Task 1.2, the deadline-cancel outcome.
3. **No second result.** Control 1.3: a call Copilot closed itself keeps exactly one result.
4. **A completed run is left alone.** Control 1.4 (flips to a failing test if `wpc7-c` is (ii)).
5. **Not Copilot-only.** Task 1.5 on the PTY path and on the Codex app-server path (a fake that
   ends the turn with the command item still open).
6. **The card reads "interrupted" without a closing row.** Task 1.6, the DB's three rows as they
   are; this is what every run recorded before the change shows.
7. **The closing row is not a failure.** Task 1.7: `interrupted`, and no `failed` count in the
   work-block header.
8. **A completed run's unanswered call says so.** Task 1.8 reads `no result`.
9. **Nothing else moves.** Control 1.9 (a new test: no result in the turn, `runs={{}}`, still
   reads `awaiting result`), control 1.13 (a result with no call in its turn still renders), and
   the full `pytest hub/tests/ -q` and `npx vitest run`.
10. **A notice between the call and the stop.** Task 1.10: the outputs read `tool_use`,
    `diagnostic`, closing `tool_result`, `status`, in the order the outputs route returns them.
11. **A result in another work block is the call's result.** Task 1.11, the rows of
    `run-08d33fa23f8e` in route order: the `edit` card reads `completed` (not `no result`, not
    `awaiting result`) and no orphan result row is shown. Under `wpc7-d` (i).
12. **A closing row after a notice is still one card.** Task 1.12: one `interrupted` card, no
    separate result row, no `failed` count.
13. **The per-block pairing test is inverted.** Task 1.14: the existing cross-block test now reads
    `completed`. It is the only existing UI test whose assertion changes.
14. **A second result, or another run's result, does not take over the card.** Control 1.15: the
    first result pairs and a later one shows as its own row; a reused call id in a later run does
    not pick up the earlier run's result.

## Human-only

1. On a trial Hub with a real Copilot agent, ask it to run `Start-Sleep -Seconds 240; echo done`
   in the shell. While the card reads `awaiting result`, press **Stop**. The card changes to
   `interrupted` without a reload, and the turn ends `Run stopped`. The work-block header shows no
   red failure count.
2. Reload the page. The card still reads `interrupted`.
3. Open a run stopped before this change. Its dangling card now reads `interrupted` too.
4. Let a shell command finish normally, then let the turn complete. Its card reads `completed`, as
   before.
5. Open `run-08d33fa23f8e` on the trial Hub (a completed run whose `edit` result came after a
   Copilot notice). Today its `edit` card reads `awaiting result` with an orphan result row below;
   after the change (under `wpc7-d` (i)) it reads `completed` and the orphan is gone.
6. With a real Codex app-server agent, press **Stop** while a shell command is running (task 3.4).
   Record whether Codex itself reported the item, and with what status, and check the card reads
   `interrupted` or `failed` but never `awaiting result`.
