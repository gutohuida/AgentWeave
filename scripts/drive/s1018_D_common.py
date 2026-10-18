"""Sweep D, 2026-10-18: shared client wiring for group D's drive scripts (port 8034).

Reads the Hub record e2e.py wrote to ~/.agentweave/e2e-sweepD.json, fetches the key from
/setup/token, and configures sweep_client. Read-only DB access only. Never :8000 or :8010.
"""

import json
import os
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import sweep_client as sc  # noqa: E402

STATE = pathlib.Path(os.environ.get("AW_E2E_STATE", r"C:/Users/huida/.agentweave/e2e-sweepD.json"))
SCRATCH = pathlib.Path(
    r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave"
    r"\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepD"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
MINE = SCRATCH / "mine.json"


def configure():
    st = json.loads(STATE.read_text(encoding="utf-8"))
    port = str(st["port"])
    assert port not in ("8000", "8010"), port
    sc.CFG["port"] = port
    sc.CFG["db"] = pathlib.Path(st["db"]).as_posix()
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/setup/token", timeout=10) as r:
        sc.CFG["key"] = json.loads(r.read())["api_key"]
    return st


def mine():
    return json.loads(MINE.read_text(encoding="utf-8")) if MINE.is_file() else {}


def save(d):
    cur = mine()
    cur.update(d)
    MINE.write_text(json.dumps(cur, indent=2), encoding="utf-8")


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    print(f"--- {label}: {text[:2500]}", flush=True)


configure()
