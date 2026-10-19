"""Sweep 2026-10-19: Spec documents x Corpus & folding, on a Hub started with `e2e.py hub-up`.

New paths first: the operator answering report_cannot_satisfy (amend / accept / reject, F700),
decided proposals (`?status=resolved`), `PUT .../roadmap`; then the fold of a change that carried
a cannot-satisfy amend. Operator routes, plus seeded running-run credentials bound to a task for
the agent routes (the pattern of s1019_evidence.py; a seeded run is labelled, not a real turn).

  AW_E2E_STATE=... py -3.11 scripts/drive/s1019_spec.py <project-id> <project-dir>
"""

import json
import os
import pathlib
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from e2e import request  # noqa: E402

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
SFX = time.strftime("%H%M%S")
BASE = f"/projects/{P}/project"
HUB = e2e.hub() + "/api/v1"
DB = json.loads(e2e.STATE.read_text())["db"]


def say(label, ok, detail=""):
    print(("HELD " if ok else "ODD  ") + label + (f"\n     {detail}" if detail else ""))


def show(label, st, out):
    print(f"  {label}: {st} {json.dumps(out, ensure_ascii=False)[:500]}")


def seed_run(name, run_id, task_id=None):
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + DB.replace("\\", "/")
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "hub"))
    from hub.agent_auth import hash_run_token

    token = "aw_run_" + secrets.token_urlsafe(24)
    db = sqlite3.connect(DB)
    cols = {c[1] for c in db.execute("pragma table_info(runs)")}
    row = {"id": run_id, "project_id": P, "agent": name, "status": "running", "turn_depth": 0,
           "capability_token_hash": hash_run_token(token)}
    if task_id:
        row["task_id"] = task_id
    for extra in ("created_at", "started_at", "updated_at"):
        if extra in cols:
            row[extra] = "2026-10-19T09:00:00"
    db.execute(f"insert into runs ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
    db.commit()
    db.close()
    return token


def ro(sql, *args):
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return db.execute(sql, args).fetchall()
    finally:
        db.close()


def agent(token, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HUB + "/agent-actions" + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw or b"null")
        except ValueError:
            return exc.code, raw[:300]


def on_disk(path):
    return json.loads((DIR / path).read_text(encoding="utf-8"))


def criterion(path, key):
    return next(c for c in on_disk(path)["acceptance_criteria"] if c["key"] == key)


def task(tid):
    st, out = request("GET", f"/projects/{P}/tasks/{tid}")
    return out if st == 200 else {"_err": (st, out)}


def amendments(doc):
    st, out = request("GET", f"{BASE}/documents/{doc}/amendments")
    return {a["id"]: a for a in out.get("amendments", [])} if st == 200 else {}


def queued_for(name):
    return ro("select id, state, origin_type, substr(content,1,400), conversation_id from inbound_queue_entries "
              "where project_id=? and agent=? order by sequence", P, name)


def payload(title, keys=("alpha", "beta", "gamma", "delta")):
    reqs = [{"key": k, "statement": f"The tool MUST handle {k}.", "modal": "MUST"} for k in keys]
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "scope": {"in_scope": ["tool"], "non_goals": ["sync"]},
        "requirements": reqs,
        "acceptance_criteria": [
            {"key": f"c-{k}", "requirement": k, "given": "a list", "when": f"{k} runs",
             "then": f"{k} finishes under 1ms", "how_to_check": f"time {k}"} for k in keys
        ],
        "tasks": [{"key": f"t-{k}", "title": f"Build {k} {SFX}", "description": "Do.", "requirements": [k]}
                  for k in keys],
        "delivery": {"mode": "none"},
    }


# --- agents (Haiku runner; the seeded running runs keep each busy, so a queued note is held) ---
st, out = request("POST", f"/projects/{P}/agents", {"name": "builder"})
show("an agent without a runner (refused?)", st, out)
st, runners = request("GET", f"/projects/{P}/runners")
runner = next((x for x in runners if x.get("model") == "claude-haiku-4-5-20251001"), None) or request(
    "POST", f"/projects/{P}/runners", {"name": "haiku " + SFX, "cli": "claude", "model": "claude-haiku-4-5-20251001"})[1]
for name in ("builder", "tester"):
    st, out = request("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner["id"]})
    print(f"  agent {name}: {st}")
    seed_run(name, f"run-hold-{name}-{SFX}")  # busy from here on: nothing this drive queues starts a turn

# --- the change document, approved, its tasks taken by builder ---------------------------------
DOC = f"spec/changes/cs-sweep-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": DOC, "title": "Cannot-satisfy sweep " + SFX})
st, out = request("PUT", f"{BASE}/documents/{DOC}/content", {"document": payload("Cannot-satisfy sweep " + SFX)})
show("write", st, {k: out.get(k) for k in ("identifiers", "blocking")} if isinstance(out, dict) else out)
request("POST", f"{BASE}/documents/close-exploration?path={DOC}")
request("POST", f"{BASE}/documents/propose?path={DOC}")
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "drive", "approve_anyway": True})
say("change approved", st == 200 and out.get("phase") == "approved", f"{st} {str(out)[:200]}")
st, tasks = request("GET", f"/projects/{P}/tasks")
T = {t["spec_task_key"]: t["id"] for t in tasks["tasks"] if t.get("spec_task_key") and SFX in t["title"]}
print("tasks", T)
for key in T:
    request("PATCH", f"/projects/{P}/tasks/{T[key]}", {"status": "assigned", "assignee": "builder"})
    request("PATCH", f"/projects/{P}/tasks/{T[key]}", {"status": "in_progress"})
print("  task acceptance criteria copied:", task(T["t-beta"]).get("acceptance_criteria"))

# --- report refusals -----------------------------------------------------------------------------
loose = seed_run("builder", "run-cs-loose-" + SFX)
st, out = agent(loose, "POST", "/spec/documents/cannot-satisfy", {"path": DOC, "criterion": "c-alpha", "reason": "too slow"})
say("a run bound to no task is refused, legibly", st == 403, f"{st} {out}")
runs = {k: seed_run("builder", f"run-cs-{k}-{SFX}", T[k]) for k in T}
st, out = agent(runs["t-alpha"], "POST", "/spec/documents/cannot-satisfy", {"path": DOC, "criterion": "c-nope", "reason": "x"})
say("an unknown criterion is refused, naming it", st in (400, 404, 409, 422) and "c-nope" in json.dumps(out), f"{st} {out}")
st, out = agent(runs["t-alpha"], "POST", "/spec/documents/cannot-satisfy", {"path": DOC, "criterion": "c-alpha", "reason": "  "})
say("a blank reason is refused", st in (400, 422), f"{st} {out}")
st, out = agent(runs["t-alpha"], "POST", "/spec/documents/cannot-satisfy", {"path": DOC, "criterion": "c-beta", "reason": "not my task's"})
show("a run reporting a criterion of ANOTHER task's requirement (t-alpha run, c-beta)", st, out)
cross = out.get("id") if st == 201 else None
print("  t-alpha after the cross report:", task(T["t-alpha"]).get("status"), "| t-beta:", task(T["t-beta"]).get("status"))

# --- three reports, one per answer ---------------------------------------------------------------
reports = {}
for k, crit in (("t-alpha", "c-alpha"), ("t-beta", "c-beta"), ("t-gamma", "c-gamma")):
    st, out = agent(runs[k], "POST", "/spec/documents/cannot-satisfy",
                    {"path": DOC, "criterion": crit, "reason": f"{crit} cannot finish under 1ms on a cold cache"})
    show(f"report {crit}", st, out)
    reports[crit] = out.get("id")
    t = task(T[k])
    say(f"{k} blocked with the reason", t.get("status") == "blocked" and crit in (t.get("blocked_reason") or ""),
        f"status={t.get('status')} reason={t.get('blocked_reason')!r}")
st, out = agent(runs["t-alpha"], "POST", "/spec/documents/cannot-satisfy",
                {"path": DOC, "criterion": "c-alpha", "reason": "said twice"})
show("a second report on the same criterion while the first is unanswered", st, out)
dup = out.get("id") if st == 201 else None

# --- respond refusals ----------------------------------------------------------------------------
R = f"{BASE}/documents/{DOC}/amendments"
for label, rid, body, want in (
    ("unknown response", reports["c-alpha"], {"response": "maybe"}, (400, 422)),
    ("reject with no reason", reports["c-alpha"], {"response": "reject"}, (400, 422)),
    ("unknown report id", "amd-nope", {"response": "accept"}, (404,)),
    ("amend with no change", reports["c-beta"], {"response": "amend"}, (400, 422)),
    ("amend changing the requirement field", reports["c-beta"], {"response": "amend", "change": {"requirement": "alpha"}}, (400, 422)),
    ("amend with a blank then", reports["c-beta"], {"response": "amend", "change": {"then": "  "}}, (400, 422)),
):
    st, out = request("POST", f"{R}/{rid}/respond", body)
    say(f"respond refuses {label}, legibly", st in want and isinstance(out, dict) and out.get("detail"),
        f"{st} {json.dumps(out)[:300]}")
nothing_answered = all(not a["reviewed"] for a in amendments(DOC).values())
say("no refusal marked anything answered", nothing_answered)

# --- reject --------------------------------------------------------------------------------------
before_q = len(queued_for("builder"))
st, out = request("POST", f"{R}/{reports['c-alpha']}/respond",
                  {"response": "reject", "reason": "1ms is the contract; warm the cache in setup"})
show("reject", st, {k: out.get(k) for k in ("response", "task_unblocked", "amendment")} if st == 200 else out)
a = amendments(DOC)[reports["c-alpha"]]
say("reject recorded on the report", a["reviewed"] and a["response"] == "rejected" and "warm" in (a["response_reason"] or ""),
    json.dumps({k: a[k] for k in ("reviewed", "response", "response_reason", "answered_by")}))
say("t-alpha stays blocked", task(T["t-alpha"]).get("status") == "blocked", task(T["t-alpha"]).get("status"))
q = queued_for("builder")
say("the rejection reached builder as input", len(q) == before_q + 1 and "rejected" in q[-1][3], str(q[-1:])[:500])
st, out = request("POST", f"{R}/{reports['c-alpha']}/respond", {"response": "accept"})
say("a second answer is refused 409 naming the first", st == 409 and "rejected" in json.dumps(out), f"{st} {out}")
# the note tells the reporter to "try again": can it?
st, out = agent(runs["t-alpha"], "PATCH", f"/tasks/{T['t-alpha']}", {"status": "in_progress"})
show("builder moving its rejected (blocked) task back to in_progress", st, out)
st, out = agent(runs["t-alpha"], "POST", "/spec/documents/cannot-satisfy",
                {"path": DOC, "criterion": "c-alpha", "reason": "warmed it; still 3ms"})
show("builder reporting again after the rejection", st, out)
re_report = out.get("id") if st == 201 else None

# --- amend ---------------------------------------------------------------------------------------
before_q = len(queued_for("builder"))
st, out = request("POST", f"{R}/{reports['c-beta']}/respond",
                  {"response": "amend", "reason": "cold cache is real", "change": {"then": "beta finishes under 5ms"}})
show("amend", st, {k: out.get(k) for k in ("response", "task_unblocked", "amendment")} if st == 200 else out)
produced = out.get("amendment") if st == 200 else None
say("the criterion now reads the amended then (file)", criterion(DOC, "c-beta")["then"] == "beta finishes under 5ms",
    str(criterion(DOC, "c-beta")))
tb = task(T["t-beta"])
say("t-beta unblocked", tb.get("status") == "in_progress", f"{tb.get('status')} blocked_reason={tb.get('blocked_reason')!r}")
say("t-beta carries the amended criterion", "under 5ms" in json.dumps(tb.get("acceptance_criteria")),
    json.dumps(tb.get("acceptance_criteria"))[:300])
am = amendments(DOC)
say("the report reads amended, and the produced amendment names it and is reviewed",
    am[reports["c-beta"]]["response"] == "amended" and produced in am and am[produced]["responds_to"] == reports["c-beta"]
    and am[produced]["reviewed"], json.dumps(am.get(produced))[:400])
q = queued_for("builder")
say("the amendment reached builder with the new wording", len(q) == before_q + 1 and "under 5ms" in q[-1][3], str(q[-1:])[:500])
st, out = request("GET", f"{BASE}/documents/{DOC}/proposals?status=all")
show("proposals after an amend (should be none: amend is not a proposal)", st, [p["status"] for p in out.get("proposals", [])])
st, doc_view = request("GET", f"{BASE}/documents/{DOC}")
show("document phase/digest after amend", st, {k: doc_view.get(k) for k in ("phase", "content_digest")} if isinstance(doc_view, dict) else doc_view)

# --- accept --------------------------------------------------------------------------------------
st, out = request("POST", f"{R}/{reports['c-gamma']}/respond", {"response": "accept"})
show("accept (no reason)", st, {k: out.get(k) for k in ("response", "task_unblocked")} if st == 200 else out)
say("accept unblocks t-gamma, criterion unchanged",
    task(T["t-gamma"]).get("status") == "in_progress" and criterion(DOC, "c-gamma")["then"] == "gamma finishes under 1ms")
q = queued_for("builder")
print("  builder's queue now:")
for row in q:
    print("   ", row[0], row[1], row[2], "conv", row[4], "|", row[3][:160].replace("\n", " "))
convs = ro("select id, lifecycle, origin, archived_at from conversations where project_id=? and agent='builder'", P)
print("  builder conversations:", convs)

# --- the cross report and the duplicate ----------------------------------------------------------
if cross:
    st, out = request("POST", f"{R}/{cross}/respond", {"response": "accept"})
    show("accepting the cross report (filed from t-alpha's run on c-beta)", st,
         {k: out.get(k) for k in ("task_id", "task_unblocked")} if st == 200 else out)
    print("  t-alpha after accepting the cross report:", task(T["t-alpha"]).get("status"))

# --- report on an archived / non-approved document? amend on non-approved ------------------------
# (amend_not_approved is driven in the fold phase below)

# --- proposals at contract rigor -----------------------------------------------------------------
PD = f"spec/changes/prop-sweep-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": PD, "title": "Proposal sweep " + SFX})
request("PUT", f"{BASE}/documents/{PD}/content", {"document": payload("Proposal sweep " + SFX, keys=("one", "two"))})
st, out = request("POST", f"{BASE}/documents/{PD}/rigor", {"rigor": "contract", "reason": "drive proposals"})
show("rigor -> contract", st, out if st != 200 else {k: out.get(k) for k in ("rigor",)})
writer = seed_run("tester", "run-pr-" + SFX)
d = payload("Proposal sweep " + SFX, keys=("one", "two"))
d["requirements"][0]["statement"] = "The tool MUST handle one quickly."
st, out = agent(writer, "POST", "/spec/documents", {"path": PD, "document": d})
show("agent edit at contract rigor", st, {k: out.get(k) for k in ("proposals", "already_pending")} if isinstance(out, dict) else out)
d2 = json.loads(json.dumps(d))
d2["requirements"][1]["statement"] = "The tool MUST handle two carefully."
d2["requirements"].append({"key": "three", "statement": "The tool MUST handle three.", "modal": "MUST"})
d2["acceptance_criteria"].append({"key": "c-three", "requirement": "three", "given": "g", "when": "w", "then": "t"})
st, out = agent(writer, "POST", "/spec/documents", {"path": PD, "document": d2})
show("second agent edit (one repeat, two new)", st, {k: out.get(k) for k in ("proposals", "already_pending")} if isinstance(out, dict) else out)
st, pend = request("GET", f"{BASE}/documents/{PD}/proposals")
pend = pend.get("proposals", [])
print("  pending:", [(p["id"], p["unit_kind"], p["unit_key"], p["change_kind"]) for p in pend])
acted = []
for p in pend:
    if p["unit_key"] == "one":
        st, out = request("POST", f"{BASE}/documents/{PD}/proposals/{p['id']}/accept", {"reason": "yes, quickly"})
    elif p["unit_key"] == "two":
        st, out = request("POST", f"{BASE}/documents/{PD}/proposals/{p['id']}/reject", {"reason": "carefully is vague"})
    elif p["unit_key"] == "three":
        st, out = request("POST", f"{BASE}/documents/{PD}/proposals/{p['id']}/withdraw", {"reason": "out of scope"})
    else:
        st, out = request("POST", f"{BASE}/documents/{PD}/proposals/{p['id']}/reject", {})
    acted.append((p["unit_key"], st))
    time.sleep(1.1)
print("  acted:", acted)
st, res = request("GET", f"{BASE}/documents/{PD}/proposals?status=resolved")
rows = res.get("proposals", [])
for p in rows:
    print("   ", p["unit_kind"], p["unit_key"], p["status"], "by", p["resolved_by_actor_name"], "at", p["resolved_at"], "why", repr(p["resolution_reason"]))
order_ok = [p["resolved_at"] for p in rows] == sorted([p["resolved_at"] for p in rows], reverse=True)
say("resolved: newest decision first", order_ok)
say("resolved rows carry who and why", all(p["resolved_by_actor_name"] for p in rows) and
    any(p["resolution_reason"] == "carefully is vague" for p in rows))
st, out = request("GET", f"{BASE}/documents/{PD}/proposals?status=bogus")
say("an unknown status filter is refused", st == 422, f"{st} {str(out)[:200]}")
withdrawn_three = next((p for p in rows if p["unit_key"] == "three"), None)
say("the withdraw reason is recorded", bool(withdrawn_three) and withdrawn_three["resolution_reason"] == "out of scope",
    json.dumps(withdrawn_three)[:300] if withdrawn_three else "no row")

# --- roadmap link (API only) ---------------------------------------------------------------------
RM = f"spec/changes/roadmap-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": RM, "title": "Roadmap " + SFX, "kind": "roadmap"})
rmp = {"schema_version": 1, "kind": "roadmap", "title": "Roadmap " + SFX,
       "scope": {"in_scope": ["tool"], "non_goals": ["sync"]},
       "slices": [{"key": "first", "title": "First", "intent": "Do the first thing.", "done": "the first thing is done"},
                  {"key": "second", "title": "Second", "intent": "Then the second.", "done": "the second thing is done",
                   "builds_after": ["first"]}]}
st, out = request("PUT", f"{BASE}/documents/{RM}/content", {"document": rmp})
show("roadmap write", st, {k: out.get(k) for k in ("blocking",)} if isinstance(out, dict) else out)
L = f"{BASE}/documents/{DOC}/roadmap"
st, out = request("PUT", L, {"document": RM, "slice": "first"})
say("link to an unapproved roadmap refused in words", st == 422 and "approved" in json.dumps(out), f"{st} {out}")
request("POST", f"{BASE}/documents/close-exploration?path={RM}")
request("POST", f"{BASE}/documents/propose?path={RM}")
st, out = request("POST", f"{BASE}/documents/phase?path={RM}&to=approved", {"reason": "drive", "approve_anyway": True})
say("roadmap approved", st == 200, f"{st} {str(out)[:200]}")
st, out = request("PUT", L, {"document": RM, "slice": "third"})
say("unknown slice refused naming the slices", st == 422 and "first" in json.dumps(out), f"{st} {out}")
st, out = request("PUT", f"{BASE}/documents/{RM}/roadmap", {"document": RM, "slice": "first"})
say("a roadmap linking itself refused", st == 422, f"{st} {out}")
st, out = request("PUT", L, {"document": "spec/changes/nope/spec.json", "slice": "first"})
say("unknown roadmap refused", st == 422 and "not a roadmap" in json.dumps(out), f"{st} {out}")
st, out = request("PUT", L, {"document": "../../etc/passwd", "slice": "first"})
say("a path escape is refused 400", st == 400, f"{st} {out}")
st, out = request("PUT", L, {"document": RM, "slice": "first"})
say("link set", st == 200 and out.get("changed") is True, f"{st} {out}")
st, out = request("PUT", L, {"document": RM, "slice": "first"})
say("same link again is a no-op", st == 200 and out.get("changed") is False, f"{st} {out}")
st, out = request("PUT", L, {"document": RM, "slice": "second"})
say("a different link refused in words", st == 422 and "{'" not in json.dumps(out), f"{st} {out}")
st, rv = request("GET", f"{BASE}/documents/{RM}")
print("  roadmap view slices:", json.dumps(rv.get("roadmap_slices") or rv.get("slices") or rv.get("slice_states"))[:400])
print("  doc on disk roadmap:", on_disk(DOC).get("roadmap"))

# --- fold the change that carried the reports ----------------------------------------------------
CAP = f"spec/capabilities/tool-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": CAP, "title": "Tool " + SFX, "kind": "capability"})
request("POST", f"{BASE}/documents/{CAP}/merge", {"payload": {
    "schema_version": 1, "kind": "capability", "title": "Tool " + SFX,
    "requirements": [{"key": "exist", "statement": "The tool MUST exist.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": "exist-c", "requirement": "exist", "given": "g", "when": "w", "then": "t"}]}})
st, out = request("POST", f"{BASE}/documents/{DOC}/fold", {"into": CAP})
say("fold refused while tasks are open, naming them", st == 409 and ("t-alpha" in json.dumps(out) or T["t-alpha"] in json.dumps(out)
    or "task" in json.dumps(out)), f"{st} {json.dumps(out)[:400]}")
st, draft = request("GET", f"{BASE}/documents/{DOC}/fold-draft?into={CAP}")
show("fold-draft warnings", st, draft.get("warnings") if isinstance(draft, dict) else draft)
for k in T:
    cur = task(T[k]).get("status")
    for to in (("in_progress",) if cur == "blocked" else ()) + ("completed", "under_review", "approved"):
        st, out = request("PATCH", f"/projects/{P}/tasks/{T[k]}", {"status": to})
        if st >= 400:
            show(f"  {k} -> {to}", st, out)
    print("  ", k, task(T[k]).get("status"))
# an unanswered report left on the document at fold time (the re-report after the rejection, or a fresh one)
open_reports = [a for a in amendments(DOC).values() if a["op"] == "cannot_satisfy" and not a["reviewed"]]
print("  unanswered reports at fold:", [(a["id"], a["target"]) for a in open_reports])
st, draft = request("GET", f"{BASE}/documents/{DOC}/fold-draft?into={CAP}")
show("fold-draft with an unanswered report", st, {k: draft.get(k) for k in ("warnings", "collisions")} if isinstance(draft, dict) else draft)
st, out = request("POST", f"{BASE}/documents/{DOC}/fold", {"into": CAP})
show("fold", st, {k: out.get(k) for k in ("phase", "archived", "merged", "warnings", "fold_state")} if isinstance(out, dict) else out)
if st == 200:
    cap = on_disk(CAP)
    crits = {c["key"]: c for c in cap.get("acceptance_criteria", [])}
    print("  capability criteria:", json.dumps({k: v.get("then") for k, v in crits.items()}))
    beta = next((c for c in crits.values() if "beta" in c["key"]), None)
    say("the capability carries the amended c-beta (5ms), not the original", bool(beta) and "5ms" in beta.get("then", ""),
        json.dumps(beta))
    st, cov = request("GET", f"{BASE}/spec/coverage?document={CAP}")
    show("capability coverage after the fold", st, [(r.get("identifier"), r.get("status")) for r in cov.get("requirements", [])]
         if isinstance(cov, dict) else cov)
    am = amendments(DOC)
    print("  amendments on the archived change:", [(a["id"], a["op"], a["target"], a["response"]) for a in am.values()])
    if open_reports:
        st, out = request("POST", f"{R}/{open_reports[0]['id']}/respond", {"response": "amend", "change": {"then": "x"}})
        say("amend on an archived change refused amend_not_approved, legibly", st == 409, f"{st} {out}")
        st, out = request("POST", f"{R}/{open_reports[0]['id']}/respond", {"response": "accept", "reason": "moot, folded"})
        show("accept a report on the archived change", st, {k: out.get(k) for k in ("response", "task_unblocked")} if st == 200 else out)
    st, out = request("PUT", L, {"document": RM, "slice": "first"})
    say("roadmap link on the archived change still a no-op 200", st == 200 and out.get("changed") is False, f"{st} {out}")
    st, out = agent(runs["t-delta"], "POST", "/spec/documents/cannot-satisfy",
                    {"path": DOC, "criterion": "c-delta", "reason": "after the fold"})
    show("a report on an archived change (run still bound to t-delta)", st, out)
print("DOC", DOC, "PD", PD, "RM", RM, "CAP", CAP)
