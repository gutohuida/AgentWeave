"""Drive for F551 part 3 (Tier 0), 2026-10-12: requirement identifiers sort as numbers.

Starts its own Hub from source on :8111 with a fresh database (never :8000 or :8010). No agent turn:
an author holds a seeded running-run credential for the Hub's own agent routes.

  1. an author submits a document of twelve requirements (FR-1 .. FR-12);
  2. the coverage route, whole project and scoped to the document, lists FR-2 before FR-10, and its
     `unserved` list (nothing is linked yet) reads the same order;
  3. a task is created naming FR-1 .. FR-9; the unserved list is then FR-10, FR-11, FR-12 and the
     linked requirements still read in numeric order.

    py -3.11 scripts/drive/d1012_f551_sort.py
"""

import pathlib
import secrets
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8111
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1012-f551sort" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

PATH = "spec/changes/ordered/spec.json"


def seed_runs(pid):
    """A running run for `author`; returns its token."""
    sys.path.insert(0, str(d.REPO / "hub"))
    import os

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{d.DB.as_posix()}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.agent_auth import hash_run_token
    from hub.db.models import Agent, Run

    tokens = {}
    engine = create_engine(f"sqlite:///{d.DB.as_posix()}")
    with Session(engine) as session:
        for name, granted in (("author", False),):
            tokens[name] = "aw_run_" + secrets.token_urlsafe(24)
            session.add(Agent(id="ag-" + secrets.token_hex(4), project_id=pid, name=name,
                              can_accept_evidence=granted))
            session.add(Run(id=f"run-d1012-{name}", project_id=pid, agent=name, status="running",
                            turn_depth=0, capability_token_hash=hash_run_token(tokens[name])))
        session.commit()
    engine.dispose()
    return tokens


def as_agent(token, method, path, body=None):
    saved = d.KEY
    d.KEY = token
    try:
        return d.api(method, path, body)
    finally:
        d.KEY = saved


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# f551 sort\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f551sort"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"

    code, out = d.api("POST", f"{base}/project/documents", {"path": PATH, "title": "Ordered"})
    d.check("0 the document is created", code == 201, f"{code} {out}")
    tokens = seed_runs(pid)
    document = {
        "schema_version": 1, "kind": "change-spec", "title": "Ordered",
        "requirements": [
            {"key": f"req-{n}", "statement": f"It does thing {n}", "modal": "MUST"}
            for n in range(1, 13)
        ],
    }
    code, out = as_agent(tokens["author"], "POST", "/agent-actions/spec/documents",
                         {"path": PATH, "document": document})
    d.check("0 the document is submitted", code == 200, f"{code} {out}")

    natural = [f"FR-{n}" for n in range(1, 13)]
    for label, query in (("project", ""), ("document", f"?document={PATH}")):
        code, out = d.api("GET", f"{base}/project/spec/coverage{query}")
        d.check(f"1 the {label} coverage lists FR-1..FR-12 in numeric order",
                code == 200 and [r["identifier"] for r in out["requirements"]] == natural,
                f"{code} {[r['identifier'] for r in out.get('requirements', [])]}")
        d.check(f"1 the {label} unserved list reads the same order",
                [r["identifier"] for r in out["unserved"]] == natural,
                f"{[r['identifier'] for r in out.get('unserved', [])]}")

    code, out = d.api("POST", f"{base}/tasks",
                      {"title": "Build the early ones",
                       "requirement_ids": ["FR-9", "FR-8", "FR-7", "FR-6", "FR-5", "FR-4", "FR-3",
                                           "FR-2", "FR-1"]})
    d.check("2 a task naming FR-1..FR-9 is created", code in (200, 201), f"{code} {str(out)[:300]}")
    code, out = d.api("GET", f"{base}/project/spec/coverage")
    d.check("2 the unserved list is the three left, FR-10, FR-11, FR-12 in order",
            [r["identifier"] for r in out["unserved"]] == ["FR-10", "FR-11", "FR-12"],
            f"{[r['identifier'] for r in out['unserved']]}")
    tied = [r for r in out["requirements"] if r["linked_task_ids"]]
    d.check("2 the linked requirements still read in numeric order",
            [r["identifier"] for r in tied] == natural[:9], f"{[r['identifier'] for r in tied]}")


if __name__ == "__main__":
    d.drive = drive
    d.main()
