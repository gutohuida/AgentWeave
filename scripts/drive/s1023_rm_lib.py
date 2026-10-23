"""Shared helpers for the 2026-10-23 Runners & models drive (scratch Hub :8117, profile rm1023).

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_rm_lib.py GET /model-catalog
"""

import importlib.util
import json
import os
import pathlib
import sys

os.environ.setdefault(
    "AW_E2E_STATE",
    "C:/Users/huida/Documents/projects/AgentWeave/testbed/e2e_state_rm1023.json",
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

PA = os.environ.get("AW_PA", "proj-8717fc708877")
PB = os.environ.get("AW_PB", "proj-4a4980f52a59")
HAIKU = "claude-haiku-4-5-20251001"


def B(p=None):
    return f"/projects/{p or PA}"


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def show(label, method, path, body=None, limit=1500):
    status, res = req(method, path, body)
    text = json.dumps(res, ensure_ascii=False)
    print(f"[{label}] {method} {path} {json.dumps(body) if body is not None else ''} -> {status}\n   {text[:limit]}")
    return status, res


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


if __name__ == "__main__":
    m, p = sys.argv[1], sys.argv[2]
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show("cli", m, p, body, limit=20000)
