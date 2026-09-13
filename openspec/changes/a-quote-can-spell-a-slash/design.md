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

**What it decodes.** Exactly what bash decodes (bash manual, "ANSI-C Quoting") — and *exactly*
matters, because faithfulness to bash is the whole safety argument (R2 found two places where a
"close enough" decoder is wrong; see "What round 2 changed"):

- the simple escapes `\a \b \e \E \f \n \r \t \v \\ \' \" \?`;
- `\NNN` octal (1–3 digits, value taken mod 256 — bash `$'\457'` is `/`, measured), `\xHH` hex
  (1–2), `\uHHHH` (1–4), `\UHHHHHHHH` (1–8);
- `\cX` a control character (`\c@` is a NUL — measured);
- an **unrecognized** escape keeps its backslash (`\/` decodes to backslash-slash, `\q` to
  backslash-q — measured, and bash rc=1 on `\/` because the resulting name has no such directory);
- a **digitless** `\x`, `\u` or `\U` (a `\x` with no hex digit following, etc.) **keeps its
  backslash** — bash `$'\x'` is the two characters backslash-x, not `x` (measured,
  `testbed/scratch/r2f332/decode_b.sh`: `digitless x -> \\x`). This is security-relevant on
  Windows and R1 had it wrong — see R2 finding 1;
- a codepoint **above U+10FFFF** (`\U110000`, `\Uffffffff`) is not a character Python `chr()` can
  build; bash emits high bytes for it, none of which is a separator. The decoder produces **no
  character** for it and **never raises** — see R2 finding 2;
- a non-backslash character is kept as itself (a literal `/` inside `$'…'` stays a `/`, a `$`
  becomes the sentinel).

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
from the rules, and none is fabricated that bash would not produce. A `\c` control and the simple
escapes cannot produce a separator, so their exact rendering does not affect the decision.

**But the digitless `\x`/`\u`/`\U` case is not free, and R1 got it wrong (R2 finding 1).** bash
keeps the backslash: `$'..\x'` is `..\x` — and on Windows `\` *is* a separator, so bash (Git Bash)
writes that outside the workspace. A decoder that drops the backslash (as R1's prototype does)
produces `..x`, no separator, and **allows an escape on Windows that is refused today**. The
backslash's rendering *is* security-relevant on Windows; the implementation MUST keep it, exactly
as bash does. See "What round 2 changed" for the measurement.

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
| N2 digitless `\x` | Bash | `echo hi > $'..\x'` (no hex digit) | POSIX: inside (name `..\x`); Win: **outside** (`\`=sep) | POSIX allow / Win deny (unchecked) | — | POSIX allow; **Win deny outside**. R1's prototype wrongly **allows** on Win — R2 finding 1 |
| N3 overrange `\U` | Bash | `echo hi > $'\Uffffffffx'` | inside (file `x`, high bytes) | deny, unchecked | deny, unchecked | **allow** (inside). R1's prototype **raises** — R2 finding 2 |
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
- **N2 (digitless `\x`, R2):** Windows stays **deny**, reason improving from *cannot be checked* to
  *outside* — but this only holds if the decoder keeps the backslash; R1's prototype would flip it
  to allow. POSIX allow, unchanged.
- **N3 (overrange `\U`, R2):** Windows goes from deny to **allow** (over-refusal corrected, bash
  writes a file named `x` inside) — but only if the decoder guards `chr()`; R1's prototype raises.
  POSIX allow, unchanged.
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
A decoded NUL (`\x00`, `\0`, `\c@`) is kept as `\x00`; on POSIX `os.path.realpath` raises
`ValueError` on an embedded NUL, which `_where` already catches and turns into *could not be
resolved* (the existing §2.5 totality behavior). A lone surrogate (`\ud800`) is a valid Python
`chr()` value and `_where` handles it without raising (measured, `os.sep=='\\'`). No new catch
after the lexer is needed **for those**.

**But the decoder itself must guard `chr()` (R2 finding 2).** `\uHHHH` and `\UHHHHHHHH` accept a
value the shell allows but Python `chr()` rejects: any codepoint above U+10FFFF (`\U110000`,
`\U7fffffff`, `\Uffffffff` — all valid 8-hex escapes) makes `chr()` raise `ValueError` or
`OverflowError`. R1's prototype calls `chr(int(hex, 16))` unguarded, so `$'\U110000'` **raises
inside the decoder**, propagating out through `_lex` → `_read_command` → `_decide`, which has no
catch — breaking totality. Measured on both platforms (`testbed/scratch/r2f332/fix_probe.py`, R1
decoder rows). The fix is in the decoder: a value above `0x10FFFF` produces no character (bash
emits high bytes for it, none of which is a `/` or `\`, so omitting them changes no verdict) and
never raises. The measurement confirms the guarded decoder answers `$'\Uffffffffx'` as *allow,
inside* — the file bash actually writes is named `x`, inside the workspace, so this is also an
over-refusal corrected (today it denies as *cannot be checked*).

## What round 2 changed

R2 re-derived the decode set against bash 5.2.21 directly (WSL Ubuntu) and re-ran R1's prototype
decoder on **both** Windows (`py -3.11`) and POSIX (WSL). Scratch is in `testbed/scratch/r2f332/`
(`decode_a.sh`, `decode_b.sh`, `decode_c.sh`, `guard.sh` = bash truth; `win_probe.py`,
`fix_probe.py` = R1 decoder vs a fixed decoder through `_decide`). Two defects found, both
measured and both fixed here; several checks found nothing.

**Finding 1 — R1's decoder opens a Windows escape that is refused today (security).** bash keeps
the backslash on a *digitless* `\x`/`\u`/`\U`: `$'..\x'` decodes to `..\x`, `$'..\xg'` to `..\xg`
(measured, `decode_b.sh`: `digitless x -> \\x`). R1's prototype (`prototype.py`, the `if j == i+2:
return c` branch) **drops the backslash**, producing `..x`. On Windows `\` is a separator, so:
- bash (Git Bash) writes `$'..\x'` **outside** the workspace;
- **today** the reader refuses `$'..\x'` on Windows (`$..\x` holds a `$` and a `\`, rule 3, *cannot
  be checked*) — measured;
- with R1's decoder the word becomes `..x`, no separator, and is **allowed** — measured
  (`fix_probe.py`, `os.sep='\\'`, R1 decoder: `digitless-x … allow=True`).

So R1's change would **regress Windows from deny to allow** for `$'..\x'`, `$'..\xg'`, `$'..\u'` —
a new escape it introduces. (An *unrecognized* escape like `\q` keeps its backslash even in R1's
decoder, so `$'..\q'` is correctly refused; only the digitless-`xuU` branch is wrong.) Design D1's
claim that a digitless escape's rendering "does not affect the decision" was the wrong argument —
true on POSIX, false on Windows. **Fix:** the decoder keeps the backslash on a digitless
`\x`/`\u`/`\U`, matching bash; then `fix_probe.py`'s fixed decoder refuses all three on Windows
(*outside*) and allows them on POSIX (a filename containing a backslash, written inside — correct).
Added as table rows **N2** and tasks §1/§4.

**Finding 2 — R1's decoder is not total on overrange codepoints (totality).** `\uHHHH`/`\UHHHHHHHH`
accept a value bash allows but Python `chr()` rejects. `$'\U110000'`, `$'\U7fffffff'`,
`$'\Uffffffff'` (all valid 8-hex escapes; bash emits high UTF-8 bytes, measured `decode_c.sh`)
make R1's unguarded `chr(int(hex,16))` raise `ValueError`/`OverflowError`. Measured on **both**
platforms (`fix_probe.py`, R1 decoder: `U-overflow … RAISED OverflowError`, `U-over2 … RAISED
ValueError`). That propagates out of `_decide`, which promises *pure and total* — a crash instead
of a decision. **Fix:** the decoder produces no character for a value above `0x10FFFF` (none of
bash's high bytes is a separator, so the verdict is unchanged) and never raises; the fixed decoder
answers `$'\Uffffffffx'` as *allow, inside* on both platforms (bash writes a file named `x` inside
— today's *cannot be checked* deny was an over-refusal, now corrected). Added as table row **N3**
and tasks §2.2/§4.

**Checks that found nothing (R1 was right):**
- **Quote-state guard.** `$'…'` inside `"…"` is literal in bash (`guard.sh`: `"x$'\x2f'y"` writes
  a file named `x$'\x2f'y` *inside*, `%q` = `x\$\'\\x2f\'y`), and R1's `quote is None` guard skips
  it. Inside `'…'` it is trivially literal. Correct.
- **`_LITERAL_DOLLAR` on a produced `$`.** `$'\x24HUB_URL\x2f..\x2f..\x2fx'` is refused *cannot be
  checked*, never treated as a reference (`fix_probe.py` / `win_probe.py`, row D1/A15: `allow=False`,
  reason has no *outside*). Correct.
- **Windows I1 / N1.** `cat $'sub\x2fhello.py'` (I1) → allow (inside) after, unchanged by the fixes.
  `$'..\x5cx'` (N1) → deny (outside) on Windows, allow on POSIX. Correct.
- **`$"…"` locale (L1).** Writes *inside* on POSIX (`guard.sh`, both with no catalog and with
  `TEXTDOMAIN`/`TEXTDOMAINDIR` set), is not decoded, stays allowed on POSIX / denied on Windows.
  Correct. (A planted `.mo` catalog under an agent-controlled `TEXTDOMAINDIR` could in principle
  translate a `$"…"` msgid to a traversal, but that needs a prior filesystem write of the catalog,
  itself checked; out of scope, no finding.)
- **Substitutions and nesting.** `$'…'` inside `$(…)` is re-lexed by `_read_command`'s recursion
  and decoded (`fix_probe.py` `nested-cmdsub` → deny *outside*, both platforms); `guard.sh` confirms
  bash writes it outside. A `$(…)` *inside* `$'…'` is literal (ANSI-C does not expand), and the
  decoder treats `$`/`(` as literal chars (the `$` → sentinel). Correct.
- **Branch placement in `_lex`.** The `quote is None` guard plus placement after the `quote=="'"`
  block and before the generic `char in "'\""` open means the opening `'` is not consumed twice and
  the branch never fires inside a quote. Confirmed by walking the state machine and by every form
  lexing to bash's word.
- **Octal edge cases.** `\457` wraps mod 256 to `/` (bash agrees; R1's `& 0xFF` matches); `\0057`
  is `chr(5)`+`7` (3-digit max, *not* a slash) — R1's 3-digit cap matches bash.
- **Spec delta integrity.** All 10 shipped scenarios and all 10 shipped prose paragraphs of the
  MODIFIED requirement survive byte-for-byte; exactly one paragraph and one scenario are added; the
  requirement's first physical line carries SHALL. `openspec validate --strict` passes.

## What R3 should attack

1. **The two R2 fixes, adversarially.** Re-run `fix_probe.py` on both platforms and confirm the
   *fixed* decoder (keep backslash on digitless `\x`/`\u`/`\U`; no `chr()` above `0x10FFFF`) refuses
   `$'..\x'`/`$'..\xg'`/`$'..\u'` on Windows, allows them on POSIX, and never raises on
   `$'\U110000'`/`$'\Uffffffff'`. Then ask: is there a *third* faithfulness gap? A `\u` producing a
   surrogate that some later `os.path` call on Windows rejects with something `_where` does not
   catch; a decoded value that `os.path.realpath` treats specially. R2 measured `_where` total on a
   lone surrogate and an embedded NUL — re-derive that it is total for *every* char the decoder can
   emit, not only those two.
2. **The digitless case is now the crux — is "keep the backslash" complete?** bash also has
   `\c` with no following char (`$'\c'`), a trailing `\` before the close quote, and `\x`/`\u`/`\U`
   at the very end of the string. Re-measure each against bash and confirm the decoder keeps the
   backslash and stays total for all of them, and that none produces a separator the rules miss.
3. **N2/N3 rows must be killed by a named test, and the mutations must bite.** Confirm tasks §1
   pins N2 (Windows deny) and N3 (allow, no raise) and §4's mutations (revert to drop-backslash;
   revert to unguarded `chr()`) each fail a *named* row. A mutation that leaves the table green is
   a hole.
4. **Whether the impl faithfully carries the fixes.** The night window is held to D2's table, not
   the prototype — but the prototype is the reference an implementer will copy. R3 should verify the
   *tasks* spell out both fixes explicitly enough that copying the prototype verbatim would fail a
   pinned row (it must, since the prototype has both defects).
5. **Drive it.** A Windows drive cannot show the POSIX allow→deny flip, but it *can* now show N2
   (`$'..\x'` refused on Windows) and N3 (`$'\Uffffffffx'` allowed, not a crash) — both are Windows
   answers this change alters. Confirm §5.2's drive exercises N2 and N3, not only G1 and I1.
