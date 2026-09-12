# Tasks — a URL is not a path

Implementation belongs to a night window. No task here is complete because this plan exists. Only
verified implementation closes one.

**This change is Python-only.** No `hub/ui` file changes, so the committed bundle in
`hub/hub/static/ui` is **not** rebuilt. The Python lint set **is** required (§8).

**Two constraints of `hub/hub/mcp_server.py` bind every task below.**
- It is spawned standalone and may import **only** the standard library and fastmcp. `urllib.parse`
  and `urllib.request` are standard library. The Hub's schema is not, so the reason cap is restated
  (§2.4).
- `approve_tool_call` has **no return annotation**. With one, FastMCP emits `structuredContent`, and
  a correct `allow` is silently not honoured. Nothing in this change touches that function, and
  `test_response_carries_no_structured_content` must still pass.

**The table is written first, and the tree stays green at every commit.** The night window commits
each checkpoint. So §1 pins D2's rows against the **unmodified** `_decide`, marking each row
expected to move `xfail(strict=True)`, and §2 removes those markers as the reader lands. A strict
xfail that starts passing early is a failure. That is the point: a row may not change answer before
its rule exists.

## 1. Pin the table before the reader moves

- [ ] 1.1 In `hub/tests/test_permission_approver.py`, add D2's table as one parametrized test over
  `_decide("Bash", {"command": …})`. Use the existing `workspace` fixture, which already has
  `sub/`, and set `HUB_URL=http://127.0.0.1:8016` with `monkeypatch`. For each row, assert `allow`,
  and where D2 names a reason, assert on a distinguishing substring of it:
  - network: `"network address"` present, `"workspace"` absent;
  - cannot be checked: `"cannot be checked"` present, `"outside your workspace"` absent;
  - outside: the word **as written**, e.g. `"'../stray.txt'"`.

  Rows are platform-scoped where D2 says so: X1–X3 and X9 on Windows only. On POSIX, X1–X3 are
  pinned **allowed**, because they contain no separator there. The `ids=` are D2's labels, so a
  failure names its row.
- [ ] 1.2 Add N8 as its own test: `_decide("WebFetch", {"url": "https://example.com/x", "prompt":
  "p"})` is **allowed**. It pins D7's statement that the rule governs shell text only. A future
  change that brings fetch under the rule must flip this deliberately.
- [ ] 1.3 Add H12: with `HUB_URL` deleted from the environment, H1–H4 are refused.
- [ ] 1.4 Run §1's tests against the unmodified `_decide`. Mark `xfail(strict=True, reason="a-url-
  is-not-a-path §2")` on exactly the rows D2 says move: W1–W5, H1–H4, H15, H16, R11, N3, and (on
  Windows) X1–X3. Also mark every row whose **reason** assertion is new: R1–R5, R10, N1, N2, N7,
  G5, H5–H10 and H13–H14. **Any other failure means the table is wrong, not the code.** Stop,
  re-measure the row with `testbed/scratch/r1f300/prototype.py`, and record what differed here.
- [ ] 1.5 Commit §1 alone, green. This is the pin: from this commit on, a regex change that flips
  R1–R5 fails CI.

## 2. The reader

- [ ] 2.1 In `hub/hub/mcp_server.py`, beside `_decide`, add the word reader of D1: the delimiter
  split, and the six rules in their order. Keep `_ABSOLUTE_PATH_RE` as rule 6's backstop, applied
  to one word at a time, and rewrite its comment to say that is now its only use. `_decide`'s
  `command` branch calls the reader. The `_PATH_KEYS` branch for file tools is **unchanged**.
- [ ] 2.2 The run's-own-Hub test of D4. For a URL: `urllib.parse.urlsplit`, schemes compared
  ignoring case, `hostname` equal, effective ports equal (80 and 443 by default), `username` and
  `password` both `None`, and any `ValueError` treated as "not own". For a reference: the remainder
  is empty or starts with `/ ? #`, the approver has a non-empty `HUB_URL`, and the command's
  case-insensitive `HUB_URL` count equals its reference count.
- [ ] 2.3 The three refusal texts of D5, verbatim from `design.md`. An edit to their wording is an
  edit to the design, so record it there.
- [ ] 2.4 The bound. Every reason quotes at most 200 characters of the word, with `…` where it
  cuts. Restate the Hub's cap as a module constant beside `MIN_WAITING_SECONDS`, with the same kind
  of comment, and add a test asserting that the longest possible reason is at or under
  `PermissionDecisionCreate.model_fields["reason"]`'s `max_length`, which the test reads from the
  Hub's schema. The longest possible reason is the longest fixed text plus 200 characters plus
  quoting. **Also** pin that a 1,200-character URL now gives a reason of at most that cap. Today it
  gives 1,244 (D5).
- [ ] 2.5 Totality. Catch `(OSError, ValueError)` around `realpath` and `commonpath`, and refuse.
  Add a test with a NUL byte in a path word that asserts a decision is **returned** (either
  answer), so that it runs meaningfully on CI's Linux, where it raises today (D5).
- [ ] 2.6 Rewrite `_decide`'s docstring and the comment at its `command` branch (D9). It reads
  shell text word by word. Relative words are resolved against the workspace root, which is where
  the run started. A `cd` in an earlier call is not seen. It is a boundary, not a sandbox. It does
  not govern network access, only which address a shell command's text may name. **Delete** the
  sentence *"Relative paths are left alone: they resolve against the run's cwd, which is the
  workspace."*
- [ ] 2.7 Remove every §1.4 `xfail` marker. The whole table is green, with no marker left, and
  `grep -n xfail hub/tests/test_permission_approver.py` shows none of this change's.

## 3. The wire shape

- [ ] 3.1 Beside `_call_tool_over_stdio`, add two cases through a **real spawn** of
  `mcp_server.py`, with `AW_WORKSPACE_DIR` and `HUB_URL` in the child's environment.
  - `curl -s https://example.com/x` answers `behavior: deny`, with a message that begins
    `Denied: 'https://example.com/x' is a network address`.
  - `curl -s "$HUB_URL/api/v1/agent-actions/tasks"` answers `behavior: allow`.

  Both results carry **no** `structuredContent`. This is the only test that sees the answer Claude
  actually receives.

## 4. Docs

- [ ] 4.1 `docs/reference/permission-postures.md`, *"A shell command declares no path"*. Replace
  *"the approval tool does read absolute paths out of the command text"* with what D1 reads, in one
  or two sentences. Add one sentence saying that a shell command under **Workspace only** may name
  only the run's own Hub as a network address, and that this is a rule about the command's text,
  not a network boundary (`WebFetch` is not checked). Keep the page's per-posture framing. It states
  a requirement (`agent-run-sandboxing`, *"The product states which postures confine a run"*).

## 5. Mutation checks — every rule must be load-bearing

Nothing existing fails for the absence of most of these rules. So each is mutated once, and a
named row must fail. Record which row failed, then restore.

- [ ] 5.1 Delete rule 6 (the backstop). G1–G4 must fail.
- [ ] 5.2 Delete the `HUB_URL` count condition. H10 must fail.
- [ ] 5.3 Delete the remainder condition (`/ ? #`). H8 must fail.
- [ ] 5.4 Delete the userinfo condition. H13 must fail.
- [ ] 5.5 Treat rule 3's words as plain relative. R4, R5 and G5 must fail.
- [ ] 5.6 Resolve rule 5's relative words without joining them to the root. R1–R3 must fail.
- [ ] 5.7 Make quotes group words instead of delimiting them. **H1 must fail**: the quoted
  `Content-Type` header becomes one non-plain word, refused as `'/json'` (`design.md` D1, measured
  by `measure6.py`). Also pin `python -c "open('/etc/x','w')"` as refused. It is refused under
  both splits, and it guards the backstop rather than the split.
- [ ] 5.8 Drop `\` from the Windows separators. X1 must fail (on Windows).
- [ ] 5.9 Drop the bound. §2.4's long-URL test must fail.

## 6. Drive it — the table is an argument, and a drive is the product

Every real agent turn binds `claude-haiku-4-5`. No job is left enabled. The drive Hub runs on a
port chosen that night, with a fresh profile, started from `hub/` with uvicorn **from source**,
and no `.py` under `hub/hub` or `src` newer than the process. Never 8000 or 8010.

- [ ] 6.1 **Pre-fix, first.** `git worktree add ../aw-url-prefix <sha>` at the commit **before**
  §2's (not `git stash`). Start the drive Hub from that worktree, on a fresh git fixture project
  containing `sub/hello.py`, with one agent on the default posture (no override) and a Haiku runner.
  On its **first** turn it is told the HTTP form, because there are no grounds for MCP yet.
  1. Ask it to create a task through that form with `curl`.
  2. Ask it to run `python sub/hello.py`.
  3. Ask it to run `curl -s https://example.com/`.

  Read `event_logs` for `permission_denied`, and the transcript's tool results. All three must be
  refused, for filesystem reasons: `'/api/…'`, `'/hello.py'` and `'s://example.com/'`. If any is
  not refused, this is not a reproduction. Say so and stop. Remove the worktree afterwards.
- [ ] 6.2 **Fixed tree**, same fixture shape, on a fresh project and agent:
  - Ask 1 creates the task. Read `tasks`: it exists, created by the run, with no
    `permission_denied` for that call.
  - Ask 2 prints `hello from sub`.
  - Ask 3 is refused, and the tool result carries D5's network text verbatim.
  - `event_logs` holds that refusal as `permission_denied`, with the same reason. That is the
    record the operator reads, and the question that F108 established the rounds never ask.
- [ ] 6.3 **What the agent does next.** In 6.2's transcript, after ask 3's refusal, record what the
  agent did: called `ask_user`, stopped and reported, or tried another route (`python -c`, `wget`,
  `WebFetch`). This is one observation, not a rate. Record it verbatim and do not grade it here;
  §7.2 is the judgement.
- [ ] 6.4 Confirm every run in the drive profile joined to `claude-haiku-4-5-20251001`, that `GET
  /jobs` is empty or every job is disabled, and stop the Hub.

## 7. Verification only a human can do

- [ ] 7.1 **Is the refusal legible where the operator reads it?** Open the agent's activity in the
  served UI and read the network refusal from §6.2. Does it tell you what happened and who can
  change it, without sending you to look at the filesystem? An agent can check that the string is
  there. Only you can say whether it reads.
- [ ] 7.2 **Is the way out the one taken?** Read §6.3's observation. An agent that routes around
  the refusal with `python -c` is the failure the research's incident report describes, and the
  wording in D5 is this change's only lever on it. Decide whether the wording needs to change.
  That is a product judgement, not a test.
- [ ] 7.3 **Decide D10's open items:** N3 (the one widening), and `/dev/null` (X4). Decide them or
  leave them open, but in writing, in `spec-queue/DECISIONS.md`.

## 8. The gate

- [ ] 8.1 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
  --target-version py311`, `mypy src/`. Use CI's path list, not a narrower one.
- [ ] 8.2 `py -3.11 -m pytest tests/ -q` from `hub/` (the whole Hub suite), under `py -3.11`, never
  bare `python`.
- [ ] 8.3 `openspec validate --strict a-url-is-not-a-path` after every delta edit.
- [ ] 8.4 No migration, no API or schema change. `git diff <base>.. -- hub/hub/migrations
  hub/hub/api hub/ui` is empty.

## 9. Close it out

- [ ] 9.1 Set `F300`, `F312` and `F321` to `fixed <sha>` in `scripts/drive/FINDINGS.md`, each
  naming the task that closed it and quoting §6.2's evidence. In `F312`, correct in place, in a
  dated block, the claim *"No agent on the default posture can make any network request from a
  shell command"*: `curl example.com` (no `/`) was always allowed (D2 N4). In `F300`, correct
  *"any URL in any shell command is denied"* the same way.
- [ ] 9.2 `F322` stays **open**, and so do `F299` and `F301`. Say so in the close-out commit, so
  that nobody reads this change as closing them.
- [ ] 9.3 Do **not** edit `spec-queue/DECISIONS.md`. D6's correction to 1c/1d is the operator's to
  record. If the review page for the night has not already carried it, put it in
  `decisions_for_user`.
- [ ] 9.4 `openspec validate --strict a-url-is-not-a-path`, then archive with the
  `openspec-archive-change` skill. Before syncing, compare the MODIFIED block with the main
  `agent-capability-plane` block. Every scenario must survive, and the F301 clause must be
  verbatim.

## 10. User test guide

- [ ] 10.1 `test-guide.md` in this change is the operator's walkthrough. Keep it true to what
  shipped, and correct it if D5's wording changes.
