## 0. Observe it before building — a gate, not a preamble

Every behavioural claim in `proposal.md` is read from code plus one CI failure. The PTY half is
drivable here and should be driven before a line is implemented. **If phase 0 has not been recorded,
do phase 0 and stop**; an unattended window then commits the write-up and moves on to the next queue
item rather than proceeding to phase 1 on the strength of having just done phase 0.

- [x] 0.1 Trial Hub on **8011** — never `proj-5e960453` or `proj-18e5d4e0`, never port 8000 — from
      `hub/` with uvicorn from source, against a fresh fixture project. Every real agent turn binds
      `claude-haiku-4-5`.
- [x] 0.2 **The headline.** Start a turn; while it runs, send a second message so an entry is
      `queued`; make a bookkeeping call *inside the window* raise once; confirm the run reaches a
      terminal status and the queued entry stays `queued` with `delivered_in_run_id` null and no
      successor run — the defect as filed.

      **R3 rewrote this task, because it was not executable as written and the injection it named
      was wrong.** (i) A running uvicorn cannot be monkeypatched from outside, so "patch … in the
      running Hub" describes nothing you can do; the executable form is to add a guarded raise to
      the 8011 checkout's `agent_trigger.py` behind an environment variable
      (`if os.environ.get("AW_F286_INJECT") and kind == "status": raise RuntimeError(...)`), start
      8011 with it set, drive, then `git checkout` the file. That is a source edit, so it belongs to
      the implementation window and not to a window that only fills. (ii) The two calls it named
      fire **before** the window on every run — `record_agent_output` at `:2014` per streamed output
      event, `_broadcast_run_lifecycle` at `:1939` as `run_started` — so the raise would land with
      the row still `running`, which is the case that already works. Predicate the raise on the
      in-window call: `kind == "status"` (`:2235`), or `_report_abandoned_entries` (`:2195`). See
      design D4.
- [x] 0.3 Confirm nothing recovers it: with the Hub left running and untouched, the entry is still
      `queued` after several minutes. Then save the project's settings and confirm it is delivered
      instantly — which is what makes "delivered by coincidence" a measurement rather than a phrase.
- [x] 0.4 Confirm the run's recorded outcome is the one it reached (not `failed`), so the fix in 1.1
      is known to be the ungating and not a relabel.
- [x] 0.5 Record run ids, entry ids and timestamps in `scripts/drive/FINDINGS.md` under F286.

## 1. `_execute_run` — split the flag's two jobs

- [x] 1.1 In the handler at `hub/hub/api/v1/agent_trigger.py`, move the
      `redrain_queued_agents(project_id)` call out of `if not already_terminal:` so it runs on every
      exception. Leave the status relabel gated exactly as it is.
- [x] 1.2 Replace the comment above it. It currently says "unconditional, where this was gated on
      `returned`", which was true of one gate while the line sat inside another — the new comment
      states which two questions `already_terminal` answers and why only one of them is its business.
- [x] 1.3 Confirm by reading that no other statement in the handler depends on the redrain's
      position, and that the `CancelledError` re-raise still happens after it.

## 2. The failure tail, once, shared by both paths

**R3 replaced this phase.** R1 and R2 had it duplicate `_execute_run`'s handler onto the app-server
path; design D3 now shares one helper, because R3 measured the three differences that decision
rested on and none of them exists in the handler. Task 2.2 in particular was actively dangerous: it
told the implementer to use the failure-fields helper "that path's own tail does", which is
`_runtime_failure_fields(outcome, …)` — and `outcome` is not bound when the exception is raised
before `run_turn` returns.

- [x] 2.1 Extract the body of `_execute_run`'s handler into one coroutine in `agent_trigger.py`,
      taking `project_id`, `agent`, `run_id`, `conversation_id`, `runner` and `exc`: open a session,
      relabel to `failed` only where the row is still `running` (`expire_pending_for_run`,
      `record_turn_usage(sample=None)`, `finalize_job_run_for_conversation`, `return_run_entries`,
      commit, `_report_abandoned_entries`, `run_failed` broadcast with
      `_transport_failure_fields(exc, conversation_id)`, per-entry `queue_entry_queued`), then the
      **unconditional** release from 1.1. It returns nothing; the caller keeps `logger.exception`
      and the `CancelledError` re-raise.
- [x] 2.2 Rewrite `_execute_run`'s handler to call it, preserving the comment block at `:2283-2303`
      — that block is the measured history of why the handler catches `CancelledError` and must not
      be lost in the move.
- [x] 2.3 Add `except (Exception, asyncio.CancelledError) as exc:` to
      `_execute_codex_appserver_run` between its outer `try` (`:2536`) and its `finally` (`:2873`),
      calling the same helper with `runner="codex"`, then re-raising `CancelledError`. Do **not**
      pass `_runtime_failure_fields` here: it needs a `TurnOutcome` the exception path does not
      have, which is why the path's own pre-spawn `except` at `:2723` already uses
      `_transport_failure_fields`.
- [x] 2.4 Leave both `finally` blocks alone. `active_ptys` (`:2362`) and `active_app_server_runs`
      (`:2874`) genuinely differ and are not part of the shared body.

## 3. Tests

- [x] 3.1 `hub/tests/test_agent_trigger.py`: a PTY-path test that patches a bookkeeping call between
      the terminal commit and the release to raise once, with an entry queued behind the run, and
      asserts the entry is delivered — `delivered_in_run_id is not None` and a successor run exists —
      with no further request made. **The exception is injected, never obtained through F285's
      in-memory pool** (design D4): a test that reproduces this through F285 goes green when F285 is
      fixed, for the wrong reason. **And it is injected inside the window**: predicate the patched
      call on `kind == "status"`, or patch `_report_abandoned_entries`. A bare "raise once" on
      `record_agent_output` or `_broadcast_run_lifecycle` fires at `:2014`/`:1939`, before the
      terminal commit, and the test then passes without the fix — R3 found both rounds had specified
      exactly that. The test also asserts the run was already terminal when the raise landed, so the
      injection cannot silently drift back out of the window.
- [x] 3.2 The same test asserts the run's outcome was **not** relabelled `failed`.
- [x] 3.3 A second-agent variant: agent B's entry is refused while agent A's run holds a task
      checkout, A's run ends abnormally, B runs. This is the half that no existing test covers and
      the half the operator would notice as "the other agent stopped working".
      **Written in `hub/tests/test_task_turn_collision.py`, not `test_agent_trigger.py`**, beside
      `test_a_run_ending_redrains_the_agents_it_was_holding_back` — the F90 test it is the
      other half of. That file already owns the D8 collision harness (a real repo, a task
      row, two writing agents, `bind_project_workspace`); reproducing ~60 lines of it in
      `test_agent_trigger.py` to honour a filename would leave the two halves of the same
      claim in different files. 3.1 and 3.2 are in `test_agent_trigger.py` as written.
- [x] 3.4 App-server variants of 3.1 and 3.2 using the existing `_fake_run_turn` harness
      (`hub/tests/test_agent_trigger.py:117`) and the in-flight poll helper
      `_wait_for_active_app_server_run` (`:67`). R1 and R2 cited `:126` and `:68`, which are those
      two definitions' docstring lines rather than their `def`s; R3 re-read both and they are
      otherwise exactly as described.

      Written as `test_an_app_server_run_that_ended_releases_its_queue_when_its_tail_raises`,
      carrying 3.2's half in the same test exactly as 3.1 does. One deviation from the PTY twin
      it copies: the first turn is held open by an `asyncio.Event`, not 3.1's `threading.Event`.
      This transport never leaves the event loop, so blocking a thread there would deadlock the
      test rather than park the run.
- [x] 3.5 An app-server test that raises **before** the terminal write and asserts the run ends
      terminal with `error` set, and that the agent runs a subsequent turn — the wedge from
      requirement 2. Written as
      `test_an_app_server_turn_that_raises_before_its_terminal_write_is_not_a_wedge`: `run_turn`
      raises once and then behaves, so the successor is a real turn rather than a retry failing
      the same way, and no second request is made — the failed run hands its own input back and
      the release delivers it.
- [x] 3.6 Check whether `test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped` is now
      asserting this behaviour by accident. If it is, say so in its docstring rather than adding a
      duplicate; it is currently the only existing test that would have caught F286, and it caught
      it only because a harness artefact supplied the exception.

      **Measured: it is not.** With F285 fixed the stopped run reaches its terminal write without
      raising at all, so the release it observes is the normal path's, which was never gated. The
      check was the mutation, not a reading: with the pre-F286 gate restored in
      `_record_run_failure_tail` this test still passes while 3.1 and 3.4 both fail. A docstring
      recording that now sits on the test, so the F286 tests are not mistaken for duplicates of it
      and it is not mistaken for a regression test for the ungating.
- [x] 3.7 The cost D2 names, asserted rather than assumed: an entry refused non-transiently by the
      first redrain, with that redrain then raising, is charged **at most twice** and is not
      withdrawn by a single run boundary. `DELIVERY_ATTEMPT_LIMIT` is `3`; the point of the test is
      that ungating cannot turn one failed boundary into a dropped message.

      Written as `test_a_second_release_charges_a_refused_entry_at_most_twice` on the **PTY** path
      (the overlap is transport-independent, and that harness is already there). It builds D2's
      premise rather than assuming it: an entry seeded straight into the queue for a second agent
      whose schedule is refused with the flagless task-checkout `TriggerAgentError` — the arm the
      counter actually charges — and `redrain_queued_agents` wrapped to sweep, then raise, on its
      first call only. Measured cost: **2**, entry still `queued`, `abandoned_reason` null.

## 4. Gates

- [x] 4.1 `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` clean.
      Measured over the full CI path lists, not the touched file: ruff **All checks passed**,
      black **548 files unchanged**. Re-run after the 4.3 fix below and still clean.
      `ruff` is not on PATH in Git Bash here — `py -3.11 -m ruff`.
- [x] 4.2 `py -3.11 -m pytest hub/tests/test_agent_trigger.py -v` green — the file this change
      touches, run whole rather than by `-k`. **48 passed** in 35.7s (44 at the 18ba8ba baseline,
      +1 in 3a, +3 in 3b).
- [x] 4.3 The wider hub suite in file chunks; it exceeds the 600s command cap when run whole.
      All 251 `hub/tests/test_*.py` in nine chunks: **3966 passed, 14 skipped, 0 failed, 0 errors.**
      Per chunk (files 1–22 / 23–43 / 44–73 / 74–103 / 104–133 / 134–163 / 164–193 / 194–223 /
      224–251): 271+2s, 334, 432, 365+2s, 698+4s, 441+4s, 469, 498, 458+2s.

      **The first pass was not green, and the cause was this change.** Ten errors across
      `test_inbound_queue.py`, `test_instance_identity.py` and `test_instructions.py`, all
      `RuntimeError: Event loop is closed` raised by `conftest.py`'s
      `_no_connection_outlives_its_event_loop` at `task.cancel()`. Triaged rather than assumed
      pre-existing: `test_inbound_queue.py` **alone** errors at HEAD and is clean with
      `hub/hub/api/v1/agent_trigger.py` checked out at `1529d91~1`.

      Traced to a stack, not reasoned: `_execute_run` → `_execute_codex_appserver_run` → the
      phase-2 `except` → `_record_run_failure_tail` → `redrain_queued_agents` → `schedule_agent`
      → `trigger_agent_directly`, which registers a **new** task in `_background_runs`. So
      cancelling a run is no longer terminal: the fixture cancelled the leftover task, gathered
      it, and then `clear()`ed the set — dropping the successor the gather had just caused. That
      successor stayed pending on an event loop that closed moments later, and every later test
      in the process died in the same fixture.

      **This is the fix working, not a product defect.** The respawn is requirement 2's behaviour
      (3.5 asserts it), it is bounded by `DELIVERY_ATTEMPT_LIMIT` (3) rather than unbounded, and
      the comment at `agent_trigger.py:2386` records that nothing in the product calls `.cancel()`
      on a run task — `_stop_requested` is a cooperative flag. Loop teardown is the only caller,
      so the gap is the fixture's, and it is fixed there: settle to a fixed point over up to
      `_MAX_BACKGROUND_SETTLE_PASSES` passes, discarding only what each pass actually settled
      (`difference_update`) instead of `clear()`.

      Mutation-checked: restoring `clear()` inside the new loop brings the error straight back
      (`test_inbound_queue.py` alone, 11 passed **1 error**), so the `difference_update` is what
      fixes it and not the loop around it. `hub/tests/conftest.py` is the only file phase 4
      touched; no production code changed.
- [x] 4.4 `openspec validate --strict a-terminal-run-releases-the-queue-behind-it` clean —
      "Change 'a-terminal-run-releases-the-queue-behind-it' is valid".
- [x] 4.5 Drive the PTY half live once more after the fix, repeating 0.2 and 0.3 and expecting the
      opposite result. A passing suite is not proof of behaviour.

      **Driven twice, as an A/B at one injection site.** Expecting an outcome is not measuring one,
      so the fixed run was paired with a control: the same 8011 checkout with the pre-F286 gate
      restored (`else: return` before the redrain in `_record_run_failure_tail`), the same guarded
      raise at the same line, a fresh database and fixture project each time, Haiku both times.
      Phase 0 raised at the in-window status write; this pair raises three statements earlier,
      immediately before `_report_abandoned_entries` -- still between the terminal commit and
      `redrain_queued_agents`, but not the same line, which is why the control matters.

      **Fixed** (`run-16b449d4a80a`, `completed`, exit 0, `error=None`, ended `00:27:34.803750Z`):
      `entry-8992a0c0b036` delivered into successor `run-9d0f885a67c4` at `00:27:34.943590Z` --
      **0.140s after the run boundary, with no operator action**. The successor ran a real turn and
      completed at `00:27:42.570573Z`. The settings save afterwards was a no-op: runs before 2,
      after 2. `GET /queue/{agent}/status` reports `waiting_count: 0`.

      **Control** (`run-262d0b6132ee`, `completed`, exit 0, `error=None`): the entry stayed `queued`,
      `delivered_in_run_id=None`, `delivery_attempts=0` across four polls over **2 minutes 6
      seconds**, then a settings save delivered it `0.14s` later into `run-1c8380d8b82c`; runs
      before the save 1, after 2. Phase 0 reproduced.

      0.4 holds in both: run #1 keeps the outcome it reached. The release was ungated without the
      relabel moving. Recorded under F286 in `scripts/drive/FINDINGS.md`; the injection and the
      control gate were reverted with `git checkout` and never committed. The app-server half was
      not driven -- Codex is undrivable here.
