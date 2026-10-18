"""Shared helpers for sweep A's drive scripts (2026-10-18). Loads the e2e harness with sweep A's
own state file, so every call goes to the Hub `e2e.py hub-up sweepa1018 8031` started.

    py -3.11 scripts/drive/s1018_A_lib.py GET /model-catalog      # print full JSON (no 6000 cap)
"""

import importlib.util
import json
import os
import pathlib
import sys

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-sweepA.json")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

P = os.environ.get("AW_P", "proj-7ddd953eccfc")


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def show(method, path, body=None, limit=4000):
    status, res = req(method, path, body)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    print(f"{method} {path} -> {status}\n{text[:limit]}")
    return status, res


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


if __name__ == "__main__":
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show(sys.argv[1], sys.argv[2], body, limit=10**7)
