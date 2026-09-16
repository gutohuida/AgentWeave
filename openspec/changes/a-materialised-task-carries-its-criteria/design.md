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

**Open for R2/R3, deliberately not settled here:** whether the criterion's `key` should be
prefixed (`ac-window-closes: Given ...`). *For*: evidence is recorded against requirements today
(`record_evidence`), and a future gate reporting *which* criterion failed needs a handle. *Against*:
it puts an identifier in front of every line a human reads in the task drawer, for a consumer that
does not exist yet, and D1's own reasoning says not to build for the later change. **R2 should pick
one and say why; R1 does not have enough to decide it.**

### D3 — Selection is by requirement key, matching what the entry already resolved

For each created task, the criteria attached are those whose `requirement` matches a key of a
requirement that entry resolved. `materialise()` already holds that set as the local `requirements`
list (`spec_tasks.py:185-192`), so no second resolution pass and no new query is needed.

Two subtleties that must not be glossed:

- The entry's `wanted` names may be **keys or identifiers** — `:190` looks up `by_key.get(named) or
  by_identifier.get(identities.get(named, ""))`. A criterion's `requirement` field is documented as
  a *key*. Matching must therefore be done against the resolved `SpecRequirement` rows' `key`
  attribute, not against the raw strings the entry listed, or a task that named its requirement by
  identifier would silently get no criteria. **This is the most likely place for this change to be
  quietly wrong, and it is what R2 and R3 should test first.**
- `unresolved` names (`:194`, absorbed as free text at `:227-229`) contribute no criteria, because
  no requirement row exists to match against. That is correct and needs no special case.

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
- **Requirement-key vs identifier mismatch (D3).** → Mitigation: a test where the declared task
  names its requirement by identifier and the criterion names it by key, asserting the criterion
  still attaches.
- **A criterion whose `requirement` names nothing.** `spec_payload.validate_payload` already checks
  referential integrity for criteria (`spec_payload.py:272-278` reports
  `acceptance_criteria[i].requirement`), so an approved document should not contain one. → Mitigation:
  do not add a defensive branch that silently drops it; if the invariant is real, a test should
  assert the validator is what enforces it. R2 should verify that claim against
  `spec_payload.py:272-288` rather than trusting this sentence.
- **Tests that assert the created task's exact field set** may now see a populated field. →
  Mitigation: extend rather than rewrite; `hub/tests/test_spec_declared_tasks.py` is the first place
  to look.

## Open Questions

1. **D2's key prefix** — include the criterion key in the rendered string, or not? R2 decides.
2. **Does the briefing need a criteria bound?** R2/R3 measure the worst case a valid document can
   produce, and say whether `agent-loops` must be modified.
3. **Is `spec_payload`'s referential check actually sufficient** to guarantee no criterion names a
   requirement the document lacks? Asserted in Risks from a read of `:272-288`; not yet verified by
   running it.
