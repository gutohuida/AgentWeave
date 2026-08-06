# Tasks — agent messaging delivery

Ordered so that each section ends with a live check, not only a unit test. This change exists
because unit tests passed while the feature was completely broken in reality.

## 1. Establish how Codex approval is actually granted

- [x] 1.1 Determine empirically which configuration grants non-interactive MCP tool approval.
      **Done 2026-08-06 against Codex CLI 0.146.0** using a throwaway one-tool MCP server. Full
      results table in `design.md` Decision 1.
- [x] 1.2 Record the finding and the version it was verified against — in `design.md`. Still to be
      repeated as a comment at the construction site when 2.1 lands.
- [x] 1.3 Establish whether a sandbox-preserving configuration exists **within `codex exec`**. It
      does not: `auto_review`, `guardian_subagent`, and `danger-full-access` all permit writes
      outside the workspace, verified by direct breach test, and no per-server MCP trust key exists.
- [x] 1.4 Establish whether another Codex transport avoids the trade. **`codex app-server` does.**
      Verified by driving the real JSON-RPC protocol: MCP tool calls arrive as a distinct
      client-answerable request identifying the server, and approving one does not approve a
      sandbox escape. See `design.md` Decision 1a. This is what section 2 implements.

## 2. Move the Codex runner to the app-server protocol

Verified in `design.md` Decision 1a: `app-server` sends each approval to the client as a distinct
request, so the Hub can approve its own MCP server's tool calls and deny everything else. The
sandbox is fully preserved. This replaces the trade `exec` would have forced.

Land section 3 first — it is independent, smaller, and fixes mis-delivery on its own.

- [ ] 2.1 Add an app-server client: spawn `codex app-server`, speak JSON-RPC over stdio, handle
      `initialize` / `initialized` / `thread/start` / `turn/start`, and answer server→client
      requests. Registering the AgentWeave MCP server keeps its existing `-c` form.
- [ ] 2.2 Approve `mcpServer/elicitation/request` **only** when `_meta.codex_approval_kind` is
      `mcp_tool_call` and `serverName` is the Hub's own server. Anything else is denied.
- [ ] 2.3 Answer `item/commandExecution/requestApproval`, `item/fileChange/requestApproval`, and
      `item/permissions/requestApproval` from the operator's selected sandbox — `yolo` approves,
      otherwise deny. `yolo` keeps its current meaning and is not required for messaging.
- [ ] 2.4 Deny any server→client request the Hub does not recognise. An unrecognised approval is
      never granted by default.
- [ ] 2.5 Map protocol events onto the existing output/timeline/usage model, replacing the
      `--json` stdout parsing in `runner_parsing.py` for this path.
- [ ] 2.6 Preserve session resume via `thread/resume`, keeping the durable session identity agents
      already rely on.
- [ ] 2.7 Handle process death, a hung turn, and `turn/interrupt` so a stuck app-server cannot wedge
      an agent.
- [ ] 2.8 Keep the `exec` path intact and selectable until 8.x proves the app-server path
      equivalent. Do not delete it in this change.
- [ ] 2.9 Unit test: an MCP elicitation for the Hub's own server is approved.
- [ ] 2.10 Unit test: an MCP elicitation naming a *different* server is denied.
- [ ] 2.11 Unit test: command-execution and file-change approvals are denied for a non-`yolo` run
      and approved for a `yolo` run.
- [ ] 2.12 Unit test: an unrecognised server→client request is denied.
- [ ] 2.13 Unit test: `yolo` is not required for a tool call to be approved.
- [ ] 2.14 **Live:** the breach test through the Hub — one turn that calls a tool *and* attempts a
      write outside the workspace. The tool call succeeds; the write is refused; no file appears.
- [ ] 2.15 Check whether the Claude runner has an equivalent defect, using the same probe-MCP-server
      method. Record what was established; do not assume parity in either direction.

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
      default-configuration (non-`yolo`, sandboxed) codex agents, ask agent one to message agent two. Confirm:
      the tool call completes; the message row exists with the right sender, recipient, and project;
      a queue entry was created for the recipient; and the recipient is scheduled for a turn.
- [ ] 8.4 **Live:** the recipient actually runs its turn and its transcript contains the message.
- [ ] 8.5 **Live:** repeat 8.3 with two claude agents.
- [ ] 8.6 **Live:** repeat 8.3 across providers — a codex agent messaging a claude agent.
- [ ] 8.7 Confirm the agents in 8.3 still cannot write outside their workspace — collaboration
      working must not have cost the sandbox.
- [ ] 8.8 `openspec validate 2026-08-06-agent-messaging-delivery --strict` — clean.
