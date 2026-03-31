"""Tests for agentweave.locking."""

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
