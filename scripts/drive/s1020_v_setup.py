"""2026-10-20 sweep, evidence x drift: the project's files, a three-requirement change approved
into tasks, and two Haiku agents (builder; checker, granted evidence decisions).

  AW_E2E_STATE=... py -3.11 scripts/drive/s1020_v_setup.py <project-id> <project-dir>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import commit_file, memo, request, show  # noqa: E402

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
BASE = f"/projects/{P}/project"
HAIKU = "claude-haiku-4-5-20251001"

commit_file(DIR, "todo/__init__.py", "", "pkg")
commit_file(DIR, "todo/items.py", "ITEMS = [('milk', 3), ('bread', 1), ('eggs', 2)]\n\n\ndef names():\n    return [n for n, _ in ITEMS]\n", "items")
commit_file(DIR, "todo/total.py", "from .items import ITEMS\n\n\ndef total():\n    return sum(q for _, q in ITEMS)\n", "total")
commit_file(DIR, "README.md", "# todo\n", "readme")

st, rn = request("POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
show("runner", st, rn)
for name in ("builder", "checker"):
    st, out = request("POST", f"/projects/{P}/agents", {"name": name, "runner_id": rn["id"]})
    show(f"agent {name}", st, {k: out.get(k) for k in ("name", "runner_id")} if isinstance(out, dict) else out)
st, out = request("PATCH", f"/projects/{P}/agents/checker", {"can_accept_evidence": True})
show("grant checker evidence decisions", st, {"can_accept_evidence": out.get("can_accept_evidence")} if isinstance(out, dict) else out)

DOC = "spec/changes/todo-sort/spec.json"
reqs = [
    {"key": "sorted", "statement": "names() MUST return the item names sorted alphabetically.", "modal": "MUST"},
    {"key": "count", "statement": "The package MUST offer count() returning how many items there are.", "modal": "MUST"},
    {"key": "total", "statement": "total() MUST return the sum of the quantities.", "modal": "MUST"},
]
doc = {
    "schema_version": 1, "kind": "change-spec", "title": "Todo sort and count",
    "scope": {"in_scope": ["todo package"], "non_goals": ["persistence"]},
    "requirements": reqs,
    "acceptance_criteria": [
        {"key": "c-sorted", "requirement": "sorted", "given": "the three items", "when": "names() runs",
         "then": "it returns ['bread', 'eggs', 'milk']", "how_to_check": "py -3.11 -c \"from todo.items import names; print(names())\""},
        {"key": "c-count", "requirement": "count", "given": "the three items", "when": "count() runs",
         "then": "it returns 3", "how_to_check": "py -3.11 -c \"from todo.items import count; print(count())\""},
        {"key": "c-total", "requirement": "total", "given": "the three items", "when": "total() runs",
         "then": "it returns 6", "how_to_check": "py -3.11 -c \"from todo.total import total; print(total())\""},
    ],
    "tasks": [
        {"key": "t-sorted", "title": "Sort names", "description": "Make names() sorted.", "requirements": ["sorted"]},
        {"key": "t-count", "title": "Add count()", "description": "Add count() to todo/items.py.", "requirements": ["count"]},
        {"key": "t-total", "title": "Check total()", "description": "total() exists; prove it.", "requirements": ["total"]},
    ],
    "delivery": {"mode": "none"},
}
request("POST", f"{BASE}/documents", {"path": DOC, "title": "Todo sort and count"})
st, out = request("PUT", f"{BASE}/documents/{DOC}/content", {"document": doc})
show("write", st, {k: out.get(k) for k in ("identifiers", "blocking")} if isinstance(out, dict) else out)
ids = out.get("identifiers") or {}
request("POST", f"{BASE}/documents/close-exploration?path={DOC}")
request("POST", f"{BASE}/documents/propose?path={DOC}")
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "drive", "approve_anyway": True})
show("approve anyway", st, {"phase": out.get("phase")} if isinstance(out, dict) else out)
st, tasks = request("GET", f"/projects/{P}/tasks")
T = {t["spec_task_key"]: t["id"] for t in tasks["tasks"] if t.get("spec_task_key")}
print("tasks:", T)
print(json.dumps(memo(project=P, dir=str(DIR), doc=DOC, ids=ids, tasks=T, doc_payload=doc)["ids"]))
