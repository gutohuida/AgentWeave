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
- [x] 1.5 **Round 3** — **a second one exists, and it is out of this change's reach.**
      `spec-document-authority`, *The payload contract is versioned and forward compatible*
      (`openspec/specs/spec-document-authority/spec.md:71`): "The Hub MUST preserve fields it does
      not recognise across a read and re-write of the same document", scenario *An unrecognised
      field survives a round trip*, "**AND** no validation error is raised on their account". That
      tolerance is real, but it lives inside `SpecDocumentSubmission.document: Any`
      (`agent_actions.py:1293`) and `MergeRequest.payload: dict` (`spec.py:250`) — one level *below*
      models that already carry `extra="forbid"`. The requirement is satisfied by field typing, not
      by model laxness, so nothing in section 3 can breach it. **Recorded in D-risks** because
      narrowing either field into a model later would.
      Two near-misses checked and cleared: `agent-stream-events`' *Cross-version compatibility*
      speaks of "clients that ignore unknown **response** fields" and of text-only producers, which
      send fewer fields, not extra ones — `AgentOutputCreate` is safe to tighten;
      `agent-context-usage`'s *Legacy context compatibility* is **not** clear and is what 1.6 and
      D8 are about.
- [x] 1.6 **Round 3** — re-derived from pydantic's own decorator registry
      (`__pydantic_decorators__`) rather than a grep, over the recursive closure of 56 body models.
      **Round 2's pydantic-layer enumeration holds, and six further candidate mechanisms are
      measured empty:** `model_validator(mode="before")` **3** (`ContextUsageCreate.normalize_legacy`,
      `TaskCreate`/`TaskUpdate.normalize_assignee_aliases`), field alias **1 model**
      (`MessageCreate`, `from`/`to`, with `populate_by_name`), and then
      `model_validator(mode="wrap")` **0**, `field_validator(mode="before")` **0**,
      `field_validator(mode="wrap")` **0**, v1 `@root_validator` **0**, v1 `@validator` **0**,
      `Annotated` `BeforeValidator`/`WrapValidator`/`AliasPath` metadata **0**, `alias_generator`
      **0**, custom `__init__` **0**, custom `__get_pydantic_core_schema__` **0**, overridden
      `model_validate` **0**. The route-layer escape is also empty, measured not assumed: **no**
      write route takes a `Request` parameter and **no** endpoint reads `request.json()`,
      `request.body()` or `request.form()`, so no dependency rewrites a body before the model sees
      it.
      **But the enumeration was incomplete one layer up, and round 2 could not have seen it by
      counting models.** Three write routes have no model at all (`body: dict`) — an unbounded
      vocabulary, and the drafted test's blind spot. See D7, and tasks 2.2 / 3.6.
      **And running round 2's own sentence for 3.5 broke it** — see D8 and the rewritten 3.5.
- [x] 1.7 **Round 3** — clean, and measured four ways. (a) All **19** lax models set *no*
      `model_config` of their own, so nothing is lost by inheriting. (b) Among the 36 strict, the
      only one setting more than `extra` is `messages.MessageCreate` (`populate_by_name`) — round 2
      is right; the `validate_by_alias`/`validate_by_name` keys that appear alongside it in the
      merged config are pydantic 2.11 derivations of `populate_by_name`, not source, and appear on
      no model that does not set it. (c) **No body model has a subclass**, so no `ConfigDict`
      propagates from a request model onto anything else, and none has a non-`BaseModel` base that
      would collide with `RequestModel`. (d) Exactly two body models are *also* reachable as
      response models — `QueueSettings` and the nested `QuestionOption`. Both response paths return
      constructed instances (`inbound_queue.py:72`, `:107`), so response validation is a model round
      trip over declared fields; `extra="forbid"` cannot reach it. Named in D-risks because that
      safety rests on the handlers' return type, not on the config.

## 2. Implementation — the base and the enforcement

Implementation begins only after 1.1–1.7.

- [x] 2.1 Add `RequestModel` to `hub/hub/schemas/common.py` — `ConfigDict(extra="forbid")` and a
      docstring stating why a request body refuses what it cannot honour (D1, D3).
- [x] 2.2 Add `hub/tests/test_request_strictness.py` (D4): walk `app.routes`, take each route's
      **`body_field`** (not its parameters — round 2's 1.1), unwrap
      `body_field.field_info.annotation` to its `BaseModel` subclasses, **recurse into those
      models' fields**, and assert `extra == "forbid"` or membership in `LAX_BY_DESIGN` with an
      inline reason. Skip `body_field is None` (**36** write routes take no body — round 3's count;
      round 2's 28 was low). **Run it now and watch it fail**, naming `TriggerAgentRequest` among
      the nineteen.
- [x] 2.2a **Round 3, D7** — the same test asserts a route with a body has a **contract**: if the
      unwrap yields no `BaseModel`, that is a failure, not a skip. Carry a second named list
      `NO_CONTRACT_BY_DESIGN` with a reason per entry, seeded with `agents.register_agent`
      (deleted by F111) and `agents.patch_agent` (filed as its own finding — D7). **Run it now and
      watch it name all three `dict` bodies**, before 3.6 removes one of them. Without this
      assertion the whole test passes over them in silence, which is this change shipping its own
      subject.
- [x] 2.3 Add a test asserting `POST …/agent/trigger` with a top-level `permission_mode` answers
      `422` naming that field — F116's exact body. **Run it and watch it fail.**

## 3. Implementation — the models

- [x] 3.1 `TriggerAgentRequest` inherits `RequestModel`. F116's own route, first.
- [x] 3.2 The remaining seventeen lax models inherit it — `OperatorAgentCreate`, `AgentRequest`,
      `ConversationRenameRequest`, `BudgetUpdate`, `QueueSettings`, `SessionSyncRequest`,
      `spec.EvidenceRecord`, `spec.EvidenceDecision`, `DriftResolution`, `ReindexRequest`,
      `RetentionSetting`, `AgentHeartbeatCreate`, `AgentOutputCreate`, `ContextUsageCreate`,
      `LogEventCreate`, `QuestionCreate`, `QuestionAnswer`.
- [x] 3.3 `SpecDocumentCreate` stays on `BaseModel`; its docstring gains the
      `agent-document-creation` citation; the test's `LAX_BY_DESIGN` carries it with the reason
      (D2).
- [x] 3.4 The 36 models that already forbid move to `RequestModel`, dropping the hand-written
      `model_config` line — keeping any other key they set (D3). Round 2 measured that this is
      exactly one model: `messages.MessageCreate`, which keeps `populate_by_name`. Separate commit
      from 3.1–3.3 so the behaviour change and the refactor are reviewable apart.
- [x] 3.5 Rewrite `ContextUsageCreate.normalize_legacy` so the residue it carries forward is
      `data` **minus the whole legacy vocabulary**, not minus the names its first-wins `next(...)`
      selected (**D8, round 3 — this corrects D6's wording, which round 3 implemented and measured
      failing**). Hoist the alias tuples to module level as `_USED`, `_LIMIT`, `_RATIO`, `_WHEN`
      and take the vocabulary as their union plus the carried `source`, `model`, `session_id`,
      `percent`; build `normalized` from `{k: v for k, v in data.items() if k not in VOCAB}` and
      then `update()` the derived fields over it. Tests, all measured against the corrected shape
      in round 3:
      - `{"tokens_used":1200,"tokens_limit":200000,"wat":1}` -> `422` naming `wat`
      - `{"status":"measured",…,"wat":1}` -> `422` naming `wat`
      - each legacy shape still normalises: `{tokens_used,tokens_limit}`, `{context_usage:0.4}`,
        `{percent:0}` -> `unavailable`, `{tokens_used,max_context_tokens}`
      - **the four rolling-upgrade pairs D8 found, all accepted**:
        `tokens_used`+`input_tokens`, `tokens_limit`+`context_limit`,
        `context_usage`+`context_usage_ratio`, `observed_at`+`updated_at`. Two of these are named
        by `agent-context-usage`'s *Legacy context compatibility*; a red test here is a breach of a
        shipped requirement, not a payload to fix.
      - `{"tokens_used":1200,"tokens_limit":200000,"breakdown":{"input_tokens":10}}` now yields
        `breakdown={"input_tokens":10}` where today it yields `None` — the intended side effect of
        the residue, asserted so it is a decision rather than a surprise.
- [x] 3.6 **Round 3, D7** — give `PUT …/project/instructions` a contract:
      `InstructionsUpdate(RequestModel)` in `hub/hub/api/v1/instructions.py` with
      `content: str = ""`, replacing `body: dict` and `body.get("content", "")`. Test that
      `{"contents": "x"}` answers `422` naming `contents` — today it answers `200 {"content": ""}`
      and **blanks the project's instructions**, measured by driving the real route in round 3. Remove it from
      `NO_CONTRACT_BY_DESIGN` in the same commit.
- [x] 3.7 **Round 3, D8** — `normalize_assignee_aliases` (`hub/hub/schemas/tasks.py:86`) removes the
      alias keys **unconditionally**, not only when `assignee` is absent. Measured today:
      `TaskCreate {"title":"t","assignee":"a","assigned_to":"a"}` -> `422 assigned_to`, a
      rolling-upgrade body refused a name the contract accepts, which the delta's new paragraph
      forbids. One line: lift the `data = {k: v for k, v in data.items() if k not in (…)}` out of
      the `data.get("assignee") is None` branch. Test both models with canonical-plus-alias bodies,
      and assert the canonical value wins.

## 4. Verification

- [x] 4.1 The tests from 2.2, 2.2a and 2.3 pass.
- [x] 4.2 Mutation-check both: revert `TriggerAgentRequest` to `BaseModel` and confirm each fails.
- [x] 4.3 Full hub suite. **Green on the implementation: 3540 passed / 84 skipped / 1 xpassed / 0 failed in 26:00** — baseline 3510 plus exactly the 30 tests this change adds. It took two runs: see 4.3a for what the first one found. Round 2 already ran it with all 18 patched: **3510 passed / 84 skipped /
      1 xpassed / 0 failed**, identical to baseline, so this is a regression check against the
      *implementation*, not a discovery run — a red test here is something 3.1–3.5 did that the
      probe did not. **It was, and it found a real gap** — see 4.3a. The guidance still holds if one appears: fix the payload, never relax the
      model; a meaningful extra field is a missing field and a finding. Note the suite takes ~26
      minutes and exceeds a 600s tool cap — run it detached, not in chunks.
- [x] 4.4 `pytest tests/ -v` (CLI), and `ruff check src/ hub/ tests/`,
      `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`.
- [x] 4.5 **Drive it live** against a Hub on 8011 running this branch: send F116's exact body and
      confirm the `422` names `permission_mode`; then send the same posture via
      `overrides` and confirm the permission card still appears. A refusal that also broke the
      working path is not a fix.
- [x] 4.5a **Drive 3.6 live too**: `PUT …/project/instructions` with `{"contents":"x"}` answers
      `422`, and the stored instructions are **unchanged** — the second half is the point, since
      the defect is the blanking, not the status code.
- [x] 4.6 Update `scripts/drive/FINDINGS.md` F116's **Status:** line, and file `patch_agent`'s
      untyped body as its own finding (D7) with the `body.keys()` guard named — round 3 decided it
      is a real defect that this change records rather than fixes.
- [x] 4.7 `openspec validate --specs --strict` → **43/43** with the new `hub-api-request-contract` document in the corpus. Change archived.

- [x] 4.3a **Implementation, D9 — the legacy context vocabulary is bigger than what the
      translation reads.** 4.3 was right that a red test here would mean something the
      implementation did, and four went red: `test_bola.py:142` posts
      `{"percent": 50, "warning": False}` and `test_context_usage.py:216` posts
      `{"agent": …, "percent": 0, "warning": False, "critical": False, "updated_at": …}` —
      "an older CLI posts this on every session reset/compaction", in that test's own words.
      All four answered `422 warning`.
      **D8 enumerated the vocabulary from the names `normalize_legacy` *reads*, and these
      three it reads nowhere.** The deleted watchdog computed `warning`/`critical` from the
      percentage and pushed them with every sample (`_check_context_usage`, commit 578afad4),
      and the body repeated the agent's own name beside the one already in the path. The
      fresh-dict rebuild is exactly what hid them: a name nothing consumes is invisible while
      rebuilding drops it silently.
      They are retired names, not missing fields — nothing should start honouring them — but
      the first body is verbatim `agent-context-usage`'s *Legacy data claims zero without a
      limit* scenario, which says it SHALL degrade to `unavailable`. A `422` there is a breach.
      Fixed by adding `_RETIRED = ("agent", "warning", "critical")` to the vocabulary, with a
      test naming both shapes, and by a delta paragraph and scenario so the rule covers the
      case rather than this being a patch under it.
      **This is the third round in a row where the enumeration was the defect, not the code**
      — round 2 found round 1's, round 3 found round 2's, and implementation found round 3's.
      Each was narrower than the last; none was found by re-reading the previous round.

