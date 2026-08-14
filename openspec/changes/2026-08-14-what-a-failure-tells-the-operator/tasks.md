# Tasks — what a failure tells the operator

Six independent fixes, none of which touch control flow. Any phase can land alone and each ends
green. **No migration.**

Landing order relative to `2026-08-14-a-failed-run-does-not-eat-its-input`: after it. Phase 2 touches
the same two broadcast sites that change adds a requeue to, and rebasing a string change is cheaper
than rebasing a control-flow one.

## 1. The dirty-checkout skip stops promising something that cannot happen

- [x] 1.1 `hub/hub/task_integration.py:54-61`: reword `CHECKOUT_DIRTY` and `CHECKOUT_ELSEWHERE` to
      point at retrying the integration, dropping *"and the next approval will merge"* (D1).
- [x] 1.2 Leave `NO_MAIN_BRANCH` alone — its instruction is true and is discharged automatically when
      followed (D1).
- [x] 1.3 Confirm no UI change is needed: `TaskIntegrationNote.tsx` already renders "Try again" for
      both reasons and special-cases only `NO_MAIN_BRANCH` (`:4`, `:43`).

## 2. One death, one exit code

- [x] 2.1 Add `stderr_tail: Optional[str] = None` to `TurnOutcome`
      (`hub/hub/codex_appserver.py:767-777`), documented as the app-server's own tail rather than the
      turn's.
- [x] 2.2 Fill it from `session.stderr_tail()` at `:982-984`, where `exit_code` is already filled.
- [x] 2.3 `hub/hub/api/v1/agent_trigger.py:1891-1900` (app-server normal path): add
      `runtime_exit_code=outcome.exit_code` and `stderr_tail=outcome.stderr_tail` to the
      `run_failed` broadcast. **Do not change `exit_code`** — `AgentOutputPanel.tsx` reads the
      synthetic 0/1 for handoff detection (D2).
- [x] 2.4 Omit both keys where there is nothing to report, rather than sending nulls, so an absent
      fact reads as absent — the rule `_transport_failure_fields` already documents.
- [x] 2.5 The exec path's broadcast (`:1452-1461`) is left alone: its `exit_code` **is** the process's
      own, so there is no second number to report.

## 3. Render an exit code a person can read

- [x] 3.1 Add a module-level renderer in `hub/hub/codex_appserver.py` normalising a value at or above
      `2**31` to its signed 32-bit form; everything else passes through; `None` stays `None`.
- [x] 3.2 Use it in `AppServerError.__init__` (`:524-526`) when composing the `(exit {code})` clause.
- [x] 3.3 **Do not** normalise `self.exit_code` or `TurnOutcome.exit_code` — what is recorded stays
      what the platform reported (D3).
- [x] 3.4 **Render at every surface a person reads, not only in the composed clause** — added
      2026-08-15 after finding L9-1 live. `runtime_exit_code` and `_transport_failure_fields`'s
      `exit_code` both go through `readable_exit_code`. Verified against a live Hub: consecutive
      `run_failed` rows in `event_logs` read `4294967295` before the fix and `-1` after.

## 4. Deliver the stderr tail

- [x] 4.1 `_transport_failure_fields` (`hub/hub/api/v1/agent_trigger.py:1005-1018`): add
      `stderr_tail=getattr(exc, "stderr_tail", None)`, matching the `getattr` shape of the keys
      beside it — this `except` also catches `FileNotFoundError`/`OSError`/`TimeoutError`.
- [x] 4.2 Confirm `stderr_tail()` remains bounded by `STDERR_TAIL_CHARS` (`:630-635`) and that
      nothing new is retained.

## 5. `ui_stale` names a command that exists

- [x] 5.1 `hub/hub/main.py:167`: name `python scripts/refresh_ui_bundle.py` first and keep `make ui`
      as the shorthand (D5).
- [x] 5.2 Leave the unstamped fallback at `:176-179` unchanged.

## 6. Requirement identifiers sort naturally

- [x] 6.1 Add a natural-sort key splitting digit runs from non-digit runs and comparing digit runs
      numerically (D6).
- [x] 6.2 Apply it to each task's list in `hub/hub/api/v1/tasks.py` after the fetch (`:110-126`), so
      `requirement_links` and the `requirement_ids` derived at `:143` both come out ordered.
- [x] 6.3 Keep the `.order_by(SpecRequirement.identifier)` at `:91` — it makes the fetch
      deterministic, which the Python sort's stability relies on.

## 7. Tests

- [x] 7.1 The reworded skip reasons asserted **through a real skip**, not by importing the constant.
      Landed as `test_a_dirty_checkout_skip_points_at_the_retry_not_at_approving_again` in
      `hub/tests/test_task_integration.py`, next to the fixtures that build a real repository.
      **Only the dirty case is driven end to end;** `CHECKOUT_ELSEWHERE` is reworded identically and
      its wording is not separately asserted, because that suite has no fixture parking the checkout
      on a third branch. Named here rather than left to be discovered.
- [x] 7.2 `run_failed` carries `runtime_exit_code` and `stderr_tail` on the app-server normal path;
      both absent when there is nothing to report.
- [x] 7.3 `_transport_failure_fields` carries `stderr_tail` from an `AppServerError`, and `None` from
      a `FileNotFoundError`.
- [x] 7.4 `4294967295` renders as `-1` in the composed message; an ordinary code is untouched; `None`
      stays absent; `AppServerError.exit_code` still holds the raw value.
- [x] 7.5 `ui_stale` detail names the script. Extended
      `test_a_stamp_naming_other_source_still_warns` in **`hub/tests/test_ui_build_stamp.py`**, not
      `test_ui_staleness.py` as planned: the stamped branch is what carries this sentence, and only
      that file has the git-backed `checkout` fixture a fingerprint needs. A hand-rolled `tmp_path`
      returns `None` and would have asserted nothing — caught by writing it the wrong way first.
      The assertion also pins the script *before* `make ui`, since the first command gets pasted.
- [x] 7.6 `FR-2` sorts before `FR-11` on a real task read, as
      `test_identifiers_are_ordered_by_number_not_as_text` in
      `hub/tests/test_task_requirement_ids_readable.py` — twelve requirements submitted in reverse,
      asserted on both `requirement_ids` and `requirement_links`.
- [x] 7.7 **Not needed, and this is the finding.** No UI test asserts the skip wording:
      `taskIntegrationRetry.test.tsx:51` supplies its own fixture string
      (`'the checkout has uncommitted changes'`) and the component renders `reason` verbatim. Nothing
      in `hub/ui/src` reads `run_failed`'s `exit_code` either — the only `exit_code` there is
      `eventSummary.ts:42`'s `watchdog_agent_exit`, an unrelated event.

**Existing tests expected to need updating — what actually happened:**

- [x] 7.8 `hub/tests/test_task_requirement_ids_readable.py` did **not** pin the lexicographic order:
      every existing case links one or two identifiers, and the two-identifier ones already sort
      themselves before asserting. No change required.
- [x] 7.9 `hub/tests/test_agent_trigger.py` and `hub/tests/test_codex_appserver_process.py` assert
      `run_failed` payload shape by membership, not by whole-dict equality, so the added keys pass
      through them. Confirmed by the full-suite run in 8.1 rather than by reading.

## 8. Verification — agent-verifiable

- [x] 8.1 **hub 2028 passed / 11 skipped; cli 360 passed / 3 skipped.** Separately, with
      `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- [x] 8.2 `ruff check hub/ src/` clean.; `black --target-version py311` on every file touched.
- [x] 8.3 `npx tsc --noEmit` clean; `npx vitest run` **864 passed**.
- [x] 8.4 `npx openspec validate --changes --strict` — **20 passed, 0 failed**.
- [x] 8.5 No UI source changed, so no bundle rebuild. If any had, `python scripts/refresh_ui_bundle.py` and commit
      `hub/hub/static/ui` with it. (`make` is absent on this machine — that is phase 5's whole
      point.)

## 9. Verification — human-only

- [ ] 9.1 Approve a task with a dirty checkout, then commit the dirt and press "Try again".
      *Expect:* the skip text points at that button, and the merge happens. Previously it told you to
      approve again, which does nothing.
- [ ] 9.2 Look at a failed run's `run_failed` event. *Expect:* one turn status, one runtime exit
      status, told apart, plus whatever the child wrote to stderr.
- [x] 9.3 **PASSED, after one round trip.** First attempt: `run.error` read `exit -1` but the
      `run_failed` payload carried `runtime_exit_code: 4294967295` — one death, three numbers
      (finding L9-1). Fixed by rendering at the payload too, then re-killed a live app-server: the
      two `run_failed` rows sit consecutively in `event_logs`, `4294967295` then `-1`. The unit
      tests passed throughout both states, which is why this had to be driven rather than read.
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
