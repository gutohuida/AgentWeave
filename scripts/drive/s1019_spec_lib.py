"""Helpers shared by the 2026-10-19 spec sweep's follow-up drives (s1019_spec_p2.py, _ui.py)."""

import json
import os
import pathlib
import secrets
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from e2e import request  # noqa: E402,F401

HUB = e2e.hub() + "/api/v1"
DB = json.loads(e2e.STATE.read_text())["db"]


def say(label, ok, detail=""):
    print(("HELD " if ok else "ODD  ") + label + (f"\n     {detail}" if detail else ""))


def show(label, st, out):
    print(f"  {label}: {st} {json.dumps(out, ensure_ascii=False)[:500]}")


def seed_run(project, name, run_id, task_id=None):
    """A running run for `name`, optionally bound to a task, and its token (labelled: not a turn)."""
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + DB.replace("\\", "/")
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "hub"))
    from hub.agent_auth import hash_run_token

    token = "aw_run_" + secrets.token_urlsafe(24)
    db = sqlite3.connect(DB)
    cols = {c[1] for c in db.execute("pragma table_info(runs)")}
    row = {"id": run_id, "project_id": project, "agent": name, "status": "running", "turn_depth": 0,
           "capability_token_hash": hash_run_token(token)}
    if task_id:
        row["task_id"] = task_id
    for extra in ("created_at", "started_at", "updated_at"):
        if extra in cols:
            row[extra] = "2026-10-19T09:00:00"
    db.execute(f"insert into runs ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
    db.commit()
    db.close()
    return token


def agent(token, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HUB + "/agent-actions" + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw or b"null")
        except ValueError:
            return exc.code, raw[:300]


def task(project, tid):
    st, out = request("GET", f"/projects/{project}/tasks/{tid}")
    return out if st == 200 else {"_err": (st, out)}


def payload(title, sfx, keys=("alpha", "beta", "gamma", "delta")):
    reqs = [{"key": k, "statement": f"The tool MUST handle {k}.", "modal": "MUST"} for k in keys]
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "scope": {"in_scope": ["tool"], "non_goals": ["sync"]},
        "requirements": reqs,
        "acceptance_criteria": [
            {"key": f"c-{k}", "requirement": k, "given": "a list", "when": f"{k} runs",
             "then": f"{k} finishes under 1ms", "how_to_check": f"time {k}"} for k in keys
        ],
        "tasks": [{"key": f"t-{k}", "title": f"Build {k} {sfx}", "description": "Do.", "requirements": [k]}
                  for k in keys],
        "delivery": {"mode": "none"},
    }
