"""The prepared-database cache tolerates two workers landing the same template (Windows WinError 5)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from . import migration_templates


def _a_real_move(target: Path):  # noqa: ANN202
    def real(config, revision):  # noqa: ANN001, ANN202
        with sqlite3.connect(target) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
        return None

    return real


def _arrange(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    target = tmp_path / "work" / "db.sqlite"
    target.parent.mkdir()
    directory = tmp_path / "climbs"
    directory.mkdir()
    monkeypatch.setattr(
        migration_templates.settings, "database_url", f"sqlite+aiosqlite:///{target}"
    )
    return target, directory


def test_a_twin_template_landed_by_another_worker_counts_as_landed(tmp_path, monkeypatch) -> None:
    target, directory = _arrange(tmp_path, monkeypatch)

    def replace_refused_after_the_twin_landed(src, dst):  # noqa: ANN001, ANN202
        Path(dst).write_bytes(Path(src).read_bytes())
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(migration_templates.os, "replace", replace_refused_after_the_twin_landed)
    move = migration_templates.caching_downgrade(_a_real_move(target), directory)

    assert move(object(), "base") is None
    assert len(list(directory.glob("*.db"))) == 1
    assert not list(directory.glob("*.building"))


def test_a_refused_replace_with_no_template_still_fails(tmp_path, monkeypatch) -> None:
    target, directory = _arrange(tmp_path, monkeypatch)

    def replace_refused(src, dst):  # noqa: ANN001, ANN202
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(migration_templates.os, "replace", replace_refused)
    move = migration_templates.caching_downgrade(_a_real_move(target), directory)

    with pytest.raises(PermissionError):
        move(object(), "base")
    assert not list(directory.glob("*.building"))
