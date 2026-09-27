# Test guide — a Copilot run shows its credits

## Agent-verifiable

1. Tasks 1.1–1.18 fail before their implementation tasks and pass after them. Record the failing
   run's output for at least 1.1, 1.10, 1.12, 1.13 and 1.15.
2. `grep -rn "ai_nano_aiu" hub/hub/usage_accounting.py` shows it in the aggregates and the recent
   turns, and `grep -n "ai_nano_aiu\|nano" hub/hub/usage_accounting.py` shows it in **no** expression
   that computes `used_tokens`, `total_tokens` or `budget_state`. Credits never reach the budget.
3. `GET /accounting` on a project with only Claude rows is identical to the pre-change response,
   except for `ai_nano_aiu: null`, `premium_requests: null` and the allowance display's `runner` key.
   Diff the two JSON bodies.
4. `resolve_policy` with no runner, or with a Claude or Codex runner, gives 80 / 70 / 92 (task 1.12).
5. Drive tasks 7.1–7.4 and 7.6 record their figures in design.md's round log: tokens equal the
   per-call sum; the second turn's credits equal the difference of the two session totals; the
   synthetic 66% reading raised a banner for the Copilot agent only.
6. `openspec validate a-copilot-run-shows-its-credits --strict` passes.

## Human-only

1. **Read the numbers.** After a couple of Copilot turns, open Settings → Budgets and a Copilot
   conversation. Do "AI credits" read as information and not as a bill? Is it clear that the budget
   counts tokens only? The credit figures should roughly match what `copilot` shows for the same
   session under `/usage` (the Hub rounds to two decimals).
2. **A mixed project.** With a Claude agent and a Copilot agent in one project, does the Budgets
   headline's allowance line say which provider it describes? Is anything confusing about seeing
   "excludes N turns with no reported cost" next to a credits line (the Copilot turns are the unpriced
   ones)?
3. **The first real quota refusal (work PC, or when this account's allowance runs out).** Does the
   agent's queue show "held until …" with the reset date, and does sending the agent a message try one
   turn? Paste the `session.error` payload from the Hub log into FINDINGS (task 8.2): it is the first
   observation of the refusal's real shape.
4. **The work PC's plan (Business).** Which `quotaSnapshots` key appears in a Copilot run's
   `assistant.usage`, and does a Business refusal carry a `resetDate`? (Design Q4. Without a reset
   date the Hub shows the exhaustion and does not hold, by design.)
5. **Compaction.** In a long Copilot conversation with checkpointing `offered`, does the checkpoint
   warning appear before Copilot compacts (Copilot starts at about 80%, the Hub now warns at 65%)?
6. **Decide Q6.** Is holding a Copilot agent's queue until the 1st of next month what you want after a
   quota refusal on an individual plan, or should it only be shown?
