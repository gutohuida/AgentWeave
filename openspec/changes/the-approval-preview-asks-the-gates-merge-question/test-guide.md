# Test guide — the approval preview asks the gate's merge question

## Agent-verifiable

1. **The conflict is known before approve.** 1.1 fails today.
2. **Preview and refusal agree.** 1.2.
3. **It is fresh.** 1.3: resolving and re-evidencing clears it with nothing persisted to clear.
4. **Where it cannot ask, it says so and does not fail.** 1.4, 1.5.
5. **The repository is untouched by asking.** 1.1's `git status` and `main` HEAD checks.

## Human-only

1. Open a task under review whose branch conflicts with the main branch. Before pressing Approve,
   the note beside it should say approval would be refused and name the file. Press Approve anyway:
   the refusal names the same file.
2. Resolve the conflict on the branch and have the evidence re-recorded and accepted. Reopen the
   drawer: the note says it merges cleanly.
