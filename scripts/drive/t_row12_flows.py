"""Row 12 FLOWS -- a flow on an approved document: parallel firing, and a reviewer
resolved for finished work.

Never reached by any previous sweep. Drives the real surface: document -> approve ->
flow -> manual firing -> real Haiku turns -> review dispatch.

Run:  AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 -u t_row12_flows.py
"""

import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
BASE = f"/projects/{P}/project"


def step(label, method, path, body=None, expect=None, show=False, limit=900):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    print(f"  {label}: {code}{'' if ok else '   <-- UNEXPECTED'}")
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = detail.get("message")
    if isinstance(detail, str):
        print(f"      refusal: {detail[:300]}")
    elif show or not ok:
        blob = json.dumps(out, default=str, indent=1)[:limit]
        print("      " + blob.replace(chr(10), chr(10) + "      "))
    return code, out


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


PAYLOAD = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "calc.py grows a power and a modulo",
    "summary": "Two independent additions to the calculator, so a flow has something to run "
    "in parallel and something to review afterwards.",
    "problem": "calc.py has add and sub and nothing else.",
    "scope": {"in_scope": ["calc.py"], "non_goals": ["tests", "packaging"]},
    "requirements": [
        {
            "key": "power",
            "statement": "calc.py SHALL offer a power(a, b) returning a raised to b.",
            "modal": "SHALL",
            "rationale": "The calculator is missing exponentiation.",
        },
        {
            "key": "modulo",
            "statement": "calc.py SHALL offer a modulo(a, b) returning the remainder of a / b.",
            "modal": "SHALL",
            "rationale": "The calculator is missing remainder.",
        },
    ],
    "acceptance_criteria": [
        {
            "key": "power-works",
            "requirement": "power",
            "given": "calc.py after the change",
            "when": "power(2, 3) is called",
            "then": "it returns 8",
        },
        {
            "key": "modulo-works",
            "requirement": "modulo",
            "given": "calc.py after the change",
            "when": "modulo(7, 3) is called",
            "then": "it returns 1",
        },
    ],
    "tasks": [
        {
            "key": "add-power",
            "title": "Add power(a, b) to calc.py",
            "description": "Append a function power(a, b) returning a ** b to calc.py, in the "
            "same style as add/sub. Change nothing else. Do not run git.",
            "requirements": ["power"],
        },
        {
            "key": "add-modulo",
            "title": "Add modulo(a, b) to calc.py",
            "description": "Append a function modulo(a, b) returning a % b to calc.py, in the "
            "same style as add/sub. Change nothing else. Do not run git.",
            "requirements": ["modulo"],
        },
    ],
    "design": "Two one-line functions, independent of each other.",
    "lifecycle": "One-off change.",
}


def board():
    c, t = api("GET", f"/projects/{P}/tasks")
    return t if isinstance(t, list) else t.get("tasks", [])


def agents():
    c, a = api("GET", f"/projects/{P}/agents")
    return {x["name"]: x["status"] for x in a}


def show_board(label):
    print(f"  --- board ({label})")
    for t in board():
        print(
            f"      {t['id']}  {t['title'][:44]:<44} {t['status']:<14} "
            f"assignee={t.get('assignee')}"
        )
    print(f"      agents: {agents()}")


def settle(rounds=30, gap=6):
    for i in range(rounds):
        time.sleep(gap)
        st = agents()
        rows = board()
        busy = [n for n, s in st.items() if s not in ("idle", "offline", "error")]
        print(
            f"      t+{(i + 1) * gap:>3}s busy={busy} "
            f"statuses={[(t['status'], t.get('assignee')) for t in rows]}"
        )
        if i >= 2 and not busy:
            return
    print("      (did not settle)")


def main():
    head("A. An approved document with two independent tasks")
    c, doc = step(
        "create document", "POST", f"{BASE}/documents",
        {"title": PAYLOAD["title"]}, expect=(200, 201),
    )
    path = doc["path"]
    doc_id = doc.get("id")
    q = urllib.parse.quote(path, safe="")
    print(f"      path={path}  id={doc_id}")

    step("write content", "PUT", f"{BASE}/documents/{q}/content",
         {"document": PAYLOAD}, expect=(200, 201))
    step("close exploration", "POST", f"{BASE}/documents/close-exploration?path={q}",
         {"reason": "row 12"}, expect=(200, 201))
    step("propose", "POST", f"{BASE}/documents/propose?path={q}",
         {"reason": "row 12"}, expect=(200, 201))

    head("B. Create the flow BEFORE approval, so materialised tasks land in its queue")
    c, job = step(
        "create flow", "POST", f"/projects/{P}/jobs",
        {
            "name": "row12-flow",
            "agent": "alpha",
            "message": "Work the task you have been given. Keep the edit minimal.",
            "cron": "0 4 * * *",
            "purpose": "Decompose the calc.py change document and get its two tasks done.",
            "spec_document_id": doc_id,
            "stop_when_queue_empties": True,
            "enabled": True,
        },
        expect=(200, 201), show=True, limit=1600,
    )
    if c >= 300:
        return
    job_id = job["id"]
    print(f"      JOB={job_id}")

    try:
        head("C. Approve the document -- do the tasks materialise into the flow's queue?")
        step("approve", "POST", f"{BASE}/documents/phase?path={q}&to=approved",
             {"reason": "row 12"}, expect=(200, 201))
        time.sleep(2)
        show_board("after approval")
        step("loop detail", "GET", f"/projects/{P}/loops/{job_id}", expect=200,
             show=True, limit=2500)

        head("D. Fire the flow by hand -- does it start BOTH tasks in parallel?")
        step("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {},
             expect=(200, 201), show=True)
        settle()
        show_board("after firing 1")
        step("job history", "GET", f"/projects/{P}/jobs/{job_id}/history", expect=200,
             show=True, limit=2500)

        head("E. Fire again -- finished work should be offered to a NON-author reviewer")
        step("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {},
             expect=(200, 201), show=True)
        settle()
        show_board("after firing 2")
        step("job history", "GET", f"/projects/{P}/jobs/{job_id}/history", expect=200,
             show=True, limit=3000)
        step("loop detail", "GET", f"/projects/{P}/loops/{job_id}", expect=200,
             show=True, limit=3000)
    finally:
        head("Z. LEAVE NO JOB ENABLED")
        step("disable", "PATCH", f"/projects/{P}/jobs/{job_id}", {"enabled": False})
        step("archive", "POST", f"/projects/{P}/jobs/{job_id}/archive", {})
        step("jobs now", "GET", f"/projects/{P}/jobs", expect=200, show=True, limit=1500)


if __name__ == "__main__":
    main()
