"""The staleness warning can be cleared by doing what it asks.

Comparing commit dates cannot answer this. A change that leaves the built bundle byte-identical —
types, comments, anything erased before the bundle is produced — gives the rebuild nothing to
commit, so the artefact's commit date never moves and the warning stands forever. Loop 7 hit
exactly that: a four-line TypeScript-types commit produced an identical bundle (verified by
rebuilding and diffing), and `/health` reported `ui_stale` regardless.

A warning that survives its own remedy teaches the operator to ignore the one signal that catches a
genuinely stale bundle.

So the bundle carries an assertion of the source state it was built from. That is a promise rather
than a proof — only rebuilding proves it — but a dated, committed, attributable promise is a
reviewable diff rather than an invisible omission.

`test_ui_staleness.py` is deliberately untouched: where no stamp exists this must behave exactly as
it did, so an installation carrying no assertion is not thereby declared current.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from hub.main import (
    UI_BUILD_STAMP,
    _compute_ui_staleness_warning,
    _reset_ui_staleness_cache,
    _ui_staleness_warning,
    read_ui_build_stamp,
    ui_source_fingerprint,
)

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)


def git(path: Path, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, **kwargs)


def make_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")


def commit_at(root: Path, date: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    git(root, "add", "-A")
    subprocess.run(
        ["git", "commit", "-q", "-m", f"at {date}"], cwd=root, env=env, capture_output=True
    )


@pytest.fixture
def checkout(tmp_path):
    """A repo holding both trees, as the real one does — the stamp compares them within one repo."""
    root = tmp_path / "repo"
    make_repo(root)
    src = root / "ui" / "src"
    dist = root / "static" / "ui"
    src.mkdir(parents=True)
    dist.mkdir(parents=True)
    (src / "App.tsx").write_text("export const App = () => null\n", encoding="utf-8")
    (dist / "index.js").write_text("console.log(1)\n", encoding="utf-8")
    commit_at(root, "2026-01-01T00:00:00+00:00")
    return root, src, dist


def stamp(dist: Path, fingerprint: str, built_at: str = "2026-01-01T00:00:00+00:00") -> None:
    (dist / UI_BUILD_STAMP.name).write_text(
        json.dumps({"src_fingerprint": fingerprint, "built_at": built_at}), encoding="utf-8"
    )


def test_a_stamp_matching_the_source_clears_the_warning(checkout):
    _root, src, dist = checkout
    stamp(dist, ui_source_fingerprint(src))

    assert _compute_ui_staleness_warning(dist, src) is None


def test_a_stamp_naming_other_source_still_warns(checkout):
    _root, src, dist = checkout
    stamp(dist, "a fingerprint from some other source state")

    warning = _compute_ui_staleness_warning(dist, src)
    assert warning is not None
    assert "the source has changed since" in warning
    # `make` is on PATH in neither Git Bash nor PowerShell on some supported installations, and
    # `CLAUDE.md` records that — so naming only `make ui` made the warning contradict the
    # project's own documentation, and an instruction that cannot be followed is one the operator
    # learns to ignore. The script is named first because the first command gets pasted; the
    # shorthand is kept for installations that have it.
    assert "python scripts/refresh_ui_bundle.py" in warning
    assert warning.index("refresh_ui_bundle.py") < warning.index("make ui")


def test_a_types_only_change_clears_after_restamping_with_no_bundle_change(checkout):
    """The loop-7 case, end to end.

    The bundle is byte-identical throughout — nothing is written to `dist` at any point — and the
    warning still appears and still clears. That is only possible because the stamp moves when the
    source does, which is what gives an identical rebuild something to commit.
    """
    root, src, dist = checkout
    before = list(dist.iterdir())
    stamp(dist, ui_source_fingerprint(src))
    assert _compute_ui_staleness_warning(dist, src) is None

    # A types-only edit: erased at build, so the bundle would be identical.
    (src / "types.ts").write_text("export type Task = { id: string }\n", encoding="utf-8")
    commit_at(root, "2026-02-01T00:00:00+00:00")

    assert _compute_ui_staleness_warning(dist, src) is not None, "the change must be noticed"

    # "Rebuild": the bundle does not change, and only the stamp is re-recorded.
    stamp(dist, ui_source_fingerprint(src), built_at="2026-02-01T00:00:00+00:00")

    assert _compute_ui_staleness_warning(dist, src) is None
    assert [p.name for p in before] == ["index.js"], "the bundle was never touched"


def test_an_uncommitted_source_edit_is_reported(checkout):
    """A commit-date comparison cannot see this at all."""
    _root, src, dist = checkout
    stamp(dist, ui_source_fingerprint(src))
    assert _compute_ui_staleness_warning(dist, src) is None

    (src / "App.tsx").write_text("export const App = () => 'edited'\n", encoding="utf-8")

    warning = _compute_ui_staleness_warning(dist, src)
    assert warning is not None
    assert "uncommitted" in warning


def test_a_stamp_recorded_against_a_dirty_tree_survives_the_commit(checkout):
    """The actual `CLAUDE.md` workflow: build, stamp, THEN commit -- and it must clear.

    `scripts/refresh_ui_bundle.py` stamps a fingerprint before `git add`/`git commit` land the
    source and dist together (`CLAUDE.md`'s documented order). A fingerprint that folded in
    `git status --porcelain`'s dirty diff was always recorded against a *dirty* tree, and the
    moment the commit landed that same tree went clean -- the dirty component vanished and the
    fingerprint could never match again. That is `known_debts.ui-stale-false-positive`, confirmed
    live: commit `8898155` rebuilt and committed byte-identical output to a fresh rebuild, and only
    the stamp moved (`ab7e5fe`).
    """
    root, src, dist = checkout
    (src / "App.tsx").write_text("export const App = () => 'built'\n", encoding="utf-8")
    # Stamp BEFORE committing -- this is the order `refresh_ui_bundle.py` actually runs in.
    stamp(dist, ui_source_fingerprint(src))
    assert _compute_ui_staleness_warning(dist, src) is None, "the freshly-stamped, dirty tree must read current"

    commit_at(root, "2026-02-01T00:00:00+00:00")

    assert _compute_ui_staleness_warning(dist, src) is None, (
        "committing exactly what was stamped must not itself produce staleness"
    )


def test_absent_stamp_falls_back_to_the_commit_date_comparison(checkout):
    """The compatibility property that keeps the existing suite standing unedited."""
    root, src, dist = checkout
    assert read_ui_build_stamp(dist) is None

    (src / "App.tsx").write_text("export const App = () => 'newer'\n", encoding="utf-8")
    commit_at(root, "2026-03-01T00:00:00+00:00")

    warning = _compute_ui_staleness_warning(dist, src)
    assert warning is not None
    assert "was last rebuilt" in warning, "the old wording, from the old comparison"


def test_a_malformed_stamp_falls_back_rather_than_crashing(checkout):
    """A truncated or hand-mangled stamp must not take the health endpoint with it."""
    _root, src, dist = checkout
    (dist / UI_BUILD_STAMP.name).write_text("{not json", encoding="utf-8")

    assert read_ui_build_stamp(dist) is None
    assert _compute_ui_staleness_warning(dist, src) is None


def test_the_fingerprint_ignores_tests(checkout):
    """Tests are not bundled, so they cannot make the artefact stale."""
    root, src, dist = checkout
    before = ui_source_fingerprint(src)

    tests = src / "__tests__"
    tests.mkdir()
    (tests / "App.test.tsx").write_text("it('works', () => {})\n", encoding="utf-8")
    commit_at(root, "2026-02-01T00:00:00+00:00")

    assert ui_source_fingerprint(src) == before


def test_the_warning_clears_within_the_ttl_without_a_restart(monkeypatch, checkout):
    """`lru_cache(maxsize=1)` meant a real rebuild needed a Hub restart before the warning cleared.

    The TTL is what makes the remedy take effect on a running Hub, which is the only place an
    operator would notice it.
    """
    import hub.main as main

    _root, src, dist = checkout
    monkeypatch.setattr(main, "UI_DIST", dist)
    monkeypatch.setattr(main, "UI_SRC", src)
    _reset_ui_staleness_cache()

    stamp(dist, "stale fingerprint")
    assert _ui_staleness_warning() is not None

    # Re-record it, as a rebuild would — and the cached answer is still the old one.
    stamp(dist, ui_source_fingerprint(src))
    assert _ui_staleness_warning() is not None, "still within the TTL"

    clock = [0.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    _reset_ui_staleness_cache()
    assert _ui_staleness_warning() is None

    clock[0] += main.UI_STALENESS_TTL_SECONDS + 1
    stamp(dist, "stale again")
    assert _ui_staleness_warning() is not None, "the TTL expired and it was re-asked"

    _reset_ui_staleness_cache()


def test_the_committed_bundle_carries_a_parseable_build_stamp():
    """This repository's own bundle. Cheap, unconditional, and catches a dropped stamp.

    Deliberately not a bundle-matches-source check: that would fail on any branch mid-edit. It is
    gated behind `AW_CHECK_UI_BUNDLE=1` below, so CI can enforce it and local work is not blocked.
    """
    from hub.main import UI_DIST

    recorded = read_ui_build_stamp(UI_DIST)
    assert recorded is not None, f"no build stamp in {UI_DIST}; run `make ui`"
    assert recorded.get("src_fingerprint"), "the stamp records no source fingerprint"


@pytest.mark.skipif(
    os.environ.get("AW_CHECK_UI_BUNDLE") != "1",
    reason="set AW_CHECK_UI_BUNDLE=1 to enforce that the committed bundle matches the source",
)
def test_the_committed_bundle_was_built_from_the_committed_source():
    from hub.main import UI_DIST, UI_SRC

    recorded = read_ui_build_stamp(UI_DIST) or {}
    assert recorded.get("src_fingerprint") == ui_source_fingerprint(UI_SRC), (
        "hub/hub/static/ui was built from different source than is present. "
        "Run `cd hub/ui && npm run build && make ui`."
    )
