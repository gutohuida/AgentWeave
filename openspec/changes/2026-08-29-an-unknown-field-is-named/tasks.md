# Tasks — An unknown field is named

Round discipline: this file is written in round 1. **Rounds 2 and 3 revise it**, and implementation
starts only after round 3. Nothing here is closed by a plan existing.

## 1. Review rounds

- [ ] 1.1 **Round 2** — re-derive the audit independently. Do not read round 1's table: re-run the
      route walk against `app.routes` yourself and compare the counts. If the population differs
      from 36 strict / 19 lax, round 1's whole argument is suspect and the proposal is wrong before
      anything else is checked.
- [ ] 1.2 **Round 2** — verify D6's `mode="before"` ordering claim *by running it*, not by reading
      pydantic's documentation. Add `extra="forbid"` to `ContextUsageCreate` alone, post a legacy
      body (`tokens_used`/`tokens_limit`, no `status`), confirm `200`. If extras are checked before
      the validator runs, D6 is wrong and `ContextUsageCreate` needs a different treatment.
- [ ] 1.3 **Round 2** — decide the delta's capability home (`api-request-strictness` as its own
      document, or a requirement inside an existing one). The directory is the expensive part to
      change after `openspec-sync-specs`.
- [ ] 1.4 **Round 2** — read the remaining fifteen lax routes' UI call sites. Round 1 read three
      `agent/trigger` sites and `accounting.ts:85` only, and said so.
- [ ] 1.5 **Round 3** — fresh comparison against the code. Specifically: search `openspec/specs/`
      for any *other* requirement, besides `agent-document-creation`, that depends on a request
      body being tolerated rather than refused. One was found by reading a docstring; a second
      would not be.
- [ ] 1.6 **Round 3** — check that no lax model is reached by a route that also accepts the same
      body from a *different* client with a different vocabulary (the `AgentOutputCreate` legacy
      fallback shape is the known case; find the others or establish there are none).
- [ ] 1.7 **Round 3** — confirm `RequestModel` inheritance does not disturb the response models
      that share a module, and that no model in the 36 loses a `model_config` key in the rewrite.

## 2. Implementation — the base and the enforcement

Implementation begins only after 1.1–1.7.

- [ ] 2.1 Add `RequestModel` to `hub/hub/schemas/common.py` — `ConfigDict(extra="forbid")` and a
      docstring stating why a request body refuses what it cannot honour (D1, D3).
- [ ] 2.2 Add `hub/tests/test_request_strictness.py` (D4): walk `app.routes`, unwrap each body
      annotation to its `BaseModel` subclasses, assert `extra == "forbid"` or membership in
      `LAX_BY_DESIGN` with an inline reason. **Run it now and watch it fail**, naming
      `TriggerAgentRequest` among the nineteen.
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
      `model_config` line — keeping any other key they set (D3). Separate commit from 3.1–3.3 so
      the behaviour change and the refactor are reviewable apart.

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
