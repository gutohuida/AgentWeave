# Tasks — agent messaging delivery

Ordered so that each section ends with a live check, not only a unit test. This change exists
because unit tests passed while the feature was completely broken in reality.

## 1. Establish how Codex approval is actually granted

- [ ] 1.1 Determine empirically, against the installed Codex CLI, which configuration grants
      non-interactive MCP tool approval for one named server. Run real `codex exec` invocations with
      candidate `-c` overrides and a registered MCP server; record the exact commands tried and
      their outcomes. `approvals_reviewer` in `~/.codex/config.toml` is a candidate, not an answer.
- [ ] 1.2 Record the finding — including the Codex version it was verified against — in
      `design.md` and in a comment at the construction site. Do not commit an unverified key.
- [ ] 1.3 If no such configuration exists on this version, implement the Decision 1 fallback instead:
      detect the condition at spawn time and record a diagnostic. Mark 1.4-1.6 not-applicable with
      that reason rather than leaving them silently unchecked.

## 2. Make the Codex tool surface invocable

- [ ] 2.1 Apply the verified approval configuration in `_build_codex_command`
      (`hub/hub/runner_commands.py`), in the same `-c` block that already registers the server.
- [ ] 2.2 Confirm sandbox flag selection is untouched: a non-`yolo` run still passes
      `--sandbox workspace-write`, a `yolo` run still passes the bypass flag.
- [ ] 2.3 Unit test: a non-`yolo` codex command carries both the approval configuration and
      `--sandbox workspace-write`.
- [ ] 2.4 Unit test: the approval configuration names only the AgentWeave server and grants nothing
      globally.
- [ ] 2.5 Check whether the Claude runner has the same defect. If it does, fix it in the same way
      and add the matching tests; if it does not, record how that was established.
- [ ] 2.6 **Live:** trigger a non-`yolo` codex agent to `send_message` another agent. Its transcript
      shows the call completing, with no "cancelled" line.

## 3. Derive the callback address from the served address

- [ ] 3.1 Capture the Hub's actually-bound address during startup (lifespan) and store it on
      application state.
- [ ] 3.2 In `hub/hub/api/v1/agent_trigger.py`, build `HUB_URL` from: explicit operator `HUB_URL`
      first, then the captured bound address. Remove the `settings.aw_port` fallback entirely.
- [ ] 3.3 Raise a typed trigger error, with the reason recorded, when neither source is available.
- [ ] 3.4 Unit test: a Hub bound to a non-default port supplies that port to a run.
- [ ] 3.5 Unit test: an explicit `HUB_URL` takes precedence over the observed address.
- [ ] 3.6 Unit test: with neither available, starting a run fails and records the reason.
- [ ] 3.7 Regression test asserting no code path reaches `settings.aw_port` to build a run's callback
      address.
- [ ] 3.8 **Live:** with the Hub on `8010` and something else on `8000`, a triggered agent's tool
      call reaches `8010`. This is the exact reproduction from `design.md`.

## 4. Scope run credentials to the issuing instance

- [ ] 4.1 Give each Hub instance a stable identity and carry it in the minted run credential.
- [ ] 4.2 In `hub/hub/agent_auth.py`, reject a credential whose instance identity is not this
      instance's, with a distinct, diagnosable reason separate from "expired" or "unknown run".
- [ ] 4.3 Unit test: a credential minted by another instance is refused and writes nothing.
- [ ] 4.4 Unit test: an ordinary same-instance credential is unaffected.

## 5. Make failures visible

- [ ] 5.1 In `hub/hub/mcp_server.py`, include the attempted endpoint in `HubAPIError` and connection
      error text.
- [ ] 5.2 Distinguish, in the message the agent receives, a rejected request from an unreachable or
      unintended destination.
- [ ] 5.3 Record an event on the causing agent's timeline when the Hub observes a tool call fail.
- [ ] 5.4 Unit test: a failing tool call produces an error naming the endpoint.
- [ ] 5.5 Unit test: an observed failure appears as a timeline event with its reason.
- [ ] 5.6 **Live:** trigger a `send_message` to a non-existent recipient; confirm the operator can
      see the failure and its reason in the UI without reading a transcript.

## 6. Collaboration readiness reporting

- [ ] 6.1 Extend the readiness surface with a collaboration-ready determination per agent, covering
      tool-surface invocability and callback-address agreement.
- [ ] 6.2 Ensure the check starts no agent run.
- [ ] 6.3 Unit tests for each unmet condition and for the all-clear case.
- [ ] 6.4 Surface the result where the operator already looks at agent readiness.

## 7. Runner name mojibake

- [ ] 7.1 Locate where the double-encoding occurs — name construction in `hub/hub/api/v1/agents.py`,
      the database write, or response serialisation. Establish which before changing anything.
- [ ] 7.2 Fix at that layer.
- [ ] 7.3 Decide and implement what happens to already-stored mis-encoded names (repair migration or
      regeneration); record the decision.
- [ ] 7.4 Unit test: an auto-provisioned runner name round-trips a non-ASCII character through the
      API unchanged.

## 8. End-to-end verification

- [ ] 8.1 `pytest hub/tests -q` — full pass, count recorded.
- [ ] 8.2 `npm test -- --run` and `npx tsc --noEmit` in `hub/ui` — clean (only if UI files changed).
- [ ] 8.3 **Live, the original failure:** on a Hub started on a non-default port, with two
      default-configuration (non-`yolo`) codex agents, ask agent one to message agent two. Confirm:
      the tool call completes; the message row exists with the right sender, recipient, and project;
      a queue entry was created for the recipient; and the recipient is scheduled for a turn.
- [ ] 8.4 **Live:** the recipient actually runs its turn and its transcript contains the message.
- [ ] 8.5 **Live:** repeat 8.3 with two claude agents.
- [ ] 8.6 **Live:** repeat 8.3 across providers — a codex agent messaging a claude agent.
- [ ] 8.7 Confirm the sandbox is still in force during 8.3 (a non-`yolo` agent still cannot write
      outside its workspace).
- [ ] 8.8 `openspec validate 2026-08-06-agent-messaging-delivery --strict` — clean.
