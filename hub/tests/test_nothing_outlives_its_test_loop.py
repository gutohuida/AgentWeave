"""Nothing a test leaves running outlives its event loop (AW-46..53, AW-55..58, AW-60, AW-61).

Each test has its own loop; the Hub's background modules remember tasks, and locks keyed by
`id(loop)`, at module level. The first test here leaves what a test that ends mid-landing leaves:
a check run whose cancellation schedules its successor (`project_checks._ended`), and a landing
lock held by a task that never finishes. The second, run after it in the same process, finds none
of it: before the teardown settled every task and forgot that state, the second test's
`project_checks.drain()` failed with "got Future <_GatheringFuture pending> attached to a different
loop", and a loop allocated where the first one was would have been handed the held lock.

A pull request's CI watch left the same way kept `pull_requests._watching` holding a job that
never finishes, which AW-57's test asserts there is none of.

The two run in this order on one worker (`xdist_group`, and pytest keeps a file's order).
"""

from __future__ import annotations

import asyncio

import pytest

from hub import known_failing, landing_queue, project_checks, pull_requests

pytestmark = [pytest.mark.asyncio, pytest.mark.xdist_group("nothing-outlives-its-test-loop")]

TASK = "task-outlives-0001"


async def test_a_test_leaves_a_check_run_and_a_held_landing_lock_behind():
    async def forever():
        await asyncio.Event().wait()

    job = asyncio.get_running_loop().create_task(forever())
    project_checks._inflight[TASK] = job
    project_checks._inflight_tips[TASK] = ("proj-test", "0" * 40)
    # What `request_run` registers: cancelled at teardown, this schedules a recheck of its own.
    job.add_done_callback(lambda done: project_checks._ended("proj-test", TASK, done))

    held = asyncio.Event()

    async def holds_the_landing_lock():
        async with landing_queue._lock("proj-test"):
            held.set()
            await asyncio.Event().wait()

    landing_queue._start("proj-test", holds_the_landing_lock(), "hold the landing lock")
    # A pull request's CI watch, as `watch_ci` registers one (AW-57 asserts none is left unfinished).
    watch = asyncio.get_running_loop().create_task(forever())
    pull_requests._watching[(id(asyncio.get_running_loop()), "build-outlives")] = watch
    await held.wait()
    async with known_failing._lock():
        pass

    assert project_checks.is_running(TASK)
    assert landing_queue._lock("proj-test").locked()


async def test_the_next_test_finds_nothing_of_it():
    assert not project_checks.is_running(TASK)
    assert not project_checks._pending and not project_checks._inflight
    assert not project_checks._semaphores
    assert not landing_queue._jobs and not landing_queue._locks
    assert not known_failing._locks
    assert not pull_requests._watching and not pull_requests._asking
    assert not landing_queue._lock("proj-test").locked()
    await asyncio.wait_for(project_checks.drain(), timeout=30)
