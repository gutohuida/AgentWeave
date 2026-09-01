# Decisions waiting for the operator

The backlog of questions the unattended windows could not answer for themselves. Written by the
windows, cleared by the operator, and **durable** — before 2026-09-01 these lived only in
`STATE-night.json`, which each window rewrites, so the list survived by being copied forward by
hand and had drifted into duplicates.

Contract, matching `APPROVALS.md`: **the status token is the authority.** One row per decision.

```
- OPEN      <id>  the question
- DECIDED   <id>  what was decided, and when
- DEFERRED  <id>  why, and what would reopen it
```

A window may **add** rows and may sharpen an OPEN row's evidence. A window may never mark one
DECIDED. Absence is not consent.

---

## Re-triage of 2026-09-01, evening — eight rows to three

The morning triage folded 32 raw entries into 8 rows. An evening pass compared all eight **against
the code** rather than against each other, and six of them turned out not to be decisions.

Two structural faults caused most of it.

**One token cannot answer ten questions.** D-7 absorbed ten entries and D-8 seven. The contract at
the top of this file says one row per decision and the status token is the authority — so there was
no answer the operator could give that made either token true. Answer two of D-7's ten and it stays
`OPEN`, and the answered parts get re-asked. Both were unclosable by construction, which is why
both sat. **D-1 is the only row that ever closed, and it is the only one that was a single
question.** Grouping is good for reading and fatal for tokens: from here, group in prose, tokenise
per question.

**A label can block work it does not describe.** D-7 was named "response-shape and API-surface calls"
and justified as "each changes a contract an existing caller depends on". Measured against the code,
**one of its ten entries** actually does. Three are purely additive — `GET /tasks/{id}/transitions`
is a new route with nothing to break (verified: no route and no MCP tool exists, the thirteen code
references are all writes), and `F212` adds a `document_id` the same response already carries. Those
sat parked behind a rationale that was never true of them.

### Where every earlier row went

| Was | Now | Why |
|---|---|---|
| **D-1** fastmcp ceiling | **stays, DECIDED** | Ratified in session 2026-09-01. Kept below as history. |
| **D-2** pin fastapi | **→ R-1** | The path that actually bit is already closed; what remains is an instance of the unwritten ceiling rule. |
| **D-3** refusals with no surface | **→ R-1** | "One convention or eleven fixes?" is R-1's question, and this is its best-evidenced instance. |
| **D-4** standing rules vs instances | **→ R-1**, three rows dropped | Measured: three of its four sweeps are 2-9 sites. Only the fourth needs deciding. |
| **D-5** sweep vs repair | **→ queue** | Overtaken: two of its three severity-A items now have approved changes. |
| **D-6(a)** archive collision | **→ R-2** | A genuine tooling call, unrelated to (b). |
| **D-6(b)** corpus ahead of code | **→ R-1** | "May a task tick on backend evidence alone?" is a rule question. |
| **D-7** API-surface calls | **→ R-3 + queue + R-1** | Splits three ways; see below. |
| **D-8** stale rows | **→ queue** | A bring-forward list, not a decision — and it rests on a figure this file already disproved. |

Nothing is lost: every original entry number is still named by whichever row now carries it.

---

### R-1 — Does this repo enforce conventions, or repair instances?

**OPEN. The one decision that manufactures the answers to most of the others.** Absorbs D-2, D-3,
D-4, D-6(b), and behind them entries 3, 5, 8, 10, 11, 13, 15, 16, 20, 27, plus F169, F173, F178,
F179, F180, F187, F190, F195, F197, F201.

The question in one line: **when the repo learns a rule, does it write a check that enforces it, or
does it fix the instance and rely on remembering?**

**The repo already answers this two ways at once, which is the tell.** `fastmcp>=2.0,<4` and
`starlette<2.0` are the *same move* — a defensive ceiling so a major needs a conscious bump — taken
twice, months apart, each with the reasoning written into a comment beside it. That is a standing
rule in practice that no file states and no check enforces. Meanwhile the same defect class gets
re-filed: *the Hub computes a sentence for an operator and no file under `hub/ui/src` reads it* has
been filed **six times across two nights**.

**The evidence, verified against the tree 2026-09-01:**

- `ChartersPage.tsx:191` is `createCharter.mutate(values, { onSuccess: … })` — **no `onError`**. The
  refusal is a plain 422 the mutation already holds. Nothing needed computing, wiring or designing,
  which is what makes this a missing convention rather than a refactor.
- `GET /documents/{path}/rigor-history` exists (`hub/hub/api/v1/spec.py:535`) and returns **zero
  hits** across `hub/ui/src`. Ten more operator-only routes are 0-hit in both the source and the
  served bundle. `spec_rigor.py`'s own docstring justifies allowing demotion *on the grounds that
  the audit trail exists* — and no screen shows it.
- The old D-2 is closed at the point it actually bit: `starlette<2.0` is pinned nineteen lines below
  `fastapi>=0.110`, and its comment names the exact incident — *"an unbounded fastapi>=0.110 once
  let pip silently resolve starlette 1.6.0 in CI while dev ran 0.52.1."* Both CI failures were
  Starlette crossings. What is left is FastAPI's own major: real, unrealised, and a *third* instance
  of the same unwritten rule.
- `runner-registry/spec.md:72-73` is a shipped requirement whose UI half was never built — ticked on
  backend evidence alone and archived. The approved `runner-model-is-chosen-from-the-catalog`
  repairs that instance; whether a task may tick on backend evidence alone is the rule question.

**What the old D-4 got wrong, measured.** It presented four findings as symmetric, each naming "a
grep that would say how big it is". The greps were never run. They are:

| From | Measured sweep |
|---|---|
| **F190** | **2** functions — and both are deleted by the change approved 2026-09-01 |
| **F195** | 21 `subprocess.run`/`Popen` sites, **13 already pass `cwd`** → ~8 |
| **F201** | **9** `model_validator`s under `hub/hub/schemas/` |
| **F197** | **133** `useQuery` declarations; 62 of 97 component files never mention `error` |

At 2, 8 and 9 sites the rule-or-instance question is academic — do both, in an afternoon. Those
three rows are **queue work, not decisions**, and are moved below. Only **F197** is large enough to
need an answer, and its real question is not the one D-4 asked: it is whether an unrendered query
error is a defect *at all* in every case, since a background poll's failure may be correctly
invisible. (133 is an order-of-magnitude grep, not a defect count.)

**The decision has two halves, unchanged from D-3 and still the right two:**

**(a)** Are the eleven operator-only routes en route to a screen, deliberately API-only, or dead? A
standing answer settles the sweep's remaining rows too.
**(b)** Should a repo check assert that a server-side refusal string is grep-able somewhere in the
UI, and that a mutation whose failure an operator must see carries an `onError`?

**Why this one first.** Answering it settles the old D-2 and D-6(b) for free, empties three of
D-4's rows into the queue, and supplies the missing axis for what an unattended window may take —
see *The axis that actually predicts it* below.

---

### R-2 — Should `openspec archive` refuse a colliding delta?

**OPEN.** Was D-6(a). Absorbs entry 18. A tooling call, unrelated to R-1.

Applying a delta against the current corpus warns about nothing when two changes both carry a
`## MODIFIED` block for the same requirement. Archiving the second **reverted the first**, dropping
a qualification that had just landed. Caught only because the diff was read before committing;
repaired, and the other six were swept — exactly one collision in a batch of seven. **Two changes in
flight against one requirement is not rare here.**

Should archiving be gated on a collision check, and does that belong in a repo script, in the
`openspec-archive-change` skill, or upstream?

---

### R-3 — Four small product calls

**OPEN, but each is one question with two defensible answers and closable in a sentence.** These are
what is left of D-7 once the additive work and the already-answered rows are removed. Absorbs
entries 1, 6, 19, 21.

- **F209** — `accept` declares a 2000-character `reason` and **stores nothing**; `reject`, three
  functions away, keeps it. Thread it through, or delete the field. The current state promises
  something it discards.
- **F196 + F198** — should `PATCH /queue/settings` exist at all? It writes four columns
  `PUT /projects/{id}/settings` already owns, with a weaker contract on both ends, and the UI never
  calls it.
- **Entry 19** — should a bare `uvicorn hub.main:app` from `hub/` **refuse to start** on the
  relative default rather than silently opening a second database beside the one everything else
  uses? This has cost time twice.
- **Entry 21** — `model_catalog.py` names `~/.codex/models_cache.json` as its source of truth and
  nothing re-checks it; it has drifted. Per-machine and absent in CI, so it can only be a
  skip-if-missing check or a `scripts/` tool. *Doing nothing is defensible; doing nothing silently
  is what let a phantom default model sit in the catalog for four weeks.*

---

## The axis that actually predicts what a window may take alone

D-7 asked *which kinds of change need the operator*, and answered "response-shape ones". Measured,
that answer was wrong about nine of its own ten entries. The property that actually separates them
is not the kind of change:

```
        is the right answer already written down?
                    │
        ┌───────────┴────────────┐
       YES                      NO
        │                        │
     REPAIR                  DECISION
   a window takes it        needs the operator
        │
        └── ...but wide or irreversible?
                    │
              REPAIR + GATE
        observe first, verify after
```

The gate arm is not theoretical: `a-turn-says-how-it-ended` was approved 2026-09-01 as a **BREAKING**
response-shape envelope — precisely D-7's blocked class — and what made it safe was not a signature
but a condition. Its phase 0 stops any builder until the defect has been observed live, and its
phase 7 puts verification in a different sitting than implementation. Authorization queues on a
person; evidence queues on a check.

**R-1 is this axis restated.** Deciding whether the repo enforces conventions is deciding whether
answers get written down — which is what moves work from the right branch to the left.

---

## Not decisions — moved to the queue

These were carried as decisions and are not. Each is work with a known answer, or a scheduling call
already made.

**From D-7 — additive, nothing to break, window-takeable:**

- **F203** — `task_transitions` is append-only, carries actor/run/policy, has a reader, and no route
  or MCP tool exposes it; drives have had to open sqlite. Verified 2026-09-01: **no GET route and no
  MCP tool exist** — the thirteen code references are all writes. `GET /tasks/{id}/transitions` is a
  new route with no existing caller to break.
- **F212** — `GET /spec/coverage` projects `unserved` to bare identifiers, which are minted per
  document, so 34 entries all read `FR-1` and feeding one back answers **422**. The same response's
  `requirements` array already carries `document_id`. Additive.
- **F202** — `GET /projects/{id}/tasks` defaults to `limit=100` with no `total`/`has_more`/`next`,
  so at 241 tasks the Overview says "100 tasks". Part two is independently fixable: `list_tasks` in
  `mcp_server.py` has no limit or offset at all. Both additive.

**From D-7 — already answered by something already written down:**

- **F185 + F181** — agent queries with no lifecycle filter. D-7 itself named clearing the bindings
  on archive as "cleanest, closes both at source", and the operator's standing directive is that the
  cleanest solution wins and "more work" is never the objection. Apply it; note that `unarchive`
  must then say the bindings are gone.
- **F193** — what archiving an agent means for its open threads. **The product already made that
  three-way choice explicitly** for archiving a conversation with a live run. Follow the precedent
  unless it is wrong.

**From D-4 — sweeps small enough that the meta-question is moot:** F190 (2 sites, already in an
approved change), F195 (~8), F201 (9). Do the narrow fix and the sweep together.

**From D-5 — overtaken by events.** Its recommendation was to spend a window on F173, F188 and F190
rather than on coverage row 9c. Since it was written, **F173** has an approved change
(`runner-model-is-chosen-from-the-catalog`) and **F190** has one approved conditionally
(`a-turn-says-how-it-ended`). Verified 2026-09-01: **F188 has no change and no design** — nothing
under `openspec/changes/` references it. What is left is not a prioritisation decision but one queue
entry: *F188 is the last unspecced severity-A.* Its cited ledger size of 219 headings is now 289.

**From D-8 — a bring-forward list.** Absorbs entries 22-26, 28, 29. Re-queue or close, per row; none
needs a decision from the operator except by being scheduled. One correction: the row claims the Hub
suite runs "~25 minutes". **This file already disproves that** — `hub/tests/` was measured at
**14:39** on 2026-09-01, recorded under *Closed by measurement* below. `STATE-night.json:101` still
carries the 25-minute figure and should be corrected with it. Also still live there: F47/F120's
categorical third-actor prohibition, F77 (an agent has no way to address the operator), F53/F65
never queued, five findings queued 2026-08-29 and dropped from three runs, and the 8010 trial Hub
serving four-day-old code.

---

## Decided

### D-1 — Ratify or widen the `fastmcp <4` bound

**DECIDED 2026-09-01 — RATIFIED by the operator, in session.** The bound stands as taken. Absorbs entries 17, 31. Severity: low, reversible in one line.

FastMCP 4.0.0 reached PyPI 2026-08-31T18:20:31Z. This repo declared `fastmcp>=2.0` **unbounded** in
three places, and CI resolves fresh with no lockfile — so CI and this machine had already diverged
on the process that starts every agent turn (`pip index versions fastmcp`: LATEST 4.0.0, INSTALLED
3.1.0). The night bounded it to `>=2.0,<4` unattended and added
`hub/tests/test_fastmcp_api_contract.py` (6 tests, verified passing again 2026-09-01 08:09).

**Nothing was measured broken.** The research probed all four FastMCP APIs `mcp_server.py` uses
against 4.0.0 and all four survive. The bound was taken because v4 additionally pulls
`pydantic>=2.12`, `FastAPI>=0.133.0` and `httpx2` — a transitive set this suite has never run
against.

**Recommendation: ratify.** The cost of the bound is a deliberate upgrade later; the cost of no
bound is an unannounced major crossing under the agent runtime. If you widen it instead, run the
contract test first and read what it says.

**Coupling:** fastmcp 4 requires `FastAPI>=0.133.0`. The old D-2 tracked that; it is now part
of **R-1**, since `fastmcp<4` and `starlette<2.0` are the same unwritten rule applied twice.

---

## Closed by measurement, 2026-09-01

- **Entry 32 — "the hub suite has not run on this branch."** Answered by measurement, not decided.
  Run in the 2026-09-01 morning session before merging:

  | Suite | Result |
  |---|---|
  | `hub/tests/` | **3831 passed, 84 skipped, 1 xpassed** in 14:39 |
  | `tests/` | **440 passed, 3 skipped** |
  | `ruff` / `black --target-version py311` / `mypy src/` | clean over CI's own path lists |
  | `hub/ui` | **not run, and not needed** — the branch's product-code diff is three files (`pyproject.toml`, `hub/pyproject.toml`, `hub/tests/test_fastmcp_api_contract.py`); `hub/ui` is untouched. Measured with `git diff --name-only`, not inferred. |

  The baseline at `9fa4c4b` was 3,825 / 84 / 1, so **+6 is exactly the six new contract tests**.
  CI was also confirmed green on `master@ad60b7b`, the merge base.
