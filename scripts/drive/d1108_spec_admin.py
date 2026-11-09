"""Acceptance drive for `an-agent-the-operator-trusts-can-tidy-the-specs` (AOTCT, spdoc-d9f38f8d3017),
2026-11-09. Written, and recorded failing on master, before the build (task `drive`, AOTCT-1).

Starts its own Hub from this checkout's source on a scratch port with a scratch database (never :8000,
never the trial :8010), serving the bundle in hub/hub/static/ui. Two parts:

  A  populated  a copy of a populated database (default: the trial profile's, copied with the sqlite
                backup API, never a file copy) is neutralised (jobs off, scheduler rows gone, queued input
                dropped, every project re-pointed at an empty scratch directory so nothing touches a real
                checkout), migrated by a Hub started on --port+1, and every agent of every project reads
                `can_admin_specs: false`; an agent created there reads false too            (ac-default-off)
  B  fresh      a fresh scratch git project (greet.py, clock.py), three Haiku agents: alpha (switch turned
                on by the operator), beta (left off), gamma (toggled in the page). Fixtures, all made by
                the operator's routes: capabilities greeting, clock, fold-cmp, fold-cmp-twin, held-cap; an
                approved roadmap with slice `s1`; approved changes loud-greeting, farewell, old-greeting-idea,
                cmp-change, cmp-change-twin, new-cap-change, mark-me, live-change (one task in progress),
                held-change, unsliced; and proposed-change (exploring: not approved, exploration open; the `proposed` phase is retired).

Steps, each printing one PASS/FAIL line per check (exit 1 on any FAIL):

  1  switch      agents read can_admin_specs false at creation; the operator's PATCH turns alpha's on
                                                                                 (FR-1 ac-default-off)
  2  route       the agent tidy route exists (401 without a run credential, not 404/405)
  3  only-op     with alpha's run credential, the operator's agent PATCH (own switch off, beta's on) is
                 refused and both switches are unchanged                          (FR-1 ac-only-operator)
  4  off         beta (switch off) is refused every op with code spec_admin_off, the reason naming the
                 switch and the operator; the spec tree and the document rows hash the same (FR-4 ac-off)
  5  reason      alpha's fold with an empty reason: reason_required, nothing changes  (FR-7 ac-reason)
  6  live        alpha's fold / supersede / set_slice on live-change: live_work naming the open task
                                                                                  (FR-5 ac-live)
  7  held        the operator holds held-change and held-cap; the read carries held {at, note}; alpha's
                 fold / supersede / set_slice on held-change and edit_capability on held-cap: document_held,
                 nothing changes; after release the fold succeeds (and the drive clears that mark)
                                                                                  (FR-11 ac-held)
  8  operators   alpha's tidy ops approve, close_exploration, archive, hold, release, accept_amendment,
                 decline_amendment, answer_cannot_satisfy, decide_evidence on proposed-change: operators_act;
                 the operator routes (phase, close-exploration, archive-batch, hold, release, tidy-acts
                 reviewed, agent PATCH) refuse alpha's run credential; the agent evidence decision is
                 refused; proposed-change is unchanged                            (FR-12 ac-no-operator-acts)
  9  fold        alpha folds cmp-change into fold-cmp retiring cmp-old; the operator folds the identical
                 twin into fold-cmp-twin with archive off; the two capabilities carry the same requirements
                 and criteria; cmp-change stays approved and reads superseded by fold-cmp
                                                                                  (FR-2 ac-fold, FR-8 ac-any)
  10 new-cap     alpha create_capability 'Notes' with fold_from new-cap-change: the capability is current,
                 carries the folded requirement and is named in spec/index.json  (FR-2 ac-new-capability)
  11 slice       alpha set_slice unsliced -> roadmap s1: the roadmap's slice-s1 names unsliced (FR-2 ac-slice)
  12 mark-clear  alpha supersedes mark-me naming greeting; it reads superseded {by alpha, reason,
                 successor}; Build is refused; clear_superseded; it reads exactly as before (FR-9 ac-mark-clear)
  13 code-wins   alpha edit_capability clock `twelve-hour` citing clock.py with code_wins: the capability
                 carries the new statement, the old one is in the document's events, the tidy list shows
                 code_wins {requirement, before, after, cited ~ clock.py}           (FR-13 ac-code-wins)
  14 turn-off    beta, in a real Haiku turn, is asked to do the four tidy acts: nothing changes and no tidy
                 act is listed for beta                                            (FR-2 ac-drive, FR-4)
  15 turn-on     alpha, in a real Haiku turn, does them: loud-greeting folded into greeting (superseded by
                 it), farewell folded into a new capability, greeting's greet-word rewritten to match
                 greet.py (code_wins citing greet.py), old-greeting-idea superseded; each act listed with
                 alpha, the turn's run and a reason                                  (FR-2 ac-drive, FR-6, FR-13)
  16 listed      GET /tidy-acts?reviewed=false lists every act with id, act, path, agent, run_id, at, reason;
                 one act marked reviewed by id leaves the list                       (FR-6 ac-listed)
  17 page        gamma's switch toggled on and off in agent settings (Access); the spec tab's superseded
                 filter shows exactly the five superseded documents with who and why; the operator selects
                 three and archives them in one action: exactly those three are archived and the two others
                 stay marked; the tidy list in the page shows every act with its reason, code-wins acts marked
                 apart naming the file; 'mark all reviewed' empties the list and the tidy events remain
                                                     (FR-1 ac-only-operator, FR-10 ac-batch, FR-6 ac-listed, FR-13)

CONTRACT (the design's, spdoc-d9f38f8d3017) plus what the drive fixes for the build, where the design
named a tool but not its route or the page's handles:

  agent field        `can_admin_specs: bool` on GET /projects/{p}/agents rows; written by PATCH
                     /projects/{p}/agents/{name}; an agent credential's write is refused (401/403)
  document read      on GET /projects/{p}/project/documents rows: `superseded: {at, by, reason, successor}
                     | null`, `held: {at, note} | null`; `?superseded=true` narrows to the marked ones
  operator routes    POST/DELETE /projects/{p}/project/documents/{path}/hold {note};
                     POST /projects/{p}/project/documents/archive-batch {paths} -> {archived, refused};
                     GET /projects/{p}/project/tidy-acts?reviewed=false -> [{id, act, path, agent, run_id,
                     at, reason, code_wins}] (a bare list, or {"acts": [...]});
                     POST /projects/{p}/project/tidy-acts/reviewed {ids} | {all: true}
  agent route        POST /agent-actions/spec/documents/tidy {path, op, reason, ...op fields} -- what the
                     MCP tool `tidy_spec_document` calls, as `amend_spec_document` calls .../amend.
                     Success: 2xx {ok: true, act_id}. Refusal: non-2xx (or ok false) with {code, reason}
                     either at the top level or under `detail`. Ops: fold {capability, items, retire,
                     retire_criteria, algorithms, criteria}; create_capability {title, area?, fold_from?};
                     edit_capability {requirement, statement | retire: true, code_wins?: {cited}};
                     supersede {successor?}; clear_superseded; set_slice {roadmap, slice}. Any op naming an
                     operator's act (approve, close_exploration, archive, hold, release, accept_amendment,
                     decline_amendment, answer_cannot_satisfy, decide_evidence) is refused `operators_act`.
  codes              spec_admin_off, document_held, live_work, reason_required, operators_act
  page handles       agent settings ?settings=access: test id `agent-can-admin-specs` on the switch (or a
                     role=switch whose name says it lets the agent tidy/admin the specs);
                     spec tab: `spec-filter-superseded`, one `spec-superseded-row` per marked document
                     (data-path) showing who marked it and why, a `spec-superseded-select` checkbox inside
                     each row, `spec-archive-selected` (and `spec-archive-confirm` if it asks);
                     the tidy list: `spec-tidy-acts` (opened by `spec-tidy-open` when not shown), one
                     `spec-tidy-act` per unreviewed act (data-act-id, data-code-wins="true"|"false"),
                     `spec-tidy-mark-all-reviewed`.

Step 14 cannot observe a refusal code inside a real turn whose tool list (D5) hides the tool from beta;
it checks the effect (nothing changed, nothing listed). Step 4 checks the codes over the route itself.

On master, step 1 fails (no can_admin_specs) and every step after it fails without spending a turn: the
real turns run only once the operator can turn the switch on.

    py -3.11 scripts/drive/d1108_spec_admin.py --port 8121 --profile d1108
    py -3.11 scripts/drive/d1108_spec_admin.py --port 8121 --profile d1108 --no-turns   # skip 14-15
    py -3.11 scripts/drive/d1108_spec_admin.py ... --populated-db C:/path/agentweave.db
"""

import argparse
import hashlib
import json
import ntpath
import os
import pathlib
import re
import secrets
import sqlite3
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import d1011_project_steps as base  # noqa: E402

HAIKU = base.HAIKU
ALPHA, BETA, GAMMA = "alpha", "beta", "gamma"
TRIAL_DB = pathlib.Path.home() / ".agentweave/hub/profiles/trial/agentweave.db"
TRIAL_KEY = pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt"
CODES = ("spec_admin_off", "document_held", "live_work", "reason_required", "operators_act")
OPERATOR_OPS = ("approve", "close_exploration", "archive", "hold", "release", "accept_amendment",
                "decline_amendment", "answer_cannot_satisfy", "decide_evidence")

CAP = "spec/capabilities/greeting/spec.json"
CLOCK = "spec/capabilities/clock/spec.json"
CMP_CAP = "spec/capabilities/fold-cmp/spec.json"
CMP_CAP_TWIN = "spec/capabilities/fold-cmp-twin/spec.json"
HELD_CAP = "spec/capabilities/held-cap/spec.json"
LOUD = "spec/changes/loud-greeting/spec.json"
FAREWELL = "spec/changes/farewell/spec.json"
DEAD = "spec/changes/old-greeting-idea/spec.json"
CMP = "spec/changes/cmp-change/spec.json"
CMP_TWIN = "spec/changes/cmp-change-twin/spec.json"
NEWCAP = "spec/changes/new-cap-change/spec.json"
MARK = "spec/changes/mark-me/spec.json"
LIVE = "spec/changes/live-change/spec.json"
HELD = "spec/changes/held-change/spec.json"
UNSLICED = "spec/changes/unsliced/spec.json"
PROPOSED = "spec/changes/proposed-change/spec.json"

GREET_PY = 'import sys\n\n\ndef greet(name):\n    return f"Hi, {name}"\n\n\nif __name__ == "__main__":\n    print(greet(sys.argv[1]))\n'
CLOCK_PY = 'import datetime\n\n\ndef now():\n    return datetime.datetime.now().strftime("%H:%M")  # 24-hour\n'

results = []


def ok_line(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    return bool(ok)


# ------------------------------------------------------------------ http helpers

def api(method, path, body=None, timeout=60, key=None):
    saved = base.KEY
    if key is not None:
        base.KEY = key
    try:
        code, out = base.api(method, path, body, timeout=timeout)
    finally:
        base.KEY = saved
    if isinstance(out, str):
        try:
            out = json.loads(out)
        except ValueError:
            pass
    return code, out


def refusal(code, out):
    """(code, reason) of a refusal, or (None, None) when the call succeeded."""
    body = out
    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
        body = body["detail"]
    if 200 <= code < 300 and not (isinstance(body, dict) and body.get("ok") is False):
        return None, None
    # Never None on a failure: a 404 from a route that does not exist is not a success.
    if isinstance(body, dict):
        return body.get("code") or f"http-{code}", str(body.get("reason") or body.get("message") or body)
    return f"http-{code}", str(body)[:300]


def tidy(token, path, op, reason="drive: tidy", **fields):
    return api("POST", "/agent-actions/spec/documents/tidy", {"path": path, "op": op, "reason": reason, **fields},
               key=token)


def documents(pid, superseded=False):
    code, out = api("GET", f"/projects/{pid}/project/documents" + ("?superseded=true" if superseded else ""))
    rows = out.get("documents", out) if isinstance(out, dict) else out
    return {d["path"]: d for d in rows} if code == 200 and isinstance(rows, list) else {}


def entry(pid, path):
    return documents(pid).get(path, {})


def agents(pid):
    code, out = api("GET", f"/projects/{pid}/agents")
    return {a["name"]: a for a in out} if code == 200 and isinstance(out, list) else {}


def tidy_acts(pid, reviewed="false"):
    code, out = api("GET", f"/projects/{pid}/project/tidy-acts?reviewed={reviewed}")
    rows = out.get("acts", out) if isinstance(out, dict) else out
    return rows if code == 200 and isinstance(rows, list) else None


def on_disk(root, path):
    try:
        return json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def state_hash(root, pid):
    """The spec tree on disk and the project's document rows, as one digest."""
    h = hashlib.sha256()
    for f in sorted((root / "spec").rglob("*")):
        if f.is_file():
            h.update(f.relative_to(root).as_posix().encode())
            h.update(f.read_bytes())
    for row in base.ro("select * from spec_documents where project_id=? order by path", (pid,)):
        h.update(repr(row).encode())
    return h.hexdigest()


# ------------------------------------------------------------------ fixtures

def capability(title, reqs):
    return {
        "schema_version": 1, "kind": "capability", "title": title,
        "requirements": [{"key": k, "statement": s, "modal": "MUST"} for k, s in reqs],
        "acceptance_criteria": [{"key": f"{k}-c", "requirement": k, "given": "the code", "when": "run",
                                 "then": s} for k, s in reqs],
        "algorithms": [],
    }


def change(title, reqs, roadmap=None):
    payload = {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"{title}.", "problem": f"Drive fixture: {title}.",
        "scope": {"in_scope": [title], "non_goals": ["anything else"]},
        "requirements": [{"key": k, "statement": s, "modal": "MUST"} for k, s in reqs],
        "acceptance_criteria": [{"key": f"{k}-c", "requirement": k, "given": "the code", "when": "run",
                                 "then": s, "how_to_check": "run it", "checked_by": "agent"} for k, s in reqs],
        "tasks": [], "algorithms": [], "design": "Fixture.", "evidence": {"checked": ["fixture"], "limits": []},
        "lifecycle": "", "open_questions": [], "delivery": {"mode": "none"},
    }
    if roadmap:
        payload["roadmap"] = roadmap
    return payload


def approve(spec, path):
    """The operator's approval names the content version it read."""
    q = urllib.parse.quote(path)
    _, read = api("GET", f"{spec}/spec?path={q}")
    version = read.get("content_version") if isinstance(read, dict) else None
    return api("POST", f"{spec}/documents/phase?path={q}&to=approved",
               {"reason": "drive", "approve_anyway": True, "content_version": version})


def make_capability(spec, path, title, reqs):
    code, out = api("POST", f"{spec}/documents", {"path": path, "title": title, "kind": "capability"})
    assert code in (200, 201), (path, code, out)
    code, out = api("POST", f"{spec}/documents/{path}/merge", {"payload": capability(title, reqs)})
    assert code == 200, (path, code, out)


def make_change(spec, path, title, reqs, approved=True, roadmap=None):
    q = urllib.parse.quote(path)
    code, out = api("POST", f"{spec}/documents", {"path": path, "title": title, "kind": "change-spec"})
    assert code in (200, 201), (path, code, out)
    code, out = api("PUT", f"{spec}/documents/{path}/content", {"document": change(title, reqs, roadmap)})
    assert code == 200, (path, code, out)
    identifiers = out.get("identifiers", {})
    if approved:
        api("POST", f"{spec}/documents/close-exploration?path={q}")
        code, out = approve(spec, path)
        assert code == 200, (path, code, out)
    return identifiers


def make_roadmap(spec):
    payload = {
        "schema_version": 1, "kind": "roadmap", "title": "Greeting roadmap",
        "summary": "One slice.", "problem": "Drive fixture roadmap.",
        "scope": {"in_scope": ["one slice"], "non_goals": ["more"]},
        "slices": [{"key": "s1", "title": "The first slice", "intent": "Greet.", "done": "It greets."}],
        "design": "", "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off", "open_questions": [],
    }
    code, doc = api("POST", f"{spec}/documents", {"title": "Greeting roadmap", "kind": "roadmap"})
    assert code in (200, 201), (code, doc)
    path = doc["path"]
    code, out = api("PUT", f"{spec}/documents/{path}/content", {"document": payload})
    assert code == 200, (code, out)
    q = urllib.parse.quote(path)
    api("POST", f"{spec}/documents/close-exploration?path={q}")
    code, out = approve(spec, path)
    assert code == 200, (code, out)
    return path


def run_credential(pid, agent):
    """A running Run row for `agent` in the drive's own database, and its plaintext credential (the
    Hub tests' pattern, as d1013 does)."""
    sys.path.insert(0, str(base.REPO / "hub"))
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{base.DB.as_posix()}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.agent_auth import hash_run_token
    from hub.db.models import Run

    token = "aw_run_" + secrets.token_urlsafe(24)
    run_id = f"run-d1108-{agent}-" + secrets.token_hex(4)
    engine = create_engine(f"sqlite:///{base.DB.as_posix()}")
    with Session(engine) as session:
        session.add(Run(id=run_id, project_id=pid, agent=agent, status="running", turn_depth=0,
                        capability_token_hash=hash_run_token(token)))
        session.commit()
    engine.dispose()
    return run_id, token


def turn(pid, agent, message):
    code, res = api("POST", f"/projects/{pid}/agent/trigger", {"agent": agent, "message": message})
    if not (code < 300 and isinstance(res, dict) and res.get("run_id")):
        return None, f"{code} {res}"
    run_id = res["run_id"]
    live = ("running", "queued", "starting", "pending")
    base.poll(lambda: base.ro("select status from runs where id=?", (run_id,))[0][0] not in live, 600)
    return run_id, base.ro("select status from runs where id=?", (run_id,))[0][0]


TIDY_PROMPT = """Tidy this project's specification documents with your tidy_spec_document tool. Do exactly
these four acts, each with a one-sentence reason, and then report what each call returned:

1. op "fold": fold spec/changes/loud-greeting/spec.json into the capability
   spec/capabilities/greeting/spec.json (path = the change, capability = the capability).
2. op "create_capability": path = spec/changes/farewell/spec.json, title = "Farewell",
   fold_from = spec/changes/farewell/spec.json -- a new capability holding the farewell change.
3. greet.py returns "Hi, <name>", but requirement `greet-word` of spec/capabilities/greeting/spec.json
   says the greeting starts with "Hello". Read greet.py, then op "edit_capability": path = that
   capability, requirement = "greet-word", statement = a sentence saying the greeting MUST start with
   "Hi", code_wins = {"cited": "greet.py"}.
4. op "supersede": path = spec/changes/old-greeting-idea/spec.json, successor =
   spec/capabilities/greeting/spec.json.

Do not change any file yourself and do nothing else. If a call is refused, say so and go on to the next."""


# ------------------------------------------------------------------ part A: a populated database

def populated(port, scratch, source):
    if not source.exists():
        ok_line("A populated database to copy exists", False, str(source))
        return
    copy = scratch / "populated.db"
    s = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(copy.as_posix())
    s.backup(d)
    s.close()
    dirs = scratch / "populated-dirs"
    dirs.mkdir(parents=True, exist_ok=True)
    # Neutralise the copy: nothing may fire, and no project may point at a real checkout.
    d.execute("update ai_jobs set enabled=0")
    d.execute("delete from apscheduler_jobs")
    d.execute("update manager_jobs set enabled=0")
    d.execute("delete from inbound_queue_entries where state='queued'")
    for (pid,) in d.execute("select id from projects").fetchall():
        target = dirs / pid
        target.mkdir(exist_ok=True)
        target = target.resolve()
        key = ("windows:" + ntpath.normcase(ntpath.normpath(str(target)))) if os.name == "nt" else f"posix:{target}"
        d.execute("update projects set working_directory=?, path_key=? where id=?", (str(target), key, pid))
    d.commit()
    before = d.execute("select count(*) from agents").fetchone()[0]
    d.close()

    saved = (base.PORT, base.HUB, base.DB, base.TMP, base.KEY)
    base.PORT, base.HUB, base.DB, base.TMP = port, f"http://127.0.0.1:{port}", copy, scratch / "populated-hub"
    if TRIAL_KEY.exists() and source == TRIAL_DB:
        base.KEY = TRIAL_KEY.read_text(encoding="utf-8").strip()
    proc = base.start_hub()
    try:
        code, projects = api("GET", "/projects")
        projects = projects if isinstance(projects, list) else (projects or {}).get("projects", [])
        seen, wrong, missing = 0, [], []
        for p in projects:
            for name, a in agents(p["id"]).items():
                seen += 1
                if "can_admin_specs" not in a:
                    missing.append(f"{p['id']}/{name}")
                elif a["can_admin_specs"] is not False:
                    wrong.append(f"{p['id']}/{name}")
        ok_line("A the migrated copy lists its agents", seen > 0, f"{seen} listed, {before} rows")
        ok_line("A every existing agent reads can_admin_specs false", seen > 0 and not wrong and not missing,
                f"missing={missing[:5]} on={wrong[:5]}")
        # A copied project has no marker in its scratch directory, so the new agent goes into a
        # project opened on the migrated Hub, with a runner of its own.
        fresh = scratch / "populated-new-project"
        fresh.mkdir(exist_ok=True)
        base.git(fresh, "init", "-q", "-b", "main")
        c, proj = api("POST", "/projects/open", {"path": str(fresh), "name": "d1108-new"})
        c2, runner = api("POST", f"/projects/{proj['id']}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})             if c < 300 else (c, proj)
        c3, out = api("POST", f"/projects/{proj['id']}/agents", {"name": "d1108new", "runner_id": runner["id"]})             if c2 < 300 else (c2, runner)
        new = agents(proj["id"]).get("d1108new", {}) if c3 < 300 else {}
        ok_line("A an agent created on the migrated copy reads can_admin_specs false",
                new.get("can_admin_specs") is False, f"{c3} {str(out)[:200]} {new.get('can_admin_specs', 'absent')}")
    finally:
        base.stop_hub(proc)
        base.PORT, base.HUB, base.DB, base.TMP, base.KEY = saved


# ------------------------------------------------------------------ part B: a fresh project

def setup(scratch):
    root = scratch / "proj"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# greeter\n\nSays hello. Checked by d1108.\n", encoding="utf-8")
    (root / "greet.py").write_text(GREET_PY, encoding="utf-8")
    (root / "clock.py").write_text(CLOCK_PY, encoding="utf-8")
    base.git(root, "init", "-q", "-b", "main")
    base.git(root, "add", "README.md", "greet.py", "clock.py")
    base.git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": "greeter"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    api("PATCH", f"/projects/{pid}", {"main_branch": "main"})
    code, runner = api("POST", f"/projects/{pid}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code < 300, (code, runner)
    for name in (ALPHA, BETA, GAMMA):
        code, out = api("POST", f"/projects/{pid}/agents", {"name": name, "runner_id": runner["id"]})
        assert code < 300, (name, code, out)

    spec = f"/projects/{pid}/project"
    make_capability(spec, CAP, "Greeting", [("greet-word", "The greeting MUST start with \"Hello\"."),
                                            ("greet-name", "The greeting MUST name the person.")])
    make_capability(spec, CLOCK, "Clock", [("twelve-hour", "The clock MUST show the time in 12-hour form.")])
    for path, title in ((CMP_CAP, "Fold cmp"), (CMP_CAP_TWIN, "Fold cmp twin")):
        make_capability(spec, path, title, [("cmp-old", "The old thing MUST happen."),
                                            ("cmp-keep", "The kept thing MUST happen.")])
    make_capability(spec, HELD_CAP, "Held cap", [("held-req", "The held capability MUST stay.")])
    roadmap = make_roadmap(spec)
    ids = {}
    for path, title, reqs in (
        (LOUD, "Loud greeting", [("loud", "A greeting MUST be printable in capitals with --loud.")]),
        (FAREWELL, "Farewell", [("bye", "The program MUST say \"Bye, <name>\" with --bye.")]),
        (DEAD, "Old greeting idea", [("wave", "The greeting MUST wave.")]),
        (CMP, "Cmp change", [("cmp-new", "The new thing MUST happen.")]),
        (CMP_TWIN, "Cmp change twin", [("cmp-new", "The new thing MUST happen.")]),
        (NEWCAP, "New cap change", [("note", "A note MUST be kept.")]),
        (MARK, "Mark me", [("mark", "A mark MUST be kept.")]),
        (LIVE, "Live change", [("live", "Live work MUST be left alone.")]),
        (HELD, "Held change", [("held", "A held change MUST stay held.")]),
        (UNSLICED, "Unsliced", [("slice", "The first slice MUST greet.")]),
    ):
        ids[path] = make_change(spec, path, title, reqs)
    ids[PROPOSED] = make_change(spec, PROPOSED, "Proposed change",
                                [("prop", "A proposed change MUST wait.")], approved=False)
    # live-change gets an open task.
    code, task = api("POST", f"/projects/{pid}/tasks", {"title": "Live work on live-change",
                                                        "spec_document": LIVE, "assignee": BETA})
    assert code < 300, (code, task)
    for status in ("assigned", "in_progress"):
        api("PATCH", f"/projects/{pid}/tasks/{task['id']}", {"status": status})
    return root, pid, roadmap, task["id"], ids


def drive_fresh(args, root, pid, roadmap, live_task, ids):
    spec = f"/projects/{pid}/project"

    # 1 switch
    a = agents(pid)
    switch_known = all("can_admin_specs" in a.get(n, {}) for n in (ALPHA, BETA, GAMMA))
    ok_line("1 new agents read can_admin_specs false",
            switch_known and all(a[n]["can_admin_specs"] is False for n in (ALPHA, BETA, GAMMA)),
            str({n: a.get(n, {}).get("can_admin_specs", "absent") for n in (ALPHA, BETA, GAMMA)}))
    code, out = api("PATCH", f"/projects/{pid}/agents/{ALPHA}", {"can_admin_specs": True})
    switched = code == 200 and agents(pid).get(ALPHA, {}).get("can_admin_specs") is True
    ok_line("1 the operator turns alpha's switch on", switched, f"{code} {str(out)[:200]}")

    # 2 route
    code, out = api("POST", "/agent-actions/spec/documents/tidy", {"path": LOUD, "op": "fold"}, key="")
    ok_line("2 the agent tidy route exists (401 without a run credential)", code == 401, f"{code} {str(out)[:200]}")

    alpha_run, alpha = run_credential(pid, ALPHA)
    beta_run, beta = run_credential(pid, BETA)

    # 3 only the operator
    for agent_name, value in ((ALPHA, False), (BETA, True)):
        code, out = api("PATCH", f"/projects/{pid}/agents/{agent_name}", {"can_admin_specs": value}, key=alpha)
        ok_line(f"3 alpha's credential cannot set {agent_name}'s switch to {value}", code in (401, 403),
                f"{code} {str(out)[:200]}")
    a = agents(pid)
    ok_line("3 both switches are unchanged", a.get(ALPHA, {}).get("can_admin_specs") is True
            and a.get(BETA, {}).get("can_admin_specs") is False,
            str({n: a.get(n, {}).get("can_admin_specs", "absent") for n in (ALPHA, BETA)}))

    # 4 off
    before = state_hash(root, pid)
    attempts = (
        (LOUD, "fold", {"capability": CAP}),
        (FAREWELL, "create_capability", {"title": "Farewell", "fold_from": FAREWELL}),
        (CAP, "edit_capability", {"requirement": "greet-word", "statement": "It MUST say Hi.",
                                  "code_wins": {"cited": "greet.py"}}),
        (DEAD, "supersede", {"successor": CAP}),
        (DEAD, "clear_superseded", {}),
        (UNSLICED, "set_slice", {"roadmap": roadmap, "slice": "s1"}),
    )
    for path, op, fields in attempts:
        c, r = refusal(*tidy(beta, path, op, **fields))
        ok_line(f"4 beta (off) {op} is refused spec_admin_off, naming the switch and the operator",
                c == "spec_admin_off" and "operator" in (r or "").lower(), f"{c} {str(r)[:200]}")
    ok_line("4 every spec file and document row is unchanged", state_hash(root, pid) == before)

    # 5 reason
    before = state_hash(root, pid)
    c, r = refusal(*tidy(alpha, CMP, "fold", reason="", capability=CMP_CAP))
    ok_line("5 a fold with an empty reason is refused reason_required", c == "reason_required", f"{c} {str(r)[:200]}")
    c, r = refusal(*tidy(alpha, CMP, "fold", reason="   ", capability=CMP_CAP))
    ok_line("5 a blank reason is refused reason_required", c == "reason_required", f"{c} {str(r)[:200]}")
    ok_line("5 nothing changed", state_hash(root, pid) == before)

    # 6 live work
    before = state_hash(root, pid)
    for op, fields in (("fold", {"capability": CAP}), ("supersede", {"successor": CAP}),
                       ("set_slice", {"roadmap": roadmap, "slice": "s1"})):
        c, r = refusal(*tidy(alpha, LIVE, op, **fields))
        ok_line(f"6 {op} on a change with a task in progress is refused live_work naming the task",
                c == "live_work" and live_task in (r or ""), f"{c} {str(r)[:200]}")
    ok_line("6 nothing changed", state_hash(root, pid) == before)

    # 7 held
    for path in (HELD, HELD_CAP):
        code, out = api("POST", f"{spec}/documents/{path}/hold", {"note": "the operator keeps this"})
        ok_line(f"7 the operator holds {path.split('/')[2]}", code == 200, f"{code} {str(out)[:200]}")
    held = entry(pid, HELD).get("held")
    ok_line("7 the read carries held {at, note}", isinstance(held, dict) and held.get("at")
            and held.get("note") == "the operator keeps this", str(held))
    before = state_hash(root, pid)
    for path, op, fields in ((HELD, "fold", {"capability": CAP}), (HELD, "supersede", {"successor": CAP}),
                             (HELD, "set_slice", {"roadmap": roadmap, "slice": "s1"}),
                             (HELD_CAP, "edit_capability", {"requirement": "held-req", "statement": "It MUST go."})):
        c, r = refusal(*tidy(alpha, path, op, **fields))
        ok_line(f"7 {op} on a held document is refused document_held", c == "document_held", f"{c} {str(r)[:200]}")
    ok_line("7 the held documents are unchanged", state_hash(root, pid) == before)
    for path in (HELD, HELD_CAP):
        code, out = api("DELETE", f"{spec}/documents/{path}/hold")
        ok_line(f"7 the operator releases {path.split('/')[2]}", code in (200, 204), f"{code} {str(out)[:200]}")
    ok_line("7 released, it reads held null", entry(pid, HELD).get("held", "absent") is None,
            str(entry(pid, HELD).get("held", "absent")))
    c, r = refusal(*tidy(alpha, HELD, "fold", capability=HELD_CAP, reason="drive: fold after release"))
    ok_line("7 after release the fold succeeds", c is None, f"{c} {str(r)[:200]}")
    # Keep the batch at exactly five marked documents: clear the mark this fold set.
    c, r = refusal(*tidy(alpha, HELD, "clear_superseded", reason="drive: keep the batch at five"))
    ok_line("7 the fold's superseded mark can be cleared", c is None, f"{c} {str(r)[:200]}")

    # 8 the operator's acts
    before = state_hash(root, pid)
    for op in OPERATOR_OPS:
        c, r = refusal(*tidy(alpha, PROPOSED, op))
        ok_line(f"8 tidy op {op} is refused operators_act, naming it the operator's",
                c == "operators_act" and "operator" in (r or "").lower(), f"{c} {str(r)[:200]}")
    q = urllib.parse.quote(PROPOSED)
    for method, path, body in (
        ("POST", f"{spec}/documents/phase?path={q}&to=approved", {"reason": "agent", "approve_anyway": True}),
        ("POST", f"{spec}/documents/close-exploration?path={q}", None),
        ("POST", f"{spec}/documents/archive-batch", {"paths": [PROPOSED]}),
        ("POST", f"{spec}/documents/{PROPOSED}/hold", {"note": "agent"}),
        ("DELETE", f"{spec}/documents/{PROPOSED}/hold", None),
        ("POST", f"{spec}/tidy-acts/reviewed", {"all": True}),
        ("POST", f"{spec}/documents/{PROPOSED}/amendments/amend-none/accept", {}),
    ):
        code, out = api(method, path, body, key=alpha)
        ok_line(f"8 the operator route {method} {path.split('/project')[-1][:60]} refuses alpha's credential",
                code in (401, 403), f"{code} {str(out)[:150]}")
    identifier = (ids.get(PROPOSED) or {}).get("prop")
    if identifier:
        code, ev = api("POST", f"{spec}/spec/evidence", {"identifier": identifier, "summary": "drive",
                                                         "kind": "test_result", "document": PROPOSED})
        if code == 201:
            code, out = api("POST", f"/agent-actions/spec/evidence/{ev['id']}/decision",
                            {"decision": "accepted", "reason": "agent"}, key=alpha)
            ok_line("8 the switch does not let alpha decide evidence", code in (401, 403), f"{code} {str(out)[:150]}")
        before = state_hash(root, pid)  # the operator's evidence is not a document change
    ok_line("8 proposed-change is unchanged and still exploring",
            state_hash(root, pid) == before and entry(pid, PROPOSED).get("phase") == "exploring",
            entry(pid, PROPOSED).get("phase"))

    # 9 fold, against the operator's fold of the identical twin
    c, r = refusal(*tidy(alpha, CMP, "fold", capability=CMP_CAP, items=[{"key": "cmp-new"}], retire=["cmp-old"],
                         reason="drive: cmp-change is built; fold it"))
    ok_line("9 alpha folds cmp-change into fold-cmp, retiring cmp-old", c is None, f"{c} {str(r)[:200]}")
    code, out = api("POST", f"{spec}/documents/{CMP_TWIN}/fold",
                    {"into": CMP_CAP_TWIN, "requirements": [{"key": "cmp-new"}], "retire": ["cmp-old"],
                     "archive": False})
    ok_line("9 the operator folds the twin with archive off", code == 200, f"{code} {str(out)[:200]}")

    def shape(path):
        doc = on_disk(root, path)
        return (sorted((r.get("statement"), r.get("modal")) for r in doc.get("requirements", [])),
                sorted((c.get("given"), c.get("when"), c.get("then")) for c in doc.get("acceptance_criteria", [])))
    ok_line("9 the agent's fold carries exactly what the operator's fold carries",
            shape(CMP_CAP) == shape(CMP_CAP_TWIN) and bool(shape(CMP_CAP)[0]),
            f"{shape(CMP_CAP)} vs {shape(CMP_CAP_TWIN)}")
    ok_line("9 cmp-old is retired from fold-cmp", "cmp-old" not in
            [r.get("key") for r in on_disk(root, CMP_CAP).get("requirements", [])])
    e = entry(pid, CMP)
    sup = e.get("superseded") or {}
    ok_line("9 cmp-change stays approved and reads superseded by fold-cmp, by alpha",
            e.get("phase") == "approved" and sup.get("successor") == CMP_CAP and sup.get("by") == ALPHA,
            f"{e.get('phase')} {sup}")

    # 10 a new capability
    c, r = refusal(*tidy(alpha, NEWCAP, "create_capability", title="Notes", fold_from=NEWCAP,
                         reason="drive: new-cap-change belongs to no capability"))
    ok_line("10 alpha creates capability Notes folding new-cap-change", c is None, f"{c} {str(r)[:200]}")
    successor = (entry(pid, NEWCAP).get("superseded") or {}).get("successor")
    new = entry(pid, successor) if successor else {}
    ok_line("10 new-cap-change is superseded by the new capability", bool(successor) and new.get("kind") == "capability",
            f"{successor} {new.get('kind')}")
    ok_line("10 the new capability is current", new.get("phase") == "current", new.get("phase"))
    ok_line("10 it carries the folded requirement", "A note MUST be kept." in
            [r.get("statement") for r in on_disk(root, successor).get("requirements", [])] if successor else False)
    index = (root / "spec/index.json").read_text(encoding="utf-8") if (root / "spec/index.json").exists() else ""
    ok_line("10 it appears in the project's spec map", bool(successor) and successor in index)

    # 11 slice
    c, r = refusal(*tidy(alpha, UNSLICED, "set_slice", roadmap=roadmap, slice="s1",
                         reason="drive: unsliced specifies s1"))
    ok_line("11 alpha sets unsliced's roadmap slice", c is None, f"{c} {str(r)[:200]}")
    code, page = api("GET", f"{spec}/spec?path={urllib.parse.quote(roadmap)}")
    html = page.get("content", "") if isinstance(page, dict) else ""
    li = re.search(r'<li id="slice-s1".*?</li>', html, flags=re.S)
    ok_line("11 the roadmap shows s1 as specified by unsliced", bool(li) and UNSLICED in li.group(0),
            li.group(0)[:300] if li else "no slice-s1 item")

    # 12 mark and clear
    q = urllib.parse.quote(MARK)
    read_before = (entry(pid, MARK), api("GET", f"{spec}/spec?path={q}")[1])
    c, r = refusal(*tidy(alpha, MARK, "supersede", successor=CAP, reason="drive: greeting covers it"))
    ok_line("12 alpha marks mark-me superseded by greeting", c is None, f"{c} {str(r)[:200]}")
    sup = entry(pid, MARK).get("superseded") or {}
    ok_line("12 it reads superseded with agent, reason and successor",
            sup.get("by") == ALPHA and sup.get("reason") == "drive: greeting covers it"
            and sup.get("successor") == CAP and bool(sup.get("at")), str(sup))
    ok_line("12 its phase is still approved", entry(pid, MARK).get("phase") == "approved")
    code, out = api("POST", f"{spec}/documents/build?path={q}", {})
    ok_line("12 Build is refused while it is superseded", code >= 400, f"{code} {str(out)[:200]}")
    c, r = refusal(*tidy(alpha, MARK, "clear_superseded", reason="drive: marked by mistake"))
    ok_line("12 alpha clears the mark", c is None, f"{c} {str(r)[:200]}")
    after = (entry(pid, MARK), api("GET", f"{spec}/spec?path={q}")[1])
    strip = lambda e: {k: v for k, v in e.items() if k not in ("updated_at",)}  # noqa: E731
    ok_line("12 after clearing it reads exactly as before",
            strip(after[0]) == strip(read_before[0]) and after[1] == read_before[1],
            json.dumps({k: (read_before[0].get(k), after[0].get(k)) for k in set(read_before[0]) | set(after[0])
                        if read_before[0].get(k) != after[0].get(k)})[:300])

    # 13 code wins
    old = "The clock MUST show the time in 12-hour form."
    new_statement = "The clock MUST show the time in 24-hour form."
    c, r = refusal(*tidy(alpha, CLOCK, "edit_capability", requirement="twelve-hour", statement=new_statement,
                         code_wins={"cited": "clock.py"}, reason="drive: clock.py formats %H:%M"))
    ok_line("13 alpha rewrites twelve-hour to match clock.py", c is None, f"{c} {str(r)[:200]}")
    stmts = [x.get("statement") for x in on_disk(root, CLOCK).get("requirements", [])]
    ok_line("13 the capability carries the new statement", new_statement in stmts and old not in stmts, str(stmts))
    doc_id = (entry(pid, CLOCK).get("id") or "")
    events = base.ro("select kind, detail from spec_document_events where document_id=?", (doc_id,))
    ok_line("13 the old statement stays readable in its history", any(old in str(d) for _, d in events),
            f"{len(events)} events")
    acts = tidy_acts(pid) or []
    cw = next((x for x in acts if x.get("path") == CLOCK and x.get("code_wins")), {}).get("code_wins") or {}
    ok_line("13 the tidy list shows it as changed to match the code, naming the file",
            cw.get("before") == old and cw.get("after") == new_statement and "clock.py" in str(cw.get("cited"))
            and bool(cw.get("requirement")), str(cw))

    # 14-15 real turns, only once the switch exists
    if args.no_turns:
        print("(turns skipped: --no-turns)")
    elif not switched:
        ok_line("14 beta's real turn (skipped: the switch cannot be turned on)", False)
        ok_line("15 alpha's real turn (skipped: the switch cannot be turned on)", False)
    else:
        before = state_hash(root, pid)
        run_id, status = turn(pid, BETA, TIDY_PROMPT)
        ok_line("14 beta's turn ran", bool(run_id) and status == "completed", f"{run_id} {status}")
        ok_line("14 nothing changed after beta's turn", state_hash(root, pid) == before)
        ok_line("14 no tidy act is listed for beta", not [x for x in (tidy_acts(pid) or []) if x.get("agent") == BETA])

        run_id, status = turn(pid, ALPHA, TIDY_PROMPT)
        ok_line("15 alpha's turn ran", bool(run_id) and status == "completed", f"{run_id} {status}")
        mine = [x for x in (tidy_acts(pid) or []) if x.get("run_id") == run_id]
        ok_line("15 four acts are listed for alpha's turn, each with a reason",
                len(mine) >= 4 and all(x.get("agent") == ALPHA and (x.get("reason") or "").strip() for x in mine),
                json.dumps(mine)[:400])
        loud = entry(pid, LOUD).get("superseded") or {}
        ok_line("15 loud-greeting is folded into greeting and superseded by it",
                loud.get("successor") == CAP and "A greeting MUST be printable in capitals with --loud." in
                [x.get("statement") for x in on_disk(root, CAP).get("requirements", [])], str(loud))
        bye = (entry(pid, FAREWELL).get("superseded") or {}).get("successor")
        ok_line("15 farewell is folded into a new current capability in the spec map",
                bool(bye) and entry(pid, bye).get("phase") == "current"
                and bye in (root / "spec/index.json").read_text(encoding="utf-8"), str(bye))
        word = next((x for x in on_disk(root, CAP).get("requirements", []) if x.get("key") == "greet-word"), {})
        cwact = next((x for x in mine if x.get("path") == CAP and x.get("code_wins")), {})
        ok_line("15 greet-word now matches greet.py, recorded as code-wins citing greet.py",
                "Hi" in (word.get("statement") or "") and "greet.py" in str((cwact.get("code_wins") or {}).get("cited")),
                f"{word.get('statement')} {cwact.get('code_wins')}")
        dead = entry(pid, DEAD).get("superseded") or {}
        ok_line("15 old-greeting-idea is superseded by greeting, by alpha",
                dead.get("successor") == CAP and dead.get("by") == ALPHA, str(dead))

    # 16 listed
    acts = tidy_acts(pid)
    ok_line("16 GET /tidy-acts?reviewed=false answers a list", acts is not None)
    acts = acts or []
    fields = ("id", "act", "path", "agent", "run_id", "at", "reason", "code_wins")
    ok_line("16 at least five acts, each with id, act, path, agent, run_id, at and reason",
            len(acts) >= 5 and all(all(f in x for f in fields) and x["agent"] and x["run_id"] and x["reason"]
                                   for x in acts), f"{len(acts)} {json.dumps(acts[:2])[:300]}")
    ok_line("16 the token acts carry their run", any(x.get("run_id") == alpha_run for x in acts))
    if acts:
        one = acts[0]["id"]
        code, out = api("POST", f"{spec}/tidy-acts/reviewed", {"ids": [one]})
        ok_line("16 one act marked reviewed by id leaves the list",
                code == 200 and one not in [x.get("id") for x in (tidy_acts(pid) or [])], f"{code} {str(out)[:150]}")
    return beta_run


def page_steps(pid):
    from playwright.sync_api import sync_playwright

    marked = sorted(documents(pid, superseded=True))
    expected = sorted([CMP, NEWCAP, LOUD, FAREWELL, DEAD])
    ok_line("17 ?superseded=true lists exactly the five marked documents", marked == expected, str(marked))
    chosen = [CMP, NEWCAP, DEAD]
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (base.KEY, base.HUB, pid))
    with sync_playwright() as p:
        chromium = p.chromium.launch()
        page = chromium.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)

        # the switch in agent settings
        page.goto(f"{base.HUB}/?project={pid}&agent={GAMMA}&settings=access", wait_until="domcontentloaded")
        switch = page.get_by_test_id("agent-can-admin-specs")
        if not base.poll(lambda: switch.count() == 1, 15):
            switch = page.get_by_role("switch", name=re.compile(r"tidy|admin.*spec|spec.*admin", re.I))
        found = base.poll(lambda: switch.count() == 1, 10)
        ok_line("17 agent settings shows the spec-admin switch", found)
        if found:
            ok_line("17 it reads off", switch.get_attribute("aria-checked") in ("false", None)
                    and agents(pid)[GAMMA].get("can_admin_specs") is False)
            switch.click()
            ok_line("17 the operator's toggle turns it on",
                    base.poll(lambda: agents(pid)[GAMMA].get("can_admin_specs") is True, 10))
            switch.click()
            ok_line("17 and off again", base.poll(lambda: agents(pid)[GAMMA].get("can_admin_specs") is False, 10))

        # the superseded filter and the batch archive
        page.goto(f"{base.HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
        filt = page.get_by_test_id("spec-filter-superseded")
        ok_line("17 the spec tab offers a superseded filter", base.poll(lambda: filt.count() == 1, 20))
        if filt.count() == 1:
            filt.click()
            rows = page.get_by_test_id("spec-superseded-row")
            base.poll(lambda: rows.count() == len(expected), 15)
            shown = sorted(r.get_attribute("data-path") for r in rows.all())
            ok_line("17 the filter shows exactly the five", shown == expected, str(shown))
            ok_line("17 each row says who marked it and why",
                    all(ALPHA in (r.inner_text() or "") for r in rows.all()) and rows.count() > 0)
            for path in chosen:
                page.locator(f'[data-testid="spec-superseded-row"][data-path="{path}"]') \
                    .get_by_test_id("spec-superseded-select").check()
            page.get_by_test_id("spec-archive-selected").click()
            confirm = page.get_by_test_id("spec-archive-confirm")
            if base.poll(lambda: confirm.count() == 1, 3):
                confirm.click()
            done = base.poll(lambda: all(entry(pid, x).get("phase") == "archived" for x in chosen), 15)
            ok_line("17 one action archives the three selected", done,
                    str({x: entry(pid, x).get("phase") for x in chosen}))
            rest = [x for x in expected if x not in chosen]
            ok_line("17 the two others stay approved and marked",
                    all(entry(pid, x).get("phase") == "approved" and entry(pid, x).get("superseded") for x in rest),
                    str({x: (entry(pid, x).get("phase"), bool(entry(pid, x).get("superseded"))) for x in rest}))
        else:
            ok_line("17 the batch archive (skipped: no filter)", False)

        # the tidy list
        page.goto(f"{base.HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
        panel = page.get_by_test_id("spec-tidy-acts")
        if not base.poll(lambda: panel.count() == 1, 8):
            opener = page.get_by_test_id("spec-tidy-open")
            if opener.count():
                opener.first.click()
        ok_line("17 the spec tab shows the unreviewed tidy acts", base.poll(lambda: panel.count() == 1, 10))
        api_acts = tidy_acts(pid) or []
        rows = page.get_by_test_id("spec-tidy-act")
        base.poll(lambda: rows.count() == len(api_acts), 10)
        ok_line("17 one row per unreviewed act", rows.count() == len(api_acts) and len(api_acts) > 0,
                f"{rows.count()} vs {len(api_acts)}")
        by_id = {x["id"]: x for x in api_acts}
        texts = {r.get_attribute("data-act-id"): r for r in rows.all()}
        ok_line("17 each row shows its act's reason",
                bool(texts) and all(by_id.get(i, {}).get("reason", "\0") in (r.inner_text() or "") for i, r in texts.items()))
        cw = [r for r in rows.all() if r.get_attribute("data-code-wins") == "true"]
        ok_line("17 code-wins acts are marked apart, naming the file",
                bool(cw) and all(any(f in (r.inner_text() or "") for f in ("clock.py", "greet.py")) for r in cw)
                and len(cw) == len([x for x in api_acts if x.get("code_wins")]), f"{len(cw)} marked")
        before_events = base.ro("select count(*) from spec_document_events where kind='tidy'")[0][0]
        mark_all = page.get_by_test_id("spec-tidy-mark-all-reviewed")
        if mark_all.count():
            mark_all.click()
        ok_line("17 'mark all reviewed' empties the list", base.poll(lambda: tidy_acts(pid) == [], 10),
                str(len(tidy_acts(pid) or [])))
        ok_line("17 every tidy act is still in the documents' history",
                before_events > 0 and base.ro("select count(*) from spec_document_events where kind='tidy'")[0][0]
                == before_events, str(before_events))
        page.screenshot(path=str(base.TMP / "spec-tab.png"), full_page=True)
        chromium.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8121)
    parser.add_argument("--profile", default="d1108")
    parser.add_argument("--populated-db", default=str(TRIAL_DB))
    parser.add_argument("--no-turns", action="store_true")
    parser.add_argument("--skip-populated", action="store_true")
    args = parser.parse_args()
    if args.port in (8000, 8010):
        sys.exit("refusing to drive :8000 or :8010")

    # Outside any checkout: the Hub refuses a project directory nested in an AgentWeave task worktree.
    scratch = pathlib.Path(tempfile.gettempdir()) / "aw-drive1108-spec-admin" / args.profile / base.STAMP
    scratch.mkdir(parents=True, exist_ok=True)
    base.results = results

    if not args.skip_populated:
        try:
            populated(args.port + 1, scratch, pathlib.Path(args.populated_db))
        except (Exception, SystemExit) as exc:  # noqa: BLE001 -- a broken step is a failure, never a pass
            ok_line("A the populated-database step ran", False, repr(exc)[:300])

    base.PORT = args.port
    base.HUB = f"http://127.0.0.1:{args.port}"
    base.TMP = scratch / "hub"
    base.DB = base.TMP / "hub.db"
    try:
        proc = base.start_hub()
    except SystemExit as exc:
        ok_line("B the scratch Hub started", False, str(exc))
        sys.exit(1)
    try:
        root, pid, roadmap, live_task, ids = setup(scratch)
        print(f"project {pid} at {root}", flush=True)
        try:
            drive_fresh(args, root, pid, roadmap, live_task, ids)
        except Exception as exc:  # noqa: BLE001
            ok_line("B the fresh-project steps ran to the end", False, repr(exc)[:300])
        try:
            page_steps(pid)
        except Exception as exc:  # noqa: BLE001
            ok_line("17 the page steps ran to the end", False, repr(exc)[:300])
    except Exception as exc:  # noqa: BLE001
        ok_line("B setup", False, repr(exc)[:300])
    finally:
        base.stop_hub(proc)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed  (artefacts: {scratch})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
