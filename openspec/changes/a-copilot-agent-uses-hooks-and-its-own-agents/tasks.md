## Before you start

Build only after slices 1–4 (`each-runner-cli-is-one-adapter`, `a-copilot-agent-runs-over-acp`,
`a-run-reaches-the-hub-without-mcp`, `a-copilot-run-shows-its-credits`) and the 2026-09-27 night
queue have landed. "Fails on today's code" below means **it fails on master after those land and
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

- [ ] 0.1 R2: re-derive independently. Compare every claim in `design.md` against the code as it
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
- [ ] 0.2 R3: a second independent re-derivation, not a re-read of R2. Re-derive D1 by re-reading
  `schemas/session-events.schema.json` in the installed Copilot package: does the raw event still
  supersede the hook for each fact? Re-derive D4's table row by row against `checkpoint_trigger.py`
  as it then stands. Ask what each changed route *returns* when the function it calls raises. The
  routes are `PATCH /agents/{name}` with a bad `copilot_review_agents`, `POST /runners` with a bad
  `provider_config`, and `record_agent_output` when `consider_from_compaction` cannot find the
  conversation. `openspec validate a-copilot-agent-uses-hooks-and-its-own-agents --strict` passes.
- [ ] 0.3 Opus adversarial review of the change and of the three operator questions in design "Open
  questions" 8: hooks wanted (D2), Azure deferred (D7), an API key for the BYOK drive (D7). Record
  it in `spec-queue/tracks/reviews/`. Apply the fixes before any APPROVED row.

## 1. Tests first — each fails on today's code

- [ ] 1.1 (A, C) **Capture real Copilot events before writing fixtures**, so that every
  test uses the order Copilot actually emits.
  - **Harness.** Adapt `acp_probe.py` into `testbed/copilot-capture/capture.py`. It uses a scratch
    `COPILOT_HOME` and a scratch cwd under `%TEMP%`, and spawns
    `%APPDATA%\npm\node_modules\@github\copilot\node_modules\@github\copilot-win32-x64\copilot.exe --acp --no-auto-update --disable-builtin-mcps`.
    Its `initialize` subscribes the six types in design D1, plus `assistant.usage`.
  - **Run (a):** prompt `Reply with the single word ok.`, then the prompt `/compact`. That is 2 Free
    model calls.
  - **Run (b):** prompt `Use the explore agent to name one file in this directory, then stop.` That
    is about 3 calls.
  - **Run (c):** BYOK with a deliberately invalid key: `COPILOT_PROVIDER_TYPE=anthropic`,
    `COPILOT_PROVIDER_BASE_URL=https://api.anthropic.com`, `COPILOT_PROVIDER_API_KEY=invalid`,
    `COPILOT_MODEL=claude-haiku-4-5-20251001`, then prompt `ok`. This spends no Copilot allowance,
    and Anthropic answers 401.
  - **Save** each transcript's `github.com/copilot/sessionEvent` notifications and `session/update`
    notifications, **in arrival order**, as `hub/tests/fixtures/copilot/{compaction,subagent,error}.jsonl`.
    Redact `sessionId`, the cwd and any token.
  - **Write down** in `design.md`'s Round log:
    - whether each type was delivered at all (open question 2);
    - which arrived first, `session.error` or the `Error:` text chunk.

  If a type is **not** delivered, stop group A. Tell the operator that D1's source does not hold and
  that D2's hook transport is the fallback.
- [ ] 1.2 (A) `hub/tests/test_copilot_lifecycle_events.py`: feed each fixture from 1.1 through the
  Copilot adapter's `map_events` in its recorded order.
  - `compaction.jsonl` gives exactly one `status` event with `phase == "compacted"`, carrying
    `pre_tokens`, `post_tokens`, `token_limit`, `trigger`, and `percent` computed as design D4 says.
    `summaryContent` appears nowhere in the payload.
  - A synthetic copy with `success: false` gives a `diagnostic` with code `copilot.compaction_failed`
    and no `compacted` status.
  - `subagent.jsonl` gives a `subagent_started` and a `subagent_completed` status sharing the
    `call_id` of the parent `task` tool call's `tool_use` event.

  Run `py -3.11 -m pytest hub/tests/test_copilot_lifecycle_events.py -v`.
- [ ] 1.3 (A) Same file, errors.
  - `error.jsonl` in its **recorded** order gives exactly one `diagnostic` (code `copilot.<errorType>`,
    with `status_code`) and no `error`/`text` event repeating the message.
  - The **reversed** order also gives exactly one. Reversing the fixture must not make the test pass
    by accident: assert on the count, not on the position.
  - With the raw `session.error` removed, the `Error:` text chunk is classified exactly as slice 2
    classifies it.
  - A `quota` error gives a diagnostic, and the agent's allowance hold state is unchanged: read it
    before and after with slice 4's reader.
- [ ] 1.4 (A) `hub/tests/test_checkpoint_from_compaction.py`: one test per row of design D4's table,
  driving `checkpoint_trigger.consider(..., compacted=True)` against real DB rows (pattern:
  `hub/tests/test_checkpoint_cutover.py`). Patch `generate_checkpoint` and `cut_over` only as
  existing checkpoint tests do. For each row, assert:
  - the conversation's `checkpoint_warning`;
  - whether generation was called, and with `trigger == "context_pressure"`;
  - whether an `InboundQueueEntry` with `origin_type == "checkpoint"` was added;
  - that the `checkpoint_due` broadcast carries `"compacted": true`.

  Include:
  - `automatic` with the percent **below** the threshold, which still generates;
  - `offered` + `dismissed` at 96%, which raises no final warning.
- [ ] 1.5 (A) Same file: `record_agent_output(kind="status", payload={"phase": "compacted", …},
  run_id=…)` dispatches `consider_from_compaction` with the conversation resolved from the run.
  Assert it through a patched `consider`. A `status` with any other phase does not dispatch.
- [ ] 1.6 (A) `hub/tests/test_copilot_home_has_no_deciding_hook.py`: create a Copilot agent through
  `POST /agents` (slice 2 writes its `COPILOT_HOME`), then:
  - every `*.json` under `<COPILOT_HOME>/hooks/` and the `hooks` key of `<COPILOT_HOME>/settings.json`
    contains none of `permissionRequest`, `PermissionRequest`, `preToolUse`, `PreToolUse`,
    `agentStop`, `Stop`, `subagentStop`, `SubagentStop`;
  - the `COPILOT_HOME` config names no trusted folder;
  - the environment slice 2's `build_launch` returns for a run has no `COPILOT_ALLOW_ALL`, under
    every posture including full access.

  This is a guard: it fails today only because the writer does not exist yet. Say so in the
  docstring.
- [ ] 1.7 (C) `hub/tests/test_runner_provider_config.py`, through `POST /runners` and
  `PATCH /runners/{id}`:
  - a `copilot` runner with `{type:"anthropic", api_key_var:"MY_ANTHROPIC_KEY"}` and model
    `claude-haiku-4-5-20251001` is created and returned with `api_key_var` and **no** key;
  - `api_key_var: "sk-ant-api03-xyz"` is refused with the sentence in design D7, and the table is
    unchanged. Count the rows before and after;
  - a `claude` runner with `provider_config` is refused;
  - `type:"azure"` is refused;
  - a model the `claude` catalog does not declare is refused;
  - no model is refused;
  - an alias (`haiku`) is refused.

  Run `py -3.11 -m pytest hub/tests/test_runner_provider_config.py -v`.
- [ ] 1.8 (C) `hub/tests/test_copilot_byok_env.py`: with `monkeypatch.setenv("MY_ANTHROPIC_KEY",
  "sk-ant-test-value")`, the adapter's `build_launch` environment for the provider runner has
  `COPILOT_PROVIDER_TYPE=anthropic`, `COPILOT_PROVIDER_BASE_URL=https://api.anthropic.com`,
  `COPILOT_PROVIDER_API_KEY=sk-ant-test-value` and `COPILOT_MODEL=claude-haiku-4-5-20251001`. The key
  is **absent** from the MCP server `env` in the `--additional-mcp-config` file.

  With `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_TYPE`, `COPILOT_MODEL` and `COPILOT_OFFLINE`
  set in the Hub's own environment, a `copilot` runner **without** `provider_config` gets none of
  them.

  Launchability:
  - with the variable unset, it is not authorized, and its reason names `MY_ANTHROPIC_KEY` and does
    not mention GitHub;
  - with the variable set, it is authorized with no GitHub token in the environment.
- [ ] 1.9 (C) Same file: after one fake run records an event whose text contains the key value, the
  key value (`sk-ant-test-value`) is absent from:
  - the `GET /runners` response;
  - the rendered agent context file;
  - every `AgentOutput.content`/`payload` row;
  - every diagnostic.
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
  - when `<base>` cannot be computed (a repository with no merge target), the bullet names the
    commit alone.
- [ ] 1.12 (B) Same file: `PATCH /agents/{name}` with `config.copilot_review_agents == ["research"]`
  or `["x"]` is refused with a 400 sentence. `["code-review", "security-review"]` is accepted.
- [ ] 1.13 (D) `hub/tests/test_copilot_github_mcp_toggle.py`:
  - the adapter's `build_launch` argv contains `--disable-builtin-mcps` when
    `config.copilot_github_mcp` is absent or false, and omits it when true;
  - the Copilot approval mapping (wherever R2 finds slice 2 put it) answers an MCP permission request
    naming server `github-mcp-server` with the ask-operator outcome under `workspace` (never `allow`),
    with `allow` under full access, and with the operator under `manual`;
  - a request for server `agentweave` under `workspace` is decided exactly as before.
- [ ] 1.14 (C, B, D) UI tests.
  - `hub/ui/src/__tests__/runnerProviderConfig.test.tsx`: the Runners page shows provider fields only
    when the CLI is `copilot`. It shows the D7 sentence about API keys and Claude Max, and renders a
    refusal's own sentence beside the key field (served in the order `POST /runners` returns it).
  - `hub/ui/src/__tests__/copilotAgentSettings.test.tsx`: the review-agents and GitHub-server
    controls appear only for a `copilot`-bound agent.

  Run `cd hub/ui && npx vitest run runnerProviderConfig copilotAgentSettings`.

## 2. Group A — Copilot's lifecycle reaches the Hub

- [ ] 2.1 Add `diagnostic_event(*, code, message, severity, facts)` to `hub/hub/runner_events.py`
  beside `error_event` (design D5). Bound it with `_truncate_utf8` and pass `facts` through
  `redact_secrets`.
- [ ] 2.2 Add the six types to the Copilot adapter's raw-event subscription list (slice 2's module;
  design D1).
- [ ] 2.3 In the Copilot adapter's `map_events`:
  - `session.compaction_complete` becomes `compacted` or a diagnostic (D4);
  - `session.error` becomes a diagnostic (D5);
  - `subagent.*` become statuses (D6);
  - add the `Error:` echo suppression per prompt turn, in both orders (D5).

  Pass tests 1.2 and 1.3.
- [ ] 2.4 `hub/hub/checkpoint_trigger.py`:
  - add `compacted: bool = False` to `consider`, with the branches of design D4's table;
  - add `consider_from_compaction(project_id, agent, conversation_id, payload)` with the
    `_in_flight` / `_dispatched` discipline;
  - add `"compacted": True` to the `checkpoint_due` payload on that path.

  Pass test 1.4.
- [ ] 2.5 `hub/hub/output_recording.py::record_agent_output`: after persisting, dispatch
  `consider_from_compaction` for `kind == "status"` with `payload.phase == "compacted"` (local import,
  as at `:233`). Pass test 1.5.
- [ ] 2.6 Confirm slice 2's `COPILOT_HOME` writer and `build_launch` meet design D3. Change them only
  if test 1.6 fails. Pass test 1.6.
- [ ] 2.7 Run `py -3.11 -m pytest hub/tests/ -q -x` and `ruff check hub/` and
  `black --check --target-version py311 hub/hub/ hub/tests/`.

## 3. Group C — BYOK on a Copilot runner

- [ ] 3.1 Add the migration for `runners.provider_config` (nullable JSON), following
  `.claude/rules/db-migrations.md`: guard a missing table, and bump both head assertions. Add the
  column to `hub/hub/db/models.py::Runner`. Pass test 1.10.
- [ ] 3.2 `hub/hub/schemas/runners.py`: add a `ProviderConfig` model with the validation in design D7,
  and add it to the create, update and response schemas. `hub/hub/api/v1/runners.py`: add the
  cross-field checks (CLI is `copilot`; model declared by the provider's catalog; model set). Pass
  test 1.7.
- [ ] 3.3 Copilot adapter:
  - `build_launch` sets the provider environment and strips ambient provider variables;
  - `launchability` authorizes on the key variable;
  - `catalog_provider` names the provider's catalog.

  Keep the key out of the MCP `env`. Pass tests 1.8 and 1.9.
- [ ] 3.4 The Runners page (`hub/ui/src/components/runners/RunnersPage.tsx`):
  - provider fields for `copilot` (type select, base URL, key variable name);
  - the API-key/Claude Max sentence;
  - the refusal shown beside the field.

  Pass the runner half of test 1.14. Then run `cd hub/ui && npm run lint && npx vitest run`, then
  `npm run build` and `py -3.11 scripts/refresh_ui_bundle.py`. Commit `hub/ui/src` and
  `hub/hub/static/ui` together.

## 4. Group B — Copilot review agents on review turns

- [ ] 4.1 `hub/hub/review_turn.py::prepare_review_turn`: compute `<base>` with the merge-target
  helper R2 names, and carry it on `ReviewContext` (design D8).
- [ ] 4.2 `hub/hub/api/v1/agents.py`, the review section of `_render_hub_agent_context`: add the D8
  bullet after the verdict line, under the D8 conditions. Validate `copilot_review_agents` in the
  agent PATCH route. Pass tests 1.11 and 1.12.
- [ ] 4.3 Agent Settings UI: add a review-agents control shown only for `copilot` agents. Pass its
  part of test 1.14. Run lint, vitest, build and bundle refresh as in 3.4.

## 5. Group D — the GitHub MCP server toggle

- [ ] 5.1 Copilot adapter `build_launch`: omit `--disable-builtin-mcps` when
  `config.copilot_github_mcp` is true. The Copilot approval mapping: `github-mcp-server` requests
  are decided as design D9 says. Pass test 1.13.
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
  - **If** slice 2 delivers a message that is exactly `/compact` as a bare prompt (R2 answers
    this): send `/compact` to `cp5`. The timeline shows `compacted` with tokens, and the
    conversation shows the checkpoint-due banner saying the runner compacted it. No checkpoint is
    generated.
  - **Otherwise:** POST the captured `compaction.jsonl` event through the Copilot mapper into
    `record_agent_output` for `cp5`'s real conversation on `:8010`, using a one-off script in
    `testbed/`. The same banner shows. Record which way it was driven.
- [ ] 7.3 (A) Error once. Give `cp5` an invalid provider key: through a group C runner whose key
  variable holds `invalid`, or, if C was cut, through ambient `COPILOT_PROVIDER_*` in the trial Hub's
  own environment. Run one turn. The timeline shows exactly **one** diagnostic
  `copilot.authentication` (or whatever `errorType` 1.1 recorded), and no duplicate `Error:` text.
  This spends no Copilot allowance.
- [ ] 7.4 (A) `dir <cp5's COPILOT_HOME>\hooks` holds no deciding hook, and the run's recorded
  environment has no `COPILOT_ALLOW_ALL`.
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
- [ ] 7.8 (D) With `copilot_github_mcp` false, the run's recorded argv contains
  `--disable-builtin-mcps`. With it true, run one turn: `List one open issue in this repository
  using the GitHub tools.` An ask-me card appears for the `github-mcp-server` call. Deny it and
  record the card text.

## 8. Archive

- [ ] 8.1 Every kept group's tasks are checked, and every cut group's spec delta is deleted.
  `openspec validate a-copilot-agent-uses-hooks-and-its-own-agents --strict` passes.
- [ ] 8.2 Sync the kept deltas into `openspec/specs/` (`openspec-sync-specs`) and archive the change
  (`openspec-archive-change`). Commit the specs, the change and the code with explicit paths, and
  push. Do not open a PR.
