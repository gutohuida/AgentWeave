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
- `\cX` a control character (`\c@` is a NUL — measured) — **but `\c` with no body character after
  it, i.e. immediately before the closing quote, keeps its backslash literal** (bash `$'..\c'` is
  `..\c` — measured, `testbed/scratch/r3f332/`), and the decode MUST NOT consume the closing quote
  as the control target. R2's one-phase decoder did — see R3 finding 2;
- an **unrecognized** escape keeps its backslash (`\/` decodes to backslash-slash, `\q` to
  backslash-q — measured, and bash rc=1 on `\/` because the resulting name has no such directory);
- a **digitless** `\x`, `\u` or `\U` (a `\x` with no hex digit following, etc.) **keeps its
  backslash** — bash `$'\x'` is the two characters backslash-x, not `x` (measured,
  `testbed/scratch/r2f332/decode_b.sh`: `digitless x -> \\x`). This is security-relevant on
  Windows and R1 had it wrong — see R2 finding 1;
- `\uHHHH`/`\UHHHHHHHH` decode to a character **only when the value is ≤ 0xFF**; a value **above
  0xFF keeps the backslash literal** (`$'..\u0100'` stays `..\u0100`). bash's decode of a
  codepoint above 0xFF is *locale-dependent*: a UTF-8 locale emits multibyte UTF-8, but the **C
  (non-UTF-8) locale that Git Bash uses by default for a non-login shell keeps the escape literal,
  backslash and all** (measured, `testbed/scratch/r3f332/unicode_probe.sh`). On Windows that
  backslash is a separator, so decoding it away opens an escape refused today — R1 and R2 both had
  this wrong. See R3 finding 1. This rule also removes the need for a separate `chr()` overflow
  guard: `chr()` is only ever called on a value ≤ 0xFF, so it cannot raise;
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

**The safety invariant (restated after R3).** The only characters that are path separators are `/`
(always) and, where `os.sep == "\\"`, the backslash `\`. An escape can put a separator into the
decoded word two ways: by decoding to the byte `/` (0x2F) or `\` (0x5C), or by **bash keeping the
escape literal, which leaves a backslash in the word.** So the decoder is safe on both platforms
**if and only if** it never emits fewer separators than bash emits under any locale the run's shell
might use. Concretely: an escape may be **decoded to a character** (removing its backslash) only
when that character is fully determined *and locale-independent* — the simple escapes, `\NNN`
octal and `\xHH` hex (byte escapes, always ≤ 0xFF), `\uHHHH`/`\UHHHHHHHH` whose value is ≤ 0xFF, and
`\cX` where `X` is a real body character. In **every other case the backslash is kept literal**:
a digitless `\x`/`\u`/`\U` (R2 finding 1), a `\u`/`\U` above 0xFF (R3 finding 1), a `\c` with no
body character after it (R3 finding 2), an unrecognized escape, and a trailing backslash. bash may
keep any of these literal, and on Windows the kept backslash is a separator, so keeping it is the
only safe rendering. Rounds 1 and 2 reasoned about individual escapes ("this one can't produce a
separator"); R3 found that the correct unit of the argument is the invariant, because bash's
keep-literal set is larger than either round enumerated. See "What round 3 changed".

**Why "decode ≤ 0xFF, keep the rest literal" is exactly right for the numeric escapes.** `\xHH` and
`\NNN` are *byte* escapes: bash emits the single byte HH/NNN mod 256 in every locale (measured:
`\x80` is one byte 0x80 under both C and UTF-8), so `chr(value)` reproduces the separator faithfully
(`\x2f` → `/`, `\x5c` → `\`) and never a spurious one. `\uHHHH`/`\UHHHHHHHH` are *codepoint* escapes
and their rendering above 0xFF is locale-dependent (§D5); at or below 0xFF the only separators are
`/`=0x2F and `\`=0x5C, both ASCII, decoded identically in every locale, so `chr(value)` is faithful
there too. Above 0xFF the value can never *be* a separator byte, but the C-locale literal *contains*
one, so keeping the backslash is both safe and matches C-locale bash.

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
| N2 digitless `\x` | Bash | `echo hi > $'..\x'` (no hex digit) | POSIX: inside (name `..\x`); Win: **outside** (`\`=sep) | POSIX allow / Win deny (unchecked) | Win deny (unchecked) | POSIX allow; **Win deny outside**. R1's prototype wrongly **allows** on Win — R2 finding 1 |
| N3 overrange `\U` | Bash | `echo hi > $'\Uffffffffx'` | POSIX: inside (file `x`); Win: outside (C-locale literal `\Ufff…`) | POSIX allow / Win deny (unchecked) | POSIX allow / Win deny (unchecked) | POSIX allow (inside); **Win deny outside** (reason improves). R1 **raises**, R2 wrongly **allows on Win** — R3 finding 1 corrects both |
| N4 `\u`>0xFF | Bash | `echo hi > $'..\u0100'` (value 0x100) | POSIX: inside; Win: **outside** (C-locale keeps literal `..\u0100`, `\`=sep) | POSIX allow / Win deny (unchecked) | POSIX allow / Win deny (unchecked) | POSIX allow; **Win deny outside**. R1 & R2 both wrongly **allow on Win** — R3 finding 1 |
| N5 `\c` at close | Bash | `echo hi > $'..\c'` (`\c` before `'`) | POSIX: inside (name `..\c`); Win: **outside** (`..\c`, `\`=sep) | POSIX allow / Win deny (unchecked) | POSIX allow / Win deny (unchecked) | POSIX allow; **Win deny outside**. R1 & R2 both wrongly **allow on Win** (consume the closing quote) — R3 finding 2 |
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
- **N3 (overrange `\U`, R2/R3):** Windows stays **deny**, reason improving from *cannot be checked*
  to *outside*. R2's table had this flipping deny→allow; that was **wrong** — in the C locale bash
  keeps `\U110000`…`\U7fffffff` literal (backslash present), a Windows traversal, so allowing it
  would open an escape. Only `\U` ≥ 0x80000000 (`\Uffffffff`) truly produces nothing in bash on
  every locale, so writing a file named `x` inside is bash's answer there; the R3 decoder declines
  to correct that one over-refusal (keeps it deny, not a regression from today's deny) in exchange
  for a single locale-independent rule. POSIX allow, unchanged.
- **N4 (`\u`/`\U` above 0xFF, R3):** Windows stays **deny**, reason improving from *cannot be
  checked* to *outside*. R1 and R2 both decode it to one character and would flip it to **allow** —
  the escape R3 finding 1 caught. POSIX allow, unchanged.
- **N5 (`\c` before the closing quote, R3):** Windows stays **deny**, reason improving from *cannot
  be checked* to *outside*. R1 and R2 both consume the closing quote as `\c`'s control target and
  would flip it to **allow** — R3 finding 2. POSIX allow, unchanged.
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
resolved* (the existing §2.5 totality behavior). No new catch after the lexer is needed.

**Totality now holds structurally, without a `chr()` overflow guard (R3 revises R2 finding 2).**
`chr()` is called **only for values ≤ 0xFF** — the byte escapes (`\xHH` ≤ 0xFF, `\NNN` mod 256) and
`\uHHHH`/`\UHHHHHHHH` values ≤ 0xFF. Every codepoint escape **above 0xFF is kept literal** (§D1, R3
finding 1), so the values R2 guarded against — anything above U+10FFFF (`\U110000`, `\Uffffffff`),
which make `chr()` raise `ValueError`/`OverflowError` — are never passed to `chr()` at all. R2's
separate `if value > 0x10FFFF: return ""` guard is therefore removed; the ≤ 0xFF cap subsumes it and
is also *more correct on Windows*, because R2's guard returned an empty string and so dropped the
backslash that C-locale bash keeps for `\U110000`…`\U7fffffff` (§D1). The one behavioural cost is
that `\U` ≥ 0x80000000 (`\Uffffffff`), which bash renders as nothing in every locale, is judged from
its kept-literal backslash and so **denied on Windows** rather than allowed — an over-refusal, not a
regression (today it denies as *cannot be checked*), and the price of one locale-independent rule.

Note the R3 rule also *narrows* what `chr()` can emit: because values above 0xFF are kept literal, a
lone surrogate (`\ud800`, value 0xD800 > 0xFF) is now kept literal rather than passed to `chr()`, so
the surrogate case R2 had to reason about cannot arise; every `chr()` output is a code point in
U+0000…U+00FF, all of which `_where` resolves without raising (measured, both platforms,
`testbed/scratch/r3f332/three_decoders.py`).

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

## What round 3 changed

R3 re-derived the decode set against **real Git Bash 5.2.37 on Windows** (not only a Python model
of it) and against WSL bash 5.2.21, under several locales, and re-ran R1's and R2's decoders through
the real `_decide` on both platforms. Scratch is in `testbed/scratch/r3f332/`
(`unicode_probe.sh`/`gen_probe.py` = bash truth per locale; `quote_lexing.py` = escaped-quote
lexing; `three_decoders.py` = R1 vs R2 vs R3 decoder through `_decide`). Two more escapes of the
**same class R2 opened** — *bash keeps a literal backslash that the decoder drops, and on Windows a
backslash is a separator* — were found, both Windows-only, both measured, both fixed here. R2 had
patched two leaks of this class (digitless; `chr()` overflow); the class was larger than either
round enumerated, which is why R3 replaced the per-escape arguments with the invariant in D1.

> **Corrected by the pre-approval review (see "Pre-approval review" below).** The claim below that
> Git Bash "uses the C locale by default" and therefore writes `\u0100` **outside** on Windows is
> **false on this machine's Git Bash** (msys2 5.2.37), which forces `LC_CTYPE=C.UTF-8` (even under
> `LC_ALL=C`) and writes `\u0100` as UTF-8 bytes `c4 80` *inside* the workspace. R3's
> keep-the-backslash decoder is still the correct **safe** choice — it never under-counts
> separators under any locale — but on the measured Git Bash its Windows deny of N3/N4 is a
> conservative **over-refusal**, not the closing of a live escape. Read this finding as "a true C
> (non-UTF-8) locale is *possible* (empty `LANG`, as R3's own probe had), and keeping the backslash
> is safe for it", not as "Git Bash does this by default".

**Finding 1 — `\u`/`\U` above 0xFF is locale-dependent, and R1/R2 open a Windows escape (security).**
bash's rendering of a codepoint escape above 0xFF depends on the locale of the shell that runs the
command: a UTF-8 locale emits multibyte UTF-8 (no backslash), but the **C (non-UTF-8) locale keeps
the escape literal, backslash and all** — `$'..\u0100'` stays `..\u0100` (the six-character escape `\u0100`, backslash included, is not decoded), and
`$'..\U00110000'` likewise (measured, `unicode_probe.sh`: `u0100 inh -> \ u 0 1 0 0`; and directly,
`three_decoders.py` on Windows). Git Bash on this machine runs a non-login `bash -c` in the **C
locale** (`LANG` empty; `\u0100` kept literal), while a login `bash -lc` inherits `en_GB.UTF-8` and
decodes it — so which behaviour the agent's Bash tool gets is not guaranteed. On Windows `\` is a
separator, so:
- C-locale bash (Git Bash) writes `$'..\u0100'`, `$'..\U00000100'`, …, `$'..\U00110000x'`
  **outside** the workspace (literal `..\…` traversal);
- **today** the reader refuses them on Windows (`$..\u0100` has `$`+`\`, rule 3, *cannot be
  checked*) — measured;
- **R1's decoder** decodes `\u0100` to one character (U+0100, no backslash) → `..`+U+0100, no separator → **allow**
  (measured, `three_decoders.py`, R1 column: `u0100 … allow=True [inside]`); and it **raises** on
  `\U00110000`/`\Uffffffff` (`chr()` overflow), breaking totality;
- **R2's decoder** decodes ≤ 0x10FFFF via `chr` (same allow for `\u0100`) and returns `""` for
  > 0x10FFFF, so `$'..\U00110000x'` becomes `..x`, no separator → **allow** (measured, R2 column:
  `U00110000 … allow=True [inside]`). R2's own argument for that row — *"bash emits high bytes, none
  of which is a separator"* — is true of the bytes but **false about the literal backslash** bash
  keeps in the C locale for 0x110000…0x7FFFFFFF. An argument wrong while its Linux/UTF-8 outcome is
  right — exactly the failure the round discipline exists to catch.

So R1 and R2 would **regress Windows from deny to allow** for every `\u`/`\U` above 0xFF (rows N3,
N4). **Fix:** decode `\u`/`\U` to a character only for values ≤ 0xFF; keep the backslash literal
above 0xFF (§D1). The R3 decoder then refuses N3/N4 on Windows (*outside*) and allows them on POSIX
(a filename with a backslash, written inside — correct), and never calls `chr()` above 0xFF, so
totality holds without a guard (§D5). Measured (`three_decoders.py`, R3 column, both platforms).
**Linux is sound with either decoder** — `\` is not a separator there and a codepoint above 0xFF
never decodes to `/` — so this finding does not touch F332's POSIX escape; it is a Windows-only
regression the change would otherwise *introduce*.

**Finding 2 — `\c` immediately before the closing quote opens a Windows escape (security).** bash
keeps `\c` literal when no body character follows it: `$'..\c'` is `..\c` (measured,
`testbed/scratch/r3f332`, both Git Bash and WSL). R1's and R2's one-phase decoders read the char
*after* `\c` as the control target without checking whether it is the closing quote — so they
consume the closing `'`, decode `\c'` to a control character, over-run the string, and produce a
word with no backslash. On Windows:
- bash writes `$'..\c'` **outside** (`..\c` traversal);
- **today** the reader refuses it (`$..\c`, rule 3, *cannot be checked*);
- **R1/R2** produce `..g` (control of `'`), no separator → **allow** (measured through `_decide`:
  `R2-lex c-at-close … allow=True inside`).
**Fix:** `\c` with no body character before the closing quote keeps its backslash literal, and the
decode never consumes the closing quote as a `\c` target (§D1, row N5). The R3 decoder then refuses
`$'..\c'` on Windows (*outside*) and allows it on POSIX (name `..\c`, inside). `\c` with a real
target (`\c/` → 0x0F, the `/` consumed) is unaffected and produces no separator in bash or the
decoder — no divergence. Linux-sound, as finding 1.

**Checks that found nothing (R1/R2 were right, or the case is benign):**
- **Escaped-quote lexing.** `\'` inside `$'…'` is an escaped literal quote that does **not** close
  the string, and `\\` is a literal backslash; the one-phase loop consumes each `\X` pair
  atomically, so both match bash (`quote_lexing.py`: `$'a\'b'` → `a'b`, `$'x\'\'y'` → `x''y`,
  matching bash's `61 27 62` / `78 27 27 79`). The only `\`-escape that over-runs the quote is `\c`
  (finding 2); every other escape is safe.
- **`\x` and octal are locale-independent.** They are *byte* escapes: `\x80` is one byte 0x80 under
  both C and UTF-8 (measured), so `chr(value)` is faithful and can produce a separator only for
  `\x2f`/`\x5c`/`\057`/`\134` — the correct set. `\457` wraps mod 256 to `/`; the 3-digit cap holds.
- **`\cX` for a symbol X is cosmetically wrong but separator-safe.** The prototype maps `\c/` to
  `chr(ord('/') ^ 0x40)` = `o`, where bash gives `& 0x1f` = 0x0F (measured). Neither is a separator,
  and `\cX` can never yield 0x2F or 0x5C by either formula, so no verdict changes. The impl need not
  match bash's control byte exactly; the design's "exactly what bash decodes" is inexact here and
  harmless. Not a finding.
- **`_where` totality over every emittable char.** Under the R3 rule the decoder emits only
  `chr(0x00…0xFF)`, literal ASCII escape text, and control bytes ≤ 0x1F — no code point above 0xFF,
  hence no lone surrogate. `_where` resolves all of these without raising (a NUL is caught by
  `realpath`'s `ValueError` → *could not be resolved*). Measured, both platforms.
- **`\U` ≥ 0x80000000.** bash emits nothing in every locale, so `$'\Uffffffffx'` is `x` inside; the
  R3 decoder keeps it literal and so denies on Windows (over-refusal, not a regression). Deliberate,
  documented (§D5); one over-refusal traded for one rule.
- **Spec-delta integrity.** Diffed against the shipped requirement (`agent-run-sandboxing/spec.md`
  lines 595–697): exactly one paragraph and one scenario are added, no shipped line is removed, the
  requirement's first physical line carries SHALL. `openspec validate --strict` passes.
- **PowerShell dialect.** The decode fires only in the bash dialect (`quote is None and $ followed
  by '` in `_lex`); PowerShell has no `$'…'`. Unchanged from R1/R2. Mutation §4.5 pins it.

## What R3 should attack (R2's list — addressed by R3, see "What round 3 changed")

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
   *(R3 note: N3's Windows answer is now **deny outside**, not allow — see finding 1.)*

## What the pre-approval review should attack

1. **The locale dependency is the load-bearing new fact — is it stated correctly and is the fix's
   scope right?** R3's finding 1 rests on Git Bash rendering `\u`/`\U` above 0xFF *literally* in the
   C locale and as UTF-8 bytes in a UTF-8 locale, and on the agent's Bash tool's locale being
   unguaranteed (non-login `bash -c` is C here; `bash -lc` is UTF-8). The decoder is made safe under
   **both** by keeping the backslash above 0xFF. Attack: is there any locale in which bash produces a
   `/` (not just a `\`) from a `\u`/`\U` above 0xFF that the ≤ 0xFF rule would miss? (UTF-8 bytes of
   any codepoint ≥ 0x80 are all ≥ 0x80, never 0x2F or 0x5C — but verify.) And is the Windows-only,
   locale-conditional nature honestly reflected in the finding's severity — this is a regression the
   change would *introduce* on Windows, not a pre-existing hole, and Linux is sound either way.
2. **Is the keep-literal set now provably complete, or is there a fourth leak?** R3 replaced R1/R2's
   per-escape arguments with an invariant (decode to a char only when it is a determined,
   locale-independent non-separator; else keep the backslash). Attack the invariant, not the list:
   find any input where bash leaves a backslash (or a `/`) in the word that the R3 decoder removes.
   Candidates not yet exhausted: `\c` followed by `\'` or `\\`; `\u{...}`-style brace forms;
   `$'…'` split across an adjacency with the backslash at the seam; a decoded byte in 0x80–0xFF that
   `os.path` on Windows treats specially.
3. **N3's changed answer.** R3 flips N3's *after* answer on Windows from R2's **allow** to **deny**
   (and drops the `chr()` guard for a ≤ 0xFF cap). Confirm the tasks (§1 marks, §4 mutations) and
   the test-guide were all updated to match, and that no artifact still asserts N3 allows on Windows.
4. **The `\c`-before-quote fix must not consume the closing quote.** The impl must not read past the
   body's closing `'` for any escape. Confirm tasks §2.2 forbids it explicitly and a mutation
   (§4.8) that consumes the quote fails a named row (N5).
5. **The drive can only reach one bash locale.** §5.2 runs on Windows and exercises N2/N4/N5 (all
   *deny outside* answers). It cannot prove which locale the agent's Bash tool used, so it cannot by
   itself show finding 1 is a *live* escape rather than a latent one. Decide whether that honesty is
   stated, and whether the CI Linux job (which is sound regardless) plus the Windows deny-reason
   drive is sufficient evidence, or whether a locale probe inside the drive is warranted.

## Pre-approval review (Opus, 2026-09-13)

Adversarial review before approval. Everything below was measured on this machine against
`autonomous/2026-09-12-daily`. Scratch: `testbed/scratch/opusf332/` (`decoder_check.py`,
`check_43.py`) and `<scratchpad>/bashtruth.py`, `<scratchpad>/locale_probe.py`. **Verdict: approve
after the three repairs below (all made in this commit); the R3 decoder, the D2 verdict table, the
spec delta, and the POSIX F332 fix are sound.**

**Finding A (major; the argument is wrong, the outcome is safe) — R3 finding 1's central factual
claim about Git Bash is false on this machine, and its "security escape" severity is
unsubstantiated.** Measured with `bashtruth.py` and `locale_probe.py`: Git Bash 5.2.37 (msys2) on
this machine reports `LC_CTYPE=C.UTF-8` by default (`LANG=C.UTF-8`, not empty) and **cannot be put
into a non-UTF-8 C locale** — `LC_ALL=C`, `LANG=C`, `LC_CTYPE=C`, `POSIX` all leave `LC_CTYPE` at
`C.UTF-8`. In every one of those, `$'..\u0100'` decodes to UTF-8 bytes `2e 2e c4 80` (no backslash),
so on Windows Git Bash writes a file named `..Ā` **inside** the workspace, not a `..\…` traversal
outside. R3's own recorded probe (`r3f332/unicode_probe.gitbash.txt`) shows it measured
`LANG=[] LC_ALL=[]` — an **empty** environment that falls back to C and keeps `\u0100` literal —
which is not what a subprocess spawned on this machine inherits. Consequences:
- The design's repeated claim (D1, D5, finding 1, and by implication N3/N4, the test-guide, and
  drive §5.2) that "the C locale Git Bash uses by default keeps the escape literal, backslash and
  all" and that R1/R2 therefore *open a Windows security escape* is **backwards on the measured Git
  Bash**: there, R1/R2's decode of `\u0100` to one character (word `..Ā`, no separator, judged
  inside) *matches* what bash actually writes (inside), and it is the **R3 decoder that
  over-refuses** it (keeps `..\u0100`, whose `\` is a Windows separator → deny outside).
- **The R3 decoder is nonetheless the correct choice, and safe.** Independently re-derived and
  measured (`decoder_check.py`, both platforms; `bashtruth.py`, C and UTF-8, WSL and Git Bash):
  **no `\u`/`\U`/UTF-8 codepoint ever produces byte 0x2F (`/`) or 0x5C (`\`)** — UTF-8 of any
  codepoint ≥ 0x80 is all bytes ≥ 0x80, and a true C locale keeps a literal backslash the decoder
  also keeps. So the decoder **never emits fewer separators than bash under any locale**; every
  divergence is an over-refusal (safe). Keeping the backslash above 0xFF is right because a true C
  (non-UTF-8) locale *is* reachable (empty `LANG`), and there is no measured platform where the
  decode-to-char behaviour would let a real traversal through.
- **Severity is therefore "over-refusal traded for locale-independence", not "security".** This is
  the round discipline's named failure mode — an argument wrong while its Linux/UTF-8 outcome is
  right. **Repair (this commit):** a correction banner above finding 1; this section; and the
  test-guide's N3/N4 wording softened to "conservative over-refusal / locale-dependent" rather than
  "bash writes outside". No code, table, or test assertion changes — the R3 decoder denies N3/N4 on
  Windows, which every pinned row already asserts.

**Finding B (moderate; a test hole) — mutation §4.3's chosen row does not catch the mutation on
POSIX, and its assertion is false on Windows.** Measured (`check_43.py`, both platforms):
`echo "x$'..\x2fy'"` decodes to `x../y`, which resolves **inside** the workspace. So with the
"fire regardless of quote" mutation applied, on **POSIX** the answer is `allow` both with and
without the guard — **no flip, the mutation leaves the table green** (the tasks' own "a mutation
that leaves the table green is a hole"). On **Windows** the unmutated answer is `deny_unchecked`
(the literal `$` and `\` trip rule 3), so §4.3's "assert it stays allowed unmutated" is false.
**Repair (this commit):** §4.3 now specifies an *escaping* row `echo "$'..\x2f..\x2f..\x2fout'"`
(measured allow→deny_outside flip on POSIX) and says to assert it on POSIX; §4.5 gets the same
platform note.

**Finding C (minor; task precision) — mutation §4.4 was not platform-scoped, but only flips on
POSIX.** Dropping octal/`\u`/`\U` decoding leaves `$'..\057x'` as literal `..\057x`; on **Windows**
the kept `\` is itself a separator, so G2/G3/G4 still resolve outside and stay `deny_outside` — the
mutation does **not** make them fail there. The night runs on Windows. **Repair (this commit):**
§4.4 now says to verify it under WSL/POSIX (like §4.1's POSIX rows).

**Checks that found nothing (the change is sound here):**
- **Decoder safety, both platforms, both locales (`decoder_check.py`, `bashtruth.py`).** Full D2
  table + adversarial rows correct: POSIX G1–G10/D1 deny, I1/N1/OK allow; Windows G1–G10 deny,
  N1–N5 deny, I1/OK allow. `\c` never yields a separator (`\c/`→0x0f, `\c\`→0x1c). `\u{2f}` brace
  form is unsupported by bash and kept literal (matches). `\x`/octal are byte escapes, faithful and
  locale-independent; `\457` wraps mod 256 to `/`.
- **Totality (`decoder_check.py`, both platforms).** No input raises: `\U110000`/`\U7fffffff`/
  `\Uffffffff` (kept literal, `chr()` never called above 0xFF), lone surrogate `\ud800` (>0xFF,
  kept literal), embedded NUL (`_where` catches `ValueError`), unterminated `$'`, trailing
  backslash, a 10 000-char input. R1 raises `ValueError`/`OverflowError` on the overrange escapes
  (confirming §4.7's totality mutation bites); R3 does not.
- **Mutations §4.6/§4.7/§4.8 bite (`decoder_check.py`, Windows).** R1 flips N2/N4/N5 to allow and
  raises on N3; R2 flips N3/N4/N5 to allow. So each named row is killed by its mutation.
- **Spec-delta integrity.** `comm` against the shipped requirement (`agent-run-sandboxing/spec.md`
  lines 595–696): every shipped line survives byte-for-byte, exactly one prose paragraph and one
  scenario (`A quote that spells a separator is judged by what it decodes to`) are added, SHALL is
  on the first physical line, `openspec validate --strict a-quote-can-spell-a-slash` passes.
- **No new reason string; import + annotation constraints intact.** Reasons are the existing
  `_OUTSIDE`/`_UNCHECKED`; the decoder is a stdlib state machine (fastmcp+stdlib only preserved);
  `approve_tool_call` is untouched and keeps no return annotation.
- **Operator commits `a3237be` (F341) and `55a95de` (F343/F344).** Touch `pty_runner.py`,
  `subprocess_windows.py`, `cli.py` and their tests — **not** `mcp_server.py` or
  `test_permission_approver.py`, so no conflict with this change's product diff. F341 changes how
  the agent's shell is spawned on Windows, which can alter the locale the Bash tool inherits — this
  only reinforces finding A's "locale is unguaranteed", and the decision logic is locale-safe, so
  the drive's assertions (refused as outside; no file appears) hold regardless.

**Residual risk the night should know.** The drive (§5.2) runs on Windows and, for N4 (`$'..\u0100'`),
shows a **conservative over-refusal**: if allowed, the real Git Bash (C.UTF-8) would write `..Ā`
*inside* the worktree, so an operator who reruns the command bare will see a file appear inside and
may read the refusal as wrong. This is the same category as I1 (an over-/under-refusal corrected or
kept), is safe, and is documented; it is a product judgement, not a defect.
