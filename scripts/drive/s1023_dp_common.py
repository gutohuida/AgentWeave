"""Shared setup for the 2026-10-23 Dependencies sweep drives (scratch Hub :8161, profile dp1023).

Reads the Hub record e2e.py hub-up wrote (AW_E2E_STATE) and points sweep_client at it.
"""

import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import sweep_client as sc  # noqa: E402

STATE = pathlib.Path(
    os.environ.get("AW_E2E_STATE") or "C:/Users/huida/.agentweave/e2e-s1023-dp.json"
)
REC = json.loads(STATE.read_text(encoding="utf-8"))
if str(REC["port"]) in ("8000", "8010"):
    raise SystemExit("refusing the operator's Hub")
sc.CFG["port"] = str(REC["port"])
sc.CFG["db"] = REC["db"]
with urllib.request.urlopen(sc.hub() + "/api/v1/setup/token", timeout=10) as r:
    sc.CFG["key"] = json.loads(r.read())["api_key"]

PROJECT = os.environ.get("DP_PROJECT", "proj-f68af439d5d3")
BASE = f"/projects/{PROJECT}"


def q(path):
    return urllib.parse.quote(path, safe="")


def show(label, code, body, n=1500):
    text = json.dumps(body, indent=1, ensure_ascii=False) if not isinstance(body, str) else body
    print(f"--- {label}: {code}\n{text[:n]}")


def doc_route(action, path, extra=""):
    return f"{BASE}/project/documents/{action}?path={urllib.parse.quote(path)}{extra}"


def make_doc(title, tasks, requirements=None, delivery=None):
    """Create a document and write a valid change payload; returns (path, put response)."""
    code, doc = sc.api("POST", f"{BASE}/project/documents", {"title": title})
    assert code in (200, 201), (code, doc)
    path = doc["path"]
    reqs = requirements or [
        {"key": f"r{i}", "statement": f"The library MUST provide behaviour {i}.", "modal": "MUST"}
        for i in range(1, len(tasks) + 1)
    ]
    payload = {
        "schema_version": 1,
        "kind": "change-spec",
        "title": title,
        "summary": "Dependencies sweep fixture.",
        "problem": "Exercise task ordering.",
        "requirements": reqs,
        "acceptance_criteria": [
            {"key": f"a-{r['key']}", "requirement": r["key"], "given": "the lib",
             "when": "called", "then": "it answers"}
            for r in reqs
        ],
        "tasks": tasks,
        "scope": {"in_scope": ["the lib"], "non_goals": ["anything else"]},
        "evidence": {"checked": ["nothing yet"], "limits": ["fixture"]},
        "open_questions": [],
        "delivery": delivery or {"mode": "none"},
    }
    code, res = sc.api("PUT", f"{BASE}/project/documents/{q(path)}/content", {"document": payload})
    return path, code, res, payload
