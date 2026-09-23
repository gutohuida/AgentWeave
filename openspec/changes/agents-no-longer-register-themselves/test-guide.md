# Test guide — agents no longer register themselves

## Agent-verifiable

1. **The route is gone.** Task 1.2 fails before, passes after.
2. **No agent is named as its own CLI.** Task 1.3 — the negative assertion on `Runner CLI '<name>'`
   is the one that matters; restoring `not agent_row.self_registered` at `launchability.py:507` must
   fail it (check the mutation by hand once).
3. **The vocabulary is gone from every response.** Tasks 1.4, 1.5; plus
   `grep -rn "watchdog-spawn\|contact_mode\|self_registered" hub/hub src/agentweave hub/ui/src`
   returns only migration files after group 2.
4. **The suite does not need a runner CLI to make an agent.** Full `hub/tests/` with `claude`
   stripped from PATH passes (task 3.1).
5. **The migration round-trips.** Task 1.6.

## Human-only

1. After the operator restarts `:8000` on this code (their decision, not an agent's), the roster,
   agent settings and conversation views load with no console errors — the four fields vanished
   from the payload and only a component nothing mounts rendered one of them.
2. An agent created from the Add-agent dialog behaves exactly as before.
