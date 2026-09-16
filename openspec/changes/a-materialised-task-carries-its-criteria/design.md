# Design: a materialised task carries its criteria

## Context

`spec_tasks.materialise()` (`hub/hub/spec_tasks.py:96-237`) walks a document's declared task entries
and creates the ones that do not exist. For each entry it already resolves the requirement rows the
entry names (`:184-194`, via `by_key` / `by_identifier`), constructs the `Task` (`:205-217`), and
links the requirements (`:221-222`). The document's acceptance criteria are never read.

The criteria live on the payload as `SpecPayload.acceptance_criteria`
(`hub/hub/spec_payload.py:188`), each an `AcceptanceCriterion` with `key`, `requirement`, `given`,
`when`, `then` (`:91-100`). `requirement` holds **a requirement's key**, the same namespace
`by_key` is built from at `spec_tasks.py:159`.

Two readers already consume `Task.acceptance_criteria`:

- `hub/hub/scheduler.py:2456-2460` — `criteria = claimed_task.acceptance_criteria or []`, then
  `f"- {criterion}"` per element, for the implementer and the reviewer alike.
- `hub/ui/src/components/tasks/TaskDetailDrawer.tsx:612-616` — maps each element into JSX, typed
  `string[]` at `hub/ui/src/api/tasks.ts:18`.

Measured state of the corpus this was found in: 0 of 32 spec-materialised tasks carry criteria; 18
of 18 hand-made ones do (proposal.md).

## Goals / Non-Goals

**Goals:**

- A task created from a document states the standard its own document already declared for it.
- No migration, no schema change, no API shape change, no UI change.
- The change is confined to one function, so a later change that makes criteria *executable* has a
  populated field to build on.

**Non-Goals:**

- Executing criteria, gating on them, or building a verification step. The field being populated is
  the precondition for that work, not the work.
- Backfilling tasks materialised before this change.
- Changing `spec_completeness`'s rules about whether a document may be approved with uncovered
  requirements (`hub/hub/spec_completeness.py:186`).
- Changing what a reviewer's briefing contains beyond the criteria block it already renders.

## Decisions

### D1 — Criteria are stored as rendered strings, not as objects

`Task.acceptance_criteria` is `JSON, nullable=True` (`hub/hub/db/models.py:684`), so the column would
accept objects. Both existing readers would break on them: the briefing would emit a Python dict
repr into the agent's turn context, and the UI would throw at render, since React cannot render a
plain object as a child.

Storing objects therefore forces a UI change and a committed bundle. `CLAUDE.md` records that the
operator's live `:8000` Hub serves `hub/hub/static/ui` straight from this checkout, so a committed
bundle reaches their running application on their next reload. Strings keep this change entirely
off that surface.

**Alternative considered — a second structured column** (`acceptance_criteria_structured`), leaving
the existing field alone. Rejected for this change: it needs a migration, it creates two sources of
truth for the same fact, and nothing currently reads it. The later change that makes criteria
executable is the one that should decide whether structure is needed and pay for it then, with a
reader in hand. Recorded here so that change does not treat D1 as having foreclosed it.

### D2 — The rendered form is `Given <given>, when <when>, then <then>`

The three parts are all present, in declaration order, in one line per criterion. This satisfies the
spec's scenario *"A criterion states its starting state, its event and its outcome"* and keeps one
list element per criterion, which is what both readers assume.

**R2 decision: include the criterion key**, as `ac-window-closes: Given ..., when ..., then ...`.

R1 framed this as "don't build for a consumer that does not exist yet", which is D1's own logic and
would argue for omitting it. R2 overturns that on an asymmetry R1 did not weigh: **the rendered
string is the only carrier, and D5 forbids backfill.** A task created without the key can never
recover it — the criterion's identity would have to be re-derived by matching prose back to the
document, for every task created between this change and whenever a gate wants the handle. Including
it costs roughly a dozen characters on a line a person reads, and that cost is paid back the moment
anything wants to say *which* criterion failed.

Omission here is lossy and irreversible; inclusion is neither. That asymmetry, not a guess about
future consumers, is the reason.

### D3 — Selection is on the payload key the entry named — **corrected by R2**

For each created task, the criteria attached are those whose `requirement` equals one of the names
in that entry's own `requirements` list — `named`, in the loop at `spec_tasks.py:187-194`. Not the
resolved `SpecRequirement` row's `.key`.

**R1 had this backwards, and its stated hazard does not exist.** R1 wrote that an entry's names
"may be keys or identifiers" and that matching must therefore use the resolved rows' `key`. Both
halves are wrong:

- **An entry cannot name a requirement by identifier.** `validate_payload` builds
  `known = {r.key for r in payload.requirements}` and refuses any `tasks[i].requirements[j]` not in
  it (`spec_payload.py:279-285`). Measured by running it: a task entry naming `REQ-0001` is refused
  with *"names requirement 'REQ-0001', which this document does not define"*, while `req-a` is
  accepted.
- **`materialise()`'s second lookup is not identifier support.** `spec_identity.read_identity()`
  returns a **key to identifier** map (`spec_identity.py:31-32,42-44`), so
  `by_identifier.get(identities.get(named, ""))` at `:190` takes a *key*, maps it to its identifier
  and looks the row up that way. `named` is a key in both branches. The fallback exists for a row
  whose `key` has moved, not for an entry that named one differently.

**And the row's key is exactly the thing that can drift.** `spec_index.py:216-218` says so in its
own comment — *"The key can move: an agent may rename its handle while the statement stands. The
identifier is what everything points at"* — and assigns `row.key = declared.key` on every reindex.
Matching on `row.key` therefore couples this change to index freshness for no benefit, while
matching on `named` stays inside one namespace: **the criterion's `requirement` and the entry's
`requirements` are both payload keys, validated against the same `known` set in the same call.**
They cannot disagree.

`unresolved` names (`:194`, absorbed as free text at `:227-229`) contribute no criteria. Under the
validation above an unresolved name should be unreachable for a validated payload, so this needs no
special case — but it must also not raise. See D6.

### D6 — The implementation must not be able to raise — **added by R2**

Approval calls `materialise_quietly()`, which catches **every** exception and returns `[]`
(`spec_tasks.py:416-423`), by deliberate design: *"Failing that decision because the board could not
be populated would make an unrelated problem look like a refusal to approve."*

The consequence for this change is severe and R1 missed it entirely: **if criteria-matching raises,
no tasks are created at all, and the approval reports success.** The failure mode of a bug here is
not "tasks without criteria" — it is "an approved document with an empty board and a warning in a
log nobody reads."

So the implementation must be total over any shape the stored payload can hold: no `[...]` indexing
that can `KeyError`, no assumption that `payload["acceptance_criteria"]` is present, is a list, or
holds dicts with the expected fields. The payload reaching `materialise()` is the **stored** dict
(`materialise(session, document, payload...)`, `spec_tasks.py:99`), not a validated `SpecPayload`,
and `_Part` keeps unknown fields (`spec_payload.py:58-68`), so a document written under another
schema version can carry shapes this code has never seen.

A test should assert that a malformed `acceptance_criteria` block does not prevent task creation.

### D4 — Ordering follows the document

Criteria are attached in the order they appear in `payload.acceptance_criteria`, not grouped by
requirement or sorted by key. The document's order is the author's, and a reader comparing the task
against the document should see the same sequence. This also makes the result deterministic, which
the tests depend on.

### D5 — Already-materialised tasks are not backfilled

`materialise()` skips any entry whose key is in `existing_keys` (`spec_tasks.py:176`), so a
re-approval never revisits a task it created earlier. Tasks that exist today keep empty criteria.

This is a deliberate limit, not an oversight: a backfill would have to decide what to do about a
task whose document has since been revised, and about criteria an operator or agent has edited by
hand since. **The consequence is that this change does nothing for the 32 tasks that motivated it**
— it changes what happens next, not what already happened. Anyone measuring its effect must measure
on tasks created after it ships.

## Risks / Trade-offs

- **The briefing grows without a bound.** `agent-loops`' *"A firing's briefing is bounded"*
  (`openspec/specs/agent-loops/spec.md:274-291`) bounds the **prior checkpoint** only —
  `_LOOP_BRIEFING_CHECKPOINT_CHARS` at `scheduler.py:2468-2471`. Nothing bounds the criteria block.
  A task resolving several requirements with several criteria each will lengthen every firing's
  briefing for that task. → **Mitigation: none in this change, by choice.** The criteria are the
  smallest statement of the standard available and the alternative is the 1.9M-token re-derivation
  this change exists to remove. But R2/R3 must confirm that a pathological document cannot produce a
  briefing that displaces the prior checkpoint or overruns the job message, and if it can, this
  change gains a bound and a second modified capability.
- ~~Requirement-key vs identifier mismatch (D3).~~ **Refuted by R2 by execution** — an entry naming
  a requirement by identifier is refused at validation. No mitigation needed; the test R1 proposed
  for it would have pinned a case that cannot occur.
- **An exception in criteria-matching silently produces an empty board (D6).** → Mitigation: a total
  implementation, plus a test that a malformed `acceptance_criteria` block still lets tasks be
  created. This is now the most serious risk in the change, and it is a failure mode R1 did not see.
- **A criterion whose `requirement` names nothing.** **Verified by R2 by running it**:
  `validate_payload` refuses it — *"acceptance_criteria[0].requirement: names requirement
  'req-missing', which this document does not define"* (`spec_payload.py:272-277`). → Mitigation: no
  defensive branch, but note that D6 still applies, because `materialise()` receives the **stored**
  payload rather than a re-validated one.
- **Tests that assert the created task's exact field set** may now see a populated field. →
  Mitigation: extend rather than rewrite; `hub/tests/test_spec_declared_tasks.py` is the first place
  to look.

## Open Questions

1. ~~D2's key prefix~~ — **closed by R2**: include it, on the lossy-and-unbackfillable asymmetry.
2. **Does the briefing need a criteria bound?** Still open. **R3 owns this**, and it is now the only
   question that could still add a second modified capability to this change. R1's note that
   `agent-loops`' bound covers the prior checkpoint alone was confirmed by R2 at
   `openspec/specs/agent-loops/spec.md:274-291` and `scheduler.py:2468-2471`, but nobody has yet
   measured the worst case a *valid* document can produce.
3. ~~Is `spec_payload`'s referential check sufficient?~~ — **closed by R2, by running it.** It
   refuses both a criterion and a task entry that names a requirement the document does not define.

## Round log

- **R1** wrote the proposal, design, specs and tasks from a code read plus a read-only measurement
  of the live database.
- **R2** re-derived against the code and by executing `validate_payload` directly. It **refuted D3's
  stated hazard** (an entry cannot name a requirement by identifier; the `by_identifier` fallback is
  a key-to-identifier remap), **inverted D3's instruction** (match on the payload key the entry
  named, not the resolved row's `key`, which `spec_index.py:216-218` explicitly allows to move),
  **added D6** (`materialise_quietly` swallows every exception, so a bug here empties the board
  rather than the criteria list), **closed D2** for inclusion of the criterion key, and **verified**
  the referential-integrity claim R1 had only inferred.
- **R3** — not yet run. Owns open question 2, and should re-derive independently rather than
  checking R2's work.
