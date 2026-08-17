# Design — rigor-gated editing, in-position proposals, authoring scope

## D1 — Where the gate lives: `spec_service.save_document()`, not a new MCP tool

`submit_spec_document` (`hub/hub/mcp_server.py:800-893`) stays the one tool an agent calls to change a
document, at any rigor. `save_document()` (`hub/hub/spec_service.py:58-173`) is the single place every
submission already flows through, and it already branches on phase (refusing when `approved`,
`:96-100`). F1 adds a second branch, read from `document.rigor`:

- `rigor == "sketch"` (the default, `DEFAULT_SPEC_RIGOR`, `models.py:1574`) → unchanged: write
  immediately via `spec_documents.write_document` + `spec_lifecycle.record_content`, exactly today's
  path.
- `rigor in ("contract", "gate")` → do not write. Diff the incoming payload against the document's
  currently stored structured content (same structured payload the read path already returns —
  `read_spec_document`'s `requirements`/`summary`/`problem`/`scope`/`design`/`tasks`/`algorithms`/
  `open_questions`, `agent_actions.py:947-1030`) and create one `SpecEditProposal` row per changed
  unit. Return a `ProposeResult` (new response shape, sibling of the existing `SaveResult`) naming
  which proposals were created and which units were unchanged (no proposal needed).

Rejected: a new MCP tool (`propose_spec_document`) alongside `submit_spec_document`. Two tools with
overlapping payload shapes, differing only by which one an agent must remember to call at which rigor,
is a footgun the existing single-tool-plus-server-side-branch design avoids — the agent's job is to
describe the change; whether it applies immediately or waits for acceptance is the document's
property, not the caller's choice.

## D2 — Unit grain: one requirement, or the whole metadata bundle

14.12 asks for "in-position proposals, individually acceptable." The natural in-position anchor
already exists for requirements — 14.1's stable identifiers (`spec_document_authority`'s "The Hub
mints requirement identifiers and they are stable", `spec.md:92-131`) — so a requirement-level
proposal has a real place to render itself: at that requirement. The non-requirement fields (summary,
problem, scope, design, tasks, algorithms, open questions) have no equivalent stable per-field
identity today, and inventing one purely to split them further is exactly the "general diff/merge
engine" the proposal explicitly declines to build. They are therefore one unit, anchored at the
document's summary/problem/scope section (the first thing a reader sees, per
`spec-document-authority`'s "A rendered document is ordered and complete for a reader",
`spec.md:752-781`).

Diff mechanics, concretely:
- Requirement units: match by requirement id. An id present in both old and new with different
  content → one `modify` proposal. An id in new but not old → one `add` proposal. An id in old but not
  new → one `remove` proposal. Unchanged content, same id → no proposal.
- Metadata unit: if any of the seven metadata fields differ, one `modify` proposal covering the whole
  bundle (matching what the submission actually sent — no partial-field proposals inside the bundle).
- No changes anywhere → the submission is accepted with zero proposals created and no error; this is
  not a failure, an agent re-submitting identical content should not be told it did something wrong.

## D3 — Data model

New table `spec_edit_proposals`:

| column | type | notes |
|---|---|---|
| `id` | str PK | `generate_id()`, matching every other table |
| `document_id` | FK → `spec_documents.id` | indexed |
| `unit_kind` | `"requirement" \| "metadata"` | |
| `unit_key` | str | requirement id, or the literal `"metadata"` |
| `change_kind` | `"add" \| "modify" \| "remove"` | |
| `proposed_payload` | JSON | just this unit's new content |
| `previous_payload` | JSON, nullable | this unit's content at proposal time (null for `add`); lets the UI render a diff without re-fetching the pre-proposal document |
| `expected_digest` | str | `document.content_digest` at proposal time — the staleness check (D5) |
| `status` | `"pending" \| "accepted" \| "rejected" \| "stale"` | terminal once non-pending |
| `proposer_actor_kind` / `proposer_actor_name` / `proposer_run_id` | str / str / str, nullable | mirrors `SpecDocumentEvent`'s existing actor fields, captured at creation |
| `created_at` | datetime | |
| `resolved_at` | datetime, nullable | |
| `resolved_by_actor_name` | str, nullable | always an operator name — enforced in code (D4), not by a constraint, matching how `set_rigor`'s operator-only check is enforced in `spec_rigor.py` rather than in the schema |
| `resolution_reason` | str, nullable | |

Indexed on `(document_id, status)` for "list this document's pending proposals" — the query every
render of the document performs.

Migration: new table only, no existing column touched, no `CheckConstraint` naming a column (the
`models.py:1637-1640` SQLite trap this session's own N2 migration (0074) already had to work around
does not apply here — `status`/`unit_kind`/`change_kind` are validated the same way `SPEC_RIGORS` is,
refused on the way in by the one writer function, not by a table-level CHECK). Guard for a missing
table the way 0033/0034/0073/0074 do. Bump the head assertions in both `hub/tests/test_migrations.py`
and `hub/tests/test_project_persistence.py` (CLAUDE.md).

## D4 — Attribution and the accept/reject API

Accept and reject are operator-only, enforced in the function that performs them (mirroring
`spec_rigor.set_rigor`'s `actor.kind != "operator"` refusal, `spec_rigor.py:88-93`), not only at the
API boundary — the same discipline `spec_lifecycle.transition` already applies to `approved`/
`archived` moves, and the standing rule this run must not weaken (`STATE.json` `limits`).

New functions in `spec_service.py` (co-located with `save_document`, the function they extend):

- `async def propose_edit(session, workspace, document, raw_payload, *, actor) -> ProposeResult` —
  D1/D2's diff-and-record. Called from `save_document` when rigor gates, not from a new route.
- `async def accept_proposal(session, document, proposal, *, actor, expected_digest=None) -> SaveResult`
  — refuses if `actor.kind != "operator"`; refuses if `proposal.status != "pending"`; refuses if
  `document.content_digest != proposal.expected_digest` (D5); otherwise applies `proposed_payload` to
  the live document at `unit_key`, calls `spec_lifecycle.record_content` with **both** actors (new
  optional `accepter` parameter, additive — existing single-actor callers unaffected), sets
  `status="accepted"`, `resolved_by_actor_name`, `resolved_at`.
- `async def reject_proposal(session, proposal, *, actor, reason="") -> None` — same operator check;
  sets `status="rejected"`, `resolved_by_actor_name`, `resolution_reason`; touches nothing else. The
  live document was never written for this proposal, so "no residue" is automatic, not a cleanup step.

API routes, following the existing split (agent-side in `agent_actions.py`, operator-side in
`spec.py`) and the rigor route's own shape (`RigorRequest` with `expected_digest`,
`spec.py:301-342`):

- Agent-side: none new. `POST /spec/documents` (existing `SpecDocumentSubmission` route) is the only
  entry point; D1's branch inside `save_document` is invisible at the API layer.
- Operator-side, in `spec.py`:
  - `GET /documents/{path}/proposals` — pending proposals for a document, each carrying `unit_kind`,
    `unit_key`, `change_kind`, both payloads (for rendering a diff), proposer identity, `created_at`.
  - `POST /documents/{path}/proposals/{id}/accept` — body `{reason?, expected_digest?}`.
  - `POST /documents/{path}/proposals/{id}/reject` — body `{reason?}`.

## D5 — Staleness over silent overwrite

`expected_digest` is captured at proposal-creation time. Between then and acceptance, the document's
`content_digest` can move for reasons unrelated to this specific proposal — another proposal on the
same document accepted first, an operator's own direct edit, a rigor change. Accepting against a
moved digest is refused (`status` becomes `stale`, matching how `spec_rigor.set_rigor`'s own
compare-and-swap already behaves at `spec_rigor.py:96-104`) rather than applied blind — the same
"drift is reported, not silently resolved" discipline `requirement-traceability`'s "A changed
implementation raises a candidate, never an edit" already commits to for a different kind of drift
(`spec.md:257-298`). A stale proposal is not resurrected automatically; the agent's next submission
against the (now current) document produces a fresh diff and fresh proposals, superseding it. The
stale row itself is left as history, imitating `SpecRigorEvent`'s append-only pattern rather than
being deleted.

## D6 — F4's mechanism, and why per-turn rather than per-agent

`runner_commands.py:35` already appends `--allowedTools "mcp__agentweave__*"` when a run's MCP server
is configured — an existing precedent for a per-run, additive tool-surface flag built by this exact
module. F4 adds a second, subtractive one, gated on whether *this turn* was triggered with
`spec_document` set (`agent_trigger.py:267`, already threaded through `trigger_agent_directly` for the
prompt-notice purpose and now read a second time by `build_command`):

- Claude: `--disallowedTools "Edit,Write,NotebookEdit"` appended to `cmd`, the direct sibling of the
  existing `--allowedTools` line.
- Codex: force `--sandbox read-only`, overriding whatever posture the run would otherwise receive
  (`runner_commands.py:283`'s `workspace-write` default, or an operator-chosen posture) — for this
  turn only, not a persistent change to the run's configured sandbox.

Per-turn, not per-agent, because the same agent identity can be triggered both with and without a
document open (an operator may ask the same agent a coding question in one turn and a spec question in
the next); the restriction is a property of what the turn is about, not who is answering. This mirrors
how `_spec_phase_for` already treats `spec_document` as per-call state, not agent state.

Rejected: gating on `document.rigor` the way F1 does. 14.14 is a role-boundary claim ("authoring
assistance" should not "perform" implementation) independent of how strict the document's enforcement
is — a `sketch`-rigor exploration is exactly where an agent is most likely to go off and "just fix it"
instead of writing down that it needs fixing, so gating F4 on rigor would remove the restriction
exactly where the boundary matters most.

`create_task` (`mcp_server.py:212-251`) is unaffected by F4 — it is an MCP tool call, not a file
write, so it remains the turn's sanctioned outlet for anything discovered. `spec_turn_notice()`
(`launchability.py:222-264`) gains a line stating this once F4 is mechanically true, so the agent is
told rather than surprised by a refusal.

## D7 — 14.15's retirement, recorded

`aw-spec-explore`, `aw-spec-propose`, `aw-spec-apply`, `aw-spec-reindex`, and `aw-verify` are deleted
skill templates the product moved past when the Hub-owned spec flow (`submit_spec_document` and
siblings, MCP tools) shipped. CLAUDE.md's "Still prohibited" table already forbids invoking the
surviving `aw-*` skills at all (`aw-delegate`, `aw-status`, `aw-relay`, `aw-setup-*`) as "product
source... predating the Hub-owned flow", the identical status these five spec skills would have if
they still existed. 14.15 asking to make them "reachable from the workspace" is asking to reverse a
decision this repository's own instructions already made, not to close a gap. No spec delta encodes a
retirement — there is nothing in any capability spec naming these skills to remove. The record is this
document, plus `tasks.md`'s closing task updating `2026-07-30-hub-native-experience/tasks.md`'s 14.15
line once this change lands.

## Open questions

None — every open question this change's shape depends on (unit grain, gate location, attribution
shape, per-turn vs per-agent scoping) is resolved above with a stated rejected alternative. The
spec-round protocol (`STATE.json`) exists for a reviewer to find ones this pass missed.

---

# Round 1 — authored, 2026-08-17 (iteration 23)

Proposal, this design, tasks.md, and the `spec-document-authority` delta written cold against
`2026-07-30-hub-native-experience` tasks.md's 14.11/14.12/14.14/14.15 wording and this session's own
iteration-22 verification pass, plus fresh grounding reads of `spec_service.py`, `spec_rigor.py`,
`spec_lifecycle.py`, `models.py`, `runner_commands.py`, `agent_trigger.py`, `launchability.py`, and the
Spec Author charter (via a research-only subagent pass, facts cited above with file:line).
`openspec validate 2026-08-17-authoring-rigor-and-scope --strict` passes; `--changes --strict` 9/9;
`--specs --strict` unchanged at 31/31 (delta not yet merged). Cap is 3 rounds (`STATE.json`
`spec_round_protocol.cap`); at cap, or earlier reviewer approval, approve and execute in the same run
per this session's binding change to that protocol. Next: a cold round-2 review (not a continuation of
this authoring context) against D1-D7 and the six ADDED requirements, checking in particular whether
D2's metadata-bundle grain and D6's per-turn (not per-rigor) scoping for F4 hold up, and whether task
3.2's `record_content`/attribution-shape decision needs settling before implementation rather than
during it.
