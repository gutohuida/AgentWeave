"""Acceptance drive for F592 + F609 (fix-D1): a deleted project stays deleted.

Before: `DELETE /projects/{id}` left the private vault under the Hub's own folder (F592), and
reopening the folder adopted the same id from the marker, serving the deleted private source again
(F609). After: a delete that asks (`remove_private=true`) removes the private entries, the project's
directory is untouched, and the reopened folder is a new project with a new id that sees no private
source.

  py -3.11 scripts/drive/d1015_f592_deleted_project_stays_deleted.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). No agent turns. Exit 1 when any check
fails.
"""

import importlib.util
import json
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def add_source(project, name, visibility):
    return e2e.call(
        "POST",
        f"/projects/{project}/vault/sources",
        {"name": name, "type": "note", "content": f"{name} text", "visibility": visibility},
    )["id"]


def main(name):
    project = e2e.cmd_setup(name)
    directory = pathlib.Path(e2e.call("GET", f"/projects/{project}")["working_directory"])
    private = pathlib.Path(
        e2e.call("GET", f"/projects/{project}/vault/settings")["effective_private_location"]
    )
    secret = add_source(project, "secret", "private")
    add_source(project, "shared", "tracked")
    check("the private source is written", private.is_dir() and any(private.rglob("*")), str(private))

    status, res = e2e.request("DELETE", f"/projects/{project}?remove_private=true")
    check("the delete answers 204", status == 204, f"{status} {res}")
    check("the private entries are removed", not private.exists(), str(private))
    marker = directory / ".agentweave" / "project.json"
    check("the project's directory and marker are untouched", marker.is_file(), str(marker))
    check(
        "the tracked vault files stay in the project",
        (directory / "knowledge").is_dir(),
        str(directory / "knowledge"),
    )

    reopened = e2e.call("POST", "/projects/open", {"path": str(directory)})["id"]
    check("the reopened folder is a new project", reopened != project, f"{project} -> {reopened}")
    named = json.loads(marker.read_text(encoding="utf-8")).get("project_id")
    check("the marker names the new project", named == reopened, str(named))
    # The private entry's stub under knowledge/ is a tracked project file (a delete never touches
    # those); what must not come back is its text, which was the deleted project's.
    status, entry = e2e.request("GET", f"/projects/{reopened}/vault/entries/{secret}")
    text = (entry or {}).get("content") if isinstance(entry, dict) else entry
    check("the deleted private text is not served", status == 200 and text is None, f"{status} {text!r}")
    check(
        "the entry says its text is unavailable",
        isinstance(entry, dict) and entry.get("available") is False,
        str(entry)[:200],
    )
    return reopened


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
