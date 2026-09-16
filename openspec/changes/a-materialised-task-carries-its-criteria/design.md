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
Matching on `row.key` therefore couples this change to index freshness for no benefit.

**R3 correction — the conclusion stands, R2's reason for it does not.** R2 justified matching on
`named` by saying the criterion's `requirement` and the entry's `requirements` are *"both payload
keys, validated against the same `known` set in the same call"*. That is false for the payload
`materialise()` actually receives:

- The approval route reads the **file** and parses it with `extract_payload`, **not**
  `validate_payload` (`hub/hub/api/v1/spec.py:1533-1537`), then hands the result straight to
  `materialise_quietly`. This is the only production call site of `materialise` in the Hub.
- A file can also come to exist without ever passing `validate_payload`: `spec_adoption.py` uses
  `extract_payload` plus its own title/kind checks (`:39,190-230`). **Adoption does not itself call
  `materialise()`** — the adopted file reaches it later, through the same approval route above — so
  this explains where an unvalidated file comes from, and is not a second path to guard.

So `validate_payload` constrains what can be **saved through the Hub**, and guarantees nothing about
what `materialise()` is given. A hand-edited or adopted file can hold anything.

**The right reason to match on `named` is simpler and survives that:** the criterion's `requirement`
and the entry's `requirements` come from **the same file**, so whatever namespace that file uses, it
uses consistently. Matching stays inside one document. Matching against the DB row's `key` crosses
into a namespace the file does not control and the index can move underneath.

**Accepted consequence:** a file that names its task requirements in one namespace and its criteria
in another attaches no criteria to those tasks. That is a silent miss, and it is deliberately
preferred to a wrong attribution — it degrades to exactly today's behaviour, which is the state this
change improves on rather than a regression. Task 3.12 pins it.

`unresolved` names (`:194`, absorbed as free text at `:227-229`) contribute no criteria. Under the
validation above an unresolved name should be unreachable for a validated payload, so this needs no
special case — but it must also not raise. See D6.

### D6 — The implementation must not be able to raise — **added by R2**

Approval calls `materialise_quietly()`, which catches **every** exception and returns `[]`
(`spec_tasks.py:416-423`), by deliberate design: *"Failing that decision because the board could not
be populated would make an unrelated problem look like a refusal to approve."*

**The adversarial review corrected what that failure actually is, and it is worse than R2 and R3
both wrote.** R2/R3 stated it as "no tasks are created at all". That holds only if the raise happens
before the first task is flushed. It does not, because `session.add(task)` and `await
session.flush()` sit **inside** the per-entry loop (`spec_tasks.py:218-219`), and
`materialise_quietly` catches without rolling back, after which `api/v1/spec.py:1537-1541` commits.

So a raise while processing entry *k* of *N* leaves **a committed partial board**: entries 1..k-1
exist, k..N do not. Three consequences follow that no round had named:

1. `_materialise_edges` (`spec_tasks.py:235`) sits after the loop and never runs, so **none** of the
   committed tasks receive dependency edges — a silent graph hole that survives until someone
   re-approves.
2. `created` is `[]`, so the route reports `tasks_created: []` and broadcasts no `task_updated`
   event (`api/v1/spec.py:1544-1546`). **The API response and the database disagree**, and the
   operator's board does not refresh to show the rows that do exist.
3. A mutation check that asserts "no tasks" would pass accidentally on a single-entry fixture and
   mean nothing. Test 3.11 must use two or more declared entries with the fault on the second.

**The design consequence:** do not merely make rendering total — build the criteria index **once,
before the loop** (D7), so that a payload this code cannot read fails identically for every entry
instead of part-way through. That converts the failure from a prefix into "every task created, none
with criteria", which is the behaviour the spec now requires.

So the implementation must be total over any shape the stored payload can hold: no `[...]` indexing
that can `KeyError`, no assumption that `payload["acceptance_criteria"]` is present, is a list, or
holds dicts with the expected fields.

**R3 upgraded this from prudent to load-bearing.** R2 justified D6 by noting that `materialise()`
receives the stored dict rather than a validated `SpecPayload`, and that `_Part` keeps unknown
fields (`spec_payload.py:58-68`). R3 found the stronger fact: the payload is parsed off **the file
on disk at approval time** with `extract_payload` (`api/v1/spec.py:1533-1537`), and the adoption
path never validates at all. Nothing anywhere guarantees that the dict reaching this code has ever
satisfied `validate_payload`. A document a person edited in their editor between save and approval
is an ordinary case, not a pathological one.

A test should assert that a malformed `acceptance_criteria` block does not prevent task creation,
and it must run through `materialise_quietly`, because that is the path that would hide the raise.

### D7 — Reuse `spec_reading.criteria_by_requirement_key`, and build the index once before the loop

**Added after the adversarial review, which found that all three rounds proposed writing a function
this repository already has.** `hub/hub/spec_reading.py:86-112` is
`criteria_by_requirement_key(payload) -> {requirement key: [criterion, ...]}` — exactly what task
2.1 described. Its own docstring states the reason it exists: *"the join happens once here rather
than being re-derived — wrongly, for a document whose criteria interleave — by each caller."*

It is also already total in the way D6 demands: it returns `{}` for a non-dict payload (`:96-97`),
skips a non-dict entry (`:99-100`), skips a non-string or empty `requirement` (`:101-103`), and uses
`.get()` for `key`/`given`/`when`/`then` so a missing field becomes `None` rather than a `KeyError`
(`:105-111`).

**One hole remains and must be closed rather than assumed away:** `payload.get("acceptance_criteria")
or []` at `:98` iterates whatever it finds. A string or dict degrades harmlessly to "no criteria",
but a scalar (`"acceptance_criteria": 5`) raises `TypeError` — which is precisely D6's failure. So
this change reuses the helper **and** guards its input with an `isinstance(..., list)` check.

CLAUDE.md's standing preference is that the cleanest solution wins; a second grouping of the same
data, differing from this one in the interleaving case its docstring names, is the opposite of that.

**The index is built once, before the per-entry loop**, for the reason in D6: a payload this code
cannot read must fail the same way for every entry, not part-way through.

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
2. ~~Does the briefing need a criteria bound?~~ — **closed by R3: no, and `agent-loops` is not
   modified.** Two independent reasons:
   - **No displacement is possible.** The criteria block (`scheduler.py:2456-2460`) and the prior
     checkpoint (`:2462-2471`) are both appended to the same `lines` list, in that order. They do
     not compete for a budget; criteria cannot truncate or evict the checkpoint. The only cap in
     `_compose_loop_briefing` is `_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000` (`:2043`), and it applies
     to the checkpoint alone.
   - **It is a different hazard from the one that requirement exists for.** `agent-loops`' bound is
     justified by *"so that a long-running loop's accumulated history cannot grow the size of what a
     single firing is asked to read"* — growth over **time**. A task's criteria are fixed by its
     document and do not grow with the loop's history. Extending a requirement about accumulation to
     cover something that does not accumulate would blur what it protects.

   **Residual — and the adversarial review found the bound all three rounds missed.**
   `spec_completeness.MAX_REQUIREMENTS_PER_TASK = 3` (`hub/hub/spec_completeness.py:39`, enforced at
   `:220-226`) is itself a stated requirement of the capability this change modifies —
   *"A declared task's requirement span is capped, and the Hub enforces it"*. A declared task can
   therefore contribute **at most three requirements' worth** of criteria, so open question 2's
   answer is right for a stronger reason than R3 gave, and task 5.4 has a concrete ceiling to
   measure against rather than an open-ended one.

   **The one gap in that bound:** it is enforced on the transition to `proposed`, so a document
   adopted from disk already at `proposed` or later, and then approved, is never checked against it.
   That is the same unvalidated-file window D6 covers, and it needs no separate remedy — but it does
   mean the cap is a strong norm rather than an invariant, and task 5.4 should not assume it.
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
- **R3** re-derived independently and **overturned R2's reasoning on its central point**. R2 had
  justified D3 by appeal to `validate_payload`; R3 found that the approval route parses the file
  with `extract_payload` (`api/v1/spec.py:1533-1537`) and that adoption never validates, so
  `validate_payload` constrains saving and not materialising. **D3's conclusion survives on a better
  reason** (both fields come from the same file, so they are self-consistent within it), **D6 is
  upgraded from prudent to load-bearing**, and a new accepted consequence is recorded with a test
  (3.12). R3 also **closed open question 2** — no `agent-loops` change, because the two blocks are
  concatenated rather than competing and criteria do not accumulate over time — and independently
  **re-measured the corpus**: all 32 spec-materialised tasks are `acceptance_criteria IS NULL`, none
  `[]`, which also confirms task 2.4's instruction to leave the field unset.

- **Adversarial review** (Opus, after R3, at the operator's standing instruction). Verdict: approve
  with fixes. It confirmed the premise, the reviewer-briefing benefit path, D1, D3, D5 and the
  corpus measurement by independent re-derivation — including that no competing review-briefing path
  exists (`api/v1/agent_trigger.py:852` dispatches through a turn context, `api/v1/agents.py:1614-1650`,
  that names the task and commit but no criteria). It then found five things three rounds had not:
  **D6's failure mode was wrong** (a committed partial board with no dependency edges, not an empty
  one — now D6 and D7); **`spec_reading.criteria_by_requirement_key` already exists** and all three
  rounds proposed rewriting it (now D7); **D2's key decision was pinned by nothing** (now a spec
  scenario, test 3.13, mutation 4.7); **D6 had no requirement text or scenario** and would have been
  lost when `tasks.md` is discarded at archive (now two scenarios); and **tasks 2.1 and D4
  prescribed opposite iteration directions**, which silently duplicates on a repeated requirement
  name (now task 2.2, tests 3.14/3.15, mutation 4.8). It also found the bound that closes open
  question 2 properly (`MAX_REQUIREMENTS_PER_TASK = 3`) and one inaccurate statistic in the
  proposal, both since corrected.

**What this round discipline caught that a single pass would not:** R1 named a hazard that does not
exist and prescribed the wrong remedy for it; R2 removed the hazard but justified the remedy with a
guarantee that does not hold where it matters; R3 kept the remedy and replaced the guarantee; the
adversarial review found that the remedy's own failure mode had been mis-stated by all three, and
that the function they were specifying was already in the repository. The instruction in the code
has been the same since R2 — everything after it has been about whether the *reasons* survive, and
the reasons are what the next person edits against.
