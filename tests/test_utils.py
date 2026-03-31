"""Tests for agentweave.utils."""

from agentweave.utils import generate_id, load_json, now_iso, save_json


def test_generate_id_format():
    id_ = generate_id("task")
    assert id_.startswith("task-")
    suffix = id_[len("task-") :]
    assert len(suffix) == 8


def test_generate_id_default_prefix():
    id_ = generate_id()
    assert id_.startswith("id-")


def test_generate_id_uniqueness():
    ids = {generate_id("x") for _ in range(50)}
    assert len(ids) == 50  # all unique


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
