"""This Hub process's stable identity, minted once and read from a local marker file.

See openspec/changes/2026-08-06-agent-messaging-delivery/design.md, Decision 3: run
credentials are scoped to the instance that minted them so a future shared-database
deployment cannot let a credential from one Hub process validate against another.
"""


def test_load_or_create_mints_and_persists_a_stable_id(tmp_path, monkeypatch):
    from hub import instance_identity
    from hub.config import settings

    db_path = tmp_path / "sub" / "agentweave.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(instance_identity, "_instance_id", None)

    first = instance_identity.load_or_create()
    assert first
    assert instance_identity.get() == first
    assert (tmp_path / "sub" / "instance_identity.json").exists()

    # Simulate a fresh process re-reading the same marker file.
    monkeypatch.setattr(instance_identity, "_instance_id", None)
    second = instance_identity.load_or_create()
    assert second == first


def test_load_or_create_recovers_from_a_corrupted_marker(tmp_path, monkeypatch):
    from hub import instance_identity
    from hub.config import settings

    db_path = tmp_path / "agentweave.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(instance_identity, "_instance_id", None)

    marker = tmp_path / "instance_identity.json"
    marker.write_text("not valid json", encoding="utf-8")

    instance_id = instance_identity.load_or_create()

    assert instance_id
    assert marker.read_text(encoding="utf-8") != "not valid json"


def test_get_returns_none_before_anything_has_loaded(monkeypatch):
    from hub import instance_identity

    monkeypatch.setattr(instance_identity, "_instance_id", None)
    assert instance_identity.get() is None


def test_in_memory_database_mints_an_id_without_writing_to_disk(monkeypatch, tmp_path):
    """An in-memory sqlite DB has no durable state to
    bind a marker file to. Regression test for a real bug caught this session: the naive
    version of `_marker_path` fell back to `os.path.dirname(":memory:") or "."`, which
    resolved to the process's current working directory — writing a stray
    `instance_identity.json` into whatever directory pytest happened to be run from."""
    from hub import instance_identity
    from hub.config import settings

    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(instance_identity, "_instance_id", None)
    monkeypatch.chdir(tmp_path)

    instance_id = instance_identity.load_or_create()

    assert instance_id
    assert instance_identity.get() == instance_id
    assert not (tmp_path / "instance_identity.json").exists()
    assert list(tmp_path.iterdir()) == []
