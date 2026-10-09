"""Fallback checks for `a-project-orders-its-own-spec-steps` (FR-1, FR-7), 2026-10-09.

d1011 covers a project's own journey; this covers the two cases it cannot reach: a project with no
spec/journey.json (the seven built-ins, no diagnostics, the built-in duty in the briefing preview)
and a spec/journey.json that is not JSON (a `journey_file_invalid` diagnostic on GET, the built-in
duty still in the preview). Reuses d1011's scratch Hub (:8099, fresh db) and helpers; no agent turn.

    py -3.11 scripts/drive/d1011b_project_steps_fallback.py
"""

import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny service.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "fallback"})
    assert code in (200, 201), (code, project)
    base = f"/projects/{project['id']}"
    code, runner = d.api("POST", f"{base}/runners",
                         {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    assert code in (200, 201), (code, runner)
    code, out = d.api("POST", f"{base}/agents", {"name": d.AGENT, "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": "A ping route", "kind": "change-spec", "path": d.DOC})
    assert code == 201, (code, out)
    code, out = d.api("POST", f"{base}/project/documents/journey?path={urllib.parse.quote(d.DOC)}",
                      {"step": "requirements", "size": "large"})
    assert code == 200, (code, out)
    d.api("POST", f"{base}/project/documents/journey?path={urllib.parse.quote(d.DOC)}",
          {"step": "requirements"})

    file = root / "spec" / "journey.json"
    assert not file.exists()
    code, got = d.api("GET", f"{base}/project/journey")
    keys = [s.get("key") for s in got.get("steps", [])] if isinstance(got, dict) else []
    text = d.preview(base)
    d.check("FR-1 no spec/journey.json: the seven built-ins, no diagnostics",
            code == 200 and keys == list(d.BUILTINS) and got.get("diagnostics") == [],
            f"{code} keys={keys} body={str(got)[:200]}")
    d.check("FR-1 its briefing preview is the built-in requirements duty",
            "[step: requirements]" in text, text[:300])

    file.parent.mkdir(exist_ok=True)
    file.write_text("{ this is not json", encoding="utf-8")
    code, got = d.api("GET", f"{base}/project/journey")
    codes = [x.get("code") for x in got.get("diagnostics", [])] if isinstance(got, dict) else []
    keys = [s.get("key") for s in got.get("steps", [])] if isinstance(got, dict) else []
    text = d.preview(base)
    d.check("FR-7 a journey file that is not JSON: journey_file_invalid on GET, built-ins served",
            code == 200 and codes == ["journey_file_invalid"] and keys == list(d.BUILTINS),
            f"{code} {str(got)[:300]}")
    d.check("FR-7 its briefing preview is still the built-in requirements duty",
            "[step: requirements]" in text, text[:300])


d.drive = drive

if __name__ == "__main__":
    d.main()
