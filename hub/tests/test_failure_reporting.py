"""What a failure tells the operator.

Six defects loop 8 found (`openspec/explorations/2026-08-14-loop8-a-dead-runtime-eats-the-message.md`)
that share a shape: the system knows a fact and does not say it, or says something that is not true.
None of them changes control flow, and none was visible to 2358 passing tests.

The tests here go through real behaviour rather than importing a constant and comparing it to
itself — that is the only failure mode a reporting change has.
"""

import json

import pytest
from sqlalchemy import select

from hub.codex_appserver import AppServerError, TurnOutcome, readable_exit_code
from hub.db.models import EventLog

# ---------------------------------------------------------------------------
# B2/B3 — one death, one exit code, readable
# ---------------------------------------------------------------------------


def test_a_forced_termination_reads_as_minus_one():
    """`4294967295` is `0xFFFFFFFF`, the unsigned reading of Windows' `-1`. It is what a run's
    error actually said on 2026-08-14, and nobody could connect it to the process they had just
    killed."""
    assert readable_exit_code(4294967295) == -1
    assert "exit -1" in str(AppServerError("app-server process ended", exit_code=4294967295))


def test_an_ordinary_exit_code_is_untouched():
    for code in (0, 1, 2, 127, 255):
        assert readable_exit_code(code) == code
    assert "exit 127" in str(AppServerError("app-server process ended", exit_code=127))


def test_no_exit_code_stays_absent():
    assert readable_exit_code(None) is None
    assert "exit" not in str(AppServerError("app-server process ended"))


def test_the_raw_value_is_still_what_is_recorded():
    """Only the rendered clause is normalised. A diagnostic that quietly rewrites its input is a
    worse diagnostic, and a bug report wants the number the platform produced."""
    error = AppServerError("app-server process ended", exit_code=4294967295)
    assert error.exit_code == 4294967295


def test_a_turn_outcome_carries_the_tail_and_the_status():
    """`TurnOutcome` is the only route by which a turn that failed *without raising* can report
    what the child said — there is no exception to hang it off."""
    outcome = TurnOutcome(
        thread_id="t-1", status="failed", exit_code=-1, stderr_tail="could not read auth.json"
    )
    assert outcome.exit_code == -1
    assert outcome.stderr_tail == "could not read auth.json"


def test_a_turn_outcome_defaults_to_no_tail():
    assert TurnOutcome(thread_id="t-1", status="completed").stderr_tail is None


# ---------------------------------------------------------------------------
# B4 — the tail reaches the payload
# ---------------------------------------------------------------------------


def test_a_transport_failure_reports_the_stderr_tail():
    """`_transport_failure_fields` had no `stderr_tail` key at all, so the tail could only surface
    by having been composed into `str(exc)`. Of the three facts it was written to report, two
    arrived."""
    from hub.api.v1.agent_trigger import _transport_failure_fields

    fields = _transport_failure_fields(
        AppServerError(
            "app-server process ended",
            exit_code=1,
            method="thread/resume",
            stderr_tail="thread not found",
        ),
        "conv-1",
    )
    assert fields["stderr_tail"] == "thread not found"
    assert fields["method"] == "thread/resume"
    assert fields["exit_code"] == 1


def test_a_failure_carrying_no_tail_reports_none():
    """This `except` also catches `FileNotFoundError`/`OSError`/`TimeoutError`, which carry none of
    these facts. An absent fact is reported as absent rather than invented."""
    from hub.api.v1.agent_trigger import _transport_failure_fields

    fields = _transport_failure_fields(FileNotFoundError("codex not found"), None)
    assert fields["stderr_tail"] is None
    assert fields["exit_code"] is None
    assert fields["method"] is None


def test_the_run_failed_payload_names_the_runtimes_own_exit_code():
    """The synthetic `exit_code` answers "did this turn succeed"; `runtime_exit_code` answers
    "what did the runtime process do". Loop 8 saw both read as answers to the same question."""
    from hub.api.v1.agent_trigger import _runtime_failure_fields

    fields = _runtime_failure_fields(
        TurnOutcome(thread_id="t-1", status="failed", exit_code=-1, stderr_tail="boom"),
        "run_failed",
    )
    assert fields == {"runtime_exit_code": -1, "stderr_tail": "boom"}


def test_the_payload_renders_the_exit_code_rather_than_shipping_it_raw():
    """Finding L9-1, measured against a live Hub on 2026-08-15.

    The first version of this change normalised only the composed message, so `run.error` said
    `exit -1` while the `run_failed` payload went out as `runtime_exit_code: 4294967295` — one
    death described by three numbers, which is the confusion the change set out to remove. A
    broadcast payload is a display surface; D3's "recorded values stay raw" covers `TurnOutcome`
    and `AppServerError`, not this.
    """
    from hub.api.v1.agent_trigger import _runtime_failure_fields, _transport_failure_fields

    outcome = TurnOutcome(thread_id="t-1", status="failed", exit_code=4294967295)
    assert _runtime_failure_fields(outcome, "run_failed")["runtime_exit_code"] == -1
    # The outcome itself is untouched — what the platform reported is still available in memory.
    assert outcome.exit_code == 4294967295

    fields = _transport_failure_fields(
        AppServerError("app-server process ended", exit_code=4294967295), None
    )
    assert fields["exit_code"] == -1


@pytest.mark.asyncio
async def test_the_lifecycle_broadcast_renders_a_forced_terminations_exit_code(app):
    """F94. The two `_*_failure_fields` builders render, and the Claude path does not use either
    — it passes `exit_code=exit_code` straight from the process. Measured live on 2026-08-28 by
    killing a running agent: the timeline read `Run failed (exit 4294967295)`, which is verbatim
    the sentence loop 8 filed and fixed for the Codex path only. Rendering now happens in
    `_broadcast_run_lifecycle`, so a caller cannot forget it."""
    from hub.api.v1.agent_trigger import _broadcast_run_lifecycle
    from hub.db.engine import async_session_factory
    from hub.sse import sse_manager

    queue = sse_manager.subscribe("proj-test")
    async with async_session_factory() as db:
        await _broadcast_run_lifecycle(
            db,
            "proj-test",
            "run_failed",
            agent="kill-render",
            run_id="run-kill-render",
            exit_code=4294967295,
        )
        await db.commit()

    seen = []
    while True:
        try:
            item = queue.get_nowait()
        except Exception:  # asyncio.QueueEmpty
            break
        seen.append((item.event, json.loads(item.data)))

    failed = [d for t, d in seen if t == "run_failed" and d["run_id"] == "run-kill-render"]
    assert len(failed) == 1
    assert failed[0]["exit_code"] == -1

    # The persisted event is the same surface the timeline summary reads, so it must agree.
    async with async_session_factory() as db:
        stored = (
            (
                await db.execute(
                    select(EventLog)
                    .where(EventLog.event_type == "run_failed")
                    .order_by(EventLog.id.desc())
                )
            )
            .scalars()
            .first()
        )
        assert stored.data["exit_code"] == -1

    # And the summary an operator actually reads.
    from hub.api.v1.agents import _run_lifecycle_summary

    assert _run_lifecycle_summary("run_failed", {"exit_code": -1}) == "Run failed (exit -1)"


def test_a_completed_run_reports_no_runtime_failure_fields():
    from hub.api.v1.agent_trigger import _runtime_failure_fields

    outcome = TurnOutcome(thread_id="t-1", status="completed", exit_code=0)
    assert _runtime_failure_fields(outcome, "run_completed") == {}


def test_absent_runtime_facts_are_omitted_not_nulled():
    """A key present but null invites a reader to render "exit: null", which is worse than saying
    nothing — the transport genuinely has no per-turn process status much of the time."""
    from hub.api.v1.agent_trigger import _runtime_failure_fields

    fields = _runtime_failure_fields(
        TurnOutcome(thread_id="t-1", status="failed"),
        "run_failed",
    )
    assert fields == {}


# ---------------------------------------------------------------------------
# B5 — the rebuild instruction names a command that exists
# ---------------------------------------------------------------------------


# B5's assertion lives in `test_ui_build_stamp.py`, which owns the git-backed `checkout` fixture
# the warning needs — a fingerprint cannot be computed outside a repository, so a hand-rolled
# tmp_path here returns `None` and would assert nothing.
#
# B6's assertion lives in `test_task_requirement_ids_readable.py`, which owns the document and
# task fixtures that produce real `FR-n` identifiers.
