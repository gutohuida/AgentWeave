# Proposal — the workspace judge reads paths, not patterns

**Round 1, 2026-10-12.** Finding **WPC-2 (medium)**, from the work-PC Copilot drive (handoff 0162,
`.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md:44-51`). Re-verified against HEAD
`6208e9a5`. Built on the **recommended** answer to `wpc2-a` (design, Open Questions): a narrowed
form of option (a). **Nothing here is implemented yet.**

## Why

Under the Workspace posture, the per-call judge refuses two ordinary, read-only PowerShell listings
that a Copilot subagent issued inside its own worktree. Both refusals were reproduced by calling
`_decide("PowerShell", {"command": …}, workspace=…)` (`hub/hub/mcp_server.py:3495`) directly. The
Bash reading and the unknown-dialect `"Shell"` key refuse both the same way.

**The evidence.** Trial DB `workpc-drive` (`mode=ro`), project `proj-d73f8848ee60`, agent `cop-1`,
run `run-b175c9ffa621`. There are two `permission_denied` events, both `decided_by: runtime`:

- `evt-12c4094a5bdb` (09:07:20): `Get-ChildItem -LiteralPath '<worktree>' -Recurse -File |
  Where-Object { $_.FullName -notmatch '\\.git(\\|$)' } | ForEach-Object { … }`. Refused as
  *"contains a variable, '~' or a command substitution"*. (R2: this row has **no** `-Force`;
  verified against `agent_outputs` row `out-3788f09bbae6` for the run. Only `evt-9d81` carries
  `-Force`.)
- `evt-9d816809f8a2` (09:07:23): `Get-ChildItem -Recurse -Force -File | Where-Object {
  $_.FullName -notmatch '\\.git\\' } | Resolve-Path -Relative`. Refused as *"'\\\\.git\\\\' is
  outside your workspace"*.

These are 2 of the 4 refusals in that database. Of the other two, `evt-8be833e9a344`
(`'C:\Python*'`) is a legitimate outside read and is out of scope here.

**Why each refusal fires.** Neither refusal is about `$_`.

1. *Refusal 1.* The regular-expression literal `\\.git\\` is lexed into a word that begins with
   `\\`, which is a UNC root. Rule 5 of `_judge_word` (`mcp_server.py:2366-2370`) reads any
   absolute-looking word as a path and hands it to `_judge_path`. `_judge_path` finds it outside
   the workspace.
2. *Refusal 2.* The pattern `'\\.git(\\|$)'` ends in a regex `$`, meaning end of string.
   - The PowerShell lexer records a `$` inside single quotes as `_LITERAL_DOLLAR`
     (`mcp_server.py:2986`, `:3007`; defined at `:1264`).
   - `_expands` deliberately still counts it as an expansion (`:2102-2108`). The comment at
     `:1258-1262` explains why: an inner shell would expand a quoted `$`.
   - The word also holds a separator (`\`), so rule 3 (`:2321`) refuses it as *uncheckable*.

   **The handoff calls this a "variable" problem. It is not.** `$_` and `$PSItem` inside `{ }` are
   already allowed. Replacing only the pattern with `'git'` makes **both** recorded commands pass
   under every dialect key.

**What it costs.** Copilot over ACP is only ever answered `allow_once` or `reject_once`
(`hub/hub/copilot_acp.py:864-868`), so the agent never sees the reason. Combined with WPC-1, where
a refusal ends the Copilot turn, a routine file listing ends the turn. F362 already counted regex
fragments among 45 regex/`$VAR` refusals on LoopEngine. F478 named "read a single-quoted PowerShell
literal as data" as an option.

The judge treats every quoted string as a possible path. But a pattern that a comparison operator
matches against is never something the command acts on.

## What Changes

- **In the PowerShell reading only**, a quoted literal that is the **pattern operand of a binary
  comparison operator** in **expression mode** is not judged as a path, nor as uncheckable.
  - The operators are `-match`, `-notmatch`, `-like`, `-notlike`, `-replace` (its first element
    only) and `-split`, plus their `c`/`i` variants.
  - Everything else in the command is judged as it is today.
- **Expression mode is how PowerShell itself reads** a statement or pipeline element whose first
  token is a variable, a quoted string, a number, `(`, `@(` or `$(`.
  - A command-mode element, one that starts with a command name, `&` or `.`, gets **no**
    exemption. There, `-match` is just an argument, and the next word reaches the command as a
    value.
  - Verified in real PowerShell: `Write-Output $x -match 'C:\out'` emits three arguments.
- **The PowerShell `_lex` must record two facts per argument:** where its statement starts, and
  whether it was fully single-quoted, or double-quoted with no `$` or backtick. Today it records
  neither.
- **The refusal text, and how it reaches a Copilot agent, are unchanged here.** That belongs to
  WPC-1.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-run-sandboxing` gets one **ADDED** requirement: *"A pattern a PowerShell comparison
  operator matches against is not a path in the command"*.
  - It narrows *"A path in a shell command is judged by where it resolves"* for that operand only.
  - That requirement's existing scenario, about a regular expression with a separator that stays
    inside, is consistent with this change and is not modified.

## Impact

- **Code:** `hub/hub/mcp_server.py` only: `_lex` (its PowerShell branch, `:2958`), `_words`
  (`:3112`) and `_read_command` (`:3153`). `mcp_server.py` may import only the standard library and
  `fastmcp` (`.claude/rules/mcp-server.md`).
- **Reach:** both callers of `_decide` get the change.
  - Copilot, through `copilot_acp._judge` (`:595`).
  - Claude, through `approve_tool_call` (`:3726`).
  - It reaches an agent only after a Hub restart, because the Hub spawns its pinned copy of the
    tool server. Verify on a trial Hub, never on `:8000`.
- **Tests:** a new file, `hub/tests/test_the_workspace_judge_reads_paths_not_patterns.py`. No
  existing row should change. Row `1.7c1` (`grep -rn '\.\./' src`, bash) must stay refused, and is
  named as a control.
- **Dialect key:** the exemption fires only when `_shell_key` (`copilot_acp.py:493`) returns
  `"PowerShell"`.
  - That requires a tracked `tool.execution_start` with `toolName: "powershell"` before the
    permission request. The captured fixture `turn_write_shell_mcp.jsonl` has that order.
  - A call without it is read in both dialects and stays refused, which fails safe.
  - R2 confirmed subagent calls **are** tracked: `CopilotEventMapper.on_raw_event` calls
    `track_call(self.calls, …)` on every armed raw event with no subagent filter
    (`copilot_acp.py:1292`), and that `self.calls` is the same map `decide_permission` reads
    (`:2193`, `:2221`, `judge()` at `:2362`). The two recorded refusals were in fact a subagent's
    (`task`/`explore`, call `toolu_0169…`, "list-workspace-files"; its shell calls are
    `agent_outputs` rows `out-3788f09bbae6` and `out-4f7c7cf6d660`). Residual empirical gap: the
    raw `tool.execution_start.toolName` is not recoverable from the trial DB (`agent_outputs`
    stores the kind-label `"shell"` from `_KIND_LABELS["execute"]`, not the raw name), so whether
    these specific calls keyed `"PowerShell"` or `"Shell"` cannot be read back. See `wpc2-e`.
- **Neighbours:**
  - WPC-1 (a refusal ends a Copilot turn) is a sibling change.
  - F478's `_hub_own_*` PowerShell grammar is the precedent for a narrow, grammar-shaped allowance.
  - No conflict with `a-run-records-that-its-calls-were-allowed`.
- **Not in scope:**
  - `Select-String -Pattern`, `Where-Object -Match` (simplified syntax), and `grep`/`rg` pattern
    positions (`wpc2-c`).
  - Dropping the conservatism of `_LITERAL_DOLLAR` (option b').
  - A positional-parameter path model (option c).
  - The outside read `'C:\Python*'`.
