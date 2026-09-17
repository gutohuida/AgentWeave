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

**The design consequence:** build the criteria index **once, before the loop** (D7), *and* make it
total (the guard, D7/D8). The two do different jobs, and an earlier draft of this paragraph confused
them — corrected by the second review:

- **Position** converts a *prefix* failure into an *all-or-nothing* failure. A raise before the loop
  means `materialise()` returns nothing and `materialise_quietly` swallows it, so **no task is
  created** — bad, but recoverable by re-approval, and free of the silent dependency-edge hole a
  committed prefix leaves behind.
- **Totality** is what actually delivers the spec's outcome, "every task created, none with
  criteria". Position alone does not; the guard does.

Mutation 4.10 already states this correctly (*"Remove the `isinstance` guard → 3.18 fails, and fails
by creating no tasks"*), and the earlier wording here contradicted it.

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
but a scalar (`"acceptance_criteria": 5`) raises `TypeError` — which is precisely D6's failure.

**The guard goes inside the helper, not at this change's call site — corrected by the second
review.** D7 originally put it at `materialise()`. The helper's other caller is
`spec_reading.requirement_view` (`spec_reading.py:130`), reached from `read_spec_document`
(`hub/hub/api/v1/agent_actions.py:1399`), which parses the same file with the same unvalidating
`extract_payload` and has no `try`/`except`. Guarding only the new call site leaves the identical
`TypeError` reachable there, turning an agent's `read_spec_document` into a 500 for exactly the
unvalidated file this change insists must not cost a document its tasks.

One line inside the helper — `raw = payload.get("acceptance_criteria")`, return early unless it is a
list — fixes both callers, and is what CLAUDE.md's "cleanest solution wins" argues for.

**The same guard is needed on `statements_by_key`, and the D4 reversal is what makes it necessary —
found by the third review.** `spec_reading.py:72` reads `for entry in payload.get("requirements") or
[]`, character-for-character the hole being closed at `:98`. Until the reversal this did not matter
to this change, because **`materialise()` never reads `payload["requirements"]` at all** — it uses
the database rows (`spec_tasks.py:149-159`) and `spec_identity.read_identity`, which is total
(measured: `read_identity({"requirements": 5})` returns `({}, 0)`). D4's reversal introduces the
first raw read of that key, so it introduces the hazard with it. Under `materialise_quietly` the
resulting `TypeError` produces **zero tasks with the approval reporting success** — what this design
calls its most serious risk, reintroduced by a later decision in new code.

**A guard is not pinned by a test that passes either way.** Test 3.18 asserts through
`materialise_quietly` and passes identically whether the guard sits in the helper or at this
change's call site, so it does not pin D7's relocation at all — the same "pinned by nothing" defect
the first review fixed for D2. `hub/tests/test_spec_reading.py:205-215` exercises grouping order
only and nothing reaches `requirement_view` with a scalar. Task 3.22 closes that.

CLAUDE.md's standing preference is that the cleanest solution wins; a second grouping of the same
data, differing from this one in the interleaving case its docstring names, is the opposite of that.

**The index is built once, before the per-entry loop**, for the reason in D6: a payload this code
cannot read must fail the same way for every entry, not part-way through.

### D8 — Rendering must be total in output, not only in control flow — **added by R4**

R4 probed `criteria_by_requirement_key` directly against ten hostile payloads. Two results matter.

**The scalar hole is real**, confirming the review rather than taking it on trust:
`{"acceptance_criteria": 5}` raises `TypeError: 'int' object is not iterable`. `{"...": "abc"}`,
`{"...": {"a": 1}}` and `{"...": [1, 2]}` all degrade harmlessly to `{}`. So the
`isinstance(..., list)` guard in task 2.1 is load-bearing, not decoration.

**And a case neither the rounds nor the review reached: the helper preserves a missing handle as
`None`.** `{"requirement": "r1", "key": None, "given": "g", "when": "w", "then": "t"}` returns
`{'key': None, 'given': 'g', ...}`, and `{"requirement": "r1"}` alone returns all four as `None`.

Under D2's `<key>: Given ..., when ..., then ...` those render as the literal strings
`"None: Given g, when w, then t"` and `"None: Given None, when None, then None"`. **Neither raises,
and both violate the requirement the review's own fix added** — a criterion rendered `None:` does
not carry the handle the document gave it, and two handle-less criteria render identically, so they
are not distinguishable. The second is worse: a line of pure noise inserted into the reviewer's
briefing under the heading "Acceptance criteria", which is the opposite of this change's purpose.

Reachable exactly where D6 says: `AcceptanceCriterion.key` is a required `str` under
`validate_payload` (`spec_payload.py:92`), and the approval path does not validate.

**Decisions:**

- Render the handle **only when it is a non-empty string**. Otherwise render
  `Given ..., when ..., then ...` with no prefix. Attaching the criterion still beats withholding
  it: the statement is what the work is judged against, and the handle is the label.
- **Skip a criterion whose `given`, `when` and `then` are all absent.** It states no standard, and a
  `Given None, when None, then None` line is worse than its absence.
- Render a *partially* absent criterion with the parts it has, rather than dropping it — the spec's
  "binary outcome" scenario is about not discarding the `then` in favour of the `when`, not about
  refusing an incomplete declaration.

This is why D6's "total" is stated as totality of **output**, not merely absence of an exception. A
function that cannot raise but emits `"None: Given None"` has satisfied the letter of D6 and
defeated the change.

### D4 — Ordering is grouped by requirement, in requirement declaration order — **reversed by the second review**

Criteria are attached **grouped by the requirement they belong to, in `payload.requirements`
declaration order, stable within each requirement**.

**R1 decided the opposite and its reason was false.** R1 wrote that criteria should follow
`payload.acceptance_criteria` order because *"a reader comparing the task against the document
should see the same sequence"*, and R2, R3, the first adversarial review and R4 all left it
standing. The document that reader actually sees does **not** use payload order —
`hub/hub/spec_render.py:305-318` sorts criteria into requirement order before rendering the table,
and says why in its own comment:

> *"Grouped by the requirement each criterion belongs to, in requirement order. Submission order is
> the author's and is not this order: the first agent-authored document listed FR-8, FR-8, FR-7, and
> a reader scanning the table by requirement lost their place. The sort is stable, so criteria for
> one requirement keep the order they were written in — that order carries the author's emphasis and
> is theirs to choose."*

So payload order is the one sequence the reader will never see, and this repository already settled
the question the other way, after a real incident. `criteria_by_requirement_key`'s docstring takes
the same side, calling per-caller re-derivation *"wrong, for a document whose criteria interleave"*
(`spec_reading.py:91-93`).

**Match `spec_render._acceptance` exactly — and "exactly" means its algorithm, not a paraphrase of
its effect.** It builds a position map from `payload.requirements` and applies **one stable sort**:

```python
position = {r.key: i for i, r in enumerate(payload.requirements)}
ordered = sorted(criteria, key=lambda c: position.get(c.requirement, len(position)))
```

**The third review found that the paraphrase this design first shipped does not reproduce it.**
"De-duplicate the entry's names, then concatenate their groups in `payload.requirements` order"
differs in two ways, both measured:

- **It silently drops criteria whose requirement is missing from `payload.requirements`.**
  `position.get(..., len(position))` sorts such a criterion *last but keeps it*; a
  concatenation-of-groups never visits it. Executed: `_acceptance` yields
  `['ac2','ac1','ac3','ac4']` where the group concatenation yields `['ac2','ac1','ac3']`. This is
  reachable exactly where D3 and D6 say the interesting cases are — the approval route parses an
  unvalidated file, so a hand-edited document can name a requirement in `tasks[].requirements` and
  in a criterion while the `requirements` list no longer holds it. The task still resolves it from
  the database rows (`spec_tasks.py:190`) and its criteria vanish — violating this change's own
  first SHALL.
- **The sentence named two orderings at once** — "de-duplicated, first-appearance order" *and* "in
  `payload.requirements` declaration order" — which are different results whenever an entry lists
  its requirements in a different order from the document: `['ac1','ac3','ac2']` against
  `['ac2','ac1','ac3']`.

So the rule is: collect the criteria for the entry's requirement names, then apply that one stable
sort with `len(position)` as the fallback. Not a concatenation of groups.

**Repeated names still de-duplicate.** An entry naming the same requirement twice is not refused
anywhere (measured: `requirements: ["req-a", "req-a"]` is accepted), so the names are reduced to a
set before their criteria are collected — otherwise the criteria appear twice.

**This reversal also dissolves a contradiction the second review found (its F1).** D7 mandates
reusing `criteria_by_requirement_key`, which returns `{requirement key: [criterion, ...]}` and
therefore *cannot* reproduce cross-requirement payload order — while task 2.2, as written after the
first review, forbade exactly the grouping D7 requires, and mutation 4.8 would have been satisfied
by the prescribed implementation itself. No implementation could satisfy both. With D4 reversed the
helper is the right tool, the grouping is the wanted behaviour, and the contradiction is gone.

**Repeated names still de-duplicate.** An entry naming the same requirement twice is not refused
anywhere (measured: `requirements: ["req-a", "req-a"]` is accepted), so the entry's names are
reduced to a set — preserving first-appearance order — before their groups are concatenated.

### D5 — Already-materialised tasks are not backfilled

`materialise()` skips any entry whose key is in `existing_keys` (`spec_tasks.py:176`), so a
re-approval never revisits a task it created earlier. Tasks that exist today keep empty criteria.

This is a deliberate limit, not an oversight: a backfill would have to decide what to do about a
task whose document has since been revised. **The consequence is that this change does nothing for
the 32 tasks that motivated it** — it changes what happens next, not what already happened. Anyone
measuring its effect must measure on tasks created after it ships.

**R4 found that this is stronger than "not backfilled": `acceptance_criteria` is write-once.** It is
a field of `TaskCreate` (`hub/hub/schemas/tasks.py:45,64`), written at `api/v1/tasks.py:770`, and it
appears on **no** update path — not on `TaskUpdate` (`schemas/tasks.py:120-142`), and not in the MCP
surface, whose `update_task(task_id, status, notes)` (`mcp_server.py`) cannot reach it.

Two consequences:

- **A hazard that does not exist, checked and recorded so nobody re-checks it:** no agent can
  overwrite or clear the criteria it is being judged against. The standard is immutable once set.
- **The 32 existing tasks can never acquire criteria through any supported route** — not by the
  operator in the UI, not by an agent, not by re-approval. Only a direct database write, or deleting
  them so a re-approval re-materialises them. D5's limit is therefore permanent for those rows, and
  R2's irreversibility argument for D2 is not merely supported by "no backfill" but by "no write
  path at all".

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
2. **Does the briefing need a criteria bound?** — **RE-OPENED by the second review, and now answered
   YES.** R3 closed this, and its closure answered only half the question the design itself had
   asked. The original test was: *"confirm that a pathological document cannot produce a briefing
   that displaces the prior checkpoint **or overruns the job message**."* R3 answered displacement
   and nobody answered the second clause.

   **The briefing is delivered as a command-line argument.** `scheduler.py:3088` builds
   `content = f"{briefing}\n{job.message}"`, and `runner_commands.py:268` emits `cmd += ["-p",
   prompt]` (Codex, `:337`, passes it positionally). Windows caps a command line at 32,767
   characters, and a run routed through `cmd.exe` at 8,191. `pty_runner.py:68-88` records that this
   repository has already been burned on this exact delivery path.

   **Nothing truncates `content`.** The only cap in `_compose_loop_briefing` is
   `_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000`, for the checkpoint alone.

   **And the "concrete ceiling" this design previously cited is not one.**
   `MAX_REQUIREMENTS_PER_TASK = 3` bounds how many *requirements* an entry may name. `spec_payload`
   sets no `max_items` on `acceptance_criteria` and no `max_length` on `given`/`when`/`then`, so
   three requirements' worth of an unbounded number of unbounded strings is unbounded.

   **[SUPERSEDED — the two derived figures in this paragraph are fabricated. Read the decision
   below before quoting anything from it.]** *Measured over this repository's own 1,319 real
   acceptance criteria*, rendered as D2 specifies: mean 164 characters, p90 220, max 362; criteria
   per requirement mean 2.92, max 12. *A typical three-requirement task contributes about 1,438
   characters; the observed worst case is about 13,032 — more than three times the cap the checkpoint
   beside it gets, from real documents rather than a contrived one.* The four marginal statistics are
   real and were re-measured by the fourth review (which counted 46 payloads / 1,337 criteria against
   this paragraph's 41 / 1,319 — corpus growth, since every derived figure agrees). **The 1,438 and
   the 13,032 are not measurements at all**; see below.

   **Decision, after the third review: no bound in this change, and no second capability.** A
   bound was added on the strength of that ~13,032 figure and has been removed, because the figure
   did not survive checking: it is exactly `362 × 12 × 3` — three independent marginal maxima
   multiplied — and was presented in this design and in the proposal as an *observed* worst case
   "from real documents rather than a contrived one". It was neither observed nor from any one
   document.

   **The measured worst real three-requirement block over the same corpus is 5,462 characters**
   (`spec/capabilities/agent-conversation-workspace/spec.html`), 1.37× the checkpoint's cap rather
   than "more than three times" it, against a 32,767-character `CreateProcess` ceiling. The typical
   figure was likewise a product of means (`164 × 2.92 × 3 = 1,437`). And the corpus declares **zero
   tasks**, so it contains no instance of the quantity being sized at all.

   Three further defects in the bound as drafted, each sufficient on its own:

   - **It had no implementation task.** `tasks.md` §2 edited only `spec_reading.py` and
     `spec_tasks.py`; nothing created the cap, while test 3.20 and mutation 4.13 referenced it.
   - **The proposal forbade it** — Non-goals said "no new briefing section, no new scheduler
     branch", Impact listed neither `scheduler.py` nor `spec_reading.py`, and Goals still said
     "confined to one function".
   - **It contradicted D8.** Slicing a block to a character cap lands mid-criterion, presenting a
     criterion whose `then` has been cut off as though it were whole — precisely the harm D8 exists
     to prevent. Nothing said to truncate at a criterion boundary; "the fixed size bound" named two
     different bounds in one requirement; and "SHALL make the truncation visible" contradicted the
     checkpoint's deliberately invisible truncation (`scheduler.py:2469-2470`) that the same
     requirement kept unchanged.

   **The residual risk is therefore accepted and unmitigated, as R3 originally had it** — but now
   with a real number behind it rather than an absent one. A criteria bound may still be worth
   having on context-cost grounds. That is a different argument, it needs its own evidence, and it
   belongs in its own change.

   ~~R3's two reasons, kept because both are still true and neither answers the question:~~
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

- **R4** (after the review, at the operator's instruction) probed the reused helper by execution
  rather than trusting the review's read of it. It **confirmed** the scalar hole
  (`TypeError: 'int' object is not iterable`) and **confirmed a hazard does not exist** —
  `acceptance_criteria` appears on no update path, so no agent can clear the standard it is judged
  against. It found two things the review did not: **a handle-less criterion renders as the literal
  `"None: …"`**, violating the identifiability requirement the review's own fix had just added and,
  in the all-absent case, injecting `"Given None, when None, then None"` into the reviewer's
  briefing (now D8, tests 3.16-3.18, mutations 4.9-4.11); and **the review's new "changes nothing
  about which tasks exist" scenario was vacuous**, because approving one document twice creates
  nothing under `existing_keys` (now reworded to two documents). It also sharpened D5: the 32
  existing tasks are permanently unfixable, not merely un-backfilled.

- **Second adversarial review** (Opus, independent of the first, over the state R4 left). Verdict:
  **do not approve** — two blocking findings, both verified here before being acted on. It found
  that **D7 and task 2.2 prescribed mutually exclusive implementations**, with mutation 4.8
  satisfied by the very implementation D7 mandated; and that **D4's justification was refuted by the
  codebase**, since `spec_render._acceptance` (`spec_render.py:305-318`) already groups criteria by
  requirement and rejects submission order, citing the real incident that settled it. Reversing D4
  dissolved the contradiction. It also **re-opened open question 2**, showing R3 had answered only
  the displacement half while the briefing reaches the runner through argv with nothing truncating
  it, and measured this repository's own 1,319 criteria to put the worst case at ~13,032 characters
  — which adds `agent-loops` as a second modified capability. Further: the `isinstance` guard was in
  the wrong layer (the helper's other caller would still 500), **D6's stated consequence contradicted
  mutation 4.10**, the `already_served` skip makes scenario 1's conclusion false while its premise
  holds, two SHALLs were over-broad, and the ordering decision was pinned by nothing durable — the
  same defect the first review fixed for D2 and left here.

- **Third adversarial review** (Opus, over the state the second review left, which had had no
  verification pass at all). Verdict: **do not approve**. It found that the `agent-loops` scope
  increase **had no implementation task** while three places in the proposal and design forbade the
  edit it needed; that the D4 reversal introduced a **new unguarded read of `payload["requirements"]`**
  — `materialise()` had never read that key, and `statements_by_key` (`spec_reading.py:72`) carries
  the identical hole D7 closes at `:98`, so the reversal reintroduced this design's own worst
  failure in new code; that task 2.2's algorithm **did not match `spec_render._acceptance`** and
  silently dropped criteria whose requirement is absent from `payload.requirements`, while naming
  two different orderings in one sentence; that test 3.15 and mutation 4.8 **did not discriminate**
  the correct ordering from the naive one; that mutation 4.6 contradicted D6 as corrected and test
  3.11's fixture was unconstructible; that D7's guard relocation was **pinned by no test**; and —
  most seriously — that **the ~13,032-character figure justifying the whole scope increase was
  `362 × 12 × 3`**, a product of three independent marginal maxima, presented in the proposal as an
  observation "from real documents". The real worst three-requirement block is 5,462 characters, the
  corpus declares zero tasks, and the `agent-loops` delta was removed.

  It also **confirmed** that the D4 reversal itself is correct (and found it is a shipped
  requirement, `openspec/specs/spec-document-authority/spec.md:756-779`, citing the same incident),
  and that **the common case survives all six passes' accumulated guards** — a document declaring
  one to three requirements with criteria still produces a task whose criteria render under "What
  the author was asked to build" for a loop- or flow-fired review.

- **Fourth adversarial review** (Opus, over the state the third review left — which, like the second,
  had had no verification pass). Verdict: **approve with fixes**, the first non-blocking verdict this
  change has had. Every fix is local to `tasks.md` and the delta spec; none reopens a decision. It
  found three blocking defects, all in the third review's own additions:

  **B1 — the delta spec forbade what `tasks.md` requires.** The spec said criteria attach to every
  requirement a task *resolves*; D3 and task 2.2 match on what its entry *names*. Those diverge:
  `spec_tasks.py:187-194` puts an unresolvable name in `unresolved` while still creating the task, so
  an entry naming a requirement with no stored row produced a task that resolves nothing and carries
  a criterion — against the spec's own "and SHALL attach no others". Test 3.23 *required* that
  behaviour, and no scenario covered it, so at archive (when `tasks.md` is discarded) the only
  durable statement of it would have been the one forbidding it. Reworded to *names*, with the
  reasoning stated and a scenario added.

  **B2 — the `statements_by_key` guard was pinned by nothing.** Task 2.7's "a guarded read of
  `payload["requirements"]`" is satisfied by an inline `isinstance`, leaving mutation 4.16 flipping
  no test; and test 3.24 asserted the wrong outcome, since matching on `named` (D3) is independent of
  `payload["requirements"]` — a scalar there costs the ordering, not the criteria. Nothing covered
  `requirement_view` with a scalar `requirements`, which is the exact 500 D7's guard-in-the-helper
  argument exists to prevent. Task 2.7 now names the helper, 3.24 is restated, and 3.25 / 3.26 /
  4.17 were added.

  **B3 — "the exact algorithm of `_acceptance`" was false, and the prescribed `set` was
  nondeterministic.** `spec_render._acceptance` sorts the flat criteria list; D7's helper groups
  first. Filtering commutes with a stable sort, so they agree for any document that ever passed
  `validate_payload` — but where **two or more** of an entry's requirements are absent from
  `payload["requirements"]` both take the `len(position)` tie key and the two orders differ
  (demonstrated by execution). And "reduce to a set" made the tie order depend on set iteration,
  which varies per process for strings, so two approvals of one file could store different orders.
  Now `dict.fromkeys`, with the divergence stated honestly instead of denied.

  It also found that the helper's criterion dicts **do not carry their `requirement`**
  (`spec_reading.py:104-111`), so task 2.2's sort key read as a field that does not exist — a literal
  implementation would have sorted nothing. And it **confirmed** the premise, both helper holes by
  execution, the D4 reversal, that 3.15/4.8/4.8b genuinely discriminate (three distinct orderings,
  worked by hand), that 3.11's fixture is constructible, every line citation it spot-checked, and the
  5,462 figure **to the character**. Its one unresolved item is the proposal's "62 measured turns /
  47 classified / 1,898,949 average", which it could not reconstruct under any filter — unverified
  rather than refuted, and recorded as such.

**What this round discipline caught that a single pass would not:** R1 named a hazard that does not
exist and prescribed the wrong remedy for it; R2 removed the hazard but justified the remedy with a
guarantee that does not hold where it matters; R3 kept the remedy and replaced the guarantee; the
adversarial review found that the remedy's own failure mode had been mis-stated by all three, and
that the function they were specifying was already in the repository. The instruction in the code
has been the same since R2 — everything after it has been about whether the *reasons* survive, and
the reasons are what the next person edits against.
