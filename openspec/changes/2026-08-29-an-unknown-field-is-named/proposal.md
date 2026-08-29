# An unknown field is named

## Why

`POST /projects/{id}/agent/trigger` accepts a top-level `permission_mode`, answers `200`, and
discards it. The run then proceeds **unsupervised** while the operator's response says it started
normally:

```
POST …/agent/trigger {"agent":"asker","message":"…","permission_mode":"manual"}
  -> 200 {"success": true, "status": "running", "run_id": "run-c10e35f30d81"}
```

No permission card was ever raised. Posture is not a top-level field at all — it travels inside
`overrides`, keyed `permission_mode` (`hub/ui/src/api/modelCatalog.ts:56`,
`hub/ui/src/components/agents/AgentOutputPanel.tsx:327-328`). Sent that way it works and the card
appears in about twelve seconds.

The sibling route on the same API is strict about exactly this shape of mistake:

```
POST …/permission-requests/{id}/decide {"decision":"allow"}
  -> 422 {"detail":[{"type":"missing","loc":["body","allow"],"msg":"Field required"},
                    {"type":"extra_forbidden","loc":["body","decision"],
                     "msg":"Extra inputs are not permitted"}]}
```

This is finding **F116**, found 2026-08-29 while driving row 14 — by making the mistake and being
told nothing.

## The audit: laxness is an omission, not a policy — with one documented exception

Round 1 enumerated **every** request-body model reachable through the running app, by walking
`app.routes` for `POST`/`PUT`/`PATCH` and reading each body model's `model_config`. That measurement
is the change's foundation, and it is reproducible (see item 4 below — it becomes the test).

**36 models forbid extras. 19 do not.** Nothing in `hub/hub/` sets `extra` to `"ignore"` or
`"allow"` on a request model: the entire lax population is the pydantic default, reached by not
writing a line. The two hits for a non-default lax setting are neither of them request models —
`hub/hub/config.py:21` (`SettingsConfigDict`, environment parsing) and `hub/hub/spec_payload.py:68`
(`extra="allow"`, a parsing helper for stored payloads).

The 19:

| Model | Route |
|---|---|
| `agent_trigger.TriggerAgentRequest` | `POST …/agent/trigger` |
| `agents.OperatorAgentCreate` | `POST …/agents` |
| `agents.AgentRequest` | `POST …/agents/request` |
| `agent_chat.ConversationRenameRequest` | `PATCH …/agent/{a}/conversations/{c}` |
| `accounting.BudgetUpdate` | `PATCH …/accounting/budget` |
| `inbound_queue.QueueSettings` | `PATCH …/queue/settings` |
| `session_sync.SessionSyncRequest` | `POST …/session/sync` |
| `spec.EvidenceRecord` | `POST …/project/spec/evidence` |
| `spec.EvidenceDecision` | `POST …/project/spec/evidence/{id}/decision` |
| `spec.DriftResolution` | `POST …/project/spec/drift/{id}/resolve` |
| `spec.ReindexRequest` | `POST …/project/spec/reindex` |
| `spec.RetentionSetting` | `PUT …/project/spec/evidence-retention` |
| `schemas.agents.AgentHeartbeatCreate` | `POST …/agents/{name}/heartbeat` |
| `schemas.agents.AgentOutputCreate` | `POST …/agents/{name}/output` |
| `schemas.agents.ContextUsageCreate` | `POST …/agents/{name}/context-usage` |
| `schemas.logs.LogEventCreate` | `POST …/logs` |
| `schemas.questions.QuestionCreate` | `POST …/questions` |
| `schemas.questions.QuestionAnswer` | `PATCH …/questions/{id}` |
| `schemas.spec.SpecDocumentCreate` | `POST /agent-actions/spec/documents/create` |

### The proof that it is an omission

`EvidenceRecord` exists **twice**, with an identical field list — `identifier`, `kind`, `locator`,
`summary`, `document`, `task_id`:

- `hub/hub/api/v1/agent_actions.py:826` — **forbids** extras.
- `hub/hub/api/v1/spec.py:329` — does not.

`EvidenceDecision` is the same pair (`agent_actions.py`, forbids; `spec.py:340`, does not). And
inside `hub/hub/api/v1/spec.py` alone, `ProposalDecision`, `DocumentCreate`, `MergeRequest`,
`PhaseRequest`, `RigorRequest`, `ArrangeRequest`, `DocumentAdopt` and `DocumentContent` all forbid, while
`EvidenceRecord`, `EvidenceDecision`, `DriftResolution`, `ReindexRequest` and `RetentionSetting` in
the same file do not. Same concept, same module, opposite policy, no stated reason on either side.
That is not two policies; it is one policy and 19 places where nobody wrote the line.

### The one place where it *is* a choice — and a shipped requirement behind it

`hub/hub/schemas/spec.py:13`'s `SpecDocumentCreate` states its laxness deliberately, in its own
docstring:

> No `path`, `kind`, `actor`, `agent` or `run_id` field exists to declare — the route never reads
> the body for any of them, so a caller that sends one anyway is not rejected, it is simply not
> listened to (design D2, D3: unexpressible, not merely refused). `extra` is left at its pydantic
> default (ignore) rather than `"forbid"`, unlike this route's siblings.

And `openspec/specs/agent-document-creation/spec.md:50-58` requires that shape:

> A minted path makes the wrong destination **unexpressible rather than merely refused**.
>
> #### Scenario: No path can be supplied
> - **WHEN** an agent attempts to create a document at a chosen path
> - **THEN** the path is not honoured **and the Hub mints one**

A 422 would not mint one. **A blanket sweep would breach a requirement that shipped 2026-08-12.**
This is exactly the failure the round discipline exists to catch, arriving in round 1 rather than
round 3 only because the audit read the docstrings instead of counting the models.

So the rule cannot be "every request model forbids extras". It has to be "every request model
forbids extras **or says in the code why it does not**" — which is what makes the test below
possible at all, and what makes this change durable rather than a sweep that decays.

## One model, or a shared base?

**A shared base**, plus a test that enumerates the exceptions. The operator's standing preference is
the cleanest solution and "more work is never the objection", and here the cleanest is also the only
one that fixes the finding. F116's complaint is *"two opposite policies inside one API"*. Forbidding
extras on `TriggerAgentRequest` alone leaves 18 of the 19, so the next route written without the
line reproduces F116 exactly — as `TriggerAgentRequest` itself did, with 36 `extra: forbid` siblings
already in the tree.

Writing `model_config = {"extra": "forbid"}` 36 times has already failed as a mechanism: it is
invisible when absent. A base class is visible when absent — `class Foo(BaseModel)` standing next to
54 `class Foo(RequestModel)` — and a test can *see* it.

## What changes

1. **`hub/hub/schemas/common.py` gains `RequestModel`** — a `BaseModel` subclass whose only content
   is `model_config = ConfigDict(extra="forbid")`, with a docstring saying why a request body
   refuses what it cannot honour.
2. **Every request-body model inherits it**, replacing the 36 hand-written `model_config` lines and
   closing the 18 gaps. Models that also need `populate_by_name` or a `mode="before"` validator keep
   them; `RequestModel` sets `extra` only.
3. **`SpecDocumentCreate` is exempt, in code, by name**, with the requirement citation above beside
   it — not by silence.
4. **A test walks `app.routes`** and asserts every `POST`/`PUT`/`PATCH` body model either forbids
   extras or is on a hard-coded exemption list carrying a reason. A new route with a lax body model
   fails the suite. This is the audit above, frozen.
5. **`TriggerAgentRequest`'s 422 is driven live** against a Hub running this branch, sending F116's
   exact body, confirming the response names `permission_mode` — because a passing test is not proof
   of behaviour, and F116 is a route that answered `200` with its tests green.

## What does not change

- **The 36 models that already forbid.** Their behaviour is identical; only where the setting is
  written moves.
- **`SpecDocumentCreate`.** A stray `path` still costs the caller nothing and gains them nothing.
- **Field-level validation everywhere.** This change is about fields that do not exist, not about
  the values of ones that do.
- **`spec_payload.py:68`'s `extra="allow"`** — not a request model; it parses stored payloads.
- **`config.py:21`'s `extra="ignore"`** — environment parsing; unrelated.
- **Response models.** `from_attributes` models are serialisation, not input, and take no `extra`.
- **The posture mechanism.** `overrides["permission_mode"]` stays the way posture travels. This
  change makes the *wrong* way loud; it does not add a second right way.

## The breaking change, said out loud

**Forbidding extras is breaking for any client that sends a field the Hub does not declare.** The
proposal's position is that this is correct and that the blast radius is small, and here is the
measurement rather than the assertion.

**In-repo clients are clean.** Every shipped caller of a lax route sends declared fields only:

| Client | Route | Verified |
|---|---|---|
| `transport/http.py:609-615` | `POST /logs` | body is exactly `event_type`/`agent`/`data`/`severity`; `LogEventCreate` declares all four |
| `transport/http.py:455-458` | `heartbeat` | `status`, optional `message` — both declared |
| `transport/http.py:537` | `session/sync` | `{"data": …}`; `data` is `Dict[str, Any]`, so its *contents* are untouched by `extra` |
| `api/tasks.ts:365`, `AgentOutputPanel.tsx:655`, `NewConversationSurface.tsx:98` | `agent/trigger` | `agent`, `message`, `conversation_id`, `overrides`, `spec_document`, `task_id` — all declared |
| `transport/http.py:161` | all writes | already strips `project_id` and seven identity fields *because* most schemas forbid extras |

**Round 2 struck a claim that was here and did not survive checking.** Round 1 wrote that
`post_agent_output` (`http.py:496-503`) "gets better, not worse": it catches `400`/`422` and retries
with a legacy body, a fallback written for a Hub too old to know `kind`/`payload`/`run_id`/
`sequence`, so — the argument went — forbidding makes that fallback fire and do its job.

**It cannot.** The fallback fires on what the *server* answers, and an old Hub runs old code; nothing
this change does to this Hub's models reaches it. And against a current Hub the question does not
arise: `AgentOutputCreate` declares all six fields the CLI sends (`schemas/agents.py:246-254`), so
forbidding extras there is a **no-op for every caller in the tree**. Its value is prospective and
worth stating as such — if a later Hub drops a field the CLI still sends, the CLI is told which one
instead of having it absorbed, which is the condition the fallback was written to detect and today
cannot. Round 1 also promised "two lax routes" and named one; there is no second.

**Two hazards a reviewer must check, not dismissed here.**

- `ContextUsageCreate` has a `mode="before"` validator (`schemas/agents.py:133`) that accepts legacy
  keys — `tokens_used`, `input_tokens`, `tokens_limit`, `context_limit`, `max_context_tokens`,
  `context_usage`, `context_usage_ratio`, `updated_at` — and rewrites them into declared ones. It
  returns the input **unchanged** when `"status"` is present. So a caller sending `status` *and* a
  legacy key is tolerated today and refused after. `post_context_usage` passes a caller-supplied
  dict straight through and has no in-repo production caller, only
  `tests/test_http_transport.py:217` — but "no in-repo caller" is not "no caller".
- `SessionSyncRequest.data` is `Dict[str, Any]`; forbidding on the wrapper is safe, and a reviewer
  should confirm no route reads a sibling key beside `data`.

**Out-of-repo clients.** `agentweave-ai` depends on `agentweave-hub`, so the CLI and Hub normally
install together — but a Docker Hub can run a different version than the local CLI, and that is the
one real skew path. A third-party script sending a stray field starts getting a `422` that names the
field: loud, immediate, one line to fix, and strictly more informative than the silence it replaces.

This is the operator's pre-authorised decision **D1** (`STATE.json`), whose `raise_it_if` was "the
audit finds a request model where extras are load-bearing, or a shipped client that relies on the
tolerance". The audit found **one** — `SpecDocumentCreate`, load-bearing on a shipped requirement —
and it is exempted by name rather than swept. No shipped client relies on the tolerance. **Proceed.**

## Round 2 — what was re-derived, and what it changed

Round 2 did not read round 1's reasoning before opening the code. The count and the shape of the fix
survived; **three of round 1's supporting arguments did not**, and one hazard round 1 named turned
out to be a hole the change would have shipped with.

**The count survives.** Two independent walks — one classifying endpoint annotations, one using
FastAPI's own `route.body_field` — return the same 55 models and the same **36 strict / 19 lax**
split, with the same names on each side. Round 1's foundation holds.

**D6's ordering is proven, and a hole it did not know about is closed.** With `extra="forbid"` on
`ContextUsageCreate` alone, a legacy `{tokens_used, tokens_limit}` body still answers `201` through
the real route, and a modern body carrying `wat` answers `422` naming `wat`. But
`{tokens_used, tokens_limit, wat}` *also* answered `201`: `normalize_legacy` builds a fresh
dictionary, so on the legacy path an unknown field is dropped by the translation before `extra` can
see it. The route would have shipped declaring that it refuses unknown fields while one of its two
vocabularies did not — this change's own defect, reintroduced inside the mechanism meant to satisfy
it, and hidden better.

Round 2's first instinct was to write that down as a stated limit. The right answer was already in
the tree: `TaskCreate`/`TaskUpdate` face the identical problem — legacy `assigned_to` aliases
reaching a model that forbids extras — and consume only the aliases they recognise, passing the rest
through to be refused, with the reason in a comment at `hub/hub/schemas/tasks.py:92`. So
`normalize_legacy` is rewritten to that pattern instead, and round 2 ran it: every legacy shape still
normalises, `{…, "wat":1}` now answers `422` naming `wat`, and **the change needs no exemption for
this route at all.** The delta states the general rule rather than licensing the hole.

**The second named hazard is closed.** `SessionSyncRequest` declares `data` and nothing else, and
`sync_session` reads `body.data` at five call sites and no sibling key
(`hub/hub/api/v1/session_sync.py:45-178`). Forbidding on the wrapper cannot reach the payload
inside, which stays `Dict[str, Any]`.

**Two vocabularies is the whole risk class, and it is now enumerated.** A request body can carry
more than one vocabulary by exactly two mechanisms, and round 2 found every instance of each.
`mode="before"` model validators: **three** across all 56 body models (including nested) —
`ContextUsageCreate.normalize_legacy` and `TaskCreate`/`TaskUpdate.normalize_assignee_aliases`. All
three were read; two are already correct and one is fixed by 3.5. Field aliases: **one** —
`MessageCreate`, whose `from`/`to` aliases sit beside `populate_by_name` *and* `extra="forbid"`
already, so both vocabularies are accepted and unknown fields are still refused. There is no third
mechanism and no fourth instance. Round 1 named this hazard on one model; it is a class, and the
class is closed.

**A claim was struck.** Round 1's "two lax routes get better" argument for `post_agent_output` does
not hold — see the breaking-change section, where it is now written up as retracted with the reason.

**The capability is its own document, renamed `hub-api-request-contract`.** No existing capability
can hold a rule that spans the operator- and agent-facing write surface both;
`agent-capability-plane` is agent-facing, `hub-interaction-feedback` is pointer and focus.
`hub-` is the corpus's prefix for Hub-wide concerns, `api-` is used by nothing, and a document named
after one property has nowhere to put the second requirement. Moved with `git mv` while moving is
still free.

**Every lax route's callers are read, and one argument in D2 was wrong.** Six of the nineteen have a
UI write call site; all six send declared fields only. The five `project/spec/*` ones have no
shipped caller at all, which is the likeliest reason their strict twins in `agent_actions.py` exist
and they do not. And D2 rejected the self-declaring-marker alternative on the grounds that it "makes
laxness expressible again" — which is simply false: under a base class a subclass writing
`extra="ignore"` overrides it and pydantic accepts that, as round 2 confirmed by running it. The
decision is unchanged; its stated reason is now the true one (an exemption should need a second
file and a second reader, not a self-declaration).

D3's supporting facts were wrong too: it named "three of the models needing it" as also setting
`populate_by_name` or running `mode="before"` validators. Measured across all 55, **exactly one body
model sets any `model_config` key besides `extra`** — `MessageCreate` — and it is already strict, so
it is not one of the models needing anything. No `spec_payload` model is a request body at all, and
validators are not `model_config`. D3's decision stands; the risk it guards against is one model and
one key, not three.

A right answer resting on a wrong argument is the failure this repository produces most, and only a
round that re-derives the argument finds it. Three turned up here.

## Open questions for round 3

- **Is any *other* shipped requirement served by tolerance?** One was found by reading a docstring
  (`agent-document-creation`). A second would not be. R3 searches `openspec/specs/` rather than the
  code.
- **Re-derive the two-vocabulary enumeration.** Round 2 claims exactly three `mode="before"`
  validators and one aliased model across all 56 body models, and that this is the complete risk
  class. It is a claim from one script and one reading, and it is now the argument the whole of 3.5
  rests on. R3 re-derives it rather than reading the paragraph — the same instruction round 2 was
  given about the 36/19 count, for the same reason.
- **Does inheriting `RequestModel` disturb anything the 36 already set?** Round 2 verified the
  mechanism — a subclass setting other `model_config` keys keeps the base's `extra="forbid"`, and a
  subclass setting `extra` itself wins — but not model by model. That is R3's 1.7.
