# Design — an arguments file written from PowerShell is the Hub's own

## Context

`_hub_own_call` (`hub/hub/mcp_server.py:1742-1775`) gives standing to three things: the Hub's MCP tools, one
shell invocation of `aw-tool` (`_hub_own_command`, `:1707-1728`), and a file-tool write of `.json` files inside
the calls root (`_hub_own_write`, `:1731-1739`). It runs first in `_decide` (`:1803`), in `approve_tool_call`'s
operator posture (`:2007`), and in Copilot's ACP handler for `execute` and `edit` requests
(`copilot_acp.py:533-539`). It is total: any raise is `None`.

The notice's fallback route for the arguments file is a PowerShell `Set-Content -Encoding utf8`. No case covers
that route, so it is decided by the workspace judge or a card. The workspace judge reads the JSON literal word by
word. Rule 6 (`:1359-1364`) refuses any word with a colon before its first separator, such as `path":"spec/x.html`,
by judging its tail as a root path (proposal, table). That is F478.

## Goals / non-goals

- **Goal:** the form the notice instructs is decided the same way as the file-tool route it stands beside: with
  standing, in every posture, without reading the arguments as paths.
- **Goal:** unblock slice 3's task 9.10 without waiting for `the-shell-judge-reads-a-word-whole`.
- **Non-goal:** fixing rule 6 for other commands. That is F362, owned by `the-shell-judge-reads-a-word-whole`
  (proposal, "Which change owns it").
- **Non-goal:** a bash form (Open question 1).

## Decisions

### D1 — Standing for the exact form, not a looser judge

Options weighed:

- **(a) Wait for `the-shell-judge-reads-a-word-whole`.** Its D2 would allow the measured 9.10 shape. But it
  still refuses an argument value naming `..`, an absolute path or a URL, which are data. It also leaves the
  PowerShell route carded under "Ask me". And it is about 72 tasks away. Rejected as the fix for this instance;
  it remains the fix for the general one.
- **(b) Loosen rule 6 narrowly now**, for example by not opening a candidate after a `":"`. Forbidden by that
  change's order clause (*"it must ship before, or with, any change that loosens rule 6 further"*), and rightly.
  Its own prototype measured `.{,.}/x` and `src/{a,..}/../y` flipping to allowed when rule 6 is loosened without
  brace expansion. Rejected.
- **(c) Teach the judge that a `Set-Content -Value '…'` literal is data**, inside `_read_command`. This keeps
  slice 3's invariant that standing never overrides a judge refusal. But the write is still carded under "Ask
  me", which is the friction F477 removed for the compound form. It also puts a cmdlet's parameter semantics
  into the general judge, which reads every command. Rejected.
- **(d) Remove the PowerShell route from the notice.** The notice cannot bind a model. 9.10's model wrote from
  PowerShell when it had `create` available, and the refusal's false reason ("outside your workspace") made it
  give up rather than retry with the file tool. Rejected. The notice keeps naming the route, so the Hub must
  decide it correctly.
- **(e) A fourth standing case for the exact instructed form. Chosen.** The write has exactly the effect case 3
  already allows by standing: a `.json` file in the Hub's git-excluded calls directory, holding data that only
  `aw-tool` reads and that the called Hub tool judges as its own arguments. A different route to the same
  effect gets the same standing, which is the argument slice 3 D8 makes for the call command itself.

**What (e) amends in slice 3.** Slice 3's requirement says that its rule *"can only spare a request from being
asked about, never refuse one or allow one the workspace decision would refuse for any other reason"*. Case 4
does allow a request that the workspace decision refuses. That is deliberate, and the requirement is modified to
say so. The refusal it overrides is always a reading of the `-Value` literal. The `-Path` must pass the
calls-root rule, which is stricter than the workspace decision's reading of it, and every other character of the
command is fixed by the grammar. So no refusal of anything *the command does* is overridden: it writes one file,
inside the calls root. The invariant still holds for cases 2 and 3, and for every near miss of case 4.

### D2 — The grammar, and the traps it closes

The predicate parses the raw command text itself. It does not use `_lex`: `_lex` returns arguments with their
quoting removed, and case 4 depends on *where* the literal was. Its shape:

```
Set-Content <p1> <p2> <p3>      each <p> one of:
  -Path <path> | -LiteralPath <path>       <path>  = bare or '…', _PLAIN_COMMAND_CHARS_POWERSHELL less space
  -Value '<literal>'                       <literal> = ( [^'‘-‛\x00] | '' )*, its closing ' then a space or the end
  -Encoding <utf8>                         <utf8> = utf8 or 'utf8', any case
```

The command name and the parameter names may be in any case, because PowerShell compares them case-insensitively.
Each parameter appears exactly once, in any order, separated by one or more ASCII spaces, with only ASCII spaces
before and after the whole command. **(R3)** In particular, the literal's closing `'` is followed by an ASCII space
or by the end of the text, and nothing else (see "Nothing joined to the literal" below).

Each rule, and what it closes:

- **Smart quotes. Measured** on 5.1.26100: `Write-Output 'a’; Write-Output INJECTED; ’'` printed `a` and then
  `INJECTED`, and `'x’’y'` is a three-character string. PowerShell treats U+2018, U+2019, U+201A and U+201B as
  single quotes, both to close a literal and to double one. A literal holding any of them falls through, and so
  does a path holding any of them, which the plain set already excludes. Without this rule, a "literal" could
  close early and run a second command under standing. This is the case's one real hazard, and it gets a test of
  its own (task 1.3). **(R3)** The set is complete, not a list of candidates: R3 passed every BMP character
  through 5.1's own tokenizer (`Parser::ParseInput("Write-Output 'a<c>b'")`), and exactly U+0027 and U+2018 to
  U+201B end the literal. The typographic *double* quotes U+201C to U+201E do not. Inside a single-quoted literal
  they are content (measured: written verbatim), so the grammar allows them. R3 also ran the hazard in the
  grammar's own shape, `Set-Content -Path '.agentweave/calls/q.json' -Value 'a<q>; Set-Content pwned.txt x;
  Write-Output <q>' -Encoding utf8`. For each of the four quotes, `pwned.txt` was created.
- **Nothing joined to the literal. (R3, measured.)** In argument mode, text joined to a closing `'` with no space
  is a second argument, and it is evaluated before the binding fails. `-Value 'a'(Write-Output INJECTED)` ran the
  subexpression (the error names its output, `INJECTED`), `-Value 'a'$env:USERNAME` expanded the variable, and
  `-Value 'a'b` passed `b`. Each failed only at parameter binding, so no file was written, but the subexpression
  had already run. So an implementation that matched `-Value '…'` without requiring a space or the end after the
  closing quote would give standing to a command that runs code. `'a''b'` is the one exception, because `''` is
  the escaped quote: it wrote `a'b`. Because no single `'` is content, the literal's extent is unambiguous.
- **A NUL** falls through: the text a harness hands to the shell may be cut at a NUL, so the predicate would be
  judging something other than what runs. **(R3)** That cut is not measured. PowerShell itself kept the NUL,
  given the text through `-EncodedCommand`: it wrote `a\x00b`. The rule stays anyway, because it costs nothing:
  a raw NUL is not valid inside a JSON string, so no arguments file the shim can read holds one.
- **Only full parameter names.** `-Val`, `-Enc`, `-Pa` and positional values fall through. PowerShell's
  prefix matching is not modelled, because a missed prefix only means a card. **(R3, measured on 5.1:)** `-Val`
  and `-Enc` bind. `-Pa` is refused as ambiguous (`-Path`, `-PassThru`). The alias `-PSPath` binds and falls
  through. `-LP` is not a 5.1 alias. The colon form `-Value:'v'` binds and falls through.
- **ASCII dashes and ASCII spaces only. (R3, measured.)** The tokenizer sweep shows that PowerShell also takes
  U+2013, U+2014 and U+2015 as a parameter's dash, and that it separates words at the tab, VT, FF, CR, LF,
  U+0085, U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F and U+3000. The en-dash and em-dash
  forms of the write, and the NBSP and tab forms, each wrote the file. The grammar accepts none of them outside
  the literal, so each falls through to today's answer. `_decide` refuses the 9.10 write in its en-dash, NBSP and
  `-Value:` forms (`'/x.html'`). That means a card or a refusal, never standing. An en dash in the *name*
  (`Set–Content`) is not the cmdlet at all ("not recognized").
- **No other parameter.** `-Force`, `-NoNewline`, `-Stream`, `-Credential`, `-Filter`, `-Include`, `-Exclude`,
  `-PassThru` and `-WhatIf` fall through. `-Stream` would write an alternate data stream. The others are not in
  the notice's form.
- **A `-Value` that is not one literal** falls through. This covers `'a','b'` (an array, through a comma that is
  not in the grammar), `"…"` (expandable), `$x`, `(…)`, `@(...)` and `@'…'@` (a here-string). **(R3, measured.)**
  `'a' ,'b'`, with a space before the comma, is an array too: both forms wrote two lines. So after the literal's
  space, the next text must be one of the other two parameters or the end, not just any token. A single-quoted
  here-string is verbatim as well (`@'<LF>x $env:USERNAME<LF>'@` wrote `x $env:USERNAME`). It falls through for
  exactness, not for safety.
- **`--%`**, the stop-parsing token, is not a parameter of the three, so it falls through. **(R3)** On 5.1,
  `Set-Content --% -Path … -Value 'v' -Encoding utf8` wrote nothing and surfaced no error.
- **Nothing chained.** A `;`, `|`, `&`, newline or redirect outside the literal is not in the grammar. A newline
  *inside* the literal is content (measured: `'line1<LF>line2'` wrote two lines).
- **Wildcards.** `-Path` expands wildcards and `-LiteralPath` does not. The plain set excludes `*`, `?`, `[` and
  `]`, so both read the same path.
- **`-Encoding` is `utf8` only.** The shim decodes a UTF-8 BOM first (slice 3 D3). `utf8NoBOM` and `utf8BOM`
  (PowerShell 7 names: 5.1 refuses `utf8NoBOM` at parameter binding, measured by R2) and `Unicode` fall through.
  **(R2)** `Unicode` is a 5.1 name, not a 7 one. It writes UTF-16LE with a BOM (`FF FE`, measured), which
  `_decode_args_file` (`mcp_server.py:2438-2456`) decodes. So it falls through for exactness, not because the
  shim cannot read it. An encoding the shim cannot decode would only produce a usage error, but the notice names
  `utf8`, and exactness costs nothing.

### D3 — Where the write lands

The predicate resolves `-Path` against the workspace (`_plain_calls_path` → `_inside_hub_calls_root`), as case 2
does for its file word. `Set-Content` resolves it against the shell's current location. These differ only after an
earlier command has changed the location in a session that persists between commands, and that earlier command was
itself decided under the run's posture. Slice 3's requirement already accepts this residual class: *"in a shell
session that persists between a run's commands, an earlier command can …"*. **Measured** on 5.1:
`Set-Content` does not create a missing directory (*"Could not find a part of the path"*). So a write after a
location change lands only where a `.agentweave/calls/` already exists, which is another workspace the Hub made
(slice 3 D14). The consequence is named in Risks.

### D4 — Order with the other changes

- **Slice 3** (`a-run-reaches-the-hub-without-mcp`): this change's delta MODIFIES slice 3's ADDED requirement. The
  code may land while slice 3 is unarchived, after which 9.10 is re-driven. Slice 3's 10.2 then archives and syncs
  its requirement, and only then does this change archive. If this change reached archive first, its MODIFIED would
  name a requirement that `openspec/specs/` does not yet hold. Task 4.1 gates on that.
- **`the-shell-judge-reads-a-word-whole`**: independent (proposal). Disjoint functions. That change rewrites
  rule 6 *after* `_hub_own_call` has run, so a case-4 command never reaches it. After both are built, a near miss
  of case 4 (`-Value "…"`, say) is judged by the new rule 6 like any command.
- **Slices 4 and 5** (`a-copilot-run-shows-its-credits`, `a-copilot-agent-uses-hooks-and-its-own-agents`): they do
  not touch `_hub_own_call` (R1 grep of both changes' tasks). **R2 confirmed it**: no file of either change
  names `_hub_own_call`, `_hub_own_command` or `_standing_rules`.
- **R2 on independence from the shell judge.** That change's files never name `_hub_own*`, and its new D5 runs
  before rule 3 on whole words, but neither of its patterns (`_SCP_ADDRESS_RE`, `_HOST_PORT_RE`) matches
  `path":"spec/x.html`. One more reason for D1(a)'s rejection, **read from its design, not measured**: its
  bounds section names a quoted JSON array of about nine or more two-key objects as refused by its bash
  reading, as too many brace alternatives. Case 4 runs before the judge, so a PowerShell write of such a
  payload keeps its standing after that change ships. A near miss does not.

## Risks

- **A write into another workspace's calls directory**, after a location change that an earlier decision allowed.
  The file is inert data. It is read only when that other run names it in its own `aw-tool` call, and then under
  that run's credential. A run that wins the race between another run's write and call could substitute that
  run's arguments. That needs (1) an earlier allowed location change into another workspace and (2) a
  file-name collision at the right moment. Under "Workspace only", (1) is refused today: `cd ../..` is a word
  outside. Under "Ask me", (1) was a card the operator approved. Accepted as part of the persistent-session
  residual. Open question 2 asks whether it is.
- **A function or alias named `Set-Content`** defined earlier in a persistent session: the same residual, already
  stated in slice 3's requirement for `aw-tool`.
- **Copilot's own measured forms might not match the grammar** (for example with `-Force`, or a double-quoted
  value). Then the write falls through exactly as today: no regression, and no fix for that form. Task 3.2's drive
  records the form Copilot actually sends.

## What each changed route returns when something raises

`_hub_own_powershell_write` is called inside `_hub_own_call`'s `try`, so any raise there is `None` and the
request falls through. Callers: `_decide` (the workspace judge then decides), `approve_tool_call` under the
operator posture (a card), and Copilot's `_hub_own` (`copilot_acp.py:533-539`; its own `try`, then the judge). No
route changes its return shape.

## Open questions

1. **A bash form?** The notice names only PowerShell. Claude has `Write` on every turn, including spec turns that
   are told `shim` (slice 3 D16). Copilot on a POSIX host has `create`. **R1 recommends leaving it out** until a
   drive shows a bash write of an arguments file being refused. **R2 checked**: across the `agent_outputs` of every drive
   profile on this machine (nine, read `mode=ro`), exactly three tool calls wrote an arguments file: Copilot's
   `apply_patch` (`run-000e23023de9`), Claude's `Write` (`run-5ffb0bac65e3`), and 9.10's PowerShell
   `Set-Content`. None was bash. R2 agrees with leaving it out.
2. **The location residual** (Risks, first bullet). Accept it as part of the persistent-session class (R1's
   recommendation), or ask the operator. An alternative that closes it: accept only an **absolute** `-Path`
   equal to a file in the calls root, and change the notice to print that absolute path. That costs a notice
   change in two places and diverges from case 2's relative form. Operator's call; R1 recommends accepting it.

## Round log

- **R1, 2026-10-02** (night iteration 4). Measured the proposal's table with `_decide` in-process at `83b53b6`,
  and PowerShell 5.1.26100's literal, smart-quote, newline and missing-directory behaviour. Found that F478 is
  rule 6, not rule 1, and that the finding's second option (*"a scheme only when followed by `//`"*) is
  already how rule 1 behaves. Read `the-shell-judge-reads-a-word-whole` D2 and its sweep, and split F478 between
  the two changes. Not measured: the shell judge's outcomes (it is unbuilt), and whether Copilot's
  `rawInput.command` for 9.10's write matches the grammar byte for byte. The finding quotes it abbreviated
  (`-Value '{"path":"spec/..."}'`); task 3.2 captures it.
- **R2, 2026-10-02** (night iteration 5, at `9efdfd8`). A fresh comparison with its own probe
  (`.claude/autonomous/tmp/f478_r2_probe.py`), not R1's. **Confirmed:** every row of the proposal's table; every
  line reference (`mcp_server.py` 1103-1122, 1359-1364, 1707-1775, 1803, 2007; `copilot_acp.py` 535; the three
  notice sites); and rule 6, not rule 1. `_lex`/`_words` give the word `path":"spec/x.html` (`continues` true),
  `_URL_SCHEME_RE` does not match it, and `_ABSOLUTE_PATH_RE` yields `/x.html`. **Measured what R1 could not:**
  9.10's exact command, recovered from the trial Hub's `agent_outputs` (`run-b30d4295abaf`, sequence 5, read
  `mode=ro`), fits D2's grammar byte for byte (`-Path '…'`, `-Value '…'`, bare `utf8`, in that order).
  `_decide` refuses it under both `PowerShell` and `Shell`. Real PowerShell 5.1.26100.9444 writes it as
  `EF BB BF` + the JSON + CRLF, and `_decode_args_file` + `json.loads` returns the dict. So the fix reaches the
  instance it is for. **Corrected:** (1) the word is not plain for two reasons, not one (its `"` as well as its
  colon; proposal). (2) `Unicode` is a 5.1 encoding the shim decodes, not a PowerShell 7 name (D2). (3) The
  Copilot route reaches case 4 only under the key `PowerShell`, which needs Copilot's start event to name
  `powershell`. Shown to hold in production by 9.4 (proposal, Impact). Task 1.8 now builds its facts that way,
  and its line reference is fixed. **Answered:** Open question 1 (no bash write in any drive) and D4's slices
  4/5 check. **Re-derived independence** from `the-shell-judge-reads-a-word-whole` (D4). Not re-measured
  (left to R3): D2's smart-quote, here-string, array and prefix traps.
- **R3, 2026-10-02** (night iteration 6, at `afa5a39`). A second fresh comparison. It does not re-run R1's or R2's
  rows: its probes are new (`.claude/autonomous/tmp/f478_r3_sweep.ps1`, `f478_r3_run.py`, `f478_r3_run2.py`,
  `f478_r3_decide.py`). **Measured, not enumerated:** every BMP character through PowerShell 5.1.26100.9444's own
  tokenizer. The closers of a `'…'` literal are exactly U+0027 and U+2018 to U+201B, so D2's exclusion is
  complete. The parameter dashes are `-` and U+2013 to U+2015, and the word separators are a list of 33
  characters, of which the grammar admits only the ASCII space (D2). **Ran every trap D2 names** through
  `-EncodedCommand`, in a scratch workspace. A typographic quote in the grammar's own shape ran a second command
  for all four quotes. The array (with or without a space before the comma), here-string, prefix, alias, colon,
  `--%`, en-dash, NBSP and tab forms each behave as D2 now states. **Added to D2 (1):** the closing quote must be
  followed by a space or the end. `-Value 'a'(Write-Output INJECTED)` ran its subexpression before the binding
  failed, so this is a safety rule, not exactness. It was implicit in "separated by spaces" and is now explicit,
  with tests (task 1.4). **Corrected (2):** the NUL rule's stated reason is not measured. PowerShell keeps a NUL,
  so the rule is kept as cost-free (a raw NUL cannot be in a JSON string). **Corrected (3):** task 1.3's and the
  scenario's example, `-Value 'a’; Remove-Item x; ’' -Encoding utf8`, does not parse in PowerShell (`’'` closes
  an empty literal, and `-Encoding` after it is an unexpected token), so it cannot demonstrate the hazard. They
  now use the measured form. **Checked, no change:** `_lex` has no typographic-quote handling, but today's judge
  is not escaped through it. It reads a quoted literal's words as paths and reads `$` as an expansion even in a
  literal, so `'a’; Remove-Item $env:USERPROFILE\zz; ’'` is refused, and `../../pwned.txt` inside the literal is
  refused. This is not a finding. **What each route returns when the predicate raises:** re-traced at
  `mcp_server.py:1742-1775`, `:1803`, `:2007` and `copilot_acp.py:533-539`; the "What each changed route returns"
  section holds. Every line reference in the proposal still holds at `afa5a39`. **Not measured:** PowerShell 7
  (`pwsh` is not installed on this host). Its tokenizer is believed to share the same quote and dash sets, and
  its `-Encoding utf8` is believed to write no BOM, which the shim's strict UTF-8 step would read. Both are
  unverified.
