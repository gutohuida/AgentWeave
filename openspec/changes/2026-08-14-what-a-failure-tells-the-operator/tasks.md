# Tasks — what a failure tells the operator

Six independent fixes, none of which touch control flow. Any phase can land alone and each ends
green. **No migration.**

Landing order relative to `2026-08-14-a-failed-run-does-not-eat-its-input`: after it. Phase 2 touches
the same two broadcast sites that change adds a requeue to, and rebasing a string change is cheaper
than rebasing a control-flow one.

## 1. The dirty-checkout skip stops promising something that cannot happen

- [ ] 1.1 `hub/hub/task_integration.py:54-61`: reword `CHECKOUT_DIRTY` and `CHECKOUT_ELSEWHERE` to
      point at retrying the integration, dropping *"and the next approval will merge"* (D1).
- [ ] 1.2 Leave `NO_MAIN_BRANCH` alone — its instruction is true and is discharged automatically when
      followed (D1).
- [ ] 1.3 Confirm no UI change is needed: `TaskIntegrationNote.tsx` already renders "Try again" for
      both reasons and special-cases only `NO_MAIN_BRANCH` (`:4`, `:43`).

## 2. One death, one exit code

- [ ] 2.1 Add `stderr_tail: Optional[str] = None` to `TurnOutcome`
      (`hub/hub/codex_appserver.py:767-777`), documented as the app-server's own tail rather than the
      turn's.
- [ ] 2.2 Fill it from `session.stderr_tail()` at `:982-984`, where `exit_code` is already filled.
- [ ] 2.3 `hub/hub/api/v1/agent_trigger.py:1891-1900` (app-server normal path): add
      `runtime_exit_code=outcome.exit_code` and `stderr_tail=outcome.stderr_tail` to the
      `run_failed` broadcast. **Do not change `exit_code`** — `AgentOutputPanel.tsx` reads the
      synthetic 0/1 for handoff detection (D2).
- [ ] 2.4 Omit both keys where there is nothing to report, rather than sending nulls, so an absent
      fact reads as absent — the rule `_transport_failure_fields` already documents.
- [ ] 2.5 The exec path's broadcast (`:1452-1461`) is left alone: its `exit_code` **is** the process's
      own, so there is no second number to report.

## 3. Render an exit code a person can read

- [ ] 3.1 Add a module-level renderer in `hub/hub/codex_appserver.py` normalising a value at or above
      `2**31` to its signed 32-bit form; everything else passes through; `None` stays `None`.
- [ ] 3.2 Use it in `AppServerError.__init__` (`:524-526`) when composing the `(exit {code})` clause.
- [ ] 3.3 **Do not** normalise `self.exit_code` or `TurnOutcome.exit_code` — what is recorded stays
      what the platform reported (D3).

## 4. Deliver the stderr tail

- [ ] 4.1 `_transport_failure_fields` (`hub/hub/api/v1/agent_trigger.py:1005-1018`): add
      `stderr_tail=getattr(exc, "stderr_tail", None)`, matching the `getattr` shape of the keys
      beside it — this `except` also catches `FileNotFoundError`/`OSError`/`TimeoutError`.
- [ ] 4.2 Confirm `stderr_tail()` remains bounded by `STDERR_TAIL_CHARS` (`:630-635`) and that
      nothing new is retained.

## 5. `ui_stale` names a command that exists

- [ ] 5.1 `hub/hub/main.py:167`: name `python scripts/refresh_ui_bundle.py` first and keep `make ui`
      as the shorthand (D5).
- [ ] 5.2 Leave the unstamped fallback at `:176-179` unchanged.

## 6. Requirement identifiers sort naturally

- [ ] 6.1 Add a natural-sort key splitting digit runs from non-digit runs and comparing digit runs
      numerically (D6).
- [ ] 6.2 Apply it to each task's list in `hub/hub/api/v1/tasks.py` after the fetch (`:110-126`), so
      `requirement_links` and the `requirement_ids` derived at `:143` both come out ordered.
- [ ] 6.3 Keep the `.order_by(SpecRequirement.identifier)` at `:91` — it makes the fetch
      deterministic, which the Python sort's stability relies on.

## 7. Tests

- [ ] 7.1 The reworded skip reasons asserted **through a real skip**, not by importing the constant:
      a dirty checkout and a checkout on another branch each produce a reason that does not tell the
      operator to approve again.
- [ ] 7.2 `run_failed` carries `runtime_exit_code` and `stderr_tail` on the app-server normal path;
      both absent when there is nothing to report.
- [ ] 7.3 `_transport_failure_fields` carries `stderr_tail` from an `AppServerError`, and `None` from
      a `FileNotFoundError`.
- [ ] 7.4 `4294967295` renders as `-1` in the composed message; an ordinary code is untouched; `None`
      stays absent; `AppServerError.exit_code` still holds the raw value.
- [ ] 7.5 `ui_stale` detail names the script — extend `hub/tests/test_ui_staleness.py`.
- [ ] 7.6 `FR-2` sorts before `FR-11` on a real task read; a non-numeric identifier still sorts
      deterministically.
- [ ] 7.7 A vitest case for the retry note if B1's wording is asserted in
      `taskIntegrationRetry.test.tsx`.

**Existing tests expected to need updating — state the reason here rather than discovering it in a
diff:**

- [ ] 7.8 `hub/tests/test_task_requirement_ids_readable.py` may pin the current lexicographic order;
      phase 6 changes it.
- [ ] 7.9 `hub/tests/test_agent_trigger.py` and `hub/tests/test_codex_appserver_process.py` assert
      `run_failed` payload shape. Added keys should not break a membership assertion; one comparing
      the whole dict needs widening.

## 8. Verification — agent-verifiable

- [ ] 8.1 `pytest hub/tests/ -q` and `pytest tests/ -q` **separately**, with
      `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- [ ] 8.2 `ruff check hub/ src/`; `black --target-version py311` on every file touched.
- [ ] 8.3 `npx tsc --noEmit`; `npx vitest run`.
- [ ] 8.4 `npx openspec validate --changes --strict`.
- [ ] 8.5 If any UI source changed, `python scripts/refresh_ui_bundle.py` and commit
      `hub/hub/static/ui` with it. (`make` is absent on this machine — that is phase 5's whole
      point.)

## 9. Verification — human-only

- [ ] 9.1 Approve a task with a dirty checkout, then commit the dirt and press "Try again".
      *Expect:* the skip text points at that button, and the merge happens. Previously it told you to
      approve again, which does nothing.
- [ ] 9.2 Look at a failed run's `run_failed` event. *Expect:* one turn status, one runtime exit
      status, told apart, plus whatever the child wrote to stderr.
- [ ] 9.3 Kill a Codex app-server and read the error. *Expect:* `-1`, not `4294967295`.
- [ ] 9.4 Judgement call: do two exit codes on one event read as informative or as noise? If noise,
      the answer is a UI change, not a revert — the facts are different and both are needed.
- [ ] 9.5 Look at a task card linked to more than nine requirements. *Expect:* `FR-2` before `FR-11`.

## 10. User test guide

**Setup.** A git-backed project with a main branch, an approved-and-merged task board, and a
Codex-backed agent.

1. **Make the project checkout dirty, approve a task, and read why it was not merged.**
   - *Expect:* it tells you to commit or stash and then **retry the integration**. Previously it said
     "the next approval will merge", which does nothing — the task is already approved.
2. **Commit the changes and press "Try again".**
   - *Expect:* the merge happens.
3. **Trigger a Codex agent and kill the `codex` process mid-turn. Open the run's failure.**
   - *Expect:* the exit status reads `-1`, not `4294967295`, and whatever the process wrote to its
     error stream is shown. Previously the tail was always empty.
4. **Compare the failure event to the run's status line.**
   - *Expect:* two clearly different numbers — the turn's status and the runtime process's — rather
     than one number that disagrees with itself depending on where you read it.
5. **Point an agent at a runner whose binary does not exist and trigger it.**
   - *Expect:* the failure names what the missing binary produced, not just that a process ended.
6. **Open a task linked to eleven or more requirements.**
   - *Expect:* `FR-1, FR-2, FR-3 … FR-11`, not `FR-1, FR-11, FR-2`.
7. **Change something under `hub/ui/src` and read `/health`.**
   - *Expect:* the staleness warning names a command you can actually run.

**Where it would go wrong:** if step 3 still shows an empty stderr tail, the failure took the
pre-spawn path rather than the turn path, or the reverse — the two are fixed separately and look
identical from the event. Check whether `runtime_exit_code` is present: it is on the turn path only.
