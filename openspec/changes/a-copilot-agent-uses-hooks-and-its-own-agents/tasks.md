## Before you start

Build only after slices 1–4 (`each-runner-cli-is-one-adapter`, `a-copilot-agent-runs-over-acp`,
`a-run-reaches-the-hub-without-mcp`, `a-copilot-run-shows-its-credits`) and the 2026-09-27 night
queue have landed. **At R2 (2026-09-28, master `ef55e6f`) none of slices 1–4 and only 5 of the
night's 28 changes had landed; R3 (master `fc33ff9`) found the same.** Before starting, re-read
design.md's *Required of slices 1–4* against the slices as built, and fix every "(rebase at IMPL)"
site first. "Fails on today's code" below means **it fails on master after those land and
before this change**.

The four groups are A, C, B and D, in order of value. Each one can be cut. If the operator REJECTED
a group, skip every task tagged with it, and delete its spec delta before archiving:

| Group | Spec delta |
|---|---|
| A | `agent-stream-events`, `conversation-checkpoint`, `agent-run-sandboxing` |
| C | `runner-registry` |
| B | `agent-flows` |
| D | `agent-configuration` |

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
- [ ] 0.3 Opus adversarial review of the change and of the three operator questions in design "Open
  questions" 8: hooks wanted (D2), Azure deferred (D7), an API key for the BYOK drive (D7). Record
  it in `spec-queue/tracks/reviews/`. Apply the fixes before any APPROVED row.

## 1. Tests first — each fails on today's code

- [ ] 1.1 (A, C) **Capture real Copilot events before writing fixtures**, so that every
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
    diagnostic is removed).
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

  If a type is **not** delivered, stop group A. Tell the operator that D1's source does not hold and
  that D2's hook transport is the fallback.
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

  This is a guard: it fails today only because the writer does not exist yet. Say so in the
  docstring.
- [ ] 1.7 (C) `hub/tests/test_runner_provider_config.py`, through `POST /runners` and
  `PATCH /runners/{id}`:
  - a `copilot` runner with `{type:"anthropic", api_key_var:"MY_ANTHROPIC_KEY"}` and model
    `claude-haiku-4-5-20251001` is created and returned with `api_key_var`, **no** key, and
    `model_unrecognised: false`;
  - `api_key_var: "sk-ant-api03-xyz"` is refused with **400** and the sentence in design D7 as a
    string `detail`, and the table is unchanged. Count the rows before and after;
  - a `claude` runner with `provider_config` is refused;
  - `type:"azure"` and `type:"openai"` are refused (design D7: both deferred);
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

  Run `py -3.11 -m pytest hub/tests/test_runner_provider_config.py -v`.
- [ ] 1.8 (C) `hub/tests/test_copilot_byok_env.py`: with `monkeypatch.setenv("MY_ANTHROPIC_KEY",
  "sk-ant-test-value")`, the run environment built for the provider runner (`resolve_agent_env`
  with the runner's `provider_config`, as the trigger calls it; design D7) has
  `COPILOT_PROVIDER_TYPE=anthropic`, `COPILOT_PROVIDER_BASE_URL=https://api.anthropic.com`,
  `COPILOT_PROVIDER_API_KEY=sk-ant-test-value` and `COPILOT_MODEL=claude-haiku-4-5-20251001`. (R2:
  no assertion about the MCP config's `env`. Slice 2 writes none and the tool server inherits the
  environment, so such an assertion would pass while the key reached the tool server.)

  With `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_TYPE`, `COPILOT_MODEL` and `COPILOT_OFFLINE`
  set in the Hub's own environment, a `copilot` runner **without** `provider_config` gets none of
  them. (R3) The same holds when they are set in the agent's `config.env_vars` instead; this fails
  on a copy of the Claude guard's `env_vars` exemption (`launchability.py:190`).

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
- [ ] 1.9 (C) Same file: after one fake run records an event whose text contains the key value, the
  key value (`sk-ant-test-value`) is absent from:
  - the `GET /runners` response;
  - the rendered agent context file;
  - every `AgentOutput.content`/`payload` row;
  - every error and diagnostic payload.
- [ ] 1.10 (C) Migration. `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`
  head assertions name the new revision, and `runners.provider_config` exists after upgrade from the
  previous head. These fail until the migration exists.
- [ ] 1.11 (B) `hub/tests/test_review_turn_copilot_agents.py`, rendering through
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
- [ ] 1.12 (B) Same file: `PATCH /agents/{name}` with `config.copilot_review_agents == ["research"]`
  or `["x"]` is refused with a 400 sentence, and the stored config is unchanged.
  `["code-review", "security-review"]` is accepted, and `GET /agents` returns it in the agent's
  `config` (it is in `ROSTER_CONFIG_KEYS`; design D8).
- [ ] 1.13 (D) `hub/tests/test_copilot_github_mcp_toggle.py`:
  - slice 2's `copilot_acp.build_acp_argv` contains `--disable-builtin-mcps` when
    `RpcTurnRequest.github_mcp` is false, and omits it when true; and (R3) the trigger sets that
    field from `config.copilot_github_mcp` (absent → false);
  - slice 2's `copilot_acp.decide_permission` answers an MCP permission request naming server
    `github-mcp-server` (a `create_issue` with `owner`/`repo`/`title`) with `ASK_OPERATOR` under
    `workspace`, `REJECT` under `acceptEdits`, `ALLOW` under full access, and the operator under
    `manual`. **Fail-before evidence:** today's `_decide("mcp__github-mcp-server__create_issue",
    {...})` returns `allow` ("inside your workspace"); record that in the test's docstring;
  - with the toggle on, a request whose MCP server cannot be identified is also `ASK_OPERATOR` under
    `workspace`;
  - the card opened for it has `tool_name` `github-mcp-server/create_issue — acts on GitHub as
    you`, and the Copilot `workspace_verdict` for it is `None`, under `workspace` and `manual`
    (R3: the card has no other place for the sentence; a two-valued verdict would say "allow");
  - a request for server `agentweave` under `workspace` is decided exactly as before;
  - a raw `session.mcp_servers_loaded` naming `github-mcp-server` as `failed` gives one
    `diagnostic` (`copilot.github_mcp_unavailable`) per turn with the toggle on, and none with it
    off; (R3) `pending` gives none. Use the status event and order task 1.1 run (c) captured; if it
    captured none, this case and the mapping are removed (design D9);
  - `GET /agents` returns `copilot_github_mcp` in the agent's `config`.
- [ ] 1.14 (C, B, D) UI tests.
  - `hub/ui/src/__tests__/runnerProviderConfig.test.tsx`: the Runners page shows provider fields only
    when the CLI is `copilot`. It shows the D7 sentence about API keys and Claude Max, and renders a
    refusal's own sentence beside the key field (served in the order `POST /runners` returns it).
  - `hub/ui/src/__tests__/copilotAgentSettings.test.tsx`: the review-agents and GitHub-server
    controls appear only for a `copilot`-bound agent, and show the value in the served agent's
    `config` (a fixture with the setting on renders it on).
  - The composer offers no model choice for an agent bound to a provider runner, and shows the
    runner's model (design D7).

  Run `cd hub/ui && npx vitest run runnerProviderConfig copilotAgentSettings`.

## 2. Group A — Copilot's lifecycle reaches the Hub

- [ ] 2.1 `hub/hub/runner_events.py` (design D4, D5):
  - `status_event` gains `facts`; `error_event` gains `facts` and redacts its `message` by value;
  - `diagnostic_event`: use slice 2's `diagnostic_event(*, code, message, severity, facts)` (R3). If
    it has no `stream` keyword, add one with a default and write it into the payload (design D5;
    *Required of slices 1–4*, 2.1);
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
  - an `agent_message_chunk` whose text equals `"Error: " + message` of an unmatched root
    `session.error` already received this turn is dropped on arrival, before accumulation; nothing
    is held; slice 2's `Error:` → `copilot_session_error` branch is deleted (D5, R3).

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
  if test 1.6 fails. Pass test 1.6.
- [ ] 2.7 Run `py -3.11 -m pytest hub/tests/ -q -x` and `ruff check hub/` and
  `black --check --target-version py311 hub/hub/ hub/tests/`.

## 3. Group C — BYOK on a Copilot runner

- [ ] 3.1 Add the migration for `runners.provider_config` (nullable JSON), following
  `.claude/rules/db-migrations.md`: guard a missing table, and bump both head assertions. Add the
  column to `hub/hub/db/models.py::Runner`. Pass test 1.10.
- [ ] 3.2 `hub/hub/schemas/runners.py`: add a `ProviderConfig` model with the validation in design D7,
  and add it to the create, update and response schemas. `hub/hub/api/v1/runners.py`: add the
  checks as 400s with a string `detail` (CLI is `copilot`; `type` is `anthropic`; `api_key_var` is a
  name; model set; model a declared **id** of the literal `CATALOG["claude"]`, with its own
  sentence). `RunnerResponse._flag_unrecognised_model` uses the same provider rule for a provider
  runner. `agent_trigger.py:1618`: a `model` override on a provider runner is refused. (R3) The
  runner `PATCH` validates the resulting `(provider_config, model)` pair whenever
  `provider_config` is sent; `ProviderConfig`'s fields carry no Pydantic constraint.
  (R3) `agent_trigger.py:802`: a provider runner's model is `runner_row.model` whatever
  `conversation.runtime_overrides` holds. Pass test 1.7 and the per-run half of 1.8.
- [ ] 3.3 Environment and launchability (design D7):
  - `provider_config` reaches `resolve_agent_env` through `config` (R3: no new parameter), and the
    Copilot `guard_env` (given `config`; *Required of slices 1–4*, 1.3) sets the provider
    environment from it, or strips the provider variables from both the ambient environment and
    the agent's `env_vars`;
  - the adapter's `launchability` authorizes on the key variable, taking only `present` and the
    version from slice 2's `CopilotProbe`;
  - one helper, `runner_probe_config(runner_row)`, builds `{runner, model, provider_config}`, used
    in `launchability.get_agent_config` (beside `:524-526`; serves `agents.py:234`,
    `inbound_queue.py:223` and the trigger), `agent_trigger.py:764-765`, `agents.py:728` and
    `runners.py:96-99` (R3: R2's `agents.py:552`/`:2004` are display code, not probes).

  Pass tests 1.8 and 1.9.
- [ ] 3.4 The Runners page (`hub/ui/src/components/runners/RunnersPage.tsx`):
  - provider fields for `copilot` (type select, base URL, key variable name);
  - the API-key/Claude Max sentence;
  - the refusal shown beside the field;
  - the composer's model control, hidden for an agent on a provider runner in favour of the runner's
    model.

  Pass the runner half of test 1.14. Then run `cd hub/ui && npm run lint && npx vitest run`, then
  `npm run build` and `py -3.11 scripts/refresh_ui_bundle.py`. Commit `hub/ui/src` and
  `hub/hub/static/ui` together.

## 4. Group B — Copilot review agents on review turns

- [ ] 4.1 `hub/hub/review_turn.py::prepare_review_turn`: read `Project.main_branch`, compute
  `git merge-base <commit> <main_branch>` (no helper exists; follow `task_integration._git`), and
  carry it as `ReviewContext.base_sha`, `None` on any failure or when it equals the commit. Never
  raise for it: catch `(subprocess.SubprocessError, OSError)`, and compute it **before**
  `ensure_review_checkout` (R3, design D8).
- [ ] 4.2 `hub/hub/api/v1/agents.py`, the review section of `_render_hub_agent_context`: add the D8
  bullet after the verdict line, under the D8 conditions. Validate `copilot_review_agents` in the
  agent PATCH route before the merge. Add it to `ROSTER_CONFIG_KEYS` (`agents.py:651`) and update
  any test that pins that tuple. Pass tests 1.11 and 1.12.
- [ ] 4.3 Agent Settings UI: add a review-agents control shown only for `copilot` agents. Pass its
  part of test 1.14. Run lint, vitest, build and bundle refresh as in 3.4.

## 5. Group D — the GitHub MCP server toggle

- [ ] 5.1 `RpcTurnRequest.github_mcp: bool = False` (if slice 1 has not added it), set by the
  trigger from `config.copilot_github_mcp`. Slice 2's `copilot_acp.build_acp_argv`: omit
  `--disable-builtin-mcps` when it is true. Slice 2's `copilot_acp.decide_permission` gains
  `github_mcp: bool = False`: `github-mcp-server` (and, with the toggle on, unidentified) requests
  are decided as design D9 says, before `_decide`. The Copilot `permission_card_label` gives D9's
  label, and the Copilot `workspace_verdict` returns `None` for such a request (R3).
  `CopilotEventMapper`: the unavailable-server diagnostic for `failed`, `needs-auth`, `disabled`,
  `stopped`, `not_configured` only, if task 1.1 showed the event arrives. Add `copilot_github_mcp`
  to `ROSTER_CONFIG_KEYS`. `mcp_server.py` is not touched. Pass test 1.13.
- [ ] 5.2 Agent Settings UI: add a GitHub-server toggle shown only for `copilot` agents. Pass its
  part of test 1.14. Run lint, vitest, build and bundle refresh as in 3.4.

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
    so a `/compact` message never reaches Copilot as a bare prompt. So: POST the captured
    `compaction.jsonl` event through the Copilot mapper into `record_agent_output` for `cp5`'s real
    conversation on `:8010`, using a one-off script in `testbed/`.
  - The timeline shows the `compacted` card with its token counts, and the conversation shows the
    (unchanged) checkpoint-due banner. No checkpoint row is created. Paste both texts verbatim.
- [ ] 7.3 (A) Error once. Give `cp5` an invalid provider key: through a group C runner whose key
  variable holds `invalid`, or, if C was cut, through ambient `COPILOT_PROVIDER_*` in the trial Hub's
  own environment. Run one turn. The timeline shows exactly **one** error event
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
- [ ] 7.6 (C, **operator key only**) If the operator has put a real Anthropic API key in the trial
  Hub's environment (design open question 8), run one turn on `claude-haiku-4-5-20251001` through
  the provider runner: `Reply with the single word ok.` It completes, and its usage is in tokens.
  Otherwise record "not driven: no key", and leave this task unchecked for the operator.
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
