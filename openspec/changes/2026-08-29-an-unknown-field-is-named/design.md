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
sense — the reason travels with the model — but it makes laxness *expressible* again, which is the
property this change is removing. A hard-coded list in the test means adding an exemption is an edit
to the enforcement itself, which is the friction that should exist. **Left open for R2/R3 to
challenge:** the proposal's last open question.

### D3 — `RequestModel` sets `extra` and nothing else

**Decided:** the base carries `model_config = ConfigDict(extra="forbid")` alone.

Three of the models needing it also set `populate_by_name` (`messages.MessageCreate`,
`spec_payload`-adjacent models) or run `mode="before"` validators (`tasks.TaskUpdate`,
`agents.ContextUsageCreate`). A base that also decided `populate_by_name` would change how three
models parse aliases as a side effect of a change about unknown fields. Those models set their own
extra config keys on top; pydantic merges a subclass's `model_config` over its base's.

### D4 — the audit becomes a test that walks the routes

**Decided:** `hub/tests/test_request_strictness.py` builds the app, iterates `app.routes` for
`APIRoute`s with a body field, unwraps the annotation to its `BaseModel` subclasses, and asserts
each either has `model_config["extra"] == "forbid"` or appears in `LAX_BY_DESIGN`.

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
key. **R2 must confirm the `mode="before"` ordering claim by test, not by reading pydantic docs** —
if extras were checked first, every legacy context-usage payload would start failing, which is the
one way this change could break something quietly.

## Risks

| Risk | Mitigation |
|---|---|
| A hub test sends an extra field to a now-strict route and goes red | Expected and wanted — each one is a caller that was being ignored. Fix the test's payload, do not relax the model. If a test's extra field turns out to be *meaningful*, that is a missing field on the model and a finding. |
| A model needs `populate_by_name` and loses it | D3: subclass `model_config` merges over the base's. Checked per model at implementation. |
| The `mode="before"` ordering assumption is wrong | D6: proven by a test that sends a legacy `context-usage` body and expects `200`, run before the change is believed. |
| A new capability document is the wrong home for the rule | Open question for R2; the delta directory is the part that is expensive to move after `openspec-sync-specs`. |
