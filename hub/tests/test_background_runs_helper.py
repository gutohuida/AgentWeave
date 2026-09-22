"""F394: the shared wait for background runs finishes when a retry ends behind the waiter.

The ordering is the one `_background_runs.py` describes: run A starts its retry B as its last
action, so B's first step is queued before the waiter's wakeup, and B finishes there. B's
`discard` then queues *behind* the waiter, which finds B done and still registered. The helper
this replaced spun on that forever without yielding, so no timeout inside the loop could stop it.
The scenario therefore runs on its own loop in a thread, and the test asserts that the thread ends.
"""

import asyncio
import threading

import hub.api.v1.agent_trigger as agent_trigger

from ._background_runs import await_background_runs


def _register(runs: set, coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    runs.add(task)
    task.add_done_callback(runs.discard)
    return task


async def _retry_finishing_behind_the_waiter(runs: set) -> None:
    async def retry():
        return None

    async def failed_run():
        # Last action, as `_execute_run`'s spawn-failure branch ends in `redrain_queued_agents`.
        _register(runs, retry())

    _register(runs, failed_run())
    await await_background_runs()


def test_a_retry_that_finishes_behind_the_waiter_is_waited_for_not_spun_on(monkeypatch):
    runs: set = set()
    monkeypatch.setattr(agent_trigger, "_background_runs", runs)
    outcome: list = []

    def scenario() -> None:
        asyncio.run(_retry_finishing_behind_the_waiter(runs))
        outcome.append("returned")

    thread = threading.Thread(target=scenario, daemon=True)
    thread.start()
    thread.join(timeout=10)

    assert not thread.is_alive(), (
        "the wait spun on a finished run whose discard was queued behind it (F394)"
    )
    assert outcome == ["returned"]
    assert runs == set()
