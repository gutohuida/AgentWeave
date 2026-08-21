# Let an agent start a specification document

## Why

An agent can create a task. It can create a message, a question, a job, a checkpoint note, a piece
of evidence, and it can even request that a whole new agent be added to the roster
(`hub/hub/api/v1/agent_actions.py:214, 189, 403, 501, 342, 807, 488`). Of everything the capability
plane exposes, **the specification document is the one artefact it cannot begin.**

The rule is explicit, stated twice, and was deliberate:

> *"The document must already exist: the operator starts an exploration, and you fill it in."*
> — `hub/hub/mcp_server.py:905`

> *"no specification document at {path}. The operator starts an exploration; you fill it in."*
> — `hub/hub/api/v1/agent_actions.py:1158-1162`

The consequence is a conversation that stops. An agent working through a problem reaches the point
where the finding deserves a document, and has to ask the operator to go and click something before
it can continue. The operator asked for this to change.

What makes the ask smaller than it sounds is that **the agent already owns the second half of
document creation.** `rename_spec_document` is agent-callable today
(`agent_actions.py:1062`), and its own description states the model the product already holds:

> *"A document is created before anyone knows its subject, so it starts with a deliberately
> meaningless name — a colour and a mythic animal. As soon as the interview establishes what the
> document actually covers, call this."*

So the design where a document is minted nameless and named later is already built, already
agent-facing, and already in use. The agent has the naming half and not the minting half.

**And the thing worth protecting is already protected.** `spec_service.save_document:128` refuses a
`capability` submission from any agent, whatever its run. The corpus with accumulated value — the
documents describing shipped behaviour — is unwritable by agents one layer below whichever endpoint
is called. An agent that can create documents can produce change-specs, which is exactly what an
agent should be able to start.

## What Changes

- **New**: `POST /agent-actions/spec/documents/create` — an agent creates a specification document,
  attributed to its run.
- **New**: `create_spec_document` MCP tool, alongside the existing `submit_spec_document` and
  `rename_spec_document`.
- The Hub mints the path. The route accepts **no path**, for the same reason `rename_document`
  accepts none: *"a rename that accepted a destination would expose that control to the least
  trusted caller in the system as its only guard"* (`hub/hub/spec_service.py:626-633`).
- `kind` is constrained **at creation** to `change-spec`. Today `create_document` sets
  `phase=CURRENT` for `kind="capability"` (`hub/hub/spec_lifecycle.py:151`), so an unconstrained
  tool would let an agent mint an empty capability document parked in `current` that every
  subsequent write then refuses.
- The two statements of *"the document must already exist"* are retired together — the tool
  description and the 404 detail. Leaving either would have the product contradict itself.

**Non-Goals** — stated explicitly, not by omission:

- **Not** letting an agent write a capability document. `save_document:128` stands untouched, and
  the `kind` constraint at creation makes it unreachable rather than merely refused later.
- **Not** letting an agent propose, approve, transition or archive a document. Approval is the
  operator's decision and no argument here expresses it.
- **Not** a request-and-accept queue. The operator's ask is that the agent not stop; a mechanism
  whose whole shape is stopping does not serve it. See design D4.
- **Not** an `unfiled` staging area. It was proposed and withdrawn during exploration: the document
  tree is disk-driven so an unfiled document is *already visible*, any created document needs a row
  or its file cannot be written, and a row is filed by the next reindex. The gate does not exist.
- **Not** a path parameter, a title-derived path, or any other way for the caller to choose where a
  document lands. See design D2.
- **Not** changing `POST /project/documents`. The operator's route is unaffected.

## Capabilities

### New Capabilities

- `agent-document-creation`: an agent beginning a specification document — what it may create, what
  it may not, where the document lands, and how the act is attributed.

### Modified Capabilities

- `spec-document-authority`: the rule that a document is started only by the operator is replaced by
  a narrower one — a document's *kind* determines who may start it, and approval remains the
  operator's alone.
- `agent-capability-plane`: gains document creation as a plane operation, run-authenticated and
  identity-bound like every other.

## Impact

**Code**

- `hub/hub/api/v1/agent_actions.py` — new route; the 404 detail on the submit route reworded.
- `hub/hub/mcp_server.py` — new `@mcp.tool()`; `submit_spec_document`'s description reworded.
- `hub/hub/schemas/` — request and response models.
- `hub/hub/spec_lifecycle.py` — `create_document` is reused unchanged.
- `hub/hub/spec_naming.py` — `mint_placeholder_path` is reused unchanged.

**Data**

New `spec_documents` rows only. No migration.

**Dependency**

None. This change does not wait on `document-adoption`, and the reason is worth stating: the Hub
mints a path that `_mint_document_path` has verified free *against both the records and the disk*
(`hub/hub/api/v1/spec.py:224-238`). The placeholder-file write that makes `POST /documents`
destructive when aimed at an existing document cannot destroy anything when the path is guaranteed
empty. Agent creation reuses the weld safely rather than needing it split.

**Risk**

The failure mode is not destruction — the minted path makes that unreachable — but volume. An agent
in a loop can create documents faster than an operator reads them. Design D5 records why no
allowance gate is proposed, and what would change that judgement.
