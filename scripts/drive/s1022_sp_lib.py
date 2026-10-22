"""Shared helpers for the 2026-10-22 Spec documents x Corpus & folding sweep (scratch Hub :8121,
profile sp1022, projects under testbed/drive1022s). Loads the e2e harness with this drive's own
state file.

    py -3.11 scripts/drive/s1022_sp_lib.py GET /health
"""

import importlib.util
import json
import os
import pathlib
import sys

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-sp1022.json")
os.environ.setdefault("AW_E2E_ROOT", "C:/Users/huida/Documents/projects/AgentWeave/testbed/drive1022s")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

P = os.environ.get("AW_P", "")
B = f"/projects/{P}"
DOCS = f"{B}/project/documents"
HAIKU = "claude-haiku-4-5-20251001"


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def show(method, path, body=None, limit=3000):
    status, res = req(method, path, body)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    print(f"{method} {path} -> {status}\n{text[:limit]}")
    return status, res


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def payload(title, sfx, keys=("alpha", "beta"), extra=None):
    reqs = [{"key": k, "statement": f"The tool MUST handle {k}.", "modal": "MUST"} for k in keys]
    doc = {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "scope": {"in_scope": ["tool"], "non_goals": ["sync"]},
        "requirements": reqs,
        "acceptance_criteria": [
            {"key": f"c-{k}", "requirement": k, "given": "a list", "when": f"{k} runs",
             "then": f"{k} finishes under 1ms", "how_to_check": f"time {k}"} for k in keys
        ],
        "tasks": [{"key": f"t-{k}", "title": f"Build {k} {sfx}", "description": "Do.", "requirements": [k]}
                  for k in keys],
    }
    doc.update(extra or {})
    return doc


if __name__ == "__main__":
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show(sys.argv[1], sys.argv[2], body, limit=20000)
