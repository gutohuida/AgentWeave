"""The probe the never-freeze tests rest on: a real hold counts, a late wake from an idle poll does
not. Without the first those tests prove nothing; without the second they fail on a loaded machine.
"""

import asyncio
import time

import pytest

from ._loop_lag import GIT_DELAY, STALL_LIMIT, LagProbe


@pytest.mark.asyncio
async def test_a_blocking_call_on_the_loop_counts_as_a_stall():
    async with LagProbe() as probe:
        time.sleep(GIT_DELAY)
    assert probe.worst >= STALL_LIMIT


@pytest.mark.asyncio
async def test_work_held_on_the_loop_counts_as_a_stall():
    async with LagProbe() as probe:
        end = time.perf_counter() + GIT_DELAY
        while time.perf_counter() < end:
            sum(range(1000))
    assert probe.worst >= STALL_LIMIT


@pytest.mark.asyncio
async def test_an_idle_loop_reads_as_polling():
    async with LagProbe() as probe:
        await asyncio.sleep(0.2)
        samples = list(probe._loop_samples)
    assert samples and probe._waiting_to_wake(samples[0][0], samples[-1][0])
