# The first real capability merge — what running it actually found

**Status:** findings from a live trial, not a proposal. Written 2026-08-18 after the operator chose
**Model A** from `2026-08-18-what-archiving-a-spec-means.md` ("run the merge that's sitting ready")
and ruled that the rigor/kind coupling should be **settled by experiment** rather than by argument.

Everything below was measured against the live trial Hub (port 8010, `hub/data/agentweave.db`,
project `proj-5e960453`), through the real HTTP endpoints, not in a test fixture.

## What was run

`spec/changes/quiet-hours-for-agent-notifications/spec.html` — phase `archived`, 7 requirements —
folded into `spec/capabilities/quiet-hours/spec.html`, an empty `current`-phase scaffold, via
`POST /project/documents/{path}/merge`.

Before: `spec_document_merges` held **0 rows**. The mechanism shipped 2026-08-16 with 270 lines of
unit tests and had never been exercised against real content. After: the capability document holds
**7 requirements** and the corpus has its first merge record.

## Finding 1 — a capability document is permanently "blocking" by rules written for changes

The first merge returned `200` with **14 blocking diagnostics**: every requirement flagged both
`requirement_without_criterion` and `requirement_without_task`.

Half of that was the author's fault and is worth separating out, because only the other half is a
finding. The first attempt carried the change's `requirements` but dropped its
`acceptance_criteria`. Carrying them cleared that half completely:

```
attempt 1 (requirements only):     {'requirement_without_criterion': 7, 'requirement_without_task': 7}
attempt 2 (+ acceptance_criteria): {'requirement_without_task': 7}
```

What remains cannot be authored away. `requirement_without_task` says *"'r1' is in neither the
document's own tasks[] nor a task already on the board, so nothing implements it."* For a change
document that is exactly the right question. For a capability document it is unanswerable by
construction: a capability states **shipped** behaviour, so there is nothing left to implement it,
and carrying the change's `tasks[]` across would assert that finished work is still outstanding.

So the corpus's own documents are, today, permanently in a blocking state — and the validation
rules do not distinguish `kind='capability'` from `kind='change-spec'`. Nobody could have seen this
from the design: it needed one real merge.

**Not decided here:** whether the fix is to exempt capability documents from the task rule, to
replace it with a merge-provenance rule ("every requirement traces to a cited source change"), or
to accept blocking as cosmetic for `current`-phase documents.

## Finding 2 — merging into a gated capability document is a 500, and it half-commits

The Q8 exploration predicted that a capability document at `contract`/`gate` rigor would silently
divert its merges into per-requirement proposals, because `save_document()` branches on
`document.rigor`, not `document.kind`. That prediction was **right about the mechanism and wrong
about how it fails.** Measured:

```
proposals before:            0
raise rigor to gate ->       200
merge at gate rigor ->       500  Internal Server Error
proposals after:             1
edit visible in document:    False
```

Called in-process, `spec_service.merge_document()` behaves correctly and returns a `ProposeResult`.
The break is one layer up, in the API:

```python
# hub/hub/api/v1/spec.py:1186-1190
await session.commit()
return {**_document_view(document), "blocking": result.blocking, "merged": len(sources)}
```

`ProposeResult` (`spec_service.py:52-62`) carries `path`, `proposals`, `unchanged` — and **no
`blocking`**. The merge route was written assuming `save_document` always returns a `SaveResult`,
which stops being true the moment rigor is raised; `spec.py` contains no reference to
`ProposeResult` anywhere.

The ordering is the damaging part. `session.commit()` runs **before** the attribute access, so the
proposal row is durably written and *then* the request fails. The operator sees a 500 and no
document change, while a pending proposal they never saw created sits in the database. That is what
produced the orphan row still present in this project (`spec_edit_proposals` count: 1).

`test_spec_merge.py` has zero references to `rigor` — the interaction is untested in both
directions, which is why a 500 on a shipped route survived two days undetected.

**Verdict on the coupling itself:** the *behaviour* — review a merge requirement-by-requirement
when the document is gated — is defensible and arguably what a gate should mean. The *implementation*
is broken: it cannot return, it commits before it fails, and it strands a proposal. Those are
separable, and only the second is unambiguously a bug.

## Finding 3 — merge records are written even when the request fails

`spec_document_merges` ended this session with **4 rows** from 4 attempts, two of which returned
500. Provenance rows are committed alongside the proposal, before the failure. So the merge history
of a capability document can record folds that the operator was told had failed, which makes
`spec_document_merges` unreliable as an audit trail exactly when something went wrong.

## State this left behind

In `proj-5e960453` on the trial Hub, deliberately not reverted — it is the first real corpus content
this project has, and it is more useful as a fixture than as a clean slate:

| | |
|---|---|
| `spec/capabilities/quiet-hours/spec.html` | phase `current`, rigor restored to `sketch`, **7 requirements**, 7 acceptance criteria |
| `spec_document_merges` | 4 rows (2 from failed requests — see Finding 3) |
| `spec_edit_proposals` | 1 orphan, from the crashed gated merge |

## What this says about Model A

The operator's choice was the cheap one, and it paid: three defects surfaced in under an hour that
no amount of reading the design would have produced, and one of them (Finding 2) is a live 500 on a
shipped route. The exploration's own framing — *"the code has an answer; reality has not tested
it"* — held exactly.

It does **not** yet answer the question Model A was supposed to answer: whether a whole-document
authored merge is pleasant to maintain as a capability grows. One merge of 7 requirements into an
empty document is the easiest possible case. The interesting case is the second merge into the same
capability, where authoring means reconciling new requirements against ones already there by hand —
and that has still never been done.
