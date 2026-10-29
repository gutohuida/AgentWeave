"""The main watch resolves every project's workspace off the event loop.

The watch looks at every project with a main branch every 30 s (before
`amendments-main-watch-and-the-next-slice` only projects with checks). Resolving a workspace
canonicalises the directory and reads its marker, which on an unreachable share blocks; done on
the loop that freezes the whole Hub. Pattern: `test_a_slow_share_does_not_freeze_the_hub.py`.
"""

import asyncio
import time

import pytest

from hub import project_checks, project_workspace

from .test_task_integration import make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

_STALL = 2.0
_BOUND = 0.3


async def test_a_stalled_resolve_does_not_block_the_loop_during_a_watch_pass(
    app, auth_headers, tmp_path, monkeypatch, bind_project_workspace
):
    make_repo(tmp_path)
    await bind_project_workspace(tmp_path)  # the real resolver, on a real bound repository
    await set_main_branch("main")
    calls: list[int] = []
    real = project_workspace.canonicalize_project_directory

    def stalling(*args, **kwargs):
        calls.append(1)
        time.sleep(_STALL)  # a blocking call, as an unreachable share's resolve is
        return real(*args, **kwargs)

    monkeypatch.setattr(project_workspace, "canonicalize_project_directory", stalling)

    worst = 0.0
    stop = False

    async def ticker():
        nonlocal worst
        last = time.monotonic()
        while not stop:
            await asyncio.sleep(0.02)
            now = time.monotonic()
            worst = max(worst, now - last)
            last = now

    watcher = asyncio.create_task(ticker())
    await asyncio.sleep(0.1)
    await project_checks.watch_main_once()
    await asyncio.sleep(0.1)  # let the ticker report a gap the pass left behind
    stop = True
    await watcher

    assert calls, "the watch pass never resolved the workspace, so this proves nothing"
    assert worst < _BOUND, f"the loop was blocked {worst:.2f}s by the watch pass"


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
