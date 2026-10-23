"""Shared helpers for the 2026-10-23 Permissions & sandbox x Capability plane x Agent environment sweep (scratch Hub :8113,
profile rc1023, projects under testbed/drive1023r). Loads the e2e harness with this drive's own
state file.

    py -3.11 scripts/drive/s1023_rc_lib.py GET /health
"""

import importlib.util
import json
import os
import pathlib
import sys

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-rc1023.json")
os.environ.setdefault("AW_E2E_ROOT", "C:/Users/huida/Documents/projects/AgentWeave/testbed/drive1023r")
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


if __name__ == "__main__":
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show(sys.argv[1], sys.argv[2], body, limit=20000)
