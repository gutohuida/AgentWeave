# Design — an unknown field is named

## Context

Measured 2026-08-29 by walking the running app's routes: of the request-body models FastAPI binds
for `POST`/`PUT`/`PATCH`, **36 forbid unknown fields and 19 do not**. No request model anywhere in
`hub/hub/` sets `extra` to a lax value on purpose except one, and that one says so in a docstring
and is backed by a shipped requirement. Every other lax model is lax because a line was not written.

The cost of the omission is not uniform. On most of the 19 an unknown field is a typo absorbed in
silence. On `POST /agent/trigger` it is a **safety posture the operator asked for and did not get**,
answered `200`, with a run already executing unsupervised by the time they could notice.

## Decisions

### D1 — the rule lives on a shared base class, not on `TriggerAgentRequest`

**Decided:** add `RequestModel` to `hub/hub/schemas/common.py`; every request-body model inherits it.

`model_config = {"extra": "forbid"}` written 36 times is a convention that fails silently: its
absence looks like nothing. That is precisely how `TriggerAgentRequest` came to be lax with 36
strict siblings already in the tree. A base class fails *visibly* — `class Foo(BaseModel)` reads
wrong next to 54 `class Foo(RequestModel)` — and, more importantly, is machine-checkable.

**Rejected:** forbidding on `TriggerAgentRequest` only. It closes F116's instance and leaves F116's
actual complaint — two opposite policies inside one API — in 18 other places, with nothing stopping
the nineteenth.

**Rejected:** a FastAPI dependency or middleware that inspects raw bodies against the route's model.
It would work, and it would put the rule somewhere no one reads when writing a model, while
duplicating validation pydantic already does. The refusal must come from the schema, because the
schema is what the error message is derived from — `{"type":"extra_forbidden","loc":["body",
"permission_mode"]}` names the field only because pydantic raised it.

### D2 — the exemption is named in code, and the test knows the list

**Decided:** `SpecDocumentCreate` keeps `BaseModel` and pydantic's default, its existing docstring
gains the `agent-document-creation` citation, and the enforcement test carries it on an explicit
exemption list with the reason inline.

`openspec/specs/agent-document-creation/spec.md` requires that an agent supplying a path is answered
by *minting one anyway* — "unexpressible rather than merely refused". A 422 refuses and mints
nothing, so inheriting `RequestModel` here would breach a requirement that shipped 2026-08-12.

**Rejected:** an implicit exemption (leave it lax, say nothing). Indistinguishable from the 18
omissions this change is closing, and it would be re-swept the next time someone runs the audit.

**Rejected:** a marker attribute on the model that the test reads, e.g.
`model_config = {"extra": "ignore", "json_schema_extra": {"aw_lax_reason": "…"}}`. Cleaner in one
sense — the reason travels with the model — but a model that can exempt itself is exempted in one
file, by the person adding it, with nothing that has to be convinced. The hard-coded list means an
exemption is an edit to the enforcement, in a second file, which is the friction that should exist.

**Round 2 corrected this decision's reasoning while keeping the decision.** Round 1 rejected the
marker because "it makes laxness *expressible* again, which is the property this change is
removing". That argument is false, and measurably so: under D1's base class a subclass writing
`model_config = ConfigDict(extra="ignore")` **already** overrides the base and is accepted by
pydantic — verified by running it. Laxness never stopped being expressible; D1 only made it
*visible*. The list belongs in the test for the reason now stated above — who has to agree — not
because the alternative would reopen a door this change closes. This is the failure mode the round
discipline exists for: a right decision resting on a wrong argument, which a review that only checks
outcomes would have passed.

### D3 — `RequestModel` sets `extra` and nothing else

**Decided:** the base carries `model_config = ConfigDict(extra="forbid")` alone.

A base that also decided `populate_by_name` would change how a model parses aliases as a side
effect of a change about unknown fields. Subclasses set their own config keys on top; pydantic
merges a subclass's `model_config` over its base's — verified by running it, including that a
subclass setting `extra` itself wins over the base.

**Round 2 corrected the facts behind this.** Round 1 said "three of the models needing it also set
`populate_by_name` … or run `mode="before"` validators", naming `messages.MessageCreate`,
"`spec_payload`-adjacent models", `tasks.TaskUpdate` and `agents.ContextUsageCreate`. Measured
across all 55 body models: **exactly one sets any `model_config` key other than `extra`** —
`messages.MessageCreate` (`populate_by_name`) — and it is already in the strict 36, so it is not one
of "the models needing it". No `spec_payload` model is a request body at all. Validators are not
`model_config` and were never at risk from what the base sets. The decision is unchanged and the
merge risk is real but far narrower than stated: one model, already strict, one key.

### D4 — the audit becomes a test that walks the routes

**Decided:** `hub/tests/test_request_strictness.py` builds the app, iterates `app.routes` for
`APIRoute`s with a body field, unwraps the annotation to its `BaseModel` subclasses, and asserts
each either has `model_config["extra"] == "forbid"` or appears in `LAX_BY_DESIGN`.

**Round 2 fixed how the body is found.** Round 1 described classifying the endpoint's *parameters*.
That re-implements a judgement FastAPI has already made and can disagree with it — a
`Depends()`-injected pydantic model is a parameter and is not a body. Use `route.body_field`, which
is FastAPI's own answer, and unwrap `body_field.field_info.annotation`. Round 2 ran both walks: they
return the identical population of 55, so nothing is miscounted today, but only one of them is
*defined* to stay correct.

Two shapes the test must handle rather than assume away, both absent today and both checked:
`route.body_field is None` (**36** write routes take no body at all — they must be skipped, not
failed; round 3 re-counted, round 2's figure of 28 was low), and the synthetic `Body_*` model
FastAPI generates when a route declares several embedded body params. No route does that today; if
one appears, the synthetic wrapper is not a model anyone wrote and asserting on it would be noise.
It must be unwrapped to its fields' models or skipped by name, deliberately.

**Round 3 found a third shape, and it is not absent — it is three routes.** Skipping
`body_field is None` is safe only if a route either has a model body or no body; it also has to be
true that a route *with* a body has a *model*. It is not. Three write routes annotate their body
`dict`, so `body_field` is present, the unwrap finds no `BaseModel`, and the test as drafted asserts
nothing and passes:

```
POST  /projects/{id}/agents/register        body: dict   (agents.register_agent)
PATCH /projects/{id}/agents/{name}          body: dict   (agents.patch_agent)
PUT   /projects/{id}/project/instructions   body: dict   (instructions.put_instructions)
```

They were invisible to rounds 1 and 2 because both counts classified *models*, and these have none.
This is not a technicality: `put_instructions` reads `body.get("content", "")`, so `{"contents": …}`
— one typo — answers `200` and **overwrites the project's instructions with an empty string**. That
is F116's own failure with data loss attached rather than an unsupervised run — **driven through the
real route in round 3, not inferred**: after `PUT {"content": "…"}`, a `PUT {"contents": "…"}`
answers `200 {"content": ""}` and the `GET` confirms the stored text is gone. `patch_agent` fails a
different way: an unknown key is absorbed for a self-registered agent, and for a *configured* one it
flips the reserved-name guard `set(body.keys()) <= _unrestricted_fields` into a `409` that blames
the agent's name for a typo in a field.

So the test asserts a route's body **is** a declared contract, and carries these three in a second
named list with reasons, exactly as `LAX_BY_DESIGN` carries `SpecDocumentCreate`. A defect that is
listed is a decision; a defect the walk cannot see is this change shipping its own subject. See D7
for which of the three this change fixes.

**Round 3 also re-derived the walk itself**, from `route.body_field` and a recursive closure over
the body models' fields: **55 root body models, 56 in closure, 37 strict / 19 lax** — the same
population, the closure's one extra model being nested-only and strict. Round 2's 36/19 counted
roots only, and is right about roots.

### D7 — the three model-less bodies: one is fixed here, two are recorded

**Decided by round 3.**

- **`put_instructions` gets a model** (`InstructionsUpdate(RequestModel)`, a single `content` field).
  It is two lines, it is the one with a live data-loss shape, and leaving it lax while this change's
  own delta says a body must declare a contract would be the change failing its own requirement in
  the cheapest available case.
- **`register_agent` is recorded as declining, pointing at F111.** The operator decided on
  2026-08-29 that self-registration leaves the product (`scripts/drive/FINDINGS.md` F111, *Status:
  superseded by an operator decision*), and this route is what leaves with it. Writing a contract
  for a route the next queued change deletes is work with a negative lifespan.
- **`patch_agent` is recorded as declining, and filed as its own finding.** It is a wide partial
  update whose semantics are "present or absent", read through `"x" in body` at a dozen sites plus
  three dynamic field-set loops, with per-field `400`s that a model would turn into `422`s and a
  reserved-name guard that reads `body.keys()`. A model can express it — all-optional fields plus
  `model_fields_set` for the guard — but that is a behaviour change across the agent-editing UI, and
  riding it in on a change about unknown fields would make both unreviewable. The exemption entry
  says so, which is the difference between a deferral and an omission.

### D8 — a translation removes its vocabulary, not the names it read

**Decided by round 3, correcting D6's own repair.**

D6's rewrite of `normalize_legacy` was stated as *"it keeps any key it did not consume, and
`extra="forbid"` refuses it."* Round 3 implemented exactly that sentence and ran it. It refuses four
legacy shapes the product must accept:

```
{"tokens_used":1200,"input_tokens":1200,"tokens_limit":200000}          -> 422  input_tokens
{"tokens_used":1200,"tokens_limit":200000,"context_limit":200000}       -> 422  context_limit
{"context_usage":0.4,"context_usage_ratio":0.4}                         -> 422  context_usage_ratio
{"tokens_used":1,"tokens_limit":10,"observed_at":1.0,"updated_at":1.0}  -> 422  updated_at
```

`normalize_legacy` selects each operand with a first-wins `next(...)` over an alias tuple, so
"consumed" means *the one alias that won*, not *the alias set*. A body carrying two names for one
operand is precisely what a rolling upgrade emits — and two of the four refusals above name fields a
**shipped requirement names explicitly**. `agent-context-usage`, *Legacy context compatibility*:

> During rolling upgrades, readers SHALL normalize unambiguous legacy aliases including
> `tokens_used`, `tokens_limit`, **`input_tokens`**, **`context_limit`**, and ratio-form
> `context_usage`.

So D6's repair, taken at its word, would have breached a requirement that shipped before this change
existed — the same shape as 2026-08-28, when round 3 caught rounds 1 and 2 both breaching a
four-day-old requirement. **The correction:** the residue is `data` minus the whole legacy
vocabulary — the names across `_USED`, `_LIMIT`, `_RATIO`, `_WHEN` and the carried
`source`/`model`/`session_id`/`percent` — not minus the names `next()` selected. Round 3 ran the
corrected shape over twelve bodies: every legacy row above is accepted and normalises identically to
today, the modern path is unchanged, and only `wat` is refused.

The precedent D6 cites is right and D6 transcribed it wrong. `tasks.py:92` removes **both**
`assigned_to` and `assigned_agent` whichever one it read — the alias set, not the winner. D6's
sentence described the winner.

**And the precedent has the narrower version of the same hole.** `normalize_assignee_aliases` guards
the removal with `data.get("assignee") is None`, so a body carrying the canonical field *and* its
legacy alias skips the removal entirely and is refused — measured live:

```
TaskCreate {"title":"t","assignee":"a","assigned_to":"a"}  -> 422  assigned_to: extra_forbidden
```

That is a rolling-upgrade body being refused a name the contract accepts, which the delta's new
paragraph now forbids. It is a one-line fix — the removal stops depending on the guard — it is in
the class this change is about, and it is cheap, so it is task 3.9 rather than a finding.

**One behaviour improves as a side effect, and it should be stated rather than discovered.** On the
legacy path `normalize_legacy` today drops `breakdown` — a *declared* field — because the fresh dict
never carries it. Under the corrected residue it survives into the model and validates. Measured:
`{"tokens_used":1200,"tokens_limit":200000,"breakdown":{"input_tokens":10}}` yields
`breakdown={'input_tokens': 10}` where today it yields `None`.

This is the only part of the change that has a future. The 18 edits are one-time; the test is what
means the nineteenth omission cannot ship. It also documents the count, so a reviewer can see the
population change when a route is added.

The test must fail before the fix — run it against the tree with only `RequestModel` added and
nothing inheriting it, and watch it name `TriggerAgentRequest`.

### D5 — the refusal is pydantic's, unmodified

**Decided:** no custom error shape, no custom handler.

FastAPI already answers `422` with `{"detail":[{"type":"extra_forbidden","loc":["body","<field>"],
"msg":"Extra inputs are not permitted"}]}`. F116's own text calls the sibling route's version of
this *"the product at its best"* — it named the field and it named what was wrong. There is nothing
to improve; the defect was that it was not reached.

### D6 — `ContextUsageCreate`'s legacy path is preserved by ordering, not by exemption

**Decided:** `ContextUsageCreate` inherits `RequestModel`. Its `normalize_legacy` validator runs
`mode="before"`, so it rewrites the payload into declared keys *before* extras are checked, and the
legacy shapes it handles keep working.

The one behaviour that changes: a payload carrying `status` **and** a legacy key returns from the
validator unchanged (`schemas/agents.py:135`) and is then refused. That is a caller mixing the new
and old vocabularies in one body, which no in-repo client does, and the refusal names the offending
key.

**Round 2 proved the ordering rather than asserting it**, at the model *and* at the route. With
`extra="forbid"` on `ContextUsageCreate` alone and the real route driven through the app:

```
POST …/agents/{a}/context-usage {"tokens_used":1200,"tokens_limit":200000}   -> 201
POST …/agents/{a}/context-usage {"status":"measured","source":"x",…,"wat":1} -> 422
    {"type":"extra_forbidden","loc":["body","wat"],"msg":"Extra inputs are not permitted"}
```

The before-validator runs first and extras are evaluated on its output. D6 stands.

**But the same run found what D6 does not say, and it is a limit on the fix rather than a risk to
it.** `normalize_legacy` does not edit the caller's dict; it builds a fresh `normalized` one from
the keys it recognises. So on the legacy path an unknown field is *dropped before `extra` can see
it*, and the route still answers `2xx`:

```
POST …/agents/{a}/context-usage {"tokens_used":1200,"tokens_limit":200000,"wat":1} -> 201
```

Round 2's first answer was to state that limit in the delta and accept it. **That answer was wrong,
and the repository already contains the right one.** `TaskCreate`/`TaskUpdate` run a `mode="before"`
validator over the same problem — legacy `assigned_to`/`assigned_agent` aliases arriving at a model
that forbids extras — and solve it by consuming only the aliases they recognise and passing
everything else through, with the reason written beside it (`hub/hub/schemas/tasks.py:92`):

> `# Remove legacy alias keys so extra='forbid' does not reject them`

`normalize_legacy` differs only in *building a fresh dict instead of editing the caller's*, which
drops unknown keys as a side effect of how it happens to be written rather than as a decision. So
**`normalize_legacy` is rewritten to the pattern already shipped one module over**: it keeps any key
it did not consume, and `extra="forbid"` refuses it. Round 2 ran this against the real validator:

```
{"tokens_used":1200,"tokens_limit":200000}          -> OK, measured, 1200
{"tokens_used":1200,"tokens_limit":200000,"wat":1}  -> 422 extra_forbidden: wat
{"status":"measured",…,"wat":1}                     -> 422 extra_forbidden: wat
{"context_usage":0.4,"source":"codex"}              -> OK, measured, 40%
```

Every legacy shape the validator exists to accept still works, and the rule now holds on both
vocabularies with **no exemption at all**. This is the operator's standing preference applied to a
place where taking the exemption was easier: the cleanest solution wins and "more work" is not the
objection. It also removes an exemption that would have had to be true forever, and an exemption
nobody wrote down is how this change's own defect got here.

The delta states the general rule this produces — a translation consumes what it recognises and
leaves the rest to be refused — rather than licensing a translated vocabulary to swallow anything.

## Risks

| Risk | Mitigation |
|---|---|
| A hub test sends an extra field to a now-strict route and goes red | **Measured in round 2: none does.** All 18 patched, full suite run — 3510 passed / 0 failed, identical to baseline. The guidance stands if one appears later (fix the payload, never relax the model), but there is nothing to fix today. |
| A model needs `populate_by_name` and loses it | D3: subclass `model_config` merges over the base's. Checked per model at implementation. |
| The `mode="before"` ordering assumption is wrong | **Closed in round 2** — proven at the model and through the route: a legacy body answers `201`, a modern body carrying an unknown key answers `422` naming it. |
| A `mode="before"` translation swallows an unknown field before `extra` can refuse it | **Found in round 2** on `ContextUsageCreate`, which is why D6 now rewrites it to `tasks.py:92`'s consume-what-you-recognise pattern. R3's 1.6 looks for the others: this is the one shape where the rule silently does not reach, and it is invisible from the model's config. |
| A new capability document is the wrong home for the rule | **Closed in round 2** — its own document, renamed `hub-api-request-contract`, moved with `git mv` while moving was still free. |
| The test passes while a lax body slips past it | **Found in round 3, and it was not hypothetical.** Three write routes annotate their body `dict`; the drafted walk finds no model in them and asserts nothing. D7 fixes one and names two. The test now asserts a body *is* a contract. |
| The legacy translation refuses a name its own vocabulary defines | **Found in round 3 by running D6's own sentence.** Four legacy shapes refused, two of them fields `agent-context-usage` names in a shipped requirement. D8 corrects the residue to the vocabulary, not the winner; verified over twelve bodies. |
| A shipped requirement other than `agent-document-creation` depends on tolerance | **Round 3 found a second one, and it is out of reach.** `spec-document-authority`'s *The payload contract is versioned and forward compatible* requires unrecognised fields to survive a round trip with no validation error — but that tolerance lives inside `SpecDocumentSubmission.document: Any` and `MergeRequest.payload: dict`, one level *below* models that already forbid extras. The requirement is met by field typing, not by model laxness, so this change cannot reach it. Recorded because narrowing either field into a model later would breach it. |
| A model that is both a request body and a response model is broken by `extra="forbid"` | **Checked in round 3.** Exactly two body models are also reachable as responses — `QueueSettings` and the nested `QuestionOption` — and both response paths return constructed model instances rather than dicts, so response validation is a model round trip over declared fields only. Named because the safety rests on the handlers' return type, not on the config. |
