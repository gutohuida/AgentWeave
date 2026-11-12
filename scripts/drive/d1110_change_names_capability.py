"""Acceptance drive for `a-change-names-the-capabilities-it-changes` (CNCC, spdoc-f214c91aac0e),
2026-11-12. Written, and recorded failing on master, before the build (task `drive`, CNCC-1).

Starts its own Hub from this checkout's source on a scratch port with a scratch database (never :8000,
never the trial :8010), serving the bundle in hub/hub/static/ui. Nothing in it depends on this
repository's layout (FR-9): both projects are fresh scratch git repositories outside any checkout.

Projects and fixtures, all made by the operator's routes unless a step says otherwise:

  main      capabilities alpha, gamma. Changes, each with one task, in this order:
              c-built     names alpha, approved first, its task approved (built)
              c-unbuilt   names alpha, approved second, its task left open
              c-exploring names alpha, never approved
              c-folded    names alpha, approved, built, folded into alpha by the operator (archive off)
              c-new       names a new capability titled 'Beta things', approved, built
            Agents: scribe (Haiku, authors in a real turn), tidier (Haiku, spec-admin switch on).
  second    capabilities p-one, p-two, p-three; changes x (p-one, exploring), y (p-one, approved),
            z (p-two, exploring): the seeded counts 2, 1, 0.

Steps, one PASS/FAIL line per check, exit 1 on any FAIL:

  1  waiting     alpha's waiting list, read through the operator's documents list, read_spec_document
                 include=waiting (tidier's run credential) and the capability's page, twice each:
                 exactly c-built, c-unbuilt, c-exploring in that order, built only on c-built, c-folded
                 absent, every read the same                                          (FR-5 ac-waiting)
  2  affects     second project: the spec list shows capability-waiting-count 2, 1, 0 for p-one, p-two,
                 p-three; the documents list rows carry waiting_count the same; read_spec_document
                 include=waiting on each returns the same changes as the app          (FR-6 ac-affects)
  3  author      scribe, in a real Haiku turn, writes the exploring change agent-change naming alpha with
                 submit_spec_document's `capabilities` argument. The read returns alpha; its page's
                 `change-capabilities` shows it; alpha's waiting list (route and page) now lists it
                                                                          (FR-1 ac-named, FR-9 ac-drive)
  4  named       the operator submits c-exploring naming alpha and creating 'Beta things': the agent read
                 returns both and the page's change-capabilities shows both             (FR-1 ac-named)
  5  unknown     the operator submits c-exploring naming spec/capabilities/nope/spec.json, then the second
                 project's p-one: refused capability_unknown naming the path; the file and the read are
                 unchanged                                                            (FR-2 ac-unknown)
  6  relink      the operator approves agent-change; tidier's tidy set_capabilities names gamma with a
                 reason: it names gamma, stays approved, its requirement digests are unchanged, the act is
                 in the operator's tidy list, alpha no longer lists it and gamma does (route and page)
                                                                     (FR-4 ac-relink, FR-9 ac-drive)
  7  fold-page   agent-change's task approved (built); the operator opens Fold on its page: `fold-target`
                 is gamma; the operator confirms; agent-change reads folded_into gamma, is on neither
                 waiting list, and its page still shows the capability it names
                                              (FR-7 ac-default-target, FR-8 ac-folded, FR-9 ac-drive)
  8  fixed       after the fold, the operator's PUT .../capabilities and tidier's set_capabilities are both
                 refused change_folded                                          (FR-4 ac-fixed-after-fold)
  9  agent-fold  tidier's tidy fold of c-built with no capability lands in alpha (folded_into alpha)
                                                                                (FR-7 ac-default-target)
  10 off-link    the operator folds c-offlink (names alpha, built, made after step 1) into gamma: it
                 succeeds and the fold's record carries fold_target_not_named          (FR-7 ac-off-link)
  11 create      the operator opens Fold on c-new: `fold-create-named` offers 'Beta things'; using it
                 creates a current capability titled 'Beta things' and folds c-new into it
                                                                                (FR-7 ac-create-named)

CONTRACT (the design's, spdoc-f214c91aac0e), and what the drive fixes where the design named a field but
not where it is read:

  payload            change-spec `capabilities: {"changes": [<capability path>], "creates": [{"title"}]}`,
                     written by PUT /projects/{p}/project/documents/{path}/content and by the agent's
                     submit_spec_document argument `capabilities` (same shape)
  reads              a capability's `waiting_changes: [{path, title, phase, built, first_approved_at}]` and
                     its list row's `waiting_count`; a change's `capabilities` and `folded_into`. The drive
                     accepts each from the documents list row (GET /projects/{p}/project/documents) or the
                     agent read (GET /agent-actions/spec/documents?path=..&include=full|waiting), wherever
                     it appears first, and compares the two where both carry it.
  routes             PUT /projects/{p}/project/documents/{path}/capabilities {changes, creates, reason}
                     -> the document, or 409 change_folded; agent tidy op set_capabilities {changes,
                     creates}; tidy fold with no capability
  codes              capability_unknown, change_folded; fold record key fold_target_not_named (looked for
                     in the fold's answer, the merge row and the tidy act)
  page handles       change page: change-capabilities; capability page: capability-waiting-list with rows
                     capability-waiting-row [data-path][data-built]; spec list: capability-waiting-count,
                     which the drive ties to its capability by its own data-path, or the nearest ancestor's
                     data-path, or the capability's title in its row; fold dialog: fold-target (value is
                     the selected path: an input's value, else data-value or value attribute) and
                     fold-create-named. Pages are opened at ?project=<p>&tab=spec(&document=<path>).

Per-check baseline: at the end the drive prints one line per covered criterion,
`check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`. A criterion is reached when
every observation it asserts on was made (the read answered, the page loaded, the turn completed); it
failed at its assertion when one of those observations was not what the criterion says. Setup lines
(SETUP ...) are not criteria.

    py -3.11 scripts/drive/d1110_change_names_capability.py --port 8131 --profile d1110
    py -3.11 scripts/drive/d1110_change_names_capability.py --port 8131 --profile d1110 --no-turns
"""

import argparse
import json
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
SCRIBE, TIDIER = "scribe", "tidier"

ALPHA = "spec/capabilities/alpha/spec.json"
GAMMA = "spec/capabilities/gamma/spec.json"
C_BUILT = "spec/changes/c-built/spec.json"
C_UNBUILT = "spec/changes/c-unbuilt/spec.json"
C_EXPLORING = "spec/changes/c-exploring/spec.json"
C_FOLDED = "spec/changes/c-folded/spec.json"
C_NEW = "spec/changes/c-new/spec.json"
C_OFFLINK = "spec/changes/c-offlink/spec.json"
AGENT_CHANGE = "spec/changes/agent-change/spec.json"
NOPE = "spec/capabilities/nope/spec.json"
P1 = "spec/capabilities/p-one/spec.json"
P2 = "spec/capabilities/p-two/spec.json"
P3 = "spec/capabilities/p-three/spec.json"
X, Y, Z = ("spec/changes/x-change/spec.json", "spec/changes/y-change/spec.json",
           "spec/changes/z-change/spec.json")
BETA_TITLE = "Beta things"

results = []
# criterion -> {"reached": bool, "failed": bool, "details": [str]}
criteria = {}
ORDER = ("ac-named", "ac-unknown", "ac-relink", "ac-fixed-after-fold", "ac-waiting", "ac-affects",
         "ac-default-target", "ac-off-link", "ac-create-named", "ac-folded", "ac-drive")


def ok_line(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    return bool(ok)


def setup_line(name, ok, detail=""):
    return ok_line("SETUP " + name, ok, detail)


def covered(criterion, name, reached, ok=False, detail=""):
    """One assertion of a criterion. Not reached is reported as such and never counted as a pass."""
    c = criteria.setdefault(criterion, {"reached": True, "failed": False, "details": []})
    if not reached:
        c["reached"] = False
        c["details"].append(f"not reached: {name}")
        return ok_line(f"{criterion} {name} (not reached)", False, detail)
    if not ok:
        c["failed"] = True
        c["details"].append(f"{name}: {str(detail)[:120]}")
    return ok_line(f"{criterion} {name}", ok, detail)


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
    if isinstance(body, dict):
        return body.get("code") or f"http-{code}", str(body.get("reason") or body.get("message") or body)
    return f"http-{code}", str(body)[:300]


def tidy(token, path, op, reason="drive: tidy", **fields):
    return api("POST", "/agent-actions/spec/documents/tidy", {"path": path, "op": op, "reason": reason, **fields},
               key=token)


def documents(pid):
    code, out = api("GET", f"/projects/{pid}/project/documents")
    rows = out.get("documents", out) if isinstance(out, dict) else out
    return {d["path"]: d for d in rows} if code == 200 and isinstance(rows, list) else None


def row(pid, path):
    return (documents(pid) or {}).get(path) or {}


def agent_read(token, path, include="full"):
    q = urllib.parse.urlencode({"path": path, "include": include})
    return api("GET", f"/agent-actions/spec/documents?{q}", key=token)


def find_key(obj, key):
    """The first value under `key` anywhere in a JSON answer, or the sentinel `missing`."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = find_key(v, key)
            if found is not MISSING:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_key(v, key)
            if found is not MISSING:
                return found
    return MISSING


MISSING = object()


def waiting_paths(entries):
    if not isinstance(entries, list):
        return None
    return [e.get("path") for e in entries if isinstance(e, dict)]


def waiting_via_list(pid, cap):
    """(answered, waiting_changes or None) from the operator's documents list."""
    rows = documents(pid)
    if rows is None:
        return False, None
    w = (rows.get(cap) or {}).get("waiting_changes")
    return True, w if isinstance(w, list) else None


def waiting_via_agent(token, cap):
    """(answered, waiting_changes or None, http code) from read_spec_document include=waiting."""
    code, out = agent_read(token, cap, include="waiting")
    w = find_key(out, "waiting_changes") if code == 200 else MISSING
    return True, (w if isinstance(w, list) else None), code


def operator_waiting(pid, cap):
    """The operator's reading of a capability's waiting list: the documents-list row when it carries one,
    else the capability page's read (GET /project/spec), wherever `waiting_changes` appears."""
    answered, w = waiting_via_list(pid, cap)
    if w is not None:
        return answered, w
    code, out = api("GET", f"/projects/{pid}/project/spec?path={urllib.parse.quote(cap)}")
    found = find_key(out, "waiting_changes") if code == 200 else MISSING
    return answered or code == 200, (found if isinstance(found, list) else None)


def change_field(pid, token, path, field):
    """A change's `field` from its list row, else from the agent read; MISSING when neither has it."""
    r = row(pid, path)
    if field in r:
        return r[field]
    code, out = agent_read(token, path)
    return find_key(out, field) if code == 200 else MISSING


def on_disk(root, path):
    try:
        return json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def file_bytes(root, path):
    try:
        return (root / path).read_bytes()
    except OSError:
        return b""


def digests(pid, path):
    return sorted(base.ro(
        "select r.key, r.digest from spec_requirements r join spec_documents d on d.id = r.document_id"
        " where d.project_id=? and d.path=? and r.state='active'", (pid, path)))


# ------------------------------------------------------------------ fixtures

def capability(title, reqs):
    return {
        "schema_version": 1, "kind": "capability", "title": title,
        "requirements": [{"key": k, "statement": s, "modal": "MUST"} for k, s in reqs],
        "acceptance_criteria": [{"key": f"{k}-c", "requirement": k, "given": "the code", "when": "run",
                                 "then": s} for k, s in reqs],
        "algorithms": [],
    }


def change(title, reqs, changes=(), creates=()):
    payload = {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"{title}.", "problem": f"Drive fixture: {title}.",
        "scope": {"in_scope": [title], "non_goals": ["anything else"]},
        "requirements": [{"key": k, "statement": s, "modal": "MUST"} for k, s in reqs],
        "acceptance_criteria": [{"key": f"{k}-c", "requirement": k, "given": "the code", "when": "run",
                                 "then": s, "how_to_check": "run it", "checked_by": "agent"} for k, s in reqs],
        "tasks": [{"key": "t", "title": f"Build {title}", "description": "Fixture task.",
                   "requirements": [reqs[0][0]], "files": ["README.md"]}],
        "algorithms": [], "design": "Fixture.", "evidence": {"checked": ["fixture"], "limits": []},
        "lifecycle": "", "open_questions": [], "delivery": {"mode": "none"},
    }
    if changes or creates:
        payload["capabilities"] = {"changes": list(changes), "creates": [{"title": t} for t in creates]}
    return payload


def approve(spec, path):
    q = urllib.parse.quote(path)
    _, read = api("GET", f"{spec}/spec?path={q}")
    version = read.get("content_version") if isinstance(read, dict) else None
    api("POST", f"{spec}/documents/close-exploration?path={q}")
    return api("POST", f"{spec}/documents/phase?path={q}&to=approved",
               {"reason": "drive", "approve_anyway": True, "content_version": version})


def make_capability(spec, path, title, reqs):
    code, out = api("POST", f"{spec}/documents", {"path": path, "title": title, "kind": "capability"})
    assert code in (200, 201), (path, code, out)
    code, out = api("POST", f"{spec}/documents/{path}/merge", {"payload": capability(title, reqs)})
    assert code == 200, (path, code, out)


def put_change(spec, path, payload):
    """Writes a change. On a Hub that refuses the `capabilities` field the write is retried without it,
    so the steps after still run and fail at their own assertions; the refusal is printed."""
    code, out = api("PUT", f"{spec}/documents/{path}/content", {"document": payload})
    if code != 200 and "capabilities" in payload:
        setup_line(f"{path.split('/')[2]} written with its capabilities", False, f"{code} {str(out)[:200]}")
        payload = {k: v for k, v in payload.items() if k != "capabilities"}
        code, out = api("PUT", f"{spec}/documents/{path}/content", {"document": payload})
    assert code == 200, (path, code, out)


def make_change(spec, path, title, reqs, changes=(), creates=(), approved=True):
    code, out = api("POST", f"{spec}/documents", {"path": path, "title": title, "kind": "change-spec"})
    assert code in (200, 201), (path, code, out)
    put_change(spec, path, change(title, reqs, changes, creates))
    if approved:
        code, out = approve(spec, path)
        assert code == 200, (path, code, out)


def build_done(pid, path):
    """Every task of the change approved: the drive's stand-in for a finished build (scratch DB only)."""
    db = sqlite3.connect(base.DB.as_posix(), timeout=30)
    n = db.execute("update tasks set status='approved' where project_id=? and spec_document_id="
                   "(select id from spec_documents where project_id=? and path=?)", (pid, pid, path)).rowcount
    db.commit()
    db.close()
    return n


def open_project(scratch, name, files):
    root = scratch / name
    root.mkdir(parents=True)
    for f, text in files.items():
        (root / f).write_text(text, encoding="utf-8")
    base.git(root, "init", "-q", "-b", "main")
    base.git(root, "add", *files)
    base.git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": name})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    api("PATCH", f"/projects/{pid}", {"main_branch": "main"})
    return root, pid


def setup(scratch):
    root, pid = open_project(scratch, "main-proj", {"README.md": "# names\n\nChecked by d1110.\n"})
    code, runner = api("POST", f"/projects/{pid}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code < 300, (code, runner)
    for name in (SCRIBE, TIDIER):
        code, out = api("POST", f"/projects/{pid}/agents", {"name": name, "runner_id": runner["id"]})
        assert code < 300, (name, code, out)
    code, out = api("PATCH", f"/projects/{pid}/agents/{TIDIER}", {"can_admin_specs": True})
    setup_line("tidier's spec-admin switch is on", code == 200, f"{code} {str(out)[:150]}")

    spec = f"/projects/{pid}/project"
    make_capability(spec, ALPHA, "Alpha", [("alpha-one", "Alpha MUST hold.")])
    make_capability(spec, GAMMA, "Gamma", [("gamma-one", "Gamma MUST hold.")])
    make_change(spec, C_BUILT, "C built", [("cb", "Built MUST stay built.")], changes=[ALPHA])
    make_change(spec, C_UNBUILT, "C unbuilt", [("cu", "Unbuilt MUST wait.")], changes=[ALPHA])
    make_change(spec, C_EXPLORING, "C exploring", [("ce", "Exploring MUST explore.")], changes=[ALPHA],
                approved=False)
    make_change(spec, C_FOLDED, "C folded", [("cf", "Folded MUST be folded.")], changes=[ALPHA])
    make_change(spec, C_NEW, "C new", [("cn", "New things MUST be new.")], creates=[BETA_TITLE])
    setup_line("c-built's task approved", build_done(pid, C_BUILT) >= 1)
    setup_line("c-folded's task approved", build_done(pid, C_FOLDED) >= 1)
    setup_line("c-new's task approved", build_done(pid, C_NEW) >= 1)
    code, out = api("POST", f"{spec}/documents/{C_FOLDED}/fold", {"into": ALPHA, "archive": False})
    setup_line("the operator folds c-folded into alpha (archive off)", code == 200, f"{code} {str(out)[:200]}")

    root2, pid2 = open_project(scratch, "second-proj", {"README.md": "# second\n"})
    spec2 = f"/projects/{pid2}/project"
    for path, title in ((P1, "P one"), (P2, "P two"), (P3, "P three")):
        make_capability(spec2, path, title, [(title.lower().replace(" ", "-"), f"{title} MUST hold.")])
    make_change(spec2, X, "X change", [("x", "X MUST happen.")], changes=[P1], approved=False)
    make_change(spec2, Y, "Y change", [("y", "Y MUST happen.")], changes=[P1])
    make_change(spec2, Z, "Z change", [("z", "Z MUST happen.")], changes=[P2], approved=False)
    return root, pid, root2, pid2


def run_credential(pid, agent):
    """A running Run row for `agent` in the drive's own database, and its plaintext credential."""
    sys.path.insert(0, str(base.REPO / "hub"))
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{base.DB.as_posix()}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.agent_auth import hash_run_token
    from hub.db.models import Run

    token = "aw_run_" + secrets.token_urlsafe(24)
    run_id = f"run-d1110-{agent}-" + secrets.token_hex(4)
    engine = create_engine(f"sqlite:///{base.DB.as_posix()}")
    with Session(engine) as session:
        session.add(Run(id=run_id, project_id=pid, agent=agent, status="running", turn_depth=0,
                        capability_token_hash=hash_run_token(token)))
        session.commit()
    engine.dispose()
    return run_id, token


def turn(pid, agent, message, spec_document):
    db = sqlite3.connect(base.DB.as_posix(), timeout=30)
    db.execute("update runs set status='completed' where agent=? and id like 'run-d1110-%' and status='running'",
               (agent,))
    db.commit()
    db.close()
    code, res = api("POST", f"/projects/{pid}/agent/trigger",
                    {"agent": agent, "message": message, "spec_document": spec_document})
    if not (code < 300 and isinstance(res, dict) and res.get("run_id")):
        return None, f"{code} {res}"
    run_id = res["run_id"]
    live = ("running", "queued", "starting", "pending")
    base.poll(lambda: base.ro("select status from runs where id=?", (run_id,))[0][0] not in live, 900)
    return run_id, base.ro("select status from runs where id=?", (run_id,))[0][0]


AUTHOR_PROMPT = f"""Write the change document spec/changes/agent-change/spec.json with your submit_spec_document
tool, in one call, and do not ask the operator anything. Use exactly:

- path: spec/changes/agent-change/spec.json, kind: change-spec, title: "Alpha gets louder"
- summary: "Alpha says its word louder."  problem: "Alpha is too quiet."
- scope: {{"in_scope": ["louder alpha"], "non_goals": ["anything else"]}}
- requirements: [{{"key": "louder", "statement": "Alpha MUST say its word in capitals.", "modal": "MUST"}}]
- acceptance_criteria: [{{"key": "louder-c", "requirement": "louder", "given": "alpha", "when": "it speaks",
  "then": "the word is in capitals", "how_to_check": "run it", "checked_by": "agent"}}]
- tasks: [{{"key": "t", "title": "Make alpha louder", "description": "Capitalise alpha's word.",
  "requirements": ["louder"], "files": ["README.md"]}}]
- design: "Upper-case the word."  delivery: {{"mode": "none", "reasons": {{"mode": "a fixture"}}}}
- capabilities: {{"changes": ["{ALPHA}"], "creates": []}}  -- this change changes the existing capability
  {ALPHA}; pass it as the `capabilities` argument.

Then report what the call returned. Do not change any file yourself and do nothing else."""


# ------------------------------------------------------------------ page helpers

def seed_script(pid):
    return ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (base.KEY, base.HUB, pid))


def open_doc(page, pid, path):
    page.goto(f"{base.HUB}/?project={pid}&tab=spec&document={urllib.parse.quote(path)}",
              wait_until="domcontentloaded")
    loaded = base.poll(lambda: page.get_by_test_id("spec-page").count() >= 1
                       or page.get_by_test_id("spec-phase").count() >= 1, 30)
    page.wait_for_timeout(1500)  # the document's own reads settle after the frame
    return loaded


def page_waiting(page, pid, cap):
    """(loaded, [(path, built)] or None) from the capability page's waiting list."""
    loaded = open_doc(page, pid, cap)
    lst = page.get_by_test_id("capability-waiting-list")
    if not base.poll(lambda: lst.count() >= 1, 10):
        return loaded, None
    rows = page.get_by_test_id("capability-waiting-row")
    base.poll(lambda: rows.count() >= 0, 2)
    return loaded, [(r.get_attribute("data-path"), r.get_attribute("data-built")) for r in rows.all()]


def page_change_capabilities(page, pid, path):
    loaded = open_doc(page, pid, path)
    el = page.get_by_test_id("change-capabilities")
    if not base.poll(lambda: el.count() >= 1, 10):
        return loaded, None
    return loaded, el.first.inner_text()


def fold_target(page):
    el = page.get_by_test_id("fold-target")
    if not base.poll(lambda: el.count() >= 1, 10):
        return None
    return el.first.evaluate(
        "e => (('value' in e && e.value) ? e.value : null) || e.getAttribute('data-value') || e.getAttribute('value')")


COUNTS_JS = """() => Array.from(document.querySelectorAll('[data-testid="capability-waiting-count"]')).map(e => {
  const anc = e.closest('[data-path]');
  const row = e.closest('li, tr, [role="row"], a, button') || e.parentElement;
  return {path: e.getAttribute('data-path') || (anc ? anc.getAttribute('data-path') : null),
          text: (e.innerText || e.textContent || '').trim(), row: row ? (row.innerText || '') : ''};
})"""


# ------------------------------------------------------------------ the steps

def expected_waiting_ok(paths_built):
    """c-built, c-unbuilt, c-exploring in order; built only on the first."""
    want = [C_BUILT, C_UNBUILT, C_EXPLORING]
    return [p for p, _ in paths_built] == want and [b for _, b in paths_built] == [True, False, False]


def norm_built(v):
    return v is True or str(v).lower() == "true"


def drive(args, root, pid, root2, pid2):
    from playwright.sync_api import sync_playwright

    spec = f"/projects/{pid}/project"
    _, tidier = run_credential(pid, TIDIER)
    with sync_playwright() as p:
        chromium = p.chromium.launch()
        page = chromium.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed_script(pid))

        # 1 waiting -----------------------------------------------------------------------------
        reads = []
        for i in (1, 2):
            answered, w = operator_waiting(pid, ALPHA)
            covered("ac-waiting", f"read {i}: the operator's read carries alpha's waiting_changes", answered,
                    w is not None, str(w)[:200])
            got = [(e.get("path"), norm_built(e.get("built"))) for e in (w or [])]
            covered("ac-waiting", f"read {i}: route order is c-built, c-unbuilt, c-exploring; built only first; "
                    "c-folded absent", answered, expected_waiting_ok(got), str(got))
            answered, aw, code = waiting_via_agent(tidier, ALPHA)
            agot = [(e.get("path"), norm_built(e.get("built"))) for e in (aw or [])]
            covered("ac-waiting", f"read {i}: read_spec_document include=waiting answers the same list", answered,
                    aw is not None and agot == got and expected_waiting_ok(agot), f"{code} {agot}")
            loaded, pw = page_waiting(page, pid, ALPHA)
            pgot = [(pth, norm_built(b)) for pth, b in (pw or [])]
            covered("ac-waiting", f"read {i}: alpha's page lists the same rows", loaded,
                    pw is not None and pgot == got and expected_waiting_ok(pgot), str(pgot))
            reads.append((got, agot, pgot))
        covered("ac-waiting", "both reads are identical", True, reads[0] == reads[1] and bool(reads[0][0]),
                str(reads))
        # c-offlink, for step 10, is made only now so it is not on the list step 1 reads.
        make_change(spec, C_OFFLINK, "C offlink", [("co", "Off-link MUST fold anywhere.")], changes=[ALPHA])
        setup_line("c-offlink's task approved", build_done(pid, C_OFFLINK) >= 1)

        # 2 affects (second project) --------------------------------------------------------------
        seeded = {P1: [X, Y], P2: [Z], P3: []}
        rows2 = documents(pid2)
        code2, out2 = api("GET", f"/projects/{pid2}/project/documents")
        setup_line("the second project's documents list answers", rows2 is not None, f"{code2} {str(out2)[:200]}")
        for cap, want in seeded.items():
            r = (rows2 or {}).get(cap, {})
            covered("ac-affects", f"{cap.split('/')[2]} row carries waiting_count {len(want)}", rows2 is not None,
                    r.get("waiting_count") == len(want), str(r.get("waiting_count", "absent")))
        page2 = chromium.new_page(viewport={"width": 1400, "height": 900})
        page2.add_init_script(seed_script(pid2))
        page2.goto(f"{base.HUB}/?project={pid2}&tab=spec", wait_until="domcontentloaded")
        loaded = base.poll(lambda: page2.get_by_text("P one").count() >= 1, 30)
        base.poll(lambda: page2.get_by_test_id("capability-waiting-count").count() >= 3, 10)
        counts = page2.evaluate(COUNTS_JS) if loaded else []
        titles = {P1: "P one", P2: "P two", P3: "P three"}
        for cap, want in seeded.items():
            shown = [c["text"] for c in counts if c["path"] == cap or (not c["path"] and titles[cap] in c["row"])]
            covered("ac-affects", f"the spec list shows {len(want)} for {cap.split('/')[2]}", loaded,
                    shown == [str(len(want))] or (len(shown) == 1 and re.search(rf"\b{len(want)}\b", shown[0] or "")),
                    str(shown))
        # The agent read on the second project, with a credential minted there.
        _, cred2 = run_credential(pid2, "reader2") if _make_agent(pid2, "reader2") else (None, "")
        for cap, want in seeded.items():
            answered, aw, code = waiting_via_agent(cred2, cap)
            _, ow = operator_waiting(pid2, cap)
            covered("ac-affects", f"include=waiting on {cap.split('/')[2]} returns the same changes as the app",
                    answered, aw is not None and ow is not None
                    and sorted(waiting_paths(aw)) == sorted(want) == sorted(waiting_paths(ow)),
                    f"{code} agent={waiting_paths(aw)} app={waiting_paths(ow)}")
        page2.close()

        # 3 author (real turn) ---------------------------------------------------------------------
        code, out = api("POST", f"{spec}/documents", {"path": AGENT_CHANGE, "title": "Alpha gets louder",
                                                      "kind": "change-spec"})
        setup_line("the operator opens agent-change for scribe", code in (200, 201), f"{code} {str(out)[:150]}")
        turn_ok = False
        if args.no_turns:
            print("(turn skipped: --no-turns; the operator writes agent-change instead)")
            put_change(spec, AGENT_CHANGE, change("Alpha gets louder", [("louder", "Alpha MUST say it louder.")],
                                                  changes=[ALPHA]))
            turn_ok = True
        else:
            run_id, status = turn(pid, SCRIBE, AUTHOR_PROMPT, AGENT_CHANGE)
            turn_ok = bool(run_id) and status == "completed"
            setup_line("scribe's turn ran", turn_ok, f"{run_id} {status}")
        reqs = [r.get("key") for r in on_disk(root, AGENT_CHANGE).get("requirements", [])]
        written = "louder" in reqs
        setup_line("agent-change carries its requirement", written, str(reqs))
        named = change_field(pid, tidier, AGENT_CHANGE, "capabilities")
        covered("ac-drive", "the agent's change reads as naming alpha", turn_ok and written,
                isinstance(named, dict) and named.get("changes") == [ALPHA], str(named if named is not MISSING
                                                                                  else "absent"))
        loaded, text = page_change_capabilities(page, pid, AGENT_CHANGE)
        covered("ac-drive", "its page's change-capabilities shows alpha", loaded and written,
                text is not None and ("alpha" in text.lower()), str(text)[:200])
        _, w = operator_waiting(pid, ALPHA)
        _, aw, code = waiting_via_agent(tidier, ALPHA)
        loaded, pw = page_waiting(page, pid, ALPHA)
        covered("ac-drive", "alpha's waiting list (route, agent read and page) lists agent-change",
                loaded and written, AGENT_CHANGE in (waiting_paths(w) or []) and AGENT_CHANGE in
                (waiting_paths(aw) or []) and AGENT_CHANGE in [pth for pth, _ in (pw or [])],
                f"route={waiting_paths(w)} agent={waiting_paths(aw)} page={pw}")

        # 4 named ------------------------------------------------------------------------------------
        payload = change("C exploring", [("ce", "Exploring MUST explore.")], changes=[ALPHA], creates=[BETA_TITLE])
        code, out = api("PUT", f"{spec}/documents/{C_EXPLORING}/content", {"document": payload})
        covered("ac-named", "c-exploring is submitted naming alpha and creating 'Beta things'", True, code == 200,
                f"{code} {str(out)[:200]}")
        named = change_field(pid, tidier, C_EXPLORING, "capabilities")
        covered("ac-named", "reading it returns both", True,
                isinstance(named, dict) and named.get("changes") == [ALPHA]
                and [c.get("title") for c in named.get("creates") or []] == [BETA_TITLE],
                str(named if named is not MISSING else "absent"))
        loaded, text = page_change_capabilities(page, pid, C_EXPLORING)
        covered("ac-named", "its page shows both", loaded, text is not None and "alpha" in text.lower()
                and BETA_TITLE.lower() in text.lower(), str(text)[:200])

        # 5 unknown ----------------------------------------------------------------------------------
        for bad in (NOPE, P1):
            before = (file_bytes(root, C_EXPLORING), change_field(pid, tidier, C_EXPLORING, "capabilities"))
            code, out = api("PUT", f"{spec}/documents/{C_EXPLORING}/content",
                            {"document": change("C exploring", [("ce", "Exploring MUST explore.")], changes=[bad])})
            c, r = refusal(code, out)
            covered("ac-unknown", f"naming {bad} is refused capability_unknown, naming the path", True,
                    c == "capability_unknown" and bad in (r or ""), f"{code} {c} {str(r)[:200]}")
            after = (file_bytes(root, C_EXPLORING), change_field(pid, tidier, C_EXPLORING, "capabilities"))
            covered("ac-unknown", f"after naming {bad} the stored document is unchanged", True, before == after)

        # 6 relink -----------------------------------------------------------------------------------
        code, out = approve(spec, AGENT_CHANGE)
        approved = code == 200
        setup_line("the operator approves agent-change", approved, f"{code} {str(out)[:200]}")
        before = digests(pid, AGENT_CHANGE)
        c, r = refusal(*tidy(tidier, AGENT_CHANGE, "set_capabilities", changes=[GAMMA], creates=[],
                             reason="drive: agent-change changes gamma, not alpha"))
        covered("ac-relink", "tidier's set_capabilities to gamma succeeds", approved, c is None, f"{c} {str(r)[:200]}")
        named = change_field(pid, tidier, AGENT_CHANGE, "capabilities")
        covered("ac-relink", "agent-change names gamma", approved,
                isinstance(named, dict) and named.get("changes") == [GAMMA], str(named if named is not MISSING
                                                                                 else "absent"))
        covered("ac-relink", "it stays approved with the same requirement digests", approved,
                row(pid, AGENT_CHANGE).get("phase") == "approved" and digests(pid, AGENT_CHANGE) == before
                and bool(before), f"{row(pid, AGENT_CHANGE).get('phase')} {before} -> {digests(pid, AGENT_CHANGE)}")
        code, acts = api("GET", f"{spec}/tidy-acts?reviewed=false")
        acts = acts.get("acts", acts) if isinstance(acts, dict) else acts
        covered("ac-relink", "the act is in the operator's tidy list with its reason", code == 200,
                any(isinstance(a, dict) and a.get("act") == "set_capabilities" and a.get("path") == AGENT_CHANGE
                    and "gamma" in (a.get("reason") or "") for a in (acts if isinstance(acts, list) else [])),
                str(acts)[:300])
        _, wa = operator_waiting(pid, ALPHA)
        _, wg = operator_waiting(pid, GAMMA)
        covered("ac-relink", "alpha no longer lists it and gamma does (route)", approved,
                wa is not None and wg is not None and AGENT_CHANGE not in waiting_paths(wa)
                and AGENT_CHANGE in waiting_paths(wg), f"alpha={waiting_paths(wa)} gamma={waiting_paths(wg)}")
        la, pa = page_waiting(page, pid, ALPHA)
        lg, pg = page_waiting(page, pid, GAMMA)
        covered("ac-drive", "after the relink the pages follow: alpha does not list it, gamma does", la and lg,
                pa is not None and pg is not None and AGENT_CHANGE not in [x for x, _ in pa]
                and AGENT_CHANGE in [x for x, _ in pg], f"alpha={pa} gamma={pg}")

        # 7 fold in the page -------------------------------------------------------------------------
        built = build_done(pid, AGENT_CHANGE) >= 1
        setup_line("agent-change's task approved", built)
        loaded = open_doc(page, pid, AGENT_CHANGE)
        opener = page.get_by_test_id("fold-open")
        has_fold = base.poll(lambda: opener.count() >= 1, 15)
        setup_line("agent-change's page offers Fold", has_fold)
        target = None
        if has_fold:
            opener.first.click()
            target = fold_target(page)
        covered("ac-default-target", "the fold dialog opens on agent-change's named capability (gamma)",
                loaded and has_fold, target == GAMMA, str(target))
        covered("ac-drive", "the fold dialog opens on the named capability", loaded and has_fold, target == GAMMA,
                str(target))
        folded = False
        if has_fold:
            confirm = page.get_by_test_id("fold-confirm")
            if target != GAMMA:
                # Today's dialog: pick gamma by hand so the steps after the fold still run.
                pick = page.get_by_test_id("fold-target")
                if pick.count():
                    pick.select_option(GAMMA)
            if base.poll(lambda: confirm.count() >= 1 and confirm.is_enabled(), 15):
                confirm.click()
                folded = base.poll(lambda: base.ro(
                    "select count(*) from spec_document_merges m join spec_documents d on d.id = m.change_document_id"
                    " where d.project_id=? and d.path=?", (pid, AGENT_CHANGE))[0][0] >= 1, 20)
        setup_line("the operator's fold of agent-change landed", folded)
        into = change_field(pid, tidier, AGENT_CHANGE, "folded_into")
        covered("ac-folded", "agent-change reads folded_into gamma", folded, into == GAMMA,
                str(into if into is not MISSING else "absent"))
        _, wa = operator_waiting(pid, ALPHA)
        _, wg = operator_waiting(pid, GAMMA)
        covered("ac-folded", "agent-change is on no waiting list", folded,
                wa is not None and wg is not None and AGENT_CHANGE not in waiting_paths(wa) + waiting_paths(wg),
                f"alpha={waiting_paths(wa)} gamma={waiting_paths(wg)}")
        _, wf = operator_waiting(pid, ALPHA)
        into_f = change_field(pid, tidier, C_FOLDED, "folded_into")
        covered("ac-folded", "c-folded (folded at setup) reads folded_into alpha and is on no list", True,
                into_f == ALPHA and wf is not None and C_FOLDED not in waiting_paths(wf),
                f"{into_f if into_f is not MISSING else 'absent'} {waiting_paths(wf)}")
        la, pa = page_waiting(page, pid, ALPHA)
        lg, pg = page_waiting(page, pid, GAMMA)
        lc, text = page_change_capabilities(page, pid, AGENT_CHANGE)
        covered("ac-drive", "after the fold the change is on no page's list and its page names gamma",
                folded and la and lg and lc, pa is not None and pg is not None
                and AGENT_CHANGE not in [x for x, _ in pa + pg] and text is not None and "gamma" in text.lower(),
                f"alpha={pa} gamma={pg} page={str(text)[:120]}")

        # 8 fixed after the fold ---------------------------------------------------------------------
        code, out = api("PUT", f"{spec}/documents/{AGENT_CHANGE}/capabilities",
                        {"changes": [ALPHA], "creates": [], "reason": "drive: after the fold"})
        c, r = refusal(code, out)
        covered("ac-fixed-after-fold", "the operator's PUT .../capabilities is refused 409 change_folded", folded,
                code == 409 and c == "change_folded", f"{code} {c} {str(r)[:150]}")
        c, r = refusal(*tidy(tidier, AGENT_CHANGE, "set_capabilities", changes=[ALPHA], creates=[],
                             reason="drive: after the fold"))
        covered("ac-fixed-after-fold", "tidier's set_capabilities is refused change_folded", folded,
                c == "change_folded", f"{c} {str(r)[:150]}")
        named = change_field(pid, tidier, AGENT_CHANGE, "capabilities")
        covered("ac-fixed-after-fold", "it still names gamma", folded,
                isinstance(named, dict) and named.get("changes") == [GAMMA], str(named if named is not MISSING
                                                                                 else "absent"))

        # 9 the agent's fold with no capability -------------------------------------------------------
        c, r = refusal(*tidy(tidier, C_BUILT, "fold", reason="drive: c-built is built; fold it where it names"))
        covered("ac-default-target", "tidier's fold of c-built with no capability succeeds", True, c is None,
                f"{c} {str(r)[:200]}")
        into = change_field(pid, tidier, C_BUILT, "folded_into")
        covered("ac-default-target", "it lands in alpha", True, into == ALPHA,
                str(into if into is not MISSING else "absent"))

        # 10 off-link --------------------------------------------------------------------------------
        code, out = api("POST", f"{spec}/documents/{C_OFFLINK}/fold", {"into": GAMMA, "archive": False})
        covered("ac-off-link", "the operator folds c-offlink (names alpha) into gamma", True, code == 200,
                f"{code} {str(out)[:200]}")
        merge = base.ro(
            "select m.* from spec_document_merges m join spec_documents d on d.id = m.change_document_id"
            " where d.project_id=? and d.path=?", (pid, C_OFFLINK))
        events = base.ro("select e.kind, e.detail from spec_document_events e join spec_documents d"
                         " on d.id = e.document_id where d.project_id=? and d.path=?", (pid, C_OFFLINK))
        flagged = (find_key(out, "fold_target_not_named") is True
                   or any("fold_target_not_named" in str(m) for m in merge)
                   or any("fold_target_not_named" in str(e) for e in events))
        covered("ac-off-link", "the fold's record carries fold_target_not_named", code == 200, flagged,
                f"answer={str(out)[:120]} merges={len(merge)}")

        # 11 create the named capability --------------------------------------------------------------
        loaded = open_doc(page, pid, C_NEW)
        opener = page.get_by_test_id("fold-open")
        has_fold = base.poll(lambda: opener.count() >= 1, 15)
        setup_line("c-new's page offers Fold", has_fold)
        offer = None
        if has_fold:
            opener.first.click()
            offer = page.get_by_test_id("fold-create-named")
            base.poll(lambda: offer.count() >= 1, 10)
        offered = offer is not None and offer.count() >= 1 and BETA_TITLE in (offer.first.inner_text() or "")
        covered("ac-create-named", "the dialog offers to create 'Beta things'", loaded and has_fold, offered,
                offer.first.inner_text()[:150] if offer is not None and offer.count() else "absent")
        created = None
        if offered:
            offer.first.click()
            confirm = page.get_by_test_id("fold-confirm")
            if base.poll(lambda: confirm.count() >= 1 and confirm.is_enabled(), 5):
                confirm.click()
            base.poll(lambda: change_field(pid, tidier, C_NEW, "folded_into") not in (MISSING, None), 20)
            created = change_field(pid, tidier, C_NEW, "folded_into")
        cap_row = row(pid, created) if isinstance(created, str) else {}
        covered("ac-create-named", "one step creates a current capability 'Beta things' holding c-new",
                loaded and has_fold, cap_row.get("kind") == "capability" and cap_row.get("phase") == "current"
                and cap_row.get("title") == BETA_TITLE, f"{created} {cap_row.get('title')} {cap_row.get('phase')}")
        page.screenshot(path=str(base.TMP / "last-page.png"), full_page=True)
        chromium.close()


def _make_agent(pid, name):
    code, runner = api("POST", f"/projects/{pid}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    if code >= 300:
        return False
    code, _ = api("POST", f"/projects/{pid}/agents", {"name": name, "runner_id": runner["id"]})
    return code < 300


def baseline():
    print("\ndrive baseline (one line per covered criterion):")
    for key in ORDER:
        c = criteria.get(key)
        if not c:
            continue
        detail = "; ".join(c["details"])[:280] or "every assertion passed"
        print(f"check {key}: reached={'yes' if c['reached'] else 'no'} "
              f"failed_at_assertion={'yes' if c['reached'] and c['failed'] else 'no'} -- {detail}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8131)
    parser.add_argument("--profile", default="d1110")
    parser.add_argument("--no-turns", action="store_true", help="the operator writes agent-change, no Haiku turn")
    args = parser.parse_args()
    if args.port in (8000, 8010):
        sys.exit("refusing to drive :8000 or :8010")

    # Outside any checkout: the Hub refuses a project directory nested in an AgentWeave task worktree.
    scratch = pathlib.Path(tempfile.gettempdir()) / "aw-drive1110-names-capability" / args.profile / base.STAMP
    scratch.mkdir(parents=True, exist_ok=True)
    base.results = results
    base.PORT = args.port
    base.HUB = f"http://127.0.0.1:{args.port}"
    base.TMP = scratch / "hub"
    base.DB = base.TMP / "hub.db"
    try:
        proc = base.start_hub()
    except SystemExit as exc:
        ok_line("SETUP the scratch Hub started", False, str(exc))
        sys.exit(1)
    try:
        root, pid, root2, pid2 = setup(scratch)
        print(f"projects {pid} at {root}, {pid2} at {root2}", flush=True)
        try:
            drive(args, root, pid, root2, pid2)
        except Exception as exc:  # noqa: BLE001 -- a broken step is a failure, never a pass
            ok_line("SETUP the steps ran to the end", False, repr(exc)[:300])
    except Exception as exc:  # noqa: BLE001
        ok_line("SETUP fixtures", False, repr(exc)[:300])
    finally:
        base.stop_hub(proc)
    baseline()
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed  (artefacts: {scratch})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
