# A non-yolo Claude run is sandboxed by the Hub's own flag, not the operator's machine

**Approved:** _pending_

## Why

`hub/hub/runner_commands.py::_build_claude_command` sets `--dangerously-skip-permissions` when a run
is `yolo`, but sets **nothing** when it is not. Claude Code then falls back to whatever
`~/.claude/settings.json` says on the machine the Hub process happens to run on. Verified live against
Claude Code CLI 2.1.221 during `2026-08-06-agent-messaging-delivery` task 2.15 (full write-up:
`openspec/changes/2026-08-06-agent-messaging-delivery/design.md`, Decision 6): on this development
machine, that file sets `defaultMode: "bypassPermissions"` — so a "non-yolo" Claude agent run through
this Hub today is not actually sandboxed at all. Whether it is depends on the operator's personal CLI
config, not on the Hub's own `yolo` flag, which is supposed to be the single source of truth for that
posture.

The same investigation found a second problem once the first is fixed: an explicit non-bypass
permission mode blocks *everything* undifferentiated — the Hub's own `agentweave` MCP tools included.
A correctly sandboxed non-yolo Claude agent could use none of AgentWeave's own tooling (`list_tasks`,
`ask_user`, etc.), which defeats the point of running it through the Hub at all.

Both the defect and the fix were established empirically last session, live, against a real CLI — see
Decision 6 for the full experiment record, including what was and was not confirmed. This change is
the implementation of that already-verified fix. It is scoped separately from
`2026-08-06-agent-messaging-delivery` because it changes the command line of every non-yolo Claude
run, not just messaging behavior.

## What changes

- `_build_claude_command` sets `--permission-mode manual` for every non-yolo run, instead of setting
  no permission flag at all. `yolo` continues to mean `--dangerously-skip-permissions`, unchanged.
- When a non-yolo run also has an MCP command configured (the Hub's own `agentweave` server),
  `_build_claude_command` additionally sets `--allowedTools "mcp__agentweave__*"`, so the Hub's own
  tools remain usable while every other action stays gated.

## Impact

- **Affected specs:** new capability `agent-run-sandboxing` (does not exist yet — this change adds
  it; no existing capability spec describes non-yolo Claude sandbox posture today).
- **Affected code:** `hub/hub/runner_commands.py` (`_build_claude_command` only — `_build_codex_command`
  is untouched; Codex's non-yolo posture already defaults to `--sandbox workspace-write` regardless of
  host config).
- **Affected tests:** `hub/tests/test_runner_parsing.py`'s `TestBuildCommandClaude` — several
  existing tests assert the exact full argv list or assert the permission flag's absence and need
  updating alongside new tests for the added flags.

## Risks

- **Behavior change for every non-yolo Claude run**, not an opt-in. Any operator currently relying on
  their own machine's `bypassPermissions` override to make a "non-yolo" Hub agent behave like yolo will
  see that agent become genuinely sandboxed instead. This is the intended fix, not a side effect, but
  it is a real behavior change worth calling out plainly.
- `--allowedTools "mcp__agentweave__*"` is a static, spawn-time allowlist scoped to the literal
  `"agentweave"` mcpServers key `_build_claude_command` already hardcodes a few lines above — if that
  key name ever changes, the two must change together.

## Out of scope

- Codex's non-yolo posture (`_build_codex_command`) — already correctly sandboxed via
  `--sandbox workspace-write`, unaffected by host machine config, and not part of Decision 6's finding.
- The Claude CLI's true zero-configuration default (no `bypassPermissions` override, no explicit
  `--permission-mode` flag) — Decision 6 states this was inferred, not directly measured, and that gap
  is not closed here; this change makes the Hub's own command line explicit regardless of what the
  true default turns out to be.
- Any operator-facing escalation UI for a refused action (that is
  `2026-08-06-operator-in-the-loop-turns`, itself deferred).
