# Exploration — Agents starting their own documents (2026-08-20)

**Status:** Stub. One of eight explore pages opened 2026-08-20 covering the open backlog. Nothing
decided.

**Origin:** item 9 of the operator's twelve:

> *"Agents should be able to create a new spec/explore page from an endpoint."*

---

## What the constraint is today, and that it is deliberate

An agent can **fill in** a document but cannot **start** one. `submit_spec_document`'s own docstring
(`hub/hub/mcp_server.py:905`) states it outright:

> *"The document must already exist: the operator starts an exploration, and you fill it in."*

That is not an oversight. `spec_lifecycle.create_document`'s docstring
(`hub/hub/spec_lifecycle.py:132-134`) gives the reasoning:

> *"Explore is the one phase that would otherwise precede its own document, which is why the entry
> point creates the document rather than setting a mode on the conversation: without it, 'propose'
> and 'approve' have no subject."*

And `POST /documents` (`hub/hub/api/v1/spec.py:1113`) is described as *"Start an exploration"* and
uses `_operator()` as the actor throughout.

So the operator-starts-it rule is load-bearing in the current design: the document is the subject
that the whole lifecycle refers to, and the operator creating it is what makes the exploration
*theirs*. The 22 agent-callable MCP tools today include `submit_spec_document`,
`rename_spec_document` and `read_spec_document` — but no create.

**This exploration is therefore about whether to relax a deliberate constraint, not about filling a
gap.** That is worth naming, because the reasoning above deserves an answer rather than a
work-around.

## What the operator is likely reaching for

An agent mid-conversation realizes there is a thing worth specifying, and today has to stop and ask
the operator to click New before it can write anything down. The friction is real and it is exactly
the kind of thing the migration is supposed to surface.

## Open questions

1. **Does an agent-created document belong to the operator?** If the operator's ownership of an
   exploration is what makes approval meaningful, an agent minting one silently changes who the
   lifecycle serves.
2. **Create, or *request* creation?** There is an existing open item — `D-a13`, the Hub carrying an
   agent's "please add this task" request with one-click accept — that is the same shape. One
   mechanism might serve both, and it preserves the operator's ownership.
3. **What phase does it start in?** `exploring` is the obvious answer and matches `create_document`.
4. **Path minting.** `_mint_document_path` already exists (`spec.py:1119`) and can exhaust
   (`NamingExhaustedError`). An agent creating documents makes exhaustion likelier and the naming
   worse, since the agent names the thing before it knows what it is.
5. **Rate and scope.** An agent in a loop that creates a document per turn is a corpus full of
   noise. Is there a cap, and is it per-project (`agent_budget` exists on the project already)?
6. **Does this need adoption first?** If the answer to item 2 is "the agent writes a file and the Hub
   picks it up", this collapses into
   `2026-08-20-adopting-documents-that-already-exist.md` and needs no new endpoint at all.
7. **Explore page versus spec page** — the operator said "spec/explore". `kind` already distinguishes
   `capability` from `change-spec`; whether an exploration is a third kind or just the `exploring`
   phase of one is worth stating.

## Size

Small if it turns out to be a request-with-accept (question 2) or a consequence of adoption
(question 6). Larger if it means genuinely giving agents document-creation authority, because that
is a change to who the spec lifecycle belongs to.
