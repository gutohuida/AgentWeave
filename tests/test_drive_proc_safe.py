"""F1197 suspect: a drive's cleanup must not tree-kill a pid that was reused.

`scripts/drive/proc_safe.py` walks a table of {pid: (parent pid, creation time)}. The old drive walk
(`ParentProcessId` only) took a process as a child of whatever pid it named; an orphan whose parent
pid was later reused by an unrelated process then looked like that process's child.
"""

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "drive" / "proc_safe.py"
_spec = importlib.util.spec_from_file_location("proc_safe_under_test", _PATH)
assert _spec is not None and _spec.loader is not None
proc_safe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = proc_safe
_spec.loader.exec_module(proc_safe)

# pid 100 is the drive's Hub (created at 1000). 101 is its real child (2000). 102 was an orphan of
# an earlier Hub that also had pid 100: it names 100 as its parent but was created at 400, long
# before this 100 existed, so it is an unrelated process. 200 is a grandchild of 101.
TABLE = {
    100: (1, 1000),
    101: (100, 2000),
    102: (100, 400),
    200: (101, 3000),
    300: (1, 50),  # a remembered pid reused by something that predates the drive (since=500)
}


def naive_walk(table, roots):
    """The pre-fix walk: ParentProcessId alone."""
    tree, grew = set(roots), True
    while grew:
        grew = False
        for pid, (parent, _created) in table.items():
            if parent in tree and pid not in tree:
                tree.add(pid)
                grew = True
    return tree


@pytest.fixture(autouse=True)
def _as_windows(monkeypatch):
    # process_job.descendants is Windows-only; the table here is fabricated, so the walk is pure.
    monkeypatch.setattr(sys, "platform", "win32")


def test_the_old_walk_would_have_taken_the_reused_pids_orphan():
    assert 102 in naive_walk(TABLE, {100})


def test_a_child_created_before_its_parent_is_not_taken():
    found = proc_safe.tree([100], TABLE)
    assert 102 not in found
    assert set(found) == {100, 101, 200}


def test_children_come_before_their_parents():
    found = proc_safe.tree([100], TABLE)
    assert found.index(200) < found.index(101) < found.index(100)


def test_a_remembered_root_older_than_the_drive_is_not_ours():
    assert proc_safe.tree([300], TABLE, since=500) == []
    assert proc_safe.tree([100], TABLE, since=500) != []


def test_a_root_that_is_gone_is_skipped():
    assert proc_safe.tree([999], TABLE) == []


def test_kill_pids_refuses_a_pid_that_is_not_in_the_snapshot(monkeypatch):
    # Nothing is opened for a pid the snapshot never saw; on any platform the answer is empty.
    assert proc_safe.kill_pids([999999], {}) == []
