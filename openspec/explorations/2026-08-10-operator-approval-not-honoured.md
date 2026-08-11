# Defect — an approved permission request still does not let the tool run

**Date:** 2026-08-10 · **Diagnosed:** 2026-08-11
**Status:** **root cause found, not yet fixed.** See "Diagnosis" below; the leads section is kept
for the record, and four of its five leads are now eliminated with evidence.
**Severity:** high. This is the operator-in-the-loop story failing at its final step.

**Reported by the operator, verbatim:**

> "When the permissions are not to allow all and a agent needs to delete or execute something even
> if he asks via agentweave and we give a positive answer it still doesn't allow it to run. This is
> a hard bug that we need to revisit later."

## Why it matters more than it looks

The whole point of a non-yolo posture is that an agent can stop, ask, and continue. If an *approval*
does not unblock the call, then the only working postures are "allow everything" and "block
everything" — and the operator-in-the-loop feature, which `CLAUDE.md` lists as a shipped
capability, does not actually function. An operator who cannot rely on approvals will set yolo and
leave it there, which is the opposite of what the permission surface exists for.

It also blocks verification elsewhere: task **9.1** of
`openspec/changes/2026-08-10-task-transition-machine` asks the operator to drive an agent into a
refusal and watch it self-correct. An agent that cannot get past a permission prompt cannot reach
that scenario.

## Ruled out on the first pass

- **`approve_tool_call` has no return annotation.** `CLAUDE.md` warns that adding one makes FastMCP
  derive `structuredContent` and *"silently defeat an allow"* — precisely this symptom. Checked:
  `hub/hub/mcp_server.py:669-673` declares `def approve_tool_call(tool_name, input, tool_use_id="")`
  with no return type. The known trap is not the cause here.
- **The allow branch returns the documented shape.** `mcp_server.py:687-689` returns
  `{"behavior": "allow", "updatedInput": input}`, which is what Claude's `--permission-prompt-tool`
  protocol expects.

## Leads, none verified

1. **`updatedInput` echoes the raw `input`, not the normalised one.** Line 675 computes
   `tool_input = input or {}`, but line 688 returns `input`. When `input` is `None` the response
   carries `"updatedInput": null` rather than `{}`. Whether Claude rejects an allow on that basis is
   untested — and `{}` is falsy in Python, so the normalisation is doing less than it appears to.
2. **The posture may not be reaching the process.** The branch at line 676 turns on
   `AW_PERMISSION_POSTURE == OPERATOR_POSTURE`. If that env var is absent or differently spelled in
   the spawned run, `_decide` runs instead of `_ask_operator`, and the operator's answer is never
   consulted — the request the operator saw and the decision the tool made would be unrelated.
3. **Timeout.** `AW_DECISION_TIMEOUT` bounds how long a run waits. An approval given after it
   expires would be recorded by the operator as "I said yes" and by the run as "no answer".
4. **Runner-specific.** Claude goes through `--permission-prompt-tool`; Codex through
   `codex_appserver.decide_approval`. The report does not say which runner, and they share no code
   on this path — so one may work and the other not.

## To reproduce

In `testbed/`, with the composer's Permissions pill set to **"Ask me"** (`manual`), ask an agent to
delete a file or run a shell command. Answer the resulting card **yes**. Observe whether the tool
call proceeds.

Worth capturing when someone picks this up: which runner, the run's environment (`AW_PERMISSION_POSTURE`,
`AW_DECISION_TIMEOUT`), the `_report_decision` output for that call, and what the agent's transcript
says it received back.

---

## Diagnosis (2026-08-11)

### The cause: a timed-out request is never closed, so the card outlives the run

`mcp_server._ask_operator` bounds the wait at `OPERATOR_DECISION_TIMEOUT` (`AW_DECISION_TIMEOUT`,
default **120s**). When it runs out it returns a local denial — and **writes nothing back to the
Hub**. The `PermissionRequest` row stays `status="pending"` forever.

Everything downstream then behaves exactly as designed, and the result is the reported bug:

1. **t=120s** — the run denies the tool call and continues. The tool does not execute.
2. `_report_decision` posts to `/permission-decisions`, which
   (`agent_actions.py:513-547`) persists a `permission_denied` event and broadcasts it. It **never
   touches the request row** — it is not even given the request id, only `tool_name`/`tool_use_id`.
3. `list_permission_requests` filters `status == "pending"` (`permissions.py:57`), so **the card is
   still on screen.**
4. The operator clicks Allow. `decide_permission_request` checks `row.status != "pending"` — it *is*
   pending, so the 409 guard does not fire. The row becomes `"allowed"` and the API returns **200**.
5. The operator has now seen a successful approval. Nothing runs. There is no message anywhere
   saying why.

That 409 guard — *"this request was already {status}; the run has moved on"* — is the author
anticipating precisely this case. It never fires, because on this path nothing ever sets a terminal
status.

### Why Codex works and Claude does not

This is lead 4, and it resolves in Claude's disfavour. The Codex counterpart
(`agent_trigger._await_codex_approval`) closes its own row on timeout:

```python
# agent_trigger.py:1448-1452
async with async_session_factory() as db:
    row = await db.get(PermissionRequest, request_id)
    if row is not None and row.status == "pending":
        row.status = "expired"
        await db.commit()
```

`agent_trigger.py:1451` is **the only place in the codebase that expires a row.** Codex runs
in-process and has a session; `mcp_server.py` is spawned standalone with no database — so the Claude
path had nowhere obvious to put the same write and silently went without it.

### Second symptom from the same cause

`conversations.py:268-269` counts a pending permission request as a reason a conversation is
"waiting" on the operator. A row that is never closed therefore pins its conversation as waiting
**permanently**, long after the run ended. Worth checking against any "why is this still waiting?"
report before treating it as a separate defect.

### Eliminated, with evidence

Each of these was a plausible cause and is now ruled out. Recorded so nobody pays for them twice.

- **`--permission-mode manual` is invalid.** No: `claude --help` on **2.1.221** lists
  `acceptEdits, auto, bypassPermissions, manual, dontAsk, plan`.
- **`--permission-prompt-tool` was removed.** No — it is absent from `--help`, which is alarming, but
  the binary carries it 16 times and documents it as *"MCP tool to use for permission prompts (only
  works with `--print`)"*. The Hub passes `-p`, so the precondition holds. (Note for future probes:
  Claude Code **silently ignores unknown flags** — `claude --not-a-real-flag x --version` exits 0 —
  so "the CLI accepted it" proves nothing on its own.)
- **`operator_set_permission_mode` misdetects the flag.** `runner_commands.py:175` uses a list
  membership test, which only works if the flag is split across two argv elements. It is:
  `render_control_args('claude', {'permission_mode': 'manual'})` → `['--permission-mode', 'manual']`.
- **The FastMCP `structuredContent` trap** (the one `CLAUDE.md` warns about). Ran the real registered
  tool through FastMCP 3.1.0: `output_schema` is `None`, `structured_content` is `None`, and the
  result is a single `type="text"` block containing
  `{"behavior": "allow", "updatedInput": {...}}`. Correct, and matching the zod schema recovered from
  the binary: `{behavior: literal("allow"), updatedInput: record(string, unknown).optional(),
  updatedPermissions: array(...).optional()}`.
- **Lead 1, `updatedInput: null`.** Real, but unreachable through MCP. The signature declares
  `input: Dict[str, Any]` (not `Optional`), so pydantic rejects `null` before the body runs — making
  the `input or {}` normalisation at `mcp_server.py:731` dead code for that case. *However*, `input`
  is `required` in the generated schema, so a permission request that omitted it would fail
  validation and surface as an invalid permission result. Latent, not the reported bug.
- **Lead 3, the timeout is too short for Claude.** Not the constraint. Claude held a permission tool
  call open through a **65s** approver delay without complaint (below).

### The live probe

Run 2026-08-11 in `testbed/scratch/`, deliberately **without the Hub**, to separate the Claude
protocol from AgentWeave's own machinery. A stub MCP server mirroring `approve_tool_call` exactly —
no return annotation, `json.dumps` of the same payload — auto-allows after a configurable delay,
driven by the same argv `runner_commands.build_command` produces.

| delay | approver called | allow returned | tool executed | elapsed |
|---|---|---|---|---|
| 0s | yes | yes | **yes** — `hello.txt` written | 10s |
| 65s | yes | yes | **yes** — `hello.txt` written | 72s |

**The Claude permission protocol works end to end, including a slow operator.** That is what moves
the fault decisively to the Hub side, and it is why the earlier eliminations kept coming up empty:
they were all looking at the half that works.

### Why no test caught it

`test_permission_approver.py` covers the MCP side thoroughly, including
`test_an_unanswered_request_is_denied_when_the_wait_runs_out` — but against a **stubbed
`_hub_request`** (line 355), so "denied locally" is asserted while the row's fate is invisible. The
UI is tested against mocked hooks. **No test exercises `/permission-requests` as an actual HTTP
route**, so the seam where the run's view and the operator's view diverge is the one place nothing
looks.

## Suggested fix

The run must tell the Hub its wait ended. Sketch, not a decision:

1. **Close the row when the wait expires.** `_ask_operator` calls a new
   `POST /agent-actions/permission-requests/{id}/expire` before returning its timeout denial,
   guarded to only affect a still-`pending` row. Best-effort, like `_report_decision`.
2. **Do not rely on that alone.** If the run is killed, or the Hub is briefly down, step 1 never
   happens and the bug returns. The Hub should also expire pending requests belonging to a run that
   has ended — the run-boundary machinery from `2026-08-10-run-task-binding` is the natural home.
3. **Close the remaining race.** An operator clicking at t=119s against a run that gives up at t=120s
   still loses. The decision should be rejected, or accepted and acted on, but not silently both —
   which argues for the run confirming the decision it acted on rather than the operator's click
   being assumed effective.
4. **Say so in the UI.** An expired request should read as expired, not vanish — the operator needs
   to learn that the agent gave up, which is the information the current design loses entirely.

Worth deciding as one small change; steps 1 and 2 together are the actual fix, 3 and 4 are what stop
it being confusing rather than broken.
