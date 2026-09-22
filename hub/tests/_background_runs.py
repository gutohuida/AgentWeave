"""Waiting for the background runs `/agent/trigger` starts, without spinning (F394).

`agent_trigger._background_runs` is a set that each run's task leaves through a done-callback,
`set.discard`, which asyncio schedules with `call_soon` rather than running when the task ends.
The loop this replaces was, in a dozen files:

    while agent_trigger._background_runs:
        for task in list(agent_trigger._background_runs):
            await task

and `await` on a task that has already finished returns without yielding to the event loop. A run
whose failure schedules a retry (the spawn-failure branch of `_execute_run` ends in
`redrain_queued_agents`, which starts the next run) can have that retry finish in the same loop
pass, *after* the step that woke the waiting test. The retry is then done but still in the set, its
`discard` is queued behind the test, and the test awaits it, finds it done, and loops again. It
never yields, so the `discard` never runs. Measured on CI as F394: `hub-test` hung for six hours
three times, then twice, once `pytest-timeout` was in place, with the main thread's stack running *inside*
`_run_once` at `await task`. A coroutine that was waiting would have left the thread parked in the
selector with no test frames on it.

Removing what was awaited from the set, rather than relying on the callback to, is what makes
every pass progress. `gather` also yields once even when every task is already done.
"""

import asyncio

import hub.api.v1.agent_trigger as agent_trigger


async def await_background_runs() -> None:
    """Wait for every background run, including runs started while waiting.

    A run that raised re-raises here, as the loop this replaces did.
    """
    while agent_trigger._background_runs:
        tasks = list(agent_trigger._background_runs)
        await asyncio.gather(*tasks)
        agent_trigger._background_runs.difference_update(tasks)
