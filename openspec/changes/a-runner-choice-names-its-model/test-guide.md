# Test guide — a runner choice names its model

## Agent-verifiable

1. Tasks 1.1–1.3 fail before task 2.2 and pass after it.
2. `grep -rn "runner.name}" hub/ui/src/components` finds no `<option>` that renders a runner
   without `runnerOptionLabel`.
3. The option texts recorded verbatim in task 3.1 differ for the two `Twin` runners.

## Human-only

1. Open an agent's Settings on a project holding two runners with the same name and different
   models. Can you tell from the select alone which one runs which model?
2. Open project settings. The checkpoint-runner and title-runner selects should read the same way.
3. Check that the labels are not so long that the settings selects (`w-48`) become unreadable. If
   they are, say so. The fix would be a wider select, not a shorter label.
