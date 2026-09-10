"""The gate for `scripts/check_openspec_collisions.py`.

That script warns when two unarchived changes touch the same requirement, and its whole value
is that it *fires*. Its failure mode is going quiet: a parser that stops recognising the delta
format, or a path index read from the wrong position, reports zero collisions -- which is
indistinguishable from a clean corpus and reads like good news. Iteration 10 of the night
window hit exactly that while measuring the archive by hand, and got a confident **0**.

**The fixtures are synthetic**, for the same reason `test_classify_findings.py` gives: the
archive grows every night, so a test that asserted its collision count would fail whenever
somebody archived a change, and the only way to keep it green would be to edit the number
until it stopped meaning anything.

The one exception is `test_the_real_archive_parses_without_orphans`, a structural invariant
with no dependence on content: it asserts that no requirement in the real corpus sits
somewhere the parser silently skips. That is the going-quiet failure, checked against the only
corpus that can actually exhibit it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_openspec_collisions.py"


def _load():
    """Import the script by path -- `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("check_openspec_collisions", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = _load()


def write_change(root: Path, change: str, capability: str, body: str) -> Path:
    """Lay down one `<change>/specs/<capability>/spec.md` under `root`."""
    path = root / change / "specs" / capability / "spec.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip("\n") + "\n", encoding="utf-8")
    return path


def keys(found) -> set[tuple[str, str]]:
    return {key for key, _ in found}


def run(root: Path):
    touched, warnings, files = cc.scan(root)
    return cc.collisions(touched), warnings, files


MODIFIES_SHARED = """
## MODIFIED Requirements

### Requirement: Shared thing
The system SHALL do the shared thing.
"""

ADDS_SHARED = """
## ADDED Requirements

### Requirement: Shared thing
The system SHALL do the shared thing.
"""


# --- the incident ------------------------------------------------------------------------


def test_two_changes_modifying_one_requirement_is_a_silent_revert(tmp_path):
    """The incident R-2 exists for: archiving the second reverted the first, silently."""
    write_change(tmp_path, "one", "cap", MODIFIES_SHARED)
    write_change(tmp_path, "two", "cap", MODIFIES_SHARED)

    found, _, files = run(tmp_path)

    assert files == 2
    assert keys(found) == {("cap", "Shared thing")}
    assert cc.is_silent_revert(found[0][1])


def test_three_changes_modifying_one_requirement_are_all_named(tmp_path):
    """n > 2 is real, not hypothetical.

    `agent-conversation-workspace | Only high-frequency controls remain visible` is MODIFIED by
    three archived changes. A report that assumed pairs would name two of them and hide one.
    """
    for change in ("one", "two", "three"):
        write_change(tmp_path, change, "cap", MODIFIES_SHARED)

    found, _, _ = run(tmp_path)

    _, hits = found[0]
    assert {hit.change for hit in hits} == {"one", "two", "three"}
    assert cc.is_silent_revert(hits)


def test_added_against_modified_collides_but_is_not_a_silent_revert(tmp_path):
    """Order-dependent -- modifying a requirement the other change has not added yet.

    Reported, because the two changes' order is still open, but not ranked with the pairing
    that leaves no trace.
    """
    write_change(tmp_path, "one", "cap", ADDS_SHARED)
    write_change(tmp_path, "two", "cap", MODIFIES_SHARED)

    found, _, _ = run(tmp_path)

    assert keys(found) == {("cap", "Shared thing")}
    assert not cc.is_silent_revert(found[0][1])


def test_silent_reverts_are_reported_before_order_dependent_ones(tmp_path):
    write_change(tmp_path, "one", "cap", ADDS_SHARED + "\n### Requirement: Both modify me\nBody.\n")
    write_change(
        tmp_path,
        "two",
        "cap",
        MODIFIES_SHARED + "\n### Requirement: Both modify me\nBody.\n",
    )
    write_change(
        tmp_path,
        "three",
        "cap",
        "## MODIFIED Requirements\n\n### Requirement: Both modify me\nBody.\n",
    )

    found, _, _ = run(tmp_path)

    assert [key[1] for key in keys([found[0]])] == ["Both modify me"]
    assert cc.is_silent_revert(found[0][1])
    assert not cc.is_silent_revert(found[1][1])


# --- what is NOT a collision -------------------------------------------------------------


def test_one_change_naming_a_requirement_twice_is_its_own_business(tmp_path):
    """A change that both adds and modifies a requirement has decided its own order."""
    write_change(tmp_path, "one", "cap", ADDS_SHARED + "\n" + MODIFIES_SHARED)

    found, _, _ = run(tmp_path)

    assert found == []


def test_the_same_requirement_name_in_two_capabilities_is_two_requirements(tmp_path):
    """The key is (capability, name). Comparing names alone invents collisions."""
    write_change(tmp_path, "one", "cap-a", MODIFIES_SHARED)
    write_change(tmp_path, "two", "cap-b", MODIFIES_SHARED)

    found, _, _ = run(tmp_path)

    assert found == []


def test_a_requirement_inside_a_fence_is_an_example_not_a_requirement(tmp_path):
    """Deltas quote the format they use; a quoted heading is not a block anyone will apply."""
    fenced = """
## MODIFIED Requirements

### Requirement: Real one
Body.

The format looks like this:

```markdown
### Requirement: Shared thing
```
"""
    write_change(tmp_path, "one", "cap", fenced)
    write_change(tmp_path, "two", "cap", MODIFIES_SHARED)

    found, _, _ = run(tmp_path)

    assert found == []


def test_a_line_after_a_closed_fence_is_read_again(tmp_path):
    """The companion to the test above: skipping the fence must not swallow the rest of the file."""
    body = """
## MODIFIED Requirements

```markdown
### Requirement: An example
```

### Requirement: Shared thing
Body.
"""
    write_change(tmp_path, "one", "cap", body)
    write_change(tmp_path, "two", "cap", MODIFIES_SHARED)

    found, _, _ = run(tmp_path)

    assert keys(found) == {("cap", "Shared thing")}


# --- going quiet -------------------------------------------------------------------------


def test_a_requirement_outside_any_section_is_warned_about_not_dropped(tmp_path):
    """A delta the parser cannot read is a delta whose collisions it cannot see."""
    write_change(tmp_path, "one", "cap", "### Requirement: Orphan\nBody.\n")

    _, warnings, _ = run(tmp_path)

    assert len(warnings) == 1
    assert "outside any section" in warnings[0].text


def test_a_requirement_under_an_unrecognised_header_is_warned_about(tmp_path):
    """If openspec grows a fourth section kind, this says so rather than ignoring its contents."""
    write_change(
        tmp_path, "one", "cap", "## RENAMED Requirements\n\n### Requirement: Moved\nBody.\n"
    )

    _, warnings, _ = run(tmp_path)

    assert [w.text.split(":")[0] for w in warnings] == [
        "unrecognised section header",
        "requirement outside any section",
    ]


def test_change_and_capability_are_read_relative_to_the_scan_root(tmp_path):
    """The iteration-10 bug, as a test.

    `<change>/specs/<capability>/spec.md` sits at different absolute depths depending on
    whether the root is `openspec/changes` or `openspec/changes/archive`. Hardcoding either
    set of indices makes the other scan find nothing -- which reads exactly like a clean
    corpus. The same fixture must give the same answer at any nesting depth.
    """
    shallow = tmp_path / "shallow"
    deep = tmp_path / "a" / "b" / "c" / "deep"
    for root in (shallow, deep):
        write_change(root, "one", "cap", MODIFIES_SHARED)
        write_change(root, "two", "cap", MODIFIES_SHARED)

    assert keys(run(shallow)[0]) == keys(run(deep)[0]) == {("cap", "Shared thing")}


def test_archive_is_skipped_as_a_sibling_and_scanned_as_the_root(tmp_path):
    """Both halves matter: the default target excludes history, and history stays reachable."""
    write_change(tmp_path, "one", "cap", MODIFIES_SHARED)
    archive = tmp_path / "archive"
    write_change(archive, "old", "cap", MODIFIES_SHARED)
    write_change(archive, "older", "cap", MODIFIES_SHARED)

    assert run(tmp_path)[2] == 1
    assert keys(run(archive)[0]) == {("cap", "Shared thing")}


# --- exit codes --------------------------------------------------------------------------


def test_exit_codes(tmp_path, capsys):
    clean = tmp_path / "clean"
    write_change(clean, "one", "cap", MODIFIES_SHARED)
    colliding = tmp_path / "colliding"
    write_change(colliding, "one", "cap", MODIFIES_SHARED)
    write_change(colliding, "two", "cap", MODIFIES_SHARED)

    assert cc.main(["--changes-dir", str(clean)]) == 0
    assert cc.main(["--changes-dir", str(colliding)]) == 1
    assert cc.main(["--changes-dir", str(tmp_path / "nope")]) == 2

    out = capsys.readouterr().out
    assert "SILENT REVERT" in out


# --- the real corpus, structurally ---------------------------------------------------------


def test_the_real_archive_parses_without_orphans():
    """No requirement in the corpus sits where the parser would silently skip it.

    Content-independent by construction: it asserts nothing about how many collisions the
    archive holds, only that every requirement in it was seen. A delta written in a shape this
    script cannot read would make the check go quiet, and this is what notices.
    """
    archive = REPO_ROOT / "openspec" / "changes" / "archive"
    _, warnings, files = cc.scan(archive)

    assert files > 0, "the archive should hold delta files; the glob or the layout has moved"
    orphans = [w for w in warnings if "outside any section" in w.text]
    assert orphans == [], f"requirements the collision check cannot see: {orphans}"
