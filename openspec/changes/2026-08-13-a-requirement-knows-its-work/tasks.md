# Tasks — A requirement knows its work

Phased so each phase is independently useful and the ones needing an operator decision come after
the ones that do not. **Phase 2 alone answers "which requirements have no work?" and makes
requirement injection possible** — the two things the end-to-end run most wanted.

Migrations: current head is `0065`. Each new one guards for a missing table as `0033`/`0034` do, and
both head assertions get bumped (`test_migrations.py` **and** `test_project_persistence.py`).

## 1. The requirement index

- [ ] 1.1 `spec_requirements` model + migration `0066` — project, document, identifier, key, state
      (`active`/`retired`), digest, anchor, `observed_at`. Unique on `(project_id, identifier)`.
- [ ] 1.2 `spec_requirement_revisions` model + migration — append-only old/new digest, source
      (`hub`/`external`), classification, actor, time.
- [ ] 1.3 Reindex from a saved payload inside `spec_service.save_document`, in the same transaction
      that writes the file. The index must never be newer or older than the document it describes.
- [ ] 1.4 A removed requirement becomes `retired`; it is not deleted, and its identifier is not
      reissued (`aw_identity`'s high-water mark already guarantees the second half).
- [ ] 1.5 `reindex_project(project_id)` — rebuild from files alone, and a test that a discarded
      index rebuilds identically.

## 2. Links replace the JSON

- [ ] 2.1 `task_requirement_links` model + migration — project, task, requirement, creating actor,
      creating run, created time. Real foreign keys, project-scoped.
- [ ] 2.2 Task create/update accept requirement **identifiers**, resolve them, and refuse an
      identifier the project does not have — stated, not silently dropped.
- [ ] 2.3 Links are not removed on a terminal task status.
- [ ] 2.4 Migration of `Task.requirements`: parse a leading `FR-\d+`; link where it resolves in the
      same project; otherwise write an `unresolved_reference` preserving the original string.
      **Never discard, never invent a requirement.**
- [ ] 2.5 `Task.requirements` stays as a nullable column, read by nothing, so a mis-parse can be
      re-derived. Removal is a later change, once the unresolved set is empty.
- [ ] 2.6 `unserved` query: requirements in a document with no link. **This is the first thing that
      pays for the phase.**

## 3. Coverage, as one computation

- [ ] 3.1 `requirement_coverage(...)` — the single definition. Precedence per design D5.
- [ ] 3.2 Invalid/unidentified requirements are diagnostics *outside* coverage, not a state.
- [ ] 3.3 Document-level and project-level rollups, both calling 3.1.
- [ ] 3.4 A test that asserts there is exactly one implementation — a second one is the failure mode
      this phase exists to prevent.

## 4. Evidence and review

Unblocked — all four questions answered at review (see `proposal.md`).

- [ ] 4.1 `requirement_evidence` model + migration — requirement, **digest produced against**, kind,
      artifact locator, actor, run, produced time, review state.
- [ ] 4.2 Kinds open to addition: `test_result`, `screenshot`, `artifact_diff`, `review_record`,
      `manual_observation`, `external_reference`.
- [ ] 4.3 **Artifacts live in a project folder tree**, not the database; the row holds the location.
- [ ] 4.4 **Retention as a project policy** — on acceptance, daily, monthly, manual, `never`.
      Removing an artifact never removes its record; the record reports the artifact as gone.
- [ ] 4.5 `evidence_reviews` — append-only, attributed to whoever decided, no update, no delete.
- [ ] 4.6 Agent-recorded evidence enters `awaiting`, never `accepted`.
- [ ] 4.7 `Agent.can_accept_evidence` + migration, alongside `can_recall` / `can_read_checkpoints`.
      Operator-granted only; never conferred by a charter.
- [ ] 4.8 Acceptance route: the operator, or a granted agent. **Refuse an agent accepting evidence
      it produced** — distinctness on agent identity, not run identity, per
      `task-lifecycle-governance`.
- [ ] 4.9 A project with no granted agent falls to the operator, as a supported path rather than an
      error.
- [ ] 4.10 Agent route to record evidence; identity from the run credential only.
- [ ] 4.11 Coverage reports `stale` where every piece of evidence names a superseded digest.

## 5. Drift and integration

Unblocked. **Both footprint paths ship together.**

- [ ] 5.1 Capture the implementation footprint when evidence is recorded: git commit + changed blob
      ids where the project is a repository; changed paths + content hashes where it is not.
- [ ] 5.2 `requirement_drift` — candidate/resolved/superseded, baseline and current fingerprints,
      attributed resolution.
- [ ] 5.3 Detection on footprint change with no new requirement revision.
- [ ] 5.4 Operator resolution: specification updated / implementation corrected / no change required;
      records the current digest and fingerprint so it does not re-fire.
- [ ] 5.5 A test that drift **never** writes to a specification document.
- [ ] 5.6 **Integration reporting** — is the footprint reachable from the project's main line of
      work? Returned with every coverage answer; `verified, not integrated` is a real result.
- [ ] 5.7 A test that no surface can report a coverage state without its integration answer.

## 6. Navigation

- [ ] 6.1 Requirement → linked tasks and evidence.
- [ ] 6.2 Task → requirements served, with their current statements.
- [ ] 6.3 Coverage on the Spec view. **Not** the task board's traceability surfaces — that is
      Program A's, per the roadmap's split of Program C.

## 7. Tests — agent-verifiable

- [ ] 7.1 Index: populated on save; rebuilt identically from files; removal retires rather than
      deletes; a reworded requirement records a revision with both digests.
- [ ] 7.2 Links: created from identifiers; refused for an unknown identifier; survive a terminal
      status; carry their creating actor and run.
- [ ] 7.3 Migration: the live legacy shape `"FR-8 — initialize-members"` becomes a link; an
      unresolvable value is preserved verbatim; nothing is dropped; no requirement is invented.
      Use the real strings from the 2026-08-13 run as fixtures.
- [ ] 7.4 Coverage: every state in the precedence, including two adjacent states resolving in the
      stated order; `unserved` for a requirement with no link; invalid requirements excluded.
- [ ] 7.5 Evidence: pinned to the digest; goes stale on rewording; agent evidence lands `awaiting`;
      a granted agent may accept another agent's evidence; **an agent accepting its own is refused**;
      an ungranted agent is refused; with no granted agent the operator can still accept; reviews
      append and never update; a deleted artifact leaves its record reporting the artifact gone.
- [ ] 7.6 Drift: a changed footprint raises a candidate; resolution stops it re-firing; **no
      document is written**.
- [ ] 7.7 `test_migrations.py` and `test_project_persistence.py` head assertions bumped.
- [ ] 7.8 `pytest hub/tests/ -q` and `pytest tests/ -q` separately; `ruff`; `black`;
      `npx openspec validate --changes --strict`.
- [ ] 7.9 `hub/hub/static/ui` refreshed and confirmed with `diff -rq` if any UI ships.
- [ ] 7.10 Footprints: both the git and the non-git path; integration reported for each; a
      requirement with accepted evidence on an unmerged branch reports `verified, not integrated`.

## 8. Human-only verification

- [ ] 8.1 **Is the coverage state legible?** Open a document with requirements in several states and
      judge whether the reason each is in its state is apparent without reading the code.
- [ ] 8.2 **Does drift feel like a diagnostic or an accusation?** Change an implementation, look at
      the resulting candidate, and judge the wording.
- [ ] 8.3 **Was the migration right on real data?** Inspect the links and unresolved references it
      produced for an existing project — this is the one step where being wrong is silent.
- [ ] 8.4 **Choose the project's retention policy** and confirm the evidence tree is somewhere you
      would actually keep artifacts.
- [ ] 8.5 **Decide which agent, if any, holds `can_accept_evidence`** — and confirm that working
      without one still feels workable rather than obstructive.

## 9. User test guide

**Setup.** A project with an approved specification and at least one task.

1. **Which requirements have no work?** Open the document's coverage.
   - *Expect:* every requirement with no linked task is listed. Before this, unanswerable.
2. **Link a task and watch it move.** Create a task naming two requirement identifiers.
   - *Expect:* both requirements stop being unserved; the task shows the two requirements with their
     current statements.
3. **A wrong identifier is refused.** Create a task naming `FR-999`.
   - *Expect:* refused, saying which identifier is unknown — not silently accepted as text.
4. **Reword a requirement.** Reopen the document, change one requirement's statement, re-approve.
   - *Expect:* its evidence (if any) is reported as no longer applying. The requirement keeps its
     identifier and its links.
5. **Retire a requirement.** Remove one from the document.
   - *Expect:* it is retired, not gone; the task that served it still names it.
6. **Old tasks still make sense.** Look at a task created before this change.
   - *Expect:* its recognizable references became links; anything unrecognizable is still visible as
     an unresolved reference, with its original text.

**Where it would go wrong:** if step 6 shows a task that lost references it used to have, the
migration dropped a value — which task 2.4 forbids.
