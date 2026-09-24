# Test guide — a retried firing records how its work ended

## Agent-verifiable

1. **A crash no longer writes off a firing that its retry completes.** Task 1.1 fails before
   (`failed` after the startup pair) and passes after. Reversing D2 or D4 fails it again.
2. **An ordinary failed attempt does not either.** Task 1.2 fails before and passes after.
3. **Giving up still concludes, with the reason.** Tasks 1.3 and 1.5.
4. **The operator's withdrawal concludes as stopped**, and a failure to conclude does not turn a
   withdrawal that happened into a 500. Tasks 1.6 and 1.7.
5. **The reaper asks about every attempt.** Task 1.4, seeded by `started_at` so that insertion order
   cannot make it pass (R2: today's `.first()` is always the earliest-started run).
6. **Scope: job input only, every open row.** Tasks 1.9 and 1.10.
7. **Nothing else moved, except on purpose.** Controls 1.8; 1.8a moves or stays by Open Question 3;
   1.8b awaits the retries a spawn failure now gets. The full-suite count in 2.5 names any other move.
8. **Live.** Task 3.1: `t_row19_crash_job.py` shows `completed` on the firing after the restart.

## Human-only

1. On a trial Hub, fire a job by hand and kill the Hub while its agent is working. Start it again
   and wait for the agent to finish. Open the job's history on the Jobs page: the firing reads
   **completed**, not failed. (Before this change it read *"Reconciled on Hub start: no live run
   behind this firing"* in red.)
2. While a firing's input waits to be retried, its row reads **in_progress** in grey, and the loop is
   not shown as firing. That is expected: the work is not done and not failed.
