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

## Triage of 2026-09-01 — 32 entries, 8 decisions

The night of 2026-09-01 handed over 32 entries in `decisions_for_user`. Read together they are not
32 questions. **Two were duplicates** (the `fastmcp` bound, entries 17 and 31), **one has since been
answered by measurement** (entry 32, "run the full suites before merging"), and **fourteen more are
instances of three recurring shapes** rather than independent calls.

What follows is the deduplicated set. Each row names the entries it absorbs, so nothing is lost.

---

### D-1 — Ratify or widen the `fastmcp <4` bound

**OPEN.** Absorbs entries 17, 31. Severity: low, reversible in one line.

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

**Coupling, and it is why D-2 is no longer independent:** fastmcp 4 requires `FastAPI>=0.133.0`.

---

### D-2 — Pin `fastapi`, or decide not to

**OPEN.** Absorbs entry 27. Severity: medium — bigger blast radius than D-1.

`fastapi>=0.110` is unbounded and has already produced **two CI-only failures** via Starlette major
bumps. Deliberately left alone on 2026-09-01 because, unlike D-1, it is not a one-line reversal.

**This is now coupled to D-1**: a future fastmcp 4 adoption forces `FastAPI>=0.133.0`, so a pin
chosen today is a pin that upgrade has to move.

---

### D-3 — "Every refusal the Hub produces has a named surface" — one convention, or eleven fixes?

**OPEN. This is the largest decision in the list and the one that pays back most.**
Absorbs entries 3, 13, 15, 16 — and behind them **F169, F173, F178, F179, F180, F187** plus
**eleven operator-only routes**.

The same defect has now been filed **six times across two nights**: the Hub computes a sentence for
an operator and no file under `hub/ui/src` reads it. Separately, eleven routes (including
`GET /spec/requirements`, `GET /spec/requirements/{identifier}`, `GET /documents/{path}/rigor-history`)
are **0-hit in both the served bundle — grepped as bytes off `hub/hub/static/ui` — and in
`hub/ui/src`**, and absent from the agent plane. They are reachable only by a direct HTTP client.

Two entries sharpen it usefully:

- **F187 is the cheapest possible instance**: the charter form's refusal is a plain FastAPI 422 the
  React Query mutation already holds, and `ChartersPage.tsx:191` simply passes no `onError`. Nothing
  needed computing, wiring or designing. That is what makes this look like a **missing convention**
  rather than a refactor.
- **`rigor-history` is the sharpest**: `spec_rigor.py`'s own docstring justifies allowing demotion
  *on the grounds that the audit trail exists* — and no screen shows it. The drive confirmed the
  trail itself is complete and ordered, so this is a **surfacing gap, not a data gap**.

**The decision has two halves.** (a) Are those eleven routes en route to a screen, deliberately
API-only, or dead? A standing answer settles the sweep's remaining rows too. (b) Should a repo check
assert that a server-side refusal string is grep-able somewhere in the UI, and that a mutation whose
failure an operator must see carries an `onError`?

---

### D-4 — Should the repo hold standing rules, or keep fixing instances?

**OPEN.** Absorbs entries 5, 8, 10, 11. Four separate findings each ask the *same meta-question*,
and each names a grep that would say how big it is.

| From | The narrow fix | The standing rule it proposes | The sweep that would size it |
|---|---|---|---|
| **F190** | one line in `runStatusByRunId` | a model function consuming an API payload is tested against a fixture derived from that route's **actual** ordering | order-sensitive reducers over timeline/event payloads |
| **F201** | move one check behind the machine | no request-body validator may refuse what a declared state machine would refuse first | `model_validator`s on request schemas whose subject is also governed by a machine |
| **F197** | render the query's error state | a panel gated on a query's `data` must render that query's `error` | React Query results used without their `error` |
| **F195** | thread `ProjectWorkspace`'s path through two call sites | no subprocess spawned on a project's behalf inherits the Hub's cwd | `subprocess.run`/`Popen` with no explicit `cwd` |

**F190 deserves singling out.** It is a shipped UI feature that **can never fire**, and its unit test
is green *because it feeds the opposite ordering to the one the route produces*. That is this
repository's named dominant failure mode — "a fix that passes its tests and cannot fire in
production" — arrived at from the other side. It is severity A.

**The narrow fix in every row is safe and queueable regardless of how the rule question is
answered.** The rule question is only about whether to also run the sweep.

---

### D-5 — Prioritisation: the sweep out-produces the repair

**OPEN, and it is the scheduling decision.** Absorbs entry 30.

The night of 2026-09-01 filed **45 findings (F170–F214: 3 A, 14 B, 25 C, 3 D)** from rows 1–9b of
the coverage matrix. **All 45 are unfixed and none has a change proposed against it.** Rows 9c and
10–17 are untouched. `FINDINGS.md` is now 219 headings.

The three severity-A findings, which are the argument for pausing:

- **`F173`** — runner management free-types models and **swallows its own refusal**; a shipped
  requirement (`runner-registry/spec.md:72-73`) says otherwise.
- **`F188`** — a repairable workspace fault **destroys the operator's message** after three
  schedules, while the identical fault one line away holds it forever.
- **`F190`** — no turn can ever report stopped, failed or interrupted (see D-4).

**Recommendation: spend the next night window on F173/F188/F190 rather than on row 9c.** Sweeping
further is cheap to resume — the leads are preserved in `STATE-night.json` under
`sweep_state.row_9c_leads` — while three A-severity defects sitting unfixed is the state the sweep
existed to end.

---

### D-6 — Two corpus questions the archiving surfaced

**OPEN.** Absorbs entries 18, 20.

**(a) `openspec archive` has a silent loser.** Applying a delta against the current corpus warns
about nothing when two changes both carry a `## MODIFIED` block for the same requirement. Archiving
the second **reverted the first**, dropping a qualification that had just landed. Caught only
because the diff was read before committing; repaired, and the other six were swept (exactly one
collision). *Two changes in flight against one requirement is not rare here — it happened in a batch
of seven.* Should archiving be gated on a collision check, and does that belong in a repo script, in
the `openspec-archive-change` skill, or upstream?

**(b) The corpus is ahead of the code, twice in two nights.** `runner-registry/spec.md:72-73` is a
**shipped requirement whose UI half was never built** — the change that introduced it ticked its
task on backend evidence alone and archived. Either narrow the requirement to what shipped, or
accept that `openspec/specs/` knowingly describes behaviour the product does not have. (The first
instance was task 8.3 of `approval-refuses`, filed as F169.)

---

### D-7 — Response-shape and API-surface calls the windows cannot take alone

**OPEN.** Absorbs entries 1, 2, 4, 6, 7, 9, 12, 14, 19, 21. Grouped because each changes a contract
an existing caller depends on, which is why none was taken unattended.

- **F209** *(smallest fix in the whole list)* — `accept` declares a 2000-character `reason` and
  **stores nothing**; `reject`, three functions away, keeps it. The record of *why* a spec change
  was let in is the half that is not kept. Thread it through, or delete the field — but the current
  state promises something it discards.
- **F212** — `GET /spec/coverage` projects `unserved` to bare identifiers, and identifiers are
  minted **per document** by design. 34 entries all read `FR-1`; feeding one into the route built to
  explain it answers **422, "declared by more than one document."** The same response's
  `requirements` array already carries `document_id`.
- **F202** — `GET /projects/{id}/tasks` defaults to `limit=100` with no `total`/`has_more`/`next`,
  so at 241 tasks the Overview says "100 tasks" and its nine chips sum to exactly 100. **Part two is
  sharper and independently fixable:** `mcp_server.py`'s `list_tasks` has *no* limit or offset at
  all, so an agent past 100 tasks cannot page even if it knew it should.
- **F203** — `task_transitions` is append-only, carries actor/run/policy, has a reader, and **no
  route or MCP tool exposes it**. The drives have had to open sqlite. Build `GET /tasks/{id}/transitions`,
  or say the trail is internal where the module claims it is "worth reading".
- **F196 + F198** — *should `PATCH /queue/settings` exist at all?* It writes four columns
  `PUT /projects/{id}/settings` already owns, with a weaker contract on both ends, and the UI never
  calls it.
- **F193** — what should archiving an agent **mean** for its open threads: leave them orphaned
  (today), archive them with it, or refuse while any thread is open? The product already made that
  three-way choice explicitly for archiving a *conversation* with a live run.
- **F185 + F181** — the second and first routes found selecting agents with **no lifecycle filter**.
  Should archiving **clear** an agent's bindings (cleanest, closes both at source, but `unarchive`
  must then say the bindings are gone), or must every query over `Agent` carry the filter — the fix
  that keeps being forgotten?
- **Entry 19** — should a bare `uvicorn hub.main:app` from `hub/` **refuse to start** on the
  relative default rather than silently opening a second database beside the one everything else
  uses? This has cost time twice.
- **Entry 21** — `model_catalog.py` names `~/.codex/models_cache.json` as its source of truth and
  nothing re-checks it; it has drifted. Per-machine and absent in CI, so it can only be a
  skip-if-missing check or a `scripts/` tool. *Doing nothing is defensible; doing nothing silently
  is what let a phantom default model sit in the catalog for four weeks.*

---

### D-8 — Stale rows: re-queue or close

**OPEN.** Absorbs entries 22, 23, 24, 25, 26, 28, 29. These are carried, not new, and several have
been carried for days without moving.

| Row | State |
|---|---|
| **F47/F120** | `task-lifecycle-governance/spec.md:359` forbids a third actor kind **categorically**, with a scenario pinning the enumeration, so the obvious repair breaches a shipped requirement. Unanswered since handoff 0101. |
| **F77** | An agent has no way to address the operator. Filed, unfixed, unqueued. |
| **F53 / F65** | `_adopt_document_tasks` orphaning half; review-briefing retry. Open, **never queued**. |
| **F130, F127, F111+F3, F113, F61** | Queued 2026-08-29, deliberately dropped from the last three runs. **Re-queue or close.** |
| **Hub suite runtime** | ~25 minutes whole; called "already too long" when it was 14. Unscheduled. |
| **Feature freeze** | Parameters still unsettled. |
| **8010 trial Hub** | Has now served 2026-08-29 code for **four** days. Restart from current master? |

---

## Closed by measurement, 2026-09-01

- **Entry 32 — "the hub suite has not run on this branch."** Answered, not decided: the suites were
  run in the 2026-09-01 morning session before merging. See that day's handoff for the numbers.
