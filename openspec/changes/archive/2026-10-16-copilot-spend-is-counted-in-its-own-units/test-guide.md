# Test guide — Copilot spend is counted in its own units

## Agent-verifiable

1. **A Copilot checkpoint's credits reach the project totals.** Task 1.1 uses the drive's own
   figures: 19 premium requests and 154.00 AI credits become 21 and 155.92. Task 1.11 runs the same
   check through the real captured envelope and `run_worker`.
2. **A credited call is not reported as "no usage".** Tasks 1.2 and 1.3. A timed-out call that
   reported nothing is still counted as unmeasured. Task 1.14 checks that a manager job's kind is
   counted the same way as a checkpoint.
3. **The budget does not move.** Control 1.5 checks the token total, `used_tokens`, and the
   PATCH response.
4. **Agents and conversations are unchanged.** Controls 1.4 and 1.6.
5. **An all-Copilot project's headline names credits.** Task 1.7, which also covers a Codex project
   whose only Copilot spend is its checkpoints, and a refused Copilot turn's charge. The precedence
   controls are in 1.8.
6. **The `'null'` allowance is harmless.** Control 1.9 pins both the storage and the fact that
   nothing reads it as a reading.
7. **No existing contract regresses.** Task 1.10, and the full suites in 2.9.
8. **The dashboard says it.** Tasks 1.12 and 1.13.
9. **A Copilot title records its credits.** Task 1.15.
10. **The project's credits are the sum of what the panel lists.** Task 1.16: project = agents +
    workers, for both figures.
11. **A credited call that did not parse still counts its credits.** Task 1.17.
12. **Live.** Task 3.1 reconciles `GET /accounting` against the raw `turn_usage` and
    `worker_invocations` sums on a trial Hub.

## Human-only

1. On a trial Hub, run a Copilot agent until a checkpoint is written. Open the accounting (Budgets) panel.
   - The credits line counts the checkpoint's premium requests: turns plus 2 for a checkpoint and
     its probe.
   - The `checkpoint` and `checkpoint_probe` worker lines each show their AI credits and
     "1 premium request". Neither shows "usage unavailable".
2. Open the project **Overview**.
   - The AI-credits row shows the same figure as Budgets.
   - The row below it reads "Copilot AI credits · no allowance reported", not "Tokens". This holds
     unless your Copilot licence reports a quota; if it does, that allowance shows instead.
3. Compare with GitHub's own Copilot usage page for the same period. The premium-request count
   should match turns plus worker calls. AgentWeave cannot read GitHub's figure itself, so this check
   is only for you.
