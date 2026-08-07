# The Hub answers its agents' permission requests

**Approved:** 2026-08-07, operator

## Why

`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge` made Claude agents able to work by
changing the non-yolo default from `manual` to `acceptEdits`. That fixed the symptom — every write
was being refused — by removing the question rather than answering it. The operator's decision at the
time was explicit: *"Both: toggle now, Hub-answered next."* This is the second half.

### `acceptEdits` trusts the boundary it does not check

Under `acceptEdits`, Claude accepts file edits without asking anyone. The agent's workspace boundary
is real — it runs in its own git worktree — but nothing enforces it per tool call. An agent that
resolves a path badly, or is told to touch something outside its worktree, is not stopped by the
permission layer; it is stopped only by whatever the filesystem happens to allow. The posture is
permissive because there was no one to ask, not because permissiveness was the right answer.

### "Ask first" is a dead end, and says so only by failing

The composer's Permissions pill offers "Ask first" (`--permission-mode manual`). The Hub spawns runs
headlessly, so nothing can answer, so every request is refused. An operator who selects it gets an
agent that reports being blocked on approvals that were never shown to anyone. It is a working
control wired to an absent answerer.

### The operator never learns an agent was stopped

`2026-08-06-operator-in-the-loop-turns` (deferred) records this gap directly: *"a sandboxed agent
that tries to write outside its workspace is silently denied by the Hub. The operator is never told
it wanted to. The agent hits a wall, works around it or gives up, and the one person who could have
unblocked it never knew."* There is no decision point today that could be surfaced, because there is
no decision — only a refusal.

### The mechanism to fix this exists and is now measured

Claude Code's `--permission-prompt-tool <mcp-tool>` names an MCP tool that is called for each
permission decision and whose answer is honoured. It is hidden from `--help`, so it was previously
recorded as researched-but-unverified. It has now been exercised end to end against Claude Code
2.1.221 (see design.md, "The measured contract"): under `--permission-mode manual`, an `allow`
answer let a write through, and a `deny` answer blocked it and delivered the reason to the model.

## What changes

- The Hub's MCP server gains an approval tool that Claude calls for every permission decision. It
  decides in-process against the run's own workspace: inside is allowed, outside is denied with a
  reason the model can act on, and anything unrecognised is denied rather than left unanswered.
- The tool is an approval endpoint, not part of the agent's tool surface. It is excluded from the
  generated "Your tools" context and is not something an agent is invited to call.
- Each decision is reported to the Hub best-effort, so denials become visible to the operator in the
  timeline instead of vanishing. Reporting can never change or delay the decision.
- The Permissions pill gains a fourth posture, "Workspace only", which pairs `manual` with the
  approver. `acceptEdits` remains the default; this posture is opt-in until it has been used for
  real work.

## Impact

- **Agents** gain a permission layer that enforces the workspace boundary per tool call instead of
  trusting it, but only when the operator selects the new posture.
- **Operators** gain a posture that is safer than `acceptEdits` without being unusable like "Ask
  first", and gain visibility into denials.
- **`2026-08-06-operator-in-the-loop-turns`** gains the decision point it needs. Escalating a denial
  to a human becomes a change to what the Hub does with a reported decision, not new plumbing.
- **Existing runs are unaffected.** The default posture, yolo runs, and Codex runs are untouched.

## Explicitly not in this change

- **The default posture does not move.** `acceptEdits` stays. Making "Workspace only" the default is
  a later decision, deliberately taken after live use.
- **No operator is asked anything.** A denial is reported, not escalated; nothing blocks on a human.
  That is `2026-08-06-operator-in-the-loop-turns`, still deferred.
- **Codex is untouched.** `codex_appserver.decide_approval` already answers Codex's approvals; this
  change gives Claude the equivalent, it does not unify them.
- **No new permission policy beyond the workspace boundary.** Command allowlists, network policy, and
  per-tool rules are out of scope.
