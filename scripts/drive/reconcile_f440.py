"""Reconcile `a-decided-task-withdraws-its-waiting-reviews` (F440) into the `run-task-binding`
capability document, through the trial Hub (the corpus is Hub-owned; never edit the HTML).

Run from hub/ so `hub.spec_payload` is importable:
  cd hub && AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 ../scripts/drive/reconcile_f440.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

from hub.spec_payload import extract_payload  # noqa: E402

PATH = "spec/capabilities/run-task-binding/spec.html"
REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "a-decided-task-withdraws-its-waiting-reviews"

payload = extract_payload((REPO / PATH).read_text(encoding="utf-8"))
if any(r["key"] == KEY for r in payload["requirements"]):
    raise SystemExit("already reconciled")
payload["requirements"].append({
    "key": KEY,
    "modal": "SHALL",
    "statement": (
        "When a task moves to approved, rejected or revision_needed, the system SHALL withdraw, in "
        "the same transaction as the move, every queued inbound entry that asks for a review of that "
        "task, recording the verdict as its reason and announcing each withdrawal; a delivered entry, "
        "an entry naming another task, and a work entry's queued state SHALL be left unchanged."
    ),
    "rationale": (
        "A review of a decided task can only be refused. Before F440 such an entry was delivered, "
        "refused up to the delivery limit and only then given up, and it booked its reviewer meanwhile."
    ),
})
payload["acceptance_criteria"] += [
    {"key": f"{KEY}-land", "requirement": KEY, "given": "a review entry queued for a reviewer mid-turn",
     "when": "the operator lands the task",
     "then": "the entry is withdrawn with the verdict as its reason, a queue_entry_withdrawn event names "
             "it, and after the reviewer's turn ends no delivery of it is attempted"},
    {"key": f"{KEY}-revise", "requirement": KEY,
     "given": "a task under review with a second reviewer's review entry queued",
     "when": "the task is sent back with revision_needed", "then": "the second entry is withdrawn"},
    {"key": f"{KEY}-others", "requirement": KEY,
     "given": "a delivered review entry for the task, a queued review entry for another task, and a "
              "queued work entry for the task",
     "when": "the task is approved",
     "then": "the first two are unchanged and the work entry stays queued with its task released"},
]
code, res = api("PUT", f"/projects/{P}/project/documents/{PATH}/content", {"document": payload})
print(code, json.dumps(res)[:400])
