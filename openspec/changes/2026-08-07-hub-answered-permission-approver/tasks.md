# Tasks

## 1. The approval tool

- [ ] 1.1 Add an approval tool to `hub/hub/mcp_server.py` taking `tool_name`, `input`, and
      `tool_use_id`, with **no return type annotation** — the annotation is what makes FastMCP emit
      `structuredContent`, which silently defeats an `allow` (design.md, "The measured contract").
      Comment the omission at the definition so it is not "cleaned up" later.
- [ ] 1.2 Return `{"behavior": "allow", "updatedInput": <input>}` or
      `{"behavior": "deny", "message": <reason>}`, JSON-encoded as a string.
- [ ] 1.3 Read the run's workspace from its environment variable. Absent or blank ⇒ deny, with a
      message saying the boundary could not be established.
- [ ] 1.4 Decide: a call whose path arguments all resolve inside the workspace is allowed; one that
      resolves outside is denied naming the offending path; a call with no path argument is allowed;
      the Hub's own tools are always allowed. Unrecognised shapes deny rather than return nothing.
- [ ] 1.5 Resolve both sides to absolute real paths before comparing, so `..` and symlinks cannot
      walk out.
- [ ] 1.6 Test: the response is a text block with no `structuredContent`, asserted against the
      server's actual JSON-RPC output rather than the Python return value.
- [ ] 1.7 Test: `tool_use_id` is accepted — a call passing it does not raise.
- [ ] 1.8 Test: inside ⇒ allow and `updatedInput` round-trips the input unchanged.
- [ ] 1.9 Test: outside ⇒ deny; `..` escape ⇒ deny; symlink escape ⇒ deny; absent workspace ⇒ deny.
- [ ] 1.10 Test: a Hub tool call and a call with no path argument are allowed.

## 2. The workspace boundary reaches the MCP process

- [ ] 2.1 Thread the run's effective working directory into the spawned MCP server's environment in
      `hub/hub/api/v1/agent_trigger.py`, alongside `AW_AGENT_IDENTITY`.
- [ ] 2.2 Use the same value already threaded into generated context as "Your workspace", so the
      stated and enforced boundaries cannot diverge.
- [ ] 2.3 Test: the spawned environment carries the same directory the context names.

## 3. Decisions are reported to the Hub, and cannot break the run

- [ ] 3.1 Report each decision to the Hub after it is determined — never before, never as a
      precondition.
- [ ] 3.2 Swallow every failure: unreachable Hub, timeout, error status. A failed report must not
      change the answer, delay it, or raise.
- [ ] 3.3 Surface a denial where the operator will see it, so a blocked agent is visible rather than
      silent.
- [ ] 3.4 Test: with reporting failing outright, the decision is still returned, unchanged and
      without raising.
- [ ] 3.5 Test: a denial reaches the operator-visible surface.

## 4. The "Workspace only" posture

- [ ] 4.1 Add the fourth `ControlValue` to `permission_mode` in `hub/hub/model_catalog.py`, labelled
      by what it permits, with the other three unchanged.
- [ ] 4.2 In `_build_claude_command`, emit `--permission-prompt-tool mcp__agentweave__<tool>`
      alongside `manual` **only** for this posture, and only when the MCP server is configured —
      there is no approver to name otherwise.
- [ ] 4.3 Emit it under the same `operator_set_permission_mode` guard as the mode itself, so an
      approver flag cannot outlive the posture that asked for it.
- [ ] 4.4 Test: selecting the posture puts both flags in argv, exactly once each.
- [ ] 4.5 Test: the other three postures emit no approver flag.
- [ ] 4.6 Test: yolo is unaffected, and still emits `--dangerously-skip-permissions`.
- [ ] 4.7 Test: with no MCP server configured, the posture emits no approver flag and no dangling
      reference.
- [ ] 4.8 Test: the default is still `acceptEdits` — this change must not move it.

## 5. The approver is not advertised as a capability

- [ ] 5.1 Exclude the approval tool from `_tool_surface_lines()` in `hub/hub/api/v1/agents.py`.
- [ ] 5.2 Test: generated context lists every callable collaboration tool and does not mention the
      approver.

## 6. Verification

- [ ] 6.1 `pytest hub/tests/ -q` — baseline 844 passed / 9 skipped.
- [ ] 6.2 `pytest tests/ -q` — baseline 372 passed / 3 skipped.
- [ ] 6.3 `cd hub/ui && npx vitest run` and `npx tsc --noEmit` — baseline 465 passed.
- [ ] 6.4 `ruff check` on every touched Python file.
- [ ] 6.5 `npx openspec validate --specs --strict`.
- [ ] 6.6 `npm run build` and regenerate `hub/hub/static/ui` **only if** UI source changed.
- [ ] 6.7 **Live:** under "Workspace only", an agent writes a file inside its worktree — succeeds.
- [ ] 6.8 **Live:** under "Workspace only", an agent is asked to write outside its worktree — denied,
      and the agent reports the reason rather than a broken approval system.
- [ ] 6.9 **Live:** the denial is visible to the operator.
- [ ] 6.10 **Live:** an agent under "Workspace only" can still send a message to a peer — the Hub's
      own tools are not caught by the boundary.
- [ ] 6.11 **Live:** with the Hub's reporting endpoint made to fail, a run still completes and
      decisions are still honoured.
- [ ] 6.12 **Live:** the three existing postures behave exactly as before.
