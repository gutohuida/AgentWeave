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

**Corrected at round 2: the diff anchor is the requirement's `key`, not its minted identifier.**
Round 1 wrote "match by requirement id" throughout this section; that is wrong, and would have sent
an implementer looking for something that does not exist yet. `spec_payload.py`'s `Requirement.key`
is what an agent's submission actually carries ("Stable handle for this requirement... It is not the
identifier and never appears in a link", `spec_payload.py:68`); the public identifier (`FR-N`) is
minted by `spec_identity.mint()` **only inside `save_document`'s write path** (`spec_service.py:110-127`),
which F1 explicitly does not run for a `contract`/`gate` submission — that write is the thing being
gated. A brand-new requirement in a proposal therefore has a `key` and no identifier at all until the
proposal is accepted and the normal mint-on-write path finally runs. This is not a workaround; it is
consistent with 14.1's own rule that identifiers are Hub-minted, never agent-supplied — a proposal
would be letting an agent supply one that early. `spec_reading.requirement_view` already returns both
`key` and `identifier` per requirement (`spec_reading.py:146-158`), so the read side has the same
anchor available for matching.

Diff mechanics, concretely:
- Requirement units: match by requirement **key** (present on both the submitted payload's
  `Requirement.key` and the stored document's requirement entries — see correction above). A key
  present in both old and new with different content → one `modify` proposal, `unit_key` = that key.
  A key in new but not old → one `add` proposal, `unit_key` = that key (no identifier yet — one is
  minted only at acceptance, when `accept_proposal` applies the unit through the normal
  `save_document`/`spec_identity.mint` path). A key in old but not new → one `remove` proposal,
  `unit_key` = that key. Unchanged content, same key → no proposal.
- **Where an `add` proposal renders "in position" (round 2 addition — round 1 did not say):** an
  added requirement has no existing row to anchor at. `SpecEditProposal` (D3) gains a nullable
  `position_after_key` column, set from the submitted payload's own ordering — the key of the
  requirement immediately preceding the new one in the submission's requirement list, or null if it
  was submitted first. The UI renders it inline after that key (or at the top, if null), same as the
  submission itself implied. Rejected: a numeric index into the live document, because the live
  document may have gained or lost requirements from other accepted proposals by the time this one
  renders, and an index would then point at the wrong neighbour; a key-relative hint degrades to "render
  near there" instead of silently pointing at the wrong place. Rejected: no position at all
  (render every `add` proposal in one pile at the end) — cheaper, but 14.12's own wording is
  "in-position," and a proposal literally inventing a new requirement's neighbour is exactly where a
  reviewer benefits most from seeing it where the agent meant it to go.
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
| `unit_key` | str | the requirement's **key** (D2 correction — not its minted identifier, which an `add` proposal does not have yet), or the literal `"metadata"` |
| `change_kind` | `"add" \| "modify" \| "remove"` | |
| `position_after_key` | str, nullable | `add` proposals only (D2): the key of the requirement this one was submitted immediately after, or null for "first". Unused for `modify`/`remove`/`metadata`, which already have a live position to anchor at. |
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
  the live document at `unit_key`, calls `spec_lifecycle.record_content` (see the settled question
  below — no new `accepter` parameter), sets `status="accepted"`, `resolved_by_actor_name`,
  `resolved_at`.

**Round 2 settles task 3.2's open question, rather than leaving it for the implementer.** `record_content`
does *not* grow an `accepter` parameter, and `SpecDocumentEvent` (`models.py:1721-1761`) is not
touched — it has single `actor_kind`/`actor`/`run_id` columns with no room for a second identity
short of a schema change, exactly as 3.2 suspected. But `SpecEditProposal` (D3, above) already *is*
the durable record of both identities: `proposer_actor_kind`/`proposer_actor_name`/`proposer_run_id`
at creation, `resolved_by_actor_name` at acceptance. Duplicating that onto `SpecDocumentEvent` would
be two copies of the same fact that can drift. Instead: `record_content` gains one small, genuinely
additive parameter — `extra_detail: Optional[Dict[str, Any]] = None`, merged into the `detail` dict
it already builds (`spec_lifecycle.py:180-187`, currently hardcoded to
`{"requirements": sorted(digests)}}` — `SpecDocumentEvent.detail` is already a JSON column,
`models.py:1746`, so this needs no migration). `accept_proposal` is the only caller that passes it,
with `{"proposal_id": proposal.id, "proposer_actor_kind": proposal.proposer_actor_kind,
"proposer_actor_name": proposal.proposer_actor_name}`. The event's own `actor` field is the accepter
(the operator who caused this specific write, consistent with every other content-write event —
"who wrote the file" is what that field has always meant); the proposer is one hop away via
`proposal_id`, on the row built to hold it. Existing callers of `record_content` are byte-for-byte
unaffected (the new parameter defaults to `None`, merging nothing).
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
`spec_document` set.

**Round 2 correction to the plumbing claim.** Round 1 said `spec_document` is "already... read a
second time by `build_command`" — checked directly against `runner_commands.py` and that is not true
today. `spec_document` is a parameter of `trigger_agent_directly` (`agent_trigger.py:267`), used
there for `_spec_phase_for`/`spec_turn_notice` — but the actual `build_command(...)` call at
`agent_trigger.py:500` does not pass it, and `build_command`'s own signature (`runner_commands.py:106-115`)
has no such parameter. Task 5.1 already describes adding it correctly ("threaded from
`agent_trigger.py:267`"); this is a correction to the design's prose, not to the task list — but a
round-2 reader should not be told the plumbing is already there when it is one hop short.

**Round 2 addition: the interaction with `yolo` was unaddressed and is a real hole, not a nuance.**
Both runner branches choose between two *different flags* depending on `yolo`, not one flag with a
variable value — F4 must check `spec_document` **before** that choice, not layer on top of whichever
branch `yolo` already picked:

- Claude (`_build_claude_command`, `runner_commands.py:218`): the existing line reads
  `if not yolo: cmd += ["--allowedTools", "mcp__agentweave__*"]` — under `yolo=True` today, a
  tool-surface-restricting flag is *skipped entirely*. If F4 followed that same pattern (`if not
  yolo and spec_document: cmd += ["--disallowedTools", ...]`), a yolo-configured agent would keep
  full `Edit`/`Write` access on a spec-authoring turn, silently defeating 14.14's SHALL for exactly
  the run posture likeliest to act on a discovered fix instead of proposing it. F4's rule: append
  `--disallowedTools "Edit,Write,NotebookEdit"` whenever `spec_document` is set, **unconditionally,
  including under `yolo=True`**. This is a deliberate divergence from the `--allowedTools` line right
  above it — `yolo` governs whether *permitted* tools need a permission prompt; F4 governs which
  tools are permitted at all, a different axis, and 14.14's requirement text (spec delta, below)
  states no `yolo` exception.
- Codex (`_build_codex_command`, `runner_commands.py:280-283`): `if yolo: cmd +=
  ["--dangerously-bypass-approvals-and-sandbox"] else: cmd += ["--sandbox", "workspace-write"]` —
  these are mutually exclusive flags to the Codex CLI, not a default value F4 can override in place.
  Appending `--sandbox read-only` *alongside* `--dangerously-bypass-approvals-and-sandbox` would ship
  a broken or ambiguous command line, not a restricted one. F4's rule: when `spec_document` is set,
  this whole `if yolo / else` branch is skipped and replaced with `--sandbox read-only` — the
  `spec_document` check runs first and is exclusive with the `yolo` branch, not additional to it.

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

None. Round 1 said the same, and round 2 (below) found that untrue in three concrete places — this
line is worth keeping honest rather than restating: every question round 2 raised has since been
resolved in D2/D3/D4/D6 above, each with a stated rejected alternative. Nothing is left deferred to
implementation time.

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

---

# Round 2 — cold review, 2026-08-17T05:34+01:00 (iteration 24)

Read `proposal.md`, this design (as round 1 left it), `tasks.md`, and the `spec-document-authority`
delta fresh, then verified round 1's grounding claims against the actual code rather than trusting the
citations — `spec_service.py`, `spec_rigor.py`, `spec_identity.py`, `spec_payload.py`,
`spec_reading.py`, `spec_lifecycle.py`, `models.py`, and `runner_commands.py`/`agent_trigger.py` were
all re-read directly. **This was not an approval pass — three concrete, code-grounded defects survived
to this point, plus the one open question round 1 flagged as needing a decision.** All four are fixed
in this same round, in place, not deferred:

1. **D2's "match by requirement id" was wrong, and the spec delta's requirement text repeated the
   error.** Verified: `spec_payload.py`'s `Requirement.key` — not an identifier — is what an agent's
   submission carries ("It is not the identifier and never appears in a link"); the public identifier
   is minted only inside `save_document`'s write path (`spec_service.py:110-127`), which F1's whole
   premise is that a `contract`/`gate` submission does *not* reach. As written, an `add` proposal (a
   brand-new requirement) would have needed to match "by id" against an id that cannot exist yet.
   Fixed: the diff anchor is `key` throughout D2/D3; the identifier is minted at acceptance, when the
   normal write path finally runs. `spec-document-authority`'s delta (below) is corrected to match —
   round 1's requirement text said "identified by its stable requirement identifier", which would have
   shipped the same wrong claim into the capability spec itself.
2. **No in-position anchor existed for `add` proposals**, despite F2/14.12 promising "in-position."
   Fixed: `SpecEditProposal` gains `position_after_key` (D3), carrying the submitted ordering forward
   so a new requirement renders near where the agent placed it rather than in an undifferentiated pile.
3. **D6/F4 never addressed `yolo`, and both runner branches needed it addressed differently.** Claude's
   existing code skips a tool-restricting flag entirely under `yolo=True`
   (`if not yolo: cmd += ["--allowedTools", ...]`) — copying that pattern for F4 would have silently
   let a yolo-configured agent keep full file-write access on a spec-authoring turn, defeating 14.14
   for exactly the posture most likely to act instead of propose. Codex's `yolo` branch picks a
   *different flag* (`--dangerously-bypass-approvals-and-sandbox`), not a sandbox value — appending
   `--sandbox read-only` beside it rather than instead of it would have shipped a contradictory command
   line. Fixed in D6: Claude's restriction is unconditional; Codex checks `spec_document` before the
   `yolo` branch and replaces it outright when set.
4. **Task 3.2's open question is decided, not left open.** `SpecEditProposal` (D3) already carries full
   proposer and accepter identity with no schema change needed anywhere else — `record_content` does
   not grow an `accepter` parameter; it grows a small `extra_detail` merge-in, and `accept_proposal`
   cites `proposal_id` there so a reader hops from the event to the row that already holds both names.
   `SpecDocumentEvent` is untouched.

**What held up, unchanged:** D1 (gate lives in `save_document`, no second MCP tool) — sound, and the
one-tool-one-branch shape is the right call for the reason round 1 gave. D3's remaining columns, D4's
operator-only enforcement mirroring `spec_rigor.set_rigor`, D5's staleness-via-`expected_digest`
compare-and-swap (verified directly against `spec_rigor.py:96-104`'s existing implementation of the
identical pattern) — all checked against the real code and found accurately described. D7's retirement
of 14.15 — checked against CLAUDE.md's own prohibited-skills table — is correct as written.

**Verified after the fixes:** `openspec validate 2026-08-17-authoring-rigor-and-scope --strict` passes
(the spec delta's `unit_key`/identifier wording was the one place the fix needed to reach the delta
itself, not just design.md — done). `--changes --strict` 9/9, unchanged count. `--specs --strict`
unchanged 31/31 (delta still not merged — correct, this is still pre-implementation).

**Verdict: not approved as round 1 wrote it; approved as revised in this round.** Every defect found
was fixable in place, in this same pass, without reopening D1's or F1-F5's shape — no restart of the
authoring round-trip was needed. Per `spec_round_protocol`, a round that finds only fixable issues and
fixes them may proceed straight to the next round or to implementation in the same run rather than
forcing an artificial pause between rounds. This iteration stops here regardless — the fixes above are
substantial enough (a new column, a settled attribution mechanism, a security-relevant flag-ordering
correction) that they deserve their own cold look rather than being waved through by the same pass that
just wrote them. **Next: round 3**, a fresh cold read of the now-twice-revised artifact — focus
specifically on whether the `position_after_key`/`key`-based matching addition (item 1-2 above) is
internally consistent everywhere it now appears (D2, D3's table, tasks 2.1/2.3, the spec delta), and
whether `tasks.md`'s section 2/3/5 wording needs updating to match D2/D4/D6's revisions before
implementation starts (a quick pass — the design changed, the task list describing it was not touched
yet this round). If round 3 finds nothing beyond that reconciliation, proceed to approve-and-execute
per `spec_round_protocol.at_cap` in the same run.
