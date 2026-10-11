"""Drive for F580: `approve_anyway` sent as a query parameter on the phase route.

Starts its own Hub from source on :8102 with a fresh database (never :8000 or :8010), opens a project
with one change document that has a gap, proposes it, and checks:

  1. approving with no override answers 409 `approval_warnings` and the message names
     `approve_anyway` and the request body;
  2. the same request with `approve_anyway=true` in the query string answers 400 naming it (it used
     to answer the same 409), and the document is still proposed;
  3. a query parameter nobody defined is refused the same way;
  4. `approve_anyway: true` in the body approves (200).

No agent turn. Run from anywhere:    py -3.11 scripts/drive/d1011_f580_phase_query.py
"""

import pathlib
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
import d1012_approval_warnings as w  # noqa: E402

d.PORT = 8102
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1011-f580-phase-query" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

PATH = w.FIRST


def detail_of(out):
    if isinstance(out, dict):
        return out.get("detail", "")
    return str(out)


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service.\n", encoding="utf-8")
    (root / "app.py").write_text("# routes go here\n", encoding="utf-8")
    d.git(root, "add", "README.md", "app.py")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f580"})
    assert code in (200, 201), (code, project)
    base = f"/projects/{project['id']}"
    w.make_document(base, PATH, "A ping route")
    quoted = urllib.parse.quote(PATH)
    code, out = d.api("POST", f"{base}/project/documents/propose?path={quoted}")
    assert code == 200 and out.get("proposed") is True, (code, out)
    phase = f"{base}/project/documents/phase?path={quoted}&to=approved"

    code, out = d.api("POST", phase, {"reason": "drive"})
    message = str(detail_of(out))
    d.check("1 the 409 names approve_anyway and the request body",
            code == 409 and "approve_anyway" in message and "body" in message,
            f"{code} {message[:300]}")

    code, out = d.api("POST", phase + "&approve_anyway=true", {"reason": "drive"})
    message = str(detail_of(out))
    d.check("2 approve_anyway in the query string is refused 400, naming it",
            code == 400 and "approve_anyway" in message
            and w.view(base, PATH).get("phase") == "proposed",
            f"{code} {message[:300]} phase={w.view(base, PATH).get('phase')}")

    code, out = d.api("POST", phase + "&bogus=1", {"reason": "drive"})
    d.check("3 an undefined query parameter is refused 400, naming it",
            code == 400 and "bogus" in str(detail_of(out)), f"{code} {str(out)[:300]}")

    code, out = d.api("POST", phase, {"reason": "drive", "approve_anyway": True})
    d.check("4 approve_anyway in the body still approves", code == 200
            and w.view(base, PATH).get("phase") == "approved", f"{code} {str(out)[:300]}")


d.drive = drive

if __name__ == "__main__":
    d.main()
