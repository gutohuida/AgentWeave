"""Shared helpers for sweep B (2026-10-18): spec documents, corpus, evidence, drift.

Every call goes through e2e.py (AW_E2E_STATE must name sweep B's state file)."""

import importlib.util
import json
import os
import pathlib
import sys
import time

assert os.environ.get("AW_E2E_STATE", "").endswith("e2e-sweepB.json"), "set AW_E2E_STATE"
sys.stdout.reconfigure(encoding="utf-8")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

P = "proj-d84cc52b6e7f"
DIR = pathlib.Path(r"C:\Users\huida\Documents\aw-sweepB-1018")
SPEC = f"/projects/{P}/project"
OUT = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepB")
OUT.mkdir(parents=True, exist_ok=True)

LOG = []


def req(method, path, body=None, show=True, cut=900):
    code, data = e2e.request(method, path, body)
    if show:
        text = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
        print(f"--> {method} {path} {('' if body is None else json.dumps(body, ensure_ascii=False)[:300])}")
        print(f"<-- {code} {text[:cut]}")
    LOG.append({"m": method, "p": path, "b": body, "code": code, "data": data})
    return code, data


def rows(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def doc_file(path):
    return json.loads((DIR / path).read_text(encoding="utf-8"))


def base_payload(kind, title, n=2, extra=None):
    p = {
        "schema_version": 1, "kind": kind, "title": title,
        "summary": f"{title}: summary.", "problem": "Touching intervals are not merged.",
        "scope": {"in_scope": ["intervals/core.py"], "non_goals": ["Open intervals"]},
        "requirements": [{"key": f"r{i}", "statement": s, "modal": "MUST"} for i, s in enumerate([
            "Interval.overlaps MUST return true for closed intervals that share an endpoint.",
            "merge MUST combine intervals that touch at a single point.",
            "Interval.length MUST return hi minus lo.",
        ][:n], 1)],
        "acceptance_criteria": [{"key": f"c{i}", "requirement": f"r{i}", "given": "the library",
                                 "when": "the unit tests run", "then": f"requirement r{i} holds",
                                 "how_to_check": "py -3.11 -m unittest discover -s tests",
                                 "checked_by": "agent"} for i in range(1, n + 1)],
        "tasks": [{"key": f"t{i}", "title": f"Satisfy r{i}", "description": f"Make r{i} hold, with a test.",
                   "requirements": [f"r{i}"], "files": ["intervals/core.py"]} for i in range(1, n + 1)],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }
    if extra:
        p.update(extra)
    return p


def save():
    (OUT / f"log_{int(time.time())}.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1, default=str),
                                                    encoding="utf-8")
