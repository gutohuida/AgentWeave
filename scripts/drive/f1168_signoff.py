"""F1168: drive acceptance through the trial Hub; no model calls.

The fixture seeds a credential-bearing Run and an approved task's historical integration,
after really merging its branch. Recording and deciding evidence use the HTTP routes.
Only the trial profile and ports 8010/8011 are allowed. Keeps its fixture for inspection.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, choices=(8010, 8011), default=8011)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    profile = Path.home() / ".agentweave/hub/profiles/trial"
    database = profile / "agentweave.db"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + database.as_posix()
    sys.path.insert(0, str(repo / "hub"))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.agent_auth import hash_run_token
    from hub.db.models import Agent, Run, Task, TaskIntegration

    operator_key = (profile / "bootstrap-key.txt").read_text().strip()
    hub = f"http://127.0.0.1:{args.port}/api/v1"

    def api(method, path, body=None, token=operator_key):
        request = urllib.request.Request(
            hub + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise AssertionError(f"{method} {path}: {exc.code} {exc.read().decode()}") from exc

    suffix = secrets.token_hex(4)
    root = Path.home() / "Documents" / f"aw-f1168-{suffix}"
    root.mkdir(parents=True)

    def git(*argv, check=True):
        return subprocess.run(["git", *argv], cwd=root, check=check, capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "drive@example.invalid")
    git("config", "user.name", "F1168 drive")
    (root / "conflict.txt").write_text("base\n")
    git("add", "conflict.txt")
    git("commit", "-qm", "base")
    project = api("POST", "/projects/open", {"path": str(root)})
    pid = project.get("id") or project["project"]["id"]
    base = f"/projects/{pid}"
    api("PUT", base + "/settings", {"main_branch": "main"})
    doc = api("POST", base + "/project/documents", {"title": "F1168 fixture"})
    path = doc["path"]
    api(
        "PUT",
        base + f"/project/documents/{path}/content",
        {
            "document": {
                "schema_version": 1,
                "kind": "change-spec",
                "title": "F1168 fixture",
                "requirements": [
                    {"key": "safe", "statement": "Signoffs merge nothing", "modal": "MUST"}
                ],
                "delivery": {"mode": "none"},
            }
        },
    )
    task = api("POST", base + "/tasks", {"title": "Already landed", "requirement_ids": ["FR-1"]})
    tid = task["id"]
    branch = f"agentweave/task/{tid}"
    git("checkout", "-qb", branch)
    (root / "own.txt").write_text("landed task work\n")
    git("add", "own.txt")
    git("commit", "-qm", "task work")
    own = git("rev-parse", "HEAD").stdout.strip()
    git("checkout", "-q", "main")
    git("merge", "--no-ff", "-qm", "landed task", branch)
    merged = git("rev-parse", "HEAD").stdout.strip()
    git("checkout", "-qb", "agentweave/signoff")
    (root / "conflict.txt").write_text("unreviewed recorder work\n")
    git("add", "conflict.txt")
    git("commit", "-qm", "foreign conflicting work")
    foreign = git("rev-parse", "HEAD").stdout.strip()
    git("checkout", "-q", "main")
    (root / "conflict.txt").write_text("main work\n")
    git("add", "conflict.txt")
    git("commit", "-qm", "main changes")
    assert git("merge-tree", "--write-tree", "main", foreign, check=False).returncode == 1
    # The recorder actually observes the conflicting branch, via a separate worktree.
    recorder = root / "recorder"
    git("worktree", "add", "-q", str(recorder), "agentweave/signoff")
    run_id = f"run-f1168-{suffix}"
    token = "aw_run_" + secrets.token_urlsafe(24)
    engine = create_engine("sqlite:///" + database.as_posix())
    with Session(engine) as session:
        session.add(Agent(id=f"ag-f1168-{suffix}", project_id=pid, name="signoff"))
        session.add(
            Run(
                id=run_id,
                project_id=pid,
                agent="signoff",
                status="running",
                turn_depth=0,
                workspace_dir=str(recorder),
                capability_token_hash=hash_run_token(token),
            )
        )
        session.get(Task, tid).status = "approved"
        session.add(
            TaskIntegration(
                id=f"tint-f1168-{suffix}",
                project_id=pid,
                task_id=tid,
                commit_sha=own,
                source_branch=branch,
                target_branch="main",
                outcome="merged",
                merged_sha=merged,
                actor_kind="operator",
            )
        )
        session.commit()
    evidence = api(
        "POST",
        "/agent-actions/spec/evidence",
        {
            "identifier": "FR-1",
            "document": path,
            "kind": "operator_signoff",
            "locator": "Operator message to Architect",
            "summary": "operator agreed",
        },
        token,
    )
    assert evidence["footprint"] is None, evidence
    with Session(engine) as session:
        session.get(Run, run_id).status = "completed"
        session.commit()
    engine.dispose()
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as db:
        before = db.execute(
            "select count(*) from task_landings where project_id=?", (pid,)
        ).fetchone()[0]
    api(
        "POST", base + f"/project/spec/evidence/{evidence['id']}/decision", {"decision": "accepted"}
    )
    observed = api("GET", base + f"/tasks/{tid}")
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as db:
        after = db.execute(
            "select count(*) from task_landings where project_id=?", (pid,)
        ).fetchone()[0]
        state, evidence_task = db.execute(
            "select review_state, task_id from requirement_evidence where id=?", (evidence["id"],)
        ).fetchone()
    assert observed["status"] == "approved", observed
    assert after == before == 0, (before, after)
    assert state == "accepted", state
    assert evidence_task is None, evidence_task
    assert git("merge-base", "--is-ancestor", foreign, "main", check=False).returncode == 1
    print(f"PASS trial :{args.port}; project={pid}; task={tid}; evidence={evidence['id']}")
    print("PASS recorder branch conflicts with main; own task branch already landed")
    print("PASS signoff footprint=null; task_id=null; operator decision=accepted")
    print(
        f"PASS task=approved; task_landings before={before} after={after}; foreign commit absent from main"
    )
    print(f"Fixture retained: {root}")


if __name__ == "__main__":
    main()
