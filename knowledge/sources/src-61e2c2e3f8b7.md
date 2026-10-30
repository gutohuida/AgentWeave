## F470 (D) — `each-runner-cli-is-one-adapter`'s design.md predates a same-named function `a-copilot-agent-runs-over-acp` already added

**Status:** fixed by task 3.4, filed 2026-09-30/10-01 from the night window's ORDER 1/24 task 1.4, reading `agent_trigger.py` closely enough to build the RPC golden. Task 3.4 took the second option this finding's own last paragraph named: `_execute_rpc_run` kept its `runner`/`start_turn`/`refusal_label` signature (Copilot's `_execute_copilot_run` still calls it that way, unchanged) and gained `adapter`/`transport` as two new leading positional parameters, mutually exclusive with the explicit style. `RpcCallbacks` was *not* moved into `hub.runner_adapters.base` — the two dataclasses of that name (agent_trigger's, with `on_session_missing`; base's, with `request_approval`) stayed separate, and the adapter branch translates between them at the boundary (builds `base.RpcCallbacks` from the local `cb` plus a `request_approval` closure, right before calling `transport.run_turn`). `_execute_codex_appserver_run` was deleted outright, not kept as a thin wrapper, because `test_runner_adapters_rpc.py` (task 1.4's own golden test, read fresh before implementing) already called `agent_trigger._execute_rpc_run(get_adapter("codex"), CodexAppServerTransport(), **inputs)` directly — the test file's own docstring stated the exact target shape.

`each-runner-cli-is-one-adapter`'s design.md D9 (R3 pass, 2026-09-28) says `_execute_codex_appserver_run` "→ `_execute_rpc_run(adapter, transport, …)`", describing it as a new function slice 1's group 2 will add. But `a-copilot-agent-runs-over-acp` (archived 2026-09-30, after that R3 pass) already added a function of that exact name at `agent_trigger.py:3386` — signature `(*, runner: str, start_turn: Callable[[RpcCallbacks], Awaitable[Any]], refusal_label, project_id, agent, run_id, conversation_id, model, work_dir, known_session_id, env, worktree, repo_root=None, pre_turn_events=())` — plus a local `RpcCallbacks` dataclass at `:3110` (with `on_session_missing`, beyond D1's field list) and `_execute_copilot_run` (`:3304`) that already calls it for Copilot's ACP turns. The `RpcCallbacks` docstring says so directly: *"slice 1's `RpcCallbacks`, built here because slice 1 is not; `a-copilot-agent-runs-over-acp` task 7.1"* — this was a deliberate, documented placeholder, not an oversight, but `each-runner-cli-is-one-adapter`'s own design.md/tasks.md never mention it because the ACP change landed after the last re-read.

Group 2 of `each-runner-cli-is-one-adapter` (not yet reached tonight — group 1 is goldens/tests only) cannot simply add a second `_execute_rpc_run(adapter, transport, …)`; it would collide with the existing name and strand `_execute_copilot_run`'s call. It has to move today's `RpcCallbacks` into `hub.runner_adapters.base` and fold the adapter/transport-taking shape into the existing `runner`/`start_turn`/`refusal_label` signature (or thread `adapter`/`transport` through it) so Copilot's ACP path keeps working. Re-read `agent_trigger.py:3110-3420` fresh at that point rather than trusting design.md's D9 text alone.

## F471 (D) — `each-runner-cli-is-one-adapter`'s D2 assumed `RUNNER_CLIS`/`CATALOG` stay 2-wide; migration 0112 already widened both

**Status:** fixed bfdc72a (task 3.7, `CopilotAdapter`; operator's decision 2026-10-01, DECISIONS `f471-copilot-adapter`), filed 2026-10-01 from the night window's ORDER 1/24 task 1.5, writing `hub/tests/test_runner_adapters_conformance.py`.

Design D2 (R1-R3, last touched 2026-09-28) states: *"`RUNNER_CLIS = ("claude", "codex")` (`db/models.py:311`) stays where it is"*, and task 1.5(a)/(b) spell out the same 2-tuple literally (`["claude", "codex"]`). D1 builds `ADAPTERS` as exactly `{"claude": ClaudeAdapter(), "codex": CodexAdapter()}` for this slice — "this change touches no Copilot code" is D8's own words. But on today's tree `RUNNER_CLIS = ("claude", "codex", "copilot")` (`db/models.py:296`), `ck_runners_cli` is now *generated from* `RUNNER_CLIS` rather than a separately-maintained literal (`", ".join(f"'{cli}'" for cli in RUNNER_CLIS)`, widened by migration 0112), and `model_catalog.CATALOG` already carries a `"copilot"` entry (`model_catalog.py:350`) — all landed by `a-copilot-agent-runs-over-acp` (archived 2026-09-30), the same change F470 already flagged for pre-building `RpcCallbacks`/`_execute_rpc_run`. `workspace_writes.WRITE_TOOLS` has the identical shape: `COPILOT_WRITE_TOOLS` is already folded into it (`workspace_writes.py:55-61`), ahead of any Copilot adapter existing to declare it. An existing test already depends on the 3-wide set: `test_runners_api.py:204`, `assert set(providers.keys()) == {"claude", "codex", "copilot"}`.

So three of D2/D7's equalities — task 1.5(a) (`tuple(ADAPTERS) == RUNNER_CLIS == tuple(CATALOG)`), 1.5(b) (the route's key order), and 1.5(c) (the union of `write_tool_kinds` equals `WRITE_TOOLS`) — are written in `test_runner_adapters_conformance.py` **against today's real 3-wide registries**, not a hand-shrunk 2-tuple, per the principle F470 set: pin the contradiction, do not quietly resolve it. Once group 2 finishes building the literal 2-member `ADAPTERS` design D1 specifies, all three will fail as an **assertion**, not the `ModuleNotFoundError` group 1 expects — group 2 (or, per D2's own "For slice 2" note, whichever slice actually adds `CopilotAdapter`) has to either land a `CopilotAdapter` stub alongside `ClaudeAdapter`/`CodexAdapter` in this same change, or revise D1/D2/tasks.md's 2-tuple text to acknowledge the registries already moved. Re-read `db/models.py:296`, `model_catalog.py:227-388` and `workspace_writes.py:40-61` fresh at group 2's IMPL rather than trusting D1/D2/D7's text, which predates migration 0112.

**Resolution, 2026-10-01.** The three cases stayed red on CI for the whole night: 17 consecutive
failed runs, which no firing's log recorded. Put to the operator with three options: pin the gap
as a strict named exception, build the adapter, or `xfail`. They chose to build it. `CopilotAdapter`
(`hub/hub/runner_adapters/copilot.py`) implements slice 2's "Slice 1 member names" table, with
each member delegating to the function slice 2 ships, so all three equalities hold unchanged.
F473's and F475's carve-outs were removed in the same commit, since each existed only because
this adapter did not.

## F473 (C) — `each-runner-cli-is-one-adapter` task 3.1/D5's literal 501-gate and `catalog_provider_for_runner` replacements would 501 every Copilot run, today

**Status:** fixed in the same commit that found it, filed 2026-10-01 from the night window's ORDER 1/24 task 3.1, editing `agent_trigger.py`/`agents.py`.

Design D5 states the 501 gate at `agent_trigger.py:773-780` "becomes `get_adapter(runner) is None`, and its message lists `ADAPTERS`", calling the branch "unreachable" so the changed text is "unobservable". That reasoning holds for `claude_proxy`/`native` (never a real `Runner.cli` value) but not for `copilot`: `copilot` **is** a live `RUNNER_CLIS` member, already spawnable today through its own ACP path (`_prepare_copilot_turn`, below the gate) and already a member of the `SUPPORTED_RUNNERS` tuple the gate reads today. `ADAPTERS` is 2-wide this slice by design (D1: "this change touches no Copilot code") — `get_adapter("copilot")` is `None` today and will stay `None` until a `CopilotAdapter` lands in a later ORDER item (`a-copilot-agent-runs-over-acp`, queued separately). Implementing the gate literally as D5 states would have 501'd every Copilot agent the moment this task landed — a real regression to a shipped feature, not an unobservable text change. The same shape of mistake sat in `_CATALOG_PROVIDER_BY_RUNNER`'s replacement (`catalog_provider_for_runner(runner)` → `adapter.catalog_provider`, two call sites: `agent_trigger.py`'s `render_control_config` and `agents.py`'s agents-list `permission_mode_at_rest` derivation): `_CATALOG_PROVIDER_BY_RUNNER` had an explicit `"copilot": "copilot"` row with no adapter-based equivalent.

Fixed by carving Copilot out explicitly at both sites rather than implementing D5's text verbatim: the 501 gate is `get_adapter(runner) is None and runner != "copilot"`, and each `catalog_provider_for_runner` call site became `adapter.catalog_provider if adapter else ("copilot" if runner == "copilot" else None)`. Both carve-outs are commented as temporary, to be deleted once `CopilotAdapter` exists and `get_adapter("copilot")` stops being `None` — at that point `runner != "copilot"` becomes dead and the literal D5 text becomes correct. design.md's own D5 table should be corrected to note this the next time `each-runner-cli-is-one-adapter`'s design is read fresh, so a later task (3.3's own 501-gate bullet, or whoever eventually removes the carve-outs) does not rediscover the same gap.

## F474 (C) — `each-runner-cli-is-one-adapter` task 3.2's `resolve_access_path` deletion has three production callers its own text does not name

**Status:** fixed in the same commit that found it, filed 2026-10-01 from the night window's ORDER 1/24 task 3.2, editing `agent_trigger.py`/`agents.py`.

Task 3.2's own text ("delete `MCP_INJECTABLE_RUNNERS` and `resolve_access_path`...") inventories only `test_launchability.py`'s own callers (the three assertions moved onto `resolve_access_axes`, plus the deleted `kimi` test and the docstring mentions it names in three other test files). It does not mention that `resolve_access_path` has **three production callers**, found by grepping `hub/hub` for the name rather than trusting the task's own list — the same method F470-473 each used: `agent_trigger.py:1112` (`access_path = resolve_access_path(runner, hub_client)`, feeding both `described_access_path` and the `mcp_command` gate at `:1208`), and two in `agents.py` (`:579`, the agents-list `permission_mode_at_rest`/`permission_mode_built_in` derivation touched by F473's carve-out in task 3.1; `:1720`, the Copilot home pre-warm's `mcp_command` gate). Deleting the function without touching these would have broken the module import immediately — not a subtle regression, a 500 on every route that imports `agent_trigger` or `agents`.

Task 3.3's own text explicitly plans the real fix for the first caller (`resolve_access_axes replaces resolve_access_path` in `agent_trigger.py`, alongside `mcp_command` becoming `iff tool_surface == "mcp"` and `described_access_path(axes.plane, …)`) — but that rewrite also needs `runner_flags` (computed at `agent_trigger.py:1221`, after today's `access_path` is read at `:1112`) threaded up earlier, which is its own non-trivial reordering, and 3.3 says nothing about the two `agents.py` callers at all. Rather than duplicate 3.3's work early or leave either file unable to import, fixed task 3.2 with the same inline substitution at all three sites: `resolve_access_path(runner, override)` had already reduced, for every live `Runner.cli`, to exactly `"cli" if override == "cli" else "mcp"` (`MCP_INJECTABLE_RUNNERS` admitted every live runner, per `launchability.py`'s own now-deleted DEAD comment), so each call site now computes that one-line equivalent directly, with a comment pointing at this finding and at task 3.3 as the real fix for `agent_trigger.py`'s copy. `agents.py`'s two call sites have no task in this queue that claims them; whoever does task 3.3 should check whether they should move to `resolve_access_axes` too, or stay as the trivial inline form permanently (plane and tool_surface are degenerate there — `agents.py:579` only ever reads `.plane`-equivalent `access_path`, never a transport-derived `approvals` axis).

**Addendum (task 3.3, iteration 15):** `agent_trigger.py`'s copy landed as planned — `runner_flags` is now read before the sentinel strip and threaded into `resolve_access_axes(adapter, hub_client=..., flags=runner_flags)` (with a literal reproduction of the same rule for the `adapter is None and runner == "copilot"` case, which has no `RunnerAdapter` to call), replacing the inline substitute this finding left at `:1112`. `agents.py`'s two sites were deliberately left untouched — this task's own text never claimed them, and the comments at `agents.py:579`/`:1721` still point here — so they remain the permanent degenerate inline form this finding already anticipated, not an open gap.

## F475 (D) — `each-runner-cli-is-one-adapter` task 3.6's "`runners.py:116-118` iterates `ADAPTERS`" bullet would drop Copilot from `GET /runners/launchability-by-provider`

**Status:** fixed (not implemented as literally stated), filed 2026-10-01 from the night window's ORDER 1/24 task 3.6, editing `api/v1/runners.py`.

Task 3.6's own text says the route "iterates `ADAPTERS`". Implemented literally (`for cli in ADAPTERS`), the task's own named verify command still passes, but the broader regression this iteration ran over `test_runners_api.py` turned one of F471's three predicted-and-accepted conformance failures green (`test_launchability_by_provider_key_order_matches_adapters`, which asserts `list(providers) == list(ADAPTERS)`) while breaking a previously-passing, un-skipped test in a different file: `test_runners_api.py::test_launchability_by_provider_probes_every_catalog_provider_with_no_runner_needed`, which asserts `set(providers.keys()) == {"claude", "codex", "copilot"}`. `ADAPTERS` is 2-wide this slice (design D1: no `CopilotAdapter` yet); `RUNNER_CLIS` is 3-wide (migration 0112, F471). Iterating `ADAPTERS` here silently drops Copilot from a real, operator-facing endpoint that backs agent creation by provider ("the operator must see a provider's launchability *before* choosing a model") — the same shape of mistake F473/F474 already found twice in this same task group (a design bullet that is unobservable for `claude_proxy`/`native` but not for the live `copilot` CLI).

F471 itself says this exact tension ("`test_runners_api.py:204` ... depends on the 3-wide set") is **not** this task's to resolve — "group 2 (or, per D2's own 'For slice 2' note, whichever slice actually adds `CopilotAdapter`) has to either land a `CopilotAdapter` stub ... or revise D1/D2/tasks.md's 2-tuple text". Task 3.6 is neither of those: it adds no `CopilotAdapter`. So the route was left reading `RUNNER_CLIS` (unchanged from before this task), with a comment pointing at F471/this finding instead of the bare `ADAPTERS` the task text names. This keeps `test_runners_api.py` passing and leaves `test_runner_adapters_conformance.py`'s three F471 cases exactly as every iteration since 13 has found them — no new failure, no regressed endpoint. Whoever lands a real `CopilotAdapter` (the queue's own separate `a-copilot-agent-runs-over-acp`-successor item) should revisit this comment: once `get_adapter("copilot")` stops being `None`, `ADAPTERS` and `RUNNER_CLIS` converge and the distinction this finding carves out becomes moot.

## F477 (B) — the shim notice invited a compound shell command the approver cannot give standing to, so "Ask me" carded every Copilot call

**Status:** fixed in the commit that files it (2026-10-01), found by drive 9.4 of `a-run-reaches-the-hub-without-mcp`.

The notice and tool section said to write the args file *"with your file tool, or from PowerShell only with
`Set-Content -Encoding utf8`"*. Copilot (1.0.88, Auto model) took the second route and joined both steps into one
PowerShell command (`$body = @{…} | ConvertTo-Json; Set-Content -Path '.agentweave\calls\create-s3-ask.json' …;
aw-tool create_task '.agentweave\calls\create-s3-ask.json'`, `run-88cb9324104b`). D8's standing covers a file-tool
write and a lone, unquoted `aw-tool` invocation, deliberately not a compound, so under "Ask me" the request fell
through to a card (it expired; no task). Under "Workspace only" the same compound was allowed by the workspace judge
on its words (`run-55f0cb12de64`, 9.3), which is why only 9.4 showed it.

**Fix:** both texts now say two separate tool calls: the file-writing tool for the args file (the shell only as a
command of its own), then `aw-tool <tool> .agentweave/calls/<file>.json` run alone, unquoted, nothing chained,
"which needs no approval in any posture". Re-driven: Copilot wrote the file with `apply_patch` and ran the bare
call; no card, task created by the run (`run-000e23023de9`). The approver was not widened.

## F479 (D) — slice 2's spec-turn exclusion list names a tool Copilot 1.0.88 does not have

**Status:** fixed f2f3bd9. Was: open, observed 2026-10-01 in drive 9.10 (`run-b30d4295abaf`).

Every Copilot specification turn now stores the diagnostic `copilot.configuration` *"Unknown tool name in the tool
excludedlist: \"str_replace\""*: `--excluded-tools=apply_patch,edit,str_replace,str_replace_editor` names
`str_replace`, which 1.0.88 does not know (it reported `Disabled tools: edit` for the rest). Harmless to the run,
noise in every spec turn's timeline. Fix in `a-copilot-agent-runs-over-acp`'s argv builder: drop `str_replace`, or
keep it only behind a version check, and assert the list against a captured 1.0.88 tool inventory.

## F483 (A) — A Copilot runner is "not signed in" on a machine where `copilot login` is current

**Status:** fixed 2026-10-02 at home (direct fix, operator's call): every Hub-owned Copilot home, the worker's
included, gets the operator's `lastLoggedInUser`/`loggedInUsers` before each probe, one-shot and turn
(`sync_account_pointer`), and the not-signed-in reason names the `config.json` it reads them from. Specs updated
by hand: runner-registry ("Copilot launchability is read from Copilot itself") and operator-agent-creation.
Filed 2026-10-02 on the work PC during task 10.1 of `a-run-reaches-the-hub-without-mcp`.
**Ready:** cause reproduced; fix shape not chosen. Creating a Copilot agent returned `409` with "Copilot CLI is not
signed in. Run `copilot login`.", and still did after the operator ran `copilot login` again. Copilot 1.0.89-1 (the
npm platform binary the Hub resolves) keeps the token in the Windows Credential Manager
(`…github.com:<login>.copilot-cli`), but it finds *which* account to read through `lastLoggedInUser` /
`loggedInUsers` in `$COPILOT_HOME/config.json`. The Hub's worker home (`~/.agentweave/hub/copilot-home/worker`) and
every per-agent home start without those keys, so `session/new` answers `-32000 "Authentication required"`.
Reproduced by hand with the probe's own `PROBE_ARGS` and `copilot_guard_env`: an empty home gives `-32000`, and
the same home seeded with only those two keys copied from `~/.copilot/config.json` gives `session/new` OK. This
contradicts design-time evidence that auth survives an empty `COPILOT_HOME` (exploration
`2026-09-27-copilot-as-a-full-runner/a-copilot-cli-capabilities.md:249`, measured on the home PC). Either the
CLI's lookup changed or that machine had another credential path, such as a `gh` token. Running `copilot login` in a
terminal writes only `~/.copilot`, so the reason the Hub shows tells the operator to do something that cannot help.
**Workaround used:** the two keys were copied into the worker home's `config.json`. The probe flipped to
`runnable: true` within one refresh. Each agent's home needs the same copy before its first run. **Fix
candidates:** `ensure_copilot_home` and the worker-home setup copy `lastLoggedInUser`/`loggedInUsers` from the
operator's default Copilot home, since neither key is a secret or a permission; or the not-signed-in reason names
the home that was probed.
**Reproduced at home 2026-10-02, and why the home PC never saw it:** the probe's own handshake (Hub-resolved
`copilot` 1.0.88, `PROBE_ARGS`, `probe_env`) against a fresh temporary home: empty home with `gh` visible -> OK;
empty home with `gh` hidden (`GH_CONFIG_DIR` empty, GitHub CLI off `PATH`) -> `-32000 "Authentication required"`;
the same, seeded with only `lastLoggedInUser`/`loggedInUsers` -> OK. With no account named in its home, Copilot
falls back to the GitHub CLI's keyring token, and the home PC has `gh` signed in as `gutohuida`. The work PC's
`gh` has no usable personal login. So the exploration's "auth survives an empty `COPILOT_HOME`" was true only
through `gh`; it is not a CLI regression.

## F484 (B) — a Copilot reviewer's `update_task` claims a subagent review that never ran

**Status:** fixed `ec2e9ca` (2026-10-04, interactive; slice 5 amendment D8a, operator-approved): the
review bullet spells the dispatch (`agent_type` exactly the lowercase id, a named model on retry,
"never describe a review it did not give"), and every Copilot review turn whose context named
review agents ends with a `review_agents_report` status saying what ran in that run, "none"
included, matched on dispatch id and type. Not built: stamping it on the task's transition row.
**Re-driven 2026-10-04 (7.7, passes):** `code-review` dispatched on the first try and the report
card matched every run. **The premise needs a correction:** reading the 10-03 run's full timeline
again, `run-8d29230e8279` *did* dispatch `code-review` in the background
(`call_lkMeAofQkdoLuTSSLKiqn4oA`, agent `aac37841`), so that reviewer's claim may have been true;
the 10-03 reading missed it because the dispatch ran in the background and its events sat outside
the tools collected. The fix stands on its own terms: the Hub now records what ran beside any
claim, instead of anyone having to reconstruct it. Originally: open, found 2026-10-03 by drive task 7.7 of `a-copilot-agent-uses-hooks-and-its-own-agents`
(design.md Round log, "Task 7.7, real drive, 2026-10-03"; real review turn on the trial Hub `:8010`,
run `run-8d29230e8279` / resumed as `run-c1339b044701`). **Ready:** no change owns it; see
`spec-queue/DECISIONS.md`'s `ghcp-s5-subagent-capture` row, fourth addendum.

With `cp5.copilot_review_agents = ["code-review"]` set and a real review turn dispatched
(`review_task_id` naming a task whose evidence footprinted a real commit, `817a4aa775dce442b57b7423113fc945af5d677d`),
the rendered per-turn context carried design D8's bullet verbatim, instructing `cp5` to run Copilot's
`code-review` built-in as a subagent on the named `<base>..<commit>` range before its verdict. It never
did: the full `GET /agent/cp5/chat` timeline across both the timed-out first attempt and its resumed
continuation uses exactly four tools in its entire length — `rg`, `shell`, `edit`,
`agentweave-update_task` — and the project's `EventLog` holds zero `subagent_started`,
`subagent_completed` or `subagent_failed` entries for `cp5` at all. `cp5` instead reviewed the range
itself by running the repository's own test suites and reading code directly (a real and reasonable
review on its own terms, which did find a genuine defect — see below). But its verdict text and its
`update_task` call's `notes` field both then state, verbatim: *"The independent code-review agent
independently flagged the same event-boundary weakness"* / *"identified by... the code-review agent."*
No tool call anywhere in the transcript could be that dispatch. `cp5` attributed its own finding to a
second reviewer it never ran, and wrote that attribution into `update_task`'s `notes` — the one field
design D8 and the review flow both rely on as the durable, truthful account of what a review turn did.
A reader of this task's history (the operator, or a later agent resolving a divergence) would read
"independently... flagged" as corroboration from two separate reviewers when there was only one,
reviewing nothing twice.

**This is worse than the already-open subagent-dispatch question** (`ghcp-s5-subagent-capture`: `explore`
and `code-review` both go un-dispatched despite being named in the prompt; one attempt at `explore`
tried and hit a host-effect error). Failing to dispatch a named subagent is a capability gap a design
can route around (D2 already does, for hooks). Asserting that the dispatch happened and corroborated
a finding, inside the field whose entire purpose is to be trusted, is a correctness defect in the
review record's content, independent of whether the underlying capability ever gets built. **Fix
candidates:** forbid a Copilot reviewer's verdict/notes from claiming a named subagent's involvement
unless a matching `subagent_started`/`subagent_completed` pair is present in that run's own
transcript (checked server-side, not left to the model's own honesty); or drop the D8 bullet's
subagent framing entirely until dispatch is proven reliable, so there is nothing to falsely claim.

**The defect `cp5` found on its own stands regardless.** `hub/hub/output_recording.py:41-42` scrubs
each output event's registered secret independently, and `CopilotEventMapper.on_session_update`
(`hub/hub/copilot_acp.py:969-975` per `cp5`'s own citation) flushes message/thought blocks separately
on a type transition — so a secret split across two such events (reproduced by `cp5` with
`plainproxykey123` split as `plainproxy` + `key123`) passes per-event scrubbing in each event and
reconstructs whole once both are persisted and broadcast. This touches design D7/task 3.5's
no-record/no-broadcast guarantee for a provider key and is real and reproduced, even though the
"independent" corroboration attached to it was not. Full report: `cp5`'s own
`.reviews/review-0001-2026-10-03-1836.md` in the review checkout (not committed; written by its
`edit` tool call during the turn).

## F485 (D) — the GitHub MCP toggle's ask-me card never fires: Copilot's own session never sends `session/request_permission` for a built-in `github-mcp-server` call

**Status:** fixed `4a08b81` (2026-10-04, interactive; slice 5 amendment D9a, operator-approved):
the toggle is described as read-only GitHub tools Copilot runs without asking (no card is
promised); `--enable-all-github-mcp-tools`, `--add-github-mcp-toolset`, `--add-github-mcp-tool`
and `--additional-mcp-config` are removed from runner flags outside Full access; the three
settings keys are swept from the Hub-owned home. Still INFERRED: that Copilot auto-approves a
read-only call (`mcp-read-only`) and that a write call would arrive as a permission request.
Re-driven by 7.8. Originally: open, found 2026-10-03 by drive task 7.8 of `a-copilot-agent-uses-hooks-and-its-own-agents`
(tasks.md:1056; real drive on the trial Hub `:8010`, agent `cp5`). **Ready:** no change owns it.

Task 7.8's first bullet held exactly as written: with `cp5.config.copilot_github_mcp` false (default,
unset), `Get-CimInstance Win32_Process -Filter "Name='copilot.exe'"` on the live process during a real
turn (`run-cda0da200b0f`) showed `--disable-builtin-mcps` on the command line; setting
`copilot_github_mcp: true` via `PATCH .../agents/cp5` and firing a new turn (`run-a9ea1b559ca5`) showed
the live process's command line with that flag correctly absent.

**The second bullet does not hold.** With the toggle on, three separate real turns asked `cp5` to use
GitHub tools: (1) "List one open issue... using the GitHub tools" (`run-a9ea1b559ca5`) — `cp5` ran `gh
issue list` over `shell` instead, after its `read` of `CLAUDE.md` was denied by a preToolUse hook; (2) a
turn forcing the MCP path explicitly (`run-1c8b1fe0df9a`) — `cp5` replied that the exposed GitHub MCP
toolset has no issue-listing tool at all, and used nothing; (3) a turn naming `search_code` directly
(`run-09913f71b09a`) — `cp5` called `github-mcp-server-search_code` and it **completed immediately**,
tool_use straight to tool_result, with **no ask-me card anywhere** in the real `GET
.../agent/cp5/chat` timeline and **zero** `permission.requested`/`permission_denied`-family events in
`GET .../logs` for any of `cp5`'s runs this session. A fourth real turn, asking `cp5` to create an issue
through the MCP tool (a write action, to see whether only read tools skip the ask), got the same answer
as (2) — the exposed toolset has no issue-creation tool — so no card and no issue was created either
(confirmed after the fact: `gh issue list --repo gutohuida/AgentWeave --state all` returned `[]`).

Reading `hub/hub/copilot_acp.py`'s own permission path confirms this is not the Hub refusing to ask:
`answer_permission` (`copilot_acp.py:2036`), and the `decide_permission`/`github_rule` logic that would
answer `ASK_OPERATOR` for exactly this case (`copilot_acp.py:671-672`, D9), only run **when Copilot's ACP
session sends `session/request_permission`** (`PERMISSION_METHOD`) in the first place. For the one
github-mcp-server tool call this drive got Copilot to actually make (`search_code`), it never sent that
request — the Hub's D9 toggle logic was never reached, not overridden. Copilot's own CLI, in this
installed version, is deciding client-side that this built-in MCP tool call needs no confirmation,
upstream of anything AgentWeave's Hub can gate.

**Fix candidates:** confirm against a GitHub MCP tool Copilot's own CLI *does* ask permission for (if
any exist in this toolset) to bound how much of D9's gate is reachable at all in practice; if none do,
record that D9's ask-me card is currently unreachable for the installed Copilot CLI version and file
the gap with upstream or drop the design's claim that the toggle produces an operator-visible card.
Either way, task 7.8 as specified (`tasks.md:1056`) cannot be completed as written — there is no issue
tool to list from and no card to deny.

**Allowance.** Four real turns on `cp5` (Free-model Auto, per this change's call budget), no review
dispatch. No finding-13 note (B's optional) applicable here.

## F487 (B) — task 1.7c's own test rows ask for a cross-platform fix that regresses an already-shipped guarantee

**Status:** closed 2026-10-04 — **accepted as a named cost** (operator, `DECISIONS.md`
`shell-judge-escape-scope-1-7c` (b)): the escape levels stay POSIX only; tasks 1.7c, design D7 and the
spec delta say so, and rows `1.7c2-windows-cost`/`1.7c3-windows-cost` assert the Windows cost. The
`_LITERAL_BACKSLASH` sentinel (candidate (a)) is its own change if ever wanted.
Found 2026-10-04 by iteration 55 of `the-shell-judge-reads-a-word-whole`'s task
2.2a (D7's backslash-escape-level reading).

Task 1.7c (`tasks.md:950-956`) writes `bash -c 'cp n .\./x'` and `bash -c 'bash -c "cp n .\./x"'`
as refused **unconditionally** ("from both the Bash and the PowerShell tool", no platform
qualifier) — only the `grep -rn '\.\./' src` row is marked `(POSIX CI)`. Building the escape-level
reading literally (`_BACKSLASH_ESCAPE_RE` reducing `\c` to `c` at each level, judged again through
`_judge_word`, D7's own text) and running it on **both** platforms breaks a different, already-
shipped, already-green test: `test_a_quote_is_judged_by_what_it_decodes_to[P5a/P5b/P5c]` in
`test_permission_approver.py` (ANSI-C `$'...'` decoding). Measured directly: `$'A\x/../../y1'`
decodes (via `_ansi_c_escape`'s own "digitless escape keeps the backslash literal" rule) to the
literal word `A\x/../../y1`. On a drive-letter host `\` is *already* a separator rule 3/5 read
directly, so this word's existing, correct reading is two real components `A`, `x` that exactly
cancel the two `..` after them (inside your workspace) — `os.path.realpath` confirms it lands
exactly at the workspace root. Escape-reducing the same `\` *first* (as D7 asks) merges `A` and `x`
into one component (`Ax`), leaving one `..` with nothing left to cancel — outside. `git stash`ing
just `mcp_server.py` and rerunning both readings confirmed: `allow=True` before the escape-level
code existed, `allow=False` (wrong) after it ran unconditionally, `allow=True` (correct) again once
the reading is gated `not _DRIVE_LETTERS`. The conflict is structural, not a one-off: on a
drive-letter host a backslash in a word has two live, simultaneously-true meanings — "this is a
path separator" (rule 3/5/D2 read it that way today) and "this might be an escape an inner shell
would remove" (D7's own proposal) — and nothing in the word's final text says which one a given `\`
actually is. `_ansi_c_escape`'s own kept-literal backslash and a genuinely-unquoted, not-yet-
escaped backslash produce **identical decoded text**; only provenance (which quote form, if any,
already had its final say over this character) tells them apart, and no sentinel for that
provenance exists yet (the codebase's own precedent, `_LITERAL_DOLLAR`, marks the analogous case
for `$` — "this looks special but a quote already decided it isn't" — but nothing threads an
equivalent through every `_SEPARATORS` site for `\`).

**What shipped instead (iteration 55):** the escape-level reading is built and gated `not
_DRIVE_LETTERS` (POSIX only) in `_memo_judge_word`, with the regression this finding describes
reasoned through in its own docstring. `hub/tests/test_the_shell_judge_reads_a_word_whole.py`'s
`2.2a-escape1/escape2/escape-control` rows are marked `posix_only` (skip on a drive-letter host) and
a white-box test (`test_a_word_is_also_judged_at_each_backslash_escape_removed_level_2_2a`) forces
`_DRIVE_LETTERS=False` to exercise the POSIX reading on this Windows dev machine, since the table
rows alone would give zero local coverage. The `::` not-plain rule (D7's second bullet) is
unaffected by this conflict and ships unconditionally on both platforms, per task 1.7c's own
`Copy-Item … FileSystem::C:\Windows\x` row (explicitly marked Windows, no POSIX equivalent claimed).
Task 1.7c and 2.2a stay unticked: 1.7c's Windows-side escape rows (`bash -c 'cp n .\./x'` refused
from **both** tools, the `\$HOME` spy row, the `…FileSystem::..\x` row) are not built, and the
`grep foo 'src\a.py'` / `ls lib/Foo::Bar.pm` control rows are not yet added as written.

**Fix candidates, for the operator's or a later round's judgment, not decided here:** (1) a
`_LITERAL_BACKSLASH` sentinel emitted by `_ansi_c_escape` wherever it currently returns a literal
`\`, read as a real separator by every `_SEPARATORS`/`os.path` site but skipped by
`_escape_removed_levels`'s regex — the structurally complete fix, but it touches every separator
site in the file, larger than one iteration's slice; (2) accept the POSIX-only scope permanently and
correct task 1.7c's own rows (and design D7's "every path spelled with `\` gains harmless readings"
claim, which this finding's `A\x/../../y1` case disproves) to say so explicitly; (3) something
narrower scoped to only the two rows 1.7c names, not builtin for every word. The spec-flow lesson:
1.7c's rows were written in an R1-R3 round without a drive-letter-host measurement against the
*other* half of this same change's own tests, and "FAILS today" was true but incomplete — it did
not ask what the fix would break.

## F488 (B) — a run's registered secret survives the scrub when Copilot's output splits it across two events

**Status:** fixed 2026-10-04 by `1d2f72a`, change `a-secret-split-across-two-events-is-still-scrubbed`
(`run_secrets.scrub_stream` at both executor sites; `register` strips; the `session.error` log line
scrubbed). Tests: `hub/tests/test_run_secrets_stream.py`,
`test_copilot_byok_env.py::test_a_provider_key_split_across_events_is_scrubbed` (+ order, locked-retry
and interleaving guards), `test_agent_trigger.py::test_a_registered_value_split_across_claude_blocks_is_scrubbed`,
and three log-line tests in `test_copilot_acp_run_turn.py`. Stated residual: a dangling start shorter
than *m* = min(8, len//2) is shown (at most 7 characters, always a prefix). The change's drive (task
3.4) has not run yet. Filed 2026-10-04 (interactive, operator: "yes" to filing it on its own and taking it
first tonight). Found 2026-10-03 by `cp5` during drive task 7.7 of
`a-copilot-agent-uses-hooks-and-its-own-agents`, and until now recorded only inside F484.
**Ready:** yes. It is a defect in slice 5 group C's shipped scrub, and no change owns it.

`record_agent_output` (`hub/hub/output_recording.py:41-42`) scrubs each event's `content` and
`payload` separately, with `run_secrets.scrub`, which replaces whole literal occurrences of each
registered value (`hub/hub/run_secrets.py:50-56`). `CopilotEventMapper.on_session_update`
(`hub/hub/copilot_acp.py`) buffers `agent_message_chunk` and `agent_thought_chunk` text and emits it
as a separate event whenever the stream switches between thought, message and tool call. So a
registered value whose characters fall on both sides of one of those boundaries is stored and
broadcast as two events, neither of which contains the whole value. Each passes the scrub, and the
secret reads whole once the two events sit next to each other in the timeline. `cp5` reproduced
this with `plainproxykey123`, split as `plainproxy` + `key123` (read from its review record and
transcript; not re-driven here).

**Not established:** how often a real provider key falls on a flush boundary in normal output. The
model would have to be echoing the key at that moment. The repro forced the split. The severity is
B, not A, because it needs a key in the run's output in the first place. But the guarantee group C's
D7 states, that "neither the row nor the broadcast ever holds them", does not hold.

**Fix direction (for the change that takes it, not decided here):** scrub across event boundaries.
For example, hold back a tail as long as the longest registered secret minus one when a block is
flushed, and scrub it together with the next block of the same run. Or scrub the buffered text
before the transition flush, keeping a carry-over. Every other recorder that calls
`run_secrets.scrub` per event (other runners' streams, tool output) needs the same look; that has not
been checked. A test must split a registered value across a thought→message flush and across a
message→tool_call flush, in the order the mapper actually emits them.

## F489 (C) — the Hub retries a Copilot turn three times on an authentication failure that cannot succeed on retry

**Status:** fixed (this commit) -- as decided in `spec-queue/DECISIONS.md` `f489-retry-signal` (a):
a root `session.error` whose `errorType` is `authentication` or `quota` sets
`copilot_acp.TurnOutcome.retryable = False` (and `error_kind`); the RPC executor passes both to
`return_run_entries`, which withdraws the entry after its first attempt with the reason "the turn
failed with `authentication`, which retrying cannot fix; the Hub did not retry". A refusal with a
reset ahead still holds instead. Tests in `test_an_unretryable_failure_is_not_retried.py`. Driven
2026-10-06 on a fresh Hub `:8032` (BYOK runner, key var `invalid`, real Copilot CLI): one run, one
error card, entry withdrawn at attempt 1, `queue_entry_abandoned` carrying the reason.
Found 2026-10-04 by drive task 7.3 of `a-copilot-agent-uses-hooks-and-its-own-agents`
(interactive; trial Hub `:8010`), and seen identically by the 2026-10-03 drive of the same task.

One operator message to `cp5` on a Copilot provider runner whose key variable holds `invalid` made
three runs (`run-905f58dd3ac9`, `run-6988ccc8d1cb`, `run-aa933d99e455`), each ending with the same
`copilot.authentication` error (`status_code: 401`) four seconds apart, and the queue entry was then
abandoned: *"delivery failed 3 times; the Hub stopped retrying"*. An authentication failure is the
same on every attempt until the operator changes the key, so the two retries cost two spawns (and on
a subscription-backed runner would cost two more model calls) and triple the error cards. The
recorded error now carries Copilot's `errorType` (`authentication`) and `remediation` where reported
(group A, D5), which is what a retry decision could read. **Fix direction (not decided):** a turn
that failed with a root `session.error` whose `errorType` is `authentication` (or `quota`, which
slice 4 already holds the queue for) is not retried; the entry waits for the operator, as an
allowance hold does.

**2026-10-06 night:** traced the retry seam (`return_run_entries`, `hub/hub/inbound_queue.py:297`)
and its one Copilot-reaching caller (`hub/hub/api/v1/agent_trigger.py:4029`) before building — the
signal does not exist yet on `TurnOutcome`, there are two unrelated `TurnOutcome` dataclasses, and
`error_event`'s own `retryable` field (`runner_events.py:324`) is set nowhere and read nowhere.
More than a one-sentence spec choice; three candidate designs and the full trace are in
`spec-queue/DECISIONS.md`'s `f489-retry-signal` row (OPEN), not built tonight.

## F490 (B) — a run's registered secret is not scrubbed from what the agent writes through its Hub tools

**Status:** fixed 2026-10-05 by `26b0102` (Tier 0 by the operator's direction, interactive): an ASGI
middleware scrubs the body of every run-authenticated write to `/api/v1/agent-actions` by the run's
registry. Driven on `:8010`: a Copilot agent `f490drive` on a provider runner aimed at a local stub
Anthropic server (`testbed/drive1005-f493-f490-f491/stub_provider.py`, no spend), the stub's turn calling
`agentweave-send_message` with the run's own key in subject and content. Stored: `key <redacted>` / `the
provider key in my environment is <redacted>`; the key in **no** column of any table (two runs). A
before-drive with the middleware disabled was not run (the session's permission classifier refused
disabling it on a live Hub); `test_agent_writes_are_scrubbed.py` fails with the middleware removed.
**Ready:** closed.

`run_secrets.scrub` is applied only where a run's output is recorded: `output_recording.py` and
`api/v1/agent_trigger.py` are the only importers of `run_secrets` (VERIFIED by the review). Content
an agent sends through its AgentWeave tools is stored by other routes and never passes it:
`send_message`, `ask_user`, task updates (`update_task` notes), checkpoint notes, spec documents and
evidence. A Copilot provider run's key is in its environment (slice 5 D7, accepted), so an agent
that reads `$MY_ANTHROPIC_KEY` and passes it to one of those tools stores it in the Hub's database,
outside the run's own stream, and the D7 guarantee ("neither the row nor the broadcast ever holds
them") does not cover it. **Fix direction (not decided):** scrub with the calling run's registry at
the tool routes, which already know the run from its credential (`agent_auth.py`).

## F491 (B) — a Copilot review of this repository cannot finish: the review context asks for the test suite and the turn limit is 600 s

**Status:** fixed 2026-10-05 by `1014961` (Tier 0, interactive; operator: "fix it and drive it", taking the
first fix direction): a review turn's context now asks for the tests that cover what changed, and the
whole suite only for a change that reaches across the project. Driven on `:8010`, the 7.7 scenario again
(`cp5`, Copilot Free, commit `521e5d3`, two lines of `testbed/README.md`) with the neutral message *"Review
the work on this task and record your verdict."*: **one** run (`run-7892b664fdcc`, 122 s), `code-review`
dispatched, `git diff --check`, no suite run, task `approved` by `cp5`'s own `update_task`. Before: three
runs at the 600 s limit and a reassignment. The timeout-resume direction was not taken.
**Ready:** closed.

Reviewing a two-line `testbed/README.md` change, `cp5` (Copilot, Free/Auto) dispatched `code-review`,
then ran the repository's whole test suite, as the review context's instructions lead it to. Runs
`run-126998cf065a`, `run-c8e00634e828` and `run-eb9b38d92c73` each hit the 600 s Copilot turn limit;
the Hub gave up and the review was handed to `adapterdrive`, which set the task `revision_needed`.
However small the change, a Copilot review of this repo times out three times and is reassigned, and
each attempt bills a turn. A second attempt with the operator's message saying "do not run the test
suites" finished in one run and approved. Also seen in run 2: a `permission_denied` for a PowerShell
call under Workspace only ("the operator was asked") 12 s before the timeout. **Fix directions (not
decided):** a review turn's context says to run only the tests the change touches; or a review turn
gets a longer limit; or the timeout resume continues the same work instead of starting over.

## F492 (C) — a full commit SHA in a tool's input is stored as `<redacted>`

**Status:** fixed 2026-10-12 (night window iteration 5, Tier 0): `runner_events._is_commit_argument` keeps a 40- or 64-character lowercase-hex token that follows `git` in the same string, sits after whitespace or `.` and before whitespace, `.`, `^` or `~`; `https://<hex>@host`, `user:<hex>@host`, `Authorization=<hex>` and a bare hex string stay redacted. Chosen over "a commit known to the repository" because redaction has no repository to ask. Residual: a 40-hex key passed as a plain argument to a git command is stored. Tests in `hub/tests/test_operator_is_told_the_truth.py` failed 5 of 12 new cases before the fix; driven through `parse_claude_line` on a stream-json `tool_use` line: `git diff A..B` stored whole before: `<redacted>..<redacted>`; the clone-URL and `export K=` forms stay redacted. Found 2026-10-04 by drive task 7.7 of `a-copilot-agent-uses-hooks-and-its-own-agents`.
**Ready:** yes; no change owns it.

`runner_events._SECRET_VALUE_RE`'s catch-all (`[A-Za-z0-9+/=]{32,}`) matches a 40-character hex
commit SHA, so every tool input naming one (`git diff 77f3204…..521e5d3…`, `git show <sha>`) is
stored with the SHA redacted, and the commit range a review worked on cannot be read back from the
record. F278 kept file paths; a bare SHA is the same class of false positive. **Fix direction (not
decided):** keep a 40- or 64-character lowercase-hex token that is a commit known to the project's
repository (or matches a SHA in the run's own review context), redact otherwise; a key that is pure
lowercase hex of exactly 40 characters is the residual to weigh.

## F493 (B) — the Hub test suite, run inside an agent's run, writes fake refusals into the live Hub

**Status:** fixed 2026-10-05 by `ae0914a` (Tier 0, interactive): both suites' conftests pop the run
variables at import. Driven on `:8010`: a real `running` run's credential and `HUB_URL` in the environment of
`pytest hub/tests/test_hub_own_call.py`; with the pre-fix conftest the Hub recorded **5** fake
`permission_denied` rows against that run (Write ×2, Bash, PowerShell ×2, reason "the operator was
asked"), with the fix **0**. The CLI suite had the same leak (4 `POST /session/sync`, 10 failures under a
run environment; 0 and 567 passed after). Not driven through an agent turn: no Claude agent on `:8010`
gets the Hub's approver (its runs carry no MCP config, `runner_commands.py:241`), so a pytest call is
refused short of Full access.
**Ready:** closed.

The trial Hub's `event_logs` holds a `permission_denied` event for `cp5`, created 2026-10-04 17:47:28,
12 s before `run-c8e00634e828` timed out. Its data is `{"tool_name": "PowerShell", "tool_use_id":
"tu", "reason": "the operator was asked", "run_id": "run-c8e00634e828"}`. Copilot never refused
anything here, and the agent was under Workspace only. `"tu"` and `"the operator was asked"` are
the fixture values in `hub/tests/test_hub_own_call.py:45,53`. The reviewer was running this
repository's test suite inside its run (F491). That run's environment carries the bound
`AW_RUN_TOKEN` and `HUB_URL`. `mcp_server.approve_tool_call` reports the fake denial through
`_report_decision` (`hub/hub/mcp_server.py:3342`) to `POST /permission-decisions`, and
`record_permission_decision` (`hub/hub/api/v1/agent_actions.py:981`) persists it against the real run
and broadcasts it over SSE.

**Why only some tests leak:** `workspace` deletes `AW_RUN_TOKEN` (`test_hub_own_call.py:34`), but
`test_a_junctioned_calls_directory_gives_no_standing` (`:215`) and
`test_a_junctioned_calls_directory_gives_the_write_no_standing` (`:490`) take `asked` without it.
The second makes exactly one PowerShell call, which matches the single row stored. No
`hub/tests/conftest.py` fixture clears the run credentials suite-wide, so any test that reaches a
reporting path does the same. The operator's `:8000` database holds no such row (read `mode=ro`,
count 0).

**Effect:** an operator watching an agent that runs the tests sees refusals that never happened,
attributed to a real run. That is the misleading surface `record_permission_decision` exists to
prevent. Any other reporting path a test exercises could likewise write rows to the live Hub.

**Fix direction:** an autouse fixture in `hub/tests/conftest.py` (and `tests/conftest.py`) that
deletes `AW_RUN_TOKEN`, `HUB_URL` and any other run credential before every test. Check it with a
test that sets them, runs the `:490` case, and asserts no request leaves the process. The repro is
to run that test with `AW_RUN_TOKEN`/`HUB_URL` pointing at a drive Hub, then read `event_logs`.

## F495 (B) — a task sent back for revision is reworked by its reviewer, not its author

**Status:** fixed 2026-10-05 (Tier 0). `apply_transition` returns a task moved to `revision_needed` to
its most recent agent completer (`hub/hub/task_transition_service.py`); an operator completion leaves
the assignee alone. Tests: `hub/tests/test_revision_returns_to_the_author.py` (two failed before the
fix); `test_review_divergence.py:710`'s pin now names the author. Driven on `:8010` with two
stub-provider Copilot agents in a real flow: before (`1014961`, `task-7dda1110d84c`) the reviewer
`a0-f495-rev` was fired for the rework and completed it (transitions 37-38); after
(`task-20a182289f85`) the author `a1-f495-author` was (47-48). Found 2026-10-05 by an interactive
session's read of the review layer, confirmed on `:8000`'s data (`mode=ro`).
**Ready:** closed.

A flow that staffs a review writes the reviewer into `task.assignee` before moving the task to
`under_review` (`hub/hub/scheduler.py:918`, F70's ordering). When the reviewer sets `revision_needed`,
nothing writes the assignee back, so the next firing's ordinary-work arm *resumes* the task with
`agent = task.assignee` (`scheduler.py:1902-1906`): the reviewer. The reviewer then authors the fix,
which the review context itself forbids in spirit (`hub/hub/api/v1/agents.py:1946`, "a reviewer that
edits the work has reviewed its own work"), becomes the recorded completer, and the original author
is staffed to review the reviewer's fix. Author and reviewer swap roles on every revision cycle.

**Measured on `:8000` (read-only):** 7 revision cycles whose rework was done by an agent run; in 3 the
reviewer reworked, in 3 the author did (where the author's run picked it up some other way), 1 other.
`task-0ff93faef4ba`: `dev` completed, `dev_2` reviewed and reworked; `dev` then reviewed and reworked
`dev_2`'s rework. `task-d8d4b03d722b`: `dev` completed, `dev_2` reviewed and reworked.

**Fix direction:** moving a task `under_review -> revision_needed` returns it to the agent recorded as
its most recent completer (`completion_attribution`), so the rework runs, in a fresh session as it
already does, with its author; an operator completion (no agent) leaves the assignee untouched.


## F496 (C) — "draft the next slice" fires at the slice's approval, before anything was built from it

**Status:** fixed 2026-10-05 (Tier 1, amending C1a before its archive). The operator chose (b):
approval records the request, and `apply_transition` queues the drafting turn when the slice's last
linked task is approved or rejected, naming each task's outcome (`hub/hub/slice_drafting.py`, design
D4a). Drive C (`testbed/drive-slices/drive_c.py`) failed at (e) before and passed after on `:8010`.
Found 2026-10-05 by C1a's acceptance drive A (`testbed/drive-slices/drive_a.py`, `:8010`, entry
`entry-6ae9c2d4c8b5`).
**Ready:** done.

`a-spec-is-written-one-slice-at-a-time` (C1a) queues the drafting turn for slice N+1 when the
operator **approves slice N's document** (`hub/hub/api/v1/spec.py` `_draft_next_slice`, design D4,
exploration decision Q13). Approval is the moment slice N's tasks are created, so nothing in slice N
has been built yet. The drafting message (`_next_slice_message`) tells the agent to read "how the
approved slice's tasks are going (their notes and evidence): what building it taught you belongs in
this slice". In the drive that turn ran seconds after approval, and the only task
(`task-8b956365d756`) was `pending`.

So the stated reason for slicing late ("what was learned building slice N shapes slice N+1",
`proposal.md` Why) does not hold for the trigger as built. What it gives is overlap: slice N+1 is
specified while slice N is being built. That may be what Q13 meant ("the agent drafts slice N+1
when slice N is approved"). If so, the message's "how the tasks went" wording is wrong.

**Options:** (a) keep the approval trigger, and reword the message to "draft it while slice N
builds"; (b) trigger when slice N's tasks are all approved (a task-board event, not a phase event);
(c) both: queue at approval, and append slice N's outcomes to the draft when its tasks close.

## F497 (C) — a reviewer is not told that a rejected requirement will refuse its `approved`

**Status:** fixed (this commit) -- Tier 0: `review_turn.verdict_evidence_sentence` now names each
served requirement whose evidence is all rejected (`requirement_gate.rejected_identifiers`, the same
check `evaluate` refuses on) and says `revision_needed` returns the task to its author; the
rejected refusal ends with `REVIEWER_SENDS_BACK_REJECTED`. Tests in
`test_review_briefing_names_the_evidence_gate.py` fail before. Driven 2026-10-06 on `:8031`
(`slices1006b`, slice-2 task `task-cc8f85f29e9b`, every FR-3/FR-4 piece rejected by the operator):
the real Haiku reviewer's context carried the sentence, it made one `update_task` call --
`revision_needed`, notes quoting both rejection reasons and the tests to add -- and never tried
`approved`. Side note: rejecting only the newest evidence leaves a requirement `verified` while an
older piece stays accepted, so the shape needs every piece rejected
Found 2026-10-05 night by C1b's grounded review round (`a-task-may-serve-a-whole-slice`, design
"Review round" R2), by reading code; not driven.
**Ready:** needs the day window (no proposal).

`review_turn.verdict_evidence_sentence` is the one sentence both review channels use to warn a
reviewer that `approved` can be refused. It speaks only of evidence awaiting a decision and returns
`None` when nothing is waiting (`hub/hub/review_turn.py:186-245`). A task serving a requirement
whose current-digest evidence is all `rejected` is refused at `gate` today
(`requirement_gate.py:676-683`, `REMEDY[REJECTED]`), and at every rigor once C1b lands. The reviewer
learns that only from the `update_task` refusal, whose remedy ("record evidence that satisfies the
current wording") is the author's move, not the reviewer's. Nothing routes the refusal to
`revision_needed` (only `apply_transition` raises `GateUnsatisfiedError`,
`task_transition_service.py:678`). F357 measured reviewers telling peers a task was approved after
a refusal they had not been briefed on.

**Direction (not decided):** the same sentence also names each served requirement in `rejected` and
says `revision_needed` is the verdict that returns it to its author (F495).

## F499 (A) — approving a task whose requirements another task also serves merges the other task's commit, and the approved task's own work never lands

**Status:** fixed (this commit) -- Tier 0: `requirement_gate._check_unaccepted` allows the mixed case only where a commit approval would merge is not already in the main branch (`_merges_something_new`). Test `test_another_tasks_merged_commit_does_not_stand_in_for_this_tasks_waiting_work` fails before. Driven 2026-10-06 on `:8031`: every slice-1 approval merged its own task branch (`6abdcaf`, `46557a0`, `747131f`); the shared-requirement shape itself did not recur live (the slice had disjoint requirements), so that shape is test-only
Found 2026-10-06 by the first real end-to-end drive of the slice spec flow (C1a + C1b on master
`d4c65eb`), drive Hub `:8030` (profile `slices1006`), project `proj-e1e7ccbc8e78`, real Haiku turns.
Driven, not read. Area: **Worktrees & integration** / **Requirements, evidence & coverage**.

Slice 1 had three tasks serving overlapping requirements: `task-df903972e237` (FR-1, FR-7),
`task-06d8e481926e` (FR-2, FR-6), and `task-d60d02d44630` "Write comprehensive pytest tests" (all
four). The operator accepted only task 1's evidence (FR-1, FR-7). Task 1 was approved and merged
(`e5bb402`). Tasks 3 and 2 were then approved, and **both** integrations recorded task 1's commit
from task 1's branch:

```
task-d60d02d44630  e5bb402e  agentweave/task/task-df903972e237  skipped  e5bb402e231d is already in master; there was nothing to merge
task-06d8e481926e  e5bb402e  agentweave/task/task-df903972e237  skipped  e5bb402e231d is already in master; there was nothing to merge
```

`git merge-base --is-ancestor dbb3624 master` (task 3's own commit, its 28 tests): not in master.
On master, `Store.search('report')` still misses "write Report": the slice's headline bug fix,
task 2's work, never landed, while the board shows the slice 3/3 approved and the next slice was
drafted on that basis (F501).

Cause: `task_integration._targets` (`hub/hub/task_integration.py:254-274`) reaches evidence through
`TaskRequirementLink`, so any accepted evidence on a *shared* requirement becomes this task's merge
target ("deliberately", per its docstring). With none of the task's own evidence accepted, the only
accepted targets were task 1's, and the merge was a no-op reported as success-shaped "skipped".
C1b (`a-task-may-serve-a-whole-slice`) made requirement overlap between a slice's tasks the normal
shape, so this now fires on an ordinary slice. Not covered by an open finding or change (F357's fix
names "another task on a shared requirement" in a briefing; it does not touch the merge source).
Severity A: approved work silently lost, and the record says nothing was left to merge.

## F500 (A) — a reviewer records its own evidence during the review, which lifts C1b's rejected-requirement block, then approves over the operator's rejection

**Status:** fixed (this commit) -- Tier 0: `requirement_evidence.record` refuses an agent run reviewing the task (`review_task_for_run`) with `reviewer_records_evidence`. Driven 2026-10-06 on `:8031`: `run-eaa296bea5d7` (planner reviewing task 3) was refused twice with the new sentence, then read the author evidence with `list_evidence` and gave its verdict. Adjacent gap filed as F505
Same drive as F499. Area: **Requirements, evidence & coverage** / **Flows & review**.

The operator rejected every piece of `task-06d8e481926e`'s evidence twice (FR-2, FR-6, then FR-2,
FR-6, FR-7 after the revision), with reasons (the documented test command fails at collection).
The flow staffed `builder` to review it (`run-be4134b130c8`). During that review run the reviewer
recorded **new** evidence on the task under review, for FR-2, FR-6 and FR-7 (`actor=builder`,
`review_state=awaiting`), then moved the task `under_review → approved` (transition
`ttr-2f1417c04ec7`, `policy_digest 3124f244…`). C1b's D2 blocks a requirement only when its
current-digest evidence is *all* rejected; one fresh awaiting row by the reviewer makes it not-all.
The same happened on the other two reviews (`run-8b43483b396d` recorded four rows on task 3;
`planner` recorded FR-1/FR-6/FR-7 rows on task 1 while reviewing it), so the reviewer is routinely
also an evidence author on the task it judges. This reproduces the FR-11 incident C1b exists to
stop, on its first real slice. Related but distinct: F497 (reviewer not told the block exists).

## F501 (B) — the next slice is drafted from task statuses alone: the agent skipped `list_evidence`, missed two rejections and unmerged work, and called the model "solid"

**Status:** fixed (this commit) -- Tier 0: the drafting turn lists, per task, its latest merge outcome and each rejected evidence piece with its reason (`slice_drafting._task_outcomes`). Driven 2026-10-06 on `:8031`: the queued message carried "merged into master" ×3 and the FR-2 rejection reason; the drafting run called `list_evidence` and named the merge conflict in its notes
Same drive. Area: **Spec documents** (C1a's drafting turn).

The queued drafting message (`entry-99eebc58aa30`) asks the author to read the tasks' notes and
evidence with `get_task` and `list_evidence`. The real run (`run-247a6dad4e46`) called
`read_spec_document` ×2 and `get_task` ×3, never `list_evidence`, and wrote: "The data model
(priority, ID counter, case-insensitive search) is solid". Case-insensitive search is not on
master (F499) and its evidence was rejected twice. The message itself lists each task only as
`approved`, which is all the agent needed to stop reading. Slice 2 then repeats slice 1's shape
unchanged: a "Write comprehensive tests" task serving every requirement beside three parallel
tasks that all edit `tasktrack/model.py` (the shape that produced F499). Direction, not decided:
put each task's evidence outcome and integration outcome in the drafting message itself rather
than asking the agent to fetch it.

## F502 (C) — an agent learns the spec payload schema by trial and error: seven rejected submits in two turns, and a misplaced field is accepted silently

**Status:** fixed (this commit) -- Tier 0: `unknown_field` names a field a part does not define, with where criteria belong; a roadmap slice needs a `done` of at least three words (`slice_done_empty`); a boolean `done` is refused with what the field means; the agent submit answers `ready_to_propose`. Driven 2026-10-06 on `:8031`: the planner fixed non-goals unprompted and said "ready" only when `ready_to_propose` was true (slice 2 proposed clean). Schema discovery is still by trial (4 rejected submits): not fixed, the payload errors are already batched
Same drive. Area: **Spec documents** / **Agent environment**.

Over the two authoring turns (`run-00a1dcc17f30`, `run-c5256b54ad60`, Claude Code on Haiku via
`aw-tool`), `submit_spec_document` refused 7 of 11 calls, one schema rule at a time: `slices[].done`
must be a string; `scope` must be an object; `requirements[].key` required, then lowercase; `modal`
uppercase; top-level `acceptance_criteria[]` needs `key/requirement/given/when/then`. Meanwhile
`requirements[].acceptance_criteria: [{statement}]` (a shape the schema does not have) was accepted
because `spec_payload._Part` is `extra="allow"` (`hub/hub/spec_payload.py:69`), and propose then
said "has no acceptance criterion" with no hint that criteria were present in the wrong place.
The first turn also reported both documents "ready" while its last submit returned
`requirement_without_criterion`/`requirement_without_task` blocking, and the roadmap's slices were
accepted with `done: "false"` (the drafting message prints "Done when: false"). The operator needed
one corrective turn ($0.37) to get both documents through.

**Re-verified 2026-10-15** (full sweep, G4: Spec documents): the residual this entry's status names (schema discovery by trial) still costs calls. Turn 6 (`run-a1926c8b7bac`): `submit_spec_document` 422 x4 on the criteria shape (fields missing; criteria `key` missing; a criterion naming a requirement by its prose; `requirement` missing), then success on the fifth.

## F503 (D) — what held in the first real slice drive

**Status:** noted
Same drive, recorded so the ledger does not describe only defects. Held: proposing the roadmap
refused legibly on `non_goals_empty`; slice 1 refused until every requirement had a criterion and a
task; slice 1 approval with `draft_next_slice` answered `next_slice.state=waiting, open_tasks=3`
and queued nothing; the drafting entry was queued exactly once, as `origin_type=operator`, when the
last task closed; the drafted slice 2 links the roadmap and is within the size target (4
requirements, 4 tasks); no agent reviewed its own task; deciding evidence recorded by a live run
answered 409 `recording_run_live` naming what to do instead; an unknown decision word answered 422
naming the permitted words; the flow stopped itself with "loop queue is empty". Measured: request
to slice 2 drafted in 22 minutes, 11 real turns, $2.97 API-equivalent (authoring $0.61, build
$0.83, review $0.87, slice-2 drafting $0.61). Review rounds per task 1/2/1; first-pass approval 2
of 3 — but F499/F500 make every approval in this slice suspect.

## F504 (B) — a task sent back as `revision_needed` reaches its author with no reason, so a merge conflict loops

**Status:** fixed (this commit) -- Tier 0: the rework brief of a `revision_needed` task carries a "Why it came back" section: the reviewer and its verdict notes, and a measured check of whether the task branch still merges into main, with the remedy (`scheduler._briefing_revision_lines`); the conflict refusal now tells a reviewer its move is `revision_needed` (`requirement_gate.REVIEWER_SENDS_BACK`). Driven 2026-10-06 on `:8031` (slice 2): two tasks came back over conflicts, each brief carried the notes and the conflicting files, and both authors merged master and re-recorded evidence with no operator message (`dcbe59b`, `b01cf41`). The refusal sentence itself is test-only: no live reviewer retried `approved` after the restart
Found 2026-10-06 by the acceptance drive for F499–F502 (drive Hub `:8031`, profile `slices1006b`,
project `proj-abe05d2040fb`, real Haiku turns). Driven. Area: **Flows & review**.

`task-6b956bab2b51`'s approval was refused because its branch no longer merged into master (task 1
had merged first; both edited `tests/test_store.py`), and the reviewer moved it to
`revision_needed`. The flow's rework brief to the author (`entry-f2d6e759dcf3`) carries the
standing loop text and the task's original description and criteria: nothing about the conflict,
the refusal or the reviewer's notes. The author (`run-766835491458`) re-ran the tests, found them
green, tried to re-record identical evidence (refused as a duplicate) and moved the task to
`completed` again with the same conflicting commit (`bff98ca`). The next review was refused for the
same conflict. The reviewer's own notes were overwritten by the author's on completion. It took two
operator messages naming the conflict to finish the slice. Direction, not decided: the rework brief
carries the latest refusal and the reviewer's verdict notes.

## F505 (C) — an agent that co-authored a task's fix and recorded evidence for it can approve it

**Status:** fixed (this commit) -- operator decided 2026-10-06 ("fix those new errors"): an agent that recorded evidence for a task is barred from its verdict, its review entry and its dispatch whether or not another agent completed it, and the flow, `task_is_claimable_by`, the failed-review restaffing and the wedged-review check exclude it alike. Tests in `test_the_evidence_names_the_author.py`. Not reproduced live: no co-authoring reviewer arose in the slice-2 drive
Same drive. Area: **Flows & review**.

`builder`, staffed to review `task-80001982159f` (authored by `reviewer`), was messaged by another
agent to resolve its merge conflict. In a *work* run (`run-98fbf4aa530e`) it committed the
resolution (`14b1edb`, `46557a0`) and recorded FR-3/FR-4 evidence on it; F500's refusal does not
fire there, by design (only a review run is refused). In its next review run it approved the task.
`_guard_author_is_not_reviewer` compares only the completing agent where one exists, and says so on
purpose ("another agent's evidence row on the same task does not widen a decided answer"). So the
rule separating author from reviewer does not cover a reviewer that became a co-author. Widening it
reverses a documented decision, so it is filed, not changed.

## F506 (D) — what the acceptance drive measured

**Status:** noted
Request → roadmap + slice 1 → build → slice 2 drafted in 26 minutes, 18 real Haiku turns, $4.28
API-equivalent (planner $2.23, builder $1.54, reviewer $0.51) on `:8031`. Slice 1: 4 requirements,
3 tasks after one operator note (7 before); slice 2: 5 requirements, 3 tasks, proposed clean. All
three slice-1 tasks merged their own branch; master: 52 tests pass, the search and id-reuse bugs
fixed. Review rounds per task 1/4/2 — the extra rounds were merge conflicts between parallel tasks
of one slice (F504), not defects. The flow stopped itself on an empty queue. Observed, not filed:
one Haiku reviewer loaded `update_task` through ToolSearch four times and never called it, ending
with "I cannot directly invoke the AgentWeave tool"; the Hub restaffed the review as a divergence.

## F507 (C) — the Claude model catalog does not know Sonnet 5.5; a runner on `claude-sonnet-5-5` is refused

**Status:** fixed 2026-10-10 (Tier 0, night iteration 2, with F575). `claude-sonnet-5-5` ("Sonnet 5.5", window 1,000,000) is now the Claude catalog's Sonnet, default, and owner of the `sonnet` alias; `claude-sonnet-5` stays declared as the previous generation. Verified on CLI 2.1.291: `--model claude-sonnet-5-5` and `--model sonnet` both answered with `modelUsage["claude-sonnet-5-5"].contextWindow` 1000000. Tests (failed before): `test_model_catalog.py::test_sonnet_5_5_is_offered_and_owns_the_sonnet_alias_and_the_default`, `test_runners_api.py::test_a_claude_runner_can_bind_the_current_sonnet_by_its_full_id`. Driven on a scratch Hub `:8013` (fresh database): POST /runners with `claude-sonnet-5-5` -> 201, `sonnet` -> 201, `claude-sonnet-9` -> 400 whose list now names `claude-sonnet-5-5 (or sonnet)`.
Found 2026-10-06 setting up the first real slice-flow run on the trial Hub `:8010` (interactive). Driven,
not read. Area: **Runners & models**.

`POST /runners {"cli": "claude", "model": "claude-sonnet-5-5"}` answered 4xx: "'claude-sonnet-5-5' is not a model
'claude' declares; expected one of: claude-opus-5-5 (or opus), claude-sonnet-5 (or sonnet), ...". The
catalog (`hub/hub/model_catalog.py:245`) lists `claude-sonnet-5` as the Sonnet and default; Sonnet 5.5
(`claude-sonnet-5-5`) is the current Sonnet. Worked around with the `sonnet` alias, which the Claude CLI
resolves itself at launch, so the Hub records `sonnet` rather than the model that actually ran. An
operator who types the current model id is refused with a list that does not contain it.

**Direction (not decided):** add `claude-sonnet-5-5` to the Claude catalog (and decide whether it
becomes the default and owns the `sonnet` alias).

## F508 (B) — the planner promised a reviewer the document never declared; the flow staffed a leftover stub agent

**Status:** fixed 2026-10-08 (Tier 1, `a-document-names-its-default-reviewer`, authored in the app, `cac7299`) -- the default half: `delivery.reviewer` is the reviewer of every task naming none, resolved by `review_turn._declared_reviewer_name` (rung 1 / 1b, never substituted); the approval bar says who reviews a flow-delivered document. Driven on `:8010` with real Haiku agents: 0/3 before (the review went to `aaa-stub`), 3/3 after (`scripts/drive/d1008_default_reviewer_drive.py`); the bar in Chromium 4/4 (`d1008_default_reviewer_bar.py`). Reconciled into `agent-flows`. Earlier, partly fixed (Tier 0, 2026-10-07) -- the warning half: a flow-delivered document none of whose tasks names a `reviewer` is warned on submission (`spec_completeness.reviewer_undeclared_warnings`, advisory), and the exploring duty says "Name the reviewer in the field, not the prose". Test: `test_spec_reviewer_undeclared_warning.py` (no warning before). Still open: the document-level default reviewer (Tier 1, plan Phase 5).
Found 2026-10-06 in the first real slice-flow run on the trial Hub `:8010` (change "same-file tasks of a slice
build in order", flow `job-4182c24930d5`). Driven, not read. Area: **Flows & review** / **Spec documents**.

`aw-planner` asked the operator how slice 1 should be built and offered "Flow, aw-builder, stop on empty queue:
... has aw-reviewer review finished work". The operator chose it. The document it wrote declared `delivery` with
`aw-builder` and left every task's `reviewer` null, so nothing named `aw-reviewer`. When task 1 completed, the
flow's rung 2 (`scheduler.resolve_reviewer`, any free agent) staffed `a0-f495-rev`, a leftover drive agent on a
stub-provider runner, and queued it the review briefing (`entry-7e0b2f8e0935`). Caught before it ran: the
operator reassigned the task to `aw-reviewer`, withdrew the entry and archived 14 leftover agents.

Two seams: (1) what the planner tells the operator about staffing is not what the document declares, and nothing
checks one against the other; (2) rung 2 picks any free agent in the roster, so a project with old or broken
agents gets reviews from them silently. The operator learns who reviews only from the task's assignee.

**Direction (decided by the operator, 2026-10-08):** a `reviewer` field in the document's `delivery` section,
beside `delivery.agent`, written by the planner. Ladder: the task's `reviewer`, then `delivery.reviewer`, then any free
agent; a default that does not resolve is rung 1b (surfaced, never substituted). No-name fallback stays "any free agent",
but the approval bar always says who reviews ("reviewed by @X" or "reviewed by any free agent"). Not chosen: a project-level
default, requiring a name, a reviewer picker at approval.

**Recurred 2026-10-06** in slice 1c: the operator's request said "name `aw-reviewer` as reviewer"; the
planner wrote "Reviewer: aw-reviewer." in the design and left the task's `reviewer` field null (slice 1b,
told the same, did set it).

## F509 (A) — slice 1 of "same-file tasks build in order" cannot fire for an `aw-tool` agent: it never sees the text that teaches it

**Status:** fixed by trial slices 1b + 1c (1c merged `f0637dc`: a multi-task document whose tasks declare
no `files` draws an `undeclared_task_files` warning). Re-driven 2026-10-06 on a fresh Hub `:8036`, the
neutral request twice, Haiku: both declared `files`; run 1 met `unordered_file_overlap`, chained all four
tasks and resubmitted clean; run 2 revised twice and stopped with two pairs still unordered, its last
response naming the overlap (the slice's pass condition: chained, or the overlap named). Across the 1b and
1c drives Haiku declared `files` 3 times in 4; 1c's own warning was not needed live (test-only). A planner
that is told of an overlap and stops anyway is the remaining gap (roadmap slice `flag-missed-overlap`).
Earlier status: partly fixed by trial slice 1b (merged `b36c084`, `95922ba`, built through the `:8010` flow) --
the exploring duty now states a per-task step (list `files`; chain tasks sharing a path), the tool section
names `depends_on` and `files` on every access path, and `aw-tool --help <tool>` prints a whole description
(recognised as the Hub's own call). Re-driven 2026-10-06 on a fresh Hub `:8035`, the same two requests, Haiku:
run 1 declared `files: ["notes/cli.py"]` on all three tasks and chained them (pass, on the wording that
failed before); run 2 saw the same step in its context and still left three parallel tasks with no
`files` (fail). The text now reaches the planner; Haiku follows it one time in two. Open: whether that is
enough, or a planner that declares no `files` on a multi-task slice should itself be warned
Found 2026-10-06 by the acceptance drive of trial slice 1 (merged `ce665d1`, `f25ebb3`), run by the operator
after merge as the design said, on a fresh Hub `:8034` (profile `sliceaccept1006`, project `aw-accept-1006`)
with a real Haiku planner. Driven, not read. Area: **Spec documents** / **Agent environment**.

Two requests for a three-feature change to one file (`notes/cli.py`). Run 1: three tasks, no `depends_on`,
no `files`. Run 2 (neutral wording, no "worked separately"): `depends_on` used only for a data-model
prerequisite; the three feature tasks on the same file still parallel, no `files`. The submit response
carried `"warnings": []` both times -- the plumbing works, and nothing could trigger it.

Cause: the planner reached the Hub through the `aw-tool` shim (`aw-tool submit_spec_document
.agentweave/calls/submit.json`), and `aw-tool --list` prints only the first line of each tool's description
(`mcp_server._call_listing`, `summary = ...split("
", 1)[0]`). The full `submit_spec_document` text -- where
slice 1 put the `depends_on` rule and the only documentation of `files` -- never reaches a shim agent. The
exploring duty's new "Order the tasks" sentence did reach it (present in the transcript) and was not
followed. So FR-3's warning can fire only for a planner that declares `files`, and no shim planner is told
`files` exists. Every test passed (171 in the task's suites); the behaviour cannot fire in production --
this repo's named dominant failure mode, caught only by driving.

**Direction (not decided):** make the full description reachable from the shim (`aw-tool --help <tool>`, or
the listing carrying each tool's whole description), and put the `files` field and the same-file rule where
every planner reads it (the exploring duty), stated as a step ("for each task, list `files`; chain any two
that share one"), not a principle. Then re-drive.

## F510 (B) — a task on a loop whose work merges its branch tip can never be given a review turn

**Status:** built on the trial Hub `:8010` (2026-10-06, document `spec/changes/a-review-turn-reviews-the-branch-tip-where-evidence-does-not-govern-the-merge/`): `task_integration.review_target`, tests in `hub/tests/test_a_review_turn_reviews_the_branch_tip.py`; on master as `3bae149`/`4f2face` -- landed through F520, not through its own approval; trial task `task-acc4664bee5a` still `under_review`. Not driven live yet. **Closed 2026-10-07:** `:8010` restarted onto `333fa9d`; task 2 approved by the operator's PATCH -- no check applied (F518), integration `skipped` "838d833643ab is already in master; there was nothing to merge"; loop `loop-ec88f6101755` stopped `completed` ("loop queue is empty"). Reconciled into `openspec/specs/agent-conversation-workspace` (`da1f784`).
Found 2026-10-06 by the acceptance drive of `approval-runs-the-projects-checks` (fresh Hub `:8038`,
profile `checks1006c`). Driven, not read. Area: **Flows & review**.

A loop created with `work_needs_evidence: false` merges its task's branch tip at approval
(`task_integration.evidence_governs`), so its tasks need no evidence, and have none: evidence is
recorded against a requirement, and such a task usually serves none. But a review turn is only ever
handed a commit through evidence (`requirement_evidence.commit_for_task_review`, :985), so
`POST /agent/trigger` with `review_task_id` answers 409 "task ... has no recorded evidence, so there is no
commit to review" -- for every task of that loop, forever. The flow's own review staffing reads the same
function. The drive worked around it with a turn bound to the task.

**Direction (not decided):** where evidence does not govern the merge, review the task's branch tip --
the same commit approval would merge (`task_integration.merge_targets`).

## F511 (D) — what the checks-gate acceptance drive measured

**Status:** noted
`scripts/drive/d1006_checks_gate.py` on `:8038`, real Haiku agents, check `py -3.11 -m pytest -q`:
(1) the builder completed its task mid-turn; the run started at the turn's end and checked the
snapshot commit `0c6adce` (the work), `failed` with `assert -1 == 5`; (2) the reviewer ran pytest
itself and sent the task back -- it never met the gate refusal, so the agent-facing refusal is
test-only; (3) the fix `d25c9d8` `passed` and approval merged exactly that commit; (4) the operator's
approval without a reason was refused, with "drive: intentional override" it merged and the reason is in
`/transitions`; (5) a Hub killed mid-run reads the run `interrupted` after restart. Limits seen: a
killed Hub leaves the run's scratch worktree (removed by the next run on that task) and its check
processes (they finish on their own).

## F512 (B) — a test-first task can never pass a whole-suite check: red-by-design work is refused at approval

**Status:** fixed (Tier 0, operator chose "test and fix in one task"), see commit on fix/f512-f515 -- the exploring duty and `submit_spec_document` say a test and its fix are one task; a task editing only tests that another task `depends_on` draws a `test_only_task` warning (`spec_completeness.test_only_task_warnings`). The gate is unchanged. Test: `test_spec_test_only_task_warning.py`
Found 2026-10-06 on the trial Hub `:8010`, F510 trial slice, task 1 (`task-f5698f83dfc3`). Driven, not read.
Area: **Checks & flows**.

The trial project's checks run the full Hub suite. The slice's task 1 writes the acceptance tests that
MUST fail until task 2 lands (the spec flow's own "acceptance drive first" shape). Its check run
(`task_check_runs`, 19:09–19:18Z) was `failed`: ruff 0, black 0, hub-tests 1 with exactly the 4 new tests
failing, 6887 passed. Approval was refused, and only the operator override
(`override_checks_reason`) let it land. Every test-first task on a gated project will hit this, and an
agent following `REVIEWER_SENDS_BACK_CHECKS` sends correct work back -- the only "fix" open to the
builder is weakening the test.

**Direction (not decided):** a task that another task of the same slice `depends_on` is checked at the
end of its chain, or the failure is compared against the task's declared red tests; or test-first
slices put test and fix in one task.

## F513 (C) — `record_evidence` refuses FR-N as ambiguous although the call names the task that fixes the document

**Status:** fixed (Tier 0, `ae1e447`) -- an ambiguous bare identifier with `task_id` resolves within `Task.spec_document_id`; consulted only when ambiguous. Test: `test_agent_evidence_plane.py::test_a_task_from_one_document_disambiguates_a_bare_identifier`
Found 2026-10-06 on `:8010`, F510 trial slice (`run-6efcf5534b92`). Driven, not read. Area: **Evidence**.

Requirement ids are per-document (`FR-1`...), so any project with two or more documents makes every
bare identifier ambiguous. The builder's three `record_evidence` calls carried `task_id` (a task
materialised from exactly one document) and were all refused 422 "FR-1 is declared by more than one
document in this project. Name the document it belongs to." `_resolve_requirement`
(`hub/hub/api/v1/agent_actions.py:1180`) resolves from `document` only and never reads `task_id`.
Recovered on the second try; costs a round of failed calls on every first evidence of every task.

**Direction:** when `document` is absent and `task_id` names a task linked to one document, resolve
within that document.

## F514 (D) — `ask_user` refuses `multiSelect`; agents trained on Claude Code's own tool send it

**Status:** fixed (Tier 0, `ae1e447`) -- `AgentQuestionCreate.multi_select` accepts `multiSelect`; `ask_user` reads either spelling. Tests: `test_question_batches.py`, `test_blocking_questions.py`
Found 2026-10-06 on `:8010` (`run-492afbb2e8cc`, aw-reviewer). The first `ask_user` call was refused 422
"questions.0.multi_select: Field required; questions.0.multiSelect: Extra inputs are not permitted"
(`hub/hub/schemas/questions.py:35`). Claude Code's built-in AskUserQuestion spells it `multiSelect`.
The agent recovered on retry. **Direction:** accept `multiSelect` as an alias.

## F515 (B) — approving a document writes its phase into the tracked file, and that write then blocks the document's own task merges

**Status:** fixed (Tier 0, `8d5740f`) -- a tracked document whose file still hashes to its `content_digest` is the Hub's write and no longer counts as a dirty checkout; an operator edit to it still does. Test: `test_hub_phase_write_does_not_block_merge.py`. Not changed: the approval response still answers 200 when the merge is skipped (the integration row and the drawer's note carry it)
Found 2026-10-06 on `:8010`, F510 trial slice. Driven, not read. Area: **Spec documents & integration**.

Approving `spdoc-eeaf6a633f2d` rewrote `spec.html` in the project checkout (`aw-spec-status`
exploring→approved, and the phase chip) and left it uncommitted. When task 1 was approved, its
integration (`tint-262b0f3bf2cf`) was `skipped`: "the project's checkout has uncommitted changes to
tracked files". The only dirty file was the Hub's own write. Committing it by hand and calling
`POST /tasks/{id}/integrations/retry` merged (`fb651cd`). An operator who commits the draft (as the
trial practice does) and then approves will hit this on every slice. Also: the approval answers 200 and
the skip is visible only in `task_integrations`, so a reviewer/operator sees "approved" with nothing
landed.

**Direction (not decided):** the Hub commits its own phase write, or integration ignores (or commits)
changes confined to the approved document's own file.

## F516 (B) — a check run's checkout is held to the 60s plumbing timeout, and its `error` is never retried

**Status:** fixed (Tier 0) -- `CHECKOUT_TIMEOUT_SECONDS` (900) for the scratch worktree's add/remove; an
`error` result is not current (`request_run` re-runs it) and approving over one starts a run instead of
refusing. Tests: `test_project_checks_run.py` (errored re-run, checkout timeout), `test_project_checks_gate.py`
(`test_approving_over_an_errored_result_runs_the_checks_again`).
Found 2026-10-06 on `:8010`, F510 trial slice task 2 (`task-acc4664bee5a`). Driven, not read.
The check run recorded `error`: "TimeoutExpired: ... git worktree add --detach --force ... timed out after
60 seconds" (`project_checks._checkout` used `GIT_TIMEOUT_SECONDS`; this repo has 3,308 files and a full
Hub suite was running beside it). It left a `locked` worktree registration behind. `error` counted as a
current result, so approval would refuse on it until an operator override or a manual re-run, although
nothing had judged the work.

## F517 (C) — a reviewer run failed at spawn with `database is locked`

**Status:** fixed (Tier 0, 2026-10-07) -- diagnosed from code: production SQLite ran a rollback journal
(`journal_mode=delete` on the trial DB) with the driver's 5s `busy_timeout`, while the migration engine (F292)
and the suite's pragma listener wait 30s -- so no test could see it. `db/engine.py` now opens connections with
`connect_args_for(url)` (`timeout=30`), and the `Run.pid` write goes through `_record_observation(drop=False)`
like the provider session binding. Tests: `test_engine_waits_out_a_lock.py` (a fresh engine's
`busy_timeout` is 30000; a write lands through a 6s-held lock) and
`test_agent_trigger.py::test_a_locked_pid_write_does_not_fail_a_spawned_run` (failed as `database is locked`
before). The other writer that held the lock 14s is still unidentified. Reaches `:8000` on its next restart.
Found 2026-10-06 on `:8010` (`run-09cdbc599c3f`, aw-reviewer, 19:55:21-19:55:35Z): `(sqlite3.OperationalError)
database is locked [SQL: UPDATE runs SET pid=?]`. The flow staffed a second reviewer run at once
(`run-6e866403a514`), which completed. Coincided with a check run's 60s `git worktree add` (F516), but
`project_checks._execute` holds no session across git calls, so that is not the holder. Watch for recurrence.

## F518 (B) — a check run checks work already on the main branch, and blames its failures on the task

**Status:** fixed (Tier 0) -- `project_checks.unmerged` drops targets already reachable from the main tip,
in both `view` and `request_run`; nothing unmerged means no check applies. Test:
`test_project_checks_run.py::test_work_already_on_main_is_not_checked`. Driven 2026-10-07 on `:8010`
(`333fa9d`): approving `task-acc4664bee5a`, whose targets `252076c`/`838d833` are both on master, started no
check run and the gate did not wait on one.
Found 2026-10-06 on `:8010`, F510 slice task 2. Its check run's `target_shas` were `[252076c]`: task 1's
accepted evidence, already merged (`fb651cd`), because both tasks serve FR-1..3. `merge_targets` names
accepted evidence for the task's requirements; before task 2's own evidence is accepted, that is only work
on main, so the run checked main itself (red by design at that moment) and the review briefing would have
stated those failures against task 2.

## F519 (B) — a reviewer judges a dependent task's diff without its dependency's work, and sends correct work back

**Status:** fixed (Tier 0) -- the review briefing (`review_turn._dependencies_sentence`, inside `verdict_evidence_sentence`, so both channels carry it) names each `depends_on` task with its title and merged commit, or its status if unmerged, and says merged work is not in this diff. Test: `test_review_briefing_names_dependencies.py`
Found 2026-10-06 on `:8010` (`run-6e866403a514`). Task 2 (the fix) `depends_on` task 1 (the F510 acceptance
tests, merged as `fb651cd`). The reviewer sent task 2 to `revision_needed`: "the diff adds no tests for any
of the six acceptance criteria". The 7 tests are task 1's, on main, and pass on task 2's branch (run by hand:
`7 passed`). The review briefing does not name the tasks this one depends on or where their work is.
F512's one-task rule removes this shape for new documents; documents that legitimately chain tasks still
meet it. **Direction:** the review briefing names each `depends_on` task, its status, and its merged commit.

## F520 (A) — accepting one task's evidence merges it into main through another approved task that serves the same requirement

**Status:** fixed (Tier 2, `a-siblings-evidence-lands-through-its-own-task`, `554f303`..) -- `task_integration._targets` counts another task's evidence only once that task is approved; `tasks_awaiting_this_commit` re-integrates no sibling for it. Acceptance: `test_sibling_evidence_waits_for_its_task.py` (failed on master, passes). The trigger was `integrate_what_was_waiting_for_this_evidence` (the decision route).
Found 2026-10-06 on `:8010`, F510 trial slice. Driven, not read. Area: **Evidence & integration**.

Task 1 (`task-f5698f83dfc3`) was approved and merged at ~19:2xZ. Task 2 (`task-acc4664bee5a`) serves the same
FR-1..3. At 21:10Z the operator accepted task 2's six evidence items. At 21:11:21Z and 21:11:22Z,
`task_integrations` recorded two `merged` rows **for task 1** with task 2's commits (`ea8795a` -> `3bae149`,
`838d833` -> `4f2face` on master), `actor_kind=operator`. Task 2 was still `under_review`, never approved,
and every one of its check runs had `error`ed. So its review verdict and the checks gate were both bypassed.
`merge_targets` for a task is the accepted evidence for its requirements from any task, so an approved task
whose integration runs again picks up a sibling's accepted, unapproved work. The trigger for the
re-integration at 21:11 is not yet identified (the evidence decision route, or the reachability refresh).
**Direction:** a task's merge targets are the accepted evidence recorded *by that task* (or by tasks already
approved); never a sibling still under review.

## F521 (B) — a half-made check worktree stays `locked` and refuses every later run

**Status:** fixed (Tier 0, `d61c2b7`) -- `_remove_checkout` unlocks before a double-forced remove. Test: `test_project_checks_run.py::test_a_locked_leftover_checkout_does_not_refuse_the_next_run`.
Found 2026-10-06 on `:8010`, task 2. After F516's timeout the scratch worktree
`.agentweave/checks/task-acc4664bee5a` was left registered and `locked` (`git worktree list`), and both later
runs (20:16Z, 21:11Z) recorded `error`: "fatal: '...' is a missing but locked worktree; use 'add -f -f' to
override, or 'unlock' and 'prune' or 'remove' to clear". `_remove_checkout` runs `worktree remove --force`
(one `-f` does not remove a locked worktree) and `worktree prune` (which skips locked ones), so the run
can never recover by itself. **Direction:** unlock before removing, or `remove -f -f`.
Not driven live: on 2026-10-07 the leftover was cleared by hand (`unlock` + `remove -f -f`) before `:8010`
restarted, so the fix has its unit test only.

## F522 (C) — the integration preview counts commits already on the main branch as "will merge"

**Status:** fixed (Tier 0, 2026-10-07) -- the preview filters its targets through `project_checks.main_tip` + `unmerged` (F518's question), so work already on the main branch is not counted; with nothing left it says "its commit is already in <main>; approval merges nothing" and `will_attempt_merge` is false. Test: `test_the_preview_asks_the_merge_question.py::test_work_already_on_main_is_not_counted_as_merging` (listed the merged commit before).
Found 2026-10-07 on `:8010` (`333fa9d`), task `task-acc4664bee5a`. `GET /tasks/{id}/integration-preview`
answered `will_attempt_merge: true`, "approval will merge 2 commits into master; it merges cleanly as of now"
for targets `252076c`/`838d833` -- both already reachable from master. Approving then recorded `skipped`,
"838d833643ab is already in master; there was nothing to merge". The preview (`api/v1/tasks.py:1171-1194`)
never asks reachability; `project_checks.unmerged` (F518) already does, so the drawer and the merge give two
answers to one question. **Direction:** filter the preview's targets through the same reachability test and
say "already in master; approval merges nothing".

## F523 (B) — `list_tasks` returns every task in one result, and a real board spills it to `tool-results/`

**Status:** fixed (Tier 0, 2026-10-12) -- the agent-facing `GET /agent-actions/tasks` writes a page over `spec_reading.READ_BUDGET_CHARS` to `<workspace>/.agentweave/reads/tasks.<agent>.<status>.<offset>.md` and answers `{total, has_more, count, task_ids, written_to, read_with}`; with nowhere to write it cuts the page to fit and `has_more` says so. Test: `test_list_tasks_read_budget.py` (failed before at the size assertion). Drive: real stdio MCP `list_tasks` on a throwaway Hub with 60 tasks answered 1,766 characters, the file held all 60.
**Source:** drive (F363, LoopEngine on `:8000`, read-only)
**Theme:** Agent tool surface

F363 measured `list_tasks` spilling 24 times on LoopEngine alongside `read_spec_document`'s 57: the
whole board in one tool result, over Claude Code's spill threshold (50,000 for an MCP result, 30,000
for `aw-tool` through a shell). The spill file lies outside the workspace, and the guard refuses it.
**Direction:** the same answer `read_spec_document` took (D7 of
`a-specification-is-read-in-results-that-fit`): inline within 25,000 characters, otherwise written
to `.agentweave/reads/` in the run's workspace with the path in the answer; or filters that keep a
board's read small.

## F524 (C) — on Windows the Hub wrote every specification document and the index with CRLF line endings

**Status:** fixed (Tier 0, 2026-10-07) -- `spec_documents.write_document` and `write_index` pass `newline="\n"`. Test: `test_spec_index_writer.py::test_the_hub_writes_documents_and_the_index_with_lf_line_endings` (read `\r\n` back before). The Hub's other text-mode writes land in git-excluded or Hub-private files (`.agentweave/context/`, `.agentweave/project.json`, `.git/info/exclude`, the instance id) and were left.
**Source:** drive (Phase 3 migration, 2026-10-07)
**Theme:** Spec & requirements

Found committing the migration: git warned "CRLF will be replaced by LF" for all 59 files the trial Hub
had written. `Path.write_text` in text mode turns `\n` into `\r\n` on Windows. This repository's
`* text=auto eol=lf` normalised them, so nothing reached history; a project without that rule would see
every Hub write as a whole-file change. The stored `content_digest` was unaffected (it is taken of the
rendered string, and a read normalises line endings).

## F525 (B) — the first Scan for drift after the legacy backfill raises a candidate for most old evidence at once

**Status:** fixed by operator decision (option d, 2026-10-07) -- a legacy row rebuilt from its merge takes today's main as its baseline; one rebuilt from its locator keeps its verified commit. On a copy of the trial DB the merge rows then raised 0 (was 10). Was: open (filed 2026-10-07 by the acceptance drive of `drift-watches-the-files-its-evidence-is-about`; a decision for the operator, not a defect in the build)
**Source:** drive
**Theme:** Spec & requirements

On the trial Hub `:8010`, project `proj-d85a82bf4216` (this repository), 31 accepted footprints were
legacy (`watched_from` NULL). The first `POST /spec/drift/detect` rebuilt 28 (15 from their locators,
13 from the merge that brought them in) and then raised **19 candidates**. Every one is technically
true -- a watched file changed on `master` after the evidence was verified -- but most are noise:
`scripts/drive/FINDINGS.md`, `.claude/autonomous/*night-log.md`, `STATE-night.json`, openspec change
documents since archived or moved (`now: null`), and code edited later the same day. The `["merge"]`
rule watches everything a merge brought in, ledger and log files included, and the baseline is the
stored commit's blob, so any file touched since raises. `:8000`'s evidence is older, so a similar
burst is expected there on its first scan after restart.
**Options:** (a) keep -- each is a real question, answered in bulk once 4c's drift panel exists;
(b) rebuild a legacy row's baseline at the current main tip, so only changes from now on raise (loses
"changed since it was verified" for old rows); (c) rebuild from the locator only, leaving merge-only
rows unwatched (13 of 28 here); (d) (b) for merge-rebuilt rows and the stored commit for locator rows.


## F526 (B) -- an `agentweave-mcp` started with no `HUB_URL` silently targets the operator's real Hub on `:8000`

**Status:** fixed (Tier 0, 2026-10-08 night), pending CI. `main()` exits 1 naming `HUB_URL` when it is unset or blank, and `_hub_request` raises `UnboundIdentityError` (call mode: kind `unbound`, exit 2) before any connection; the `:8000` default is gone. The run token is deliberately not checked at start: the permission approver runs without one (its wire tests pop it) and every effect already refuses in `_bound_token`. Driven: the file spawned with no environment exits 1 with the message; `--call list_tasks` without `HUB_URL` returns the `unbound` envelope. Five wire tests and two unit tests relied on the default and now set `HUB_URL`.
Was: open. Filed 2026-10-07 (interactive, while choosing how to author in the app). This repo's
Claude Code config (`~/.claude.json`, project `AgentWeave`) starts `agentweave-mcp` with no
environment, and `hub/hub/mcp_server.py:221` falls back to `http://127.0.0.1:8000`. Any MCP tool an
interactive session called would have gone to the operator's live instance -- the one CLAUDE.md
says never to call -- with no run credential (`AW_RUN_TOKEN`) to act under. Nothing broke because
the session never called it. Repair shape: refuse to start (or answer every tool with a refusal
naming the missing variable) when `HUB_URL` or the run token is absent, as the Hub itself now
refuses to open an unnamed database.


## F527 (C) -- a change document names no capability, so reconciling an archived change into the corpus is a hand-written script

**Status:** fixed in substance (2026-10-08) by `a-finished-change-is-folded-into-its-capability`: the fold route and the app's **Fold into capability…** carry an approved change's requirements into a capability in one audited merge, and archiving an unfolded change asks for a reason. Not done: the change-spec payload still names no capability; the operator picks it at fold time. Was: open. Filed 2026-10-07 (first change authored in the app after the switch,
`a-decided-task-withdraws-its-waiting-reviews`). The change-spec payload has no field for the
capability document(s) it amends, and the app offers no step that carries an approved change's
requirements into them. Reconciling F440 into `spec/capabilities/run-task-binding/spec.html` meant
`extract_payload` on the file, appending a requirement and three criteria in Python, and a `PUT` of
the whole payload (`scripts/drive/reconcile_f440.py`). openspec's delta-and-archive did this as one
step; here it is invisible to the flow, so nothing reminds the author and coverage cannot say which
change a capability requirement came from.


## F528 (C) -- `close-exploration` and `propose` answer 200 for a document whose content was refused

**Status:** fixed (Tier 0, 2026-10-08 night), pending CI. `propose` keeps its 200 -- "not yet" is one shape, the `blocking` list (F113,
`a-document-moves-forward-only-through-its-checks`; the UI and ~15 drive scripts read it) -- and now carries `proposed: true|false`, true only when the phase is
`proposed`. `close-exploration`'s 200 is truthful and unchanged: it records the operator's judgement that exploration is over (`explore_closed: true`) and never
claimed the content was usable; the mechanical half is `propose`'s to report. Driven on a throwaway Hub (:8043): refused PUT 422 -> close 200 -> propose 200
`{phase: exploring, proposed: false}` with blockers. UI type not touched (the field is additive; a `hub/ui/src` edit would need a bundle commit that reaches :8000 live).
Was: open. Filed 2026-10-07 (same authoring). A `PUT .../content` refused with 422
(`modal must be one of MUST, SHOULD, MAY, SHALL` -- `MUST NOT` is not a modal) left the document
empty; the script's following `close-exploration` and `propose` both answered **200**, `propose`
with `phase: exploring` and a `blocking` list. A caller reading the status code believes it
proposed. A refused proposal should be a 4xx naming the blockers (or the 200 body should say
`proposed: false` in a field a client checks).

## F529 (C) -- operator evidence always pins the HEAD it was recorded at, never the commit that did the work

**Status:** fixed (Tier 0, 2026-10-08, `55be440`): operator evidence takes an optional `commit`, verified like F71's locator commit and footprinted there; `close_change.py` sends a change's `commit` (`hub/tests/test_operator_evidence_names_the_commit_that_did_the_work.py`, 2 red before). Not checked reachable from main (the footprint records `reachable_from_main`, which drift and integration read). Drive `scripts/drive/d1008_findings_drive.py f529`: 422 before, footprint at the named commit after. Was: open. Filed 2026-10-07, closing F440, F450 and F425's change tasks on `:8010`
(`scripts/drive/close_change.py`). All twelve operator evidence rows carry footprint commit
`0300f0f` (HEAD at recording, a one-line script commit), not the commits that built each change
(`49dedde`, `3212bee`, `546fa92`). `EvidenceRecord` (`hub/hub/api/v1/spec.py:451`) has no commit
field, so the operator cannot say which commit demonstrates the requirement; recording late, as an
operator closing work after the build always does, ties the evidence to an unrelated commit.
Harmless for integration here (already in master), but drift and "what does this evidence
describe" read the wrong commit. Suggested: an optional `commit` on the operator's record, checked
reachable from the main branch, defaulting to HEAD as now.

## F530 (B) -- under xdist a leaked `shutil.which` patch makes `pty_runner` spawn `/usr/bin/claude`, and CI's hub-test goes red by order

**Status:** fixed (Tier 0, 2026-10-07 night), pending CI on two consecutive pushes -- the leak was not `shutil.which` itself: `ptyprocess.util` / `winpty.ptyprocess` do `from shutil import which` at first import, and `PtySession.spawn` imports them lazily, so the first real pty spawn in a worker made under a faked `which` pinned the fake for the worker's life (an absolute `sys.executable` never reaches `resolve_executable`'s lookup; ptyprocess re-resolves argv[0] itself). 18 tests in 8 files fired a real trigger under `patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude")` with no spawn stub; they now use the conftest fixture `no_agent_cli_spawn` (spawn fails as the fake path did, no backend import). Guard: `pytest_runtest_teardown` in `hub/tests/conftest.py` fails the test that leaves `which` changed in `shutil` or a pty backend. Found on Linux (WSL) only: on Windows no leaker is first to spawn. All 18 named by running the which-patching files with a diagnostic plugin that forgets ptyprocess before every test (`testbed/f530/fresh_pty.py`, untracked): 17 errors before, 0 after; the 18th was named by the guard's first plain run and missed by the diagnostic one, because the spawn runs in a background task that races the `with patch` exit. A 19th, `test_a_loop_does_not_staff_its_own_review.py::test_the_operator_can_still_review_a_loops_completed_task_by_hand`, was named by the guard in CI on 8de6be7 (hub-test red; the guard worked as designed) and got the same fixture on 2026-10-08; WSL full `-n 4 --dist loadfile` with the guard and the diagnostic plugin: 7135 passed, 0 failed. Lesson: the F530 sweep was by local worker placement, so a leaker can survive it. A 20th, `test_a_flows_moves_are_the_flows.py::test_an_operators_by_hand_review_is_the_operators`, was named by the guard in CI on 9c6a73f (the night's close-out, whose run it never read). 2026-10-08 (interactive) the sweep was made deterministic instead of placement-dependent: a recorder plugin wrapping `PtySession.spawn` (`testbed/f530/spawn_recorder.py`, untracked) logs, for every spawn, the running test and whether `shutil.which` is faked at that moment. Over all 53 which-patching files it named exactly three more, all through `_dispatch_review` in `test_review_dispatch_staffs_the_task.py` (by-hand review, already-staffed review, binding order); every other spawn under a faked `which` was already stubbed. All four took `no_agent_cli_spawn`; the recorder then logs 0 spawns under a fake.
Was: open. Filed 2026-10-07 ~22:52 (interactive), the night after `741f44e` put hub-test on `-n auto --dist loadfile`.
CI run `37683661654` (job `113005821492`, commit `99d9cdf`, a METRICS-only commit): `8 failed, 7082 passed`, all `OSError: [Errno 2]`:
seven in `test_pty_runner.py` (`TestProcessSessionSpawn`, `TestPidAlive`, `TestTerminateProcessTree`) and
`test_lifespan_shutdown.py::test_hub_shutdown_kills_a_real_tracked_process`, all on worker `gw1`. The run before it on the
same test tree (`075ae20`, `37682640540`) was green, so it depends on which files share a worker. The traceback shows
`argv = ['/usr/bin/claude', '-c', "print('hello from pty')"]` at `hub/pty_runner.py:260`: the test passed `sys.executable`,
and `resolve_executable` (which calls `shutil.which`) returned `/usr/bin/claude`. So a `shutil.which` patch returning
`/usr/bin/claude` was still in force. 53 test files patch it, most as `patch("hub.runner_adapters.base.shutil.which", ...)`,
which replaces the global `shutil.which`. A likely way to leak it: two overlapping patches of the same attribute exited
out of order (a background run outliving its `with` block), so the later one restores the earlier one's fake.
Suspected, not proven.

Fix: find the leaker. An autouse guard in `hub/tests/conftest.py` that fails the test leaving `shutil.which` different
from the real function names it; then fix that test. Do not drop `-n`, and do not patch around it in `test_pty_runner.py`.
Acceptance: CI green on two consecutive pushes, plus a local `-n 4 --dist loadfile` run with the guard in place.

## F531 (B) -- a Hub Claude run loads the operator's own claude.ai connectors (Gmail, Drive, Calendar, Docs)

**Status:** fixed 594f477 (Tier 2, 2026-10-08): `--strict-mcp-config` on every Claude agent turn; acceptance drive 1/3 -> 3/3 on `:8010`; reconciled into `agent-run-sandboxing`. Reaches `:8000` at its next restart, after which project `.mcp.json` and user-scope servers no longer load in agent runs (a runner `--mcp-config` flag brings one back). Codex runs still read `~/.codex/config.toml` servers: not checked (Codex undrivable). Was: proposed, Tier 2 (operator, 2026-10-08: "fix now"): `spec/changes/a-hub-claude-run-gets-only-the-hubs-tool-server` (`spdoc-721c3e827237`, trial project `proj-d85a82bf4216`). Acceptance drive `scripts/drive/d1008_f531_no_connectors_drive.py` 1/3 on today's code (no flag in the argv; the agent named 8 `mcp__claude_ai_Claude_Docs__*` tools). Was: open (filed 2026-10-08, interactive, from the F21 probe).

`runner_commands._build_claude_command` passes `--mcp-config` without `--strict-mcp-config`, so a Hub run also gets
whatever MCP servers the operator's own Claude Code configuration and account carry. Read from `system/init` of a
Hub-shaped `claude -p` (Haiku, the Hub's `--mcp-config` with `"alwaysLoad": true`, which makes startup wait for servers):
`mcp_servers` held `claude.ai Claude Docs` (connected, its tools in the run's tool list) and `claude.ai Google Drive`,
`Google Calendar`, `Gmail` (needs-auth). Without `alwaysLoad` the connectors are absent from `system/init` only because
they attach after it, so a plain init read-out (R1's method) reports them missing.

Why it matters: an agent run can reach the operator's account tools that no Hub surface granted, describes, or records;
under `bypassPermissions`/yolo they are callable with no prompt. It also adds their schemas to every run's context. The
Hub already applies the remedy elsewhere: `conversation_titles.py:82` passes `--strict-mcp-config` for exactly this reason.
Likely fix: `--strict-mcp-config` whenever `_claude_mcp_args` injects the Hub's server (and decide what a run with no
server gets). Acceptance drive: a Hub run's tool list on `:8010` names no `claude_ai_*` server.

## F532 (C) -- the Hub cannot delete a specification document, a task or an agent

**Status:** fixed a29a308 (Tier 2, 2026-10-08, authored in the app: `spec/changes/the-operator-can-delete-a-document-a-task-or-an-archived-agent`): `DELETE /project/documents/{path}` and `DELETE /tasks/{id}` with their cascades in `hub/hub/deletion.py` (a guard test covers every reference column), Delete in the phase bar and the task drawer. Agents are still archived, never deleted (the operator kept `agent_lifecycle`'s decision); instead a runner no open agent holds now deletes, unbinding its archived holders. Drive 1/9 -> 9/9. Was: open (filed 2026-10-08, interactive, from cleaning the trial project `proj-d85a82bf4216`).

The operator API deletes projects, runners, jobs and charters (`@router.delete` in `projects.py`, `runners.py`,
`jobs.py`, `charters.py`) and nothing else. Clearing drive residue out of this repo's own trial project (26 documents
with no file, 28 tasks, 20 archived agents and their 168 runs) therefore took a hand-written cascade over 30 tables
against the database with the Hub stopped (4,793 rows; backup `agentweave.db.bak-20261008-cleanup`). An archived agent
also still blocks deleting its runner (`runners.py:238`), so archive is not a way out. Likely shape: delete for an
exploring/proposed document that produced nothing (the archive edge F37 already allows), for a task nobody worked, and
for an archived agent with its history -- each refusing what has evidence or a merge behind it.

## F533 (C) -- a fold cannot amend or retire what a capability already says

**Status:** fixed 407e9fc (Tier 1, 2026-10-08, authored in the app: `spec/changes/a-fold-can-retire-what-the-change-supersedes`): a fold takes `retire` and `retire_criteria`, applied in the same merge; the dialog offers the capability's requirements and criteria. Drive 2/7 -> 7/7; folded into `spec-document-authority` and archived. Was: open (filed 2026-10-08, interactive, closing `a-finished-change-is-folded-into-its-capability` with its own fold).

The fold appends a change's requirements and criteria and can replace a whole requirement (`replaces`), but cannot edit
or remove an existing acceptance criterion or retire a requirement. Restating `spec-document-authority`'s `ac136` (which
the change contradicts) took a second, hand-built merge naming no change (`a504858`). A change that narrows or retires
behaviour has no fold path at all. Likely shape: the change payload states what it modifies or removes in the capability
(by key), and the fold draft shows those edits beside the appended text.

## F534 (C) -- a merge into a capability answers with change-spec completeness findings

**Status:** fixed (Tier 0, 2026-10-08): `spec_completeness.check` asks a capability for neither tasks nor non-goals; criteria and clarification rules still apply (`hub/tests/test_a_capability_is_not_held_to_change_rules.py`, 2 of 4 red before). Was: open (filed 2026-10-08, interactive, from the `ac136` merge edit).

`POST .../documents/{capability}/merge` returned 200 with `blocking` holding `non_goals_empty` and 76
`requirement_without_task` entries for `spec-document-authority`: the completeness checks for a change document run
against a capability, which by design has no tasks and no non-goals. Nothing is blocked (the merge wrote), but a caller
reading `blocking` sees a document that is wrong in 77 ways. Likely fix: skip the task and scope rules for
`kind == "capability"` in the completeness check, or omit `blocking` from the merge response.

## F535 (C) -- re-approving an amended document leaves its tasks as the first approval made them

**Status:** fixed (Tier 1, 2026-10-08, `spec/changes/re-approving-an-amended-document-refreshes-its-open-tasks`, `spdoc-7f722adeb750`, folded into `task-lifecycle-governance` and archived): operator chose "Refresh open tasks". Re-approval refreshes an open declared task's title, description, criteria and same-document links (status, assignee, priority, other documents' links untouched); approved/rejected tasks stay frozen; `approval_outcome` lists `refreshed`, `closed_linking_retired`, `no_longer_declared`, shown in the app's report (`hub/tests/test_re_approving_refreshes_open_tasks.py`; drive `d1008_reapproval_refresh_drive.py` 4/10 -> 10/10). Was: open (filed 2026-10-08, interactive, from amending F532's document after the operator kept agent archival).

Reopening an approved change, replacing a requirement (`agent` FR-3 retired, `runner` FR-5 minted) and approving again
created no task and changed none: the `backend` task kept its first title and its link to the retired FR-3, and FR-5 was
served by no task until the operator linked it by hand (`PATCH /tasks/{id}` with `requirement_ids` and `spec_document`,
since an identifier like FR-5 exists in many documents). Coverage would otherwise show the new requirement unserved while
a task still claims a retired one. Likely fix: at re-approval, reconcile the board with the document's declared tasks
by key -- refresh title, description and requirement links of a task the document still declares, and report (not
silently drop) links to retired requirements.

## F536 (C) -- a capability can be neither deleted nor retired, so the corpus cannot lose one

**Status:** fixed 14695f6 (Tier 2, 2026-10-08, authored in the app: `spec/changes/a-capability-can-be-retired`, folded into `spec-document-authority` and archived): the operator retires a capability to `archived` with a reason and optional absorbing capability (migration 0121); its requirements are retired on every reindex, merge/fold into it is refused, `GET /spec` says why. Drive `d1008_retire_capability_drive.py` 0/7 -> 8/8. Was: open (filed 2026-10-08, interactive, spec overhaul).

`spec/capabilities/quiet-hours/` describes a feature nothing implements (no match for quiet hours anywhere in `hub/`
or `src/`, absent from `openspec/specs/`); it entered the trial corpus on 2026-08-18 as a sample and was adopted as
`current` on 2026-10-07. There is no way out: `DELETE /documents/{path}` refuses with `delete_capability` ("a capability
is the corpus; change it through a merge instead", `hub/hub/deletion.py:201`), `current` has no transition in
`spec_lifecycle.TRANSITIONS`. A merge can empty it (`validate_payload` accepts a capability with no requirements), but it
then stays listed in the map and the index as an empty `current` capability. The same wall stops the overhaul from
merging two overlapping capabilities: the absorbed one is left behind as a shell. Likely fix: a `retired` end state for
a capability (operator-only, recorded with a reason and, when merged away, the capability that absorbed it), its
requirements retired with it, dropped from `spec/index.json` and coverage, the file kept as history.

## F537 (C) -- the openspec corpus importer dropped every wrapped line of a scenario clause

**Status:** fixed 2026-10-13 (night iteration 24, Tier 0). `parse_scenario` joins an indented continuation line to the clause it wraps (`scripts/migrate_openspec_corpus.py`); `tests/test_migrate_openspec_corpus_wrapped_clause.py` has 3 of its 4 tests failing before the fix (the fourth pins unchanged behaviour) and all passing after. Driven: the converter run on `agent-capability-plane` into a temp dir now emits "...presented to an operator API" whole; `spec/` untouched. Corpus repaired earlier. Filed 2026-10-08 (interactive, spec overhaul). The 2026-10-08 overhaul restored 117 cut clauses from `openspec/specs/` in the capabilities it rewrote; the converter itself is unchanged.

`scripts/migrate_openspec_corpus.py:147-153` (`parse_scenario`) keeps a GIVEN/WHEN/THEN/AND bullet's first physical line and
skips any continuation line that does not start with `-`, so a clause wrapped in the source markdown was imported cut
mid-phrase: `agent-capability-plane` ac3 read "a run credential is presented to an" (source lines 33-34 continue
"operator API"). At least 261 of 9,174 imported clauses ended on a dangling word; requirement statements and
rationales were unaffected (0 of 1,542). Fix if the converter is ever run again: join indented continuation lines.

## F538 (C) -- a checkpoint can fire on a context window that was never measured

**Status:** fixed 2026-10-13 (Tier 0, branch autonomous/2026-10-11-daily). `resolve_usage_limit` returns an `unavailable`/`unsupported` sample untouched, and `consider_from_reading` drops the percent of one (the provider-reported token count still counts toward a token threshold). Tests `test_an_unavailable_sample_is_not_completed_from_the_catalog` and `test_a_checkpoint_is_not_considered_on_a_percent_of_an_unmeasured_window` failed before. Driven: the real `copilot_acp.usage_sample` for `used` with no `size` on `claude-sonnet-5` now resolves to no limit and no percent, and the trigger is dispatched with `percent=None`; a measured sample still resolves 1.22% of 1,000,000. **Not verified:** no live Copilot run; full Hub suite not run (CI is the full check). Filed 2026-10-08 (spec overhaul audit; found by running `output_recording.resolve_usage_limit`).

`output_recording.resolve_usage_limit` fills the catalog's window into any usage sample, including one marked
`unavailable`: a Copilot `usage_update` with no `size` on `claude-sonnet-5` came back with a 1,000,000 limit and 1.22%.
`checkpoint_trigger` reads `percent` without checking `status`, so a threshold can be crossed (or never crossed) on a
window nobody measured.

## F539 (C) -- the checkpoint a successor receives drops the wait-ended mark on open questions

**Status:** fixed 2026-10-10 (Tier 0, branch autonomous/2026-10-10-daily). `render_checkpoint` now ends an open question's line with "(wait ended: the asker stopped waiting for an answer)" when the stored `wait_ended` is set; a question still waited on renders as before. `test_the_render_tells_a_question_whose_wait_ended_from_one_still_waited_on` failed before. The cut-over delivery (`checkpoint_cutover.py:111`), the probe prompt and the checkpoint routes all render through this one function. Hub subset (checkpoint/probe/cutover/handover/question) 492 passed. **Not verified:** no live-Hub drive of a real cut-over with a timed-out `ask_user` (needs a checkpoint worker run). Filed 2026-10-08 (spec overhaul audit, reading code).

`checkpoints.py:355` sets the flag that a question's wait ended, but `render_checkpoint`
(`checkpoint_generation.py:323`) does not render it, and the rendered text is what the successor is given
(`checkpoint_cutover.py:109`). The successor cannot tell a question still open from one whose wait expired.

## F540 (C) -- a failed automatic checkpoint is invisible to the operator

**Status:** fixed 2026-10-10 (Tier 0, branch autonomous/2026-10-09-daily, DECISIONS `overhaul-failed-checkpoint`). The conversation now shows a `checkpoint-failed` problem banner when its newest checkpoint is an automatic one that is `unwritten` or `failed`, naming the reason (the worker invocation's `generation_error`, else the failed probe dimensions) with a `Retry checkpoint` action (the operator checkpoint-and-cut-over path). A newer checkpoint of any kind clears it. Tests: three in `agentHandoff.test.tsx` failed before (no banner); `test_the_list_leads_with_a_failed_automatic_checkpoint_and_says_why` pins the route's newest-first order and `generation_error`. UI bundle rebuilt and refreshed. **Not verified:** no live-Hub drive of a real failed generation (needs a checkpoint runner that fails); full Hub suite not run. Filed 2026-10-08 (spec overhaul audit, reading code).

`checkpoint_trigger.py:403` records the failure, but the conversation's banner renders only a `ready` checkpoint
(`AgentOutputPanel.tsx:613-616`); nothing in the conversation says the automatic checkpoint was attempted and failed.

## F541 (C) -- checkpoint token thresholds are checked against the wrong window, or not at all

**Status:** fixed 2026-10-10 (Tier 0, branch autonomous/2026-10-09-daily, DECISIONS `overhaul-token-threshold-window`). `PATCH /agents/{name}` now refuses a token threshold at or above the window of the agent's own model (bound runner's, else `config.model`; unknown window accepts), judged against the runner the same body binds. `PUT /projects/{id}/settings` no longer judges the threshold against the checkpoint worker's `checkpoint_model`; it saves and answers `warnings` naming each open agent that inherits the threshold and cannot reach it. Tests `test_a_token_threshold_above_the_agents_own_window_is_refused` and `test_a_project_threshold_that_cannot_fire_for_an_agent_is_saved_with_a_warning` (and the worker-window one) failed before. ASGI only, no live-Hub drive. **Not done:** the app does not yet show `warnings` (a `hub/ui/src` edit plus a bundle refresh); an agent that later rebinds to a smaller-window runner is not re-judged. Filed 2026-10-08 (spec overhaul audit, reading code).

A project's token threshold is validated against the checkpoint worker model's window (`api/v1/projects.py:171`),
not the window of the agents it applies to; an agent-level token threshold is not validated at all
(`api/v1/agents.py:2703`).

## F542 (C) -- a spent checkpoint is still offered for cutover on the archived predecessor

**Status:** fixed 2026-10-10 (Tier 0, branch autonomous/2026-10-10-daily). `AgentOutputPanel` no longer offers a checkpoint whose `cut_over_to_conversation_id` is set, and a 409 shows the Hub's own sentence (`readableRefusal`, the old generic text kept as the fallback for a body that is not a refusal). Both tests in `agentHandoff.test.tsx` failed before. Vitest only, no browser drive; the route returning the field is covered by `test_checkpoint_handover.py:223`. Filed 2026-10-08 (spec overhaul audit, reading code).

The offer banner ignores `cut_over_to_conversation_id` (`AgentOutputPanel.tsx:613-615`), so the predecessor still
offers a checkpoint already used; pressing it earns the Hub's 409, which the UI replaces with a generic "finish or stop
the run" instead of the Hub's sentence naming the successor (`:626-630`).

## F543 (C) -- an agent's loop and flow rules exist only in the MCP adapter

**Status:** fixed 2026-10-10 (Tier 0, branch autonomous/2026-10-09-daily). `create_job` (`api/v1/jobs.py`) now refuses, before any row, a flow-evidence declaration beside a document (every caller) and a loop with no stop condition when an agent run asks (the operator keeps the spec's optional stop; agent-loops ac39). The third rule, a document making the call a flow, needed nothing: a document on the route already does. Tests `test_an_agent_cannot_create_a_loop_that_cannot_stop_by_posting_to_the_route` and `test_a_flow_refuses_the_evidence_declaration_on_the_route_as_the_tool_does` failed before. ASGI only, no live-Hub drive. Filed 2026-10-08 (spec overhaul audit, reading code).

`create_loop`/`create_flow` refuse a loop without a stop condition, make a loop naming a document a flow, and refuse
`work_needs_evidence` on a flow only in `mcp_server.py:822-940`. `POST /agent-actions/jobs` passes straight to
`jobs.py:722`, which builds a loop from `purpose` alone, so an agent reaching the HTTP plane directly gets none of
them, against the plane's equal-capability rule. Operator question recorded in DECISIONS.md (`overhaul-agent-loop-rules`).

## F544 (C) -- an explicit "Workspace only" Claude run without the tool server denies every prompted call

**Status:** fixed 2026-10-13 (night iteration 13; `_build_claude_command` swaps the explicit Workspace-only `--permission-mode manual` for `acceptEdits` when no MCP server is configured and logs a WARNING saying so; `test_permission_approver.py` 3 cases, driven through `build_command`; `manual` (Ask me) left as chosen; only the Hub log says so, no UI notice). Filed 2026-10-08 (spec overhaul audit, reading code).

On a Claude run with no MCP server, an explicitly chosen Workspace-only posture yields `--permission-mode manual` with
no `--permission-prompt-tool` (`runner_commands.py:247-263`), so every call that would prompt is refused. The built-in
default falls back to `acceptEdits` in that case; the explicit choice does not.

## F545 (C) -- an exploring spec turn is told two contradictory ways to ask its questions

**Status:** fixed 2026-10-10 (exploring-prose, `spdoc-a56fa9bf6cdd`, night iterations 29-33): an exploring turn is told to ask in its reply, step duties and the ask_user text no longer say otherwise; `scripts/drive/d1020_exploring_prose.py` 4/4 on the committed tree, `d1009` checks 1-5 pass with check 3 amended. Filed 2026-10-08 (spec overhaul audit, reading code).

The turn notice says "Interview in THIS REPLY, in prose … Then stop" (`launchability.py:380`); the turn context
says ending a turn without submitting or calling `ask_user` "is not a way to finish. Questions written as ordinary
reply text reach nobody" (`api/v1/agents.py:2254`). Both reach the same turn. Operator question in DECISIONS.md
(`overhaul-exploring-interview`).

## F546 (C) -- a declared task title is cut to 80 characters mid-word

**Status:** fixed ea32608 (2026-10-12; `_title_for` clips through the same word-boundary clip as `_title_from`; drive d1012 7/7). Filed 2026-10-08 (spec overhaul audit, reading code).

The payload allows a declared task `title` of 200 characters (`spec_payload.py:116-120`); materialisation cuts it to
80 with no word boundary (`spec_tasks.py:186`), the failure the derived-title rule exists to prevent.

## F547 (C) -- the fold draft is served for a change that is not approved

**Status:** fixed a530484. Filed 2026-10-08 (spec overhaul audit, reading code). Minor: the fold itself refuses. Fixed 2026-10-12 (night iteration 13): `spec_service._require_approved_change` is shared by `fold_draft` and `fold`; route test and drive `d1012_f547_fold_draft_phase.py` (11/11, 1 fail pre-fix).

`GET …/fold-draft` has no phase check (`spec_service.py:877-900`), so the app can show a draft for an exploring change.

## F548 (C) -- a divergence recorded for a run whose task someone else decides never closes

**Status:** fixed 2026-10-13 (Tier 0, night iteration 14): `evaluate_run_end` records nothing for a task already `approved`/`rejected` at the boundary (decided by someone else while the run was live; the decision had already resolved every open divergence, so a later row was born unresolvable, and `retry` queued a run on finished work). Tests in `test_run_divergence.py` (approved and rejected via `apply_transition`, plus the operator's `PATCH` route and `divergences/recent`) failed first, pass now. Not driven against a live Hub run. Left alone: a task moved to a non-terminal status by someone else (e.g. operator completes it mid-run) still records; the next transition closes it. Filed 2026-10-08 (spec overhaul audit, reading code).

A run bound to a task that another actor approves still has a divergence recorded that nothing resolves
(`run_divergence.py:762-816`).

## F549 (C) -- a multi-line prompt through a .cmd shim that adds its own arguments is cut, yet marked delivered

**Status:** fixed 2026-10-17 (Tier 0): `resolve_executable` unwraps a JS shim (`"%dp0%
ode.exe" "%dp0%\script.js" %*`, and npm cmd-shim's `"%_prog%"` form, node beside the shim or on PATH) to `[node, script]`, so cmd.exe never sees the argv. `test_a_multiline_argument_survives_a_js_shim` spawned npm's real shim shape through real `node` and lost the second line before the fix; the installed `copilot.cmd` now resolves to `node npm-loader.js` and runs. No CLI on this machine took that path with a multi-line prompt (Copilot uses its platform exe, Claude's shim unwraps to an exe, Codex is an exe), so the exposure was npm JS-shim installs elsewhere. Earlier: open. Filed 2026-10-08 (spec overhaul audit, reading code).

`pty_runner.py:57-102` unwraps npm `.cmd` shims but deliberately leaves one that adds its own arguments
(`node script %*`) to cmd.exe (`test_pty_runner.py:111` asserts it). cmd.exe cuts a multi-line prompt at its first
newline, and the input is still marked delivered, against `agent-conversation-workspace`'s "a delivered turn reaches the
model intact". Related: F439, F349.

## F550 (C) -- an ordinary save strips corpus navigation and the map from a document's file

**Status:** superseded by `b1a4559` (2026-10-09, documents stored as `spec.json`, rendered on open). Ledger closed 2026-10-12 night, by reading: a save now writes only the payload and the hub block (`spec_documents.serialize`, `spec_service.rerender_phase`), and corpus navigation and the map are added at read time by `render_page` (`spec_service.py:~1440`), so there is nothing in the file for a save to strip. Not driven. Was: open. Filed 2026-10-08 (spec overhaul audit, reading code).

`spec_service.py:256` and `:1340` re-render without the corpus navigation and map that `rerender_corpus` adds, so a
document saved after placement loses them until the next corpus re-render.

## F552 (C) -- operator- and agent-facing text that describes things that no longer exist

**Status:** fixed 2026-10-09 (Tier 0, night iteration 3). Seven sentences corrected, each with a test that failed first at its seam: the board hint now says no document declares a hand-made task's dependencies (and no longer that it cannot have one; the picker is F571); the doctor hint is `agentweave --port N` and a test parses it with the real parser; the Logs chips lose `transport`/`watchdog` (a `hub_` event now falls under `other`); the briefing drops "where those are shared with the project"; `send_message` documents the cutover successor (it keeps the binding, under a new conversation id, so the finding's "new thread" is stated as that); slice guidance says "built" in the briefing and both MCP docstrings; the `agent_actions.py` comment now says binding, not recency (a comment, so no test). Not driven in a browser: the hint and chips are covered by rendered vitest tests only. Filed 2026-10-08 (spec overhaul audit, reading code). Each is a sentence to correct:
- the dependency board's hint says a hand-made task "can never have a dependency", false since F36
  (`DependencyBoardView.tsx:37`, `tasks.py:957`);
- `diagnostics.py:269` tells the operator to run `agentweave --port N hub-start`; there is no `hub-start`
  (`cli.py:1524-1590`);
- the Logs view still offers `watchdog` and `transport` categories (`LogsView.tsx:24`);
- the agent briefing describes a peer-checkpoint sharing restriction that no longer exists (`api/v1/agents.py:2386`;
  migration 0111);
- `send_message`'s description omits that a checkpoint cutover starts a new thread (`mcp_server.py:288-295`);
- the slice guidance says the next slice is drafted once a slice is approved; drafting waits until it is built;
- a comment at `api/v1/agent_actions.py:81-83` says an omitted `conversation_id` means the most recent open one; it
  resolves by binding.

## F554 (C) -- the project header draws the rules two requirements say it must not, and the tests cannot see it

**Status:** fixed 2026-10-10 (night iteration 16, decision `overhaul-header-rules`): the rule stays; change document `spec/changes/the-project-header-and-tabs-keep-a-faint-rule` (`spdoc-5f2f8771807d`) was approved and folded into `hub-workspace-shell` on the trial Hub, replacing both requirements under their keys with the faint `--border-region` rule and retiring ac18 and ac37. `hubVisualLanguage.test.ts` now reads `index.css` for both selectors (mutations to `--border` and to a tab background each fail it). Was: open. Filed 2026-10-08 (spec overhaul audit, reading code).

`index.css:812` and `:831` draw a `--border-region` rule under `.project-header` and `.project-tabs` (b92d7de), against
`hub-workspace-shell`'s `the-project-header-is-not-a-box` and `the-project-view-switcher-is-separated-by-its-plane-alone`.
The tests asserting "no rule" scan only TSX. Operator question in DECISIONS.md (`overhaul-header-rules`).

## F555 (C) -- the app-server path writes a run's closing status row outside `_record_observation`, untested

**Status:** fixed 2026-10-10 (Tier 0, night iteration 3): the closing row in `_execute_rpc_run` now goes through `_record_observation`; `test_an_app_server_status_line_that_meets_a_lock_is_retried_then_dropped` failed before (the lock reached the catch-all, `Unhandled error in app-server run`). Drive limit: app-server is Codex, whose plan is cancelled, so the seam is driven with the fake runtime only. Was: open. Filed 2026-10-08 (spec overhaul audit, reading code).

`agent_trigger.py:4201` writes the terminal status row directly; the process path goes through `_record_observation`
(locked-database retry, F359) and is the only one tested (`test_a_turn_says_how_it_ended.py:729,776`).

## F556 (C) -- "creator" names two different agents, so an operator-created loop never reports an outstanding message

**Status:** fixed 2026-10-13 (Tier 0, night window, decision `F556-outstanding-message-direction` (a)): `_pending_loop_request` now names mail addressed TO the job's agent from anyone else, still queued or delivered into a turn that has not ended; it no longer reads `loop.created_by_run_id`. The mail tests in `test_scheduler.py` failed before (an operator loop with mail to its agent reported nothing). Driven on the trial Hub: `scripts/drive/t_f556_operator_loop_outstanding_mail.py` (operator-created loop, operator mail held queued by a blocked agent checkout, drained loop fired: the event names the mail; a loop with no mail names nothing). Not done: the `agent-loops` ac41/ac42 and requirement wording ("from the loop's agent to its creator") still describes the old direction -- a capability is changed only through a change document and fold, so it is left for the day window. Was: open. Filed 2026-10-08 (spec overhaul audit, reading code). Night 2026-10-10: not built; applying the decision `overhaul-loop-creator` literally leaves the check matching only an agent's mail to itself.

When a loop's queue empties, the outstanding-request check treats the creator as the agent whose run created the loop
(`scheduler.py:487-493`); everywhere else the creator is the agent the job names (`api/v1/tasks.py:683-692`). A loop
the operator created has no creating run, so it never reports an outstanding message. Operator question in
DECISIONS.md (`overhaul-loop-creator`).

**Re-verified 2026-10-15** (full sweep, G6: Jobs & loops, scratch Hub `:8036`): fix holds for `/messages` (`pending_request: {"kind":"message","to":"alpha",…}`). An operator turn queued from the composer is not counted: filed as F624.

## F558 (C) -- evidence retention is a stored policy nothing applies

**Status:** fixed 2026-10-10 (Tier 0, night iteration 7, decision `overhaul-evidence-retention`): removed `PUT /spec/evidence-retention`, `RetentionSetting`, `retention_is_valid` and `EVIDENCE_RETENTION_POLICIES`; the `projects.evidence_retention` column stays, commented unused, because dropping it is a migration. `test_evidence_retention_is_retired` failed before (route answered 200). The two old drive scripts lose their retention legs. Was: open. Filed 2026-10-08 (interactive, reading code for R2/F379).

`projects.evidence_retention` (`db/models.py:124`, default `never`) is written only by `PUT
/project/spec/evidence-retention` (`api/v1/spec.py:1468-1486`) and read by nothing: no sweeper deletes an artifact under
`on_acceptance`, `daily`, `monthly` or `manual`, and `mark_artifact_removed` has no production caller (its own DEAD note,
`requirement_evidence.py`). The 2026-10-08 overhaul already dropped the retention clauses from `requirement-traceability`
as unbuilt. A setting with a writer and no effect: build the cleanup, or remove the column and the route. Kept off the
Settings page by operator decision (2026-10-08) rather than surfacing a choice that does nothing.

## F559 (C) -- the project-page settings change shipped seven query reads that show a failure as a value

**Status:** fixed 2026-10-08 (Tier 0). Found by CI (`test_surface_ceilings.py`, run 37828650862: unhandled sites 104 >
ceiling 97, 7 unclassified), not by the change's own checks: R2/F379 changed no backend file, so its build ran vitest
and the drive but not the Hub suite, and the ratchet lives there.

`CollaborationSummary` and `AgentPostureChips` (`e38f017`) bound no `error` on seven queries. A failed agent list read
"0 of 8 agents" and hid every hop-held agent; a failed budget read "No limit"; failed settings removed the block without
a word; a failed launch check or queue removed the "can't run"/"held" flags, so the card said nothing was wrong. Each
read now says it failed (alert, flagged value or flag chip); five vitest cases failed before the fix. Lesson for UI-only
changes: `hub/tests/test_surface_ceilings.py` gates `hub/ui/src`, so run it before pushing a component that queries.

## F561 (C) -- the project's `spec/journey.json` was discovered as a specification document

**Status:** fixed 2026-10-09 (Tier 0), in the project-steps build (`a-project-orders-its-own-spec-steps`, t4). Found by driving: d1011 check 6 opened the spec page and the app auto-selected `journey.json` as the first document ("no specification document at spec/journey.json", the phase bar empty); no Hub test or review had listed the tree with the file present.

`spec_documents.discover` skipped only `spec/index.json`, and `validate_spec_path` refused only that path, so the file t3 writes was listed in the spec tree and a document could have been created over it. Both now refuse `spec/journey.json` (`spec_manifest.JOURNEY_PATH`, which `spec_journey.JOURNEY_FILE` uses); `test_the_journey_file_is_not_a_spec_document` failed before the fix. The same drive also showed that d1011's own turn handling was model-dependent (a Haiku turn sometimes asks the advance question the drive stops on, sometimes runs past the step, sometimes ends at requirements); check 4 now asserts the agent's recorded advance and spends up to three turns.

## F562 (C) -- the approval-warnings change's `drive-first` criterion names a shape its own rule cannot detect

**Status:** fixed 2026-10-17: the criterion (now `approve-lists-what-is-missing-and-can-approve-anyway-drive-first` in `spec/capabilities/spec-document-authority`, the change being archived) was restated on the trial Hub through the capability's merge route as an operator edit: the first task waits on another, or no later task waits on it, are the gap; a later task waiting on the first and a single task are not, as `test_approval_gaps.py` tests. The missing check (a criterion contradicting a requirement in the same document) stays unbuilt. Earlier: open 2026-10-09. Found by building (approval-warnings t2, night iteration 16): the test written from the criterion failed against the structural rule the same change chose.

`spec/changes/approve-lists-what-is-missing-and-can-approve-anyway` (spdoc-9a9d313a4894) criterion `drive-first` says a change whose tasks are "build then drive (drive depends on build)" has `no_acceptance_drive`. FR-2 and decision D3 (night-1009-7) define the gap structurally: the first task depends on another, or is not a direct or transitive dependency of every other task. "build then drive" with drive depending on build satisfies that rule (build depends on nothing and drive waits on it): it is "drive then build" with the keys swapped, and D3 rejected reading names. `hub/tests/test_approval_gaps.py` tests the shapes FR-2 names instead (first task waits on another; a later task does not wait on the first). The criterion's text should be amended on :8010 to one of those shapes; the spec-flow had no check that would catch a criterion contradicting a requirement in the same document.

## F563 (B) -- a flow reviewer whose verdict the evidence gate refuses waits on ask_user until it times out

**Status:** fixed 2026-10-12 (Tier 0, night iteration 9). The cause was the briefing: `review_turn.verdict_evidence_sentence` told an ungranted reviewer to `ask_user` the operator when `approved` was refused, which is the wait the drive measured. It now says to end the turn, naming the waiting evidence, and not to wait on a question; a turn that ends while the gate refuses is already surfaced to the operator with the gate's sentence and re-staffs nobody (`run_divergence`, `F374-fix`, driven live 2026-09-26). `test_an_ungranted_reviewer_is_told_the_approval_can_be_refused_and_what_then` fails without the change (both channels, loop briefing and turn context) and passes with it. **Not driven:** no real Haiku reviewer turn on a flow was run, so that a model follows the new sentence by ending its turn is unverified; the surfacing it relies on is F374's. Found by driving (tester-amends d1013 run 2, artefacts `testbed/drive1013-tester-amends/093412`).

A Haiku test turn in a flow (tess, reviewing task `usage`) tried `update_task` to give its verdict and got 409 (the builder's evidence was still `awaiting`; tess has no `can_accept_evidence`). It then called `ask_user` and polled `GET /questions/{id}` for about five minutes until the turn ended; the task stayed `under_review` with no verdict, and the flow had nothing else to do. Hub log lines 165-183 of that run. The review briefing names the evidence gate (`review_turn.verdict_evidence_sentence`) but a reviewer that cannot decide the evidence has no way to end its turn usefully besides a question nobody in a flow is watching. Not caused by tester-amends; the drive avoids it by accepting the evidence as the operator. Worth deciding: should a flow review that cannot pass the gate set `revision_needed`/leave a note and end, rather than ask?

**Re-verified 2026-10-15** (full sweep, G3: Flows & review, scratch Hub `:8033`): fix holds live. The tester's first turn on t-char (`run-a105d649138b`) ended with *"approval cannot be recorded … evidence `ev-f1b8907929a6` … is awaiting the operator's decision"* instead of waiting on `ask_user`.

## F564 (C) -- deleting a task deletes its divergence records, which the model says are never deleted

**Status:** fixed 2026-10-10 (Tier 0 in intent, but it carries migration `0125`: `run_divergences.task_id` was NOT NULL, so clearing it needed the column nullable). Found by reading code (overhaul decision `overhaul-task-delete-divergence`, operator 2026-10-09). `deletion.py` now CLEARs the pointer; the task-delete test seeds a divergence and asserts it survives with `task_id` None (failed before). `0125` recreates the table (batch), keeping rows, indexes and both CHECK constraints (migration test: upgrade, insert NULL, CHECK still enforced, downgrade drops the orphaned rows only). Head assertions bumped to 0125. **Left, not done:** the UI type `RunDivergence.task_id: string` in `hub/ui/src/api/tasks.ts` is now wrong (`string | null`) but `useDivergences` has no consumer, and a src-only edit needs a bundle refresh, so I did not touch the UI; no live-Hub drive and the migration was not run on a copy of a real database.

`hub/hub/deletion.py:63` cascades `("run_divergences", "task_id", DELETE)`, while `RunDivergence`'s own docstring (`hub/hub/db/models.py:878-890`) says nothing is deleted, so "how often does this agent drop its work?" can still be asked. Runs survive a task delete with the pointer cleared. **Decided:** keep divergence rows on task delete with `task_id` cleared, as runs are; the deletion guard test's column list changes with it.

## F565 (C) -- the Hub's half of the single-segment project-name rule is untested

**Status:** fixed 2026-10-10 (Tier 0, tests only: all three cases were already refused, so no code changed). `test_create_project_refuses_a_name_that_is_not_one_new_directory` (`hub/tests/test_operator_projects_api.py`) posts a `..` final segment, a missing parent and a nested `a/b` under a missing parent; each answers 4xx and the parent's tree is identical afterwards. A `dir/../x` path is not refused: it normalises to one new directory beside `dir`, the same as any absolute path, so it is not in the test. No live-Hub drive (checked through the real app over ASGI). Found by reading code (overhaul decision `overhaul-create-name-check`, operator 2026-10-09); the overhaul's "UI-only" was imprecise.

The Create project dialog refuses a name that is empty, holds a path separator or is a traversal segment (`local-project-workspace` FR-43, `projectNameProblem`). `POST /projects/create` (operator credential only) takes the joined path, and `ProjectLifecycleService.create_new` (`hub/hub/project_lifecycle.py:144-157`) already refuses a relative path or an existing target, canonicalises an existing parent and creates exactly one directory with a non-recursive `mkdir`, so a nested or traversing name cannot create more than one level. Nothing tests that from the route. **Decided (as enforce on the Hub):** pin it with route tests (a `..` final segment, a missing parent, a nested `a/b`), each refused with the parent left unchanged; change code only if one of them is not refused.

## F566 (C) -- the rule that a refusal fits every surface that records it was dropped with no test

**Status:** fixed 2026-10-10 (Tier 0, test only). Found by reading the overhaul (decision `overhaul-refusal-length`, operator 2026-10-09). `hub/tests/test_a_refusal_fits_every_surface_that_records_it.py` builds the refusal at a 64-character task id and 32-character agent name and checks the operator PATCH, agent PATCH and dispatch 403 details (each <= 500 and ending in the remedy, ids whole), and both `_safe_error_summary` recorders plus `fit_error_summary` (remedy whole, uncut). Passed on first run, so no failing-first step and no code change; shown able to fail by cutting `scheduler._safe_error_summary` to 300 characters (test failed, reverted). **Noted, not changed:** on the job-run surface the secret redactor turns a 32+ alphanumeric task id or agent name into `<redacted>` (deliberate); the remedy survives. No live-Hub drive (ASGI only).

`task-lifecycle-governance` dropped "the refusal SHALL keep its remedy whole wherever it is recorded, so it SHALL fit the shortest surface that records it at the longest task identifier and agent name the Hub accepts" (from `a-refusal-names-a-remedy-that-works`, 2026-09-16; frozen text at `openspec/specs/task-lifecycle-governance/spec.md:366-367`) because no test named it. **Decided:** restore it, with a test that builds the review-reassignment refusal at the maximum task id (64) and agent name (32) and checks every surface that records it (each stored column or event payload and its length limit) holds the remedy whole.

## F567 (C) -- a failed link of a shared dependency directory into an agent's checkout is only logged

**Status:** fixed 2026-10-10 (Tier 0). Found by reading the overhaul (decision `overhaul-symlink-failure`, operator 2026-10-09; `workspace-isolation` limits line). `worktrees._symlink_shared_dependencies` now returns each failure with its OS error; the trigger asks `shared_dependency_link_failures(repo_root, workspace)`, which reads the disk (an existing checkout is never re-linked, so a failure from an earlier turn or before a restart still shows, and a directory since installed does not). The agent is told in the turn's prompt, and the run records a `warning` diagnostic coded `workspace.dependency_link_failed` (reason and remedy; facts `failed`) first in its timeline on all three execution paths (stream, Codex RPC, Copilot). `test_a_failed_dependency_link_is_shown.py` failed before (3 tests: helper, Claude stream run, Codex run). ASGI only, no live-Hub drive; Copilot path shares the RPC executor but has no test of its own. The `workspace-isolation` `limits` entry is now stale; it is Hub-owned, so not edited here.

Expensive shared dependency directories (`node_modules`, a venv) are linked into an agent's worktree rather than rebuilt (`workspace-isolation` FR-6). When the link fails the Hub logs it and goes on, so the agent works in a checkout without its dependencies and its builds and tests fail as if by its own fault. **Decided:** show it to the operator on the run and the agent, with the reason and the remedy.

## F568 (C) -- two context routes have no caller

**Status:** fixed 2026-10-10 (Tier 0). Found by reading code (overhaul decision `overhaul-unused-context-routes`, operator 2026-10-09). Both routes removed from `agents.py`; `record_context_usage` kept. `test_retired_context_routes.py` (route table and HTTP) failed before. The tests that used the POST to seed readings now call `record_context_usage` through `hub/tests/_usage_ingest.py` (still validating via `ContextUsageCreate`); the charter-lookup tests and the HTTP-only rolling-upgrade test were deleted; `docs/reference/hub-api.md` rows removed; `CLIENTLESS_ROUTE_CEILING` 22 -> 21. **Left, not decided:** `ContextUsageCreate` is now used only by tests; `HttpTransport.post_context_usage` in the CLI posts to the retired route (no caller, one test); `scripts/drive/` sweeps d1002 and t_sweep_row3/row4 still call the routes; capability `agent-context-usage` still names `POST /agents/{name}/context-usage` (needs a fold on the trial Hub, not a file edit). No browser/live-Hub drive: checked through the real app over ASGI only.

`GET /agents/context?charter=` (`hub/hub/api/v1/agents.py:3145`, superseded by `get_agent_context`, which its own hint names) and `POST /agents/{name}/context-usage` (`:3390`; the Hub records usage itself at `api/v1/agent_trigger.py:2958` and `:3903`) have no in-repo callers. **Decided:** retire both routes and their tests; `record_context_usage` stays.

## F569 (C) -- `checkpoint_access.participants()` is called only from tests

**Status:** fixed 2026-10-10 (Tier 0). Found by reading code (overhaul decision `overhaul-participants`, operator 2026-10-09). `participants()` deleted from `checkpoint_access.py` (with the `Run`/`Task`/`Any` imports it alone used); its two tests replaced by `test_participants_is_retired`, which failed before. Checked by grep: no other caller in `src/`, `hub/`, `tests/`, `scripts/`. No live-Hub drive: a pure deletion, nothing routed through it.

`hub/hub/checkpoint_access.py:242` derives which agents touched a conversation's work; nothing in the product calls it since the peer-checkpoint restriction it served was removed (migration 0111). **Decided:** delete it and its tests.

## F570 (C) -- a loop's history does not record its creation or what was added to its queue

**Status:** fixed 2026-10-10 (commits 9c51904, ba1027e; drive `scripts/drive/d1018_loop_history.py` 6/6 on a scratch Hub, real Haiku turn). Found by the spec overhaul (decision `overhaul-loop-history`, operator 2026-10-09).

A loop's own history records edits, control changes, stops, archiving, adoption and stalls, but not its creation (who made it, when) nor queue additions (who added which task). **Decided:** record both; ordinary firings stay in the job's run history only. Tier 1 (a short change: what each entry carries, where it shows).

## F571 (C) -- a hand-made task's dependencies can be declared only through a REST route

**Status:** fixed 2026-10-10 (Tier 1, night iterations 24-27; `d1019_task_depends_on.py` 6/6). `depends_on` on `create_task` (REST, agent route, MCP) and a Depends on section with picker in the task drawer. Found by the spec overhaul (decision `overhaul-dependency-ui`, operator 2026-10-09; the hint half is F552).

Since F36 a hand-made task can carry dependencies, but only `POST` on the task-dependency route sets them: no control in the app and no MCP tool field. **Decided:** a "depends on" picker in the task drawer, and a `depends_on` field on `create_task` (both agent renderings). Tier 1.

## F572 (C) -- the conversation has no collapsing thinking section and no way to hide diagnostics

**Status:** fixed 2026-10-10 (night iterations 38-41; d1022 3/3 on the committed tree, scratch :8108). Found by the spec overhaul (decision `overhaul-thinking-ui`, operator 2026-10-09); successor `spec/changes/live-thinking-stays-open-and-diagnostics-can-be-hidden` (`spdoc-a56fbfe278d0`) approved on :8010 2026-10-10 night iteration 38, built. Only a runner that streams reasoning shows the section (F578).

Specified earlier and never built (the specs now say so): a live thinking section that is open while the agent reasons and collapses when its answer arrives, and a control that hides diagnostic lines in the conversation. **Decided:** build both, as one small UI change in `AgentTimeline` (not the deleted `SharedStreamRenderer`). Tier 1.

## F573 (C) -- a roadmap cannot leave a question for a later slice: every open question blocks proposing it

**Status:** fixed 2026-10-17 (Tier 1, `a-roadmaps-open-question-can-wait-for-its-slice`, `spdoc-1e3378cb827a`): an open question on a roadmap may name its `slice`; it then raises no gap on the roadmap, and the slice's change document gets a `roadmap_question_for_slice` gap until it restates the question among its own open questions. The blocking half had already gone: unresolved questions became gaps, not refusals. Earlier: open 2026-10-09. Found while authoring `spec/changes/the-knowledge-vault-and-its-manager-roadmap/` (trial Hub `spdoc-7c75066d6403`), interactive.

A roadmap's slices are specified later, one at a time, in their own change documents (`spec_payload.py` `_check_kind_shape`). So a question that only that slice's spec can answer is a normal thing for a roadmap to carry. One example is "is the map rendered into every turn?", which belongs to the vault slice. `spec_completeness.py:264-272` blocks proposing any document with an unresolved question, roadmaps included. The author then has two bad choices: answer early, as a guess, or hide the question in a slice's `intent` prose, where nothing tracks it. That second choice is the workaround used here.

**Fix shape (not decided):** let an open question name the slice it belongs to (`slice: <key>`). On a roadmap, only questions with no slice block proposing it. The question should then show up when that slice's change document is written. Tier 1.

**2026-10-12, build window:** the images-and-pdfs question hidden in that slice's `intent` was answered by measurement when the slice was authored (`spdoc-99b7eb144fcd`, design D2): a Claude/Haiku worker given only the Read tool read a PDF and a PNG exactly. Nothing carried it there but the playbook naming F573: the workaround held this once because a human-written queue item repeated it. The finding itself (the roadmap's open questions cannot name their slice) stays open.

## F574 (C) -- a document written whole through the content route always warns "steps skipped" on approval

**Status:** fixed 2026-10-15 (Tier 0, the plan's second option). The warning now names the one call that records where a document written whole really stands: `POST /project/documents/journey?path=<path> {"step": "<last step>"}` (the phase bar's step control). Judging the skipped steps by content instead was not taken: `spec-document-authority` defines `steps_skipped` as the journey steps after the recorded step, so that is a Tier 1 change to a current requirement, not a fix. `test_the_journey_steps_a_document_never_reached_are_a_gap_naming_them` asserts the remedy and failed before. Driven on a scratch Hub: a document written in one PUT, proposed, warned with the call named. Opened 2026-10-09. Found while approving `spdoc-a78776d50704` (`the-hubs-background-jobs-are-configured-on-a-manager-page`), interactive.

The operator wrote that change document in one PUT. It had every section filled: requirements, acceptance criteria with how-to-check, tasks, design and delivery. Approval still answered 409 `approval_warnings` with `steps_skipped`: "the document is at step 'intake' ... goes on to requirements, acceptance, approach, tasks, delivery, which it never reached". The step-skipped warning judges the document by its recorded step, not by what it contains. So every document authored outside a stepwise conversation gets the warning, including `scripts/drive/author_change.py` documents and imported ones. A warning that fires on every complete document trains the operator to click "approve anyway". Approved anyway here.

**Fix shape (not decided):** compute the warning from the content each skipped step produces (requirements present, criteria with `how_to_check`, tasks), or advance the step on a content write that fills the later steps. Tier 0 or 1.

**Re-verified 2026-10-15** (full sweep, G4: Spec documents; also listed re-verified open by G3): still bites. A document written in one PUT warned `steps_skipped` on its first propose (`olive-chimera`, `olive-kraken`). One `POST /documents/journey {"step":"delivery"}` clears it (`saffron-selkie`, `russet-minotaur` proposed with `warnings: []`). By spec, not a defect: `steps_skipped` measures only the recorded step, so an operator jump `intake -> delivery` passes (`spec-document-authority`).

## F575 (C) -- the Claude runner's model catalog does not offer Sonnet 5.5

**Status:** fixed 2026-10-10 with F507 (same change, see its entry; the verified id, window and alias behaviour are recorded there). Opened 2026-10-09. Noticed in sessions 0186 and 0187 while choosing a model for the manager's title job; filed at the operator's request.

The Claude provider in `hub/hub/model_catalog.py:234-267` offers Opus 5.5, Sonnet 5, Haiku 4.5, Fable 5.1, Opus 5 and Fable 5. It does not offer `claude-sonnet-5-5`. Copilot's list in the same file has `claude-sonnet-5.5` (line 218). So a Claude runner, a Manager job or a composer turn cannot select the current Sonnet. The only way to reach it is the `sonnet` alias, and only if the CLI has moved that alias to Sonnet 5.5, which is unverified. This catalog's rule is that each id and window is live-verified (docstring, lines 10-18), so the fix first checks `claude --help` and a real `modelUsage.contextWindow`.

**Fix shape:**
- Verify the id and its window on this machine's CLI.
- Add a `ModelDescriptor`, and decide whether the `sonnet` alias and `default=True` move to it.
- Re-run `scripts/check_model_catalog.py`.

Tier 0.

## F576 (C) -- `test_the_slice_adds_no_migration` fails on any branch that carries a migration

**Status:** fixed e7d2763 (night iteration 15, 2026-10-12): both tests removed, with the `subprocess`/`Path` imports only they used. Reproduced first in a throwaway worktree with a dummy migration committed: both failed. Was: open 2026-10-10. Found running the Hub task tests on `autonomous/2026-10-09-daily` (iteration 26); failed identically with the iteration's changes stashed.

`hub/tests/test_spec_task_files.py:94-102` asserts `git diff --name-only master -- hub/hub/migrations/versions` is empty. That pins one slice's "no migration" promise to the whole branch's distance from `master`, so it went red the moment `6789c14` (F564, migration `0125_run_divergence_task_nullable.py`) landed on the cycle branch, and it stays red on this branch until `master` takes it. Any later migration on a branch breaks it the same way. The test cannot tell what it claims (this slice added none) from what it measures (the branch has none).

**Fix shape (not decided):** compare against the slice's own commit range or the migration head the slice was built on, or drop the test now the slice has shipped. Tier 0.

A sibling with the same body fails the same way: `hub/tests/test_spec_undeclared_files_warning.py:130` `test_the_change_adds_no_migration` (night iteration 31; both fail with that iteration's changes stashed). Fix them together. Both skip where `master` is not resolvable, which is presumably why CI stays green on them (not verified).

## F577 (C) -- the task drawer's prerequisite picker read a failed task list as "no other tasks"

**Status:** fixed 2026-10-10 (night iteration 29). Found by CI: run 38019656990 on `80d45bd`, `hub-test`, `test_surface_ceilings.py` (3 tests) named `TaskDetailDrawer.tsx` `useTasks #1` as an unclassified call site that ignores its error.

The "Depends on" picker added for F571 (`97ef44f`) called `useTasks()` binding only `data`. When the read failed, the picker offered nothing but "Choose a task…", which looks like a project with no other tasks. The ratchet caught it before any operator did. Fix: the drawer binds `error` and shows the Hub's sentence under the picker (`task-dependency-picker-error-<task>`). Test: `taskDependsOn.test.tsx`, "says the task list could not be read", failed before the fix and passes after. The same run's fourth failure, `test_copilot_context_split.py::test_context_for_a_claude_run_is_unchanged`, was the context snapshot not updated for `create_task`'s new `depends_on` parameter (`94e0ff7`); the snapshot was regenerated, and its diff is that one line. Tier 0.

## F578 (C) -- a Claude conversation never shows thinking: the CLI sends thinking blocks with empty text

**Status:** fixed 2026-10-18 (Tier 0): every Claude run passes `--thinking-display summarized` in place of the `showThinkingSummaries` settings file, which brought text back on Haiku 4.5 only. Re-measured on CC 2.1.301: Haiku 5.5 0 -> 199 characters, Haiku 4.5 858 with the flag alone (research 2026-10-10 §1 measured it on 2.1.291). `test_every_claude_run_asks_for_summarized_thinking` failed first; argv goldens updated. Driven: a live Haiku 5.5 turn on scratch `:8076` recorded a `thinking` row of 173 characters. Earlier: fixed 2026-10-17 (Tier 0, operator vis-D10): a thinking block with no text, or a `redacted_thinking` block, is recorded as a `thinking` row with `payload.hidden` and no content, and the conversation shows a muted "Reasoned" line (a row among a block's calls; "Reasoning…" with a breathing icon while it is the live turn's latest event). Driven with a live Haiku 5.5 turn (`scripts/drive/d1017_hidden_reasoning.py`, 2 PASS). Sonnet 5.5 sends no block at all, so its turns still show nothing: there is nothing to record. Earlier: partly fixed 2026-10-17 (Tier 0): every Claude run now gets `--settings <hub/hub/data/claude_run_settings.json>` with `showThinkingSummaries: true`, a file because a JSON argument's quotes do not survive a `.cmd` shim (F549). Measured on CLI 2.1.301: Haiku 4.5 sent 0 characters of thinking without it and 336 with it, and a live Haiku 4.5 turn on scratch :8129 recorded the first `thinking` row any Claude run has produced. Still open: Haiku 5.5 sends a signed but empty thinking block even with the setting, and Sonnet 5.5 sends none, so 5.x runs show no reasoning. The other fix shape (a work row saying the agent reasoned, without its text) is undecided. Earlier: open 2026-10-10. Found while authoring the F572 successor (night iteration 38).

`claude 2.1.291 -p --model claude-haiku-4-5 --output-format stream-json --verbose` with `MAX_THINKING_TOKENS=4096` sends `{"type": "thinking", "thinking": "", "signature": "..."}`: the block is there, its text is not. `runner_parsing.py:282-285` drops a thinking block whose text is empty, so no Claude run records a `thinking` event; the trial Hub's `agent_outputs` and 98 scratch drive databases under `testbed/` hold none. The live thinking section F572's change builds can therefore only show for a runner that streams its reasoning (Copilot's thought chunks). Not measured: whether another model, a CLI setting, or a newer CLI returns the text.

**Fix shape (not decided):** find out whether the CLI can be asked for thinking text; if not, consider a work row that says the agent reasoned (empty block present) without its text. Tier 1.

## F579 (C) -- a roadmap cannot show which of its slices are closed

**Status:** fixed 2026-10-17 (Tier 1, `a-roadmap-shows-which-of-its-slices-are-done`, `spdoc-eaf6fb419bb7`): a roadmap's page shows each slice's state and document, derived on read from the change documents whose roadmap link names it, or "not started". `d1017_roadmap_slice_states.py` 3 FAILED before, ALL PASS after. Earlier: open 2026-10-11. Found closing the `contradictions` slice (build window iteration 3).

The build playbook's close step ends "mark the slice done in the roadmap document through the Hub" (`.claude/loops/build-window.md:101`). There is nothing to mark: a slice carries `key`, `title`, `intent`, `done`, `builds_after` and no state (`hub/hub/spec_payload.py`, `_check_kind_shape`), and `spec_render._slices` (`hub/hub/spec_render.py:444-460`) renders only those fields. A slice is closed when the change document naming it (`roadmap.slice`) is archived, but nothing joins the two for a reader: the roadmap page reads the same after `sources-that-disagree-are-pointed-out` was folded and archived (200) as before. Each loop composes by listing `spec/changes/` and `spec/changes/archive/` and matching slice keys by hand (`build-window.md:27-30`).

**Fix shape (not decided):** derive each slice's state on read from the change document that names it (none / exploring / proposed / approved / archived), as `roadmap_states` already does in the other direction (`hub/hub/spec_service.py:1197`), and show it beside the slice on the roadmap page. Tier 1.

## F580 (C) -- `approve_anyway` sent as a query parameter is silently ignored

**Status:** fixed fc7e37d (2026-10-11, Tier 0): the phase route answers 400 naming any query parameter other than `path`/`to` (`set_phase`, `hub/hub/api/v1/spec.py`), and the `approval_warnings` message says `approve_anyway: true` goes in the request body (`spec_lifecycle.py`). Tests `test_approve_anyway_sent_as_a_query_parameter_is_refused_not_ignored` and `test_the_approval_warnings_message_says_where_approve_anyway_goes`, each mutation-checked; drive `scripts/drive/d1011_f580_phase_query.py` 4/4 on a fresh Hub. Originally open 2026-10-11. Measured 2026-10-10 (vault loop iteration 5, `2026-10-10-vault-log.md`); not re-measured today (the 2026-10-11 approval of `spdoc-e4f531e0b926` sent the body field and got 200). Unfiled until now.

`POST /projects/{id}/project/documents/phase?path=...&to=approved&approve_anyway=true` answers the same 409 `approval_warnings` as without it: `path` and `to` are query parameters (`hub/hub/api/v1/spec.py`, `set_phase`) but `approve_anyway` is a field of the `PhaseRequest` body (`spec.py:411-428`), and FastAPI drops an unknown query parameter without a word. The 409's message ("fix them, or approve anyway", `hub/hub/spec_lifecycle.py:409-412`) does not name the field or where it goes, so a caller following the message repeats the same request. The body `{"approve_anyway": true}` approves (200).

**Fix shape (not decided):** name the body field in the `approval_warnings` message, or refuse unknown query parameters on the phase route with a 400 naming them. Tier 0.

## F581 (C) -- a worker's model answer is not kept, so a wrong judgement cannot be read after the fact

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 93ea888): the Manager panel shows each firing's `answer` under a closed "What the model answered"; with a test that failed before. Earlier status: fixed 2026-10-15 (Tier 1, change `spec/changes/a-workers-answer-is-kept`). Every manager firing that spawned a model keeps the model's answer as `answer` on its `manager_job_fired` event, and so in `GET /manager/activity`. That covers distillation's read, distil and check, vault reports, spec-vault-check and titles. The answer is the raw text, else the parsed answer as JSON, cut at 8,000 characters with a marker; a firing whose spawn returned nothing keeps null. No migration (the event's data is JSON). Showing it in the Manager panel is in the UI batch. Acceptance drive `scripts/drive/d1015_f581_answer_kept.py` committed failing first (ff44cbc), ALL PASS after. Tests: `test_a_workers_answer_is_kept.py`. Opened 2026-10-11. Measured 2026-10-11 (build window iteration 7, d1025 run `testbed/drive1025-specs-vault/095027/`).

The spec-vault-check firing recorded `outcome empty`, `0 conflicts kept, 0 dropped` and 1,373 output tokens, but neither `worker_invocations` (`hub/hub/worker.py`, `_record`; columns are usage and outcome only) nor the `manager_job_fired` event keeps what the model answered, so *why* it found nothing was unreadable. It took re-sending the same prompt by hand (`claude -p`) to see Haiku's reasoning (it read "300 euros or less need no approval" as silent beyond 300). The same holds for every vault job (distillation, contradictions, reports): an operator who doubts a judgement has only the count.

**Fix shape (not decided):** keep the parsed answer (or its first N characters) on the invocation row or the firing event, private-vault redaction rules applying. Likely Tier 1 (a column means a migration, so Tier 2 if stored on the row).

**Re-verified 2026-10-15** (full sweep, G5: Manager jobs, scratch Hub `:8035`): still open. Activity keeps only a count line; the report answers and the spec-check messages keep the model's reasoning, but the distillation and transcription answers do not. An example of why it matters (model judgement, not filed): `spec-vault-check` (Haiku) judged "pay within 30 days" to contradict "due within 45 days" at propose and again on Check now.

## F582 (C) -- an unknown API route answers 405 Method Not Allowed, not 404, to anything but GET

**Status:** fixed 2026-10-12 (night window iteration 2, Tier 0): `hub/hub/main.py` registers a 405 handler beside `serve_spa` that answers 404 `{"detail": "Not Found"}` unless another route recognises the path (a real route's wrong-method 405 and `Allow` header are kept); test `hub/tests/test_an_unknown_route_answers_404_for_every_method.py` failed 5 of 7 before the fix; driven on a throwaway Hub (port 8582): POST/PUT/DELETE to unknown `/api/...` and `/zzz` answer 404, `POST /health` and `DELETE` on a POST-only route stay 405. Measured 2026-10-12 (build window iteration 5, d1026 run `testbed/drive1026-images-pdfs/093112/`).

`POST /api/v1/projects/{id}/vault/files` on a Hub that has no such route answered `405 {"detail": "Method Not Allowed"}`. The dashboard's SPA fallback `@app.get("/{full_path:path}")` (`hub/hub/main.py:589`) partially matches every path, so Starlette reports the method as wrong rather than the path as unknown (measured: the only route matching that scope is `/{full_path:path}` with `Match.PARTIAL`). A caller of a route that does not exist yet, such as an agent or script talking to a Hub older than it, is told to change the method. The images-and-pdfs spec predicted 404 for exactly this case.

**Fix shape (not decided):** let the fallback answer 404 for any non-GET method and for `/api/` paths, or register it for every method and answer 404 itself outside the bundle. Tier 0.

## F583 (C) -- `test_each_piece_is_one_spawn_and_one_firing` fails on this machine whatever the tree

**Status:** fixed 2026-10-12 (build window iteration 9): `_firings()` now breaks the timestamp tie by `event_logs.rowid`; the test passed 3 of 3 runs after. Measured 2026-10-12 (build window iteration 6): `py -3.11 -m pytest hub/tests/test_vault_distillation.py -k each_piece_is_one_spawn` failed 3 of 3 runs with this window's changes and 3 of 3 more with them stashed (one earlier run passed), asserting `['failed', 'written', 'written'] == ['written', 'failed', 'written']`. It also failed inside a 1,000-test chunk.

`_firings()` (`hub/tests/test_vault_distillation.py:89`) orders by `EventLog.timestamp, EventLog.id`; three firings written within one tick of the Windows clock tie on timestamp and fall back to the random id. Unverified: the timestamp resolution was not read, only the symptom (order differs run to run) measured.

**Fix shape (not decided):** order by a column that is monotone for rows written in sequence, or compare the outcomes as a multiset with the position of the failed piece taken from its call index. Tier 0.

## F584 (C) -- `spec_reconcile.latest` picks a random reconcile result when two are recorded within one clock tick

**Status:** fixed 2026-10-12 (build window iteration 9). Found by the task gate: `hub-tests` on `task-edc80dd92218` failed `test_the_fold_state_carries_the_latest_result_and_fold_is_not_refused` (`'first' == 'second'`; failed 2 of 2 alone, passed in an xdist chunk). `latest` ordered by `created_at desc, id desc`, and the id is random, so a tie on the 15.625 ms wall clock returned the older result. It now breaks the tie by `spec_document_events.rowid` as `_approval_outcome` already does; the test passes 3 of 3 runs. It was a product defect, not only a test one.

## F585 (C) -- `tests/test_skill_sync.py` fails on a clean tree: two skill mirrors are stale

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 3). Re-ran `py -3.11 scripts/sync_skills.py` (additive; 18 skills into `.agents/skills` and `~/.codex/skills`); `tests/test_skill_sync.py` 2 failed -> 2 passed. The CI half is already covered: the test skips a destination that is not a directory (`tests/test_skill_sync.py:68`) and the script's docstring records both trees as machine-local, so no code change was needed. The mirrors are untracked, so the fix leaves no diff beyond this line. Original report: open 2026-10-12. Measured (night window iteration 4, clean tree at 8b2bf1d): `py -3.11 -m pytest tests/test_skill_sync.py` fails 2 cases, the Kimi+OpenCode project mirror and the Codex user-level mirror, both stale against `.claude/skills/`: `autonomous-session/scripts/run-iteration.ps1` and `night-briefing/SKILL.md`.

The mirrors live under the user's home, so the autonomous window did not rewrite them. A CI runner has no such home, so this is likely local-only; unverified. **Fix shape (not decided):** re-run the sync for those two mirrors, and have the test skip or point at a temp home when the mirror is outside the repository. Tier 0.

## F586 (B) -- re-distilling a source re-opens a contradiction the operator resolved, and presumes the fact they overruled

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 9). `vault.dated_facts(..., current_only=True)` leaves out facts a decision or corrected report superseded; `distillation._check` and `vault_spec_check` both use it. `test_a_redistil_does_not_compare_with_a_fact_the_operator_overruled` (`test_vault_contradictions.py`) failed before and passes after. Driven on scratch Hub `:8112` with real Haiku: 300 vs 500 contradiction opened, resolved with 300 standing, January re-distilled (`distil_requested` fired, no `facts_written` check, contradiction stays `resolved`, no disputed fact). Originally measured 2026-10-13 (build window, driving sweep 1 `vault`, scratch Hub :8110, `testbed/sweep1013-vault/`, `scripts/drive/s1013_vault_sweep.py`).

Repro: a transcript dated 2026-01-10 (300-euro refund limit) and a PDF dated 2026-03-01 (500 euros) are distilled; contradiction `ctr-7f0006294a4d` pairs the two facts, the 500 one presumed. The operator resolves it with the 300 fact standing (`POST /vault/contradictions/{id}/resolve`, 200); the map then shows the 500 fact `superseded_by` the decision and nothing disputed. Pressing Distil on the January transcript (`POST /vault/sources/{id}/distil`, 202) re-writes its facts and its `facts_written` check records **a new open contradiction `ctr-99cdc445147e` between the new 300 fact and the superseded 500 fact**, the 500 fact `presumed: true` again. The map now marks the overruled fact disputed and presumed, which is what an agent reading `vault_map` is told.

Seam: distillation x contradictions. `distillation._check` compares the new facts with every fact `vault.dated_facts` returns (`hub/hub/distillation.py:415-418`, `compared_set`), superseded ones included, while `vault_spec_check.prepare` already leaves superseded facts out (`hub/hub/vault_spec_check.py:255-264`).

**Fix shape:** leave superseded facts out of the distillation check's compared set, as spec-vault-check does. Tier 0.

**Re-verified 2026-10-15** (full sweep, G5: Knowledge vault, scratch Hub `:8035`): fix holds. A re-distil from the Vault tab's Distil button left `ctr-2f72c1449976` `resolved`, opened no new contradiction and marked no fact disputed; the overruled fact carries `superseded_by: src-38c622894f41` (the decision source).

## F587 (B) -- re-distilling a source replaces every fact with a new id, orphaning the decision and the requirements that cite them

**Status:** fixed 2026-10-15 (Tier 1, change `spec/changes/a-redistilled-fact-keeps-its-id`, with F617). A re-distil keeps, under its id and unchanged, every earlier fact drawn again from the same lines: the same source and span, and the quote equal ignoring case, runs of whitespace and trailing punctuation. The first drive run on HEAD showed Haiku quoting the same line with and without its period, so an exact quote would churn. Each earlier fact is kept at most once, and only new facts are checked for contradictions. Acceptance drive `scripts/drive/d1015_f587_redistil_keeps_ids.py` committed failing first (efa77b4: both facts re-minted on HEAD), ALL PASS after (Haiku, scratch `:8054`). Tests: `test_a_redistilled_fact_keeps_its_id.py`; three `test_vault_contradictions` re-distils now quote a different line, so they still exercise replacement and the check. Opened 2026-10-13. Measured in the same sweep as F586.

After the same re-distil, the 300 fact that stood in the resolved contradiction (`fct-1b7ccb9bf93f`) is deleted (`distillation.distil` deletes `earlier - stored`, `hub/hub/distillation.py:312-322`) and an identical claim is written under a new id. Consequences, each measured: the resolved contradiction's `stands` side now reads `claim: None, source: None`, and the Vault tab renders it as "A private fact, held on another machine" (`VaultPage.tsx:748`) though nothing is private; the approved change `spec/changes/refund-limits/spec.json` that cited the fact gets a `missing` warning ("It cites fct-1b7c..., which is not in the vault on this machine"); its R2 conflict names a deleted image fact the same way. Only open contradictions citing the old facts are cleaned up (`delete_open_contradictions_citing`), so resolved ones keep pointing at nothing.

Seam: distillation x contradiction resolution x spec citations. Not Tier 0: whether a re-distil keeps the id of a fact whose claim is unchanged, or refuses/asks when a fact stands in a decision or is cited by a requirement, is a design choice (operator's or a Tier 1 change).

**Re-verified 2026-10-15** (full sweep, G5: Knowledge vault): still open. A Distil from the Vault tab on the February source replaced its facts with `fct-9f16f124d469` and `fct-9ea52a3b15d1`; the standing fact `fct-dd4574520c84` of resolved `ctr-2f72c1449976` is gone (`GET /vault/entries/fct-dd4574520c84` -> 404). The operator-visible labels this produces ("A private fact, held on another machine"; "not in the vault on this machine") are filed as F617.

## F588 (C) -- a spec-vault-check conflict against a fact the operator has since overruled stays on the spec page

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 11). `document_warnings` now skips a conflict whose fact is superseded or no longer in the vault (`vault.dated_facts(current_only=True)`). `test_a_conflict_against_a_fact_since_overruled_or_gone_is_not_shown` (real routes: contradiction resolved through `/resolve`, then `GET /vault/warnings`) failed before and passes after; stashing the fix makes it fail again.

The proposed document's R1 (300 euros) got a spec-vault-check conflict naming the 500 fact. After the operator resolved the contradiction against the 500 fact (superseded by the decision), `GET /vault/warnings` still answers that conflict, its message even saying the 500 fact "supersedes the January version". After F587's re-distil the R2 conflict names a fact that no longer exists ("which is not in the vault on this machine"). Pressing check again (`POST /vault/warnings/check`) cures it, because `prepare` leaves superseded facts out; nothing tells the operator to.

Seam: contradiction resolution x spec-vault-check. `document_warnings` drops a conflict only when its requirement was reworded (`hub/hub/vault_spec_check.py:159-163`), not when its fact is superseded or gone, against D5's "a warning always points at something real".

**Fix shape:** in `document_warnings`, skip a conflict whose fact is superseded or missing. Tier 0.

**Re-verified 2026-10-15** (full sweep, G5: Knowledge vault, scratch Hub `:8035`): fix holds. After the resolve, both FR-1 warnings (the disputed one, and the conflict against the overruled 25 kg) left the warnings list; FR-2's unrelated conflict stayed.

## F589 (B) -- deleting a runner a manager job uses is allowed, and the job then silently does nothing

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 7, with F595). `delete_runner` now also refuses a runner any `manager_jobs` row names, 409 naming the jobs. `hub/tests/test_a_runner_a_setting_names_cannot_be_deleted.py` failed 2 of 3 before (204) and passes after. Driven on scratch Hub `:8111`: DELETE answered 409 "bound to background job(s): conversation-titles; the project's checkpoint runner setting", a settings save still worked, and after the settings were cleared the DELETE answered 204.

`DELETE /runners/{id}` refuses a runner an agent is bound to (409 "Runner is bound to agent(s): scout"), but answered 204 for a runner the enabled `vault-distillation` job used. `GET /manager/jobs` then still reports the job `enabled: true` with the deleted `runner_id`. A source uploaded next (201) got no facts and **no firing at all** in the activity log; only pressing Distil says why (409 "The vault distillation job has no runner"). The Manager page shows the dangling job's runner control as "The agent's own runner" (see F590).

Seam: runners x manager jobs. **Fix shape:** refuse the deletion with 409 naming the jobs, as for agents (or clear the job's runner and say so). Tier 0.

**Re-verified 2026-10-15** (full sweep, G1: Runners & models, scratch Hub `:8031`): fix holds. Delete names every holder (agent, both jobs, checkpoint setting); an archived holder does not block.

## F590 (C) -- the Manager page tells the operator a vault job without a runner uses "the agent's own runner"

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 12). `JobSpec.needs_runner` (False only for the titler) is listed by `GET /manager/jobs`; the page words a needs-runner job's empty choice "No runner (the job does nothing)" with help "It does nothing until a runner is chosen.". `test_each_job_says_whether_it_can_run_without_a_runner` failed (KeyError) before; `managerSection.test.tsx` fails before on the option. Driven on scratch Hub `:8112` in Chromium against the rebuilt bundle: titles row keeps "The agent's own runner", vault-distillation row shows the new wording. A Hub that predates the field reads as the old wording.

Every job's runner control carries the conversation-titles wording: help "None uses each conversation's own agent's runner." and the empty option "The agent's own runner" (`hub/ui/src/components/environment/ManagerPanel.tsx:134,144`). For the three vault jobs that is false: their own descriptions say "Needs a runner", and with none they do nothing (`distillation.prepare` refuses "has no runner"). Seam: manager framework x the vault jobs it later hosted. Tier 0 (per-job wording, the empty option saying the job does nothing).

**Re-verified 2026-10-15** (full sweep, G5: Manager jobs, scratch Hub `:8035`): fix holds. The titles row reads "The agent's own runner"; the vault rows read "No runner (the job does nothing)" / "It does nothing until a runner is chosen."

## F591 (C) -- a file source whose transcription failed or has not run yet is shown as "Held on another machine"

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 13). A tracked file source with no text now reads "No text yet: the file has not been read, or reading it failed" (`withoutText` in `VaultPage.tsx`); a private entry still says "Held on <machine>". `vaultFiles.test.tsx` failed before (mutation-checked). Driven on scratch Hub `:8113`: an uploaded PNG with no runner shows the new wording in the Vault tab. The failure detail itself is still not operator language (not filed).

A tracked GIF whose reading failed (firing `failed`, "reading the image: 1 schema violation(s): Field required") is listed in the Vault tab as "Held on another machine", and a just-uploaded PDF reads the same until it is transcribed: the map answers `available: false, holder: null` and `VaultPage.tsx:224` renders any unavailable entry as held elsewhere. The file is in the repository. Seam: images-and-pdfs x text-sources' availability label. Tier 0 (say "not read yet" / "could not be read" when the entry is a file source on this machine). The failure detail itself ("Field required") is also not operator language; noted, not filed separately.

**Re-verified 2026-10-15** (full sweep, G5: Knowledge vault, scratch Hub `:8035`): fix holds ("No text yet: the file has not been read, or reading it failed"). The Distil button stays disabled in that state: filed as F616.

## F592 (C) -- deleting a project leaves its private vault behind in the Hub's own directory

**Status:** fixed 2026-10-15 (Tier 2, decision fix-D1, change `spec/changes/a-deleted-project-stays-deleted`, with F609). `DELETE /projects/{id}?remove_private=true` removes the private entries before any record (the whole `vaults/<id>` folder at the default location; only `sources`/`facts`/`contradictions`/`reports` at a chosen one), refuses 409 deleting nothing when another project shares the location or the removal fails, and never touches the project's directory; without the flag they are kept (the app's current bundle), and the dialog's checkbox, checked by default, is in the UI batch. Acceptance drive `scripts/drive/d1015_f592_deleted_project_stays_deleted.py` committed failing first (d1cb332: 4 of 9 on HEAD), ALL PASS after. Tests: `test_a_deleted_project_stays_deleted.py`. Opened 2026-10-13. Measured at the end of driving sweep 1 (`vault`).

`DELETE /projects/{id}` answered 204 and, as its docstring says, "never touches the filesystem" (`hub/hub/api/v1/projects.py:740`). That is right for the project's own directory, but the default private location is the Hub's (`~/.agentweave/hub/vaults/<project-id>/`), and the private note's full text (`sources/src-....md`) stayed there with nothing in the app pointing at it any more. Seam: project deletion x vault private location. Not Tier 0: whether deletion removes, keeps, or asks about private vault contents is the operator's call (private data either way).

**Re-verified 2026-10-15** (full sweep, G1: Projects x Knowledge vault): still bites, and worse. `DELETE /projects/proj-aba065a4865e` -> 204 left `~/.agentweave/hub/vaults/proj-aba065a4865e/sources/src-….md`; reopening the folder then resurrected the same project id with the private source readable again. That resurrection is filed separately as F609 (B).

## F593 (B) -- folding a verified change leaves its requirements "unserved" in the capability, while the archived change keeps counting as verified

**Status:** fixed 2026-10-16 (Tier 0, UI batch, e94b128): a served capability requirement reads "served by FR-n of <change path>" and its Evidence reads the serving change (the Hub adds `served_by.document_path`); with a test that failed before. Earlier status: fixed 2026-10-15 (Tier 1, change `spec/changes/a-folded-requirement-keeps-its-verification`). Option (a) of the fix shape, without copying evidence: a capability requirement with no evidence of its own takes its coverage from the same-digest requirement of a change merged into it (`spec_document_merges` + the semantic digest, which a verbatim fold keeps and a rewording changes), and its entry names it as `served_by`; the project rollup leaves archived documents out of its totals and of `unserved` (a document's own coverage still lists its history). Acceptance drive `scripts/drive/d1015_f593_fold_keeps_verification.py` committed failing first (858da57: 3 of 9 on HEAD), ALL PASS after. Tests: `test_a_folded_requirement_keeps_its_verification.py`. The app's showing of `served_by` is in the UI batch. The side symptom (a later commit broke the capability's `add`) is drift's job, not this. Opened 2026-10-13. Measured in driving sweep 2 (spec-flow), scratch Hub `:8110`, `scripts/drive/s1013_spec_flow_sweep.py`.

A change `indigo-kirin` (FR-1 `subtract`, FR-2 `help`) was built by a Haiku agent, both pieces of evidence were accepted, both tasks were landed (the commit is on `main`), and coverage read FR-1 and FR-2 `verified` / `integrated`. Folding it into `spec/capabilities/calculator/spec.json` answered 200 and archived the change. Straight afterwards, `GET /project/spec/coverage` listed five rows: the capability's `indigo-kirin-subtract` (FR-2) and `indigo-kirin-help` (FR-3) were `unserved` with `evidence_count` 0, although their digests are the ones the change's verified requirements carry (`3ecd5489…` and `a70d4279…`, recorded in the capability's `aw_identity.digests`). The archived change's FR-1 and FR-2 still appeared as `verified`, and they still counted in `totals`. So the project's coverage says that the shipped behaviour is unserved, and it counts as verified a document that is only history. `requirement_coverage` (`hub/hub/requirement_coverage.py:228`) does not filter on phase, and `spec_service.fold` (`hub/hub/spec_service.py:1010`) carries no evidence or links into the capability. No capability requirement in `spec-document-authority` says what verification a folded requirement keeps.

A related symptom from the same drive: the agent's commit changed `calc.py`'s CLI so that the capability's existing `add` requirement (`python calc.py A B`) no longer holds (it now prints "Unknown command: 2"). Nothing could notice, because the capability's requirements carry no verification at all.

Seam: fold x coverage. **Fix shape (operator's call):** one option is that a fold carries accepted evidence across to the capability requirement when the digest is unchanged, and coverage leaves archived documents out of its totals. The other is that capabilities are declared outside coverage and the page says so. This is a design question, not Tier 0.

**Re-verified 2026-10-15** (full sweep, G4: Corpus & folding, scratch Hub `:8034`): still bites, through the API and on screen. After folding `olive-chimera` (verified FR-1, evidence digest `bbf6c43c…`), the capability's FR-4 carries that digest in `aw_identity.digests` and reads `unserved`, evidence 0, while the archived change keeps counting `verified` in totals. After folding the flow-delivered `russet-minotaur` (both requirements verified, merged) through the **fold dialog**, the capability's coverage bar reads "7 no work linked", FR-7/FR-8 included.

## F594 (B) -- an answered question can be answered again; the second answer overwrites the first, and after delivery it spends a new turn

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 7). `answer_question` refuses an answered question with 409 and the claim guards `answered == False` too (`questions.py`); `hub/tests/test_an_answered_question_cannot_be_answered_again.py` failed 1 of 1 before (200, `red` overwrote `blue`) and passes after. Driven on a scratch Hub `:8111`: answer 1 200, answer 2 409, `blue` kept. Not re-driven with a live Haiku asker.

A Haiku agent called `ask_user` ("Pick a colour", red/blue). `PATCH /questions/{id}` with `blue` answered 200. A second `PATCH` 20 ms later with `red` **also answered 200**: it overwrote `answer`, cleared `answer_labels`, and restamped `answered_at`. The agent's `ask_user` returned `red`, and the agent replied `red`. After that run had completed, a third `PATCH` (`green, actually`) answered 200 again (`asker_waiting: false`). It queued `Question: Pick a colour / Answer: green, actually` as a new operator entry and **started a new run** (`run-f117e6b31547`), which replied `green`. The decline route refuses an answered question ("Declining it would discard a decision that was already made"). The answer route has no mirror refusal: the conditional `UPDATE` in `answer_question` (`hub/hub/api/v1/questions.py:476`) guards `declined == False` only, not `answered == False`. No UI surface offers to change an answer (grep of `hub/ui/src`: no edit or re-answer), so the reachable paths are a double submit, a second tab, or a stale page. Same shape as F430 (drift candidates).

Seam: operator answer x the asker's tool wait and late-answer delivery. **Fix shape:** add `Question.answered == False` to the claim, and answer 409 "already answered" when it claims nothing (mirroring decline, F227). Test: answer twice, expect 409, the first answer kept, and nothing queued. Tier 0.

## F595 (B) -- deleting the runner that project settings name leaves a dangling id; every later settings save is refused, and checkpoints say no runner is configured

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 7, with F589). `delete_runner` refuses with 409 naming every holder: open agents, manager jobs (the title runner is one) and the project's `checkpoint_runner_id`. Same test file and live drive as F589.

Created runner `Ck`, then `PUT /projects/{p}/settings` with `checkpoint_runner_id` = `Ck` and `conversation_title_mode: generate` + `conversation_title_runner_id` = `Ck` (200). `DELETE /runners/Ck` answered **204**. `GET settings` still names the deleted id for both. Then:
- `PUT settings {"hop_budget": 7}`, an unrelated change, answered **400** "Unknown runner 'runner-8b04…': no runner by that id belongs to this project". The merge validates the stale stored id (`projects.py:574-583`), so the project's settings cannot be saved at all until the operator first re-picks a runner. Nothing names that as the cause of the error.
- `POST /conversations/{c}/checkpoint` answered 409 "No checkpoint runner is configured for this project", while settings show one configured.

`delete_runner` (`hub/hub/api/v1/runners.py:231`) checks only `Agent.runner_id`. The title runner is a job's runner (`projects.py:453`), so that half is F589's root. The checkpoint runner is a `Project` column that F589's fix would not reach.

Seam: runners x project settings (checkpoint and title). **Fix shape:** have `delete_runner` refuse with 409, naming every holder (agents, jobs, the project's checkpoint runner), so one fix closes F589 and F595 together. The alternative is to clear the references and say so. Tier 0.

**Re-verified 2026-10-15** (full sweep, G1: Runners & models, scratch Hub `:8031`): fix holds; the settings save after the runner's deletion works.

## F596 (B) -- a job fired at an agent with no runner answers 500 and records the firing `failed`, but its message stays queued and runs as soon as a runner is bound

**Status:** fixed 2026-10-13 (Tier 0, build window iteration 8; option 1, DECISIONS `build-1013-2`). A terminal refusal about the environment (no runner, CLI missing) now sets `ScheduleResult.kept_for_repair`, so `no_turn_began` is false: the firing stays `in_progress` and the press answers 200 with `waiting_reason` (`jobs.py`, `scheduler.py`, `turn_scheduler.py`). `hub/tests/test_a_job_for_an_agent_with_no_runner_waits.py` failed before (500) and passes after. Driven on scratch Hub `:8111`: press 200 with "No runner is bound…", history `in_progress`, entry `queued`; after re-binding Haiku the job run and the agent run both `completed`.

Job `norunner` (agent `idle`, enabled, far-future cron). `PATCH /agents/idle {"runner_id": null}`, then `POST /jobs/{id}/run` answered **500** "No runner is bound to this agent. Bind one in the Hub UI before it can run.". The job's history shows the firing `failed` with that summary, and `run_count` became 1. But `GET /queue/idle` still holds the firing's entry as `queued`, and queue status reads `waiting_reason` "No runner is bound…". Re-binding the Haiku runner redrained the queue as designed (F96): `run-a2ba8a095904` delivered the entry and **completed**. The history still says `failed`. So the operator is shown a server error and a failed firing for work that then ran, and nothing in the job's record says it ran. `scheduler.py:4030-4037` treats `waiting_reason` + `terminal_failure` as "no turn began" and writes `failed`, but the entry it committed a few lines earlier is left `queued`. `jobs.py:1815` then maps that `failed` row to a 500.

Seam: job firing x the inbound queue's wait-for-runner redrain. **Fix shape:** pick one of two. Either the firing is a wait (`in_progress`/queued, answered 409 or 202 with the waiting reason, and resolved when the entry is delivered), or a terminal failure withdraws the entry it queued so nothing runs later. In either case "no runner" is not a 500. Tier 0 once the choice is made; the first option matches how an operator trigger to the same agent already behaves (`status: queued`, `waiting_reason`).

**Re-verified 2026-10-15** (full sweep, G6: Jobs & loops, scratch Hub `:8036`): fix holds (runnerless firing: 200 with `waiting_reason`, history `in_progress`). The same pattern with the budget refusal is filed as F608; a waiting firing whose entry is withdrawn stays `in_progress` forever (F625).

## F597 (C) -- the "May agents schedule work?" question stays open after the operator enables `allow_agent_jobs` in settings

**Status:** fixed 2026-10-15 (Tier 0, decision fix-D10). A settings save that turns `allow_agent_jobs` on answers each open `capability-refusal:allow_agent_jobs` record with its first option ("Enabled it — go ahead", saying it was turned on in Environment › Settings), through the operator's own answer path (`questions.apply_answer`, extracted from the answer route), so the refused agent is told and woken as an answer would. It is never fatal to the save. `test_refused_capability.test_enabling_the_setting_answers_the_open_question_and_tells_the_agent` failed before. Opened 2026-10-13. Measured in driving sweep 4 (jobs-loops).

A Haiku agent's `create_loop` was refused 403 with `allow_agent_jobs` off, and the Hub opened question `q-cbfeb678bbde` ("Enabled it — go ahead" / "Leave it off", subject `capability-refusal:allow_agent_jobs`). The operator then turned the setting on via `PUT /settings`, and the agent's next `create_loop` succeeded. The question was still `answered: false`, `asker_waiting: true`, listed on the Questions page. Answering it now would send the agent a decision about a setting already changed; "Leave it off" would contradict the live setting. Nothing in the settings write (`projects.py`) consults `refused_capability.py`'s record. Seam: settings x refused-capability question. Not Tier 0: whether a settings change resolves the record (and whether that tells the agent) is a design call in `a-refused-capability-reaches-the-operator`'s territory.

**Re-verified 2026-10-15** (full sweep, G6: Capability plane, scratch Hub `:8036`): still reproduces. After `PUT /settings {"allow_agent_jobs": true}`, `q-a1a891baa04f` stayed `answered: false, asker_waiting: true`.

## F598 (A) -- with `checkpoint_auto_continue` off, automatic checkpoints in a two-agent project feed each other through the project-wide redrain into a self-sustaining chain of autonomous turns

**Status:** fixed 2026-10-15 (Tier 2, `spec/changes/a-held-successor-waits-for-continue`, migration 0127). A cutover with auto-continue off marks the successor's entry `awaits_continue`; `select_turn` leaves a held conversation out whole unless the operator wrote into it, so no redrain, settings save, job or peer message starts it; Continue writes the release before scheduling (kept for the run's end if the agent is busy); the scheduler and queue status answer "waiting for Continue: conversation …". The backfill held already-queued successors in auto-continue-off projects. Acceptance drive `scripts/drive/d1015_f598_held_successor.py` failed on HEAD (the settings save started run 2; Continue then answered "queue is empty") and passes after (runs 1→1 across the save, Continue starts the successor; scratch Hub `:8031`, Haiku). Tests: `hub/tests/test_a_held_successor_waits_for_continue.py` (10) and the 0127 migration test. Measured in the 2026-10-15 full sweep (G6: Checkpoints, with Inbound queue; scratch Hub `:8036`, profile `sweep1015g6`, project `proj-c8a70822d8e2`).

Settings were `checkpoint_mode: automatic`, threshold 5,000 tokens, Haiku as the checkpoint runner, and `checkpoint_auto_continue: false`. The Settings page tells the operator: *"Off means a Continue button — never a message you have to invent."*

Each cutover queues the successor's `origin_type='checkpoint'` entry without scheduling it (`checkpoint_cutover.py:194-203`; `schedule_agent` runs only `if auto_continue:` at :235). But every run's end calls `redrain_queued_agents(project_id)`, which reschedules every queued agent in the project (`agent_trigger.py:2913`, `:3383`, `:4145`, `:4344`; `turn_scheduler.py:782`). Even the operator's `PUT /settings` does this (`projects.py:349`): the sweep's own `checkpoint_mode: off` write started `run-f99b5d0954c5`. With beta's per-minute job running, alpha's successors were drained by beta's run endings, and the reverse. Each successor turn crossed the threshold again, which made another checkpoint, another cutover and another entry.

The record: alpha ran 5 autonomous turns with no operator input (`run-5d4db5c59619` 10:48:09, `run-3292a5bb74bd` 10:49:11, `run-3997e264585b` 10:50:18, `run-a5b266c6c4f2` 10:51:03, `run-f99b5d0954c5` 10:52:40). Beta ran 8 more on top of its 3 job firings. There were 28 checkpoint worker calls ($0.52 that no total shows, F240). It stopped only when the operator set `checkpoint_mode: off`. In `inbound_queue_entries` the checkpoint-origin entries were delivered 0.3-60 s after arrival, for example `10:48:21.368707` -> delivered `10:48:21.655818` in `run-fcf3788a9834`, just as alpha's run ended at `10:48:21.503552`. `conversations` shows alpha's line as 7 conversations, all titled "Continued: Read calc/__init__.py …". The group planned about 12 turns and ran 22; 16 came from this runaway and the job firings.

Not covered: F131 knew that "two cutovers on auto-continue-off" queue without scheduling, but not that the project-wide redrain then delivers them. F604 (the stale summary) is what each of these successor turns then did.

Seam: Checkpoints (cutover) x Inbound queue (project-wide redrain). Tier guess: 0 or 1 (no fix shape in the report).

## F599 (B) -- a runner's `flags` silently override its model and the permission posture; a `--dangerously-skip-permissions` runner wrote outside the workspace while the roster said `workspace`

**Status:** fixed 2026-10-15 (Tier 2). One rule, `runner_flag_rules.posture_flags_problem`, names per CLI the flags that set the model or the permission posture (Claude: --model, --permission-mode, --dangerously-skip-permissions, allowed/disallowed tools, --permission-prompt-tool, --add-dir, --settings; Codex: model, sandbox, approval and bypass flags and their `-c` keys; Copilot: --model, its widening flags being stripped by posture at run time). Create and PATCH refuse them with 400 naming the owner; a runner already storing one is not launchable (`probe_agent`), so the trigger keeps its input and nothing spawns. Stored rows are not rewritten. The F281 rewording of `outside_workspace_writes = []` is not part of this change. Change `spec/changes/a-runner-s-flags-cannot-override-the-posture` (Tier 2, F599 with F600). Acceptance drive `scripts/drive/d1015_f599_runner_flags.py` committed failing (seven override runners accepted, the flagged runner bound) and passes 17/17 after; `hub/tests/test_a_runner_s_flags_cannot_override_the_posture.py` (21). Live on a stored row from the HEAD run: binding `runner-91ffcb09ba98` (`--dangerously-skip-permissions`) to a new agent is refused with the reason, and the launchability route names it. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: Runners & models, Permissions & sandbox; scratch Hub `:8031`, profile `sweep1015g1`, project `proj-f0200ae7d008`).

`POST /runners` accepts `flags: ["--model","claude-opus-5-5"]`, `["--model=opus"]` or `["--dangerously-skip-permissions"]` on a plain `claude` runner whose `model` is `haiku`. `_build_claude_command` appends `extra_flags` after its own `--model` and `--permission-mode`, so the flags win. The command built for such a runner (`hub/hub/runner_commands.py:194-298`, called directly):

```
['claude', ..., '--model', 'claude-haiku-4-5-20251001', ..., '--permission-mode', 'manual',
 '--model', 'claude-opus-5-5', '--dangerously-skip-permissions', '-p', 'hi']
```

Driven: agent `beta` on runner `flagged` (`["--dangerously-skip-permissions"]`) ran `run-627f16bdf402`. Told to run `python -c "open(r'C:/Users/huida/Documents/g1-outside-proof.txt','w')..."`, it did, and the file appeared outside the project. The control, agent `alpha` on `haiku-full` with the same prompt (`run-17534890245f`), was refused: *"denied ... outside my workspace"*. `GET /agents` reports both as `permission_mode_at_rest: workspace`. The Runners page and every runner select show "haiku" and no flags. `provider_flags_problem` refuses `--model` in flags **only** on provider runners (`runner_provider.py:73-81`).

Both runs recorded `outside_workspace_writes = '[]'`, the value that reads "observed, nothing left the workspace". beta's write went through an interpreter inside a shell command, which F281 closed as out of the record's scope by design; F281's remaining no-spec step (reword `models.py:1214` to "no file tool wrote outside this run's boundary") is what would stop `[]` reading as clean here.

Extends **F469** (open; the operator answered "show flags read-only", 2026-09-30, not yet built): the flags were invisible, and are now shown to defeat the posture and the model the UI displays. F600 is how the operator gets such a runner without choosing it.

Seam: Runners & models x Permissions & sandbox. Tier guess: 2 (permission posture; no fix shape in the report beyond F469's read-only display).

## F600 (B) -- the Add-agent dialog binds whichever runner with the same cli and model the database returns first, a flagged one included

**Status:** fixed 2026-10-15 (Tier 2). Add-agent's find-or-create matches only a runner with no flags and no provider config, oldest first (F177's order), and creates one when none exists; a second add reuses it. Change `spec/changes/a-runner-s-flags-cannot-override-the-posture` (Tier 2, F599 with F600). Acceptance drive `scripts/drive/d1015_f599_runner_flags.py` committed failing (seven override runners accepted, the flagged runner bound) and passes 17/17 after; `hub/tests/test_a_runner_s_flags_cannot_override_the_posture.py` (21). Live on a stored row from the HEAD run: binding `runner-91ffcb09ba98` (`--dangerously-skip-permissions`) to a new agent is refused with the reason, and the launchability route names it. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: Agents, Runners & models; scratch Hub `:8031`).

The dialog offers only provider + model ("the Hub provisions the runner for you"). Its find-or-create (`hub/hub/api/v1/agents.py:734-741`) selects by `cli` + `model` with no `order_by`, and ignores `flags` and `provider_config`. `POST /agents {"name":"beta","provider":"claude","model":"haiku"}` was bound to `runner-a9034f11968d` "flagged" (`--dangerously-skip-permissions`), although two earlier plain `haiku-alias` runners had the same cli and model:

```
ro: {'name':'beta','rn':'flagged','model':'haiku','flags':'["--dangerously-skip-permissions"]'}
```

beta's turn then wrote outside the workspace (F599). The operator picks "Claude Code, Haiku" and silently gets a permission-bypassing runner, or an Opus one (F599), or a provider runner. Not covered: F177 fixed the runner list's unstable order; F268 the indistinguishable labels.

Seam: Agents (Add-agent) x Runners & models. Tier guess: 0 (no fix shape in the report).

## F601 (B) -- Workspace-only allows writes to PowerShell provider drives (`HKCU:`, `Env:`, `Function:`) written without a separator, and says they are "inside your workspace"

**Status:** fixed 2026-10-15 (Tier 2). In the PowerShell reading a word on a built-in non-FileSystem provider drive (Alias, Cert, Env, Function, HKCU, HKLM, Variable, WSMan, any case, with or without a separator, also as a colon-joined option value) is refused as outside, quoting the word (`_PS_PROVIDER_DRIVE_RE`, `_drive_word`, `_judge_word`). The built-in set rather than the plan's 'any `<name>:`', which would refuse `git show HEAD:README.md`; a `New-PSDrive` root is judged as a path already. Change `spec/changes/the-workspace-judge-reads-paths-not-patterns` (Tier 2, with F601/F661 together). Wire acceptance drive `scripts/drive/d1015_judge_wire.py` (the real tool server over stdio, Workspace posture) was committed failing (9 rows wrong) before the build and passes 16/16 after; `hub/tests/test_the_workspace_judge_reads_paths_not_patterns.py` 39 tests, 24 failing on the unfixed judge; the existing judge suites (938) unchanged. Copilot's own call path is not driven at home (work PC). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G7: Permissions & sandbox; scratch Hub `:8037`, profile `sweep1015g7`, project `proj-c62f8f7873d4`).

`_judge_drive_word` (`hub/hub/mcp_server.py:2275`) handles only drive letters and `Temp:`. Every other PowerShell provider drive, written without a separator after its colon, falls through as a relative file name: the call is allowed and the operator is told it is inside the workspace. With a separator (`HKCU:\Software`) the same command is refused. `_decide` called directly (the function the run's tool server calls), with `AW_WORKSPACE_DIR` set to the project and the PowerShell tool:

```
Remove-Item HKCU:Software\AwG7Probe                      -> True inside your workspace
New-ItemProperty -Path HKCU:Environment -Name X -Value y -> True inside your workspace   (persistent user env var)
Remove-Item Env:PATH                                     -> True inside your workspace
Remove-Item Function:prompt                              -> True inside your workspace
Get-Content HKCU:\Software                               -> False '\\Software' is outside your workspace
Copy-Item x Temp:foo                                     -> False 'Temp:foo' is outside your workspace
```

Not run against a live turn: probed at the function, not the MCP wire; no registry key was touched. Not covered: no registry or provider-drive entry in the ledger; F402 D1 covers drive letters and `Temp:` only.

Seam: Permissions & sandbox (the judge's drive-word path). Tier guess: 2 (sandbox boundary; no fix shape in the report).

## F602 (B) -- an `aw_live_` key in an agent's reply text is stored and broadcast unredacted, while the same value in tool input and output is redacted

**Status:** fixed 2026-10-15 (Tier 2, `spec/changes/a-secret-in-reply-text-is-redacted`). `runner_events.redact_text_secrets` redacts the named patterns only (`aw_live_`, `aw_run_`, `sk-` tokens, and the value of an api_key/secret_key/access_token/auth_token/password field, also as a payload key), not the tool events' high-entropy catch-all, so commit SHAs, paths and prose are kept. It is the floor in `record_agent_output` for every kind and caller, the operator's `POST .../output` included. `run_secrets.scrub_stream` matches the same patterns over the run's joined prose, so a token split across events is redacted in the later one; every registered (live) run carries a 160-character tail, cleared by `forget`, and a run never registered or already forgotten leaves no state. Acceptance drive `scripts/drive/d1015_f602_text_redaction.py` (a Haiku agent quotes a committed notes file) committed failing (all three fake values verbatim in the text row, the route's two verbatim) and passes 9/9 after; `hub/tests/test_a_secret_in_reply_text_is_redacted.py` (21) and the F488 stream tests (13) pass. Drive note: a model declines to echo credential-shaped text on request, so the drive quotes a file. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G7: Logs, events & SSE; scratch Hub `:8037`).

A real turn (`run-7f3f8fe482d2`) was asked to write a fake `aw_live_…` key in its reply and to echo an `sk-…` value through the shell. The tool rows carry `<redacted>`; the text row, and its payload `text`, carry the key verbatim:

```
{'kind': 'text', 'c': 'aw_live_Fake0123456789abcdefghijABCDEFGH', 'p': '{"version": 1, "text": "aw_live_Fake0123456789abcdefghijABCDEFGH"}'}
{'kind': 'tool_use', ... "echo \"<redacted> and path C:/Users/huida/Documents/aw-sweep-1015-g7/calc/__init__.py\"" ...}
{'kind': 'tool_result', ... "output": "<redacted> and path C:/Users/.../calc/__init__.py" ...}
```

The path survived, which is correct. `agent-stream-events` says: *"Before an event is stored or broadcast, the Hub SHALL redact known secret patterns…"*. Separately, the operator route `POST /agents/{name}/output` stores `sk-abc123` and `{"api_key": "hunter2"}` verbatim: it scrubs only the run's registered secrets (`output_recording.py:49`), not the patterns. Not covered: F484/F488 concern registered secrets split across Copilot event boundaries, not pattern redaction of text rows.

Seam: Logs, events & SSE (text-row recording x pattern redaction). Tier guess: 2 (secrets; no fix shape in the report).

## F603 (B) -- a reviewer reviews pre-fix code: work from a mail turn that claimed its task mid-turn sits on the agent's branch, and the task's checkout is cut fresh from main for the review

**Status:** fixed 2026-10-15 (Tier 1, `spec/changes/work-from-a-mid-turn-claim-reaches-the-task`). The trigger records an author turn's checkout HEAD at spawn; at finalize, a run that ran in an agent's own worktree and ended bound to a task that takes its own checkout has its turn's non-merge commits cherry-picked onto the task's branch (`worktrees.carry_turn_work_to_task`, the task checkout provisioned at the integration base with its approved prerequisites). Only the turn's own range, never the agent's earlier work (F58). A dirty task checkout, one held by another agent's running turn, or a conflict leaves both branches as they were and records a `task_work_not_carried` warning naming why. Acceptance drive `scripts/drive/d1015_f603_mid_turn_claim.py` committed failing (no task branch after a mid-turn claim) and passes 5/5 after (the task's branch holds the turn's FIX.txt); `hub/tests/test_mid_turn_task_work_is_carried.py` 5 tests. The two-agent mail flow of the sweep is not re-driven; one agent's untasked turn stands in for it. The duplicate on the agent's branch (the same change twice) is left: it merges cleanly. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Worktrees & integration, Flows & review; scratch Hub `:8033`, profile `sweep1015g3`, project `proj-14a9256af359`).

dev2 messaged dev1. That mail-triggered run (`run-5c239e9c24f3`) claimed task A mid-turn, worked in the **per-agent** worktree (`.agentweave/worktrees/dev1`, commit `7bca975` "Auto-snapshot: dev1's turn") and completed A. dev2 then asked `rev` to review. The reviewer's run (`run-9f7c919c968a`) was given A's **per-task** checkout `.agentweave/tasks/task-e219c28fc828`, created for that run from `master` (`200d5ee`), so without dev1's fix. rev, in its own words: *"The `word_count` function still uses `text.split(" ")` instead of the required `text.split()`"*. It wrote a REJECTED note and sent dev1 back, and dev1 redid the identical fix in the task checkout (`run-a23e7ce9d858`, `223fa49`). Cost: two wasted turns and a false rejection.

The duplicate fix stayed in `GET /worktrees/conflicts` for the rest of the drive, as `agentweave/dev1` against `agentweave/task/task-e219c28fc828` on `wordlib/counts.py`: a conflict between two copies of an approved task's work, after the task's worktree was removed. Related: F10 (fixed, reviewer could not see the work) and F519 (fixed, dependency briefing); neither covers a task claimed mid-turn. F607 is the same staleness seen from reconcile.

Seam: Worktrees & integration (per-agent vs per-task checkout) x Flows & review. Tier guess: 1 (no fix shape in the report).

## F604 (B) -- an automatic checkpoint summarises the turn as it stood at its first context reading, mid-turn, so every successor is told to redo work that finished

**Status:** fixed 2026-10-15 (Tier 0). Under `automatic`, `checkpoint_trigger.consider` now waits, outside its read transaction, until no run in the conversation is running (`_turn_ended`, polled every 2 s, bounded at 30 min, past which the reading is declined and a later one tries again), re-reads the conversation and project, then generates. `hub/tests/test_checkpoint_cutover.py`: `test_an_automatic_checkpoint_waits_for_the_turn_it_was_read_in_to_end` and `test_a_turn_that_never_ends_gets_no_checkpoint_from_its_reading` failed before (generation ran twice while the run was `running`; the stuck turn was spawned for). Driven with `scripts/drive/d1015_f598_held_successor.py` on a scratch Hub (Haiku): the checkpoint worker started +0.15 s after the turn ended (every checkpoint on the unfixed code started 2-4 s before it), and its body reads "Current state: Complete … Nothing is pending". Measured in the 2026-10-15 full sweep (G6: Checkpoints; scratch Hub `:8036`).

`consider_from_reading` fires on the turn's first `context_warning`. For `run-41d73f552632` that was 10:44:53; the run ended at 10:44:56. Checkpoint `ckpt-792cab6b03e7`, written at 10:45:06, says *"Current state: Checkpoint created at task start… File not yet read or analyzed."* and *"Next actions: Read calc/__init__.py…"*, while its own "Recorded observations" list the finished answer `out-be15c2fe2eb3`. Every successor then re-read the file and re-answered the two-sentence question (`run-5d4db5c59619`, `run-3292a5bb74bd`, `run-f99b5d0954c5`: "I'll start by reading the mean() function…"). The job alpha created afterwards (`nightly-tests`, in `conv-00d0cdeed668`) never appears in any later checkpoint objective, so the line of work forgot it. Not covered.

Seam: Checkpoints (summary snapshot taken mid-turn; cutover after the turn). Tier guess: 0 or 1 (no fix shape in the report).

## F605 (B) -- the checks gate charges a task with failures already on main; the reviewer is told to send correct work back, and the override has no control in the app

**Status:** fixed 2026-10-16 (Tier 0, UI batch, afad0be): a Land refused by failing checks alone offers "Land anyway" with a required reason (`override_checks_reason`); with a test that failed before. Earlier status: fixed 2026-10-15 (Tier 1, change `a-check-that-fails-on-main-too-is-not-the-tasks`, decision fix-D13). A failing check is re-run on the main tip and its result records `on_main` and `preexisting`; a refusal whose only failures are pre-existing says they fail on main too, drops the reviewer's send-back line and is an operator-only hold (flow, divergence and briefing say approval waits on the operator); a new failure beside one stays the author's, the old one labelled. `POST /tasks/{id}/land` takes `override_checks_reason` (the sweep's exit took four PATCHes). 4 new tests; the shared FAIL fixture now fails only where the task's work is. Acceptance drive `scripts/drive/d1015_f605_preexisting_checks.py`, committed failing (5 checks) before the build, ALL PASS after. The app's override control is left to the UI batch. Opened before: open 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Worktrees & integration, project checks; scratch Hub `:8033`).

`master` carried the `word_count` defect, because task A was approved but never merged (F622). Every check run on later work failed on `test_double_space` and `test_newline` (e.g. `chk-6ce5e2f71a26`, `main_sha 200d5ee`), though neither t-char nor t-slug touches `word_count`. The reviewer briefing did what it said: tester sent t-slug back, its notes *"the full test suite has pre-existing failures … These failures existed before this task's changes … Returning to author"*. `POST /tasks/{id}/land` answered 409 `gate_unsatisfied`, *"approving would land work that breaks the project"* (it would not), then *"If you are reviewing this task, fixing what the checks found is its author's work"*; nothing in it is addressed to the operator. The only exit took four PATCHes: under_review refused (author holder) "Land it"; `assignee: null`; `under_review`; `approved` with `override_checks_reason`. `grep override_checks_reason hub/ui/src` returns nothing.

Related: F512 (test-first tasks, a different cause).

Seam: Worktrees & integration (project checks gate) x Flows & review. **Fix shape (not decided):** compare a task's check result against main's own result at the same check, charging only new failures; and give the operator an override control. Tier 1.

## F606 (B) -- a reviewer turn can undo its own send-back and complete the author's task, after which the flow refuses to review it

**Status:** fixed 2026-10-15 (Tier 0). `task_transition_service._guard_run_holds_the_task`: a bound run that gave the task a verdict (`revision_needed`), or took it to `under_review` while another agent is its assignee, may not then move it to `in_progress` or `completed`; the refusal names the assignee. Read from the task's own history by run id, so the author's next run, and an operator-started run on someone else's task, are unaffected. `test_a_reviewer_cannot_take_back_its_own_send_back` replays the sweep's sequence and failed before (the move went through); control: the assignee takes the task back up. **Not driven live:** it needs a reviewer turn to misjudge on cue. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Tasks actor boundary, Flows & review; scratch Hub `:8033`).

tester was re-asked on `task-f80bdb75c239` (assignee `dev1`). In one turn (`run-5a2b76860b93`) it moved the task `under_review -> revision_needed` (wrongly: it judged the *other* task's FR-2), then `-> approved` (refused 409), then `revision_needed -> in_progress` (accepted), then `in_progress -> completed` (accepted). `task_transitions` records `actor_agent=tester` on all three accepted moves, so tester is the task's recorded completer. The next flow tick (`job_runs` 11:05) skipped: *"this task names 'tester' as its reviewer, and that agent is the one that completed this task. Naming a different reviewer, or reviewing it yourself, is the way forward"*. The checklist's "finishing *another agent's* task" boundary did not refuse it, and the record then makes the task unreviewable by its named tester. Related: F495 (fixed: revision returns the assignee to the author) covers the assignee, not the reviewer's own moves.

Seam: Tasks (actor boundary) x Flows & review. Tier guess: 0 (no fix shape in the report).

## F607 (B) -- a reconcile pass (and every untasked turn) reads the agent's own worktree, which is never brought up to main; it recorded three false "missing" gaps against shipped code

**Status:** fixed 2026-10-15 (Tier 1, `spec/changes/an-agent-checkout-catches-up-with-main`). Before an untasked turn in a writing agent's own worktree, `worktrees.catch_up_agent_worktree` brings it to the project's integration base (the same `task_workspace.integration_base` a task branch is cut from): fast-forward, or a merge when it has commits of its own; uncommitted changes or a conflict leave it exactly as it was (merge aborted, logged) and the turn still runs. Task and review checkouts and read-only agents are unaffected. Acceptance drive `scripts/drive/d1015_f607_worktree_catch_up.py` committed failing (the agent could not find a file committed after its worktree was cut) and passes 5/5 after; `hub/tests/test_an_agent_checkout_catches_up_with_main.py` 6 tests, all failing on HEAD. A reconcile turn goes through the same path, so its reading of main is covered; not re-driven through reconcile. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G4: Corpus & folding (reconcile), Worktrees & integration; scratch Hub `:8034`, profile `sweep1015g4`, project `proj-681ccc923e49`).

`c_to_k` was landed (`14d271e Integrate approved work edf73bbafe99` on `master`). `POST /project/documents/spec/changes/saffron-selkie/spec.json/reconcile {"agent":"alpha"}` (202) ran alpha in `.agentweave/worktrees/alpha`, branch `agentweave/alpha` at `065cb70`, which lacks it. alpha's `record_reconcile` stored "c_to_k function does not exist", "c_to_k validation does not exist", "tests/test_kelvin.py … does not exist", all `class: missing`, all false on main. Evidence: `git -C .agentweave/worktrees/alpha log --oneline -1` -> `065cb70 c1`; `grep -c "def c_to_k"` -> master 1, alpha worktree 0; the `spec_document_events` kind `reconcile` detail quoted above. The same staleness showed earlier: the exploring turn after the landing read `tempconv/__init__.py` without `c_to_k`. No capability requirement says an agent's own checkout follows the main branch or that a reconcile reads main (searched `spec/capabilities/*`: only task, review and check worktrees are specified). The reconcile record is the operator's evidence that a change matches its code, and here it says the opposite. F603 is the same staleness from the review side.

Seam: Corpus & folding (reconcile) x Worktrees & integration. Tier guess: 1 (design gap; no fix shape in the report).

**Seen again 2026-10-15** (F602's drive, scratch Hub `:8031`, `proj-f4b261050f5f`): a file committed to master after agent `alpha`'s worktree was cut was not there for its next turn. The agent searched with Read and Bash and answered "I cannot find BUILD-NOTES.txt in the worktree or in the git repository". A fresh project, whose worktree was cut after the commit, saw it. Same root as F607: an agent worktree is never brought forward from main.

## F608 (B) -- a job fired on a spent token budget answers 500 and records the firing `failed`, but its entry stays queued and runs once the budget is raised (F596's pattern, a different refusal)

**Status:** fixed 2026-10-15 (Tier 0). The scheduler's spent-budget refusal is now a hold (`terminal_failure=False`, as the allowance hold already was) and writes its reason on the held entries, so a job's press answers 200 with `waiting_reason: "token budget exhausted"` and the firing stays `in_progress` until the delivered run finishes it. `hub/tests/test_a_job_on_a_spent_budget_waits.py` failed before (500). Driven with `scripts/drive/d1015_s1_tier0.py` on a scratch Hub (Haiku), 10/10. The held firing completed once the budget was cleared. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G6: Jobs & loops x Accounting & allowance; scratch Hub `:8036`).

With `token_budget` set below usage, `POST /jobs/{id}/run` on job `spent` returned **HTTP 500 `{"detail": "token budget exhausted"}`**, and the history shows `failed` / "token budget exhausted". `GET /queue/beta/status` shows `waiting_count: 1, waiting_reason: "token budget exhausted"`. After the budget was cleared the entry was delivered in `run-40d8f19c2d4d` (completed), while the job history still says `failed`. F596's fix (`kept_for_repair`) covers "no runner" and "CLI missing", not the budget refusal.

Seam: Jobs & loops (firing outcome) x Accounting & allowance (budget hold). **Fix shape:** treat the budget refusal as `kept_for_repair` too, as F596 did: firing `in_progress`, answered 200 with `waiting_reason`. Tier 0.

## F609 (B) -- deleting a project and reopening its folder resurrects the same project id and its "permanently" deleted private vault content

**Status:** fixed 2026-10-15 (Tier 2, decision fix-D1, with F592). Migration 0128 adds `deleted_projects`; reopening a folder whose marker names an id this database deleted registers a new project under a new id and rewrites the marker, so the deleted private text is not served (a marker from another database is still adopted). The private entry's stub under `knowledge/` is a tracked project file and stays listed, text unavailable; its note then says the text is "held on <this machine>", the F617 mislabel. Same drive and tests as F592; `test_project_lifecycle` flipped. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: Projects x Knowledge vault; scratch Hub `:8031`, throwaway project `proj-aba065a4865e`).

`DELETE /projects/proj-aba065a4865e` -> 204. `~/.agentweave/hub/vaults/proj-aba065a4865e/sources/src-….md` remains (F592), and the folder keeps `.agentweave/project.json` and the `knowledge/` stub. `POST /projects/open` on the same folder returns the **same id** `proj-aba065a4865e`; `vault map` then lists the private source again, and `GET /vault/entries/src-d4f1f9528bd8` returns its full text. The delete dialog says it removes "every other record — permanently". This is new behaviour beyond F592 (which filed only the leftover files, C): the leftovers come back into the app, and the dialog's promise is false for private data.

Seam: Projects (delete, reopen by marker) x Knowledge vault (private location). Not Tier 0: as F592 says, whether deletion removes, keeps or asks about private vault contents is the operator's call. Tier guess: 2 (private data).

## F610 (B) -- the private vault location may be set inside another registered project or any git work tree, and saving it creates the directory

**Status:** fixed 2026-10-15 (Tier 0). Choosing a private location now refuses a folder inside another project this Hub registered (naming it) or inside any git work tree (an ancestor holding `.git`, folder or worktree file), and creates nothing: the folder is made by the first private entry written there. The work-tree and other-project rules are asked on choosing only, so the default location under the home folder is not refused on each write when a home folder is a repository. `test_settings_refuse_another_project_and_any_git_work_tree` failed before, and `test_settings_refuse_locations_in_the_project_and_bad_values` now asserts nothing is created. Driven on a scratch Hub: another project -> 400 naming it; `AgentWeave/x-f610` -> 400 naming the work tree; an outside folder -> 200 and no folder made. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G5: Knowledge vault; scratch Hub `:8035`, profile `sweep1015g5`, projects `proj-122981b843d9` and `proj-7283c4a8d706`).

The guard refuses a private location inside *this* project: `…\aw-sweep-1015-g5\secret is inside the project's directory … could be committed with the repository; choose a folder outside it.` It also refuses `..` tricks that resolve inside, and relative and `Z:relative` paths. But both of these answered `200`: `PUT /vault/settings {"private_location":"C:/Users/huida/Documents/aw-sweep-1015-g5b/vault"}` (inside another project this Hub has registered, a git repo) and `{"private_location":"C:/Users/huida/Documents/projects/AgentWeave/x"}`. **The save itself created both directories** (`ls -d …/AgentWeave/x` existed right after; removed by hand, empty). The stated reason, "could be committed with the repository", applies equally to any git work tree. Not covered.

Seam: Knowledge vault (private-location guard) x Projects. **Fix shape:** refuse a location inside any registered project's directory or any git work tree (`git rev-parse` from it); create the directory only when the first private entry is written. Tier 0.

## F611 (B) -- at contract/gate rigor the operator's own edit becomes a pending proposal that approval neither lists nor blocks; it then goes stale and disappears

**Status:** fixed 2026-10-15 (Tier 0). Tier 1, decision fix-D8, change `spec/changes/the-operators-own-edit-applies-at-any-rigor`. `spec_service.save_document` proposes only a non-operator submission at contract/gate rigor; the operator's write applies at any rigor and records no proposal. The operator's capability merge (and so a fold) is the operator's own edit too: it now writes at gate rigor instead of proposing (no requirement said otherwise; the old proposal left the fold unarchived, the same loss). Acceptance drive `scripts/drive/d1015_f611_operator_edit_applies.py` committed failing first (863c103: 4 of 8 on HEAD), ALL PASS after. Tests: `test_operator_authored_documents.py` (flipped), `test_spec_merge.py` (two gated-merge tests rewritten), `test_spec_edit_proposals.py` (agents still propose). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G4: Spec documents, proposals x approval; scratch Hub `:8034`).

On `saffron-selkie` at `contract`, the operator PUT the content with one more criterion (`k3`). The response carried `"proposals": [{"id": "spprop-e2959e35e5ee", "unit_kind": "metadata"}]` instead of a write (as `the-operator-can-write-a-document-s-content` specifies). Propose answered 200 `warnings: []`; approve answered 200 with no mention of the pending proposal. The approved document has criteria `['k1', 'k2']` only. Accepting the proposal afterwards: **409 `proposal_stale`**; `GET …/proposals` then returns `[]`, and the Spec page shows no proposals panel (`SpecProposalsPanel` returns null on an empty list, `hub/ui/src/components/spec/SpecProposalsPanel.tsx:30-31`). The operator's edit is gone, and no screen ever said it was waiting. No capability requirement mentions pending proposals at approval. Related: F213 (twin proposals), not this.

Seam: Spec documents (rigor proposals x approval). Tier guess: 1 (design gap; no fix shape in the report).

## F612 (B) -- adopting a hand-placed `spec.json` indexes none of its requirements, and nothing but an agent's read says so

**Status:** fixed 2026-10-15 (Tier 0). After adoption (one document and the corpus sweep) the route calls `spec_service.mint_missing_identity`, which writes through `_apply_and_write` only when a requirement has no identifier: identity minted, file rewritten with its own content plus the identity and hub blocks, requirements indexed, the response's `minted` naming them. `spec_adoption` stays writer-free, and a file whose requirements all carry identity (any Hub-written corpus) is still adopted byte-for-byte. `test_an_adopted_requirement_is_indexed.py` failed before. Driven with `scripts/drive/d1015_f612_adopt_indexes.py`, 7/7 (FR-1 indexed, listed, reindex unchanged). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G4: Corpus & folding (Adopt); scratch Hub `:8034`).

`POST /project/documents/adopt` on an untracked `spec/changes/rounding-rules/spec.json` (one SHALL requirement `one-decimal`, one criterion) answered **201** with `"requirements": {"created": [], ...}`. No `spec_requirements` row was ever made: not by adopt, not by `POST /spec/reindex` (`unchanged: []`), not by propose, not by approve (approved anyway, 200, `tasks_created: []`). `ro "select identifier,state from spec_requirements where document_id='spdoc-1eb00639c57c'"` -> `[]` after each. `GET /spec/coverage` and `GET /spec/requirements` omit it, so the document reads as asserting nothing on every operator surface. Only the agent's `read_spec_document` shows it: `"identifier": null, "state": "unindexed"`, diagnostic "the document declares this requirement and the index has not seen it". Cause: `spec_index.requirements_from_payload` skips a requirement with no minted identifier (`hub/hub/spec_index.py:98-104`), and `spec_adoption.adopt` (`hub/hub/spec_adoption.py:284-345`) is deliberately writer-free, so it never mints one; a hand-placed file has no `aw_identity`. Not covered (grep "adopt", "unindexed").

Seam: Corpus & folding (Adopt) x Requirements, evidence & coverage. Tier guess: 0 (no fix shape in the report).

## F613 (B) -- the gate says "checks are still running… retry when they finish" while every check run is `error`

**Status:** fixed 2026-10-15 (Tier 0). `requirement_gate`: a Land that retries an errored check run now says the run's error and that it started again (never "Nothing is wrong yet"), and a task whose work does not merge starts no check run at Land (it could only error the same way) and gets no "they start when approval is requested" line; the conflict is the refusal. `test_approving_over_an_errored_result_runs_the_checks_again` (extended) and `test_a_land_refused_for_a_conflict_does_not_restart_the_checks` failed before. Driven with `scripts/drive/d1015_f613_errored_checks_said.py` (Haiku commits a file on the task, main commits a conflicting one, three Lands): before, three errored runs piled up; after, each Land names the conflict and adds no run (6/6). Opened before: open 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Worktrees & integration; scratch Hub `:8033`).

t-slug conflicts with a master commit (`df2cba3`). Two Land calls in a row both ended *"This task's checks are still running on the work approval would merge. Nothing is wrong yet; approval can be retried when they finish."* `GET /tasks/{id}/checks` at the same moment showed `running: false` and three runs, all `state: error`: *"c7f46c47706f does not merge cleanly onto df2cba307a5d … so there is no merged work to check"*. Each Land seems to start another check run. The sentence sends the operator into a retry loop that can never clear.

Seam: Worktrees & integration (gate refusal text x check state). Tier guess: 0 (wrong text in a refusal; no fix shape in the report).

## F614 (B) -- `agent_wrote_outside_workspace` records a write that was refused and never happened

**Status:** fixed 2026-10-15 (Tier 1 in substance: it moves design D5's notice). A declared write whose call the Hub can pair is on `Run.outside_workspace_writes` from first sight as `"status": "requested"` (still durable, D5), and becomes `written` with its `agent_wrote_outside_workspace` Warn only when its `tool_result` succeeds; a refused or failed call takes back what it added and is never announced. A killed run keeps `requested` entries, not announced (outcome unknown; footprints still count them, the conservative reading). An unpairable call (no `call_id`) is taken at its word as before. `test_outside_write_record.py`: 3 new tests, 2 failing on the old recorder; 13 tests updated to feed the result a runner emits (subagent-written, verified). Driven with `scripts/drive/d1015_f614_f669.py` (Haiku, acceptEdits): Write refused (`tool failed`), file absent, column `[]`, 0 events. Opened before: Measured in the 2026-10-15 full sweep (G7: Permissions & sandbox, Logs; scratch Hub `:8037`).

Under `acceptEdits`, alpha's `Write` to `C:\Users\huida\Documents\aw-sweep-1015-g7-outside\written.txt` was refused by Claude itself (`tool failed`), and the file does not exist. Even so, `run-e399f409512c` has `outside_workspace_writes = [{"kind": "outside", "tool": "Write", "path": "C:\\Users\\...\\written.txt", "calls": 1}]`, and the Activity feed shows a Warn: **"alpha wrote outside its workspace: Write → C:\Users\huida\Documents\aw-sweep-1015-g7-outside\written.txt"**. Its tool_result is `"Claude requested permissions to write to C:\\...\\written.txt, but you haven't granted it yet."`, `is_error: true`; `ls` of the outside dir shows `outside.txt` only. The recorder classifies the declared `tool_use`, not its result. A false accusation in the durable record. Not covered: F281/F282 cover shell writes not recorded and junction paths. F599 is the opposite error (a real write recorded clean). F628 is the same run's missing card.

Seam: Permissions & sandbox (outside-write recorder x tool result). Tier guess: 0 (no fix shape in the report).

## F615 (B) -- a vault report that brings new outside information can only end "answered", so the operator never hears it

**Status:** fixed 2026-10-15 (Tier 1, change `spec/changes/a-report-with-news-reaches-the-operator`). The vault-reports instruction (`vault-reports-4`) now says a report bringing information the source does not hold is not settled by the source and is answered `disputed`, which refers it to the operator; `answered` is kept for a report the source itself settles. No new outcome. Acceptance drive `scripts/drive/d1015_f615_outside_news_referred.py` committed failing first (8e633ae: answered on HEAD), ALL PASS after in two Haiku samples, with the control report (one the source settles) still answered. Test: the prompt assertions in `test_vault_reports.py`. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G5: Knowledge vault; scratch Hub `:8035`).

The agent reported `fct-1963faa9c835` ("Invoices are due within 45 days"): "The accountant informed this morning that the Nordlicht contract was renegotiated last week to 60-day payment terms." The `vault-reports` job answered `answered: the entry stands`: "…that renegotiated agreement is not part of the source provided for verification. The entry is accurate relative to the source it cites." That follows the design: `vault_reports.py:52` tells the model "Decide what is true from the source alone", and `answered` closes the report with no close control (`vault-report-…-close` count 0). The likeliest real report, "the source is out of date", goes nowhere: the operator never learns of the change, and the fact keeps answering 45 days to every agent. A report on a *source* ("the April email was a typo") did reach the operator as `referred`, and was closed from the Vault tab. Related: F581 (the answer is kept here, but nobody is shown it).

Seam: Knowledge vault (reports) x Manager jobs (`vault-reports`). **Fix shape (not decided):** a fourth outcome, "the source may be outdated -> refer", or refer any report whose claim is not found in the source. Tier 1.

## F616 (B) -- Distil is disabled on exactly the file sources that need it: a PDF or image uploaded while distillation was off never gets its facts from the app

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 93ea888): a tracked PDF or image with no text yet can be distilled and previewed; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G5: Knowledge vault; scratch Hub `:8035`).

`exact.pdf` and `mismatch` (the real `contract.pdf` bytes) were uploaded before the job had a runner. Their entries read "No text yet: the file has not been read, or reading it failed". `vault-distil` is **disabled** on both (`distil_disabled=True`, from `disabled={distil.isPending || !entry.available}`, `VaultPage.tsx:366`). The inline preview is absent too (`vault-file-pdf` count 0), although `GET /vault/sources/src-912e2171d796/file` answers 200. The API path works: `POST /vault/sources/src-912e2171d796/distil` answered `202 {"queued": true}`, then `distil_requested … written … read the PDF: 6 lines transcribed` and `… 1 fact stored`. The button is disabled in the one state where the route would help; the operator's only recourse is the API. F591 changed only this state's wording.

Seam: Knowledge vault (Vault tab x file-source availability). **Fix shape:** gate the button on a tracked file being present, not on `available`; show the preview whenever the file route serves. Tier 0.

## F617 (B) -- after a re-distil, a resolved contradiction calls the standing fact "A private fact, held on another machine", and an approved spec says its cited fact "is not in the vault on this machine"

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 93ea888): a contradiction side whose fact is gone carries `missing` and reads "no longer in the vault"; with a test that failed before. Earlier status: fixed 2026-10-15 for the Hub's words (Tier 1, with F587). The churn itself is gone (F587). A fact in no record or stub is now warned of as "no longer in the vault (it was deleted, or replaced when its source was distilled again)". A private entry, file or source whose holder is this machine says its text "is not at this machine's private location (it was removed, or the private location changed)" (`vault.private_text_is`). The Vault tab's card text "A private fact, held on another machine" for a fact that is gone is in the UI batch. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G5: Knowledge vault; scratch Hub `:8035`).

**Also (2026-10-15, F609's drive):** after a project is deleted with its private entries removed and its folder reopened, a private source's tracked stub reads "its text is held on TITAN, not on this machine" on TITAN itself. The same wording problem from another cause: the text is gone, not elsewhere. Fix with F617's honest wording.

F587's id churn seen from the operator's side. The operator resolved `ctr-2f72c1449976` in the Vault tab: 40 kg (`fct-dd4574520c84`) stands. Pressing **Distil** on the February source in the Vault tab brought its facts back as `fct-9f16f124d469` and `fct-9ea52a3b15d1`; `fct-dd4574520c84` is gone (`GET /vault/entries/fct-dd4574520c84` -> 404). Two screens then mislabel it, both pointing at a machine or privacy problem:

- The contradiction card: `The minimum wholesale order is 25 kilograms per delivery. · 2026-04-20 presumed` / `A private fact, held on another machine` / `Resolved: one fact stands. Müller confirmed by phone…`. The tracked fact the operator chose shows as "private", and the overruled one still "presumed" (F640).
- The approved document's FR-1 warning (`GET /vault/warnings`): `"kind": "missing", "message": "It cites fct-dd4574520c84, which is not in the vault on this machine."`

The real cause is the vault's own re-distil. F587 covers the id churn, but neither label.

Seam: Knowledge vault (distillation x contradiction card x spec warnings). **Fix shape:** fixing F587 removes both; until then, "no longer in the vault (its source was distilled again)" would be honest. Tier 0 for the wording.

## F618 (B) -- agent-keyed routes (heartbeat, compact, new-session, output, sessions) accept any name, and the writes mint phantom agents that the roster, the Overview and the agent-budget line count

**Status:** fixed 2026-10-15 (Tier 0). The roster (`GET /agents`) is the `agents` table: the 24-hour activity fallback (mail senders/recipients, heartbeats, output) and the task-assignee source are gone, so no write lists a name and `hub` is never an agent. `POST .../heartbeat` and `.../output` refuse a name with no agent row (`agent_roster.require_agent_row`; a write cannot ask `agent_is_known`, it is what made a name known); `GET .../timeline`, `GET .../output` and `GET /agent/sessions/{agent}` ask `require_known_agent`. Per fix-D9, `/compact` and `/new-session` and `hub/ui/src/api/context.ts` are deleted. No migration was needed: the phantoms were never `agents` rows, only names the fallback read from activity. `test_an_unknown_name_mints_no_agent.py` failed before (8/9). Driven with `scripts/drive/d1015_f618_names_mint_no_agent.py` on a scratch Hub, 18/18. A task assignee with no row is F642. Opened before: Measured in the 2026-10-15 full sweep (G1: Agents, Projects (Overview); G2: Runs; G6: Checkpoints, Agents; G7: Resilience refusal probes, Whole-project UI; scratch Hubs `:8031`, `:8032`, `:8036`, `:8037`).

`POST /agents/{name}/heartbeat`, `/compact`, `/new-session` and `/output` answer 201 for a name that was never an agent; the record they write makes the name "known", and `GET /agents` then returns it as an `open` agent. Measured in four groups:

- **G1** (`:8031`): `nonesuch`, `ghost1`, `ghost2` via heartbeat/compact/new-session. Before the heartbeat `GET /queue/ghost1/status -> 404 "ghost1 is not an agent in this project…"`; after it, 200, and every guarded read route (queue status, worktree, chat, conversations) answers 200. `GET /agents` names `[..., 'ghost1', 'ghost2', 'holder1', 'hub', ..., 'nonesuch', ...]` while `select count(*) from agents where lifecycle='open'` -> 11. The Overview reads "15 agents", shows Attention cards for ghost1, ghost2, nonesuch and hub, and Collaboration reads "15 of 8 agents". `hub` is the `sender` of the compact/new-session Message, added because the activity fallback skips only `operator`; even a legitimate New session on a real agent adds it (fresh project: `POST /agents/solo/new-session` changed `GET /agents` from `['solo']` to `['hub','solo']`). `GET /agents/{x}/timeline` and `GET /agent/sessions/{x}` answer 200 for an unknown name even before any write.
- **G2** (`:8032`): `GET /projects/$P/agent/sessions/nosuch` -> `HTTP 200 {"sessions": []}`, while `PATCH /agents/nosuch` is 404 "Agent 'nosuch' not found"; `POST /agents/nosuch/compact` -> 201 `{"status":"ok","message_id":"msg-5dff461b94f0"}`.
- **G6** (`:8036`): `POST /agents/ghost/compact` -> **201**; `GET /agents` and the Overview then list alpha, beta, `ghost` ("no runner") and `hub`, and the Overview reads "4 of 8 agents" against `agent_budget`.
- **G7** (`:8037`): `POST /agents/{name}/output` -> 201 for `nobody`, `operator` (reserved) and `a b c` (an invalid name). Each gets a conversation and then appears in `GET /agents` (`"name": "a b c" / "alpha" / "nobody" / "operator"`). The Overview reads "4 agents" while the header reads "1 agent"; "Delivery cap · agent budget" read "2 of 8 agents" with one phantom; an agent card shows for `nobody` with "no runner".

The checklist requires an unknown agent name to be refused on every agent-keyed route. `request_agent`'s budget is unaffected (it counts the table). The routes are API-only today (`context.ts` has no importers), but the Overview count and budget line are wrong for any project that ever had one. F417 (open) covers compact/new-session delivering nothing; the roster pollution, the `hub` phantom, the unguarded heartbeat, output and sessions routes are not covered. F642 is the same rule broken on the task assignee; F645 the refused trigger's conversation.

Seam: Agents (agent-keyed route guards) x Projects (Overview roster and counts). Tier guess: 0 (no fix shape in the report; F417's own recommendation is to delete compact/new-session and their hooks).

## F619 (C) -- an operator turn bound to a gated task runs the whole job; every status move is refused, and its peer mail starts a seven-turn chain

**Status:** fixed 2026-10-15 (Tier 0). `POST /agent/trigger` with a `task_id` on a start edge (`pending`/`assigned`, the edges `task_transition_service` gates) asks `dependency_gate.evaluate` and refuses with 409 `dependency_unmet` naming the prerequisite before any run or queue entry. Started work is not asked (D8: flagged, not stopped). `test_a_turn_for_a_task_whose_prerequisite_is_unmet_is_refused` failed before (the run started); controls for an approved prerequisite and an in-progress task pass. Driven with `scripts/drive/d1015_s1_tier0.py` (12/12): 409 naming the prerequisite, no run. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Dependencies, Inbound queue; scratch Hub `:8033`).

`POST /agent/trigger {agent: dev2, task_id: B}` started a run while B's prerequisite A was `pending`. dev2 implemented B in full; `in_progress` and `completed` were both refused with `dependency_unmet` (legible). It messaged dev1, and the agent-to-agent chain ran seven turns (dev2 -> dev1 -> dev2 -> rev -> dev1 -> rev -> dev2) before it went quiet. The trigger itself said nothing about the gate. The spec (`an-unmet-dependency-prevents-starting-and-nothing-else`) gates the status only, so this is a design gap rather than a defect.

Seam: Dependencies x Inbound queue (operator trigger). **Fix shape (from the report):** a warning or `waiting_reason` on the trigger would have saved most of the turns. Tier guess: 0.

## F620 (C) -- `POST /agent/trigger` with `"message": ""` starts a paid run

**Status:** fixed 2026-10-15 (Tier 0). `TriggerAgentRequest.message` refuses an empty or whitespace-only message with 422 naming Continue as the way to resume without words (the codebase's body-validation convention, not the plan's 400). `test_an_empty_message_is_refused_before_any_run` (3 cases) failed before: each started a run. Driven with `scripts/drive/d1015_s1_tier0.py` on a scratch Hub (Haiku), 10/10. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G7: Resilience refusal probes, Conversations; scratch Hub `:8037`).

`HTTP 200 "alpha started (run run-fe90137bada5)."` The model is `str` with no `min_length` (`agent_trigger.py:386`). The run was stopped at once.

Seam: Conversations & composer x Runs (trigger validation). Tier guess: 0.

## F621 (C) -- accepting the evidence a reviewer's verdict waited on does not re-dispatch the review, and the only way to ask again is the API

**Status:** fixed 2026-10-15 (Tier 0). `run_divergence.review_held_on_the_operator` / `ask_held_reviewer_again`: both evidence-decision routes (operator's and a granted agent's) read, before deciding, the reviewer's open `review` divergence on a task under review where approval is held for the operator; after the decision commits, if the hold has lifted and the reviewer has nothing running or queued, the same reviewer is asked again in the same checkout, recorded as that divergence's response (`retried`). A rejection lifts the hold too, so the reviewer can send the work back. 3 tests (asked again on accept; asked for its send-back on reject; nobody asked with no held review on record); the first failed before. Driven with `scripts/drive/d1015_f621_held_review_asked_again.py` (Haiku builder records evidence, Haiku tester's approval held, operator accepts): before, the tester was never asked and the task stayed under review; after, the tester ran again and approved (8/8). The app's own "Ask again" control is left to the UI batch (F336). Opened before: open 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Flows & review; scratch Hub `:8033`).

The first tester turn on t-char (`run-a105d649138b`) ended with *"approval cannot be recorded … evidence `ev-f1b8907929a6` … is awaiting the operator's decision"* (so F563's fix holds live: a Haiku reviewer ended its turn instead of waiting on `ask_user`). The operator accepted the evidence. The flow then skipped every tick with *"Ask tester again, review it yourself, or send it back"*. Asking again needs `POST /agent/trigger` with `review_task_id`, which has no UI control (`grep review_task_id hub/ui/src` returns nothing; F336, still open). The flow stalled on a decision the operator had already made. Related: F336, F563, F654.

Seam: Flows & review x Requirements, evidence & coverage (evidence decision). Tier guess: 0 or 1 (design gap; no fix shape in the report).

## F622 (C) -- a hand-authored task without requirements is approved and Landed, and its work never reaches main

**Status:** fixed 2026-10-15 (Tier 0, decision D7; also closes wpc-obs-1). `task_integration.review_alone_gates`: a loopless task with no requirement link and no evidence merges, and is reviewed at, its own branch tip instead of skipping with `NOTHING_TO_MERGE` / being refused as missing evidence. A task with evidence keeps evidence governing (D10). Three tests that pinned the old behaviour were inverted with D7 named. Driven with `scripts/drive/d1015_f622_land_without_requirements.py` (Haiku works the task, operator approves): merged, master holds the file (3/3). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Worktrees & integration, Tasks; scratch Hub `:8033`).

Task A was free-standing (no document, no requirement), worked by dev1. Land answered 200, approved. The integration record says `skipped: "no accepted evidence names a commit, so there is nothing to merge"`; the drawer shows "Not merged — …", the board Approved. No agent can fix it: recording evidence is refused (*"this project has no requirement task-e219c28fc828"*; dev1 and dev2 both tried). The task's commits `7bca975` and `223fa49` sit on branches, and no message names a remedy (add a requirement, record evidence, or merge by hand). It cascaded into F605: main kept the defect, and every later check failed on it. Deliberate per `task_integration.py:435-458` (a task with no loop lets evidence govern), and the F9-era notes (ledger lines 916 and 5078) record the skip as intended; still, the product approves work and then silently keeps it off main.

Seam: Worktrees & integration (integration skip) x Tasks (free-standing tasks). Tier guess: 1 (design gap; no fix shape in the report).

## F623 (C) -- a message to an agent with no runner answers plain success, and the Team block calls that agent "runner=native"

**Status:** fixed 2026-10-15 (Tier 0). A send to an agent with no runner is answered with `held: "no_runner"` and a delivery note (`messages.no_runner_note`; `Held` carries either hold and `held_by_hop_budget` stays for the budget's), and `send_message` passes both to the agent. The Team block lists a runnerless peer as "no runner; a message to it waits until the operator binds one", and the roster's `display_model` reads "No runner" where it fell through to "Native" (a stored legacy runner/model still shows). `test_a_message_to_a_runnerless_agent_says_held.py` failed before (4/4). Driven with `scripts/drive/d1015_f623_runnerless_held.py` (one Haiku turn): the agent told the operator gamma had not received it; 6/6. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G2: Inbound queue & messages, Agent environment; scratch Hub `:8032`, profile `sweep1015g2`, project `proj-47a583065b8e`).

alpha's `send_message` to runnerless gamma returned `{"success":true,"message_id":"msg-316388dd14b5"}` (transcript of `run-c1baf5d3b3ed`, `mcp__agentweave__send_message {"to_agent":"gamma"…}`). Nothing said gamma cannot run; `inbound_queue_entries` `entry-dba7c60b482d` sat `queued` until the operator bound a runner (F96 then held). The turn context's Team block (`GET /agents/agent-context?agent=alpha`) lists ``- `gamma`: runner=native``, which reads as if gamma runs; the palette says "gamma Native · idle". The hop-budget hold on the same tool does carry `held_by_hop_budget` + `delivery_note` (`hub/hub/mcp_server.py:313-318`); the runnerless hold has no equivalent, so the sender tells its operator the message was delivered. Not covered: F96 covers the drain, F97 the operator-side reason.

Seam: Inbound queue & messages x Agent environment (team roster in context). Tier guess: 0 (design gap; no fix shape in the report).

## F624 (C) -- a loop's outstanding-request check ignores an operator turn queued from the composer; F556 names only `/messages` mail

**Status:** fixed 2026-10-15 (Tier 0). `_pending_loop_request` names an operator entry for the job's agent with no `Message` (the composer's turn), still queued or delivered into a live run, as `{"kind": "operator", "to": <agent>, ...}` after the question and mail cases. `test_an_operator_turn_queued_from_the_composer_is_an_outstanding_request` failed before (`None`); a delivered-turn control passes. **Not driven live:** a drained loop needs an agent's `create_loop`; the check is called directly, as F556's sibling tests do. The UI does not render `pending_request` kinds. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G6: Jobs & loops; scratch Hub `:8036`).

alpha had no runner. `POST /agent/trigger` queued "When you next run, tell me the date." (`status: queued`). The drained loop then fired and `loop_queue_exhausted` gave `pending_request: null`. Same setup with `POST /messages {"to":"alpha",…}` gave `pending_request: {"kind":"message","to":"alpha","reason":"please answer",…}`, so F556 holds for mail. `_pending_loop_request` (`scheduler.py:435`) reads only the `Message` model, and the composer, the operator's commonest door, creates an inbound-queue entry with no `Message`. In the territory of decision `F556-outstanding-message-direction`; the `agent-loops` ac41/ac42 wording is also still open.

Seam: Jobs & loops (loop stop) x Inbound queue (composer entries). Tier guess: 0 (design gap; no fix shape in the report).

## F625 (C) -- a waiting firing whose queued entry is withdrawn stays `in_progress` forever, even after its job is archived

**Status:** fixed 2026-10-15 (Tier 0). `scheduler.close_firings_left_without_input` stops a job's `in_progress` firing that has no queued entry in its conversation and no live run, with "its queued message was withdrawn before a turn delivered it". Called by the withdraw route and by the job archive (for firings orphaned before this fix). Closed as the existing `stopped`, not a new `withdrawn` status, so the UI needs nothing new. Two tests in `test_a_job_for_an_agent_with_no_runner_waits.py` failed before, and a control (archive leaves a still-queued firing `in_progress`) passes. Driven with `scripts/drive/d1015_s1_tier0.py` on a scratch Hub (Haiku), 10/10. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G6: Jobs & loops; scratch Hub `:8036`).

Job `f596` (`job-1529db113fd4`) waited on a runnerless agent (200, `waiting_reason`, history `in_progress`). `DELETE /queue/entries/entry-166e680617e0` answered 200. The history still read `"status": "in_progress"` after the loop drained, stopped and was archived. The follow-on to F596's "the firing stays `in_progress`" choice: nothing resolves the firing when its entry is withdrawn.

Seam: Jobs & loops (firing record) x Inbound queue (withdraw). Tier guess: 0 (no fix shape in the report).

## F626 (C) -- with a vault job enabled and no runner, an upload or proposal records nothing at all; only Distil refuses

**Status:** fixed 2026-10-15 (Tier 0). The plan's second shape (the panel toggles `enabled` on its own, so refusing an enable before a runner is chosen would refuse a natural order of clicks): when the distillation, spec-vault-check or reports job is on with no runner, its background start records a `failed` firing, "Did nothing: the <job> job is on but has no runner. Choose one on the Manager page." (`manager.record_no_runner`; the three refusals carry `no_runner`). A job that is off records nothing. `test_a_job_with_no_runner_says_so.py` failed before; `test_with_no_runner_nothing_is_spawned_or_recorded` now expects that one firing. Driven on a scratch Hub: enable with no runner, upload -> the activity shows the failed firing with that sentence. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G5: Manager jobs; scratch Hub `:8035`).

`PATCH /manager/jobs/vault-distillation {"enabled": true}` with no runner answers 200, `"needs_runner": true, "runner_id": null`. An API upload (`POST /vault/sources`, 201) and an upload from the Vault tab's own form both produced no `manager_job_fired` row, an empty `GET /manager/activity` (`{"firings": []}`), and no message on the page. Only `POST …/distil` says why: `409 "The vault distillation job has no runner. Choose one on the Manager page."` The Manager page does word the row "No runner (the job does nothing)" (F590 holds). This was the 2026-10-13 sweep's unfiled observation, now filed. F590 covers only the page wording.

Seam: Manager jobs x Knowledge vault (upload trigger). **Fix shape (from the report):** the PATCH should refuse, or the upload should say so. Tier guess: 0.

## F627 (C) -- when another process holds the database, every route answers a bare `500 Internal Server Error` after about 42 s

**Status:** fixed 2026-10-15 (Tier 0). A `database is locked` error answers 503 with `Retry-After: 5`, saying the database is busy, that the Hub waited its 30 s busy timeout, and that the request did not finish. The wait stays bounded by that timeout (F517 chose 30 s; not shortened). Any other driver error is still a 500. `test_a_locked_database_answers_busy.py` failed before. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G7: Resilience, failure injection; scratch Hub `:8037`).

A `BEGIN EXCLUSIVE` with no writes was held on the scratch DB for 45 s; the journal mode is `delete`, so readers block too. GET agents, GET events/history, PATCH agent, POST trigger, POST permission decide and POST tasks all returned `500 Internal Server Error` in 42.5-42.6 s. The log shows `sqlite3.OperationalError: database is locked`. There is no legible "the database is busy, retry" answer. Not covered: F349 covers concurrent triggers (that held) and F292 CI setup locks; neither covers a route's answer to an external lock.

Seam: Resilience (SQLite lock x route error handling). Tier guess: 0 or 1 (design gap; no fix shape in the report).

## F628 (C) -- under `acceptEdits`, a write outside the workspace is refused silently: no card, and the agent tells the operator to approve it in a dialog that does not exist

**Status:** fixed 2026-10-15 (Tier 2, decision fix-D12, `spec/changes/edit-files-asks-the-operator-for-everything-else`). `acceptEdits` joins `runner_commands.APPROVER_PERMISSION_MODES` and the operator-answered postures, so a Claude "Edit files" run names the Hub's approval tool and every call Claude Code would ask a person about becomes an operator card; Claude still approves its own edits inside the workspace. Claude only: Codex takes its posture from `posture_for`, not the run env, and keeps its own. Acceptance drive `scripts/drive/d1015_f628_accept_edits_card.py` committed failing (no card on HEAD) and passes 5/5 after (card for the outside Write, denied, nothing written); four argv goldens gain the approver flag pair and nothing else. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G7: Permissions & sandbox; scratch Hub `:8037`).

No `permission_requests` row was created for `run-e399f409512c`. The agent's reply was *"The Write tool requires permission approval to create the file at that location. The request is pending your approval in the permission dialog."* The run ended `completed`, and there is no dialog to approve. The refusal is legible to the agent but reaches the operator only as the agent's wrong paraphrase. The same run's record wrongly says the write happened (F614).

Seam: Permissions & sandbox (acceptEdits refusal x operator surface). Tier guess: 1 (design gap; no fix shape in the report).

## F629 (C) -- Land is the approval control on a completed task, but the merge-verdict note renders only under review

**Status:** fixed 2026-10-16 (Tier 0, UI batch, afad0be): a completed task shows what approving writes before Land; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Worktrees & integration (UI); scratch Hub `:8033`).

On t-slug (`completed`, conflict with master), the drawer offers **Land it** but no `task-approval-writes-*` note: `ApprovalWritesNote` renders only when `canApprove`, i.e. under review. The operator sees the conflict only after pressing Land, as a 409 (Chromium logged `Failed to load resource: 409`). `GET /integration-preview` already knew: *"approval will be refused: wordlib/shared.py in commit c7f46c47706f conflict with master"*.

Seam: Worktrees & integration (task drawer x integration preview). Tier guess: 0 (missing warning; no fix shape in the report).

## F630 (C) -- a manager job accepts a model its runner's CLI does not declare; it fails only at the firing

**Status:** fixed 2026-10-15 (Tier 0). `PATCH /manager/jobs/{key}` judges a newly set model against the runner the job will use, with the catalog's sentence `POST /runners` gives (400), and refuses a model on a job with no runner ("Choose the job's runner first…"); an unchanged stored model is left alone, as on runners. `test_a_job_model_is_one_its_runner_declares.py` failed before; fixtures in `test_manager_jobs.py` and `test_vault_distillation.py` used undeclared models (`m`, `claude-sonnet-4-6`) and now use declared ones. Driven on a scratch Hub: `gpt-9` -> 400 with the catalog sentence; `haiku` -> 200. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G5: Manager jobs; scratch Hub `:8035`).

`PATCH /manager/jobs/vault-distillation {"runner_id": "<claude runner>", "model": "gpt-9"}` answers 200 and stores it; it answers 200 with no runner as well. `POST /runners {"cli":"claude","model":"gpt-9"}` answers `400 "'gpt-9' is not a model 'claude' declares; expected one of: …"`. The next firing failed with that same sentence (`duration_ms` 0, nothing spent; the sentence shows in activity). Validation at the wrong door; legible later.

Seam: Manager jobs x Runners & models (model catalog). Tier guess: 0 (no fix shape in the report).

## F631 (C) -- setting a document's size leaves its step outside the new journey

**Status:** fixed 2026-10-15 (Tier 0). A size change moves a step the new journey lacks to where the document now stands (`spec_journey.step_for_size`): the requirements and acceptance steps map to their joined or split form (`requirements` -> `requirements-and-acceptance` on small, and back to `requirements` on large); any other step moves forward to the journey's first step after it, as `next_step` does; a step named in the same request still wins. The move is recorded in the journey event. Both size routes pass the project's steps. `test_spec_journey.py` (6 new cases) failed before. Driven on a scratch Hub: `requirements` then size small -> `requirements-and-acceptance`. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G4: Spec documents; scratch Hub `:8034`).

`POST /documents/journey {"step":"requirements"}` then `{"size":"small"}` -> `step: "requirements"`, `journey: ["intake","requirements-and-acceptance","tasks","delivery"]`. Propose then warned "the document is at step 'requirements'; … goes on to requirements-and-acceptance, tasks, delivery", a step that is not in its journey.

Seam: Spec documents (size x step). Tier guess: 0 (no fix shape in the report).

## F632 (C) -- the payload schema tells agents an unresolved question blocks proposing; it only warns

**Status:** fixed 2026-10-15 (Tier 0). `OpenQuestion.resolved`'s description now says proposing or approving with an unresolved question is allowed but warns (`unresolved_question`). `test_the_schema_says_a_question_warns.py` failed before. Not driven live: text only, read from the same model the tool schema is built from. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G4: Spec documents; scratch Hub `:8034`).

`OpenQuestion.resolved`'s description (`hub/hub/spec_payload.py:239-242`), which is in the tool schema agents read: "An unresolved question blocks the document from being proposed". Observed: propose with an unresolved question -> 200 `proposed: true`, `unresolved_question` under `warnings`. Stale since the warn-don't-gate change (2026-10-08). Related: F573 (roadmap open questions).

Seam: Spec documents (payload schema text x propose warnings). Tier guess: 0.

## F633 (C) -- "1 waiting — hop budget exhausted" shows in a conversation that has nothing waiting, with no Continue and no pointer

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 8087723): the agent-level waiting line says "in another conversation" when nothing is queued here; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G2: Inbound queue & messages; scratch Hub `:8032`).

After beta's hop-held entry (`conv-1cd110c03f20`), a *fresh* beta conversation (`conv-0dca16415b1e`) showed "1 waiting — hop budget exhausted" under its transcript, with no Continue button and no word of which conversation holds the entry (screenshot `g2-stopped.png`). Not covered: F131 (fixed) was about Continue reporting another conversation's entry.

Seam: Inbound queue & messages (agent-level queue status x conversation view). Tier guess: 0 (wrong context; no fix shape in the report).

## F634 (C) -- in a narrow window the panel toggle flips to "Hide panel" but opens nothing; a separate "Panel" button opens the drawer

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 973aee3): the narrow-window panel toggle opens the drawer; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G2: Conversations & composer; scratch Hub `:8032`, Playwright Chromium).

At 700 px, clicking `conversation-toggle-panel` ("Show panel") sets `aria-pressed=true` with no visible change and no dialog. The drawer opens only from the `conversation-open-document` "Panel" button at the top of the page (`ConversationView.tsx:570-580`, where the drawer needs both `shellVisible` and `overlayOpen`). Once open, the drawer takes focus ("Close Panel"), one Escape closes it, and focus returns to the opener: all held.

Seam: Conversations & composer (narrow layout). Tier guess: 0 (dead click; no fix shape in the report).

## F635 (C) -- the Ctrl+K palette drops focus to `<body>` on Escape and after choosing an item

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 613ca3b): Ctrl+K gives focus back to its opener on Escape and after choosing; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G7: Keyboard & dialogs; scratch Hub `:8037`, Playwright, keyboard only).

Before: `BUTTON|project-tab-jobs`; open: `INPUT`; after Escape: `BODY`. After typing "alpha" and Enter: `BODY`. Every Radix dialog opened from a button returns focus correctly; the palette (`cmdk` `Command.Dialog`, opened by a global key handler) does not. Not covered.

Seam: Keyboard & dialogs (palette focus return). Tier guess: 0.

## F636 (C) -- the "Permission decisions" history is reachable only while a question is open, and its rows do not say what was decided

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 613ca3b): the Overview links to questions and decisions when none is open; decision rows name their command and an expired one when it was asked; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G7: Permissions & sandbox; scratch Hub `:8037`).

`QuestionsPanel` holds `PermissionDecisions` (`QuestionsPanel.tsx:273`). The only way into the panel is `QuestionInterruptCard` on the Overview, rendered when `unanswered > 0` (`OverviewPage.tsx:155`); the palette has no "questions" entry. With no open question, no screen shows past decisions. The rows show `status · agent · tool · who · when`, not the command, so three "PowerShell" rows cannot be told apart; expired rows show no time. F231's fix (2026-09-23) added the list, but its reachability was not driven.

Seam: Permissions & sandbox (decision history) x Questions (panel entry point). Tier guess: 0 or 1 (design gap; no fix shape in the report).

## F637 (C) -- the Jobs page says "No jobs yet / Create First Job" after six jobs have fired, because archived jobs and loops have no view

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 3c9dd5c): the Jobs page lists archived jobs and an all-archived project reads "No active or paused jobs · N archived"; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G6: Jobs & loops; scratch Hub `:8036`).

After archiving every job, the Jobs page rendered:

> Scheduled Jobs … all / active 0 / paused 0 · No jobs yet · Create scheduled jobs to automatically trigger agents on a cron schedule. · Create First Job

`GET /jobs` hides archived jobs and the page offers no archived filter, so a past loop's history, firings and stop reason have no screen (a known API trap). Not covered: the ledger notes near line 17912 cover only the enable controls.

Seam: Jobs & loops (archive x Jobs page). Tier guess: 0 or 1 (design gap; no fix shape in the report).

## F638 (C) -- an agent cannot create a disabled job

**Status:** fixed 2026-10-15 (Tier 0). The MCP `create_job` takes `enabled` (default true), and passes it to the agent route, which already accepted it; the rendered tool surface describes it. The `test_mcp_server` payload case with `enabled=False` fails on the old signature; `test_tool_surface_matches_server` and the Claude context snapshot are updated. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G6: Capability plane; scratch Hub `:8036`).

The `create_job` MCP tool has no `enabled` parameter (`mcp_server.py:778`), while the operator route has one. Asked for a disabled job, Haiku created an enabled one and then called `toggle_job`, which leaves a window where a frequent cron could fire. The agent and operator planes disagree.

Seam: Capability plane (MCP `create_job` x operator job route). Tier guess: 0.

## F639 (C) -- the settings copy for `allow_agent_jobs` names only flows and loops, but the setting refuses `create_job` too

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 3c9dd5c): the settings row and Overview hint name create_job too; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G6: Capability plane; scratch Hub `:8036`).

Settings page: *"Agents may create flows and loops (create_flow, create_loop)."* Overview: *"Agents may start flows — Needed for create_flow and create_loop."* The actual refusal was for `create_job`, and the refused-capability question itself says "loops, flows and jobs".

Seam: Capability plane (settings copy x refusal). Tier guess: 0.

## F640 (C) -- a resolved contradiction keeps marking the overruled fact "presumed"

**Status:** fixed 2026-10-15 (Tier 0). The contradictions list answers a resolved contradiction with `presumed: null` and no side marked presumed (`vault._listed_contradiction`); the record on disk keeps what was presumed, and the card and spec-check texts already spoke of presumption only while open. `test_resolving_writes_a_decision_and_supersedes_the_other_fact` asserts it and failed before. Not driven live: a contradiction needs two sources distilled by a real worker; the route-level test drives the real list with a fake distiller. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G5: Knowledge vault; scratch Hub `:8035`).

After the resolve, `GET /vault/contradictions` still has `"presumed": "fct-186c668439d9"`, and that side carries `"presumed": true`. The card shows `25 kilograms … · 2026-04-20 presumed` above "Resolved: … 40 kilograms … stands." (see F617 for the same card after a re-distil).

Seam: Knowledge vault (contradiction resolution x card). Tier guess: 0.

## F641 (C) -- the Manager page reads "empty" for a firing that answered a report, and the upload 413 does not name the limit

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 93ea888): the reports firing that answered records `answered` (manager.OUTCOMES), badged in the Manager panel; with a test that failed before. Earlier status: partly fixed 2026-10-15 (Tier 0). The 413 names the limit it applied, which differs by route: "Request body too large: this route takes at most 10 MiB (10485760 bytes)." for a vault file, 1 MiB elsewhere (`main` body-size middleware). `test_vault_files.py` asserts both and failed before. Driven: a 2 MiB JSON source -> 413 naming 1 MiB. **Left for the UI batch:** the reports firing's `empty` -> `answered` (a new outcome; the Manager page types its outcome badges, so the backend and UI change land together). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G5: Manager jobs, Knowledge vault; scratch Hub `:8035`).

The Manager page lists the `vault-reports` firing that answered a report as `Vault reports · empty · … answered: the entry stands`; an operator reads "empty" as "did nothing". Separately, a PDF of 10 MiB + 19 bytes answers `413 {"detail": "Request body too large"}`, which never says the limit is 10 MiB; one at exactly 10 MiB is accepted (201).

Seam: Manager jobs (firing outcome label) x Knowledge vault (upload limit). Tier guess: 0.

## F642 (C) -- a task's assignee accepts an agent that does not exist

**Status:** fixed 2026-10-15 (Tier 0). Task create (`check_task_create`, so `create_job`'s initial tasks and the agent plane too) and PATCH refuse an assignee that is not an open agent of the project with 422 naming why (`agent_roster.assignee_refusal`: no row, or archived); a PATCH repeating the current holder is not refused. `test_a_task_is_held_by_an_open_agent.py` failed before. Driven with `scripts/drive/d1015_s4_names.py`: create and PATCH to `ghost` 422, holder kept. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Tasks; scratch Hub `:8033`).

`PATCH /tasks/{A} {"assignee": "ghost"}` -> 200, and `assignee: "ghost"` was stored. The Agents row requires an unknown agent name to be refused on every agent-keyed route (F618 is the same rule on the agent routes). Not tried: the same value on create.

Seam: Tasks (assignee validation) x Agents. Tier guess: 0.

## F643 (C) -- refusals and diagnostics that give a code instead of a sentence (drift resolve, arrange, the manifest-drift strip)

**Status:** fixed 2026-10-16 (Tier 0, UI batch, e94b128): the drift strip, corpus strip and place-under refusal print each diagnostic's `message`; with a test that failed before. Earlier status: fixed 2026-10-15 (Tier 0). Every corpus diagnostic (`ManifestDiagnostic.to_dict` and `spec_documents._diag`) carries a `message` sentence beside its code (`spec_manifest.describe_diagnostic`); the arrange refusal reads "this placement is not allowed: <why>"; an unknown drift resolution names the three accepted and what each means. `test_a_diagnostic_is_a_sentence.py` and two `test_spec_index_writer.py` assertions failed before. Driven on a scratch Hub: an unfiled document's message, and a self-parent arrange answering "… cannot be its own parent." **Left for the UI batch:** the Spec page's drift strip still prints `code — path`; it should print `message`. The "every new document is unfiled until Rebuild" observation is unchanged (a new document is not added to the index on create). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G4: Corpus & folding, Drift; scratch Hub `:8034`).

- `POST /spec/drift/{id}/resolve {"resolution":"whatever"}` -> 422 "unknown resolution 'whatever'", naming none of `specification_updated` / `implementation_corrected` / `no_change_required` (`hub/hub/requirement_evidence.py:1736-1741`); the evidence decision route's equivalent names its permitted words.
- `POST /spec/documents/arrange` cycle / self-parent -> 422 "this placement is not allowed" with only `manifest_parent_cycle` / `manifest_self_parent` codes.
- The Spec page's manifest-drift strip prints raw codes: "unfiled_document — spec/changes/saffron-selkie/spec.json", "intrinsic_metadata_conflict — … (status: exploring → approved)". Every newly created document shows as `unfiled_document` until someone presses Rebuild.

Seam: Corpus & folding / Drift (refusal wording, Step 4 rule 6). Tier guess: 0.

## F644 (C) -- a capability created from the app lands under `spec/changes/<random-name>/`

**Status:** fixed 2026-10-15 (Tier 0). `mint_document_path` takes the kind and title: a capability created with no path goes to `spec/capabilities/<slug-of-title>/spec.json` (`spec_naming.mint_capability_path`; a taken name gets `-2`, `-3`…; a title with no slug a placeholder name under the same root). A change keeps its placeholder name. `test_a_capability_is_created_under_capabilities.py` failed before. Driven on a scratch Hub: two "Temperature conversion" capabilities -> `temperature-conversion`, `temperature-conversion-2`; a change -> `spec/changes/emerald-minotaur`. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G4: Spec documents, Corpus & folding; scratch Hub `:8034`).

`POST /project/documents {"title":"Temperature conversion","kind":"capability"}` -> `spec/changes/magenta-sylph/spec.json`. `mint_document_path` ignores the kind (`hub/hub/api/v1/spec.py:2099-2101`), so the corpus convention (`spec/capabilities/<name>/`, as this repository's own `spec/` has it) is reachable only by passing an explicit `path`. The name is random, not from the title.

Seam: Spec documents (create) x Corpus & folding (layout). Tier guess: 0.

## F645 (C) -- a refused trigger for an unknown agent leaves an open conversation (and a withdrawn queue entry) that the rail files under "Archived agents"

**Status:** fixed 2026-10-15 (Tier 0). The trigger route asks for the agent row before it opens a conversation or queues an entry (`agent_trigger.trigger_agent`), with the dispatch's own sentence (`_not_an_agent_to_trigger`). `test_a_refused_trigger_leaves_no_conversation_and_no_queue_entry` failed before (a conversation was created). Driven with `scripts/drive/d1015_s4_names.py`: 409, no conversation, no queue entry. Rows left by earlier refused sends stay (no migration). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: Agents, Conversations & composer; G7: Resilience refusal probes; scratch Hubs `:8031`, `:8037`).

- **G1:** `POST /agent/trigger {"agent":"ghost3","message":"refused first send"}` -> 409 "ghost3 is not an agent…". `conversations` gains `conv-ef676120ce46` (agent ghost3, open, titled with the message), and `inbound_queue_entries` gains a withdrawn row. The rail shows it under **Archived agents** marked *agent archived*; opening it showed the composer and no `archived-agent-notice`.
- **G7:** `POST /agent/trigger {"agent":"ghost","message":"x"}` -> 409 *"ghost is not an agent in this project…"*, but `get_open_conversation` (`agent_trigger.py:922`) has already created `conv-2af9b04f614b` for agent `ghost`, titled "x". The rail lists it under **Archived agents** as "x — agent archived".

The label rests on the F193 premise "an agent absent from the open roster is archived", and neither agent ever existed. The checklist says *"a refused first send deletes the exploration it created"*. Not covered. F618 is the same unknown-name gap on the other agent routes.

Seam: Agents (trigger refusal) x Conversations & composer (conversation created before the check). Tier guess: 0 (no fix shape in the report).

## F646 (C) -- a directory inside another project's directory opens as a separate project

**Status:** fixed 2026-10-15 (Tier 0, per the fix plan's S8). Opening (or creating, which opens) a directory inside another registered project's directory is refused 409 `project_nested`, naming that project, and writes no marker. A sibling whose name only starts with the outer's still opens. `test_project_lifecycle.test_a_directory_inside_another_project_is_refused_naming_it` failed before. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: Projects; scratch Hub `:8031`, nested project `proj-590bb70106aa`).

`POST /projects/open {"path":".../aw-sweep-1015-g1/nested"}` -> 200, a new `proj-590bb70106aa`. Its `.agentweave/project.json` lands inside g1's repository (`git status`: `?? nested/`). One project's agents can then edit the other's files, and the outer project's worktrees and integration see the inner one as untracked content. Whether this should be refused or warned about is a design question (the report grades it C/D). F610 is the same nesting question for the private vault location.

Seam: Projects (open x ProjectWorkspace binding). Tier guess: 1 (design gap).

## F647 (C) -- `PUT /project/instructions {}` clears the instructions without a word

**Status:** fixed 2026-10-15 (Tier 0). `InstructionsUpdate.content` is required: `{}` answers 422 naming `content` and changes nothing; clearing is an explicit `{"content": ""}` (the app always sends the field). `test_instructions.test_an_empty_body_is_refused_and_clearing_takes_an_explicit_empty_string` failed before. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: Projects; scratch Hub `:8031`).

`InstructionsUpdate.content` defaults to `""`, so an omitted field is a clear. The UI asks first ("Clear the instructions…? … no history and no undo"), and that held, but the API's omitted-field path bypasses it (Step 4 rule 7).

Seam: Projects (instructions route x clear confirmation). Tier guess: 0.

## F648 (C) -- the agent-budget refusal names no remedy

**Status:** fixed 2026-10-15 (Tier 0). The `request_agent` budget refusal says how many open agents the project has and names both remedies and whose they are: ask the operator to archive an agent (freeing its slot) or raise the agent budget in Settings. `test_the_budget_still_bounds_it` asserts the remedies and failed before. Driven with `scripts/drive/d1015_s4_names.py`: a Haiku agent at budget 1 met the refusal and relayed both remedies; no agent created. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: Agents; scratch Hub `:8031`).

An agent's `request_agent` at budget gets `409: Project agent budget exhausted (12/8)` (`run-31a3ebe212d5` transcript). It does not say that the operator raises it in Settings -> Agent budget, or that archiving frees a slot (Step 4 rule 6).

Seam: Agents (`request_agent` x agent budget). Tier guess: 0.

## F649 (C) -- `agentweave status` ignores `--profile`, and the CLI's hints drop profile and port

**Status:** fixed 2026-10-15 (Tier 0). `status --profile X` says when the port is held by another profile's Hub (by its PID file), returns 1, and warns when a hand-started Hub has no PID file for X. The stopped and reset hints name `--profile`/`--port` (`_hub_start_hint`). Tests in `tests/test_cli_port_and_runtime.py::TestProfilesAreHonoured` failed before. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: CLI & lifecycle; scratch Hub `:8031`).

`status --profile nosuchprofile1015 --port 8031` reports "running (native) … 4 registered", which is profile `sweep1015g1`'s Hub; the code reads only the port (`src/agentweave/cli.py:85-126`). `status --profile sweep1015g1 --port 8039` says "stopped. Run 'agentweave' to start it", which would start the default profile on :8000. `reset --profile g1throw1015 --yes` ends "Run 'agentweave' to start fresh", with the same problem.

Seam: CLI & lifecycle (status/reset x profiles). Tier guess: 0.

## F650 (C) -- `agentweave stop --profile X --port N` against a native Hub it did not start falls through to Docker and prints a Docker-daemon error

**Status:** fixed 2026-10-15 (Tier 0, with F649). `stop` reads the running Hub's `/health`: a native Hub with no PID file for this profile is left running, with an error saying this CLI did not start it; nothing calls Docker. Same test class. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G1: CLI & lifecycle).

The Hub on :8038 was started from source, so it had no pidfile. Stop printed `[ERR] Failed to stop Hub: failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine…` while a native Hub answered `/health` on that port. The CLI-started Hub stopped cleanly ("Stopping Hub (native, PID 9264)… Hub stopped").

Seam: CLI & lifecycle (stop x pidfile x Docker fallback). Tier guess: 0.

## F651 (D) -- an answer that arrives after the timeout is both read in-run by `get_answer` and delivered as a new paid turn

**Status:** fixed 2026-10-15 (Tier 0). When the asking agent's run reads an answered question (`GET /agent-actions/questions/{id}`, behind both `get_answer` paths), the queued delivery of its completed batch is withdrawn with "the agent read this answer in its run with get_answer" and announced. The entry is identified by its content, which `_batch_delivery_text` renders exactly. `hub/tests/test_an_answer_read_in_run_is_not_delivered_again.py`: 2 failed before, plus controls (a read before the answer withdraws nothing; an unrelated operator message stays). **Not driven live:** it needs a question to time out mid-run and the agent to then poll `get_answer`, which a model does not do on cue. Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G2: Questions; scratch Hub `:8032`).

`q-d372bc1b55b6` timed out at 10:48:29 and was answered "No" at 10:48:43 while the run was still alive. The agent's in-run `get_answer` returned "No". When the run ended, `entry-737fc8ae9288` ("Question: … Answer: No"), together with the first late answer, started `run-75314a518786`, whose whole content was "the operator's answers have now come through, and they confirm my implementation decisions": a paid turn repeating what the agent already knew. Delivery as new input is the specified behaviour; the duplicate is the cost. Not covered.

Seam: Questions (late answer x in-run `get_answer`). Tier guess: 0 (design gap; no fix shape in the report).

## F652 (D) -- Explore in an existing conversation creates its document on the press; a refused or never-made send leaves an empty `exploring` document

**Status:** fixed 2026-10-16 (Tier 0, decision fix-D15, amending D4's "one press creates"). In an existing conversation Explore now arms, as in a new one: the document is created at send, before the turn, attached to it, and withdrawn if the turn is refused. Unit tests in `specChatSurface.test.tsx` (3 failed first); driven with `scripts/drive/d1016_d14_d15_screens.py`: the press created nothing, a 10,050-character send was refused and left nothing, the next send created `maroon-yeti` and attached it. The composer still has no length counter (side note above, not built). Opened before: open 2026-10-15. Measured in the 2026-10-15 full sweep (G2: Conversations & composer; scratch Hub `:8032`).

In an existing conversation, pressing Explore POSTs `/project/documents` at once (201, `teal-pegasus`). A 10,050-character send was then refused with 422 (the UI showed "String should have at most 10000 characters" and kept the draft), but **the document stayed**. A second press in another browser session left `coral-kirin` behind with no send at all. In a *new* conversation the requirement (`spec-chat-session` n1) holds: the document is created at send, the 422 follows, and the DELETE answers 200 (`amber-hydra` gone). n1 is scoped to new conversations, and D4 says one press creates. Side note: the 422 text is pydantic's ("String should have…"); it names the limit, but the composer has no counter.

Seam: Conversations & composer (Explore x refused send). Tier guess: 0 (design gap).

## F653 (D) -- one hop-held entry gets three Continue controls and two explanations

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 8087723): one held entry gets one Continue (its own); the red band and the composer Continue are gone for hop-held work; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G2: Inbound queue & messages; scratch Hub `:8032`).

For a single held entry, beta's conversation shows the entry's own `Continue` / `Discard`; an amber banner "Autonomous continuation paused — … Continue"; a red band "Queued messages reached the hop limit … Continue to deliver them, or discard them"; and the composer's `Continue` "beta has work waiting". The red error styling also reads as a failure (screenshot `g2-beta-held.png`).

Seam: Inbound queue & messages (hop hold x conversation view). Tier guess: 0 (friction).

## F654 (D) -- the review-dispatch refusal omits the remedy that works

**Status:** fixed 2026-10-15 (Tier 0). `review_dispatch_refusal` now asks the author rules before the holder check, so an author asking to review is told it is the author (403), and `holder_refusal` names asking the silent holder again before deciding it yourself. 2 assertions failed before. Driven on a scratch Hub: the author (builder) got the 403 author sentence, a third agent the 409 naming "Ask 'tester' to review it again". Opened before: open 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Flows & review; scratch Hub `:8033`).

`POST /agent/trigger {agent: dev1, review_task_id: t-char}`, where dev1 is the author -> 409 *"already under review by 'tester'. 'tester' has no turn running or queued on it … Decide it yourself: approve, reject, or send it back"*. It names the occupancy, not the author rule, and omits the remedy that worked a moment later: re-dispatching tester, which the flow's own skip line recommends (F621).

Seam: Flows & review (review-dispatch refusal wording). Tier guess: 0.

## F655 (D) -- a loop past its `stop_at` still shows as enabled with a next run until the next tick records the stop

**Status:** fixed 2026-10-16 (Tier 0, UI batch, 3c9dd5c): a loop past stop_at with no stop_reason reads "Stopping" and shows no next run; with a test that failed before. Earlier status: open 2026-10-15. Measured in the 2026-10-15 full sweep (G6: Jobs & loops; scratch Hub `:8036`).

`stop_at` was 10:50:00.8. At 10:51:23 the job read `enabled: true, next_run: 10:52:00Z, stop_reason: null`. The 10:52 tick recorded `job_run_skipped` and `loop_stopped` "loop stop time reached". Nothing fired late, so this is display only.

Seam: Jobs & loops (stop_at x job read). Tier guess: 0.

## F658 (D) -- Check now is unreachable for a document with no vault warnings

**Status:** fixed 2026-10-16 (Tier 0, UI batch, e94b128): a document with no vault warnings shows "No vault warnings" with Check now; with a test that failed before. Earlier status: open 2026-10-15. Found by reading code in the 2026-10-15 full sweep (G5: Knowledge vault; not driven: no clean document was opened in the browser).

`SpecVaultWarnings.tsx` returns `null` when the list is empty. A document that cites nothing and has no conflict yet therefore has no **Check now**, even when a new vault fact contradicts it later; only the next propose checks it.

Seam: Knowledge vault (spec-vault-check x Spec page). Tier guess: 0 (design gap).

## F659 (D) -- a stale "Decided without you" card stays on a task after its cause is gone

**Status:** fixed as decided 2026-10-16 (Tier 0, decision fix-D14, amending D7's "permanent"). Once the task carrying it is approved, the "Decided without you" block collapses to one muted history line on the card and in the drawer ("Earlier, decided without you: ...", full text on hover); before that it stays. Driven with `scripts/drive/d1016_d14_d15_screens.py` (13/13). Not covered: this finding's literal case, a *dependency* (A) approved while the card's own task (B) is still in progress, keeps B's block until B is approved, because the Hub cannot tell which task a question was about without reading its prose. Opened before: open 2026-10-15. Measured in the 2026-10-15 full sweep (G3: Tasks, noted for the Questions row; scratch Hub `:8033`).

B's board card kept the yellow "Decided without you" block, with dev2's timed-out question *"Can you either change Task A's status to 'approved'…"*, after A was approved. It also showed "Stalled".

Seam: Questions (timed-out question) x Tasks (board card). Tier guess: 0.

## F660 (A) -- on Copilot, any Hub-refused tool call ends the turn silently: the run records `completed`, exit 0, no reply, and a task turn leaves its task `in_progress` with no notes

**Status:** fixed 2026-10-16 (Tier 2, decision fix-D3, wpc1-a..c, e, f, h; wpc1-d and wpc1-g built as recommended and still open; change `spec/changes/a-refused-copilot-call-does-not-end-the-turn`, re-authored from the openspec draft of the same name). When the Hub's judge or the operator refuses a root call and Copilot ends the prompt with nothing after it, the Hub sends one follow-up `session/prompt` naming the call and the reason (`copilot.refusal_continued`); a turn that still ends on a refusal writes `copilot.turn_ended_on_refusal` (or `copilot.refusal_continuation_failed`), and a task divergence names the refusal; `run_completed` and the closing status row carry `stop_reason` and `refusal_continuations`. Driven at home with `scripts/drive/d1016_f660_refusal_continues.py` (Copilot 1.0.98, Auto model): 8 failed at 0909d30 (both the judge refusal and the operator Deny ended `Run completed` right after the refused result), ALL PASS after the build; the follow-up cost one more premium request (2.0 vs 1.0) on the same turn row. Opened before: open 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Draft change (openspec, to be re-authored under `spec/`): `openspec/changes/a-refused-copilot-call-does-not-end-the-turn`; decisions `wpc1-a..h` OPEN in `spec-queue/DECISIONS.md` (wpc1-f is KEY).

A parent-level `reject_once` -- decided by the Workspace judge or by an operator Deny -- ends Copilot's prompt at once. Observed 3 of 3: `run-047359204292` (manual Deny of `echo hi`), `run-b175c9ffa621` (judge refused a listing), `run-b1f5b4bedc18` (a **task** turn: the judge refused `Get-ChildItem 'C:\Python*'`; the turn ended mid-work, the task stayed `in_progress` with no notes, nobody was told). A refusal inside a `task` subagent does not end the parent. `permission_answer` (`hub/hub/copilot_acp.py:863`) can only select `reject_once`, which carries no reason; the reason is recorded as `permission_denied` (`decided_by: runtime`) but the agent sees only "The user rejected this tool call." `stopReason` is not logged. Claude's `approve_tool_call` returns the reason and the agent carries on: a parity gap. With F661 an ordinary listing ends the turn.

Seam: Permissions & sandbox x Runs (Copilot ACP). Recommended fix (wpc1-a): one follow-up `session/prompt` in the same session carrying the refusal reason, plus a visible "turn ended on a refusal" diagnostic. Tier 1 (wpc1-f asks for a narrow carve-out from the no-backstop rule, keyed on the Hub's own refusal record, never on prose).

## F661 (B) -- the Workspace judge reads regex and script-block text as paths: a read-only `-notmatch '\\.git\\'` is refused as a UNC root, and `$` inside a single-quoted pattern as an expansion

**Status:** fixed 2026-10-15 (Tier 2, decisions wpc2-a narrowed, wpc2-b, wpc2-g). `_lex` records per argument whether it is one qualifying quoted literal and whether it starts a pipeline element (`_ArgumentShape`); in an expression-mode element the literal right after an unquoted `-match/-notmatch/-like/-notlike/-replace/-split` (c/i variants) is not judged (`_ps_pattern_operands`). Command mode, a later statement or subexpression, an assignment, the left operand, a `-replace 'a','b'` pair, an expanding double quote, Unicode quotes and an unquoted operand are all judged as before (tests). Both recorded commands verbatim are allowed. Change `spec/changes/the-workspace-judge-reads-paths-not-patterns` (Tier 2, with F601/F661 together). Wire acceptance drive `scripts/drive/d1015_judge_wire.py` (the real tool server over stdio, Workspace posture) was committed failing (9 rows wrong) before the build and passes 16/16 after; `hub/tests/test_the_workspace_judge_reads_paths_not_patterns.py` 39 tests, 24 failing on the unfixed judge; the existing judge suites (938) unchanged. Copilot's own call path is not driven at home (work PC). Opened 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Draft change: `openspec/changes/the-workspace-judge-reads-paths-not-patterns` (SECURITY-tagged); decisions `wpc2-a..g` OPEN (wpc2-a KEY). Same judge as F601, opposite failure (F601 lets a write through; this refuses a read).

`Get-ChildItem -Recurse -Force -File | Where-Object { $_.FullName -notmatch '\\.git\\' } | Resolve-Path -Relative` is refused "'\\\\.git\\\\' is outside your workspace"; the `-LiteralPath <worktree>` variant is refused because `'\\.git(\\|$)'` "contains a variable". Both are read-only and inside the worktree; plain `Get-ChildItem -Recurse -File` and `git ls-files` are allowed. Repro: `mcp_server._decide("Bash", {"command": ...}, workspace=..., hub_url=...)`. Combined with F660, the refusal ends a Copilot turn.

Seam: Permissions & sandbox. Recommended (wpc2-a): exempt a quoted literal on the right of `-match/-notmatch/-like/-notlike/-replace` (pattern)/`-split`, PowerShell expression mode only; disqualify Unicode quotes (wpc2-g). Precondition: capture one live payload for the subagent's raw toolName. Tier 2 (sandbox boundary): fix together with F601.

## F662 (B) -- the Copilot model catalog has drifted from the CLI: `claude-haiku-5.5` and `grok-4.7` are refused (400) though the CLI runs them, and four retired models are still offered

**Status:** (2026-10-16, 973aee3: the composer pill now reads "<model> — unrecognised" instead of the default model's name.) fixed 2026-10-16 (Tier 1, decision fix-D5, change `spec/changes/the-copilot-catalog-tracks-the-cli`, re-authored from openspec `the-copilot-catalog-matches-the-cli` items 1, 2 and 4). `CATALOG["copilot"]` is the 30 models of `copilot help config` 1.0.94-3; the pin fixture is `tests/fixtures/copilot/help-config-1.0.94-3.txt`, and the drift script prints the build it compared against. A stored model the catalog dropped keeps working: an override equal to the conversation's stored model is accepted, and `run_worker` runs a stored one with a warning instead of `unknown_model`. A newly chosen one is refused, now including a newly set `checkpoint_model`. Conversations carry `model_unrecognised`; the pill label is in the UI batch. Item 3 of the draft (a substitution reported at session start) was built 2026-10-16 as the successor change `a-substituted-copilot-model-is-reported` (Tier 1, 22bc1e7; acceptance test committed failing first, 58288f6, 4 of 11; folded into `model-catalog`): `run_turn` reads the session's model and effort after agent selection and posts one `copilot.model_substituted` / `copilot.effort_substituted` before the prompt. Grounded on a no-prompt 1.0.91 capture at home (the agent answer carries the `model` option; an Auto-only plan answers a concrete model with `auto`). Not driven with a prompt: the work-PC check (runner on claude-opus-4.7 shows the notice and the meter names claude-sonnet-5) is the operator's. Per-model effort (wpc3-d) and the catalog scenario wording (wpc3-g) stay open. Acceptance drive `scripts/drive/d1016_f662_copilot_catalog.py` committed failing first (dcaef3c: 3 of 3), ALL PASS after. Opened 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Draft change: `openspec/changes/the-copilot-catalog-matches-the-cli` (with probe evidence); decisions `wpc3-a..g` OPEN (wpc3-b, c, f KEY).

`hub/hub/model_catalog.py` `CATALOG["copilot"]` against `copilot help config` 1.0.94-3: missing `claude-haiku-5.5`, `grok-4.7` (a trigger override with `claude-haiku-5.5` gets 400 "not a model 'copilot' declares"); still listed but no longer offered: `claude-opus-4.7`, `gemini-3.6-flash`, `gemini-3.5-flash`, `kimi-k2.7-code`. R3 also found `worker.py:348-349` refuses a stored model that left the catalog as `unknown_model`, which would stop checkpoints, handovers and distillation (wpc3-f).

Seam: Runners & models. Tier 1.

## F663 (C) -- a stale `.agentweave/calls/*.json` collides with the shim prompt's example name `1.json`; the second shim turn's create failed twice and the turn cost 151k tokens instead of ~75k

**Status:** fixed 2026-10-16 (Tier 1, decision fix-D6 / wpc4-a (a2), change `spec/changes/a-call-mode-turn-starts-with-an-empty-calls-directory`, re-authored from openspec `a-call-file-turn-starts-clean-and-can-write-its-file`, archived). `prepare_calls_dir(work_dir, *, empty)`: the trigger empties the calls directory of an isolated workspace (own worktree, task or review checkout) at turn start, links as links, best effort (an entry that cannot go is a warning: wpc4-b's recommendation, built; the row stays the operator's); a shared workspace is not emptied. Both call-mode texts ask for a new file name per call. Reproduced at home first: `scripts/drive/d1016_f663_calls_dir_clean.py` (Haiku in call mode) had turn 2's `Write` refused on turn 1's `create_task.json` ("File has not been read yet"), 2 of 9 failing at 53b447a; ALL PASS after (6fdf5ff). open 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Draft change: `openspec/changes/a-call-file-turn-starts-clean-and-can-write-its-file`; decisions `wpc4-a`, `wpc4-b` OPEN (wpc4-a KEY).

`prepare_calls_dir` (`hub/hub/api/v1/agent_trigger.py:250`) never clears the directory; the agent read and edited the leftover file. Seam: Runs (`aw-tool` call mode). Recommended (wpc4-a): empty the calls dir only in an isolated workspace, and have the prompt ask for a fresh file name. Tier 1.

## F664 (C) -- a Copilot shim spec turn is told to write its args file with the file-writing tool, which spec turns exclude

**Status:** fixed 2026-10-16 with F663 (same change). The failed spec-turn write was Copilot's `create` refusing the leftover, and `create` is kept on spec turns (`copilot_acp.py` SPEC_TURN_EXCLUDED_TOOLS keeps it), so an empty calls directory plus the new-name sentence removes it; `edit` stays excluded (wpc5-a's recommendation; the row stays the operator's). Not driven on Copilot (work PC). open 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Same draft change as F663; decision `wpc5-a` OPEN (recommended: keep `edit` excluded, fix the prompt).

`SPEC_TURN_EXCLUDED_TOOLS` (`copilot_acp.py:142`) removes `edit`, but the shim prompt (`launchability.py` ~460, `agents.py` ~1794) says to write the args file with the file-writing tool. Claude keeps `Write` on shim spec turns (D16); Copilot has no equivalent. One call failed before a `Set-Content` fallback worked. Seam: Agent environment x Spec documents. Tier 1 with F663.

## F665 (C) -- Copilot worker credits are outside project accounting: accounting showed 19 premium requests / 154.00 AIU against true 21 / 155.92, and `preferred_display` is `tokens` for an all-Copilot project

**Status:** fixed 2026-10-16 `f6701ef` (line added 2026-10-30; `9f36af3` closed it without one).

**Live check 2026-10-16** (fix-D16): `scripts/drive/d1016_f665_copilot_worker_credits.py` on a scratch Hub (Copilot 1.0.98) recorded the checkpoint and probe at 49,267,500 and 42,855,000 nano-AIU and 1.0 premium request each, `credited_calls` 1 on both lines, and the project at turns + workers (3.0, 428,540,000); the headline stayed `allowance` because this account reports a chat-allowance reading, which outranks credits by design. It first needed F671's fix: the checkpoint had failed on the runner's model. **Status:** fixed 2026-10-16 (Tier 1, decision fix-D2 slice B, wpc6-a..c; wpc6-d/f built as recommended and still open; change `spec/changes/copilot-spend-is-counted-in-its-own-units`, folded into `usage-accounting`, archived). Worker lines carry Copilot credits and credited calls, the project's credits include them, and `preferred_display` gains a `credits` kind. Checked at the route with the drive's own figures (21.0 / 155,924,675,000); not driven live (a Copilot worker call spends premium requests). Opened before: open 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Draft change: `openspec/changes/copilot-spend-is-counted-in-its-own-units`, gated on `worker-spend-counts-against-the-budget` D7; decisions `wpc6-a..f` OPEN. Copilot face of F240 (worker spend outside every total), re-verified by the 2026-10-15 sweep ($0.52 of checkpoint workers counted nowhere).

The two checkpoint `worker_invocations` rows carry `premium_requests 1.0` and `ai_nano_aiu` ~1.1/0.8 AIU with `input_tokens` NULL; `GET /projects/{pid}/accounting` sums only `turn_usage`. Also `turn_usage.allowance` stored as the string `'null'`. Seam: Accounting & allowance. Tier 1, after F240's decision.

## F666 (C) -- after a Stop, the interrupted shell `tool_use` never gets a `tool_result`, so its timeline card stays "awaiting result" forever

**Status:** fixed 2026-10-16 (Tier 1, decision fix-D6 / wpc7-a (c), wpc7-b (i), wpc7-d (i); wpc7-c built as recommended and still open; change `spec/changes/stop-closes-the-tool-card-it-interrupted`, re-authored from the openspec draft of the same name, folded into `agent-stream-events`, archived). Both executors track open tool calls and, when a run ends stopped or failed, record one `tool_result` per open call (`status: "interrupted"`, `is_error: false`) before the status line; the timeline pairs a result with its call across the whole turn and reads an unanswered call from its run's facts (interrupted / no result / awaiting result). Reproduced at home on Claude Haiku (PTY): `scripts/drive/d1016_f666_stop_closes_card.py` failed 2 checks at 5a9d5c8 (tool_use, then `Run stopped`, no result) and passes after e6d80f2. Not measured: what real Copilot or Codex send after a cancel (openspec tasks 3.2, 3.4; work PC). Opened before: open 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Draft change: `openspec/changes/stop-closes-the-tool-card-it-interrupted`; decisions `wpc7-a..d` OPEN (wpc7-d KEY: pair call and result across the whole turn, since 6 of 50 real results sit in a different work block).

Seen in the stop-race retry. Seam: Runs x Conversations (timeline). Recommended (wpc7-a): the Hub persists a synthetic interrupted `tool_result` and the UI derives the state for history and reconciled runs. Tier 1.

## F668 (B) -- two different agents bound to one task both start in the same task checkout; D8 serialises one agent's turns, not different agents'

**Status:** fixed 2026-10-15 (Tier 0). `agent_trigger`: one lock per `(project, task)` checkout is taken before D8's read of who holds the task and held until the trigger call ends, when a started turn's `Run` row is committed, so a second agent's read waits for it and is refused (transient, so its input waits). `test_two_agents_started_together_on_one_task_do_not_both_start` pauses the first turn between its read and its commit and failed before (both started). Driven with `scripts/drive/d1015_f668_two_agents_one_task.py` (two Haiku agents, two simultaneous `POST /agent/trigger` on one task): before, both answered `running` and two turns ran on the task at once; after, one runs, the other waits naming the holder and starts when it ends (5/5). Opened before: open 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Raised as `wpc4-d` by the F663 change's R2 round from code reading; not driven live. Related to the 2026-10-15 sweep's F603/F606 (reviewer and author on one task). Seam: Worktrees & integration x Tasks. Tier guess: 1.

## F669 (C) -- an explicit `work_dir` can point into another agent's isolated workspace

**Status:** fixed 2026-10-15 (Tier 0). Both work_dir doors (the route and `trigger_agent_directly`) refuse a work_dir that resolves to the project's `.agentweave/` or inside it (case-normalised), naming why. `test_work_dir_cannot_point_into_the_hubs_own_directory` failed before (the run started). Driven: a read-only agent's `.agentweave` and `.agentweave/worktrees/alpha` answer 400; an ordinary directory still starts. Opened before: Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Raised as `wpc4-e` by the F663 change's R3 round; not driven live. Recommended: refuse a `work_dir` under `.agentweave/`. Seam: Worktrees & integration x Permissions & sandbox. Tier guess: 0.

## F670 (C) -- `PATCH /budget` commits before reading totals, so an overflow answers 500 and skips rescheduling

**Status:** fixed 2026-10-15 (Tier 0). Reproduced at home first: 2^63-1 was accepted and 2^63 or more answered 500 (`OverflowError` at the database write); `PUT /settings` had the same hole on `token_budget`. Both doors now refuse past `usage_accounting.MAX_TOKEN_BUDGET` (SQLite's signed 64-bit INTEGER) with 422 before writing. `test_a_budget_the_database_cannot_hold_is_refused_and_nothing_changes` failed before. Driven with `scripts/drive/d1015_s1_tier0.py` on a scratch Hub (Haiku), 10/10. Opened 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Noted as F486-adjacent in the handoff addendum; not driven live. Seam: Accounting & allowance x Inbound queue. Tier guess: 0.

## F671 (B) -- a Copilot worker call fails outright on a model the plan does not offer, while the same runner's turns run on Auto

**Status:** fixed 2026-10-16 (Tier 0). `worker._run_worker_process` retries once without `--model` when the CLI's stderr says exactly `Model "<id>" from --model flag is not available` for the id this call named; any other failure, another id, or a timeout is not retried. Tests in `test_a_copilot_worker_falls_back_to_auto.py` (2 of 5 failed first). Re-driven live: the Copilot checkpoint went `ready` with its probe `passed`, each 1.0 premium request on its worker line. Opened before: open 2026-10-16. Found by the F665 live check (`scripts/drive/d1016_f665_copilot_worker_credits.py`, scratch Hub `:8074`, Copilot CLI 1.0.98, home account).

A Copilot runner on `claude-haiku-5.5`: its ACP turn completed, with `copilot.model_substituted` "Copilot did not run the requested claude-haiku-5.5; it chooses the model itself (Auto); this plan offers only Auto." The operator's checkpoint on the same runner then failed in 3 s: worker row `outcome=nonzero_exit`, `exit_code=1`, `error="exited 1: Error: Model \"claude-haiku-5.5\" from --model flag is not available."`, no tokens and no credits. `copilot -p ... --model <id>` refuses an id the account's plan does not offer, where `session/set_config_option` over ACP falls back to Auto. Every one-shot worker call on such a runner fails the same way: checkpoint, probe, titles, distillation, report reviews, spec checks. It is also why F665 could not be confirmed live: there was no credited worker call to count.

Seam: Runners (Copilot catalog vs plan) x Manager/worker jobs. Recommended: Tier 0, retry once without `--model` on exactly that refusal, as the ACP turn lets Copilot choose (decision fix-D5 wpc3-b: a stored model that left the catalog keeps working).

## F672 (B) -- evidence waiting on the operator stalls a loop, and nothing tells the operator; the controls sit behind a collapsed one-line bar

**Status:** fixed 2026-10-17. Finding the evidence: a task's drawer opens on its story with every piece and its proof (`a-tasks-whole-story-is-in-its-drawer`), and the Spec tab's Evidence view lists every piece, linked from coverage rows, the story, the approval report and job firings (`every-piece-of-evidence-in-one-place`); judged on a Terra replica in a browser. Earlier: stall fixed 2026-10-17 (Tier 2, `the-reviewers-verdict-decides-the-tasks-evidence`, `spdoc-d9f7e6b296f7`; operator decision vis-D1/vis-D4): the reviewer's verdict decides the task's evidence, so nothing waits on the operator, the loop does not stall and the re-run question is moot. `d1017_agentic_evidence.py` 6 FAILED before, ALL PASS after. Finding the evidence is the visibility roadmap's task-story and evidence-browser slices. Earlier: open 2026-10-16. Reported by the operator on `:8000` (project Terra, `proj-cd006955cbe2`, loop `loop-c2e824f58319`), read from its database `mode=ro`: "Very hard to find the evidence. I don't know that I need to review anything."

Builder's task `task-87ce01a67b0c` went to `under_review` with 10 evidence rows `awaiting`; no agent held `can_accept_evidence`. QA2 judged the work right, its `update_task` approve was refused, and it ended its turn in prose without `ask_user` (questions table empty). The next tick (job run `run-606a31a48402`, 14:20) was `skipped` with the reason "Approval of task-87ce01a67b0c ... waits on you: accept or reject the evidence"; that reason was the only record, and the other four tasks stayed `pending`. The operator read the project as stalled. Once told, they could not find where to decide: Accept/Reject exist only in `EvidencePieces`, inside `SpecCoverageBar` (a collapsed single line under the phase bar that reads as a status label), one requirement's evidence open at a time (10 pieces over 9 rows). The task drawer, the loop and the skip reason all say "accept the evidence" and link to none of it. Also worth weighing against "approvals are scarce: warn, don't gate": one task's evidence gate halted the whole queue (not checked whether the other tasks depend on it). After the operator granted QA1/QA2 `can_accept_evidence` (14:48), the loop still did not re-run the reviewer: from 14:35 its skip reason reads "QA2 ... is not reviewing it ... Nothing will move it on its own. Ask QA2 again" (`scheduler._wedged_review_reason`), so the operator granted the right and still had to message the reviewer by hand. Seam: Spec evidence x Loops x Tasks (operator attention). Tier guess: 1.

## F673 (B) -- an evidence piece gives the operator nothing to judge it by

**Status:** fixed 2026-10-17. The screens: each piece opens into its proof (the requirement's wording, command, output, coverage, the diff of the work, every review) in the task story and the Evidence view, and a requirement's story shows how its wording changed (`a-tasks-whole-story-is-in-its-drawer`, `every-piece-of-evidence-in-one-place`, `how-a-requirement-changed-and-what-proved-it`). Earlier: data half fixed 2026-10-17 (Tier 2, `evidence-carries-what-it-takes-to-judge-it`, `spdoc-bb78c9e5f3ef`, vis-D5): evidence carries `command`, an output tail and `covers`; every view carries the requirement's wording and `superseded_by`; `GET /spec/evidence/{id}/diff` returns the work's diff. `d1017_evidence_worth_reading.py` 6 FAILED before, ALL PASS after. The screens are the roadmap's task-story and evidence-browser slices. Earlier: open 2026-10-16. Reported by the operator on `:8000` (same project and task as F672): "seeing the evidence is very bad. I don't know if I can accept those... have no way to judge."

A piece renders as one run-on line: the agent's own summary, actor, locator, commit, task id, `awaiting` (`EvidencePieces.tsx`). Missing are what the operator needs to decide: the requirement's text beside it, what was actually run and its output, the diff at that commit, whether the evidence covers the requirement fully or partly (several Terra rows say "reading side only; create is a later task" in passing), and the reviewing agent's verdict (QA2 had checked all of it, and its notes are on the task, not beside the evidence). A superseded piece (FR-5's `ev-ad7e0dd48ff5`, replaced by `ev-3ec864b816fa`) is not marked as such. Seam: Spec evidence x Reviews. Tier guess: 1.

## F674 (C) -- a roadmap slice's change document can be written, approved, built and archived without ever naming its slice

**Status:** fixed 2026-10-17 (Tier 1, `a-change-can-name-its-roadmap-slice-after-the-fact`, spdoc-2ecc1c4a0ac4, folded into spec-roadmaps; operator vis-D9): `PUT .../documents/{path}/roadmap` sets a change document's roadmap link at any phase, archived included, changing that field alone; the seven slice documents were backfilled on the trial Hub and the roadmap page shows them archived (`scripts/drive/d1017_roadmap_backfill.py`). Earlier: partly fixed 2026-10-17 (Tier 1, same change as F579): proposing or approving a change document that names no slice, while an approved roadmap has unclaimed slices, lists a `roadmap_slice_unclaimed` gap (warn, never gate). Open: whether an archived document may gain its roadmap link afterwards (the change's open question `backfill`, for the operator), which is what the visibility roadmap's seven archived slice documents would need to read as done. Earlier: open 2026-10-17. Found closing the visibility roadmap (interactive, after slice remaining-hidden-data).

All seven change documents that built `evidence-goes-agentic-and-the-project-becomes-visible-roadmap` (`spdoc-d882f76795b3`) carry no `roadmap` link (`SpecPayload.roadmap`, `hub/hub/spec_payload.py:316`): `the-reviewers-verdict-decides-the-tasks-evidence`, `evidence-carries-what-it-takes-to-judge-it`, `a-tasks-whole-story-is-in-its-drawer`, `every-piece-of-evidence-in-one-place`, `how-a-requirement-changed-and-what-proved-it`, `the-activity-tab-becomes-the-projects-ledger`, `the-rest-of-what-the-hub-records-becomes-reachable`. Each was written through `PUT .../content`, proposed, approved with `approve_anyway`, and folded; no step said the project has an approved roadmap whose slices no document claims. Their problem statements name the slice in prose ("Slice X of roadmap spdoc-…"), which nothing reads. So even with F579's fix (derive each slice's state from the change document that names it) this roadmap would read as seven unstarted slices, and the documents are archived, which refuses an edit.

**Fix shape (not decided):** at propose or approve, when the project holds an approved roadmap with a slice no document claims, list it as an approval gap (warn, not gate: approvals are scarce) naming the `roadmap` field; and decide whether an archived document's `roadmap` link may be added afterwards, as a metadata write that changes no requirement. Pairs with F579.

## F675 (A) -- under "Workspace only" an agent can write its runner's allow rules, and its next turn runs past the approver

**Status:** fixed 2026-10-18 (Tier 0). `_decide` refuses a write tool's path, and any shell word, naming `.claude/settings.json`, `.claude/settings.local.json`, `.claude/hooks/`, `.mcp.json`, `.codex/` or `.github/hooks/` at the workspace root (`mcp_server._RUNNER_CONFIG_PATHS`), with a reason that sends the agent to `ask_user`. Reading them with a file tool stays open; `CLAUDE.md`, skills and a nested project's files are ordinary work. `test_an_agent_cannot_write_its_runners_configuration.py` (28 of 36 failed first). Driven with `scripts/drive/d1018_f675_f676_f677_workspace_posture.py` on scratch `:8076` (Haiku, CC 2.1.301): the Write was refused and no settings file exists. Opened 2026-10-18 from research 2026-10-01 §1, which measured it end to end on CC 2.1.280 and 2.1.286: an approver mimicking `_decide` allowed `Write .claude/settings.local.json` with `{"permissions":{"allow":["Bash","PowerShell"]}}` as inside the workspace; on the next `--resume` turn `mkdir <outside>` ran and the approver was never called, because a project or local allow rule runs ahead of `--permission-prompt-tool` (and the Hub launches with `--setting-sources project,local`). Still a text boundary: `cd .claude && echo ... > settings.local.json` is not seen. Seam: Approver posture x Runner configuration.

## F676 (A) -- a pipe can carry a path the shell judge never reads

**Status:** fixed 2026-10-18 (Tier 0). `_decide` refuses a command whose stage takes paths or code from another command's output (`mcp_server._feeds_arguments`): `xargs`/`parallel` anywhere; a shell, `eval`/`source`/`while`, or an interpreter with no script after a pipe; a decoder (`base64 -d`, `xxd -r`) feeding a pipe or a substitution; `pwsh -EncodedCommand`; in PowerShell `Invoke-Expression`/`iex`, `[scriptblock]::Create`, `FromBase64String`, and a path cmdlet fed by a pipe (directly or in a `ForEach-Object` block using `$_`) unless a listing (`Get-ChildItem`) feeds it. Reading stages (`| wc`, `| head`, `| python -m json.tool`) stay allowed. `test_arguments_from_another_commands_output_are_not_allowed_on_their_text.py` (23 of 40 failed first). Driven with the same script: refused, and nothing appeared outside the worktree. Opened 2026-10-18 from research 2026-10-02 §1: `echo Li4vb3V0c2lkZS0xMDAy | base64 -d | xargs touch` was allowed as "inside your workspace" and, run in Git Bash, created `../outside-1002`. The research measured this rule at about 1% of Hub agents' commands (one read-only `find | xargs grep` in 77). Seam: Approver posture x Shell judge.

## F677 (B) -- a Claude run waits for its background command and then takes an unprompted second turn

**Status:** fixed 2026-10-18 (Tier 0). Claude runs get `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` (`ClaudeAdapter.run_env_defaults`, applied in `agent_trigger` with `setdefault`, so an agent's own `env_vars` win). Tests `test_a_claude_run_has_background_tasks_turned_off` (failed first) and `test_an_agents_own_background_tasks_setting_wins`. Driven with the same script: the Bash tool rejected `run_in_background`, the run ended at its reply in 26 s with one Completed, and `sleep 40 && echo done > bg.txt` never ran. Opened 2026-10-18 from research 2026-10-07 §1 (also 09-24/25/26/27, 10-09): on CC 2.1.292 a `-p` run under a PTY waited 44 s for a backgrounded command, then took a second model turn with tools and a second `result`; the run stayed `running` with nothing on the timeline saying why, holding its task checkout. Before 2.1.292 the command was killed 5 s after the reply. Seam: Runs (Claude PTY lifecycle) x Accounting. Also measured 2026-10-18 on CC 2.1.301: without the variable an `Agent` (subagent) call itself runs as a background task -- its result returns at once, then a second `system/init` and a second `result` follow -- and with it the subagent runs in the foreground and the stream ends at one `result`.

## F678 (A) -- a resumed Claude turn records its session's running total as its own cost, and drops subagent tokens

**Status:** fixed 2026-10-18 (Tier 2, `spdoc-7f874f103d5b`, `spec/changes/maroon-dragon/`, folded into usage-accounting). Migration 0132 adds `runs.runner_version` (from `system/init`) and `turn_usage.session_totals` (the reported cumulative cost and tokens); `usage_accounting.settle_claude_session_totals` records a turn on 2.1.277+ as its totals minus the session's previous recorded totals, a pre-2.1.277 turn as its per-process totals, and a session with only pre-change rows with `usage` tokens and no cost, once. Tokens come from `modelUsage`, so subagents count. `hub/tests/test_a_claude_turn_records_its_own_cost.py` 4 FAILED before, all pass. Driven with `scripts/drive/d1018_f678_turn_cost.py` on scratch `:8076` (Haiku, CC 2.1.301; that Hub migrated 0131 to 0132 on restart): turn 2 recorded 1,217 micros where its session total read 2,539. Earlier: open 2026-10-18. From research 2026-09-27 §1, re-measured 2026-10-18 on CC 2.1.301 (Haiku 5.5, `-p` then `-p --resume`): `total_cost_usd` 0.00272 / 0.00303 / 0.00333 and `modelUsage` output 31 / 36 / 41 are session totals, where `usage` reads 31 / 5 / 5; a `--fork-session` turn inherits its parent's totals under a new session id (the Hub never forks). `runner_parsing.py`'s result branch takes `total_cost_usd` as the turn's cost and `usage` as its tokens, so every later turn re-records the session's cost (the research's replay of `:8000`: $1,134 recorded-cumulative against $419 spent), and the token budget misses every subagent call (`usage` omits them; only `modelUsage` has them). `claude_code_version` arrives in `system/init` and is discarded, so per-process (before 2.1.277) and per-session figures cannot be told apart. Seam: Runs (Claude stream) x Accounting & allowance.

## F679 (B) -- a Claude subagent's tool call reaches the operator as the agent's own

**Status:** fixed 2026-10-18 (Tier 1, `spdoc-48a94dbf4a02`, `spec/changes/opal-phoenix/`, folded into agent-run-sandboxing). The Claude parser records a subagent line's `parent_tool_use_id`, `task_description` and `subagent_type` as `payload.subagent` on its tool calls and results; `GET /permission-requests` resolves each request's `subagent` from the run's streamed call when the list is read; the card says "From a subagent: <description>" and the conversation's call row says "subagent: <description>". Acceptance `test_a_subagents_call_reaches_the_operator_as_the_subagents.py` on four real stream lines (2 FAILED first) plus 3 UI tests (failed first). Driven with `scripts/drive/d1018_f679_subagent_request.py` on scratch `:8076` (Haiku, Ask me): the subagent's pending `Write` was listed as `write marker` with its parent call. Opened 2026-10-18 from research 2026-10-01 §2 (Approval Laundering's Delegation class; CC 2.1.285 routes a subagent's request to the prompt tool), re-measured on CC 2.1.301: every subagent line carries `parent_tool_use_id`, `agent_id`, `subagent_type` and `task_description`, and the Hub read none of them. Not done: nesting a subagent's calls under its `Agent` call in the timeline. Seam: Approver (Ask me) x Agent stream events.

<!-- 2026-10-18 full-surface sweep (four parallel groups on master 7c86b0c; scratch Hubs :8031 A agents/runs/posture, :8032 B spec/evidence/corpus, :8033 C tasks/flows/loops/worktrees, :8034 D vault/manager/accounting/UI/resilience; Haiku 4.5/5.5, Copilot via stub). Drive scripts scripts/drive/s1018_{A,B,C,D}_*.py. Ranked by what each cost. -->

## F680 (A) -- with project checks configured, a reviewer can never approve a task whose merge depends on its evidence: "checks are still running" while no check run exists

**Status:** fixed 9ee1227 2026-10-18 (Tier 0): the approval gate now passes the merge targets its own transaction resolved to project_checks.schedule/request_run, so the check run sees the evidence the verdict just accepted instead of finding nothing and starting no run (test_the_reviewers_verdict_decides_the_tasks_evidence::test_approval_with_checks_starts_a_run_on_the_evidence_the_verdict_accepts).

**Found:** open 2026-10-18. Found by the 2026-10-18 sweep, group C (scratch `:8033`, `aw-sweepC-1018`, checks `tests` and `text`). Reproduced twice. rev's `update_task -> approved` on a flow task answered 409 "This task's checks are still running on the work approval would merge. Nothing is wrong yet; approval can be retried when they finish." while `GET /tasks/{id}/checks` read `{"running": false, "runs": []}` and `task_check_runs` held no row for the task. rev retried by `ScheduleWakeup` inside its run: `task-24f78326cf0e` 5 refusals over ~9 min; the README task 16 refusals in ~4 min (`run-b0c417bd0f0c`). Each cleared only when the operator accepted the waiting evidence first. Mechanism (grounded): `requirement_gate._check_checks` (`requirement_gate.py:811-832`) runs inside the PATCH transaction in which F672's verdict has just accepted the evidence, finds no check result and calls `project_checks.schedule`; `request_run` (`project_checks.py:397-430`) opens its own session (`async_session_factory()`), cannot see the uncommitted acceptance, so `merge_targets` is empty and it returns without a run; the 409 rolls the acceptance back, so every retry repeats. Reaches every document flow on a project with checks. Defect; sibling of F613 (same sentence, different cause), seam with `the-reviewers-verdict-decides-the-tasks-evidence`. Seam: Flows & review x Worktrees & integration (project checks). Tier guess: 0-1.

## F681 (B) -- Land approves a task on evidence another, task-less run recorded at main's tip, then skips the merge: the task's own commit never reaches main while its requirement reads verified

**Status:** fixed db2ae99 2026-10-18 (Tier 0): approval (PATCH and Land) refuses with a new gate_unsatisfied category, unlanded, when the task's branch holds commits on neither main nor inside any merge target, naming them and asking for evidence recorded from the task's checkout (worded per for_operator); the review-dispatch "has no recorded evidence" 409 now names its remedy.

**Found:** open 2026-10-18. Sweep group B (`:8032`). The builder recorded FR-1 evidence in a turn bound to no task (`ev-9493...`, footprint `agentweave/builder@efd83ab` = master's tip), then worked the task without recording evidence (commit `29d4830` on `agentweave/task/task-8735ec91be9e`). Dispatching a review was refused 409 "task ... has no recorded evidence, so there is no commit to review" (no remedy named; the app has no review control, F336). The operator accepted the evidence and Landed: 200, approved; `task_integrations` `skipped` "efd83abb1f37 is already in master; there was nothing to merge". README on master lacks the change; FR-1 reads verified. Rejecting `ev-9493...` afterwards left the task approved (task-less evidence reopens nothing). Defect; sibling of F622 (fixed only for tasks with no requirements). Seam: Requirements, evidence & coverage x Worktrees & integration. Tier guess: 1.

## F682 (B) -- a vault source piece longer than ~32k characters fails distillation on Windows: the 50,000-character piece is passed on the command line

**Status:** fixed ab1e849 2026-10-18 (Tier 0): the Claude worker and title prompts go on stdin (OneShotCommand), so a 50,000-character vault piece no longer hits Windows' 32,767-character command line; Codex/Copilot one-shots still pass the prompt as an argument.

**Found:** open 2026-10-18. Sweep group D (`:8034`). `distillation.PIECE_CHARS = vault.PAGE_CHARS = 50_000`; the Claude adapter passes the prompt as `-p <prompt>` (`hub/hub/runner_adapters/claude.py:180`); Windows caps a command line at 32,767 characters. "On-call handbook" (55,262 chars) split into three pieces; the 50k piece failed `FileNotFoundError: [WinError 206] The filename or extension is too long` (`worker_invocations.outcome = spawn_failed`), the other two distilled, so the lost facts are silent (the source still shows facts). Same exposure: `vault_reports.SOURCE_CHARS`, `distillation.COMPARED_CHARS` (both 50k), and any worker prompt past the limit. Defect. Seam: Knowledge vault x Manager jobs (worker argv). Tier guess: 0 (prompt on stdin, as the agent turns already do for long input?).

## F683 (B) -- two projects can share one private vault location, and each then reads the other's private entries

**Status:** fixed 535ad49 2026-10-18 (Tier 0): PUT /vault/settings answers 400 naming the other project for a private location equal to, inside or holding another project's location (chosen or default), including a reset to a default another project holds.

**Found:** open 2026-10-18. Sweep group D. `PUT /vault/settings` answered 200 for P1 pointed at P2's default private folder (`~/.agentweave/hub/vaults/proj-3c1db4d37322`) and for P1 and P2 both at `C:\Users\huida\Documents\sweepD private vault ü`. P2's vault map then listed P1's private source `src-399b9bd5a7f5` "Escalation contacts" (holder TITAN, "support line is 555-0142"). The Hub already knows the hazard: `vault.remove_private_entries` (`hub/hub/vault.py:262`) refuses delete on a shared location because "private files carry no project id"; only the settings route lets the sharing happen. Defect; F610 covered other projects' directories and git work trees, not another project's private location. Seam: Knowledge vault (privacy). Tier guess: 0.

## F684 (B) -- re-distilling the winning side of a resolved contradiction mints a new fact id, so the fact the resolution says "stands" is gone

**Status:** fixed f34c388 2026-10-18 (Tier 1, amends knowledge-vault distil-route / same-lines-same-id): after the exact citation match, a leftover re-distilled draft claims an unclaimed earlier fact with the same visibility and the same (source, line span) citations, each claimed once, so a re-quoted standing fact keeps its id and its resolution; acceptance test committed xfail first (9326a2e), drive on :8056 showed master re-minting and the build keeping the id.

**Found:** open 2026-10-18. Sweep group D. First pass quoted "the public API rate limit is 100 ..."; the re-distil quoted "Decision: the public API rate limit is ..." on the same line 3. `citation_key` includes `loose_quote(quote)`, so `fct-fb32e8f38742` was deleted and `fct-d628e12bc1c8` created, unlinked from the decision. `ctr-ea180246ee9c` side reads `{"id":"fct-fb32e8f38742","claim":null,"missing":true}`; the Vault card "A fact no longer in the vault ... Resolved: one fact stands"; the spec warning "the fact that stands is fct-fb32e8f38742, which is no longer in the vault". The loser kept its id (quote matched). F587/F617 hold only while the model quotes identically. Defect. Seam: Knowledge vault (distil x contradictions x spec warnings). Tier guess: 1.

## F685 (B) -- opening a folder that contains existing projects is accepted, and every later project under it is then refused as nested

**Status:** fixed 5daee14 2026-10-18 (Tier 0): `_refuse_inside_another_project` also refuses a folder that contains a registered project (`project_nested`, naming it). The parent's leftover marker on delete is unchanged by design (delete never touches the folder).

**Found:** open 2026-10-18. Sweep group A (`:8031`). `POST /projects/open {"path":"C:\\Users\\huida\\Documents"}` -> 200 (`proj-347524cd72f9`), writing `~/Documents/.agentweave/project.json`, though `aw-sweepA-1018` lives inside it; opening `~/Documents/aw sweepA ü 1018` then got 409 `project_nested` "...is inside the directory of project Documents". `project_lifecycle._refuse_inside_another_project` checks only that the new path is under an existing project, never the reverse (F646's other direction). Deleting the parent leaves its marker on disk. (Harness: `e2e.py clean` on such a project would have removed `~/Documents`; guarded 2026-10-18.) Defect. Seam: Projects (workspace binding). Tier guess: 0.

## F686 (B) -- project instructions take any size and are prepended to every agent turn

**Status:** fixed 4fa0ed3 2026-10-18 (Tier 0): instructions over 40,000 characters are refused 422 with both sizes, and the Instructions page shows the size against the limit and disables Save over it.

**Found:** open 2026-10-18. Sweep group A. `PUT /project/instructions` with 300,000 characters -> 200; every later turn carried them (a 330,231-char system block in the transcript). Haiku 4.5 first turns read ~70k input tokens (vs ~33k after reset); one Haiku 5.5 "is 391 prime" turn wrote 315,416 cache tokens, 316,982 micros (~$0.32). The Instructions page shows no size or warning. Design gap. Seam: Projects x Accounting & allowance. Tier guess: 0 (a limit, or a size warning on screen).

## F687 (B) -- an operator trigger binds an agent to another agent's task, and that run then completes the task while it stays assigned to the other agent

**Status:** fixed c978b9b + 3e162d0 2026-10-18 (Tier 0): starting an agent on a task assigned to another agent is a 409 naming the holder; a task_id start on an under_review task is a 409 pointing at review_task_id, except for the task's author (recorded completer, else in_progress/completed edges or evidence recorders).

**Found:** open 2026-10-18. Sweep groups A and C. `task-94234b3b55c8` (assignee `board`) + `POST /agent/trigger {"agent":"alpha","task_id":...}` -> 200; `task_transitions`: alpha moved it `pending->in_progress` (origin runtime) then `->completed` (origin actor), editing `calc`; the task ends completed with assignee `board`, which the board credits. `run_task_binding` keeps an existing assignee and the completion gate lets the bound run through; no warning at trigger. Group C saw the same with `task_id` on an under-review task (the reviewer ran in the author's checkout, which led to F693). The checklist says a run claims only an unassigned task or its own agent's. Defect or design gap (refuse with a sentence, or reassign visibly). Seam: Runs x Tasks. Tier guess: 0.

## F688 (B) -- the Ask-me card's verdict says "Outside this agent's workspace" for refusals that are not about the workspace

**Status:** fixed 6b66c0c 2026-10-18 (Tier 0): the Ask-me verdict no longer prefixes every refusal with "Outside this agent's workspace"; the reason says why.

**Found:** open 2026-10-18. Sweep group A, rendered in Chromium (`permission-verdict-*`): "Outside this agent's workspace -- Workspace only would refuse this: '...\worktrees\alpha\.claude\settings.local.json' configures your runner...". `PermissionRequestCard.tsx:146-147` prefixes every refusal with "Outside...", so F675 (runner config), F676 (pipe-fed) and variable/`~` refusals all read as outside-the-workspace. Defect (legibility). Seam: Permissions & sandbox x F675/F676. Tier guess: 0.

## F689 (B) -- an adopted spec.json whose payload fails validation is accepted (201), indexes nothing, and its page loads forever

**Status:** fixed b6425bf 2026-10-18 (Tier 0): adoption refuses a payload the schema refuses (422 payload_invalid, naming the field, e.g. requirements[1].key) and the sweep reports it skipped; a rebuild now says why a document's requirements were not indexed (f8fbe25).

**Found:** open 2026-10-18. Sweep group B. Hand-placed `spec/changes/hand-written-fmt/spec.json` with one requirement lacking `key`: Adopt -> 201 `"requirements": null, "minted": []`, no `spec_requirements` row (not even the valid `fmt1`); Reindex reports the path `null` with no diagnostic; the Spec page shows its skeleton after 15 s, with two 422s in the console from `GET /project/spec?path=...` ("holds no readable spec payload") that never reach the screen. Only rigor/propose name the cause ("requirements[1].key: Field required"). `spec_index.requirements_from_payload` returns `None` on `PayloadError`; adopt never validates. Defect; variant of F612 (fixed for a valid payload without identity). Seam: Corpus & folding x Spec documents. Tier guess: 0.

## F690 (B) -- after a fold, drift on the folded requirement's evidence shows only on the archived change, while the capability reads verified with nothing to answer

**Status:** fixed 833e72a 2026-10-18 (Tier 0): drift is carried across a fold as verification was (F593): a served capability requirement reads drifting, and its drift list shows the change's candidate with serves FR-n.

**Found:** open 2026-10-18. Sweep group B. Folded `scarlet-minotaur` into `interval-arithmetic`, then edited the watched `tests/test_core.py`; Scan raised `drift-cd814faeb6c1` on the archived change's FR-2. The capability's FR-4 (served by it) reads "Verified - Accepted evidence for the current wording" and "Drifting: nothing to answer"; the archived change reads "Drifting: 1 to answer". F593 carried verification across the fold, not drift. Design gap. Seam: Drift x Corpus & folding. Tier guess: 1.

## F691 (B) -- evidence for a reworded requirement still reads "accepted" in the requirement story and the evidence browser

**Status:** fixed e9c86e5 2026-10-18 (Tier 0): evidence views carry for_current_wording; the requirement story and evidence browser count earlier-wording pieces apart instead of as accepted.

**Found:** open 2026-10-18. Sweep group B. FR-1 reworded after `ev-031...` was accepted: the coverage bar says "Stale -- reworded after its evidence was accepted", but the requirement story shows "Evidence - 1 accepted" (green) under the new wording and the evidence browser counts it in "Accepted 3". Neither `components/evidence/*.tsx` nor `components/spec/RequirementStory.tsx` compares digests (grep stale/digest: nothing). Group C saw the converse: the drawer's "Serves FR-1" still reads "Rejected: <old reason>" after the piece was superseded. Defect. Seam: Requirements, evidence & coverage (screens built 10-17). Tier guess: 0.

## F692 (B) -- a decided piece of evidence has no control to reverse it, and a granted agent overturns a rejection silently

**Status:** fixed bffb71a 2026-10-18 (Tier 1): agents decide only awaiting evidence (409 already_decided); the operator overturns a decided piece with a required reason via the Overturn control and POST .../spec/evidence/{id}/overturn; earlier-wording evidence is never accepted (409 evidence_stale); acceptance tests xfail-first at cb65db9.

**Found:** open 2026-10-18. Sweep group B. `EvidencePieces.tsx` offers Accept/Reject only while `awaiting`; F672's "the operator rejecting an accepted piece of an approved task reopens it" works by API (`task-67fd...` approved -> revision_needed) with no screen. The granted tester called `decide_evidence(ev-da84..., accepted, "probe overturn")` on a piece its own review had rejected (an empty commit, stale digest): answer `{"id","review_state":"accepted"}`, no overturn note, no stale-digest refusal. Design gap. Seam: Requirements, evidence & coverage. Tier guess: 1.

## F693 (B) -- an agent that approves a task from inside its checkout leaves an empty directory that refuses the task's next turn

**Status:** fixed b6595bb 2026-10-18 (Tier 0): task, agent and review checkout provisioning now removes an empty, unregistered leftover directory (the one a release from inside a held cwd leaves on Windows) instead of refusing the turn; non-empty directories, links and registered worktrees still refuse (test_a_blocked_workspace_refusal_states_its_remedy::test_an_empty_*).

**Found:** open 2026-10-18. Sweep group C. Operator triggered rev with `task_id` on an under_review task (see F687); rev ran inside `.agentweave/tasks/<task>` and approved; the integration merged, but `git worktree remove --force ...task-31419f3604b8 failed (255): ... Permission denied` (`task_worktree_release_failed`); git deregistered the worktree, the empty directory stayed. After a reopen the author's trigger queued with "refusing existing path ...: it is not the registered git worktree ... Move or delete that directory (`rm -r ...`)". Only a filesystem action clears it; nothing retries the release. Flow reviews (`.agentweave/reviews/<agent>`) released cleanly, as did 7 other releases. Defect on Windows (the run's cwd holds the folder). Seam: Worktrees & integration x Dependencies (reopen). Tier guess: 0.

## F694 (B) -- the planner's same-file warning never reaches the operator, so same-file tasks run in parallel and collide

**Status:** fixed c70fe5d 2026-10-18 (Tier 0): PUT content (and every SaveResult route) returns warnings, and unordered_file_overlap is now a propose/approval gap the operator sees and can approve over.

**Found:** open 2026-10-18. Sweep group C. Tasks `t-cv` and `t-trunc` both declare `mathkit/registry.py` in `files`, no `depends_on`. `PUT /project/documents/{path}/content` answers with no `warnings` key: the route builds its response by hand (`spec.py` ~832) and drops `SaveResult.warnings` (`spec_service.py:352-360`), which carries `overlap_warnings`; propose's warnings and approve's `approval_warnings` carry no `unordered_file_overlap` either. The two ran in parallel, conflicted in `registry.py`, rev sent `t-cv` back: one extra author and one extra review turn. Defect. Seam: Dependencies x Spec documents (`same-file-tasks-run-in-order` roadmap). Tier guess: 0.

## F695 (B) -- a conflicting prerequisite refuses the author's turns, so only the operator, in a terminal, can resolve it

**Status:** fixed 6d7ba49 + 0e1c0f5 2026-10-18 (Tier 1): a conflicting approved prerequisite is abandoned clean and the author's turn starts with a prompt note to run git merge --no-ff <sha> (naming the prerequisite task, commit and conflicting paths), via ResolvedWorkspace.notes from resolve_turn_workspace; the approval gate refuses (new unmerged_prerequisites category) naming the task and commit until the branch contains it; an unfinished conflicted merge is never auto-snapshotted and the next turn is told which paths are still conflicted; a dirty checkout is snapshotted before the catch-up instead of refused; acceptance test test_a_conflicting_prerequisite_is_the_authors_to_merge (xfail-first 9b4be5c).

**Found:** open 2026-10-18. Sweep group C. Beta's turn refused: "approved work of task-31419f3604b8 ... conflicts with work already on task-436c2082fb8c's branch ... Reconcile it there with `git -C ... merge --no-ff ...`; this task's turns are refused until it is in." The gate's own sentence calls resolving it the author's work, but the author gets no turn to do it; the operator merged by hand, then Continue worked. A conflict with main (no prerequisite) was resolved by beta itself in its turn. Design gap in F158's remedy. Seam: Dependencies x Worktrees & integration. Tier guess: 1.

## F696 (C) -- "Workspace only" refuses ordinary read-only commands: sed/awk scripts read as paths, every `| while read` loop, `echo $PWD`

**Status:** fixed d0a27d4 + 570e93d 2026-10-18 (Tier 0): sed/awk/cut/tr scripts and delimiters are no longer read as paths (a sed/awk script only when provably read-only) and a printing '| while read' loop passes F676; grep's pattern is text (-f/--file and file operands still judged; rows 1.5a2/1.7c1 flipped, 1.5a2b/1.7c1b added) and a bare whole-argument $PWD is judged as '.', while $PWD/.., $(dirname $PWD), (Split-Path $PWD), x=$PWD and any reassigned PWD stay refused.

**Found:** open 2026-10-18. Sweep group A. In real turns: `pwd | sed 's/^/PWD=/'` refused "'/' is outside your workspace" (`run-99e650f426ce`); `cat README.md | while read l; do echo "$l"; done` refused by F676 "at 'while read l'"; `echo $PWD` refused "contains a variable...". In-process `_decide`: `sed 's|/usr|x|' a.txt` and `awk -F/ '{print $1}' a.txt` refused alike. `git status --short | sed ...` ran only because Claude's own read-only rule passed it first. F661 fixed PowerShell `-match` operands only; this is the bash counterpart plus a new F676 false positive. Defect (cost: turns spent rephrasing). Seam: Permissions & sandbox (shell judge). Tier guess: 0.

## F697 (C) -- a stopped Claude turn's spend is recorded nowhere

**Status:** fixed 898a87d 2026-10-18 (Tier 1, migration 0134): a stopped Claude turn's unavailable row records its interrupted call as estimated_input_tokens (the turn's last context reading); Budgets shows it as "≈N input tokens, not measured — not counted against the budget", and it counts toward no measured total or budget; acceptance test xfail-first at eb1f366.

**Found:** open 2026-10-18. Sweep group A. `run-02af114595bf` stopped mid-Bash: `turn_usage` `unavailable`, null cost. The next turn `run-7f0a832b742f` recorded 17,173 micros = exactly its own one call; session totals 316,982 -> 334,155. The CLI's totals never included the interrupted call (~333k cached tokens), so it is in no row and no difference. Accounting admits "unavailable turns" but never sizes them: about one model call lost per Stop. Confirms handoff 0202's untested crash path (F678). Design gap. Seam: Runs x Accounting & allowance. Tier guess: 1.

## F698 (C) -- Copilot conversation rows show `Edit {` / `Shell {` instead of the path or command, and an F675 refusal's reason is not on the card

**Status:** fixed 1f35809 2026-10-18 (Tier 0): Copilot rows show rawInput's path/command (else locations, else title), and the refusal-continued card quotes the refusal's reason.

**Found:** open 2026-10-18. Sweep group A, real Copilot CLI 1.0.91 over ACP with the model replaced by `s1018_A_copilot_stub.py`. For Copilot `agent_outputs.payload.input` is a JSON string (`"{\"changes\":...,\"rawInput\":{\"path\":\".mcp.json\"...}}"`) and the row prints its first character. Same run: the F675 diagnostic card says only "the Hub told it why"; the reason (`.mcp.json` configures your runner) is in `permission_denied` but not on screen (the F676 card does show its reason). Defect. Seam: Conversations & composer x Copilot. Tier guess: 0.

## F699 (C) -- a tester's `add_criterion` amendment never reaches the task it was written for

**Status:** fixed eda00fb 2026-10-18 (Tier 0): every tester amendment re-materialises the document, refreshing open tasks' acceptance_criteria.

**Found:** open 2026-10-18. Sweep group B. After `amd-3541...` added `c2-touching`, `GET /tasks/task-26c0...` still listed only `["c2: ..."]`. Defect. Seam: Spec documents (amendments) x Tasks. Tier guess: 0.

## F700 (C) -- after `report_cannot_satisfy`, the operator's only response is "mark reviewed", which changes nothing

**Status:** fixed c730d0a 2026-10-18 (Tier 1): the operator answers a cannot_satisfy report with amend (criterion changed, task unblocked), accept (task unblocked) or reject (reason sent to the reporter, task stays blocked) via POST .../amendments/{id}/respond and the panel; Mark reviewed no longer answers a report; acceptance tests xfail-first at 0a05217.

**Found:** open 2026-10-18. Sweep group B. `amd-06eb...` blocked `task-26c0...`; marking it reviewed left c2 unchanged in the file and the task `blocked`, with no pointer between the two. Design gap. Seam: Spec documents x Tasks. Tier guess: 1.

## F701 (C) -- the gate refusal at sketch rigor offers "lower the document's rigor", which cannot work

**Status:** fixed 4106610 2026-10-18 (Tier 0): the gate refusal offers "lower the document's rigor" only when a gate-enforced entry could be relieved by it; an all-rejected refusal says a rejection blocks at every rigor (test_requirement_gate::test_a_sketch_refuses_a_rejected_requirement).

**Found:** open 2026-10-18. Sweep group B. FR-2 rejected at `sketch`; Land 409 `gate_unsatisfied` "...requirements a gate is enforcing... Satisfy them, or lower the document's rigor" (`requirement_gate.py:204-206`). Sketch is the lowest rigor and a rejection blocks at every rigor. Defect (legibility). Seam: Requirements, evidence & coverage. Tier guess: 0.

## F702 (C) -- the corpus strip still promises fixes that cannot happen and prints codes (F643 remainder)

**Status:** fixed f8fbe25 2026-10-18 (Tier 0): the corpus strip and rebuild speak in sentences (untracked -> adopt first, home codes, unreadable requirements naming the field, skip reasons), an unknown home is refused 422 home_unknown, and Adopt all no longer offers refused documents.

**Found:** open 2026-10-18. Sweep group B. "spec/areas/noid/spec.json is not in the index yet. Rebuilding the index files it." after Rebuild reported it unindexable; "Adopt all 2" still offered after Adopt all answered "skipped 2"; "Skipped ...hand-written-fmt...: no_readable_payload" raw; "Unindexable document: X." with no reason; a homeless rebuild says "Home ambiguous: the index." / "Index home required: the index."; a rebuild naming an unknown home path is not refused. Defect. Seam: Corpus & folding. Tier guess: 0.

## F703 (C) -- a document write calls warn-only gaps `blocking`

**Status:** fixed 5486070 2026-10-18 (Tier 0): a document write splits findings with spec_completeness.split as propose does: refusals in blocking, gaps in warnings, so write and propose agree.

**Found:** open 2026-10-18. Sweep group B. `PUT .../content` and `POST /documents` return `blocking: [unresolved_question, delivery_unanswered, ...]`; propose then answers `blocking: []` with the same codes under `warnings`. `SaveResult.blocking` is every completeness finding (`spec_service.py:343`); F632 fixed only the schema text, so agents reading the answer are still told these block. Defect. Seam: Spec documents. Tier guess: 0.

## F704 (C) -- once an approved roadmap has an unclaimed slice, every unrelated change needs "Approve anyway"

**Status:** fixed 4765e0a 2026-10-18 (Tier 0): roadmap_slice_unclaimed is a non-gating note (proposal warnings; approval_notes on approval, no Approve anyway needed).

**Found:** open 2026-10-18. Sweep group B. An agent-written change and a large catalogue document both got 409 `roadmap_slice_unclaimed` ("has slices no document names: printing"); there is no way to say "this change is not a slice". Design gap against "warn, don't gate" (F674's gap). Seam: Spec documents (roadmaps). Tier guess: 1.

## F705 (C) -- a slice link can be backfilled to an unapproved roadmap, and it then blocks re-proposing the change

**Status:** fixed effebce 2026-10-18 (Tier 0): a slice link is backfilled only to an approved roadmap (propose's rule, roadmap_not_approved), and a differing link is named in words, not a dict repr.

**Found:** open 2026-10-18. Sweep group B. `PUT .../roadmap` naming a proposed roadmap -> 200 `changed: true`; after a reopen, propose refused `roadmap_not_approved` until the roadmap was approved. Asking for a different slice is refused with a Python dict repr ("already names {'document': ...}"). Defect. Seam: Spec documents (roadmaps, F674 backfill). Tier guess: 0.

## F706 (C) -- evidence that says `covers: partial` alone makes a requirement Verified

**Status:** fixed 0fdd11f 2026-10-18 (Tier 1): a requirement whose accepted current evidence is all covers: partial reads in_progress with reason "partial evidence only" (full or absent covers still verify), so a gate document refuses approval until a full piece is accepted; acceptance test xfail-first at cfab18b.

**Found:** open 2026-10-18. Sweep group B. FR-2 and the capability's FR-4 read verified though the only accepted current piece said `covers: partial`; `covers` is displayed, never weighed. Design gap (F673 data). Seam: Requirements, evidence & coverage. Tier guess: 1.

## F707 (C) -- a metadata-only proposal is labelled as a Summary/problem/scope change and shows no diff

**Status:** fixed 8ed7aa7 2026-10-18 (Tier 0): a metadata proposal is labelled by the fields it actually changes and shows each before -> after (lifecycle: "one-off" -> (empty)).

**Found:** open 2026-10-18. Sweep group B. `spprop-cf64...` only clears `lifecycle` (`'one-off' -> ''`), but the panel says "modify Summary / problem / scope" with no diff. Defect. Seam: Spec documents (proposals). Tier guess: 0.

## F708 (C) -- sending back an operator-completed task leaves the reviewer holding it

**Status:** fixed e9e4ffc 2026-10-18 (Tier 0): with no recorded completer, revision_needed returns the task to the agent named by evidence or the in_progress/completed edges, and never leaves the reviewer who sent it back holding it.

**Found:** open 2026-10-18. Sweep group B. The tester sent back `task-26c0...`, which the operator had moved to completed: it ended `revision_needed` with assignee `tester`, the agent that must not write the fix. When the builder completed it, the same send-back returned it to `builder`. Defect. Seam: Tasks x Flows & review. Tier guess: 0.

## F709 (C) -- an agent can overwrite the notes of another agent's task, and notes become evidence verdict text

**Status:** fixed 618f27e 2026-10-18 (Tier 0): an agent may write a task's notes only as its assignee, from a run bound to it, or alongside a real status move; otherwise 403 before any write.

**Found:** open 2026-10-18. Sweep group C. alpha's run (bound to its task A) called `update_task` with notes only on beta's `task-436c2082fb8c`: 200, `notes: "Attempting to set description to hijacked"`, `updated_by_run_id: run-d2ca91a5a825`. `_guard_run_holds_the_task` checks only moves to in_progress/completed; the operator-only field check covers assignee/priority/description, not notes; notes feed `_verdict_text`. Defect or design gap. Seam: Tasks (actor boundaries). Tier guess: 0.

## F710 (C) -- `POST /tasks` accepts an empty title that rename refuses

**Status:** fixed 2fba73b 2026-10-18 (Tier 0): both task-creation doors refuse a blank title with rename's 422, through one shared check_task_title.

**Found:** open 2026-10-18. Sweep group C. `{"title": ""}` -> 201, untitled card; `PATCH {"title": "   "}` -> 422 "A task's title cannot be blank." `TaskCreate.title` has no validator (`schemas/tasks.py:62` vs `:210`). Defect. Seam: Tasks. Tier guess: 0.

## F711 (C) -- the task story leaves out refused turns, a failed checkout release and an operator's manual merge

**Status:** fixed 959a3c4 2026-10-18 (Tier 0): the story now shows refused/abandoned/withdrawn turns and failed checkout releases; a hand merge in a terminal leaves no Hub record and stays out.

**Found:** open 2026-10-18. Sweep group C. `/story` for A and B has no event for two refused deliveries ("Could not prepare the checkout ..."), `task_worktree_release_failed`, or the manual merge: ~13 minutes of a jammed task invisible in its "whole story" (1143a0f). Design gap. Seam: Tasks (story) x Worktrees. Tier guess: 0.

## F712 (C) -- a flow firing whose staged review is withdrawn stays `in_progress` forever

**Status:** fixed 8e9faec 2026-10-18 (Tier 0): withdrawing a flow's staged review on a verdict closes the firing waiting for it (stopped, with a reason).

**Found:** open 2026-10-18. Sweep group C. JobRun `run-55e1d5b4f085` staged rev's review of `t-trunc`; landing `t-trunc` withdrew the queued review; the JobRun was still `in_progress` after the loop completed and its job was archived; the Loop tab lists it with no state. Defect; a new path to open F442. Seam: Jobs & loops x Flows & review. Tier guess: 0.

## F713 (C) -- a loop stops on a blank reason, and a real reason is then refused

**Status:** fixed 8d0a355 2026-10-18 (Tier 0): a blank stop_reason is a 422 before any write, so the real reason sent next is still the first stop.

**Found:** open 2026-10-18. Sweep group C. `PATCH {"stop_reason": "  "}` -> 200, loop `stopped`; the next PATCH with a real reason -> 409. Defect. Seam: Jobs & loops. Tier guess: 0.

## F714 (C) -- an ended loop's collapsed job card reads "Paused" and offers Resume

**Status:** fixed 2f1feb5 2026-10-18 (Tier 0): the collapsed job card reads Complete/Stopped for an ended loop with no Resume, and the card and loop tab both read Stopping past stop_at.

**Found:** open 2026-10-18. Sweep group C. The completed flow's card shows a "Paused" chip with Run and Resume; Resume (`enabled: true`) -> 409 `loop_ended`; only the expanded card says "Stopped: loop queue is empty". For a loop past `stop_at` the Jobs card says "Stopping" while the side panel says "idle". Defect. Seam: Jobs & loops (UI, 3c9dd5c). Tier guess: 0.

## F715 (C) -- the integration preview says "merges cleanly" when approval will skip the merge for a dirty checkout

**Status:** fixed 9bf91eb 2026-10-18 (Tier 0): the preview asks integrate()'s own checkout preconditions (task_integration.checkout_obstacle) and names a dirty or off-branch checkout instead of "merges cleanly"; a repeat retry no longer appends an identical "already in" row (test_the_preview_asks_the_merge_question, test_task_integration_retry).

**Found:** open 2026-10-18. Sweep group C. With an uncommitted edit in the project checkout the preview says "merges cleanly as of now"; approval 200 approved, integration `skipped` ("uncommitted changes to tracked files"); Retry worked once clean. Also: Retry on an already-merged task appends a new `skipped` row per press. Defect. Seam: Worktrees & integration. Tier guess: 0.

## F716 (C) -- Checkpoint now on an already-handed-over conversation still makes a paid checkpoint

**Status:** fixed cb7a934 2026-10-18 (Tier 0): Checkpoint now on an already-handed-over conversation is refused 409 naming the successor, before the worker call.

**Found:** open 2026-10-18. Sweep group C. After cutover, `POST /conversations/{old}/checkpoint` -> 201 `ckpt-39bcd7b2614f` (a worker call); its own cutover is then refused "already handed over". Defect (spend). Seam: Checkpoints. Tier guess: 0.

## F717 (C) -- a private vault location on a missing drive is accepted, then every private add is a bare 500

**Status:** fixed 535ad49 2026-10-18 (Tier 0): a private location on a drive or share that is not there is refused 400 when chosen, and a private add after it disappears answers 409 naming it instead of a bare 500.

**Found:** open 2026-10-18. Sweep group D. `PUT /vault/settings {"private_location":"Q:\\nowhere\\vault"}` -> 200; `POST /vault/sources {visibility: private}` -> 500 "Internal Server Error", log `FileNotFoundError: [WinError 3] ... 'Q:\\'`. A path that is a file, or under one, is refused 400. Defect. Seam: Knowledge vault x Resilience. Tier guess: 0.

## F718 (C) -- clicking the Activity tab always opens the "Activity" view; the Ledger never leads

**Status:** fixed 9e32ea8 2026-10-18 (Tier 0): the Activity tab's onSelect resets to `ledger`, so a click on Activity opens the Ledger.

**Found:** open 2026-10-18. Sweep group D. 1ffaf49 made `ledger` the initial state (`hub/ui/src/App.tsx:108`), but the tab's onSelect still runs `if (tab === 'activity') setActivitySubview('activity')` (`App.tsx:587`). A fresh browser clicking `project-tab-activity` lands on Activity. Defect. Seam: Logs, events & SSE (Activity ledger). Tier guess: 0.

## F719 (C) -- Manager firing rows never say what they fired on

**Status:** fixed da76102 2026-10-18 (Tier 0): Manager activity rows say what each firing worked on (source by name and id, document, report and entry, conversation).

**Found:** open 2026-10-18. Sweep group D. `ManagerPanel.tsx:240` renders only `subject.conversation_id`; 23 firings on screen named no source, report or document; identical "1 fact stored" rows cannot be told apart. The route returns `subject`. Design gap. Seam: Manager jobs. Tier guess: 0.

## F720 (C) -- the vault entry detail tells the operator to enable a job that is already enabled

**Status:** fixed 535ad49 2026-10-18 (Tier 0): an unread image/PDF's entry note names what is actually in the way (job off, no runner, non-reading runner, or the last reading firing's failure such as the spent budget) instead of always saying to enable the job.

**Found:** open 2026-10-18. Sweep group D. Job on with a Claude runner, budget spent: the image entry said "enable the job with a Claude runner on the Manager page, then distil the source" (static text near `vault.py:744`); the firing said token budget exhausted. Defect. Seam: Knowledge vault x Accounting. Tier guess: 0.

## F721 (C) -- at a spent budget a conversation-title job leaves no firing, while vault jobs record a failed one

**Status:** fixed 535ad49 2026-10-18 (Tier 0): a conversation-title call paused by a spent budget records a failed manager firing naming the budget, as the vault jobs do.

**Found:** open 2026-10-18. Sweep group D. `conversation_titles.py:286-288` returns before `record_firing`; only a `worker_invocations` row (`budget_exhausted`) exists. Manager Activity shows nothing; Budgets says "Conversation titles: Unavailable" though nothing ran. Defect. Seam: Manager jobs x Accounting. Tier guess: 0.

## F722 (C) -- the Overview budget card omits the Hub's workers, so its lines do not sum to its total

**Status:** fixed 1c75a3c 2026-10-18 (Tier 0): the Overview budget card lists a "Hub workers" row, so its lines sum to the project total.

**Found:** open 2026-10-18. Sweep group D. Total 710,206; alpha 575,030 + beta 32,227 = 607,257. Environment -> Budgets lists the workers. Design gap left by F240. Seam: Accounting & allowance. Tier guess: 0.

## F723 (C) -- `agentweave doctor --profile X` without `--port` is not refused and examines :8000

**Status:** fixed 5e3f4d3 2026-10-18 (Tier 0): `doctor --profile X` without `--port` is refused by the same rule status/stop/start apply, instead of probing :8000; `--no-network` help now states it only exists for compatibility.

**Found:** open 2026-10-18. Sweep group D. `src/agentweave/cli.py:170` defaults the port to 8000 and skips the named-profile port rule that status/stop/start apply (F649/F650); it reported "[OK] port:8000 ... running and answering" beside the sweepdcli database; `--no-network` did not stop the local probe. (The probe was a read-only liveness check on the operator's instance.) Defect. Seam: CLI & lifecycle. Tier guess: 0.

## F724 (C) -- `agentweave stop` leaves the desktop window that start opened

**Status:** fixed 5e3f4d3 2026-10-18 (Tier 0): app windows register a per-port marker and close when `stop`/`reset` removes it, so stopping the Hub closes the window start opened.

**Found:** open 2026-10-18. Sweep group D. start opened a pywebview "AgentWeave" window (pid 25200); after `stop` printed "[OK] Hub stopped" the window was alive 20 s later against a dead Hub. Defect or design gap. Seam: CLI & lifecycle. Tier guess: 0.

## F725 (D) -- a Copilot provider runner gets three different model labels

**Status:** fixed 8f3f76e 2026-10-18 (Tier 0): the runner select labels a provider runner's model from the claude catalog, agreeing with model_unrecognised and the composer pill.

**Found:** open 2026-10-18. Sweep group A. Settings runner select: "copilot-stub -- claude-haiku-4-5-20251001 (unrecognised) (copilot)"; API `model_unrecognised: false`; composer pill "Haiku 4.5". Seam: Runners & models.

## F726 (D) -- relocating onto a folder another project claims gives a misleading refusal

**Status:** fixed 5daee14 2026-10-18 (Tier 0): relocating onto another project's folder names that project and both remedies; an unmarked folder is told it has no .agentweave/project.json.

**Found:** open 2026-10-18. Sweep group A. 409 `project_identity_conflict` "relocation target does not carry the project marker": it carries another project's marker, and the message names neither that project nor a remedy. Seam: Projects.

## F727 (D) -- the capability question's "Enabled it -- go ahead" reads as a grant but grants nothing

**Status:** fixed 5fd3870 2026-10-18 (Tier 0): picking the enabling option while the setting is off is refused (409, says where to turn it on) instead of waking the agent into a second 403.

**Found:** open 2026-10-18. Sweep group A. Picking it without turning the setting on delivers the answer; the agent retries: a paid turn, a second 403, a second question ("this is the last time"). Seam: Capability plane x Questions.

## F728 (D) -- small agent/project items from the 2026-10-18 sweep

**Status:** fixed 2026-10-18 (Tier 0): items (1)-(2) fixed 0463fe8 2026-10-18 (Tier 0): a budget below the open agents saves with a warning the settings panel now shows (it showed no save warnings before); the writing-agent work_dir refusal names its checkout and both remedies. Item (3) fixed a0b82e5 2026-10-18: a file directly in .agentweave/worktrees|tasks|reviews/ is the Hub's, not an agent named after the file.

**Found:** open 2026-10-18. Sweep group A. (1) `agent_budget` can be set to 8 while 10 agents are open (`warnings: []`); Overview reads "10 of 8 agents". (2) `work_dir` refusals for a writing agent are one sentence with no remedy. (3) An outside write into `.agentweave/worktrees/` is recorded `destination_kind: agent`, `destination_name: f614-allowed.txt` (a file read as an agent's workspace). Seam: Agents x Permissions.

## F729 (D) -- after a project delete the app refetches the deleted project

**Status:** fixed 7a55bb1 2026-10-18 (Tier 0): the delete no longer writes the selected project itself (which raced App's destination->store effect back to the deleted id); navigation resolves the fallback once, and no query for the deleted project runs. Recurred 2026-10-23 (day `sweep-projects-sweep`): filed as F1021.

**Found:** open 2026-10-18. Sweep groups A and D. Ten-odd queries for the deleted project return 404 in the console before the app navigates away. Seam: Projects (UI).

## F730 (D) -- small spec/evidence echoes from the 2026-10-18 sweep

**Status:** fixed 2026-10-18 (Tier 0), all eight items: items 2-7 89afece (operator review_state filter, unknown phase 422, merge answers applied, agent decide answer carries footprint, full journey route, rename repoints the index); item 1 b96fd14 (a "specification updated" drift answer stores no fingerprint, so the next scan asks again unless the requirement was reworded); item 8 0012ceb (rejecting evidence of an approved task on an archived document keeps the rejection, leaves the task approved, and task_reopen says why).

**Found:** open 2026-10-18. Sweep group B. (1) `specification_updated` drift answer accepted with no rewording, silencing that drift. (2) Operator `GET /spec/evidence?review_state=rejected` -> 200 with every piece (the agent route filters). (3) `to=nonsense` on `/documents/phase` -> 409 while an unknown rigor is 422 (F657). (4) A capability `merge` that applied the operator's edit answers `merged: 0`. (5) An agent's `decide_evidence` answer omits the footprint (F657 fixed the operator route only). (6) The `steps_skipped` message names the journey route without its `/projects/{id}` prefix. (7) After an agent's `rename_spec_document` the picker and tree show the slug, and Place under is hidden until a Rebuild. (8) Rejecting evidence of an approved task on an archived, folded change reopens the task on a document that cannot reopen. Seam: Spec documents x Evidence x Drift.

## F731 (D) -- small task/flow/loop items from the 2026-10-18 sweep

**Status:** fixed 2026-10-18 (Tier 0), all seven items: items 1 c14ba89, 2 f7d80f6, 3 f14bdbd, 4 664e614, 5 13f76d8, 7 428815e; item 6 c558074 (a checks refusal the operator receives ends on the operator's next step and keeps its line breaks in the drawer).

**Found:** open 2026-10-18. Sweep group C. (1) Story says "Loop ... moved it", Details history says "Flow ... moved" for the same move. (2) `POST /jobs/{id}/run` names one `job_run_id` when the firing created two JobRuns. (3) `stop_at` with no timezone accepted and shown as local; one in the past accepted silently. (4) `task_integrations.actor` is `""` when the operator integrates. (5) Review of a pending task refused "has no branch to review" (not its status); review of a nonexistent task tells the operator "A delegation may only name a task in the project the delegating run belongs to". (6) Land refusal loses failing-check line breaks and reads as addressed to reviewers. (7) Dependency 404 lists an existing id beside the missing one. Seam: Tasks x Flows x Jobs.

## F732 (D) -- the `reset` hint is a command that is refused

**Status:** fixed 5e3f4d3 2026-10-18 (Tier 0): a named profile's start hint always names a port (`--port <port>` when unknown), so reset's "start fresh" line is a command the CLI accepts.

**Found:** open 2026-10-18. Sweep group D. `reset --profile sweepdcli --yes` ends "Run 'agentweave --profile sweepdcli' to start fresh", refused without `--port`. Seam: CLI & lifecycle.

## F733 (D) -- every Claude turn logs a second, empty context reading, and the Ledger counts routine readings as warnings

**Status:** fixed bd5881e 2026-10-18 (Tier 0): a 'measured' reading with neither tokens nor percent is no longer recorded (one reading per Claude turn), and the Ledger labels the folded row "Context readings" in a neutral tone.

**Found:** open 2026-10-18. Sweep groups D and B. A second `context_warning` ~40 ms after the real one, `status:"measured"`, `context_tokens:null`, shown in Logs as "a context reading with no measurement"; the Ledger's "Repeated notices - Context warnings" counted 37 for ~14 turns (group B: 56, routine 3-4% measurements). Stored `context_usage` is correct. Seam: Logs, events & SSE.

## F734 (D) -- a client sending a body over the limit gets a connection abort instead of the 413 sentence

**Status:** fixed 85cd26c 2026-10-18 (Tier 0): ContentSizeLimitMiddleware reads (bounded, 64 MiB) and discards an over-limit body before answering, so clients that send first read the 413 sentence.

**Found:** open 2026-10-18. Sweep group D. Python urllib sending 10 MiB+1 gets `[WinError 10053]`: the middleware answers from `content-length` without draining the body; curl reads the 413. F641 holds for curl. Seam: Knowledge vault x Resilience.

## F735 (D) -- two silent vault dead ends: "check now" with no requirements, and decision-type uploads

**Status:** fixed 535ad49 2026-10-18 (Tier 0): spec-vault "check now" answers 409 naming what is missing (no requirements, or no current fact) instead of 202 queued, and a decision-type upload's answer says it is not distilled.

**Found:** open 2026-10-18. Sweep group D. (1) On a document with no requirements, spec-vault "check now" answers 202 `queued` and nothing fires or is recorded. (2) An upload typed `decision` is never distilled; Distil explains with a 409, the upload response and form do not. Seam: Knowledge vault.

## F736 (D) -- starting the Hub from a folder registers that folder as a project and rewrites its binding

**Status:** fixed 459106a 2026-10-18 (Tier 0): a bare agentweave start opens implicitly and is refused (409 deleted_project_marker, marker untouched, reason printed by the CLI and logged) for a folder whose marker names a project this database deleted; an explicit open from the app keeps F609's re-mint.

**Found:** open 2026-10-18. Sweep group D. `agentweave --profile sweepdcli --port 8035` run from `testbed/scratch` rewrote `testbed/scratch/.agentweave/project.json` to `proj-49aa617ace86` (a profile since reset); any earlier binding of that folder is gone. Seam: CLI & lifecycle x Projects.

## F737 (B) -- the workspace judge still reads commands as text: four shapes reach the runner's configuration or feed arguments without F675's or F676's rule seeing them

**Status:** fixed 00d599e + 38f4e5a 2026-10-18 (Tier 2, migration 0133): every turn launch fingerprints the workspace's runner configuration (runner_config.RUNNER_CONFIG_PATHS, shared with the judge) and a change holds the turn (input kept, uncounted) and asks the operator once on the permission card naming the files — Allow records and starts, Deny keeps it held; a fresh checkout bringing config the project directory lacks is asked too; the pipe-fed shapes (3) launcher/option-only interpreters and (4) pipe-fed listings are refused by the judge. Acceptance: test_a_changed_runner_configuration_holds_the_next_turn.py (xfail-first 9339833).

**Found:** open 2026-10-18. Sweep group A, found calling `_decide` in-process (deliberately not run as agent turns). Shapes neither rule sees: a copy or move whose destination is the runner-config directory without naming the file; a decoder writing a file that a later command substitution reads; an interpreter reached through a version launcher; a listing cmdlet piped into a path cmdlet. Same "text boundary" class F675's status concedes for `cd .claude && ...`, without needing `cd`. Grounded review points: the directory-as-destination match in `_RUNNER_CONFIG_PATHS`, the scope of `_PIPE_INTERPRETERS_RE` and `_PS_LISTING` (`hub/hub/mcp_server.py`). Defect (posture holes, not driven to effect). Seam: Permissions & sandbox (shell judge). Tier guess: 0 per shape; the class is the research question of a structural boundary.

## F738 (B) -- `agentweave reset --profile X` cannot find X's running Hub, so it deletes the data folder from under it

**Status:** fixed fc204fe 2026-10-18 (Tier 0): `reset --profile X` now stops every live Hub whose `hub-X-<port>.pid` it finds (`_hub_pid_files_of`, exact-name match so `a` does not claim `a-b`) before deleting the data folder. Test: tests/test_cli_named_profile_port_rule.py (red before the fix). Driven: a real Hub on a fresh profile at :8061, reset stopped PID and freed the port before the data dir went.
**Source:** review
**Theme:** CLI & lifecycle

`src/agentweave/cli.py:1514` builds the PID path with `_hub_pid_file(profile=profile)` and no port, so it only ever looks for `hub-X-8000.pid`. A named profile's Hub runs on its own port (the named-profile port rule, F723/F732), so reset never sees it, never stops it, and deletes the profile's data directory while that Hub still has the database open. Related: F723, F732.

## F739 (C) -- a request body sent without a Content-Length is not size-limited

**Status:** fixed 66dba2a 2026-10-18 (Tier 0): with no Content-Length the middleware counts the bytes as they arrive; past the limit the app is told the client went away, its answer is dropped and the same 413 goes out. Test: hub/tests/test_oversized_body_reads_the_413.py (chunked over the limit red before the fix). Driven: real Hub on a scratch DB at :8125, a 3 MB chunked POST to /projects/open got the 413, a 10-byte one reached the route (422), no tracebacks.
**Source:** review
**Theme:** Resilience

`ContentSizeLimitMiddleware` (`hub/hub/main.py:365`) checks only the `content-length` header, so a chunked body is read whole with no limit. F734 made an over-limit declared body read the 413; an undeclared one is never refused. Related: F734.

## F740 (D) -- a failed conversation-title firing does not say why

**Status:** fixed b714c26 2026-10-18 (Tier 0): a failed conversation-title firing records why (the spawn's error, e.g. "exited 1: ...", or "claude produced no JSON envelope") as its detail.

**Found:** open 2026-10-18. Filed from the 2026-10-18 fix pass (vault group), by reading the code.
**Source:** review
**Theme:** Manager jobs

`conversation_titles.py` records a failed firing (spawn failure, non-zero exit) with `_fired(db, "failed" if failed else "empty", None)`, so the Manager activity row reads "failed" with no detail; the vault jobs record their reason. Related: F719, F721.

## F741 (D) -- a vault report on an unread file still gets the fixed "enable the job" note

**Status:** fixed cddc65a 2026-10-18 (Tier 0): a report on an image/PDF held here but unread now tells the model what is in the way (F720's reason, e.g. the distillation job is disabled) instead of "the source is not on this machine"; the fixed note itself never reached the prompt.

**Found:** open 2026-10-18. Filed from the 2026-10-18 fix pass (vault group), by reading the code.
**Source:** review
**Theme:** Knowledge vault

F720 replaced the fixed note on the entry-read route only. `vault_reports.py:136` calls `vault.read_entry` directly, so the vault-reports job reading an unread image or PDF still sees "enable the job" when the job is enabled. Related: F720.

## F742 (C) -- renaming a spec document changes its index title but not the file's, which then reads as a metadata conflict

**Status:** fixed 2026-10-18 night (Tier 0). `rename_document` now rewrites the moved file's payload `title` to the row's (after the move; an OSError is logged, never a refused rename). `test_the_index_follows_the_rename` asserts empty diagnostics and the file's title, and was red first (`intrinsic_metadata_conflict` on `title`, actual `Demo`). Driven on a scratch Hub :8127: create, reindex, rename via a run token -> `/specs` diagnostics `[]`, file title = subject.
**Source:** review
**Theme:** Spec documents

`spec_service.rename_document` (`hub/hub/spec_service.py:1180`) sets the row's title to the rename subject but leaves the payload `title` in `spec.json` unchanged. After a rename plus a rebuild (and now after F730 (7)'s index update), `/specs` reports `intrinsic_metadata_conflict` on `title`. Related: F730.

## F743 (C) -- an operator PATCH to revision_needed that names an assignee silently ignores it

**Status:** fixed 2026-10-18 night (Tier 0). `apply_transition` takes `holder_named`; the operator route passes it when the PATCH carries `assignee`, so the author-return no longer overwrites it (a named agent or an explicit null both stand; no `assignee` still returns to the author). Test `test_an_operator_send_back_naming_an_assignee_gives_it_to_that_agent` in `hub/tests/test_revision_returns_to_the_author.py` was red first. Driven on a scratch Hub :8126: named -> `named`, null -> unassigned, omitted -> `author`; no tracebacks.
**Source:** review
**Theme:** Task ledger

`update_task_for_actor` (`hub/hub/api/v1/tasks.py`) writes `body.assignee` before `apply_transition`, whose revision_needed path (`task_transition_service.py`, the F495/F708 author-return block) then overwrites it with the author. `{status: "revision_needed", assignee: "X"}` answers 200 and the task goes to the author, not X. Related: F708.

## F745 (C) -- a command substitution's output is never judged: `cp x $(dirname $(pwd))` copies outside the workspace

**Status:** fixed c22b861 2026-10-19 (Tier 0): the working directory spelled as a command is judged as `$PWD` is -- a whole-argument `$(pwd)`/`` `pwd` ``/PowerShell `$(Get-Location)` is `.`, and a substitution, group or assignment that consumes a location command's output is refused (`$(dirname $(pwd))`, nested backticks, `d=$(pwd)`, `(Split-Path (pwd))`, `$d = Get-Location`); bash backtick substitutions now un-escape. Conceded and asserted allowed: a value handed on through a file (example 2) and `$(dirname $(realpath .))`. Driven through the spawned approver with each allowed command then run in Git Bash: nothing landed outside the workspace. Spec drift stays with F755.

**Found:** open 2026-10-18. Filed from the 2026-10-18 decision pass (judge group, F696), by calling `_decide` in-process; not driven to effect.
**Source:** review
**Theme:** Permissions & sandbox

The workspace judge does not judge the output of a command substitution. Each of these is allowed today:

- `cp x $(dirname $(pwd))`
- `dirname "$(pwd)" > f; cp x $(cat f)`
- PowerShell `Copy-Item x (Split-Path (pwd))`

The gap is at the `_decide` docstring, `hub/hub/mcp_server.py` around line 3967. Refusing `$(dirname $PWD)` (F696) is therefore consistent but not a real boundary.

F737's launch-time fingerprint covers this class only for the runner's configuration, not for writes outside the workspace in general. Related: F696, F737, F676.

## F746 (D) -- releasing a task checkout throws away a half-resolved prerequisite merge

**Status:** fixed 2026-10-19 (Tier 0), not as filed in one respect: the checkout is kept, not the merge saved. `release_task_worktree` now holds back a checkout whose merge is still conflicted (`ReleaseResult.kept_reason`), and `release_task_workspace` records a warn `task_worktree_release_skipped` event naming the paths; a release after the merge is resolved works. Reached by rejection only: approval is refused with a conflict (`gate_unsatisfied`). Not changed: `release_worktree` (the per-agent path) has the same shape, and the UI has no summary line for the new event (its generic fallback shows). Tests: `test_releasing_a_checkout_keeps_a_half_resolved_merge.py` (2) and `test_a_half_resolved_merge_keeps_its_checkout_and_says_so` (real route, real git); all red without the fix.
**Source:** review
**Theme:** Worktrees & integration

`release_task_worktree` (`hub/hub/worktrees.py` around line 1440) force-removes the checkout after the snapshot declines to commit an unfinished conflicted merge (0e1c0f5). The author's partial resolution is lost. The branch keeps its commits, and the next provisioning retries the merge and sends the note again. Related: F695.

## F747 (C) -- a delete/modify merge conflict has no markers, so the snapshot commits it as the files stand

**Status:** fixed 2026-10-19 night (Tier 0), part-as-filed not a defect. The claim does not hold: a delete/modify path stays unmerged in the index (`diff --diff-filter=U` names it, driven in a raw git repo), so `unresolved_merge_paths` already declines the snapshot, and once the agent stages it, keeping the file or taking the deletion is the resolution the conflict asks for; git keeps no marker to tell a careless `add` from a deliberate one. The real gap was next to it: keeping this side's file leaves the tree equal to HEAD, so `snapshot_worktree` saw nothing dirty and never concluded the merge, leaving it open. It now commits when a merge is open and unresolved-free. `hub/tests/test_a_delete_modify_merge_conflict_is_unresolved_until_the_path_is_resolved.py` (3 tests; the keep case red first); the 377 worktree/merge/checkout Hub tests pass. Was: open 2026-10-18. Filed from the 2026-10-18 decision pass (F695 group), by reading the code; not driven.
**Source:** review
**Theme:** Worktrees & integration

`worktrees.unresolved_merge_paths` reads a merge as unfinished in two cases: when the index still has unmerged entries, or when a staged path carries conflict markers. One side deleting a file the other modified writes no markers. So once the agent stages the result, the auto-snapshot commits the merge as the files stand, whether or not the conflict was really resolved. Related: F695.

## F749 (C) -- `e2e.py hub-up` from a worktree serves the main checkout's code

**Status:** fixed 2026-10-19 night (Tier 0), 353b67a. `REPO` in `e2e.py` now defaults to the checkout the script sits in (`parents[3]`), `hub-up` prints "serving the Hub from <path>" and refuses a tree with no `hub/hub/main.py`; `AW_REPO_ROOT` still wins. `tests/test_e2e_harness_repo_root.py` (3 tests; two red first). Driven: a real git worktree whose `hub/hub/main.py` carried a marker in `/health`; `hub-up` from it on :8131 answered with the marker, then `hub-down`. Filed from the 2026-10-18 decision pass. One fix agent's first drive Hub served master's code without saying so.
**Source:** drive
**Theme:** CLI & lifecycle

`.claude/skills/e2e-loop/e2e.py` (around line 61) defaults `REPO` to the main checkout. A drive started from a worktree therefore tests master unless `AW_REPO_ROOT` is set, and nothing warns.

The harness should default to the git toplevel of the current directory, or refuse when the two differ. The workaround is recorded in `DEAD-ENDS.md`.

## F750 (D) -- two processes pinning the same new tool-server digest race, and one fails with Access denied on Windows

**Status:** fixed 2026-10-19 (Tier 0, night window): `_write_verified` treats a refused replace as done when the target already holds the bytes, and otherwise retries a short while before raising. Tests in `hub/tests/test_tool_server_pin.py`, the race case red first. Driven with 6 real processes pinning one new digest, 15 rounds: 37 failures before, 0 after. Seen 2026-10-18 in the full Hub suite run: `test_mcp_server_stdio_surface.py` failed collection on two xdist workers. A re-run, with the digest already pinned, passed.
**Source:** drive
**Theme:** Resilience

`tool_server.py` (around lines 81-86) writes `<target>.<pid>.tmp` and then calls `os.replace(temp, target)`. When two processes pin a new digest at the same moment, the second replace onto a file the first has just written, and may hold open, raises `PermissionError: [WinError 5]`. Two Hubs starting together after an upgrade could hit the same race. An existing identical target should count as success.

## F751 (D) -- a reviewer's verdict still accepts a task's own awaiting evidence recorded for an earlier wording

**Status:** fixed 2026-10-19 (Tier 0, night window): `decide_with_verdict` leaves an awaiting piece whose digest differs from its requirement's when accepting (rejecting stays open, as in `decide`). Tests in `hub/tests/test_the_reviewers_verdict_decides_the_tasks_evidence.py`, the accept case red first. Filed 2026-10-18 from the decision pass (F692 group).
**Source:** review
**Theme:** Requirements & evidence

F692 refuses accepting evidence for an earlier wording on `decide` and `overturn`, but `decide_with_verdict` still accepts it. It does no harm, because coverage ignores stale acceptance, but the record reads "accepted" for evidence that no longer applies. Related: F692, F691.

## F752 (C) -- recording already-built work as a spec change cannot be approved without "Approve anyway"

**Status:** fixed 97be062 2026-10-19 (Tier 1, night window; change `spec/changes/already-built-work-is-approved-without-approve-anyway`, approved and folded into `spec-document-authority`'s gap set): a requirement whose coverage is `verified` at the payload's wording is served, so `requirement_without_task` is not raised (`spec_service.served_keys`, used by the write report and the phase checks); partial-only evidence and evidence for an earlier wording still raise it. Found on the way: `steps_skipped` named the journey call, which answers 409 `no_journey` on a proposed document (where approval meets it); its message now names the send-back to exploring first. Test `hub/tests/test_a_demonstrated_requirement_needs_no_task.py`, red first. Driven on the trial Hub :8010: the change itself, with no tasks, recorded test evidence, was proposed with no `requirement_without_task`, refused once on `steps_skipped`, and after following the message was approved without `approve_anyway`. Spec-flow friction from authoring the 2026-10-18 decisions on the trial Hub (eight changes).
**Source:** drive
**Theme:** Spec documents

A change whose work was built with tests, not through tasks, has no tasks. Every requirement then raises `requirement_without_task` as a blocking gap, and `steps_skipped` fires on a document written in one PUT. All eight changes needed `approve_anyway`, and there is no record-only path. Approvals are scarce: this trains the operator to approve over gaps. Related: F704.

## F753 (C) -- a fold can change requirements but not an algorithm or a criterion's text

**Status:** fixed 2026-10-19 (Tier 1, night window, 213e169): a fold carries the change's algorithms (all by default or named, appended, replacing a named capability algorithm, or retiring one; a same name without `replaces` collides), and `criteria` items put a change criterion in place of a named capability criterion under its key. A change archived after a fold is still folded into a capability no merge names it with, staying archived (`fold_already_folded` for the same one), so the default archive no longer strands a second fold. Change `spec/changes/a-fold-carries-algorithms-and-criterion-rewrites` (spdoc-7dff3813cc51) on :8010, approved without Approve anyway, folded into `spec-document-authority` with a criterion replaced through the new item. Test `hub/tests/test_a_fold_carries_algorithms_and_criterion_rewrites.py`, 16 red first. Drive `scripts/drive/d1019_f753_fold_drive.py` on a fresh Hub (:8032). Not as filed: the change's algorithms were not only unamendable but dropped without a word. Spec-flow friction from the same authoring.
**Source:** drive
**Theme:** Spec documents

`fold_draft` (`hub/hub/spec_service.py`) folds requirements (`replaces`, `as_key`, `statement`) and retires criteria, but cannot amend an algorithm step or a criterion's wording. F696's correction needed a separate full-payload `merge` of the capability.

Folding one change into several capabilities works, but only with `archive:false` on every fold except the last, and nothing in the route or the app guides that.

## F754 (D) -- every fold into some capabilities reports the capability's old gaps as if they were the change's

**Status:** fixed 2026-10-19 (Tier 0, night window): the fold's `warnings` name only what the fold introduced; the capability's warnings from before it are returned apart as `standing_warnings` (matched by code and message; `where` is an index that shifts). Test `hub/tests/test_a_fold_reports_only_the_gaps_it_introduced.py`, red first. Driven on a fresh Hub (:8031): `warnings` named only the folded `widgets-glow-pulse`, `standing_warnings` the capability's own `widgets-exist`. Not as filed: since F703 (5486070) these were already `warnings`, not `blocking`. Spec-flow friction from the same authoring.
**Source:** drive
**Theme:** Spec documents

Folding into `requirement-traceability` or `workspace-isolation` answers `blocking` entries for long-standing `requirement_without_criterion` gaps, e.g. `evidence-carries-what-it-takes-to-judge-it-tool-says-so` and `an-agent-checkout-catches-up-with-main-scope`. They are existing gaps in the capability, not something the change introduced, but the fold reports them as the change's.

## F755 (C) -- Tier 0 judge fixes leave the spec corpus behind: the shell judge's rules are not specified

**Status:** fixed 2026-10-19 (Tier 1, spec-only, `spdoc-7251e74e6ba7`, `spec/changes/the-shell-judges-text-rules-are-specified/`, folded into agent-run-sandboxing): three requirements stated from the code (`runner-configuration-is-not-written-by-a-tool-call` for F675, `a-text-tools-script-is-not-a-path` for F696's sed/awk/cut/tr/grep exemptions, `the-working-directory-by-name-is-judged-as-the-workspace-root` for F696's `$PWD` and F745's `$(pwd)`), six criteria, and the shell-text algorithm replaced: a pipe-fed step and a runner-configuration step added, and step 5's exceptions amended. F676's rule was already `pipe-fed-shapes`. Every criterion example is checked against the real `_decide` by `scripts/drive/d1019_f755_judge_rules_check.py` (44/44). No judge behaviour changed. Earlier: open 2026-10-18. Found while folding F696/F737.
**Source:** drive
**Theme:** Permissions & sandbox

No capability states F675's or F676's text rules: the interpreter and pipe-fed rules, or the sed/awk/grep pattern exemptions (d0a27d4, 570e93d). The 2026-10-18 fold added `pipe-fed-shapes` to `agent-run-sandboxing`, but the rest of the judge's behaviour exists only in code and in `test_permission_approver.py`'s row table. Related: F675, F676, F696, F737.

## F756 (C) -- a glob in the last component after `..` through a link out is allowed

**Status:** fixed 2026-10-19 (Tier 0): wider than filed. `_glob_links` returned None for any piece with a second glob-holding component, so `ls */*` and `ls sub*/../*` were allowed too when a glob matched a link out; the walk now goes on (`_match_glob_component`, called from `_glob_tail_walk` for each later glob component). Test `hub/tests/test_a_second_glob_after_a_link_is_judged_where_it_resolves.py`, 7 refusals red before, 15 green after. Earlier: open 2026-10-19. Found while writing the F444 test.
**Source:** drive
**Theme:** Permissions & sandbox

With `up` a link to a directory outside the workspace, `ls up/..`, `ls up*/..` and `ls up/../*` are refused, but `ls up*/../*` is allowed (`{'allow': True, 'reason': 'inside your workspace'}`, measured on a junction through `_decide`), though it lists the link target's parent. Probably the glob walk (`_glob_tail_walk`, `hub/hub/mcp_server.py`) judges the `..` it walks to and then the final glob component as inside the listed path, not the resolved one. Reads only as filed; a write form (`cp n up*/../*`) is not measured. Related: F444.

## F757 (D) -- a fold renames a change's requirements, and the change's own text still names the old keys

**Status:** fixed 2026-10-19 (Tier 0). The fold draft and the fold now warn (`fold_renamed_key_named`) when a folded requirement, algorithm or criterion names, as a key, a requirement the fold files under another key; keeping the key (`as_key`) reports nothing. Test: `hub/tests/test_a_fold_warns_when_text_names_a_key_it_renames.py`; drive: `scripts/drive/d1019_f757_renamed_key_drive.py`. Found while folding F755.
**Source:** drive
**Theme:** Spec authoring

With no `as_key`, the fold draft gives each folded requirement a prefixed key (`the-shell-jud-runner-configuration-is-not-written-by-a-tool-call` for `runner-configuration-is-not-written-by-a-tool-call`; measured on `GET .../fold-draft` on :8010), and criterion keys gain the change's whole name. An algorithm step or rationale in the change that names one of its own requirements by key (`(*a-text-tools-script-is-not-a-path*)`) is folded verbatim, so in the capability it names a key that does not exist. Neither the draft nor the fold warns. Worked around with `as_key` on every requirement. Related: F753.

## F759 (B) -- an open drift candidate on evidence the operator overturned to rejected hides the rejection from the approval gate

**Status:** fixed aa37fd7 2026-10-21 (night iteration 15, Tier 0): `requirement_evidence.decide` supersedes the piece's open drift candidates when the decision is `rejected`, so coverage reads `rejected` and the approval gate answers 409 `gate_unsatisfied`. Driven through the real routes in-process (`hub/tests/test_an_overturned_piece_supersedes_its_drift.py`: overturn, coverage, and the task walk to `approved`); all three failed before the fix. Not re-run on a live Hub (labelled). Found in the evidence sweep (`scripts/drive/s1019_evidence.py` + `s1019_evidence_p2.py`, scratch Hub :8150).
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes -- repro below, control included.
**Tier:** 0

FR-3 (sketch rigor) has one operator piece with `locator: todo/other.py` (accepted). Change `todo/other.py`, commit, `POST .../spec/drift/detect` -> `raised: [drift-…]`. Then `POST .../spec/evidence/{id}/overturn {reason}` -> 200 `rejected`. The drift candidate stays `candidate` (`GET .../spec/drift?document=…`), and since `DRIFTING` outranks `REJECTED` in `requirement_coverage.PRECEDENCE` (`hub/hub/requirement_coverage.py:73`), FR-3 reads `drifting` with `accepted_count: 0`. Walking FR-3's task to `under_review` and PATCHing `approved` as the operator answers **200** -- `_rejected_entries` (`hub/hub/requirement_gate.py:937`) only sees `state == rejected`. Control, same walk on a requirement whose only piece was overturned with no drift: **409 `gate_unsatisfied`**, `blocking: [{state: rejected}]` (D2: a rejected requirement blocks approval at every rigor). On screen the coverage bar says "Drifting — The implementation changed after this was verified" and the requirement story shows two rejected pieces beside an approved task. Answering the drift `no_change_required` afterwards flips FR-3 to `rejected`, but the task stays approved. Two seams: the overturn (`_operator_decides`, `hub/hub/api/v1/spec.py`) leaves the piece's open candidate standing (the scan itself only reads accepted evidence, `requirement_evidence.detect_drift`), and `open_drift_for` counts candidates whose evidence is no longer accepted. A failing test: `hub/tests/` -- accept, raise drift, overturn, approve task -> expect 409 rejected. Related: F692, F730.

## F760 (B) -- the evidence diff reads git output as cp1252: a 500 on some non-ASCII content, mojibake on the rest, and non-ASCII paths quoted with no patch

**Status:** fixed 2026-10-20 (night iteration 13, Tier 0). `requirement_evidence._git` reads git as UTF-8 (`errors="replace"`) with `core.quotepath=off`, so content with any byte is read, not a 500, and a non-ASCII path is named as itself with its patch. `worktrees._run_git` got the same two arguments. Tests: `hub/tests/test_evidence_diff_reads_utf8.py` (both failed first). Driven on scratch :8130 (`d1020_f775_f777_git_reads.py`): operator evidence on a commit with `todo/ñandú.py` containing `Ángel → café` -> diff 200, the path as itself, `+name = "Ángel → café"` in the patch. Original report: open 2026-10-19. Found in the evidence sweep (`scripts/drive/s1019_evidence.py`, scratch Hub :8150), seen in a browser.
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes -- three repros below, one seam.
**Tier:** 0

`requirement_evidence._git` (`hub/hub/requirement_evidence.py:729`) runs `subprocess.run(..., text=True)` with no `encoding`, so on this machine (locale cp1252) git's UTF-8 output is decoded as cp1252, and `core.quotepath` is left on. Each repro records operator evidence with `commit: <sha>` and reads `GET .../spec/evidence/{id}/diff`: (1) a file containing `"Ángel → café"` (UTF-8 byte 0x81) -> **500**; the reader thread dies with `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`, `result.stdout` is None and `.strip()` raises (`work_diff`, line 851). The Evidence view shows "The diff of this work could not be read." (2) A file containing `café` -> 200 with `+drink = "cafÃ©"`, on screen too. (3) A file named `todo/ñandú.py` -> `path: "\"todo/\303\261and\303\272.py\""`, `patch: ""` (`work_diff`'s `diff --git` regex does not match the quoted header); the view shows that path with +0 -0. Fix sketch: `encoding="utf-8", errors="replace"` and `-c core.quotepath=off` on `_git`. Check the other `_git` callers that compare paths (`tree_entries`, `_commit_paths`, `branch_paths`) agree once quoting changes: today they agree only because they are all quoted. Failing test: a diff route test with a non-ASCII file name and content, under `PYTHONUTF8=0` and a cp1252 locale.

## F761 (B) -- a piece that names no commit shows, as its work, whatever commit HEAD happened to be

**Status:** fixed 5f86cd4 2026-10-21 night iteration 16 (Tier 0, with one nullable column). A footprint now records whether the recorder named its commit (`evidence_footprints.commit_named`, migration `0139`; an operator's `commit` or a locator that is one is named, the checkout's HEAD is not, an agent re-stamp is not). `GET /spec/evidence/{id}/diff` passes the recorded branch to `work_diff` for a piece whose `commit_named` is false, and where that branch is the main line and the commit is already on it, answers no files and a reason naming the checkout's commit; the `commit^` fallback stays for a named commit or a task line that has merged. NULL (rows from before) reads as it did. Why a column: a first cut read `watched_from`, and the drive caught it misfiring on a piece that named a commit and also a file locator (watches `locator`, not `commit`), so the fact has to be stored. Tests `hub/tests/test_evidence_carries_what_it_takes_to_judge_it.py` (the repro failed before the fix; a commit plus locator on main still diffs its commit) and `hub/tests/test_migration_0139_footprint_commit_named.py`. Drive: scratch Hub :8153 (`scripts/drive/s1021_f761_drive.py`): the no-commit piece answered 200, no files, 'this piece names no commit; it was recorded with the checkout at 617128272ca2 on master...'; the commit-plus-locator piece answered `todo/fix.py`. Not measured: an agent piece recorded on master, or in a task checkout before its first commit (the finding's 'by the same path' cases).
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes -- repro below.
**Tier:** 0

The operator records `{identifier: FR-2, summary: "watched it sort", covers: partial}` with no `commit` and no locator. Its footprint takes HEAD on master (`b51a700`, which was the commit made for FR-1, `watched_from: []`). `GET .../spec/evidence/{id}/diff` answers 200 with `files: [todo/list.py]` and that commit's patch (`+    return ['a', 'b']  # today`), and the Evidence view shows it under FR-2's proof as the work. `work_diff` treats the footprint's commit as "the piece's commit". The commit is already on main, so `_line_of_work_base` finds no merge and falls back to `commit^` (`hub/hub/requirement_evidence.py:833`). By the same code path (not measured) this should also apply to an agent piece recorded on master, or recorded in a task checkout before its first commit there. The route's own docstring promises "200 with no files and a `reason` where there is no commit". Expected: a piece that named no commit and whose footprint commit was already on the main line at recording answers no files and a reason saying what the checkout was at. The fallback to `commit^` is right only for a commit the piece named (`watched_from` holds `commit`, or a task line that has since merged). Failing test: record operator evidence with no commit after an unrelated commit, then read the diff, which should have no files.

## F767 (B) -- a flow hands fresh work to its own named reviewer, and the task that reviewer builds can then never be reviewed: one event, and nothing on the loop or the task

**Status:** fixed 2026-10-21 night iteration 17, 997519b (Tier 0). `scheduler._agents_a_loop_may_staff` withholds the agents a flow's document names to judge work (`review_turn.named_reviewers`: each task's `reviewer`, `delivery.reviewer`, `delivery.tester`) from fresh work, unless no other agent with a runner exists on the roster (a pool that would empty keeps them). Tests `hub/tests/test_a_flow_does_not_hand_fresh_work_to_its_named_reviewer.py` (reviewer and tester cases failed before; control: no named reviewer still runs two builds; sole-agent flow still runs). Drive: scratch Hub :8154 (profile f767), the finding's own shape (flow, builder + rev Haiku, two ready tasks, `rev` named reviewer, approve_anyway, `POST /jobs/{id}/run`): one build, on builder (`scripts/drive/s1021_f767_drive.py`). Not done: the second half of the finding's expectation (a reviewer that must build says on the task that it waits on the operator) is F768's story fix. Found in the tasks sweep (`scripts/drive/s1019_tasks.py`, scratch Hub :8170, real Haiku turns). Original: open 2026-10-19.
**Source:** drive
**Theme:** Flows & review
**Ready:** yes -- repro below.
**Tier:** 0

Two agents, `builder` and `rev`, both Haiku. A change with two independent tasks (`t-clamp`, `t-sub`) and `delivery: {mode: flow, agent: builder, reviewer: rev}`, approved with `approve_anyway`. The first `POST /jobs/{id}/run` started both tasks in parallel: `t-clamp` to builder, **`t-sub` to rev** (`job_run_ids` two; the loop's `current_tasks` named `rev` as t-sub's agent before the firing). rev completed t-sub. The next firing staged t-clamp's review to rev and emitted `review_unstaffed` for t-sub: "this task names 'rev' as its reviewer, and that agent is the one that completed this task. Naming a different reviewer, or reviewing it yourself, is the way forward -- the flow will not substitute somebody else for a named reviewer."

The cause is that a flow draws fresh work from every free agent: `scheduler._agents_a_loop_may_staff` returns `_agents_that_are_free(...)` unfiltered for a loop with a document (`hub/hub/scheduler.py:1384-1386`), so the agent the delivery names as reviewer is offered as an author. The rule "the flow will not substitute somebody else for a named reviewer" then makes that task unreviewable by construction.

What the operator sees afterwards: the event fired **once** (08:50:44). Over four more firings t-sub stayed `completed`, the loop's `stall_reason` was `null` and `queue` read `{"completed": 2}`, the task's `blocked_reason` was null, and its story said nothing (F768). It waited until I accepted its evidence and pressed Land.

Expected: a flow that names a reviewer does not hand that reviewer fresh work while another agent can take it, so with two agents the flow runs one build at a time. Or, if the reviewer has to build, the task it built says on the loop and on the task that it waits on the operator. Failing test: `decide_firing` on a flow whose delivery names `rev`, with two ready independent tasks and `builder` and `rev` free, selects `rev` for neither task. Seam: Flows & review (parallel firing x the named reviewer).

## F768 (C) -- a task's story leaves out the flow's refusal to staff its review, so an unreviewable task's story ends at "completed" and says nothing more

**Status:** fixed 2026-10-21 night iteration 19 (Tier 0), 9eade29. `task_story` reads `review_unstaffed` from `event_logs` for the task (`data.task_id`) as its own story kind, with the reason, and `TaskStory.tsx` renders it ("Nobody could be found to review this"). Tests: `test_a_tasks_whole_story_is_in_its_drawer.py::test_a_review_the_flow_could_not_staff_is_in_the_story` (failed before; another task's event is excluded), `taskStory.test.tsx` (F768). Drive: the route in the test app and the component test stand in for the browser; not re-seen on a live Hub (labelled). Found in the tasks sweep (`scripts/drive/s1019_tasks.py`, `s1019_tasks_ui.py`, scratch Hub :8170), seen in a browser. Original: open 2026-10-19.
**Source:** drive
**Theme:** Tasks
**Ready:** yes -- repro is F767's.
**Tier:** 0

`GET /tasks/task-960d7005a969/story` for F767's t-sub: `assigned` (flow), `in_progress`, the run, the evidence, `completed` at 08:49:33, and then nothing until the operator's own accept and Land at 08:56. The `review_unstaffed` event for this task (`event_logs`, `data.task_id` = the task, 08:50:44, with the sentence naming the remedy) is not in the story. In the browser, the drawer's Story reads "rev moved it to completed" followed directly by "Checks passed 11m ago, You moved it to under review". `task_story.story_for` already reads `event_logs` for one task-scoped event (`_WORKSPACE_EVENTS = {"task_worktree_release_failed": ...}`, F711). `review_unstaffed` carries `task_id` and is the one record of why the task waited.

Expected: the story carries a `review_unstaffed` event, with its reason, at its time. Failing test: in `test_task_story`, a task with a `review_unstaffed` event in `event_logs` has a story event of that kind. Seam: Tasks (story) x Flows & review.

## F769 (B) -- the integration note hides a merge behind a later "already in master" skip and keeps a resolved "no main branch" line, so merged work reads "Not merged" twice

**Status:** fixed 2026-10-21 at 1df4f02. `newestPerTarget` lets a merged row outrank a skip for the same commit and drops a null-commit skip once any row merged. Test: `taskIntegrationRetry.test.tsx` (F769, route's order). Found in the tasks sweep (`scripts/drive/s1019_tasks_p2.py`, `s1019_tasks_ui.py`, scratch Hub :8170), seen in a browser.
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes -- repro below.
**Tier:** 0

A documentless task (`task-3e217a6750c7`, "Add mul()", built by a real builder turn), with the project's `main_branch` set to null, is landed by the operator: 200 approved, and the integration row is skipped with "this project has no main branch set". Saving `main_branch: "master"` re-attempts the merge: a `merged` row at `146d99b`. A later **Retry** records a `skipped` row "146d99b84f01 is already in master; there was nothing to merge", which `retry_integration`'s docstring says is the honest answer. `GET /tasks/{id}/integrations` lists all four rows correctly.

The drawer's note (`TaskIntegrationNote`) keeps only the newest row per `commit_sha@target_branch` (`newestPerTarget`, `hub/ui/src/components/tasks/TaskIntegrationNote.tsx:11-17`). Rendered, it read: "Not merged -- this project has no main branch set -- choose one in the project's settings / Not merged -- 146d99b84f01 is already in master; there was nothing to merge". The merge itself does not appear. The board card shows the same lines. The same rule puts "Not merged -- 24638934ecla is already in master" at the top of the flow task `t-clamp`'s card, above "Merged f97918a0 into master". That line is about the sibling task's commit, which `t-clamp` named through a stray FR-2 evidence piece (F771).

Expected: an `ALREADY_INTEGRATED` skip does not replace a `merged` row for the same commit. It reads as "Merged", or drops out. A no-main-branch skip (null commit) is not shown once a later row merged the task's work. Failing test: `TaskIntegrationNote` given rows [skipped no-main (null), merged X, skipped already-in-master X] in the route's order shows "Merged X into master" and no "Not merged". Seam: Worktrees & integration (Retry) x the task drawer.

## F770 (C) -- the checks row never says a failure also fails on main: the drawer shows a red "Checks failed" with the output, and only the Land refusal says it is not the task's

**Status:** fixed 2026-10-21 night iteration 20 (Tier 0, UI) at 4c1013c. `TaskCheckResult` types `preexisting`; `TaskChecksRow` adds a line "<checks> fails on main too, not this task's work" under a failed latest run and the same words on each earlier run's result. Tests `hub/ui/src/__tests__/taskChecksRow.test.tsx` (3 new, failing before); full UI suite 216 files, 2210 tests pass; eslint and tsc clean. Bundle rebuilt and committed. Drive: component test with the finding's result shape stands in for the browser (labelled: not re-seen on a live Hub). Found in the tasks sweep (`scripts/drive/s1019_tasks.py div`, `s1019_tasks_ui.py`, scratch Hub :8170), seen in a browser.
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes -- repro below.
**Tier:** 0

The setup: a task whose checks passed, then an operator commit on master that adds a failing test, then **Re-run**. The run is `failed`, and its result carries `"on_main": {"exit_code": 1}`, `"preexisting": true` (F605's fix). `POST /land` says so: "This task's checks fail, and they fail on main too, so the failure is not this task's work ... Land it with an override reason, or fix main first", and the drawer offers Land anyway. But the checks row above it reads "Checks failed: tests" in red, with the output tail, and "Earlier runs" lists "Checks failed · tests · exit 1 · 0.5s" with nothing more. `grep -rn "preexisting\|on_main" hub/ui/src` returns nothing: `TaskCheckRun`'s result type and `TaskChecksRow` never read either field. So the row a reviewer or operator reads first charges the task with a failure the Hub knows is main's.

Expected: a failed result with `preexisting: true` reads "tests failed -- fails on main too, not this task's work", in the latest row and in each earlier run. Failing test: `TaskChecksRow` given a failed run whose only result has `preexisting: true` renders "fails on main too". Seam: Worktrees & integration (project checks) x the task drawer.

## F771 (C) -- a review turn is not told which of the document's requirements are someone else's, and a Haiku reviewer sent correct work back twice for the sibling task's requirement

**Status:** fixed 2026-10-21 night iteration 21 (Tier 0), 089bb89, the briefing half. `review_turn._other_requirements_sentence` joins `verdict_evidence_sentence` (so the loop briefing and the turn context both carry it): "This task serves `FR-1`. The document's other requirements belong to other tasks (`FR-2`: `task-...` (Add sub())): do not send this task back for them." A requirement the task also serves is not called the other's; a one-task document says nothing. Test `hub/tests/test_review_briefing_names_other_tasks_requirements.py` (3, failed before). Not built: `read_spec_document` marking the reviewed task's requirements (the run-to-task lookup and the budgeted view make it more than a one-line change); the briefing line is what the reviewer reads first. Not re-seen with a live Haiku reviewer (labelled).
**Source:** drive
**Theme:** Flows & review
**Ready:** yes -- repro below; behavioural, measured 2 of 2 here, and once in F606's drive.
**Tier:** 0

In F767's flow, `t-clamp` serves FR-1 only and `t-sub` serves FR-2. rev reviewed t-clamp twice (`run-82e6d2001130`, `run-02929cb026e6`). Both times it called `mcp__agentweave__read_spec_document`, read FR-1 and FR-2, and sent the task back: "the specification requires TWO requirements to be satisfied: FR-1 (clamp) and FR-2 (sub). The sub(a, b) function is entirely missing". Both rejected evidence pieces carry that as their reason. The review briefing does scope the work ("Under review: Fix clamp upper bound ... Acceptance criteria: a-clamp", and "Your verdict decides this task's evidence (ev-... for FR-1)"). But nothing says that FR-2 belongs to another task, and `read_spec_document` returns the whole document with no mark on which requirements the reviewed task serves. The builder then gave in: it merged master (which by then held t-sub's work) and recorded FR-2 evidence on t-clamp, and the third review approved. That stray evidence is the source of the "Not merged -- 24638934 already in master" line in F769. Two wasted review rounds (about $0.26 of Haiku) and a builder pushed outside its task. F606 records the same misjudgement by a tester ("it judged the *other* task's FR-2").

Expected: the review briefing adds one line: "This task serves FR-1. The document's other requirements (FR-2) belong to other tasks (Add sub(), task-...): do not send this task back for them." A `read_spec_document` from a run reviewing a task marks which requirements that task serves. Failing test: the review briefing for a task serving FR-1 of a two-requirement document names FR-2 as another task's. Seam: Flows & review (review briefing) x Spec documents (read_spec_document).

## F772 (C) -- Land on a task with awaiting evidence also says its commit is "on neither master nor inside any commit the accepted evidence names" and asks the author to record evidence they already recorded

**Status:** fixed 2026-10-21 (night iteration 22, Tier 0, 9db0fa8). `GateRefusal._unlanded_detail` returns nothing when every commit in the `unlanded` entry is named by a piece in `unaccepted`, so the 409 message carries only "nobody has judged it ... accept the evidence"; the body's `unlanded` list and `refuses` are unchanged. A commit no awaiting piece names (or nothing awaiting) keeps the paragraph. `hub/tests/test_land_gate_does_not_ask_for_evidence_already_recorded.py` (the awaiting-piece case failed before; 4 tests). Not re-seen on a live Hub: the gate object with the route's field shapes stands in (labelled). Found in the tasks sweep (`scripts/drive/s1019_tasks.py`, scratch Hub :8170).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes -- repro below.
**Tier:** 0

F767's t-sub was completed by rev, and its evidence `ev-f2583f4de03b` was awaiting, naming `24638934` on `agentweave/task/task-960d7005a969`. `POST /tasks/{id}/land` answered 409 `gate_unsatisfied`, with `unaccepted` (that piece, remedy "accept the evidence") and `unlanded` (`commits: ["24638934..."]`, the same commit). The message has both paragraphs. The first is right: "nobody has judged it: FR-2 at 24638934ec1a ... accept the evidence". The second, from `_unlanded_detail` (`hub/hub/requirement_gate.py:414`), says: "commit 24638934ec1a is on neither master nor inside any commit the accepted evidence names ... What clears it is evidence recorded from the task's own checkout ... Ask the task's author to record it, accept it, and approve again; or send the task back". The author had already recorded exactly that. Accepting the piece cleared both paragraphs at once. The landing then needed one more retry while the checks ran, then 200.

Expected: when every unlanded commit is named by an awaiting piece in `unaccepted`, leave the unlanded paragraph out, because accepting is the whole remedy. Failing test: a gate with one awaiting piece on the task branch's tip produces no "Ask the task's author to record it" sentence. Seam: Worktrees & integration (land gate).

## F773 (C) -- a flow task's checks never run while it waits for review: the reviewer judges without them, and its approval is first refused "checks are still running"

**Status:** fixed a8bbbde 2026-10-21 (night iteration 23, Tier 0). `project_checks.request_run`, resolving its own targets, falls back to `task_integration.review_target` when `merge_targets` is empty and the task is `completed`/`under_review`, so `_after_run` starts a run on the commit the review will be given (the approval gate passes its own targets and is untouched). `hub/tests/test_a_flow_tasks_checks_run_while_it_waits_for_review.py` (failed first: no run; a flow task with no evidence naming a commit is still not checked); project-checks files 53 passed. Not re-seen with a live Haiku turn (labelled). Original report: open 2026-10-19. Found in the tasks sweep (`scripts/drive/s1019_tasks.py`, scratch Hub :8170, real Haiku turns).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes -- repro below.
**Tier:** 0

The project has one check configured (`py -3.11 -m pytest -q tests`) and `main_branch: master`. A flow task completed by a real turn got no check run: `GET /tasks/{id}/checks` stayed `{"configured": true, "runs": []}` through three build-and-review rounds of t-clamp, and the drawer read "Checks have not run". `project_checks._after_run` calls `request_run`, which takes its targets from `task_integration.merge_targets`. Where evidence governs, that is **accepted** evidence only (`task_integration.py:516-518`), and a just-completed flow task's evidence is awaiting, so `request_run` returns `None` before creating a run. The first run starts only from the approval gate. rev's verdict `approved` (`run-40aaf30388a5`) was refused: "The approval is blocked because checks are still running. Let me wait for them to complete and retry". The check ran at 08:58:28, after the verdict, and the approval landed on retry at 08:58:39. A documentless task in the same project got its run at the end of the turn, as `project_checks`' docstring says ("when a turn bound to a completed task ends").

Expected: at the end of a run bound to a completed, evidence-governed task, the checks run on the commit the review will be given (`review_target`, the newest evidence naming a commit). The reviewer's briefing and the drawer then carry a result, and the verdict is not refused for a run nobody started. Failing test: `project_checks._after_run` for a completed flow task with one awaiting piece naming a commit on the task branch creates a `TaskCheckRun`. Seam: Worktrees & integration (project checks) x Flows & review.

## F774 (B) -- `POST /session/sync` deletes an agent that holds an in-progress task and a live run, answers 200, and a payload with no `agents` key deletes every agent

**Status:** fixed 2026-10-20 (night iteration 12, Tier 0). `POST /session/sync` now refuses (409 `agent_removal_under_held_work`, `held: {runs, tasks}`, the shape of `isolation_change_under_held_work`) a payload that would delete an agent with a live turn or a task not yet `approved`/`rejected`, before anything is written (`launchability.held_work` shared with the isolation guard, `agent_removal_refusal`); a payload with no `agents` key leaves the roster alone (so `{"data": {"mode": "peer"}}` no longer deletes every agent or loses runner/charter bindings), and its answer lists the roster as it stands. An explicit `agents: {}` is still a replace. Four tests in `hub/tests/test_session_sync.py` (two failed before). `test_an_author_asking_to_review_is_told_it_is_the_author` relied on the deletion (its roster sync dropped the task holders) and now adds its agent with `add_agent`. Driven on scratch :8120 (`scripts/drive/d1020_f774_sync_keeps_held_agents.py`, real Haiku turn mid-sleep holding an in_progress task): omit -> 409 naming run and task, roster kept; mode=peer -> 200, both agents and builder's runner kept; a `completed` task still holds its agent. Found 2026-10-19 in the ledger sweep (`scripts/drive/s1019_ledger_p4.py`, scratch Hub :8180, real Haiku turns).
**Source:** drive
**Theme:** Agents
**Ready:** yes -- repro below.
**Tier:** 0

builder held `task-06d192c080c9` (`in_progress`) and was 8 s into a live run (`run-468c7ab733a3`, a 100 s sleep) when `POST /api/v1/projects/<p>/session/sync {"data": {"agents": {"rev": {}}}}` answered `200 {"ok": true, "agents": ["rev"]}`. builder's `agents` row was gone (`GET /agents` -> `["rev"]`). Nothing refused, and nothing named the task or the run. The run went on: it committed, and its `update_task` moved the task to `completed` as an agent that no longer existed. The task still reads `assignee: builder`, and builder's two open conversations stay open. A trigger for builder then answers 409 "builder is not an agent in this project". Re-creating builder with `POST /agents` (201) re-attaches all of it by name. The worse case is `{"data": {"mode": "peer"}}`: no `agents` key, so `agents_data = body.data.get("agents", {})` is empty, and the route answers `200 {"ok": true, "agents": []}` with **every** agent deleted. Re-syncing the names (`{"agents": {"builder": {}, "rev": {}}}`) brings the rows back with `runner_id: null, charter_id: null`: each agent's binding is lost.

The route's own docstring says no caller remains except tests (`hub/hub/api/v1/session_sync.py:1-17`). The F242 fix added `isolation_change_refusal` for agents the payload *names* (`:68-91`), but omitted agents are deleted with no check (`:136-142`).

Expected: deleting an agent through sync is refused, 409 with the same shape as `isolation_change_under_held_work`, while it has a live run or an unfinished task, naming them. A payload without `agents` is either refused (422) or leaves the roster alone; it never empties it. (Retiring the route's delete half altogether is the cleaner alternative, since no caller needs it. That choice is the operator's if the night prefers it.) Failing test: in `hub/tests/test_session_sync*.py`, sync omitting an agent with an `in_progress` task, and a running `Run`, -> 409 with the row kept; `{"data": {}}` -> roster unchanged. Seam: Agents x Runs x Tasks.

## F775 (B) -- a checkpoint says "No files recorded as changed" when the agent committed its own work, because `files_changed` reads only the Hub's auto-snapshot commit

**Status:** fixed 2026-10-20 (night iteration 13, Tier 0). `checkpoints._files_from_runs` also reads the turn's own commits: `worktrees.files_committed_between(repo_root, branch, started_at, ended_at)`, the branch being the checkout's checked-out one while it exists (a detached review writes nothing), else the task's branch, else the agent's. Commit time is the only link to a turn, so two turns sharing one branch at once each see the other's commits. Test in `test_checkpoint_record.py` (failed first; a commit three hours before the turn is excluded). Driven on scratch :8130, real Haiku turn that committed `hello.txt` with a clean tree and `snapshot_commit_sha` NULL: the checkpoint's `files_changed` is `["hello.txt"]`. Original report: open 2026-10-19. Found in the ledger sweep (`scripts/drive/s1019_ledger_p2.py`, `_p3.py`).
**Source:** drive
**Theme:** Checkpoints
**Ready:** yes -- repro below.
**Tier:** 0

builder's real turn (`run-af8019ec2ad9`, bound to `task-5f15fb870841`) fixed `src/calc.py` and committed it (`f8ee91b Fix add()...`, 1 file changed, on `agentweave/task/task-5f15fb870841`), as it was asked to. `POST /conversations/conv-bfc7c908389f/checkpoint` -> 201 with `"files_changed": []`. The rendered checkpoint, which is what the successor receives, reads "## Files changed\n\n_No files recorded as changed._", and the Checkpoints sheet shows the same. The DB has `runs.snapshot_commit_sha = NULL` for all three runs. `_files_from_runs` (`hub/hub/checkpoints.py:227-255`) reads only that column, and it is set only when `snapshot_worktree` commits a dirty tree (`hub/hub/api/v1/agent_trigger.py:3509-3512`, "NULL when the turn changed nothing"). An agent that commits its own work leaves the tree clean, so its turn "changed nothing" to the checkpoint. Agents are routinely told to commit, and Haiku does.

Expected: a turn's changed files include its own commits. For example, take the commits on the run's branch between `started_at` and `ended_at` (`git log <branch> --since --until --name-only`, from the repo root as the docstring argues), plus the snapshot commit. No migration is needed for that reading. Failing test: a run whose agent commits in its checkout with a clean tree at the end; `generate_checkpoint(...).files_changed` names the file. Seam: Checkpoints x Worktrees.

## F776 (C) -- a turn bound to a task already `completed` (waiting for its reviewer) records an open divergence, "builder ended completed with Fix add() still completed"

**Status:** fixed bc6715d 2026-10-21 (night iteration 24, Tier 0). `evaluate_run_end`'s non-review branch returns None for a task in `completed`/`under_review` (same reasoning as the F548 terminal exclusion), before the policy and `retry` are consulted. `hub/tests/test_run_divergence.py::test_a_turn_bound_to_a_task_waiting_for_its_reviewer_records_nothing` (4 cases, surface/retry x completed/under_review; failed first). Two older fixtures built an open divergence on a completed task by the operator completing it under a live run, which is now correctly nothing; `_completed_with_an_open_divergence` (shared with `test_an_event_is_announced_after_commit.py`) now records the divergence at `in_progress`, then writes the status directly. Hub slice 813 passed. Not re-seen on a live Hub (labelled). Original report: open 2026-10-19. Found in the ledger sweep (`scripts/drive/s1019_ledger_p2.py`, `_p3.py`, `_ui.py`).
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes -- repro below.
**Tier:** 0

builder completed `task-5f15fb870841` and messaged rev "no reply needed"; rev replied anyway. builder's acknowledgement turn (`run-85c693116220`, 9 s, bound to the same task through its conversation) ended with the task still `completed`. That recorded `div-71d745fc8951` (`policy_applied: surface`, `outcome: surfaced`, `task_status_at_end: completed`, never resolved). The Activity tab's Ledger counts it as "Divergences 1, 1 open" and shows "builder ended completed with Fix add() still completed", and the task story lists it too. Nothing was neglected: a completed task waits for a reviewer, and its author can make no move on it (`completed` -> `under_review`/`rejected` are not the author's). `evaluate_run_end` (`hub/hub/run_divergence.py:920-1062`) excludes `blocked` and terminal statuses, but not the awaiting-handoff band (`completed`, `under_review`) for a run that is not a review.

Expected: a non-review run whose task is in `completed`/`under_review` at its end records no divergence (the same reasoning as the F548 terminal exclusion). Failing test: in `hub/tests/test_run_divergence*.py`, a run bound to a `completed` task, by its author, not a review entry -> `evaluate_run_end` returns None and no `RunDivergence` row exists. Seam: Runs x Tasks (divergence) x the Ledger.

## F777 (B) -- a non-ASCII file name reaches the `@` picker git-quoted (`"notes caf\303\251.md"`), and neither that string nor the real name can be read

**Status:** fixed 2026-10-20 (night iteration 13, Tier 0). `list_workspace_paths` runs `git -c core.quotepath=off ls-files` and decodes UTF-8, so the picker lists `notes café.md` as itself. Test beside the existing path tests (failed first). Driven on scratch :8130: `/workspace/paths` listed `notes café.md`; `/workspace/file` reads it. Original report: open 2026-10-19. Found in the ledger sweep (`scripts/drive/s1019_ledger.py`, `_ui.py`).
**Source:** drive
**Theme:** Conversations & composer
**Ready:** yes -- repro below.
**Tier:** 0

A project file `notes café.md` (untracked, not ignored). `GET /workspace/paths` -> `["\"notes caf\\303\\251.md\"", ".gitignore", "README.md", ...]`. `GET /workspace/file?path=notes%20caf%C3%A9.md` -> 404 "path not found in this workspace", and so does `?path=` the listed string itself (404: it passes membership, then no such file exists). In the browser, typing `@notes` in the composer offers `"notes caf\303\251.md"`, and picking it writes `look at @"\"notes caf\303\251.md\""` into the composer. `list_workspace_paths` (`hub/hub/workspace_paths.py:31-38`) runs `git ls-files` with `core.quotepath` left on and `text=True` with no `encoding` (cp1252 here). This is the same root cause as F760, in a different module: F760's fix sketch names only `requirement_evidence._git`.

Expected: `git -c core.quotepath=off ls-files ...` (or `-z`), decoded as UTF-8, so the listing carries `notes café.md`, and `/workspace/file` and the `@` insert work with it. Failing test: `hub/tests/test_workspace_paths*.py`, a repo with `café.md` -> the listing contains `"café.md"`, and `read_workspace_file` returns its content. Seam: Conversations & composer x the workspace listing.

## F780 (B) -- Copilot's long context tier cannot be chosen: over ACP neither `--context long_context` nor a persisted `contextTier` changes the window

**Status:** fixed 2026-10-19 (Tier 0, by removal). A `context` control (Standard / Long 1M, rendered as `--context {value}`) was added to `CATALOG["copilot"]` the same morning and reached the argv (traced: conversation `runtime_overrides` -> `control_overrides` -> `build_acp_argv`), but the window did not move. Drive 2026-10-19, work PC, Copilot CLI 1.0.99-2, ACP `session/prompt` "Reply with just OK.": `claude-sonnet-5` reported `usage_update.size` 200,000 with `--context long_context` and 200,000 with `settings.json` `{"contextTier": "long_context"}` in the config dir; `claude-haiku-5.5` 100,000 either way; the operator's `claude-opus-5.5` Architect run carried the flag and showed 200k. `session/new` offers config options `mode`, `model`, `reasoning_effort`, `allow_all` only, so there is no ACP route. The control is removed (it changed nothing and read as a promise), and `validate_overrides(stored_controls=)` now drops a control that left the catalog when it arrives with its stored value, since the composer sends stored overrides back with every message (`test_model_catalog.py`: `test_copilot_declares_no_context_tier`, `test_a_stored_control_that_left_the_catalog_is_dropped_not_refused`). Re-add the control when a Copilot build honours the tier over ACP; the probe is the same one-line prompt, comparing `usage_update.size`.
**Source:** drive
**Theme:** Runners & models

## F781 (A) -- the Workspace judge reads `Select-String`'s pattern as a path: `-Pattern '- \[ \]'` is refused as "'\' is outside your workspace", and the Copilot turn ends

**Status:** fixed 2026-10-19 (Tier 0). The operator's FinOps Architect (Copilot, a spec turn, so judged under Workspace whatever the conversation's posture) ran `Select-String -Path openspec\changes\...\tasks.md -Pattern '- \[ \]'`; it was refused in both dialects, the refusal continuation (`REFUSAL_CONTINUATIONS_PER_TURN = 1`) was already spent, and the turn ended with no reply (`copilot.turn_ended_on_refusal`, run `run-67cbae2e7804`). F661 exempted only an expression-mode `-match` operand; this is the same pattern in command mode. `_select_string_patterns` (`hub/hub/mcp_server.py`) exempts, in both dialects, a quoted literal that is `-Pattern`'s value (unambiguous prefix) or, with `-Pattern` unnamed, the first positional argument; nothing positional after a parameter it does not know, an ambiguous prefix (`-Pa`) or a glued `-x:value`. `-Path`, `-LiteralPath` and every other operand are judged as before. `hub/tests/test_select_string_pattern_is_not_a_path.py`: the allow rows failed before the fix (a double-quoted pattern holding a backslash is exempt in the PowerShell reading only: bash's lexer does not count it as one plain literal, so a both-dialect Copilot call still judges it); the deny rows (outside paths through `-Path`, positional, `-LiteralPath`, `-Pa`, an unknown parameter, a later statement, another command's `-Pattern`) pass before and after. Related: F661, F696, F755, F780.
**Source:** drive
**Theme:** Permissions & sandbox

## F783 (A) -- the 600 s turn clock keeps running while `ask_user` waits for the operator: the turn fails with its question still open, the retry asks the same question again, and the operator's answer to the first card reaches the agent ten minutes later

**Status:** fixed 2026-10-20 (night iteration 10, change `the-turn-clock-counts-work-not-waiting`, folded into `agent-capability-plane`): the Copilot turn deadline stops counting while the run waits on a blocking `ask_user` (from the ask until it is answered, declined or its wait is reported ended, never past `wait_expires_at`) or on an open Ask me card (`hub/hub/run_waits.py`). Driven on scratch :8110 (`c1019_copilot_s4.py ask`, real Copilot): the turn lived 627 s on the open card, the answer at 620 s came back as the tool result in the same run, which completed 7 s later; one question asked, no queued answer. (The run was the second attempt: the first failed at startup under load, F789.) Found 2026-10-19 in the Copilot stall drive (`scripts/drive/c1019_copilot_s4.py ask`, scratch Hub :8110, real turns).
**Source:** drive
**Theme:** Questions
**Ready:** yes -- repro below.
**Tier:** 1

Agent `asker` had `question_timeout_seconds: 600`, the most the Hub accepts (`MAX_WAITING_SECONDS = 600`, `hub/hub/api/v1/agents.py:2798`), which equals the fixed turn deadline (F782). Its first call was `ask_user` (`q-6289e8817f0b`, created 18:01:16, `wait_expires_at` 18:11:16). Nobody answered. At 18:11:13, 3 s before the question's own wait ended, the turn deadline killed the run: `run-68747a9a68a2` `failed`, "Copilot did not finish the turn within 600 s", tool card "agentweave-ask_user interrupted". The question row stayed open (`answered 0`, `wait_ended_at NULL`), and the Questions route lists it with `asker_waiting: false`. The input was requeued, and the retry (`run-88ac0afdf99c`, resumed session) asked again: `q-0c201324c8fb`, the same text and options. The operator now had two identical cards. Answering the first one at 18:11:40 (`PATCH /questions/q-6289...` 200) made a new queue entry ("Question: ... Answer: double", `entry-1184980e3fdf`) that **queued behind the retry run**, which was blocked on the duplicate card. That run also died at the deadline (18:21:17). Only the third attempt (`run-6d9a4558d3f5`, a fresh session, both entries) saw the answer and finished in 13 s. Result: an answer given 24 s after the first failure took 9 min 38 s to reach the agent. The run cost three runs and three premium requests, and `q-0c201324c8fb` is still open with nobody waiting (seen at cleanup). With the default 240 s wait the same cut happens to any question asked after about six minutes of work, and to two questions in one turn. Permission cards (120 s) eat the same clock (F784).

Expected: time the run spends blocked on the operator (an open `ask_user`, a pending permission card) does not count against the turn deadline. At the least, the question's wait is clamped to the turn's remaining time, so the tool returns "no answer yet" before the deadline kills the turn. A run that ends leaves no question open that nothing waits for: it is marked ended, or its answer is delivered into the retry rather than behind it. A retry does not ask again when an answer to that question has already arrived. Failing test: in `hub/tests/test_copilot_acp*.py`, a fake ACP session whose tool call waits on `ask_user` past `turn_timeout` is not failed while the question is open. Or, in `hub/tests/test_questions*.py`: after a run ends `failed`, its unanswered questions read `asker_waiting: false` **and** carry `wait_ended_at`, and an answer to one is delivered as input to the next turn of the same conversation ahead of the requeued entry. Seam: Questions x Runs (Copilot deadline) x Inbound queue & messages.

## F784 (B) -- under Ask me, a card nobody answers ends a Copilot turn `completed` with no reply after 4 minutes: the expiry is told to the agent as "the operator did not approve", and its retry raises a second card for the same command

**Status:** fixed 2026-10-20 (night iteration 11, Tier 0). `_await_operator_permission` now stamps `subject["card_status"]` (`expired`/`denied`) and `copilot_acp` records it on the refusal, so `refusal_continuation_text` says "Nobody answered the operator's approval card ... Do not ask for it again this turn ... end your turn saying what you need approved" and the notices carry "nobody answered the approval card in time" instead of "did not approve". A Deny keeps the old wording. Driven on scratch :8110 (`c1019_copilot_s4.py card`, real Copilot): one card (was two), expired after 120 s, and the turn ended with the agent's reply "I need approval to run `git log --oneline -3`..." (was no reply). The turn still reads `completed`: the hold-as-waiting-for-approval route stays unbuilt. Original report: open 2026-10-19. Found in the Copilot stall drive (`scripts/drive/c1019_copilot_s4.py card`, scratch Hub :8110, real turn).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes -- repro below.
**Tier:** 0

`cop` under `manual` was asked to run `git log --oneline -3`. Card `perm-f2cb351664d2` was left alone and became `expired` after 120 s (`decided_by: NULL`). Copilot ended the prompt. The Hub's one continuation (`copilot.refusal_continued`) said "The operator did not approve your last tool call (a command)... Continue the task another way, or call ask_user if you cannot." Haiku's thinking was: "Let me try the powershell command again - maybe there was a transient issue". So it asked for the same command, which raised card `perm-7949384a271f`. That card also expired after 120 s, and the turn ended (`copilot.turn_ended_on_refusal`, "The turn ended on a refused call (a command): the operator did not approve it."). `run-4f879e16b2d3` reads `completed`, exit 0, and the conversation has no reply. An operator who stepped away for four minutes comes back to a finished turn that did nothing and two expired cards. Their message is spent, and nothing invites them to approve and continue. The Hub knows the difference: `permission_requests.status` is `expired`, not `denied`. But `refusal_continuation_text` (`hub/hub/copilot_acp.py:2923-2932`) has one sentence for both ("the card cannot tell a Deny from expiry", its docstring), and the closing notice uses the same words.

Expected: an expired card is not a refusal. Either the turn ends as *waiting for approval* (not `completed`), with its input kept and a Continue (the `awaits_continue` path), or the continuation says "your request timed out waiting for the operator; do not ask for it again this turn; say in your reply what you need approved". The notice says "nobody answered the card in 120 s", not "did not approve". Failing test: `refusal_continuation_text` for a refusal whose card status is `expired` differs from the Deny text and does not say "did not approve" (and, if the hold is taken, `_await_prompt` for an expired card gives a non-`completed` outcome). Seam: Permissions & sandbox x Runs (Copilot ACP).

## F785 (B) -- the refusal continuation says "continue another way", and Haiku's other way is the same path through another tool: the judge refuses it again and the task turn ends with no reply

**Status:** fixed 2026-10-20 (night iteration 11, Tier 0). `refusal_continuation_text` for a Hub refusal whose reason is "is outside your workspace" says any tool on that path is refused the same way, not to retry it, and to end the turn saying what is needed from the operator. Driven on scratch :8110 (`c1019_copilot_s2.py`, real Copilot): one refusal, no second attempt through powershell, and the reply "I cannot access the file outside my workspace. Please provide the requirement ... or copy it into my workspace" (was no reply). One sample. Original report: open 2026-10-19. Found in the Copilot stall drive (`scripts/drive/c1019_copilot_s2.py`, scratch Hub :8110, real turn).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes -- repro below; behavioural, 1 of 1 (and F784's card case is the same shape).
**Tier:** 0

A task turn (`task-dc7c3489de12`, default Workspace posture) was asked to apply a requirement kept in `C:\Users\huida\Documents\aw-c1019-outside\notes.txt`, outside the workspace. Copilot's `view` of it was refused ("... is outside your workspace", `permission_denied`, `decided_by: runtime`). The continuation followed (`copilot.refusal_continued`). Haiku's thinking: "Let me try using powershell to read it instead, since the Hub's file tool refuses to read outside the workspace. That might work since powershell has more flexibility." `Get-Content "...notes.txt"` was refused with the same reason 2.7 s later, and the turn ended (`copilot.turn_ended_on_refusal`). `run-394914b24ee6` is `completed` with no reply and the task is still `in_progress`. A divergence was surfaced, and it does name the refusal. The agent never told the operator the one thing that would unblock it ("copy notes.txt into the project, or paste it"). With **Hide diagnostics** on, the conversation shows only a failed tool card and "Run completed". The continuation text (`hub/hub/copilot_acp.py:2932`, "Continue the task another way, or call ask_user if you cannot") reads to the model as "use a different tool". The judge judges the *path*, so every tool fails the same way, and the one continuation (`REFUSAL_CONTINUATIONS_PER_TURN = 1`, wpc1-c) is spent on a guaranteed second refusal.

Expected: when the refusal is a path outside the workspace, the continuation says so: "Any tool that reads or writes this path will be refused the same way. Do not retry it. Continue without it, or end your turn saying what you need from the operator." (For an operator Deny: "do not ask for the same call again.") A second refusal of the *same subject* (same path or command) after the continuation should not end the turn silently either: it ends with a Hub-written reply line in the conversation. Failing test: `refusal_continuation_text` for a `decided_by: runtime` refusal whose reason is "outside your workspace" contains "will be refused the same way" (or equivalent) and does not say "another way" alone. Related: F660 (the mechanism), F781/F661/F696 (refusals that should not happen at all). Seam: Permissions & sandbox x Runs (Copilot ACP).

## F786 (C) -- a Copilot turn that hits the 600 s deadline (or is cut by a Hub restart) records no premium request, though its prompt was sent and billed

**Status:** fixed 2026-10-20 (night iteration 11, Tier 0). `_send_and_wait` no longer breaks at the deadline: it sends the cancel and waits `CANCEL_GRACE_SECONDS` for the cancelled prompt's result, as a Stop does, then returns it as a cut (no result, `turn_timeout`, so a cancelled stop reason never reads as a Stop). Driven on scratch :8110 (`c1019_copilot_s3.py`, 700 s command, real Copilot): the cut run `run-81e71b87bb6c` recorded `premium_requests` 0.33 (the five earlier cuts: NULL), withdrawn with the turn-limit reason. Original report: open 2026-10-19. Found in the Copilot stall drive (scratch Hub :8110).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes -- repro below.
**Tier:** 0

`turn_usage.premium_requests` is NULL for all five timed-out runs (`run-c2e1184edfe9`, `run-d1044857d61a`, `run-23d84ec23d71`, `run-68747a9a68a2`, `run-88ac0afdf99c`) and for the restart-interrupted `run-187ca67f997a`. Each sent a `session/prompt` on `claude-haiku-4.5` (0.33 each, as every completed turn in the drive recorded). A stopped run, by contrast, did record 0.33 (`run-c7ca5e821643`). The difference is in `_send_and_wait` (`hub/hub/copilot_acp.py:2976-2979`). On Stop, the loop sends `session/cancel` and keeps polling up to `CANCEL_GRACE_SECONDS` (10 s) for the prompt's result, whose `usage` goes to the ledger. On the deadline it sends the cancel and `break`s at once, then cancels the prompt task, so the result that carries the usage is thrown away. In this drive, 1.65 of about 5 premium requests went uncounted. That is the same F665 gap in another place, and it falls exactly on the turns that fail (F782).

Expected: on the deadline, wait the same grace for the cancelled prompt's result before closing, as Stop does, so its `usage` is observed. Failing test: in `hub/tests/test_copilot_acp*.py`, a fake session that answers `session/cancel` with a result carrying `usage` after the deadline gives a ledger reading (premium requests not None). Seam: Runs (Copilot deadline) x Accounting & allowance.

## F789 (B) -- a Copilot run whose ACP startup request times out fails with an empty error: the run, its `run_failed` event and the conversation say nothing about why

**Status:** fixed 937ae0d 2026-10-21 (night iteration 13, Tier 0): `ACPProcess.request` turns a timed-out request into a `CopilotACPError` reading "Copilot did not answer `initialize` within 30 s" (method and stderr tail attached), and both the pre-spawn `run.error` and `_transport_failure_fields` fall back to `type(exc).__name__`, so a bare timeout is never empty. Driven: a real stand-in child process that never answers (`test_a_copilot_startup_timeout_names_itself.py`) and the trigger route with a scripted `run_turn` raising each shape (`test_copilot_trigger.py`); both failed before. Not driven against a loaded real Copilot CLI (labelled). Found in the F782/F783 acceptance drive (`scripts/drive/c1019_copilot_s4.py ask`, `c1019_copilot_s3.py`, scratch Hub :8110, `proj-ecfcc899dc34`, real Copilot CLI) while the full Hub suite ran with `-n auto` on the same machine.
**Source:** drive
**Theme:** Runs
**Ready:** yes -- the seam and the repro are below.
**Tier:** 0

Under CPU load, three of four first attempts (`run-331d557c454e`, `run-20bf26c760d4`, `run-2cb5fc049d43`) ended `failed` about 33-35 s after they started, before the prompt was sent. Each had `error = ''`, a `run_failed` event with `"error": ""`, `exit_code`, `method` and `stderr_tail` all null, and no agent output. The 33 s matches spawn plus `DEFAULT_REQUEST_TIMEOUT_SECONDS` (30 s, `codex_appserver.py`) on an ACP startup request: `ACPProcess.request` raises `asyncio.TimeoutError` from `asyncio.wait_for` (`copilot_acp.py`, `request`), and `str(asyncio.TimeoutError())` is `''`. The RPC executor's pre-spawn branch writes `run.error = run_secrets.scrub(run_id, str(exc))` (`hub/hub/api/v1/agent_trigger.py:4534`), and `_transport_failure_fields` broadcasts `"error": str(exc)` (`:2686`). The sibling Claude path at `:2920` already writes `str(exc) or type(exc).__name__`. Each failure also spent one of the entry's three delivery attempts, so a slow machine can lose an operator's message with nothing on screen saying why.

Expected: a pre-prompt timeout fails with an error naming what timed out, for example "Copilot did not answer `initialize` within 30 s", by raising a `CopilotACPError`/`AppServerError` carrying `method` from `ACPProcess.request` on timeout. At the least, the error is never empty (`str(exc) or type(exc).__name__` in both places). Failing test: a fake ACP process that never answers `initialize`, with a 0.1 s request timeout, makes the executor record a run whose `error` is non-empty and names the method. Seam: Runs (Copilot ACP startup) x Runs (RPC executor failure record).

## F790 (B) -- a run's `aw.permission_wait` span stores the tool call's arguments unredacted, while the same call's `execute_tool` span redacts them; the download and the OTLP push carry the raw value

**Status:** fixed a0fed3c 2026-10-21 (night iteration 14). The wait span's arguments pass `runner_events.redact_secrets` before `traces.redact`, as the tool event's input does; test `test_trace_seams.py::test_a_permission_wait_redacts_its_arguments_as_the_tool_call_does` failed first. Drive (scratch Hub :8152, `scripts/drive/s1021_f790_drive.py`): a real Haiku turn under `manual`, card approved, run-8fb3f84d26c5 completed; `execute_tool PowerShell` and `aw.permission_wait PowerShell` (same call id) both read `print('build', '<redacted>')` in `/traces/by-run` and in the OTLP export; the permission row keeps the raw value. The prompt, queue content and model text still carry the token, as the conversation's own text rows do (FR-3 binds spans to the redaction recorded output passes), so that is not this finding. Opened 2026-10-20. Found by the day sweep `sweep-traces-sweep` (scratch Hub :8141, `scripts/drive/s1020_traces.py`).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

Repro: a Claude Haiku agent under `manual` (`POST /projects/{p}/agent/trigger` with `overrides.permission_mode=manual`), told to run `py -3.11 -c "print('build', 'Q7r8S9t0U1v2W3x4Y5z6A7b8C9d0E1f2G3h4')"`; the operator approves the card (`POST /permission-requests/{id}/decide {"allow": true}`). Then `GET /projects/{p}/traces/by-run/run-80339e599c95`:
- `execute_tool PowerShell`: `gen_ai.tool.call.arguments` = `{"command": "py -3.11 -c \"print('build', '<redacted>')\"", ...}`, and the result `build <redacted>`.
- `aw.permission_wait PowerShell` (same `gen_ai.tool.call.id` toolu_011bYh7R...): `gen_ai.tool.call.arguments` = `{"command": "py -3.11 -c \"print('build', 'Q7r8S9t0U1v2W3x4Y5z6A7b8C9d0E1f2G3h4')\"", ...}`.
- The app's **Download OTLP JSON** file (Settings -> Traces) contains the 36-character value: `"Q7r8S9t0U1v2W3x4Y5z6A7b8C9d0E1f2G3h4" in file` -> True. The span detail shows it behind the collapsed "Content gen_ai.tool.call.arguments 130 chars".

Cause: the `execute_tool` span copies the tool event's payload, which `runner_events.redact_secrets` already scrubbed (the high-entropy catch-all included). `traces.finish_run` builds the permission span from `PermissionRequest.tool_input` with `traces.redact` only (`hub/hub/traces.py:631`: `redact(run_id, request.tool_input or {})`), i.e. registered values plus named patterns, so a GitHub token, an AWS secret or any other unnamed credential passes. Requirement `trace-content-is-redacted` (FR-3 of `a-run-is-a-trace-you-can-export`): "Every string a span stores or exports SHALL first pass the redaction recorded output passes". The tool event is that recorded output, so the two spans of one call should agree.

Expected: the permission span's arguments pass the same redaction as the tool event's input (`runner_events.redact_secrets`, then `traces.redact`). Failing test at the seam: in `hub/tests/test_a_run_is_one_trace.py` (the permission-wait test near line 144), give the request a `tool_input` holding a 40-character mixed-case token and assert the `aw.permission_wait` span's `gen_ai.tool.call.arguments` does not contain it. The `permission_requests` row keeps the raw input (the card needs it); only the span changes. Seam: Traces x Permissions & sandbox.

## F791 (C) -- every run's trace shows two routine `git rev-parse --verify --quiet MERGE_HEAD` probes as red error spans

**Status:** fixed 2a060e9 2026-10-21 night iteration 25 (Tier 0). `traces.run` and `traces.exited` take `ok_codes` (default `(0,)`); `worktrees._run_git` passes it through and the two `MERGE_HEAD` probes (`_is_mid_merge`, `_merge_head`) pass `(0, 1)`, so their exit code 1 is recorded on the span with status `ok`. Any other command, and any other exit of git, is still an `error` span. Tests `hub/tests/test_a_merge_head_probe_is_not_a_failed_command.py` (failed before: span status `error`; 2 cases, the second pins that another failing git command stays an error); two fakes of `_run_git` in `test_a_task_checkout_catches_up.py` take the new keyword. Drive: real git repository and real subprocess under a current work span; not re-seen in the app's trace drawer (labelled). Slice `-k "trace or worktree or isolation or merge or checkout or review"` 853 passed after the fakes were fixed. Found by the day sweep `sweep-traces-sweep`.
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

Repro: any completed Claude turn on a clean project (four drove here: run-82a990b9d101, run-80339e599c95, run-e29790a7fee5, run-0f1b472b91c7). `GET /traces/by-run/{run}` lists four `aw.command` spans at the end of every one; the first two are `git -c core.quotepath=off rev-parse --verify --quiet MERGE_HEAD`, `process.exit.code` 1, `status` `error`, `status_message` "exit code 1". In the app's trace drawer, both rows have `data-status="error"` and render in red (`TraceWaterfall.tsx:109`), in a run whose root reads `ok`. Exit 1 from `--verify --quiet` is the answer "no merge in progress": that is the normal case, not a failure. An operator who opens any trace to look for what went wrong is first shown two false errors.

Cause: `traces.run()` -> `exited(span, result.returncode)` treats every non-zero exit as an error (`hub/hub/traces.py:1055`); the caller that probes `MERGE_HEAD` knows that 1 means "absent".

Expected: a probe whose non-zero exit is an answer records its exit code without error status. For example, `exited(span, code, expected=(0, 1))`, or the probe passes `ok_codes` through `traces.run`. The callers are `hub/hub/worktrees.py:554` and `:560`, `_run_git(worktree, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False)`; their `check=False` already says that a non-zero exit is an answer there. Failing test: the run-finish path on a clean checkout leaves no `aw.command` span with `status == "error"` (`hub/tests/test_trace_seams.py`). Seam: Traces x Worktrees & integration (the end-of-run checkout probe).

## F792 (C) -- a stopped run's trace reads `ok`, and its stop is recorded as an `aw.status.completed` event; the trace list and drawer cannot tell a stopped turn from a completed one

**Status:** fixed 17c14d5 (iteration 26, Tier 0). `finish_run` leaves a stopped/interrupted/abandoned root `unset` with a message naming how it ended; the trace summary carries `run_status`; the drawer header and the Traces list show it. Left alone: the `aw.status.completed` event name for a stop's status line. Drive: real route + real finish_run in tests, not re-seen in a live Hub drawer. Was: open 2026-10-20. Found by the day sweep `sweep-traces-sweep` (scratch Hub :8141).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

Repro: trigger a turn that runs a 150 s `time.sleep` loop under `workspace`; once its tool call is recorded, `POST /projects/{p}/agent/tracer/stop` -> 200 `"status": "stopping"`. The run ends `stopped` (exit 2), and the conversation shows "Turn stopped · 09:29". `GET /traces/by-run/run-e29790a7fee5`: root `status` `ok`, `status_message` null; root events `run_started, context_warning, run_stopped, aw.status.completed` (summary "Run stopped (exit 2)."). The `execute_tool PowerShell` span is correctly `error` "PowerShell interrupted". In the app, the trace drawer's header reads "ok tracer ...", and Settings -> Traces lists the run with no badge, the same as a completed run. Only the attribute `aw.run.status = stopped` says otherwise.

Cause: `traces.finish_run` sets `error` only for `run.status == "failed"` and `ok` for everything else (`hub/hub/traces.py:710-714`), so `stopped`, `interrupted` and `abandoned` all read as success. The status-event name is the runner phase (`aw.status.{phase}`, `:434`), and the stop's status line is written with phase `completed`.

Expected: a run that did not complete is not `ok`. Leave the status `unset` with `status_message` "stopped by the operator" (OTel keeps `error` for failures), and let the drawer header and the list show the run's own status (`aw.run.status`), so a stopped turn reads "stopped" in both places. Failing test: `finish_run` on a run with status `stopped` leaves the root not `ok` and with a message naming the stop. Seam: Traces x Runs (stop).

## F793 (C) -- after the OTLP collector was down, a fixed endpoint receives nothing for up to 300 s while Settings -> Traces shows no error and "Never"

**Status:** fixed 2026-10-21 (night iteration 27, Tier 0, e850402). `trace_export.forget_backoff` runs when the settings route saves the endpoint, headers or enable flag; `test_saving_trace_settings_ends_the_backoff.py` (3 of 4 failed before). Drive: real route + real pusher against a live local receiver; not re-seen on a live Hub. Found by the day sweep `sweep-traces-sweep` (scratch Hub :8141).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

Repro: `PUT /projects/{p}/traces/settings {"otlp_endpoint": "http://127.0.0.1:9", "export_enabled": true}` (nothing listens) and leave it for about 12 minutes of normal operator writes. Settings then reads `last_error` "URLError: ... actively refused it", which is correct and legible. Now fix it the way the operator would: start a collector (`scripts/drive/otlp_receiver.py 4419`) and `PUT {"otlp_endpoint": "http://127.0.0.1:4419"}`, then disable and re-enable export. The response clears `last_error`, `last_export_at` stays null, and the screen reads "Never · 0 spans sent" with no error. A write made right after it reached the collector **176 s later**, measured by polling `GET /traces/settings` every 5 s. Nothing in between says that the Hub is waiting.

Cause: `trace_export` keeps per-project `_failures` / `_retry_after` in process memory, with backoff `push_interval() * 2**failures` capped at `MAX_BACKOFF_SECONDS = 300` (`hub/hub/trace_export.py:136-139`). `update_trace_settings` (`hub/hub/api/v1/traces.py`) resets `last_error` and `enabled_at` but not the backoff, so the old endpoint's failures delay the new endpoint.

Expected: saving the endpoint, its headers or the enable flag resets that project's backoff (`trace_export._failures.pop(p)`, `_retry_after.pop(p)`), so the next pass, within 5 s, tries the new settings. Failing test: after `push_project` fails three times against a dead URL, a settings PUT followed by `push_once()` posts to the new URL at once. Seam: Traces (settings route) x Traces (pusher).

## F794 (C) -- a shell or write call on a path inside a root granted for reading only is refused as "is outside your workspace", the same words as an ungranted path; neither the agent nor the operator is told the root is granted for the file-reading tool

**Status:** fixed 2026-10-21 (night iteration 28, Tier 0, 308121a). `_Reach` keeps the roots granted `read` that a non-read tool may not reach (`read_only`); `_judge_resolved` answers `_READ_ONLY_ROOT` (names the read grant, the file-reading tool, and that writing needs read and write) for a path in one. `test_a_read_only_root_refusal_says_so.py` (2 of 4 failed before; the read tool still allowed, an ungranted path still "outside your workspace"). Drive: `_decide` over real directories for Bash and Write; not re-seen in the Questions panel (labelled). The mcp_server copy a Hub spawns is pinned at its start, so a running Hub's agents get the wording on its next restart.
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

Repro: `PUT /projects/{p}/settings {"default_permission_mode": "workspace", "reach_grants": {"roots": [{"path": "C:\Users\huida\Documents\reach1020-read", "access": "read"}], "hosts": []}}`. A Claude turn (Haiku) asked to Read `...\reach1020-read\notes.txt`, then `cat` it in Bash, then Write a file there: Read allowed (the word came back), Bash and Write refused, `permission_denied` reasons `'C:/Users/huida/Documents/reach1020-read/notes.txt' is outside your workspace` and `'C:\Users\huida\Documents\reach1020-read\written.txt' is outside your workspace`. A Copilot turn's `Get-Content` on `...\reach1020-read\other.txt` was refused with the same words. The judge's decision is right (reach-D3: a read root covers read tools only); the sentence is wrong. The path is not merely outside the workspace: it is in a root the operator granted, for reading, and the call that would work is the file-reading tool. Haiku worked it out here only because the turn context names the read root; the operator reading the refusal in the Questions panel's permission decisions sees "outside your workspace" for a folder they granted and has nothing to tell them why.

Cause: `_judge_resolved` (`hub/hub/mcp_server.py:1660-1675`) asks `_in_granted_root(resolved)` against `_REACH`, which `_parse_reach` built with the read roots already dropped for a non-read tool (`hub/hub/mcp_server.py:1601-1606`), so a path in a read root falls through to `_resolves_elsewhere` and `_OUTSIDE`.

Expected: when a refused path lies in a root granted `read` and the tool is not a read tool, the reason says so and names what works: e.g. `'...\notes.txt' is in a folder granted for reading only: read it with your file-reading tool, not a shell command; writing there needs the operator to grant read and write`. Failing test: in `hub/tests/test_an_operator_sets_how_far_an_agent_reaches.py`, `_decide` for `Bash` `cat <read-root>/f` with `AW_REACH_GRANTS` naming that root `read` returns a deny whose reason names the read grant (today: `is outside your workspace`). Seam: Permissions & sandbox (workspace judge) x reach grants.

## F795 (C) -- an agent's granted-reach save the Hub refuses shows only "Could not save the granted reach."; the route's own detail is pydantic's raw dump with a docs URL

**Status:** fixed 2026-10-21 (night iteration 29, Tier 0, a2176e9). `reach.validated_grants` raises the `reach_grants.<field>: <message>` sentence (no pydantic dump, no docs URL), which the agent route's 400 carries as its detail; `ReachGrantsSetting` shows it through `readableApiError`, keeping the fixed sentence when the failure has none. `test_a_refused_agent_grant_names_the_field_and_the_bad_value` and `agentReachGrantsRefusal.test.tsx` failed before. Drive: real route over a real agent (relative root, bad host); component with a real `ApiError`; not re-seen in a browser (labelled). Original: open 2026-10-20. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8142, `scripts/drive/s1020_reach_ui.py`, Playwright on the served bundle).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

Repro (browser): agent page `?project=<p>&agent=cla&settings=execution`, Granted reach -> "This agent's own", type `http://bad host` in Granted host, Enter, **Save granted reach**. The PATCH answers 400 and the page shows, in red, only "Could not save the granted reach." (screenshot `testbed/ui-judge/s1020-reach/100046/04_agent_bad_save.png`); nothing says which entry or why, and the bad host chip stays in the list. The same refusal on the project's Reach group shows the Hub's sentence ("reach_grants.roots.0.path: a granted root is an absolute path, {temp} or {project}: 'notes'"), so the two editors of one setting disagree. The route's detail is not fit to show either: `PATCH /projects/{p}/agents/cla {"reach_grants": {"roots": [{"path": "rel", "access": "read"}]}}` -> 400 `"reach_grants: 1 validation error for ReachGrants\nroots.0.path\n  Value error, a granted root is an absolute path, {temp} or {project}: 'rel' [type=value_error, input_value='rel', input_type=str]\n    For further information visit https://errors.pydantic.dev/..."`.

Cause: `hub/hub/api/v1/agents.py:3184-3189` raises `detail=f"reach_grants: {exc}"` with the `ValidationError`'s `str()`; `ReachGrantsSetting` (`hub/ui/src/components/agents/AgentSettingsControls.tsx:296-300`) renders a fixed sentence on `update.isError`.

Expected: the route's detail is the same `loc: msg` sentence the project route yields (e.g. `reach_grants.hosts: a granted host is host, host:port, host:* or *.domain, not 'http://bad host'`), and the agent page shows it. Failing tests: a Hub test that the 400 detail has no `errors.pydantic.dev` and names the field and the bad value; a UI test (`hub/ui/src/__tests__/`) that a 400 from the agent reach PATCH renders the Hub's detail. Seam: Agents (settings PATCH) x Permissions & sandbox (reach grants UI).

## F796 (C) -- a host typed into Granted host but not added with Enter or "Add host" is silently dropped when the settings are saved, and stays in the field as if it were granted

**Status:** fixed 2026-10-21 (night iteration 30; commit b330255). Drive: a real `userEvent` type-then-click-Save over a stateful form carrying the real editor submitted `hosts: ['localhost:*','registry.npmjs.org']` and cleared the field; test `hub/ui/src/__tests__/reachGrantsHostDraft.test.tsx` (failed before the fix). The editor adds a typed host on blur, so both the project and agent pages are covered; not re-seen in a browser. Original: open 2026-10-20. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8142, `scripts/drive/s1020_reach_ui.py`).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

Repro (browser): Environment -> Settings -> Reach. Add `localhost:*` with Enter (becomes a chip), then type `registry.npmjs.org` in Granted host and press **Save settings** without pressing Enter. `GET /projects/{p}/settings` reads `"hosts": ["localhost:*"]`; the field still shows `registry.npmjs.org` after the save, with no warning. The operator who granted a registry for `npm install` finds the agent refused and the setting apparently in place. Same editor on the agent page (`ReachGrantsEditor` is shared).

Cause: `ReachGrantsEditor` (`hub/ui/src/components/environment/ReachGrantsEditor.tsx`) keeps the typed host in local `hostDraft` state that only `addHost` folds into `grants`; the form's save reads `grants`.

Expected: a non-empty host draft is either added on save (and validated by the Hub like the others) or blocks the save with "Add or clear the host you typed". Failing test: a UI test typing a host without Enter and submitting the project settings form sends it in `reach_grants.hosts` (or refuses the submit). Seam: Permissions & sandbox (Reach UI) x Projects (settings form).

## F798 (B) -- adding a folder by path that holds one unreadable subfolder answers a bare 500, adds nothing, and the agent's `vault_add` reads only "Internal Server Error"

**Status:** fixed 2026-10-20 (night iteration 3; sha in the commit that carries this line). Drive: a real `icacls /deny (RD)` subfolder through `vault_intake.expand` gave one refusal "The Hub could not list the folder ...\locked: Access is denied." and `ok.md` kept. Test: `hub/tests/test_vault_paths.py::test_a_folder_that_cannot_be_listed_is_refused_by_name_and_the_rest_is_added` (failed before the fix). Original: open 2026-10-20. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8143, branch tip 636ce55).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

Repro: a folder `edge/acl` holding `ok.md` and a subfolder `locked/` whose listing is denied (`icacls edge\acl\locked /deny %USERNAME%:(RD)`; on Windows the same happens under any home folder, e.g. `AppData\Local\Application Data`). `POST /projects/{p}/vault/paths {"paths": ["C:/.../edge/acl"], "distil": false}` -> `500 "Internal Server Error"`; the log has `PermissionError: [WinError 5] Access is denied: '...\acl\locked'` from `vault_intake._walk` (`hub/hub/vault_intake.py:188`, `folder.iterdir()`), reached from `expand` (`:210`). Nothing is added, not even `ok.md`. Through the agent door (the project grants a read root over `edge`), Haiku's `vault_add(["C:/.../vault1020-outside/outside.md", "C:/.../edge/acl"], distil=false)` got `Tool error: Hub rejected POST /vault/paths (500): Internal Server Error`, so the legitimate `outside.md` in the same batch was lost with it. A single file *inside* the denied folder, named directly, is added (200), so the walk is the only seam.

Expected: the unreadable folder becomes one `refused` result naming it ("The Hub could not list this folder: Access is denied."), the rest of the batch is added, and no route answers 500. Failing test: `hub/tests/test_vault_paths.py`, a folder whose subfolder raises `PermissionError` on `iterdir` (monkeypatch) answers 200 with the sibling file added and the subfolder refused. Seam: Knowledge vault (add by path) x Resilience (what a route returns when the thing it calls raises).

## F799 (C) -- the folder walk follows junctions and directory links (a loop adds each file 64 times to the batch), and the 200-file cap is checked only after the whole folder is walked

**Status:** fixed 2026-10-21 f3e013c (night iteration 31). Drive: `vault_intake.expand` over the real `hub/ui/node_modules` refused in 0.1 s (was 14.1 s). Tests: `hub/tests/test_vault_paths.py::test_a_folder_holding_a_link_to_itself_yields_each_file_once` (a real junction) and `::test_a_folder_past_the_limit_is_refused_without_walking_all_of_it` (both failed before the fix). Original: open 2026-10-20. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8143, `scripts/drive/s1020_vault.py` steps L and B).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

Two measurements of one function, `vault_intake._walk` / `expand` (`hub/hub/vault_intake.py:185-238`):

- **A link loop.** Folder `loop/` holding `a.md`, `b.md` and a junction `back -> loop` (`mklink /J`). `POST /vault/paths {"paths": [".../loop"], "distil": false}` -> 200 in 0.4 s with **128 results for 2 files**, the same two resolved paths repeated until Windows' path length ended the recursion (on the first call: 1 added, its 63 copies "skipped" as duplicates). Every copy counts toward `MAX_BATCH_FILES`, so a folder of four files plus one such link is refused as "more than 200 files". `child.is_dir()` follows the link; nothing records folders already visited.
- **The cap after the walk.** `POST /vault/paths {"paths": [".../hub/ui/node_modules"], "distil": false}` (27,135 files) -> 400 "These paths reach more than 200 files ..." after **14.1 s**: `expand` walks the given folder completely and only then compares the count. The docstring's own case, "a mistaken path (a home directory)", walks the whole home folder before refusing (and on Windows usually hits F798's 500 first).

Expected: the walk does not descend into a directory link or junction (or tracks the resolved folders it has visited), and stops as soon as the 201st file is reached. Failing tests (`hub/tests/test_vault_paths.py`): a folder with a link to itself yields one result per real file; a folder of 300 files is refused without yielding more than 201. Seam: Knowledge vault (add by path).

## F800 (B) -- `agentweave reset --profile <name> --all` deletes the shared `~/.agentweave/hub/.env` (the default profile's bootstrap key and ticket secret) and every other instance's `*.log`

**Status:** fixed 2026-10-20 (night iteration 2; sha in the commit that carries this line). Drive: sandboxed home, `reset --profile life --all --yes` removed `profiles/life` and `hub-life-8144.log`, left `.env` and `hub-trial-8010.log`. Tests: `tests/test_hub_commands.py::TestResetAllIsScopedToTheNamedProfile` (two failed before the fix). Original: open 2026-10-20. Found by the day sweep `sweep-vault-sweep` (CLI & lifecycle row), reproduced with `USERPROFILE`/`HOME` pointed at `testbed/life1020-home`, so no real state was touched.
**Source:** drive
**Theme:** CLI & lifecycle
**Ready:** yes
**Tier:** 0

Repro (sandboxed home): start `agentweave --profile life1020 --port 8144`, stop it, put a `hub-trial-8010.log` and a default-profile `data/agentweave.db` in the Hub folder, then `agentweave reset --profile life1020 --all --yes`. Output: `Deleted ...\hub\profiles\life1020`, `Deleted ...\hub\.env`, `Deleted ...\hub\hub-trial-8010.log`. The default profile's `data/` survived; the shared `.env` and the other instance's log did not. `cmd_reset` (`src/agentweave/cli.py:1546`, `:1610-1618`) uses `env_path = HUB_DIR / ".env"` and `HUB_DIR.glob("*.log")` whatever `--profile` says, although its own comment says "reset's blast radius is always exactly one profile, named or default, never inferred (`design.md` D6)". `.env` is one file for every profile (`_hub_native_scaffold`, `cli.py:811`, written by whichever profile starts first; in the sandbox it named the *named* profile's database), so on this machine `reset --profile scratch --all` would delete the file the default profile's `AW_BOOTSTRAP_API_KEY` and `AW_TICKET_SECRET` come from, and every log in `~/.agentweave/hub/`, `hub-trial-8010.log` included. The confirmation lists the `.env` under "profile 'life1020'", so it reads as that profile's own.

Expected: with a named profile, `--all` touches only that profile (its own logs, such as `hub-<profile>-<port>.log`), and either leaves the shared `.env` alone or refuses `--all` saying why. Failing test: `tests/test_hub_commands.py` (or a new `tests/test_reset_blast_radius.py`): `cmd_reset` with `profile="x"`, `all=True`, `yes=True` and `HUB_DIR` in `tmp_path` leaves `.env` and a foreign `*.log` in place. Seam: CLI & lifecycle (reset) x Projects (profiles).

## F801 (C) -- a vault report filed while the reports job has no runner stays `pending` forever: choosing a runner never looks into it, and the operator cannot close a pending report

**Status:** fixed 62d3062 2026-10-21 (a door, not auto-pickup): `POST /vault/reports/{id}/review` (202; 404 unknown report, 409 not pending / job off / no runner) and a "Look into it" button on each pending report; the no-runner and failed-spawn firings now say the report stays pending and name the door. Tests: `test_a_pending_report_is_looked_into_again_once_the_job_has_a_runner`, vaultTab "looks into a pending report again". Drive: real route over ASGI with a faked worker; component over a real ApiError; not driven through a live Hub with a real Haiku turn (labelled). Found by the day sweep `sweep-vault-sweep` (scratch Hub :8143).
**Source:** drive
**Theme:** Manager jobs
**Ready:** yes
**Tier:** 1

Repro: `PATCH /projects/{p}/manager/jobs/vault-reports {"enabled": true}` (no runner). A Haiku agent calls `vault_report` on a fact -> report `rpt-cffc675f654b`, `pending`; one `manager_job_fired` row, `failed`, "Did nothing: the Vault reports job is on but has no runner. Choose one on the Manager page." (F626's fix holds). Then choose the runner as told (`PATCH ... {"enabled": true, "runner_id": "<haiku runner>", "model": "claude-haiku-4-5-20251001"}`) and wait 45 s: still one firing, the report still `pending`, `answer: null`. `POST /vault/reports/rpt-cffc675f654b/close {"note": "closing"}` -> 409 "Report rpt-cffc675f654b is pending; only a referred report is closed." The Vault tab's Reports list shows the report with a bare `pending` badge and no control (screenshot `testbed/ui-judge/s1020-vault/101454/01_vault.png`; `VaultPage.tsx:924` renders a close form only for `referred`). The same dead end follows any failed spawn (`vault_reports.py:277`, "the report stays pending"). No route looks into a pending report again; the source-side twin has one (`POST /vault/sources/{id}/distil`).

Expected: a pending report can be looked into again (a "Look into it" door on the report, or the job picking up its pending reports when it gains a runner), and the failed firing's sentence says what will happen to the report. Acceptance: file a report with the job runner-less, set the runner, use the door -> one `written` firing and the report `answered`, `corrected` or `referred`. Seam: Manager jobs x Knowledge vault (reports).

## F802 (C) -- `agentweave doctor --profile <name> --port N` tells the operator to start `agentweave --port N`, which starts the default profile's database on that port; doctor also prints bare `diagnostic_check_warn` lines

**Status:** fixed 2026-10-21 (night iteration 33, Tier 0, sha 8efcf90). `collect_diagnostics(start_command=)` carries `_hub_start_hint(profile, port)` into `check_hub_instance`'s hint; `_emit_diagnostic_log` logs at INFO (the stderr handler shows WARNING+; the JSONL file and Hub handler still get the full result). Tests in `tests/test_doctor_port_names_its_profile.py` (hint for named and default profile; a real subprocess whose stderr must be empty), failing before. Drive: `py -3.11 -m agentweave doctor --profile life1020 --port 8149` printed `Start it with ``agentweave --profile life1020 --port 8149``` and wrote 0 bytes to stderr. Side note: `tests/test_skill_sync.py` was failing on a clean tree (stale untracked local skill mirrors, the F585 class); re-running `scripts/sync_skills.py` made it pass, no diff. Found by the day sweep `sweep-vault-sweep` (CLI & lifecycle row, sandboxed home).
**Source:** drive
**Theme:** CLI & lifecycle
**Ready:** yes
**Tier:** 0

Repro: with no Hub on 8144, `agentweave doctor --profile life1020 --port 8144` prints `[WARN] port:8144: No Hub answered on port 8144 (...)` with `Hint: Start it with ``agentweave --port 8144``, if it should be running.` (`src/agentweave/diagnostics.py:269`; the hint has no profile). `agentweave status --profile life1020 --port 8144` gets it right: `Run 'agentweave --profile life1020 --port 8144' to start it`. Following doctor's hint starts the **default** profile's database on 8144. The same doctor run also writes two lines reading only `diagnostic_check_warn` above the `[DOCTOR]` header: `_emit_diagnostic_log` (`cli.py:24-34`) logs the event name through an unconfigured logger, so Python's last-resort handler prints the bare name to stderr.

Expected: the hint is the status command's (`_hub_start_hint(profile, port)`), and doctor prints no bare event names. Failing tests: `tests/test_doctor_port_names_its_profile.py`, doctor for a named profile with nothing on the port gives a hint containing `--profile <name>`; a capsys test that doctor's stderr has no line equal to `diagnostic_check_warn`. Seam: CLI & lifecycle (doctor).

## F804 (B) -- a question nobody waits on, asked in one conversation, takes over the composer of every other conversation with that agent (archived ones included): the operator's next instruction there is stored as its answer and reaches the agent as "Question: ... Answer: <instruction>"

**Status:** fixed 2026-10-21 (night iteration 10, Tier 0; sha in the commit that carries this line). The questions payload now carries `conversation_id` (`QuestionResponse`, the column already existed); `activeQuestionFor(questions, agent, conversationId)` shows only questions asked in the conversation on screen (or naming none), the card and the panel both pass it, and the composer sends typed text as a message when the active question has `asker_waiting === false` (picking an option still answers it). Tests `hub/tests/test_a_question_names_its_conversation.py` and `hub/ui/src/__tests__/questionTrayConversation.test.tsx`, failing before. Drive: scratch Hub :8150 (profile f804, seeded stale question in conversation A, no agent asked it), Chromium against the rebuilt served bundle (`scripts/drive/s1021_f804_ui.py b|a`): in B no card, placeholder "Message asker…", Send started a run in B and the question stayed unanswered; in A the card shows ("Answer asker…") and typed text started a run in A, question still unanswered. Not done: the "no longer waiting" question in its own conversation still renders as the composer's placeholder owner; archived-conversation questions are covered by the same scoping but not driven separately. Found by the day sweep `sweep-questions-sweep` (scratch Hub :8146, Chromium against the served bundle).
**Source:** drive
**Theme:** Questions
**Ready:** yes -- repro below, driven twice.
**Tier:** 0

Agent `asker` (`claude-haiku-4-5-20251001`, `question_timeout_seconds: 30`) asked `q-5266fa021f02` ("Which name should the new helper have?", options double/twice) in conversation A (`conv-5933fff47ed8`). Nobody answered, its run ended, and the Questions route lists it with `asker_waiting: false` (the "no longer waiting" chip, which is right). Then the operator opened a different conversation B with the same agent (`conv-45ef9d145288`). B shows A's question card with the "no longer waiting" chip above B's composer, and the composer's placeholder reads "Answer asker…". The operator typed "New task: add a subtract(a, b) function to src/calc.py and reply in one line." and pressed Send. Nothing was triggered as a message. Instead `PATCH /questions/q-5266fa021f02` stored that sentence as A's answer (`answered 1`, `answer` = the instruction), and the Hub queued `entry-c45c84e0366d` into B with the content "Question: Which name should the new helper have?\n\nAnswer: New task: add a subtract(a, b) ...". Haiku happened to do the task. The record of A's question now holds an answer the operator never gave, and anything the send would have carried with it is skipped: the answer path returns before the Explore document is created and before the model, effort and permission pills are applied.

Archiving A does not release it. A second stale question (`q-3bf07bba7fe5`), with its conversation archived through `POST .../conversations/{id}/archive`, still rendered in B (`agent-question-q-3bf07bba7fe5` present) with "Answer asker…". The only way out is to notice the card belongs elsewhere and press its X to decline it.

Cause: `activeQuestionFor(questions, agent)` (`hub/ui/src/lib/pendingQuestions.ts:30-38`) filters by `from_agent` only. It never looks at `question.conversation_id`, and the card's own docstring says "the card sits inside one conversation" (`hub/ui/src/components/agents/AgentQuestionCard.tsx:8`). `AgentOutputPanel.handleComposerSubmit` (`hub/ui/src/components/agents/AgentOutputPanel.tsx:1040-1046`) then hands every send to `answerPendingQuestion` whenever a `pendingQuestion` exists, and its reason is "otherwise the operator's reply becomes a new message and the agent keeps waiting". That reason is false for a question with `asker_waiting === false`, because nothing is waiting.

Expected: the tray in conversation X shows only questions whose `conversation_id` is X (or have none). A question nobody waits on does not take free text away from the composer: picking one of its options still answers it, but typed text is sent as a message. Failing tests: in `hub/ui/src/__tests__/` (beside `refusalRecordTray.test.ts`), `activeQuestionFor` given conversation B returns no question asked in conversation A; and an `AgentOutputPanel` render with a stale question from another conversation, after typing and sending, calls the trigger (`postTrigger`) and not the question PATCH. Seam: Questions x Conversations & composer.

## F806 (B) -- one folder-browser listing, project open or relocate of a path on an unreachable network host freezes the whole Hub for about 21 s: the filesystem calls run on the event loop

**Status:** fixed (this commit, night 2026-10-21 iteration 11). Listing, open, create and relocate now run their filesystem work through `asyncio.to_thread` (`fs_browse.py`, `ProjectLifecycleService._canonicalize`, marker reads, create's `exists`); `hub/tests/test_a_slow_share_does_not_freeze_the_hub.py` stalls each call 1.5 s and fails before the fix (`/health` waited the whole stall), passes after. Drive: the real unreachable address answered at once on this machine (no 21 s stall reproduced; network state differs from the sweep's), so the real-share timing is unverified. `GET /projects`' per-project refresh (`_refresh_project_observation`) is still synchronous and was not measured. Confirmed live 2026-10-21 (day sweep `sweep-projects-sweep`, scratch Hub :8158, `scripts/drive/s1021_p_api.py block 31`): on fresh blackholed hosts each of list/open/create/relocate still took 21.04-21.05 s, and `/health` sent meanwhile answered in 0.00-0.11 s every time, so the real-share timing now holds. `GET /projects` with a registered project on a dead share still not reached.
**Source:** drive
**Theme:** Projects
**Ready:** yes -- measured three times, each against a fresh blackholed address (Windows caches a failed host, so a repeat answers at once).
**Tier:** 0

Repro (`py -3.11 scripts/drive/s1020_p_api.py fs-block`, and `open-block`): send one slow request, and half a second later time `GET /api/v1/health` (baseline 0.001-0.008 s).

- `GET /fs/list?path=\\10.255.255.4\share` took 21.04 s (200, `reason` "[WinError 53] The network path was not found"). `/health` sent meanwhile took **20.54 s**.
- `POST /projects/open {"path": "\\10.255.255.2\share\proj"}` took 21.08 s (409 `project_workspace_unreadable`), and `/health` took **20.57 s**.
- `POST /projects/{id}/relocate {"path": "\\10.255.255.3\share\proj"}` took 21.18 s (409 `project_workspace_missing`), and `/health` took **20.68 s**.

Nothing else is served for that time: no SSE, no agent tool call, no run event. A typed path is enough to cause it, in the Add-project dialog or its in-Hub browser (which lists as soon as it opens on the typed path). Cause: `list_fs_directory` is `async def` and calls `fs_browse.list_directory` (`Path.resolve`, `os.scandir`) directly (`hub/hub/api/v1/fs_browse.py:19-34`). The open, create and relocate routes reach the same kind of synchronous `resolve`/`stat` calls through `ProjectLifecycleService` (`hub/hub/api/v1/projects.py:357-372`, `:792-806`). `create` was not measured separately: its probe hit the cached failure. On the same unreachable share, open says "unreadable" and relocate says "does not exist".

Expected: the filesystem work runs off the loop (`await asyncio.to_thread(list_directory, path)`, and the same around the workspace resolution in open/create/relocate), so a slow share costs only its own request. Failing test: in `hub/tests/test_fs_browse*.py`, monkeypatch `os.scandir` to sleep 2 s, `asyncio.gather` the listing with `GET /health` through the ASGI client, and assert `/health` finishes in under 0.5 s. Do the same for `POST /projects/open` with the workspace probe patched to sleep. Not measured: `GET /projects` refreshes every project's directory state (`_refresh_project_observation`), so a registered project whose share goes offline may freeze every project-list poll the same way. Seam: Projects (folder browser, open/relocate) x the whole Hub's event loop.

## F807 (B) -- switching the checkpoint runner to a Copilot or Codex runner keeps a Claude checkpoint model the screen no longer shows, and Save is refused naming it

**Status:** fixed 29f099a 2026-10-21 (night iteration 12; drive: scratch Hub :8151, Chromium on the rebuilt bundle, `scripts/drive/s1021_f807_ui.py` -- stored claude runner + model `haiku`, picking the copilot runner showed "Use the runner's model", Save said "Settings saved." and stored runner-885c5930c473 with checkpoint_model null; the copilot option read "r-cop — Claude Haiku 4.5 (copilot)", no "(unrecognised)"). Originally open 2026-10-20. Found by the day sweep `sweep-projects-sweep` (scratch Hub :8147, Chromium against the served bundle). Confirmed live 2026-10-21 on the ui-finesse autosaving Checkpointing group (day sweep, :8158, `scripts/drive/s1021_p_ui.py checkpoint`): picking r-cop stored the runner with `checkpoint_model` null and the model menu read "Use the runner's model"; copilot `claude-haiku-4.5` -> back to a claude runner also cleared; claude -> claude kept `claude-opus-5-5`; no refusal notice.
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 0

Repro (`py -3.11 scripts/drive/s1020_p_ui.py checkpoint`). Settings store `checkpoint_runner_id` = `r-haiku-id` (claude) and `checkpoint_model` = `haiku`. On Settings -> Checkpointing the operator picks `r-cop` (copilot, `claude-haiku-4.5`) in "Checkpoint runner". The "Checkpoint model" select now shows **"Use the runner's model"** (DOM value `''`): its options are Copilot's, and `haiku` is not among them. The form still holds `haiku`. Pressing Save shows "checkpoint_model: 'haiku' is not a model 'copilot' declares; expected one of: auto, claude-sonnet-5.5, ... kimi-k3" (32 ids), and nothing is stored (`checkpoint_runner_id` stays `r-haiku-id`). The refusal names a value the screen says is not set. Choosing "Use the runner's model" again may not fire `onChange`, because it already looks selected. That is not driven: Playwright's `select_option` always dispatches. In that case the only way out is to pick some other model and then go back.

While choosing, every option of the runner select carries the stored override: "r-cop — haiku (unrecognised) (copilot)", "r-codex — haiku (unrecognised) (codex)", "Copilot (default) — haiku (unrecognised) (copilot)". So the select itself warns that each non-Claude choice cannot run, and the save then refuses. `runnerOptionLabel(runner, catalog, { model: form.checkpoint_model })` (`hub/ui/src/components/environment/ProjectSettingsPanel.tsx:375`) applies the override to every runner. The model select (`:380-398`) renders `value={form.checkpoint_model}` with no option for a value its new catalog lacks. Ledger line 33583 saw the cross-CLI labels and left them unfiled, before 2026-10-16 made a newly set cross-CLI `checkpoint_model` a refusal (F662's change).

Expected: changing the checkpoint runner to one whose CLI does not declare the stored `checkpoint_model` clears it in the form (it shows "Use the runner's model" and saves as null), or keeps it visible as "haiku (not a copilot model)" so the refusal matches the screen. The runner options take the override only where the runner's CLI declares it. Failing test: a `ProjectSettingsPanel` UI test (`hub/ui/src/__tests__/`) seeded with a claude checkpoint runner and model `haiku` that picks a copilot runner and saves, then asserts the PUT body carries `checkpoint_model: null` (it carries `"haiku"` today). Seam: Runners & models x Projects (settings, Checkpointing group).

## F808 (C) -- every project with no agents tells the operator to run `agentweave start`, a command the CLI refuses

**Status:** fixed (night iteration 34, Tier 0; 06528cd). The empty roster reads "No agents yet. Agents are added here, in the app." with an Add agent button that opens the dialog for the project (`OverviewPage` `onAddAgent`, wired in `App.tsx`). Test `hub/ui/src/__tests__/overviewEmptyRoster.test.tsx`, failing before. Drive: jsdom with real click events; not re-seen in a browser. Found by the day sweep `sweep-projects-sweep` (scratch Hub :8147, Chromium against the served bundle). Confirmed in Chromium 2026-10-21 (day sweep, :8158, `s1021_p_ui.py empty`): "No agents yet. Add agent", no `agentweave start`; Enter on the button opened Create agent with focus in the name, Escape returned focus to it, and Create made `first` in that project only.
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

A fresh project's Overview reads "No agents connected. Run `agentweave start` to connect agents." (`hub/ui/src/components/overview/OverviewPage.tsx:179-184`; screenshot `testbed/ui-judge/s1020-p-picker/105638/05_pending.png`). Running it gives `agentweave: error: argument command: invalid choice: 'start' (choose from 'doctor', 'status', 'stop', 'reset', 'vault')` (`py -3.11 -m agentweave start` in `testbed/scratch`). Agents are added in the app, through the rail's "Add agent" directly above this card. Ledger line 16075 quoted the same sentence in 2026-09 as a failed-fetch MISREPORT example. The sentence itself, which is wrong on every successful fetch too, was never filed.

Expected: the empty state names the way that works ("No agents yet." plus a button that opens the Add-agent dialog), with no CLI command. Failing test: an `OverviewPage` UI test with an empty roster asserting the text does not contain `agentweave start` and that the card offers Add agent. Seam: Projects (Overview) x Agents.

## F810 (B) -- `POST /session/sync` deletes an agent whose messages are still queued, which archive refuses to do: the entries and the conversation are orphaned, the rail calls them "agent archived", and a later agent of the same name inherits them

**Status:** fixed 2026-10-20 night iteration 4 (Tier 0). `launchability.agent_removal_refusal` now counts `InboundQueueEntry.state == 'queued'` and names the entry ids (`held.queue_entries`); sync answers the same 409 `agent_removal_under_held_work` archive does, row and entry kept. Tests `hub/tests/test_session_sync.py` (queued -> 409; spent queue -> still removed), failing before. Drive: through the real ASGI app and database (no scratch Hub). Not done: the rail still says "agent archived" for conversations of an agent already deleted by an older sync, and F812 (non-object agents -> 500) left for its own item.
**Source:** drive
**Theme:** Agents
**Ready:** yes
**Tier:** 0

F774's guard (`launchability.agent_removal_refusal`, `hub/hub/launchability.py:668`) refuses a sync that would delete an agent holding a live run or an unfinished task. It does not count **queued inbound entries**. Archive, on the same agents, does: `POST /agents/gamma/archive` answered `409 "gamma has 1 queued message, and nothing delivers to an archived agent, so archiving it now would strand them. Bind a runner so it can deliver them, or discard them to archive the agent now."` (`hub/hub/api/v1/agents.py:3341`). Sync then deletes the same agent with the same message:

```
gamma, delta: runner unbound, one operator message each queued (waiting_reason "No runner is bound ...")
POST /session/sync {"data": {"agents": {"alpha": {}, "beta": {}}}}
  -> 200 {"ok": true, "agents": ["alpha", "beta"]}       gamma and delta rows gone
inbound_queue_entries: entry-d3f9a75962e5 (delta) queued, entry-7a274edd13f4 (gamma) queued
conversations conv-b5dbabe96813 (delta), conv-834a29b23fb1 (gamma): lifecycle open
```

What happens afterwards:
- gamma's entry: the scheduler retried it three times and logged `queue_entry_abandoned` "delivery failed 3 times (gamma is not an agent in this project ...)". The row ends `withdrawn`.
- gamma's conversation: the rail lists it under **Archived agents** as "held for gamma — agent archived". Opening it (`?agent=gamma&conversation=conv-834a29b23fb1`) shows only "gamma is not on this project's roster.", with no Unarchive button and no way to read it. `GET /agents/gamma/chat/{id}` returns 404. Screenshot: `testbed/ui-judge/s1020-a-orphan/114315/orphan-gamma.png`.
- delta's entry stays `queued`. `POST /agents {"name": "delta", "runner_id": ...}` (201) creates a *new* agent of that name. `GET /queue/delta/status` then reads "the last delivery attempt was refused: No runner is bound to this agent", which is false, since the new delta has a runner. On the new agent's first trigger, the scheduler delivers the deleted agent's message first ("held for delta", `run-c9b86b8d9fda`), in the deleted agent's conversation, and only then the operator's new message (`run-604b5014e273`). That is a paid turn spent on someone else's message.

Expected: removal by sync is refused like archive (409, the same `agent_removal_under_held_work` shape, naming the queued entry ids), or the omitted agent's queued entries are withdrawn with an event saying why. Either way, a deleted agent's open conversations are not shown as "agent archived". Fix: `held_work`/`agent_removal_refusal` counts `InboundQueueEntry.state == 'queued'` for removal, not for the isolation check. Failing test: `hub/tests/test_session_sync.py`, an agent with a queued entry omitted from the payload -> 409, with the row and the entry kept. Seam: Agents (roster sync) x Inbound queue & messages x Conversations.

## F811 (B) -- two agents whose names differ only in case are both accepted; on Windows and macOS the second shares the first's worktree folder and can never run, and the refusal tells the operator to `rm -r` the other agent's checkout

**Status:** fixed (this commit, 2026-10-20 night). `route_words.agent_case_twin` refuses a name equal to an existing agent's (archived included) or a synced session's name case-insensitively, 409 with a sentence naming the existing agent, at `POST /agents`, `request_agent` and `POST /session/sync` (also two new names in one payload); an existing pair still syncs. Drive: real ASGI app against the real test database (`hub/tests/test_agent_names_differing_only_in_case.py`, 7 tests, 6 failed before the fix), not a scratch Hub; the related suites (59 tests) pass. Found by the day sweep `sweep-agents-sweep` (scratch Hub :8149, a real trigger).
**Source:** drive
**Theme:** Agents
**Ready:** yes
**Tier:** 0

Agent-name uniqueness is case-sensitive: `Agent.name == body.name` (`hub/hub/api/v1/agents.py:639`), the same in `request_agent` (`:2734`) and in sync. Reserved names and route words are compared case-insensitively. Worktrees live at `.agentweave/worktrees/<name>` on a filesystem that is case-insensitive by default on Windows and macOS.

```
eps: an agent that has run once (worktree .agentweave/worktrees/eps, branch agentweave/eps), then archived
POST /agents {"name": "eps", ...}  -> 409 "Agent name 'eps' already exists in this project"
POST /agents {"name": "EPS", ...}  -> 201
POST /agent/trigger {"agent": "EPS", "message": "..."}
  -> 200 status "queued", waiting_reason: "Could not prepare EPS's own workspace: refusing existing
     path C:\...\aw-a-1020\.agentweave\worktrees\EPS: it is not the registered git worktree for
     refs/heads/agentweave/EPS. Move or delete that directory (`rm -r C:\...\worktrees\EPS`) once you
     have salvaged anything in it; ..."
GET /queue/EPS/status -> waiting_count 2, the same sentence
```

`worktrees\EPS` is `worktrees\eps`: the remedy the Hub prints deletes another agent's checkout, which may hold unmerged work. If the operator doesn't follow it, EPS waits for ever. `eps` and `EPS` were both `open` after an Unarchive from eps's old conversation. Branch refs `agentweave/eps` and `agentweave/EPS` also collide as loose refs on these filesystems.

Expected: a name that equals an existing agent's name case-insensitively, archived included, is refused at creation with a sentence ("an agent named 'eps' already exists (archived); names differ by more than case"), on `POST /agents`, `request_agent` and sync. It is not added to `RESERVED_AGENT_NAMES`, which is checked at every use. Failing test: `hub/tests/test_operator_agent_creation*.py`, create `eps` then `EPS` -> 409, and the same for `request_agent`. Seam: Agents x Worktrees & integration.

## F812 (C) -- `POST /session/sync` answers 500 to an `agents` that is not an object, never says which agents it deleted, and leaves every agent it named with a `config` the operator can no longer PATCH ("reserved for a configured agent")

**Status:** fixed (night iteration 35, Tier 0; f0f51ee). `agents` that is not an object answers 422 "agents must be an object of agent name -> config" (roster untouched); the answer carries `removed: [...]` and each deletion persists an `agent_removed` warn event (also in the `session_synced` broadcast); the patch 409 now says the last session sync owns the agent's config and that `POST /session/sync {"data": {}}` releases it (leaves the roster alone). Tests: `test_session_sync.py` (list/str/int -> 422, removed listed + event rows, nothing removed -> `[]`) and `test_patch_agent_refuses_unknown_fields.py` (409 text), all seen failing first. Drive: real routes over ASGI, no live Hub, no agent turns (labelled). Dropping the lock outright was not done: the sync row still outranks `Agent.config` for isolation.
**Source:** drive
**Theme:** Agents
**Ready:** yes
**Tier:** 0

The route is reached only by direct API calls (its own docstring, `hub/hub/api/v1/session_sync.py:1-19`). Three gaps were measured after F774:

1. `{"data": {"agents": ["alpha"]}}` and `{"data": {"agents": "alpha"}}` each answer **500 Internal Server Error**: `list((body.data.get("agents") or {}).keys())` (`:73`) calls `.keys()` on a list or a str. The roster is untouched. `{"agents": null}` is 200, treated as no key.
2. A sync that deletes agents answers `200 {"ok": true, "agents": ["alpha", "beta"]}`, the roster that remains. Nothing names the two agents it just deleted. No event is persisted either: `session_synced` is only broadcast (`:221`), so `event_logs` holds nothing for the deletion (queried: no `session_synced`, no `agent_removed`). In the Activity feed, an agent vanishes with no record.
3. Once a sync names an agent, `PATCH /agents/<name>` with any `config` key answers `409 "Agent name 'beta' is reserved for a configured agent"` (`hub/hub/api/v1/agents.py:3096-3104`). Measured: `PATCH /agents/beta {"config": {"read_only": true}}` -> 409, before and after. The sentence names neither the stored sync row nor the way out (`POST /session/sync {"data": {}}` clears it, as found by reading the code). The operator never knowingly made beta "configured".

Expected: (1) 422 "agents must be an object of name -> config"; (2) the answer carries `removed: [...]`, and an `agent_removed` (or `session_synced` with `removed`) event is persisted; (3) the 409 says the agent's config is owned by the last session sync and names how to release it, or the lock is dropped now that no CLI pushes session.json. Failing tests: `hub/tests/test_session_sync.py` (list -> 422, removed listed, event row) and `test_patch_agent_refuses_unknown_fields.py` (the 409's text). Seam: Agents (roster sync) x Logs, events & SSE.

## F814 (B) -- with the token budget spent, the operator's own message waits "Queued — token budget exhausted" behind an agent's budget-held message, so "operator messages can still run" does not hold

**Status:** fixed 2026-10-21 (night iteration 9, Tier 0; sha in the commit that carries this line). Scheduler and status route select the operator's conversation when the budget is spent (`inbound_queue.select_operator_turn`). Drive: real ASGI app and database, scripted spawn, not a scratch Hub. The Continue control on the held peer conversation still offers a start that answers "Not started" -- left alone, arguably by design. Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8150, profile c1020, real Haiku turns, Chromium against the served bundle).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 0

`PATCH /accounting/budget {"token_budget": 1000}` (used 1,004,695, `exhausted: true`). beta's operator turn (`run-07b58ed50efd`, `budget_note` returned, as F456 promises) sent alpha a message. That entry (`entry-3572d64d8b7d`, `origin_type: agent`, sequence 6, alpha's peer conversation) was held, correctly, `waiting_reason: "token budget exhausted"`. The operator then typed "Reply with the single word PRED." into one of alpha's own conversations from the composer. The screen said **"Queued — token budget exhausted"**. `entry-8e67483040e9` (`origin_type: operator`, sequence 7) stayed `queued`, and no run started until the budget was cleared (`PATCH {"token_budget": null}`). Then both drained (`run-2b0f9ff394ca`, `run-919f757fb747` "PRED"). `BudgetExhaustionNotice.tsx:12` and the trigger's own `budget_note` tell the operator that operator messages still run.

Cause: `schedule_agent` (`hub/hub/turn_scheduler.py:456`) takes `select_turn`'s oldest eligible entry, here the autonomous one in another conversation. `initiator` (`:476`) is computed from that head only, so the budget gate (`:492-501`) holds the whole agent. The provider-allowance hold just above (`:477-490`) already handles this case: "their message can sit in a conversation behind an autonomous head", via `operator_would_probe(entries, hold)`. The budget gate has no such case. **Continue** on the held peer conversation does nothing either: "start it without sending a message" answers `started: false`, "Not started — token budget exhausted" (`POST /conversations/{id}/continue`). That one is arguably by design (the entry is autonomous), but the control still offers it.

Expected: with the budget spent, an operator entry anywhere in the agent's queue is the turn that runs (select the operator-controlled turn first, as the allowance path probes with operator input), and the autonomous head stays held. Failing test: in `hub/tests/test_a_budget_passed_over_is_said.py` (or a sibling), queue an autonomous entry in conversation A, exhaust the budget, then `POST /agent/trigger` as the operator into conversation B. Assert that a run starts for B, and that A's entry is still `queued` with "token budget exhausted". Seam: Accounting & allowance x Inbound queue & messages (the scheduler).

## F815 (C) -- an agent's `send_message` while the token budget is spent answers plain success, so the sender waits for a reply that cannot come

**Status:** fixed (night iteration 36, Tier 0; 2f12806). `create_message_for_actor` returns `Held("token_budget", ...)` for an agent's message when the budget is exhausted (after the hop-budget and no-runner holds); `MessageResponse.held` accepts it and `send_message` passes it through unchanged. The operator's own message is never held (F814). Tests `hub/tests/test_a_message_on_a_spent_budget_says_held.py`, the first failing before. Drive: real route over ASGI and database (no scratch Hub, no agent turns; labelled). Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8150).
**Source:** drive
**Theme:** Inbound queue & messages
**Ready:** yes
**Tier:** 0

With the budget spent (see F814), beta's `send_message {"to_agent": "alpha", ...}` returned `{"ok": true, "result": {"success": true, "message_id": "msg-f7cb9fe5754d"}}` (the tool result in `agent_outputs` of `run-07b58ed50efd`). beta replied "Message sent to alpha — waiting for their one-word reply". alpha's turn was held "token budget exhausted" until the operator raised the budget. The two other holds already tell the sender: hop budget (`held_by_hop_budget` + `delivery_note`, F361) and no runner (`held: "no_runner"`, `no_runner_note`, F623; `hub/hub/api/v1/messages.py:47-70`, `hub/hub/mcp_server.py:305-323`). A spent token budget is the third hold, and the only one that says nothing.

Expected: `create_message_for_actor` returns a `Held("token_budget", note)` when the project's budget is exhausted, since the recipient's turn would be autonomous. Suggested note: "Recorded as msg-…, but not delivered yet: the project's token budget is spent, so alpha's turn waits until the operator raises it. Do not tell anyone it was delivered; if it matters now, ask the operator with ask_user." The tool passes it through as it does the others. Failing test: beside the F623 test (messages), with the budget exhausted, `POST /agent-actions/messages` returns `held == "token_budget"` and a `delivery_note` naming the budget. Seam: Inbound queue & messages x Accounting & allowance.

## F816 (C) -- unarchiving a conversation that was cut over reopens it as a live line of work: no notice, a working composer on the old session, while the successor holds the same work

**Status:** fixed feb1947 (2026-10-21, Tier 0). `POST .../unarchive` on a handed-over conversation is 409 naming the successor (via `handover_of`); the UI's existing error path shows the sentence; an ordinary archived conversation still reopens. Driven over the real route and database (not in a browser, labelled); the F293 test now reopens through the database helper. The sheet's "carried into a new conversation" link to the successor is not done. Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8150, Chromium against the served bundle).
**Source:** drive
**Theme:** Checkpoints
**Ready:** yes
**Tier:** 0

`POST /checkpoints/ckpt-8a3375a6ae49/cutover` -> 200: successor `conv-1dbec82e6c34`, predecessor `conv-5bf3fe5c7c84` archived. `POST /agent/alpha/conversations/conv-5bf3fe5c7c84/unarchive` (`hub/hub/api/v1/agent_chat.py:659`) -> 200 with the plain conversation. Nothing in the body says it was handed over, and nothing was refused. A second cutover and a Checkpoint now on it are refused correctly, naming the successor (F716 holds). On screen the predecessor looks like any open conversation. There is no "continued in …" notice, and its composer is live. The Checkpoints sheet says only "Probe: passed · carried into a new conversation" (`CheckpointsPanel.tsx:47`), without naming or linking the conversation. A message typed there ran a real turn on the predecessor's old provider session (`run-919f757fb747`, reply "PRED"). That leaves two open conversations for one line of work: the checkpoint went to one, and the other keeps the full old context.

Expected: either unarchive of a handed-over conversation is refused, naming the successor ("conv-… was cut over to conv-…; continue there"; `checkpoint_cutover.handover_of` already answers it), or it reopens read-only with a notice linking the successor. The sheet's "carried into a new conversation" should link `cut_over_to_conversation_id`. Failing test: in `hub/tests/test_checkpoint_cutover.py`, cut over, then unarchive the predecessor. Assert a 409 naming the successor (or, if reopening is kept, a `handed_over_to` field and a refused trigger). Seam: Checkpoints x Conversations & composer.

## F817 (C) -- a failed Checkpoint now clears the conversation's checkpoint warning: after a reload the offer and the failure are both gone

**Status:** fixed 0657be1 (2026-10-21, Tier 0). `take_checkpoint` clears `due`/`final`/`dismissed` only when `checkpoint.status == "ready"`; an `unwritten` press leaves the warning standing so the banner still offers Checkpoint now. Test `test_a_failed_checkpoint_press_leaves_the_warning_standing` (3 params) failed before. Driven over the real route and database with a failing runner stub; not re-seen in a browser.
**Source:** drive
**Theme:** Checkpoints
**Ready:** yes
**Tier:** 0

The project's `checkpoint_runner_id` was pointed at a Codex runner that cannot run here. alpha's peer conversation `conv-bcf112b0ce9b` showed the threshold banner ("This conversation has reached its checkpoint threshold. Nothing has been written yet — checkpoint now, or dismiss this and keep working."). Pressing **Checkpoint now** -> `POST /conversations/{id}/checkpoint` 201 with `status: "unwritten"` and `generation_error: "exited 1: Reading additional input from stdin..."`. The screen showed "Checkpoint failed: exited 1: …" in a toast. In the database `checkpoint_warning` went from `due` to NULL. After a reload, the banner is gone, no failure is shown, and only the header's Checkpoint control remains (`testbed/ui-judge/s1020-c-reload/120418/failed-reloaded.png`). `take_checkpoint` (`hub/hub/api/v1/checkpoints.py:256`) clears `due`/`final`/`dismissed` whatever `checkpoint.status` came back. Its comment says "the warning has been answered by doing the thing it asked about", which is false for `unwritten`. F540's failure banner covers only an *automatic* checkpoint, so an operator's failed press leaves no trace on screen.

Also: the error is `hub/hub/worker.py:304`'s *last* stderr line, which for Codex is its "Reading additional input from stdin..." banner, not a cause. That wording is general, but Codex is undrivable here, so its real stderr was not read.

Expected: clear the warning only when the checkpoint is `ready`; an `unwritten` press leaves `due` (or `final`) in place, so the banner still offers Checkpoint now and can show the failure. Failing test: in `hub/tests/test_checkpoint*.py`, a worker stub that exits non-zero on a conversation with `checkpoint_warning = "due"`; after `POST .../checkpoint`, assert `status == "unwritten"` and the warning is still `"due"`. Seam: Checkpoints (operator press) x Runners (a failing worker).

## F819 (C) -- a loop whose agent cannot run gives up on the delivery, but the loop does not say so: its task stays `in_progress` with that agent, the card reads "Active", and the next Run briefs the same broken agent again

**Status:** fixed d3ec267 (2026-10-21, Tier 0). `task_attendance` gains `abandoned`: a `(task, agent)` pair whose entry the delivery-attempt limit withdrew (it keeps `delivered_in_run_id`) and for which the agent has no newer run on the task. The loop walk's ordinary-work arm records it in flight and unstaffed with `_abandoned_work_reason` ("<agent> could not start: <the run's own error> The Hub stopped retrying, and <task> is still assigned to <agent>. Fix <agent>'s runner and message <agent>, or reassign the task."), so `stall_reason` and the card name it and no further briefing is queued. A newer run, or reassigning the task, ends it. Tests `hub/tests/test_a_loop_says_its_delivery_was_abandoned.py` (first failed before). Drive: `decide_firing` and real firings over the real database (labelled: not a scratch Hub, no live Codex, no browser). Not done: the task itself stays `in_progress` (not released to `pending`); the `JobRun` `error_summary: null` stays with F123/F147.
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

A documentless loop on agent `delta`, bound to a Codex runner (Codex cannot run on this machine: every spawn exits 1). `POST /jobs {"name": "loop E codex", "agent": "delta", "initial_tasks": [{"title": "Write E.txt", ...}], "stop_when_queue_empties": true, ...}` and then `POST /jobs/{id}/run`:

```
POST /jobs/job-7f2da45bc1f4/run -> 200 {"success": true, "job_run_id": "run-01e70a76375a"}
runs:  run-5b905c738b6c, run-d4342da5642c, run-2f31974989c5  delta  failed exit 1
       error: "The 'gpt-5.6-sol' model is not supported when using Codex with a ChatGPT account."
queue: entry-74c856ce3103  state withdrawn  delivery_attempts 3
       abandoned_reason "delivery failed 3 times; the Hub stopped retrying"
task-21832111a8e0 "Write E.txt"   in_progress  assignee delta     (left there)
GET /loops/loop-8fb2d27d2497 -> queue {"in_progress": 1}, stall_reason null
GET /queue/delta/status       -> waiting_count 0, waiting_reason null
POST /jobs/{id}/run (again)   -> 200 success; a new briefing ("It is `in_progress` now ...") and
                                 three more failed runs (429), withdrawn the same way
```

So once the Hub has stopped retrying, nothing on the loop says that its one task is held by an agent whose every delivery failed. The card (Jobs tab) reads "Active", and the queue says "in_progress: 1". The task is never released, so another agent cannot take it, and the operator's only remedy, pressing Run, spends another three attempts on the same agent. The run's own error, which names the cause, is not on the loop or on the task. (The firing's `JobRun` being `failed` with `error_summary: null` is the openspec leftover `a-retried-firing-records-how-its-work-ended`, F123/F147, re-measured here. It is not part of this finding.)

**Expected:** after a loop's delivery is abandoned, the loop's `stall_reason` (and the card) names the task, the agent and the last run's error ("delta could not start: <error>; its task Write E.txt is still assigned to it"). The task goes back to `pending` or `assigned`, so that a press or a flow can staff it again, or the press refuses with that sentence instead of briefing the same agent.
**Seam:** `inbound_queue.py`'s abandonment (the `DELIVERY_ATTEMPT_LIMIT` path) never reaches the loop's task. The loop's stall check (`scheduler._loop_stop_reason` / the stall text in `api/v1/jobs.py`) reads no abandoned entry. **Test:** in `hub/tests/test_scheduler.py` (or a new `test_a_loop_says_its_delivery_was_abandoned.py`): a loop entry abandoned after three failed runs leaves `GET /loops/{id}` with a non-null `stall_reason` naming the agent, and a second `POST /run` does not create a fourth delivery to that agent. Both fail today.

## F820 (B) -- Land during a passing git failure approves the task and records the permanent skip "this project is not a git repository": its commit is never merged, and the screen offers no Retry, though the API's retry would merge it

**Status:** fixed 2026-10-21 night iteration 7 (Tier 0). `_integrate_task` now asks `task_integration.repository_fault` (git's own stderr) and, when git fails for a project the Hub has proof was a repository (`repository_proof`: the task's own worktree directory exists, or accepted/awaiting evidence for it names a git commit), records a `failed` row (`GIT_UNREADABLE`, quoting git) instead of the permanent skip, so `is_retryable` is True and the retry merges once git is back. A project with no such proof keeps `NOT_A_REPOSITORY`. Tests `hub/tests/test_task_integration.py` (`..._unreadable_for_a_moment...`, `..._worktree_exists_proves...`), failing before. Drive: real git, `.git` renamed away while the real ASGI app approved, then restored and the retry route merged (labelled: real ASGI app and database, not a scratch Hub). Not done: the drawer still has no Retry control (a separate finding, filed below); a task with neither signal and a vanished `.git` still reads as not a repository. Found by the day sweep `sweep-loops-sweep` (Resilience, failure injection; scratch Hub :8160, project `proj-205b3b4c85ec`).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

This is a real git repository with task branches. Its `.git` was moved aside for a few seconds, the way an unreadable or locked `.git`, a git that drops off the Hub's PATH, or a sync tool holding the folder would look. During those seconds the operator pressed Land on two completed loop tasks:

```
POST /tasks/task-8d36435b40ca/land -> 200 status "approved"
  latest_integration: {"outcome": "skipped", "reason": "this project is not a git repository, so there is nothing to merge"}
  story: workspace release_failed "git status --porcelain failed (128): fatal: not a git repository: .../.git/worktrees/task-8d36435b40ca"
(.git restored)
git log agentweave/task/task-8d36435b40ca -> fe1e4b7 "Write C.txt"   (not on master)
Tasks tab / drawer (Chromium, served bundle): "Not merged — this project is not a git repository, so there is nothing to merge", no Retry control
POST /tasks/task-8d36435b40ca/integrations/retry -> 200; new row outcome "merged"; master dd86047 "Integrate approved work fe1e4b76521b"
```

Reproduced a second time on `task-68d5b577682f` ("Write D.txt"), which is still unmerged and approved, with the same drawer text and no button.

**What is wrong:** `is_repository(root)` (`hub/hub/task_integration.py:167-169`) answers False for any git failure. Integration then records `NOT_A_REPOSITORY`, which the module classes as unretryable because it is "nothing this screen can change" (`task_integration.py:134`). So a passing fault becomes a permanent fact. The task reads `approved`, the work is on a branch nobody will merge, and the operator is told the project is not a repository, which is false. The retry route itself does not honour the classification, and merges.

**Expected:** a project the Hub already knows is a repository (it has task branches and recorded worktrees, or `GET /worktrees` reported `repository: true` before) records a git failure as `failed`, with git's stderr, so it can be retried. Or Land refuses (409) while git cannot be read, naming the error. Either way the drawer offers Retry once git is back.
**Test:** in `hub/tests/test_task_integration.py`: make `_git(root, "rev-parse", ...)` fail in a repository that has a task branch, then approve. Today the row is `skipped`/`NOT_A_REPOSITORY` and `is_retryable` is False. The test asserts `failed` and retryable.

## F823 (C) -- a failed merge's Retry ("Try again") exists only on the board card: the task drawer, where the failure is read, offers none, and a retry that fails again looks exactly like nothing happened

**Status:** fixed 5af9d2e, 2026-10-21 night iteration 40 (Tier 0). `TaskDetailDrawer` renders `TaskIntegrationNote` above both views (Story and Details), so the failure and its Try again sit together; the note's non-merged rows now carry a `<time>` ("tried HH:MM", ISO in `dateTime`/`title`) so a retry that fails the same way no longer reads identically. Tests `taskDetailDrawer.test.tsx` (retry inside `task-drawer-<id>`; nothing when no merge) and `taskIntegrationRetry.test.tsx` (newest row's time), failing before; full vitest 2219 passed, lint and tsc clean, bundle refreshed. Drive: the real components rendered in jsdom with fixture rows (labelled: no Chromium, no scratch Hub, no real git hook). Not done: a button-press feedback beyond the time stamp. Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8170).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

```
project repo: .git/hooks/pre-merge-commit -> echo "policy: merges into master are frozen for the release (hook)" >&2; exit 1
POST /tasks/task-6d2ada38a152/land {}  -> 200, latest_integration {"outcome": "failed", "reason": "policy: merges into master are frozen ... (hook)\nNot committing merge; ...", "retryable": true}
Chromium, served bundle, Tasks tab:
  drawer, Story view:   "Not merged (failed) ... policy: merges into master are frozen ..."  -- task-integration-retry-<id>: 0
  drawer, Details view: no mention of the merge at all                                         -- task-integration-retry-<id>: 0
  board card (behind the modal): "Merge failed -- policy: ... Try again"                       -- 1
card "Try again" with the hook still there -> a second `failed` row (GET .../integrations: 2 rows); the card text is identical before and after
hook removed, card "Try again" -> "Merged 87a62644 into master"; master b511a00 "Integrate approved work 87a6264407b9"
```

The integration note and its button are rendered only by `TaskCard` (`hub/ui/src/components/tasks/TaskCard.tsx:589`, the sole user of `TaskIntegrationNote`). The drawer's Story renders the failure (`TaskStory`) but has no control, and the Details view does not render the note. An operator who opens the task to read why its work is not on master has to close the drawer and find the card to act. And `newestPerTarget` keeps one row per target, so a repeated failure renders identically: the operator cannot tell that the press did anything. **Expected:** the drawer (Story's "Not merged" event, or Details beside Status) offers the same Try again when the newest row is `retryable`; after a press, the note shows the attempt time (or "failed again at HH:MM"). **Test:** `taskDetailDrawer.test.tsx`: a task whose integrations answer one `failed` retryable row renders `task-integration-retry-<id>` inside `task-drawer-<id>`; `taskIntegrationRetry.test.tsx`: two failed rows for one target render the newer row's time. Not F820 (that one is a reason classed unretryable; this one is retryable and still unreachable from the drawer).

## F824 (C) -- deleting a task from its drawer makes the page request the deleted task's story ~110 times in five seconds, and the card stays on the board for 5-10 s

**Status:** fixed (residual), 2026-10-22 night iteration 13 (Tier 0, UI only). Cause: the delete route broadcasts `task_updated {id, deleted: true}` as it commits (`tasks.py` `defer_broadcast`), and `useSSE`'s `task_updated` case invalidated the whole `tasks` prefix, so the still-open drawer's story observer refetched the dead key (404) -- the hook's own predicate never saw that path. `task_updated` now skips the deleted id's keys when the payload says `deleted`. Test `useSSE.test.tsx` F824 (live story observer, real client, the event the route sends; failed before: one story GET). Drive: `scripts/drive/s1021_r_ui.py` in Chromium on scratch :8161, served rebuilt bundle: DELETE 204, card gone by t+2s, **0** story requests through t+10s (the day measured 7 on the old bundle; the same script was not re-run against the old bundle tonight). Earlier residual note: (re-driven 2026-10-21 day, Chromium on scratch :8160 via `scripts/drive/s1021_r_ui.py`): the ~110-request loop and the 5-10 s card persistence are gone (card absent within 2 s; DELETE 204), but 7 GETs for the deleted task's `/story` still fire within 0.11 s of the 204, all 404, each a console error, then stop. The night's "never refetched" claim does not hold in the real page (its test used a stubbed fetch). Earlier status: fixed f5435c3, 2026-10-21 night iteration 41 (Tier 0, UI only). `useDeleteTask.onSuccess` takes the card out of every cached task page (and its `total`) on the 204 and invalidates the `tasks` prefix with a predicate that skips the deleted task's own keys, so its story is never refetched. Plain `removeQueries` was tried first and failed the test: removing a query a mounted observer holds makes the observer rebuild it and refetch, so the keys are left to garbage collection. Test `tasksApi.test.tsx` `useDeleteTask` (live story observer plus a cached board; failed before: one story GET after the 204); full vitest 2220 passed, lint and tsc clean, bundle refreshed. Drive: real hooks over a real QueryClient with a stubbed fetch (labelled: no Chromium, no 104-task scratch Hub, so the ~110-request loop itself and the 5-10 s persistence were not re-measured). Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8170).
**Source:** drive
**Theme:** Tasks
**Ready:** yes
**Tier:** 0

```
Chromium, served bundle, project with 104 tasks: open "bulk 004"'s drawer -> Details -> Delete -> Delete task
DELETE /tasks/task-d5dfdb335e86 -> 204 (drawer closes)
404 responses recorded by page.on("response") after the click:
  t+2s  card task-open-task-d5dfdb335e86 present  404s=57
  t+5s  card present                               404s=113
  t+10s card gone                                  404s=113
  all 113: GET projects/<p>/tasks/task-d5dfdb335e86/story
(a first delete of "bulk 002" the same way: 90 console 404s, card still on the board at t+2.5s)
```

`useTaskStory` has `retry: false` (`hub/ui/src/api/tasks.ts:397-405`), so 113 requests are not React Query retries. Something re-subscribes the story query of the deleted task in a tight loop until the board's own refetch drops the card; the delete mutation invalidates the whole `['project', p, 'tasks']` prefix (`tasks.ts:647-649`), which includes the deleted task's `story` key. **Expected:** after a 204 the deleted task's queries are removed (`removeQueries` for `['project', p, 'tasks', id]`) before the list is invalidated, and the card leaves the board on the 204, not on a later refetch. **Test:** a UI test that deletes from the drawer and counts calls to the story `queryFn` for that id after the mutation resolves: at most 0. The 5-10 s card persistence on a 104-task project is measured once; on a small board it may not show.

## F825 (C) -- deleting a prerequisite answers 204 and silently releases every task that waited on it; the confirm says only "Its dependencies ... go with it", and nothing names the released tasks

**Status:** fixed 5be6c22, 2026-10-21 night iteration 42 (Tier 0). `DELETE /tasks/{id}` reads the tasks that depend on the one being deleted before the rows go and puts them in the `task_deleted` event as `released_dependents` (`[{id, title}]`); the drawer's inline confirm lists them by title ("2 tasks wait on this one: ... -- they will be free to start"), its wording now says "Its own prerequisites" so it no longer reads as the dependents, and it takes focus on Cancel. Tests `test_the_operator_can_delete_a_document_a_task_or_an_archived_agent.py::test_deleting_a_prerequisite_names_the_tasks_it_releases` (failed before: KeyError), `taskDetailDrawer.test.tsx` (names the dependents and Cancel has focus; silent when none; both failed before the first); full vitest 2222 passed, lint and tsc clean, bundle refreshed, hub `-k "ui_build_stamp or ui_staleness or static or delet or task"` 1287 passed. Drive: real route over ASGI and database, real components in jsdom (labelled: no Chromium, no scratch Hub). Not done: whether deleting an approved, merged task should be refused is the operator's call and is not decided here. Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8170).
**Source:** drive
**Theme:** Dependencies
**Ready:** yes
**Tier:** 0

```
POST /tasks/<bulk001>/dependencies {"depends_on": "<bulk000>"} -> 201 added; bulk001 dependency_state "gated"
DELETE /tasks/<bulk000> -> 204
GET /tasks/<bulk001> -> prerequisites [], dependency_state null   (now startable)
event_logs: task_deleted {"id": "<bulk000>", "title": "bulk 000 ..."}   -- nothing about bulk001
Chromium: bulk003 depends on bulk002; bulk002's drawer -> Delete:
  confirm text: "Delete this task? Its dependencies, links, transitions and evidence go with it. This cannot be undone."
  focus after opening the confirm: the opener "Delete" button, not Cancel
  Delete task -> bulk003 prerequisites [], dependency_state null
DELETE /tasks/task-d58872f60abf (approved, merged into master, C depended on it) -> 204: its transitions and integration rows are gone; the merge commit stays on master
```

`deletion.delete_task` refuses only an active run (`hub/hub/deletion.py:192-195`); documents refuse archived and folded ones (`:206-223`), tasks refuse nothing. A gate the operator set up (or a document declared) disappears without a word, and the dependent can start on work that no longer exists. "Its dependencies ... go with it" reads as the deleted task's *own* prerequisites. **Expected:** the confirm names the tasks it will release ("2 tasks wait on this one: bulk 003, ... -- they will be free to start"), using the drawer's `dependents`; the `task_deleted` event carries `released_dependents`; and the inline confirm takes focus on Cancel like every other confirm (Keyboard & dialogs row). Whether deleting an approved, merged task should be refused (as an archived document is) is the operator's call; record the answer. **Test:** `hub/tests/test_task_delete.py`: delete a prerequisite of a gated task; the event payload names the dependent. UI: the confirm text contains the dependent's title.

## F828 (C) -- deleting a document (or a task) leaves the deleted task's checkout and branch, with the agent's unmerged commit, listed under a task id that no longer exists; neither the response nor the dialog mentions them

**Status:** fixed 5198a1b, 2026-10-21 night iteration 43 (Tier 0, backend). `worktrees.discard_task_checkout` removes a deleted task's checkout and branch when the branch holds no commit the primary HEAD lacks, no uncommitted edit and no half-resolved merge; otherwise both are kept. `DELETE /tasks/{id}` and the document delete call `deletion.discard_checkouts` after the rows commit and record a `task_checkout_kept` event (task_id, branch, unmerged_commits, uncommitted) for each kept one; the document delete's 200 also carries `kept_work` with the same entries. Tests `hub/tests/test_deleting_a_task_names_the_work_it_leaves.py` (4, all failed before: leftover checkout/branch, no event, no `kept_work`) against a real tmp git repo; delete/worktree test files 61 passed; ruff, black clean. Drive: real routes over ASGI and database with real git worktrees (labelled: no scratch Hub, no Chromium). Not done: the dialogs do not show `kept_work` yet, and the task 204 has no body, so the operator sees it only in the event log. Found by the day sweep `sweep-spec-sweep` (scratch Hub :8180, `scripts/drive/s1020_s_api.py` + real Haiku turns).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

```
approved change spec/changes/slug-speed, task task-67b0bf33dda8 worked by a real Haiku turn (builder):
  commit a15d775 on agentweave/task/task-67b0bf33dda8, task completed, two evidence pieces
DELETE /projects/<p>/project/documents/spec/changes/slug-speed/spec.json
  -> 200 {"deleted": true, "tasks": ["task-67b0bf33dda8"], "requirements": 1, "diagnostics": [...]}
git -C <project> worktree list
  .../.agentweave/tasks/task-67b0bf33dda8  a15d775 [agentweave/task/task-67b0bf33dda8]   <- still there
GET /projects/<p>/worktrees -> {"kind": "task", "name": "task-67b0bf33dda8", ...}            <- still listed
GET /projects/<p>/tasks/task-67b0bf33dda8 -> 404
```

The delete dialog says "Its file, its requirements and their evidence, and every task it put on the board go with it". The code the agent wrote does not go with it: `deletion.delete_document` / `delete_task` (`hub/hub/deletion.py:177-198`) delete rows only, and `DELETE /tasks/{id}` (`hub/hub/api/v1/tasks.py:1459`) is the same. The operator can't tell whether the work was discarded or kept, and Worktrees lists a checkout named after a task that 404s. **Expected:** the delete removes a deleted task's checkout and branch when the branch holds nothing unmerged. When it does hold unmerged commits, the checkout is kept and the response (and the dialog's result) names the branch and its unmerged commit count. **Test:** `hub/tests/` next to the F532 deletion tests: a task with a checkout and a commit on its branch, deleted through the document route; assert the response names the branch (or the checkout is gone), and fail on the current rows-only delete.

## F829 (C) -- after Delete document in the app, the page stays on the deleted document: its old title and phase, three load failures, and 404s, with no word that it was deleted

**Status:** fixed 2026-10-21 night iteration 44 (Tier 0; commit ad358d2). `useDeleteSpecDocument` now takes the path out of the cached `specs` and `specDocuments` lists and invalidates the corpus with a predicate that skips the dead path's own keys; `SpecPhaseBar` takes `onDeleted`, records `{path,title,tasks}` in `specDeletionStore` and calls it; the Spec screen goes to the home document (`onOpenDocument(null)`), the conversation panel closes the tab (`onClose`); `SpecDeletedNote` says "Deleted “T” and its N tasks." above the phase bar until dismissed. Tests: `specDeleteApi.test.tsx` (failed before: one GET of the dead path after the 200), `specFold.test.tsx` (+2). Drive: real hook over a real QueryClient with fetch stubbed, real components in jsdom (labelled: no Chromium, no scratch Hub). Not done: the conversation host shows the note only if another spec tab remains. Found by the day sweep `sweep-spec-sweep` (scratch Hub :8180, `scripts/drive/s1020_s_ui2.py`), seen in Chromium on the served bundle.
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

```
Chromium: ?tab=spec&document=spec/changes/ui-delete-131858/spec.json -> spec-delete -> "Delete document"
DELETE .../documents/spec/changes/ui-delete-131858/spec.json -> 200 {"deleted": true}
the page 3 s later (testbed/ui-judge/s1020-spec2/132004/03_after_delete.png):
  title "UI delete 131858", chips change-spec / exploring / sketch, "No requirements yet."
  "Drift could not be read: no specification document at spec/changes/ui-delete-131858/spec.json"
  "Could not load retired requirements: no specification document at ..."
  "This document's decided proposals could not be read."
  URL still ...&document=spec%2Fchanges%2Fui-delete-131858%2Fspec.json; 15 console 404s
```

`onConfirmDelete` (`hub/ui/src/components/spec/SpecPhaseBar.tsx:306-314`) closes the dialog and does nothing else. `useDeleteSpecDocument` (`hub/ui/src/api/spec.ts:1344`) invalidates the corpus but leaves the selected document in place, and its per-document queries then fail one by one. This is the document twin of F824 (task drawer). **Expected:** on a 200, the page leaves the deleted document for the document browser (or the home document) and says what was deleted, with the response's task count. The deleted path's queries are removed rather than refetched. **Test:** a UI test that deletes from the phase bar and asserts the selected document changes and no query for the deleted path runs after the mutation resolves.

## F832 (B) -- a refused Land tells the operator to "send the task back (revision_needed)", a move the Hub never offers the operator from `completed`; the one control that might, "Move to under review", is refused with "Land it"

**Status:** fixed 2026-10-21 night iteration 8 (Tier 0; the cleaner of the two expected options). `task_transitions.TRANSITIONS['completed']` gains `revision_needed` for the operator only (an agent still reaches a verdict through `under_review`), so the Land refusals' "send the task back (revision_needed)" now names a legal move, and the drawer menu (built from `/tasks/transitions/allowed`) offers it as "Move to Revision needed" with no UI change or bundle refresh. The send-back returns to the author (F495, asserted). Tests `hub/tests/test_operator_sends_completed_work_back.py` (failing before); `test_review_leaves_the_pool` updated to say agents have no verdict from `completed`. Drive: the real ASGI app and database through `PATCH /tasks/{id}` (labelled: not a scratch Hub, no Chromium); 159 tests across transitions, review and revision files pass. Not done: a dedicated "Send back" label in the drawer; the rejected-requirement refusal still quotes reviewer text (`REVIEWER_SENDS_BACK_REJECTED`) to the operator. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8190, real Haiku `builder`; `scripts/drive/s1020_v_ui2.py`).
**Source:** drive
**Theme:** Tasks
**Ready:** yes
**Tier:** 0

```
task-8c50aa06ab24 completed by builder (real turn); its requirement FR-2 not verified (rejected, then amendment_unreviewed)
POST /tasks/{id}/land {}  -> 409 gate_unsatisfied, message ends:
  "... Ask the task's author to record it, accept it, and approve again; or send the task back (revision_needed) naming the commits."
  (with FR-2 rejected it also says "If you are reviewing this task, ... move the task to revision_needed with notes ...")
PATCH /tasks/{id} {"status":"revision_needed"}  -> 409 "Cannot move a task from 'completed' to 'revision_needed'.
  From 'completed' the available transitions are: rejected, under_review."
Drawer status menu (Chromium): ["Move to rejected", "Move to under review"] -- no send-back item
"Move to under review" -> 403 "... with 'builder' as its holder: it is the agent recorded as completing this task ...
  Land it, on the task, to review it yourself, or dispatch a different agent's review turn (POST /agent/trigger with review_task_id)."
```

The operator goes round a loop: Land says send it back, the menu has no send-back, and the menu's only other move says Land it. A way out exists, but no sentence names it. `PATCH {"status":"under_review","assignee":null}` answers 200, and `revision_needed` then works and returns the task to `builder` (F495). The remedy strings are `OPERATOR_ON_UNLANDED` and `OPERATOR_ON_FAILING_CHECKS` (`hub/hub/requirement_gate.py:111-125`). The rejected refusal also hands the operator `REVIEWER_SENDS_BACK_REJECTED` (`:134`), which is reviewer text. The table is `task_transitions.py:134` (`completed` -> `under_review`, `rejected` only). This is F353's class: a refusal naming a remedy that does not work. **Expected:** either the operator can send completed work back in one move (a `completed -> revision_needed` edge for the operator, offered in the drawer as "Send back"), or every operator-facing remedy names the move that works. The first is the cleaner one: the gate already says "send it back" in four places. **Test:** beside `test_revision_returns_to_the_author.py`: a task completed by an agent, whose Land is refused, can be sent back by the operator with one PATCH and returns to its author; plus a check that no operator-facing Land refusal names `revision_needed` unless that move is legal from the task's status.

## F833 (C) -- a criterion-only amendment is recorded and shown as "reworded it" with the same wording twice, and the stale-evidence refusal says the requirement "has been reworded"

**Status:** fixed (iteration 45, Tier 0, commit f798785). Found 2026-10-20 by the day sweep `sweep-evidence-sweep`. Fix: the requirement detail route adds `change` to each revision (`spec_index.change_kind`: a `reworded` revision whose statement equals the one before is `criteria`; stored classification unchanged, so no migration), the story says "changed its acceptance criteria" with no repeated wording, and the `evidence_stale` refusal says the criteria changed when the statement stood (`spec_index.stale_cause`). Tests: `test_a_criterion_only_change_is_not_a_rewording`, `test_stale_refusal_for_a_criterion_change_does_not_say_reworded`, `requirementStory.test.tsx`. Drive: real routes over ASGI and database, real component in jsdom; no Chromium, no scratch Hub. Not done: the story does not name which criterion moved or its before/after. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8190, a real Haiku `checker` test turn calling `amend_spec_document`, Chromium: `scripts/drive/s1020_v_ui.py`).
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes
**Tier:** 0

```
checker (review turn on t-count) amend_spec_document op=change_criterion criterion=c-count change={"then": "it returns 3, as an int"}
GET /spec/requirements/FR-2 -> revisions: [created "The package MUST offer count() ...",
                                           reworded (actor checker) "The package MUST offer count() ..."]  -- same statement
RequirementStory (Chromium): "You wrote it ... The package MUST offer count() ...  /  checker reworded it ... The package MUST offer count() ..."
  chip "current"; Evidence "2 for an earlier wording"; nothing names criterion c-count or the unreviewed amendment
decide_evidence(ev-a650d4cd3b7a, accepted) -> 409 "ev-a650d4cd3b7a was recorded for an earlier wording of FR-2, which has been
  reworded since; it cannot be accepted."
```

The requirement's digest covers its criteria, so changing a criterion is correctly a new revision, and correctly makes earlier evidence stale. But `spec_index.py:268-277` classifies every digest change `REWORDED` and stores only the statement. The story (`RequirementStory.tsx:26`) then shows two identical wordings under "reworded it". The refusal (`requirement_evidence.py:1254`) sends the reader to compare statements that did not change. The story also reads "current" while coverage reads `amendment_unreviewed`. **Expected:** a revision whose statement is unchanged is classified as a criterion change. The story names the criterion and its before/after (the amendment row already holds `before` and `change`), and the stale refusal says "its criteria changed since" in that case. **Test:** in the spec-index tests: a change to a criterion alone records a revision that is not `reworded`; and the `evidence_stale` message for that piece names the criterion rather than a rewording.

## F835 (C) -- a dependent's turn refused because its prerequisite's merge could not be brought in is never tried again when the prerequisite lands: it sits `queued` behind a stale refusal until the operator presses Continue

**Status:** fixed 2026-10-22 (Tier 0): `task_transition_service._integrate_task` re-drains the project's queue (`turn_scheduler.redrain_queued_agents`) after the commit of any session whose integration `merged` (an `after_commit` listener, so an approval that rolls back drains nothing); and the prerequisite-merge refusal says "could not be merged into its base" unless git printed CONFLICT (`worktrees._merge_prerequisites`). Tests `test_a_merge_that_lands_redrains_the_queue.py` (all three failed before; the third is the finding's own repro with a real pre-merge-commit hook, real retry route, only the runner process faked: the queued dependent is delivered with no other call). Not done: the refusal still names the prerequisite by sha, not by task title. Not driven in Chromium. Day 2026-10-22 (`sweep-tasks-sweep`, :8114, Chromium): CONFIRMED live -- a hook refused A's merge (retryable), beta's trigger on B queued with "could not be merged into its base", the hook removed, the board card's Retry merged A and B's queued turn started with no other call (completed, its commit on top of the integration).
**Source:** drive
**Theme:** Dependencies
**Ready:** yes
**Tier:** 0

```
B depends_on A (both real Haiku tasks). project repo: .git/hooks/pre-merge-commit -> exit 1 ("policy: merges into master are frozen (hook)")
POST /tasks/<A>/land {}                       -> 200, A approved, latest_integration failed, retryable (F823 path)
GET  /tasks/<B>                               -> dependency_state null (released by A's approval)
POST /agent/trigger {agent: beta, task_id: B} -> 200 {"status": "queued", "waiting_reason": "Could not prepare the checkout for task <B>:
     the work <B> depends on conflicts with its base: merging prerequisite commit f9b6e8a188ec failed. policy: merges into master are frozen (hook) ..."}
remove the hook; drawer Try again on A    -> "Merged f9b6e8a1 into master" (08:18:01Z)
inbound_queue_entries <B's entry>          -> state queued, delivery_attempts 1, same waiting_reason -- still so at 08:39:14Z (21 min), no run started
conversation (Chromium): "1 waiting -- the last delivery attempt was refused: ... merges into master are frozen (hook) ... Continue"
press Continue                             -> POST .../conversations/<c>/continue, run-da547dc87e9d delivered, B's checkout has A's commit, task completed
```

The prerequisite merge in `worktrees.py:648-652` raises `IsolationUnavailableError`, which `agent_trigger.py:1523-1527` turns into the task-checkout refusal; the entry stays `queued` (correct: it is not the agent's fault). But nothing re-tries it: `redrain_queued_agents` runs only at a run's end, project open, settings save and relocate (`agent_trigger.py:3282-3293`, `:3786-3804`), and neither `POST /tasks/{id}/integrations/retry` (`tasks.py:1414-1449`) nor `land` / an approval that merges calls it. So the one event that clears the refusal (the prerequisite now on the main line) does not deliver the waiting work, and the screen keeps saying the merge is frozen after it went through. The same holds for any retryable integration failure (a hook, an index lock), not only this repro's hook. Smaller, same sentence: it says "the work <B> depends on conflicts with its base" for a merge that failed on a hook, not a conflict, and names the prerequisite by sha, not by task title. **Expected:** a successful integration (approve, Land, Retry) re-drains the project's queue as a run's end does; the refusal names the prerequisite task and says "could not be merged" rather than "conflicts" unless git reported a conflict. **Test:** `hub/tests/` beside the F158 prerequisite tests: a dependent entry refused by a failing prerequisite merge is delivered after `POST /tasks/{A}/integrations/retry` merges, without any other call (fails today: the entry stays `queued`).

## F836 (C) -- when deleting a task keeps its work (unmerged commits), nothing on screen says so: the drawer just closes, Activity shows a bare `task_checkout_kept`, and Worktrees lists the checkout under the deleted task's id as one "released when the task is approved or rejected"

**Status:** fixed 2026-10-22 (Tier 0): the `task_checkout_kept` event now carries the task's `title`; `eventSummary` reads "Kept <branch> (1 unmerged commit) from deleted task “<title>”" and `task_deleted` names the released tasks; `GET /worktrees` marks a task checkout whose task is gone (`task_deleted`) and the Worktrees panel says "Task deleted -- its work is kept on this branch." Tests: `eventSummary.test.ts` (2 cases), `worktreesPanel.test.tsx`, `test_a_task_checkout_says_when_its_task_is_gone`, title assertion in `test_deleting_a_task_names_the_work_it_leaves`. Not done: the drawer itself still closes silently after the 204 (no body, and `persist_event` does not broadcast, so there is nothing to toast; the Activity and Worktrees rows now say it); the delete-confirm text still promises everything "goes with it". Not driven in Chromium. Day 2026-10-22 (Chromium): the Worktrees panel's "Task deleted -- its work is kept on this branch." and the Logs view's sentence held; the confirm, the silent close and the Activity tab's default (digest) view did not -- filed as F916.
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

```
K1 worked by a real Haiku turn: commit 921a51d on agentweave/task/task-0a0ea57ec87c, task completed, checks passed
drawer -> Details -> Delete -> confirm: "Delete this task? Its own prerequisites, links, transitions and evidence go with it. This cannot be undone."
  (no word about the commit on its branch) -> Delete task -> drawer closes; page text has no "kept", "branch", "checkout", "unmerged"
event_logs: task_checkout_kept {"task_id": "task-0a0ea57ec87c", "branch": "agentweave/task/task-0a0ea57ec87c", "unmerged_commits": 1, "uncommitted": false}
Activity -> Activity feed row: "task_checkout_kept  warn  1 minute ago"            (no branch, no count, no task title)
           and "task_deleted  P2: prerequisite deleted from the drawer"             (released_dependents not shown)
Environment -> Worktrees: "Task checkouts -- One per task being worked. Released when the task is approved or rejected; the branch is kept.
           task-0a0ea57ec87c  ...\.agentweave\tasks\task-0a0ea57ec87c  agentweave/task/task-0a0ea57ec87c  No conflicts"   (no discard control)
control: K2 (no commit) deleted -> checkout and branch removed, no event (F828 holds)
```

The backend keeps and names the work correctly (F828), but `eventSummary.ts` has no case for `task_checkout_kept` or `task_deleted`'s `released_dependents`, so the default branch prints the event name; the task drawer's delete gets a 204 with no body; and `WorktreesPanel.tsx:129` describes a release that can no longer happen for a task that no longer exists. An operator who deleted a task cannot learn from the app that its commit survives on a branch, nor find which branch. **Expected:** the Activity row reads "Kept agentweave/task/<id> (1 unmerged commit) from deleted task “K1: add shop/tax.py”" (carry `title` in the event), and `task_deleted` names the released tasks; the drawer's delete, once done, says the same (the board can toast the event it already receives); the Worktrees row for a checkout whose task is gone says "task deleted -- 1 unmerged commit kept". Whether Worktrees should offer a discard control is a separate design question, not this fix. **Test:** `eventSummary.test.ts` cases for both payloads; a Worktrees panel test with a task checkout whose task 404s.

## F838 (C) -- deleting a document whose task kept work says only "Deleted “T” and its 2 tasks.": the 200's `kept_work` (branch, unmerged commit) never reaches the screen, and the confirm promises every task "goes with it"

**Status:** fixed 2026-10-22 (Tier 0): `useSpecDeletionStore` notices carry the 200's `kept_work`, and `SpecDeletedNote` adds "Kept <branch> (1 unmerged commit) from a deleted task." per entry (or the cleanup error). Test `names the branch a deleted task left with unmerged work (F838)` in `specFold.test.tsx` (failed before). Not done: the document-delete confirm still says every task "goes with it"; the document-delete `task_checkout_kept` events carry no task title. Not driven in Chromium.
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

```
approved change spec/changes/ui-delete2, task task-33a51cd750bc worked by a real Haiku turn: commit 3e1be22 on agentweave/task/task-33a51cd750bc
Spec tab -> spec-delete -> confirm: "Delete “ui-delete2 095124”? Its file, its requirements and their evidence, and every task it put on the
  board go with it. This cannot be undone."  -> Delete document
DELETE .../documents/spec/changes/ui-delete2/spec.json -> 200 {"deleted": true, "tasks": [2 ids], "requirements": 2,
  "kept_work": [{"task_id": "task-33a51cd750bc", "branch": "agentweave/task/task-33a51cd750bc", "unmerged_commits": 1, "uncommitted": false}]}
page after: spec-deleted-note "Deleted “ui-delete2 095124” and its 2 tasks."  -- body text has no "kept", "branch", "unmerged", "commit", "checkout"
git worktree list: .agentweave/tasks/task-33a51cd750bc 3e1be22 [agentweave/task/task-33a51cd750bc]   <- kept, correctly (F828 holds)
```

The backend keeps and names the work (F828 holds: the other task's clean checkout was discarded, this one kept, `task_checkout_kept` recorded). The UI drops it: `useDeleteSpecDocument` types the result as `{path, deleted, tasks}` (`hub/ui/src/api/spec.ts:1352`), `onConfirmDelete` stores only `tasks.length` (`hub/ui/src/components/spec/SpecPhaseBar.tsx:315-319`), and `SpecDeletedNote` has nothing else to say. The operator who deleted the document cannot learn from this screen that a commit survives, nor on which branch. **Expected:** the note adds "Kept agentweave/task/<id> (1 unmerged commit) from a deleted task." for each `kept_work` entry (and "uncommitted edits" when `uncommitted`). **Test:** `specFold.test.tsx` beside the existing `SpecDeletedNote` cases: a delete whose stubbed 200 carries `kept_work` must render the branch and count; fails today.

## F841 (C) -- "Look into it" can be pressed again while the first review runs: each press spawns a paid review of the same report, and the second records a `failed` firing "the outcome could not be stored (Report ... is answered, not pending.)"

**Status:** fixed 2026-10-22 (Tier 0): `vault_reports.prepare` claims the report in a per-process `_under_review` set and `review` releases it in a `finally`, so a second press (or a press beside a filing's own review) is refused 409 "Report R is already being looked into."; the card's button stays disabled once the Hub has queued the review. Tests: `test_a_report_under_review_is_not_looked_into_a_second_time` (failed before: second POST spawned a second review), `vaultTab` "re-reads the reports after a review is queued". Drive `scripts/drive/d1022_f841_review_twice.py` on scratch :8158, real Haiku: 202 + 409, one firing, no `failed`. Not covered: the claim is per process and per Hub run (a restart mid-review forgets it), and a press that reads `pending` just before another review settles can still pass.  [A residue of F801's door. Found by the day sweep `sweep-vault-sweep`.]
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

```
reports job on, runner Haiku; report rpt-3006877942ba pending (filed by a real Haiku turn while the job was off)
Vault -> Reports -> "Look into it" -> card: "Looking into it in the background. ..."; 3 s later the button is still enabled -> pressed again
manager_job_fired 09:02:45 vault-reports answered "answered: the entry stands"                                      cost 17253 micro-USD
manager_job_fired 09:02:59 vault-reports failed   "the outcome could not be stored (Report rpt-3006877942ba is answered, not pending.)"  cost 24442 micro-USD
same over the API: two concurrent POST .../vault/reports/rpt-dcaea150ac59/review -> 202, 202 -> two paid firings, one `written` (referred), one `failed`
```

`vault_reports.prepare` (`hub/hub/vault_reports.py:156`) checks `status == "pending"` and nothing marks the report as under review, so every press inside the review's ~10-13 s passes; the button is disabled only while the POST itself is in flight (`VaultPage.tsx:937`, `disabled={review.isPending}`), and F842 keeps the card reading `pending`, which invites the second press. The same race follows a press while the review a filing started (`review_in_background`, `agent_actions.py:620`) is still running. The Manager page then lists a `failed` firing for work that succeeded. **Expected:** one review per report at a time. The second press gets 409 "Report R is already being looked into", and the card's button goes once a 202 comes back. **Test:** `hub/tests/test_vault_reports.py` (beside `test_a_pending_report_is_looked_into_again_once_the_job_has_a_runner`): two concurrent POSTs with a faked worker that awaits an event -> one 202, one 409, one firing; fails today (two 202s).

## F842 (C) -- after "Look into it", the Reports list never re-reads: the card promises "The answer appears here when it finishes" and stays `pending` until a reload

**Status:** fixed 2026-10-22 (Tier 0): `VaultScreen`'s `onReviewReport` calls `watch()` after the 202, so the reports list re-reads every 3 s like after an upload and the answer appears without a reload. Test: `vaultTab` "re-reads the reports after a review is queued" (the answer must render after the 202 with no remount; failed before at the button seam, the same test). Drive: `d1022_f841_review_twice.py` covers the Hub half; **not driven in Chromium**.  [A residue of F801's door. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8151, `scripts/drive/s1021_v_ui.py`, Chromium; screenshots `testbed/ui-judge/s1021-vault/100012/02_runner_after.png`, `.../100233/04_twice_after.png`).]
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

```
10:00:18 press "Look into it" on rpt-19be8afdf6a0 -> "Looking into it in the background. The answer appears here when it finishes."
10:00:29 manager_job_fired vault-reports answered (GET /vault/reports: status "answered", answer "The source directly settles the report ...")
10:01:03 the same page, card: "pending ... Look into it  Looking into it in the background. ..."   (no refetch)
reload -> card: "answered ... The source directly settles the report ..."
```

`useVaultReports` polls only while `VaultPage`'s `watching` is set (`hub/ui/src/components/vault/VaultPage.tsx:72`), and only an upload or a Distil starts the watch; `ReviewReportButton` (`:931`) cannot, and `useReviewVaultReport` (`hub/ui/src/api/vault.ts:355-365`) invalidates the list once, at the 202, while the report is still pending. No SSE handler re-reads reports on `manager_job_fired`. **Expected:** a 202 from the review starts the same watch, or a `manager_job_fired` for `vault-reports` invalidates `['project', p, 'vault', 'reports']`, so the answer shows up as the note promises. **Test:** `hub/ui/src/__tests__/vaultTab.test.tsx` ("looks into a pending report again"): after the 202, a second GET of reports answering `answered` must render the answer without a remount; fails today (one GET).

## F844 (B) -- a conversation whose agent is busy in another conversation reads as its own live turn: "asker is responding…", a `running` chip and **Stop turn**, which stops the other conversation's run (here, one waiting on the operator's own question)

**Status:** fixed 2026-10-21 (night, Tier 0). The roster now carries `running_conversation_id` (newest running run's conversation); `AgentOutputPanel` reads a run on another conversation as `busyElsewhere`: the bar says "busy in <conversation>" (or "waiting on your answer in" when that run's question waits), with an Open link, no Stop; the placeholder says a message will queue. Test `agentBusyElsewhere.test.tsx` (fails before) and `test_list_agents_names_the_conversation_the_live_run_belongs_to`. Not driven in a browser. Found by the day sweep `sweep-questions-sweep` (scratch Hub :8152, profile q1021, Chromium against the served bundle, `scripts/drive/s1021_q_ui.py live|stopb`).
**Source:** drive
**Theme:** Conversations & composer
**Ready:** yes -- driven twice with real Haiku turns.
**Tier:** 0

Agent `asker` (`claude-haiku-4-5-20251001`). Conversation B (`conv-dcf733acc50f`) had one finished turn. A fresh turn in A (`conv-c328e0e052d5`, `run-1d1f9326627c`) called `ask_user` ("Which colour for the border?", wait 120 s) and was blocked on it. The operator opened B:

```
B header: asker  [running]  <tokens>  ...  [Stop turn]          (screenshot testbed/ui-judge/s1021-q-stopb/101510/B_stop_before.png)
B composer placeholder: "asker is responding…"
B, after typing a message (run live phase): "Queued — agent is already running"   (s1021-q-live/101133/B_while_A_waits_after.png)
press Stop turn in B -> POST /projects/{p}/agent/asker/stop -> A's run: status 'stopped'; A's question q-78be2ced7918 left open, asker_waiting false
B afterwards: chip 'idle', nothing saying which conversation's turn was stopped
```

Nothing in B says the turn is in another conversation, or that it is waiting on the operator's own answer there; the B message waited in the queue for as long as A's question did (up to the question's timeout). Cause: `AgentOutputPanel` takes `isRunning = agent.status === 'running'` (`hub/ui/src/components/agents/AgentOutputPanel.tsx:384`), the agent's state, not the conversation's, and feeds it to the chip, the composer placeholder (`Composer.tsx:316`) and the Stop control (`ConversationControls.tsx:91`). `handleStop` (`AgentOutputPanel.tsx:878-887`) posts `POST /agent/{agent}/stop`, which stops the agent's newest running run whatever its conversation (`hub/hub/api/v1/agent_trigger.py:2547-2553`).

**Expected:** in a conversation that is not the one the live run belongs to, the header says the agent is busy in another conversation (named, linked) and, when that run waits on a question, says so ("waiting on your answer in <conversation>"); the placeholder says the message will queue; Stop turn is either absent there or names the conversation it stops. **Tests:** a UI test beside `hub/ui/src/__tests__/questionTrayConversation.test.tsx`: with the agent `running` on a run whose `conversation_id` is A, rendering conversation B shows no "Stop turn" (or one labelled with A) and no "is responding" placeholder; fails today. Seam: Conversations & composer x Runs x Questions.

## F849 (C) -- an agent a session sync deletes leaves its conversations open; the rail files them under "agent archived", and an agent later created with the same name inherits them and resumes the deleted agent's provider session

**Status:** fixed 2026-10-22 (Tier 0): `sync_session` archives the departing agent's open conversations in the same commit as the delete, so a later agent of the name has none to resume (a trigger naming the old id is refused as archived); test `test_sync_that_deletes_an_agent_archives_its_open_conversations` failed before; drive `scripts/drive/d1022_f849_sync_deletes_agent.py` on scratch :8159, real Haiku, 7/7. Original report: Found by the day sweep `sweep-agents-sweep` (scratch Hub :8154, profile a1021, three real Haiku turns, Chromium against the served bundle, `scripts/drive/s1021_a_api.py history turn|remove|recreate`, `s1021_a_ui.py removed`). F810's fix refuses the deletion only while an entry is `queued`; an agent with a finished history is still deleted, and this is what it leaves.
**Source:** drive
**Theme:** Agents
**Ready:** yes
**Tier:** 0

gamma (Haiku) ran one turn, "Reply with the single word PONG" (`run-2b5931fb62a9`, completed, `conv-c7cc72d97030`, provider session `b82eaf02-…`). `POST /session/sync {"data": {"agents": {"alpha": {}, "beta": {}, "eps": {}}}}` -> 200 `removed: ["gamma"]`. The Agent row went; `conv-c7cc72d97030` stayed `lifecycle: open` and is still listed by `GET /conversations`. Then `POST /agents {"name": "gamma", ...}` -> 201 (a new agent, `agent-06a9bdd093fb`). The palette (Ctrl+K) and gamma's rail group list the old conversation as the new gamma's. `POST /agent/trigger {"agent": "gamma", "conversation_id": "conv-c7cc72d97030", "message": "...what single word did you reply with earlier...?"}` -> 200, `provider_session_id: "b82eaf02-…"`, and the new agent answered **"PONG."** (`run-688f1d04e180`). It resumed the deleted agent's session and memory. The Ledger's "By agent" also adds the deleted gamma's spend to the new one. Before re-creation, the same residue for kappa (deleted the same way) shows in the rail as "Archived agents · Say hello. · **agent archived**" (`testbed/ui-judge/s1021-a-removed/104643/removed-2-reload.png`). The page itself says "kappa is not on this project's roster", but the row's label and its title "kappa is archived; open this to unarchive it" (`ConversationRow.tsx:224`) name an archive that never happened and an unarchive that cannot work.

Cause: conversations, runs and ledger rows are keyed by the agent's *name* string, and `sync_session` (`hub/hub/api/v1/session_sync.py:174`) deletes only the `Agent` row. `AgentTree.tsx:73-77` treats any conversation whose agent is not on the open roster as an archived agent's. Archive keeps the name for ever ("a name is never reused", F465), but the sync deletion frees it.

**Expected:** a sync deletion archives the departing agent's open conversations (`lifecycle: archived`) in the same commit, so nothing open belongs to a name with no agent. Alternatively, refuse the deletion as F810 does for queued entries, naming the conversations. Either way, a later agent of the same name starts with no conversation and no provider session of the old one. **Test:** `hub/tests/test_session_sync.py`: an agent with one conversation holding a `provider_session_id`, synced away, then re-created by `POST /agents`. `GET /conversations` lists no open conversation for it, and a trigger naming the old `conversation_id` is refused, not resumed. Fails today. Seam: Agents (roster sync) x Conversations & composer.

**Re-verified 2026-10-22** (day sweep `sweep-agents-sweep`, scratch Hub :8116, Chromium against the served bundle, `scripts/drive/s1022_ag_ui.py sync|after`): fix holds. With gamma's conversation open, `POST /session/sync` omitting gamma -> 200 `removed: ["gamma"]`; the conversation is `archived`, the page reads "gamma is not on this project's roster." with no composer; after `POST /agents {"name": "gamma"}` (201) the new gamma's rail group reads "No conversations yet". (A job naming the deleted agent is a different hole: F925.)

## F850 (D) -- a session sync that deletes an agent leaves it in the rail until a reload: `session_synced` never refreshes the projects summary the rail reads, and the Activity row is a bare `agent_removed`

**Status:** fixed 2026-10-22 (Tier 0): the central SSE switch invalidates `['projects']` and the conversations list on `session_synced`, and `eventSummary` reads `agent_removed` as "lam was removed from the roster by a session sync"; tests in `useSSE.test.tsx` and `eventSummary.test.ts` failed before. Not driven in Chromium. Original report: Found by the day sweep `sweep-agents-sweep` (scratch Hub :8154, Chromium against the served bundle, `scripts/drive/s1021_a_ui.py removed` and an inline live probe).
**Source:** drive
**Theme:** Agents
**Ready:** yes
**Tier:** 0

With the dashboard open, `POST /agents {"name": "lam"}` (201) and then `POST /session/sync` omitting lam -> 200 `removed: ["lam"]`. Polled at +2, +6, +15 and +30 s, the rail still listed **lam** ("No activity yet") and the header still said "4 agents". A reload dropped it. The same happened to kappa while its conversation was open. The `agent_removed` event F812 added does reach Activity and Logs, as a WARN row reading `lam agent_removed`. The Logs message column repeats the type, and neither says it was a session sync (`data.by: "session_sync"`) (`testbed/ui-judge/s1021-a-activity2/105128/sub-logs.png`).

Cause: the rail's agents are the projects summary (`Sidebar.tsx:433` `agents={project.agents}`). On `session_synced`, `useAgents` invalidates only `['project', projectId, 'agents']` (`hub/ui/src/api/agents.ts:218-223`). The archive mutation also invalidates `['projects']` (`agents.ts:273-275`), and the sync handler does not.

**Expected:** `session_synced` also invalidates the `['projects']` summary (and the conversations list), so a deleted agent leaves the rail live. The Activity/Logs message for `agent_removed` reads "lam was removed from the roster by a session sync". **Test:** `hub/ui/src/__tests__/useSSE.test.tsx` (or an AgentTree test): dispatch `session_synced` with `removed: ["lam"]` and assert the `['projects']` query is invalidated; fails today. Seam: Agents (roster sync) x Logs, events & SSE.

**Re-verified 2026-10-22** (day sweep `sweep-agents-sweep`, Chromium, `scripts/drive/s1022_ag_ui.py sync|views`): fix holds in the browser. The rail dropped gamma within 3 s of the sync, no reload; the Logs view reads "gamma was removed from the roster by a session sync". The Activity view (the digest) still reads "gamma agent removed": recorded on F908, whose fallback it is.

## F900 (C) -- two files added to the vault by path, each named `README.md`, are both listed as "README.md"

**Status:** fixed a92a822 2026-10-20 (Tier 0): a file added by path inside the project directory or the agent's workspace is named by its path there (`app/README.md`, `plugins/export/README.md`), the nearest root winning; a folder outside both keeps its name in front as before.
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

Found on the Terra replica (`:8130`, `proj-cd006955cbe2`) during the ui-finesse mock review (handoff 0204): one operator batch at 2026-10-20T18:16:19 added `app/README.md`, `plugins/export/README.md` and `plugins/export/docs/format.md` by path, and the map listed them as `README.md`, `README.md` and `format.md` (`GET /vault/map`). The Library could only tell the two READMEs apart by their opening lines. `vault_intake.expand` named a single file `located.name`, and a folder's files `<folder name>/<path beneath it>`, never the path from the project. Test: `test_files_named_alike_in_different_folders_keep_the_path_that_tells_them_apart` (`hub/tests/test_vault_paths.py`), failing before the fix (`'README.md' != 'app/README.md'`). Seam: Knowledge vault (add by path) x the Vault tab's Library. Not covered: two files with the same name outside the project and the workspace still share a name (no root to name them from).

## F901 (C) -- the Vault reader's "Used by" can say how often an entry was read, never by which agent

**Status:** fixed a92a822 2026-10-20 (Tier 2, migration 0140 -- renumbered from 0139 at the merge with the night branch, whose F761 took 0139 -- change `the-vault-names-who-read-an-entry`): an agent's `vault_read` at offset 0 is recorded against the run credential's agent in `vault_readers`, and both maps and both entry routes list `readers` ({agent, count, last_read_at}, most recent first). The reader's Used by tab names each agent with its count and last read, and says how many earlier reads predate the record (`vaultAccess.test.tsx`).
**Source:** operator
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 2

The ui-finesse mock's reader has a "Used by" tab (`hub/ui/src/components/vault/VaultReader.tsx`), and the operator asked for it to name the agents (handoff 0204, open question 2; answered "Build as Tier 0/1 now" on 2026-10-20). `vault_fetches` (migration 0126) holds one count per entry, no agent, so the tab could only say "Read 3 times". Tests: `hub/tests/test_vault_readers.py` (written first; failed on `KeyError: 'readers'` and the missing model), `test_migration_vault_readers_creates_the_table_and_its_downgrade_drops_only_it`. Reads counted before 0139 stay unattributed, so `fetches` may exceed the readers' sum. Seam: Knowledge vault (agent reads) x the Vault tab.

## F902 (C) -- the compact task card shows one fact at a time: a task both waiting and stalled shows only "waiting"

**Status:** fixed 2026-10-22 (night window, Tier 0). `cardStatus` keeps the stalled fact beside the wait: "Waiting on you · <why> · stalled", the title carrying the dropped-run sentence (`taskCardCompact.test.tsx`, failed before). Original: open 2026-10-20. Found applying the ui-finesse mock (`ui/finesse-mocks`), porting the old `TaskCard` tests to `TaskCardCompact`.
**Source:** code
**Theme:** Tasks
**Ready:** yes
**Tier:** 0

`cardStatus()` (`hub/ui/src/lib/taskCardStatus.ts`) returns the first matching fact for the card's one status line. The old card showed blocked/waiting and stalled side by side; now a task that is waiting on the operator *and* whose last run ended without changing its status shows only "waiting", and the drawer shows no divergence state either (only the policy control), so "stalled" is shown nowhere. Expected: the status line carries the second fact (e.g. "Waiting on you · stalled"), or the drawer states it. Test: a `taskCardCompact` case with both facts set. Seam: Tasks (card) x Runs.

## F903 (C) -- a requirement awaiting review lost its own tone on the task card and in the drawer

**Status:** fixed 2026-10-22 (night window, Tier 0). `useRequirementTallies` counts `evidence_awaiting_review` and the card's tally names it in its title ("1 awaiting review") and in `data-awaiting-review`, amber when nothing is rejected (`taskRequirementLinks.test.tsx`, failed before). The drawer's Serves list still carries no coverage tone. Original: open 2026-10-20. Found in the same port as F902. Day 2026-10-22 (Chromium): held on the card -- `0/1 FR`, `data-awaiting-review=true`, title "0 of 1 requirements verified, 1 awaiting review".
**Source:** code
**Theme:** Tasks
**Ready:** yes
**Tier:** 0

The old card's per-requirement chips gave a requirement awaiting review a pending tone. The compact card replaces the chips with a tally (`N/M FR`) that does not count it, and the drawer's Serves list has no coverage tone, so "this requirement is waiting for review" is shown nowhere. Expected: the tally's title or the drawer's Serves list names requirements awaiting review. Test: `taskRequirementLinks.test.tsx`, a requirement in review. Seam: Tasks x Spec (coverage).

## F904 (C) -- the Overview's "Needs you" lost two question behaviours: blocking questions first, and no "waiting" claim for a non-blocking one

**Status:** fixed 2026-10-22 (night window, Tier 0). `OverviewScreen` orders questions an agent is blocked on first (stable) and each question's meta says "is waiting" or "is asking" (`overviewScreen.test.tsx`, failed before); `QuestionInterruptCard.tsx` and its test deleted. Original: open 2026-10-20. Found in the same port as F902.
**Source:** code
**Theme:** Overview
**Ready:** yes
**Tier:** 0

`QuestionInterruptCard` (now rendered by nothing, kept so this is not lost) put the question an agent is blocked on first, and did not say anyone waits on a non-blocking question. `OverviewScreen`/`OverviewView` order "Needs you" by time and word every question alike. Expected: blocking questions first; a non-blocking one is not described as something an agent waits on. Test: `overviewScreen.test.tsx`, one blocking and one non-blocking question. Then delete `QuestionInterruptCard.tsx`. Seam: Overview x Questions.

## F905 (C) -- the compact task card offers Retry on every unmerged task, even one a retry can never clear

**Status:** fixed 2026-10-22 (night window, Tier 0). `TaskIntegrationSummary.retryable` (computed from `task_integration.is_retryable`) rides every task payload; the card offers Retry only when it is true (`test_task_integration.py`, `taskCardCompact.test.tsx`, failed before). Driven on :8162 in Chromium: an approved task skipped with "nothing to merge" shows "Not merged", no Retry. The Overview's merge rows offer only Open task, so they needed no change. Original: open 2026-10-20. Found in the same port as F902. Day 2026-10-22 (Chromium, :8114): held both ways -- a hook-failed merge shows "Merge failed" with Retry (and Retry merged it); a "nothing to merge" skip shows "Not merged", no Retry on the card, no Try again in the drawer.
**Source:** code
**Theme:** Tasks
**Ready:** yes
**Tier:** 0

`TaskCardCompact` shows Retry whenever `latest_integration` is not merged. `latest_integration` in the task-list payload carries no retryability, so a skip that retrying cannot clear ("already in master; nothing to merge", a missing main branch) still shows the button; `TaskIntegrationNote` in the drawer gets it right from the integration route. The same goes for the Overview's "approved but not merged" rows. Expected: the list payload carries `retryable` (Hub) and the card shows Retry only then. Tests: `hub/tests` for the field, `taskCardCompact` for the button. Seam: Tasks x Integration.


## F906 (B) -- the clientless-route ratchet measures nothing: `n10_route_reachability.py` reads 0 declared `/api/v1` routes

**Status:** fixed 2026-10-22 (night window, Tier 0). Cause: `app.routes` holds `_IncludedRouter` wrappers with relative paths on Starlette 1.x, so `declared_routes()` found none. It now walks the table with `hub/tests/_routing.py`'s `iter_api_routes` (241 route+method pairs, 19 clientless); `test_no_new_route_without_a_client` asserts the rows are non-empty (failed before), and the ceiling is lowered 21 -> 19 to the real count. Original: open 2026-10-20. Found by the n11 ratchet repair during the ui-finesse apply.
**Source:** code
**Theme:** Tooling
**Ready:** yes
**Tier:** 0

`test_no_new_route_without_a_client` warns "routes with no client anywhere dropped to 0 from a ceiling of 21". The drop is not a repair: `n10` finds zero declared routes, in this worktree and in the main checkout alike, so the count is 0 whatever the clients do and the ratchet cannot fail. Expected: `n10` reads the route table (or the test fails, rather than passes, when it reads none). Test: assert the declared-route count is > 0 before ratcheting. Seam: Tooling (surface ratchets) x the Hub route table.

## F852 (B) -- an agent piece that names no commit, recorded in a task checkout before the task's first commit, still shows master's HEAD commit as its work (F761's unmeasured case)

**Status:** fixed 2026-10-22 (night window, Tier 0); **confirmed live 2026-10-22** by the day sweep `sweep-evidence-sweep` (:8124, two real Haiku turns, `scripts/drive/s1022_ev_drive.py nowork|work|merge`, Chromium `s1022_ev_ui.py`): builder's unnamed FR-3 piece in a fresh task checkout at master's tip (`8d3c6ce`, FR-1's sort commit) answers `files: []` and "…checkout at 8d3c6cebc6b3 on agentweave/task/…, already on the main line, which is not work of its own…", shown under the opened row in the Evidence view; builder's unnamed FR-2 piece with real uncommitted work was re-stamped to its snapshot commit and diffs `todo/items.py` (+count()), still after Land merged it `--no-ff` (`reachable_from_main` 1). Residue in the gate sentence and the coverage bar: F957. `work_diff` takes `unnamed`; an unnamed piece whose commit is on main's own first-parent chain answers no files and the F761 reason, whichever branch the checkout was on. Not the stored `reachable_from_main`, which `refresh_reachability` overwrites at merge (the finding's premise missed this); the Hub merges `--no-ff`, so integrated work is never on that chain. Test beside F761's. Not driven on a live Hub. Original: open 2026-10-21. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8155, a real Haiku `builder` turn, Chromium on the served bundle: `scripts/drive/s1021_e_f761.py`, `s1021_e_ui.py`). F761's fix holds for the case it measured (an operator piece on master); this is the case its Status line names as not measured.
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes -- repro below.
**Tier:** 0

```
master: commit dc83446 "sort names (made for FR-1)" -> todo/items.py  return sorted(...)
POST /agent/trigger builder, task t-total (FR-3), --perm workspace: "do not edit or commit; run total(); record_evidence FR-3, no commit, no locator"
  builder (aw-tool record_evidence) -> ev-841c7f0fb485 awaiting, "recorded on the current branch agentweave/task/task-83948495b82c, commit dc83446d"
evidence_footprints: commit_sha dc83446d.., branch agentweave/task/task-83948495b82c, commit_named 0, reachable_from_main 1, watched_from []
GET /spec/evidence/ev-841c7f0fb485/diff -> 200 files [todo/items.py M "-    return [n for n, _ in ITEMS] / +    return sorted(n for n, _ in ITEMS)"],
                                           base e6038937 (dc83446^), reason null
Evidence view (Chromium), the FR-3 piece opened: "dc83446d on agentweave/task/task-83948495b82c  todo/items.py modified +1-1 ... return sorted(...)"
```

The piece's task checkout was created at master's tip and has no commit of its own, so the footprint's commit is master's HEAD, which is FR-1's sort change. The guard F761 added (`requirement_evidence.work_diff`, `hub/hub/requirement_evidence.py:862`) fires only when `unnamed_branch == main`; here the branch is the task's, so `_line_of_work_base` finds the commit already on main and falls back to `commit^` (`:840`), and the Evidence view presents an unrelated requirement's change as this piece's work. The footprint already stores what is needed: `commit_named` is 0 and `reachable_from_main` was 1 at recording. **Expected:** a piece that named no commit, whose footprint commit was already on the main line when it was recorded, answers no files and the F761 reason (naming the checkout's commit and branch), whichever branch it was recorded on. Check that an agent re-stamp, which moves the footprint to the agent's own later commit, also clears or recomputes `reachable_from_main`, so a re-stamped piece still diffs its real work. **Test:** beside F761's in `hub/tests/test_evidence_carries_what_it_takes_to_judge_it.py`: create a task branch at main's tip, record an unnamed piece with the checkout there, and read the diff, which should have no files and a reason (fails today: it answers main's HEAD patch).

## F856 (C) -- a GitHub token (`ghp_...`) in an operator message or an agent reply is stored and exported verbatim in the run's trace, while an `sk-` key beside it in the same string is redacted

**Status:** fixed 2026-10-22 (night window, Tier 2): `_TEXT_TOKEN_RE` names `gh[pousr]_` + 36 and `github_pat_` + 22 at a word start. Change `a-github-token-in-prose-is-redacted` (spdoc-15471a5288ee, approve_anyway, folded into `agent-stream-events`, archived). Acceptance drive `scripts/drive/d1022_f856_github_token.py`: 6 FAIL before, 19/19 PASS after on scratch :8157. Rows stored before the fix keep their token (no backfill). Was: open 2026-10-21. Found by the day sweep `sweep-traces-sweep` (scratch Hub :8156, `scripts/drive/s1021_tr_traces.py redact`, `proj-65bd45d1fb38`, run-19d5dfe8bbb5, one real Haiku 4.5 turn).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 2 -- secrets (CLAUDE.md's table); the diff itself is one alternative in a regex.

```
POST /projects/{p}/agent/trigger {"agent":"tracer","overrides":{"permission_mode":"workspace"},
  "message":"Run exactly this one shell command ... echo token=ghp_Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2 key=sk-ant-api03-FAKEfake0987654321zyxwvuABC"}
GET /traces/by-run/run-19d5dfe8bbb5 -> "...token=ghp_Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2 key=<redacted>..."
  ghp_ token present in: aw.deliver `aw.queue.content`, invoke_agent `gen_ai.input.messages`,
  chat `gen_ai.output.messages` (Haiku declined the command and quoted the token back)
GET /traces/export -> ghp_ token present, sk- key absent; agent_outputs text row: ghp_ present
event_logs and /events/history for the run: neither value present
```

The prose floor `runner_events.redact_text_secrets` knows only `aw_live_`, `aw_run_` and `sk-` tokens plus credential-named fields (`_TEXT_TOKEN_RE`, `hub/hub/runner_events.py:127`). That is deliberate: F602 keeps the high-entropy catch-all out of prose so that commit SHAs and paths survive, and F790 confirmed that the prompt and the model text follow the conversation's rule. But GitHub's token prefixes (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`) are as unambiguous as `sk-`. They are the credential an operator of a git-centred tool is most likely to paste, and with export enabled the trace pushes them to an external OTLP collector. **Expected:** `_TEXT_TOKEN_RE` (and so `run_secrets.scrub_stream`'s joined-prose match) also names `gh[pousr]_[A-Za-z0-9]{36,}` and `github_pat_[A-Za-z0-9_]{22,}`, anchored at a word start as the others are. Then the queue content, the prompt, the model text, the text row and the export all read `<redacted>`. **Test:** in `test_a_secret_in_reply_text_is_redacted.py`, a text row and a trace's `gen_ai.input.messages` carrying `ghp_` + 36 base62 characters store `<redacted>`, while a 40-hex commit SHA in the same row is kept. The spec to amend is the requirement in `spec/changes/a-secret-in-reply-text-is-redacted` that names the patterns.

## F860 (B) -- the conversation never shows a tool's output: an expanded tool row reads only "tool completed" or "tool failed", so a Hub refusal's sentence (F794's read grant included) never reaches the place the operator watches the turn

**Status:** fixed 2026-10-22 (Tier 0): `WorkRow` (`AgentTimeline.tsx`) now shows the paired result's `payload.output`, falling back to `content`. Tests in `agentTimeline.test.tsx` (the refusal case failed before; the fallback case pins the old reading); full vitest 2228 passed, eslint and tsc clean; UI bundle refreshed. Tested through the real component, not driven in a browser. **Confirmed in Chromium 2026-10-23** (day `sweep-questions-sweep`, :8117, `scripts/drive/s1023_cv_live.py`): the expanded `mcp__agentweave__send_message` row shows its arguments and the whole refusal "Hub rejected POST /messages (404): The operator is not a message recipient. ..." (`testbed/ui-judge/s1023-conversations/122507/f860_row_8.png`). Originally: open 2026-10-21. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8157, Chromium on the served bundle, `scripts/drive/s1021_rc_reach_ui.py`, conversation conv-e5e9db86ecb0, run-e34a086c8e63).
**Source:** drive
**Theme:** Conversations & composer
**Ready:** yes
**Tier:** 0

A Haiku turn under Workspace only with a read root: Read allowed, Bash and Write in the read root refused, a Bash `cat` of an ungranted path refused. In the conversation, with every work block opened and every tool row expanded, each refused row reads `Bash · failed`, the command, and `tool failed`. The Read row reads `tool completed`. The page text has no "granted for reading only", no "outside your workspace" and no "heron-5521". The stored rows hold all of it: `agent_outputs.content` is the summary `tool failed`, and `payload.output` is `Denied: 'C:/Users/huida/Documents/reach1020-read/notes.txt' is in a folder the operator granted for reading only: read it with your file-reading tool ...` (the Read's is `1\tThe word is heron-5521.`). The timeline route returns that payload unchanged (`agent_chat.py:233-243`). The refusal reaches the operator only in Activity and Logs, which do show the sentence.

Cause: `tool_result_event` (`hub/hub/runner_events.py:318-345`) writes `content = "<tool> completed|failed"` and the output into `payload.output` (redacted and capped at `MAX_TOOL_RESULT_BYTES`). `WorkRow` (`hub/ui/src/components/agents/AgentTimeline.tsx:959-961`) takes `resultBody` from `paired.content`, which is always the summary, and nothing under `hub/ui/src` reads `payload.output` (grep: no hit outside evidence). Its own comment says "The result body is worth reading". F144 (2026-09) noted that results record as `tool completed`; the output has since been stored, and the screen was never wired to it.

**Expected:** an expanded tool row shows the paired result's `payload.output` (already redacted and capped), falling back to `content`. A refused call then shows the Hub's sentence under its command. **Test:** an `AgentTimeline` test whose `tool_result` entry carries `content: "tool failed"` and `payload.output: "Denied: ... granted for reading only ..."`, in the order the timeline route returns (tool_use, then tool_result). The expanded row renders the output text. Seam: Runs (runner events) x Conversations (work rows) x Permissions & sandbox (refusal legibility).

## F861 (B) -- an agent's `archive_job` puts a card to the operator that does not say which job: "cla wants to use archive_job — no details given — the provider sent none"

**Status:** fixed 2026-10-21 (Tier 0): the archive route's direction request now carries `{job_id, job_name, cron}` (`jobs.py`), and `PermissionRequestCard.describe` renders "name (cron)"; its last fallback is the neutral "no details given", no longer blaming a provider. Tests `test_the_archive_card_names_the_job_it_asks_about` (failed before) and `names the job an archive request is about`; 57 Hub tests and 34 card tests pass; UI bundle refreshed. Tested through the real route and the real component, not driven in a browser. **Held live 2026-10-22** (`sweep-loops-sweep`, Chromium, :8117): the card read "alpha wants to use archive_job · archive-me (0 4 * * *)", Allow archived it; its placement is F928. Originally: open 2026-10-21. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8157, Chromium, `scripts/drive/s1021_rc_archive.py`, runs run-d64b7d0cdc12 and run-98d3f8072dca).
**Source:** drive
**Theme:** Capability plane
**Ready:** yes
**Tier:** 0

With `allow_agent_jobs` on, Haiku called `mcp__agentweave__archive_job` on `job-bdd57e64ad62` ("archive-me", cron `0 4 * * *`). The route opened its always-ask request (409 `operator_direction_required`), and the card in the conversation read in full: "Tool request · cla wants to use archive_job · no details given — the provider sent none · Allow · Deny · The agent is waiting, and will be refused if nobody answers." Deny -> the agent got "archiving this job was not approved: the operator refused this action" and the job stayed; Allow (fresh conversation, job-e91d95486bc7) -> archived. Both decisions held, but the operator made each one without being told which job, its name or its schedule. "The provider sent none" is untrue as well: the Hub opened this request itself (`hub/hub/api/v1/jobs.py:1570-1572`, `tool_input={"job_id": job_id}`), not a provider. This is the one tool whose design (D18, `mcp_server.py:1056-1080`) exists to put "this exact request" to the operator.

Cause: `describe` (`hub/ui/src/components/agents/PermissionRequestCard.tsx:21-46`) knows only `file_path`/`path`/`notebook_path`/`command`/`paths`/`grantRoot`/`cwd`/`reason`, and `job_id` is none of them. The request's `tool_input` carries only the id.

**Expected:** the card names the job: for example, the Hub puts the job's name and schedule into the request (`{"job_id", "job_name", "cron"}`, or a `reason` sentence such as "Archive job 'archive-me' (0 4 * * *, cla)"), and the card renders it. Where nothing matches, the fallback does not blame a provider for a request the Hub opened. **Test:** a Hub test that the archive route's direction request carries the job's name, plus a `PermissionRequestCard` test that a request `{tool_name: "archive_job", tool_input: {job_id, job_name}}` shows the name and not "the provider sent none". Seam: Capability plane (always-ask archive) x Permissions & sandbox (the card).

## F864 (B) -- a flow whose own agent is also its named reviewer still hands that agent fresh work while another agent is free, so the task it builds can never be reviewed (F767's species, through the default-agent arm)

**Status:** fixed 2026-10-21 (Tier 0): `scheduler._agents_withheld_from_fresh_work` is now the one home of F767's withholding rule (pool and default-agent arm both ask it); `decide_firing` skips its default-agent branch when that agent is a named judge and somebody else has a runner, so alpha (agent == reviewer) is kept for review and beta builds. Test `test_the_flows_own_agent_is_not_offered_fresh_work_when_it_is_also_the_reviewer` failed before (selected alpha), passes; 374 flow/loop/review/scheduler tests pass. Tested at `decide_firing`, not driven on a live Hub. **Held live 2026-10-22** (`sweep-loops-sweep`, :8117, flow agent = reviewer = alpha): the first press briefed beta only, the second staged alpha's review of beta's task and gave beta the other, both approved and merged, the loop ended `completed`. Originally: open 2026-10-21. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8159, profile l1021, project `proj-4420966f352c`).
**Source:** drive
**Theme:** Flows & review
**Ready:** yes
**Tier:** 0

Repro (`scripts/drive/s1021_l_flow.py hold|start|fire`): two Haiku agents, alpha and beta. A change with two independent tasks (`t-cv`, `t-trunc`) and `delivery: {mode: flow, agent: alpha, reviewer: alpha}`, approved with `approve_anyway`. `POST /jobs/{id}/run` started **both** tasks: t-cv to **alpha**, t-trunc to beta. Both completed. The next firing staged t-trunc's review to alpha (approved it) and emitted `review_unstaffed` for t-cv: "this task names 'alpha' as its reviewer, and that agent is the one that completed this task. Naming a different reviewer, or reviewing it yourself, is the way forward -- the flow will not substitute somebody else for a named reviewer." The loop then reads `stalled` with that sentence, and t-cv waits on the operator.

F767's fix withholds named reviewers from the flow's recruitment pool (`scheduler._agents_a_loop_may_staff`, `hub/hub/scheduler.py:1366-1402`). That docstring states the job's own agent "never comes from this pool": `decide_firing`'s ordinary-work arm takes `default_agent` first for the first unstaffed task (`scheduler.py:2084-2102`), tested against `running`/`held_agents`/`taken` only. So when the delivery's `agent` and `reviewer` are the same agent, the withholding never applies, and the outcome is exactly F767's: unreviewable by construction while beta was free to build.

Expected: the default-agent arm applies the same rule as the pool. A default agent the document names to judge work takes fresh work only when no other agent with a runner could (the same roster test `_agents_a_loop_may_staff` uses), so here alpha reviews and beta builds both tasks in turn. **Test:** beside `hub/tests/test_a_flow_does_not_hand_fresh_work_to_its_named_reviewer.py`, a flow with `delivery.agent == delivery.reviewer == "alpha"`, two ready independent tasks and alpha and beta free: `decide_firing` selects alpha for neither task. Seam: Flows & review (D2's default agent x the named reviewer).

## F865 (B) -- with git unreadable for a moment, Land approves a task the preview said approval would refuse for a conflict; once git is back every retry fails on the conflict, and the task stays `approved` with its work never merged

**Status:** fixed 8c95b19 2026-10-21 (Tier 0): `requirement_gate.situation_or_fault` tells git-unreadable-with-proof from no-repository, and `evaluate` refuses with a `git_unreadable` entry ("git could not be read in the project's folder, so whether this work merges is unknown (...): try again in a moment"); a folder that never was a repository approves unchanged. Tested through the real task route with real git (`test_git_unreadable_does_not_approve_work_that_conflicts`, F865's own repro; F820's test now expects the refusal and a merge on the retry); 202 gate/approval/land tests pass. Tested, not driven on a live Hub. Originally: open 2026-10-21, found by the day sweep `sweep-loops-sweep` (Resilience, failure injection; scratch Hub :8159), while re-driving F820 live.
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

Repro (`scripts/drive/s1021_l_resil.py land_nogit task-9ad5210fd05c`, after the F864 flow): t-trunc was approved and merged, so t-cv's commit `fb04875` conflicts on `mathkit/registry.py`. Its evidence accepted, `GET /tasks/{id}/integration-preview` -> `"conflicts": [{"paths": ["mathkit/registry.py"]}]`, `"reason": "approval will be refused: mathkit/registry.py in commit fb04875d1692 conflict with master"`. Move the project's `.git` aside, `POST /tasks/{id}/land {}` -> **200, `status: approved`**, and the integration row is F820's `failed` "git could not be read in the project's folder ...", `retryable: true`. Restore `.git`; in Chromium the drawer's **Try again** (F823) records a second `failed` row, "CONFLICT (content): Merge conflict in mathkit/registry.py". The task is `approved`, its work is not in master, and every further retry fails the same way. The flow's loop then reads `complete` in the Loops panel.

Cause: the gate's merge question is skipped when git cannot be read. `requirement_gate.merge_situation` returns `None` when `task_integration.is_repository(root)` is false (`hub/hub/requirement_gate.py:658-659`), and `None` means "not checked, approve" (`_check_mergeable` is never asked). F820's fix taught `_integrate_task` to tell an unreadable repository from no repository (`repository_proof`), but the gate in front of it still reads a git failure as "no repository". With git readable, the preview says the same Land is refused naming the conflict (not re-pressed: the task had already been approved).

Expected: where the Hub has proof the project is a repository (F820's `repository_proof`: the task's worktree exists, or its evidence names a commit), an unreadable git refuses approval with a sentence ("git could not be read in the project's folder, so whether this work merges is unknown: try again in a moment"), rather than approving unchecked. **Test:** in `hub/tests/test_task_integration.py` (beside F820's `..._unreadable_for_a_moment...`), a task whose commit conflicts with master and whose worktree exists, with `.git` renamed away: `POST /land` does not answer 200 `approved`. Seam: Worktrees & integration (approval gate) x Resilience (git fault).

## F907 (B) -- the Activity digest leaves a stopped or failed turn reading "alpha is working" forever, and puts its ending on a separate row by wire name ("alpha run stopped", "alpha run failed")

**Status:** fixed (this commit) 2026-10-23. `buildDigest` now joins `run_failed` and `run_stopped` to their run (`runOf`), ends the turn on any of the three (`done`), and reads "was stopped" (warn) / "stopped with an error" (error). Test first `hub/ui/src/__tests__/activityDigest.test.ts` (2 of 3 failed). Drive: scratch Hub :8125 (profile f907, cleaned), real Haiku turns, one stopped through the stop route and one with claude.exe killed; Chromium `scripts/drive/f907_ui.py` -> "alpha was stopped" (warn), "alpha stopped with an error" (error), both under the Warnings filter, no wire-name rows.
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes -- driven with real Haiku turns; both endings reproduced.
**Tier:** 0

Agent `alpha` (`claude-haiku-4-5-20251001`), conversation `conv-532cea81cbfb`. `run-2ecf43ed6f9b` ran a 120 s sleep and was stopped through `POST /projects/{p}/agent/alpha/stop` (200, run `stopped`, event `run_stopped` exit 2). `run-5a0d005db3b8` ran the same sleep and its `claude.exe` was killed (run `failed`, event `run_failed` exit 1, severity warn). The trace list agrees (`run_status` stopped / failed, `invoke_agent` span status unset / error). The Activity tab -> **Activity** view, read in Chromium:

```
[info] 09:26 | alpha run failed     (severity warn)      <- run_failed alone
[info] 09:25 | alpha is working | Reply with the single word OK.   <- run-5a0d005db3b8: triggered, delivered, started
[info] 09:25 | alpha run stopped                         <- run_stopped alone
[info] 09:25 | alpha is working | Reply with the single word OK.   <- run-2ecf43ed6f9b
Warnings filter: ['alpha run failed']   (the failed turn's own row is info)
```

Both turns ended minutes earlier; neither "is working" row has a duration, tokens or cost, and no row says the turn was stopped or failed. Cause: `buildDigest` (`hub/ui/src/lib/activityDigest.ts`) joins only `run_triggered` / `run_started` / `run_completed` / `queue_entry_delivered` into a turn (`runOf`), and computes `done` and `failed` from `run_completed` alone; the Hub ends a turn with one of `run_completed` / `run_failed` / `run_stopped` (`_RUN_LIFECYCLE_EVENTS`, `hub/hub/api/v1/agent_trigger.py:2745`), so the other two fall to the `default:` branch as their own rows. There is no test file for `activityDigest.ts`.

**Expected:** `run_stopped` and `run_failed` join their run's row; the row reads "alpha was stopped" / "alpha stopped with an error" (severity warn/error, so Warnings shows it) with the duration from `run_started`; no separate wire-name row. **Test:** a new `hub/ui/src/__tests__/activityDigest.test.ts` fed the event order the Hub writes (`queue_entry_queued`, `run_triggered`, `queue_entry_delivered`, `run_started`, `context_warning`, `run_stopped`): one turn row, not "is working", no `run stopped` row; the same with `run_failed` (row severity error). Fails today. Seam: Runs x Logs, events & SSE.

## F909 (B) -- a conversation reads "waiting" on the rail and the Overview's agent card says "Waiting for your answer" for a question whose asking run has already ended, while Needs you, on the same screen, says nobody is waiting on it

**Status:** fixed 4060a64 (2026-10-23). `conversation_attention`'s question arm (`hub/hub/conversations.py`) now skips a question whose `created_by_run_id` names a run that is no longer `running`, the same rule as `asker_waiting`; an unrecorded asker stays presumed waiting. Test: `hub/tests/test_conversation_attention.py` (3 parametrised cases completed/failed/stopped failed before; two neighbouring tests used a completed asker incidentally and now use a live one). Drive: scratch Hub :8126 (profile f909, torn down), real Haiku turn asking with a 10 s timeout then ending: question `answered` false, `wait_ended_at` NULL, run `completed`, `asker_waiting` false, and both `/conversations` and `/agent/beta/conversations` read `attention` "idle" (UI reads this field; no bundle change). **Confirmed in Chromium 2026-10-23** (day `sweep-questions-sweep`, :8116, `scripts/drive/s1023_qa_ui.py f909`): a stopped asker and a 10 s timeout both leave no rail "waiting", Needs you reads "is asking" with "The turn that asked has ended", the agent cards read "Last active"; the live-blocked control still reads "waiting". Found 2026-10-22. Found by the day sweep `sweep-questions-sweep` (scratch Hub :8113, profile qs1022, `proj-7716d9f754a0`, Chromium against the served bundle, `scripts/drive/s1022_qs_drive.py timeout` then `scripts/drive/s1022_qs_ui.py needs`).
**Source:** drive
**Theme:** Questions
**Ready:** yes -- reproduced with one real Haiku turn.
**Tier:** 0

`beta` (`claude-haiku-4-5-20251001`, aw-tool call mode on its first run) asked "Ship the release on Friday?" (yes/no, a 10 s timeout); its shell call timed out and the turn ended ("NOANSWER"), `run-ff00f3895e36` `completed` at 08:38:56. The question `q-f499ff0210f2`: `answered` false, `wait_ended_at` NULL, `wait_expires_at` 08:42:39. Read at ~08:40-08:42:

```
GET /questions?answered=false   -> q-f499ff0210f2 asker_waiting: false
GET /conversations              -> conv-8f95d2b762cc (beta) attention: "waiting"
Overview, Needs you row         -> "The turn that asked has ended; nobody is waiting on this answer any more." / "beta is asking"
Overview, Agents card (beta)    -> "Waiting for your answer" (amber)
Rail                            -> beta  waiting
```

Two readers of one fact disagree: `_with_asker_state` (`hub/hub/api/v1/questions.py:457`) treats a question as inert once its asking run is not `running` **or** its wait is recorded as ended; `conversation_attention`'s question arm (`hub/hub/conversations.py:~455`) checks only `wait_ended_at IS NULL`, so it keeps "waiting" (which outranks running, by design) from the asking run's end until the wait's expiry is swept (`run_task_binding.py:1173`) -- here 3 min 43 s; an agent that asks with a long wait and then gives up keeps it that long. Whether it clears at expiry: by code yes, not measured.

**Expected:** the attention question arm excludes a question whose `created_by_run_id` names a run that is no longer `running`, exactly as `asker_waiting` does (one helper both use). **Test:** in the conversation-attention tests (`hub/tests/`, beside the `wait_ended_at` case): an unanswered question with `wait_ended_at` NULL whose asking run is `completed` leaves the conversation `idle`, not `waiting`. Fails today. Seam: Questions x Conversations (rail, Overview agent strip).

## F918 (B) -- the Vault's Add dialog and page drop store any file that is not a PDF or an image as a text "transcript": a Word document goes in as zip bytes, is committed under `knowledge/`, shown to every agent's map, and distilled for money

**Status:** fixed f99977b 2026-10-23 (night). `vault.add_source` refuses text holding a NUL (400, "This looks like a binary file..."), and `VaultScreen.add` refuses, per file, an extension outside the text list (`vaultFileRefusal` in `api/vault.ts`, mirroring `vault_intake.TEXT_EXTENSIONS`) with the path door's sentence, keeping the file in the dialog. Drive: scratch Hub :8128, Chromium (`scripts/drive/f918_ui.py`): minutes.docx + notes.txt chosen together -> dialog stays with "minutes.docx: A .docx file is not a vault source; the vault takes ...", notes.txt added, map holds no binary entry; curl POST /vault/sources with a NUL -> 400. Found 2026-10-22. Found by the day sweep `sweep-vault-sweep` in Chromium on the served bundle (scratch Hub :8115, `scripts/drive/s1022_vt_ui.py add`).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

```
Vault -> Add -> Files or folders -> browse docs/minutes.docx (a real zip) -> Add      -> dialog closes, toast "Added "minutes"", library "Transcripts 1"
GET  .../vault/map  -> {"id": "src-9ffa86eec5e7", "type": "transcript", "media_type": "text/plain", "opening": "PK\u0003\u0004\u0014\u0000..."}
GET  .../vault/entries/src-9ffa86eec5e7 -> 299 chars, 95 NUL, 14 U+FFFD
Manager activity: vault-distillation on "minutes" -> "Nothing to do", $0.02 (a paid Haiku call on zip bytes)
the same file by path:  POST .../vault/paths {"paths": [".../docs/minutes.docx"], "distil": false}
  -> refused: "A .docx file is not a vault source; the vault takes .md, .markdown, .txt, ... .pdf, .png, .jpg, .jpeg, .gif, .webp."
agentweave vault add docs/minutes.docx --no-distil   -> the same refusal
```

`VaultScreen.add` (`hub/ui/src/components/vault/VaultScreen.tsx:190-199`) sends a PDF or an image to `POST /vault/files` and **everything else** through `File.text()` to `POST /vault/sources`, and `vault.add_source` (`hub/hub/vault.py:966`) accepts any non-empty string, NULs included. The path door and the CLI hold the type list (`vault_intake.ACCEPTED`, `hub/hub/vault_intake.py:65`); the drop door, the one the dialog advertises ("Text, Markdown, PDF and images"), holds none. A tracked entry lands in the repository, so the garbage is committed with the project, and its opening is in every agent's turn context. **Expected:** (1) the dialog refuses a file whose extension the vault does not take, per file, with the path door's sentence (kept in the list with its reason, as a Hub refusal is kept today); (2) `POST /vault/sources` refuses text containing a NUL character (400, "this looks like a binary file; the vault takes ..."), so an API caller cannot do it either. **Tests:** `hub/tests/test_vault*.py`: `POST /vault/sources` with `"PK\u0003\u0004\u0000..."` -> 400, nothing written under `knowledge/`; a `VaultScreen`/`VaultAddDialog` test: adding a `minutes.docx` File calls neither upload hook and shows the refusal. Both fail today. Seam: Vault Add dialog x `POST /vault/sources` x the by-path door's type list.

## F919 (B) -- `agentweave reset --profile <p> --yes` says "Deleted <dir>" and "Hub data destroyed" while the profile's database is still there, held open by a Hub that is still serving it

**Status:** fixed 8641f27 2026-10-22 (night). `cmd_reset` now returns 1 and names what remains when `data_dir` survives the delete; test `test_reset_that_leaves_the_profile_behind_does_not_claim_it_destroyed_it` red before, green after. Drive: a throwaway profile `drv919` with `agentweave.db` held open -> exit 1, "Could not delete ...: still there: agentweave.db ... Stop it with 'agentweave --profile drv919 --port <port> stop'", db still on disk; after releasing the handle the same reset deleted the folder, exit 0. Originally: open 2026-10-22. Found by the day sweep `sweep-vault-sweep` (CLI & lifecycle row; throwaway profile `vt1022`, its Hub started from source by `e2e.py hub-up`, so with no PID file).
**Source:** drive
**Theme:** CLI & lifecycle
**Ready:** yes
**Tier:** 0

```
agentweave --profile vt1022 --port 8115 status   -> "Status: running (native)" + "[WARN] No PID file for profile 'vt1022' on port 8115: this Hub was started by hand ..."
agentweave reset --profile vt1022 --yes
  [INFO] Deleted C:\Users\huida\.agentweave\hub\profiles\vt1022
  [OK] Hub data destroyed. Run 'agentweave --profile vt1022 --port <port>' to start fresh.     exit 0
ls profiles/vt1022  -> agentweave.db (1,523,712 bytes) still there; instance_identity.json gone
GET :8115/api/v1/projects -> 401 (the Hub still serves, on a half-deleted profile)
after stopping the Hub: the same reset deletes the folder
```

`cmd_reset` (`src/agentweave/cli.py`, the block after "Stop the Hub first if running") stops only Hubs it finds through the profile's PID files, then calls `shutil.rmtree(data_dir, ignore_errors=True)` and prints `Deleted {data_dir}` and the success line unconditionally. On Windows a file another process holds open cannot be removed, so any Hub serving the profile without a PID file (started by hand, after a stale PID file was cleared, or by another tool), or any process holding the database open, leaves the data in place behind a success message -- and the command is the escape hatch for "when something is wedged", exactly when that happens. **Expected:** after the delete, if `data_dir` still exists, print an error naming what remains and the likely holder ("a process still holds agentweave.db open -- a Hub serving this profile? Stop it with `agentweave --profile vt1022 --port <port> stop`"), and exit 1; never print `Deleted` for a folder that is still there. **Test:** `tests/test_cli*.py`: `cmd_reset` with `shutil.rmtree` patched to leave the directory in place -> exit 1, output does not contain "Hub data destroyed" and names the file left. Fails today. Seam: CLI reset x a running Hub's open database.

## F925 (B) -- a job whose agent a session sync deleted (or the operator archived) can still be enabled and fired; the press answers 500 and records the firing `failed`, but leaves a queued entry and an open conversation that the next agent of that name receives and runs

**Status:** fixed 0f2771e 2026-10-23 (night) for plain jobs, re-driven 2026-10-23 day (`sweep-loops-sweep`, API + Jobs screen, held); a *loop* job on a gone or archived agent still answers 500 and writes no row: filed as F970. `scheduler.agent_unfirable_reason` is asked before a firing writes its run, entry and conversation (plain job) or enters a task (loop): a gone or archived agent records `failed` + `job_run_failed` and queues nothing; `PATCH enabled:true` runs job create's roster check (which no longer counts an archived agent the synced roster still lists); a press refused for this reason answers 409 with the sentence. Tests `hub/tests/test_a_job_for_a_vanished_agent_does_not_fire.py` (6, red before). Drive on scratch Hub :8122 (profile f925, torn down): enabled jobs for delta/gamma, sync removed delta, gamma archived -> press 409 each, one `failed` row each, no queue entry or conversation for either, re-enable 400. The optional design note (sync/archive answers naming the jobs left behind) is not done. Originally: open 2026-10-22. Found by the day sweep `sweep-agents-sweep` (scratch Hub :8116, profile ag1022, real Haiku, `scripts/drive/s1022_ag_api.py` and `s1022_ag_lib.py` calls).
**Source:** drive
**Theme:** Agents
**Ready:** yes
**Tier:** 0

```
POST /agents {"name": "delta", "runner_id": <haiku>}                                   -> 201
POST /jobs {"name": "delta job", "agent": "delta", "message": "Reply OK.", "cron": "0 4 * * *", "enabled": false} -> 201
POST /session/sync {"data": {"agents": {"alpha": {}, "beta": {}, "gamma": {}}}}        -> 200 removed ["delta"]  (nothing about the job)
POST /jobs {"name": "nobody job", "agent": "nobody", ...}                              -> 400 "agent 'nobody' is not one of this project's agents, so this job could only ever fail. On the roster: ..."
PATCH /jobs/job-75ec4f38de20 {"enabled": true}                                          -> 200   (the same job, naming a name no agent has)
POST /jobs/job-75ec4f38de20/run                                                         -> 500 "delta is not an agent in this project, so there is nothing to trigger. ..."
  job_runs: run-dc2a825d751f status failed, error_summary the same sentence
  event_logs: queue_entry_queued (entry-483406b43f74, agent delta, origin job) + job_fired (info); no job_run_failed
  inbound_queue_entries: entry-483406b43f74 state queued, conversation conv-f830dd1b4827
  conversations: conv-f830dd1b4827 agent delta, lifecycle open, title "delta job"
POST /agents {"name": "delta", "runner_id": <haiku>}                                   -> 201 (a new agent); the entry stays queued, the conversation is in its rail
POST /agent/trigger {"agent": "delta", "message": "Reply with the single word ZED..."}  -> 200 queued, waiting_reason "an older conversation's queued input is being delivered first (run run-058cab85b127)"
  run-058cab85b127 completed in conv-f830dd1b4827 -- the dead firing's "Reply OK." ran on the new agent; job_runs still says failed
```

The archive door does the same: `POST /agents/gamma/archive` -> 200 while job `gamma nightly` names gamma (the answer does not mention it); enable -> 200; run -> 500 "gamma is archived and cannot be triggered. Unarchive it first.", firing `failed`, and entry-506bbdc81e1b is left `queued` under the archived agent with an open conversation "gamma nightly" -- the state `archive_agent` refuses to create ("nothing delivers to an archived agent", F180). After unarchive the entry is still queued and goes ahead of the next input, as delta's did. The Activity digest reads both firings as "job fired · Runs as …". Before the firing, `GET /queue/delta/status` (no agent named delta) answered 200 with `waiting_reason` "Runner CLI 'delta' was not found in PATH." -- a reason about a CLI for a name with no agent.

Cause: `scheduler._fire_job_internal` queues the entry and opens the conversation before the trigger refuses an agent that is not on the roster (`agent_trigger._not_an_agent_to_trigger`, `agent_trigger.py:1052`) or archived, and that refusal is not one of the terminal ones that withdraw the entry; `jobs.py` `run_job` maps any `failed` row to 500 (`jobs.py:~1838`). Job create checks the roster; `PATCH /jobs/{id}` does not. Neither `sync_session` (`session_sync.py`) nor archive looks at jobs naming the agent. Same family as F596 (no runner) and F849 (a later agent of the name inherits). **Expected:** a firing whose agent is not an open agent of the project queues nothing and opens no conversation (or withdraws both in the same commit), records `failed` with its `job_run_failed` event, and the press answers 409 with the sentence, not 500; `PATCH /jobs/{id} {"enabled": true}` on a job naming such an agent is 400 with the create's sentence. Optional, design: the sync answer and archive answer name the jobs left naming the agent. **Test:** `hub/tests/test_jobs*.py`: a job naming an agent, the agent removed by sync (and, separately, archived), enable -> 400; run (forced) -> 409, no `InboundQueueEntry` and no open `Conversation` for that name afterwards; a later `POST /agents` of the name finds no queued entry. Fail today. Seam: Agents (sync/archive) x Jobs & loops x Inbound queue.

## F928 (B) -- a permission card is shown in whichever of the agent's conversations is open, not the one whose run asked: under a finished review's transcript it reads as the review asking to archive a job

**Status:** fixed e63686b 2026-10-23 (night). Drive: scratch Hub :8127 (profile f928), real Haiku turns, Chromium `scripts/drive/f928_ui.py`: with the panel on an earlier conversation only that conversation's own expired card showed and the bar said "waiting on your answer in <asking conversation>"; opening the asking conversation showed the live archive_job card, Allow -> request allowed, run completed. Superseded text: open 2026-10-22. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8117, profile lp1022, project `proj-042da656a1f4`, Chromium against the served bundle; `testbed/ui-judge/s1021-archive/110245/01_archive_card.png`).
**Source:** drive
**Theme:** Permissions
**Ready:** yes
**Tier:** 0

Repro (`AW_E2E_STATE=<lp1022 state> py -3.11 scripts/drive/s1021_rc_archive.py <project> alpha 1:allow`): alpha has a flow review conversation, "alpha · review: Add truncate()" (conv-ef40d3cfe577, finished: "Review complete. APPROVED ... The task has been approved and merged."), which is what clicking alpha in the rail opens. A fresh alpha turn in a *new* conversation ("Call the AgentWeave archive_job ...", run-cde848c060ef) calls `archive_job` -> `perm-a4beb84251b3` pending. The card "alpha wants to use archive_job · archive-me (0 4 * * *) · Allow / Deny" renders at the foot of the **review** conversation, directly under the review's verdict, above a composer reading "Continuing alpha · review: Add truncate()". The header's F844 note does say "busy in Call the AgentWeave archive_job ...", but the card itself is placed as this conversation's interjection. The operator is invited to judge a job archive as the review's next step. Allow did reach the right run (archived, run completed), so the decision works. Only its placement is wrong. F861's half holds: the card names the job and its schedule.

Cause: `openPermissionRequestsFor(requests, agent)` (`hub/ui/src/lib/pendingPermissions.ts`) filters by `agent` and status only. `PermissionRequestCard` (whose prop comment says "the card sits inside one conversation", `PermissionRequestCard.tsx:13-14`) and `AgentOutputPanel` (`:248`, `:266` the interjection tray, `:1203`) use it for every conversation of the agent. A request carries `run_id` but no conversation (`hub/ui/src/api/permissions.ts`). Questions were scoped to their own conversation by F804, with the busy-elsewhere note saying "waiting on you" (`AgentOutputPanel.tsx:416-421`). Permission requests were not. **Expected:** a card renders only in the conversation whose run asked (the Hub adds `conversation_id` from `Run.conversation_id`, or the panel maps `run_id` through the agent's runs). Any other conversation of the agent says, in the busy-elsewhere note, that the other conversation is waiting on the operator, with a link. **Test:** `hub/ui/src/__tests__/` AgentOutputPanel (or `pendingPermissions`): a pending request whose run belongs to conversation B, with the panel on conversation A of the same agent -> no `permission-requests` card in A. This fails today. Seam: Permissions (card) x Conversations x Runs.

## F933 (B) -- a project or agent default of "Ask me" or "Workspace only" reaches an agent with no tool server as `manual` with nobody to answer: every write is refused, no card, no Activity line, and the roster says "manual"

**Status:** fixed 89ce56a 2026-10-23 (night). `agent_trigger` resolves the run's access axes before it applies an inherited default, and an agent or project default that needs an approver (`runner_commands.posture_needs_approver`: `manual`, `workspace`) is skipped when the run has none (`axes.approvals == "none"`), so the runner's own at-rest posture (acceptEdits) applies; the roster's `permission_mode_built_in`/`_at_rest` (`agents.py`) applies the same rule. An operator's explicit per-run choice is untouched (the related composer question is left open). Test: `hub/tests/test_an_inherited_posture_that_needs_an_approver_is_not_given_to_a_run_with_none.py` (4 of 5 failed before). Drive: scratch Hub :8123 (profile f933, torn down), beta on a Haiku runner with `hub_client: cli`, project default Ask me: roster `acceptEdits`; a real turn (`run-225b7e4554c7`) wrote hello.txt with the Write tool, completed, 0 permission requests.
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

Repro: agent beta on a Claude Haiku runner with `PATCH /agents/beta {"config": {"hub_client": "cli"}}`, so it has no tool server and no approver. With nothing chosen, the roster says `permission_mode_at_rest: "acceptEdits"`. The runner's own rule (`claude_posture_at_rest`, `runner_commands.py:118`) falls back to acceptEdits when `approvals == "none"`. Then `PUT /projects/{p}/settings {"default_permission_mode": "manual"}` (Project settings -> General -> Reach -> Default permissions -> Ask me). Now `GET /agents` says beta's `permission_mode_at_rest: "manual"`. A turn with no posture of its own (`run-a84a5bdafbd0`): `Write hello.txt` inside its own worktree failed with "Claude requested permissions to write to ...\hello.txt, but you haven't granted it yet." `Set-Content` into its own `.agentweave/calls/1.json` was blocked ("Claude Code may only access files in the allowed working directories"), so `aw-tool` was unreachable too. Only `git status` ran. `permission_requests` for the run: 0 (no card). `permission_denied` events: 0 (no Activity line). The run ended `completed`. The same agent with the default cleared (`run-617f5746460c`, acceptEdits) wrote hello.txt and the call file. Cause: `agent_trigger.py:1198-1208` fills the permission control from the agent's or the project's default without asking whether the run has an approver. `_build_claude_command` (`runner_commands.py:289-305`) then sees an operator-set mode, names no prompt tool (`mcp_args` is empty), and passes `--permission-mode manual`. The roster's `permission_mode_built_in = project_posture or ...` (`agents.py:502`) reports the inherited default the same way. Who reaches it: `hub_client: "cli"` is F299's documented one-line workaround for a machine whose policy blocks MCP (the operator's work PC). On that machine, picking the new reach-1019 project default silently disables every agent so configured. **Expected:** an *inherited* default (agent or project) that needs an approver, on a run with none, falls back to the runner's own at-rest posture (acceptEdits), and the roster says what the run will get. Whether an operator's explicit per-run "Ask me" on such an agent should be refused with a sentence, or not offered, is a related question; the composer offers it today. **Test:** `hub/tests/test_agent_trigger*`: a `hub_client: "cli"` Claude agent with project `default_permission_mode: "manual"` -> the built argv carries `--permission-mode acceptEdits`, and `GET /agents` reads `permission_mode_at_rest: "acceptEdits"`. This fails today. Seam: Permissions & sandbox (reach default) x Agent environment (call mode).

## F944 (B) -- an agent's `read_spec_document include=full` never returns `delivery`, so a read, edit and resubmit silently erases the document's flow, agent, reviewer and schedule

**Status:** fixed 24aa973 (2026-10-23). Drive: scratch Hub :8124, two real Haiku 4.5 turns -- turn 1 submitted a `delivery` and its `read_spec_document include=full` returned it (cron `*/7 * * * *`); turn 2 read full, changed a statement, resubmitted every returned field, and the file's `delivery` and `checked_by` survived. Found 2026-10-22. Found by the day sweep `sweep-spec-sweep` (scratch Hub :8121, two real Haiku 4.5 turns).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro, two real turns by `builder` (claude-haiku-4-5). Turn 1 called `submit_spec_document` on `spec/changes/hdr-new2/spec.json` with `delivery {"mode": "flow", "agent": "builder", "reviewer": "builder", "stop_when_queue_empties": true, "cron": "*/7 * * * *"}` and one criterion with `checked_by: "agent"`. The file on disk then held the whole `delivery`. The same turn's `read_spec_document include=full` came back with no `delivery` key, and Haiku said so in its report ("the `delivery` field is absent from the read result"). Turn 2 was told to read `full`, fix one requirement statement, and submit back every field the read returned. Afterwards the file's `delivery` was `None`, the statement was changed, and `checked_by` survived. Seam: `hub/hub/api/v1/agent_actions.py:1784` `_READ_SECTIONS = ("design", "tasks", "algorithms", "evidence", "lifecycle")`. The `full` branch (`:1963`) adds only those. `spec_reading.OPTIONAL_SECTIONS` (`spec_reading.py:226`) also lists `slices` and `roadmap`, which the agent read leaves out too. `delivery` is in neither list, and the tool's `include` Literal (`mcp_server.py:5224`) offers no `delivery` section, so an agent has no way to read it. `submit_spec_document` replaces the payload, so the operator's flow decision is lost without a warning. The agent's docstring promises `full` "adds the design, declared tasks, algorithms and evidence sections", and the read gives no hint that anything is held back. **Expected:** `full` returns `delivery`, `slices` and `roadmap` (`_READ_SECTIONS` follows `OPTIONAL_SECTIONS` plus `delivery`), and `include` accepts `delivery`. **Test:** `hub/tests/` agent-plane read: a document whose payload has `delivery`, read with `include=full`, answers `delivery` equal to the stored one. This fails today. A second test: read `full`, submit the returned fields back, and `delivery` is unchanged. Seam: Spec documents (agent read x submit round trip).

## F945 (B) -- the Spec header's requirements fact counts every requirement not verified or rejected as "in progress", including ones not started and ones with no task

**Status:** fixed cb80cae 2026-10-23 (night iteration 10). Test `specHealthLine.test.tsx` (names each state; failed before). Drive: scratch Hub :8129, Chromium `scripts/drive/f945_ui.py`: approved change with untouched requirements reads "0/2 verified · 2 not started", proposed change with no task reads "0/2 verified · 2 with no task". Was: open 2026-10-22. Found by the day sweep `sweep-spec-sweep` (Chromium, scratch Hub :8121; `scripts/drive/s1022_sp_ui.py header`).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro: approved change `hdr-main`, where FR-1 is verified (accepted evidence, landed) and FR-2's task is `pending` and never worked. The header fact reads "1/2 verified · 1 in progress", and its own popover lists FR-2 as "Not started". On proposed `hdr-proposed`, the only requirement is `unserved` (popover "No task") and the fact reads "0/1 verified · 1 in progress". `SpecHealthLine.tsx:69`: `const working = coverage.length - verified - rejected` lumps `not_started`, `unserved`, `stale`, `drifting`, `evidence_awaiting_review` and `amendment_unreviewed` together as "in progress". So the one-line summary tells the operator someone is working a requirement nobody has touched, and a drifting or stale one does not warn there. The old `SpecCoverageBar` named each state. **Expected:** the summary names the states it has, for example "1/2 verified · 1 not started", or "0/1 verified · 1 with no task". `drifting`/`stale` take the warn tone. **Test:** `SpecHealthLine.test.tsx`: coverage `[verified, not_started]` renders no "in progress" and does render "not started". This fails today. Seam: Spec documents (header) x Requirements, evidence & coverage.

## F946 (B) -- the Spec header says "Vault agrees" on a project whose spec-vault check is off and has never run, and pressing "Check against the vault again" answers only "The spec vault check job is disabled."

**Status:** fixed ca0e398 2026-10-23 (Tier 0). `GET /vault/warnings` now carries `checked` (whether the job ever fired on the document); the header reads "Vault not checked" with no tone when there are no warnings and no firing, and its action reads "Check against the vault"; the 409 sentences name Project settings → Manager. Drive: scratch Hub :8131, Chromium `scripts/drive/f946_ui.py`: "Vault not checked", press -> toast "The spec vault check job is disabled. Turn it on under Project settings → Manager." Found 2026-10-22. Found by the day sweep `sweep-spec-sweep` (Chromium, scratch Hub :8121; `scripts/drive/s1022_sp_ui.py fact <path> spec-health-vault "Check against"`).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

Repro: a fresh project (`GET /manager/jobs`: all four jobs `enabled: false`, vault empty). Every document's header shows a quiet "Vault agrees" fact. Its popover says "No requirement contradicts what the vault knows." and offers "Check against the vault again". Pressing that gives the toast "Could not start the check — The spec vault check job is disabled." (`POST /vault/warnings/check` 409). The toast names no way out (Project settings → Manager → spec-vault-check, with a runner). The fact is built from `GET /vault/warnings` (`hub/hub/api/v1/vault.py:494`), which answers `[]` when no check ever ran. `SpecDocumentPanel.tsx:233` maps `[]` to "agrees". The component's own comment says the fact is "left out rather than shown as fine" when the Hub cannot answer. A check that cannot run is that case. So the operator reads a vault verdict that no check ever produced, on every document, and "again" implies one ran. **Expected:** `GET /vault/warnings` says whether a check has run and whether the job is on (for example `checked_at`, `job_enabled`). The fact reads "Vault not checked", or is left out, when no firing exists, and the 409's sentence names Project settings → Manager. **Test:** a panel test: warnings `[]` with no check recorded renders no "Vault agrees". A Hub test: the 409 detail names the Manager page. Both fail today. Seam: Spec documents (header) x Manager jobs x Knowledge vault.

## F952 (B) -- the Overview's spend line drops everything the budget card used to say: a turn with no reported cost counts as $0.00 with no caveat, "API-equivalent" is gone, and the project's preferred unit (allowance, Copilot credits) is never shown

**Status:** fixed 26ecda6 2026-10-23 (Tier 0). The spend line takes its figure from `/accounting` when loaded: "$0.07 API-equivalent so far", a "N turn(s) unpriced" note, the project's AI credits (the figure itself when nothing was priced, else a dash), and the allowance label when the preferred display is one; the agent strip reads "—" for an agent with no priced turn. Drive: scratch Hub :8132, two seeded `turn_usage` rows (scratch profile `f952`; alpha priced, cop credits only), Chromium `scripts/drive/f952_ui.py`: "$0.07 API-equivalent so far · 265.8K tokens · 0.28 AI credits · 1 turn unpriced"; alpha $0.07, cop —. Not driven: the allowance note in the browser (unit test only). Found 2026-10-22. Found by the day sweep `sweep-checkpoints-sweep` (Chromium against the served bundle, scratch Hub :8122, profile ck1022, project `proj-d2fc106b8594`; `scripts/drive/s1022_ck_ui.py overview`, screenshots `testbed/ui-judge/s1022-ck-overview/`).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 0

Repro: agent `cop` on a Copilot provider runner aimed at the zero-spend stub (`scripts/drive/s1018_A_copilot_stub.py`), one turn: `turn_usage` row `measured`, 30 tokens, `api_equivalent_usd_micros` NULL. Then alpha (Haiku 4.5) one turn, 265,791 tokens, $0.0725. `GET /accounting` reads `project.unpriced_turns: 1` and `preferred_display.kind: "allowance"` (a Claude subscription: "Rate-limit allowance"). Project settings -> Budgets says it: "Spent $0.07 — API-equivalent; 1 turns could not be priced" and "Rate-limit allowance available · resets …". The Overview's spend line says "**$0.07 so far · 265.8K tokens**", and its agent strip says "cop **$0.00**". With only the stub turn, `GET /ledger` read `total_usd: 0.0` for 30 tokens, so the line read "$0.00 so far" by construction.

Seam: `OverviewScreen.tsx:177` feeds the line `ledger.spend.total_usd` alone. `project_ledger.py:128-170` counts a NULL cost as 0 and carries no unpriced count, no credits and no allowance. So the line cannot say what `accountingDisplayLabel(preferred_display)` (`accountingDisplay.ts:73`) says on Budgets. The budget summary card that showed it (F665's credits unit, F722's worker row, "excludes N turns with no reported cost") was removed by ui-finesse (a8ca6e2). The same goes for a Copilot-only project spending credits: the ledger has no credits field, so the line reads "$0.00 so far". That case is read from the code, not driven: the stub reports no credits. **Expected:** the line uses `/accounting`'s `preferred_display` (or the ledger grows the same fields). A partly priced figure says so ("$0.07 API-equivalent · 1 turn unpriced"). An agent with no priced turn reads "—" (as Budgets does), not "$0.00". **Test:** `OverviewScreen` with an accounting payload of `unpriced_turns: 1` renders the caveat, and with `preferred_display.kind: "credits"` renders the credits; `OverviewView`'s agent row renders "—" for a null cost.

## F953 (B) -- with the token budget spent, the Overview says only "Autonomous turns are paused; operator messages can still run.": no limit, no way to raise it, and a held turn leaves "Nothing needs you · Nothing running"

**Status:** fixed 9509788 (Tier 0, 2026-10-23). Drive: scratch Hub :8133, `scripts/drive/f953_seed.py` + `f953_ui.py` (Chromium): budget 100K, 298.2K used, a job fired with Run now left one turn queued `token budget exhausted`; the Overview band read "Token limit reached: 298.2K of 100K tokens. ... 1 turn waiting. Change it in Budgets", the summary "1 turn held by the budget · Nothing running", the link opened Project settings -> Budgets, one border, no console errors. Not done: the Needs-you section itself still reads "No questions, approvals or failed merges are waiting" beside a held turn (the summary line and band carry it). Found by the day sweep `sweep-checkpoints-sweep` (Chromium, :8122; `s1022_ck_ui.py overview -spent|-held`, screenshots `overview-spent.png`, `overview-held.png`).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 0

Repro: `PATCH /accounting/budget {"token_budget": 100000}` with 265,821 used (`exhausted: true`). Then fire job `ping-beta` (Run now), which leaves beta's entry `queued` with `waiting_reason: "token budget exhausted"`. The Overview shows an amber band, "Autonomous turns are paused; operator messages can still run.", with no control in it (`NOTICE controls: []`). Below it: "**Nothing needs you · Nothing running** · 0 tasks", and beta "Last active never". The word "budget" appears nowhere on the page. The operator cannot tell from the Overview why turns are paused, how far over the limit they are (265.8K of 100K), where to change it (Project settings -> Budgets), or that a turn is waiting on them.

Seam: `BudgetExhaustionNotice.tsx` takes only `exhausted`. `OverviewScreen.tsx:183-190` renders it bare, and the Needs-you list has no kind for budget-held work. The band also nests a bordered box inside the tinted `aw-overview-notice` wrapper (a double border). **Expected:** the notice names the limit and the use ("Token limit reached: 265.8K of 100K"), counts what it holds ("1 turn waiting"), and links to Budgets. Held entries make "Nothing needs you" false: they belong in Needs you, or the summary line says "1 held by the budget". **Test:** `OverviewScreen` with `budget.exhausted` and a queue entry `waiting_reason: "token budget exhausted"` renders the figures, a link to `section=budgets`, and does not render "Nothing needs you".

## F1016 (B) -- an operator's "nothing merges" (Main branch cleared) is silently undone the next time the folder is opened: the Hub re-adopts `master`, records no settings change, and drains the approved work that was waiting

**Status:** fixed 2026-10-27 (slice A: a cleared main branch survives reopen and the Hub's own adoption is a settings event; test_project_main_branch_reopen); opened 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Projects row; scratch Hub :8116, profile pj1023, proj-19b3a5f0a902, inline probe after `scripts/drive/s1023_pj_api.py branch`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

Settings -> Integration -> Main branch says "Approving a task merges its work here. Empty: nothing merges." Emptying the field sends `main_branch: null` (`hub/ui/src/components/settings/GeneralSettings.tsx:230`, `v || null`) and toasts "Approved work no longer merges". Through the API, on a git project whose branch is `master`:

```
PUT  /projects/proj-19b3a5f0a902/settings {"main_branch": null}   -> 200, main_branch null
GET  /projects/proj-19b3a5f0a902/settings                         -> main_branch null
POST /projects/open {"path": "C:\\Users\\huida\\Documents\\aw-pj1023-a"} -> 200   (re-adding the folder; the CLI's start does the same open)
GET  /projects/proj-19b3a5f0a902/settings                         -> main_branch 'master'
GET  /projects/proj-19b3a5f0a902/events/history                   -> the clear ("was 'master', now None") is recorded; the change back to 'master' is not
```

Cause (verified by reading): `open_project` always calls `_adopt_detected_main_branch` (`hub/hub/api/v1/projects.py:374`), which writes the detected branch into any falsy `main_branch` (`:408`, `:425`) and then runs `_integrate_what_was_waiting_for_a_branch` (`:427`). Its docstring says a project "that has chosen a branch has made a statement" -- but `null` is both "never chosen" and the operator's explicit "nothing merges", so the statement is overwritten. Not driven: the drain itself (no approved-and-skipped task existed); by `:427` each approved task that skipped "for want of a main branch" while merging was off would then merge into `master` with nobody asking.

**Expected:** an explicit "nothing merges" survives a reopen -- either the empty choice is stored distinctly from "never chosen" (e.g. `""` or a flag, which `_adopt_detected_main_branch` leaves alone), or the adoption runs only on first registration; any change the Hub makes to settings on its own is recorded as a settings event. **Test:** `hub/tests/test_project_*` beside the F4 adoption test: open a repository project, `PUT main_branch null`, `POST /projects/open` again -> `main_branch` is still null (fails today). Seam: Projects (open) x Integration (merge target).

## F1023 (C) -- rebinding an agent to a runner of another CLI resumes the conversation's old provider session on the new CLI: Copilot starts over with a notice, Claude fails the turn twice ("No conversation found with session ID") before the queue drops the session and silently starts a fresh one

**Status:** fixed 2026-10-27 (slice J, rebinding-an-agents-runner-starts-clean: a session is resumed only by the CLI that created it (migration 0148); test_rebinding_an_agents_runner_starts_clean); opened 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Runners & models row; scratch Hub :8117, profile rm1023, proj-8717fc708877, `scripts/drive/s1023_rm_rebind.py`, Chromium `scripts/drive/s1023_rm_ui2.py`, shot `testbed/ui-judge/s1023-rm/140238/13_conversation_after_cli_rebind.png`).
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 1

Agent `a-run` on Claude runner `ch` (model `haiku`) had two Claude turns in `conv-f45e1b5b2180` (Claude session `62f1c78b-...`). Then the agent was rebound with the Execution screen's own door and given one more turn in that conversation, then rebound back:

```
PATCH /projects/{p}/agents/a-run {"runner_id": <copilot runner, model auto>}  -> 200
POST  /projects/{p}/agent/trigger {"agent":"a-run","message":"Reply with exactly the single word OK.","conversation_id":"conv-f45e1b5b2180"}
  run-ac31c018701e (copilot) completed; on screen: "Copilot had no saved session 62f1c78b-519b-4c54-93a3-79caab462564; a new one was started."
  conversations.provider_session_id -> b36d6aef-... (Copilot's)
PATCH /projects/{p}/agents/a-run {"runner_id": <ch, claude>}  -> 200
POST  /projects/{p}/agent/trigger (same conversation, one message)
  run-48eb218457b6 failed exit 1: "No conversation found with session ID: b36d6aef-4b63-4d07-8e6c-ab63539cc2c7" (printed twice), "Turn failed"
  run-e6eee0b7e373 failed exit 1: the same, twice, "Turn failed"            (queue_entry_queued -> redelivered, initiator "operator")
  run-d079343e0501 completed, session_mode "new", session 822b2667-...        (no notice that the context was dropped)
```

The operator sent one message and sees two failed turns with four copies of a Claude error naming an id Claude never issued, then an answer from a session that has lost the whole conversation, with nothing saying so. Copilot's leg recovers only because Copilot alone has the "no saved session" rescue (`copilot_acp.py:2700-2716`, `agent_trigger.py:4385-4398`).

Cause (verified): the agent PATCH changes `runner_id` and leaves every conversation's `provider_session_id` alone (`hub/hub/api/v1/agents.py:3158-3165`); the launch resumes `conversation.provider_session_id` whatever CLI wrote it (`hub/hub/api/v1/agent_trigger.py:1280-1281`); for Claude only the queue's generic give-up clears it, after `RESUME_RETRY_LIMIT = 2` failed deliveries (`hub/hub/inbound_queue.py:365`, `:463`).

**Expected:** a provider session is resumed only by the CLI that created it. A turn whose conversation's session belongs to another CLI starts a new session at once and says so in the conversation ("a-run now runs on Copilot; this conversation's earlier turns were on Claude and are not carried into its session"), rather than failing twice. Recording the session's CLI beside `provider_session_id` (or clearing it when the agent is rebound to another CLI) are both candidate shapes; the notice is the point. **Test:** beside `hub/tests/test_runner_binding_redrain.py`: a conversation with a Claude `provider_session_id`, the agent rebound to a Copilot (or Codex) runner and back; the next launch's command carries no `--resume <foreign id>` and the conversation gets the notice. Fails today. Seam: Runners & models (rebind) x Runs (session resume) x Inbound queue (retry).

## F1024 (C) -- a conversation's per-run model survives the agent's rebind to another CLI and is handed to it as is: Copilot was launched with `--model haiku`, ran `claude-sonnet-5` on a premium request, and the Hub recorded the run as model `haiku`

**Status:** fixed 2026-10-27 (slice J: a foreign stored model is withheld and the recorded model is what ran; same test file); opened 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Runners & models row; scratch Hub :8117, profile rm1023, proj-8717fc708877, `scripts/drive/s1023_rm_turn.py` then `scripts/drive/s1023_rm_rebind.py`).
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 0

```
POST /projects/{p}/agent/trigger {"agent":"a-run", ..., "conversation_id":"conv-f45e1b5b2180", "overrides":{"model":"haiku"}}   (a-run on Claude runner ch)
  conversations.runtime_overrides = {"model": "haiku"}   -- stored as written, correct for Claude
PATCH /projects/{p}/agents/a-run {"runner_id": <copilot runner, model "auto">}  -> 200, no word about the conversation's model
POST /projects/{p}/agent/trigger {"agent":"a-run","message":"Reply with exactly the single word OK.","conversation_id":"conv-f45e1b5b2180"}  (no overrides)
  event run_started: {"runner": "copilot", "model": "haiku"}
  conversation: "Copilot ran claude-sonnet-5 instead of the requested haiku; this plan allows: [claude-sonnet-5, ..., claude-haiku-4.5, ...]"
  turn_usage: runner copilot, model claude-sonnet-5, premium_requests 1.0
```

`haiku` is a Claude alias the `copilot` catalog does not declare (`POST /runners {"cli":"copilot","model":"sonnet"}` is 400 naming Copilot's ids). The operator chose the cheapest model; the turn ran on the plan's default instead, and the Hub's own record says `haiku`. The same stored value is what `inherit_runtime_overrides` copies into a job's or a peer message's new conversation (`hub/hub/conversations.py:66-110`; the job door was driven and inherits `{"model": "haiku"}` as written, `s1023_rm_jobdoor2.py`).

Cause (verified): "Overrides were already validated against the catalog when the operator set them ... so they are trusted here rather than re-validated per turn" (`hub/hub/api/v1/agent_trigger.py:1189-1200`): for a runner without a provider, `model = conversation_overrides.get("model") or config.get("model")`. They were validated against the CLI bound *then*. The provider branch just above already declines a stored model that no longer fits (`:1194-1198`, design D7); a plain CLI change has no such branch, and the rebind (`hub/hub/api/v1/agents.py:3158-3165`) does not look at conversations.

**Expected:** at launch, a stored per-run model the bound runner's CLI does not declare is not applied (kept, as D7 keeps it, so rebinding back restores it); the turn runs on the runner's model and the conversation says so once ("this conversation's model haiku is not one Copilot offers; running on the runner's model"). The composer's model pill reads what will run. **Test:** in `hub/tests/test_agent_trigger_overrides.py`: a conversation with `runtime_overrides {"model": "haiku"}`, the agent rebound to a Copilot runner, trigger -> the spawned command carries no `--model haiku`. Fails today. Seam: Runners & models (rebind) x Conversations (per-run model) x Jobs (inherited overrides).

## F1027 (C) -- one Escape on the Add-agent dialog's open Provider list closes the whole dialog and throws away the typed name; the list takes no arrow keys

**Status:** fixed in code 2026-10-27 (Tier 0, built with slice I): the Provider list is the `MenuSelect` the Vault dialogs use (arrows and Enter pick; Escape closes only the list and focus stays on Provider). Test: `the Provider list is one layer (F1027)` in `agentCreateDialogFocusRestore.test.tsx`. The browser re-drive (`scripts/drive/s1023_kb_*.py`) is still to be run against the rebuilt bundle. Found 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Keyboard & dialogs row; scratch Hub :8118, profile kb1023, proj-f7897cfb459c, Chromium against the served bundle, `scripts/drive/s1023_kb_layers.py popover`, shot `testbed/ui-judge/s1023-kb/layers_add_agent_provider_open.png`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Repro, keyboard only, with `document.activeElement` read after each key: focus the rail's **Add agent to aw-kb1023** and press Enter. The Create agent dialog opens with focus in the name field (held). Type `kbtwo`, Tab to **Provider** ("Select a provider"), and press Enter. The listbox opens (`[role=listbox]` count 1). Focus stays on the Provider button. ArrowDown twice: nothing moves, and focus is still on the button. Tab reaches the options ("Claude Code", then "Codex CLI"). Now press Escape once, with focus on the button or on an option. **Both** the listbox and the dialog close (`dialogs` = `[]`), focus returns to Add agent, and the typed name is gone.

Cause (verified): `ProviderPicker` (`hub/ui/src/components/agents/AgentCreateDialog.tsx:26-115`) is a hand-built `role="listbox"` with only a click toggle and an outside-mousedown close. It has no key handling, so it never claims Escape. The dialog's `useDialogFocus` Escape branch (`hub/ui/src/hooks/useDialogFocus.ts:41-58`) stands down only when `event.defaultPrevented` (line 53), so it closes the dialog. This is the arbitration F310 introduced. The listbox also has no ArrowUp/ArrowDown/Enter handling.

**Expected:** with the list open, Escape closes only the list (`preventDefault()`, as `DirectoryPicker` does) and focus returns to Provider. A second Escape closes the dialog. Arrow keys move between options, and Enter picks one. Alternatively, use the Radix `Select` the Vault dialogs already use. Those Kind/Storage selects inside their Radix dialogs held: one Escape closed one layer.

**Test:** `hub/ui/src/__tests__/agentCreateDialogFocusRestore.test.tsx` (or a sibling): open the dialog, open Provider, fire Escape; the dialog is still open and the listbox is gone. It fails today. Seam: Keyboard & dialogs x Agents (create).

## F1028 (C) -- Ctrl+K over an open dialog or the task drawer: the palette opens on top, but the first Tab moves focus into the dialog behind it, and typing goes into a field the operator cannot see

**Status:** fixed in code 2026-10-27 (Tier 0, built with slice I): `useDialogFocus` stands down on Tab when focus is inside a dialog that does not contain its panel, and `useModalLayer` lets the command palette take a place in the layer stack. Tests: `useDialogFocus.test.tsx` (`F1028`). The browser re-drive (`scripts/drive/s1023_kb_*.py`) is still to be run against the rebuilt bundle. Found 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Keyboard & dialogs row; scratch Hub :8118, profile kb1023, proj-f7897cfb459c, Chromium against the served bundle, `scripts/drive/s1023_kb_palette_over.py`, shots `testbed/ui-judge/s1023-kb/palette_over_add_agent.png`, `palette_over_task_drawer.png`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Repro 1: focus **Add agent**, press Enter, and the Create agent dialog has focus. Press Ctrl+K. The palette opens over the dialog with focus in its input (`dialogs` = `['Create agent', 'Command palette']`). Press Tab once. Focus is now the Create agent **name field** (placeholder `codex-reviewer`), and the palette is still drawn on top of it (shot). Type `zz`, and it lands in that hidden name field. The `input` whose value holds `zz` is the agent name, not the palette. One Escape then closes the palette (held), and the dialog shows `zz` in its name.

Repro 2: the same with the task drawer open (Enter on a board card). After Ctrl+K, Tab puts focus on the drawer's Close button behind the palette.

Cause (verified): `CommandPalette` (`hub/ui/src/components/palette/CommandPalette.tsx:74-87`) opens whatever is open beneath it. It is a cmdk/Radix dialog and is not in `useDialogFocus`'s `openDialogs` stack. The older dialog therefore still believes it is the newest. Its Tab branch sees focus "outside" its panel (`useDialogFocus.ts:73`) and pulls it to its own first control. This is F307's fix firing against a layer it does not know about.

**Expected:** either the palette does not open while a modal is open, or `useDialogFocus` stands down when focus is inside another modal layer, so Tab stays in the palette. Registering the palette in the same stack would also work.

**Test:** `hub/ui/src/__tests__/useDialogFocus.test.tsx`: mount a `useDialogFocus` panel and a second `role="dialog"` with focus in it. Fire Tab: focus stays in the second dialog. It fails today. Seam: Keyboard & dialogs (palette x every `useDialogFocus` dialog).

## F1029 (C) -- the Vault's Add and Vault storage dialogs drop keyboard focus to `<body>` on every close: Escape, Cancel and the X alike

**Status:** fixed in code 2026-10-27 (Tier 0, built with slice I): the shared `DialogContent` reads what had focus when it opened and restores it on close (Radix had no Trigger to restore to). Test: `returns focus to %s after closing its dialog` in `vaultTab.test.tsx`. The browser re-drive (`scripts/drive/s1023_kb_*.py`) is still to be run against the rebuilt bundle. Found 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Keyboard & dialogs row; scratch Hub :8118, profile kb1023, proj-f7897cfb459c, Chromium against the served bundle, `scripts/drive/s1023_kb_dialogs.py vault`, shots `testbed/ui-judge/s1023-kb/dlg_vault-add_open.png`, `dlg_vault-storage_open.png`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Repro, on a project with one vault entry: focus **Add** (`vault-upload-open`) and press Enter. The dialog "Add to the vault" opens with focus on the header's **Close** (X). Press Escape, and focus is `BODY`. Reopen, Tab to **Cancel**, and press Enter: focus is `BODY`. Do the same with **Vault storage** (the toolbar's icon button) and the result is the same, `BODY` both ways. A keyboard user's next Tab starts again from the rail. Tab was trapped in both dialogs (held), and the Kind/Storage selects inside them close one layer at a time (held).

Cause (verified): both are controlled Radix dialogs with no `DialogTrigger`: `VaultAddDialog.tsx:131` and `VaultStorageDialog.tsx:39`, opened from buttons at `VaultLibrary.tsx:221` and `:312`. On close, Radix's modal content prevents its default focus restore and focuses `context.triggerRef.current` (`hub/ui/node_modules/@radix-ui/react-dialog/dist/index.mjs:146-148`). With no Trigger that ref is null, so nothing is focused. The shared `DialogContent` (`hub/ui/src/components/ui/dialog.tsx:14-45`) offers no way to say where focus goes back to. `JobsView.tsx:376` has the same shape: it is F931's "after Archive focus drops to the page" half. The Radix dialogs that do use a `DialogTrigger` held: the agent's Archive confirm and Add check both returned focus to their opener.

**Expected:** focus returns to **Add** / **Vault storage** after any close. Either wrap each opener in `DialogTrigger`, or give `DialogContent` a `returnFocusTo` ref used in `onCloseAutoFocus`.

**Test:** `hub/ui/src/__tests__/vaultTab.test.tsx`: open Add with the keyboard, press Escape, and `document.activeElement` is the Add button. It fails today. Seam: Keyboard & dialogs x Knowledge vault.

## F1030 (C) -- in the task drawer, Escape on the inline "Delete this task?" confirm closes the whole drawer, not just the confirm

**Status:** fixed in code 2026-10-27 (Tier 0, built with slice I): the delete confirm claims Escape with `preventDefault`, cancels itself and returns focus to Delete; the second Escape closes the drawer. Test: `one Escape closes one layer of the drawer (F1030)` in `taskDetailDrawer.test.tsx`. The browser re-drive (`scripts/drive/s1023_kb_*.py`) is still to be run against the rebuilt bundle. Found 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Keyboard & dialogs row; scratch Hub :8118, profile kb1023, proj-f7897cfb459c, Chromium against the served bundle at 1440 and 760 px, `scripts/drive/s1023_kb_tasks.py`, shot `testbed/ui-judge/s1023-kb/task_delete_confirm_1440.png`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Repro: on the board, focus a card (`task-open-<id>`) and press Enter. The drawer opens with focus on Close. Tab to **Details** and press Enter. Tab to **Delete** (`task-delete-<id>`) and press Enter. The inline confirm appears and focus lands on its **Cancel** (held). Press Escape once. The confirm **and** the drawer both go (`dialogs` = `[]`), and focus is back on the board card. The operator who meant "no, don't delete" has lost the ticket as well. The result is the same at 760 px.

Cause (verified): the confirm (`hub/ui/src/components/tasks/TaskDetailDrawer.tsx:703-745`) has no Escape handling. The drawer's `useDialogFocus(open, panelRef, onClose)` (`:375`) therefore takes the key and closes the drawer. The blocking-reason panel in the same drawer claims Escape with `preventDefault()` (`:775-781`, F310's fix), and the delete confirm was left out. The comment at `:701-702` chose an inline confirm precisely so that "a nested dialog would [not] take both with it".

**Expected:** Escape on the confirm cancels it (like its Cancel button) and focus returns to **Delete**. A second Escape closes the drawer.

**Test:** `hub/ui/src/__tests__/taskDetailDrawer.test.tsx`: open the confirm, fire Escape, and the drawer is still mounted with the confirm gone. It fails today. Seam: Keyboard & dialogs x Tasks (delete).

## F1031 (C) -- a task can be renamed only with a mouse: the drawer's title is a click-only heading, and after Enter or Escape in the title field focus falls to `<body>`

**Status:** fixed in code 2026-10-27 (Tier 0, built with slice I): the drawer title is a heading holding a `Rename` button (a Tab stop, Enter opens the input), and focus returns to it after save or Escape. Tests: `renaming a task from the keyboard (F1031)` in `taskDetailDrawer.test.tsx`. The browser re-drive (`scripts/drive/s1023_kb_*.py`) is still to be run against the rebuilt bundle. Found 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Keyboard & dialogs row; scratch Hub :8118, profile kb1023, proj-f7897cfb459c, Chromium against the served bundle, `scripts/drive/s1023_kb_tasks.py`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Repro: open a task's drawer with Enter and Tab through it (30 presses, cycling). The title `task-drawer-title-<id>` is never a stop: it is an `H2` with `tabIndex -1` and no role. Enter on any reachable control does not open the rename. Clicking the title opens the input (`task-drawer-title-input-<id>`). Typing and Enter save once (exactly one `PATCH /tasks/<id>`, held), but focus is then `BODY`. Clicking again, typing and pressing Escape cancels and keeps the drawer open (held: one layer), but focus is again `BODY`. The checklist's Tasks row says "rename in the drawer (Enter saves, Esc cancels)". A keyboard user cannot reach the rename at all.

Cause (verified): `TaskDetailDrawer.tsx:491-502` is `<h2 ... title="Click to rename" onClick=...>` with no `tabIndex`, `role` or key handler. When the input unmounts, nothing receives focus, because the heading cannot take it. A scan of `hub/ui/src/components` for `onClick` on a non-interactive element without `role`/`tabIndex`/`onKeyDown` finds only this one, apart from scrim backdrops.

**Expected:** the title is a button (or `role="button" tabIndex={0}` with Enter/F2) labelled "Rename", and after save or cancel focus returns to it.

**Test:** `hub/ui/src/__tests__/taskDetailDrawer.test.tsx`: the title is reachable with `userEvent.tab()`, Enter opens the input, and after Enter the active element is the title control, not `document.body`. It fails today. Seam: Keyboard & dialogs x Tasks (rename).

## F1032 (C) -- the pane resizers are tab stops with no visible focus: the line meant to light up on focus is pinned to its resting colour by an inline style

**Status:** fixed in code 2026-10-27 (Tier 0, built with slice I): the resizer line's resting colour is a class (`bg-[var(--border-region)]`), so the `--ring` focus and hover colours win. Test: `draws its line from classes` in `PaneResizer.test.tsx`. The browser re-drive (`scripts/drive/s1023_kb_*.py`) is still to be run against the rebuilt bundle. Found 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Keyboard & dialogs row; scratch Hub :8118, profile kb1023, proj-f7897cfb459c, Chromium against the served bundle, `scripts/drive/s1023_kb_tabwalk.py`, `s1023_kb_rings.py`, shots `testbed/ui-judge/s1023-kb/ring_light_pane-resizer.png`, `ring_dark_pane-resizer.png`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Repro: from a fresh load, Tab through the shell. Stop 12 is `DIV role=separator aria-label="Resize navigation"` (`pane-resizer`). Every other rail and top-bar stop draws a ring: the teal `--ring` box-shadow, or the browser's outline on Search, Add project and the agent menu. This one draws nothing. Its outline is `solid 2px rgba(0,0,0,0)`, its box-shadow is `none`, and the 1px line inside reads `rgba(0, 0, 0, 0.06)` both unfocused and focused (light mode, `--ring` = `#1d6b6e`). The control works: ArrowRight moves the rail from 248 to 256. The operator cannot see that they are on it, so arrow keys pressed there appear to do nothing until the rail moves.

Cause (verified): `hub/ui/src/components/layout/PaneResizer.tsx:139-160` sets `focus-visible:outline-none` on the separator. It relies on the inner span's `group-focus-visible:bg-[var(--ring)]`, but the same span has `style={{ background: 'var(--border-region)' }}`, and the inline style beats the class in both hover and focus. Every `PaneResizer` has this, including **Resize conversation** (`ConversationView.tsx:581-588`). The hover colour is dead for the same reason.

**Expected:** a focused resizer shows the `--ring` line (move the resting colour into a class, or set the colour from state), and it reads in both modes.

**Test:** `hub/ui/src/__tests__/PaneResizer.test.tsx`: after focus, the line's computed background is `var(--ring)`. In jsdom, assert that the inline style no longer pins `background`. It fails today. Seam: Keyboard & dialogs (focus visibility).

---

## F1038 (B) -- removing a task worktree that holds a `node_modules` junction empties the main checkout's `node_modules`: `git worktree remove --force` follows the junction

**Status:** fixed 2026-10-27 (slice A, worktrees-never-destroy-or-strand-anything: every removal unlinks links first, the Hub links nested node_modules itself with a junction fallback; tests test_worktree_removal_links, test_dependency_links_fall_back_to_junctions); opened 2026-10-23. Found while building `agentweave-calls-you-with-its-own-sound` interactively: `hub/ui/node_modules` was emptied twice in 20 minutes (20:36 and 20:51) while the `:8000` Hub ran this repo's flow tasks. **Recurred 2026-10-27 05:44** on `:8000`: the main checkout's `hub/ui/node_modules` was found empty with that mtime (T4's merge and worktree removal); restored with `npm ci`. Slice A (`worktrees-never-destroy-or-strand-anything`) is being built in Wave 0.
**Source:** drive
**Theme:** Worktrees
**Ready:** yes
**Tier:** 0

An agent in `.agentweave/tasks/task-919d0e3104b5` linked `hub/ui/node_modules` to the main checkout's (`mklink /J`, 20:25, the recipe DEAD-ENDS gives for running vitest in a worktree). When the Hub removed that task's worktree, the main checkout's `hub/ui/node_modules` was left empty (mtime 20:51:33); the same happened at 20:36, consistent with `task-64b4438d6b98`. Repro without the Hub, git 2.49.0.windows.1: `git worktree add ../wt`; `mklink /J ..\wt\node_modules ..\target` (target holds a file); `git worktree remove --force ../wt` deletes the file in `target`. Every Hub removal path is `_run_git(repo_root, "worktree", "remove", "--force", path)` (`hub/hub/worktrees.py:988`, `:1193`, `:1513`, `:1567`, `:1627`), and the fallback `shutil.rmtree(path, ignore_errors=True)` at `:1195` also follows a junction on Python 3.11. Nothing unlinks junctions first, which DEAD-ENDS (2026-10-22) already says to do by hand. A junction can point anywhere (a shared `.venv`, a vault), so the loss is not limited to regenerable dependencies. **Fix:** before each removal, walk the worktree without following links, and remove every reparse point (`os.path.isjunction` is 3.12+; on 3.11 use `os.lstat(p).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT`) with `os.rmdir` / `os.unlink`, then remove the worktree. **Test:** a hub test makes a real junction in a task worktree to a `tmp_path` directory holding a file, runs each removal path, and asserts the file survives; red before.

## F1039 (C) -- the operator stream opened twice when its last subscriber unmounted mid-connect, so every event reached every listener twice

**Status:** fixed 2026-10-23 (Tier 0, interactive, with `agentweave-calls-you-with-its-own-sound`). Found by that change's drive: one question asked behind the window counted as "(2) AgentWeave".
**Source:** drive
**Theme:** Live updates
**Ready:** yes
**Tier:** 0

`connect()` (`hub/ui/src/hooks/useSSE.ts`) guarded a second attempt with `connectingUrl`, but `cancelReconnect()` (run when the last subscriber unmounts) cleared it while the first `fetch` was still in flight and had nothing to cancel yet. StrictMode's mount, unmount, mount does exactly that, so a remount started a second fetch; when both resolved, both readers stayed open (the page showed two `/api/v1/events` requests). Every listener got each event twice, which was harmless for cache invalidation and visible once something counted. **Fix:** a connect generation, bumped by each attempt and by `cancelReconnect`; an attempt whose fetch resolves stale cancels its own body and returns without scheduling a reconnect. **Test:** `hub/ui/src/__tests__/useSSE-one-stream.test.tsx` renders a subscriber under `<StrictMode>` with a fetch that answers after the remount: 2 deliveries before, 1 after, one stream left open. **Drive:** `scripts/drive/d1023_notifications.py` asserts '(1) AgentWeave' (it read '(2)' before). **2026-10-24:** the test's own fixture kept CI's `ui-test` red from f72cace on. The stale stream the fix cancels still had a timer queued to enqueue into it, so Vitest reported `Invalid state: Controller is already closed` as an unhandled error even though every test passed. The fixture's `cancel()` now clears that timer, which is what a server does with a closed connection.

## F1042 (B) -- the first chapters run on a real project is refused: the prompt says new knots may be left out, the Hub requires all of them on a first version

**Status:** fixed 2026-10-24 (Tier 0), not yet driven on `:8000` (needs its restart and a "Write chapters" press). The prompt now says to leave no knot out, and an answer refused only for knots it left out is answered back once with that list, both spawns' usage on the one firing (`retried_for`). Tests: `test_the_prompt_never_invites_leaving_a_knot_out`, `test_unplaced_knots_are_answered_back_once_and_both_spawns_are_counted`, `test_a_second_refusal_is_not_retried_again`, `test_a_refusal_for_anything_else_is_not_retried`. Found on the operator's `:8000` Hub, AgentWeave's own project: the first "Write chapters" firing (Sonnet, 65 s, $0.22, event `manager_job_fired` 21:02:17) ended `failed`, "The answer was refused", with 146 problems, every one `knot document:spdoc-… is in no chapter`. No version was saved.
**Source:** drive
**Theme:** Thread
**Ready:** yes
**Tier:** 0

`chapters.save` (`hub/hub/chapters.py:231-234`) requires every knot known at the previous save to be in a chapter, and with no previous save it requires the whole surface (`required = set(surface)`), which is what `every-knot-once` in `the-thread-reads-as-chapters-the-manager-writes` states. The job's prompt (`hub/hub/chapters_job.py:107-109`) tells the model "A knot no chapter holds yet may be placed in a chapter or left out", which on a first run covers every knot. The model followed the prompt: it placed the other kinds and left the spec-document knots out, and the Hub refused the whole answer. The trial-Hub acceptance drive passed because its project was small enough for the model to place everything. Fix candidates: the prompt states that a first version places every knot, and that later versions may leave out only knots recorded since the last version (a test asserts the first-run prompt says so); consider whether a refusal made only of unplaced knots should be answered back to the model once rather than discarding a paid answer.

## F1043 (B) -- every run longer than 10 minutes is reported dead: the stall sweep reads a heartbeat column nothing writes

**Status:** fixed 2026-10-24 (Tier 0): a run is dead only when it is recorded running, this Hub is not executing it (`run_liveness.live_run_ids`) and it started over 5 minutes ago; an open `dead_run` stall ends itself once its run is live or over. A live run that goes silent is the operator's, never the mender's (operator's option b): change `a-run-that-goes-quiet-is-shown-to-the-operator`, Tier 2, not built. Raised by the operator ("long running work keeps triggering the stale state and making the mender run to do nothing"); confirmed on `:8000` read-only.
**Source:** drive
**Theme:** Mender
**Ready:** yes
**Tier:** 0

`stalls._sweep` (`hub/hub/stalls.py`, `cause="dead_run"`) takes `run.last_heartbeat_at or run.started_at` and reports a run dead when that is older than `HEARTBEAT_STALE_AFTER * 5` (10 minutes, `agent_status.py:8`). No code writes `Run.last_heartbeat_at` (the only heartbeat route writes `AgentHeartbeat` rows), so the sweep always measures from the run's start. On `:8000`: 250 runs, 0 with `last_heartbeat_at` set; 43 `dead_run` stalls since the mender shipped (d8f7303, 2026-10-23), over 9 runs, and all 9 ended `completed` -- every one a false alarm. They cost 41 mender turns, and the same live run was re-reported every sweep after the mender closed it (`run-4ab083547f1e`, Architect, 21:24, 21:29, 21:34, 21:39), twice with the mender wrongly concluding no process existed. Silence is not death: a run waiting on a 19-minute test suite sends nothing and is healthy. The Hub already holds an authoritative answer for its own runs, `run_liveness.active_ptys` / `active_app_server_runs` (an entry exists exactly while this process executes the run), and every run row carries `pid`.

## F1045 (C) -- Overview shows notifications that cannot be dismissed and offer nothing to do

**Status:** fixed 2026-10-27 by slice I `overview-notices` (7e32e8e, merged c38a94f): every Overview row can be cleared. Was: open 2026-10-25. Operator request, noted at their ask for later ("there are some notifications in overview that are not dismissable and I have no action to take on them they are just living there"); not explored.
**Source:** operator
**Theme:** Overview
**Ready:** no
**Tier:** ?

Seen on the operator's `:8000` Hub. Not yet looked at: which notices they are, what raises them, and whether each should carry an action, clear itself when its cause ends, or be dismissable. Start by asking the operator for a screenshot or by reading the Overview's notice sources read-only.

## F1047 (A) -- input queued into an archived conversation wedges the agent's whole queue

**Status:** fixed 2026-10-27 (Tier 0): the scheduler holds input whose conversation no turn can start in, records why and the repair on it ("conversation … is archived. Unarchive it to deliver this input, or withdraw it"), and runs the agent's other conversations; Unarchive now schedules the agent, so the named repair delivers; a roadmap's next-slice turn opens a new conversation when the one it was asked from is no longer open. Tests: `hub/tests/test_input_in_a_closed_conversation_holds_nothing_else.py`, `test_spec_roadmaps.py::test_a_slice_whose_conversation_was_archived_is_drafted_in_a_new_one`. Raised by the operator ("I've written a checkpoint for architect but it seems stuck … Never started a turn"); confirmed on `:8000` read-only.
**Source:** drive
**Theme:** Queue
**Ready:** yes
**Tier:** 0

On `:8000`, 2026-10-27: approving slice B of the "Flows that do not stall" roadmap with `draft_next_slice` (22:57 on 10-26) recorded the slice author's conversation `conv-a2c7eee14525`, which the operator had archived at 22:14. When the slice's last task was approved (05:44:45) `slice_drafting._queue_if_built` queued the drafting turn into it, unchecked. The entry was the Architect's queue head, and `turn_scheduler._attempt_turn`'s "conversation is unavailable" early return ended every pass on it without recording a reason, counting an attempt or giving up -- so the checkpoint successor (06:40, auto-continue on) and the operator's own message (06:46), in open conversations, sat `queued` with 0 attempts and no reason, and nothing told anyone why. The archive route's own refusal ("nothing delivers into an archived conversation") guards only input queued *before* the archive. The repair the reason would have named, Unarchive, did not re-schedule the agent either. The other early return of the same shape ("queued entry has no conversation") is held the same way.

## F1048 (A) -- a stall the mender gave up on is raised again on the next firing, and the mender is woken again: 30 turns overnight on one unchanged situation

**Status:** fixed 2026-10-27 (Tier 0): `stalls.record` counts a report on the latest stall of its key when that one ended `gave_up` with the same reason, and wakes no one; a changed reason opens a new stall. Tests: `test_a_stall_given_up_on_is_not_raised_again_while_its_reason_holds` and `…_raised_again_once_its_reason_changes` (`hub/tests/test_a_stalled_project_wakes_the_mender.py`). Found reading `:8000` read-only after the operator said "it seems that the mender had a lot of problems this night".
**Source:** drive
**Theme:** Mender
**Ready:** yes
**Tier:** 0

The night of 10-26/27 (AgentWeave project): 40 stalls, 42 mender runs, all Opus, 15.2M tokens, about $15.9 API-equivalent. 30 of the 40 were `review_unstaffed:task-8618731d065d`, one every 5 minutes from 00:44 to 03:16, all with the same reason text ("Approval of task-8618731d065d … waits on you: its checks fail on main too …"), and every one ended `gave_up` with the same diagnosis: the operator has to land it with an override, or master has to be fixed first. Each also asked the operator the same blocking question, 27 in all, none answered (4-minute waits while the operator slept). The cause: `stalls.record` (`hub/hub/stalls.py:190-224`) counts again only an *open* stall with the key. A stall ended `gave_up` matches nothing, so the next firing's `stalls.report` (`scheduler.py:4331`, every tick of the loop's job) opens a new one and `wake` sends the mender again, though nothing has changed. `gave_up` means "this is the operator's now", so the same key with the same reason should be counted on the stall that gave up (`seen_count`, `last_seen_at`) and not wake anyone. A changed reason is a new situation and should open a new stall; at 03:25 the text changed and the mender fixed it in one turn. **Test:** in the stall tests: record → end `gave_up` → record with the same key and text creates no stall and wakes nothing; with a different text, it does.

## F1049 (B) -- `loop_stalled` fires in the seconds between a task finishing and the flow handing it on

**Status:** fixed 2026-10-27 (Tier 1, slice `the-mender-wakes-only-for-real-stalls`): `decide_firing`'s fresh-review arm records a completed task whose author's turn is still running as in flight, not deferred, so the firing is not a stall; the end of that turn requests the firing that offers the review, and a turn that never ends stays the sweep's (`dead_run`, `no_progress`). Not a timer or a second sighting. Tests: `hub/tests/test_the_mender_wakes_only_for_real_stalls.py`, `test_review_waits_for_the_authors_turn.py`. Same read of `:8000`; the night-after check (no `loop_stalled` within 10 s after a `completed` transition) is the operator's.
**Source:** drive
**Theme:** Mender
**Ready:** yes
**Tier:** 1

All 6 `loop_stalled` stalls that night were false alarms of one shape. A flow's last claimable task reached `completed`, and the firing in the next ~3 seconds found "no claimable task" or "awaiting a prerequisite's approval" (`scheduler.py:4405-4412`) before the flow moved the task to `under_review` and started the review. The mender then read the situation, found the review running, changed nothing and ended `fixed` (23:42, 23:53, 00:15, 04:20, 04:53, 05:24). Each is one Opus turn spent finding nothing. A completed task that is about to be handed to review is the flow working. Either a stall should need to be seen on a second firing before it wakes the mender, or a just-completed task awaiting its review dispatch should not count as a stall.

## F1050 (C) -- a `stuck_task` stall for a task that no longer exists stays open forever

**Status:** fixed 2026-10-27 (Tier 0): each sweep ends an open `stuck_task` stall whose task is gone or no longer `in_progress` (`stalls._end_stuck_task_stalls_that_moved`). Test: `test_a_stuck_task_stall_ends_once_its_task_is_gone_or_moved`. Same read of `:8000`.
**Source:** drive
**Theme:** Mender
**Ready:** yes
**Tier:** 0

`stall-119d728f8da6` (`stuck_task:task-ca661c1265b8`, "Flaky: test_the_continuation_uses_the_remaining_deadline …") has been open since 10-25 21:32, was seen 211 times, and was last seen 10-26 18:35. The task row no longer exists, so the sweep has stopped seeing it (`stalls.py:701-716` reads only existing `in_progress` tasks), but nothing ends the stall: `resolve_task` runs on transitions, and deleting a task goes through none. The stall shows as open, with an open mender conversation, about nothing. Like the `dead_run` fix in F1043, the sweep should end an open `stuck_task` stall whose task is gone or no longer `in_progress`.

## F1051 (B) -- the newest integration row is chosen by timestamp alone, and one approval writes several rows with the same timestamp

**Status:** fixed 2026-10-27 (Tier 0, built with slice I): `_latest_integrations_by_task` orders by `created_at` desc, then the outcome that matters (`failed`, then `merged`, then `skipped`), then insertion (`task_integrations.rowid`), so a tie cannot be left to SQLite. Tests: `hub/tests/test_the_newest_integration_is_decided_without_a_tie.py` (merged before or after skipped both report `merged`; a failure is not hidden by a merge; equal rows resolve to the last inserted). Found while drafting slice I (`the-apps-other-surfaces-make-sense`), confirmed on `:8000` read-only.
**Source:** code
**Theme:** Integration
**Ready:** yes
**Tier:** 0

`_latest_integrations_by_task` (`hub/hub/api/v1/tasks.py:557-578`) orders by `(task_id, created_at desc)` and keeps the first row per task. One approval can write more than one `task_integrations` row in the same transaction with an identical `created_at`: on `:8000`, task-8618731d065d has `merged` and `skipped` ("09617d3b6920 is already in master") both at `2026-10-27 03:39:29.548442`, and 26 task/timestamp pairs tie. Which row wins is then up to SQLite, so a task that merged can read "approved but not merged" on the Overview and in its drawer (part of what F1045 shows). **Expected:** the newest is decided by an order that cannot tie (the row's insertion sequence, or the outcome that matters for the approval: a `merged` row in the same approval wins over a `skipped` one). **Test:** two rows for one task with the same `created_at`, `merged` inserted before `skipped`: the route reports `merged`.

## F1053 (C) -- every press of Check starts the vault's spec check, a model run, even for unchanged or blocked content

**Status:** fixed 2026-10-27 (Tier 0): the route starts the check only for a document with no blocking gap whose content version the newest firing (not a failed one) has not recorded in its subject; the firing now records `content_version` (`hub/tests/test_check_starts_the_vault_check_once_per_version.py`).
**Source:** code
**Theme:** Spec flow
**Ready:** yes
**Tier:** 0

`POST /documents/check` (`hub/hub/api/v1/spec.py:3182-3187`) schedules `vault_spec_check.check_in_background` on every call. The old propose started it only after a successful move. Check is meant to be pressed freely while an agent edits, and on `:8000` the `spec-vault-check` Manager job is enabled (Sonnet), so each press spawns a model run, including presses on a document with blocking gaps and repeated presses on content that was already checked (nothing in `vault_spec_check.py` compares the content to the newest firing's). **Expected:** the check starts only for a document with no blocking gaps, and not again for a content version whose newest firing already checked it. **Test:** Check twice on unchanged ready content starts one check; Check on a document with a blocking gap starts none; Check after an edit starts one.

## F1054 (C) -- a flake the task itself introduces lands with the Hub's automatic override

**Status:** won't fix 2026-10-28 -- by design. The operator decided: yes, a flake the task itself introduces still gets the Hub's automatic override (the fix task M files keeps it visible). Found by the review of slice M (`a-red-main-does-not-hold-the-night`), adversarial run.
**Source:** code
**Theme:** Checks
**Ready:** no -- needs a decision on how much evidence of flakiness on main is required
**Tier:** 1

Slice M treats a failed test id that passes when rerun on its own as a flake, lands the approval with the Hub's recorded override, and files a fix task, without asking main (its FR-2). The reviewer changed `lib.py` (not a test file, so the touched-file rule does not fire) so that `test_lib.py::test_ok` failed once and then passed on the serial rerun: approval returned 200 with "passed when rerun on its own" and a fix task blamed the flake. A flake the task introduced through code it changed is the task's own defect. **Options:** require the id to have flaked before on main (the flaky-test records already kept, `flaky_tests.py`), or rerun the id on main's tree as well and count it a flake only when it is unstable there too; or treat a flake as the task's own when any file the task changed is imported by the test (costlier to compute). Not fixed in M: the operator decides.

## F1059 (B) -- inside a flow, a builder's completion is recorded without waiting for the fast checks: two flow tasks completed in ~0.4 s and their first check run started 5-20 s afterwards

**Status:** fixed 2026-10-28 in b513303 (merge 4aebe4a) (Tier 0, slice L's own defect; a test failing before the fix, then the fix). Found by the scoped drive of slices L/M/J (scratch Hub :8031, profile drivelmj, project aw-drive-lmj, Haiku runners).
**Source:** drive
**Theme:** Checks
**Ready:** yes
**Tier:** 0

Outside a flow the fast check ran before the completion was recorded (task-7973: run 09:20:41, completed 09:20:51; task-222e: run 09:21:53.9, completed 09:21:54.5). In the flow, `shout` (task-0356) completed 09:33:06.67 with its first run chk-f272e33e44ac starting 09:33:11.18, and `title_case` (task-e0e7) completed 09:34:17.3 with chk-7fb9fec82c6e starting 09:34:37.6; the Hub-filed fix task (task-a8340) in the same flow did get its run first. A fast-check failure on those tasks would have reached `completed` and been caught only after. Evidence: `task_check_runs.started_at` vs `task_transitions.created_at`, read-only, and the agents' update_task call times. Path: `api/v1/tasks.py:1947` -> `run_fast_checks_before_completion` -> `project_checks.fast_checks_at_completion` (silent `return None` exits). Area: Worktrees & integration (project checks) x Flows & review.

## F1060 (B) -- a re-completion of unchanged work is refused with the earlier run's output and never says the work is unchanged or which checkout is checked; the builder, editing its agent worktree, retried ~10 times and decided the checks were a "stale cached result"

**Status:** fixed 2026-10-28 in b513303 (merge 4aebe4a) (Tier 0, slice L's own defect; a test failing before the fix, then the fix). Found by the scoped drive of slices L/M/J (:8031, aw-drive-lmj).
**Source:** drive
**Theme:** Checks
**Ready:** yes
**Tier:** 0

Task-222e was sent back with origin `checks`. The next builder turn was an empty-queue flow firing with no task checkout bound; it edited `.agentweave/worktrees/dev` instead of `.agentweave/tasks/task-222e...`, then called `update_task(completed)` about ten times, each answered 409 "check unit failed on b872798b33c5 ... check run chk-f3ef5307ba17" (a non-fast check, quoted from the earlier run). The agent's words: "The check system seems to be showing a stale cached result." Refusing unchanged work with its recorded verdict is by design (`fast_checks_at_completion` docstring); the refusal must say the work is unchanged since that run and where the task's checkout is. Area: Worktrees & integration x Runs.

## F1063 (B) -- at Fast a builder's approval is refused because its evidence is unjudged, so "Fast approves without a reviewer" never fires

**Status:** fixed 2026-10-28 in 2d7ed79 (merge 12050fd) (Tier 0, slice D's own defect; a test failing before the fix, then the fix). Found by the scoped drive of slices D/D2/E (scratch Hub :8032, profile drivedde, project aw-drive-dde, Haiku runners).
**Source:** drive
**Theme:** Flows & review
**Ready:** yes
**Tier:** 0

At a Fast build the builder completed its task (evidence `awaiting`) and called `update_task(approved)`: 409 "This task's work has been recorded and nobody has judged it: FR-5 at 4b5ac3a5b3db. Approving now would record that the work is good and merge none of it, because only accepted evidence is merged. To land it, accept the evidence, or grant an agent the capability to accept it...". A builder cannot accept its own evidence; the operator's approval accepted it in the same act ("Accepted with the approval of task-..."). Slice D's D4 promises completed -> approved at Fast for the builder, the lead and the flow. The flow's own Fast approval after checks pass was not driven. Area: Tasks x Requirements, evidence & coverage.

## F1064 (B) -- the Hub's own batched landings raise "main moved" notices, and join an open one, because their integration rows carry no merge sha

**Status:** fixed 2026-10-28 in bd55d7a (merge 139f6d5) (Tier 0, slices D2/E's own defect; a test failing before the fix, then the fix). Found by the scoped drive of slices D/D2/E (:8032).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

Every `task_integrations` row the batch wrote had `merged_sha = NULL`, so the main watch could not tell the Hub's "Integrate approved work..." merges from a hand commit: after the first notice was marked seen, a batch of Hub merges alone produced `mnot-9c494088cdc7`, and the genuine notice (a hand commit) absorbed the Hub's merges as its list grew; `main_moved` events at 09:25:26, 09:30:57, 09:43:28. The operator is notified after every landing. Area: Worktrees & integration x Logs, events & SSE.

## F1065 (B) -- a "no reviewer free" stall names agents outside the build's reviewer pool as "running a turn" when they are not running

**Status:** fixed 2026-10-28 in 2d7ed79 (merge 12050fd) (Tier 0, slice D; a test failing before the fix, then the fix). Found by the scoped drive of slices D/D2/E (:8032).
**Source:** drive
**Theme:** Flows & review
**Ready:** yes
**Tier:** 0

`review_unstaffed` at 09:24:40 with reviewers `[qa]`: "dev2 is running a turn; lead is running a turn; qa is booked for task-471e79841cd2"; no dev2 or lead run was active. `scheduler._rung_3_clause_text`'s fallback label is applied to out-of-pool agents. Area: Flows & review.

## F1069 (B) -- the composer's "Open an existing specification document" picker overflows its dialog: 697 px of content in a 558 px dialog, "+ New", "Roadmap" and the phase filter cut off (Ctrl+Shift+K the same)

**Status:** fixed 2026-10-28 in 9826951 (Tier 0, slice F's own defect; a test failing before the fix, then the fix). Found by the scoped browser drive of slices F/G/I (scratch Hub :8033, profile drivefgi, Haiku runners); shots `testbed/ui-judge/drive1028-fgi/open_existing.png`, `ctrlshiftk.png`.
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

`spec-picker` scrollWidth/clientWidth 697/557: the corpus strip takes a wide left column and pushes the picker to the right edge. The panel's Specs tab renders the same picker cleanly (`panel_specs_tab.png`). Area: Spec documents x Keyboard & dialogs.

## F1070 (B) -- the side panel at 360 px clips the spec page's approval-gaps block (scrollWidth 392 vs 360), against `side-panel-parity`

**Status:** fixed 2026-10-28 in 9826951 (Tier 0, slice F; a test failing before the fix, then the fix). Found by the scoped browser drive of slices F/G/I (:8033); shot `panel_narrow.png`.
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

The right edge of the gap text is lost ("at s", "whic", "th"). Area: Spec documents (side panel).

## F1071 (C) -- Ctrl+Shift+K opens the spec picker on top of the command palette: two layers, two Escapes

**Status:** fixed 2026-10-28 in 9826951 (Tier 0, slice F; a test failing before the fix, then the fix). Found by the scoped browser drive of slices F/G/I (:8033): dialogs `['Command palette', 'Search documents']`, then `['Command palette']`, then `[]`.
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Area: Keyboard & dialogs.

## F1080 (B) -- a flow that stops on an empty queue stays stopped when the landing checks send one of its tasks back

**Status:** fixed 2026-10-29 by `a-checks-send-back-returns-the-task-s-accepted-evidence` (D2): a flow with `stop_when_queue_empties` does not end while an approved task's landing is open (queued, checking, landing, held), and a firing whose only open work is landings in progress is in flight, not a stall. Tests: `hub/tests/test_a_flow_stays_open_until_its_work_lands.py` (`test_ac_flow_stays_open_while_its_last_tasks_landing_is_queued`, `test_ac_landing_wait_quiet_records_in_progress_and_wakes_no_mender` and `test_ac_resumed_after_landing_send_back_starts_the_assignees_turn` failed before the change). Was: open 2026-10-29. Reported by the operator ("another thing stopped the flow") on `Vault sources can be edited, replaced and archived` (`spdoc-ed2248eba283`).
**Source:** drive
**Theme:** Flows x Worktrees & integration
**Ready:** yes
**Tier:** 1

Repro, read from the live database (read-only): QA approved the last task, `task-a80259e4ab36` (vault-tab), at 09:14:53. At that same moment flow `loop-5d6bd866f424` (`job-953637bb694f`, `stop_when_queue_empties`) ended: `ending_state: completed`, `stop_reason: "loop queue is empty"`. At 09:29:33 landing batch `lbat-3bc888bd9903` ran the project's checks on master and sent the task back to `revision_needed` (transition origin `checks`). The reason was the `hub-tests` surface-ceiling ratchet: 68 query call sites ignore their error, against a ceiling of 67. The task is still assigned to Developer, but its flow has ended, so no firing ever picks it up. Its document is half-landed with no signal on the flow, and the operator only notices because the work did not arrive. Cause: the flow's stop condition counts `approved` as done, but approval comes before landing. **Expected:** one of two behaviours (the operator chooses): (a) the flow does not end while any of its approved tasks is still waiting to land; or (b) a landing send-back of an ended flow's task reopens the flow, or at least triggers the task's assignee and records a `loop_task_reopened` event on the flow. **Test:** a flow with `stop_when_queue_empties`, its last task approved and then sent back by a landing batch. Today the loop stays `completed` and no run starts. Seam: Flows x landing queue.

## F1081 (B) -- re-completing a sent-back task checks the commit its old accepted evidence names, not the fix

**Status:** fixed 2026-10-29 by `a-checks-send-back-returns-the-task-s-accepted-evidence` (D1): a checks send-back (a failed check run at completion, or a failing landing batch) now holds the task's own accepted evidence, less pieces already on main, so the next completion is checked on the fix. Tests: `hub/tests/test_a_checks_send_back_returns_accepted_evidence.py` (`test_fix_is_checked_after_check_run` and `test_fix_is_checked_after_landing` failed before the change by targeting A). Was: open 2026-10-29. Found right after F1080, on the same task, `task-a80259e4ab36`. (F1080 and F1081 were first written as F1047/F1048 on a branch whose ledger was behind master's; renumbered 2026-10-29.) Second occurrence of the archive task's 9-hour stall (vault note `src-f2ceb873aae1`). Being fixed by the change `a-checks-send-back-returns-the-task-s-accepted-evidence`.
**Source:** drive
**Theme:** Worktrees & integration x Evidence
**Ready:** yes
**Tier:** 0

Repro, read from the live database (read-only): landing batch `lbat-3bc888bd9903` sent the task back (`hub-tests` surface ceiling, 68 against 67). The send-back left QA's earlier acceptance of the evidence at `fd8aa77` in place. Developer fixed `VaultScreen.tsx`, re-recorded evidence, and completed the task at 09:46:05. The completion auto-committed the fix as `a6f5617` (09:46:04). Check run `chk-2edc3a8bd93b` then started with `target_shas: ["fd8aa77"]`, the commit without the fix, and failed with the same 4 `test_surface_ceilings` failures. `test_surface_ceilings.py` passes 6/6 at `a6f5617`. Cause: `project_checks.check_targets` (`hub/hub/project_checks.py:1021`) takes `merge_targets`, which names commits from accepted evidence; the evidence still accepted at that moment pointed at the pre-fix commit. From `completed`, the only way on is `under_review`, and the failed check refuses that, so neither agent can recover the task. The operator's "run checks again" (`POST /tasks/{id}/checks/run`) does not help either: it resolves the same accepted targets and checks the same commit. What unblocked the archive task was a reviewer accepting evidence at the fix, which makes the fix the newest accepted commit. **Expected:** a landing send-back holds or rejects the task's accepted evidence, so it cannot be merged as is. Alternatively, a completion's check targets include the task branch tip the completion just committed. **Test:** a task with accepted evidence at commit A, sent back by a landing batch, fixed in commit B and completed. Its check run must target B; today it targets A.

## F1088 (C) -- a document whose default checker is named `checker` reads on its spec page as "the document names no reviewer"

**Status:** fixed 2026-10-29 (task-5f4335f3826b; filed as a second F1085, renumbered F1088): the delivery status and the build outcome's `reviewer` resolve through `spec_payload.default_checker` (`hub/tests/test_a_document_names_its_default_reviewer.py`). Opened 2026-10-29. Found by QA2 driving the Build dialog for `the-build-plan-lives-in-the-spec-and-every-task-goes-to-its-people` (task-a85075abe995, `scripts/drive/d1029_build_dialog_browser.py`, artefacts `%TEMP%/drive1029-build-plan-in-spec/211931-dialog/no_build_button.png`).
**Source:** drive
**Theme:** Builds
**Ready:** yes
**Tier:** 0

Repro: approve a change document whose delivery is `{"mode": "flow", "agent": "Developer", "builder": "Developer", "checker": "QA"}` and open it on the spec page. The approval bar's `ReviewerLine` (`hub/ui/src/components/spec/SpecPhaseParts.tsx:93`) reads "Reviewed by any free agent: the document names no reviewer." Yet the Build dialog for the same document pre-selects QA as the default checker, and the build sends t1's check to QA. The delivery status only looks at the old field: `hub/hub/api/v1/spec.py:295` sets `status["reviewer"]` from `delivery.reviewer` alone. The build outcome's `reviewer` key does the same (`spec.py:3563`, `:3634`). The change brought in `delivery.checker` (FR-1 `one-checker`) without updating these readers. **Expected:** the status names the default checker as `spec_payload.default_checker(payload)` resolves it (checker, else tester, else reviewer), with the same not-an-open-agent warning. **Test:** a document with `delivery.checker: "QA"` and no `reviewer`; the delivery status read carries `reviewer` (or `checker`) `QA` with state `ok`.

## F1089 (B) -- a spec whose build finished reads `approved`, the same as one never built, so the operator cannot tell which specs are done

**Status:** fixed 2026-10-29 (task-5776b7d94b0c: the Hub computes `display_phase`, approved/building/done, in the document reads; `hub/tests/test_a_spec_shows_building_and_done.py`). Operator report ("When a spec finished building it goes back to approved. We don't know which spec finished building").
**Source:** operator
**Theme:** Builds
**Ready:** yes
**Tier:** 1

Repro: `spdoc-a7d41f10be14`'s build `build-c68972449bdc` ended `finished` at 2026-10-29 21:49. The document reads `phase: approved, step: build`, exactly as it did before Build was pressed. The finished state lives only in `build.last_ended` (and the header's `BuildStatusStrip`, `useSpecPhaseControls.tsx:598`, which only shows once the document is open). Nothing in the UI reads `last_ended`. The spec list and search show phase alone, and no notice says a build finished. To find the specs that are done, you have to open each approved one. **Expected (to be decided):** every place a document is listed says built / building / not built, and a build finishing raises a notice that names the document and what is left before it can be folded (see F1090). **Test:** a Hub test where a build finishes, then the document listing carries the build state `finished`; plus a UI test that the list shows it.

