"""Day sweep 2026-10-20: Knowledge vault x Manager jobs x CLI & lifecycle.

Drives a scratch Hub (never :8000 or :8010) through its real routes, vault-by-path first
(vault-1019): `POST /vault/paths` from the operator, `vault_add` from an agent, and the CLI's
`agentweave vault add`.

  L. a folder holding a junction back to itself: how many rows, and does it end;
  B. a big folder (past MAX_BATCH_FILES): how long the refusal takes;
  D. the Vault tab's view of what the batch added (the map, an entry's opening).

Usage (AW_E2E_STATE names the hub-up record):
  py -3.11 scripts/drive/s1020_vault.py <project-id> [steps, default L,B]
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("e2e", ROOT / ".claude/skills/e2e-loop/e2e.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)  # type: ignore[union-attr]

EDGE = pathlib.Path.home() / "Documents" / "vault1020-edge"


def add(project, paths, **extra):
    body = {"paths": [str(p) for p in paths], "distil": False, **extra}
    started = time.time()
    status, answer = e2e.request("POST", f"/projects/{project}/vault/paths", body, timeout=900)
    return status, answer, time.time() - started


def step_l(project):
    status, answer, took = add(project, [EDGE / "loop"])
    rows = answer.get("results", []) if isinstance(answer, dict) else []
    print(f"L: {status} in {took:.1f}s, {len(rows)} rows, counts {answer.get('counts')}")
    names = sorted({r.get("path") for r in rows})
    print("   distinct paths:", names)


def step_b(project, folder):
    status, answer, took = add(project, [folder])
    detail = answer.get("detail") if isinstance(answer, dict) else answer
    print(f"B: {folder} -> {status} in {took:.1f}s: {str(detail)[:300]}")


def step_d(project):
    status, vmap = e2e.request("GET", f"/projects/{project}/vault/map")
    print("D: map", status, str(vmap)[:1500])


if __name__ == "__main__":
    project = sys.argv[1]
    steps = (sys.argv[2] if len(sys.argv) > 2 else "L,B").split(",")
    for step in steps:
        if step == "L":
            step_l(project)
        elif step.startswith("B"):
            step_b(project, step[2:] or str(ROOT / "hub" / "ui" / "node_modules"))
        elif step == "D":
            step_d(project)
