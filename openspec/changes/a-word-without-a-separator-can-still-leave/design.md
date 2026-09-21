# Design — a word without a separator can still leave

**R1, 2026-09-21.** Every file:line below was read in this round, and every "measured" row was run
this session. Decisions were measured in two ways: by calling `hub.mcp_server._decide` in-process
with `AW_WORKSPACE_DIR` set to a scratch `ws/` directory, and by running the real command in Git Bash
5.2.37 (msys) and Windows PowerShell 5.1 inside that directory.

## Context

The shell-command judge reads a command in the tool's dialect and judges each word by the first of
six rules that matches it:

- `_read_command` (`hub/hub/mcp_server.py:1402-1433`) splits the command into words with `_words`
  (`:1385-1399`).
- `_judge_word` (`:1141-1168`) applies the rules.
- Rule 4 (`:1158`) returns `None`, meaning "may stand", for any word without a separator.
- `_SEPARATORS` is platform-based, not dialect-based (`:953`): `/` on POSIX, `/\` on Windows.
- Rule 3 (uncheckable: `$`, a leading `~`, `%VAR%`) is gated on `has_separator` (`:1156`).
- Rule 5 (a resolved path) and rule 6 (the backstop) are reached only after rule 4, so they are
  gated too.

`_where` (`:1034-1054`) joins a relative word to the root, takes `realpath`, and compares the result
with `commonpath`. It is already total: `OSError` and `ValueError` become `_UNRESOLVED` or
`_OUTSIDE`. `_judge_path` (`:1057-1073`) wraps it with the `continues` extension check.

Measured today, with the workspace `…/f375/ws` and its parent `…/f375`:

| Word or command | `_decide` today | Real landing |
|---|---|---|
| `cp notes.md ..` (Bash / PowerShell) | allow | parent (both shells) |
| `cp notes.md '..'`, `.""."` | allow | parent |
| `--target-directory=..` | allow | parent |
| `$'..\x00x'` | allow | parent (Git Bash: the copy appeared in `f375/`) |
| `cp notes.md ~`, `~root`, `~-` (Bash); `Copy-Item notes.md ~` | allow | home (PowerShell: appeared in `$HOME`) |
| `cp notes.md ../` | **deny, outside** | parent |
| `cp notes.md $HOME`, `cp notes.md $(dirname $PWD)` | allow | home / parent (non-goal, D5) |
| `Copy-Item notes.md Z:` | allow (judged word is `Z`, the colon is trimmed) | drive Z's current directory (non-goal, D6) |
| `cp notes.md ...` / `'.. '` / `C:` (Git Bash) | allow | a **file** with that name inside `ws/` |
| `Copy-Item notes.md ...` / `'.. '` (PowerShell) | allow | error: "Could not find a part of the path" |
| `git log HEAD~1`, `echo a,..` | allow | not a path |

In Git Bash, `globskipdots` is `on`: `echo .?` and `echo .*` printed only `.x`, never `..`.

## Goals / Non-Goals

**Goals:**

- A separator-less word that is the parent directory is judged exactly as `../` is. A leading `~`
  is refused as uncheckable, exactly as `~/` is.
- No other separator-less word changes decision.
- Row P7 of `test_permission_approver.py` flips to deny. So far it is the only pinned evidence of the
  hole.

**Non-Goals:** as listed in `proposal.md`. The two that are near-misses of this one are argued here
(D5, D6), so a later round can overturn them with evidence rather than rediscover them.

## Decisions

### D1 — Route the two spellings; do not judge every separator-less word

Rule 4 keeps its exemption, and names the two spellings it no longer covers:

```python
if not has_separator:  # 4: a name in the directory the shell runs in -- unless it names another
    if word.startswith("~"):
        return _refuse(word, _UNCHECKED)
    if word.partition("\x00")[0] == "..":
        return _judge_path("..", root, word, argument, continues)
    return None
```

**Alternative rejected: judge every separator-less word with `_where`.** It catches `..`, but
measurement shows it is wrong in three ways:

- **It does not catch `~`.** `os.path.join(root, "~")` resolved to `ws\~`, which is inside, because
  Python does not expand the shorthand. That is correct Python and a wrong answer for the shell.
- **It refuses harmless words on Windows.** `ntpath` reads any `X:` prefix as a drive, so
  `sed s:a:b: file` would resolve `s:a:b` on drive S and be refused as outside. On this
  machine, where the Hub runs, that is a false refusal of ordinary shell.
- **It costs a `realpath` system call for every word of every shell command,** to answer a question
  whose answer is already known for every word except two.

**Alternative rejected: drop the `has_separator` gate from rule 3 as well.** That would refuse every
`echo $x` (D5).

### D2 — `..` is judged, not refused outright

`..` goes through `_judge_path`, not straight to `_refuse(word, _OUTSIDE)`. The one case where the two
differ is a workspace whose parent is itself (a workspace at a filesystem root). There `..` really is
inside, and `commonpath` says so. That keeps the rule identical to what rule 5 does for `../`, which
is what the spec's "judged alike" scenario asserts. The refusal quotes the whole word (`shown=word`),
so a NUL-ended word is quoted as typed, with its `\x00` rendered by `repr` (`_quote`, `:1022`).

`continues` is passed through unchanged. For a `..` that its argument carries on past (the `..` in
`..,x`, split by `_WORD_SPLIT_RE`), `_judge_path` also tries `.._`, which is a child of the parent.
That is outside too, so the added check cannot turn a refusal into an allow.

### D3 — A leading `~` is uncheckable, not outside

`~`, `~user`, `~+` and `~-` are each substituted by the shell from state the judge cannot see: `HOME`,
the password database, `PWD` and `OLDPWD`. `~+` is the current directory and can be inside. So the
honest reason is `_UNCHECKED`, the same constant rule 3 uses, and not `_OUTSIDE`. This matches the
existing requirement's SHALL NOT for separator-bearing words (`spec.md:624-628`).

The shorthand is matched on the lexed word, so a quoted `'~'` (which bash would not expand) is also
refused. Rule 3 already does exactly this for `'~/x'`, because `_expands` reads the lexed word
(`:1076-1085`). The over-refusal is accepted there, and it is accepted here for the same reason.

### D4 — The NUL comparison lives in rule 4, not in the lexer

An argument the shell passes on is a C string: it ends at the first NUL. Measured: in Git Bash,
`cp notes.md $'..\x00x'` copied into the parent. The archived `a-quote-can-spell-a-slash` D5
deliberately decodes `\x00` into a real NUL in the word. Truncating there would change what every
other rule sees, and that change's ANSI-C rows were validated against the untruncated word over
eight rounds. So only rule 4's comparison truncates.

This is not a general NUL rule. A separator-bearing word containing a NUL is left exactly as today:
`_PLAIN_RELATIVE_RE` excludes NUL (`:973`), so such a word falls to rule 6's backstop. Whether every
such word is refused there is not re-derived in R1; this change does not alter that path.

### D5 — A bare variable or substitution stays exempt (non-goal)

`cp notes.md $HOME` is an escape, and it is measured as allowed. Refusing separator-less words that
contain `$` would refuse `echo $x`, `for f in $files` and `test -n "$VAR"`, which is most real shell.
`_decide`'s docstring already disclaims paths built at run time (`:1447-1449`). This is proposed as
a separate finding, where the trade-off can be decided on its own evidence.

### D6 — PowerShell drive-qualified words stay out (non-goal)

`Copy-Item notes.md Z:` reaches the judge as the word `Z`, because `_WORD_TRIM` includes `:`
(`:981`) and `_words` strips it from both ends (`:1396`). A fix has to see the colon, so it
belongs in `_words` or in a dialect-aware pre-check, and it must be PowerShell-only: Git Bash wrote a
file named `C:`. It also has to handle multi-letter PSDrives (`Temp:` in PowerShell 7) without
refusing `git show HEAD:README.md`. That is a design of its own, and it is proposed as a separate
finding.

## Risks / Trade-offs

- **`cd ..` inside a compound command is newly refused**, for example
  `cd sub && make && cd .. && ls`. → This is consistent: `cd ../` is refused today, and so is
  `cd ../other` (the judge resolves every relative word against the root, per the docstring). The
  refusal names `'..'` and says it is outside, so an agent can rewrite it as `(cd sub && make)` or
  `make -C sub`. Accepted.
- **`ls ~` or `echo ~` is newly refused.** → Rare in agent work, and the refusal says why.
  Accepted.
- **A workspace at a filesystem root.** → D2 keeps `..` inside there, via `commonpath`. A test row
  pins it only if the fixture can create such a root. It cannot on this machine, so the row is
  argued and not tested. R2 should check this claim.
- **Row P7's comment and the archived design's P7 row describe the old allow.** → The test comment
  is updated in the same task that flips the row. Archived design documents are not edited.

## Migration Plan

None. The judge runs in each run's MCP server process (`_decide`). It needs no schema change, no Hub
restart and no UI bundle. A run picks up the change the next time its MCP server starts. Rollback
is a revert of one commit.

## Open Questions

1. **File D5 and D6 as findings now?** R1 recommends yes: two findings, sized **B**, since each is an
   escape but needs a spelling an agent is less likely to produce by accident than `..`. They were
   not filed in R1, so that the operator decides the numbering and severity.
2. **Should R2 measure on Linux?** Every real-shell row here is Windows (Git Bash, PowerShell 5.1).
   The POSIX branch of `_SEPARATORS` changes nothing for `..` or `~`, but CI runs Linux, so the new
   test rows will run there, which is where they must pass.

## Round log

- **R1, 2026-09-21** (interactive, Opus 5). Explored `_judge_word`, `_words`, `_where`,
  `_judge_path` and `_expands`, plus the `agent-run-sandboxing` shell requirement (`spec.md:595-708`)
  and archived P7. Measured 19 commands through `_decide`, and 8 real landings across two shells.
  Proposed routing exactly two spellings (D1-D4). Recorded two related holes as non-goals with
  their reasons (D5, D6).
