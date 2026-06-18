"""Tests for agentweave.utils."""

import platform

import pytest

from agentweave.utils import generate_id, load_json, now_iso, save_json, write_json_atomic


def test_generate_id_format():
    id_ = generate_id("task")
    assert id_.startswith("task-")
    suffix = id_[len("task-") :]
    assert len(suffix) == 32  # full UUID4, no truncation


def test_generate_id_default_prefix():
    id_ = generate_id()
    assert id_.startswith("id-")


def test_generate_id_uniqueness():
    ids = {generate_id("x") for _ in range(50)}
    assert len(ids) == 50  # all unique


def test_generate_id_uuid_length():
    id_ = generate_id("task", uuid_length=8)
    assert id_.startswith("task-")
    assert len(id_) == len("task-") + 8
    # out-of-range lengths are clamped
    assert len(generate_id("task", uuid_length=0)) == len("task-") + 1
    assert len(generate_id("task", uuid_length=64)) == len("task-") + 32


def test_now_iso_format():
    ts = now_iso()
    # Should be parseable as ISO datetime
    from datetime import datetime

    dt = datetime.fromisoformat(ts)
    assert dt is not None


def test_save_and_load_json(tmp_path):
    data = {"key": "value", "num": 42}
    fp = tmp_path / "test.json"
    assert save_json(fp, data) is True
    loaded = load_json(fp)
    assert loaded == data


def test_load_json_missing_file(tmp_path):
    fp = tmp_path / "nonexistent.json"
    assert load_json(fp) is None


def test_load_json_invalid_content(tmp_path):
    fp = tmp_path / "bad.json"
    fp.write_text("not valid json")
    assert load_json(fp) is None


def test_save_json_creates_parent_dirs(tmp_path):
    fp = tmp_path / "a" / "b" / "c.json"
    assert save_json(fp, {"ok": True}) is True
    assert fp.exists()


@pytest.mark.skipif(platform.system() == "Windows", reason="POSIX-only file mode test")
def test_save_json_sets_0600_on_posix(tmp_path):
    """S11: message/task files must be owner-only readable on POSIX.
    save_json is the single chokepoint for all transport writes; chmodding
    here means every caller inherits the fix.
    """
    fp = tmp_path / "msg.json"
    assert save_json(fp, {"x": 1}) is True
    mode = fp.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


@pytest.mark.skipif(platform.system() == "Windows", reason="POSIX-only file mode test")
def test_write_json_atomic_sets_0600_on_posix(tmp_path):
    fp = tmp_path / "msg.json"
    assert write_json_atomic(fp, {"x": 1}) is True
    mode = fp.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_write_json_atomic_writes_atomically(tmp_path):
    """write_json_atomic must write to a .tmp then os.replace into place.

    A torn write to the destination would leave a partial JSON; the .tmp +
    os.replace pattern is the only crash-safe write for this codebase.
    """
    fp = tmp_path / "msg.json"
    assert write_json_atomic(fp, {"k": "v"}) is True
    assert fp.exists()
    # No .tmp file should be left behind
    leftover = list(tmp_path.glob("*.json.tmp"))
    assert leftover == [], f"leftover tmp files: {leftover}"


def test_write_json_atomic_cleans_up_tmp_on_failure(tmp_path, monkeypatch):
    """If the dump step fails, write_json_atomic must not leave a .tmp file."""
    fp = tmp_path / "msg.json"
    import json as _json

    def boom(*_a, **_k):
        raise OSError("simulated disk full")

    monkeypatch.setattr(_json, "dump", boom)
    assert write_json_atomic(fp, {"k": "v"}) is False
    assert not fp.exists()
    assert list(tmp_path.glob("*.json.tmp")) == []
