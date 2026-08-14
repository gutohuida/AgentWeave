# Loop 8 — the re-stamp holds; a dead runtime eats the message

**Date:** 2026-08-14 · **Branch:** `hub-native-experience` · **Hub:** restarted onto `d38419f`
(migration `0071 → 0072` ran at startup, which is how we know the running process carried the fixes)
**Project:** `aw-loop8` (`proj-94f3f169`), `C:\Users\huida\Documents\aw-loop8`
**Purpose:** phase 9 of `openspec/changes/2026-08-14-the-seams-loop7-found/tasks.md`, at the
operator's instruction to run the whole loop "from spec to the final merge", plus the three
off-path fixes.

The loop was driven end to end with no simulated steps: an interview, an 11-requirement spec, three
tasks, a Claude builder, a Codex verifier with evidence acceptance, five agent-to-agent hops with no
operator in between, and two merges into `master`.

**The headline is that phase 9.1 passes.** The evidence footprint named the snapshot commit, the
verifier reviewed that commit, and there was no commit-mismatch rejection anywhere in the run — the
exact round trip loop 7 spent a whole review cycle on. See "What held".

**The most expensive thing found is unrelated to what was fixed:** an app-server that dies *mid-turn*
consumes the operator's input and loses it, and the give-up machinery built last session cannot see
that path at all.

---

## Findings, ranked by what each costs

### 1. A runtime that dies mid-turn silently eats the input — `delivery_attempts` never moves

**What happens.** Kill the Codex app-server after the turn has started. The run is marked `failed`,
the agent returns to `idle`, and the queue entry that carried the operator's instruction stays
`state='delivered'` with `delivery_attempts = 0`. It is never requeued, never retried, never
abandoned, and nothing tells the operator their message was consumed by a run that died.

**Evidence.** Two kills, two identical outcomes — not a race:

```
runs:
  run-332ef259  victim  failed  app-server process ended before the turn completed (exit 4294967295)
  run-68eca96d  victim  failed  app-server process ended before the turn completed (exit 4294967295)

inbound_queue_entries:
  entry-66cb9671  state=delivered  delivery_attempts=0  abandoned_reason=None  delivered_in_run_id=run-332ef259
  entry-e6cbad28  state=delivered  delivery_attempts=0  abandoned_reason=None  delivered_in_run_id=run-68eca96d

agent victim: status=idle
```

**One defect or a design gap?** A design gap, and it is the one that matters. `return_run_entries`
is called from exactly two places, both of them *pre-spawn* `except` blocks
(`agent_trigger.py:1239` and `:1807`). A process that dies after `run_turn` is under way does not
raise out of those blocks — it comes back as a failed `TurnOutcome` and travels the *normal*
completion path, which has no notion of returning input. So `RESUME_RETRY_LIMIT` and
`DELIVERY_ATTEMPT_LIMIT` are structurally unreachable on the death mode most likely to occur in
practice: the runtime that dies while doing work.

Migration `0072`'s own message reads "count failed deliveries, so an input that kills the runtime
cannot wedge its agent forever". Half of that is delivered — the agent does not wedge. The other
half is not: the input does not survive.

**Covered by an existing change?** No. `hub/tests/test_delivery_attempts.py` (11 tests) exercises
`return_run_entries` directly and proves the counting, the reset and the abandonment are all
correct. Nothing asserts that a mid-turn death *reaches* it. This is the shape the loop exists to
find: every unit is right and the seam between them is missing.

**Note on 9.3.** Its stated pass condition — "by the third, the entry is abandoned with a reason and
the agent accepts new input again" — is not met by the mid-turn path. The agent does accept new
input. The entry is not abandoned, because it is not counted at all.

---

### 2. Nothing drives the retry of a requeued entry

**What happens.** On the paths where an entry *is* requeued (a pre-spawn failure), it returns to
`queued` and then sits there. Nothing schedules the next attempt.

**Evidence.** `entry-95f08a24` went back to `queued` with `delivery_attempts = 1` at 18:23:03. It was
still sitting there, untouched, when I next looked. Attempt 2 happened only when I issued an
unrelated `PUT /settings`; attempt 3 required a second one:

```
18:23:03  run_failed (run-6cf52727)  →  entry queued, delivery_attempts=1
          … nothing …
18:25:11  [after PUT /settings]      →  run-d0d663fa, delivery_attempts=2, failed again
          … nothing …
18:27:—   [after PUT /settings]      →  run-2ab1c48e, delivered, SUCCEEDED
```

**Why.** The transport-failure branch requeues, broadcasts `run_failed`, and `return`s at
`agent_trigger.py:1254` — *before* the `schedule_agent(project_id, agent)` that the normal path runs
at `:1504`. `redrain_queued_agents` is called from only three places, all project-lifecycle
endpoints (open, settings save, relocate), and there is no periodic drain: `hub/scheduler.py` is the
jobs scheduler, not a queue pump.

**Consequence.** The give-up ceiling is reached by coincidence or not at all. In an ordinary session
the input parks indefinitely while the agent reads `idle` — which is indistinguishable from "nothing
pending".

**Mitigating, and worth saying plainly:** when something *does* drain it, the machinery is excellent.
The conversation's provider session was genuinely unresumable — two consecutive `thread/resume`
deaths — and the reset-at-2 rule cleared `provider_session_id`, so attempt 3 started a fresh thread
and completed the review that the first two attempts could not. That is the designed behaviour,
observed on a real failure rather than a fabricated one.

---

### 3. The dirty-checkout skip instructs the operator to do the one thing that cannot work

**What happens.** `CHECKOUT_DIRTY` reads:

> the project's checkout has uncommitted changes to tracked files — commit or stash them and **the
> next approval will merge**

There is no next approval. The task is already `approved`, and restating a status is a documented
no-op (`to_status == from_status` returns early, deliberately, per D5).

**Evidence.** I followed the instruction exactly:

```
$ git commit -m "Operator note"            # discharge the instruction
$ PATCH /tasks/task-fbc2dc51 {status: approved}
  → 200, status: approved
  → integrations: 1 row, still the same skip
  → master: unmoved

$ POST /tasks/task-fbc2dc51/integrations/retry
  → outcome: merged, commit 014d675
  → master: 293b4c9 Integrate approved work 014d675e56de
```

**One defect or a symptom?** A symptom. This is the *same shape* as the `NO_MAIN_BRANCH` message
that was fixed last session — the message was rewritten to point at settings, and settings-save was
taught to re-run the merge. `CHECKOUT_DIRTY` got the retry button but kept the old sentence. The
remedy exists and works; the text sends the operator somewhere else.

---

### 4. Two surfaces report different exit codes for the same death

```
runs.error            : app-server process ended before the turn completed (exit 4294967295)
run_failed payload    : {"exit_code": 1, ...}
```

`4294967295` is `0xFFFFFFFF` — the unsigned reading of Windows' `-1` from a forced termination. It
is not a number an operator can act on; `-1`, or the word "terminated", is.

The disagreement matters more than the formatting. `AppServerError`'s own docstring gives the reason
the facts are composed into the message: *"so that every existing reader of `str(exc)` — `Run.error`,
the `run_failed` payload, an abandoned queue entry's reason — reports them without being changed"*,
and `_transport_failure_fields`' docstring says the two shapes previously *"disagreed exactly where
diagnosis is hardest"*. On this path they still disagree.

---

### 5. The stderr tail never reached the operator, on any of four real failures

`_transport_failure_fields` (`agent_trigger.py:1013`) returns `error`, `exit_code`, `method`,
`conversation_id` — there is **no `stderr_tail` key**. The tail can only surface by being composed
into `str(exc)`, and it is appended only when non-empty. Across four genuine failures this run
(`run-6cf52727`, `run-d0d663fa`, `run-332ef259`, `run-68eca96d`) it was empty every time.

So of the three facts the change set out to deliver — exit code, in-flight method, stderr tail —
**only `method` arrived**, and it arrived well: `"app-server process ended during thread/resume"`
told me immediately that the failure was a session-resume problem rather than a crash, which is what
made finding 2's diagnosis quick. That part is a real improvement. The other two did not land.

---

### 6. `ui_stale` tells the operator to run a command that does not exist here

The warning ends *"Run `make ui` to rebuild and re-record it."*

```
$ command -v make        → make: NOT on PATH in Git Bash
$ powershell -c "Get-Command make"  → make NOT found in PowerShell either
```

`python scripts/refresh_ui_bundle.py` works. This is a direct answer to task 9.6's question — *is
`make ui` a workflow you would actually run, or will the stamp rot?* — from the outside: the one
instruction the operator is given cannot be executed on this machine in either shell.

---

### 7. `requirement_ids` is sorted lexicographically

```
task-28b15399  ['FR-1', 'FR-11', 'FR-2', 'FR-3', 'FR-4']
task-fbc2dc51  ['FR-1', 'FR-10', 'FR-11', 'FR-2', 'FR-3', ...]
```

The data is correct and the fix works; the ordering reads as a bug on a card. Cosmetic, cheap,
and in the code this change touched (`_attach_requirements`).

---

### 8. The spec declared "Open questions: None outstanding" for an area I never answered

The architect asked four question areas as prose. I answered three, decisively, and deliberately
left the fourth — non-goals and packaging — unanswered, per the method.

The approved document contains six invented Non-goals and the line **"Open questions: None
outstanding."** Its own "Limits" section is more honest (*"Packaging metadata … remain implementation
design details"*), so the document contradicts itself: it knows the area is unsettled and still
reports nothing outstanding.

The inventions were all reasonable, and a plausible default beats a stall. The recordable defect is
narrower: **an area the operator never addressed is written down as settled.**

**Related observation, recorded as observation only.** The architect asked all four areas as prose
and opened **zero question rows** (`select count(*) from questions … → 0`), exactly as loop 7
observed. Per the standing directive this is a non-goal — *"the AI should answer or not deliberately
based on the test"* — and is **not** being re-proposed.

---

### 9. The merged product cannot run its own tests from a clean checkout

Not an AgentWeave defect, but it passed the whole evidence gate, which is the interesting part.

```
$ cd aw-loop8 && pytest tests -q
E   ModuleNotFoundError: No module named 'freightquote'

$ PYTHONPATH=src pytest tests -q
111 passed
```

`pyproject.toml` carries no `[tool.pytest.ini_options] pythonpath`, and there is no `conftest.py`.
Both agents verified behaviour inside environments where the package was importable (the builder
built a venv and `pip install`ed it; the verifier loaded it from `src`), and both were telling the
truth. FR-11's acceptance criterion says *"a clean Python 3.11 environment … freightquote is
installed and imported"* — which was satisfied.

Nothing in the chain asks whether the repository **as merged** is usable. Evidence proves behaviour;
it does not prove the artefact.

---

## What held

Worth recording, because a gate that correctly refuses is a result and the next session needs to know
it was exercised.

**Phase 9.1 — the headline, passed.** Five footprints from `run-94f48f1a` all named `b8b8664`, the
snapshot commit of the builder's own turn. Verified independently rather than taken from the API:

```
footprint entry  src/freightquote/_models.py → 2c5c07b9759f...
git rev-parse b8b8664:src/freightquote/_models.py → 2c5c07b9759f...   (identical)
git ls-tree -r --name-only 87c050f  →  README.md                      (the parent, i.e. what the
                                                                       old code would have stamped)
```

The verifier read that commit and raised **no commit-mismatch complaint at all**. It did reject
FR-3 — on merit, having found that `Decimal("NaN")` reached a `<= 0` comparison and raised
`decimal.InvalidOperation` instead of `InvalidParcel`. I reproduced that by hand and found one case
it had missed (`Decimal("Infinity")` was *accepted* as a valid length). The rejection was correct and
the review gate did its job.

**D3's fallback.** The correcting turn committed its own work mid-turn, so no auto-snapshot was
taken. The re-stamp fell back to `HEAD` and named `a875651` — the builder's own commit — while
correctly leaving the previous run's rows on `b8b8664`. Both halves of that decision observed live.

**9.2, passed.** With `main_branch` null, approval recorded `NO_MAIN_BRANCH`. Naming `master` in
settings merged the waiting work on save (`fcb0f51 Integrate approved work a875651754d4`). The
transition history is a clean forward path with no walk-back:

```
pending → assigned → in_progress → completed → under_review → approved
```

**Reachability outranks the dirty check.** Approving `task-becee601` with a dirty checkout produced
`"a875651754d4 is already in master; there was nothing to merge"` — not `CHECKOUT_DIRTY`. D6's
self-guard on a fact rather than the attempt log, working in the right order.

**The retry route merged**, on the operator plane, from a genuine skip.

**`requirement_ids` is populated** on `TaskResponse` for all three tasks, with `requirement_links`
and an empty `unresolved_requirements`.

**A failed run did not wedge its agent** — `verifier` read `idle` after each failure and accepted new
input.

**The peer loop ran unattended.** Five agent-to-agent hops (verifier → builder → verifier → builder),
each triggering the next within ~15 seconds with no operator turn between them, up to `hop_depth: 3`.

**A bogus model was refused at the source:** `POST /runners {model: "not-a-real-model-xyz"}` → 400,
*"'not-a-real-model-xyz' is not a model 'codex' declares"*.

**`--untracked-files=no` is correct and deliberate.** Every project is untracked-dirty by
construction — the Hub writes `spec/` and `.agentweave/` into the working tree — and the code says so
in a comment at `task_integration.py:114`.

**The Hub's procedure outranked the installed one.** The architect volunteered: *"I also found an
installed OpenSpec workflow; as directed, I am not using its layout, files, or process."*

**`rename_spec_document` worked**, emitting a `renamed` event with `actor_kind=agent`.

**The arithmetic is right to the cent.** Five cases computed by hand from the spec and compared, not
taken from the suite — including the `0.725 → 0.73` ROUND_HALF_UP case and both exact boundaries:

| parcel | zone | dim | billable | total | oversize |
|---|---|---|---|---|---|
| 50×40×30, 5kg | 3 | 12 | 12.0 | **28.60** | no |
| 130×20×20, 3kg | 1 | 10.4 | 10.5 | **35.10** | longest side |
| 10×10×10, 0.5kg | 2 | 0.2 | 0.5 | **6.48** | no |
| 120×10×10, 30kg | 5 | 2.4 | 30 | **105.00** | no — both exactly on the line |
| 130×10×10, 31kg | 4 | 2.6 | 31 | **100.10** | both causes, one surcharge |

**Axis varied (step 6): no encoding-class defect this time.** 111 tests pass under
`PYTHONIOENCODING=cp1252`, under `PYTHONUTF8=0 LANG=C LC_ALL=C`, and from a foreign working
directory. The only environmental dependency is finding 9's.

**The `ui_stale` TTL works in both directions with no restart.** An uncommitted types-only edit under
`hub/ui/src` raised the warning within the 30s TTL, and reverting cleared it within the TTL — the Hub
process was never touched. The message also correctly distinguished the uncommitted case
(*"hub/ui/src has uncommitted changes"*). `refresh_ui_bundle.py --check` passes at HEAD.

---

## Suggested ordering, if these are taken up

1. Finding 1 — input loss on mid-turn death. Everything else is recoverable by hand; this one is not,
   because there is nothing left to recover.
2. Finding 2 — drive the retry. 1 and 2 are the same story told from two ends, and a fix for 1 that
   does not also schedule the next attempt lands the entry in 2's parking lot.
3. Finding 3 — a one-sentence change with a real cost, and the remedy already exists.
4. Findings 4, 5, 6, 7 — small, independent, cheap.
5. Finding 8 — needs a decision, not a patch: may a document assert "no open questions" about an area
   the operator never addressed?
6. Finding 9 — a question about what evidence is *for*, and the widest of them. Worth an exploration
   of its own rather than a fix.
