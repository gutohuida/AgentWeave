"""Shared helpers for the 2026-10-23 Projects sweep (`sweep-projects-sweep`, scratch Hub :8116,
profile pj1023). Loads the e2e harness with this drive's own state file.

    py -3.11 scripts/drive/s1023_pj_lib.py GET /fs/roots
"""

import importlib.util
import json
import os
import pathlib
import sys

os.environ.setdefault(
    "AW_E2E_STATE", "C:/Users/huida/Documents/projects/AgentWeave/testbed/e2e_state_pj1023.json"
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

PA = os.environ.get("AW_PA", "proj-19b3a5f0a902")
PB = os.environ.get("AW_PB", "proj-c29934c5b878")


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def show(method, path, body=None, limit=3000):
    status, res = req(method, path, body)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    print(f"{method} {path} -> {status}\n{text[:limit]}")
    return status, res


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def hub_and_key():
    return e2e.hub(), e2e.key()


if __name__ == "__main__":
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show(sys.argv[1], sys.argv[2], body, limit=20000)
