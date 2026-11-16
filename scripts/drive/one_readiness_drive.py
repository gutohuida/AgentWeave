"""Acceptance drive for `ready-means-the-same-thing-to-the-author-and-the-operator` (RMSTA-1),
2026-11-16: the seven acceptance criteria that only a running Hub, the agent tool and a browser can
answer, written failing first, before RMSTA-2 (one readiness), RMSTA-3 (steps follow content) and
RMSTA-4 (acknowledged gaps in the app) are built. A later task runs it green and fixes only the drive.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default :8023
and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), on 127.0.0.1, and refuses a port something
already answers on. Never :8000 or :8010. No real agent turn is spent: the "agent" calls its tool
routes with a run credential minted in the scratch database (the Hub tests' pattern); were a turn
needed, it would bind Haiku.

Two change documents in a throwaway git repository on `main`:

  Gappy  "Gappy route"  a custom journey step `threat-model` after requirements, the document at
                        step intake (size large): a skipped custom step; a criterion with no check; two
                        tasks sharing app.py with no order; an unreviewed amendment (a proposal event
                        written into the scratch database, as an author's proposal after approval is);
  Clean  "Clean route"  a complete document at the journey's end with nothing missing, so its save
                        says ready; later given exactly one acknowledged and one open gap.

The checks (one drive_baseline line each; the first failing assertion decides the line):
  ac-same-list     the save result, the operator's Check and Approve's 409 list the same gaps by
                   (code, place) and the same notes;
  ac-verdict       Clean saves ready_to_approve true; Check shows no gap; Approve completes;
  ac-verdict-false a document whose only gap is amendments_unreviewed saves ready_to_approve false;
  ac-ack           the author acknowledges a gap with a reason (recorded with the agent's name and a
                   time); an empty reason is refused; so is a refusal (an unknown field is one);
  ac-operator-ack  the operator acknowledges an open gap from Check; Check shows it acknowledged by
                   the operator and the verdict updates;
  ac-ack-visible   the document page, Check and the rendered document show the acknowledged gap with
                   reason, author and time, apart from the open one. Screenshots of page and Check;
  ac-approve-acks  a document whose only gaps are acknowledged is approved without the 'approve
                   anyway' stop, and the dialog lists the acknowledged gaps. Screenshot of Approve.

The contract the drive fixes for the build (RMSTA-2 and RMSTA-4 may rename it and the drive's fixing
task then follows them, not the behaviour):
  * agent:     POST /api/v1/agent-actions/spec/documents/acknowledge {path, code, where, reason}
               answers 200/201 with the recorded `{code, where, reason, by, at}`; no reason or a
               refusal answers 4xx naming why;
  * operator:  POST /api/v1/projects/{id}/project/documents/acknowledge?path=<p> {code, where, reason}
               answers 200 and records the operator as `by`;
  * every list that reports gaps (the save's, Check's, Approve's 409 `detail.warnings`) leaves an
    acknowledged gap out of `warnings` and lists it under `acknowledged`, each
    `{code, where, reason, by, at}`; the save's `ready_to_approve` and Check's `ready` are true
    exactly when nothing blocks and no gap is open; notes are listed under `notes`;
  * Approve with only acknowledged gaps answers 200, with the acknowledged gaps under
    `acknowledged`;
  * the page: `[data-testid=acknowledged-gaps-list]` (the header notice) with one
    `[data-testid=acknowledged-gap-<code>]` per acknowledged gap, its text holding the reason, author
    and time; Check on the page offers `[data-testid=acknowledge-open]` (inside `check-acknowledge`),
    then `acknowledge-reason` and `acknowledge-submit`; the rendered document (GET
    /project/spec?path=) holds `acknowledged`.

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/one-readiness-drive/<HHMMSS>/.

    py -3.11 scripts/drive/one_readiness_drive.py                  # own Hub on :8023
    py -3.11 scripts/drive/one_readiness_drive.py --only ac-ack
    py -3.11 scripts/drive/one_readiness_drive.py --self-test      # the drive's own logic, no Hub
"""

import argparse
import json
import os
import pathlib
import secrets
import socket
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
PORT = int(os.environ.get("AW_DRIVE_PORT") or 8023)
HUB = f"http://127.0.0.1:{PORT}"
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-one-readiness" / STAMP
DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or SCRATCH / "hub.db")
KEY = "aw_live_" + secrets.token_hex(16)
AGENT = "scribe"
GAPPY = "spec/changes/gappy-route/spec.json"
CLEAN = "spec/changes/clean-route/spec.json"
ORDER = ["ac-same-list", "ac-verdict", "ac-verdict-false", "ac-ack", "ac-operator-ack",
         "ac-ack-visible", "ac-approve-acks"]
# What is told and never gates, whichever list carries it.
NOTES = {"import_not_approved", "delivery_unanswered", "delivery_flow_incomplete",
         "capability_unnamed", "roadmap_slice_unclaimed",
         # advisory since they were written: told on a save and a Check, never a gate
         "test_only_task", "reviewer_undeclared", "recommended_people"}
OUT = [REPO / "testbed" / "one-readiness-drive" / STAMP]

checks = {}  # key -> (reached, failed, detail)


class Setup(Exception):
    """Something the drive depends on could not be arranged."""


def record(key, reached, ok, detail):
    checks[key] = (reached, reached and not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


# --------------------------------------------------------------------------- pure logic (self-tested)


def gap_keys(items):
    """The (code, place) of each entry of a list of findings, notes excluded."""
    return sorted({(i.get("code"), i.get("where")) for i in items or []
                   if isinstance(i, dict) and i.get("code") not in NOTES})


def note_codes(*lists):
    """The codes of the notes any of the lists carries: under `notes`, or a note code among findings."""
    return sorted({i.get("code") for items in lists for i in items or []
                   if isinstance(i, dict) and i.get("code") in NOTES})


def open_gaps(listed):
    """Gaps a report leaves open: blocking plus warnings, as (code, place)."""
    return gap_keys((listed.get("blocking") or []) + (listed.get("warnings") or []))


def lists_agree(named):
    """`(ok, detail)`: `named` is {who: {"gaps": [...], "notes": [...]}}; every who lists the same."""
    gaps = {who: sorted(map(tuple, v["gaps"])) for who, v in named.items()}
    notes = {who: sorted(v["notes"]) for who, v in named.items()}
    same = len({json.dumps(g) for g in gaps.values()}) == 1 and len({json.dumps(n) for n in notes.values()}) == 1
    return same, "; ".join(f"{who}: gaps={gaps[who]} notes={notes[who]}" for who in named)


def acked(items, code):
    """The acknowledged entry for `code`, if the list holds one."""
    return next((a for a in items or [] if isinstance(a, dict) and a.get("code") == code), None)


def ack_complete(entry):
    """An acknowledgement carries its reason, who made it and when."""
    return bool(entry) and all(entry.get(k) for k in ("reason", "by", "at"))


def self_test():
    save = {"blocking": [], "warnings": [{"code": "criterion_without_check", "where": "c[0]"},
                         {"code": "delivery_unanswered", "where": "delivery"}]}
    cases = [
        (gap_keys(save["warnings"]), [("criterion_without_check", "c[0]")]),
        (note_codes(save["warnings"], [{"code": "capability_unnamed"}]),
         ["capability_unnamed", "delivery_unanswered"]),
        (open_gaps(save), [("criterion_without_check", "c[0]")]),
        (lists_agree({"a": {"gaps": [("x", "y")], "notes": []},
                      "b": {"gaps": [("x", "y")], "notes": []}})[0], True),
        (lists_agree({"a": {"gaps": [("x", "y")], "notes": []},
                      "b": {"gaps": [], "notes": []}})[0], False),
        (lists_agree({"a": {"gaps": [], "notes": ["n"]}, "b": {"gaps": [], "notes": []}})[0], False),
        (ack_complete({"code": "c", "reason": "r", "by": "scribe", "at": "t"}), True),
        (ack_complete({"code": "c", "reason": "", "by": "scribe", "at": "t"}), False),
        (ack_complete(None), False),
        (acked([{"code": "c"}], "c"), {"code": "c"}),
        (acked(None, "c"), None),
        (len(ORDER), 7),
        (len(set(ORDER)), 7),
    ]
    bad = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    for i, got, want in bad:
        print(f"self-test case {i}: got {got!r}, wanted {want!r}")
    print("self-test:", "PASS" if not bad else "FAIL", f"({len(cases) - len(bad)}/{len(cases)})")
    return not bad


# --------------------------------------------------------------------------- the Hub


def api(method, path, body=None, timeout=120, key=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + path if raw else HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + (key or KEY), "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode() or "null"
            try:
                return response.status, json.loads(text)
            except ValueError:
                return response.status, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:6000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return 0, str(exc)


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def poll(fn, secs=15.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render; try again
            pass
        time.sleep(0.25)
    return False


def port_answers():
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def start_hub(log_path):
    DB.parent.mkdir(parents=True, exist_ok=True)
    # Nothing of the shell's own Hub may reach the scratch one (HUB_URL is the operator's :8000 when
    # this runs inside an agent turn).
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if not poll(lambda: api("GET", "/projects")[0] == 200, 120):
        proc.kill()
        sys.exit(f"hub did not come up; see {log_path}")
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


# --------------------------------------------------------------------------- fixtures


def payload(title, complete=True):
    """A change document. `complete` holds a check on its criterion and one task; otherwise the
    criterion names no check and two tasks share app.py with no order between them."""
    criterion = {"key": "ac-answers", "requirement": "answers", "given": "the service is up",
                 "when": "GET /ping is called", "then": "it answers 200 with a short body"}
    if complete:
        criterion.update({"how_to_check": "curl /ping and read the status", "checked_by": "agent"})
    tasks = [{"key": "route", "title": "Add the route", "description": "Add it to app.py.",
              "requirements": ["answers"], "depends_on": [], "files": ["app.py"], "from": None,
              "reviewer": None}]
    for task in tasks:
        task.update({"builder": AGENT, "builder_reason": "A one-line route suits any builder.",
                     "checker": "second", "checker_reason": "A second agent checks it."})
    if not complete:
        tasks.append({"key": "docs", "title": "Document it", "description": "Also app.py.",
                      "requirements": ["answers"], "depends_on": [], "files": ["app.py"],
                      "from": None, "reviewer": None})
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"{title}: GET answers 200 with a short body.",
        "problem": "The service has no route a caller can use to see that it is up.",
        "scope": {"in_scope": ["One route"], "non_goals": ["Authentication"]},
        "requirements": [{"key": "answers", "modal": "MUST", "rationale": None, "party": None,
                          "statement": "The route MUST answer 200 with a short body."}],
        "acceptance_criteria": [criterion], "tasks": tasks, "algorithms": [],
        "design": "One handler.", "evidence": {"checked": ["app.py has no routes"], "limits": []},
        "lifecycle": "", "open_questions": [],
        "delivery": {"mode": "none", "agent": None, "reviewer": None,
                     "stop_when_queue_empties": False, "stop_at": None, "cron": "*/5 * * * *"},
        "capabilities": {"changes": [], "creates": [{"title": "Ping"}]},
    }


def run_credential(pid, agent):
    """A running Run row for `agent` in the scratch database, and its plaintext credential."""
    sys.path.insert(0, str(REPO / "hub"))
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.agent_auth import hash_run_token
    from hub.db.models import Run

    token = "aw_run_" + secrets.token_urlsafe(24)
    engine = create_engine(f"sqlite:///{DB.as_posix()}")
    with Session(engine) as session:
        session.add(Run(id="run-one-readiness-" + secrets.token_hex(4), project_id=pid, agent=agent,
                        status="running", turn_depth=0, capability_token_hash=hash_run_token(token)))
        session.commit()
    engine.dispose()
    return token


def propose_amendment(document_id, pid):
    """An author's proposed amendment the operator has not reviewed: the event the Hub writes when an
    author proposes one to an approved document (`spec_amendments.PROPOSED_EVENT`)."""
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    con.execute(
        "insert into spec_document_events (id, document_id, project_id, kind, actor_kind, actor, "
        "origin, run_id, detail, created_at) values (?,?,?,?,?,?,?,?,?,datetime('now'))",
        ("evt-" + secrets.token_hex(6), document_id, pid, "amendment_proposed", "agent", AGENT,
         "submission", None,
         json.dumps({"id": "amd-" + secrets.token_hex(4), "op": "add_criterion", "target": "ac-extra",
                     "reason": "drive", "how_to_check": "drive"})))
    con.commit()
    con.close()


class Ctx:
    """What the checks share."""

    def __init__(self):
        self.pid = self.base = self.token = None
        self.gappy_id = self.clean_id = None

    def agent(self, method, path, body=None):
        return api(method, "/agent-actions" + path, body, key=self.token)

    def save(self, path, doc):
        return self.agent("POST", "/spec/documents", {"path": path, "document": doc})

    def check(self, path):
        return api("POST", f"{self.base}/project/documents/check?path={urllib.parse.quote(path)}")

    def view(self, path):
        _, listed = api("GET", f"{self.base}/project/documents")
        return next((x for x in (listed or {}).get("documents", []) if x.get("path") == path), {})

    def approve(self, path, **extra):
        """The operator's Approve: the phase move, naming the version Check read."""
        q = urllib.parse.quote(path)
        _, checked = self.check(path)
        version = checked.get("content_version") if isinstance(checked, dict) else None
        return api("POST", f"{self.base}/project/documents/phase?path={q}&to=approved",
                   {"reason": "drive", "content_version": version, **extra})

    def ack_agent(self, path, code, where, reason):
        return self.agent("POST", "/spec/documents/acknowledge",
                          {"path": path, "code": code, "where": where, "reason": reason})

    def ack_operator(self, path, code, where, reason):
        return api("POST", f"{self.base}/project/documents/acknowledge?path={urllib.parse.quote(path)}",
                   {"code": code, "where": where, "reason": reason})


def detail_of(out):
    """A 4xx body's `detail` as a dict, whatever shape the answer came in."""
    if isinstance(out, dict):
        detail = out.get("detail", out)
        return detail if isinstance(detail, dict) else {"message": str(detail)}
    return {"message": str(out)}


def arrange(ctx):
    root = SCRATCH / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "app.py").write_text("# routes go here\n", encoding="utf-8")
    git(root, "add", "app.py")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": "onereadiness"})
    if code not in (200, 201):
        raise Setup(f"opening the project: {code} {str(project)[:300]}")
    ctx.pid = project["id"]
    ctx.base = f"/projects/{ctx.pid}"
    # A custom step after requirements: a document at intake skips it however complete it is.
    steps = [{"key": k} for k in ("intake", "requirements")]
    steps.append({"key": "threat-model", "title": "Threat model", "sizes": ["large"],
                  "instructions": "List what could go wrong, then ask to advance."})
    steps += [{"key": k} for k in ("requirements-and-acceptance", "acceptance", "approach", "tasks",
                                   "build")]
    code, out = api("PUT", f"{ctx.base}/project/journey", {"steps": steps})
    if code != 200:
        raise Setup(f"the journey: {code} {str(out)[:300]}")
    for path, title in ((GAPPY, "Gappy route"), (CLEAN, "Clean route")):
        code, out = api("POST", f"{ctx.base}/project/documents",
                        {"title": title, "kind": "change-spec", "path": path})
        if code != 201:
            raise Setup(f"creating {path}: {code} {str(out)[:300]}")
    ctx.token = run_credential(ctx.pid, AGENT)
    code, out = ctx.save(GAPPY, payload("Gappy route", complete=False))
    if code != 200:
        raise Setup(f"the author's save of {GAPPY}: {code} {str(out)[:300]}")
    q = urllib.parse.quote(GAPPY)
    for body in ({"size": "large", "step": "intake", "reason": "drive setup"},):
        code, out = api("POST", f"{ctx.base}/project/documents/journey?path={q}", body)
        if code != 200:
            raise Setup(f"moving {GAPPY} to intake: {code} {str(out)[:300]}")
    api("POST", f"{ctx.base}/project/documents/close-exploration?path={q}")
    ctx.gappy_id = ctx.view(GAPPY).get("id")
    propose_amendment(ctx.gappy_id, ctx.pid)
    # Clean: the journey's built-in steps only, at its end (no custom step to skip).
    code, out = ctx.save(CLEAN, payload("Clean route"))
    if code != 200:
        raise Setup(f"the author's save of {CLEAN}: {code} {str(out)[:300]}")
    ctx.clean_id = ctx.view(CLEAN).get("id")
    # Small, so the large-only custom step is not on its journey, and left at intake: a complete
    # document whose save says ready while its step is behind (Approve lists steps_skipped).
    cq = urllib.parse.quote(CLEAN)
    code, out = api("POST", f"{ctx.base}/project/documents/journey?path={cq}",
                    {"size": "small", "step": "intake", "reason": "drive setup"})
    if code != 200:
        raise Setup(f"sizing {CLEAN}: {code} {str(out)[:300]}")
    api("POST", f"{ctx.base}/project/documents/close-exploration?path={cq}")


# --------------------------------------------------------------------------- the checks


def check_same_list(ctx):
    code, saved = ctx.save(GAPPY, payload("Gappy route", complete=False))
    saved = saved if isinstance(saved, dict) else {}
    checked_code, checked = ctx.check(GAPPY)
    checked = checked if isinstance(checked, dict) else {}
    approve_code, approve = ctx.approve(GAPPY)
    detail = detail_of(approve)
    reached = code == 200 and checked_code == 200 and approve_code == 409
    named = {
        "save": {"gaps": gap_keys(saved.get("blocking", []) + saved.get("warnings", [])),
                 "notes": note_codes(saved.get("warnings"), saved.get("notes"))},
        "check": {"gaps": gap_keys(checked.get("blocking", []) + checked.get("warnings", [])),
                  "notes": note_codes(checked.get("warnings"), checked.get("notes"))},
        "approve": {"gaps": gap_keys(detail.get("warnings")),
                    "notes": note_codes(detail.get("warnings"), detail.get("notes"),
                                        detail.get("approval_notes"))},
    }
    ok, text = lists_agree(named)
    seen = {c for c, _ in named["approve"]["gaps"]}
    expected = {"criterion_without_check", "steps_skipped", "amendments_unreviewed"}
    record("ac-same-list", reached, ok and expected <= seen,
           f"statuses save={code} check={checked_code} approve={approve_code} "
           f"{str(approve)[:200]}; {text}")


def check_verdict(ctx):
    code, saved = ctx.save(CLEAN, payload("Clean route"))
    saved = saved if isinstance(saved, dict) else {}
    checked_code, checked = ctx.check(CLEAN)
    checked = checked if isinstance(checked, dict) else {}
    approve_code, approve = ctx.approve(CLEAN)
    open_here = open_gaps(checked)
    reached = code == 200 and checked_code == 200
    ok = (saved.get("ready_to_approve") is True and not open_here and checked.get("ready") is True
          and approve_code == 200)
    record("ac-verdict", reached, ok,
           f"save ready_to_approve={saved.get('ready_to_approve')} warnings={open_gaps(saved)}; "
           f"Check ready={checked.get('ready')} open={open_here}; Approve {approve_code} "
           f"{str(detail_of(approve))[:200]}")


def check_verdict_false(ctx):
    """A document whose only gap is amendments_unreviewed: Clean's twin, one proposal unreviewed."""
    path = "spec/changes/amended-route/spec.json"
    code, out = api("POST", f"{ctx.base}/project/documents",
                    {"title": "Amended route", "kind": "change-spec", "path": path})
    if code != 201:
        raise Setup(f"creating {path}: {code} {str(out)[:300]}")
    code, saved = ctx.save(path, payload("Amended route"))
    if code != 200:
        raise Setup(f"saving {path}: {code} {str(saved)[:300]}")
    api("POST", f"{ctx.base}/project/documents/journey?path={urllib.parse.quote(path)}",
        {"size": "small", "step": "build", "reason": "drive setup"})
    propose_amendment(ctx.view(path).get("id"), ctx.pid)
    code, saved = ctx.save(path, payload("Amended route"))
    saved = saved if isinstance(saved, dict) else {}
    only = open_gaps(saved) == [("amendments_unreviewed", "amendments")]
    checked_code, checked = ctx.check(path)
    gaps = open_gaps(checked) if isinstance(checked, dict) else []
    record("ac-verdict-false", code == 200 and checked_code == 200 and "amendments_unreviewed"
           in {c for c, _ in gaps}, saved.get("ready_to_approve") is False,
           f"save ready_to_approve={saved.get('ready_to_approve')} (only gap listed by the save: {only}); "
           f"Check lists {gaps}")


def check_ack(ctx):
    code, out = ctx.ack_agent(GAPPY, "criterion_without_check", "acceptance_criteria[0]",
                              "The check is a manual curl the operator runs; not worth a script.")
    done = isinstance(out, dict) and ack_complete(out.get("acknowledgement") or out)
    empty_code, empty = ctx.ack_agent(GAPPY, "criterion_without_check", "acceptance_criteria[0]", "")
    refusal_code, refusal = ctx.ack_agent(GAPPY, "unknown_field", "requirements", "meant to")
    reached = ("criterion_without_check", "acceptance_criteria[0]") in open_gaps(ctx.check(GAPPY)[1])
    ok = (done and (out.get("acknowledgement") or out).get("by") == AGENT
          and 400 <= empty_code < 500 and "reason" in json.dumps(empty).lower()
          and 400 <= refusal_code < 500 and "refus" in json.dumps(refusal).lower())
    record("ac-ack", reached, ok,
           f"acknowledge {code} {str(out)[:160]}; empty reason {empty_code} {str(empty)[:100]}; "
           f"a refusal {refusal_code} {str(refusal)[:100]}")


def check_operator_ack(ctx):
    before_code, before = ctx.check(GAPPY)
    before = before if isinstance(before, dict) else {}
    code, out = ctx.ack_operator(GAPPY, "amendments_unreviewed", "amendments",
                                 "Reviewed in the amendments panel; fine as proposed.")
    after_code, after = ctx.check(GAPPY)
    after = after if isinstance(after, dict) else {}
    entry = acked(after.get("acknowledged"), "amendments_unreviewed")
    still_open = ("amendments_unreviewed", "amendments") in open_gaps(after)
    reached = before_code == 200 and ("amendments_unreviewed", "amendments") in open_gaps(before)
    ok = ack_complete(entry) and entry.get("by") == "operator" and not still_open
    record("ac-operator-ack", reached, ok,
           f"open before {open_gaps(before)}; acknowledge {code} {str(out)[:120]}; after: open "
           f"{open_gaps(after)} acknowledged={after.get('acknowledged')}")


def ack_text(page):
    """The acknowledged gaps the page shows: each gap's code (from its testid) and its text."""
    parts = []
    count = page.locator("[data-testid=spec-notice-count]")
    if count.count() and not page.locator("[data-testid=spec-notices]").count():
        count.first.click()  # the header's notices open from their count
        page.wait_for_timeout(500)
    for item in page.locator("[data-testid^=acknowledged-gap-]:not([data-testid=acknowledged-gaps-list]):not([data-testid=acknowledged-gaps]):not([data-testid=acknowledged-gap-meta])").all():
        parts.append(item.get_attribute("data-testid").replace("acknowledged-gap-", "") + " " + item.inner_text())
    if not parts and os.environ.get("AW_DRIVE_DEBUG"):
        pop = page.locator("[data-testid=spec-notices]")
        print("DEBUG notice-count", count.count(), "pop", pop.count(), (pop.inner_text()[:600] if pop.count() else ""))
    return " | ".join(parts)


def browser_checks(ctx, only):
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, ctx.pid))
    OUT[0].mkdir(parents=True, exist_ok=True)
    shot = str(OUT[0] / "shot")
    # Gappy has one acknowledged gap (the author's) and, after the operator's, a second; leave one open.
    rows = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)

        def open_document(path, title):
            """Open the document by its row's title and return True only once the header shows it."""
            page.goto(f"{HUB}/?project={ctx.pid}&tab=spec", wait_until="domcontentloaded")
            row = page.locator(".aw-sp-list-row").filter(has=page.locator(".aw-sp-list-name", has_text=title))
            if not poll(lambda: row.count() > 0, 8):
                trigger = page.locator("[data-slot=switcher]")
                if trigger.count():
                    trigger.first.click()
                poll(lambda: row.count() > 0, 8)
            if row.count():
                row.first.click()
            return poll(lambda: page.locator(".aw-sp-title").count() > 0
                        and page.locator(".aw-sp-title").first.inner_text().strip() == title, 15)

        if not only or "ac-ack-visible" in only:
            opened = open_document(GAPPY, "Gappy route")
            page.wait_for_timeout(1500)
            shown = opened and page.get_by_role("button", name="Check", exact=True).count() > 0
            page_ack = ack_text(page)
            page.screenshot(path=shot + "_page.png", full_page=True)
            check_button = page.get_by_role("button", name="Check", exact=True)
            if check_button.count():
                check_button.click()
                page.wait_for_timeout(3000)
            check_ack_text = ack_text(page)
            open_text = " | ".join(page.locator(".aw-sp-finding").all_inner_texts())
            page.screenshot(path=shot + "_check.png", full_page=True)
            code, rendered = api("GET", f"{ctx.base}/project/spec?path={GAPPY}")
            rendered = json.dumps(rendered) if not isinstance(rendered, str) else rendered
            rows["visible"] = (shown, page_ack, check_ack_text, open_text, rendered)
        if not only or "ac-approve-acks" in only:
            ack_codes = []
            for code_, where in (("criterion_without_check", "acceptance_criteria[0]"),
                                 ("steps_skipped", "step"), ("amendments_unreviewed", "amendments"),
                                 ("undeclared_task_files", "tasks")):
                ack_codes.append(ctx.ack_operator(GAPPY, code_, where, "Drive: acknowledged so Approve has none open.")[0])
            for finding in ctx.check(GAPPY)[1].get("warnings", []):
                ack_codes.append(ctx.ack_operator(GAPPY, finding["code"], finding["where"], "Drive: acknowledged.")[0])
            opened = open_document(GAPPY, "Gappy route")
            check_button = page.get_by_role("button", name="Check", exact=True)
            checked_here = False
            if opened and check_button.count():
                check_button.click()
                page.wait_for_timeout(2500)
                checked_here = page.locator(".aw-sp-finding").count() > 0
            approve = page.get_by_role("button", name="Approve", exact=True)
            poll(lambda: approve.count() >= 1, 10)
            shown = opened and approve.count() >= 1
            dialog = ""
            stopped = False
            if shown:
                approve.first.click()
                page.wait_for_timeout(2000)
                dialog = ack_text(page)
                stopped = page.get_by_role("button", name="Approve anyway").count() > 0
                # Reached only once the approval step opened or answered (dialog, stop, or a phase move).
                shown = bool(dialog) or stopped or page.get_by_role("dialog").count() > 0                     or ctx.view(GAPPY).get("phase") != "exploring"
                page.screenshot(path=shot + "_approve.png", full_page=True)
            # The page offers Approve only on a document whose Check is clean. Before the build the
            # acknowledgements that would make Gappy clean answer 404/405 (the feature's absence), so
            # the page, opened on Gappy and checked, has findings and no Approve: that is reached, as
            # an absent acknowledge route is for ac-ack. Once they exist, only the dialog counts.
            absent = bool(ack_codes) and all(c in (404, 405) for c in ack_codes)
            shown = shown or (opened and checked_here and absent)
            rows["approve"] = (shown, dialog, stopped, ctx.view(GAPPY).get("phase"))
        browser.close()
    if "visible" in rows:
        shown, page_ack, check_text, open_text, rendered = rows["visible"]
        both = [a for a in ("criterion_without_check", "amendments_unreviewed")
                if a in page_ack and a in check_text]
        ok = (len(both) == 2 and "Drive" not in open_text
              and all(w in page_ack for w in ("scribe", "operator"))
              and "acknowledged" in rendered.lower() and "criterion_without_check" in rendered)
        record("ac-ack-visible", shown, ok,
               f"page lists {page_ack[:160]!r}; Check lists {check_text[:160]!r}; open findings "
               f"{open_text[:120]!r}; rendered holds 'acknowledged': {'acknowledged' in rendered.lower()}")
    if "approve" in rows:
        shown, dialog, stopped, phase = rows["approve"]
        ok = shown and not stopped and bool(dialog) and "criterion_without_check" in dialog
        record("ac-approve-acks", shown, ok,
               f"'Approve anyway' stop shown: {stopped}; dialog lists {dialog[:200]!r}; phase {phase}")


# --------------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="check the drive's own logic only; no Hub")
    parser.add_argument("--only", default="", help="comma-separated check keys to run (iteration)")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if str(PORT) in ("8000", "8010"):
        sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")
    if port_answers():
        sys.exit(f"REFUSED: :{PORT} already answers, and it may be running another checkout's code. "
                 "Pick another AW_DRIVE_PORT; this drive does not reuse a Hub.")
    only = {k.strip() for k in args.only.split(",") if k.strip()}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = start_hub(SCRATCH / "hub.log")
    ctx, setup_error = Ctx(), None
    try:
        arrange(ctx)
        for key, fn in (("ac-same-list", check_same_list), ("ac-verdict", check_verdict),
                        ("ac-verdict-false", check_verdict_false), ("ac-ack", check_ack),
                        ("ac-operator-ack", check_operator_ack)):
            if only and key not in only:
                continue
            try:
                fn(ctx)
            except Setup as exc:
                checks[key] = (False, False, f"setup: {exc}")
                print(f"SETUP {key}: {exc}", flush=True)
        if not only or only & {"ac-ack-visible", "ac-approve-acks"}:
            browser_checks(ctx, only)
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        stop_hub(proc)
    print("\n== drive_baseline")
    failed = False
    for key in ORDER:
        if only and key not in only:
            continue
        reached, failed_here, detail = checks.get(key, (False, False, setup_error or "not run"))
        failed = failed or failed_here or not reached
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if failed_here else 'no'} -- {detail}")
    print(f"output: {OUT[0]}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
