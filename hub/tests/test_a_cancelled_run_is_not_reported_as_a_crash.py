"""A run cancelled out from under itself is reported as a cancellation, not a crash — F298.

Both transports catch `(Exception, asyncio.CancelledError)` around the whole body of a run,
and each handler's own comment block says the cancellation it was written for is the
event-loop teardown of a Hub that was asked to stop. Until this, both reported that with
`logger.exception`: an `ERROR` line and a full traceback, per in-flight run, on every clean
shutdown — the one place an operator looks to decide whether a stop went cleanly, and the
one thing a log scraper greps for.

These tests pin the split rather than the shutdown: what changes is the *report*, and the
report is a pure function of the exception. The row marking, the failure tail and the
re-raise are unchanged and are covered where they already were
(`test_shutdown_settles_background_runs.py`, `test_an_operator_stop_actually_stops.py`).
The live half — that the two handlers actually route through this — was driven with
`scripts/drive/f295_shutdown_drive.py`, whose "no traceback after the break" check fails
before this change and passes after it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from hub.api.v1.agent_trigger import _log_abnormal_run_end

_LOGGER_NAME = "hub.api.v1.agent_trigger"


class _Recorder(logging.Handler):
    """Captures records from one named logger, at every level."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextlib.contextmanager
def _records_from(logger_name: str):
    """Everything one logger emits, independent of root handlers and pytest's capture.

    Attached to the logger itself rather than using `caplog` for the reason
    `test_shutdown_settles_background_runs.py` measures: anything that reconfigures the
    root logger (Alembic's `fileConfig`, in that file's case) empties a root-attached
    capture, and a test that asserts over an empty list asserts nothing.
    """
    logger = logging.getLogger(logger_name)
    recorder = _Recorder()
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(recorder)
    try:
        yield recorder.records
    finally:
        logger.removeHandler(recorder)
        logger.setLevel(previous_level)


def _report(exc: BaseException, label: str = "run") -> logging.LogRecord:
    """One report, raised and caught so `logger.exception` has an exception to attach."""
    with _records_from(_LOGGER_NAME) as records:
        try:
            raise exc
        except BaseException as caught:  # noqa: BLE001 — the handlers being modelled catch both
            _log_abnormal_run_end(caught, run_id="run-abc123", agent="scribe", label=label)
    assert (
        len(records) == 1
    ), f"expected exactly one record, got {[r.getMessage() for r in records]}"
    return records[0]


def test_a_cancelled_run_is_logged_as_a_cancellation_without_a_traceback():
    record = _report(asyncio.CancelledError())

    assert record.levelno == logging.WARNING, (
        "a cancellation is reported at "
        f"{logging.getLevelName(record.levelno)}; an operator's own stop is not an error"
    )
    assert record.exc_info is None, "the cancellation carries a stack trace an operator has to read"
    message = record.getMessage()
    assert "Unhandled error" not in message, message
    assert "cancelled" in message, message
    # The two facts that make the line usable at all: which run, and whose.
    assert "run-abc123" in message and "scribe" in message, message


def test_a_real_failure_keeps_its_error_and_its_traceback():
    record = _report(ValueError("the spawn died"))

    assert record.levelno == logging.ERROR
    assert record.exc_info is not None, "a genuine failure lost the traceback"
    assert record.exc_info[0] is ValueError
    assert record.getMessage() == "Unhandled error in run run-abc123 for 'scribe'"


def test_the_app_server_transport_keeps_its_own_label_on_both_branches():
    """One helper, two callers — the label is what distinguishes their lines in a log."""
    failed = _report(ValueError("the app server died"), label="app-server run")
    assert failed.getMessage() == "Unhandled error in app-server run run-abc123 for 'scribe'"

    cancelled = _report(asyncio.CancelledError(), label="app-server run")
    assert cancelled.levelno == logging.WARNING
    assert "app-server run run-abc123" in cancelled.getMessage()
