# Tasks — A gate that only evidence opens

**Depends on B3** (`2026-08-13-a-requirement-knows-its-work`) phases 1–4: the links, the single
coverage query and evidence acceptance. Phases 1–2 below can be built against B3 phase 1; phase 3
cannot start until B3 phase 4 exists, because there is nothing to be verified against.

Migrations follow B3's. Guard for a missing table as `0033`/`0034` do, and bump **both** head
assertions (`test_migrations.py` and `test_project_persistence.py`).

## 1. Rigor on the document

- [ ] 1.1 `aw-spec-rigor` metadata rendered into the document, defaulting to `sketch`; parsed back
      on read. Extends the existing head-metadata handling rather than adding a second mechanism.
- [ ] 1.2 `gate_policy` in the payload stops being an inert passthrough — reconcile it with the
      rendered metadata, or retire the field. **Decide which; do not leave two spellings.**
- [ ] 1.3 Rigor transitions are compare-and-swap against the document's current content digest,
      reusing `spec_lifecycle.divergence`'s machinery rather than a second staleness check.
- [ ] 1.4 `spec_rigor_events` model + migration — from, to, actor, reason, digest, time.
      Append-only: no update path, no delete path.
- [ ] 1.5 Operator route to set rigor.
- [ ] 1.6 Rigor is reported on the document view and in the document list.

## 2. Only the operator changes it

- [ ] 2.1 **No agent-facing route, argument or tool sets rigor.** Enforced by absence, as approval
      is — not by an instruction telling agents not to.
- [ ] 2.2 The rigor-setting function refuses a non-operator actor, so the rule survives a second
      caller being added later.
- [ ] 2.3 Promotion to `contract`/`gate` refused while identifiers are unresolved, references
      duplicated, or the document does not parse — naming what is unresolved.
- [ ] 2.4 Demotion is not subject to 2.3 and preserves links, revisions, evidence and reviews.
- [ ] 2.5 Operator demotion is recorded and attributed. **No unrecorded override exists.**

## 3. The gate

- [ ] 3.1 `gate_refusal(task)` inside the transition service: resolve linked requirements → select
      `gate` rigor → compute coverage **via B3's single query** → collect failures.
- [ ] 3.2 Wired as a precondition on the move into `approved` only. **Not** on `completed` — see
      design D5.
- [ ] 3.3 Structurally invalid or unidentified requirements block a gate and are reported as
      diagnostics, not as unverified requirements.
- [ ] 3.4 A typed refusal: per requirement, the identifier, its coverage state, and what would
      satisfy it.
- [ ] 3.5 Identical behaviour over the operator route, agent HTTP actions, the tool surface and
      jobs — because all four already call the one service. Assert it rather than assume it.
- [ ] 3.6 Policy digest recorded on the transition.

## 4. Tests — agent-verifiable

- [ ] 4.1 The demonstrable case from the design source: **identical task completion succeeds for a
      sketch and a contract, is refused for an unsatisfied gate, then succeeds after independent
      evidence acceptance.** One test, three outcomes.
- [ ] 4.2 An agent cannot promote rigor; an agent cannot demote it; a blocked agent's demotion
      attempt leaves rigor unchanged.
- [ ] 4.3 Promotion refused on an unresolved identifier, a duplicate reference, an unparseable
      document — each naming its cause.
- [ ] 4.4 Demotion preserves links, evidence and reviews; demotion succeeds on a document that does
      not parse.
- [ ] 4.5 A rigor change against a stale digest is refused.
- [ ] 4.6 `spec_rigor_events` appends and never updates.
- [ ] 4.7 The refusal names every blocking requirement and its reason — asserted on the payload, not
      on a message string.
- [ ] 4.8 The gate holds over HTTP, MCP and a job, not only the operator route.
- [ ] 4.9 A task with no linked requirements is unaffected; `completed` is never blocked.
- [ ] 4.10 The gate and the document badge derive from the same computation — a test that they
      cannot disagree.
- [ ] 4.11 A transition's recorded policy survives a later rigor change.
- [ ] 4.12 `pytest hub/tests/ -q` and `pytest tests/ -q` separately; `ruff`; `black`;
      `npx openspec validate --changes --strict`.
- [ ] 4.13 `hub/hub/static/ui` refreshed and confirmed with `diff -rq` if any UI ships.

## 5. Human-only verification

This is the first change that can stop the operator's own work, so most of what matters here is a
judgement about how it feels rather than whether it fires.

- [ ] 5.1 **Is a refusal actionable?** Get blocked deliberately and decide whether the message tells
      you what to do without reading the code. If it does not, the gate will end up switched off.
- [ ] 5.2 **Is demotion the right escape hatch?** Use it to get past a gate under time pressure and
      judge whether it feels like a legitimate recorded decision or like defeat.
- [ ] 5.3 **Is `contract` worth having?** It reports and blocks nothing. Decide whether that middle
      level earns its place or whether two levels would be clearer.
- [ ] 5.4 **Does gating at `approved` match how you work?** If you rarely take tasks past
      `completed`, the gate will rarely fire and that is worth knowing early.

## 6. User test guide

**Setup.** A project with an approved specification, a task linked to its requirements, and a tester
agent granted `can_accept_evidence` (or none, and you accept).

1. **A sketch blocks nothing.** Leave the document at its default rigor. Take a task through to
   `approved` with no evidence at all.
   - *Expect:* it approves. Rigor `sketch` is the default and never blocks.
2. **Promote to `gate`.** Set the document's rigor to `gate`.
   - *Expect:* accepted, and the document itself now says `gate` when you read it.
3. **The gate fires.** Take another task, linked to that document's requirements, to `approved` with
   no accepted evidence.
   - *Expect:* refused, naming each requirement and saying why — "no evidence", "awaiting review",
     or "evidence no longer applies".
4. **Evidence opens it.** Record evidence and accept it, then approve again.
   - *Expect:* it approves.
5. **An agent cannot get around it.** Ask an agent to lower the document's rigor.
   - *Expect:* it has no way to do so, and says as much. This is the point of the change.
6. **You can.** Demote the document yourself.
   - *Expect:* it works, it is recorded with your name, and the task approves. Nothing about the
     evidence or the links is lost.
7. **A broken document cannot become a gate.** Break a requirement identifier and try to promote.
   - *Expect:* refused, naming what is unresolved.

**Where it would go wrong:** if step 3 refuses without naming which requirement, task 3.4 is
incomplete — and that is the failure that makes people disable gates rather than satisfy them.
