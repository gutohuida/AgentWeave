# Proposal — a runner that cannot collaborate says so where it is bound

**Round 1, 2026-09-24** (bundle B10, decision D6, surface "launchability card"). Finding: **F178 (B)**,
re-verified on HEAD `404c7d5` (worktree `ce086b6`). **Its shape changed on 2026-09-23. Nothing here
is implemented yet.**

## Why

F178 said that the launchability report the Hub computes reaches no screen. **Half of that is fixed**:
F179's repair (UI-1, 2026-09-23) mounted `useAgentLaunchability` in `RunnerPicker`
(`hub/ui/src/components/agents/AgentSettingsControls.tsx:225-275`). The agent's Execution settings
now show `runnable: false` with the Hub's reason. `grep -rn useAgentLaunchability hub/ui/src`
(excluding tests) finds that one caller.

**The other half is still open, and it is the half F178 was filed about.** `collaboration_ready` and
`collaboration_reason` (`hub/hub/api/v1/agents.py:236-270`) are fetched by the same query and
rendered nowhere. Their only renderer is `AgentCard` (`hub/ui/src/components/agents/AgentCard.tsx`).
Only `hub/ui/src/__tests__/agentCardCollaboration.test.tsx` imports it, so it has been unreachable
since `e4958fc` (2026-08-08). The sentence that goes unseen:

> *This Codex agent's runner opted out of the app-server transport (flags: ["--no-app-server"]) and
> does not have yolo enabled, so it falls back to classic exec — AgentWeave tool calls
> (send_message, etc.) will be silently denied with no operator present to approve them.*
> (`agents.py:257-262`)

That agent passes every check the screen shows, and every tool call it makes is denied without a
word. `runtime-diagnostics`' *"Collaboration readiness is checkable before it is needed"* requires
each unmet condition to be named *"in terms an operator can act on"*. The API names it and no
operator sees it.

**Which verdicts can reach the screen.** `collaboration_ready` is `false` in two cases: the Hub does
not know its callback address (`agents.py:242-248`), or a Codex runner opted out of the app-server
(`:249-262`). The first cannot reach the UI. `bound_address.known()` is true once any HTTP request
has been served (`hub/hub/main.py:516-520`, the `_observe_bound_address` middleware), and the
launchability request is itself such a request. So from the app, the Codex opt-out is the case that
shows. The first case is still rendered the same way if it ever arrives.

## What changes

1. `RunnerPicker` renders `This agent will run, but cannot collaborate: <collaboration_reason>` as a
   `role="status"` line under the control when the verdict is `runnable: true` and
   `collaboration_ready === false`. It uses the same query and verdict it already reads. `null`
   means "not applicable" (`api/agents.ts:51-54`) and renders nothing.
2. **`AgentCard.tsx` and `agentCardCollaboration.test.tsx` are deleted.** The card is unreachable,
   and its one unique fact moves to (1). Its other content (status, model, message and task counts,
   context usage) is shown by the rail and the conversation header already. The stale mention in
   `hub/ui/src/lib/agentStatusConfig.ts:3` is corrected.
3. `agents.py`'s `get_agents_launchability` docstring, *"Feeds launchability indicators in the
   agent/runner selector"*, is corrected to name the Execution settings' runner picker.

## What does not change

- The launchability route and its payload are unchanged.
- No new query and no new call site: `RunnerPicker` already reads the verdict and already handles a
  failed read (`AgentSettingsControls.tsx:258-263`). The `n11` counts do not move.

## Impact

- `hub/ui/src/components/agents/AgentSettingsControls.tsx`, one new test file, two deleted files,
  and the bundle.
- `hub/hub/api/v1/agents.py` (docstring only).
- Spec: `runtime-diagnostics`, one ADDED requirement.
