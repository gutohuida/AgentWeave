"""Reconcile `a-run-claims-only-its-agents-or-nobodys-work` (F450) into the `run-task-binding`
capability document, through the trial Hub (the corpus is Hub-owned; never edit the HTML).

Run from hub/ so `hub.spec_payload` is importable:
  cd hub && AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 ../scripts/drive/reconcile_f450.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

from hub.spec_payload import extract_payload  # noqa: E402

PATH = "spec/capabilities/run-task-binding/spec.html"
REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "a-run-claims-only-its-agents-or-nobodys-work"

payload = extract_payload((REPO / PATH).read_text(encoding="utf-8"))
if any(r["key"] == KEY for r in payload["requirements"]):
    raise SystemExit("already reconciled")
payload["requirements"].append({
    "key": KEY,
    "modal": "SHALL",
    "statement": (
        "An agent run not already bound to a task SHALL be refused a move of that task to "
        "in_progress where the task is assigned to a different agent, naming the assignee and the "
        "operator's remedy and leaving the task, its assignee and the run's binding unchanged; where "
        "the task is unassigned, the claim SHALL record the run's agent as its assignee in the same "
        "transaction; a claim of the run's own agent's task, a bound run, and the operator SHALL "
        "behave as before."
    ),
    "rationale": (
        "Before F450 any idle run bound itself to any task it claimed: a real Haiku beta took alpha's "
        "task to completed while the board still named alpha as its holder."
    ),
})
payload["acceptance_criteria"] += [
    {"key": f"{KEY}-refused", "requirement": KEY,
     "given": "a task assigned to alpha and a run of beta bound to nothing",
     "when": "beta's run moves it to in_progress",
     "then": "403 naming alpha and the operator's remedy; the task stays assigned to alpha with no "
             "transition, and beta's run stays unbound"},
    {"key": f"{KEY}-claim-assigns", "requirement": KEY,
     "given": "an unassigned task", "when": "beta's run claims it",
     "then": "the task is in_progress with assignee beta and beta's run is bound to it"},
    {"key": f"{KEY}-unchanged", "requirement": KEY,
     "given": "a task assigned to beta, and a task assigned to alpha",
     "when": "beta's run claims the first and the operator moves the second to in_progress",
     "then": "both succeed as before"},
]
code, res = api("PUT", f"/projects/{P}/project/documents/{PATH}/content", {"document": payload})
print(code, json.dumps(res)[:400])
