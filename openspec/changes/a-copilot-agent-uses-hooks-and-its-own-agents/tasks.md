## Before you start

Build only after slices 1–4 (`each-runner-cli-is-one-adapter`, `a-copilot-agent-runs-over-acp`,
`a-run-reaches-the-hub-without-mcp`, `a-copilot-run-shows-its-credits`) and the 2026-09-27 night
queue have landed. **At R2 (2026-09-28, master `ef55e6f`) none of slices 1–4 and only 5 of the
night's 28 changes had landed; R3 (master `fc33ff9`) found the same.** Before starting, re-read
design.md's *Required of slices 1–4* against the slices as built, and fix every "(rebase at IMPL)"
site first. "Fails on today's code" below means **it fails on master after those land and
before this change**.

**Done 2026-10-03** (IMPL pre-check; slices 1–4 are archived, along with
`a-claude-run-is-told-its-agentweave-tools-by-their-full-names` and
`an-ask-me-card-says-what-workspace-only-would-decide`). Every "(rebase at IMPL)" site naming one
of those is now VERIFIED-CODE in design.md's Round log and in place; nothing needed correcting.
The sites naming `worker-spend-counts-against-the-budget`, `a-run-records-that-its-calls-were-allowed`
and `a-file-path-is-not-redacted-as-a-credential` are unchanged — those three remain open/unbuilt.

The four groups are A, C, B and D, in order of value. Each one can be cut. If the operator REJECTED
a group, skip every task tagged with it, and delete its spec delta before archiving:

| Group | Spec delta |
|---|---|
| A | `agent-stream-events`, `conversation-checkpoint`, `agent-run-sandboxing` |
| C | `runner-registry` |
| B | `agent-flows` |
| D | `agent-configuration` |

**Not cut with any group (review 2026-09-28, finding 6):** task 2.8 and its test halves (in 1.6 and
1.8) are tagged with no group. They strip the provider and trust variables from every Copilot spawn
that names no provider, which must hold whichever groups are kept (design D7, D10; *Required* 2.9,
2.10).

**Run tests with `py -3.11`, never bare `python`.**

**Do not use `git stash` or `git checkout --`** in a shared tree. For fail-before evidence, mutate a
scratch copy (DEAD-ENDS 2026-09-27).

## 0. Rounds

- [x] 0.1 R2: re-derive independently. Compare every claim in `design.md` against the code as it
  stands after slices 1–4 and the night queue land, and answer the "Open questions for R2/R3" in
  `design.md`, questions 1 to 7:
  - slice 2's raw-event subscription list and `Error:` classification (D5);
  - where Copilot's `request_permission` meets `_decide` (D9);
  - whether `allow_all` trusts the folder (D3, by reading `app.js`);
  - the merge-target helper for D8's `<base>`;
  - whether `ReviewContext` needs a new field.

  Also re-verify the sites marked "re-verify in R2":
  - `every-event-the-hub-sends-reaches-the-app` (D4);
  - `a-file-path-is-not-redacted-as-a-credential` (D5);
  - `a-run-records-that-its-calls-were-allowed` (D3);
  - `the-codex-models-offered-are-the-ones-its-cli-lists` and `a-model-alias-is-a-model-choice` (D7);
  - `a-flow-stages-its-review-in-the-dispatch` and
    `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` (D8).

  Record the result in `design.md`'s Round log.

  **Done 2026-09-28** (at `ef55e6f`; slices 1–4 unbuilt, 5/28 night changes landed): 15
  corrections, the main ones an unseeable `compacted` banner flag, a dropped in-flight compaction,
  `*_tokens` redaction, `session.error` as an error not a diagnostic, aliases and `openai` for BYOK,
  a false MCP-env allow-list, BYOK launchability unreachable on every surface, `_decide` allowing
  GitHub calls; questions 1, 3, 4 answered, 2/5/6/7 carried, 9 and 10 added; 16 slice mismatches
  tabulated. See the Round log.
- [x] 0.2 R3: a second independent re-derivation, not a re-read of R2. Re-derive D1 by re-reading
  `schemas/session-events.schema.json` in the installed Copilot package: does the raw event still
  supersede the hook for each fact? Re-derive D4's table row by row against `checkpoint_trigger.py`
  as it then stands. Ask what each changed route *returns* when the function it calls raises. The
  routes are `PATCH /agents/{name}` with a bad `copilot_review_agents`, `POST /runners` with a bad
  `provider_config`, and `record_agent_output` when `consider_from_compaction` cannot find the
  conversation (R2's answers are in the Round log; re-derive them, do not re-read them). Also
  `POST /agent/trigger` with a `model` override on a provider runner, and `prepare_review_turn` when
  the merge base cannot be computed. `openspec validate a-copilot-agent-uses-hooks-and-its-own-agents --strict` passes.

  **Done 2026-09-28** (at `fc33ff9`; slices 1–4 still unbuilt): D1 held and D4's rows held (one
  added); 15 corrections, chiefly R2's `Error:` hold replaced by a chunk match on the code-verified
  raw-first order, whole-`data` omission and subagent `agentId` on compactions, a `payload: null`
  500, 3 of 6 wrong probe sites, stored model overrides and runner PATCH bypassing the BYOK model
  rule, a leaking review checkout on a merge-base timeout; Q9 answered; R2's table rewritten as
  *Required of slices 1–4*. See the Round log.
- [x] 0.3 Opus adversarial review of the change and of the three operator questions in design "Open
  questions" 8: hooks wanted (D2), Azure deferred (D7), an API key for the BYOK drive (D7). Record
  it in `spec-queue/tracks/reviews/`. Apply the fixes before any APPROVED row.

  **Done 2026-09-28.** Opus review ghcp-s5-2026-09-28: APPROVE WITH FIXES (C: REVISE) → 11 applied
  (the 3 blocking and 8 should-fix findings: 1-10 and 12; 6 and 8 by reference to slice 2, which owns
  them), 5 answered (notes 11, 13, 14, 15, 16; 11, 14 and 15 also applied as fixes). Contract
  conflict decided: slice 2's REJECT for an unidentified server. The three operator questions carry
  the reviewer's recommended answers in design Open question 8 and remain the operator's. See
  design's Round log, *Review fixes, 2026-09-28*.

  **Operator decisions, 2026-09-28:** every item of design Open question 8 DECIDED ("yes" to all
  recommendations): no hooks (D2); Azure and OpenAI BYOK deferred (D7); a key for drive 7.6 only on
  task 7.6's conditions below; the key in the run's shell and tool server accepted (D7); no
  runner-compacted banner now (D4, possible follow-up); the GitHub-unavailable diagnostic's removal
  path accepted (D9). See design's Round log, *Operator decisions, 2026-09-28*.

## 1. Tests first — each fails on today's code

- [x] 1.1 (A, C) **Capture real Copilot events before writing fixtures**, so that every
  test uses the order Copilot actually emits.
  - **Harness.** Adapt `acp_probe.py` into `testbed/copilot-capture/capture.py`. It uses a scratch
    `COPILOT_HOME` and a scratch cwd under `%TEMP%`, and spawns
    `%APPDATA%\npm\node_modules\@github\copilot\node_modules\@github\copilot-win32-x64\copilot.exe --acp --stdio --no-auto-update --disable-builtin-mcps`
    (slice 2's D3 argv). Its `initialize` subscribes the union of slice 2's list (its D10), slice
    4's additions, and the six types in design D1, plus `assistant.usage`.
  - **Run (a):** prompt `Reply with the single word ok.`, then the prompt `/compact`. That is 2 Free
    model calls.
  - **Run (b):** prompt `Use the explore agent to name one file in this directory, then stop.` That
    is about 3 calls.
  - **Run (c):** BYOK with a deliberately invalid key: `COPILOT_PROVIDER_TYPE=anthropic`,
    `COPILOT_PROVIDER_BASE_URL=https://api.anthropic.com`, `COPILOT_PROVIDER_API_KEY=invalid`,
    `COPILOT_MODEL=claude-haiku-4-5-20251001`, then prompt `ok`. This spends no Copilot allowance,
    and Anthropic answers 401. Record whether the scratch `COPILOT_HOME` was signed in to GitHub
    and what `session/new` returned (design open question 9; R3 predicts no `authRequired` from the
    code). **R3: spawn this run without `--disable-builtin-mcps`** and with no GitHub sign-in in
    the scratch home, so the GitHub server should fail; record whether and when a
    `session.mcp_servers_loaded` / `session.mcp_server_status_changed` names `github-mcp-server`,
    and with which status (design D9: if none arrives within the turn, the unavailable-server
    diagnostic is removed; operator-accepted 2026-09-28, with no replacement signal). (Review 2026-09-28, finding 4) Also record the `mcpServerName` that
    `tool.execution_start` reports for each built-in server's tool, if any tool call reaches one.
  - **Save** each transcript's `github.com/copilot/sessionEvent` notifications and `session/update`
    notifications, **in arrival order**, as `hub/tests/fixtures/copilot/{compaction,subagent,error}.jsonl`.
    Redact `sessionId`, the cwd and any token.
  - **Write down** in `design.md`'s Round log:
    - whether each type was delivered at all (open question 2);
    - which arrived first, `session.error` or the `Error:` text chunk (R3 predicts the raw event,
      from `setupEventForwarding`; design D5), and whether the chunk's text is exactly
      `"Error: " + message`;
    - the byte size of the captured `session.compaction_complete` and whether it carried
      `dataOmitted` (design D4, *Omitted data*; a tiny conversation will not reach 32 KB, so the
      oversized case is tested synthetically in 1.2);
    - whether `subagent.started` arrived before the `tool_call` update of its `task` call.

  If a type is **not** delivered, stop group A. Tell the operator that D1's source does not hold.
  Do **not** build D2's hook transport (operator decision 2026-09-28: no hooks; the fallback is not
  pre-built, and any revisit is the operator's call).

  **Done 2026-10-03.** Real capture: `session.compaction_start`, `session.compaction_complete` and
  `session.error` delivered; `subagent.started`/`completed`/`failed` did not arrive (the model
  declined to dispatch the explore agent for a trivial prompt). **Group A stops here**, per this
  task's own instruction — see design.md's Round log (*Task 1.1, real capture, 2026-10-03*) and
  `spec-queue/DECISIONS.md` `ghcp-s5-subagent-capture` (OPEN, the operator's call: retry with a
  heavier capture, or drop the three `subagent.*` scenarios and ship compaction+error only). Tasks
  1.2–1.6 and 2.1–2.8 below are **not** started pending that decision.
- [ ] 1.2 (A) `hub/tests/test_copilot_lifecycle_events.py`: feed each fixture from 1.1 through the
  Copilot adapter's `map_events` in its recorded order.
  - `compaction.jsonl` gives exactly one `status` event with `phase == "compacted"`, carrying
    `pre_tokens`, `post_tokens`, `token_limit`, `trigger`, and `percent` computed as design D4 says.
    The three token counts are **integers**, not `"<redacted>"` (design D4: `_SECRET_FIELD_RE`
    matches `token`). `summaryContent` appears nowhere in the payload. `trigger` is the captured
    value, one of the schema's `CompactionTrigger` values (R3: not `auto`).
  - A synthetic copy with `success: false` gives a `diagnostic` with code `copilot.compaction_failed`,
    `stream == "copilot"` and `severity == "warning"`, and no `compacted` status.
  - (R3) A synthetic `session.compaction_complete` envelope with `dataOmitted: "too-large"` and
    `data: {omitted, bytes, limit}`, preceded by a root `session.compaction_start {currentTokens,
    tokenLimit}`, gives one `compacted` status with `pre_tokens`/`token_limit` from the start event
    and no `post_tokens`. This fails on a mapper that requires `data.success`.
  - (R3) The captured compaction with an `agentId` added to its envelope gives **no** `compacted`
    status.
  - `subagent.jsonl` gives a `subagent_started` and a `subagent_completed` status sharing the
    `call_id` of the parent `task` tool call's `tool_use` event; `total_tokens` is an integer. The
    pairing assertion is by `call_id`, not position (R3: the raw event can precede the `tool_use`).

  The mapper is slice 2's `copilot_acp.CopilotEventMapper` (slice 1's `map_events` is a
  stream-transport member; design, *Required of slices 1–4*).

  Run `py -3.11 -m pytest hub/tests/test_copilot_lifecycle_events.py -v`.
- [ ] 1.3 (A) Same file, errors.
  - `error.jsonl` in its **recorded** order (R3 predicts raw event first) gives exactly one `error`
    event (code `copilot.<errorType>`, with `status_code` and `remediation` in its facts), no
    `diagnostic` for it, and no `text` event containing `Error: <message>` (design D5:
    `session.error` is an error, not a diagnostic, because diagnostics are hideable).
  - (R3) The same fixture with a model `agent_message_chunk` ("Let me run the tests.") inserted
    just before the `Error:` chunk, with no non-message update between them, gives that prose as
    one `text` event without the `Error:` suffix, and still exactly one `error` event. This fails
    on R2's block-level hold and on slice 2's block classifier.
  - (R3) The **reversed** fixture (chunk before raw event) gives the error event **and** the
    `Error:` text: the test documents that the order matters, and the first case fails if the
    fixture's order is reversed (CLAUDE.md: the ordering the source actually emits). If task 1.1
    recorded the chunk first, stop and revisit design D5 before writing the mapper.
  - With the raw `session.error` removed, the `Error:` text is emitted exactly as slice 2 emits it
    (a `text` event).
  - (Review 2026-09-28, finding 7) A **subagent's** `session.error` (envelope `agentId`; and a
    second copy carrying only `data.parentToolCallId`, Copilot's `_d()` test) followed by its
    `Error:` chunk gives exactly one `error` event with `subagent_id` in its facts and no `Error:`
    text. This fails on a root-only echo match.
  - An `errorType` outside `^[a-z_]{1,32}$` gives code `copilot.unknown`.
  - An error message containing `sk-ant-test-value` is stored redacted.
  - Recording a `quota` error event through `record_agent_output` leaves the agent's allowance hold
    state unchanged: read it before and after (slice 4's reader if built, else
    `provider_allowance`). This tests the recorder, not the run: slice 4 may hold the queue from the
    same raw event through the allowance reading, and that is not this change's.
- [ ] 1.4 (A) `hub/tests/test_checkpoint_from_compaction.py`: one test per row of design D4's table,
  driving `checkpoint_trigger.consider(..., compacted=True)` against real DB rows (pattern:
  `hub/tests/test_checkpoint_cutover.py`). Patch `generate_checkpoint` and `cut_over` only as
  existing checkpoint tests do. For each row, assert:
  - the conversation's `checkpoint_warning`;
  - whether generation was called, and with `trigger == "context_pressure"`;
  - whether an `InboundQueueEntry` with `origin_type == "checkpoint"` was added;
  - whether `checkpoint_due` was broadcast. (R2: no `"compacted"` field; no UI reads the payload,
    design D4.)

  Include:
  - `automatic` with the percent **below** the threshold, which still generates;
  - `offered` + `dismissed` at 96%, which raises no final warning;
  - **in flight:** with the conversation already in `checkpoint_trigger._in_flight`, a
    `consider_from_compaction` is not dropped: once the in-flight task finishes, `consider` is
    called with `compacted=True`, and never while the first is still running. This fails on a
    plain copy of `consider_from_reading`'s early return.
- [ ] 1.5 (A) Same file: `record_agent_output(kind="status", payload={"phase": "compacted", …},
  run_id=…)` dispatches `consider_from_compaction` with the conversation resolved from the run.
  Assert it through a patched `consider`. A `status` with any other phase does not dispatch. With
  `consider` patched to raise, `POST /agents/{name}/output` still answers 201 and stores exactly
  one row. (R3) `POST /agents/{name}/output` with `kind: "status"` and `payload: null` answers 201
  and stores one row; this fails on a bare `payload.get(...)`. (R3) "No running loop" cannot be
  reached through a route (an ASGI app always runs in one), so it is a direct synchronous call of
  `consider_from_compaction`, which returns `None` and leaves `_in_flight` and
  `_compaction_pending` without that conversation.
- [ ] 1.6 (A) `hub/tests/test_copilot_home_has_no_deciding_hook.py`: create a Copilot agent through
  `POST /agents` (slice 2 writes its `COPILOT_HOME`), then:
  - every `*.json` under `<COPILOT_HOME>/hooks/` and the `hooks` key of `<COPILOT_HOME>/settings.json`
    contains none of `permissionRequest`, `PermissionRequest`, `preToolUse`, `PreToolUse`,
    `agentStop`, `Stop`, `subagentStop`, `SubagentStop`;
  - the `COPILOT_HOME` config names no trusted folder;
  - the run environment `resolve_agent_env` returns for a Copilot agent (ending in slice 2's
    `guard_env`) has no `COPILOT_ALLOW_ALL`, under every posture including full access. (R2
    verified in `app.js` that full access's `allow_all` does not trust the folder; design D3.)
    (Review 2026-09-28, finding 6) With `COPILOT_ALLOW_ALL=true` set **ambient**
    (`monkeypatch.setenv`) and, separately, in the agent's `config.env_vars`, it is still absent,
    and absent from the worker and title spawns' `one_shot_env` too. The strip is slice 2's
    (*Required* 2.9); this half is ungrouped (task 2.8) and not cut with A.

  This is a guard: it fails today only because the writer does not exist yet. Say so in the
  docstring.
- [x] 1.7 (C) `hub/tests/test_runner_provider_config.py`, through `POST /runners` and
  `PATCH /runners/{id}`:
  - a `copilot` runner with `{type:"anthropic", api_key_var:"MY_ANTHROPIC_KEY"}` and model
    `claude-haiku-4-5-20251001` is created and returned with `api_key_var`, **no** key, and
    `model_unrecognised: false`;
  - `api_key_var: "sk-ant-api03-xyz"` is refused with **400** and the sentence in design D7 as a
    string `detail`, and the table is unchanged. Count the rows before and after;
  - a `claude` runner with `provider_config` is refused;
  - `type:"azure"` and `type:"openai"` are refused (design D7: both deferred, operator decision
    2026-09-28);
  - a model the `claude` catalog does not declare is refused;
  - no model is refused, on create, and a `PATCH` setting `model: null` on a provider runner is
    refused;
  - an alias (`haiku`) is refused, and the sentence does **not** offer `haiku` (the shared
    `undeclared_model_reason` does since `63d9f34`). This fails if the provider check reuses
    `ProviderDescriptor.model()`;
  - (R3) `PATCH` adding `provider_config` to a `copilot` runner whose stored model is `auto`,
    without sending `model`, is refused with 400 and the row is unchanged; the same `PATCH` also
    setting `model: "claude-haiku-4-5-20251001"` succeeds. `PATCH` with `provider_config: null` on
    a provider runner on `claude-haiku-4-5-20251001` is refused unless it also sets a `copilot`
    model or `null`. These fail on today's `model == current` exemption (`runners.py:37`);
  - (R3) `api_key_var` of 300 characters starting `sk-ant-` gets the 400 sentence, not a 422, and
    the response body does not contain the submitted value.
  - (Review 2026-09-28, finding 15) `provider_config: {"type":"anthropic","api_key":"sk-ant-test-value"}`
    is refused with **400** (not 422), a sentence naming `api_key`, and a response body that does
    not contain `sk-ant-test-value`; a non-string `api_key_var` is refused the same way.
    `api_key_var` of `GH_TOKEN`, `GITHUB_TOKEN`, `COPILOT_GITHUB_TOKEN`, `DATABASE_URL` or
    `AW_ANYTHING` is refused with its sentence.
  - (Finding 10) `base_url` `http://localhost.evil.com`, `http://localhost@evil.com` and
    `http://example.com` are refused; `http://localhost:4000`, `http://127.0.0.1:4000`,
    `http://[::1]:4000` and `https://example.com` are accepted.
  - (Finding 11) a provider runner with `flags: ["--model", "haiku"]` or `["--model=haiku"]` is
    refused on create, and a `PATCH` adding `provider_config` to a runner whose flags carry
    `--model` is refused with the row unchanged.
  - (Finding 1) `PATCH /projects/{id}` choosing a provider runner as `checkpoint_runner_id` with
    `checkpoint_model: "auto"` is refused (400) with the provider sentence, and with
    `checkpoint_model: "claude-haiku-4-5-20251001"` succeeds.

  Run `py -3.11 -m pytest hub/tests/test_runner_provider_config.py -v`.
  **Done 2026-10-03 (night iter 3): 42 passed.** Against HEAD `427bd1a` in a scratch worktree: 42
  failed (the create answers FastAPI's 422 `extra_forbidden` with the pasted key in
  `detail[].input` -- finding 15 as predicted). Ten mutations of the real implementation (variable
  pattern, alias-resolving model rule, Hub-credential names, a prefix-matched base URL, unknown
  field, the PATCH pair judgement, the removal check, PATCH flags, the checkpoint check, the
  response flag) each fail a named test. The "PATCH /projects" case is the route
  `PUT /projects/{id}/settings`, the one settings write there is. It is judged only when the
  `(checkpoint_runner_id, checkpoint_model)` pair changes, so a model stored before the runner
  gained a provider does not block unrelated saves (generation ignores it instead, task 3.3).
- [x] 1.8 (C) `hub/tests/test_copilot_byok_env.py`: with `monkeypatch.setenv("MY_ANTHROPIC_KEY",
  "sk-ant-test-value")`, the run environment built for the provider runner (`resolve_agent_env`
  with the runner's `provider_config`, as the trigger calls it; design D7) has
  `COPILOT_PROVIDER_TYPE=anthropic`, `COPILOT_PROVIDER_BASE_URL=https://api.anthropic.com`,
  `COPILOT_PROVIDER_API_KEY=sk-ant-test-value` and `COPILOT_MODEL=claude-haiku-4-5-20251001`. (R2:
  no assertion about the MCP config's `env`. Slice 2 writes none and the tool server inherits the
  environment, so such an assertion would pass while the key reached the tool server.)

  With `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_TYPE`, `COPILOT_MODEL` and `COPILOT_OFFLINE`
  set in the Hub's own environment, a `copilot` runner **without** `provider_config` gets none of
  them. (R3) The same holds when they are set in the agent's `config.env_vars` instead; this fails
  on a copy of the Claude guard's `env_vars` exemption (`launchability.py:190`). (Review
  2026-09-28, finding 6) This no-provider half is **ungrouped** (task 2.8): it is kept if C is cut.

  (Review 2026-09-28, finding 3) With `COPILOT_PROVIDER_BEARER_TOKEN`, `COPILOT_PROVIDER_WIRE_MODEL`,
  `COPILOT_PROVIDER_API_KEY_COMMAND` and `COPILOT_PROVIDER_HEADERS` set ambient, and separately in
  `config.env_vars`, the **provider** runner's environment contains none of them: its
  `COPILOT_PROVIDER_*` names are exactly `TYPE`, `BASE_URL` and `API_KEY`, plus `COPILOT_MODEL`.
  This fails on R3's "overwrite the four".

  (Finding 10) With `MY_ANTHROPIC_KEY` **unset**, building the provider runner's environment does
  not raise; it sets `TYPE`, `BASE_URL` and `COPILOT_MODEL` with `COPILOT_PROVIDER_API_KEY == ""`.
  `POST /agent/trigger` for such an agent answers the launchability refusal, never 500.

  (Finding 1) One-shot spawns. With `run_worker`'s and the titler's process spawn patched to
  capture `env` and `argv`:
  - a checkpoint generated on a provider checkpoint runner, a handover on it, and a title
    generated on it (project title runner) and on an agent's own provider runner (no title runner)
    each get exactly the provider's variables and `COPILOT_MODEL` equal to the runner's model;
  - with a stored `checkpoint_model` of `auto` (written directly, as one stored before the runner
    gained a provider), generation uses `runner.model`;
  - on a plain `copilot` checkpoint runner with ambient `COPILOT_PROVIDER_BASE_URL` set, the worker
    and titler environments carry no `COPILOT_PROVIDER_*` (ungrouped half, task 2.8).

  Launchability, **through the routes**, not only the adapter (design D7, R3 table of sites):
  - with the variable unset, `GET /runners/launchability` for the runner, and
    `GET /agents/launchability` for an agent bound to it, report not authorized, with a reason
    naming `MY_ANTHROPIC_KEY` and not mentioning GitHub;
  - with the variable set, both report authorized with no GitHub token in the environment and a
    `CopilotProbe` verdict of "not signed in" patched in, and (R3) `POST /agents` binding a new
    agent to the runner answers 201, not the create-time 409 (`agents.py:728-733`).

  Per-run model: `POST /agent/trigger` for an agent bound to the provider runner with
  `overrides: {"model": "auto"}` answers 400 with a stated reason, and no run is created and the
  conversation's `runtime_overrides` is unchanged. (R3) With `runtime_overrides = {"model":
  "auto"}` written directly on the agent's conversation (as one stored before the runner gained a
  provider would be), a triggered run's request carries `model == "claude-haiku-4-5-20251001"`.
  This fails on today's `agent_trigger.py:802`.
  **Per-run half done 2026-10-03 (night iter 4)** in `hub/tests/test_copilot_byok_env.py` (the
  stored model reaches the conversation through a real override on a plain runner, then a rebind,
  rather than a direct write). Environment, one-shot and launchability halves are task 3.3's.
  **Environment and launchability halves done 2026-10-03 (night iter 5)**, same file, 16 passed
  (6 fail at `1b2ef1a`): the four provider variables exactly, with the outranking names ambient
  and in `env_vars`; none on a plain runner from either source; a `provider_config` in
  session.json is not a provider (bound or unbound); the missing key builds `API_KEY == ""`; the
  routes' verdicts with the variable unset/set and Copilot "not signed in" patched, `POST /agents`
  201. One deviation: with the variable unset, `POST /agent/trigger` answers 200 `queued` with the
  sentence as `waiting_reason` (and no run), the route's launchability refusal for any agent, not a
  409. **One-shot half done 2026-10-03 (night iter 6)**, same file, **25 passed** (7 of the 9 new
  fail at `05cbc21`; the plain-runner control and the worker-gate test's accepted half hold there):
  the operator's checkpoint and its probe, a handover (`consider_handover` on `_flow_handover`'s
  rows), a title on the project's provider title runner and on an agent's own provider runner each
  get exactly the provider's four variables and `--model`/`COPILOT_MODEL` = the runner's model; a
  stored `checkpoint_model` of `auto` (written directly) is ignored at the route, the handover and
  `checkpoint_trigger._resolve_runner`, and left in place; a plain runner's worker and titler spawns
  carry no `COPILOT_PROVIDER_*` with the outranking names ambient. Added beyond the text: a damaged
  stored provider spawns no one-shot (worker `spawn_failed`, no title), and the worker refuses
  `auto` on a provider runner (`unknown_model`) while accepting the runner's Claude API id.
- [x] 1.9 (C) Same file (review fixes 2026-09-28, finding 2): a fake run on the provider runner, with
  the key registered for it as the trigger registers it, records the key value through a **text**
  event, a **thinking** event, an error event, a diagnostic, a `POST /agents/{name}/output` with its
  `run_id`, and a permission request whose subject quotes it (`{"command": "echo sk-ant-test-value"}`
  through `_await_operator_permission`), and ends with a failure text quoting it. The key value is
  then absent from:
  - the `GET /runners` response;
  - the rendered agent context file;
  - every `AgentOutput.content`/`payload` row, and every SSE broadcast of them (captured);
  - the `PermissionRequest.tool_input` row and its broadcast;
  - `Run.error`;
  - every error and diagnostic payload.

  Repeat with `MY_ANTHROPIC_KEY=plainproxykey123` (a key no `sk-`/`aw_live_` pattern matches, as on a
  localhost proxy). A tool result must not be the only carrier: this test fails on today's
  `text_event` (the F190 pattern). After the run is finalised the registry holds nothing for it.
  **Done 2026-10-03 (night iter 7)**, same file, both keys, with task 3.5: 2 red before 3.5
  (`seen["registered"] == ()`), green after (28 passed in the file). Added beyond the text: a
  refusal Copilot's own judge decided (`on_refusal`, its `permission_denied` event) and the
  `run_failed` lifecycle's `stderr_tail` as carriers; each carrier is asserted recorded as
  `<redacted>`, not dropped. The failed turn's input is retried, so the run is three runs; each was
  registered and forgotten. Plus `test_the_registry_scrubs_only_its_own_runs_values`.
- [x] 1.10 (C) Migration. `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`
  head assertions name the new revision, and `runners.provider_config` exists after upgrade from the
  previous head. These fail until the migration exists.
  **Done 2026-10-03 (night iter 3):** `HEAD_REVISION = "0118"` in both files; two tests
  (`test_migration_adds_runner_provider_config_and_keeps_an_existing_runner`, `..._downgrade_drops_...`)
  red before `0118` existed (3 failed + the persistence head), green after: 129 passed, 1 skipped
  over both files.
- [x] 1.11 (B) `hub/tests/test_review_turn_copilot_agents.py`, rendering through
  `_render_hub_agent_context` with a real `ReviewContext` (pattern:
  `test_review_turn.py::test_the_turn_context_says_this_is_a_review_and_names_the_task_and_commit`).
  Cases:
  - a `copilot` agent with `config.copilot_review_agents == ["code-review"]` gets the D8 bullet,
    naming `code-review`, `<base>` and the commit, and "recorded only by `update_task`";
  - the verdict line is byte-identical to the no-setting render;
  - the same agent on an ordinary turn gets no bullet;
  - a `claude` agent with the same config gets no bullet;
  - an empty list gets no bullet;
  - when `<base>` cannot be computed, the bullet names the commit alone, and
    `prepare_review_turn` does not refuse the turn. Cover: the project has no `main_branch`; it
    names a branch that does not exist; the commit is already on `main_branch` (merge base equals
    the commit). `<base>` is `git merge-base <commit> <Project.main_branch>` (design D8).
  - (R3) with the merge-base `_git` call patched to raise `subprocess.TimeoutExpired`,
    `prepare_review_turn` returns a context with `base_sha is None`, and the patched call happened
    **before** `worktrees.ensure_review_checkout` (assert call order), so a raise there could not
    leave a provisioned checkout unclaimed.
  **Done 2026-10-03 (night iter 9):** all cases pass. Red before 4.1/4.2 existed (15 of 16
  tests in the file failed; the 16th, the ordinary-turn case, passes either way). Two mutations
  run and caught (dropping the vocabulary filter on render; swapping the merge-base/checkout
  order) -- both failed the case they target.
- [x] 1.12 (B) Same file: `PATCH /agents/{name}` with `config.copilot_review_agents == ["research"]`,
  `["x"]` or the string `"code-review"` (review 2026-09-28, finding 14: not iterated as characters)
  is refused with a 400 sentence, and the stored config is unchanged. A value stored through
  `POST /agents/register` as `["code-review", "research"]` renders a bullet naming `code-review`
  only, and one stored as `"code-review"` renders no bullet.
  `["code-review", "security-review"]` is accepted, and `GET /agents` returns it in the agent's
  `config` (it is in `ROSTER_CONFIG_KEYS`; design D8).
  **Done 2026-10-03 (night iter 9):** `POST /agents/register` no longer exists
  (`agents-no-longer-register-themselves`); its stand-in for "a writer the PATCH check does not
  see" is the `add_agent` test fixture, which inserts the `Agent` row directly, exactly what that
  route's replacement note says to use. Both narrowing cases (an unknown vocabulary entry mixed
  with a valid one; a stored string instead of a list) pass against that fixture.
- [ ] 1.13 (D) `hub/tests/test_copilot_github_mcp_toggle.py`:
  - slice 2's `copilot_acp.build_acp_argv` contains `--disable-builtin-mcps` when
    `RpcTurnRequest.agent_config["copilot_github_mcp"]` is false or absent, and omits it when true;
    and (R3) the trigger fills `agent_config` from the agent's config (contract reconciliation,
    2026-09-28: slice 1's field name, not `github_mcp`);
  - slice 2's `copilot_acp.decide_permission` answers an MCP permission request naming server
    `github-mcp-server` (a `create_issue` with `owner`/`repo`/`title`) with `ASK_OPERATOR` under
    `workspace`, `REJECT` under `acceptEdits`, `ALLOW` under full access, and the operator under
    `manual`. **Fail-before evidence:** today's `_decide("mcp__github-mcp-server__create_issue",
    {...})` returns `allow` ("inside your workspace"); record that in the test's docstring;
  - (review 2026-09-28, finding 4) with the toggle on, a request whose reported server is
    `some-other-server` (identified from `tool.execution_start`'s `mcpServerName`, not only
    `permission.requested`) is also `ASK_OPERATOR` under `workspace`, its card label is
    `some-other-server/<tool> — a tool of MCP server some-other-server, not the Hub's` (no GitHub
    claim), and its `workspace_verdict` is `None`. With the toggle off it is decided by slice 2's
    foreign row as before;
  - (DECIDED 2026-09-28, finding 5) with the toggle on **and** off, a request whose MCP server
    Copilot did not report is `REJECT`ed by slice 2's identify step, under every posture, and never
    reaches this rule (no card);
  - (finding 14) `agent_config == {"copilot_github_mcp": "false"}` (a string) gives
    `--disable-builtin-mcps` in the argv and slice 2's rows unchanged; the trigger fills
    `agent_config` with the `copilot_github_mcp` key only, never `env_vars`;
  - the card opened for it has `tool_name` `github-mcp-server/create_issue — acts on GitHub as
    you`, and the Copilot `workspace_verdict` for it is `None`, under `workspace` and `manual`
    (R3: the card has no other place for the sentence; a two-valued verdict would say "allow");
  - a request for server `agentweave` under `workspace` is decided exactly as before;
  - a raw `session.mcp_servers_loaded` naming `github-mcp-server` as `failed` gives one
    `diagnostic` (`copilot.github_mcp_unavailable`) per turn with the toggle on, and none with it
    off; (R3) `pending` gives none. Use the status event and order task 1.1 run (c) captured; if it
    captured none, this case and the mapping are removed (design D9; operator-accepted
    2026-09-28), with the two spec scenarios on reporting a failed or starting server;
  - `GET /agents` returns `copilot_github_mcp` in the agent's `config`.
- [ ] 1.14 (C, B, D) UI tests.
  - `hub/ui/src/__tests__/runnerProviderConfig.test.tsx`: the Runners page shows provider fields only
    when the CLI is `copilot`. It shows the D7 sentence about API keys and Claude Max, and renders a
    refusal's own sentence beside the key field (served in the order `POST /runners` returns it).
    (Review 2026-09-28, finding 9) With a provider set, the model picker's options are exactly the
    served `claude` catalog's ids: no "Latest" alias group, no "Provider default", no Copilot model;
    turning the provider on, then off, clears the chosen model each time.
  - `hub/ui/src/__tests__/copilotAgentSettings.test.tsx`: the review-agents and GitHub-server
    controls appear only for a `copilot`-bound agent, and show the value in the served agent's
    `config` (a fixture with the setting on renders it on).
  - The composer offers no model choice for an agent bound to a provider runner, and shows the
    runner's model (design D7).

  Run `cd hub/ui && npx vitest run runnerProviderConfig copilotAgentSettings`.
  **Runner half done 2026-10-03 (night iter 8):** `runnerProviderConfig.test.tsx`, 10 passed (the
  first and third bullets; the composer case renders `NewConversationSurface`). Each of 12
  mutations of the code it covers fails a named case. `copilotAgentSettings.test.tsx` (B, D) is
  not written.

## 2. Group A — Copilot's lifecycle reaches the Hub

- [ ] 2.1 `hub/hub/runner_events.py` (design D4, D5):
  - `status_event` gains `facts`; `error_event` gains `facts` and redacts its `message` by value;
  - `diagnostic_event`: use slice 2's `diagnostic_event(*, stream, severity, summary, code=None,
    facts=None)` (its R3; contract reconciliation, 2026-09-28), with `summary=` and
    `stream="copilot"`. Nothing to add to it (design D5; *Required of slices 1–4*, 2.1);
  - facts: string values through the value rule only, numbers kept. Never `redact_secrets(facts)`
    whole.
- [ ] 2.2 Ensure the six types are in slice 2's raw-event subscription constant, as a set union
  (design D1: `session.error` is slice 2's and `session.compaction_complete` slice 4's already).
- [ ] 2.3 In slice 2's `copilot_acp.CopilotEventMapper`:
  - a root `session.compaction_complete` becomes `compacted` or a diagnostic; one with `agentId`
    becomes nothing; one with `dataOmitted: "too-large"` becomes `compacted` with counts from the
    turn's last root `session.compaction_start` (D4);
  - `session.error` becomes an error event (D5);
  - `subagent.*` become statuses (D6);
  - an `agent_message_chunk` whose text equals `"Error: " + message` of an unmatched
    `session.error` already received this turn, **root or subagent** (review 2026-09-28, finding 7),
    is dropped on arrival, before accumulation; nothing is held; slice 2's `Error:` →
    `copilot_session_error` branch is deleted (D5, R3);
  - "is a subagent's" is Copilot's `_d()` test: envelope `agentId`, else `data.agentId`, else
    `data.parentToolCallId` (D5).

  The mapper needs the whole `sessionEvent` params, `agentId` and `dataOmitted` included
  (*Required of slices 1–4*, 2.3).

  Pass tests 1.2 and 1.3.
- [ ] 2.4 `hub/hub/checkpoint_trigger.py`:
  - add `compacted: bool = False` to `consider`, with the branches of design D4's table;
  - add `consider_from_compaction(project_id, agent, conversation_id, payload)` with the
    `_in_flight` / `_dispatched` discipline, plus `_compaction_pending`: a compaction arriving
    while the conversation is in flight is re-dispatched from the running task's `finally` (D4),
    **including `consider_from_reading`'s `finally`** (R3: the in-flight task is usually a
    reading's);
  - it never raises into its caller.

  Pass test 1.4.
- [ ] 2.5 `hub/hub/output_recording.py::record_agent_output`: after persisting, dispatch
  `consider_from_compaction` for `kind == "status"` with `isinstance(payload, dict) and
  payload.get("phase") == "compacted"` (R3: `payload` may be `None`; local import, as at `:233`).
  Pass test 1.5.
- [ ] 2.6 Confirm slice 2's `COPILOT_HOME` writer and run environment
  (`resolve_agent_env`/`guard_env`) meet design D3. Change them only
  if test 1.6 fails. Pass test 1.6. (Review 2026-09-28, finding 6: the `COPILOT_ALLOW_ALL` strip is
  slice 2's, *Required* 2.9. If slice 2 landed without it, task 2.8 adds it.)
- [ ] 2.7 Run `py -3.11 -m pytest hub/tests/ -q -x` and `ruff check hub/` and
  `black --check --target-version py311 hub/hub/ hub/tests/`.
- [ ] 2.8 (**no group; never cut**; review 2026-09-28, finding 6) Confirm slice 2's Copilot
  `guard_env` and `one_shot_env` strip `COPILOT_ALLOW_ALL`, every `COPILOT_PROVIDER_*` name,
  `COPILOT_MODEL` and `COPILOT_OFFLINE` from both the ambient environment and `env_vars` for a spawn
  that names no provider (*Required* 2.9, 2.10). Add whatever is missing there: as the no-provider
  branch of `copilot_provider_env` if group C is kept, or as a plain strip if it is cut. Pass the
  ungrouped halves of tests 1.6 and 1.8.

## 3. Group C — BYOK on a Copilot runner

- [x] 3.1 Add the migration for `runners.provider_config` (nullable JSON), following
  `.claude/rules/db-migrations.md`: guard a missing table, and bump both head assertions. Add the
  column to `hub/hub/db/models.py::Runner`. Pass test 1.10. **Done 2026-10-03: `0118_runner_provider_config.py`.**
- [x] 3.2 `hub/hub/schemas/runners.py`: add a `ProviderConfig` model with the validation in design D7,
  and add it to the create, update and response schemas. `hub/hub/api/v1/runners.py`: add the
  checks as 400s with a string `detail` (CLI is `copilot`; `type` is `anthropic`; `api_key_var` is a
  name; model set; model a declared **id** of the literal `CATALOG["claude"]`, with its own
  sentence). `RunnerResponse._flag_unrecognised_model` uses the same provider rule for a provider
  runner. `agent_trigger.py:1618`: a `model` override on a provider runner is refused. (R3) The
  runner `PATCH` validates the resulting `(provider_config, model)` pair whenever
  `provider_config` is sent. (Review 2026-09-28) The create/update schemas type `provider_config`
  as `Optional[Dict[str, Any]]` and the route refuses unknown keys and non-string values with 400s
  naming the key only (finding 15); `base_url` by `urlsplit` hostname (finding 10); `api_key_var`
  not a Hub credential name (finding 15); no `--model` in a provider runner's `flags`, judged on the
  resulting pair on `PATCH` too (finding 11). `PATCH /projects`: a `checkpoint_model` failing the
  provider rule for a provider checkpoint runner is refused (finding 1).
  (R3) `agent_trigger.py:802`: a provider runner's model is `runner_row.model` whatever
  `conversation.runtime_overrides` holds. Pass test 1.7 and the per-run half of 1.8.
  **Partly done 2026-10-03 (night iter 3): everything except the two `agent_trigger.py` sites.**
  `hub/hub/runner_provider.py` holds the rules (sentences never repeat a submitted value);
  `RunnerCreate`/`RunnerUpdate.provider_config` are `Optional[Any]` (not `Dict`: a string there
  would 422 with the value echoed); `ProviderConfig` is the response's stored shape, read
  defensively; the runner routes and the settings route apply the checks. Test 1.7 passes.
  **Finished 2026-10-03 (night iter 4):** the trigger route refuses a per-run `model` override on a
  provider runner (400, `runner_provider.provider_override_problem`, checked before
  `validate_overrides`; nothing queued, no conversation stored), and the spawn's model resolution
  uses `runner_row.model` for a provider runner whatever `runtime_overrides` holds (the stored value
  is kept). 1.8's per-run half passes (`test_copilot_byok_env.py`, 5 passed; each site's removal
  fails a named test). Driven on a source Hub (`:8018`, profile `drive1003b`): both `auto` and
  `claude-haiku-4.5` refused with the sentence, 0 runs / 0 queue entries / 0 conversations after.
- [x] 3.3 Environment and launchability (design D7):
  - `provider_config` reaches `resolve_agent_env` through `config` (R3: no new parameter), and the
    Copilot `guard_env` (given `config`; *Required of slices 1–4*, 1.3) sets the provider
    environment from it, or strips the provider variables from both the ambient environment and
    the agent's `env_vars`;
  - the adapter's `launchability` authorizes on the key variable, taking only `present` and the
    version from slice 2's `CopilotProbe`;
  - one helper, `runner_probe_config(runner_row)`, builds `{runner, model, provider_config}`, used
    in `launchability.get_agent_config` (beside `:524-526`; serves `agents.py:234`,
    `inbound_queue.py:223` and the trigger), `agent_trigger.py:764-765`, `agents.py:728` and
    `runners.py:96-99` (R3: R2's `agents.py:552`/`:2004` are display code, not probes); it treats a
    non-dict `provider_config` as invalid, never raising (review 2026-09-28);
  - (review 2026-09-28, finding 3) `copilot_provider_env(env, provider_config)`: strip the whole
    `COPILOT_PROVIDER_` prefix, `COPILOT_MODEL`, `COPILOT_OFFLINE` from the merged environment, then
    set exactly `TYPE`, `BASE_URL`, `API_KEY` (`os.environ.get(..., "")`, finding 10) and
    `COPILOT_MODEL`; the Copilot `guard_env` and `one_shot_env` both call it;
  - (finding 1) the one-shot spawns: `one_shot_env` receives the runner's `config` (slice 1,
    *Required* 1.7), read from the row `run_worker(runner_id=…)` and the titler already hold;
    `one_shot_model(runner, checkpoint_model)` replaces `project.checkpoint_model or runner.model`
    at `checkpoint_trigger.py:153`, `checkpoint_handover.py:188` and `api/v1/checkpoints.py:183`.

  Pass test 1.8.
  **Split in two (2026-10-03 night): runs first, then one-shots.** **First slice done (night iter
  5):** `runner_provider.copilot_provider_env(env, provider_config, model)` (whole-prefix strip,
  then exactly `TYPE`/`BASE_URL`/`API_KEY` via `os.environ.get(..., "")` and `COPILOT_MODEL`;
  `model` is a parameter because the function sees no runner row), called by the Copilot
  `guard_env`; the adapter's `launchability` authorizes a provider runner on its key variable
  (`runner_provider.provider_launch_verdict`: the probe supplies `present` and `version` only; a
  damaged stored value is reported, not raised on); `runner_probe_config(runner_row)` at all four
  sites (`get_agent_config`, which also drops a `provider_config` from the agent's own config or
  session.json; the trigger; `POST /agents`; `GET /runners/launchability`). **Left (second
  slice):** `one_shot_env` given the runner's `config` at the worker and titler spawns,
  `one_shot_model` at the three checkpoint/handover/title sites, and 1.8's one-shot half.
  **Second slice done (night iter 6):** `worker.one_shot_env(cli, config)`; `run_worker` reads
  its runner's row by `runner_id` in a session of its own, closed before the spawn, and passes
  `{**runner_probe_config(row), "model": model}`; the titler passes `runner_probe_config(runner)`;
  `copilot_one_shot_env(config)` ends in `copilot_provider_env`; `runner_provider.one_shot_model`
  at the three sites. **Deviation, needed for the plumbing to fire at all:** `run_worker`'s
  `model_is_declared` gate checked the `copilot` catalog, which declares no Claude API id, so every
  provider-runner checkpoint would have been refused `unknown_model` before its spawn. A provider
  runner's model is now judged by the provider rule there (as `runners.py` judges it), and a
  damaged stored provider is refused (`spawn_failed`; the titler skips) rather than run on the
  GitHub subscription, since no launchability check precedes a one-shot. Driven on a source Hub
  (port 8020, a local fake provider): the checkpoint one-shot's requests reached the provider with
  the key in `x-api-key` and the runner's model.
- [x] 3.4 The Runners page (`hub/ui/src/components/runners/RunnersPage.tsx`):
  - provider fields for `copilot` (type select, base URL, key variable name);
  - the API-key/Claude Max sentence;
  - the refusal shown beside the field;
  - the composer's model control, hidden for an agent on a provider runner in favour of the runner's
    model;
  - (review 2026-09-28, finding 9) with a provider set, the model picker lists `claude` catalog ids
    only (no alias group, no "Provider default"), and toggling the provider resets the model.

  Pass the runner half of test 1.14. Then run `cd hub/ui && npm run lint && npx vitest run`, then
  `npm run build` and `py -3.11 scripts/refresh_ui_bundle.py`. Commit `hub/ui/src` and
  `hub/hub/static/ui` together.
  **Done 2026-10-03 (night iter 8).** `RunnersPage.tsx`: for a `copilot` runner, a "Send runs to a
  model provider" checkbox revealing Provider (Anthropic only), Base URL and Key variable name, the
  D7 sentence under the key field, and the Hub's refusal rendered there (else at the foot as
  before). With a provider the model list is the served `claude` catalog's ids behind a disabled
  placeholder; each toggle clears the model; edit sends `provider_config` (or `null`) for a Copilot
  runner. The composer (`ComposerModelControls`, via `runnerSetsModel` in `lib/runnerProvider.ts`)
  shows the runner's model as a static pill. **Beyond the task's words:** both composer callers
  drop a stored `model` override for a provider runner (`overridesForRunner`), since the trigger
  refuses it 400 and a conversation seeded before the rebind carries one (driven: 400 by API with
  it, 200 from the composer without it). `npm run lint` clean, `npx vitest run` 1843 passed.
  Driven in Chromium against the served bundle on a source Hub (port 8022).
- [x] 3.5 (C; review 2026-09-28, finding 2) The per-run exact-value scrub: a `run_secrets` registry
  (in-process, never persisted), registered by the trigger with the resolved
  `COPILOT_PROVIDER_API_KEY` before the spawn and forgotten when the run is finalised; applied in
  `record_agent_output` to `content` and every string in `payload` before storing and broadcasting,
  in `_await_operator_permission` to `tool_input` before storing and broadcasting, and to
  `Run.error`. The trigger fills `RpcTurnRequest.agent_config` with only `copilot_github_mcp`
  (finding 14). Pass test 1.9.
  **Done 2026-10-03 (night iter 7):** `hub/hub/run_secrets.py` (`register`/`forget`/`registered`/
  `scrub`; dict keys and values, lists, tuples). Registered from the run's built `env` just before
  `asyncio.create_task(_execute_run(...))`; forgotten by that task's done callback, so every end
  (completed, failed, raised, cancelled) forgets. Scrubbed: `record_agent_output` (`content`,
  `payload`); the card's `tool_input`, `tool_name` and `workspace_verdict`, and its broadcast;
  `Run.error` at all four sites that store a foreign string; `_broadcast_run_lifecycle`'s payload
  (its event row and SSE); the runtime refusal's `permission_denied` event and broadcast.
  `RpcTurnRequest.agent_config: Mapping = field(default_factory=dict)`, filled through
  `_CopilotTurn` with `{"copilot_github_mcp": config.get("copilot_github_mcp") is True}`; nothing
  reads it until group D. Eleven mutations (each site, register, forget, `agent_config`) each fail
  test 1.9. **Driven** (port 8021, real Copilot CLI, a local fake Anthropic provider, key
  `plaindrivekey77731`): the `powershell` call, its output, the reply and a `manual`-posture card
  were recorded with `<redacted>`; the key appeared in 0 rows, events, runs, routes and Hub log lines.

## 4. Group B — Copilot review agents on review turns

- [x] 4.1 `hub/hub/review_turn.py::prepare_review_turn`: read `Project.main_branch`, compute
  `git merge-base <commit> <main_branch>` (no helper exists; follow `task_integration._git`), and
  carry it as `ReviewContext.base_sha`, `None` on any failure or when it equals the commit. Never
  raise for it: catch `(subprocess.SubprocessError, OSError)`, and compute it **before**
  `ensure_review_checkout` (R3, design D8).
  **Done 2026-10-03 (night iter 9):** `review_turn._git` (module-level, `**no_console_kwargs()`,
  matching `test_no_console_flash.py`'s static check) and `_merge_base_sha`, called from
  `prepare_review_turn` after `is_git_repo`/`seed_repo_excludes` and before
  `ensure_review_checkout`. `ReviewContext.base_sha: Optional[str] = None` added.
- [x] 4.2 `hub/hub/api/v1/agents.py`, the review section of `_render_hub_agent_context`: add the D8
  bullet after the verdict line, under the D8 conditions. Validate `copilot_review_agents` in the
  agent PATCH route before the merge: a list first, then the vocabulary (review 2026-09-28,
  finding 14); the renderer filters the stored value to the vocabulary and ignores a non-list. Add it to `ROSTER_CONFIG_KEYS` (`agents.py:651`) and update
  any test that pins that tuple. Pass tests 1.11 and 1.12.
  **Done 2026-10-03 (night iter 9):** `COPILOT_REVIEW_AGENTS` vocabulary tuple,
  `_validated_copilot_review_agents` wired into `PATCH /agents/{name}` before the merge, the D8
  bullet inserted between the verdict line and the evidence-gate sentence, gated on
  `runner == "copilot"` and a non-empty filtered list. `copilot_review_agents` added to
  `ROSTER_CONFIG_KEYS`; no existing test pinned that tuple literally, so none needed updating.
  Tests 1.11 and 1.12 pass (16/16); CLI suite and the F392 regression union (135 tests across
  `test_review_turn*`, `test_agent_tool_surface*`, `test_a_request_means_what_it_says.py`,
  `test_request_agent_models_an_existing_agent.py`, `test_no_console_flash.py`) all pass. `ruff`,
  `black --check --target-version py311`, `mypy src/` clean.
- [ ] 4.3 Agent Settings UI: add a review-agents control shown only for `copilot` agents; its help
  text says that on a provider runner Copilot's review agents may not run (review 2026-09-28,
  finding 13). Pass its part of test 1.14. Run lint, vitest, build and bundle refresh as in 3.4.

## 5. Group D — the GitHub MCP server toggle

- [ ] 5.1 `RpcTurnRequest.agent_config: Mapping = {}` (slice 1's D16 name; contract reconciliation,
  2026-09-28), filled by the trigger from the agent's config. `copilot_acp.run_turn` passes
  `agent_config.get("copilot_github_mcp", False)` as `github_mcp`. Slice 2's
  `copilot_acp.build_acp_argv` gains `github_mcp: bool = False`: omit `--disable-builtin-mcps` when
  it is true. Slice 2's `copilot_acp.decide_permission` gains
  `github_mcp: bool = False`: with the toggle on, every request whose **reported** server is not
  `agentweave` is decided as design D9 says, before `_decide` (review 2026-09-28, finding 4); a
  request with no reported server is slice 2's identify-step REJECT and never reaches the rule
  (DECIDED, finding 5). `run_turn` reads `agent_config.get("copilot_github_mcp") is True`
  (finding 14). The Copilot `permission_card_label` gives D9's label, built from the reported
  server name, and the Copilot `workspace_verdict` returns `None` for such a request (R3).
  `CopilotEventMapper`: the unavailable-server diagnostic for `failed`, `needs-auth`, `disabled`,
  `stopped`, `not_configured` only, if task 1.1 showed the event arrives (if not, delete it from
  `specs/agent-configuration/spec.md` too: the requirement's paragraph on an unavailable server and
  its two scenarios; operator-accepted 2026-09-28). Add `copilot_github_mcp`
  to `ROSTER_CONFIG_KEYS`. `mcp_server.py` is not touched. Pass test 1.13.
- [ ] 5.2 Agent Settings UI: add a GitHub-server toggle shown only for `copilot` agents; its help
  text says that while it is on every non-Hub MCP call under Workspace only is asked, and that a
  runner's pre-approval flags (`--allow-tool`, `--allow-all-tools`) bypass the card (review
  2026-09-28, finding 11). Pass its part of test 1.14. Run lint, vitest, build and bundle refresh as in 3.4.

## 6. Full suite

- [ ] 6.1 Run exactly what CI runs:
  - `ruff check src/ hub/ tests/`
  - `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`
  - `mypy src/`
  - `py -3.11 -m pytest tests/ -q`
  - `py -3.11 -m pytest hub/tests/ -q`
  - `cd hub/ui && npm run lint && npx vitest run`

  All green.

## 7. Drive

Drive on the trial Hub `:8010` only. Start it from `hub/`, from source, with `DATABASE_URL` naming
the trial profile (`.claude/reference/hubs.md`), and confirm which database it serves before
trusting it. **Never touch `:8000`.**

Use a Copilot agent on the **Copilot Free plan: Auto model only, with a small monthly allowance.**
Keep turns few and tiny. Before and after the section, record the allowance with the `/usage` slash
prompt, which makes no model call. The budget for this whole section is 12 Free model calls. Record
every run id, and paste each surface's text verbatim into the Round log.

- [ ] 7.1 (A) Create a Copilot agent `cp5` on `:8010` and set its checkpoint mode to `offered`. Run
  one turn: `Use the explore agent to name one file here, then stop.` The run's timeline shows a
  `subagent_started` and a `subagent_completed` sharing the `task` call's id.
- [ ] 7.2 (A) **The compaction backstop.**
  - R2 answered the condition: slice 2's D5 sends a per-turn context block ahead of every message,
    so a `/compact` message never reaches Copilot as a bare prompt. So a one-off script in
    `testbed/` maps the captured `compaction.jsonl` with the Copilot mapper **in the script**, then
    `POST`s the resulting event to `POST /agents/cp5/output` on `:8010` (`kind: "status"`, the
    mapped payload, `cp5`'s real `run_id`/`session_id`), with the trial project's operator key.
    (Review 2026-09-28, finding 12: calling `record_agent_output` in the script's own process would
    run the consideration there, where it finds no loop or broadcasts to nobody; the POST makes the
    trial Hub's own process dispatch it.)
  - The timeline shows the `compacted` card with its token counts, and the conversation shows the
    (unchanged) checkpoint-due banner. No checkpoint row is created. Paste both texts verbatim.
- [ ] 7.3 (A) Error once. Give `cp5` an invalid provider key through a group C runner whose key
  variable holds `invalid`. Run one turn. (Review 2026-09-28, finding 6: the old "if C was cut,
  ambient `COPILOT_PROVIDER_*`" fallback relied on exactly the hole task 2.8 closes, so it no longer
  works. If C was cut, replay the captured `error.jsonl` as 7.2 does, mapping in the script and
  `POST`ing each resulting event, and record that the live echo drop was not driven.) The timeline shows exactly **one** error event
  `copilot.authentication` (or whatever `errorType` 1.1 recorded), still visible with diagnostics
  hidden, and no duplicate `Error:` text. This spends no Copilot allowance.
- [ ] 7.4 (A) `dir <cp5's COPILOT_HOME>\hooks` holds no deciding hook, and the home's config names
  no trusted folder. (R2: `Run` records no environment, so the `COPILOT_ALLOW_ALL` half is test
  1.6's.)
- [ ] 7.5 (C) On the Runners page, create a Copilot provider runner:
  - with the key field set to `sk-ant-not-a-name`. It is refused; record the sentence verbatim;
  - with `MY_ANTHROPIC_KEY` unset. The agent's launchability reason names the variable.

  Then grep the trial database file (read-only, `mode=ro`) for `sk-ant-not-a-name`. There must be no
  match.
  *Pre-driven 2026-10-03 night iter 8 on a source drive Hub (:8022), not :8010, so still open:* the
  pasted value was refused 400 beside the key field with `api_key_var must be the name of an
  environment variable (capital letters, digits and underscores, such as MY_ANTHROPIC_KEY), not the
  key itself. Put the key in the Hub's environment and name that variable here.`; the runner on
  unset `MY_ANTHROPIC_KEY` was created, and creating an agent on it was refused 409 naming
  `$MY_ANTHROPIC_KEY`; 0 matches in the database file, any column, and the Hub log.
- [ ] 7.6 (C, **operator key only**) **Preconditions (operator decision 2026-09-28, design D7 and
  Open question 8), all required before the key is set:**
  - the fixes for review findings 2 (the exact-value scrub, task 3.5), 3 (the whole-prefix strip,
    task 3.3) and 10 (the `urlsplit` address check, task 3.2, and the `os.environ.get` key read,
    task 3.3) are built, and tests 1.7, 1.8 and 1.9 are green;
  - the key is a **dedicated Anthropic workspace key** with a **hard monthly spend limit of a few
    dollars**;
  - it is set **only in the trial Hub's launch environment** (the shell that starts `:8010`), not in
    the user-wide environment, so the `:8000` Hub cannot see it;
  - it is **revoked after this task**; record that it was.

  The key is readable by the agent's shell commands and the Hub's tool server (accepted by the
  operator, design D7). With the preconditions met and the operator's key in place, run one turn on
  `claude-haiku-4-5-20251001` through the provider runner: `Reply with the single word ok.` It
  completes, and its usage is in tokens. Otherwise record "not driven: no key" (or which
  precondition is unmet), and leave this task unchecked for the operator. Then grep the trial
  database (`mode=ro`) for the key's value: no match. If group B is kept, add one turn asking `cp5` to use the `explore`
  agent and record the `model` its `subagent_completed`/`subagent_failed` reports (finding 13).
- [ ] 7.7 (B) Give a task completed by another agent evidence at a real commit. Set
  `cp5.copilot_review_agents = ["code-review"]` and fire a review turn at `cp5` through a flow.
  - The context file contains the D8 bullet with `<base>..<commit>`.
  - The timeline shows a `code-review` subagent. Record whether it reviewed the named range
    (open question 7).
  - The task ends `approved` or `revision_needed`, set by `cp5`'s `update_task`.

  This costs about 3 to 6 calls. If the allowance is under 10 calls, stop before this task and
  record why.
- [ ] 7.8 (D) With `copilot_github_mcp` false, the live `copilot.exe`'s command line contains
  `--disable-builtin-mcps` (R2: `Run` records no argv; read it while the run is live with
  `Get-CimInstance Win32_Process -Filter "ProcessId=<Run.pid>"`, or its child's). With it true, run one turn: `List one open issue in this repository
  using the GitHub tools.` An ask-me card appears for the `github-mcp-server` call, labelled
  `… — acts on GitHub as you`, with no "Workspace only would …" line (R3). Deny it and record the
  card text.

## 8. Archive

- [ ] 8.1 Every kept group's tasks are checked, and every cut group's spec delta is deleted.
  `openspec validate a-copilot-agent-uses-hooks-and-its-own-agents --strict` passes.
- [ ] 8.2 Sync the kept deltas into `openspec/specs/` (`openspec-sync-specs`) and archive the change
  (`openspec-archive-change`). Commit the specs, the change and the code with explicit paths, and
  push. Do not open a PR.
