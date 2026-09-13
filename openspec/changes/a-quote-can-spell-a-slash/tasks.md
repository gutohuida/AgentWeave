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

- [ ] 1.1 In `hub/tests/test_permission_approver.py`, add D2's table as one parametrized test over
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
- [ ] 1.2 Platform-scope the rows exactly as measured (D2):
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
- [ ] 1.3 Commit §1 alone, green. From this commit, a decode that flips a row before §2 fails CI.

## 2. The decode

- [ ] 2.1 In `hub/hub/mcp_server.py` `_lex`, add a branch: **in the bash dialect, when no quote is
  open**, `$` immediately followed by `'` opens an ANSI-C string. Consume the `$` and the `'`,
  decode until the closing `'` (or end of text — stay total), consume the closing `'`, and append
  the decoded characters to the current word (`started = True`). A produced literal `$` is appended
  as `_LITERAL_DOLLAR`, exactly as a `$` inside ordinary single quotes already is. The branch sits
  **after** the `quote == "'"` block and **before** the generic `char in "'\""` open, so `quote is
  None` is guaranteed and the opening `'` is not consumed twice.
- [ ] 2.2 Add the decoder helper beside `_lex`: given the text and the index of a `\`, return the
  decoded string and the next index. It must honour **one invariant** (design D1): an escape may be
  **decoded to a character** (removing its backslash) only when that character is determined and
  **locale-independent**; **in every other case keep the backslash literal**, because bash may keep
  it and on Windows a backslash is a path separator. Concretely:
  - simple escapes decode: `\a \b \e \E \f \n \r \t \v \\ \' \" \?`;
  - `\NNN` octal (1–3 digits, value mod 256 — `\457` is `/`) and `\xHH` hex (1–2 digits) decode via
    `chr(value)` — they are *byte* escapes, always ≤ 0xFF, locale-independent;
  - `\uHHHH` (1–4 digits) / `\UHHHHHHHH` (1–8 digits): decode via `chr(value)` **only when
    `value <= 0xFF`**; **when `value > 0xFF`, keep the backslash and the escape text literal**
    (return e.g. `"\\" + letter + hexdigits`);
  - `\cX` control (`\c@` is a NUL) decodes **only when `X` is a real body character**; a `\c`
    immediately before the closing quote (or at end of text) **keeps its backslash literal** and the
    decode **MUST NOT consume the closing quote** as `X`;
  - unrecognized escape keeps its backslash; a trailing `\` is literal;
  - a **digitless** `\x`/`\u`/`\U` (no hex digit follows) keeps its backslash.
  It MUST NOT raise on any input. Note `chr()` is therefore called **only for values ≤ 0xFF**, so it
  cannot raise on a codepoint above U+10FFFF — no separate overflow guard is needed (this replaces
  R2's `if value > 0x10FFFF: return ""`, which was measured wrong on Windows — design D5/finding 1).
  **Four rules R1 and R2 got wrong — implement bash, not the prototype:**
  - **Digitless `\x`/`\u`/`\U` keeps its backslash** (R2 finding 1): R1 returns just the letter,
    dropping a Windows separator and allowing an escape refused today (row N2).
  - **`\u`/`\U` above 0xFF keeps its backslash** (R3 finding 1): R1 and R2 decode it to one
    character; the C locale Git Bash uses by default keeps it literal, so on Windows `$'..` + a `\u`
    above 0xFF is a traversal, and decoding it away allows an escape refused today (rows N3, N4).
  - **`\c` before the closing quote keeps its backslash** (R3 finding 2): R1 and R2 read the closing
    `'` as `\c`'s control target, over-run the string, and allow `$'..\c'` on Windows (row N5).
  - **Never consume the closing quote** for any escape while decoding the body.
  `testbed/scratch/r1f332/prototype.py` and `testbed/scratch/r2f332/fix_probe.py` are references
  **each with defects still in them** (R1: all four; R2: the two R3 findings);
  `testbed/scratch/r3f332/three_decoders.py` holds the corrected decoder beside them. The
  implementation is held to D2's table — which now pins N2, N3, N4, N5 — not to any prototype.
- [ ] 2.3 Leave everything after the lexer unchanged: the six rules, `_is_own_hub`, the refusal
  wordings, the reason bound. Confirm **no new reason string** is introduced (`grep` the refusal
  constants; the diff is `_lex` plus a helper).
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
- [ ] 4.7 **Decode `\u`/`\U` above 0xFF via `chr()`** instead of keeping the backslash literal
  (R1/R2's behaviour — drop the `value <= 0xFF` branch and `chr(value)` for the whole range). Two
  named rows must break: **on Windows, N4 (`$'..` + `\u0100`) flips from deny to allow** (the escape
  R3 finding 1 caught), and **N3 (`$'\Uffffffffx'`) fails by raising** — `chr(0xffffffff)` raises
  `OverflowError`, so `_decide` errors instead of returning a decision. Assert N4's Windows answer
  is deny unmutated / allow mutated, and that `_decide` on N3 **returns a dict unmutated and raises
  mutated** (this pins totality, which no outcome-only assertion would catch). On POSIX N4 is allow
  either way, so run N4's assertion on Windows (or force `os.sep` under WSL).
- [ ] 4.8 **Consume the closing quote as `\c`'s control target** (drop the "keep `\c` literal when
  the next char is the closing quote" check, R1/R2's behaviour). **On Windows, N5 (`$'..\c'`) must
  flip from deny to allow** — the decoder reads the `'` as the control char, over-runs the string,
  and produces `..g` with no separator (R3 finding 2). On POSIX N5 is allow either way, so run its
  assertion on Windows (or force `os.sep`). A mutation that leaves N5 green means the closing-quote
  guard is not load-bearing.

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
  - `echo hi > $'\Uffffffffx'` (N3, R3 finding 1) — **refused** as `'\Uffffffffx' is outside your
    workspace` on Windows (a `\U` above 0xFF keeps its backslash, a separator there), and the
    decision **returns rather than the turn erroring** (totality holds without a `chr()` guard).
    Confirm the reason names the backslash form and no file appears. *(R2's plan expected allow
    here; R3 finding 1 corrected it — the C-locale bash keeps the literal, so allowing would open
    an escape.)*
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
  shipped; correct it if any reason string changes (none is expected).
