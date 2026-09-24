# Design — a drive or a home variable names a directory by itself

**Built on the recommended answer to D5** (*"How strict should the shell judge be about bare `$VAR` /
`$(…)`?"*): refuse a bare reference only where it names a directory by itself, the way rule 4
already refuses `~`, and leave every other bare expansion allowed. **If the operator answers
otherwise:** answer (a) (accept the disclaimer) drops D2 and D3 below and keeps D1 (F402 needs no
decision); answer (b) (refuse every bare expansion) is not buildable under the default posture — see
the options — and would need its own change and a new default.

**Also built on D4's recommended answer** (the default posture stays `workspace`). Under that answer
this judge decides every unattended run, so a rule that refuses ordinary shell costs every agent,
not only agents whose operator chose the posture. That is the reason D5's recommendation is narrow.

**R1, 2026-09-24.** file:line at `ce086b6`; measured as in the proposal.

## D5 — the options, with evidence

| Option | What it refuses | Cost | Verdict |
|---|---|---|---|
| (a) Accept the disclaimer; close F401 as documented | nothing new | `cp x $HOME` stays allowed while `cp x ~` is refused, the incoherence F375 removed for `..` | rejected: leaves the spec's own shorthand rule inconsistent |
| (b) Refuse every separator-less word with an expansion | `$HOME` and everything else | refuses `echo $x`, `for f in $files`, `test -n "$VAR"`, and **every commit** Claude Code makes: `git commit -m "$(cat <<'EOF' …)"` lexes to the single word `$(…)` (measured: `_words` yields `['git','commit','-m','$(…']`) | rejected: breaks the default posture |
| (c) Refuse a bare expansion only in a destination position of a known file tool (`cp`/`mv`/`tee`/`Copy-Item -Destination`/a redirect) | `cp x $DEST` | a command-aware layer in a judge that is deliberately word-based (`a-url-is-not-a-path` D1); defeated by `bash -c`, functions and aliases; large | rejected: cost out of proportion, and still incomplete |
| **(d) Refuse a bare reference to a directory variable, and a `..` before an expansion** | `$HOME`, `${HOME}`, `$PWD`, `$OLDPWD`, `$USERPROFILE`, `$TMP(DIR)`, `$TEMP`, `$APPDATA`, `$LOCALAPPDATA`, PowerShell `$HOME`/`$PWD`/`$env:…`, `%…%`; `..$x` | `echo $HOME` and `ls $PWD` are refused, as `echo ~` already is | **recommended** |

(d) is the F375 rule applied to the shorthand's other spellings. The set is closed and written in
the code beside `_TILDE_PREFIX_RE` (`hub/hub/mcp_server.py:1051`); the requirement states that any
other variable is not judged.

**Interaction with D4's card.** Under (d), `cp x $DEST` is still allowed and the allow reason today is
*"inside your workspace"* (`:1586`). Nobody reads an allow reason today (`record_permission_decision`
records refusals only), but `an-ask-me-card-says-what-workspace-only-would-decide` shows it to the
operator, where "inside" would overclaim. That change makes the reason say the command names values
decided when it runs; this change does not need it.

## Decisions

### D1 — A PowerShell drive keeps its colon (F402)

`_words(arguments)` (`:1484-1499`) becomes `_words(arguments, dialect)`. In the PowerShell reading, a
piece is first trimmed of `_WORD_TRIM` less `:`; if that fullmatches
`_PS_DRIVE_RE = [A-Za-z]:[^:\\/]*` or `(?i)temp:[^:\\/]*`, it is the word (colon kept). Otherwise the
existing trim applies. Rule 4 then checks, before its option handling:

- `[A-Za-z]:…` → `_judge_path(word, root, word, argument, continues)`. `_where` gives Windows'
  answer: measured, `_where("Z:")` → outside (`it resolves to 'Z:'`), `_where("C:")` and
  `_where("C:foo")` → inside for a workspace on C. On a POSIX host (pwsh on Linux, no letter drives)
  `Z:` resolves as a file name inside, which is what pwsh does with it (an error, nothing written).
- `Temp:…` → `_judge_path(os.path.join(tempfile.gettempdir(), rest), …)` quoting the word;
  `gettempdir` can raise when no temp directory is usable, so it is wrapped and becomes
  `_UNRESOLVED`.
- A colon-joined option value (`_COLON_OPTION_RE`, `:1047`) is read with the colon kept, so
  `-Destination:Z:` judges `Z:`. **R2: the trim rule above does not do this by itself.** Measured,
  `_words` turns `-Destination:Z:` into the word `-Destination:Z` (the trailing `:` is in
  `_WORD_TRIM`), and the piece `-Destination:Z:` does not fullmatch `_PS_DRIVE_RE`, so it falls to
  the existing trim and rule 4 sees the value `Z`. The PowerShell trim must also keep the colon when
  the piece, trimmed of `_WORD_TRIM` less `:`, is `_COLON_OPTION_RE` followed by a `_PS_DRIVE_RE`
  fullmatch. Task 1.1's `-Destination:<other>:` row fails if it does not.
- **R2: with a separator after the drive** (`Z:foo\bar`, `-Destination:Z:foo\bar`) the word is
  not rule 4's; today rule 6 refuses it by its tail (`'\\bar'`). `the-shell-judge-reads-a-word-whole`
  (design D2 step 3) keeps that refused when it replaces rule 6, by not breaking at a drive colon in
  the PowerShell reading (R3: and in the bash reading on a Windows host). The two changes agree on
  one meaning of `Z:` per platform.

`s:a:b` (a second colon) and `HEAD:README.md` (more than one letter, not `Temp`) do not match and
stand, meeting F402's constraint. Bash is unchanged on a POSIX host (F402: Git Bash wrote a file named `C:`); on Windows see D4 (R3).

### D2 — A directory variable, referenced alone, is uncheckable (F401)

In rule 4, after the `~` check and on the same `value` (the whole word, or an option's joined value):

- bash: `\$(?:NAME|\{NAME\}?)` — the trailing `}` is optional because `_words` trims it (measured:
  `${HOME}` reaches the judge as `${HOME`);
- PowerShell: `\$(?:HOME|PWD)` or `(?i)\$env:NAME`;
- either: `%NAME%`;

with `NAME` from `HOME|PWD|OLDPWD|USERPROFILE|TMPDIR|TMP|TEMP|APPDATA|LOCALAPPDATA` (bash names are
case-sensitive, PowerShell's and cmd's are not), matched **at the start of the value and not
followed by a name character** (R2: R1 wrote "fullmatched", which contradicts "not followed by a
name character" and misses `cp x $HOME.bak` and `cp x $PWD..`, a sibling of home and a sibling of
the workspace, both separator-less, both outside; a prefix match refuses them at no extra cost,
since `echo $HOME` is already refused). The bash form also takes any parameter expansion of such a
variable, `${NAME` followed by a non-name character or the end (`${HOME-x}`, `${HOME:+y}`), whose
value is the directory or a word the operator wrote; `${HOME%/}` has a separator and is rule 3's.
Match → `_refuse(word, _UNCHECKED)`. A `$` the lexer marked literal (`_LITERAL_DOLLAR`, single
quotes or an escape) does not match, so `echo '$HOME'` stands; this is narrower than rule 3, which
counts a literal `$` too (`_expands`, `:1161-1170`), and it is deliberate: the word is exactly the
reference, and a quoted reference is text.

**Measured words** (`_lex` + `_words`): `"$HOME"` → `$HOME`; `${HOME}` → `${HOME`;
`--target-directory=$HOME` → `$HOME`; PowerShell `-Destination:$HOME` → one word
`-Destination:$HOME` (the colon form); `$env:TEMP` → `$env:TEMP`.

### D3 — `..` before an expansion is uncheckable

In rule 4, a word (or option value) whose text before its first `$`, `_SUBSTITUTION` or `%` is
exactly `..` is refused as uncheckable. Git Bash (F403, R2 of F375): `cp notes.md ..$x` with `x`
unset landed in the parent. No ordinary word starts `..$`.

### D4 (R3) — three separator-less shapes the same rule must cover

R3 looked for words rule 4 still allows after D1-D3 that name a directory by themselves:

- **The drive reading is keyed on the platform, not only the dialect.** On a Windows host the Bash
  tool hands words to native programs and to nested PowerShell (`powershell -c 'Copy-Item x Z:'`,
  `python w.py Z:`; both allowed today, measured at `b66f6a6`), which read `Z:` as drive Z. So D1's
  drive words are judged in the bash reading too when `os.sep == "\\"`. Git Bash's own `cp x Z:`
  writing a file named `Z:` becomes a harmless false refusal; `cp notes.md C:` with the workspace on
  C still stands (`_where` joins `C:` to the root). `the-shell-judge-reads-a-word-whole` D2 step 3
  makes the same call for a drive with a separator after it; the two changes keep one meaning of
  `Z:` per platform. On POSIX, bash is unchanged.
- **`~` after a colon.** Bash expands a tilde prefix after `:` in an assignment-shaped argument
  (measured in Git Bash 5.2.37: `echo of=c:~/y` prints `of=c:/c/Users/huida/y`), so `dd if=x
  of=c:~` names the home directory. `_words` splits at `=`, leaving `c:~`, which rule 4 allows (and
  D1's drive reading would judge `c:~` as inside drive C). So the `~` check also applies to the text
  after the value's last `:` (`_TILDE_PREFIX_RE.fullmatch`), refused as `_UNCHECKED`. Cost:
  `git show HEAD:~` — none in practice.
- **A separator-less glob beginning with `..`.** `cp x ..*` and `cp x .{,.}*` (after
  `the-shell-judge-reads-a-word-whole`'s brace expansion) are allowed today; with `globskipdots`
  off (bash before 5.2, e.g. Ubuntu 22.04's 5.1), `..*` matches `..`. A value that begins with `..`,
  holds `*`, `?` or `[`, and satisfies `fnmatch.fnmatchcase("..", value)` is judged as `..` (the
  sibling change's D3, applied to rule 4). **`.*` and `.?` are deliberately left out** when
  separator-less: they are as often a quoted regular expression (`grep '.*' f`), which the judge
  cannot tell from a glob because the lexer does not mark a quoted `*`. Named residual:
  `chmod -R x .*` on bash 5.1 reaches the parent. This is part of the D5 answer the operator gives.

### Totality

Regex matches, a slice, `tempfile.gettempdir` (wrapped), and `_judge_path` (total). No route changes;
`approve_tool_call` still returns `_decide`'s answer (`:1708`).

## Risks

- `echo $HOME`, `ls $PWD`, `cd $HOME` are refused (as `echo ~` is). The reason says where it points
  cannot be checked and to write a workspace-relative path.
- A PowerShell run whose workspace is on drive D sees `C:` refused. Correct: it is another drive.
- Reaches `:8000` on edit (as F375).

## Open questions

1. D5 itself (recommended (d)).
2. The variable set: include `PWD` (mirrors `~+`, which F375 refuses) — recommended — or leave it out
   because the run starts in the workspace?
