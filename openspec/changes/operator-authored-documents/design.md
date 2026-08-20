## Context

The operator's authority over specification documents is already designed, already specified, and
partly unreachable.

`openspec/specs/spec-document-authority/spec.md:1046` requires: *"A capability document's content
SHALL be written only by the operator"*, with the scenario *"an agent submits content against a
capability document → it is refused → and the same submission from the operator succeeds."*

`hub/hub/spec_service.py:128` enforces precisely that:

```python
if document.kind == "capability" and actor.kind != "operator":
    raise SaveRefusedError("capability documents are written by the operator, through a merge", ...)
```

And `hub/tests/test_spec_capability_kind.py:114` proves the operator branch works — by importing
`spec_service` and calling `save_document` in-process, because there is no route to call.

`save_document` has exactly one caller in the API: `POST /spec/documents`
(`hub/hub/api/v1/agent_actions.py:1131`), which binds `actor` to the run
(`Actor(kind="agent", name=actor.agent, run_id=actor.run_id)`) and so can never be an operator. No
route in `hub/hub/api/v1/spec.py` calls it at all.

The practical consequence is that a capability document can only receive content by
`POST /documents/{path}/merge` — absorbing an approved `change-spec`. That is the right mechanism
for evolving a corpus one change at a time, and the wrong one for importing 33 documents that are
already current and have no change to absorb.

## Goals / Non-Goals

**Goals:**

- Make the operator branch of an existing check reachable over HTTP.
- One payload contract, one validation path, whoever is writing.
- Attribution that distinguishes an operator's write from an agent's, established from the
  credential.
- Make a corpus import possible without four steps and an agent run per document.

**Non-Goals:**

- Bulk import. One document per call; looping is the caller's business, and a batch endpoint would
  need its own partial-failure semantics for no benefit here.
- Any change to agent authorship or the MCP surface. Agents still cannot write capability
  documents.
- Relaxing anything for operators: not approval, not rigor, not `kind`, not the approved-document
  refusal.
- A delete route. Documents stay permanent — a real gap (finding 3), deliberately not bundled.
- UI. An import screen is a separate concern.

## Decisions

### 1. `PUT /documents/{path}/content`, not `POST /spec/documents`

The agent route is `POST /spec/documents` with the path in the body. The operator route puts the
path in the URL, matching every other operator document route in `spec.py`
(`/documents/{path:path}/rigor`, `/documents/{path:path}/proposals`, `/documents/{path:path}/merge`).

`PUT` rather than `POST`: submitting the same payload twice must leave the same content, and the
operation names a document that already exists rather than creating one. That is what `PUT` means,
and it also makes an interrupted import safe to re-run — which matters when the import is a loop
over 33 documents.

*Alternative rejected — reuse `POST /spec/documents` with a dual-credential dependency.* One route
resolving either an operator or a run credential would put the identity decision inside the handler,
which is exactly where identity confusion has bitten this codebase before. Two routes, two
dependencies, two unambiguous actors.

### 2. The route is thin, and the service is untouched apart from a docstring

The handler validates the path, resolves the workspace, loads the document, and calls
`save_document` with `Actor(kind="operator", name=...)`. Every refusal already exists in the
service, so the route adds no rules of its own: `kind_is_fixed`, `document_approved`,
`payload_invalid` and the rigor branch all apply unchanged.

This matters for the boundary. The change does not weaken a rule; it reaches an existing branch. If
a future rule is added to `save_document`, both callers get it.

### 3. The docstring is corrected, because it is narrower than the code

`save_document`'s docstring says a capability document is "written only by the operator, through a
merge" and the refusal message repeats it. The check forbids only non-operators — it says nothing
about merges. A reader following the docstring concludes direct operator authoring is forbidden,
which is how this gap stayed invisible while the requirement it violates sat in the corpus.

The message becomes "capability documents are written by the operator" — true, and no longer naming
a mechanism the check does not enforce.

### 4. Attribution rides on the existing actor model

`spec_lifecycle.Actor` already carries `kind` and maps `operator → origin "control"`, and
`SpecDocumentEvent.actor_kind` already stores it. Nothing new is recorded; the operator path simply
starts producing events that were previously only reachable in tests.

The run id is left unset for an operator write, which is correct: there is no run.

## Risks / Trade-offs

- **The operator can now write a capability document without a merge, so a corpus can drift from
  the change history that produced it.** → This is inherent to importing an existing corpus and is
  the point. Mitigated by attribution: an operator-authored document is recorded as such, so a
  document with no originating change is identifiable rather than indistinguishable.
- **A convenience route can become the default path, eroding the change → approve → merge flow.**
  → Mitigated by scope: no UI, no bulk endpoint, and agents are unaffected, so the flow stays the
  path of least resistance for ordinary work. Worth revisiting if an import screen is ever built.
- **`PUT` implies idempotence the service does not strictly guarantee** — a second identical write
  still records a second event. → Accepted: the *content* is idempotent, which is what a caller
  re-running an interrupted import depends on. The event log is deliberately append-only.

## Migration Plan

1. Correct the docstring and refusal message in `spec_service.py`.
2. Add the route in `spec.py`.
3. Tests: operator writes a capability; agent still refused; attribution recorded as operator;
   approved still refused; rigor still proposes; kind still fixed; validation still applies.
4. Exercise it against a throwaway project by importing two real openspec capabilities end to end
   before any of the 33 are imported for real.

**Rollback:** deleting the route removes the capability entirely; nothing else changes behaviour.

## Open Questions

- **Should an operator write be visible in the UI as "imported" rather than "authored"?** The
  distinction is recorded either way. Deferred until there is an import screen to show it on.
