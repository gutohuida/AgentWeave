"""Drive for F412: pressing Run on a job whose turn cannot begin.

Starts its own Hub from source on :8103 with a fresh database (never :8000 or :8010), opens a
project, creates an agent with no runner bound and a plain job for it, and presses Run:

  1. the press answers 500 naming the reason, not `200 {"success": true}`;
  2. the `JobRun` it wrote reads `failed` with that same reason (the answer agrees with the row);
  3. a second press answers the same way (the answer does not depend on a fresh state).

No agent turn: nothing here can spawn one, since no runner is bound. Run from anywhere:
    py -3.11 scripts/drive/d1011_f412_run_answer.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8103
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1011-f412-run-answer" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f412"})
    assert code in (200, 201), (code, project)
    base = f"/projects/{project['id']}"
    code, runner = d.api("POST", f"{base}/runners", {"name": "claude (drive)", "cli": "claude"})
    d.check("0 a runner is created", code in (200, 201), f"{code} {str(runner)[:300]}")
    code, out = d.api("POST", f"{base}/agents", {"name": "alpha", "runner_id": runner["id"]})
    d.check("0 the agent is created", code in (200, 201), f"{code} {str(out)[:300]}")
    code, out = d.api("PATCH", f"{base}/agents/alpha", {"runner_id": None})
    d.check("0 the agent is unbound again", code == 200, f"{code} {str(out)[:300]}")
    code, job = d.api("POST", f"{base}/jobs", {
        "name": "f412", "agent": "alpha", "message": "say hi", "cron": "0 0 1 1 *",
        "purpose": "f412 drive", "enabled": True})
    d.check("0 the job is created", code in (200, 201), f"{code} {str(job)[:300]}")
    job_id = job["id"]

    code, out = d.api("POST", f"{base}/jobs/{job_id}/run")
    runs = d.ro("select status, error_summary from job_runs where job_id=?", (job_id,))
    d.check("1 the press is not answered success", code != 200 and "success" not in str(out)[:40],
            f"{code} {str(out)[:300]}")
    d.check("2 the row it wrote reads failed and the answer carries its reason",
            len(runs) == 1 and runs[0][0] == "failed" and runs[0][1]
            and runs[0][1][:60] in str(out), f"rows={runs} answer={str(out)[:200]}")

    code, out = d.api("POST", f"{base}/jobs/{job_id}/run")
    d.check("3 a second press answers the same way", code == 500 or code == 409,
            f"{code} {str(out)[:300]}")


d.drive = drive

if __name__ == "__main__":
    d.main()
