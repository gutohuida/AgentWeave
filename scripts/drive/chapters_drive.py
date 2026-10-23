"""Acceptance drive for the-thread-reads-as-chapters-the-manager-writes (slice manager-chapters).

Written and run BEFORE anything is built: it must fail at the first missing piece, the `chapters`
manager job (PATCH /manager/jobs/chapters answers 404 today). It passes only when the behaviour
fires end to end on a real Hub with real Haiku turns. Not part of the pytest suite.

Covers ac-git, ac-fires, ac-controls, ac-cost, ac-agent. ac-story is the operator's to judge.
Needs AW_HUB (trial Hub :8010, never :8000), AW_KEY, AW_DB (that Hub's SQLite, read only), and for
ac-git AW_PROJECT (this repository's project, proj-d85a82bf4216).

The contract these steps assume, taken from the spec; a build that names it differently changes
this file, not the spec:
  PATCH /manager/jobs/chapters  {enabled, mode: "automatic"|"button", runner_id, model}
  POST  /manager/jobs/chapters/run              the 'Weave the thread' button
  GET   /chapters                               {chapters: [{id, title, summary, starts_at,
                                                  author, version, commits: [{sha, tag, date,
                                                  author, subject}], ...}]}
  GET   /chapters/versions                      [{author, requested_by, at, reason}]
  GET   /manager/activity?job=chapters          firings, each with usage
  GET   /manager/jobs                           each job carries `usage_total`
  agent tools create_chapter / edit_chapter (MCP), refused with a named citation on a miss.
"""

import json
import os
import pathlib
import sqlite3
import subprocess
import tempfile
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

DB = os.environ["AW_DB"]
REPO = pathlib.Path(__file__).resolve().parents[2]
HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
JOB = "chapters"
failures = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)
    return ok


def stop_if_failed(label):
    """The first missing piece ends the drive: later steps would only repeat its absence."""
    if failures:
        print(f"\nSTOPPED at: {label}\n{len(failures)} failed: {failures}")
        sys.exit(1)


def rows(query, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def firings(pid):
    out = []
    for (d,) in rows(
        "select data from event_logs where project_id=? and event_type='manager_job_fired'", (pid,)
    ):
        data = json.loads(d)
        if data.get("job") == JOB:
            out.append(data)
    return out


def first_hub_record(pid):
    """The earliest record the Hub holds for the project, across every source a knot can come from."""
    queries = (
        "select min(created_at) from tasks where project_id=?",
        "select min(created_at) from spec_documents where project_id=?",
        "select min(timestamp) from event_logs where project_id=?",
    )
    found = []
    for q in queries:
        try:
            v = rows(q, (pid,))[0][0]
        except sqlite3.Error:
            continue
        if v:
            found.append(str(v).replace(" ", "T"))
    return min(found)


def wait_for(pred, secs, what):
    end = time.time() + secs
    while time.time() < end:
        got = pred()
        if got:
            return got
        time.sleep(3)
    print("TIMEOUT waiting for", what)
    return None


def scratch_project(name):
    root = pathlib.Path(os.environ.get("AW_SCRATCH") or tempfile.gettempdir()) / f"{name}-{TAG}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("chapters drive\n", encoding="utf-8")
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "a@example.invalid"],
        ["git", "config", "user.name", "a"],
        ["git", "add", "README.md"],
        ["git", "commit", "-m", "x"],
    ):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"{name}-{TAG}"})
    if c == 500:
        # The trial Hub registers the project and then answers 500 (seen 2026-10-23); the project
        # is listed, so find it rather than fail a drive on a fault that is not this change's.
        print("note: POST /projects/open answered 500; looking the project up by directory")
        _, listed = api("GET", "/projects")
        proj = next((p for p in listed or [] if p.get("working_directory") == str(root)), None)
        c = 200 if proj else 500
    if c not in (200, 201):
        show("open", c, proj)
        sys.exit(1)
    pid = proj["id"]
    c, runner = api(
        "POST", f"/projects/{pid}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU}
    )
    check(f"{name}: runner created", c == 201, c)
    return pid, runner["id"]


def approved_document(pid, title, agent="builder"):
    """A one-task document, approved. Returns (path, task id)."""
    S = f"/projects/{pid}/project"
    c, doc = api("POST", f"{S}/documents", {"title": title})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": title,
        "summary": "Fixture for the chapters drive.", "problem": "Drive fixture.",
        "scope": {"in_scope": ["README"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "r1", "statement": "The README MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "the README",
                                 "when": "read", "then": "it exists"}],
        "tasks": [{"key": "t1", "title": "Check README", "description": "Check it.",
                   "requirements": ["r1"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }
    api("PUT", f"{S}/documents/{path}/content", {"document": payload})
    api("POST", f"{S}/documents/close-exploration?path={path}")
    api("POST", f"{S}/documents/propose?path={path}")
    # The fixture has no how_to_check and skips journey steps, so approval lists gaps (409
    # approval_warnings) unless the drive approves over them, as the operator may.
    c, res = api("POST", f"{S}/documents/phase?path={path}&to=approved",
                 {"reason": "drive", "approve_anyway": True})
    created = (res or {}).get("tasks_created") or []
    ok = check(f"{title}: approved with a task created", c == 200 and bool(created), (c, created))
    if not ok:
        show("approve", c, res)
        sys.exit(1)  # nothing after this means anything if the approval did not happen
    return path, created[0]


def approve_task(pid, task):
    """Walk a task through the moves the map allows, then land it: pending to approved."""
    A = f"/projects/{pid}"
    for to in ("in_progress", "completed"):
        c, res = api("PATCH", f"{A}/tasks/{task}", {"assignee": "builder", "status": to})
        if c != 200:
            show(f"task -> {to}", c, res)
            return False
    c, res = api("POST", f"{A}/tasks/{task}/land", {})
    if c != 200:
        show("land", c, res)
    return c == 200 and (res or {}).get("status") == "approved"


def fired(pid, before, what, secs=240):
    """Exactly one more chapters firing than `before`, once the Hub has had time to record it."""
    got = wait_for(lambda: len(firings(pid)) > before, secs, what)
    time.sleep(3)  # a second, wrongly-recorded firing would land by now
    n = len(firings(pid)) - before
    check(what, bool(got) and n == 1, f"{n} new firings")
    return n


# ---------------------------------------------------------------- ac-controls (new project)
pid, rid = scratch_project("chapters-controls")
A = f"/projects/{pid}"
api("POST", f"{A}/agents", {"name": "builder", "runner_id": rid})

if os.environ.get("AW_FIXTURES_ONLY"):
    # Proves every non-chapters step works on this Hub: approve, walk the task, archive.
    fpath, ftask = approved_document(pid, f"fixture {TAG}")
    check("fixture: the task reaches approved", approve_task(pid, ftask))
    c, res = api("POST", f"/projects/{pid}/project/documents/phase?path={fpath}&to=archived",
                 {"reason": "drive", "no_capability_change": True})
    check("fixture: the document archives", c == 200, (c, res))
    sys.exit(1 if failures else 0)

c, jobs = api("GET", f"{A}/manager/jobs")
listed = [j["key"] for j in (jobs or {}).get("jobs", [])]
check("the chapters job is among the Manager's jobs", JOB in listed, listed)
stop_if_failed("no chapters job")  # <- where the drive fails before anything is built

job = next(j for j in jobs["jobs"] if j["key"] == JOB)
check("default: the job is off", job.get("enabled") is False, job)
c, feed = api("GET", f"{A}/thread")
check("default: the Thread offers no button", not (feed or {}).get("can_weave"), (feed or {}).get("can_weave"))
base = len(firings(pid))
approved_document(pid, f"controls default {TAG}")
time.sleep(20)
check("default: approval records no firing", len(firings(pid)) == base)

c, _ = api("PATCH", f"{A}/manager/jobs/{JOB}", {"enabled": True, "mode": "button", "runner_id": rid, "model": HAIKU})
check("button-only configured", c == 200, c)
c, feed = api("GET", f"{A}/thread")
check("button-only: the Thread offers the button", bool((feed or {}).get("can_weave")))
approved_document(pid, f"controls button {TAG}")
time.sleep(20)
check("button-only: approval records no firing", len(firings(pid)) == base)
c, _ = api("POST", f"{A}/manager/jobs/{JOB}/run")
check("button-only: the press is accepted", c in (200, 202), c)
fired(pid, base, "button-only: the press records one firing")
last = firings(pid)[-1]
check("the press's firing records the chosen runner and model",
      last.get("runner_id") == rid and last.get("model") == HAIKU, (last.get("runner_id"), last.get("model")))
check("the press's firing is a requested one", last.get("trigger") in ("button", "operator", "requested"), last.get("trigger"))

# ---------------------------------------------------------------- ac-fires (same project, automatic)
c, _ = api("PATCH", f"{A}/manager/jobs/{JOB}", {"mode": "automatic"})
check("automatic firing configured", c == 200, c)
n = len(firings(pid))
path, task = approved_document(pid, f"fires {TAG}")
fired(pid, n, "a document approved: one firing")
n = len(firings(pid))
check("the document's last task approved", approve_task(pid, task))
fired(pid, n, "a document's last task approved: one firing")
n = len(firings(pid))
c, res = api("POST", f"/projects/{pid}/project/documents/phase?path={path}&to=archived",
             {"reason": "drive", "no_capability_change": True})
check("the document archived", c == 200, (c, res))
fired(pid, n, "a document archived: one firing")
n = len(firings(pid))
api("POST", f"{A}/manager/jobs/{JOB}/run")
fired(pid, n, "the button pressed: one firing")

# ---------------------------------------------------------------- ac-cost
c, act = api("GET", f"{A}/manager/activity?job={JOB}")
shown = (act or {}).get("firings", [])
recorded = firings(pid)
check("every firing is listed with its usage", len(shown) == len(recorded) >= 2 and all("usage" in f for f in shown),
      f"{len(shown)} listed, {len(recorded)} recorded")


def tokens(u):
    return sum((u or {}).get(k) or 0 for k in ("input_tokens", "output_tokens"))


c, jobs = api("GET", f"{A}/manager/jobs")
job = next((j for j in jobs["jobs"] if j["key"] == JOB), {})
total = (job.get("usage_total") or {})
check("the project's total for the job is shown and equals the firings' sum",
      tokens(total) == sum(tokens(f.get("usage")) for f in recorded) and tokens(total) > 0,
      f"shown {tokens(total)}, recorded {sum(tokens(f.get('usage')) for f in recorded)}")
stop_if_failed("ac-cost")

# ---------------------------------------------------------------- ac-agent (job off)
pid2, rid2 = scratch_project("chapters-agent")
B = f"/projects/{pid2}"
api("POST", f"{B}/agents", {"name": "organiser", "runner_id": rid2})
check("the job is off for this project", not any(
    j["key"] == JOB and j.get("enabled") for j in api("GET", f"{B}/manager/jobs")[1]["jobs"]))
approved_document(pid2, f"agent subject {TAG}")
msg = ("Use your AgentWeave chapter tools. First create ONE chapter titled 'Drive chapter' holding "
       "every knot of the thread, with a one-sentence summary. Then submit an edit to that chapter "
       "citing the task id task-doesnotexist00. Report in one line whether each call was accepted "
       "or refused. Do not use any other tools.")
api("POST", f"{B}/agent/trigger", {"agent": "organiser", "message": msg}, timeout=90)


def chapters():
    return (api("GET", f"{B}/chapters")[1] or {}).get("chapters", [])


made = wait_for(lambda: [c for c in chapters() if c.get("title") == "Drive chapter"], 240, "the agent's chapter")
check("the chapter is on the surface", bool(made))
check("it is a version under the agent's name", bool(made) and made[0].get("author") == "organiser",
      (made or [{}])[0].get("author"))
c, vers = api("GET", f"{B}/chapters/versions")
vers = vers if isinstance(vers, list) else (vers or {}).get("versions", [])
check("exactly one version: the refused edit left none", len(vers) == 1, len(vers))

print(f"\n{len(failures)} failed: {failures}" if failures else "\nall passed")

# ---------------------------------------------------------------- ac-git (this repository)
PROJECT = os.environ.get("AW_PROJECT")
if PROJECT and not failures:
    C = f"/projects/{PROJECT}"
    api("PATCH", f"{C}/manager/jobs/{JOB}", {"enabled": True, "mode": "button"})
    before = len(firings(PROJECT))
    api("POST", f"{C}/manager/jobs/{JOB}/run")
    fired(PROJECT, before, "ac-git: the press records one firing", secs=1800)
    chs = (api("GET", f"{C}/chapters")[1] or {}).get("chapters", [])
    first_knot = first_hub_record(PROJECT)
    early = [c for c in chs if c.get("commits")]
    check("ac-git: chapters from git exist", bool(early), len(chs))
    check("ac-git: they are dated before the first Hub record",
          all(str(c["starts_at"]) < str(first_knot) for c in early), first_knot)
    shas = [x["sha"] for c in early for x in c["commits"]]
    missing = [s for s in shas if subprocess.run(["git", "cat-file", "-e", s], cwd=REPO).returncode]
    check("ac-git: every cited commit exists in the repository", bool(shas) and not missing, f"{len(missing)} missing")
    check("ac-git: commits carry tag, date, author and subject",
          all(all(x.get(k) for k in ("date", "author", "subject")) and "tag" in x for x in early[0]["commits"]))
    print("ac-story is the operator's: read the Thread surface of", PROJECT)

sys.exit(1 if failures else 0)
