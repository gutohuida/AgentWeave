"""The lifespan teardown's settle-then-dispose — `hub/hub/main.py`, finding F295.

Two things the teardown has to get right, and neither is visible from "shutdown
completed": that the background run tasks are *settled before* the pool is released
(disposing first takes the connection away from a run still using it — the failure
`hub/tests/conftest.py` documents having already made), and that a settle which cannot
reach a fixed point **logs and continues** rather than raising, because an instance asked
to stop must stop.

**These drive the real `lifespan()` context manager**, not a transcription of it.
`conftest`'s `app` fixture uses `httpx.ASGITransport`, which deliberately never runs
`lifespan()`, and `test_lifespan_shutdown.py`'s `TestClient` runs it on a loop of its own
in another thread — neither lets a test put a task into `agent_trigger._background_runs`
on the same loop the teardown will settle. `async with lifespan(app)` does.

**`caplog` does not work across a lifespan startup, and that is measured, not assumed.**
`init_db()` runs Alembic, Alembic's `fileConfig` reconfigures logging, and the root logger
comes out of startup holding one `StreamHandler` where pytest's four handlers used to be
— so a warning emitted in the *teardown* reaches no capture handler at all. A recorder
attached to the `hub.main` logger itself survives, which is what `_warnings_from` below
does. A test here that used `caplog` would assert over an empty list.

**Every wait here is bounded.** A teardown that fails to settle is a hang, and an
unbounded hang in CI is what F292 costs hours to.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from hub import main
from hub.api.v1 import agent_trigger
from hub.main import _MAX_BACKGROUND_SETTLE_PASSES, create_app, lifespan

#: Every wait in this file. Seconds.
_BOUND = 30.0

#: Long enough that a task using it is only ever ended by the teardown cancelling it.
_NEVER = 3600.0


class _Recorder(logging.Handler):
    """A capture handler that lives on one named logger, not on the root."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextlib.contextmanager
def _warnings_from(logger_name: str):
    """Records at WARNING and above from one logger, surviving a lifespan startup."""
    logger = logging.getLogger(logger_name)
    recorder = _Recorder()
    previous_level = logger.level
    if logger.getEffectiveLevel() > logging.WARNING:
        logger.setLevel(logging.WARNING)
    logger.addHandler(recorder)
    try:
        yield recorder.records
    finally:
        logger.removeHandler(recorder)
        logger.setLevel(previous_level)


class _DisposeProbe:
    """Stands in for `hub.main`'s `engine` name for the length of one teardown.

    The teardown's only use of that name is `await engine.dispose()`, so replacing the
    whole object is enough and is narrower than patching a method on the shared engine.
    `observe()` is sampled *at the moment dispose is entered* — which is the ordering
    assertion 3.5 asks for, as opposed to the weaker one that would still hold with the
    bug.
    """

    def __init__(self, real_engine, observe):  # noqa: ANN001
        self._real_engine = real_engine
        self._observe = observe
        self.calls = 0
        self.observations: list = []

    async def dispose(self) -> None:
        self.calls += 1
        self.observations.append(self._observe())
        await self._real_engine.dispose()


async def test_shutdown_settles_a_background_run_before_disposing(monkeypatch):
    """3.5: assert the ordering, not merely that shutdown finished.

    "Shutdown completed" is true with the bug — the buggy teardown disposes and returns
    happily, having abandoned a pending task on a loop that is about to close. What
    distinguishes the two is the task's state *at the instant dispose is called*, so that
    is what the probe samples.
    """
    app = create_app()
    task: asyncio.Task | None = None

    probe = _DisposeProbe(main.engine, lambda: None if task is None else task.done())

    try:
        async with lifespan(app):
            task = asyncio.create_task(asyncio.sleep(_NEVER))
            agent_trigger._background_runs.add(task)
            task.add_done_callback(agent_trigger._background_runs.discard)
            # Cancelling a task that has never been scheduled skips its `except` clause
            # entirely; one yield puts it into the state a real in-flight run is in.
            await asyncio.sleep(0)
            assert not task.done()
            monkeypatch.setattr(main, "engine", probe)
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=_BOUND)
        agent_trigger._background_runs.discard(task)

    assert probe.calls == 1, "the teardown did not dispose the pool exactly once"
    assert probe.observations == [True], (
        "the background run task was still pending when the pool was disposed — the "
        "dispose is ahead of the settle"
    )
    assert task.cancelled(), "the teardown returned without cancelling the in-flight run"
    assert not agent_trigger._background_runs, "the settled task was left in the registry"


async def test_the_settle_bound_logs_and_completes_rather_than_raising(monkeypatch):
    """3.6: a settle that cannot reach a fixed point stops anyway, loudly, and disposes.

    `conftest.py`'s reference implementation of the same loop raises `AssertionError` on
    its cap, which is right for a test — a leak that poisons later tests is worth an
    error on the test that leaked. It is wrong for an instance being shut down, so this
    pins the difference rather than leaving it to the comment that explains it. The
    dispose assertions are the sharp end of "rather than raising": a raise on the bound
    would not merely be noisy, it would skip the release of the pool underneath it.

    The driver is a task that re-registers a successor from its own
    `except CancelledError`, which is the shape F286 made reachable in the product: a
    cancelled run hands its input back, the release can schedule the same agent again,
    and that registers a new task in the very set the teardown is draining.
    """
    successors: list[asyncio.Task] = []
    spawning = True

    def _spawn() -> None:
        async def _body() -> None:
            try:
                await asyncio.sleep(_NEVER)
            except asyncio.CancelledError:
                if spawning:
                    _spawn()
                raise

        task = asyncio.create_task(_body())
        successors.append(task)
        agent_trigger._background_runs.add(task)
        task.add_done_callback(agent_trigger._background_runs.discard)

    app = create_app()
    probe = _DisposeProbe(main.engine, lambda: len(agent_trigger._background_runs))
    registry_after = None
    try:
        with _warnings_from("hub.main") as records:
            async with lifespan(app):
                _spawn()
                # Without this the first task has never run, so cancelling it never
                # reaches the `except` clause and no successor is ever spawned — the
                # loop would settle on pass one and this test would assert nothing.
                await asyncio.sleep(0)
                monkeypatch.setattr(main, "engine", probe)
        registry_after = set(agent_trigger._background_runs)
    finally:
        spawning = False
        for task in list(successors):
            task.cancel()
        await asyncio.wait_for(asyncio.gather(*successors, return_exceptions=True), timeout=_BOUND)
        agent_trigger._background_runs.clear()

    # One task per pass, plus the one the test spawned itself: the loop ran to its bound
    # rather than giving up early or spinning past it.
    assert len(successors) == _MAX_BACKGROUND_SETTLE_PASSES + 1

    warnings = [record for record in records if "did not settle" in record.getMessage()]
    assert (
        len(warnings) == 1
    ), f"expected exactly one bound warning, got {[r.getMessage() for r in records]}"
    assert warnings[0].levelno == logging.WARNING
    message = warnings[0].getMessage()
    assert (
        "1 background run task(s)" in message
    ), f"the warning does not report the leftover count: {message!r}"
    assert f"in {_MAX_BACKGROUND_SETTLE_PASSES} passes" in message

    assert probe.calls == 1, (
        "the teardown did not reach the dispose after hitting its bound — a settle that "
        "gives up must still release the pool"
    )
    assert probe.observations == [0], (
        "the abandoned tasks were still in the module-level registry when the pool was "
        "disposed; a later lifespan in this process would await them on a dead loop"
    )

    assert (
        registry_after == set()
    ), "the unsettled tasks were carried out of the teardown in a module-level set"
