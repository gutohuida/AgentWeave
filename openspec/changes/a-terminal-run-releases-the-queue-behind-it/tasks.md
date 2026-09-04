## 0. Observe it before building — a gate, not a preamble

Every behavioural claim in `proposal.md` is read from code plus one CI failure. The PTY half is
drivable here and should be driven before a line is implemented. **If phase 0 has not been recorded,
do phase 0 and stop**; an unattended window then commits the write-up and moves on to the next queue
item rather than proceeding to phase 1 on the strength of having just done phase 0.

- [ ] 0.1 Trial Hub on **8011** — never `proj-5e960453` or `proj-18e5d4e0`, never port 8000 — from
      `hub/` with uvicorn from source, against a fresh fixture project. Every real agent turn binds
      `claude-haiku-4-5`.
- [ ] 0.2 **The headline.** Start a turn; while it runs, send a second message so an entry is
      `queued`; make a bookkeeping call between the terminal commit and the release raise once
      (patch `_broadcast_run_lifecycle` or `record_agent_output` in the running Hub, or use the
      injected-exception harness from 3.1). Confirm the run reaches a terminal status, and that the
      queued entry stays `queued` with `delivered_in_run_id` null and no successor run — the defect
      as filed.
- [ ] 0.3 Confirm nothing recovers it: with the Hub left running and untouched, the entry is still
      `queued` after several minutes. Then save the project's settings and confirm it is delivered
      instantly — which is what makes "delivered by coincidence" a measurement rather than a phrase.
- [ ] 0.4 Confirm the run's recorded outcome is the one it reached (not `failed`), so the fix in 1.1
      is known to be the ungating and not a relabel.
- [ ] 0.5 Record run ids, entry ids and timestamps in `scripts/drive/FINDINGS.md` under F286.

## 1. `_execute_run` — split the flag's two jobs

- [ ] 1.1 In the handler at `hub/hub/api/v1/agent_trigger.py`, move the
      `redrain_queued_agents(project_id)` call out of `if not already_terminal:` so it runs on every
      exception. Leave the status relabel gated exactly as it is.
- [ ] 1.2 Replace the comment above it. It currently says "unconditional, where this was gated on
      `returned`", which was true of one gate while the line sat inside another — the new comment
      states which two questions `already_terminal` answers and why only one of them is its business.
- [ ] 1.3 Confirm by reading that no other statement in the handler depends on the redrain's
      position, and that the `CancelledError` re-raise still happens after it.

## 2. `_execute_codex_appserver_run` — the guarantee the path never had

- [ ] 2.1 Add `except (Exception, asyncio.CancelledError) as exc:` between the function's outer
      `try` and its `finally`, mirroring `_execute_run`'s handler: `logger.exception`, relabel to
      `failed` only where the row is still `running` (with `expire_pending_for_run`,
      `record_turn_usage(sample=None)`, `finalize_job_run_for_conversation`, `return_run_entries`,
      commit, abandonment report, `run_failed` broadcast, per-entry `queue_entry_queued`), then an
      **unconditional** release, then re-raise `CancelledError`.
- [ ] 2.2 Use `_runtime_failure_fields`/`_transport_failure_fields` as that path's own tail does —
      do not copy `_execute_run`'s choice without checking which one this path uses.
- [ ] 2.3 Comment the duplication with design D3's reason, so the next reader knows it was decided
      rather than overlooked.

## 3. Tests

- [ ] 3.1 `hub/tests/test_agent_trigger.py`: a PTY-path test that patches a bookkeeping call between
      the terminal commit and the release to raise once, with an entry queued behind the run, and
      asserts the entry is delivered — `delivered_in_run_id is not None` and a successor run exists —
      with no further request made. **The exception is injected, never obtained through F285's
      in-memory pool** (design D4): a test that reproduces this through F285 goes green when F285 is
      fixed, for the wrong reason.
- [ ] 3.2 The same test asserts the run's outcome was **not** relabelled `failed`.
- [ ] 3.3 A second-agent variant: agent B's entry is refused while agent A's run holds a task
      checkout, A's run ends abnormally, B runs. This is the half that no existing test covers and
      the half the operator would notice as "the other agent stopped working".
- [ ] 3.4 App-server variants of 3.1 and 3.2 using the existing `_fake_run_turn` harness
      (`hub/tests/test_agent_trigger.py:126`) and the in-flight poll helper (`:68`).
- [ ] 3.5 An app-server test that raises **before** the terminal write and asserts the run ends
      terminal with `error` set, and that the agent runs a subsequent turn — the wedge from
      requirement 2.
- [ ] 3.6 Check whether `test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped` is now
      asserting this behaviour by accident. If it is, say so in its docstring rather than adding a
      duplicate; it is currently the only existing test that would have caught F286, and it caught
      it only because a harness artefact supplied the exception.

## 4. Gates

- [ ] 4.1 `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` clean.
- [ ] 4.2 `py -3.11 -m pytest hub/tests/test_agent_trigger.py -v` green — the file this change
      touches, run whole rather than by `-k`.
- [ ] 4.3 The wider hub suite in file chunks; it exceeds the 600s command cap when run whole.
- [ ] 4.4 `openspec validate --strict a-terminal-run-releases-the-queue-behind-it` clean.
- [ ] 4.5 Drive the PTY half live once more after the fix, repeating 0.2 and 0.3 and expecting the
      opposite result. A passing suite is not proof of behaviour.
