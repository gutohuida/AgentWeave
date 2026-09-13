# Design — a quote can spell a slash

Everything below was measured on 2026-09-13 against `autonomous/2026-09-12-daily`, with the reader
shipped by `a-url-is-not-a-path` (`hub/hub/mcp_server.py` `_decide` and its lexer). "Prototype"
means `testbed/scratch/r1f332/prototype.py`: it monkeypatches `hub.mcp_server._lex` with the D1
decode and re-judges every form beside today's answer. **It is a design aid, not the
implementation**; the implementation is held to D2's table. "bash" is bash 5.2.21 under WSL Ubuntu
(`testbed/scratch/r1f332/forms.sh`, `decode.sh`); "reader" answers are from
`testbed/scratch/r1f332/reader_forms.py` (WSL Ubuntu, Python 3.12.3; Windows, `py -3.11`).

## D0 — Scope: close F332's ANSI-C class, nothing wider

F332 is one mechanism: bash's ANSI-C `$'…'` quoting decodes an escape into a path separator that
the reader treats as literal text. R1 measured the whole class (D2) and found no other shell form
that writes outside today and is allowed: `$"…"` locale strings write *inside* (a literal
backslash on POSIX), brace expansion cannot both produce a separator and hide it, tilde and glob
are already accounted for (D3). So this change decodes `$'…'` and stops there.

**Rejected: fold this into a broader "decode everything the shell decodes" pass.** There is nothing
else to decode — `$"…"` is translation, not escape-decoding, and every other quote form the reader
handles removes characters rather than transforming them. A wider remit would be scope with no
measured escape behind it.

## D1 — The lexer decodes bash ANSI-C `$'…'`, then the existing rules judge the decoded word

The reader's second stage (the six rules) is already correct: it judges the *word the shell
produces*. The defect is entirely in the first stage — the lexer does not produce the word bash
produces, because it does not know `$'…'` is a decoding quote. So the fix is one addition to `_lex`
and nothing after it.

**When it fires.** In the **bash** dialect only (PowerShell has no `$'…'`), and only when the `$'`
is encountered with **no quote open** — inside `"…"`, `$'` is a literal `$` then a literal `'`
(measured: bash prints `x$'y'z` unchanged, and `a$'\x2f'b` unchanged). The lexer consumes the `$`
and the opening `'`, decodes until the closing `'` (or end of text, keeping the lexer total), and
consumes the closing `'`.

**What it decodes.** Exactly what bash decodes (bash manual, "ANSI-C Quoting"):

- the simple escapes `\a \b \e \E \f \n \r \t \v \\ \' \" \?`;
- `\NNN` octal (1–3 digits), `\xHH` hex (1–2), `\uHHHH` (1–4), `\UHHHHHHHH` (1–8);
- `\cX` a control character;
- an **unrecognized** escape keeps its backslash (`\/` decodes to backslash-slash — measured, and
  bash rc=1 on it because the resulting name has no such directory);
- a non-backslash character is kept as itself (a literal `/` inside `$'…'` stays a `/`).

**The produced characters join the current word** like any other lexed text, so concatenation is
handled for free: `'.'$'.\x2f'x` and `$'..\x2f'"x"` both assemble their traversal across segments
(D2 rows G7, G8), and an ANSI-C word in argument position (`tee`, `cp`) is judged like any other
argument (G9, G10).

**A produced literal `$` becomes the `_LITERAL_DOLLAR` sentinel**, exactly as a `$` inside ordinary
single quotes already does. ANSI-C output is not re-expanded by the shell, so a `$` in it is
literal. Without the sentinel, `$'\x24HUB_URL\x2f..\x2f..\x2fx'` would decode to
`$HUB_URL/../../x`, be read as a reference (rule 2), have the approver's real Hub URL substituted,
and pass — while bash writes to a directory literally named `$HUB_URL` and climbs out of it (D2 row
D1). This is the ANSI-C analog of `a-url-is-not-a-path` D11a item 1 (E20–E22), and it reuses the
same sentinel and the same `_quote` un-rendering.

**Why the safety argument is complete.** After the decode, the word contains a separator (`/`
always; `\` where `os.sep == "\\"`) **if and only if** the `$'…'` source contained a literal
separator (passed through unchanged) or a numeric escape decoding to one (`\x2f`, `\057`, a 4- or
8-hex unicode escape for `/`; and on Windows the `\`-producing `\x5c`, `\134`, etc.). Every numeric
route is decoded, and every literal separator is preserved. So no separator bash produces is hidden
from the rules, and none is fabricated that bash would not produce. A digitless `\x` or `\u`, a
`\c` control, and the simple escapes cannot produce a separator, so their exact rendering does not
affect the decision — the implementation should still match bash for faithfulness (e.g. keep the
backslash on a digitless `\x`), but nothing security-relevant rests on it.

**Rejected: decode only `\x2f`/`\057` (the separators seen so far).** It would miss `\uHHHH`,
`\UHHHHHHHH`, and the octal/hex spelling of `\` on Windows, and would need re-visiting the first
time an agent spells the slash a fourth way. A faithful decoder closes the class in one pass and is
no larger.

**Rejected: refuse any word that contains `$'`.** Simpler, but it would refuse legitimate ANSI-C
strings that write *inside* (`cat $'sub\x2fhello.py'`, D2 row I1, decodes to `sub/hello.py`), and
it refuses on a reason (*a shell expansion*) that is false — `$'…'` is not an expansion, it is a
literal. Judging the decoded word gives the true answer for both the escape and the inside path.

## D2 — The decided table

Measured by `forms.sh` (bash) and `reader_forms.py` (today) and `prototype.py` (after).
`AW_WORKSPACE_DIR` is a directory named `work` containing `sub/hello.py` and `notes.md`; `HUB_URL`
is `http://127.0.0.1:8016`. `[/]` marks the 4-hex unicode escape that spells `/`.

The **today** answers differ by platform, exactly as F331/F331's rows did: on POSIX the reader
keeps the literal `\` (not a separator there) and finds no separator, so it **allows**; on Windows
the literal `\` *is* a separator and, with the `$`, trips rule 3, so it **refuses (cannot be
checked)**. The **after** answer is the same on both platforms except where noted.

| row | tool | command | bash | today (POSIX) | today (Win) | after |
|---|---|---|---|---|---|---|
| G1 hex | Bash | `echo hi > $'..\x2fstray.txt'` | outside | **allow** | deny, unchecked | **deny, `'../stray.txt'` outside** |
| G2 octal | Bash | `echo hi > $'..\057x'` | outside | **allow** | deny, unchecked | deny, `'../x'` outside |
| G3 `\u`[/] | Bash | `echo hi > $'..[/]x'` | outside | **allow** | deny, unchecked | deny, `'../x'` outside |
| G4 `\U` | Bash | `echo hi > $'..\U0000002fx'` | outside | **allow** | deny, unchecked | deny, `'../x'` outside |
| G5 full hex | Bash | `echo hi > $'\x2e\x2e\x2fx'` | outside | **allow** | deny, unchecked | deny, `'../x'` outside |
| G6 adjacency | Bash | `echo hi > $'..'/x` | outside | **deny, unchecked** | deny | deny, `'../x'` outside |
| G7 split quote | Bash | `echo hi > '.'$'.\x2f'x` | outside | **allow** | deny | deny, outside |
| G8 dq-adjacent | Bash | `echo hi > $'..\x2f'"x"` | outside | **allow** | deny | deny, `'../x'` outside |
| G9 tee arg | Bash | `echo hi \| tee $'..\x2fx'` | outside | **allow** | deny | deny, `'../x'` outside |
| G10 cp target | Bash | `cp notes.md $'..\x2fx'` | outside | **allow** | deny | deny, `'../x'` outside |
| D1 literal `$` | Bash | `echo hi > $'\x24HUB_URL\x2f..\x2f..\x2fx'` | outside (dir `$HUB_URL`) | **allow** | deny, unchecked | **deny, cannot be checked** |
| I1 inside ansic | Bash | `cat $'sub\x2fhello.py'` | inside | allow | **deny, unchecked** | **allow** (inside) |
| L1 `$"` locale | Bash | `echo hi > $"..\x2fx"` | inside (literal) | allow | deny, unchecked | **unchanged**: allow (POSIX), deny (Win) |
| N1 bslash ansic | Bash | `echo hi > $'..\x5cx'` | POSIX: inside (name w/ `\`); Win: outside | allow | deny | POSIX allow; **Win deny outside** |
| OK1 inside | Bash | `python sub/hello.py` | inside | allow | allow | allow |
| OK2 own-hub | Bash | `curl -s "$HUB_URL/api/v1/agent-actions/tasks"` | (request) | allow | allow | allow |

**What moves.**
- **POSIX: G1–G5, G7–G10, D1 go from allow to deny** (ten forms), each refused as the decoded path
  is. G6 is already refused today (a literal `/` outside the quotes trips rule 3), reason improves.
- **Windows: G1–G10 and D1 stay refused**, reason improving from *cannot be checked* to *outside*
  (or staying *cannot be checked* for D1). **I1 goes from deny to allow** — an over-refusal
  corrected, since it decodes to a path inside the workspace. **N1 stays deny** on Windows (the
  decoded `\` is a separator, so `..\x` is a real traversal there) and is allowed on POSIX (a
  filename containing a backslash, written inside).
- **L1, OK1, OK2 unchanged.**

## D3 — What does not escape, and stays out of scope

- **`$"…"` (L1).** bash: `$"..\x2fx"` writes a file named `..\x2fx` inside the workspace (measured).
  It is locale translation, not escape decoding — no `\x2f` is decoded. The reader must not touch
  `$"…"`; leaving the double-quote path unchanged does exactly that.
- **Brace expansion.** A brace that yields a separator must contain a literal `/` (`..{/,}x`), which
  the reader sees, and a brace that expands to a traversal produces more than one word — so
  `echo hi > ..{/,}x` is a two-target redirection bash rejects (rc=1, measured). A brace form built
  on `$'…'` (`..$'\x2f'{a,b}`) is covered by D1's decode. Residual, unchanged.
- **Tilde / glob.** A leading `~` with a separator is rule 3 already. `globskipdots` (on by default
  in bash 5.2) stops `*` matching `.`/`..`; glob characters stay the X5 residual
  (`a-url-is-not-a-path` D8). Unchanged.

## D4 — POSIX gets its evidence the way F331 did; a Windows drive cannot show the flip

The night window runs on Windows, where every F332 form is **already refused** today (for a false
reason). So a Windows live drive can show the *reason* improving and can show the I1 over-refusal
corrected, but it **cannot** witness the allow→deny flip that is the whole finding — that flip is
POSIX-only. The evidence for it, exactly as `a-url-is-not-a-path` did for F331:

- **CI's `hub-test` job on `ubuntu-24.04`.** The table rows that flip are pinned as `xfail(strict)`
  on POSIX against the unmodified tree, and the pin turns from XFAIL to PASS when the decode lands.
  A strict xfail that passes early fails CI, so a decode that fires before its rule exists is
  caught. This is the authoritative POSIX evidence.
- **WSL Ubuntu direct runs.** `forms.sh` (bash writes outside), `reader_forms.py` (today allows),
  and `prototype.py` (after refuses) reproduce the flip locally under Linux, and the test file runs
  under WSL with `testbed/scratch/night0912/posix_stubs.py` as `a-url-is-not-a-path` did.

A Windows drive is still worth doing (tasks §6): it confirms the reason a real operator reads, and
that I1 is not a regression (an inside ANSI-C path really is allowed and really writes inside in
Git Bash).

## D5 — Totality

The decoder must not raise on any input, because `_decide` promises *pure and total*. A malformed
escape (`\x` with no hex digits, `\u` with none, a trailing `\` before the closing quote, an
unterminated `$'…'` running to end of text) is decoded to a best-effort literal and never raises.
A decoded NUL (`\x00`, `\0`) is kept as `\x00`; on POSIX `os.path.realpath` raises `ValueError`
on an embedded NUL, which `_where` already catches and turns into *could not be resolved* (the
existing §2.5 totality behavior). No new catch is needed.

## What R2 should attack

1. **The decode set (D1).** Re-derive, against bash directly, that every numeric route to a
   separator is decoded and every literal separator preserved — the safety argument rests entirely
   on that completeness. Try `\uHHHH` and `\UHHHHHHHH` for `/` and (on Windows) for `\`, and octal
   `\057`/`\134`. Confirm an unrecognized escape keeps its backslash and cannot smuggle a separator.
2. **The quote-state guard.** Confirm `$'…'` inside `"…"` is *not* decoded (bash treats it as
   literal — re-measure `echo "x$'\x2f'y"`), and that inside `'…'` it is literal too. A decode that
   fires inside double quotes would change words the shell does not.
3. **The `_LITERAL_DOLLAR` sentinel on produced `$` (D1, row D1).** Verify `$'\x24HUB_URL…'` is
   refused as *cannot be checked* and never treated as a reference. Check that the refusal renders
   the sentinel back to `$` (via `_quote`).
4. **The Windows non-regression (I1, N1).** Confirm no ANSI-C spelling of an *inside* path becomes
   refused, and that `$'..\x5cx'` is a real traversal on Windows (so refusing it is correct) while
   being an inside filename on POSIX (so allowing it is correct). This is the one place the change
   alters a Windows answer.
5. **`$"…"` (L1).** Re-measure that it writes inside on POSIX and is left allowed there — the fix
   must not decode it.
6. **Interaction with substitutions and nesting.** `$'…'` inside a `$(…)` substitution: confirm the
   decode applies when the substitution's text is re-read as a command (`_read_command` recursion),
   and that a substitution *inside* `$'…'` is not treated as a substitution (ANSI-C does not expand
   `$(…)`).
7. **Placement in `_lex`.** The new branch must sit where `quote is None` is guaranteed and before
   the generic single-quote-open branch, or the `'` is consumed twice. Re-derive the branch order.
