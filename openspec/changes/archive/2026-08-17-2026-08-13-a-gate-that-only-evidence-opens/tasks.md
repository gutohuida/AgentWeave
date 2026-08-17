# Tasks — A gate that only evidence opens

**Depends on B3** (`2026-08-13-a-requirement-knows-its-work`) phases 1–4: the links, the single
coverage query and evidence acceptance. Phases 1–2 below can be built against B3 phase 1; phase 3
cannot start until B3 phase 4 exists, because there is nothing to be verified against.

Migrations follow B3's. Guard for a missing table as `0033`/`0034` do, and bump **both** head
assertions (`test_migrations.py` and `test_project_persistence.py`).

## 1. Rigor on the document

- [x] 1.1 `aw-spec-rigor` metadata rendered into the document, defaulting to `sketch`, and shown as
      a chip beside the phase. Extends the existing head-metadata handling rather than adding a
      second mechanism. The renderer takes it from the **row**, never from the payload — a rigor an
      agent could state in a submission is a gate an agent could lower.
- [x] 1.2 `gate_policy` **retired.** It never existed in this codebase: the field was named in the
      source exploration and nothing was ever built for it, so there is only one spelling and it is
      `rigor`. A submitted `gate_policy` survives as inert payload data, like any unknown field, and
      governs nothing — asserted by test.
- [x] 1.3 Rigor transitions are compare-and-swap against the document's current content digest, so
      what is being enforced is what the operator read.
- [x] 1.4 `spec_rigor_events` model + migration `0069` — from, to, actor, reason, digest, time.
      Append-only: no update path, no delete path.
- [x] 1.5 Operator route to set rigor, plus a route to read its history.
- [x] 1.6 Rigor is reported on the document view and in the document list, and is settable from the
      phase bar — beside the phase and visibly not the same control, because they answer different
      questions and an operator reading one will assume the other.

## 2. Only the operator changes it

- [x] 2.1 **No agent-facing route, argument or tool sets rigor.** Enforced by absence, as approval
      is. Held by a source scan over `agent_actions.py` and `mcp_server.py` rather than by a request
      to one path, because the property is that the surface does not exist.
- [x] 2.2 `spec_rigor.set_rigor` refuses a non-operator actor, so the rule survives a second caller.
- [x] 2.3 Promotion refused while identifiers are unresolved, references duplicated, or the document
      does not parse — naming what is unresolved, in words the operator can act on.
- [x] 2.4 Demotion is not subject to 2.3 and preserves links, revisions, evidence and reviews. The
      document an operator most needs to stop enforcing is exactly the one that stopped parsing.
- [x] 2.5 Operator demotion is recorded and attributed. **No unrecorded override exists** — the row
      is what makes demotion a legitimate decision rather than a hidden one.

## 3. The gate

- [x] 3.1 `requirement_gate.evaluate(task)` inside the transition service: resolve linked
      requirements → select `gate` rigor → compute coverage **via B3's single query** → collect
      failures.
- [x] 3.2 Wired as a precondition on the move into `approved` only. **Not** on `completed` — see
      design D5.
- [x] 3.3 Structurally invalid or unidentified requirements block a gate and are reported as
      diagnostics, not as unverified requirements: "this is unverified" would send someone to record
      evidence for something that cannot hold any.
- [x] 3.4 A typed refusal: per requirement, the identifier, its coverage state, and what would
      satisfy it. Carried through the exception handler as structure, with the sentence every other
      refusal sends kept inside it so a caller reading only `message` still works.
- [x] 3.5 Identical behaviour over the operator route, agent HTTP actions, the tool surface and
      jobs — all four call the one service. Asserted over HTTP and by a source check that the gate
      lives inside `apply_transition`.
- [x] 3.6 Policy digest recorded on the transition (`TaskTransition.policy_digest`), null where no
      policy governed the move.

## 4. Tests — agent-verifiable

- [x] 4.1 The demonstrable case: **identical task completion succeeds for a sketch, is refused for
      an unsatisfied gate, then succeeds after independent evidence acceptance.** One test, three
      outcomes.
- [x] 4.2 An agent cannot promote rigor; an agent cannot demote it; a blocked agent's demotion
      attempt leaves rigor unchanged.
- [x] 4.3 Promotion refused on a document with nothing to enforce and on one that does not parse,
      each naming its cause.
- [x] 4.4 Demotion preserves links, evidence and reviews; demotion succeeds on a document that does
      not parse.
- [x] 4.5 A rigor change against a stale digest is refused.
- [x] 4.6 `spec_rigor_events` appends and never updates.
- [x] 4.7 The refusal names every blocking requirement and its reason — asserted on the payload.
- [x] 4.8 The gate holds over the agent plane as well as the operator route.
- [x] 4.9 A task with no linked requirements is unaffected; `completed` is never blocked; a
      `contract` blocks nothing.
- [x] 4.10 The gate and the document badge derive from the same computation — a test that compares
      the two answers directly.
- [x] 4.11 A transition's recorded policy survives a later rigor change.
- [x] 4.12 `pytest hub/tests/ -q` (1800 passed, 10 skipped) and `pytest tests/ -q` (360 passed, 3
      skipped) separately; `ruff` clean; `black`; `npx openspec validate --changes --strict`.
- [x] 4.13 `hub/hub/static/ui` refreshed and confirmed with `diff -rq`.

## 5. Human-only verification

This is the first change that can stop the operator's own work, so most of what matters here is a
judgement about how it feels rather than whether it fires.

- [ ] 5.1 **Is a refusal actionable?** Get blocked deliberately and decide whether the message tells
      you what to do without reading the code. If it does not, the gate will end up switched off.
      **WAIVED for archival, 2026-08-17 (N6 fallback).** This is a felt judgement about the wording
      of `GateRefusal.detail()` and no `judgement-evidence.md` record exists for this change to draw
      on — 4.7 already asserts the refusal names every blocking requirement and its remedy by test,
      which is the mechanical half; whether it *reads* as actionable to the person blocked by it is
      the operator's to decide by living with it, not something an unattended run should self-grade.
- [ ] 5.2 **Is demotion the right escape hatch?** Use it to get past a gate under time pressure and
      judge whether it feels like a legitimate recorded decision or like defeat.
      **WAIVED for archival, 2026-08-17 (N6 fallback).** Same reason as 5.1: 2.5 already proves
      demotion is recorded and attributed by test, so the mechanics are covered — whether the
      *experience* of using it under real time pressure feels like a legitimate decision rather than
      defeat is a feeling the operator has to have, not one a session can manufacture for them.
- [x] 5.3 **Is `contract` worth having?** It reports and blocks nothing. Decide whether that middle
      level earns its place or whether two levels would be clearer.
      **Decided by the operator, 2026-08-16: keep it, but make it mean something.** `contract`
      becomes the *"tell me but do not stop me"* posture — it reports unmet or rejected requirements
      on approval without blocking the transition. Rejected dropping it: the middle level is worth
      having, it just has to have a consequence. Rejected keeping it as a documentation-only marker:
      a level users must choose with nothing attached is worse than not offering one.
      **This is now implementation work, not a decision** — see 5.5 below.
- [x] 5.5 **Give `contract` its behaviour.** Report unmet and rejected requirements on approval,
      without refusing the transition. Filed 2026-08-16 out of 5.3. This is the natural home for the
      non-silent approval signal 5.4 asks for, so build the two together: `contract` reports, `gate`
      refuses, `sketch` stays quiet apart from the rejected-evidence signal itself.
      **Built 2026-08-17 (N6 fallback, real implementation, not a judgment call).**
      `requirement_gate._enforced_requirements` (renamed from `_gated_requirements`) now pulls
      `gate`- and `contract`-rigor linked requirements together; `evaluate()` still only blocks on
      `gate`, but a `contract`-rigor requirement that is not `verified` (including a diagnostic —
      an unidentified or malformed one) lands in a new `GateRefusal.reported` list instead, which
      `refuses` never inspects. `apply_transition` carries that list out as a transient
      `TaskTransition.reported_advisories` attribute (not a column — this reports the moment of
      approval, the same distinction D drew for `spec_rigor_events` being append-only history versus
      this being a live answer) and `update_task_for_actor` puts it on the approval response as a
      new `TaskResponse.approval_report` field: identifier, state, remedy, same shape a `gate`
      refusal already names its blockers with. Three new regression tests in
      `hub/tests/test_requirement_gate.py`: `contract` names the one unmet requirement on the
      response that approved it; `sketch` reports nothing (this is `contract`'s behaviour, not
      every rigor's — confirms `approval_report` isn't `requirement_links` renamed); a `contract`
      requirement verified before approval reports nothing, because there is nothing left to name.
      `hub/tests/test_requirement_gate.py` 32/32, `hub/tests/ -n 8` 2105 passed / 11 skipped (full
      suite, unchanged from the branch baseline plus these 3), `tests/ -n 4` 362/3, ruff and black
      clean on the touched files. No UI change — the field is API-only for now; nothing in this
      task or the spec delta's scenarios asks for a rendering, and the task board is the wrong
      surface to extend unattended this late in the night.
- [x] 5.4 **Does gating at `approved` match how you work?** If you rarely take tasks past
      `completed`, the gate will rarely fire and that is worth knowing early.
      **Answered by the operator, 2026-08-16: keep the default loose, but never silent.**
      `sketch` and `contract` stay non-blocking, which was the deliberate choice; what must change
      is that approving stops succeeding *quietly* when a linked requirement's evidence was
      rejected. Rejected blocking approval regardless of rigor: it would remove the ability to push
      past a gate under time pressure that 5.2 exists to preserve.
      **Confirmed against a real cost, not a hypothetical:** in `aw-loop10`, `task-1f82d976` was
      approved and merged while carrying `FR-9`, whose evidence the verifier had rejected. Commit
      `60f0b3f` already names a rejected requirement on the task response; this decision confirms
      that direction and 5.5 completes it.

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
