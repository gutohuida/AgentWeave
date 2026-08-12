# Design — The Hub owns the specification document

Decisions taken here, with the reasoning that produced them. Where a decision was the operator's,
the exploration section carrying their words is cited; where it is the agent's, it says so and is
reopenable.

## D1 — The document is a file, and there is no second copy

**Decision:** documents are read and written through `ProjectWorkspace.resolve_relative`. No cache
table, no snapshot table, no sync endpoint. (Operator: exploration §1.11.)

The cache existed for one stated reason — *"so the UI can display them without filesystem access"* —
and that reason is void in both deployment modes. `resolve_relative` already rejects absolute paths,
traversal, control characters and symlink escapes in one place, so it is the security boundary the
cache's path re-validation was providing.

**Why not keep the cache as a read-through:** two copies of a fact require a reconciliation rule for
the case where they disagree, and §1.3 forbids the Hub silently winning one. A cache would create the
conflict class the design then has to resolve. One authority per fact is cheaper than a good merge.

## D2 — JSON in, HTML out

**Decision:** `submit_spec_document(payload)` takes a structured object; the Hub validates and
renders. An agent never emits specification HTML. (Operator: §1.9; alternatives compared in §2.6.)

The rejected options are worth recording because both are plausible. *The agent writes HTML* puts a
713-line format contract in every model's context on every turn forever and fails in the ways
formats fail — tags, escaping, anchors, metadata drift — with a retry loop that burns tokens.
*Granular tools* (`add_requirement()` × 40) cannot emit an invalid document but costs ~40 round trips
and handles prose sections badly; the operator pushed back on it as too complex, correctly.

The complexity does not vanish under D2, it **moves**: paid once in tested Hub code instead of in
every model's context forever.

## D3 — The schema is the contract, and it is how the agent learns the format

**Decision:** the format is delivered as the tool's input schema, not as a document. (Agent proposal,
§2.10.)

This is what makes the skills' deletion safe. MCP delivers tool schemas to Claude and Codex alike, by
protocol, every turn, with no skills directory and no runner-specific path. A model does not need to
be *taught* the format; it needs to be *shown the tool*. A schema violation returns a field-level
error rather than a paragraph of prose about conventions.

## D4 — The payload is versioned; unknown fields survive a round trip

**Decision:** every payload carries `schema_version`. On read, fields the current version does not
define are preserved and re-emitted on write. (Agent proposal resolving §3.5.)

§3.5 is binding: the contract must not be frozen until gates and traceability have stated their
requirements on it. But the first slice *is* the contract, so deferring would deadlock. Versioning
resolves it — the only thing frozen is what must be permanent (D5), and a later change adds gate
fields to documents authored before gates existed.

§1.11 also lowered the cost of being wrong: the Hub is now the only reader and the only writer of the
format, and a format with one reader is migratable by that reader.

## D5 — The Hub mints requirement identifiers, and they outlive the text

**Decision:** the agent does not supply identifiers. The Hub assigns them, and an identifier survives
rewording of its requirement and any schema version change. Identifiers are never recycled. (§2.6;
forward commitment 1 of §7.)

An agent inventing identifiers reintroduces the drift they exist to remove — two documents, two
numbering schemes, the same requirement under different names. Changes 2 and 3 both point at these,
so instability here is not a cosmetic problem: it silently re-targets a task or an evidence link.

**Not recycling** matters for the same reason. If `FR-4` is deleted and a later requirement takes the
identifier, every historical reference to `FR-4` now points at something else, and the transition log
that recorded them becomes misleading rather than merely stale.

## D6 — The phase machine owns transitions, and the agent cannot approve

**Decision:** `exploring → proposed → approved` with entry conditions checked by code. Approval is
recorded from an operator action and by no other path. (§4; operator §1.7.)

Today `aw-spec-apply.md:33-51` implements the gate by instructing the agent to grep the document's
own status metadata and stop if it is not `approved` — the agent checking its own permission slip,
in a file the agent can write. `aw-spec-propose.md:279` says *"Never set approved without an explicit
user approval decision"*, which is a request, not a gate.

Under D6 an agent cannot express approval at all: there is no tool argument and no payload field for
it. This is the property §4 identifies as impossible for a skill to have.

**Phase lives on the document, not the conversation** (§2.7). The decisive argument is the referent:
with a conversation-level mode, "propose" and "approve" have no subject. Explore is the one phase
that would precede its document, which is why the entry point creates an empty document in
`exploring` rather than setting a flag.

## D7 — Validation is blocking, and it is the skills' self-check promoted

**Decision:** the checks in `aw-spec-propose.md:230-259` become Hub validators that refuse a
transition to `proposed`. (Agent proposal, §2.11.)

Every one of them is mechanical: anchors resolve, no duplicate identifiers, every requirement
referenced by at least one acceptance criterion, every task referencing at least one requirement,
modal verb present, non-goals non-empty, no unresolved clarification markers. Today the model is
asked to run them on itself and report — which is `unverifiable_claim` (§3.2) by construction.

**What stays judgment:** *"rewrite anything unfalsifiable — robust, user-friendly, as needed."* A
word list is a hint, not a gate, so this stays in the charter.

**Structural checks mostly disappear** rather than moving: under D2 the Hub emits the HTML, so dead
anchors and duplicate identifiers cannot occur.

## D8 — Events and digests ship before anything reads them

**Decision:** every write records an attributed event (actor, origin, run identifier where one
exists, what changed) and stores the document's content digest. Nothing in this change consumes
either. (Operator §1.3; §2.8; forward commitments 3–5.)

This is deliberate scope that looks like waste. The justification is that **neither can be
backfilled**: a change-4 telemetry query over history that began recording in change 4 reports on a
fraction of the work, and a digest that starts existing later cannot detect an edit made before it
did.

The digest does two jobs from one primitive (§2.8): the file digest detects an external edit, and the
per-requirement text digest detects that a requirement's *meaning* moved out from under evidence
accepted against the old wording — which change 3 needs.

**On a detected external edit this change reports and stops.** It does not merge, prompt, or
overwrite. §1.3 forbids the Hub silently winning, and the resolution interface is change 5.

## D9 — The procedure floor is code; the interviewing craft is the charter

**Decision:** the per-turn context carries a short, non-optional statement of the phase and the
agent's obligation in it. Interviewing skill stays in the charter. (Correction recorded in §2.1.)

§1.8 is the constraint — *"Not necessarily I want to use the charter for spec. Is good practice but I
can skip it"* — so nothing load-bearing may live there. "Grill the user before proposing" is two
things, and only one is judgment:

| | belongs to | optional |
|---|---|---|
| the obligation to interview | the phase machine | no — it is an exit condition |
| skill at interviewing | the charter | yes — degrades quality, not validity |

The floor is roughly five lines. The delivery channel exists: `agent_trigger.py:376-405` writes
`.agentweave/context/<agent>.md` every turn for both runners, and `agents.py:1015` already carries an
`### Open specification document` section.

**A spec-phase run binds the spec charter by default** unless the operator overrides — so "optional"
means "you may remove it", not "you must remember to add it".

## D10 — Explore exits on an operator action

**Decision:** in this version the `exploring → proposed` transition requires the operator to say
exploring is complete. (Agent proposal resolving part of §3.6 — reopenable.)

§4 states the exit as *"no unresolved clarifications; distilled notes exist"*, checked by code.
Whether "is this exploration complete enough to propose from" is mechanically checkable is exactly
what §3.6 leaves open. Making it an operator action is honest about that, puts no model in the path,
and holds against a blank charter.

The mechanical half still applies: the payload must validate (D7). The operator decides *readiness*;
code decides *validity*.

## D11 — Four requirements move rather than die with their capability

**Decision:** `spec-manifest-sync` is removed, but discovery, home-document selection, visible
degradation of an unreadable index, and subscriber refresh are re-stated in the new capability.
(Operator §1.13.)

These describe a **document tree**, not a sync. Their mechanism changes — the index is read from disk
and owned by the Hub — but the behaviour an operator sees does not, and dropping them would silently
unspecify shipped behaviour.

**The removal ships in this change, not ahead of it.** Removing 19 requirements before their
replacement exists leaves a window where behaviour is specified nowhere. This is the one place the
"small verifiable commit first" pattern used for the charter harvest does not apply.

## Alternatives considered and rejected

**Keep `aw-spec-workflow` and rewrite it in place.** Rejected: a capability describing a phase machine
under a name meaning "the skill workflow" misstates its own subject, and a 10-requirement rewrite
reads as evolution when this is replacement. The paper-trail argument was withdrawn — the archive and
git preserve it either way. Decisive evidence: that capability's spec-role requirement was patched in
the previous session to stop routing agents to mechanisms a project lacks, which is a spec being
maintained to survive a product that moved out from under it.

**Ship the phase machine as a separate change.** Rejected: §2.7 requires the entry point to create a
document *in `exploring`*, so a phase field is needed here regardless. Splitting would ship a state
column with no machine enforcing it — a gate that looks real and is not, which is worse than no gate.

**Write changes 2–5 now while the design is fresh.** Rejected: their requirements depend on what
using change 1 teaches — what the rejection categories need to be, whether relevance-at-the-link is
workable, what a hand-edit conflict looks like in practice. The mitigation is §7's five forward
commitments, which are requirements *here*. The risk of sequencing is foreclosing the design, not
forgetting it.
