# Tasks — a quote can spell a slash

Implementation belongs to a night window. **No task here is complete because this plan exists.**
Only verified implementation closes one. Size each section so one night firing finishes it.

**This change is Python-only.** No `hub/ui` change, so `hub/hub/static/ui` is **not** rebuilt. The
Python lint set **is** required (§6).

**Two constraints of `hub/hub/mcp_server.py` bind every task.**
- It is spawned standalone and may import **only** the standard library and fastmcp. The ANSI-C
  decoder is stdlib code (a small state machine). Add nothing else.
- `approve_tool_call` has **no return annotation**; with one, FastMCP emits `structuredContent` and
  a correct `allow` is silently not honoured. Nothing here touches that function, and
  `test_response_carries_no_structured_content` must still pass.

**The table is pinned first, and the tree stays green at every commit.** §1 pins D2's rows against
the **unmodified** lexer, marking each row that will move `xfail(strict=True)`; §2 removes those
markers as the decode lands. A strict xfail that starts passing early is a failure — that is the
point: a row may not change answer before the decode exists.

## 1. Pin the table before the lexer moves

- [x] 1.1 In `hub/tests/test_permission_approver.py`, add D2's table as one parametrized test over
  `_decide("Bash", {"command": …})`. Every row goes in: G1–G10, D1, I1, L1, N1, **N2, N3, N4, N5**,
  OK1, OK2 (N2 = `echo hi > $'..\x'`, a digitless `\x`; N3 = `echo hi > $'\Uffffffffx'`, an overrange
  `\U`; **N4 = a `\u` escape whose value 0x100 is above 0xFF — the command is `echo hi > $'..` then
  the six literal characters backslash-u-0-1-0-0 then `'`, built in Python as
  `"echo hi > $'..\\u0100'"` (NOT the decoded character U+0100); N5 = `echo hi > $'..\c'`, a `\c`
  immediately before the closing quote** — R3 added N4 and N5
  to close two more decoder defects of the same class as R2's, and reshaped N3, see "What round 3
  changed"). Use the
  existing `workspace` fixture (it has `sub/` and the workspace directory is named `work`, so write
  the escapes against `../work`-relative paths as D2 does) and set `HUB_URL=http://127.0.0.1:8016`
  with `monkeypatch`. For each row assert `allow`, and where D2 names a reason assert a
  distinguishing substring:
  - outside: the whole decoded path, e.g. `"'../stray.txt'"` for G1;
  - cannot be checked: `"cannot be checked"` present, `"outside your workspace"` absent (D1);
  - inside: `allow is True` (I1, OK1, OK2).
  Build each escaped command from explicit bytes/`chr` where a literal `\uHHHH` in a source string
  would be mangled by an editor (see DEAD-ENDS, backslash handling); assert once at import that each
  command string contains the intended `$'…'` text.
  `ids=` are D2's labels so a failure names its row.
- [x] 1.2 Platform-scope the rows exactly as measured (D2):
  - **POSIX only**, `xfail(strict=True, reason="a-quote-can-spell-a-slash §2")`: G1–G5, G7–G10, D1
    (they flip from allow to deny). G6 is refused today on POSIX too but for a false reason, so mark
    only its **reason** assertion xfail on POSIX.
  - **Windows only**: every G row and D1 are refused today as *cannot be checked*, so mark their
    **reason** assertion (outside, resp. still cannot-be-checked for D1) xfail on Windows. **I1**
    flips deny→allow on Windows, so mark its answer xfail on Windows. **N1** flips allow→deny on
    Windows (mark its answer xfail on Windows); on POSIX N1 is allowed today and after (no mark).
  - **N2 (digitless `\x`, R2 finding 1):** POSIX allow today and after (backslash is not a
    separator; filename written inside) — no mark. Windows: today the reader refuses it *cannot be
    checked* (`$..\x` has a `$` and a `\`); after the fix it refuses it *outside* (`..\x` is a
    traversal). It is **refused on Windows today and after**, so its *answer* needs no mark on
    Windows; mark only its **reason** assertion xfail on Windows (the reason improves from
    *cannot be checked* to *outside*). A decoder that drops the backslash would flip the Windows
    answer to allow — that is what §4.6's mutation must catch.
  - **N3 (overrange `\U`, R2/R3 — reshaped by R3 finding 1):** measured today — **Windows deny**
    *cannot be checked* (`$\Uffffffffx` holds a `$` and a `\`), **POSIX allow**. After the R3 fix,
    `\U` above 0xFF keeps its backslash literal, so N3 stays **Windows deny** (reason improving to
    *outside*) and **POSIX allow** (unchanged). It does **not** flip on either platform. So mark
    only its **reason** assertion xfail on **Windows** (cannot-be-checked → outside); no answer mark
    anywhere. *(R2's plan flipped N3 deny→allow on Windows; that was wrong — see design finding 1.)*
  - **N4 (`\u`/`\U` above 0xFF, R3 finding 1):** POSIX allow today and after (backslash not a
    separator; filename `..` + U+0100 written inside) — no mark. Windows: today refused *cannot be
    checked* (`$..` + `\` + `u0100`); after the fix refused *outside* (`..` then `\`-separator then
    `u0100`). **Refused on Windows today and after**, so mark only its **reason** assertion xfail on
    Windows. A decoder that decodes it to one character would flip the Windows answer to allow —
    §4.7's mutation must catch that.
  - **N5 (`\c` before the closing quote, R3 finding 2):** POSIX allow today and after (name `..\c`
    inside) — no mark. Windows: today refused *cannot be checked* (`$..` + `\` + `c`); after the fix
    refused *outside* (`..\c`, `\`-separator). **Refused on Windows today and after**, so mark only
    its **reason** assertion xfail on Windows. A decoder that consumes the closing quote as `\c`'s
    control target would flip the Windows answer to allow — §4.8's mutation must catch that.
  - **Unmarked on both**: L1 (allow POSIX / deny Win, unchanged), OK1, OK2, and I1 on POSIX
    (allowed today and after).
  Verify every mark on both platforms before §2: run the file on Windows (`py -3.11`) and under WSL
  Ubuntu (`python3 -p posix_stubs`, per `testbed/scratch/night0912/posix_stubs.py`). Record which
  assertion each row fails. **Any failure not explained by a mark means the table is wrong, not the
  code** — re-measure with `testbed/scratch/r1f332/reader_forms.py` and record the difference.

  **Done 2026-09-13 night, and two marks above were wrong against the measurement.** D2's table is
  right; this list's prose disagreed with it twice. **N1** on Windows is refused *today* (*cannot
  be checked*, like every other row with a `$` and a `\`), so it takes a **reason** mark there, not
  an answer mark — it does not flip allow→deny. **D1** on Windows is *cannot be checked* today and
  after, so it takes **no** mark there; the reason mark listed would have been a strict XPASS. As
  pinned, each mark is `xfail(strict=True, raises=…)` naming the one assertion that moves
  (`_WrongAnswerError` or `_WrongReasonError`), so a row failing the *other* assertion is a real
  failure, not an XFAIL. Measured (`testbed/scratch/night0913/s1_measure.py`, `--runxfail`):
  Windows — G1–G10, N1–N5 fail their reason, I1 its answer; D1, L1, OK1, OK2 pass (16 xfailed,
  4 passed). WSL — G1–G5, G7–G10, D1 fail their answer, G6 its reason; I1, L1, N1–N5, OK1, OK2
  pass (11 xfailed, 9 passed). With R3's reference decoder patched in
  (`testbed/scratch/night0913/r3_lex_plugin.py`) all 20 rows pass on both platforms and exactly
  the marked rows XPASS; with R1's, Windows fails N2–N5, and with R2's, N3–N5.
- [x] 1.3 Commit §1 alone, green. From this commit, a decode that flips a row before §2 fails CI.
- [ ] 1.4 **New (Round 4, 2026-09-15) — corrects a gap in 1.2's committed pinning and pins the seven
      new rows Round 4 added.** Not optional: without this, §2 landing the Round-4 decoder makes N3
      XPASS (a strict failure) rather than flip cleanly, and P1–P7 have no pinning to hold them at
      all.
      - **N3's Windows mark is wrong as committed.** 1.2 marked only N3's *reason* assertion xfail
        on Windows, because at the time the Round-3 decoder was believed to keep N3 denied (an
        accepted over-refusal). Round 4 found that belief was the bug: the corrected decoder decodes
        `\U`≥0x80000000 to nothing, and N3 **answers allow on Windows** once §2 lands (design.md,
        D2's revised N3 row). Add `xfail(strict=True)` to N3's Windows **answer** assertion too (not
        only its reason), matching the pattern already used for I1 and N1. Until this lands, §2
        cannot be committed clean — N3 would XPASS its reason mark alone while still failing its
        answer, which is a real, uncaught mismatch, not a false alarm.
      - **Pin P1–P7** (design.md D2) the same way 1.1/1.2 pinned G/N: add each to the parametrized
        table, `ids=` its label. **Measure each row's *today* (unmodified lexer) answer and reason
        first, against the real current `_decide`, before writing any mark** — Round 4's own first
        pass at this instruction guessed several of these wrong (design.md's rows record the
        correction; use those values as a start, but re-measure rather than transcribe, the same
        way 1.2's own "Done" note verified itself against real runs). What design.md's corrected
        rows say should move:
        - **P1–P4:** today, **deny, unchecked, both platforms** (the raw pre-decode word always
          carries a real `/` and a `$`, tripping rule 3 regardless of platform). After, **deny,
          outside, both platforms** — the answer does not flip; only the *reason* moves
          (unchecked → outside), once the decoded word no longer contains a `$` and rule 5/6 takes
          over from rule 3. Mark only the reason assertion xfail, on both platforms, for each row.
        - **P5 (three commands, digitless `\x`/`\u`, unrecognized `\q`):** today, **deny,
          unchecked, both platforms.** After: **POSIX — deny, outside** (reason-only mark, same
          pattern as P1–P4: bash's real POSIX rendering is one component, genuinely outside).
          **Windows — allow, inside**: mark the **answer** assertion xfail on Windows for all three
          commands (bash's real Windows rendering, backslash-as-separator, is two components that
          the same two `..` exactly absorb — this is a real deny→allow flip, not a reason
          improvement, and must not be marked as reason-only).
        - **P6:** today, **POSIX allow** (rule 4 — the raw, undecoded word has no real `/` at all;
          `\x2f` is unprocessed literal text before the fix lands), **Windows deny, unchecked**
          (the raw word's literal `\` counts as a separator there, and the leading `$$` trips rule
          3). After: **deny, unchecked, both platforms** (the lexer's `$'` detection fires at the
          *second* `$`, decoding to a real `/` and leaving the first `$` glued in front). Mark the
          **answer** assertion xfail on **POSIX only** (allow→deny); no mark needed on Windows
          (already deny, same reason, both before and after).
        - **P7:** today, **POSIX allow** (rule 4, no real separator in the raw word), **Windows
          deny, unchecked** (raw word's literal `\` plus leading `$`). After: **allow, both
          platforms** — the decoded word contains an actual NUL byte but **no separator
          character**, so rule 4 returns before the NUL is ever checked. Mark the **answer**
          assertion xfail on **Windows only** (deny→allow; POSIX stays allow→allow, no mark). **Do
          not treat this as a row that should stay denied** — design.md's corrected P7 explains why
          the flip is real but does not meaningfully widen exposure (F375's unescaped route was
          already open). Cite F375 in a comment beside this row's assertion so a future reader does
          not mistake the flip for an unnoticed regression.
      - **Fix N3's asserted value, not only its mark.** The committed test's N3 param currently
        asserts the *old* after-value (deny, outside) with only a reason xfail on Windows. Change
        the asserted Windows answer itself to **allow** (matching design.md's corrected N3 row),
        and add `xfail(strict=True)` to that answer assertion (today's unmodified lexer still
        answers deny there). Leaving the old assertion in place and only adding a mark would pin
        the wrong target — the mark would apply to an assertion that already says the wrong thing.
      - Verify on both platforms exactly as 1.2's "Done" note did (`--runxfail`, record pass/xfail
        counts), and update that note's numbers in this file once done.
      - Commit alone, green, before §2 resumes.
- [ ] 1.5 **New (Round 6, corrected by Round 7, Round 8 and Round 9, 2026-09-15) — pins Q1–Q4, S1,
      S2, T1, T2, S3 (design.md D2/D6), the rule-5/6 fallthrough class and its fix's own
      regression-guards.** Add all nine to the same parametrized table, `ids=` their labels.
      **Measure each row's *today* answer against the real, unmodified `_decide` first**, same
      discipline as 1.4 — every round that checked this task so far found marks it previously
      specified were wrong against a real measurement; re-measure rather than transcribe, including
      the values below. **This task alone does not prove the fix is safe** — task 2.2c's
      verification gate (running the *existing* `hub/tests/test_permission_approver.py` in full)
      is what catches a too-permissive candidate; these nine rows only prove the intended cases
      work, not that nothing else broke.
      - **Q1, Q2, Q4:** today, **POSIX allow** (rule 4, no real `/` in the raw word), **Windows
        deny, unchecked** (the raw word carries a literal `\` and a leading `$`, rule 3). After
        2.2c lands: **allow, both platforms**. Mark the **Windows** answer assertion
        `xfail(strict=True)` (deny-unchecked → allow). **Do not mark the POSIX answer** — POSIX is
        already `allow` today and stays `allow` after, so a POSIX `xfail` on this assertion would
        XPASS immediately at §1 commit time. Their protection against a future too-narrow fix comes
        from §4.9's mutations, not from a POSIX pin.
      - **Q3 (Round 9: example replaced):** use `$'sub\u2212\x2fhello.py'` (U+2212, MINUS SIGN),
        **not** the original `$'sub\u2000\x2fhello.py'` (U+2000, EN QUAD) — `_WORD_SPLIT_RE`
        (`hub/hub/mcp_server.py:968`) is a Unicode-aware `\s` pattern and splits a word at U+2000
        before `_judge_word` ever runs, so the original example never reached rule 5/6 at all and
        cannot demonstrate this class of fix. Same today/after values and marks as Q1/Q2/Q4 above.
      - **Q4:** today, **POSIX allow, Windows deny, unchecked** (its raw pre-decode word also
        carries a literal `\` and `$`, refused today exactly like every other pre-decode ANSI-C
        row). After: **allow, both platforms** — this flip happens once §2's decoder lands on its
        own, independent of 2.2c, because é is already inside the *old*, unfixed `\w` class. Mark
        the **Windows** answer assertion `xfail(strict=True)`, same as Q1–Q3, but do not treat this
        as evidence for 2.2c specifically — §4.9's mutations must leave Q4 unmoved.
      - **S1 (leading-position case):** today, **POSIX allow, Windows deny, unchecked** — same
        reasoning as Q1. After 2.2c's **corrected** regex (leading class broadened): **allow, both
        platforms**. **Today's POSIX answer for S1 is already `allow`, and the shipped, final
        regex also answers `allow`, so — exactly like Q1–Q3 — the POSIX answer needs no mark.**
        (An earlier version of this task asked for a
        POSIX mark here on the theory that an *intermediate*, interior-only draft of the fix would
        wrongly deny it; that intermediate state is never a real, committed tree — no task commits
        the interior-only draft standalone — so the mark would XPASS just like Q1–Q3's would have.
        S1's own protection against a future interior-only-broadened regression belongs to §4.9's
        leading-only-revert mutation, not to an xfail here.) Mark only the **Windows** answer
        assertion `xfail(strict=True)` (deny-unchecked → allow).
      - **S2 (glue-form regression guard):** today and after, **deny, outside, both platforms,
        unchanged** — no mark. If this ever starts passing with a *different* reason or flips to
        `allow`, the leading-class broadening went too far.
      - **T1 (directly-typed interior widening — `cat x!/etc/passwd`, not the original
        `x@/etc/passwd`; see design.md's note on why `@` was replaced):** today, **deny, outside,
        both platforms** (unaffected by any decoder work — no `$'…'` in it at all). After 2.2c
        lands: **allow, both platforms** — mark **both platforms'** answer assertions
        `xfail(strict=True)`. Depends on the interior broadening only (its leading character `x`
        was always inside the old leading class) — see §4.9's mutation split.
      - **T2 (directly-typed leading widening — `cat !/etc/passwd`, not the original
        `*/etc/passwd`; Round 9 found `*` needed excluding everywhere too, X5's glob concern):**
        today, **deny, outside, both platforms**. After 2.2c: **allow, both platforms** — mark
        both platforms' answer assertions `xfail(strict=True)`. Depends on the leading broadening
        only (its first segment
        is empty, so the interior classes are never exercised) — the complement of T1; see §4.9.
      - **S3 (curl `name@filename` convention stays protected):** today and after, **deny, outside,
        both platforms, unchanged** — no mark. This is the row that would have moved to `allow`
        under the pre-Round-8 version of 2.2c (leading-only `@` exclusion) — see design.md D6's
        correction. If this row ever starts passing with a different reason or flips to `allow`,
        the `@` exclusion narrowed back to leading-only and the curl exfiltration path (design.md
        S3's row) is open again.
      - Commit all nine rows' marks alongside 2.2c — none of them depends on an intermediate state
        that is ever separately committed, so there is nothing here to check twice.

## 2. The decode

> **STOPPED 2026-09-13 night (f332-s2). §2 as written opens a Windows escape. Nothing of §2 is
> committed; the tree is §1's (`1ebff15`).** The invariant in design.md ("safe iff it never emits
> *fewer* separators than bash") is half of the truth. On Windows an *extra* separator is just as
> unsafe, because it adds a directory level for a later `..` to climb out of. Keeping the backslash
> is only safe where bash keeps it too. Measured with 2.2's rules built into `_lex`, against real
> Git Bash 5.2.37 (`testbed/scratch/night0913/s2/depth_probe2.py`, workspace `a\work`):
> - `mkdir A` (allowed), then `echo hi > $'A\Uffffffff/../../esc2.txt'` — **allowed**, and bash
>   wrote `a\esc2.txt`, **outside**. bash emits *nothing* for `\U` ≥ 0x80000000 in every locale, so
>   the kept `\Uffffffff` is a phantom directory level. Not locale-dependent.
> - Under `LANG=C.UTF-8` or `en_US.UTF-8`, `mkdir -p $'A\u0100'`, then
>   `echo hi > $'A\u0100/../../x'` — **allowed**, and bash wrote `a\x`, **outside**. UTF-8 bash
>   encodes `\u0100` as `c4 80`, with no backslash.
> - At `1ebff15` (today's lexer) both are **refused**, so §2 would be a regression, Windows only (on
>   POSIX a backslash is not a separator, so keeping and decoding have the same structure).
>
> Git Bash's rendering, measured for every locale (`render_probe.sh` beside it): `\u0100`…`\U7fffffff`
> is kept literal (backslash included) under C or an unset `LANG`, and encoded under C.UTF-8 and
> en_US.UTF-8; `\U80000000` and `\Uffffffff` are empty in all four; `\u00ff` is `ff` or `c3 bf`;
> `\cA`, `\c/` and `\c` + é are `01`, `0f` and `03 a9` in all four. No single rendering of a `\u`
> above 0xFF is safe in every locale.
>
> **Round 4, 2026-09-15, confirmed and completed the candidate correction — see design.md's
> replaced invariant (D1) and "What round 4 changed".** It is no longer a sketch: judge both
> readings of a codepoint escape between 0x100 and 0x7FFFFFFF, refusing if either would escape;
> render `\U` ≥ 0x80000000 as nothing (not kept literal — Round 4 found the R3 "keep it, call it
> a safe over-refusal" answer was itself the phantom-component bug, not a safe trade); decode
> `\cX` from X's first UTF-8 byte for **any** real body character, not only ASCII (restricting to
> ASCII was tried and re-broken, same mechanism). Two things Round 4 added that 2.2 below now
> carries: the UTF-8 reading needs its own `chr()`-overflow guard (a fixed placeholder above
> U+10FFFF, not R2's dropped-empty-string answer, which loses bash's kept backslash where one is
> real); and the reading flag must reach `_read_command`'s own recursive call for a nested
> `$(...)` substitution, or it silently narrows to one reading inside one. This changes N3's
> Windows answer (deny→allow) and adds D2 rows P1–P7 (task 1.4 pins them). The stopped
> implementation from the night is kept, unapplied and now superseded, at
> `testbed/scratch/night0913/s2/s2-stopped.patch` — do not build from it as written; it predates
> the dual-reading rule and the \U≥0x80000000 fix.

- [ ] 2.1 In `hub/hub/mcp_server.py` `_lex`, add a branch: **in the bash dialect, when no quote is
  open**, `$` immediately followed by `'` opens an ANSI-C string. Consume the `$` and the `'`,
  decode until the closing `'` (or end of text — stay total), consume the closing `'`, and append
  the decoded characters to the current word (`started = True`). A produced literal `$` is appended
  as `_LITERAL_DOLLAR`, exactly as a `$` inside ordinary single quotes already is. The branch sits
  **after** the `quote == "'"` block and **before** the generic `char in "'\""` open, so `quote is
  None` is guaranteed and the opening `'` is not consumed twice.
- [ ] 2.1b **New (Round 4, simplified by Round 5).** Thread a `reading` argument (`"c"` or
  `"utf8"`) through `_lex` and `_read_command`, **including `_read_command`'s own recursive call
  for a substitution's command text** (`_substitution`'s caller) — a reading that stops at the top
  level judges a nested `$(...)`'s ANSI-C content in one reading only, silently narrowing the dual
  check design.md's D1 requires. **`_decide` always calls `_read_command` twice per dialect pass,
  once per reading, unconditionally** — Round 4's draft of this task proposed having the decoder
  helper (2.2) report back whether it actually used the dual-reading branch, so the second pass
  could be skipped when nothing in the command needed it. Round 5: that report has nowhere safe to
  live. `_lex` returns `Tuple[List[str], List[str]]` and `_read_command` returns
  `Optional[Dict[str, Any]]` — neither has room for a third value without changing every caller,
  and a module-level flag would make `_decide` read mutable state set by a previous call, which
  breaks its own documented "pure and total" contract (`_decide`'s docstring). The unconditional
  two-pass cost is small (one extra lex of the same, already-short command text) and keeps the
  function pure. Refuse if either reading's `_read_command` call returns a refusal.
- [ ] 2.2 Add the decoder helper beside `_lex`: given the text, the index of a `\`, and the
  `reading` (2.1b), return the decoded string and the next index. It must honour **the replaced
  invariant** (design D1, Round 4): an escape may be **decoded to a character** (removing its
  backslash, contributing no separate path component) only when that character's contribution to
  the word's component structure is determined **for the reading in effect**; **in every other
  case keep the backslash literal**, because bash may keep it and on Windows a backslash is a
  path separator. Concretely:
  - simple escapes decode: `\a \b \e \E \f \n \r \t \v \\ \' \" \?`;
  - `\NNN` octal (1–3 digits, value mod 256 — `\457` is `/`) and `\xHH` hex (1–2 digits) decode via
    `chr(value)` — they are *byte* escapes, always ≤ 0xFF, locale-independent, same in both
    readings;
  - `\uHHHH` (1–4 digits) / `\UHHHHHHHH` (1–8 digits) **at or below 0xFF**: decode via `chr(value)`
    in both readings (locale-independent);
  - `\uHHHH`/`\UHHHHHHHH` **from 0x100 to 0x7FFFFFFF (Round 4 — replaces the R3 "always keep
    literal" rule)**: in the `"c"` reading, keep the backslash and the escape text literal
    (return `"\\" + letter + hexdigits.upper()` — **Round 6, finding 3**: bash uppercases the hex
    digits of a kept-literal escape (`$'..\u07ff'` renders `..\u07FF`, measured, Git Bash
    `LC_ALL=C`); echoing the agent's own typed casing is not byte-for-byte what bash renders,
    which D1 says matters. No verdict changes — case does not affect component count, separator
    identity, or `os.path.normcase` comparison — but implement the uppercase form to actually meet
    D1's "exactly" standard); in the `"utf8"` reading, decode via `chr(value)`
    **guarded**: for `value > 0x10FFFF` (only reachable via `\U`), emit **one fixed ASCII letter**
    (e.g. `"z"`, chosen once, never derived from the input) instead of calling `chr()` at all —
    **not** an arbitrary "non-separator" character (design.md D5, Round 5): the placeholder must
    fall inside `_PLAIN_RELATIVE_RE`'s `\w` class or the word can fall through from rule 5 to
    rule 6, changing the refusal text a pinned row asserts even though the verdict is unchanged.
    Do **not** return `""` (R2's old guard) — an empty string drops the kept backslash the `"c"`
    reading needs to stay faithful, and the two readings must disagree only in how they render
    this escape, not in whether the rest of the word around it is intact. (Bash itself does render
    real bytes above 0x10FFFF under a UTF-8 locale via its own legacy encoding — design.md D5
    explains why a placeholder is still safe without reproducing them exactly: every byte such an
    encoding can produce is 0x80 or above, so it can never itself be a separator.);
  - `\uHHHH`/`\UHHHHHHHH` **at or above 0x80000000 (Round 4 — replaces the R3 "keep literal,
    accepted over-refusal" answer)**: decode to **nothing**, in both readings — this is
    locale-independent (bash emits nothing here in every locale, measured at the boundary
    `\U7fffffff` kept / `\U80000000` nothing), so it needs no reading distinction at all;
  - `\cX` control (`\c@` is a NUL) decodes **only when `X` is a real body character, of any byte
    length** — do not restrict to ASCII (Round 4: restricting it re-creates a phantom component
    the same way a restricted `\u`/`\U` rule does). The control byte is X's *first* UTF-8 byte
    `& 0x1F`; X's remaining bytes, if any, are kept literal after it. A `\c` immediately before
    the closing quote (or at end of text) **keeps its backslash literal** and the decode **MUST
    NOT consume the closing quote** as `X`;
  - unrecognized escape keeps its backslash; a trailing `\` is literal;
  - a **digitless** `\x`/`\u`/`\U` (no hex digit follows) keeps its backslash.
  It MUST NOT raise on any input, **in either reading**. The `"c"` reading's `chr()` calls are
  bounded exactly as R3 derived (only for values ≤ 0xFF, so U+10FFFF cannot be exceeded); the
  `"utf8"` reading's `chr()` calls are bounded by the placeholder guard above, added by Round 4 —
  do not assume R3's "no guard needed" conclusion still holds for this reading, it does not.
  **Rules Round 4 changed from R1/R2/R3 — implement the corrected version, not any prototype:**
  - **Digitless `\x`/`\u`/`\U` keeps its backslash** (R2 finding 1, unchanged): R1 returns just
    the letter, dropping a Windows separator and allowing an escape refused today (row N2).
  - **`\u`/`\U` from 0x100 to 0x7FFFFFFF gets a dual reading, not an unconditional keep-literal**
    (Round 4 replaces R3 finding 1): R1 and R2 decode it to one character unconditionally; R3
    always keeps it literal; both are wrong inside a longer path with a real component before the
    escape and enough `..` after it (design.md P1–P3) — see 2.1b.
  - **`\u`/`\U` at or above 0x80000000 decodes to nothing, not keep-literal** (Round 4 — this
    range was inside R3 finding 1's scope but R3's answer for it was itself the bug; see D2 row
    N3, design.md P1).
  - **`\c` before the closing quote keeps its backslash** (R3 finding 2, unchanged): R1 and R2
    read the closing `'` as `\c`'s control target, over-run the string, and allow `$'..\c'` on
    Windows (row N5).
  - **`\cX` is never restricted to an ASCII `X`** (Round 4 — the night's build briefly did this
    and reopened the phantom-component class in a new shape; design.md P4 pins the non-ASCII
    case).
  - **Never consume the closing quote** for any escape while decoding the body.
  `testbed/scratch/r1f332/prototype.py`, `testbed/scratch/r2f332/fix_probe.py` and
  `testbed/scratch/r3f332/three_decoders.py` are references **each with defects still in them**
  (R1: all four rules above; R2: the R3-and-Round-4 rules; R3: the two Round-4 rules) — none of
  them implements the dual reading or the ≥0x80000000 fix. `%TEMP%/f332/proto.py` (Round 4) is
  the first reference that does, but it is scratch, not the implementation. The implementation is
  held to D2's table — which now pins N2–N5 and P1–P7 — not to any prototype.
- [ ] 2.2c **New (Round 6, corrected by Round 7, Round 8 and Round 9, 2026-09-15) — this is the
  one place §2.3's "leave everything after the lexer unchanged" does not hold, and the one task
  whose "done" bar is different from every other task in this file: it is not done until the
  *existing* test file passes, not only the new rows.** Broaden `_PLAIN_RELATIVE_RE`
  (`hub/hub/mcp_server.py:966`) from its current `\w`-allowlisted character classes to a denylist.
  See design.md D6 for the full derivation and the D2 rows (Q1–Q4, S1, S2, T1, T2, S3) it fixes
  and pins — **read D6's own three-round correction history before implementing**: broadening only
  the interior classes left a leading-position gap (Round 7); excluding `@` from the leading
  position only left curl's `name@filename` convention open from any interior position (Round 8);
  and **the whole "enumerate what's dangerous" approach, checked only against constructed cases,
  missed that the reader's own already-shipped test suite depends on the *narrow* regex to keep
  five pinned rows safe — two of them real escapes, not documentation gaps (Round 9).** This is
  the three-times-corrected pattern:
  ```python
  _PLAIN_RELATIVE_EVERYWHERE = "\"'`{}[]()<>|;&@*?%\x00"
  _PLAIN_RELATIVE_RE = re.compile(
      rf"^[^{re.escape(_SEPARATORS)}{re.escape(_PLAIN_RELATIVE_EVERYWHERE)}:\-]"
      rf"[^{re.escape(_SEPARATORS)}{re.escape(_PLAIN_RELATIVE_EVERYWHERE)}:]*"
      rf"(?:[{re.escape(_SEPARATORS)}][^{re.escape(_SEPARATORS)}{re.escape(_PLAIN_RELATIVE_EVERYWHERE)}]*)+$"
  )
  ```
  `_PLAIN_RELATIVE_EVERYWHERE` is every character in `_WORD_TRIM` (`hub/hub/mcp_server.py:972` —
  defined *after* this regex in the file, so it cannot be referenced directly; the set is restated
  literally) except `:` (scoped separately, unchanged), plus `@` (Round 8, curl), `*` and `?`
  (X5's pre-existing, deliberate glob-character exclusion — `[` and `]` are already in
  `_WORD_TRIM`), `%` (tied to `_CMD_VARIABLE_RE`'s own `%NAME%` expansion syntax a few lines below
  this regex), and a NUL byte (row `X8`). Every one of these is excluded from **every** position —
  leading, first segment, every later segment — because none of the reasons behind any of them is
  specific to where in the word the character sits. `:` stays first-segment-only and `-` stays
  leading-only, both unchanged from every earlier version — see design.md D6.
  **Verification gate — this is not optional and is separate from §6.2's later, whole-suite run:**
  before considering this task done, patch the candidate regex into a real checkout of
  `hub/hub/mcp_server.py` and run `hub/tests/test_permission_approver.py` **in full, unfiltered**
  (`py -3.11 -m pytest tests/test_permission_approver.py -q` from `hub/`). It must return exactly
  the baseline count the unmodified tree returns (currently `182 passed, 1 skipped, 16 xfailed` —
  re-measure this exact count against the tree at implementation time, since §1's pinning adds to
  it; the point is *zero regressions among rows this task did not intend to touch*, not a specific
  number). **Rows `E11`, `J5`, `X5`, `X8` and `H11` are the ones a too-permissive candidate breaks
  first** — `E11` and `J5` are real escapes if they flip (an inner-shell quote-join traversal and
  an absolute-path write, respectively; see design.md D6's account of each), not merely wrong
  reasons. If any of them move, the candidate regex is still too permissive — go back to D6's
  derivation and find what character class it omits; do not special-case these rows out of the
  suite run to make it pass. This is why 2.2c's regex is derived from `_WORD_TRIM` and the file's
  own other special-character constants (above), rather than from constructing new adversarial
  cases round after round — that approach found a new gap on average once per round today, and
  running the existing suite is what actually catches the class of thing three rounds of
  construction missed.
  **Refusal-text fidelity: this task changes the *wording* of two rows already pinned by task
  1.4, without changing their verdict.** P4 and P5(POSIX) both carry a non-`\w`/non-ASCII decoded
  character and, before this task, are denied via rule 6's backstop (whose refusal quotes only the
  matched absolute-looking tail, e.g. `'/../../x'`); once this task lands, rule 5 resolves them
  directly and the refusal quotes the *whole word* instead (e.g. a form like `A` followed by the
  `\c`-decoded control byte and its UTF-8 continuation byte, then `/../../x`, for P4). Both stay
  `deny, outside` — task 1.4's *answer* assertions for P4 and P5(POSIX) are unaffected — but if
  1.4's *reason* assertions were written to match a substring of the old rule-6 quoting, re-check
  them against the actual quoted text once 2.2c lands, before relying on them as passing.
- [ ] 2.3 Leave everything after the lexer unchanged, **except 2.2c above**: the six rules'
  *decisions*, `_is_own_hub`, the refusal wordings, the reason bound are untouched. Confirm **no
  new reason string** is introduced (`grep` the refusal constants; the diff is `_lex`, a helper,
  and `_PLAIN_RELATIVE_RE`).
- [ ] 2.4 Add one sentence to the reader's block comment (above `_SEPARATORS`): a shell may carry a
  quote form that *decodes* escapes into characters, not only removes them, so the word judged is
  what the shell produces.
- [ ] 2.5 Remove every §1 `xfail` marker. The whole table is green on both platforms with no marker
  left; `grep -n "a-quote-can-spell-a-slash" hub/tests/test_permission_approver.py` shows no xfail.
- [ ] 2.6 Commit §2, green.

## 3. The wire shape

- [ ] 3.1 Beside `_call_tool_over_stdio`, add one case through a **real spawn** of `mcp_server.py`
  with `AW_WORKSPACE_DIR` and `HUB_URL` in the child's environment: `echo hi > $'..\x2fstray.txt'`
  answers `behavior: deny` on POSIX with a message beginning `Denied: '../stray.txt' is outside`.
  On Windows the same command already denies (as *cannot be checked* before, *outside* after), so
  assert the deny and, after §2, the *outside* reason. The result carries **no** `structuredContent`.

## 4. Mutation checks — the decode must be load-bearing

Apply each mutation alone (UTF-8 in and out; assert the edit matched exactly once), run the whole
`test_permission_approver.py`, record which named row failed, then restore with `git checkout`.

- [ ] 4.1 Remove the ANSI-C branch from `_lex` (revert to treating `$'` as `$` + ordinary single
  quote). **On POSIX, G1–G5, G7–G10 and D1 must fail.** On Windows their reason assertion fails.
- [ ] 4.2 Decode the ANSI-C string but do **not** map a produced `$` to `_LITERAL_DOLLAR`. **D1 must
  fail** (it becomes a trusted reference and is allowed).
- [ ] 4.3 Fire the ANSI-C branch regardless of quote state (drop the `quote is None` guard). A row
  with `$'…'` inside `"…"` must change answer. **Use a row that ESCAPES the workspace, not
  `echo "x$'..\x2fy'"`** — the pre-approval review measured that `x$'..\x2fy'` decodes to `x../y`,
  which resolves *inside* the workspace, so on POSIX it is `allow` both with and without the guard
  (no flip → the mutation leaves the table green, a hole), and on Windows its unmutated answer is
  `deny_unchecked` (the literal `$` and `\` trip rule 3), not `allow`. Use
  `echo "$'..\x2f..\x2f..\x2fout'"` (three traversals): **on POSIX** the unmutated word `$'..\…'`
  has no `/` and is **allowed**, and the mutation decodes it to `../../../out` and **refuses it
  outside** — a clean allow→deny flip. Assert this row on **POSIX** (WSL / CI Linux), where
  "allowed unmutated" holds; on Windows the same row is `deny_unchecked` unmutated and `deny_outside`
  mutated (still a flip, but not the "allowed unmutated" shape). Measured
  `testbed/scratch/opusf332/check_43.py`.
- [ ] 4.4 Decode only `\x` (drop octal, `\u`, `\U`). **On POSIX, G2, G3 and G4 must fail** (the
  kept-literal `\057`/`/`/`\U…` has no `/`, so the word is judged inside and the row flips
  deny→allow). **On Windows they do NOT flip** — the kept backslash is itself a separator there, so
  `..\057x` still resolves outside and stays `deny_outside`. So verify §4.4 under **WSL/POSIX** (or
  with `os.sep` forced to `/`); the night runs on Windows, where this mutation is silently harmless.
  Measured `testbed/scratch/opusf332/decoder_check.py` (R3 vs the drop-octal case).
- [ ] 4.5 Apply the decode in the PowerShell dialect too. A PowerShell row with `$'…'` (which
  PowerShell does not decode) must change answer — pin `_decide("PowerShell", {"command": ...})` on
  a `$'…'` traversal as unchanged from today, and assert it fails under this mutation. Use an
  **escaping** traversal (e.g. `$'..\x2f..\x2f..\x2fout'`) and verify on **POSIX** for the same
  reason as §4.3/§4.4: on Windows the unmutated PowerShell word already denies (its literal `$`/`\`
  trip rule 3), so the mutation's flip is observable only if the pin asserts the full reason;
  on POSIX it is a clean allow→deny_outside flip.
- [ ] 4.6 **Drop the backslash on a digitless `\x`/`\u`/`\U`** (R1's prototype behavior — return
  the letter, not `"\\" + letter`). **On Windows, N2 must fail** (`$'..\x'` flips from deny to
  allow — the escape R2 finding 1 caught). On POSIX N2 is allow either way, so run this mutation's
  assertion on Windows (or assert the Windows *reason* under WSL by forcing `os.sep`). A mutation
  that leaves N2 green means the backslash is not actually load-bearing.
- [ ] 4.7 **Decode `\u`/`\U` above 0xFF via `chr()`** instead of applying the corrected rule
  (drop the `value <= 0xFF` branch, the >=0x80000000 decode-to-nothing case, and the dual
  reading; `chr(value)` for the whole range unconditionally — R1/R2's behaviour). Two named
  rows must break: **on Windows, N4 (`$'..` + `\u0100`) flips from deny to allow** (the escape
  R3 finding 1 caught, unaffected by Round 4/5), and **N3 (`$'\Uffffffffx'`) fails by
  raising** — `chr(0xffffffff)` raises `OverflowError`, so `_decide` errors instead of
  returning a decision. Assert N4's Windows answer is deny unmutated / allow mutated, and that
  `_decide` on N3 **returns a dict unmutated (Round 4/5: this is `allow`, not `deny` — see
  1.4's corrected N3 assertion) and raises mutated** (this pins totality, which no
  outcome-only assertion would catch). On POSIX N4 is allow either way, so run N4's assertion
  on Windows (or force `os.sep` under WSL).
- [ ] 4.8 **Consume the closing quote as `\c`'s control target** (drop the "keep `\c` literal when
  the next char is the closing quote" check, R1/R2's behaviour). **On Windows, N5 (`$'..\c'`) must
  flip from deny to allow** — the decoder reads the `'` as the control char, over-runs the string,
  and produces `..g` with no separator (R3 finding 2). On POSIX N5 is allow either way, so run its
  assertion on Windows (or force `os.sep`). A mutation that leaves N5 green means the closing-quote
  guard is not load-bearing.
- [ ] 4.9 **New (Round 6, corrected by Round 7, Round 8 and Round 9) — five mutations, because the
  fix broadens four independent things (the leading class, the general interior character set, the
  `@` exclusion specifically, and — Round 9 — the quote/glob/`%`/NUL exclusion specifically) and
  each needs its own proof, not one combined revert. This task's own rows are necessary but not
  sufficient — task 2.2c's gate (running the existing `hub/tests/test_permission_approver.py`
  against the real candidate regex) is the one that actually proved 4.9e is needed at all; do not
  treat passing 4.9a–4.9d as evidence the regex is complete.**
  - **4.9a — full revert** (restore the original `\w`-only pattern:
    `r"^[\w.+][\w.+\-]*(?:[sep][\w.+\-:]*)+$"`). **Q1, Q2, Q3, S1, T1 and T2 must each flip from
    allow to deny** (S1, T2 on the leading class reverting; Q1–Q3, T1 on the interior class
    reverting). **Q4, S2 and S3 must not move.**
  - **4.9b — leading-only revert** (restore the leading class to `[\w.+]`, leave the interior
    classes at their broadened, `@`-excluding form). **S1 and T2 must flip from allow to deny**
    (both depend on the leading class specifically: S1's exotic byte and T2's `*` are the word's
    first character). **Q1–Q3, T1, Q4, S2 and S3 must not move** — none of these depends on the
    leading class (Q1–Q3 and T1's exotic content is not in the leading position; T1's own leading
    character `x` was always inside `[\w.+]`). This is the mutation that isolates the leading
    broadening specifically; do not skip it in favor of 4.9a alone, or a regression that reverts
    only the leading class (leaving the interior fix intact) would pass 4.9a's own assertions on
    the untouched interior rows while still reopening S1/T2.
  - **4.9c — interior-only revert** (leave the leading class at its broadened form, restore the
    interior classes to the original `[\w.+\-]` / `[\w.+\-:]` allowlist — this drops the general
    interior broadening, and, incidentally, `@` along with it, since `@` was never in the original
    allowlist to begin with). **Q1, Q2, Q3 and T1 must flip from allow to deny.** **S3 does *not*
    flip under this mutation** — measure it: `name@/etc/passwd` still denies, because the original
    allowlist never matched `@` in the first place, so reverting *to* it removes nothing S3 was
    relying on. Do not list S3 under 4.9c's flips — a version of this task once did, wrongly (it
    conflated "the interior broadening in general" with "the `@` exclusion specifically", which
    this mutation does not isolate). **S1, T2, Q4, S2 and S3 must not move.**
  - **4.9d — the `@`-exclusion-only mutation, and the one that actually proves Round 8's fix**
    (leave the leading class and the rest of the interior broadening exactly as shipped; remove
    only `@` from the interior denylist, i.e. `[^{sep}:]` instead of `[^{sep}:@]` in both the
    first-segment and later-segment interior classes). **Only S3 must flip, from deny to allow** —
    measured: under this mutation `name@/etc/passwd` matches rule 5 and resolves to `allow`,
    reproducing exactly the exfiltration design.md's S3 row and Round 8 finding 4 describe.
    **Q1, Q2, Q3, T1, S1, T2, Q4 and S2 must not move** — none of them involves `@` at all, so
    dropping only the `@` exclusion leaves every one of them exactly as shipped. 4.9c's full
    interior revert is not a substitute for this mutation: it happens to leave S3 denied for an
    unrelated reason (the original allowlist's absence of `@`), so 4.9c alone would let a
    real regression — the interior denylist gaining `@` back while everything else about D6
    stays fixed — pass unnoticed. 4.9d is the only mutation that actually exercises the fix Round
    8 added.
  - **4.9e — the quote/glob/`%`/NUL-exclusion-only mutation (Round 9), and the one that proves
    this task's own biggest fix** (leave the leading class, the general interior broadening, and
    the `@` exclusion exactly as shipped; remove `_PLAIN_RELATIVE_EVERYWHERE`'s other members —
    the quote characters, `{}[]()<>`, `|;&`, `*?`, `%` and NUL — from every position, i.e. revert
    to exactly the Round-8 pattern this task's own history describes as broken). **The reader's
    own pre-existing, already-shipped rows `E11`, `J5`, `X5` and `X8`
    (`hub/tests/test_permission_approver.py`) must each flip from deny to allow under this
    mutation** — this is not a new row this change adds, it is proof that the fix, if shipped
    without the quote/glob/`%`/NUL exclusions, reopens rows that were never part of F332 at all.
    **Q1–Q4, S1, S2, T1, T2 and S3 must not move** — none of them involves a quote, glob, `%` or
    NUL character. If 4.9e's named rows do not flip, the mutation was not applied correctly (it
    should reproduce exactly the Round-9 measurement in design.md D6 — `182 passed` becomes
    `5 failed, 177 passed` under this exact mutation) — re-check the edit before concluding the
    fix is safe without this exclusion.
  A mutation that leaves its own named rows green means the broadening it is supposed to prove is
  not actually doing anything — check all five mutations' predicted outcomes above by actually
  running them; do not assume 4.9a's combined revert alone is sufficient evidence for any of the
  four narrower claims, and do not assume 4.9c substitutes for 4.9d or 4.9d substitutes for 4.9e.

## 5. Drive it — the reason a real operator reads (Windows), POSIX proven on CI

Every real agent turn binds `claude-haiku-4-5`. No job left enabled. The drive Hub runs on a port
chosen that night, fresh profile, started from `hub/` with uvicorn **from source**, no `.py` under
`hub/hub` or `src` newer than the process. Never 8000 or 8010.

- [ ] 5.1 **Pre-fix, first.** `git worktree add ../aw-ansic <sha>` at the commit **before** §2's.
  Start the drive Hub from that worktree, on a fresh git fixture project with `sub/hello.py`, one
  agent on the default posture (no override), Haiku. Ask it, with its **Bash** tool:
  1. `python sub/hello.py` — allowed.
  2. `echo hi > $'..\x2fstray.txt'` — on Windows this is **refused today** (as *cannot be checked*),
     so a Windows drive cannot show the escape writing out; record the refusal reason verbatim.
  Read `event_logs` and the transcript. Record every `permission_denied` row's `tool_name`. Remove
  the worktree afterwards. **The POSIX allow→deny flip is not drivable on Windows (D4); say so.**
- [ ] 5.2 **Fixed tree**, fresh project and agent. Ask it, with its Bash tool:
  - `echo hi > $'..\x2fstray.txt'` — refused as `'../stray.txt' is outside your workspace`, and no
    `stray.txt` appears in the fixture's parent (`.agentweave\worktrees\` for a git-project agent,
    per `a-url-is-not-a-path` §6.1).
  - `cat $'sub\x2fhello.py'` (I1) — **allowed**, prints the file. This is the over-refusal the fix
    corrects on Windows; confirm it reads the file rather than being refused.
  - `echo hi > $'..\x'` (N2, R2 finding 1) — **refused** as `'..\x' is outside your workspace` on
    Windows (a digitless `\x` keeps its backslash, and `\` is a separator there). Confirm the
    reason names `..\x` and no file appears in the worktrees directory. This is a Windows answer
    the fix changes — the reason improves from *cannot be checked* to *outside*.
  - `echo hi > $'\Uffffffffx'` (N3) — **allowed**, and the file `x` is created (real Git
    Bash writes it too — bash emits nothing for `\U`>=0x80000000 in every locale, so the real
    write matches the decoder's). Confirm the file appears and the decision **returns rather
    than the turn erroring** (totality holds via the >=0x80000000 decode-to-nothing rule, not a
    `chr()` guard — that value is never passed to `chr()` at all). *(Round 4/5, not R3: R1
    raised, R2 wrongly allowed for the wrong reason, R3 wrongly kept it denied believing the
    over-refusal was safe — that belief was itself the phantom-component bug (design.md, "What
    round 4 changed"). This is the one row in this drive where the fix's Windows answer is
    allow, not deny — do not mistake the file's appearance for a leak; it matches bash exactly.)*
  - `echo hi > $'..\u0100'` — the command being `echo hi > $'..` then the six literal characters
    backslash-u-0-1-0-0 then `'` (N4, R3 finding 1) — **refused** as outside on Windows (a `\u`
    above 0xFF keeps its backslash). Confirm the reason names the `..\u0100` form and no file
    appears. This is a Windows answer the fix changes (reason improves *cannot be checked* →
    *outside*); a decoder that decoded it to one character would have allowed it. Note the deny is a
    conservative over-refusal: on this machine's `C.UTF-8` Git Bash the command would write a file
    *inside* if allowed (pre-approval review, design.md).
  - `echo hi > $'..\c'` (N5, R3 finding 2) — **refused** as outside on Windows (`\c` before the
    closing quote keeps its backslash `..\c`, a traversal). Confirm the reason names `..\c` and no
    file appears. A decoder that consumed the closing quote would have allowed it.
  - `cat $'sub\xd7\x2fhello.py'` (Q1, Round 6, D6) — **allowed** (the approval decision, not the
    file read — the fixture has no file literally named `sub×/hello.py`, so the tool itself then
    reports "not found"). Confirm the *permission* decision is allow, not a refusal; a refusal here
    (`'/hello.py' is outside your workspace`) is exactly 2.2c's regression, still present.
  - `python sub/hello.py` — allowed. `curl "$HUB_URL/api/v1/agent-actions/tasks"` — allowed.
  Record every `permission_denied` row's reason and `tool_name`; confirm `event_logs` holds the
  refusal with the same reason. Stop the Hub, confirm every run bound `claude-haiku-4-5-*` and no
  job is enabled.

## 6. The gate

- [ ] 6.1 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
  --target-version py311`, `mypy src/`. Use `py -3.11 -m ...` (ruff/mypy are not on PATH in Git
  Bash; the failure is silent — see DEAD-ENDS). CI's path list, not a narrower one.
- [ ] 6.2 `py -3.11 -m pytest tests/ -q -p no:cacheprovider` from `hub/` (the whole Hub suite),
  never bare `python`. Run in the background or in chunks — the suite takes 15–47 min and exceeds
  the 600 s cap. Only re-run whole if something here could plausibly break it (it changes `_lex`, so
  run the whole suite once). Attribute any red by signature (F292 `database is locked`, F314 event
  loop) before blaming this change.
- [ ] 6.3 `openspec validate --strict a-quote-can-spell-a-slash` after every delta edit.
- [ ] 6.4 No migration, no API/schema/UI change. `git diff <base>.. -- hub/hub/migrations hub/hub/api
  hub/ui` is empty. The whole product diff is `hub/hub/mcp_server.py` and
  `hub/tests/test_permission_approver.py`.

## 7. Close it out

- [ ] 7.1 Set `F332` to `fixed <sha>` in `scripts/drive/FINDINGS.md`, naming §2 as the mechanism and
  quoting §5.2's evidence (the Windows reason and the corrected I1) plus the CI Linux XFAIL→PASS run
  ids for the POSIX flip (§1/§2, the F331-style evidence, per D4). Label it **tested on Linux, not
  driven on POSIX**; the drive is Windows.
- [ ] 7.2 `F299`, `F301` and `F322` stay **open**. Say so in the close-out commit so nobody reads
  this change as closing them.
- [ ] 7.3 `openspec validate --strict a-quote-can-spell-a-slash`, then archive with the
  `openspec-archive-change` skill. Before syncing, compare the MODIFIED block with the main
  `agent-run-sandboxing` requirement: every shipped scenario must survive byte-for-byte and only the
  one new paragraph and the one new scenario are added.

## 8. Verification only a human can do

- [ ] 8.1 **Is the refusal legible?** Open the agent's activity in the served UI and read §5.2's
  refusal of `$'..\x2fstray.txt'`. Does *"'../stray.txt' is outside your workspace"* tell you what
  happened? An agent can check the string is there; only you can say whether it reads. (This is the
  same judgement as `a-url-is-not-a-path` §7.1.)
- [ ] 8.2 **Is I1's allow acceptable?** `cat $'sub\x2fhello.py'` is now allowed on Windows. Confirm
  by eye that it is the same file as `cat sub/hello.py`, i.e. the change made an inside path
  reachable, not an escape. If you disagree that an ANSI-C-spelled inside path should be allowed,
  that is a product judgement — record it in `spec-queue/DECISIONS.md`.

## 9. User test guide

- [ ] 9.1 `test-guide.md` in this change is the operator's walkthrough. Keep it true to what
  shipped; correct it against the actual built behaviour. **Several changes are expected, not
  none** — most rows' Windows reason improves from *cannot be checked* to *outside* (design.md D2),
  and N3 changes more than its reason: it flips from refused to **allowed** on Windows (Round 4/5).
  Update `test-guide.md`'s own N3/N4 rows to match design.md's corrected D2 table before calling
  this task done — they were written against the pre-Round-4 design and are stale as of this spec.
