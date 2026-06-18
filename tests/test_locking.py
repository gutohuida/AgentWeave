"""Tests for agentweave.locking."""

import threading
import time

import pytest

from agentweave.locking import LockError, acquire_lock, is_locked, lock, release_lock


def test_acquire_and_release(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert acquire_lock("mylock") is True
    assert is_locked("mylock") is True
    release_lock("mylock")
    assert is_locked("mylock") is False


def test_context_manager_releases_on_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with lock("ctx-lock"):
        assert is_locked("ctx-lock")
    assert not is_locked("ctx-lock")


def test_context_manager_releases_on_exception(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    try:
        with lock("err-lock"):
            raise ValueError("oops")
    except ValueError:
        pass
    assert not is_locked("err-lock")


def test_lock_timeout_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    acquire_lock("busy-lock")
    with pytest.raises(LockError), lock("busy-lock", timeout=0.1):
        pass
    release_lock("busy-lock")


def test_double_acquire_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert acquire_lock("double") is True
    # Second acquire should fail (short timeout)
    assert acquire_lock("double", timeout=0.05) is False
    release_lock("double")


def test_release_nonexistent_lock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Should not raise
    result = release_lock("ghost-lock")
    assert result is False


def test_is_locked_nonexistent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert is_locked("no-such-lock") is False


# ---------------------------------------------------------------------------
# Thread-race tests (PR 12, T8)
#
# These exercise the real acquire_lock / release_lock pair from two
# concurrent threads. The test pattern:
#   1. monkeypatch.chdir to a temp dir so the .agentweave/.locks dir
#      lives inside the sandbox.
#   2. Use threading.Barrier(N) to start all threads simultaneously.
#   3. Use short timeouts (100-500 ms) to keep the suite fast.
#
# Cross-platform: works on Windows (file open with "x" mode) and POSIX
# (same O_EXCL-equivalent semantics). The DEFAULT_RETRY_DELAY is 0.1s,
# so timeout=0.3s gives T2 ~3 chances to retry before giving up.
# ---------------------------------------------------------------------------


def test_two_threads_serial_acquire(tmp_path, monkeypatch):
    """T1 acquires the lock; T2 must NOT acquire until T1 releases.

    Verifies that a held lock actually blocks a concurrent acquirer
    (not just sequential acquire/release, which the earlier tests cover).
    """
    monkeypatch.chdir(tmp_path)
    barrier = threading.Barrier(2)
    t1_got = []
    t2_got = []
    t2_done = threading.Event()

    def t1_acquire():
        barrier.wait()
        with lock("race-serial"):
            t1_got.append(True)
            # Hold the lock for long enough that T2 has to wait.
            time.sleep(0.3)
        # After release, signal T2 to retry.
        t2_done.set()

    def t2_acquire():
        barrier.wait()
        # T2 waits for T1 to release, then acquires.
        t2_done.wait(timeout=2.0)
        with lock("race-serial", timeout=1.0):
            t2_got.append(True)

    t1 = threading.Thread(target=t1_acquire)
    t2 = threading.Thread(target=t2_acquire)
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)
    assert not t1.is_alive() and not t2.is_alive(), "threads deadlocked"
    assert t1_got == [True]
    assert t2_got == [True], "T2 must acquire the lock after T1 releases"


def test_lock_held_blocks_other_thread_with_short_timeout(tmp_path, monkeypatch):
    """T1 holds the lock for the entire test; T2 must time out."""
    monkeypatch.chdir(tmp_path)
    barrier = threading.Barrier(2)
    t1_in_critical = threading.Event()
    t2_started = threading.Event()
    t2_result = []

    def t1_hold():
        barrier.wait()
        with lock("race-timeout"):
            t1_in_critical.set()
            # T2 will try to acquire; hold the lock until it gives up.
            time.sleep(0.5)

    def t2_try_acquire():
        barrier.wait()
        # Wait for T1 to actually be in the critical section (deterministic).
        assert t1_in_critical.wait(timeout=2.0), "T1 never entered the critical section"
        t2_started.set()
        # 200ms timeout — T1 will still be holding the lock at that point.
        t2_result.append(acquire_lock("race-timeout", timeout=0.2))

    t1 = threading.Thread(target=t1_hold)
    t2 = threading.Thread(target=t2_try_acquire)
    t1.start()
    t2.start()
    # Wait for T2 to finish (it should time out within 200-400ms).
    t2.join(timeout=3.0)
    t1.join(timeout=3.0)
    assert t1_in_critical.is_set(), "T1 must have entered the critical section"
    assert t2_result == [
        False
    ], f"T2 should have failed to acquire (T1 held the lock), got {t2_result!r}"


def test_concurrent_threads_exactly_one_wins(tmp_path, monkeypatch):
    """Two threads race to acquire a FRESH lock. Exactly one wins.

    Uses a Barrier(2) so both threads enter acquire_lock at nearly the
    same instant. With a tight timeout and a fresh lock, the
    open-with-O_EXCL primitive decides the race deterministically: one
    thread wins, the other gets FileExistsError and eventually times out.
    """
    monkeypatch.chdir(tmp_path)
    barrier = threading.Barrier(2)
    results = []
    results_lock = threading.Lock()

    def attempt():
        barrier.wait()
        got = acquire_lock("race-fresh", timeout=0.3)
        with results_lock:
            results.append(got)

    t1 = threading.Thread(target=attempt)
    t2 = threading.Thread(target=attempt)
    t1.start()
    t2.start()
    t1.join(timeout=3.0)
    t2.join(timeout=3.0)
    assert sorted(results) == [
        False,
        True,
    ], f"exactly one of the two threads should win, got {results!r}"
