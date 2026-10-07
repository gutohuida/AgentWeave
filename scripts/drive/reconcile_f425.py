"""Reconcile `a-read-only-agent-holds-no-task-work` (F425) into the `run-task-binding`
capability document, through the trial Hub (the corpus is Hub-owned; never edit the HTML).

Run from hub/ so `hub.spec_payload` is importable:
  cd hub && AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 ../scripts/drive/reconcile_f425.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

from hub.spec_payload import extract_payload  # noqa: E402

PATH = "spec/capabilities/run-task-binding/spec.html"
REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "a-read-only-agent-holds-no-task-work"

payload = extract_payload((REPO / PATH).read_text(encoding="utf-8"))
if any(r["key"] == KEY for r in payload["requirements"]):
    raise SystemExit("already reconciled")
payload["requirements"].append({
    "key": KEY,
    "modal": "SHALL",
    "statement": (
        "An agent declared read_only SHALL hold no task's work: a turn of it bound to a task's work "
        "SHALL be refused before any workspace is resolved, naming the agent, the task and the "
        "remedy; a task create or update naming it as assignee outside a review status, and its "
        "run's claim of a task, SHALL be refused; and a flow SHALL NOT select it for ordinary work. "
        "Its review turns SHALL be unaffected."
    ),
    "rationale": (
        "A read-only agent gets no task checkout, so before F425 its task-bound turn ran in the "
        "project directory, unsnapshotted: a real Haiku turn wrote NOTES.md into the operator's "
        "checkout."
    ),
})
payload["acceptance_criteria"] += [
    {"key": f"{KEY}-turn", "requirement": KEY,
     "given": "a read_only agent and a task", "when": "the operator triggers it on the task",
     "then": "409 naming the agent, the task and the remedy; no run; the project directory unchanged"},
    {"key": f"{KEY}-review", "requirement": KEY,
     "given": "a completed task with evidence naming a commit",
     "when": "the read_only agent's review of it is dispatched",
     "then": "it runs in the agent's review checkout as before"},
    {"key": f"{KEY}-doors", "requirement": KEY,
     "given": "a read_only agent",
     "when": "a task is created or PATCHed to it outside under_review, or its run claims a task",
     "then": "422 for the create and PATCH, 403 for the claim; nothing changes"},
    {"key": f"{KEY}-flow", "requirement": KEY,
     "given": "a flow with a read_only agent and a writing agent free, or a read_only job agent",
     "when": "it fires on a pending task", "then": "the task goes to the writing agent"},
]
code, res = api("PUT", f"/projects/{P}/project/documents/{PATH}/content", {"document": payload})
print(code, json.dumps(res)[:400])
