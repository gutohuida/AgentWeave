"""Reconcile `a-document-names-its-default-reviewer` (F508) into the `agent-flows` capability
document, through the trial Hub (the corpus is Hub-owned; never edit the HTML).

Run from hub/ so `hub.spec_payload` is importable:
  cd hub && AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 ../scripts/drive/reconcile_f508.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

from hub.spec_payload import extract_payload  # noqa: E402

PATH = "spec/capabilities/agent-flows/spec.html"
REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "a-document-names-its-default-reviewer"

payload = extract_payload((REPO / PATH).read_text(encoding="utf-8"))
if any(r["key"] == KEY for r in payload["requirements"]):
    raise SystemExit("already reconciled")
payload["requirements"].append({
    "key": KEY,
    "modal": "SHALL",
    "statement": (
        "A change-spec document's delivery MAY name a default reviewer, and a task whose own entry "
        "names no reviewer SHALL be treated as declaring that one: resolved by the same declared-"
        "reviewer resolution, surfaced and never substituted when it does not resolve, and "
        "overridden by a task's own reviewer. For a flow-delivered document awaiting approval, the "
        "approval bar SHALL state who reviews: the default by name, or any free agent, and SHALL "
        "flag a default that names no open agent."
    ),
    "rationale": (
        "F508: a planner promised the operator a reviewer in prose, no field named it, and a flow "
        "gave the review to a leftover stub agent that sorted first among the free ones."
    ),
})
payload["acceptance_criteria"] += [
    {"key": f"{KEY}-staffs", "requirement": KEY,
     "given": "a flow-delivered document whose delivery names critic and whose tasks name none, "
              "and a free agent sorting before critic",
     "when": "a completed task's review is staffed", "then": "critic reviews it"},
    {"key": f"{KEY}-unresolved", "requirement": KEY,
     "given": "a default reviewer that is archived or not on the roster",
     "when": "a completed task's review is staffed",
     "then": "nobody is staffed; the reason names the document's default reviewer"},
    {"key": f"{KEY}-bar", "requirement": KEY,
     "given": "a proposed flow-delivered document",
     "when": "the operator opens it",
     "then": "the approval bar reads 'Reviewed by @X', 'Reviewed by any free agent', or an amber "
             "line for a default that is no open agent"},
]
code, res = api("PUT", f"/projects/{P}/project/documents/{PATH}/content", {"document": payload})
print(code, json.dumps(res)[:400])
