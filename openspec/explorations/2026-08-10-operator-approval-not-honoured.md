# Defect — an approved permission request still does not let the tool run

**Date:** 2026-08-10
**Status:** open, deferred by the operator. Not investigated beyond the first-pass elimination below.
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

## Not addressed here

No fix attempted. Recorded so the report is not lost in a conversation, and so the next session
starts from the eliminations above rather than repeating them.
