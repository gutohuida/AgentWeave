"""The main watch resolves every project's workspace off the event loop.

The watch looks at every project with a main branch every 30 s (before
`amendments-main-watch-and-the-next-slice` only projects with checks). Resolving a workspace
canonicalises the directory and reads its marker, which on an unreachable share blocks; done on
the loop that freezes the whole Hub. Pattern: `test_a_slow_share_does_not_freeze_the_hub.py`.
"""

import threading
import time

import pytest

from hub import project_checks, project_workspace

from ._loop_lag import STALL_LIMIT, LagProbe
from .test_task_integration import make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

#: Far past the probe's limit, so a resolve on the loop fails it however the machine is loaded.
_STALL = 2.0


async def test_a_stalled_resolve_does_not_block_the_loop_during_a_watch_pass(
    app, auth_headers, tmp_path, monkeypatch, bind_project_workspace
):
    make_repo(tmp_path)
    await bind_project_workspace(tmp_path)  # the real resolver, on a real bound repository
    await set_main_branch("main")
    loop_thread = threading.current_thread()
    #: For each resolve, whether it ran on the loop's thread: where it ran does not depend on how
    #: busy the machine is. The probe judges the rest of the pass (it was a 20 ms ticker against a
    #: 300 ms wall-clock bound, which a loaded machine's late wakes could cross).
    on_loop: list[bool] = []
    real = project_workspace.canonicalize_project_directory

    def stalling(*args, **kwargs):
        on_loop.append(threading.current_thread() is loop_thread)
        time.sleep(_STALL)  # a blocking call, as an unreachable share's resolve is
        return real(*args, **kwargs)

    monkeypatch.setattr(project_workspace, "canonicalize_project_directory", stalling)

    async with LagProbe() as probe:
        await project_checks.watch_main_once()

    assert on_loop, "the watch pass never resolved the workspace, so this proves nothing"
    assert not any(on_loop), "the watch pass resolved a workspace on the loop"
    assert probe.worst < STALL_LIMIT, f"the loop stalled {probe.worst * 1000:.0f} ms: {probe.why}"


async def test_a_stretch_longer_than_the_list_says_how_many_more():
    from hub import main_watch

    listed = [{"sha": f"{i:040d}", "subject": f"c{i}", "author": "a"} for i in range(5)]
    cap = main_watch.MAX_COMMITS
    prior = [{"sha": f"{i:040d}", "subject": "old", "author": "a"} for i in range(cap)]

    kept = main_watch._with_overflow(listed, prior, more=7)
    assert len(kept) == cap + 1
    assert kept[-1]["more"] == 7 + 5 and kept[-1]["subject"] == "and 12 more"
    # the next move carries what an earlier one dropped
    again = main_watch._with_overflow(listed[:1], kept, more=0)
    assert again[-1]["more"] == 12 + 1
