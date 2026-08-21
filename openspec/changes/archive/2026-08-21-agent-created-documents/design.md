# Design — agent-created documents

## Context

Three existing facts do most of the work, and the design is largely a matter of composing them.

1. **Nameless-then-named is already the model.** `spec_naming.mint_placeholder_path` produces "a
   colour and a mythic animal", and `rename_spec_document` — already agent-callable — exists
   precisely to replace it once the subject is known.
2. **The capability corpus is protected below the endpoint.** `spec_service.save_document:128`
   refuses a `capability` submission from any agent, on any run, through any route.
3. **A minted path is free against records *and* disk.** `_mint_document_path`
   (`hub/hub/api/v1/spec.py:224-238`): *"A name is only available if nothing at all occupies it: a
   document the project has recorded, or a file somebody put there by hand."*

Fact 3 is the one that changes the shape of this change. The reason `POST /project/documents` is
called a destructive weld in `document-adoption` is that it renders a placeholder over whatever the
caller's path points at. Aimed at a path the Hub just minted, there is nothing to render over. So
agent creation can reuse the existing creation path as-is, and does not queue behind adoption.

## Goals

- An agent that reaches the point of needing a document creates one and keeps working.
- Nothing an agent can do through this reaches the current-behaviour corpus.
- The act is attributable to a run, like every other effect on the capability plane.

## Non-goals

- Any new gate, queue, or approval step.
- Any change to what an agent may write once the document exists.

## Decisions

### D1 — A new route on the capability plane, not an agent branch in the operator's route

`POST /project/documents` binds its actor with `_operator()`, which is *"named rather than taken
from a request body — an actor a caller can state is an actor a caller can invent"*
(`hub/hub/api/v1/spec.py:215-221`). Adding an agent branch would put two identities through one
route and reintroduce the question that comment exists to close.

The plane already carries the other two halves of document work — `POST /agent-actions/spec/documents`
(submit) and `.../rename`. Creation joins them, deriving identity from `get_agent_actor` exactly as
they do.

**Rejected:** a `?as=agent` parameter or an actor field in the body, for the reason quoted above.

### D2 — The route accepts no path, and no way to influence one

`rename_document` already argued this, and the argument transfers without modification:

> *"It is not an oversight that there is no way to pass a path: `validate_spec_path` is the single
> control keeping a document from being written to an arbitrary location beneath `spec/`, and a
> rename that accepted a destination would expose that control to the least trusted caller in the
> system as its only guard. Deriving a slug makes a traversal, a hidden segment or a different
> filename unexpressible rather than merely rejected."*
> — `hub/hub/spec_service.py:626-633`

If creation accepted a path, an agent could aim it at `spec/capabilities/agent-charter/spec.html`.
`validate_spec_path` would pass it — the path is well-formed — and the placeholder write would
destroy a capability document that `save_document:128` was carefully built to protect. The write
gate would have been walked around by the create gate.

**Rejected, and this is the sharper call: deriving the path from a subject at creation time.** It is
tempting, because `spec_naming.document_path_for(subject)` exists and the agent usually knows roughly
what the document is about. But a derived slug is still caller-influenced placement: an agent
submitting the subject "Agent charter" lands on the existing capability document's path. That
collision is refused by `is_taken`, so nothing is destroyed — but it is refused by a uniqueness check
rather than by design, and the difference matters when the corpus is large and the collision is
partial.

The agent creates nameless and calls `rename_spec_document` once the subject is established. That is
the flow the product already documents, and it means the agent reaches a real name through a route
that already refuses approved documents and already handles collisions.

### D3 — `kind` is fixed to `change-spec` at creation

Not validated-and-refused: **not offered**. The route takes no `kind` parameter.

The immediate reason is a trap. `create_document` sets `phase=CURRENT` when `kind == "capability"`
(`hub/hub/spec_lifecycle.py:151`) — *"this is the only place a document's phase is ever set there"*.
An agent permitted to pass `kind` could mint an empty capability document sitting in `current`, and
then find every subsequent `submit_spec_document` refused by `save_document:128`. Creation would
succeed and the document would be permanently unfillable: the worst available failure, because it
looks like success.

The broader reason is that the other three kinds are statements about the corpus rather than
contributions to it. `baseline`, `roadmap` and `system-map` describe what the project *is* and how it
is arranged — and once `corpus-aware-documents` lands, `system-map` is the kind an area document
uses, so an agent minting one would be rearranging the project's own map. `change-spec` is the one
kind whose entire lifecycle — exploring, proposed, approved, archived — is built to be filled in by
an agent and gated by the operator at every transition.

Relaxing this later is a small, separate decision. Starting permissive and narrowing is not.

### D4 — No approval step, because the ask was that the agent not stop

Three options were weighed during exploration:

| | gates the corpus | matches the ask | cost |
|---|---|---|---|
| **Agent creates directly** | already, at the write layer | ✅ | one route, one tool |
| Request + operator accepts | yes | ✗ blocks the agent mid-flow | new card, queue, notification |
| Create into `unfiled` staging | **no — the gate is illusory** | ✅ | a new flag, to make it real |

The staging option was proposed and withdrawn within one exchange, and the withdrawal is worth
recording so it is not re-proposed: the document tree is disk-driven (`GET /specs` walks `spec/`),
so an unfiled document is **already visible**; any created document needs a row or `save_document`
cannot write its file; and a row is filed by the next reindex. There is no "accept" step to attach
anything to. Manufacturing one means inventing a flag, which is a larger claim than the feature
earns.

`POST /agent-actions/agents/request` (`agent_actions.py:488`) is the propose-and-accept shape the
product already has, and it is the right shape for adding an agent to a roster — an act with a
standing cost. A document has no standing cost.

### D5 — No project allowance gate, and the line where that would change

Jobs are gated by `project.allow_agent_jobs`, default `False` (`hub/hub/api/v1/jobs.py:40`). Tasks,
messages, questions, evidence and checkpoint notes are not gated at all. Documents belong with the
second group, and the distinction is spend: a job is a standing instruction that invokes a model on
a schedule, and an agent that can create one can commit the operator's money indefinitely. A
document is a file and a row that cost nothing to hold and nothing to delete.

**What would change this judgement:** volume. An agent in a loop creating documents faster than an
operator reads them is a real failure mode, and the honest position is that no evidence exists yet
about whether it happens. The correct response, if it does, is a rate or count bound with a stated
reason — not a standing off-switch that makes the feature unavailable by default and therefore
untested.

### D6 — Both statements of the old rule are retired together

The rule lives in two places: `mcp_server.py:905` (the tool description the model reads) and
`agent_actions.py:1158-1162` (the 404 an agent hits). Changing one leaves the product contradicting
itself in exactly the place a confused agent looks.

The 404 keeps existing — submitting to a path with no document is still an error — but it stops
saying the operator must be the one to fix it. It says to create the document.

### D7 — The tool's description carries the flow, because the flow is now three calls

`create_spec_document` → work out the subject → `rename_spec_document` → `submit_spec_document`.

The middle step is not mechanical, and the existing descriptions already teach this well:
`rename_spec_document` says *"Use the new path for anything else you do with this document in this
turn"*. The new tool's description states the sequence and says plainly that the path it returns is a
placeholder, not a name.

## Risks

**An agent creates a document instead of thinking.** The cheapest artefact tends to become the
default response. Mitigated only by the tool description, which is an instruction rather than an
enforcement — the same category of protection as *"never write specification HTML yourself"*.

**Placeholder-named documents accumulate.** An agent that creates and never renames leaves
`spec/crimson-griffin/` behind. Nothing breaks; the corpus gets untidy. Worth a look after real use
rather than a mechanism now.

**The `kind` decision looks arbitrary from outside.** An operator who wants an agent to draft a
roadmap will find it refused with no obvious reason. The refusal must name the permitted kind rather
than only the forbidden one.

## Migration plan

1. Route and schemas, refusing nothing an agent can express because there is nothing to express.
2. MCP tool.
3. Both old statements of the rule retired, in the same commit, so no build has one without the
   other.

No data migration and no compatibility window: the tool is additive, and the two reworded strings
are read by models, not parsed by code.

## Open questions

- **Should `create_spec_document` accept an optional `title` for the placeholder payload?**
  `POST /project/documents` does (`body.title or UNTITLED`). It would give the operator something
  readable in the rail before the rename lands. It is not placement, so D2 does not forbid it.
  **Recommendation: yes**, as a plain string on the payload only, never touching the path.
- **Should the response include the standard next step?** The tool returns a path the agent must
  then rename. Returning a `next` hint is either helpful or patronising depending on the model, and
  the existing tools do not do it. **Recommendation: no** — keep the shape consistent, put the flow
  in the description.
- **Does an agent creating a document need to state why?** A reason recorded on the creation event
  would make an accumulating pile of placeholder documents diagnosable. It is also one more required
  argument on a tool whose point is not stopping. Undecided.
