# Loop 6 — the verified→integrated pipeline exists, and no agent can drive it

**Date:** 2026-08-14 · **Project:** `aw-loop6` (`proj-c28f08df`, `C:\Users\huida\Documents\aw-loop6`)
**Scope, set by the operator before anything was read:** *full loop from zero* — interview →
specification → approval → tasks → two runners build and review → approve → integrate. Spec
evolution and peer-to-peer messaging were offered and **not** chosen; they are out of scope here and
remain unexercised.

**Runners:** `architect` (Codex / Spec Author), `builder` (Claude / Developer), `reviewer` (Codex /
Code Reviewer). The Hub was restarted onto `615f415` first and confirmed.

The loop completed. A real specification with 10 requirements was written, three tasks were created
by approval, a Claude agent implemented it, a Codex agent reviewed it and sent it back with a real
bug, the builder fixed it, and the work merged to `master`. **But the operator had to reach past the
product twice for it to get there** — and one of those reaches is not something an operator could do
at all.

---

## Findings, ranked by what each cost

### 1. No agent can record or accept evidence — the routes exist, no tool reaches them

The agent HTTP plane has both halves of the evidence loop:

```
POST /api/v1/agent-actions/spec/evidence              # record
POST /api/v1/agent-actions/spec/evidence/{id}/decision # accept or reject
```

**Neither is exposed as an MCP tool.** The Hub serves 18 tools (`hub/hub/mcp_server.py`); none of
them touches evidence. The only occurrence of the word in a tool signature is
`submit_spec_document(evidence=...)`, which is the *document's own* evidence section
(`{"checked": [...], "limits": [...]}`) — a different concept entirely.

The builder found this the hard way and described it exactly:

> "For the evidence, I need the spec document's path to attach it (via `submit_spec_document`'s
> `evidence` field, keyed to FR-1 through FR-10)…"

It reached for that field because it is the only thing named "evidence" an agent can touch.

**What it costs.** Integration is gated on accepted evidence, so with no agent able to produce any:

```
approve task-455c6e2d  →  skipped: no accepted evidence names a commit, so there is nothing to merge
```

The entire `verified, not integrated` guarantee built across 2026-08-13 and 2026-08-14 **cannot be
driven by agents**. To finish this run I minted a run credential directly in the database and
POSTed evidence with `curl`. An operator cannot do that. This is a design gap, not one defect: it
also makes the standing directive *"only test agents can accept the evidence"* unimplementable,
because no test agent has a tool to accept with.

### 2. A task-triggered agent cannot discover the document path

`read_spec_document(path: str)` documents its own argument as *"The document's path, as given in
your turn context."* For a run triggered on a **task**, the turn context contains no path and no
document id. Verified directly against the rendered context:

```
mentions read_spec_document: True
mentions spec/changes path:  False
mentions spdoc-:             False
```

There is no list-documents route on the agent plane either. The builder tried plausible slugs, got
404s, and said so:

> "I tried `read_spec_document` on several guessed paths (`spec/late-fees.html`,
> `spec/late-fee-calculator.html`, …) and all 404. `document_id` in the task ledger is
> `spdoc-d5632909` but that's not an accepted path."

**It happened twice**, in two separate conversations — the second time blocking evidence entirely.
The agents worked around it themselves: the builder messaged the architect, which confirmed the path
with its own `read_spec_document` call and sent it back. That is the product compensating for
itself, at the cost of a full extra turn, and it only worked because another agent happened to know.

Contributing: `Task.spec_document_id` and `Task.spec_task_key` are written correctly in the database
but are **not on the Pydantic task schema**, so not even the id reaches the API or the UI.

```
task-455c6e2d  doc=spdoc-d5632909  key='define-public-contract'   # database
"spec_task_key": null, "spec_document_id": null                    # API response
```

### 3. A peer-triggered run inherits no posture, and its refusal is never recorded

The reviewer run was started by the builder's message, not by me. It was refused permission to write
its own review file into its own worktree:

> "The review-file write was declined by the workspace approval layer, so I'm not bypassing that
> decision. I'll preserve the same evidence in AgentWeave's durable task/message records instead."

Two problems, one worse than the other.

- **Posture does not carry.** `agent_trigger.py:345` fills the posture from
  `agent_row.default_permission_mode`, which is `None` for all three agents here. Nothing carries the
  triggering run's posture, so the operator-triggered builder ran `workspace` while the
  peer-triggered reviewer ran with the runner default.
- **The refusal left no trace.** The only `permission_denied` event in the whole project is the
  builder's (`run-59bd07da`). There is none for the reviewer's run. The agent told us in prose; the
  Hub's durable log says nothing, so an operator reading the activity feed would never know a
  reviewer was blocked from recording its own review.

The reviewer degraded gracefully and put its findings in messages and task states instead, which is
the right behaviour. That is what made this cheap rather than silent.

### 4. A fresh project cannot integrate, and approval does not say so

`setup` leaves `main_branch` unset. The first approval therefore recorded:

```
skipped: this project has no main branch set — choose one in the project's settings
```

The row is honest. **The operator-facing surface is not**: approving the task reported only
`task-3393df0f -> approved`. Nothing surfaced the skip; you have to know to fetch
`/tasks/{id}/integrations`. The information exists and is correct — it just never reaches the person
who needs it, at the moment they act.

`GET /main-branch-suggestion` correctly answers `{"suggestion":"master","chosen":null}`. Nothing
prompts the operator to use it. Setting it also requires a full-object `PUT /settings` — a partial
`{"main_branch":"master"}` is refused for every other missing field.

### 5. The Hub's own auto-snapshot commits build artefacts

`snapshot_worktree` committed the builder's Python bytecode:

```
$ git -C .agentweave/worktrees/builder ls-files
__pycache__/late_fees.cpython-311.pyc
__pycache__/test_late_fees.cpython-311.pyc
late_fees.py  test_late_fees.py  README.md
```

`git status` read clean, which is worse — not because they were ignored, but because they were
already tracked. The reviewer caught it independently:

> "Correction after inspecting the commit object: the actual boundary is 4 changed files, not 2 —
> the commit also tracks two generated `__pycache__/*.pyc` files."

Decision 9 of the ignore-rules work deliberately scoped seeding to *what the Hub creates*, excluding
`__pycache__` as belonging to the project's language. That reasoning holds for a `.gitignore` the
operator owns — but it is **the Hub's snapshot** that commits these, on the agent's behalf, without
either party choosing to. The builder later removed them and added its own `.gitignore`, so the
product's own agents cleaned up after the product.

### 6. Approval creates well-chosen tasks with unusable titles — the answer to §10.4

The decomposition is genuinely good: three units (contract, implementation, verification) with
correct requirement coverage and statements joined on. I would have written the same three.

The **titles** are not usable. `_title_from` takes the description's first sentence, and these
descriptions are each one long sentence, so the title is the whole description clipped at
`MAX_TITLE = 200` — mid-word:

```
Add automated examples covering the public API, strict input types, exception split, on-time and
early return, Sunday exclusion, grace boundaries, charging, the cap with an uncapped day count, explici
```

Title lengths: 170, 112, 200. A board of these is not a board.

### 7. A question nobody answers leaves no trace

Per the method, one interview question was deliberately left unanswered — whether any borrowers or
materials are exempt (children, seniors, staff, reference books). It vanished completely: zero
occurrences of `exempt`, `senior`, `child`, `staff`, or `reference book` anywhere in the document,
including `open_questions` and `non_goals`.

The contrast is the interesting part. The five questions the architect asked **in the same turn as
writing the document** were recorded as `open_questions` and later resolved. A question asked in an
*earlier* turn and never answered was simply lost. Nothing distinguishes "answered", "declined" and
"forgotten".

Per the operator's standing decision this is **not a defect to fix** — *"the AI should answer or not
deliberately based on the test"* — and G5 remains a non-goal. Recorded because the asymmetry between
same-turn and prior-turn questions is a fact about the product worth knowing.

### 8. `context_warning` fires at 6% of context (low)

Seven `context_warning` events in the first turn, the first at `"percent": 6.28`. Severity is `info`,
so nothing misrenders, but the event type says "warning" for routine telemetry emitted on every
measurement.

---

## What held

Worth recording, because each was exercised against a real project rather than a fixture.

- **Ignore rules reach the agent's own checkout** (`615f415`, this morning). `git status` inside
  `.agentweave/worktrees/builder` was **clean**, with nothing from the Hub tracked — including
  `.agentweave/context/builder.md`, which is written into that worktree on every turn. This is the
  exact thing the previous mechanism could not do.
- **The footprint names the agent's work**, on a fresh project:
  `{"branch": "agentweave/builder", "commit_sha": "639bf9a2…", "reachable_from_main": false}`,
  matching `git rev-parse agentweave/builder` exactly.
- **The whole integration cycle tells the truth**, once evidence exists:
  `skipped (nothing to merge)` → `merged` → `skipped: 639bf9a2ad1f is already in master` →
  coverage `state: verified, integration: integrated` → `drift/detect` raises `[]`.
- **Re-approving an approved document is refused cleanly** — `409 phase_unchanged`, no duplicate
  tasks; the board stayed at three.
- **Workspace isolation refused the builder** a `Bash` outside its worktree — *"'/c/Users/huida/
  Documents/aw-loop6' is outside your workspace"* — and that one **was** recorded as
  `permission_denied`.
- **The revision cycle ran unattended and peer-driven.** The reviewer found a genuine bug the
  builder's own 18 tests missed — `late_fee(date(9999,12,30), date.max)` raised `OverflowError` from
  incrementing past the last valid day — sent all three tasks back to `revision_needed`, and the
  builder rewrote the loop with ordinal arithmetic and added the reproducer. No operator input.
- **The implementation is correct.** Checked against an independently written reference over 400
  date pairs: 0 mismatches, including the operator's own worked example (due Friday → returned
  Tuesday = Sat, Mon, Tue = 3 open days), the grace boundary, a Sunday return date, and the uncapped
  day count past the money cap (74 days, $10.00).
- **The tests survive a varied axis.** 18→20 tests pass under `PYTHONIOENCODING=utf-8`,
  `PYTHONUTF8=1 LC_ALL=C`, a varied `PYTHONHASHSEED`, and a different working directory.

## Corrections to my own earlier reads

Recorded so they are not re-derived as findings later:

- The task payload has **no** `title` field by design; `spec_tasks._title_from()` derives one from
  the description (`hub/hub/spec_tasks.py:43-54`). Not a defect.
- The messages API uses `from`/`to`, not `from_agent`/`to_agent`. Not a defect.
- Coverage reports verification under `state`, not `verification`. Not a defect.

## Cleanup

`aw-loop6` is **kept deliberately** as the reproduction for findings 1–5, all of which need a project
with a real agent worktree and a real merge to demonstrate. It contains a hand-minted run credential
`run-ev6` (token `aw_run_loop6_evidence`) created to work around finding 1; **that row should be
deleted if the project is ever shared.** Remove the whole project with
`python .claude/skills/e2e-loop/e2e.py clean proj-c28f08df`.
