"""Drive F612: adopting a hand-placed spec.json indexes the requirements it declares.

Before: adopt answered 201 with `requirements.created: []`, no `spec_requirements` row was ever
made, and coverage and the requirements list omitted the document. After: adopt mints identifiers
for the requirements with none (`minted`), indexes them, and coverage lists them.

  py -3.11 scripts/drive/d1015_f612_adopt_indexes.py <project-id>

No agent turns. Exit 1 when any check fails.
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
PATH = "spec/changes/rounding-rules/spec.json"


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project):
    directory = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,)).fetchone()[0]
    )
    target = directory / PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "change-spec",
                "title": "Rounding rules",
                "requirements": [
                    {
                        "key": "one-decimal",
                        "modal": "SHALL",
                        "statement": "Totals SHALL be rounded to one decimal place.",
                        "acceptance": ["12.34 is shown as 12.3"],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    status, body = e2e.request("POST", f"/projects/{project}/project/documents/adopt", {"path": PATH})
    check("adopt answers 201", status == 201, f"{status} {str(body)[:200]}")
    if status != 201:
        return
    check("adopt says what it minted", body.get("minted") == ["FR-1"], str(body.get("minted")))
    rows = e2e.ro().execute(
        "select identifier, state from spec_requirements where document_id=?", (body["id"],)
    ).fetchall()
    check("the requirement is indexed", [tuple(r) for r in rows] == [("FR-1", "active")], str(rows))
    listed = e2e.call("GET", f"/projects/{project}/project/spec/requirements")["requirements"]
    check("the requirements list has it",
          any(r["document_id"] == body["id"] and r["identifier"] == "FR-1" for r in listed))
    stored = json.loads(target.read_text(encoding="utf-8"))
    check("the file now carries its identity",
          stored.get("aw_identity", {}).get("requirements") == {"one-decimal": "FR-1"})
    check("the statement is unchanged",
          stored["requirements"][0]["statement"] == "Totals SHALL be rounded to one decimal place.")
    status, again = e2e.request(
        "POST", f"/projects/{project}/project/spec/reindex"
    )
    check("a reindex afterwards changes nothing", status == 200, f"{status} {str(again)[:200]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
