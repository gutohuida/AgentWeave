# Tasks — A requirement knows its work

Phased so each phase is independently useful and the ones needing an operator decision come after
the ones that do not. **Phase 2 alone answers "which requirements have no work?" and makes
requirement injection possible** — the two things the end-to-end run most wanted.

Migrations: current head is `0065`. Each new one guards for a missing table as `0033`/`0034` do, and
both head assertions get bumped (`test_migrations.py` **and** `test_project_persistence.py`).

## 1. The requirement index

- [x] 1.1 `spec_requirements` model + migration `0066` — project, document, identifier, key, state
      (`active`/`retired`), digest, `digest_version`, anchor, `observed_at`. Unique on
      **`(project_id, document_id, identifier)`**: identifiers are minted per document, so `FR-1`
      exists in every document and a project-wide constraint cannot hold. Everything that points at
      a requirement points at the row, which is unambiguous regardless; resolution *by name* refuses
      an identifier two documents declare rather than choosing.
- [x] 1.2 `spec_requirement_revisions` model + migration — append-only old/new digest, source
      (`hub`/`external`), classification, actor, time.
- [x] 1.3 Reindex from a saved payload inside `spec_service.save_document`, in the same transaction
      that writes the file. The index must never be newer or older than the document it describes.
- [x] 1.4 A removed requirement becomes `retired`; it is not deleted, and its identifier is not
      reissued (`aw_identity`'s high-water mark already guarantees the second half). Retirement is
      permanent: a key that returns is minted a **new** identifier, so `restored` exists only for a
      file edited outside the Hub.
- [x] 1.5 `reindex_project(project_id)` — rebuild from files alone, and a test that a discarded
      index rebuilds identically. Needed the identity block to start carrying per-identifier
      digests: a retired requirement's wording is gone from the document, so nothing else could
      reconstruct what it meant.
- [x] 1.6 One semantic digest, in `spec_digest`, called by both the index and the document row.
      Covers modal, statement, party and acceptance criteria; excludes rationale. Carries a
      canonicalization version so a later change to the rule is visible rather than silent.

## 2. Links replace the JSON

- [x] 2.1 `task_requirement_links` model + migration `0067` — project, task, requirement, creating
      actor, creating run, created time. Real foreign keys, project-scoped.
- [x] 2.2 Task create/update accept requirement **identifiers** (`requirement_ids`, with an
      optional `spec_document` to disambiguate), resolve them, and refuse an identifier the project
      does not have — stated, not silently dropped. A partly-unknown set links nothing: a task that
      silently serves two of the three it named is a task whose author believes it serves three.
      On both the operator route and the agent plane, which `agent-capability-plane` requires to
      accept the same things.
- [x] 2.3 Links are not removed on a terminal task status.
- [x] 2.4 Migration of `Task.requirements`: parse a leading `FR-\d+`; link where it resolves in the
      same project; otherwise write a `task_requirement_references` row preserving the original
      string. **Never discard, never invent a requirement.** The same conversion runs on every
      create, so an agent still using the free-text field gets real links — leniently there, since a
      free-text field that starts refusing values breaks every caller using it as prose.
- [x] 2.5 `Task.requirements` stays as a nullable column, written verbatim and read by nothing that
      answers a traceability question, so a mis-parse can be re-derived. Removal is a later change,
      once the unresolved set is empty.
- [x] 2.6 `unserved` query: active requirements with no link, per project or per document. **This is
      the first thing that pays for the phase.**
- [x] 2.7 `POST .../project/spec/reindex` — operator-only: rebuild the index from the files, then
      retry the unresolved references. Needed because a project whose documents predate the index
      resolves nothing at migration time; this converts what becomes resolvable without ever having
      guessed in between.

## 3. Coverage, as one computation

- [x] 3.1 `requirement_coverage(...)` — the single definition. Precedence per design D5, read from
      the `PRECEDENCE` tuple rather than restated as a chain whose order could drift from it.
- [x] 3.2 Invalid/unidentified requirements are diagnostics *outside* coverage, not a state.
- [x] 3.3 Document-level and project-level rollups, both calling 3.1 and computing nothing.
- [x] 3.4 A test that asserts there is exactly one implementation — it reads the rollups' source and
      refuses either of them reaching the precedence directly.

## 4. Evidence and review

Unblocked — all four questions answered at review (see `proposal.md`).

- [x] 4.1 `requirement_evidence` model + migration `0068` — requirement, **digest produced
      against**, kind, artifact locator, actor, run, produced time, review state.
- [x] 4.2 Kinds open to addition: `test_result`, `screenshot`, `artifact_diff`, `review_record`,
      `manual_observation`, `external_reference`. Values outside the list are accepted; the list is
      what the surfaces know how to label.
- [x] 4.3 **Artifacts live in a project folder tree**, not the database; the row holds the location.
- [x] 4.4 **Retention as a project policy** — `Project.evidence_retention`, defaulting to `never`.
      Removing an artifact never removes its record; the record reports the artifact as gone.
- [x] 4.5 `evidence_reviews` — append-only, attributed to whoever decided, no update, no delete.
- [x] 4.6 Agent-recorded evidence enters `awaiting`, never `accepted`. An operator's own observation
      is accepted on arrival: there is nobody else for it to await.
- [x] 4.7 `Agent.can_accept_evidence` + migration, alongside `can_recall` / `can_read_checkpoints`.
      Operator-granted only; never conferred by a charter.
- [x] 4.8 Acceptance route: the operator, or a granted agent. **An agent accepting evidence it
      produced is refused** — distinctness on agent identity, not run identity.
- [x] 4.9 A project with no granted agent falls to the operator, as a supported path.
- [x] 4.10 Agent route to record evidence; identity from the run credential only, with no actor
      field on the schema to supply.
- [x] 4.11 Coverage reports `stale` where every piece of evidence names a superseded digest.

## 5. Drift and integration

Unblocked. **Both footprint paths ship together.**

- [x] 5.1 Capture the implementation footprint when evidence is recorded: git commit + changed blob
      ids where the project is a repository; changed paths + content hashes where it is not.
- [x] 5.2 `requirement_drift` — candidate/resolved/superseded, baseline and current fingerprints,
      attributed resolution.
- [x] 5.3 Detection on footprint change with no new requirement revision. A reworded requirement is
      deliberately *not* also drift: it is already reported as stale evidence, and raising both
      would ask the operator the same question twice in two vocabularies.
- [x] 5.4 Operator resolution: specification updated / implementation corrected / no change
      required; records the current digest and fingerprint so it does not re-fire.
- [x] 5.5 A test that drift **never** writes to a specification document.
- [x] 5.6 **Integration reporting** — reachability from the project's main line of work, returned
      with every coverage answer. `verified, not integrated` is a real result. A project with no
      main branch reports `unknown` rather than `not_integrated`: the second would be an accusation
      about a choice.
- [x] 5.7 A test that no surface can report a coverage state without its integration answer.

## 6. Navigation

- [x] 6.1 Requirement → linked tasks and evidence (`GET .../spec/requirements/{identifier}`).
- [x] 6.2 Task → requirements served, on every task response, with the document each belongs to.
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
