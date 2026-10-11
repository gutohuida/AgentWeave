"""Drive for F551 part 1 (Tier 0), 2026-10-12: rejecting evidence needs a reason, on both planes.

Starts its own Hub from source on :8109 with a fresh database (never :8000 or :8010). No agent turn:
an author and a granted verifier hold seeded running-run credentials for the Hub's own agent routes.

  1. an author records evidence against FR-1 of a submitted document;
  2. the operator route: a rejection with no reason, and with a whitespace reason, answers 422
     `rejection_needs_reason` and leaves no review; a reasoned rejection answers 200;
  3. the agent plane: the granted verifier's blank rejection answers 422; acceptance without a
     reason is still 200.

    py -3.11 scripts/drive/d1012_f551_rejection_reason.py
"""

import pathlib
import secrets
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8109
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1012-f551" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

PATH = "spec/changes/reasoned/spec.json"


def seed_runs(pid):
    """Running runs for `author` and a `verifier` granted evidence acceptance; returns their tokens."""
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
        for name, granted in (("author", False), ("verifier", True)):
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
    (root / "README.md").write_text("# f551\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f551"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"

    code, out = d.api("POST", f"{base}/project/documents", {"path": PATH, "title": "Reasoned"})
    d.check("0 the document is created", code == 201, f"{code} {out}")
    tokens = seed_runs(pid)
    document = {
        "schema_version": 1, "kind": "change-spec", "title": "Reasoned",
        "requirements": [{"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}],
    }
    code, out = as_agent(tokens["author"], "POST", "/agent-actions/spec/documents",
                         {"path": PATH, "document": document})
    d.check("0 the document is submitted", code == 200, f"{code} {out}")

    ids = []
    for _ in range(2):
        code, out = as_agent(tokens["author"], "POST", "/agent-actions/spec/evidence",
                             {"identifier": "FR-1", "summary": "ran it"})
        d.check("1 evidence is recorded", code == 201, f"{code} {out}")
        ids.append(out["id"])
    operator_ev, agent_ev = ids

    for label, body in (("no reason", {"decision": "rejected"}),
                        ("whitespace reason", {"decision": "rejected", "reason": " \n"})):
        code, out = d.api("POST", f"{base}/project/spec/evidence/{operator_ev}/decision", body)
        d.check(f"2 operator rejection with {label} is 422 rejection_needs_reason",
                code == 422 and "rejection_needs_reason" in str(out), f"{code} {str(out)[:300]}")
    code, out = d.api("GET", f"{base}/project/spec/evidence/{operator_ev}/reviews")
    d.check("2 no review was recorded by the refusals", code == 200 and out["reviews"] == [],
            f"{code} {out}")
    code, out = d.api("POST", f"{base}/project/spec/evidence/{operator_ev}/decision",
                      {"decision": "rejected", "reason": "the test cites the wrong file"})
    d.check("2 a reasoned rejection is 200", code == 200, f"{code} {str(out)[:300]}")

    code, out = as_agent(tokens["verifier"], "POST",
                         f"/agent-actions/spec/evidence/{agent_ev}/decision",
                         {"decision": "rejected", "reason": ""})
    d.check("3 the granted verifier's blank rejection is 422 rejection_needs_reason",
            code == 422 and "rejection_needs_reason" in str(out), f"{code} {str(out)[:300]}")
    code, out = as_agent(tokens["verifier"], "POST",
                         f"/agent-actions/spec/evidence/{agent_ev}/decision",
                         {"decision": "accepted"})
    d.check("3 acceptance without a reason is still 200", code == 200, f"{code} {str(out)[:300]}")


if __name__ == "__main__":
    d.drive = drive
    d.main()
