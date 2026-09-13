# Proposal — a quote can spell a slash

## Why

Under "Workspace only", the posture every ordinary Claude run gets by default
(`DEFAULT_CLAUDE_PERMISSION_MODE`, `hub/hub/runner_commands.py:66`), the Hub's approver
(`_decide`, `hub/hub/mcp_server.py`) reads a shell command's text as the tool's shell will read it,
then judges each word (the reader shipped by `a-url-is-not-a-path`, 2026-09-13). It closed F300,
F312, F321 and F323. It left one escape open, filed as **F332 (A)** by the night window while it was
being built, and named as a residual in that change's design (D11a, *"Found, not fixed"*).

**The escape: bash's ANSI-C quoting spells out a separator the reader never sees.** In bash,
`$'…'` is a quote form that *decodes* backslash escapes: `$'..\x2fstray.txt'` is the word
`../stray.txt`, and the command text contains no `/`. The reader treats `$'…'` as a literal `$`
followed by an ordinary single-quoted string, so on POSIX it sees the word `$..\x2fstray.txt`,
finds no separator in it, and allows it (rule 4). Bash decodes the `\x2f` to `/` and writes the
file in the workspace's parent.

Measured 2026-09-13 by R1:

- **Bash writes outside.** `wsl -d Ubuntu -- bash testbed/scratch/night0912/ansic.sh`:
  `echo hi > $'..\x2fansic_stray.txt'` run from `/tmp/ansic/ws` exited 0 and wrote
  `/tmp/ansic/ansic_stray.txt`, in the workspace's parent. Bash 5.2.21.
- **The reader allows it.** `_decide("Bash", {"command": "echo hi > $'..\\x2fstray.txt'"})` returns
  `allow` under WSL Ubuntu (Python 3.12.3, `testbed/scratch/r1f332/reader_forms.py`).

This breaches the shipped scenario *"Traversal and links cannot escape"*
(`agent-run-sandboxing`, *"A posture exists in which the workspace boundary is enforced per tool
call"*), on the Docker deployment's platform (`hub/Dockerfile` is Linux, and so is CI).

### The class, measured

R1 mapped the class by running every candidate form in bash (`testbed/scratch/r1f332/forms.sh`,
which writes to a fresh workspace and reports where the file landed) and through today's `_decide`
on both platforms (`reader_forms.py`). One mechanism accounts for every escape: bash `$'…'`
decodes a numeric escape (`\xHH`, `\NNN` octal, `\uHHHH`, `\UHHHHHHHH`) — or a literal separator
carried inside the quotes — into a separator the reader treats as literal text.

| form | command (POSIX) | bash | today (POSIX) | today (Win) |
|---|---|---|---|---|
| hex | `echo hi > $'..\x2fx'` | writes outside | **allow** | deny, cannot be checked |
| octal | `echo hi > $'..\057x'` | writes outside | **allow** | deny, cannot be checked |
| `\u` (4-hex, spelling `/`) | `echo hi > $'..[/]x'` | writes outside | **allow** | deny, cannot be checked |
| `\U` | `echo hi > $'..\U0000002fx'` | writes outside | **allow** | deny, cannot be checked |
| full hex | `echo hi > $'\x2e\x2e\x2fx'` | writes outside | **allow** | deny, cannot be checked |
| split quote | `echo hi > '.'$'.\x2f'x` | writes outside | **allow** | deny |
| dq-adjacent | `echo hi > $'..\x2f'"x"` | writes outside | **allow** | deny |
| tee arg | `echo hi \| tee $'..\x2fx'` | writes outside | **allow** | deny |
| cp target | `cp notes.md $'..\x2fx'` | writes outside | **allow** | deny |
| literal `$` | `echo hi > $'\x24HUB_URL\x2f..\x2f..\x2fx'` | writes outside | **allow** | deny, cannot be checked |

Every one is allowed on POSIX today. On Windows every one is refused today — for a false reason
(*cannot be checked*), because the literal `\` the reader keeps is a separator there and, with the
`$`, trips rule 3. So the escape is **POSIX-only**, exactly as F331 was.

### What does not escape, also measured

- **`$"…"` (locale translation) is not ANSI-C and does not decode.** `echo hi > $"..\x2fx"` writes
  a file named `..\x2fx` *inside* the workspace (a literal backslash on POSIX), and the reader
  allows it — correctly, it is inside. This change must not decode `$"…"`.
- **Brace expansion does not hide a separator.** To produce a `/` a brace must contain a literal
  `/` (`..{/,}x`), which the reader sees; and a brace that expands to a traversal yields more than
  one word, so `echo hi > ..{/,}x` is a two-target redirection that bash rejects (rc=1). Residual,
  unchanged.
- **Tilde and globbing.** A leading `~` with a separator is already refused (rule 3). Bash 5.2's
  `globskipdots` keeps `*` from matching `.`/`..`; glob characters remain the pre-existing X5
  residual (`a-url-is-not-a-path` D8), unchanged.

## What Changes

- `_lex` (`hub/hub/mcp_server.py`) decodes bash ANSI-C `$'…'` quoting **in the bash dialect only**,
  when the `$'` is not already inside another quote. The `$` is consumed; each escape is decoded as
  bash decodes it; the decoded characters join the current word like any other lexed text. A
  literal `$` the decoding produces becomes the `_LITERAL_DOLLAR` sentinel, exactly as a `$` inside
  ordinary single quotes already does — so an ANSI-C-spelled `$HUB_URL` is not read as a reference
  (the ANSI-C analog of D11a item 1, `$'\x24HUB_URL…'`).
- Nothing else changes. The six rules, the own-Hub test, the refusal wordings, and the reason bound
  are untouched. After the fix, `$'..\x2fstray.txt'` is the word `../stray.txt`, which rule 5
  already refuses as `'../stray.txt' is outside your workspace`; the literal-`$` form falls to rule
  3 as *cannot be checked*. **This change adds no new reason string.**
- The comment above the reader gains one sentence: a quote form may *decode* escapes into
  characters, not only remove them, so the word judged is what the shell produces.

**What moves, measured on R1's prototype** (`testbed/scratch/r1f332/prototype.py`, which patches
`_lex` and re-judges every form):

- **On POSIX, ten forms go from allowed to refused** — the ten in the table above, each now refused
  as the decoded path is (outside, or cannot be checked for the literal-`$` form).
- **On Windows, the escape forms stay refused**, their reason improving from *cannot be checked* to
  *outside your workspace* (the truer reason).
- **One Windows over-refusal is corrected.** `cat $'sub\x2fhello.py'`, an ANSI-C spelling of a path
  *inside* the workspace, is refused today on Windows (the literal `\` trips rule 3) and allowed
  after (it decodes to `sub/hello.py`, which is inside). It writes inside in Git Bash, so allowing
  it is correct.
- **`$"…"` and legitimate work are unchanged**: `python sub/hello.py`,
  `curl "$HUB_URL/api/v1/agent-actions/tasks"`, and `echo hi > $"..\x2fx"` keep their answers.

## Scope

- **Closes F332** and the whole ANSI-C class R1 measured escaping today (the table above), including
  its literal-`$` member.
- **Bash dialect only.** PowerShell has no `$'…'`; its reading is untouched. An unknown tool is
  still read both ways and refused if either reading refuses.

## Non-goals

- **PowerShell runtime path builders** (`Set-Content (Join-Path .. x)`, `Resolve-Path`,
  `[IO.Path]::Combine`) — a path built at run time never appears as a word. Recorded as a residual
  in `a-url-is-not-a-path` D9, unchanged.
- **`cd ..` then write, `git -C ..`** — the approver does not track the shell's working directory
  (`a-url-is-not-a-path` D9), unchanged.
- **The single-quoted literal `$` over-refusal** (`a-url-is-not-a-path` D10 item 7) — rule 3 refuses
  a word with a literal `$` and a separator. This change keeps that behavior for ANSI-C-produced
  literal `$` too (the reason is true of the rule, not the word). Unchanged.
- **Glob characters** (X5), **`$"…"` locale strings that write inside** — unchanged.
- **Codex.** "Workspace only" on Codex decides by working directory alone
  (`codex_appserver.py:280-283`); it never reads a shell command's text. Recorded as F322,
  unverified because Codex is undrivable. Unchanged.

## Cost

One localized addition to `_lex` (a small ANSI-C decoder plus one branch), plus its table rows and
one delta scenario. No migration, no API or schema change, no UI change, no new reason string.
`hub/hub/mcp_server.py` keeps its stdlib+fastmcp-only constraint (the decoder is stdlib code), and
`approve_tool_call` is untouched and keeps **no return annotation**.

## Capabilities

### Modified Capabilities

- `agent-run-sandboxing`: the requirement *"A path in a shell command is judged by where it
  resolves"* is MODIFIED — one sentence of prose and one ADDED scenario, that a quote form which
  decodes an escape into a separator is judged by what it decodes to. Every shipped line is kept.

## Impact

- **Code:** `hub/hub/mcp_server.py`, `_lex` only (a decoder helper and one branch). Standard library
  plus fastmcp only.
- **Tests:** `hub/tests/test_permission_approver.py` gains the table above as pinned `_decide`
  cases, written **before** the reader changes (tasks §1) and their `xfail` markers removed as the
  decode lands (tasks §2), plus a mutation per rule and a wire-shape case.
- **Docs:** none required; the reader comment is code, and the posture page already describes the
  reader in general terms.
- **Findings:** closes **F332** when built and driven (POSIX proven on CI's Linux job and WSL, per
  the evidence route below). Leaves F299, F301, F322 open, and names each.
