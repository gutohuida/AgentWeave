"""Drive for F546 (Tier 0), 2026-10-12: a declared task title longer than the board's width is clipped
at a word boundary, not mid-word.

Starts its own Hub from source on :8107 with a fresh database (never :8000 or :8010). No agent turn:
the document is submitted with a seeded running-run credential, the Hub's own agent route. Steps:

  1. a document declaring a 199-character task title and a short one is submitted (200 allowed);
  2. the document is taken exploring -> proposed -> approved, which materialises its tasks;
  3. GET /tasks: the long title ends on the ellipsis, is a whole-word prefix of the declared one and
     is at most 81 characters; the short title is unchanged.

    py -3.11 scripts/drive/d1012_f546_declared_title.py
"""

import pathlib
import secrets
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8107
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1012-f546" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

PATH = "spec/changes/long-title/spec.json"
LONG = " ".join(f"stage{n:02d}" for n in range(1, 26))
SHORT = "Verify the fee policy"


def seed_run(pid):
    """A running run for `author`, so the agent submit route has a credential (the Hub tests' pattern)."""
    sys.path.insert(0, str(d.REPO / "hub"))
    import os

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{d.DB.as_posix()}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.agent_auth import hash_run_token
    from hub.db.models import Agent, Run

    token = "aw_run_" + secrets.token_urlsafe(24)
    engine = create_engine(f"sqlite:///{d.DB.as_posix()}")
    with Session(engine) as session:
        session.add(Agent(id="ag-" + secrets.token_hex(4), project_id=pid, name="author"))
        session.add(Run(id="run-d1012", project_id=pid, agent="author", status="running",
                        turn_depth=0, capability_token_hash=hash_run_token(token)))
        session.commit()
    engine.dispose()
    return token


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# f546\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f546"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"

    code, out = d.api("POST", f"{base}/project/documents", {"path": PATH, "title": "Long title"})
    d.check("0 the document is created", code == 201, f"{code} {out}")
    token = seed_run(pid)
    reqs = [{"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}]
    document = {
        "schema_version": 1, "kind": "change-spec", "title": "Long title",
        "scope": {"in_scope": ["the demo"], "non_goals": ["everything else"]},
        "requirements": reqs,
        "acceptance_criteria": [{"key": "c-alpha", "requirement": "alpha",
                                 "given": "the document is approved", "when": "the work is done",
                                 "then": "the requirement is shown"}],
        "delivery": {"mode": "none"},
        "tasks": [
            {"key": "long", "title": LONG, "description": "Build it.", "requirements": ["alpha"]},
            {"key": "short", "title": SHORT, "description": "Check it.", "requirements": ["alpha"]},
        ],
    }
    saved = d.KEY
    d.KEY = token
    try:
        code, out = d.api("POST", "/agent-actions/spec/documents", {"path": PATH, "document": document})
    finally:
        d.KEY = saved
    d.check(f"1 a {len(LONG)}-character declared title is accepted", code == 200, f"{code} {out}")

    q = f"?path={PATH}"
    code, out = d.api("POST", f"{base}/project/documents/close-exploration{q}")
    d.check("2a exploration closes", code in (200, 409), f"{code} {out}")
    for phase in ("proposed", "approved"):
        code, out = d.api("POST", f"{base}/project/documents/phase{q}&to={phase}",
                          {"reason": "drive", "approve_anyway": phase == "approved"})
        d.check(f"2 moved to {phase}", code == 200, f"{code} {str(out)[:300]}")

    code, out = d.api("GET", f"{base}/tasks")
    titles = [t["title"] for t in out["tasks"]] if code == 200 else []
    long_title = next((t for t in titles if t.startswith("stage01")), "")
    body = long_title[:-1]
    d.check(
        "3 the long title is a whole-word prefix ending on the ellipsis",
        long_title.endswith("…") and LONG.startswith(body) and LONG[len(body)] == " "
        and len(long_title) <= 81,
        f"title={long_title!r}",
    )
    d.check("3 the short title is unchanged", SHORT in titles, f"titles={titles}")


if __name__ == "__main__":
    d.drive = drive
    d.main()
