# Gate spec edits by rigor, make proposals in-position, and keep authoring in its lane

## Why

`openspec/changes/2026-07-30-hub-native-experience/tasks.md` section 14 (specification traceability
and authoring) was scenario-verified in full this session (`.claude/autonomous/2026-08-16-spec-corpus-and-jobs-log.md`,
iteration 22). 11 of 19 items are real, shipped behaviour in the four capability specs that now exist
(`requirement-traceability`, `spec-document-authority`, `spec-chat-session`, `task-lifecycle-governance`
— none existed when section 14 was written). Three items were confirmed as genuine, unbuilt product
surface, and one as a superseded design that needs retiring rather than implementing. This change is
those four, together, because all four sit in the same place — how an agent's edit to a specification
document reaches the live document, and what an authoring turn is and is not allowed to do.

**14.11** ("Make agent edits direct on sketches and proposals on contracts and gates; attribute
accepted changes to both proposer and accepter.") **is unbuilt.** Verified this session:
`hub/hub/spec_service.py:save_document()` (`:58-173`) applies every agent submission to the live
document unconditionally, the instant it arrives, for every phase except `approved` (`:96-100`).
`document.rigor` is read only when rendering (`:129-137`, "never from the submission") — it plays no
role in whether an edit applies. `SPEC_RIGORS = ("sketch", "contract", "gate")`
(`hub/hub/db/models.py:1573`) already exists as a value the operator can set
(`hub/hub/spec_rigor.py:set_rigor`, operator-only, `:88-93`), but nothing downstream of it changes
behaviour. A `gate`-rigor document — the strictest tier, promoted only once its requirements hold
stable identifiers (`spec_rigor.py:promotion_blockers`, `:109-178`) — is edited by one agent call with
exactly the same immediacy as a brand-new sketch.

**14.12** ("Build authoring against a visible document: in-position proposals, individually
acceptable, rejection leaving no residue.") **is unbuilt — there is no proposal concept at all.**
Grepping `hub/hub/db/models.py` and every `hub/hub/*.py` module for "proposal", "pending_edit", and
"draft" returned no matches. The only existing precedent for "someone proposes, someone else accepts,
and both are attributed" in this codebase is `TaskTransition`
(`hub/hub/db/models.py:698-761`, `actor_kind`/`run_id`/`actor_agent`/`origin`) — built for the same
author/reviewer separation problem on the task board (`openspec/changes/2026-08-10-task-transition-machine/`)
because a task's `updated_by_run_id` is a single mutable column that cannot answer "who approved
this?" `SpecDocumentEvent` has the identical limitation for documents: single-actor per row
(`kind`/`actor_kind`/`actor`/`origin`, `models.py:1722-1739`).

**14.14** ("Scope authoring assistance to specifications; discovered implementation work is proposed,
not performed.") **is unbuilt, and the existing "enforcement" is prose only.** The Spec Author charter
(`hub/hub/data/charters/spec.md`, "The Boundary On Yourself" and "Anti-Patterns" sections) already
says "you are working out what to build, not building it" and calls implementing-instead-of-specifying
an anti-pattern — but this is a text block competing for the model's attention alongside everything
else in the prompt, the same failure mode `launchability.py`'s own module docstring names as the
reason `spec_turn_notice()` exists at all (`hub/hub/launchability.py:224-234`). Verified: tool access
built for a spawned run (`hub/hub/api/v1/agent_trigger.py`, `runner_commands.py`) is uniform
regardless of whether a specification document is open in the turn — `access_path_notice()`
(`launchability.py:267-283`) varies only by MCP-vs-none, never by turn kind. An agent authoring a
specification can call `Edit`/`Write`/`Bash` exactly as freely as one doing ordinary development,
despite `spec_document` already being threaded per-turn through `trigger_agent_directly`
(`agent_trigger.py:267`) for the prompt-notice purpose. `create_task` already exists as an MCP tool
(`hub/hub/mcp_server.py:212-251`) an agent could use to propose discovered work instead — nothing
requires or channels it there.

**14.15** ("Make `aw-spec-explore`, `aw-spec-propose`, `aw-spec-apply`, `aw-spec-reindex`, and
`aw-verify` reachable from the workspace; invert `aw-verify` to attach evidence to requirements.")
**is not a gap — it is a rejected design that needs to be recorded as retired, not implemented.**
`submit_spec_document` and its siblings are MCP tools today (`hub/hub/mcp_server.py`), not skills, and
CLAUDE.md's "Still prohibited" table already rules out invoking the `aw-*` skills at all — the item
asks to make a superseded surface "reachable" when the product direction has already moved past it.

## What Changes

- **F1 — rigor gates whether an edit applies directly or becomes a proposal.** `sketch` (the default)
  is unaffected: an agent's `submit_spec_document` call continues to apply immediately, exactly as
  today. At `contract` or `gate` rigor, the same call no longer writes the live document — it diffs
  the incoming payload against the stored one and records one pending, individually addressable
  `SpecEditProposal` row per changed unit (each added/modified/removed requirement by its stable
  identifier, plus one row for the non-requirement metadata bundle — summary, problem, scope, design,
  tasks, algorithms, open questions — treated as a single unit; see design.md D2 for why that grain
  and not finer). The live document does not change until an operator accepts.
- **F2 — proposals render in position and accept/reject individually.** A pending proposal against a
  requirement is discoverable at that requirement, not only in a separate queue; the metadata proposal
  sits at the document's summary/problem/scope section. Accepting or rejecting one proposal never
  touches another pending proposal on the same document. Rejecting leaves the live document exactly as
  it was — the rejected content never touched a requirement or the metadata bundle, so there is
  nothing on the document itself to clean up.
- **F3 — dual attribution, and staleness instead of silent overwrite.** An accepted proposal's
  resulting content-change event names both the proposer (the actor whose submission created the
  proposal) and the accepter (the operator who accepted it) as distinct fields, imitating
  `TaskTransition`'s existing author/reviewer shape rather than `SpecDocumentEvent`'s single-actor
  one. If the document's stored content moves after a proposal is created — another proposal accepted
  first, a rigor change, a direct edit while still at `sketch` before promotion — accepting the now-
  stale proposal is refused rather than applied against content it was never diffed against, the same
  compare-and-swap discipline `spec_rigor.set_rigor`'s `expected_digest` already uses.
- **F4 — authoring turns lose file-write tools, mechanically, not by prompt.** When a turn is
  triggered with a specification document open (`spec_document` already threaded through
  `trigger_agent_directly`), the spawned run's command gains an explicit write restriction — for
  Claude, `--disallowedTools` naming the file-editing tools, the sibling of the `--allowedTools` flag
  already appended at `runner_commands.py:218`; for Codex, the run's sandbox is forced to
  `--sandbox read-only` for that turn regardless of the run's configured posture. `create_task`
  remains available (it is an MCP tool, not a file-editing one) and becomes the turn's sanctioned path
  for anything the agent discovers that needs code to change. `spec_turn_notice()` states the
  restriction explicitly once it is mechanically true, so an agent is told why a write was refused
  rather than discovering it by failure. This applies whenever a document is open, independent of its
  phase or rigor — 14.14 is a role boundary, not a rigor-gated one.
- **F5 — retire 14.15.** Recorded in `design.md` as a superseded design, with the citations above.
  Once this change is implemented, `2026-07-30-hub-native-experience/tasks.md`'s 14.15 line is updated
  from "confirmed superseded design, needs re-wording" to a waived, cited closure pointing at this
  change — a task in this change's own `tasks.md`, not a separate change.

## Non-Goals

- **Not a general diff/merge engine.** The unit granularity is fixed at "one requirement" or "the
  whole metadata bundle" — not per-sentence, per-field-within-metadata, or per-line. Splitting the
  metadata bundle further is a plausible future refinement, not required to satisfy 14.12's "in-
  position" and "individually acceptable" wording, which is satisfied at requirement grain.
- **Not changing what `sketch` rigor documents can do.** They are explicitly unaffected by F1 — the
  entire point of rigor-gating is that early, low-stakes documents keep today's fast direct-apply
  loop.
- **Not touching `spec_rigor.py`'s promotion/demotion rules.** F1 reads `document.rigor`; it does not
  change when a document is allowed to move between rigor tiers.
- **Not restricting Bash entirely during a spec turn.** F4 removes file-editing tools only — an agent
  can still read the repository, run tests, or otherwise ground a proposal in real code. Only
  *performing* the implementation is scoped away, not reading around it.
- **Not building a UI queue/inbox for proposals across documents.** F2 is in-position discovery on the
  one open document; a cross-document proposals list is not part of this change.
- **Not re-implementing the deleted `aw-spec-*` skills under any name.** F5 retires 14.15, it does not
  satisfy it under different branding.
