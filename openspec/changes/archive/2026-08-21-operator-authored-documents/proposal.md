# Let the operator write a document's content

## Why

`spec_service.save_document` already has an operator branch, and nothing can reach it.

```python
# hub/hub/spec_service.py:128
if document.kind == "capability" and actor.kind != "operator":
    raise SaveRefusedError(
        "capability documents are written by the operator, through a merge",
        code="capability_write_is_the_operators",
    )
```

Two facts follow, both established by reading the code rather than the docs:

1. **An agent cannot write a capability document.** Any submission is refused at that line,
   whatever the agent does.
2. **The operator is permitted but has no route.** Auditing all 24 routes in
   `hub/hub/api/v1/spec.py` and the agent-facing routes in `hub/hub/api/v1/agent_actions.py`,
   `save_document` is called from exactly one place — `POST /spec/documents`
   (`agent_actions.py:1131`) — which binds `actor` to the run and is therefore never an operator.

So a capability document can acquire content by exactly one path today: `POST
/documents/{path}/merge`, absorbing an already-approved `change-spec`.

**Why now.** The operator is migrating 33 openspec capabilities into `spec/`. Every one is
current, shipped behaviour, so every one is a `capability` document. Under the only available path,
each import needs a `change-spec` created, an agent to author it, an operator approval, and a
merge — four steps and an agent run apiece, to import documents that already exist and are already
current. There is no change to absorb and nothing to approve.

That flow is right for *evolving* a corpus one change at a time. It is the wrong shape for
importing one, and it is the only shape there is.

## What Changes

- **A new operator route, `PUT /documents/{path}/content`**, taking the same payload shape as the
  agent submission and calling `save_document` with `Actor(kind="operator", ...)`.
- **The refusal message and its docstring are corrected.** `save_document`'s docstring says
  capability documents are written "through a merge"; the check it documents forbids only
  non-operators. The docstring is narrower than the code, and a reader would conclude direct
  operator authoring is forbidden when it is not.
- **Nothing about the boundary moves.** Approval stays operator-only; rigor still routes
  `contract`/`gate` submissions through pending proposals; `kind` is still fixed at creation;
  an approved document is still refused until reopened. The only thing that changes is that the
  operator branch of an existing check becomes reachable.

**Non-Goals.**

- No bulk or batch import endpoint. One document per call; looping is the caller's business.
- No change to agent authorship, the MCP tool surface, or `submit_spec_document`. Agents still
  cannot write capability documents.
- No delete route. Documents remain permanent (a real gap, recorded as finding 3, not fixed here).
- No UI. This is an API affordance; an import screen is a separate concern.
- No relaxation of the approved-document refusal for operators. An operator who wants to change
  what they approved reopens it first, exactly as today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `spec-document-authority`: today's requirements describe submission as the agent's act
  ("The agent submits a structured payload and the Hub renders the document",
  `openspec/specs/spec-document-authority/spec.md:42`) and give the operator control acts only —
  approval, rigor, archiving, merging. This adds the operator as a possible author, states that
  authorship is attributed to whoever performed it, and records that a capability document is the
  operator's to write directly.

## Impact

**Code**

- `hub/hub/api/v1/spec.py` — the new route; reuses the existing `_operator()` helper.
- `hub/hub/spec_service.py` — docstring and refusal message corrected to match the check.

**Data**

- None. No schema change: `SpecDocumentEvent.actor_kind` and `SpecDocumentMerge.actor_kind` already
  record who acted, and `spec_lifecycle.Actor` already models `"operator"` with
  `origin == "control"`.

**Tests**

- `hub/tests/` — an operator can write a capability document; an agent still cannot; attribution is
  recorded as the operator's; an approved document is still refused; `contract`/`gate` rigor still
  produces proposals rather than a write.

**Not affected**

- The MCP tool surface, rendering, the requirement/evidence/coverage graph, and every existing
  agent submission path.
