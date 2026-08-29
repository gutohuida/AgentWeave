# Tasks — An unknown field is named

Round discipline: this file is written in round 1. **Rounds 2 and 3 revise it**, and implementation
starts only after round 3. Nothing here is closed by a plan existing.

## 1. Review rounds

- [x] 1.1 **Round 2** — re-derived independently, twice, without reading round 1's table:
      **36 strict / 19 lax, identical model list.** The second walk used `route.body_field` —
      FastAPI's own answer to "what is the body" — rather than classifying endpoint parameters, and
      returned the same 55. Round 1's count stands. Round 2 also recursed into the body models'
      *fields*, which round 1 did not: only two models are reachable one level down
      (`AgentQuestionCreate` via `AgentQuestionBatchCreate.questions`, `QuestionOption` via both
      question models) and both already forbid. The hole is empty today; the test must still
      recurse, because it will not stay empty. See D4.
- [x] 1.2 **Round 2** — **D6 proven by running it**, at the model and through the real route. With
      `extra="forbid"` on `ContextUsageCreate` alone: a legacy body (`tokens_used`/`tokens_limit`,
      no `status`) answered `201`; a modern body carrying `wat` answered `422` naming `wat`. The
      before-validator runs first. **And it found what D6 did not say:** `normalize_legacy` builds a
      *fresh* dict, so `{"tokens_used":…,"tokens_limit":…,"wat":1}` also answers `201` — the legacy
      vocabulary keeps absorbing unknown fields silently. **Closed rather than documented:**
      `hub/hub/schemas/tasks.py:92` already solves the identical problem the right way — consume
      the aliases you recognise, pass everything else through to be refused — so `normalize_legacy`
      is rewritten to that pattern (new task 3.5). Verified by running it: legacy bodies still
      normalise, `{"tokens_used":…,"wat":1}` now `422`s naming `wat`. No exemption needed.
- [x] 1.3 **Round 2** — **its own capability, renamed `hub-api-request-contract`.** Own document:
      the rule spans the whole HTTP write surface, operator- and agent-facing;
      `agent-capability-plane` is agent-facing only (run credentials, the agent allowlist),
      `hub-interaction-feedback` is pointer and focus states, and `runtime-diagnostics` is the
      doctor's surface. None can hold it without being about something else. Renamed because
      `api-` is a prefix the corpus does not use while `hub-` is its established one for
      Hub-wide concerns, and because a document named after one property (`strictness`) has nowhere
      to put the next requirement about a request body — `contract` is the subject, and the delta's
      own text already says "contract" seven times. Directory moved with `git mv` in round 2, which
      is the cheap moment.
- [x] 1.4 **Round 2** — all nineteen read, not fifteen. **Six of the nineteen have a UI write call
      site at all**: `agent/trigger` (×3), `accounting.ts:85` (`{token_budget}`), `questions.ts:70`
      (`{answer, labels}` — both declared), `agents.ts:335` (`{name, provider, model, charter_id?}`
      from `AgentCreateDialog.tsx:185`), `agentChat.ts` conversation rename, and `session/sync`
      (**read** only — the UI GETs it; the writer is the CLI). Every body sends declared fields
      only. The three `agent/trigger` sites send from `{agent, message, conversation_id, overrides,
      spec_document, task_id}`, all ten trigger fields being declared including `review_task_id`,
      which `scripts/drive` uses. **The five lax `project/spec/*` routes have no UI caller and no
      shipped caller of any kind** — only this repo's drive harnesses — which is the likeliest
      reason their strict twins in `agent_actions.py` were written and they were not.
- [ ] 1.5 **Round 3** — fresh comparison against the code. Specifically: search `openspec/specs/`
      for any *other* requirement, besides `agent-document-creation`, that depends on a request
      body being tolerated rather than refused. One was found by reading a docstring; a second
      would not be.
- [ ] 1.6 **Round 3** — re-derive round 2's two-vocabulary enumeration independently: that the only
      ways a body carries more than one vocabulary are `mode="before"` model validators (round 2
      counts three: `ContextUsageCreate.normalize_legacy`, `TaskCreate`/`TaskUpdate.
      normalize_assignee_aliases`) and field aliases (round 2 counts one: `MessageCreate`, already
      correct). Task 3.5 rests entirely on that enumeration being complete. Do not read round 2's
      paragraph — run the walk.
- [ ] 1.7 **Round 3** — confirm `RequestModel` inheritance does not disturb the response models
      that share a module, and that no model in the 36 loses a `model_config` key in the rewrite.

## 2. Implementation — the base and the enforcement

Implementation begins only after 1.1–1.7.

- [ ] 2.1 Add `RequestModel` to `hub/hub/schemas/common.py` — `ConfigDict(extra="forbid")` and a
      docstring stating why a request body refuses what it cannot honour (D1, D3).
- [ ] 2.2 Add `hub/tests/test_request_strictness.py` (D4): walk `app.routes`, take each route's
      **`body_field`** (not its parameters — round 2's 1.1), unwrap
      `body_field.field_info.annotation` to its `BaseModel` subclasses, **recurse into those
      models' fields**, and assert `extra == "forbid"` or membership in `LAX_BY_DESIGN` with an
      inline reason. Skip `body_field is None` (28 write routes take no body). **Run it now and
      watch it fail**, naming `TriggerAgentRequest` among the nineteen.
- [ ] 2.3 Add a test asserting `POST …/agent/trigger` with a top-level `permission_mode` answers
      `422` naming that field — F116's exact body. **Run it and watch it fail.**

## 3. Implementation — the models

- [ ] 3.1 `TriggerAgentRequest` inherits `RequestModel`. F116's own route, first.
- [ ] 3.2 The remaining seventeen lax models inherit it — `OperatorAgentCreate`, `AgentRequest`,
      `ConversationRenameRequest`, `BudgetUpdate`, `QueueSettings`, `SessionSyncRequest`,
      `spec.EvidenceRecord`, `spec.EvidenceDecision`, `DriftResolution`, `ReindexRequest`,
      `RetentionSetting`, `AgentHeartbeatCreate`, `AgentOutputCreate`, `ContextUsageCreate`,
      `LogEventCreate`, `QuestionCreate`, `QuestionAnswer`.
- [ ] 3.3 `SpecDocumentCreate` stays on `BaseModel`; its docstring gains the
      `agent-document-creation` citation; the test's `LAX_BY_DESIGN` carries it with the reason
      (D2).
- [ ] 3.4 The 36 models that already forbid move to `RequestModel`, dropping the hand-written
      `model_config` line — keeping any other key they set (D3). Round 2 measured that this is
      exactly one model: `messages.MessageCreate`, which keeps `populate_by_name`. Separate commit
      from 3.1–3.3 so the behaviour change and the refactor are reviewable apart.
- [ ] 3.5 Rewrite `ContextUsageCreate.normalize_legacy` to `hub/hub/schemas/tasks.py:92`'s pattern
      (D6, round 2): keep every key it did not consume, so `extra="forbid"` refuses it, instead of
      returning a freshly built dict that drops unknown keys silently. Add a test for
      `{"tokens_used":1200,"tokens_limit":200000,"wat":1}` -> `422` naming `wat`, alongside one
      asserting each legacy shape still normalises.

## 4. Verification

- [ ] 4.1 The two tests from 2.2 and 2.3 pass.
- [ ] 4.2 Mutation-check both: revert `TriggerAgentRequest` to `BaseModel` and confirm each fails.
- [ ] 4.3 Full hub suite **in file chunks** (`pytest hub/tests/` exceeds the 600s cap). Every red
      test is a caller that was being ignored: fix the payload, never relax the model. If an extra
      field turns out to be meaningful, that is a missing field and a finding — record it.
- [ ] 4.4 `pytest tests/ -v` (CLI), and `ruff check src/ hub/ tests/`,
      `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`.
- [ ] 4.5 **Drive it live** against a Hub on 8011 running this branch: send F116's exact body and
      confirm the `422` names `permission_mode`; then send the same posture via
      `overrides` and confirm the permission card still appears. A refusal that also broke the
      working path is not a fix.
- [ ] 4.6 Update `scripts/drive/FINDINGS.md` F116's **Status:** line.
- [ ] 4.7 `openspec validate --specs --strict`, sync the delta, archive the change.
