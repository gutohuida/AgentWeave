"""A module-level `asyncio` primitive must not carry state between tests.

F383's first half. `turn_scheduler._lock_for` caches an `asyncio.Lock` per
`(project_id, agent)` in a module-level dict, and nothing used to clear it. A background
run cancelled inside `async with _lock_for(...)` — which is what the autouse teardown in
`conftest.py` does to every leftover run — leaves that lock **held**, and the next test to
contend for the same key gets `RuntimeError: ... is bound to a different event loop` from a
lock belonging to an event loop that closed with the previous test.

The pair below is deliberately order-dependent, which is unusual here and is the point:
the first test leaks on purpose and the second one is the assertion. Delete
`_module_level_async_primitives_are_per_test` from `conftest.py` and the second test fails,
which is the property that makes this a regression test rather than a restatement of the
fixture. Anything that reads only one of the two proves nothing.
"""

import asyncio

import pytest

import hub.turn_scheduler as turn_scheduler

_LEAKED_KEY = ("proj-f383-leak", "dev")


@pytest.mark.asyncio
async def test_a_lock_held_when_a_test_ends_is_the_leak_this_guards():
    """Leak one, the way a cancelled background run does. Nothing is asserted about later."""
    lock = turn_scheduler._lock_for(*_LEAKED_KEY)
    await lock.acquire()

    assert lock.locked()
    assert _LEAKED_KEY in turn_scheduler._agent_locks
    # Deliberately never released, and deliberately not cleaned up here: the whole
    # question is what the *next* test inherits.


@pytest.mark.asyncio
async def test_the_next_test_does_not_inherit_the_held_lock():
    assert _LEAKED_KEY not in turn_scheduler._agent_locks, (
        "the previous test's held lock survived into this one; "
        "conftest._module_level_async_primitives_are_per_test is not running"
    )

    # And the fresh one is usable from *this* test's event loop, which is the failure the
    # CI traceback actually showed — an inherited lock raises here rather than at creation.
    lock = turn_scheduler._lock_for(*_LEAKED_KEY)
    assert not lock.locked()
    async with lock:
        assert lock.locked()


@pytest.mark.asyncio
async def test_a_contended_lock_is_usable_from_a_second_test_loop():
    """The uncontended path never consults the loop, so contention is what must be checked.

    `asyncio.Lock.acquire` returns on a fast path that does not call `_get_loop()` when the
    lock is free, so a stale lock can be acquired once without complaint. Only a second
    waiter reaches the loop check and raises. Contending here means this test exercises the
    branch the CI failure came from rather than the one that stays quiet.
    """
    lock = turn_scheduler._lock_for("proj-f383-contended", "dev")
    order = []

    async def waiter(name: str) -> None:
        async with lock:
            order.append(name)
            await asyncio.sleep(0)

    await asyncio.gather(waiter("first"), waiter("second"))

    assert sorted(order) == ["first", "second"]
    assert not lock.locked()
