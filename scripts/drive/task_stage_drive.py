"""Acceptance drive for `task-stages-in-the-build-view-and-dependency-map` (TSBVD-1), criterion
drive-a-landing-build (FR-11), written failing first, before the Hub derives the pre-review stage and
before the build view and the map draw stages.

What it does, against the trial Hub on :8010 (never :8000):
  - opens a scratch git project with a Haiku runner, a Builder and a Checker, and project checks for
    review and for landing (each sleeps a few seconds, so a check is there to be seen);
  - approves a two-task document and builds it as a flow at Reviewed, landing on main; the drive
    fires the flow itself (its cron fires once a year) until both tasks are on main;
  - holds three pages open for the whole build: the build view, the Tasks board and the dependency map
    (the board's Dependencies view). Every 2 seconds it records the stage each shows for each task, by
    the words each page draws; between records it keeps reading every 0.25 s, so a check start is timed
    to a quarter of a second against the run's `started_at` (database, read only);
  - asserts (1) each surface shows, in order, Building -> Pre-review checks -> In review -> Waiting to
    land -> Landing checks -> Landing -> On main for each task; (2) the three surfaces agree at every
    record; (3) during both check stages each surface shows a waiting or running check of the matching
    kind (pre-review, landing); (4) each check start shows on each surface within 3 s of the run's
    started_at.

Prints one line in the `drive_baseline` shape and exits 1 if the check failed:
    check drive-a-landing-build: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
Screenshots at the two check stages and the end go to testbed/task-stage-drive/<HHMMSS>/.

It spends Haiku turns (a builder and a checker per task). It is a drive, not a suite test: nothing under
tests/ or hub/tests/ imports it.

    py -3.11 scripts/drive/task_stage_drive.py --key aw_live_... --db <trial agentweave.db>
    py -3.11 scripts/drive/task_stage_drive.py --start-hub         # starts the trial Hub from this checkout
    py -3.11 scripts/drive/task_stage_drive.py --self-test         # the drive's own logic only
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
STAMP = time.strftime("%H%M%S")
OUT = REPO / "testbed" / "task-stage-drive" / STAMP
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-task-stage" / STAMP
TRIAL_DB = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial" / "agentweave.db"
HAIKU = "claude-haiku-4-5-20251001"
KEY_NAME = "task-stage-drive"
CRITERION = "drive-a-landing-build"

SEQUENCE = ["Building", "Pre-review checks", "In review", "Waiting to land", "Landing checks", "Landing", "On main"]
# Longest first: "Landing checks" must win over "Landing", "Pre-review checks" over nothing shorter.
KNOWN = sorted(SEQUENCE + ["Not started", "Ready for review", "Preparing checkout", "Sent back",
                            "Needs your answer", "Landing held", "Did not land", "Closed"], key=len, reverse=True)
CHECK_STAGES = {"Pre-review checks": "pre-review", "Landing checks": "landing"}
RECORD_EVERY = 2.0     # seconds between recorded samples (the criterion)
PROBE_EVERY = 0.25     # seconds between the reads that time a check start
START_LIMIT = 3.0      # seconds a check start may take to show (FR-6)
BUILD_WAIT = 45 * 60
FIRE_EVERY = 20.0

HUB = ""
KEY = ""
DB = pathlib.Path()


class Setup(Exception):
    """The scenario could not be built: the check was not reached."""


# --------------------------------------------------------------------------- logic, self-tested


def stage_of(text):
    """The canonical stage a surface's words open with, else the raw text (so today's raw statuses show)."""
    text = " ".join((text or "").split())
    for word in KNOWN:
        if text.lower().startswith(word.lower()):
            return word
    return text


def without_stage(text):
    """The marker's words with the stage word it opens with taken out: 'Pre-review checks' is the stage,
    not a check marker."""
    text = " ".join((text or "").split())
    word = stage_of(text)
    return text[len(word):] if word in KNOWN else text


def check_of(marker):
    """(kind, state) a marker tells, each None when it says nothing: kind pre-review or landing, state
    waiting/running/passed/failed/could-not-run."""
    text = without_stage(marker).lower()
    kind = "landing" if "landing" in text else "pre-review" if re.search(r"pre-?review|review", text) else None
    state = next((s for s, pat in (("could-not-run", r"could not run|couldn.t run"), ("failed", r"fail"),
                                   ("passed", r"pass"), ("running", r"running|in progress|ran"),
                                   ("waiting", r"waiting|queued")) if re.search(pat, text)), None)
    return kind, state


def collapse(words):
    out = []
    for word in words:
        if not out or out[-1] != word:
            out.append(word)
    return out


def sequence_of(words):
    """The stages of SEQUENCE a surface went through, in order of appearance, repeats folded."""
    return collapse([w for w in words if w in SEQUENCE])


def utc_ms(value):
    if isinstance(value, (int, float)):
        return float(value) * 1000
    when = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.timestamp() * 1000


def _pattern_finds_branch():
    """head_pattern must match a real ref shaped like the Hub's task branches (in a throwaway repo)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        def git(*a):
            return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=d,
                                  capture_output=True, text=True).stdout
        git("init", "-q")
        git("commit", "-q", "--allow-empty", "-m", "x")
        git("branch", "agentweave/task/task-abc123")
        return bool(git("for-each-ref", "--format=%(objectname)", head_pattern("task-abc123")).split())


def self_test():
    cases = [
        (stage_of("Landing checks on Developer"), "Landing checks"),
        (stage_of("Landing"), "Landing"),
        (stage_of("in progress"), "in progress"),
        (stage_of("Pre-review checks"), "Pre-review checks"),
        (check_of("Pre-review checks Pre-review check running"), ("pre-review", "running")),
        (check_of("Landing checks Landing check waiting for a slot"), ("landing", "waiting")),
        (check_of("Pre-review checks"), (None, None)),
        (check_of("Landing checks Pre-review check failed"), ("pre-review", "failed")),
        (sequence_of(["Not started", "Building", "Building", "Ready for review", "Pre-review checks", "Building"]),
         ["Building", "Pre-review checks", "Building"]),
        (sequence_of(SEQUENCE), SEQUENCE),
        (sequence_of(["in progress", "completed"]), []),
        (int(utc_ms("2026-11-25T21:35:19+00:00") - utc_ms("2026-11-25 21:35:16")), 3000),
        # one batched landing run, filed under the first task, holds both branch heads: both tasks get it
        (tasks_of("a", "['aaa111', 'bbb222']", {"a": "aaa111", "b": "bbb222"}, ["a", "b"]), ["a", "b"]),
        (tasks_of("a", "['aaa111']", {"a": "aaa111", "b": "bbb222"}, ["a", "b"]), ["a"]),
        (tasks_of("b", None, {}, ["a", "b"]), ["b"]),
        (_pattern_finds_branch(), True),
    ]
    bad = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    for i, got, want in bad:
        print(f"self-test case {i}: got {got!r}, wanted {want!r}")
    print("self-test:", "PASS" if not bad else "FAIL", f"({len(cases) - len(bad)}/{len(cases)})")
    return not bad


# --------------------------------------------------------------------------- Hub


def api(method, path, body=None, timeout=60, key=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HUB + "/api/v1" + path, data,
                                 {"Authorization": "Bearer " + (key or KEY), "Content-Type": "application/json"},
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode(errors="replace")[:4000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def as_agent(pid, agent, method, path, body=None):
    """One agent-plane call as `agent`, through a run credential that lives for the call: a run row
    seeded the way the Hub's tests seed one, completed straight after."""
    token = "aw_run_" + secrets.token_urlsafe(24)
    run_id = "run-tsdrive-" + secrets.token_hex(4)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    con.execute("insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
                "capability_token_hash) values (?, ?, ?, 'running', ?, 'operator', 0, ?)",
                (run_id, pid, agent, now, hashlib.sha256(token.encode()).hexdigest()))
    con.commit()
    try:
        return api(method, "/agent-actions" + path, body, key=token)
    finally:
        con.execute("update runs set status='completed', ended_at=? where id=?", (now, run_id))
        con.commit()
        con.close()


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def poll(fn, secs=15.0, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            value = fn()
            if value:
                return value
        except Exception:  # noqa: BLE001 -- a row not yet written, a page mid-render
            pass
        time.sleep(every)
    return None


def start_hub(port):
    """The trial Hub, from this checkout's hub/, on the trial profile's database (hubs.md)."""
    key = "aw_live_" + secrets.token_hex(16)
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{TRIAL_DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = key
    SCRATCH.mkdir(parents=True, exist_ok=True)
    log = open(SCRATCH / f"hub-{port}.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | 0x08000000)
    return proc, key


def stop_hub(proc):
    if proc is not None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


# --------------------------------------------------------------------------- the scenario


def payload():
    def task(key, word):
        return {"key": key, "title": f"Add {word}.txt", "requirements": [word], "files": [f"{word}.txt"],
                "description": f"Create the file {word}.txt at the repository root holding the single line "
                               f"`{word}`. Change nothing else.",
                "builder": "Builder", "checker": "Checker"}
    words = ("hello", "bye")
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Two notes",
        "summary": "Two one-line files.", "problem": "The repository has no notes.",
        "scope": {"in_scope": ["hello.txt", "bye.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": w, "modal": "MUST", "statement": f"The repository MUST hold {w}.txt reading {w}."}
                         for w in words],
        "acceptance_criteria": [{"key": f"says-{w}", "requirement": w, "given": "the repository checked out",
                                 "when": f"{w}.txt is read", "then": f"it reads {w}", "how_to_check": f"cat {w}.txt",
                                 "checked_by": "agent"} for w in words],
        "tasks": [task("t1", "hello"), task("t2", "bye")],
        "delivery": {"mode": "flow", "agent": "Builder", "stop_when_queue_empties": True, "cron": "0 0 1 1 *",
                     "reasons": {"mode": "Two tasks.", "agent": "Builder builds both."}},
    }


def setup():
    root = SCRATCH / "project"
    root.mkdir(parents=True, exist_ok=True)

    def git(*args):
        subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                       cwd=root, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the task stage drive.\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"taskstage-{STAMP}"})
    if code not in (200, 201):
        raise Setup(f"open the project: {code} {project}")
    pid = project["id"]
    base = f"/projects/{pid}"
    api("PATCH", base, {"main_branch": "main"})
    sleeper = f'"{pathlib.Path(sys.executable).as_posix()}" -c "import time; time.sleep(8)"'
    code, out = api("PUT", f"{base}/settings", {
        "allow_agent_jobs": True,
        "checks": [{"name": "review-check", "command": sleeper, "timeout_seconds": 60, "phase": "review"},
                   {"name": "landing-check", "command": sleeper, "timeout_seconds": 60, "phase": "landing"}]})
    if code != 200:
        raise Setup(f"configure the checks: {code} {str(out)[:300]}")
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    if code not in (200, 201):
        raise Setup(f"a Haiku runner: {code} {runner}")
    for name in ("Builder", "Checker"):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        if code not in (200, 201):
            raise Setup(f"agent {name}: {code} {out}")
    doc = "spec/changes/two-notes/spec.json"
    quoted = urllib.parse.quote(doc)
    for method, path, body in (("POST", f"{base}/project/documents", {"title": "Two notes", "kind": "change-spec", "path": doc}),
                               ("PUT", f"{base}/project/documents/{doc}/content", {"document": payload()})):
        code, out = api(method, path, body)
        if code not in (200, 201):
            raise Setup(f"{method} {path}: {code} {str(out)[:400]}")
    code, out = as_agent(pid, "Checker", "POST", "/spec/documents/confirm-criteria",
                         {"path": doc, "confirmations": [{"criterion": f"says-{w}", "kind": "new"} for w in ("hello", "bye")]})
    if code != 200:
        raise Setup(f"confirm the criteria: {code} {str(out)[:300]}")
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True,
                     "content_version": read.get("content_version") if isinstance(read, dict) else None})
    if code != 200:
        raise Setup(f"approve: {code} {str(out)[:400]}")
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                    {"driver": "flow", "level": "reviewed", "builders": ["Builder"], "landing": "main"})
    if code != 200:
        raise Setup(f"build: {code} {str(out)[:400]}")
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    rows = ro("select t.id, t.readable_id, t.spec_task_key, t.loop_id from tasks t join spec_documents d "
              "on d.id=t.spec_document_id where d.project_id=? and d.path=?", (pid, doc))
    tasks = {r["spec_task_key"]: dict(r) for r in rows}
    loop = tasks["t1"]["loop_id"] if "t1" in tasks else None
    job = ro("select job_id from loops where id=?", (loop,))[0]["job_id"] if loop else None
    document_id = ro("select id from spec_documents where project_id=? and path=?", (pid, doc))[0]["id"]
    if not (build_id and job and len(tasks) == 2):
        raise Setup(f"the build runs no flow over both tasks: build={build_id} job={job} tasks={list(tasks)}")
    print(f"project {pid}, build {build_id}, job {job}, tasks { {k: v['readable_id'] for k, v in tasks.items()} }",
          flush=True)
    return {"pid": pid, "base": base, "build": build_id, "job": job, "doc": document_id,
            "tasks": list(tasks.values())}


# --------------------------------------------------------------------------- the three surfaces

MARKER_JS = """(el) => {
  if (!el) return null;
  const bits = [el.innerText || ''];
  for (const n of [el, ...el.querySelectorAll('[aria-label],[title]')]) {
    for (const a of ['aria-label', 'title']) if (n.getAttribute(a)) bits.push(n.getAttribute(a));
  }
  return bits.join(' ');
}"""

READ_BUILD_VIEW = """(ids) => Object.fromEntries(ids.map((id) => {
  const el = document.querySelector('li#build-task-' + id + ' .aw-bv-status');
  const word = el ? (el.querySelector('.aw-bv-stage-word') || el).innerText : null;
  return [id, el ? {word, all: (%s)(el)} : null];
}))""" % MARKER_JS

READ_BOARD = """(ids) => Object.fromEntries(ids.map((id) => {
  const el = document.querySelector('[data-testid="task-stage-' + id + '"]');
  const card = document.querySelector('[data-testid="task-open-' + id + '"]');
  const root = card ? (card.closest('[data-slot=task-card]') || card.parentElement) : el;
  return [id, el ? {word: el.innerText, all: (%s)(root)} : null];
}))""" % MARKER_JS

READ_MAP = """(refs) => Object.fromEntries(refs.map((ref) => {
  const node = [...document.querySelectorAll('[data-slot=flow-node]')]
    .find((n) => (n.querySelector('.aw-st-node-ref') || {}).innerText === ref);
  const meta = node && node.querySelector('.aw-st-node-meta');
  const first = meta && meta.firstElementChild;
  return [ref, first ? {word: first.innerText || first.getAttribute('aria-label') || '', all: (%s)(first)} : null];
}))""" % MARKER_JS


def init_script():
    return ("try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
            "localStorage.setItem('agentweave-selected-project', %s); } catch (e) {}"
            % (json.dumps(KEY), json.dumps(HUB), json.dumps(S["pid"])))


S: dict = {}


def open_pages(browser):
    pid, doc = S["pid"], S["doc"]
    pages = {}
    for name in ("build view", "board", "map"):
        context = browser.new_context(viewport={"width": 1440, "height": 940})
        context.add_init_script(init_script())
        page = context.new_page()
        if name != "build view":
            page.add_init_script("try { localStorage.setItem(%s, %s); localStorage.setItem(%s, 'true'); } catch (e) {}" % (
                json.dumps(f"aw.boardScope.{pid}"), json.dumps(json.dumps({"kind": "spec", "id": doc})),
                json.dumps(f"aw.boardShowFinished.{pid}")))
        pages[name] = page
    pages["build view"].goto(f"{HUB}/?project={pid}&tab=spec&view=build&focus={S['build']}", wait_until="domcontentloaded")
    pages["board"].goto(f"{HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
    pages["map"].goto(f"{HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
    for name, page in pages.items():
        try:
            page.get_by_test_id("build-view").first.wait_for(timeout=30000) if name == "build view" else \
                page.locator("[data-testid^=task-open-]").first.wait_for(timeout=30000)
        except Exception as exc:  # noqa: BLE001 -- absence is reported by the check
            raise Setup(f"the {name} did not draw: {str(exc)[:160]}") from exc
    mapper = pages["map"]
    switch = mapper.get_by_role("radio", name="Dependencies")
    if not switch.count():
        switch = mapper.get_by_role("button", name="Dependencies")
    switch.first.click()
    try:
        mapper.locator("[data-slot=flow-node]").first.wait_for(timeout=15000)
    except Exception as exc:  # noqa: BLE001
        raise Setup(f"the dependency map drew no node: {str(exc)[:160]}") from exc
    return pages


def read_surfaces(pages):
    """{task id: {surface: (stage, marker words)}} as each page draws it right now."""
    ids = [t["id"] for t in S["tasks"]]
    refs = [t["readable_id"] for t in S["tasks"]]
    got = {
        "build view": pages["build view"].evaluate(READ_BUILD_VIEW, ids),
        "board": pages["board"].evaluate(READ_BOARD, ids),
        "map": dict(zip(ids, pages["map"].evaluate(READ_MAP, refs).values())),
    }
    return {tid: {surface: ((stage_of(cell["word"]), cell["all"]) if cell else (None, "")) for surface, cells in got.items()
                  for cell in [cells[tid]]} for tid in ids}


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(OUT / f"{name}.png"))
    except Exception:  # noqa: BLE001 -- a screenshot is evidence, not a step
        pass


HEADS: dict = {}  # task id -> branch head seen while its branch existed


def head_pattern(task_id):
    """A for-each-ref pattern for a task branch such as refs/heads/agentweave/task/<id>: `*` does not cross `/`."""
    return f"refs/heads/**/*{task_id}*"


def note_heads():
    root = SCRATCH / "project"
    for t in S["tasks"]:
        got = subprocess.run(["git", "for-each-ref", "--format=%(objectname)", head_pattern(t["id"])],
                             cwd=root, capture_output=True, text=True).stdout.split()
        if got:
            HEADS[t["id"]] = got[0]


def tasks_of(task_id, target_shas, heads, all_ids):
    """The tasks a check run is about: its own task, and every task whose branch head its target_shas hold
    (a landing run is batched: one row, the first task's id, both heads)."""
    text = str(target_shas or "")
    return sorted({task_id} | {t for t in all_ids if heads.get(t) and heads[t] in text})


def check_runs():
    """Each check run of the project's tasks with its kind: a run started after its task's approval is a landing run."""
    out = []
    note_heads()
    all_ids = [t["id"] for t in S["tasks"]]
    for r in ro("select c.id, c.task_id, c.started_at, c.state, c.target_shas, (select min(created_at) from task_transitions x "
                "where x.task_id=c.task_id and x.to_status='approved') as approved_at "
                "from task_check_runs c where c.project_id=? order by c.started_at", (S["pid"],)):
        landing = r["approved_at"] is not None and utc_ms(r["started_at"]) >= utc_ms(r["approved_at"])
        out.append({"id": r["id"], "tasks": tasks_of(r["task_id"], r["target_shas"], HEADS, all_ids),
                    "started_ms": utc_ms(r["started_at"]),
                    "kind": "landing" if landing else "pre-review", "state": r["state"]})
    return out


def fire():
    code, out = api("POST", f"{S['base']}/jobs/{S['job']}/run")
    print(f"  fired {S['job']}: {code} {str(out)[:120]}", flush=True)
    return code


TRACE: list = []  # every read, timed, written to records.json so a failure can be read back


def write_records(samples, runs, first_seen):
    """Every read and record, timed, beside the screenshots: the evidence behind each FAIL line."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "records.json").write_text(json.dumps({
        "reads": TRACE, "records": [s["t"] for s in samples], "runs": runs,
        "first_seen": [{"run": r, "task": t, "surface": s, "ms": ms} for (r, t, s), ms in first_seen.items()],
    }, indent=1, default=str), encoding="utf-8")


def run_build(pages):
    samples, shots, first_seen, reads = [], set(), {}, []
    end = time.time() + BUILD_WAIT
    last_record = last_fire = 0.0
    done_since = None
    flow_ended = False
    runs = []
    while time.time() < end:
        now = time.time()
        if now - last_fire >= FIRE_EVERY and not flow_ended:
            flow_ended = fire() == 400  # "Job is disabled": the flow stopped itself, its queue empty
            last_fire = now
        cells = read_surfaces(pages)
        runs = check_runs()
        for run in runs:
            for task in run["tasks"]:
                for surface, (stage, marker) in cells[task].items():
                    kind, state = check_of(marker)
                    if kind == run["kind"] and state in ("waiting", "running"):
                        first_seen.setdefault((run["id"], task, surface), now * 1000)
        reads.append(cells)
        TRACE.append({"t": now, "cells": cells})
        if now - last_record >= RECORD_EVERY:
            last_record = now
            samples.append({"t": now, "cells": cells})
            for tid, per in cells.items():
                for surface, (stage, _) in per.items():
                    if stage in CHECK_STAGES and (stage, surface) not in shots:
                        shots.add((stage, surface))
                        shot(pages[surface], f"{stage.split()[0].lower()}-{surface.replace(' ', '-')}")
        # The board is the surface that already draws On main; the others are held to it by judge().
        if all(per["board"][0] == "On main" for per in cells.values()):
            done_since = done_since or now
            if now - done_since >= 6:
                break
        else:
            done_since = None
        time.sleep(PROBE_EVERY)
    for surface, page in pages.items():
        shot(page, f"end-{surface.replace(' ', '-')}")
    return samples, reads, runs, first_seen, bool(done_since)


def judge(samples, reads, runs, first_seen, finished):
    problems, notes = [], []
    if not finished:
        problems.append(f"both tasks were not on main within {BUILD_WAIT // 60} minutes")
    # 1. the sequence, per task and surface
    for t in S["tasks"]:
        for surface in ("build view", "board", "map"):
            words = [cells[t["id"]][surface][0] for cells in reads]  # every read: a stage can last under 2 s
            got = sequence_of(words)
            if got != SEQUENCE:
                seen = collapse([w or "(not drawn)" for w in words])
                problems.append(f"{t['readable_id']} on the {surface} went {got or 'through none of the stages'}; it drew {seen}")
    # 2. the three agree at every record
    split = []
    for n, s in enumerate(samples):
        for t in S["tasks"]:
            per = {surface: s["cells"][t["id"]][surface][0] for surface in ("build view", "board", "map")}
            if len(set(per.values())) > 1:
                split.append((n, t["readable_id"], per))
    if split:
        n, ref, per = split[0]
        problems.append(f"the surfaces disagree in {len(split)} records, first at record {n} for {ref}: {per}")
    # 3. a check of the matching kind during both check stages
    for stage, kind in CHECK_STAGES.items():
        for surface in ("build view", "board", "map"):
            at_stage = [(t, s["cells"][t["id"]][surface]) for s in samples for t in S["tasks"]
                        if s["cells"][t["id"]][surface][0] == stage]
            if not at_stage:
                problems.append(f"the {surface} never drew {stage} (no check to look for)")
                continue
            bare = [t["readable_id"] for t, (_, marker) in at_stage
                    if check_of(marker)[0] != kind or check_of(marker)[1] not in ("waiting", "running")]
            if bare:
                problems.append(f"the {surface} at {stage}: {len(bare)} of {len(at_stage)} reads show no waiting or "
                                f"running {kind} check ({bare[0]} first)")
    # 4. each check start shows within 3 s of started_at, on each surface
    late = []
    names = {t["id"]: t["readable_id"] for t in S["tasks"]}
    for run in runs:
        for task in run["tasks"]:
            for surface in ("build view", "board", "map"):
                seen = first_seen.get((run["id"], task, surface))
                who = f"{run['kind']} run {run['id']} for {names.get(task, task)}"
                if seen is None:
                    late.append(f"{who} never showed on the {surface}")
                elif (seen - run["started_ms"]) / 1000 > START_LIMIT:
                    late.append(f"{who} showed on the {surface} {(seen - run['started_ms']) / 1000:.1f}s after it started")
    if not runs:
        problems.append("no check run was recorded (the checks did not run)")
    problems += late
    notes.append(f"{len(samples)} records of 2 tasks x 3 surfaces; {len(runs)} check runs "
                 f"({', '.join(sorted({r['kind'] for r in runs})) or 'none'})")
    return problems, notes


def main():
    global HUB, KEY, DB
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="the drive's own logic only; no Hub")
    parser.add_argument("--hub", default="http://127.0.0.1:8010")
    parser.add_argument("--key", default=os.environ.get("AW_KEY", ""))
    parser.add_argument("--db", default=str(TRIAL_DB), help="the database the Hub serves (read only)")
    parser.add_argument("--start-hub", action="store_true", help="start the trial Hub from this checkout on :8010")
    parser.add_argument("--keep", action="store_true", help="keep the scratch project")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if args.hub.rstrip("/").endswith(":8000"):
        sys.exit("REFUSING: :8000 is the operator's real instance")
    HUB, KEY, DB = args.hub.rstrip("/"), args.key, pathlib.Path(args.db)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = None
    reached, failed, detail = False, False, "not run"
    build_id = None
    try:
        if args.start_hub:
            if api("GET", "/projects")[0] != 0:
                sys.exit("REFUSING: something already answers on that port; drop --start-hub")
            proc, bootstrap = start_hub(8010)
            KEY = KEY or bootstrap  # a trial profile that already has operators ignores the bootstrap key
            if not poll(lambda: api("GET", "/projects")[0] == 200, 300, every=1):
                raise Setup(f"the trial Hub did not come up; see {SCRATCH / 'hub-8010.log'}")
        if not KEY:
            raise Setup("no operator key: pass --key (or AW_KEY), or --start-hub")
        if api("GET", "/projects")[0] != 200:
            raise Setup(f"no trial Hub answers at {HUB}; start it (see .claude/reference/hubs.md) or pass --start-hub")
        from playwright.sync_api import sync_playwright

        S.update(setup())
        build_id = S["build"]
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                pages = open_pages(browser)
                print(f"output {OUT}", flush=True)
                samples, reads, runs, first_seen, finished = run_build(pages)
            finally:
                browser.close()
        reached = True
        write_records(samples, runs, first_seen)
        problems, notes = judge(samples, reads, runs, first_seen, finished)
        failed = bool(problems)
        detail = f"build {build_id}: " + "; ".join(problems + notes) if problems else f"build {build_id}: " + "; ".join(notes)
        for p in problems:
            print("FAIL", p, flush=True)
    except Setup as exc:
        detail = f"not reached: {exc}"
        print(f"SETUP: {exc}", flush=True)
    finally:
        if S.get("build"):
            code, _ = api("POST", f"{S['base']}/project/builds/{S['build']}/stop")
            print(f"stopped the build {S['build']}: {code}", flush=True)
        stop_hub(proc)
        if not args.keep:
            time.sleep(3)
            shutil.rmtree(SCRATCH, ignore_errors=True)
    print("\n== drive_baseline")
    print(f"check {CRITERION}: reached={'yes' if reached else 'no'} failed_at_assertion={'yes' if failed else 'no'} -- {detail}")
    print(f"output: {OUT}")
    sys.exit(1 if failed or not reached else 0)


if __name__ == "__main__":
    main()
