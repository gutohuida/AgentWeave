# Proposal — an arguments file written from PowerShell is the Hub's own

**Round 1, 2026-10-02** (night window; the operator's explicit exception in `spec-queue/APPROVALS.md`
`## 2026-10-01`). Finding: **F478 (B)**. **Nothing here is implemented.** R2 and R3 (2026-10-02, night
iterations 5 and 6) each re-derived it against the code and against real PowerShell 5.1. An adversarial review
follows, then the operator approves it.

## Why

Slice 3 (`a-run-reaches-the-hub-without-mcp`, built, not archived) tells every run described `shim` to write
a tool's arguments as JSON to `.agentweave/calls/<file>.json` *"with your file-writing tool (from PowerShell,
only `Set-Content -Encoding utf8` as a command of its own)"*. The advice appears in `hub/hub/api/v1/agents.py:1628-1632`,
`hub/hub/launchability.py:445-449` and the shim's own decode error (`hub/hub/mcp_server.py:2452-2455`).

Drive 9.10 (`run-b30d4295abaf`) followed that advice on a Copilot specification turn, whose only file tool is
`create`. It ran `Set-Content -Path '.agentweave/calls/r.json' -Value '{"path":"spec/..."}' -Encoding utf8`, and the Hub
refused it as outside the workspace. The turn gave up and nothing was submitted. Slice 3's task 9.10 is open on
this alone.

**What actually refuses it.** R1 measured this with `_decide` in-process at `83b53b6`, against a scratch workspace,
on this Windows host:

| Command | Today |
|---|---|
| PowerShell `echo 'a:b/c'`; the same in bash, quoted or not | deny `'/c'` |
| `Set-Content -Path '.agentweave/calls/r.json' -Value '{"path":"spec/x.html"}' -Encoding utf8` | deny `'/x.html'` |
| the same with `{"path": "spec/x.html"}` (a space after the colon) | **allow** |
| the same with `{"title":"x"}` | allow |
| the same with `{"path":"spec\x.html"}` | deny `'\\x.html'` |
| the same with `{"path":"../x.html"}`, `{"path":"/etc/x"}` | deny `'/x.html'`, `'/etc/x'` |
| the same with `{"url":"https://example.com/x"}` | deny `'s://example.com/x'` (the `s:` read as a drive) |
| bash `echo '{"path":"spec/x.html"}' > .agentweave/calls/r.json` | deny `'/x.html'` |
| **(R2)** 9.10's exact bytes, from the trial Hub's `agent_outputs`: `Set-Content -Path '.agentweave/calls/read-spec.json' -Value '{"path":"spec/changes/ivory-hydra/spec.html"}' -Encoding utf8`, as `PowerShell` or `Shell` | deny `'/changes/ivory-hydra/spec.html'` |

R2 re-ran every row above with its own probe (`.claude/autonomous/tmp/f478_r2_probe.py`) at `9efdfd8`, and
each matched. It also measured `{"path": "../x.html"}` (a space after the colon) still refused as `'../x.html'`,
`{"path": "C:\x"}` refused, and `{"body": "see https://example.com/x"}` refused as a network address. So the
argument values this change calls data are refused today in either spacing.

The finding calls the culprit the *URL reader* and suggests treating a scheme only when `//` follows it.
**That is not the mechanism, and the suggested behaviour is already in place.** Rule 1 (`_URL_SCHEME_RE`,
`mcp_server.py:1108`) matches only a `scheme://` that starts a word. The refusal comes from **rule 6, the
backstop** (`:1359-1364`), which the archived `a-url-is-not-a-path` also built:

- After `_words` trims the edges, the word is `path":"spec/x.html`.
- It holds a separator. It is not plain, because `_PLAIN_RELATIVE_RE` (`:1109-1122`) refuses a colon in the
  first segment, by design: *"a colon in the first segment is where a host or a revision goes, and those are
  left to the backstop"*. **(R2)** It also refuses the `"` left inside the word, which
  `_PLAIN_RELATIVE_EVERYWHERE` excludes at every position. So the JSON word reaches rule 6 even without its
  colon: R2 measured `path""spec/x.html` refused `'/x.html'` too. The colon is the only reason for
  `echo 'a:b/c'`.
- So it falls to rule 6. Rule 6's `_ABSOLUTE_PATH_RE` (`:1103-1106`) opens a candidate at the first separator
  and judges `/x.html` as a path at the root of the drive.

That is F362's mechanism, exactly.

## Which change owns it, and how the two order

F478 has two halves, and they belong to two changes.

1. **The general half** is any word with a colon before its first separator, such as `echo 'a:b/c'`. This is F362.
   **`the-shell-judge-reads-a-word-whole` already owns it.** Its D2 replaces rule 6 with pieces split at
   `` [<>|;&(@:\s'"`] ``, and its measured sweep lists `echo a:b/c` among the commands it moves to allowed.
   Under that design, the word `path":"spec/x.html` divides into the pieces `path` and `spec/x.html`, and both
   are inside the workspace. **This change does not touch rule 6** and does not repeat that work. That
   change's order clause (*"it must ship before, or with, any change that loosens rule 6 further"*) does not
   bind this one, because this one does not loosen rule 6.
2. **The half that blocks 9.10** is the Hub's own protocol write, in the form its notice instructs. After the
   shell judge reads words whole, that write is still decided wrongly in two ways. These come from reading that
   change's design and are not measured, because it is not built:
   - An argument **value** that names `..`, an absolute path or a URL is still refused, because the shell
     judge still reads the literal as paths: `{"path":"../x"}` (the piece `../x`), or a message whose text
     holds `https://…` (the piece `//…`). These are data passed to a Hub tool, which judges its own arguments.
   - Under "Ask me" the write still raises a card every time. F477 fixed exactly this friction for the compound
     form. The notice offers two routes for the arguments file. The file-tool route has standing (slice 3 D8
     case 3), but the PowerShell route does not.

So **neither change supersedes the other.** They touch disjoint code. This one adds a predicate beside
`_hub_own_command` and calls it from `_hub_own_call`. That one changes `_lex`, `_words`, `_judge_word` and
`_decide`'s per-call budget. Either may build first. This one is small and unblocks 9.10 now. The shell judge
is fourth from last in tonight's ORDER, and with its sibling it is about 72 tasks.

## What changes

1. **A fourth case of the Hub's own call** (slice 3 design D8). A `PowerShell` request has standing when its
   command is exactly one `Set-Content` write of an arguments file:
   - The command name is `Set-Content` (any case). It is followed by exactly the three parameters `-Path` (or
     `-LiteralPath`), `-Value` and `-Encoding`, each once and by its full name (any case), in any order. ASCII
     spaces separate them, and nothing but ASCII spaces comes before or after.
   - `-Path`'s value, bare or in single quotes, passes the existing `_plain_calls_path`: a plain relative `.json`
     path inside the calls root, by the calls-root rule. It holds only `_PLAIN_COMMAND_CHARS_POWERSHELL`
     characters, less the space.
   - `-Encoding`'s value is `utf8` (any case), bare or in single quotes.
   - `-Value`'s value is **one** single-quoted PowerShell literal. An ASCII `'` opens and closes it, and `''`
     inside is an escaped quote. It contains none of U+2018, U+2019, U+201A and U+201B, because PowerShell
     reads each of them as a single quote (measured: design D2; R3 swept the whole BMP and found no others). It
     contains no NUL either. **(R3)** The closing quote is followed by a space or the end of the command. Text
     joined to it is a second argument that PowerShell evaluates: `-Value 'a'(Write-Output INJECTED)` ran the
     subexpression before the binding failed.

   Its content is not read at all, because a single-quoted PowerShell literal is verbatim: no variable, no
   subexpression and no escape. **Measured** on 5.1.26100: `-Value 'it''s {"path":"spec/x.html"}
   $env:USERNAME $(Write-Output NO)'` wrote exactly `it's {"path":"spec/x.html"} $env:USERNAME
   $(Write-Output NO)`, with a UTF-8 BOM, which the shim decodes (slice 3 D3).
2. **Anything that is not exactly that falls through**, as every near miss does today. The workspace judge or the
   operator's card decides it, unchanged.
3. **The notice text is unchanged.** It already names this form. Only the Hub's decision about it changes.

## What does not change

- Rules 1 to 6 of the workspace judge, `_lex` and `_words`, and every refusal they make of any other command.
- Cases 1 to 3 of `_hub_own_call`, the calls-root rule, and the shim's own read-side check.
- Bash: no bash form of the write gets standing (design, Open question 1).
- Codex: `_hub_own_call` does not read its approvals. Slice 3 says so, and that is unchanged.

## Findings

- **F478**: this change fixes the arguments-file half. The general half (`echo 'a:b/c'`) is F362's mechanism,
  fixed by `the-shell-judge-reads-a-word-whole` D2. When this change archives, F478's status line says both.
- It unblocks slice 3's task 9.10. That task needs a re-drive; this change does not tick it.

## Impact

- **Code:** `hub/hub/mcp_server.py` gets a new `_hub_own_powershell_write(command, workspace)`, called from
  `_hub_own_call`'s shell branch after `_hub_own_command`. Its docstring and D8's "three cases" become four.
  Copilot's ACP handler already reaches it through `_hub_own_call` (`copilot_acp.py:535`), so nothing changes
  there. **(R2)** It reaches case 4 only under the key `PowerShell`, which `_shell_key` (`copilot_acp.py:444-453`)
  gives only when Copilot's `tool.execution_start` reported `toolName: "powershell"` before the permission
  request. Any other name (`write_powershell`), or none, is the key `Shell`, which never earns standing, as for
  case 2. That holds in production: the captured fixture (`turn_write_shell_mcp.jsonl`) orders the start event
  first, and slice 3's 9.4 (`run-000e23023de9`, "Ask me") got case 2's standing on Copilot with no card.
- **Tests:** `hub/tests/test_hub_own_call.py`.
- **Spec:** `agent-run-sandboxing`, **MODIFIED** "The Hub's own call command is decided like the Hub's own
  tools". That requirement is slice 3's ADDED one and is not yet synced. **This change archives only after slice
  3 has archived.** Its code may land earlier, so that 9.10 can be re-driven first (design, Order).
- **No migration, no UI bundle, no Hub restart.** `mcp_server.py` still reaches the operator's `:8000` agents on
  their next run, committed or not (`.claude/rules/mcp-server.md`), so the implementing session tells the
  operator first.
