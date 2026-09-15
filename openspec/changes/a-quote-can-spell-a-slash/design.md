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
- `\cX` a control character, for **any real body character** including a multi-byte UTF-8 one
  (`\c` + é is `03 a9` — the control byte of X's *first* UTF-8 byte, the remaining bytes kept
  literal; measured) — **but `\c` with no body character after it, i.e. immediately before the
  closing quote, keeps its backslash literal** (bash `$'..\c'` is `..\c` — measured,
  `testbed/scratch/r3f332/`), and the decode MUST NOT consume the closing quote as the control
  target. R2's one-phase decoder did — see R3 finding 2. **Round 4: restricting this to an ASCII
  `X` was tried and rejected** — it re-creates a phantom path component for the same reason a
  restricted `\u`/`\U` rule does (see the invariant below), because it turns a would-be-safe
  multi-byte control decode back into a kept literal that adds a component. `\cX` itself is
  always safe regardless of X's byte length: it can never emit `/` (0x2F) or `\` (0x5C) — a
  control byte is X's first byte `& 0x1F`, and every UTF-8 lead/continuation byte is ≥ 0x80 —
  and it always contributes exactly one component either way, so no divergence from bash is
  possible here (measured, `%TEMP%/f332/adv.sh`, `$'A\cé/../../y'`);
- an **unrecognized** escape keeps its backslash (`\/` decodes to backslash-slash, `\q` to
  backslash-q — measured, and bash rc=1 on `\/` because the resulting name has no such directory);
- a **digitless** `\x`, `\u` or `\U` (a `\x` with no hex digit following, etc.) **keeps its
  backslash** — bash `$'\x'` is the two characters backslash-x, not `x` (measured,
  `testbed/scratch/r2f332/decode_b.sh`: `digitless x -> \\x`). This is security-relevant on
  Windows and R1 had it wrong — see R2 finding 1;
- `\uHHHH`/`\UHHHHHHHH` **at or below 0xFF** decode to a character (locale-independent — see
  below);
- `\uHHHH`/`\UHHHHHHHH` **from 0x100 to 0x7FFFFFFF** are locale-dependent, and **Round 4
  replaces the R3 "always keep literal" rule with a dual reading, judged against both.** bash's
  rendering here genuinely differs by the shell's locale — a UTF-8 locale decodes to real
  multibyte UTF-8 (no backslash), a C/non-UTF-8 locale keeps the escape literal (backslash and
  all) — and **both are live on this machine**: measured directly, `LANG=` empty (this Hub's
  Bash-tool default) and `LC_ALL=C`/`LANG=C` all keep `\u0100` literal, while any
  `LANG=*.UTF-8` decodes it (`%TEMP%/f332/loc.sh`). R3 assumed only the C reading was reachable
  here and so always kept the backslash; the pre-approval review's claim that Git Bash "cannot
  be put into a non-UTF-8 C locale" was **measured false** by Round 4 — so R3's rule, applied
  inside a longer path, opens a Windows escape of its own (Round 4 finding, below). **The rule
  is now: render both the C-locale literal reading and the UTF-8-decoded reading, and refuse the
  command if *either* reading would put the write outside the workspace.** Building it is one
  boolean flag threaded through `_lex` and `_read_command` (**including its own recursive call
  for a nested substitution** — Round 4: a reading argument that stops at the top level judges
  `$(...)`-nested ANSI-C in one reading only, which is wrong), with `_decide` running both
  passes the way it already reads an unknown tool in both dialects, and refusing if either pass
  refuses;
- `\uHHHH`/`\UHHHHHHHH` **at or above 0x80000000** decode to **nothing** — not "keep
  literal". bash emits nothing for these in *every* locale, measured exactly at the boundary
  (`%TEMP%/f332/w4.sh`: `\U7fffffff` kept literal, `\U80000000` → nothing) — this is
  locale-**independent**, so it needs no dual reading, and R3's "keep literal" answer for it was
  itself the bug Round 4 found (see below);
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

**The safety invariant (replaced by Round 4 — R3's version was wrong, not just incomplete).** R3
stated the invariant as a **separator count**: the decoder is safe iff it never emits fewer
separators than bash emits under any reachable locale, reasoning that an extra kept-literal
backslash can only make the decoder more conservative. **Round 4 measured a case where that is
false.** A kept-literal escape does not just add a separator in isolation — inside a longer word
it inserts an extra *path component* between two real ones, and a `..` chain after it can absorb
that phantom component instead of climbing past it. `mkdir A; echo hi > $'A\Uffffffff/../../x'`:
bash emits nothing for `\Uffffffff` in every locale, so bash's real word is `A/../../x` — one real
component before two `..`, landing one level **above** the workspace root, genuinely outside. R3's
decoder keeps `\Uffffffff` literal, so its word is `A\Uffffffff/../../x` — **two** apparent
components (`A`, then `Uffffffff`, the kept backslash itself being a Windows separator) before the
same two `..`, landing exactly at the workspace root — **inside**. The extra separator did not
make the decoder stricter here; it hid a real escape by giving the `..` chain something harmless
to consume first. Measured directly against real Git Bash and the real `_decide`
(`%TEMP%/f332/w3.sh`, `proto.py`): R3's decoder answers **allow** where bash's real write is
outside.

**The corrected invariant is about component structure, not separator count, and is stated
directly in terms of the decision, not in signed depth arithmetic — Round 4's first attempt at
this restatement used "shallower"/"deeper" language that reads oppositely depending on which sign
convention the reader assumes, and a signed-depth phrasing is exactly the kind of restatement that
can silently re-derive the R3 bug it replaces. Stated unambiguously:**

> **The decoder may answer allow only if *every* rendering bash could actually produce — across
> every locale the run's shell might use — would itself write inside the workspace. Equivalently:
> the decoder must refuse if *any* reachable rendering would write outside.**

This is checked by walking each candidate rendering's real path-component sequence exactly as bash
would produce it (each `..` climbs one level, every other component descends one level from
wherever the walk currently is) and confirming the walk never leaves the workspace subtree for
*that* rendering. A kept-literal escape is safe only when it reproduces the same component that
bash's real rendering has *at that position* — not merely "some extra separator", because an extra
component in the wrong position can let a `..` climb the decoder inserted (rather than a real one)
without ever landing outside in the decoder's own accounting, even while bash's real, shorter
rendering does land outside. `mkdir A; echo hi > $'A\Uffffffff/../../x'` is the concrete failure of
the old phrasing: bash's one real rendering is `A/../../x`, which walks to one level **outside**
the workspace — so by the rule above, the decoder must refuse. R3's decoder answers allow, because
its kept-literal `\Uffffffff` inserts a component bash's rendering never has, and the `..` that
should have climbed past the workspace root climbs past the decoder's phantom component instead. An escape may
**decoded to a character** (removing its backslash, contributing no separate component) only when
that character's *component contribution* is fully determined and locale-independent: the simple
escapes, `\NNN` octal and `\xHH` hex (byte escapes, always ≤ 0xFF, so they can decode to a real
separator byte and nothing else locale-dependent), `\uHHHH`/`\UHHHHHHHH` whose value is ≤ 0xFF (the
only separator bytes below 0x100 are ASCII, decoded identically in every locale), and `\cX` for any
real body character (never produces a separator byte, always exactly one component — see above).
**Where a rendering genuinely differs by locale, both readings must be judged and the command
refused if either would escape** — this is new in Round 4, and is what closes the compound case
above: `\uHHHH`/`\UHHHHHHHH` from 0x100 to 0x7FFFFFFF now gets a dual reading (the C-locale literal
and the UTF-8 decode) rather than an unconditional "keep literal", because the pre-approval
review's premise that only the C reading is reachable on this machine was **measured false** by
Round 4. `\uHHHH`/`\UHHHHHHHH` at or above 0x80000000 is now **decoded to nothing**, matching
bash's own locale-independent behaviour exactly, rather than kept literal — R3's "keep literal"
answer for this range was itself the phantom-component bug, not a safe over-refusal. In every
remaining case the backslash is still kept literal — a digitless `\x`/`\u`/`\U` (R2 finding 1), a
`\c` with no body character after it (R3 finding 2), an unrecognized escape, and a trailing
backslash — because these render identically in every locale (bash always keeps them literal as
syntax, not as a locale choice), so keeping the backslash reproduces bash's own single component
exactly rather than adding a phantom one. See "What round 4 changed" for the full re-derivation,
the new adversarial cases it constructed, and what stays true from Round 3.

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
| N3 overrange `\U` | Bash | `echo hi > $'\Uffffffffx'` | **inside (file `x`), every platform, every locale** (Round 4: bash emits nothing for `\U`>=0x80000000, measured at the exact boundary) | POSIX allow / Win deny (unchecked) | POSIX allow / Win deny (unchecked) | **allow (inside), every platform** -- Round 4 decodes this range to nothing, matching bash exactly. R1 **raises**, R2 wrongly **allows on Win** for the wrong reason (an unguarded `chr()` that happened not to fire on this row), R3 wrongly **kept it denied** believing it an over-refusal -- Round 4 corrects all three |
| N4 `\u`>0xFF | Bash | `echo hi > $'..\u0100'` (value 0x100) | POSIX: inside; Win: **outside** under a C/non-UTF-8 locale (kept literal `..\u0100`, `\`=sep) -- **both C and UTF-8 locales are reachable on this machine, measured (Round 4)** | POSIX allow / Win deny (unchecked) | POSIX allow / Win deny (unchecked) | POSIX allow; **Win deny outside** (unchanged from R3 -- the dual reading's C-locale pass alone already refuses this single-component form; Round 4 confirms this row does not move) |
| N5 `\c` at close | Bash | `echo hi > $'..\c'` (`\c` before `'`) | POSIX: inside (name `..\c`); Win: **outside** (`..\c`, `\`=sep) | POSIX allow / Win deny (unchecked) | POSIX allow / Win deny (unchecked) | POSIX allow; **Win deny outside**. R1 & R2 both wrongly **allow on Win** (consume the closing quote) -- R3 finding 2 |
| OK1 inside | Bash | `python sub/hello.py` | inside | allow | allow | allow |
| OK2 own-hub | Bash | `curl -s "$HUB_URL/api/v1/agent-actions/tasks"` | (request) | allow | allow | allow |
| P1 phantom component, `\U`>=0x80000000 (Round 4) | Bash | `mkdir A; echo hi > $'A\Uffffffff/../../x'` | outside, every locale (one real component `A`, decode-to-nothing, two `..`) | (new form; not in R1-R3's table) | (new form; not in R1-R3's table) | **deny, outside, every platform.** R3's decoder (keep-literal above 0xFF, including this range) wrongly **allows**: the kept `\Uffffffff` becomes a second apparent component that absorbs one `..`, landing at depth 0 instead of bash's real depth -1. This is the case that broke R3's invariant; Round 4's decode-to-nothing rule removes the phantom component entirely and matches bash's real word (`A/../../x`) exactly |
| P2 phantom component, `\u`/`\U` 0x100-0x7FFFFFFF (Round 4) | Bash | `mkdir A; echo hi > $'A\u0100/../../x'` | outside under a UTF-8 locale (one real component `AĀ`, the decoded character glued onto `A`, then two `..`) | (new form) | (new form) | **deny, outside.** The C-locale reading alone still shows the phantom component (`A`, `u0100`, `..`, `..` -> depth 0, allow) -- the *dual* reading is load-bearing here: the UTF-8 reading correctly computes depth -1 (outside) and the rule refuses if *either* reading refuses, so the pair together closes this case even though neither reading is individually sufficient |
| P3 two leading components (Round 4) | Bash | `mkdir -p A/B; echo hi > $'A/B\u0100/../../../x'` | outside under a UTF-8 locale (measured) | (new form) | (new form) | **deny, outside** -- same mechanism as P2, one more `..` and one more real component; confirms the dual reading generalises past a single leading component |
| P4 `\cX`, non-ASCII body, corrected (Round 5 fixes a wrong command in Round 4's row) | Bash | `mkdir A; echo hi > $'A\cé/../../x'` | outside, every locale (`\c`+é is one component, the control byte of é's first UTF-8 byte; measured) | (new form; deny, unchecked, both platforms -- has no real `/`, but the leading `$` and, on Windows, the literal kept `\` of the not-yet-decoded escape both trip rule 3 today) | (new form) | **deny, outside.** Confirms `\cX` for a real non-ASCII body character does not reopen the phantom-component class -- it always contributes exactly one component and can never itself be a separator byte, so no dual reading is needed here. (Restricting `\c` to an ASCII `X`, briefly tried during the night and dropped, would recreate this bug by falling back to a kept-literal, separator-producing form. Round 4's own row pinned the ASCII form it meant to reject, not this one -- Round 5 caught it.) |
| P5 keep-literal compounds, corrected (Round 4's "stays safe, unchanged" framing was wrong -- Round 5) | Bash | `mkdir A; echo hi > $'A\x/../../y1'`, `$'A\u/../../y2'`, `$'A\q/../../y3'` (digitless `\x`, digitless `\u`, unrecognized `\q`) | **platform-dependent, not uniformly inside.** POSIX: `\` is not a separator, so `A\x` etc. is **one** real component, then two `..` -- **outside** (measured: bash's real word `A\x/../../y1` walks to one level above root). Windows: `\` **is** a separator, splitting `A\x` into **two** components (`A`, `x`), which the same two `..` exactly absorb -- **inside** | deny, unchecked, both platforms (has a real `/`, and the leading `$` trips rule 3; unaffected by platform since the backslash question does not arise until the escape is actually decoded) | (new forms) | **Not "stays safe unchanged" -- a real, platform-split flip, same shape as N1/N2.** POSIX: **deny, outside** (reason improves from unchecked; the decoder's kept-literal rendering correctly matches bash's one-component POSIX truth, which is outside). Windows: **allow, inside** (deny-to-allow flip; the decoder's kept-literal rendering correctly matches bash's two-component Windows truth, which is inside). Both are *correct* -- the row was never wrong about the decoder matching bash, only wrong about summarising both platforms as one unchanging "inside" |
| P6 `$$\'...'`, corrected today-POSIX (Round 4 said unchanged; Round 5 measured a real flip there) | Bash | `echo hi > $$'..\x2fq'` | inside (`$$` is the shell PID, then an ordinary single-quoted literal `..\x2fq` -- not ANSI-C at all, no escape processing) | **POSIX: allow** (the raw word `$$..\x2fq` has no `/` at all -- `\x2f` is unprocessed literal text today, not a decoded separator -- so rule 4 lets it through unchecked, same hole F375 names, reached a different way). Windows: deny, unchecked (the literal `\` counts as a separator, and the leading `$$` trips rule 3) | deny, unchecked, both platforms (the lexer's `$'` detection fires at the *second* `$`, decoding `..\x2fq` to `../q` and leaving the first `$` glued in front as `$../q` -- a real separator plus a leading `$`, rule 3 on both platforms) | **POSIX flips allow to deny (reason improves to unchecked); Windows unchanged.** Still over-refusal only where it denies, proved by Round 4's argument (the decoder's word always opens with a literal `$`, and any separator it contains trips rule 3 before depth ever matters) -- but the POSIX *today* value was wrong, not the safety conclusion. `$$\'x/../../q'` (bash: outside) correctly still denies on both platforms |
| P7 embedded NUL, corrected (Round 4 understated this as "not fixed"; Round 5 measured this change actually flips it) | Bash | `cp notes.md $'..\x00x'` | outside (bash truncates the word at the NUL: the real argument is `..`, which lands outside via rule 4's bare-`..` hole, not via anything this change decodes) | **POSIX: allow** (the raw undecoded word has no `/`, rule 4). Windows: deny, unchecked (raw word has a literal `\`, and the leading `$` trips rule 3) | **allow, both platforms.** D5 decodes `\x00` to an actual NUL byte inside the word (`..` + NUL + `x`); that word has **no separator character at all**, so rule 4 -- "not a path" -- returns before `_where` (and its NUL-triggered `realpath` refusal) is ever reached. The NUL never gets a chance to be caught | **This is a real deny-to-allow flip on Windows, not a neutral non-fix -- say so plainly, do not pin it as unchanged.** It does not meaningfully widen exposure: the unrestricted, unescaped route to the same outcome (`cp notes.md ..`, no quoting at all) is **already allowed today**, independent of this change or of ANSI-C decoding (F375). This change removes an *accidental* block on one dressed-up spelling of a hole that was already open in plain text. **Do not add NUL-truncation handling here to make this row deny** -- that would fix one spelling of F375's hole while leaving the direct one (and any other spelling) open; F375's own change is where the real fix belongs. Pin this row's *after* value as **allow**, with a comment pointing at F375, so a future reader does not mistake the flip for a regression this change is silently responsible for |

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
- **N3 (overrange `\U`, revised again by Round 4):** `\U110000`…`\U7fffffff` (below 0x80000000)
  still keep the C-locale backslash literal — bash's C-locale rendering there really is a Windows
  traversal, so R2's original deny→allow flip for this sub-range was correctly rejected by R3 and
  still is. But `\U` ≥ 0x80000000 (`\Uffffffff`, this row's own form) is a **different sub-range**,
  and R3's own text already said bash produces nothing there in every locale — R3 just then chose
  to leave it denied anyway, reasoning that was a harmless over-refusal. **Round 4 found that
  reasoning was the bug**, not the safe choice: kept literal inside a longer path, that same
  backslash becomes the phantom component P1 exploits. Decoding this sub-range to nothing (§D1)
  removes the phantom component and lets this row flip deny→allow correctly. POSIX allow,
  unchanged.
- **N4 (`\u`/`\U` above 0xFF, R3, confirmed unchanged by Round 4):** Windows stays **deny**,
  reason improving from *cannot be checked* to *outside*. R1 and R2 both decode it to one
  character and would flip it to **allow** — the escape R3 finding 1 caught, and Round 4's dual
  reading agrees with R3 here because the C-locale reading alone already refuses this
  single-component form (no leading real component for a phantom one to hide behind — that
  needs P1–P3's shape). POSIX allow, unchanged.
- **N5 (`\c` before the closing quote, R3):** Windows stays **deny**, reason improving from *cannot
  be checked* to *outside*. R1 and R2 both consume the closing quote as `\c`'s control target and
  would flip it to **allow** — R3 finding 2. POSIX allow, unchanged.
- **L1, OK1, OK2 unchanged.**
- **P1–P7 are new (Round 4).** P1–P4 pin the phantom-component class the compound cases expose and
  confirm the correction closes each one; P5 confirms the compound form of the already-safe
  keep-literal cases (N2's class) doesn't regress; P6 confirms `$$'…'` can only over-refuse; P7
  pins a mismatch this change does **not** fix — see F375 (filed separately) and D2's row above.

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

**The C-locale reading's `chr()` call still cannot raise, by the same argument R3 made (revising
R2 finding 2), narrowed to the values that reading ever decodes.** `chr()` is called **only for
values ≤ 0xFF** in the C-locale reading — the byte escapes (`\xHH` ≤ 0xFF, `\NNN` mod 256) and
`\uHHHH`/`\UHHHHHHHH` values ≤ 0xFF — and every codepoint above 0xFF is kept literal in that
reading (§D1), so no value that would raise `ValueError`/`OverflowError` reaches it. A lone
surrogate (`\ud800`, value 0xD800 > 0xFF) is likewise kept literal rather than passed to `chr()`.

**Round 4: the UTF-8 reading reopens the trap R2 closed and R3 removed the guard for — it must be
guarded again, separately. Round 5 corrects Round 4's own justification for the guard, which was
measured false.** The UTF-8 reading exists specifically to decode `\uHHHH`/`\UHHHHHHHH` from 0x100
to 0x7FFFFFFF (§D1's dual reading), and `chr()` raises `ValueError` above U+10FFFF (0x10FFFF) —
measured, `$'\U110000'` and `$'\Uffffffff'` both raise if passed to `chr()` unguarded. R2's
original guard (`if value > 0x10FFFF: return ""`) is not simply restored, but **not for the reason
Round 4 gave.** Round 4 claimed bash renders nothing above 0x10FFFF in any locale — **measured
false by Round 5**: under a UTF-8 locale, bash mechanically applies its own (pre-RFC 3629, up to
6-byte) UTF-8 encoding even to values Unicode itself does not define, and produces real bytes —
`$'A\U00110000\x…'` renders `41 f4 90 80 80 …`, not nothing.

**The guard is still correct, for a narrower and actually-true reason: none of those bytes can
ever be a separator.** A UTF-8 lead byte for a 5- or 6-byte legacy sequence is always in
`0xF8`–`0xFD`, and every continuation byte is always `0x80`–`0xBF` — neither range can ever equal
`/` (0x2F) or `\` (0x5C). So while replicating bash's exact legacy encoding above 0x10FFFF would be
more faithful, it is not more *safe*: whatever bash actually renders there, it is guaranteed to
contribute a non-separator, and **exactly one** component (the bytes are contiguous with no
separator among them) — precisely what a placeholder needs to guarantee, not what it needs to spell
correctly. **The UTF-8 reading therefore emits one fixed placeholder character for any value above
0x10FFFF**, so the dual-reading comparison still runs, and totality holds without `chr()` ever being
called outside `0 ≤ value ≤ 0x10FFFF`.

**The placeholder must be a plain ASCII word character (`_PLAIN_RELATIVE_RE`'s `\w` class), not an
arbitrary "non-separator" one.** Round 5: a placeholder outside `\w` (a symbol, an unassigned code
point) can change which of rules 5/6 a word reaches — `_judge_word` rule 5 matches
`_PLAIN_RELATIVE_RE` first, and a non-`\w` character can fall through to rule 6's regex backstop
instead. That never changes the *verdict* the invariant cares about (both rules call `_judge_path`
on the same resolved path), but it can change the *refusal text* a row asserts, which would make a
pinned test brittle for the wrong reason. Pick a single fixed ASCII letter (e.g. `"z"`, chosen once
and never derived from the input) so the placeholder is unambiguously `\w` and every row's refusal
text is predictable.

**`\U` ≥ 0x80000000 (`\Uffffffff`) is no longer judged from a kept-literal backslash, and is no
longer an over-refusal.** §D1 (Round 4) now decodes this range to **nothing**, exactly matching
bash's own behaviour in every locale — R3's "keep literal, over-refuse" answer for this range was
the phantom-component bug Round 4 found, not a safe trade. `$'\Uffffffffx'` (D2 row N3) now
**allows** on Windows, writing a file named `x` inside, matching bash exactly — this is a
behaviour change from the R3-approved table, not merely a reworded reason; see "What round 4
changed" and D2's revised N3 row.

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

## What round 4 changed

Round 4, 2026-09-15, re-derived the decode set against real Git Bash 5.2.37 (msys2, this machine)
a second time, this time specifically attacking R3's own invariant rather than re-checking its
individual escape rules — the operator's own decision (`spec-queue/DECISIONS.md`, `F332-rule`)
asked for exactly this before the night's candidate correction could be built. Scratch is in
`%TEMP%/f332/` (`decode2.sh`, `loc.sh`, `w3.sh`, `w4.sh`, `nul.sh`, `adv.sh` = bash truth; `proto.py`
= the correction run through the real `_decide`).

**The invariant itself was wrong, not just incomplete.** R3's "never emit fewer separators than
bash" reasoning holds for every single-escape form R1–R3 ever tested, and fails for a shape none
of them constructed: a real path component *before* a kept-literal escape, followed by enough
`..` to matter. `mkdir A; echo hi > $'A\Uffffffff/../../x'` — measured through the real
`_decide` with the R3-as-approved decoder — answers **allow**, while bash's real write
(`A/../../x`, since bash emits nothing for `\U`≥0x80000000 in every locale) lands one level
**above** the workspace root. The kept `\Uffffffff` becomes a phantom path component that
absorbs one of the two `..`, so the decoder's apparent depth (0, at the workspace root) is
shallower — safer-looking — than bash's real depth (-1). See §D1's replaced invariant.

**The pre-approval review's premise was also measured false.** It stated Git Bash on this machine
"cannot be put into a non-UTF-8 C locale". Round 4 measured directly: `LANG=` empty (this Hub's
own Bash-tool default), `LC_ALL=C` and `LANG=C` all keep `\u0100` literal (the C-locale reading);
any `LANG=*.UTF-8` decodes it. **Both readings are live, not one hypothetical and one real** — so
the dual-reading correction (§D1) is necessary, not a conservative extra.

**Every rule the night's candidate correction sketched is confirmed correct, and closes every
compound case Round 4 could construct** — P1–P4 in D2's table, each measured against real bash
and the real `_decide`: two leading path components (P3), an escape that decodes validly under
both locale readings but to different byte lengths (P2), `\cX` combined with the phantom-prone
shape (P4). None reopened the bug.

**Two things the sketch did not anticipate, both now fixed:**
1. **A `chr()` totality trap in the new UTF-8 reading.** That reading decodes values up to
   0x7FFFFFFF, and `chr()` raises above 0x10FFFF (no such Unicode code point exists). R2 closed an
   identical trap once already, and R3 removed the guard because its own decoder never called
   `chr()` above 0xFF; the UTF-8 reading reopens exactly the range R2 guarded. §D5 restores a
   guard, scoped to the UTF-8 reading only: a fixed placeholder character for any value above
   0x10FFFF, so the dual-reading comparison still runs and `chr()` is never called outside
   `0 <= value <= 0x10FFFF` anywhere in the decoder.
2. **The reading flag must thread through `_read_command`'s own recursive call.** A command
   substitution (`$(...)`) is read by a fresh call to the same function; a flag that only the
   top-level call sets judges a nested ANSI-C escape in one reading and not the other, silently
   narrowing the dual check for anything inside a substitution. §D1 states this explicitly now;
   it was implicit (and unstated) in the night's sketch.

**Confirmed safe, not merely re-asserted:**
- **`$$\'…'` can only over-refuse (P6).** Proved, not just measured on one example: the
  decoder's word always opens with a literal `$`, which trips rule 3 on its own whenever the word
  also carries a separator; and where the decode leaves *no* separator, every backslash in bash's
  raw text began a recognised escape, so no component after the PID-glued first one can be an
  unescaped `..` — bash's own depth can never go negative there either. `$$\'x/../../q'` (bash:
  outside) still correctly denies.
- **`\cX` for a non-ASCII `X` is safe, and restricting it to ASCII is the actual trap (P4).**
  `\cX` takes the control byte of X's first UTF-8 byte and keeps the rest of X's bytes literal;
  it can never emit `/` or `\`, and always contributes exactly one path component regardless of
  X's byte length, so no dual reading is needed for it. The night's own build briefly restricted
  `X` to ASCII and found this reopened the phantom-component class in a new shape — Round 4
  confirms that restriction must not ship.

**One real mismatch found, and it is not this change's to fix.** `cp notes.md $'..\x00x'` (P7):
bash truncates the ANSI-C word at the embedded NUL, so the real argument is a bare `..`, which
lands outside the workspace. The dual-reading correction does not truncate at NUL and would answer
allow. Tracing why: `_judge_word`'s rule 4 treats any word with **no separator character** as "not
a path" and never calls `_where` on it at all — and a bare `..` has no separator. This is a
pre-existing hole, completely independent of ANSI-C decoding (`cp notes.md ..` is already allowed
today, unescaped, with no quoting tricks needed at all — measured). **Filed as F375, severity A,
its own finding.** This change should pin P7 against the unmodified decoder as evidence the
mismatch exists, and must not paper over it with ad hoc NUL-truncation logic inside the ANSI-C
decoder — that would fix one route into rule 4's hole while leaving every other route (a `.`-only
word, a truncation from some other escape) open.

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
