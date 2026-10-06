"""Task `files` and the unordered-overlap warning (slice: same-file tasks build in order)."""

import subprocess
from pathlib import Path

import pytest

from hub.spec_completeness import check, overlap_warnings, paths_overlap
from hub.spec_payload import SCHEMA_VERSION, PayloadError, payload_to_dict, validate_payload


def _complete(tasks):
    return validate_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "change-spec",
            "title": "A change",
            "requirements": [{"key": "alpha", "statement": "It responds", "modal": "MUST"}],
            "acceptance_criteria": [
                {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
            ],
            "tasks": tasks,
            "scope": {"in_scope": ["x"], "non_goals": ["y"]},
            "delivery": {"mode": "none"},
        }
    )


def _tasks(*specs):
    return [
        {"key": key, "description": "work", "requirements": ["alpha"], **extra}
        for key, extra in specs
    ]


def _overlap(*specs):
    return overlap_warnings(_complete(_tasks(*specs)))


def test_files_are_accepted_and_survive_storage():
    payload = _complete(_tasks(("t1", {"files": ["a/b.py", "docs"]})))
    assert payload_to_dict(payload)["tasks"][0]["files"] == ["a/b.py", "docs"]


def test_a_task_without_files_stores_none_so_old_documents_do_not_change():
    assert "files" not in payload_to_dict(_complete(_tasks(("t1", {}))))["tasks"][0]


@pytest.mark.parametrize("bad", ["", "  ", "/abs/x", "C:\\x\\y", "\\x"])
def test_an_empty_or_absolute_path_is_refused_naming_the_task(bad):
    with pytest.raises(PayloadError) as exc:
        _complete(_tasks(("task-one", {"files": [bad]})))
    assert "task-one" in str(exc.value)
    assert exc.value.field == "tasks[0].files[0]"


def test_a_directory_covers_the_paths_beneath_it():
    assert paths_overlap("hub/hub", "hub/hub/scheduler.py")
    assert paths_overlap("hub/hub/scheduler.py", "hub/hub/")
    assert paths_overlap("hub/hub", "hub/hubris.py") is None


def test_unordered_overlap_names_both_tasks_and_the_path_without_blocking():
    tasks = _tasks(
        ("a", {"files": ["hub/hub/mcp_server.py"]}), ("b", {"files": ["hub/hub/mcp_server.py"]})
    )
    found = overlap_warnings(_complete(tasks))
    assert len(found) == 1
    assert "'a'" in found[0].message and "'b'" in found[0].message
    assert "hub/hub/mcp_server.py" in found[0].message
    assert "unordered_file_overlap" not in {f.code for f in check(_complete(tasks))}


def test_an_ordered_pair_is_silent_directly_and_transitively():
    both = {"files": ["x.py"]}
    assert not _overlap(("a", both), ("b", {**both, "depends_on": ["a"]}))
    assert not _overlap(
        ("a", both), ("m", {"depends_on": ["a"]}), ("b", {**both, "depends_on": ["m"]})
    )


def test_tasks_without_files_and_imported_entries_are_never_named():
    imported = {
        "key": "imp",
        "from": {"document": "spec/changes/x/spec.html", "key": "k"},
        "files": ["x.py"],
    }
    tasks = _tasks(("a", {"files": ["x.py"]}), ("b", {})) + [imported]
    assert overlap_warnings(_complete(tasks)) == []


def test_the_slice_adds_no_migration():
    versions = Path(__file__).resolve().parents[1] / "hub" / "migrations" / "versions"
    diff = subprocess.run(
        ["git", "diff", "--name-only", "master", "--", str(versions)],
        capture_output=True,
        text=True,
        cwd=versions,
    )
    if diff.returncode != 0:
        pytest.skip("master is not resolvable here")
    assert diff.stdout.strip() == ""
