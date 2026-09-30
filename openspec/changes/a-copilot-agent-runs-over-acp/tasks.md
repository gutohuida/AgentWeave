## 0. Rounds

- [x] 0.1 R2: an independent re-derivation against the code as it stands after tonight's queue and slice 1. Re-read, fresh:
  - `codex_appserver.py`;
  - `agent_trigger.py` (the trigger body, `_execute_run`'s dispatch, the RPC executor, the stop paths);
  - `runner_commands.py`, `launchability.py`, `model_catalog.py`;
  - `mcp_server._decide` and its callers;
  - `workspace_writes.py`, `worker.py`, `conversation_titles.py`;
  - `agents.py` (`_render_hub_agent_context`, create, PATCH).

  Re-derive D1–D19 from those files, not from this design. Re-check every row of design § "Sites touched by open changes" against what landed, including slice 1's adapter member names, and correct the design where they differ. Answer Open questions 2, 4 and 9 from `app.js` or the command reference. Record the round in `design.md`'s Round log. `openspec validate a-copilot-agent-runs-over-acp --strict` passes
  - **Done 2026-09-28** against master `ef55e6f` (3 of the queue's sites landed; the rest and slice 1 unbuilt, marked "rebase at IMPL"): 16 corrections, incl. three gates that would 501 or never inject MCP, an empty `--available-tools=` that grants every tool, and JSON-titled conversations; Open questions 2, 4, 9, 10 answered. See the Round log
- [x] 0.2 R3: a second independent re-derivation, not a re-read of R2. Ask of each route in design § "What each route returns when what it calls raises" what it actually returns when the Copilot function it calls raises, by reading the route. Re-derive the D8 table from `app.js`'s `XDo`/`nNo` and `mcp_server._decide`. Record the round in the Round log
  - **Done 2026-09-28** against master `fc33ff9` (code identical to `ef55e6f`). There are five changes:
    - R2's MCP identification by `tool_call` title is replaced, because the title is the model-written `description` argument (`VDo`). The source is now `tool.execution_start`, and an unidentified call is refused;
    - the trigger route answers 200 queued, not 409, so three refusals gain `agent_wide`;
    - `run_turn` returns rather than raises after the prompt;
    - MCP calls are labelled by server, not by `YDo`'s guessed kind;
    - `diagnostic_event` gets the spec's `stream`/`severity`.

    The contract with slices 3–5 is written down. Open questions 3, 6 and 7 are answered and 8 in part; 1 and 5 are carried. See the Round log
- [x] 0.3 Opus adversarial review of the change and of the decisions it assumes (the operator's standing step before APPROVED). It MUST address:
  - D5: the context split, and whether the tool surface belongs in `per_turn`;
  - D8: whether the `acceptEdits` emulation, fetch-allowed parity and the refusal to emulate full access under policy are right;
  - D9: plan mode on specification turns;
  - D15: whether a pending launchability verdict should be permissive.

  Record the result in the Round log and in `spec-queue/tracks/reviews/`
  - **Done 2026-09-28:** Opus review ghcp-s2-2026-09-28: REVISE → 11 fixes applied (findings 1–11, all verified against `app.js`/the capture; none disputed), 6 notes answered (12–17, all applied), plus 4 cross-slice items (subagent `session.error`, both contract conflicts closed as decided, `COPILOT_ALLOW_ALL` owned here). See the Round log, "Review fixes, 2026-09-28"

## 1. Captures, then tests first — each test fails on today's code

Copilot Free plan: **two** model-calling prompts in this group, and no more. Every other probe is a slash command or a handshake. Run captures with `openspec/changes/a-copilot-agent-runs-over-acp/evidence/r1_probe.py` as the starting point. Always use a scratch `COPILOT_HOME` under `%TEMP%`, and point the MCP server's `HUB_URL` at a dead port, never `:8000`.

- [x] 1.1 **Capture 1 (1 prompt, ACP).** Set up a scratch workspace holding a custom agent file whose body carries the marker `AW-MARKER-5521`, and the Hub's real `mcp_server.py` from `--additional-mcp-config`. Subscribe to design D10's raw events (`COPILOT_RAW_EVENTS`, which since R3 includes `tool.execution_start`). Answer every `session/request_permission` with `allow_once`, **recording its params**. Send one prompt: *"Quote the marker in your agent instructions. Then create file probe.txt containing hi. Then run each of these shell commands separately: `Set-Content probe2.txt hi`, then `Get-ChildItem`, then `curl.exe -s http://127.0.0.1:<DEAD>/`. Then fetch `http://127.0.0.1:<DEAD>/` with your web fetch tool. Then call agentweave-list_tasks."* `<DEAD>` is the dead Hub port. (Review 2026-09-28, findings 1 and 2: R3's `echo done` is the class Copilot auto-approves, so it would have captured **no** `execute` request and 1.6 would have had no execute fixture. `Set-Content` writes, so Copilot must ask.)
  - **Done 2026-09-29** (`evidence/t1_1_capture.py`, dead port 9, build 1.0.88): fixture saved,
    386 wire messages, redacted, no token. Headline corrections: the marker did **not** come back
    (policy refusal, not proof of an empty body); no `kind:"edit"` request occurred at all (both
    writes went through `Set-Content` shell calls); `Get-ChildItem` **did** raise a permission
    request three times (`readOnly:false`), disproving the "auto-approved read-only class" premise
    this task and task 10.1 both stated; `curl.exe` raised only `kind:"shell"`, never finding 2's
    anticipated `kind:"url"`; `session.mcp_servers_loaded`'s `agentweave` entry carries neither
    `source` nor `transport`, unlike `github-mcp-server`'s `"source":"builtin"`. Full detail,
    including the ordering and stop-reason sub-items, in the Round log

  Save the transcript, in wire order, to `hub/tests/fixtures/copilot_acp/turn_write_shell_mcp.jsonl`. Paths must be replaced by `<WS>`/`<HOME>`, and it must hold no token. Record in the Round log:
  - whether the marker came back (Open question 1);
  - the three `request_permission` shapes (edit, execute, mcp) against design D8;
  - the `session.error|warning|info` field names, if any appeared (Open question 10);
  - (R3) for each permission request, the order of its raw `tool.execution_start`, its raw `permission.requested` and the ACP `session/request_permission`. Also whether `tool.execution_start` carried `mcpServerName` for the `agentweave` call. Design D8 relies on it preceding the request (CODE, `setupEventForwarding`);
  - (R3) the stop reason the prompt returned if a `session.error` appeared, and any second `session_info_update` title (Open question 8);
  - (review) that `Get-ChildItem` raised **no** permission request (the read-only class), and which requests `curl.exe` raised: an `execute`, a `url` carrying the `powershell` call's `toolCallId`, both, or none. And the `url` request of the `web_fetch` call, with its `toolCallId`;
  - (review) for each `execute` request, whether `tool.execution_start` named its tool (how often a genuine `powershell` request arrives with no name known; slice 3's conflict 1);
  - (review) the `source` and `transport` `session.mcp_servers_loaded` reported for `agentweave` (fixes D8's accepted source), and whether `session.mode_changed` or `exit_plan_mode.requested` appeared.
- [x] 1.2 **Capture 2 (1 prompt, `-p`).** Run `copilot.exe -p "Reply with the word ok" --output-format json --no-auto-update --disable-builtin-mcps --no-custom-instructions --no-ask-user --excluded-tools=builtin:*,mcp:*,custom:* --allow-all-tools` under a scratch home. **Never `--available-tools=`**: R2 read `app.js`'s `Y0`, and an empty value means *no filter* (design D14). Save stdout to `hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl`. Record which event carries the answer and whether any tool was offered. If the source-qualified patterns did not remove every tool, record that; design D14's fallback (the explicit built-in list) applies. Also save `evidence/help-config.txt` (the output of `copilot help config`, no model call) for task 2.4
  - **Done 2026-09-29** (`evidence/t1_2_capture.py`, build 1.0.88): 16 wire messages, RC 0, saved.
    The answer is carried by `assistant.message_delta` then finalized in `assistant.message`
    (`content:"ok"`, `toolRequests:[]`). No tool was offered: `session.info` lists 16 disabled
    tools and `session.usage_checkpoint`'s `promptCacheBreakState` reports `tool_count:0`,
    `tools:[]` — the source-qualified `--excluded-tools` patterns removed every tool by
    themselves, so D14's explicit-built-in-list fallback was not exercised (nothing to record
    beyond confirming the non-fallback path). See the Round log, "Task 1.2 — Capture 2,
    2026-09-29"
- [x] 1.3 `hub/tests/test_runners_api.py`: `POST /runners` with `cli: "copilot"` returns 201, and the row reads back. Today it fails with 422, the validator's refusal. Add a model-level test that inserts a `Runner(cli="copilot")` and commits; it fails today on `ck_runners_cli`
  - Verify: `py -3.11 -m pytest hub/tests/test_runners_api.py -q -k copilot`
  - **Done 2026-09-30:** both tests added, confirmed red on today's code —
    `test_create_runner_with_copilot_cli_returns_201_and_reads_back` fails `422 != 201`
    (`RunnerCreate.validate_cli` against `RUNNER_CLIS`); `test_copilot_runner_row_commits_at_the_model_level`
    fails on `sqlite3.IntegrityError: CHECK constraint failed: ck_runners_cli`. The other 23 tests
    in the file still pass. Section 2 (`RUNNER_CLIS`, the migration) turns these green.
- [x] 1.4 `hub/tests/test_runner_charter_models.py` (or the seeding test beside `db/engine.py`'s seeder): a zero-runner project is seeded with `claude`, `codex` and `copilot`. A project holding one runner gets nothing. Cover both seeders, `engine.py:_seed_default_runners` and `project_lifecycle._seed_new_project`
  - **Done 2026-09-30:** two tests added to `test_runner_charter_models.py` —
    `test_seed_default_runners_seeds_copilot_for_a_zero_runner_project` (a zero-runner project
    seeds `{claude, codex, copilot}`; a project with one pre-existing runner gets nothing added,
    confirmed via `engine._seed_default_runners` called directly) and
    `test_seed_new_project_seeds_copilot_runner` (`ProjectLifecycleService._seed_new_project`
    called directly on an uncommitted `Project`). Both confirmed red on today's code: each seeds
    only `{claude, codex}` because `RUNNER_CLIS` doesn't include `"copilot"` yet (widened in
    section 2). The file's other 7 tests still pass.
- [x] 1.5 `hub/tests/test_copilot_probe.py` (new): `resolve_copilot_executable` on a fake tree in `tmp_path`. Cover:
  - an npm `copilot.cmd` JS shim plus `node_modules/@github/copilot/node_modules/@github/copilot-win32-x64/copilot.exe` resolves to the `.exe`;
  - a shim with no platform package raises, with the looked-for path in the message;
  - a native executable on `PATH` is used as-is;
  - a pinned override that is a `.cmd` is refused.

  Patch `shutil.which` and the platform. The test fails today because the module does not exist
  - **Done 2026-09-30**: four tests added, patching `shutil.which` and
    `hub.copilot_probe.platform.system`/`.machine`. Confirmed red: the whole file fails at
    collection with `ModuleNotFoundError: No module named 'hub.copilot_probe'`, exactly as the
    task states — no per-test behaviour is checked yet, only that the module doesn't exist.
    `CopilotExecutableNotFound` (imported alongside `resolve_copilot_executable`) is asserted as
    the raised type per design D2 ("`resolve_copilot_executable` raises `CopilotExecutableNotFound`,
    a `FileNotFoundError`"); the "no platform package" case asserts the looked-for path
    (`.../node_modules/@github/copilot/node_modules/@github/copilot-win32-x64/copilot.exe`)
    appears in the exception message. Task 3.1 implements the module against this file.
- [ ] 1.6 `hub/tests/test_copilot_acp_decide.py` (new): `decide_permission` over every row of design D8's table, for all four postures. Use the `request_permission` params captured in 1.1 for edit, execute and mcp, and CODE-shaped params for read, fetch, memory and an unknown kind. It must include:
  - (consistency pass 2026-09-28, design D9 item 1a) with `spec_turn=True`, an `edit` inside the workspace → REJECT under `workspace`, `acceptEdits`, `manual` and full access (no card under `manual`); with `spec_turn=False` the same request keeps its posture's answer;
  - (operator decision 2026-09-28, design open question 13, option (c)) with `spec_turn=True` under full access, every **non-`edit`** row is answered as the `workspace` column answers it, never ALLOW on full access's account: a PowerShell command writing `..\..\x` → REJECT, one writing `.\x` → ALLOW, a foreign MCP server judged as under `workspace`, an MCP request whose server is not identified → REJECT, `memory` → REJECT; the same requests with `spec_turn=False` under full access → ALLOW;
  - a PowerShell command writing `..\..\x` refused under `workspace`;
  - `agentweave` MCP allowed under `manual`;
  - a foreign MCP server judged;
  - `memory` refused;
  - the answer never being `allow_always`;
  - (R2) an `edit` request with no `locations` and no `fileName` refused;
  - (R2) an unset `permission_mode` judged exactly as `workspace`;
  - (R3, replacing R2's title case) the server taken from a raw `tool.execution_start` (`mcpServerName: "agentweave"`, `mcpToolName: "send_message"`) read before the request → ALLOW under `manual`;
  - (R3) the same request with **no** raw event read, but a preceding `tool_call` titled `agentweave-send_message` (a foreign tool's `description` argument) → REJECT under every posture but full access. Under R2's rule this is an allow; it must fail on R2's code;
  - (R3) `mcpServerName: "agentweave-x"`, or `"agentweave"` with a tool the Hub does not serve → judged as foreign;
  - (R3) a `read` request with no `rawInput.path` and no `locations` → REJECT;
  - (R3) an `execute` request whose `tool.execution_start.toolName` is `local_shell`, carrying a command that only the Bash reading refuses → REJECT (both dialects);
  - (R3) a foreign MCP call whose arguments name no path and no command → ALLOW under `workspace` (Claude parity, stated in the test's docstring);
  - (review, finding 2) a `url` request carrying a `powershell` call's `toolCallId` with `https://example.com` → REJECT under `workspace`; the same URL on a `web_fetch` call → ALLOW; the same with `requestSandboxBypass: true` → REJECT; a `url` request whose id is `"url-permission"` or unknown → judged as shell text, and a URL naming the run's `hub_url` → ALLOW;
  - (review, finding 5) server `agentweave` with a tool the Hub does not serve and `{"command": "Remove-Item ..\\..\\x"}` → REJECT under `workspace`; server `agentweave__x` → judged as foreign (same command → REJECT). Both are ALLOW on R3's `mcp__<server>__<tool>` name, so the test fails on R3's code;
  - (review, finding 6) `agentweave`/`send_message` with `servers` reporting `agentweave` from source `workspace`, or `plugin`, or not reported at all → not the Hub's own (REJECT under `acceptEdits`); from the Hub's source with transport `stdio` → ALLOW;
  - (review, finding 1/slice 3) an `execute` request with no `rawInput.command` (e.g. `write_powershell`'s `{shellId, input}`) → REJECT; an `execute` whose tool name is `write_powershell` carrying a command → key `"Shell"`;
  - (review, note 12) after `tool.execution_complete` for `call_0`, a new request on `call_0` with no new `tool.execution_start` → unidentified → REJECT;
  - (review, note 16) under `manual`, an unidentified MCP request → ASK_OPERATOR with label "an MCP tool Copilot did not identify", never the title;
  - (review, note 17) a `read` whose one path contains `", "` is judged whole as well as in pieces;
  - (review, conflict 2) under `workspace`, with slice 5's rule stubbed at step 3 to return ASK_OPERATOR for everything, an unidentified MCP request is still REJECT (step 1 answers it)
  - **Partial 2026-09-30 (part 1/N, not yet checked):** `test_copilot_acp_decide.py` written,
    covering the base D8 table (design.md:634-645) across all four postures for
    execute/edit/read/fetch/mcp-own/mcp-foreign/mcp-unidentified/memory, plus the four
    baseline bullets above ("PowerShell refused under `workspace`", "`agentweave` MCP allowed
    under `manual`", "a foreign MCP server judged", "`memory` refused"). Confirmed red at
    collection: `ModuleNotFoundError: No module named 'hub.copilot_acp'` (task 3.x adds the
    module against this file, as 1.5's probe file does for `copilot_probe`). CODE-shaped params
    used throughout rather than the 1.1 capture's, because 1.1 never raised a `kind:"edit"`
    request (both file writes went through `Set-Content` shell calls) — recorded as a gap in
    iteration 2's log; 1.9 needs a different source for that fixture case too. Left for a later
    firing, unchecked: the `spec_turn=True` rows (bullets 1-2), R2/R3's MCP-identification edge
    cases (bullets 6-9, 12, 16-17), review finding 2's shell-classified-`url` rows beyond plain
    `web_fetch`/bypass, findings 5 and 6's load-time-condition rows, finding 1/slice 3's
    `write_powershell`/`local_shell` shapes, and "the answer never being `allow_always`" (that
    is the RPC-answering step's property, not `decide_permission`'s — tested alongside whichever
    task covers that function). Also surfaced, not resolved here: design.md's `fetch` +
    `requestSandboxBypass` row gives no `manual`/full-access cell, so this slice asserts only
    `workspace`/`acceptEdits` for it.
  - **Partial 2026-09-30 (part 2/N, not yet checked):** added `TestSpecTurn` (8 tests) covering
    bullets 1-2: an `edit` inside the workspace REJECTed under every posture on a spec turn,
    including no card under `manual` and no `allow_all` under full access (D9 item 1a,
    design.md:896-908), with the same request kept at its ordinary per-posture answer off a spec
    turn; under full access with `spec_turn=True`, a PowerShell write outside/inside the
    workspace judged as `workspace` (REJECT/ALLOW), a foreign MCP server likewise judged as
    `workspace` (REJECT), and `memory` REJECTed (open question 13, option (c),
    design.md:666-669, 796-812) — each paired with the same request off a spec turn, staying
    full access's ordinary ALLOW. One exception recorded rather than assumed: the
    unidentified-MCP request stays REJECT under full access **whether or not** it is a spec
    turn, because that is `decide_permission`'s standing full-access fallback (design.md:583-585)
    already covered by part 1/N's `test_mcp_request_with_no_identified_server_is_rejected_under_every_posture`,
    not a spec-turn-specific rule — the task bullet's "same requests ... → ALLOW" clause does not
    apply to that one row. Still red at collection: `ModuleNotFoundError: No module named
    'hub.copilot_acp'`. Left for a later firing, unchecked: R2/R3's MCP-identification edge cases
    (bullets 6-9, 12, 16-17), review finding 2's shell-classified-`url` rows beyond plain
    `web_fetch`/bypass, findings 5 and 6's load-time-condition rows, finding 1/slice 3's
    `write_powershell`/`local_shell` shapes, and "the answer never being `allow_always`".
  - **Partial 2026-09-30 (part 3/N, not yet checked):** added `TestMcpServerIdentification` (4
    tests) and `TestReadPathSplitting` (3 tests) covering bullets 6-9, 12 and 17. Read design.md's
    "Identifying the MCP server" and "calls holds open calls only" text (design.md:671-745) and the
    read row (design.md:638) fresh rather than off the part-1/N summary, per the standing
    instruction. Two things this re-derivation surfaced, not guessed:
    `decide_permission` never sees *how* a `calls` entry was populated and never reads
    `toolCall.title` (R3, design.md:676-687), so bullets 6, 7 and note 12 — each naming a
    different upstream source feeding `calls` — collapse at this function's boundary into just two
    shapes already exercised: a call id present in `calls` (bullet 6, same shape as part 1/N's
    Hub-own-under-manual test) and one absent from it (bullet 7 and note 12, same shape as part
    1/N's unidentified-server test, including REJECT under the full-access fallback per the
    settled design.md:582-585 text — this file does not follow this bullet's own "but full access"
    gloss, which predates that settled carve-out). Bullet 8 (`agentweave-x`, or `agentweave` with a
    tool the Hub does not serve, judged foreign) got a new parametrized test under `acceptEdits`,
    where the foreign row's REJECT is unconditional. Bullet 9 (a `read` with no path at all)
    was already covered by part 1/N; no new test added for it. For bullet 17 (a `read` path
    containing `", "` judged whole as well as in pieces), a real, differentiating fixture where
    piece-only judging would disagree with whole-string judging could not be constructed from
    actual Windows path semantics (verified against `_where` directly, not assumed): a real
    absolute path's drive-and-directory prefix always survives in the first split piece, so
    piece-only judging already answers correctly by itself. `TestReadPathSplitting` instead tests
    both directions a comma-bearing single filename can go (inside → ALLOW, outside → REJECT) plus
    the ordinary two-real-paths-joined case, and records the unresolved question rather than
    inventing a fixture for it. Note 16 (the operator card's label text) is out of scope for
    `decide_permission` — it belongs to `RpcTransport.permission_card_label` (D3,
    design.md:778-781), a different function; noted in the test file's docstring, not tested here.
    Still red at collection: `ModuleNotFoundError: No module named 'hub.copilot_acp'`. Left for a
    later firing, unchecked: review finding 2's shell-classified-`url` rows beyond plain
    `web_fetch`/bypass, findings 5 and 6's load-time-condition rows, finding 1/slice 3's
    `write_powershell`/`local_shell` shapes, and "the answer never being `allow_always`".
  - **Partial 2026-09-30 (part 4/N, not yet checked):** added `TestFetchAsShellText` (4 tests,
    3 parametrizations) covering the rest of review finding 2's row (design.md:640). Read
    design.md:640-641 and `_judge_url`/`_is_own_hub` (`mcp_server.py:1210-1266`) fresh, per the
    standing instruction, not off part-1/N's summary. `web_fetch` and the sandbox-bypass row stay
    part 1/N's `TestFetch`, unrepeated. New: a `powershell`-classified call's `https://example.com`
    REJECTed under `workspace`; the same URL with the call's id absent from `calls` altogether
    (`"url-permission"` and an arbitrary unrecognised id, parametrized) REJECTed the same way,
    since either reads as an unidentified shell call rather than `web_fetch`; a URL naming the
    run's own `hub_url` ALLOWed even with no `calls` entry — traced through `_judge_url` to
    `_is_own_hub`'s scheme/host/port match, then `_judge_path`, which reads the URL text as the
    relative path it spells and finds it inside the workspace root, exactly as design.md's "the
    shell does not know it is a URL" note explains. Only `workspace` is exercised, matching this
    slice's own scope. Still red at collection: `ModuleNotFoundError: No module named
    'hub.copilot_acp'`. Left for a later firing, unchecked: findings 5 and 6's
    load-time-condition rows, finding 1/slice 3's `write_powershell`/`local_shell` shapes, and
    "the answer never being `allow_always`".
  - **Partial 2026-09-30 (part 5/N, not yet checked):** added `TestMcpForeignNameCollision` (2
    tests) covering review finding 5, the naming bug itself: `_decide`'s own first statement
    (`mcp_server.py:1557-1558`) allows any tool name starting `mcp__agentweave__` unconditionally,
    and R3's foreign-MCP name, `mcp__<server>__<tool>`, collides with that prefix for a server
    reporting exactly `agentweave` with a tool the Hub's server does not serve, and for a server
    registered under the config key `agentweave__x` (whose buggy name,
    `mcp__agentweave__x__<tool>`, also starts with the prefix — the plain-hyphen `agentweave-x`
    case part 3/N's `TestMcpServerIdentification` already covers does not). Both new tests supply
    `{"command": "Remove-Item ..\\..\\x"}` under `workspace` and assert REJECT, so they fail on
    R3's `mcp__`-prefixed naming (which would unconditionally ALLOW) and pass only on the
    `copilot-mcp:{server}/{tool}` naming design.md:643 actually specifies. Finding 6's true
    load-time-condition row (the `session.mcp_servers_loaded` source+transport check) is left
    **genuinely blocked**, not merely unattempted, and recorded as an open question rather than
    guessed: design.md:572 states `decide_permission`'s complete keyword signature with no
    parameter carrying this map, `CallFacts` is stated as exactly `(tool_name, mcp_server,
    mcp_tool)` (design.md:576) with no room for a verification flag, and no CODE citation anywhere
    in design.md shows a `servers=` keyword or a `ServerFacts`-shaped value actually reaching this
    function — design.md:725-726 describes the `servers` map only as client-side bookkeeping "fed"
    "like `calls`", never as a stated argument. This needs a review-round decision on the
    parameter shape before a fixture can be written, not a guess in a test file. Still red at
    collection: `ModuleNotFoundError: No module named 'hub.copilot_acp'`. Left for a later firing,
    unchecked: finding 6's load-time-condition row (pending the signature decision above), finding
    1/slice 3's `write_powershell`/`local_shell` shapes, and "the answer never being
    `allow_always`".
  - **Partial 2026-09-30 (part 6/N, not yet checked):** added `TestExecuteDialectSelection` (2
    tests) covering the rest of review finding 1/slice 3: design.md:636's dialect-key rule
    (`powershell` → `"PowerShell"`, `bash` → `"Bash"`, any other name or none known → `"Shell"`,
    read in both dialects, refused if either refuses). Built a fixture command,
    `"echo x`..`y"`, and verified it directly against the real `_read_command`/`_decide`
    (`mcp_server.py`) before writing any assertion: read as Bash it is refused (a backtick pair is
    bash-only command substitution, `mcp_server.py:1467-1472`, so it excises `..` and separately,
    recursively judges that text as its own command — an exact `".."` word, refused as the
    workspace's own parent); read as PowerShell it is allowed (backtick is only PowerShell's
    escape character there, so `` `..` `` collapses to the literal two characters `..` glued
    between the surrounding `x`/`y` into one harmless word, `"x..y"`). Confirmed with
    `_decide("PowerShell", {"command": ...})` → `allow=True` and `_decide("write_powershell", ...)`
    / `_decide("local_shell", ...)` (both outside `_TOOL_DIALECTS`, so both dialects) → `allow=False`.
    Both new tests supply this command under `workspace`: one with `CallFacts.tool_name =
    "write_powershell"`, one with `"local_shell"`, both asserting REJECT — a test that fails if the
    implementation ever keys either name as `"PowerShell"` alone (R2's platform-guessing rule,
    already gone per design.md:636's "Review 2026-09-28"). The no-`command`-key half of finding
    1/slice 3 (`write_powershell`'s real `{shellId, input}` shape) was already covered by part
    1/N's `test_command_that_is_not_a_non_empty_string_is_rejected`; not repeated here. Still red
    at collection: `ModuleNotFoundError: No module named 'hub.copilot_acp'`. Left for a later
    firing, unchecked: finding 6's load-time-condition row (blocked, pending a review-round
    signature decision) and "the answer never being `allow_always`" (belongs with the
    RPC-answering step's own tests, not this function's).
- [x] 1.7 `hub/tests/test_permission_approver.py`: `_decide(..., workspace=W, hub_url=U)` judges against `W` and `U` when `os.environ` names other values. It fails today because the keywords do not exist. 2026-09-30: added `test_decide_workspace_keyword_overrides_the_environment` (a path inside the `workspace` keyword's directory, outside `AW_WORKSPACE_DIR`'s, is ALLOWed; the reverse is REJECTed) and `test_decide_hub_url_keyword_overrides_the_environment_for_a_literal_url` (design.md:614-615's literal-URL case, decided only by `_is_own_hub`: a literal URL naming the `hub_url` keyword's host is ALLOWed even though `HUB_URL` names a different one; the same call with no `hub_url` keyword falls back to the wrong environment value and is REJECTed). Confirmed red: both raise `TypeError: _decide() got an unexpected keyword argument`, since `_decide` takes no such keywords yet (task 5.1 adds them). Every expected ALLOW/REJECT was checked directly against the real `_decide`/`_is_own_hub` first, by setting `AW_WORKSPACE_DIR`/`HUB_URL` to the value the keyword should end up winning with, not assumed.
- [ ] 1.8 `hub/tests/test_copilot_acp_mapper.py` (new): replay `evidence/acp4-turn-mcp-shell-1.0.88.log` and the 1.1 fixture, **in their recorded order**, through `CopilotEventMapper`. 2026-09-30 (part 1/N): added `TestTextEventGrouping` (a synthetic two-chunk block flushed by an arriving `tool_call`, and the log's own "DONE" chunk flushed only by an explicit `flush()` at prompt completion -- scoped to the log's first turn only, id 3's request through its matching result, after discovering the raw log actually replays three prompts on one session and an unscoped read wrongly concatenates "DONE" with the later `/usage`/`/context` reply text), `TestShellToolCorrelationAndStreaming` (the echo shell call's `tool_use`/`tool_result` share a call id and keep that order; the two non-terminal, no-`status` updates emit nothing and the terminal update emits exactly one result carrying the full concatenated output) and `TestOrderingRule` (feeding the same call's terminal update before its `tool_call` deterministically reverses the event order, from design.md's own unconditional builder rules -- proving the correlation test's ordering assertion is real, not incidental). `CopilotEventMapper`'s method names (`on_session_update`, `on_raw_event`, `flush`) are not given in design.md except `on_raw_event`'s signature (`_on_armed_raw_event` hands `(type, data, params)` to it, design.md:1818-1820); the others are inferred from D10's own dispatch/flush language and flagged in the file's docstring for a future round to confirm. Confirmed red: whole-file collection failure, `ModuleNotFoundError: No module named 'hub.copilot_acp'`. 2026-09-30 (part 2/N): added `TestMcpToolNaming`, replayed from the 1.1 fixture's real `agentweave-list_tasks` MCP call (`toolCallId: call_GfOgPoS504CrdMt9ry34xI6a`; the fixture never calls the bullet's example `create_task` -- checked directly, so the real captured name is used throughout) in its recorded order (raw `tool.execution_start` -> `session/update` `tool_call` -> raw `tool.execution_complete` -> `session/update` `tool_call_update`, all four checked directly): covers the MCP half of bullet 2 (`tool_use`/`tool_result` share the call id, in order; the fixture's own call fails, Hub unreachable, so the result's `is_error` is asserted `True`) and the R3 MCP-naming bullet (`tool` is `"agentweave-list_tasks"` and `category` is `"mcp"`, never `edit`/`file_change`, regardless of this call's own `kind: "read"`). Confirmed still red at the same whole-file collection error. 2026-09-30 (part 3/N): added `TestMcpServerUnavailableDiagnostic` and `TestDiagnosticPayloadShape`, covering the two R3 diagnostic-payload bullets: (1) an `agentweave` server status that is not `connected` becomes the `copilot.mcp_server_unavailable` diagnostic, not the `copilot_mcp_server_failed` error, when the run's told access path is not `mcp` (and the reverse: `told_access_path == "mcp"` gets the error, not the diagnostic, proving the gate is real), deduped once per turn across both raw event types; and (2) every `diagnostic` payload carries `version`, `stream == "copilot"`, `severity` and `summary`. Neither real fixture has a failed `session.mcp_servers_loaded`/`session.mcp_server_status_changed` (both captures' own `agentweave` entries read `status: "connected"`, checked directly), so both raw events are synthetic, built from `session.mcp_servers_loaded`'s real wire shape with only `status` changed; `session.mcp_server_status_changed` never appears in either capture at all, so its singular (one server, not a `servers` list) shape is INFERRED, flagged in the file's docstring. Also gives `CopilotEventMapper`'s constructor a `told_access_path` keyword, not named anywhere in design.md, to carry `RpcTurnRequest.told_access_path` (D18) into the mapper -- flagged the same way as the file's other inferred surfaces. Sanity-checked both new test classes against a hand-written stand-in mapper embodying the rule under test, outside pytest, before trusting the assertions. Confirmed still red at the same whole-file collection error. 2026-09-30 (part 4/N): added `TestEditDiffToolUse` (a synthetic `kind:"edit"` `tool_call`, since neither capture has one -- checked directly again -- carrying `locations` and a `content` item of type `diff`; asserts `tool == "edit"`, `category == "file_change"`, and the path plus both `oldText`/`newText` sides all survive into the `tool_use` event's stringified `input`) and `TestWarningInfoTextClassification` (a synthetic `session.warning`/`session.info` raw event followed by a matching `"Warning: X"`/`"Info: X"` message block becomes one `diagnostic` carrying `code == "copilot.<warningType/infoType>"`; the same block with no raw event received first stays `text`). Also resolved, without a new test, the caution this part was queued with: "an `agentweave` server status `failed` emits one error" is D10's own rule (design.md:1066-1079), not D8's differently-sourced `copilot.hub_server_unverified` (design.md:1023, a `decide_permission`-side diagnostic, `test_permission_approver.py`'s file, tasks 1.6/1.7) -- so it is already covered by part 3/N's `TestMcpServerUnavailableDiagnostic`, not a gap. Confirmed still red at the same whole-file collection error; `ruff`/`black --target-version py311` clean; `openspec validate --strict` (npm CLI) passes. 2026-09-30 (part 5/N): added `TestSessionErrorRootVsSubagent`, the review/cross-slice subagent-error bullet: a synthetic root `session.error` (no `agentId` anywhere) whose matching `"Error: "` echo becomes `error_event(code="copilot_session_error")`, never `text`; a subagent's, tested via both named signals separately (envelope `agentId`, and `data.parentToolCallId`), becomes `diagnostic_event(code="copilot.subagent_error")` instead, also never `text` -- this slice's own direct `Error:`-match rule (design.md:986-994), symmetric with the already-tested `Warning:`/`Info:` rule, not slice 5's later different chunk-drop mechanism (design.md:1030-1034, explicitly that slice's to change). Turn failure/success is deliberately not asserted -- `on_raw_event`/`on_session_update` return `RunEvent`s, never a `TurnOutcome`, and `codex_appserver.py`'s own `run_turn` (`:1150-1195`, checked directly) decides `status`/`error` from raw notification types inline, not from a mapper's returned events, so that half of the bullet is task 1.9's (`test_copilot_acp_run_turn.py`) to answer, not this file's to force. Sanity-checked against a hand-written stand-in mapper outside pytest, same as parts 3-4. Confirmed still red at the same whole-file collection error; `ruff`/`black --target-version py311` clean; `openspec validate --strict` passes. **Correction, not a close-out: task 1.8 is still not fully covered.** Re-reading the Assert list fresh while writing this part found two bullets the part-3/N-to-part-4/N handoff silently dropped from its own running tally (part 3/N's `TestDiagnosticPayloadShape` docstring had explicitly flagged the model-substitution one as "left for a later part"; part 4/N's closing note and the `next_action` that queued this part both then claimed the subagent-error bullet was the *only* one left, which was wrong): (1) `session.model_change`/`session.auto_mode_resolved`/`session.tools_updated` and the model-substitution diagnostic (design.md:1096-1108) have no test in this file at all; (2) `user_message_chunk` is separately listed in the mapper's own "Dropped" set for `on_session_update` (design.md:977), which is mapper-testable regardless of the (out-of-scope) arming gate, and is not yet tested either. Left for part 6/N. Do not move to task 1.9 until both are closed here or explicitly ruled out of scope the same recorded way the D8-vs-D10 point was in part 4/N. 2026-09-30 (part 6/N): closed both gaps, re-reading design.md:1096-1108 and :977 fresh rather than off the correction's summary. Added `TestModelSubstitutionDiagnostic` (four cases over synthetic `session.tools_updated {model}` -- the shape the real capture actually shows, design.md:1084-1085; `session.model_change`/`session.auto_mode_resolved` never appear in either capture, checked directly, so their CODE-cited shapes are used only for the "first raw event wins" case): a resolved model differing from the requested one emits one `copilot.model_substituted` diagnostic (`severity="info"`); an unchanged model emits none; a requested model of `"auto"` emits none even when the resolved model differs; and the *first* of the three raw event types the mapper sees decides the resolved model, so a second, differently-shaped event afterward does not re-diagnose. Gives `CopilotEventMapper`'s constructor a second inferred keyword, `requested_model` (not named in design.md, carries `RpcTurnRequest.model`, design.md:1527, flagged the same way as `told_access_path`). The example message text and list format (design.md:1089-1091) are not asserted byte-exact, per this part's own caution -- only `code`/`severity`/`stream` and that both model names appear in `summary`. Added `TestUserMessageChunkDropped`: `on_session_update` returns nothing for a `user_message_chunk`, and one arriving mid-block neither flushes nor joins the still-open `agent_message_chunk` text (`flush()` afterward still yields exactly the agent text alone). The "before arming" half of the bullet stays explicitly out of this file's scope, same resolution as the `agentweave`-server-status bullet in part 4/N. Sanity-checked all six new assertions against a hand-written stand-in mapper outside pytest before trusting them, same as parts 3-5 (not committed, deleted after use). Confirmed still red at the same whole-file collection error, `ModuleNotFoundError: No module named 'hub.copilot_acp'`; `ruff`/`black --target-version py311` clean; `openspec validate --strict` (via the `openspec` CLI directly, not `npx`, which could not resolve an executable here) passes. **Task 1.8's Assert list is now fully covered**: every bullet below either has a direct test in this file, is explicitly out of this file's scope (the "before arming" half), or is already covered by another bullet's test (the `agentweave`-server-status bullet, part 4/N) -- re-verified against the literal list below, not a summary. Next: task 1.9 (`test_copilot_acp_run_turn.py`). Assert:
  - one `text` event per contiguous message block;
  - `tool_use` then `tool_result` with the same call id for the shell and the MCP call;
  - a streamed partial shell output emits nothing until the terminal update;
  - the edit's `tool_use` carries the file path and diff;
  - a replayed `user_message_chunk` before arming emits nothing;
  - a synthetic message `"Warning: X"` with a matching raw `session.warning` becomes `diagnostic`, and without one stays `text`;
  - an `agentweave` server status `failed` emits one error;
  - `session.model_change` to a different model emits one diagnostic;
  - (R3) an MCP `tool_call` whose raw `tool.execution_start` names `mcpServerName: "agentweave"`, `mcpToolName: "create_task"` (so `YDo` gives it kind `edit`) emits `tool_use` with `tool == "agentweave-create_task"` and category `mcp`, never `edit`/`file_change`;
  - (R3) every `diagnostic` payload carries `version`, `stream == "copilot"`, `severity` and `summary`;
  - (R3) an `agentweave` server status `failed` on a run whose `told_access_path` is `cli` emits a `copilot.mcp_server_unavailable` diagnostic, not the error;
  - (review, cross-slice) a `session.error` whose envelope carries `agentId` (and separately one whose `data` carries `parentToolCallId`) emits a `copilot.subagent_error` diagnostic, its `Error:` echo is dropped, and the mapper does not mark the turn failed; a root `session.error` still does.

  Reversing the order of a `tool_call` and its `tool_call_update` must make the correlation assertion fail (the CLAUDE.md ordering rule)
- [ ] 1.9 `hub/tests/test_copilot_acp_run_turn.py` (new): a scripted fake session in the style of `test_codex_appserver_run_turn.py`, whose `session/prompt` response is delivered **after** that turn's notifications, as Copilot does. 2026-09-30 (part 1/N): added `_FakeACPSession` (a single strictly-ordered script of `response`/`notification`/`server_request` entries, not two independent queues, since Copilot's `session/prompt` gates its result behind that turn's notifications and a fake that returned it instantly would leave the drain-during-the-call property untested) and `TestNewSessionSequence`, covering case (a) only: `initialize` → `session/new` (`mcpServers: []`) → `session/set_config_option agent` → `session/prompt` (context block first, byte-identical prompt last), in order, plus `on_session` binding before return and `ACPProcess.close(force=False)` on every exit (D17). `COPILOT_RAW_EVENTS`/`COPILOT_TURN_CONTEXT_HEAD` are design-cited names (D10 `:1130`, D5 `:479`); `run_turn`'s own keyword surface and `TurnOutcome`'s fields are this file's least-invented reading of D18's field lists, flagged for a future round. Confirmed red: whole-file collection failure, `ModuleNotFoundError: No module named 'hub.copilot_acp'`. 2026-09-30 (part 2/N): added `TestResumedSessionSequence`, case (b): `session/load` (not `session/new`) for a `resume_session_id`, and two placements of a replayed `user_message_chunk`/`agent_message_chunk` pair (before and after `session/load`'s own response, both strictly before `session/prompt`) both produce no event -- D7's "handled order-independently" line, tested both ways rather than just one. Neither evidence log captures a `session/load` that finds a session, so the replay shape and `session/load`'s success response are synthetic, flagged as such. Changed `_patch_spawn` to forward `run_turn`'s own `on_notification`/`on_server_request` kwargs onto the fake, so the handler a script's notifications reach is `run_turn`'s real one, not a test stand-in -- otherwise the "no event" assertions would pass vacuously regardless of what `run_turn` does. Sanity-checked against a throwaway stand-in, including a deliberately-broken arming gate re-run (failed as expected), before trusting. Confirmed still red at the same error; `ruff`/`black --target-version py311` clean; `openspec validate --strict` (openspec CLI directly) passes. 2026-09-30 (part 3/N): added `TestSessionLoadNotFoundRebinds`, case (c): `session/load` answered `-32002` (VERIFIED, `r1-probe-load.log:8-12`) is followed by exactly one `session/new` (D7's stated recovery, `:560`, not itself captured), a `copilot.session_missing` diagnostic (dead id in `summary`), a new `on_session_missing(old_id)` callback firing once, and `on_session` binding only the fresh id. Gave `_FakeACPSession` its first error-response script entry, `{"error": {"code", "message", "data"}}`, raised by `request()` as `CopilotACPError(message, code=code, data=data)` (design.md's stated translation, `:1175`, `.data` at `:1179`) -- reused verbatim by every later error-carrying case (k, n, o, p). Sanity-checked against a throwaway stand-in, including a deliberately-broken `on_session_missing` call re-run (failed as expected), before trusting. Confirmed still red at the same error; `ruff`/`black --target-version py311` clean; `openspec validate --strict` passes. 2026-09-30 (part 4/N): added `TestVersionGateFailsBeforeAnySessionRequest`, case (d): a Copilot CLI version below `COPILOT_MIN_VERSION` (`"1.0.81"`, asserted directly against the module constant, D12 `:1155`), or missing `agentInfo.version` entirely (`:1165`, "a missing version is treated as too old"), makes `run_turn` raise `CopilotACPError` with design.md's own verbatim message (`:1163-1165`, "Copilot CLI <v> is older than the supported 1.0.81. Update it with `copilot update` or npm.") before any second `request()` call -- proved by scripting only `initialize`'s response and relying on `_FakeACPSession`'s own "script exhausted" `AssertionError` to catch a real implementation that incorrectly sent `session/new`/`session/load` past the gate, rather than adding new fake machinery for it. The missing-version test asserts only the sentence's fixed half, not what stands in for `<v>` in that case, since design.md never states it -- inventing a literal there would be this file's guess, not design.md's. Both tests also assert `ACPProcess.close(force=False)` still happens on this path (D17: every exit, not only a normal one). Sanity-checked against a throwaway stand-in, including a deliberately-broken gate (`if False:` instead of the real comparison) re-run -- both tests failed as expected, on the fake's own `script exhausted before a response to 'session/new'` `AssertionError`, proving the assertions are evidence of the gate and not incidentally true regardless of it. Restored, re-ran clean, deleted the stand-in, confirmed red again at the same `ModuleNotFoundError`. `ruff`/`black --target-version py311` clean (black reformatted the new class once, then reported clean); `openspec validate a-copilot-agent-runs-over-acp --strict` (openspec CLI directly) passes. Task 1.9 stays **unchecked**. 2026-09-30 (part 5/N): added `TestFullAccessWithNoAllowAllOption`, case (e): under full access (`permission_mode="bypassPermissions"`), a `configOptions` list missing the `allow_all` option entirely (checked in both `session/new`'s and `session/set_config_option agent`'s own responses, since D8's earlier "after session/new/load" wording and its later, unified posture-step listing, `:815-844`, do not agree on which call's `configOptions` is actually read) makes `run_turn` skip trying to set it, emit one `copilot.full_access_withdrawn`/`warning` diagnostic carrying design.md's own verbatim sentence (`:804-806`) with the literal "no allow-all option was offered" bracketed half (this case never reaches a Copilot error message, so the other half is not exercised), and judge every subsequent request as `workspace` rather than defensively ALLOWing it -- proved with the same outside-workspace-edit technique `test_codex_appserver_run_turn.py` already uses for Codex (`test_an_outside_workspace_decline_is_reported`): a `session/request_permission` for an `edit` naming a path outside `workspace` gets `reject_once`, which full access's own defensive-ALLOW rule (D8, `:807-813`) would not produce. The `toolCall`/`options` wire shape is CODE-only (design.md:60-61, 74: neither evidence log has a captured `session/request_permission` at all), flagged synthetic the same way `test_copilot_acp_mapper.py`'s `TestEditDiffToolUse` flags its own edit fixture. Sanity-checked against a throwaway stand-in (`hub/hub/copilot_acp.py`, not committed) implementing the sequence through this diagnostic and permission decision: the new test passed against a correct stand-in, then failed as expected (on the `fake.sent_responses` assertion) against a deliberately-broken variant that always answered `allow_once` regardless of posture -- proving the assertion is evidence of the workspace judgment, not incidentally true. Restored, re-ran clean, deleted the stand-in, confirmed red again at the same `ModuleNotFoundError`. `ruff`/`black --target-version py311` clean; `openspec validate a-copilot-agent-runs-over-acp --strict` (openspec CLI directly) passes. **Correction, not a close-out:** re-counting the Assert list below fresh, rather than trusting the running tally, found it actually runs `(a)` through `(w)` -- 23 lettered cases, not the 18 (`a`-`s`) this task's module docstring and every earlier part's tally (part 3/N's "15 of 18", part 4/N's "14 of 18") stated. The module docstring (`test_copilot_acp_run_turn.py`'s opening comment) is corrected in this same commit. With (a)-(e) now covered, **18 cases remain: (f)-(w)**, not 13. 2026-09-30 (part 6/N): added `TestAgentMarkerMismatchFallsBackToResourceBlock`, case (f): an `agent` option whose description is not the marker -- D6's "foreign description" branch (design.md:498-517, the repository-agent-with-the-same-name scenario D6 itself states). Read D6 fresh by grepping "AGENT_MARKER"/"agent option"/"resource block" rather than assuming a line range, confirming the check's three conditions (`:500-506`), the fallback's exact `resource` content-block shape and diagnostic sentence (`:519-524`), and the separate deselect step (`:526-536`, review finding 6, tasks.md's own case (t)). Checked `test_copilot_context_split.py` first per this part's own queued caution: it does not exist yet (task 1.11 is still unbuilt, confirmed directly), so there is no existing coverage to avoid duplicating; this part scopes itself to what only `run_turn`'s wire behaviour can prove (the `session/prompt` block order and the diagnostic), not to the `stable`/`per_turn`/`tool_surface` split itself, which stays task 1.11's to test. Diagnostic code: re-derived from D10's table (`:1011-1025`) rather than assumed -- `copilot.agent_not_selected`/`warning` is the table's only row naming D6 at all (source column literally "D6 fallback"), covering every branch of D6's check by one code, so it does apply to this branch and is not reserved for a different "no agent selected" case as the previous part's note had flagged as open. The deselect call (D6's second half, case (t)'s own territory) is scripted so the turn can reach the prompt at all, but not asserted beyond that, per this part's own docstring. Ordering of the scripted deselect relative to `session/set_mode` follows design.md's explicit statement that the posture step runs "after new/load and agent selection (D6)" (`:815-821`), so the deselect precedes `session/set_mode` in the script. Sanity-checked against a throwaway stand-in (`hub/hub/copilot_acp.py`, not committed): the new test passed against a correct implementation, then failed as expected (on the `len(blocks) >= 3` assertion, `assert 2 >= 3`) against a deliberately-broken variant that skipped building the resource block -- proving the assertion is evidence of the resource-block fallback, not incidentally true. Restored, re-ran clean, deleted the stand-in, confirmed red again at the same `ModuleNotFoundError`. `ruff` and `black --check --target-version py311` both clean. `openspec validate a-copilot-agent-runs-over-acp --strict` (via the `openspec` CLI directly, not `npx`, which still cannot resolve an executable here) passes. With (a)-(f) now covered, **17 cases remain: (g)-(w)**. Task 1.9 stays unchecked. 2026-09-30 (part 7/N): added `TestStopSendsSessionCancelAndInterrupts`, case (g): stop. Read D17 fresh by grepping "session/cancel"/"stopReason"/"interrupted" rather than assuming a line range, landing on design.md:1481-1505 (not the two other hits the queued caution named as belonging to unrelated cases, `:841-843` posture escalation and `:1163` the version gate): a stop sends `session/cancel {sessionId}` as a **notification** (`:1486`, unlike Codex's `turn/interrupt`, which is a request), waits for the pending `session/prompt` to return `stopReason:"cancelled"` (`:1488`), maps that to `TurnOutcome.status == "interrupted"` (`:1493`, "as for Codex"), and closes with `terminate_process_tree(force=True)`, not `proc.kill()` (`:1489-1491`) -- the first case in this file where `closed_with_force` is asserted `True` rather than `False`. Flagged as this file's own least-invented reading: D18 names `should_interrupt` as one of `run_turn`'s callbacks (`:1514-1517`) but this file's fake has no notification-reading loop of its own (Copilot's notifications arrive via `on_notification` from *inside* the single `session/prompt` `request()` call, not a separate queue like Codex's), so the test places one otherwise-inert `session/update` notification ahead of `session/prompt`'s response to give a real implementation the only reentrant point this fake can offer while that call is pending. Built `_CancelOrderingFake`, a `_FakeACPSession` subclass instrumenting whether `session/cancel` is sent *before* the `session/prompt` `request()` call itself returns -- proving the notification precedes the response causally (CLAUDE.md's ordering rule), not merely appearing first in some unordered set; a `run_turn` that instead waited for the full response and only afterward decided to call `session/cancel` would produce the same final message set but fail this specific check. Sanity-checked against a throwaway stand-in (`hub/hub/copilot_acp.py`, not committed) three ways: passed against a correct implementation; failed as expected (`assert 0 == 1`, empty `sent_notifications`) against a variant that never sent `session/cancel` at all; failed as expected (the ordering assertion) against a variant that sent `session/cancel` only after `session/prompt`'s `request()` call had already returned. Restored, re-ran clean, deleted the stand-in, confirmed red again at the same `ModuleNotFoundError`. `ruff` and `black --check --target-version py311` both clean (black reformatted the new class once during this part; re-checked clean after). `openspec validate a-copilot-agent-runs-over-acp --strict` (openspec CLI directly) passes. With (a)-(g) now covered, **16 cases remain: (h)-(w)**. Task 1.9 stays unchecked. 2026-09-30 (part 8/N): added `TestEveryRequestPermissionAnsweredExactlyOnce`, case (h): every `session/request_permission` is answered exactly once. Tasks.md states only the bare bullet; design.md's own contract is D8 step 5 (`:597-600`), "answer through one function that writes the JSON-RPC response ...; every decision reaches the recorders, whichever step made it" -- one correlated response per request, never zero (dropped) and never more than one (double-answered), and the response for a given id is that id's own decision, not another request's. A single request answered correctly is not evidence of this (a `run_turn` that always sent one fixed response regardless of which request it answered would still pass a one-request script), so this part scripts **two** `session/request_permission` requests in one turn, judged to different outcomes under `workspace` (an `edit` inside the workspace and one outside, design.md:637 -- the same inside/outside-workspace distinguishing technique part 5/N's `TestFullAccessWithNoAllowAllOption` already uses for its own single request), each its own id and `toolCallId`, and asserts `fake.sent_responses` is exactly `[(1, allow_once), (2, reject_once)]` in order -- catching a dropped response, a double-answered id, or the two answers swapped, all of which this file's own harness (`_FakeACPSession`, appending one `(id, result)` pair per `server_request` script entry as its handler is invoked) makes directly observable. Sanity-checked against a throwaway stand-in (`hub/hub/copilot_acp.py`, not committed) four ways: (1) a correct implementation (judges each request by its own `toolCall` against the workspace) -- passed; (2) always-allow regardless of judgment -- failed as expected (index 1 mismatch, `reject_once` expected got `allow_once`); (3) the two decisions swapped (inside answered `reject_once`, outside answered `allow_once`) -- failed as expected (index 0 mismatch); (4) a stale-default bug answering only the first request by the real judge and hardcoding `allow_once` for any later one in the same turn -- failed as expected (index 1 mismatch), a distinct failure mode from (2) and (3). Restored the correct variant, re-ran clean, deleted the stand-in, confirmed red again at the same `ModuleNotFoundError`. `ruff` clean; `black --check --target-version py311` clean (no reformatting needed this time). `openspec validate a-copilot-agent-runs-over-acp --strict` (openspec CLI directly) passes. With (a)-(h) now covered, **15 cases remain: (i)-(w)**. Task 1.9 stays unchecked. Assert:
  - (a) new: `initialize` subscribes the D10 events, then `session/new` with `mcpServers: []`, then `set_config_option agent`, then the prompt with the per-turn block first;
  - (b) load: `session/load` is used, and replayed chunks before the prompt produce no event;
  - (c) load `-32002`: `session/new` follows and `on_session_missing` fires;
  - (d) version `1.0.75`: fails before any `session/*` request;
  - (e) full access with no `allow_all` option: a diagnostic, and requests are judged as `workspace`;
  - (f) an `agent` option whose description is not the marker: the stable context goes as a `resource` block, with a diagnostic;
  - (g) stop: `session/cancel` is sent, and `stopReason: cancelled` → `interrupted`;
  - (h) every `session/request_permission` is answered exactly once;
  - (i) `usage_update` → `on_usage` with a measured sample and the resolved model;
  - (j) a spec turn (consistency pass 2026-09-28, slice 3's D16): the spawn argv holds `--excluded-tools=apply_patch,edit,str_replace,str_replace_editor` (no `create`); under full access `allow_all` is **not** set on (read back `off`), and an `execute` request for a PowerShell command writing outside the workspace is REJECTed (judged as `workspace`; operator decision 2026-09-28, design open question 13); a `create` `edit` request for `x.py` is REJECTed and recorded through `_on_refusal`; with the switch patched on, `set_mode` carries the full plan URI before the prompt;
  - (k) (R2, narrowed in R3) a JSON-RPC `error` response to a request **before** the prompt (e.g. `session/new`) raises `CopilotACPError` carrying `.code` and `.data`, and it is an `AppServerError`;
  - (l) (R2, amended in R3) `initialize` sends `clientCapabilities._meta["github.com/copilot"].events` equal to `COPILOT_RAW_EVENTS`, de-duplicated, including `tool.execution_start`. There is no `on_raw_event` callback and no `prompt_usage`/`session_was_new` field (removed, design D10);
  - (m) (R2) the process tree is terminated on a failed turn too, not only on a stop;
  - (n) (R3) a `session/prompt` answered with a JSON-RPC error, and separately a process that exits after the prompt is written, each **return** `TurnOutcome(status="failed")` with the error and `stderr_tail`, and raise nothing;
  - (o) (R3) an armed raw `session.error` followed by `stopReason: end_turn` returns `status == "failed"` with the event's `message`. With `stopReason: cancelled` it is `interrupted`;
  - (p) (R3) `session/new` answered `-32000` raises, and `CopilotProbe`'s verdict reads not authorized before the raise propagates;
  - (q) (R3) the prompt's first text block is `per_turn_context` then `tool_surface_context`, and `control_overrides {"effort": "high"}` puts `--reasoning-effort high` on the spawn argv;
  - (r) (review, note 15 and the D5 answer) the first block opens with `COPILOT_TURN_CONTEXT_HEAD`; with `per_turn_context` and `tool_surface_context` both empty and the message `/allow-all on`, the prompt still has two blocks and the first does not start with `/`;
  - (s) (review, finding 4) a `session/load` response with `currentModeId` `#plan` on a non-spec turn → `set_mode #agent` is sent before the prompt; `#autopilot` likewise; `allow_all` `on` after load under `workspace` → `off` is set and read back; an `off` that reads back `on` → `run_turn` raises and **no** `session/prompt` is sent; an armed `session.mode_changed` into `#autopilot` under `workspace` → `session/cancel`, a `copilot_posture_escalated` error, status `failed`;
  - (t) (review, finding 6) an `agent` option whose description is not the marker → `set_config_option agent ""` is sent before the prompt; a deselect that does not read back `""` raises and sends no prompt;
  - (u) (review, finding 10) `build_acp_argv` with runner flags `--yolo --allow-tool=shell --add-dir C:\x --config-dir C:\y --deny-tool=x` under `workspace` keeps only `--deny-tool=x` and emits one `copilot.runner_flag_removed` per removed flag; under full access it keeps all but `--config-dir`;
  - (v) (review, finding 7) with `os.path.realpath` patched to sleep 2 s, a coroutine running beside the turn makes progress while a `path` request is decided (the judge runs in `asyncio.to_thread`);
  - (w) (review, finding 9) an armed `exit_plan_mode.requested` → `session/cancel`, a `copilot.plan_mode_exit_unanswerable` diagnostic, status `failed`; `SPEC_TURN_USES_PLAN_MODE` is `False`, so a spec turn sends `set_mode #agent`, not `#plan`, and still carries `--excluded-tools`

  2026-09-30 (part 1/N): built the fake-session harness, `_FakeACPSession`, and covered case (a)
  only. Unlike `test_codex_appserver_run_turn.py`'s `_FakeSession` (canned instant responses),
  `_FakeACPSession.request()` pops one strictly-ordered script, delivering any notification or
  server-request entry it passes over before returning the response entry -- reproducing directly,
  rather than asserting separately, that a `session/prompt` response arrives after that turn's
  notifications (`acp4…log`: request at line 5, result at line 54). `TestNewSessionSequence`
  asserts `initialize` < `session/new` < `session/set_config_option(agent)` < `session/prompt`
  by index (not a fixed full sequence: `session/set_mode`, which D8's posture step sends
  unconditionally after agent selection on every turn, is scripted with its real VERIFIED `{}`
  response so a real implementation calling it does not exhaust the script, but is otherwise
  unasserted here -- that is D8's own coverage, not case (a)'s four waypoints); that `initialize`'s
  subscribed-events list equals the module constant `COPILOT_RAW_EVENTS` itself, de-duplicated
  (not a re-derived copy of its contents, to avoid inventing a second, possibly-wrong list this
  file would then enforce); that `session/new`'s `mcpServers` is `[]`; and that `session/prompt`'s
  first content block opens with `COPILOT_TURN_CONTEXT_HEAD` and contains both `per_turn_context`
  and `tool_surface_context`, while its last block is the caller's `prompt` byte-identical. A
  second test proves the ordering assertion itself is real, not incidental, by feeding it a
  reversed method list and checking it fails (the CLAUDE.md ordering rule, applied here since
  `_FakeACPSession` makes reordering the fixture, not the real routing, the thing under test).
  Every symbol imported (`run_turn`, `ACPProcess`, `TurnOutcome`, `COPILOT_RAW_EVENTS`,
  `COPILOT_TURN_CONTEXT_HEAD`) is checked in the file's own docstring against design.md citations
  where one exists (`ACPProcess.close()`, D17 `:1502`; `COPILOT_RAW_EVENTS`, D10 `:1130`;
  `COPILOT_TURN_CONTEXT_HEAD`, the D5 review note `:479`) and flagged INFERRED otherwise
  (`run_turn`'s keyword surface, mirrored from D18's `RpcTurnRequest`/`RpcCallbacks` field names
  and from `codex_appserver.run_turn`'s analogous shape). Sanity-checked both tests against a
  throwaway stand-in `copilot_acp.py` (not committed, deleted after use) before trusting them, same
  discipline as 1.8. Confirmed red: `ModuleNotFoundError: No module named 'hub.copilot_acp'`
  (checked directly: neither `hub/hub/copilot_acp.py` nor `hub/hub/copilot_probe.py` exist).
  `ruff`/`black --target-version py311` clean; `openspec validate --strict` (via the `openspec`
  CLI directly) passes. Cases (b)-(s), 17 of the 18 lettered cases, remain for later parts.

  2026-09-30 (part 2/N): covered case (b) only. Read D7's *Replay* and *A load that finds nothing*
  paragraphs fresh, plus the Uncertainties table's own line 96 ("Whether session history replay on
  `session/load` arrives entirely before the load response | INFERRED (ACP spec) | handled
  order-independently, D7"). Added `TestResumedSessionSequence` with two tests, not one, because
  that line's "order-independently" claim is untestable by a single ordering: one delivers both
  replayed `user_message_chunk`/`agent_message_chunk` `session/update` notifications while
  `session/load` itself is still in flight (the same slot `r1-probe-load.log:9-10` proves is real
  for a *different* notification, `available_commands_update`, on case (c)'s own -32002 path, not
  case (b)); the other delivers them after `session/load`'s response but still before
  `session/prompt` is written (D7's actual line, "any update before that point ... is dropped" --
  not "before the load response" specifically). Both assert `events == []`, that `session/load`
  (not `session/new`) was sent with `sessionId`/`cwd`/`mcpServers: []`, `on_session` binds the
  resumed id, and the outcome is `TurnOutcome(status="completed")`. Neither evidence log captures a
  `session/load` that actually finds a session (`r1-probe-load.log`'s two calls both target an
  unprompted id and get -32002, checked directly), so the replayed-chunk notifications and the
  `session/load` success response body are synthetic, built from D7's own named update types and
  the mapper's already-known `session/update` shape, and from `session/new`'s own response shape by
  symmetry (D7 says nothing about `session/load`'s response body) -- flagged in the new code's own
  docstrings, not asserted as captured.

  This part also changes `_patch_spawn` (shared with part 1/N's test class): it now forwards
  whatever `on_notification`/`on_server_request` keywords `run_turn`'s own `ACPProcess.spawn` call
  supplies onto the fake, instead of ignoring them, because the property under test -- what
  `run_turn`'s own arming gate does with a delivered update -- is only real if the handler the
  fake invokes is `run_turn`'s, not a test-written stand-in. `ACPProcess.spawn` taking these two
  keywords is this file's own least-invented reading (unconfirmed against any design.md citation,
  same status as `run_turn`'s other inferred surfaces); if the real module wires notification
  delivery some other way, a script with notification entries fails loudly rather than passing
  vacuously, flagged for a future part or round to resolve either way. Sanity-checked all four
  tests in this file (parts 1/N and 2/N together) against a throwaway stand-in `copilot_acp.py`
  (not committed, deleted after use): first confirmed all four pass against a correct stand-in,
  then re-confirmed the two new tests fail when the stand-in's arming flag is deliberately broken
  (started `True` instead of `False`) -- the CLAUDE.md ordering-rule discipline, applied here to an
  arming gate rather than a method-order fixture. Confirmed still red at the same
  `ModuleNotFoundError: No module named 'hub.copilot_acp'` after deleting the stand-in;
  `ruff`/`black --target-version py311` clean; `openspec validate --strict` (via the `openspec` CLI
  directly) passes. Cases (c)-(s), 16 of 18, remain for later parts.

  2026-09-30 (part 3/N): covered case (c) only. Read D7's *A load that finds nothing* paragraph
  (design.md:556-568) and `r1-probe-load.log:8-12` fresh. The `-32002` half is VERIFIED, reused
  verbatim from that capture (`code`, `message`, `data`); the "`session/new` follows" half is not
  captured (that log goes straight to a doomed `session/prompt` on the dead id instead, itself
  erroring `-32602`, an unrelated error this case does not cover) -- it is D7's own stated recovery
  path, synthetic in the same sense case (b)'s replayed-chunk shape was, flagged as such rather than
  asserted as captured. Added `TestSessionLoadNotFoundRebinds` with one test:
  `session/load` answered `-32002` is followed by exactly one `session/new` (never two, never a
  hang); the fake's `session/load` params still name the dead `RESUME_ID`; the fake's `session/new`
  params carry the fresh `cwd`/`mcpServers: []`; a `diagnostic` event with
  `payload["code"] == "copilot.session_missing"`, `severity == "info"` and the dead id in `summary`
  appears in `on_event`'s collected list; `on_session_missing` (a new callback this test adds
  alongside `on_event`/`on_session`) receives exactly the dead id; `on_session` binds only the new
  id, once; and the turn still completes normally afterward (`session/set_config_option agent`,
  `session/set_mode`, `session/prompt` all still fire on the new id).

  This part also gives `_FakeACPSession` its first error-response script entry,
  `{"error": {"code", "message", "data"}}`, which raises `CopilotACPError(message, code=code,
  data=data)` from `request()` instead of returning -- mirroring design.md's own stated translation
  ("`ACPProcess.request` raises `CopilotACPError(code=<error.code>)` for a response holding
  `error`", `:1175`, R3 adds `.data`, `:1179`). Until this part every script in the file only ever
  used success `response` dicts, so a JSON-RPC error path had no way to be scripted at all; cases
  (k), (n), (o), (p) will reuse this same entry shape rather than inventing a second one.

  Sanity-checked before trusting: wrote a throwaway stand-in `hub/hub/copilot_acp.py` (not
  committed) implementing the sequence, the `-32002` catch-and-rebind branch, and the diagnostic/
  callback emissions under test; all five tests in the file (parts 1/N-3/N together) passed. Then
  deliberately broke the stand-in (the `-32002` branch stopped calling `on_session_missing`) and
  re-ran with `-k TestSessionLoadNotFoundRebinds`: the new test failed as expected (on the
  `sessions_missing == [RESUME_ID]` assertion) while the other four tests were unaffected -- the
  CLAUDE.md ordering-rule discipline, applied here to a rebinding callback rather than a method-
  order fixture, so the new assertion is evidence of the callback firing, not incidentally true
  regardless of it. Restored the fix, re-ran (all five passed again), deleted the stand-in and
  re-ran: confirmed red again at the same `ModuleNotFoundError: No module named 'hub.copilot_acp'`.
  `ruff`/`black --target-version py311` clean; `openspec validate --strict` (via the `openspec` CLI
  directly) passes, both before and after this edit. Cases (d)-(s), 15 of 18, remain for later
  parts.
- [ ] 1.10 `hub/tests/test_copilot_home.py` (new): `copilot_home_path` is `…/copilot-home/projects/<pid>/<agent>` and refuses a project id of `..`, `a/b`, `a\b` or one resolving outside the root (R2); the worker home is `…/copilot-home/worker`. `ensure_copilot_home` writes `agents/<agent>.agent.md` with frontmatter `name`, `description` (the marker), `tools`, `model` (omitted for `auto`) and `reasoningEffort`, and a body that opens with the precedence statement and holds the stable context. It also writes `agentweave-mcp.json` with no `env` and `timeout == (agents.MAX_WAITING_SECONDS + 60) * 1000`. A second call with the same content does not rewrite the file (mtime unchanged). No file contains an `aw_run_` string. (Review, finding 8) With `hooks/allow.json`, `settings.json`, `mcp-config.json`, `installed-plugins/p/`, `agents/other.agent.md` and a `config.json` holding `trustedFolders` and `firstLaunchAt` placed in the home, `ensure_copilot_home` removes the first five, drops `trustedFolders` and keeps `firstLaunchAt`, leaves `session-state/` alone, and reports what it removed; a hook recorded in `.agentweave-owned.json` survives, and the same path with changed content is removed
- [ ] 1.11 `hub/tests/test_copilot_context_split.py` (new):
  - `_render_hub_agent_context`'s `stable`, `per_turn` and `tool_surface` (R3) together hold every `##`/`###` section of `context` exactly once;
  - the charter and project instructions are in `stable`;
  - the workspace is in `per_turn`, and the tool surface only in `tool_surface`;
  - `context` for a Claude run equals a snapshot taken before the change (write the snapshot as the first step of this task, from today's code)
- [ ] 1.12 `hub/tests/test_model_catalog.py`: `get_provider("copilot")` exists, its default model is `auto` labelled "Auto", every model's `context_window is None`, its Permissions values and labels equal Codex's with default `workspace` (R2), and `validate_overrides("copilot", {"model": "bogus-model"})` is refused
- [ ] 1.13 `hub/tests/test_workspace_writes.py`: `written_paths("edit", {"locations": [{"path": "C:/elsewhere/x.py"}], …})` returns that path, and `delete`/`move` likewise. `"shell"` returns `()`. `OutsideWriteRecorder` records a Copilot edit outside the workspace
- [ ] 1.14 `hub/tests/test_worker.py` and `test_conversation_titles.py`:
  - `build_worker_command(cli="copilot", …)` returns design D14's argv (the resolved `.exe`, not the npm shim, with `--no-custom-instructions`);
  - `build_title_command` returns it without `--no-custom-instructions`;
  - `parse_copilot_envelope` on the 1.2 fixture returns `"ok"`;
  - `copilot` is in both supported sets;
  - (R2) neither argv contains `--available-tools`, and both contain `--excluded-tools=builtin:*,mcp:*,custom:*`;
  - (R2) a Copilot conversation titled from the 1.2 fixture gets the answer, not a JSON fragment (`generate_conversation_title` with `_run_titler` patched to return the fixture);
  - (R2, mechanism fixed in R3) with `resolve_copilot_executable` raising `CopilotExecutableNotFound` (a `FileNotFoundError`), `run_worker` returns `spawn_failed` (not `unsupported_cli`) naming the looked-for path, raises nothing and removes its temporary directory, and titling returns `None`;
  - (R2) the spawn helpers pass the Copilot environment (`COPILOT_HOME` = the worker home, no `GH_TOKEN`) and still pass `env=None` for Claude and Codex
- [ ] 1.15 `hub/tests/test_launchability.py`:
  - with `GH_TOKEN` unset and a cached probe verdict "signed in, 1.0.88", `probe_agent` for `copilot` is runnable (today it says "No GitHub auth token found");
  - "not signed in" → not authorized, with the `copilot login` sentence;
  - "1.0.75" → not authorized, with the version sentence;
  - pending → runnable with `verdict_pending: True`;
  - (review, finding 11) a cached "not signed in" verdict younger than the TTL: a read returns it **and** schedules a refresh; a second read within 5 s schedules none; a positive verdict younger than the TTL schedules none. The probe's argv carries `--disable-builtin-mcps`
- [ ] 1.16 `hub/tests/test_runner_command_env.py`: `resolve_agent_env("copilot", {})` with `GH_TOKEN`/`GITHUB_TOKEN`/`COPILOT_GITHUB_TOKEN` in `os.environ` returns an environment without them. With `env_vars: {"COPILOT_GITHUB_TOKEN": "COPILOT_GITHUB_TOKEN"}` that variable is kept. Claude's environment is unchanged. (Review, finding 3) `COPILOT_ALLOW_ALL=true` ambient, and separately in `env_vars`, is absent from the result under every posture, and the `env_vars` case is reported as removed (the turn's `copilot.permission_override_removed` diagnostic); the same for every name in `COPILOT_TRUST_ENV_NAMES`; `COPILOT_HOME` in `env_vars` does not survive over the Hub's. (Consistency pass 2026-09-28, slice 5's 2.10) Ambient `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_BEARER_TOKEN`, `COPILOT_PROVIDER_WIRE_MODEL`, `COPILOT_MODEL` and `COPILOT_OFFLINE`, and the same names in `env_vars`, are absent under every posture (the `env_vars` case reported as removed). The one-shot environment (`one_shot_env`) and the probe's environment pass through the same function
- [ ] 1.17 `hub/tests/test_mcp_server_stdio_surface.py`: spawn `mcp_server.py` as the Hub does, with `HUB_URL` on a dead port. Send `{"jsonrpc":"2.0","id":0,"method":"server/discover","params":{}}` **before** `initialize`. Assert a JSON-RPC error response with id 0 (not a crash, not silence). Then `initialize` with `protocolVersion "2025-11-25"` succeeds and `tools/list` lists `send_message`.

  This test documents behaviour R1 measured (design § VERIFIED). It passes today and is a guard, which it says in its docstring
- [ ] 1.18 `hub/tests/test_tool_surface_matches_server.py`: a Copilot run in the MCP form names every tool `agentweave-<tool>`, and the access notice does too. **Depends on** `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` having landed. If it has not, leave this unchecked and say so
- [ ] 1.19 UI tests:
  - `hub/ui/src/__tests__/` asserts `providerForRunner('copilot') === 'copilot'`;
  - `ProviderMark` renders an SVG, not initials, for `copilot`;
  - the Runners page's CLI select offers `copilot`;
  - (R2) an `AgentTimeline` tool row with `tool: "edit"` is rendered as a writing block.

  Extend `modelCatalogFixture.ts` with the Copilot provider. Verify: `cd hub/ui && npx vitest run`
- [ ] 1.20 **Probe (no model call; review 2026-09-28, finding 6).** Under a scratch `COPILOT_HOME`, in a scratch git repository holding `.mcp.json` and `.github/agents/<agent>.agent.md` whose `mcp-servers` both name a stand-in server `agentweave`, spawn `copilot.exe --acp` with the Hub's `--additional-mcp-config` (dead `HUB_URL`) and `COPILOT_ALLOW_ALL` unset. Run `initialize` (subscribing `session.mcp_servers_loaded`), `session/new`, select then deselect the agent, and `session/close`. Record in the Round log which `agentweave` loaded and with what `source`/`transport`, whether the repository agent's `mcp-servers` loaded at all in an untrusted folder, and whether deselecting it changed the loaded servers. The result fixes D8's accepted `source`

## 2. Registry, migration, seeding, catalog

- [ ] 2.1 `db/models.py`: `RUNNER_CLIS = ("claude", "codex", "copilot")`, and the `ck_runners_cli` constraint is written from `RUNNER_CLIS`, so the two cannot drift
- [ ] 2.2 A new migration, the next free revision after tonight's queue, recreates `runners` with the widened constraint (`batch_alter_table(recreate="always")`) and guards a missing table. Downgrade refuses when a `copilot` row exists. Bump `HEAD_REVISION` in `hub/tests/test_migrations.py` and the head in `hub/tests/test_project_persistence.py` (`.claude/rules/db-migrations.md`)
  - Verify: `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py hub/tests/test_runners_api.py -q`
- [ ] 2.3 Confirm both seeders produce `Copilot (default)`. Task 1.4 passes
- [ ] 2.4 `model_catalog.py`: add `CATALOG["copilot"]` per design D13, taking the model tuple from `evidence/help-config.txt`, with the Permissions default `workspace`. Add `"copilot": "copilot"` to `runner_commands._CATALOG_PROVIDER_BY_RUNNER` (or slice 1's `catalog_provider`) and `copilot` to `SUPPORTED_RUNNERS` (`test_model_catalog.py:16-18` requires it). R2: drift is checked by a `--provider copilot` section in `scripts/check_model_catalog.py` that runs `copilot help config`, **not** by a pytest that skips without the binary (that script's docstring says why). Tasks 1.12 and 1.3 pass
  - Verify: `py -3.11 -m pytest hub/tests/test_model_catalog.py hub/tests/test_model_catalog_api.py -q`

## 3. Executable, probe, launchability

- [ ] 3.1 `hub/hub/copilot_probe.py`: `resolve_copilot_executable` (design D2). Task 1.5 passes
- [ ] 3.2 `CopilotProbe`: a cached, TTL'd, async refresh using `initialize` → `session/new` → `session/close` under the worker home, with no model call (design D15). R2: the refresh is scheduled by `CopilotProbe.verdict()` itself whenever the verdict is stale and a loop is running, so all six `probe_agent` callers keep it fresh; amend `get_agents_launchability`'s "never spawns anything" docstring. Test its refresh against a fake process
- [ ] 3.3 `launchability.py`: delete the env-token branch (`:116-126`) with its tests (`test_launchability.py:124-140`) and (R3, slice 1 D5) the `RUNNER_CLI["copilot"]` row, make `probe_agent` read the Copilot verdict (its `cli` the resolved path; an unclassified refresh failure leaves the verdict unchanged and adds `probe_error`, design D15), add `copilot` to `MCP_INJECTABLE_RUNNERS` (`:230`; R2: without it no Copilot run is given the MCP server), and extend `resolve_agent_env` with the GitHub-token strip and (review 2026-09-28) the unconditional `COPILOT_TRUST_ENV_NAMES` strip and (consistency pass 2026-09-28) the no-provider `COPILOT_PROVIDER_*`/`COPILOT_MODEL`/`COPILOT_OFFLINE` strip, with `COPILOT_HOME` set after `env_vars` (design D3). Tasks 1.15 and 1.16 pass
  - Verify: `py -3.11 -m pytest hub/tests/test_launchability.py hub/tests/test_runner_command_env.py hub/tests/test_copilot_probe.py -q`

## 4. The Hub-owned Copilot home and the context split

- [ ] 4.1 `_render_hub_agent_context` returns `stable` and `per_turn` beside the unchanged `context` (design D5). Task 1.11 passes
- [ ] 4.2 `hub/hub/copilot_home.py`: `copilot_home_path` and `ensure_copilot_home` (design D4), including (review) the configuration-surface sweep and the `.agentweave-owned.json` recorder. Task 1.10 passes
- [ ] 4.3 Call `ensure_copilot_home` after `create_operator_agent` commits and after `PATCH /agents/{name}` commits, for a Copilot-bound agent: on create after the `agent_created` broadcast (`agents.py:758`), on PATCH before the `schedule_agent` re-drain (`:2720`). **Any** exception is logged and does not fail the route (R3: not only `OSError`). Not after `POST /agents/request`, design D4 (R3). Add route tests: creating a Copilot agent produces the agent file; a patched write raising `OSError`, and one raising `RuntimeError`, each still return 201 and broadcast `agent_created`
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_home.py hub/tests/test_copilot_context_split.py -q`

## 5. Approvals

- [ ] 5.1 `mcp_server.py`: add keyword-only `workspace`/`hub_url` to `_decide`, and thread `hub_url` through `_read_command`, `_judge_word`, `_judge_url` and `_is_own_hub` (R2: all five; `HUB_URL` is read at `:1191` and `:1241`), defaulting to the environment. Add no import (`.claude/rules/mcp-server.md`). Task 1.7 passes, and `test_permission_approver.py` and `test_mcp_server.py` are otherwise unchanged
- [ ] 5.2 `copilot_acp.decide_permission` (design D8), with the per-kind operator-card labels beside `_CODEX_APPROVAL_LABELS`; (review) the client and `workspace_verdict` call it through `asyncio.to_thread`. Task 1.6 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_acp_decide.py hub/tests/test_permission_approver.py hub/tests/test_mcp_server.py -q`

## 6. The ACP transport

- [ ] 6.1 `runner_events.diagnostic_event(*, stream, severity, summary, code=None, facts=None)` (R3: slice 5's shape, which `agent-stream-events` requires) in the closed set, with a test that its payload has `version`, `stream`, `severity` and `summary`. `copilot_acp.CopilotEventMapper` (design D10). Task 1.8 passes
- [ ] 6.2 `copilot_acp.ACPProcess`: stdio JSON-RPC as `AppServerProcess`, UTF-8, stderr drained, and a pending-request map. It additionally supports a request whose response is awaited while notifications are drained, and handles agent→client requests. `close()` ends the process tree with `terminate_process_tree`. Test it against a stand-in script, as `test_codex_appserver_process.py` does
- [ ] 6.3 `copilot_acp.build_acp_argv` and `run_turn` (design D3, D6, D7, D9, D11, D12, D17). Task 1.9 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_copilot_acp_mapper.py hub/tests/test_copilot_acp_run_turn.py -q`

## 7. Wiring into the trigger

- [ ] 7.1 If slice 1 did not already make `_execute_codex_appserver_run` a runner-parameterised RPC executor, do that first: replace the four `runner="codex"` literals (`agent_trigger.py:3089`, `:3261`, `:3350`, `:3445`) with the adapter's name, and `codex_run_turn` with the adapter's `run_turn`. Run the whole Codex app-server suite unchanged
  - Verify: `py -3.11 -m pytest hub/tests/test_codex_appserver_run_turn.py hub/tests/test_codex_appserver.py -q`
- [ ] 7.2 In `trigger_agent_directly`, a `copilot` runner:
  - resolves the executable (a `TriggerAgentError(409, agent_wide=True)` with the probe's sentence when absent);
  - ensures its home with this turn's model and effort (`TriggerAgentError(409, agent_wide=True)` on failure; R3);
  - sets `COPILOT_HOME` in the environment;
  - sends the per-turn block and the prompt;
  - reaches the RPC executor with the Copilot adapter.

  `on_session_missing` rebinds under design D7's exception. Add `_bind_session_id(replace_missing=True)`. Add a trigger-level test with the adapter's `run_turn` patched, asserting `Run.session_id` and `Conversation.provider_session_id` after a rebind.

  R2: first admit `copilot` past the three gates of design D1: `SUPPORTED_RUNNERS` (`agent_trigger.py:773`, 501 today), the `build_command` call (`:1214`, 501 at `:1230`; skipped for an RPC transport) and `MCP_INJECTABLE_RUNNERS` (task 3.3). The trigger-level test enters through `trigger_agent_directly`, not the executor, and asserts the patched `run_turn` received a non-`None` `mcp_command` and the per-turn block. It fails today with 501. (R3) A route test through `POST /agent/trigger` with the home write patched to fail asserts **200** `status: "queued"` with the sentence in `waiting_reason`, and that the queue entry's delivery attempts are unchanged
- [ ] 7.3 Route an operator card for `ASK_OPERATOR` through `_await_operator_permission` with Copilot's labels (and its `workspace` verdict once `an-ask-me-card-says-what-workspace-only-would-decide` lands). Route refusals through `_on_refusal`, and allows through the `on_decision` callback whose executor side is `permission_tally.note`/`write_counts` from `a-run-records-that-its-calls-were-allowed` (R2: unbuilt at R2; if still unbuilt at IMPL, record refusals only and say so)
  - Verify: `py -3.11 -m pytest hub/tests -q -k "copilot or appserver or trigger"`

## 8. Outside writes, one-shot calls, tool names, display

- [ ] 8.1 `workspace_writes.py`: `COPILOT_WRITE_TOOLS = {"edit", "delete", "move"}` reading `locations[].path`, added to `WRITE_TOOLS`. Task 1.13 passes
- [ ] 8.2 `worker.py`: add the `copilot` branch, `parse_copilot_envelope` and the worker-home environment; `_run_worker_process` and `_run_titler` gain an `env` parameter (R2: neither passes one today). `conversation_titles.py` gets its `copilot` branch and parses the envelope before `title_from_output` (design D14). The builders catch a resolution failure rather than raise. Task 1.14 passes
  - Verify: `py -3.11 -m pytest hub/tests/test_worker.py hub/tests/test_conversation_titles.py hub/tests/test_title_generation.py -q`
- [ ] 8.3 The tool surface uses the `agentweave-` prefix and Copilot preamble for Copilot runs (design D16), through the mechanism of `a-claude-run-is-told-its-agentweave-tools-by-their-full-names`. Task 1.18 passes
- [ ] 8.4 `api/v1/agents.py` `_display_model` gains `"copilot": agent_meta.get("model", "GitHub Copilot")`
- [ ] 8.5 CI parity: `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`, `py -3.11 -m pytest hub/tests/ -q`. With `claude` stripped from `PATH`, re-run the Copilot tests to confirm they do not depend on a local CLI (memory: the local suite is green because `claude` is on `PATH`)

## 9. UI

- [ ] 9.1 `RunnerCli`, `CLI_OPTIONS`, `providerForRunner`, `PROVIDER_MARKS.copilot` from `siGithubcopilot` in `currentColor`, and (R2) `AgentTimeline.tsx`'s `WRITING_TOOLS`/`TOOL_ICON` gain `edit`, `delete`, `move` (design D19). Task 1.19 passes
- [ ] 9.2 `cd hub/ui && npm run lint && npx vitest run && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`. Commit `hub/ui/src` and `hub/hub/static/ui` together (`.claude/rules/hub-ui.md`)

## 10. Findings and docs

- [ ] 10.1 Record in `spec-queue/` FINDINGS the appendix corrections from the Round log (R1: `--no-auto-update` version, `~/.agents/skills`, the MCP 30 s timeout; R2: an empty `--available-tools=` means no filter, project-level custom agents outrank `$COPILOT_HOME/agents`), so later slices do not inherit them. From the review (2026-09-28), also file:
  - Copilot auto-approves shell commands it classes read-only, so a Copilot run's Workspace only judges fewer commands than Claude's (parity measured, not assumed; cite 1.1's `Get-ChildItem` record);
  - `_decide` resolves UNC and device paths with `realpath` before refusing them, which blocks ~21 s per unreachable host and opens an SMB connection from whichever process judges; it should refuse `\\`, `//`, `\\?\` and `\\.\` before any I/O, for every runner

## 11. Drive on the trial Hub `:8010`

Start it **from `hub/`, from source**, never through `agentweave --port 8010`, and never touch `:8000`:
`cd hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/trial/agentweave.db" py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1`.
Confirm the database it serves before trusting it (`.claude/reference/hubs.md`).

Copilot **Free plan**, Auto only: this group spends **at most four** model prompts. Keep every prompt tiny, and record each prompt's cost in the drive notes.

- [ ] 11.1 No model call. Check the following:
  - the Runners page offers `copilot`;
  - create a Copilot runner, then a Copilot agent `cop-1` on it with a short charter;
  - `~/.agentweave/hub/copilot-home/projects/proj-d85a82bf4216/cop-1/agents/cop-1.agent.md` exists (confirm the trial Hub's project id first) and holds the charter and the precedence statement, and the repository has no new file;
  - launchability for `copilot` reads runnable and names no token.
- [ ] 11.2 **Prompt 1.** Under Workspace only, send `cop-1`: *"Create hello.txt containing hi in your workspace, then send me a one-line message with agentweave-send_message."* Record the timeline verbatim:
  - one text block per message;
  - the edit's tool row with its path;
  - the message arriving in the operator inbox;
  - a context reading with a limit;
  - the Auto-substitution diagnostic, if any;
  - no replayed history.

  Then confirm `Conversation.provider_session_id` is set.
- [ ] 11.3 **Prompt 2.** A specification turn, with `SPEC_TURN_USES_PLAN_MODE` switched **on for this drive only** (it ships off, design D9): open an empty spec document and ask `cop-1` one question about it. Check: it interviews rather than writing a plan file; it has no editing tool but `create`, and any file it tries to create is refused (design D9 item 1a); whether `exit_plan_mode` was called and whether `exit_plan_mode.requested` reached the client (and so cancelled the turn); and that the next, non-spec turn of the conversation (11.4) starts in `#agent`. Leave the constant `False` unless neither the interview nor the ending suffered; turning it on is a commit citing this drive. If the turn was cancelled, file a finding and re-run with prompt 3 with the constant off.
- [ ] 11.4 **Prompt 3.** Under Ask me, in the same conversation (a resume), ask for `echo hi` in the shell. An operator card opens. Deny it: the timeline shows the refusal, the run completes, and the first turn's output is not rendered again.
- [ ] 11.5 **Prompt 4 (only if unused).** Stop a running turn with the stop button during a long request. The run ends `stopped`, and no `copilot.exe` or `powershell.exe` child of it survives: check with `Get-Process`.
- [ ] 11.6 Write the drive notes into `design.md`'s Round log (prompts spent, what matched, what did not). File every mismatch as a finding. Measure Open question 5 from the context readings of 11.2 and 11.4.

## 12. Archive

- [ ] 12.1 All tasks above checked, or explicitly deferred with a finding. `openspec validate a-copilot-agent-runs-over-acp --strict` passes. Sync the deltas into `openspec/specs/` (`openspec-sync-specs`) and archive (`openspec-archive-change`). Write the handoff per the handoff-cadence rule
