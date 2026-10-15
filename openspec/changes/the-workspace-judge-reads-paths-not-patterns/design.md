# Design — the workspace judge reads paths, not patterns

This design is built on the **recommended** answer to `wpc2-a`, a narrowed option (a). If the
operator answers otherwise:

- **(b') A single-quoted PowerShell `$` is literal.** Drop D1–D6. The change becomes one edit:
  `_lex` stops emitting `_LITERAL_DOLLAR` for a PowerShell single-quoted `$`. That fixes refusal 2
  only. Refusal 1 then needs (a) as well, or it stays.
- **(c) A path-position model.** Drop D1–D6 and write a new proposal. This is a rewrite of the
  judge, out of scale for a medium finding.
- **(d) The message only.** Drop D1–D6. The work moves to WPC-1: the channel that tells a Copilot
  agent why it was refused, plus a reworded `_UNCHECKED` for a quoted `$`. The judge is untouched.

## Context

### How the judge reads a command

`_decide(tool_name, tool_input, *, workspace=None, hub_url=None)` (`mcp_server.py:3495`) reads a
shell command in the dialects that `_TOOL_DIALECTS` (`:1255`) gives its key. `"PowerShell"` is read
as PowerShell only. Any key the table lacks, such as `"Shell"`, is read in both dialects and refused
if either reading refuses.

`_read_command` (`:3153`) does three things:

1. It lexes the command.
2. It splits each argument into words (`_words`, `:3112`). The split is on whitespace, `=` and `,`,
   and each word is trimmed of ``"'`{}[]()<>|;&:``.
3. It judges every word with `_judge_word` (`:2294`).

Two of `_judge_word`'s rules matter here:

- Rule 3 (`:2321`) refuses a word that has both a separator and an expansion.
- Rule 5 (`:2366-2370`) judges an absolute or plainly relative word as a path.

Nothing in this pipeline knows what a word is used for, so every literal is a candidate path.

### The two refusals

Two drive commands, both read-only, were both refused:

| Command fragment | Rule | Why |
|---|---|---|
| `-notmatch '\\.git\\'` | 5 | `\\.git\\` is a UNC-shaped absolute word |
| `-notmatch '\\.git(\\|$)'` | 3 | the regex `$` in single quotes is `_LITERAL_DOLLAR`, which counts as an expansion; `\` is a separator |

### What the judge allows and refuses today

Measured with `_decide` at HEAD `6208e9a5`:

| Allowed today | Refused today |
|---|---|
| `Where-Object { $_.FullName -notmatch 'git' }` | `-notmatch '\.git'` |
| `-like '*\.git\*'` | `'a\b$'` as an operand |
| `Select-String '[0-9]' f` (row 1.4f19) | `Select-String -Pattern '\\d+'` |
| `git log --grep='a/b'` | `rg '\\.git\\' .` |
| `$a -match 'a{1,2}'` | `'x' -replace '\\','/'` |
| `Remove-Item $x` (a bare variable; residual) | `grep -rn '\.\./' src` (row 1.7c1, must stay refused) |
| `Copy-Item n ('C' + ':' + [char]92 + 'outside')` (computed; residual) | |

The two "residual" rows show that the judge reads text. A computed or variable path already passes,
so this boundary is a best-effort check against literal paths. This change must not widen it beyond
pattern operands.

### PowerShell facts this design relies on

All five were verified in Windows PowerShell 5.1 on this machine.

1. **Expression mode versus command mode.**
   - A statement or pipeline element is parsed in expression mode when its first token is `$name`,
     a quoted string, a number, `(`, `@(` or `$(`.
   - In command mode (first token a command name, `&` or `.`), a word that looks like an operator
     is just an argument.
   - `Write-Output $x -match 'C:\out'` emits three arguments: `abc`, `-match` and `C:\out`.
   - `cmd /c echo $x -match 'C:\out'` hands `C:\out` to the native program.
2. **Pattern operators consume their right operand.** Binary `-match`, `-notmatch`, `-like` and
   `-notlike` return a Boolean, or the filtered left operand. The right operand is consumed as a
   pattern and never produced.
3. **Binary and unary `-split` differ.** Binary `-split` returns pieces of the **left** operand.
   **Unary** `-split 'C:\outside\f'` returns the operand itself: `(-split 'C:\outside\f')[0]` is
   `C:\outside\f`.
4. **`-replace` produces its replacement.** It takes `pattern, replacement`, and the replacement is
   a value that reaches the output: `'x' -replace 'x','C:\outside\f'` is `C:\outside\f`.
5. **The drive command does what the agent meant.** `Where-Object { $_.FullName -notmatch
   '\\.git\\' }` filters as intended.

## Decisions

### D1 — the exemption is keyed to expression mode, decided per statement

A quoted literal is exempt only inside a statement or pipeline element whose first token puts it in
expression mode (Context, fact 1).

A statement starts at any of these points:

- the start of the command;
- after `|`, `;`, `&&`, `||` or a newline;
- after `{`, which opens a script block's body;
- after `(`, `@(` or `$(`;
- after an assignment `=`.

A script block's body is itself a list of statements. So `Where-Object { $_.FullName -notmatch
'…' }` has a body in expression mode, even though `Where-Object` itself is in command mode.

*Alternative considered:* exempt the word after any comparison operator, which is option (a) as
first framed. **Rejected**, because in command mode that word is a path. Both `Copy-Item $x -match
'C:\outside'` and `robocopy $x -match 'C:\outside'` would pass.

### D2 — binary operators only, from a fixed list

The operator must directly follow an operand, which is what makes it binary. An operand here is a
variable, a member access, a quoted string, a number, or a closing `)` or `]`.

- **The list:** `-match`, `-notmatch`, `-like`, `-notlike`, `-replace` and `-split`, each with its
  `c` and `i` prefixes. They are matched case-insensitively.
- **Not exempt:** a unary `-split`, including `-split` after `(` or at a statement start (fact 3).
- **Left out:**
  - `-join`, because its operand is a separator that reaches the output.
  - `-contains`, `-in`, `-eq` and the rest, because they compare values, not patterns, and no drive
    has needed them.

### D3 — for `-replace`, only the pattern is exempt

In `'x' -replace '<p>','<r>'`, only `<p>` is exempt. Both `<r>` and the left operand are judged as
they are today (fact 4). The comma inside the operand is the lexer's own split point
(`_WORD_SPLIT_RE` splits on `,`), so the first word after the operator is the pattern.

### D4 — the operand must be one quoted literal

The exempt operand must be **one quoted literal**: either single-quoted, or double-quoted with no
`$` and no backtick (`wpc2-b`). An unquoted operand, or one with any interpolation, is judged as it
is today. The literal must also contain no PowerShell quote character — ASCII `'`/`"` **or** a
Unicode smart quote (`‘ ’ ‚ ‛ “ ” „`) — because `_lex` closes on the ASCII pair only while real
PowerShell closes on the smart quotes too, so a smart quote inside an apparently closed literal could
end the string early (`wpc2-g`).

- `-notmatch $pattern` gains nothing.
- A double-quoted operand that interpolates is a value the shell builds, so it is still judged.
- The conservatism of `_LITERAL_DOLLAR` stays everywhere else.

### D5 — the PowerShell reading only; the `"Shell"` key stays strict

The bash reading never applies the exemption. In bash, `$x -match '/outside'` is a command named by
`$x`, and its argument is a path.

A key that reads both dialects (`"Shell"`) is refused if the bash reading refuses. So the change
reaches Copilot only when `_shell_key` (`copilot_acp.py:493`) returns `"PowerShell"`.

- That key comes from a tracked `tool.execution_start` with `toolName "powershell"`.
  - R2: the tracking fires for **subagent** calls too. `track_call(self.calls, …)` runs on every
    armed raw event (`copilot_acp.py:1292`), with no subagent filter; `_is_subagent` gates only
    notices, compaction and errors. The recorded drive refusals were in fact a subagent's
    (`task`/`explore`). So R1's doubt is refuted at the code level. The one gap is empirical: the
    raw `toolName` of those subagent calls is not recoverable from the trial DB (see `wpc2-e`), so
    the live key (`"PowerShell"` vs `"Shell"`) on this drive cannot be read back.
- `turn_write_shell_mcp.jsonl` records that event **before** its `session/request_permission`
  (lines 46/48/50, then 52/55/58).
- Claude's `PowerShell` tool keys directly.
- `wpc2-e` asks whether a Windows host should read `"Shell"` as PowerShell only. Recommended: no.

### D6 — the lexer carries what the decision needs

Today the PowerShell branch of `_lex` (`:2958`) keeps `{` and `}` only as text that `_words` trims,
and drops `|`, `;`, `(` and `)`. It must record two things per argument:

- whether the argument begins a statement (D1);
- whether it was one fully quoted literal (D4).

`_words` passes both on, and `_read_command` skips `_memo_judge_word` for an exempt operand — in
**both** passes that judge its words: the main word loop (`:3200-3206`) and the inner-brace pass
(`:3209-3236`).

- The exempt unit is the whole argument (D4: one fully quoted literal operand), so a word the brace
  pass would otherwise expand out of it is skipped too (R3). Skipping only the main-loop word while
  the brace pass still expands `'\d{1,3}'` into `'\d1'`/`'\d3'` and judges those would leave a
  separator-plus-quantifier pattern refused, which contradicts the requirement's unconditional "SHALL
  NOT judge … as a path". A regex quantifier `{n,m}` beside a `\` is a common, legitimate pattern
  (an IP or path regex), so this is not a corner case.
- Skipping the brace pass for an exempt operand is safe: `expand_braces` models an inner POSIX/cmd
  shell that would brace-expand an argument it receives, but a consumed `-match`/`-like`/`-replace`
  pattern operand is never handed to such a shell (fact 2). Only an exempt argument is skipped; every
  other brace-bearing argument is still expanded and judged.
- Still judged as they are today: the same statement's other, non-exempt arguments, and nested
  substitutions (`nested`) — which cannot occur inside a `$`-free quoted literal anyway.
- A glued opener such as `{$_.FullName` must count as a statement start.

*Alternative considered:* a regex over the raw command, in the style of F478's
`_hub_own_powershell_write`. **Rejected**, because it would duplicate the lexer's quoting rules and
drift from them. F478 could use a regex because its grammar was a single fixed statement.

### D7 — the message stays

The `_OUTSIDE` and `_UNCHECKED` text is unchanged.

- A Copilot agent never sees the reason, because `copilot_acp.py:864-868` answers `reject_once`
  only. Fixing that is WPC-1's work.
- If the operator picks (d) instead, this decision is replaced (see the top of this file).

## What each route returns when what it calls raises

Both routes fail closed:

- **Copilot:** `copilot_acp` decides inside a `try`, and an exception answers `reject_once`
  (`copilot_acp.py:2415-2417`).
- **Claude:** `approve_tool_call` catches any exception from `_decide`. It answers `deny` with
  *"the workspace check failed on this call (<type>); ask the operator with ask_user"*
  (`mcp_server.py:3744-3753`).

A new fault in the lexer therefore fails closed on both routes. Task 1.9 pins this for the new code
path.

## Risks / Trade-offs

- **Fail-open surface.** The exemption skips judging, so a mistake in D1 or D2 lets a path through.
  - The guard is the set of controls in task group 1. Every bypass listed there is refused today
    and must stay refused.
  - The worst plausible miss is a command-mode element misread as being in expression mode.
  - D1's "first token" test is deliberately strict. Anything that is not clearly a variable, a
    string, a number or an opener is treated as command mode.
- **A pattern that is also used as a path later.** `$p = 'C:\outside'; $x -match $p; Remove-Item
  $p` is not affected.
  - The literal is an assignment value, not an operand, so it is still judged.
  - `Remove-Item $p` is the already-allowed variable residual, not something new.
- **Nested shells.** `powershell -Command "<text>"` is in command mode at the outer level, so the
  outer reading gains nothing.
  - R2 confirmed the judge does **not** re-lex the inner `-Command` text as a PowerShell command:
    only `$(...)` (and bash backticks) recurse via `nested`. But `_words` still splits the inner
    quoted literal on whitespace and judges every word, so `powershell -Command 'Remove-Item
    C:\outside'` is refused today on `C:\outside` (measured). The nested shell therefore gains
    nothing, and the exemption never reaches the inner text (its operator, if any, is inside a
    single argument the exemption logic does not re-parse). Fails safe.
- **Regex quantifiers in the pattern (R3).** A pattern operand often contains a brace quantifier
  (`'\d{1,3}'`, `'\.git\\{1,2}'`). The inner-brace pass (`:3209-3236`) expands any brace-bearing
  argument and judges the pieces, so beside a `\` separator such a pattern is **refused today and
  would stay refused** if the exemption skipped only the main word loop. D6 therefore skips the
  exempt operand in the brace pass too; without that, the change leaves a whole common class of
  pattern still refused, breaking the requirement's unconditional wording. The two *recorded* drive
  refusals have no braces, so they are fixed either way — this is about not shipping a half-exemption.
- **Coverage.** `Select-String -Pattern`, `Where-Object -Match` and `rg`/`grep` patterns stay
  refused (`wpc2-c`). Agents may still hit them.
- **Path normalisation stays refused.** `$s -replace '\\','/'` is common, and after this change it
  is still refused, now on its replacement `'/'`. On a drive-letter host, `/` reads as the drive's
  root (measured: `$s -replace 'a','/'` is refused today). D3 keeps it that way on purpose:
  `('x' -replace 'x','/')` can be the value of a `-Path`. `wpc2-f` asks whether a one-character
  separator replacement should be exempt.

## Migration Plan

None. Ship with a Hub restart, on a trial Hub first.

## Round log

- **R1 (2026-10-12, HEAD `6208e9a5`).**
  - Reproduced both refusals and the controls through `_decide`.
  - Traced refusal 1 to rule 5, and refusal 2 to rule 3 via `_LITERAL_DOLLAR`, not `$_`.
  - Verified facts 1–5 in real PowerShell.
  - Found that naive (a) can be bypassed in three ways: in command mode, by unary `-split`, and by
    the `-replace` replacement.
  - Found that (b) as framed fixes nothing.
  - Checked that the fixture records START before PERM, which the dialect key depends on.
- **R2 (2026-10-12, HEAD `6208e9a5`, work PC).** Independent re-derivation; R1 not trusted.
  - Re-ran every control and both refusals through `_decide`. Confirmed the "allowed today" and
    "refused today" tables, the `$_`/`$PSItem`-are-fine / single-quoted-`$`-is-the-trigger split,
    and that `$s -replace 'a','/'` is refused on `'/'` (so after the exemption, `-replace`'s
    replacement keeps the row refused — D3/`wpc2-f` consistent).
  - **Bypass sweep, all refused today (added as controls):** `(Copy-Item $x -match 'C:\o')`
    (command mode inside `(`); `Write-Output $x -match 'C:\out'` (command mode); `Invoke-Expression
    'Remove-Item C:\o'`; a here-string `@'…C:\outside…'@`; a newline statement separator; and
    `powershell -Command 'Remove-Item C:\outside'`. Each fails safe because the outside path is a
    word `_words` still judges, or the element is command mode under D1.
  - **Nested `-Command` text is not re-lexed** as a command (only `$(...)` recurses); its words are
    still judged. The design's nested-shell note updated.
  - **Subagent tracking confirmed from code** (`track_call` on every armed raw event, shared
    `self.calls`), and the two recorded refusals were a subagent's (`task`/`explore`). R1's doubt
    refuted; one empirical gap remains (raw `toolName` not stored in the DB) — folded into `wpc2-e`.
  - **Correction carried into the proposal:** the `evt-12c4` quote had a spurious `-Force`; the DB
    command (`out-3788f09bbae6`) has none. Only `evt-9d81` carries `-Force`.
  - **F478 precedent consistent:** `_hub_own_powershell_write` is a narrow, strictly-guarded
    exemption (allow-list path, exact grammar, literal never read) for a *write*; this change
    exempts a read-only consumed pattern operand, a lower-risk shape, and deliberately uses the
    lexer rather than a regex (D6) because the grammar is open-ended. No contradiction.
  - **Limitation noted (tasks §1):** a pattern operand containing a comma (e.g. `-replace
    'a,C:\out','x'`) is split by `_WORD_SPLIT_RE`; only the first word is the pattern, so the rest
    stay judged — a false refusal, never a bypass. Acceptable; recorded.
- **R3 (2026-10-12, HEAD `6208e9a5`, work PC).** Independent re-derivation; neither R1 nor R2
  trusted. Re-lexed and re-judged from the code.
  - **Citations re-verified at HEAD:** rule 3 `:2321`, rule 5 `:2370`, `_LITERAL_DOLLAR` `:1264`,
    `_lex` `:2958`, `_words` `:3112`, `_read_command` `:3153` (main word loop `:3200-3206`, inner-brace
    pass `:3209-3236`, nested pass after it), `_decide` `:3495`; Copilot fail-closed
    `copilot_acp.py:2415`, Claude fail-closed `mcp_server.py:3750`. All correct.
  - **HIGH — the inner-brace pass defeats the exemption for `{n,m}` patterns.** The brace pass
    iterates `arguments` and re-judges every expanded word with no exemption; D6 as written (R1/R2)
    left it unchanged. Measured today: `$a -match 'a{1,2}'` ALLOW, but `$ip -match '\d{1,3}'`
    REFUSE on `'\d1'`, and `$x -match 'C:\x{1,2}'`, `$x -match '\.git\\{1,2}'` all REFUSE. So a
    separator-plus-quantifier pattern would stay refused after the as-designed change, contradicting
    the requirement. **Fixed here:** D6 and task 2.3 now skip the exempt operand in the brace pass
    too; added failing row 1.2g (`$ip -match '\d{1,3}'`, must ALLOW) and control 1.6f (a non-exempt
    command-mode `'\d{1,3}'` still refused).
  - **Adversarial sweep, written before reading the controls, all refused today through `_decide`,
    none a bypass of the as-designed exemption:**
    - `-f` format operator — `Remove-Item ('{0}' -f 'C:\outside\f')` REFUSE. `-f` is an
      expression-mode binary operator **not** on D2's list and it *produces* its result, so it must
      stay judged. Added control 1.5f.
    - redirection target — `$x -match 'y' > C:\outside\f` REFUSE on the target, a separate word.
      Added control 1.6r.
    - binary `-split` outside **left** operand — `'C:\outside\f' -split '\\'` REFUSE; the left
      operand is not exempt (D3's logic, fact 3). Added control 1.5s.
    - `.NET` static call `[IO.File]::Delete('C:\outside\f')` REFUSE — `[` is not an expression-mode
      starter and there is no operator; not masked.
    - `cmd /c`, `Start-Process … -ArgumentList '/c del …'`, dot-sourcing `. 'C:\…'`, `&{ Remove-Item
      C:\… }`, backtick continuation — all command mode or a separate word; REFUSE, not masked.
    - pipeline into a writer `$x -match 'C:\outside' | Set-Content` — the operand is exempt but is
      consumed as a pattern; `Set-Content` receives a Boolean, not the path. Not a bypass.
  - **Spec-wording check:** the delta's "a quoted literal that is the right-hand operand of one of
    these binary operators" plus the fixed operator list and the "SHALL still judge" scenarios pin
    exactly the exemption; no broader reading (any operator, left operand, unary `-split`, `-join`,
    `-f`) is licensed. One tightening added — see `wpc2-g`.
  - **R2's `track_call` claim confirmed from code.** `on_raw_event` (`copilot_acp.py:1287`) calls
    `track_call(self.calls, event_type, data)` at `:1292` unconditionally, before any subagent
    check; `track_call` (`:369`) records `toolName` from `tool.execution_start`; `_is_subagent`
    (`:928`) gates only notices. So the judge sees a subagent's PowerShell calls with the real key.
  - **New open question `wpc2-g`** on whether the spec should name the Unicode quote characters as
    disqualifying a "quoted literal" (a smart-quote inside a single-quoted argument closes the string
    in real PowerShell but not in `_lex`); recommended yes, as a belt-and-braces spec sentence.
- **R3.** Done (this entry).

## Open Questions

These are the open questions for the operator.

- **`wpc2-a`: which approach?**
  - Options:
    - (a) narrowed, as in D1–D6;
    - (b') a single-quoted PowerShell `$` is literal;
    - (c) only known path-taking parameter positions are paths;
    - (d) leave the judge alone and fix the message.
  - **Recommended: (a) narrowed.**
    - It fixes both refusals.
    - It skips judging only an operand that PowerShell consumes as a pattern and never produces.
    - Every bypass found in R1 is a named control.
  - Why not the others:
    - (b') fixes refusal 2 only. It also gives up the conservatism that catches
      `powershell -c '…$env:TEMP…'`.
    - (c) fails open for unknown cmdlets and native programs, and it is a rewrite.
    - (d) leaves the turn ending on a routine listing.
  - If the operator picks differently, see the top of this file.
- **`wpc2-b`: may a double-quoted operand qualify?**
  - Options: single-quoted only; or also double-quoted with no `$` and no backtick.
  - **Recommended: also double-quoted without `$` or a backtick.** Such a string is literal in
    PowerShell, and agents write both forms.
  - If single-quoted only: D4 shrinks, and rows 1.4 move to the controls.
- **`wpc2-c`: should this change cover other pattern positions?**
  - Options:
    - none;
    - `Select-String -Pattern` only;
    - also `Where-Object -Match` and `-NotMatch` (simplified syntax, command mode);
    - also `grep`, `rg` and `git grep` pattern positions in bash.
  - **Recommended: none now.**
    - Each is a grammar of its own command, with its own bypasses. For example,
      `Select-String -Pattern x -Path C:\outside` must still refuse the path.
    - File them as a follow-up if drives show them.
  - If others are included: add one decision per command, with its own controls.
- **`wpc2-d`: reword the refusal for a quoted `$`?**
  - Options: leave the text; or say "a `$` in a quoted string reads as a variable an inner shell
    would expand".
  - **Recommended: leave it, and let WPC-1 decide how a reason reaches Copilot.** Until WPC-1
    lands, only Claude agents and the operator read the wording.
  - If reworded: change one string at `mcp_server.py:1414`, plus the existing tests that pin the
    text of `_UNCHECKED`.
- **`wpc2-e`: should an unknown-dialect (`"Shell"`) call on a Windows host get the exemption?**
  - Options: no, both readings stay; or read `"Shell"` as PowerShell on a drive-letter host.
  - **Recommended: no.**
    - The key is `"Shell"` only when the tool name is unknown.
    - Assuming a dialect there is the one place where a misread could open the boundary.
  - **R2 note:** the recorded drive refusals were a subagent's, and their raw
    `tool.execution_start.toolName` is not stored in the trial DB (`agent_outputs` keeps the
    kind-label `"shell"`, not the raw name), so whether they keyed `"PowerShell"` or `"Shell"`
    cannot be read back. If they keyed `"Shell"`, the fix would **not** rescue them (the bash
    reading still refuses `\\.git\\` as a UNC root). IMPL should capture one live subagent
    `tool.execution_start` payload (hub log at debug, or a fixture) to settle which key Copilot's
    Windows PowerShell subagent calls actually get. This does not change the recommendation, but it
    decides whether the change fixes the *observed* drive failures or only equivalent main-agent
    ones.
  - If yes: D5 changes, and the bash-reading controls must run under the `"Shell"` key on Windows.
- **`wpc2-f`: may a `-replace` replacement that is one bare separator (`'/'` or `'\'`) pass?**
  - Options: no, the replacement is judged like any value (D3); or exempt a replacement that is
    exactly `/` or `\`.
  - **Recommended: no, for now.**
    - The output of `-replace` is a value the command can use as a path, and `/` alone is the
      drive's root.
    - Revisit it if drives show agents normalising paths this way often.
  - If yes: D3 gains one exception, and task 1.2's control becomes an allowed row, plus a control
    `Set-Content -Path ('x' -replace 'x','/') -Value y` that must still refuse.
- **`wpc2-g` (R3): must a "quoted literal" exclude the Unicode quote characters?**
  - `_lex` knows only ASCII `'` and `"`. Real PowerShell also closes a single-quoted string at `’`
    (and the other smart quotes). So `'$x -match ''a’ ; Remove-Item C:\outside ; ‘'''` is, to the
    lexer, one fully single-quoted argument that D4 would mark exempt, while PowerShell closes the
    string at `’` and runs `Remove-Item C:\outside`. The exemption would then skip a word that is a
    real path. Not yet reproduced against the PowerShell parser.
  - Options: treat any PowerShell quote character (including `‘ ’ ‚ ‛ “ ” „`) inside the literal as
    disqualifying; or accept the ASCII-only reading.
  - **Recommended: disqualify.** D4 should require the operand to contain no PowerShell quote
    character at all, and the spec should say so. It is one predicate in the classifier and removes
    the only sweep shape R3 could not rule out purely from the ASCII lexer.
  - If accepted as-is: add a control row proving `_lex`'s ASCII reading keeps the whole argument a
    single word (so nothing after `’` is a separate judged word) and document the residual.
