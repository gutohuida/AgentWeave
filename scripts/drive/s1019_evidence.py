"""Sweep 2026-10-19: Requirements, evidence & coverage x Drift, on a Hub started with `e2e.py hub-up`.

Operator routes only, plus the seeded running-run credential the agent routes need (the pattern of
d1019_night_recheck_spec.py). Prints every answer it judges; asserts nothing silently.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1019_evidence.py <project-id> <project-dir>
"""

import json
import os
import pathlib
import secrets
import sqlite3
import subprocess
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
RESULTS = []


def say(label, ok, detail=""):
    RESULTS.append((label, ok))
    print(("HELD " if ok else "ODD  ") + label + (f"\n     {detail}" if detail else ""))


def r(method, path, body=None):
    st, out = request(method, path, body)
    return st, out


def git(*args):
    return subprocess.run(["git", "-C", str(DIR), *args], capture_output=True, text=True).stdout.strip()


def commit_file(rel, text, msg, binary=None):
    p = DIR / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if binary is not None:
        p.write_bytes(binary)
    else:
        p.write_text(text, encoding="utf-8")
    git("add", rel)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)
    return git("rev-parse", "HEAD")


def seed_run(name, run_id):
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + json.loads(e2e.STATE.read_text())["db"].replace("\\", "/")
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "hub"))
    from hub.agent_auth import hash_run_token

    token = "aw_run_" + secrets.token_urlsafe(24)
    db = sqlite3.connect(json.loads(e2e.STATE.read_text())["db"])
    cols = {c[1] for c in db.execute("pragma table_info(runs)")}
    row = {"id": run_id, "project_id": P, "agent": name, "status": "running", "turn_depth": 0,
           "capability_token_hash": hash_run_token(token)}
    for extra in ("created_at", "started_at", "updated_at"):
        if extra in cols:
            row[extra] = "2026-10-19T09:00:00"
    db.execute(f"insert into runs ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
    db.commit()
    db.close()
    return token


def end_run(run_id):
    db = sqlite3.connect(json.loads(e2e.STATE.read_text())["db"])
    db.execute("update runs set status='completed' where id=?", (run_id,))
    db.commit()
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


def payload(alpha="It MUST list today's items.", with_tasks=True):
    reqs = [
        {"key": "alpha", "statement": alpha, "modal": "MUST"},
        {"key": "beta", "statement": "It MUST sort items by due date.", "modal": "MUST"},
        {"key": "gamma", "statement": "It MUST print a total.", "modal": "MUST"},
    ]
    d = {
        "schema_version": 1, "kind": "change-spec", "title": "Evidence sweep " + SFX,
        "scope": {"in_scope": ["list"], "non_goals": ["sync"]},
        "requirements": reqs,
        "acceptance_criteria": [
            {"key": f"c-{q['key']}", "requirement": q["key"], "given": "g", "when": "w", "then": "t"} for q in reqs
        ],
        "delivery": {"mode": "none"},
    }
    if with_tasks:
        d["tasks"] = [{"key": f"t-{q['key']}", "title": f"Build {q['key']} {SFX}", "description": "Do.",
                       "requirements": [q["key"]]} for q in reqs]
    return d


def coverage(doc):
    st, out = r("GET", f"{BASE}/spec/coverage?document={doc}")
    return {e["identifier"]: e for e in out.get("requirements", [])} if st == 200 else {"_err": (st, out)}


def evidence(ev_id):
    st, out = r("GET", f"{BASE}/spec/evidence")
    return next((e for e in out["evidence"] if e["id"] == ev_id), None)


# --- setup: files, document, approval -------------------------------------------------------------
base_sha = commit_file("todo/list.py", "def items():\n    return ['a']\n", "list")
commit_file("todo/other.py", "X = 1\n", "other")
DOC = f"spec/changes/ev-sweep-{SFX}/spec.json"
st, out = r("POST", f"{BASE}/documents", {"path": DOC, "title": "Evidence sweep " + SFX})
st, out = r("PUT", f"{BASE}/documents/{DOC}/content", {"document": payload()})
print("write:", st, json.dumps(out)[:300])
ids = (out or {}).get("identifiers") or {}
A, B, G = ids.get("alpha", "FR-1"), ids.get("beta", "FR-2"), ids.get("gamma", "FR-3")
print("identifiers", A, B, G)

# --- 1. operator evidence with a commit and a locator; accepted on arrival ------------------------
alpha_sha = commit_file("todo/list.py", "def items():\n    return ['a', 'b']  # today\n", "alpha: today")
st, ev_a = r("POST", f"{BASE}/spec/evidence", {"identifier": A, "document": DOC, "summary": "list shows today",
                                                "locator": "todo/list.py", "commit": alpha_sha,
                                                "command": "pytest -q", "output": "1 passed", "covers": "full"})
say("operator evidence accepted on arrival with a footprint", st == 201 and ev_a.get("review_state") == "accepted"
    and (ev_a.get("footprint") or {}).get("commit_sha") == alpha_sha, f"{st} {json.dumps(ev_a)[:400]}")
EA = ev_a["id"]

# --- 2. the piece's diff -------------------------------------------------------------------------
st, d = r("GET", f"{BASE}/spec/evidence/{EA}/diff")
say("diff names exactly the piece's commit's file", st == 200 and [f["path"] for f in d.get("files", [])] == ["todo/list.py"],
    f"{st} base={str(d.get('base'))[:8]} files={[(f['path'], f['status']) for f in d.get('files', [])]} reason={d.get('reason')}")
st, d = r("GET", f"{BASE}/spec/evidence/ev-nope/diff")
say("diff of an unknown piece 404", st == 404, f"{st} {d}")
st, ev_nc = r("POST", f"{BASE}/spec/evidence", {"identifier": B, "document": DOC, "summary": "watched it sort",
                                                 "covers": "partial"})
st2, d = r("GET", f"{BASE}/spec/evidence/{ev_nc['id']}/diff")
print("   no-commit piece footprint:", json.dumps(ev_nc.get("footprint"))[:300])
say("diff of a piece without a named commit answers 200 with a reason", st2 == 200,
    f"{st2} files={[f['path'] for f in d.get('files', [])]} commit={d.get('commit')} reason={d.get('reason')}")

# a commit carrying a non-ASCII file, a path with a space, a binary and a >400 KB file
big = "".join(f"line {i} ünïcödé →\n" for i in range(30000))
commit_file("todo/data file ü.txt", big, "big")
wide_sha = commit_file("todo/logo.png", None, "wide", binary=bytes(range(256)) * 40)
st, ev_w = r("POST", f"{BASE}/spec/evidence", {"identifier": B, "document": DOC, "summary": "sorted fixture",
                                                "commit": wide_sha, "covers": "partial"})
st, d = r("GET", f"{BASE}/spec/evidence/{ev_w['id']}/diff")
files = [(f["path"], f["status"], len(f["patch"])) for f in d.get("files", [])]
say("a piece's diff over a two-commit line reads both (binary + non-ASCII path + >400KB)", st == 200,
    f"{st} truncated={d.get('truncated')} base={str(d.get('base'))[:8]} files={files} reason={d.get('reason')}")

# --- 3. F706: all-partial accepted evidence reads in_progress ------------------------------------
cov = coverage(DOC)
say("F706: two accepted partial pieces read in_progress, with a reason", cov.get(B, {}).get("state") == "in_progress",
    json.dumps(cov.get(B))[:300])
st, ev_full = r("POST", f"{BASE}/spec/evidence", {"identifier": B, "document": DOC, "summary": "all cases", "covers": "full"})
cov = coverage(DOC)
say("adding a full piece covers it", cov.get(B, {}).get("state") not in ("in_progress", "uncovered", None),
    json.dumps(cov.get(B))[:300])
st, bad = r("POST", f"{BASE}/spec/evidence", {"identifier": B, "document": DOC, "summary": "x", "covers": "most"})
say("covers outside full/partial refused legibly", st in (400, 409, 422), f"{st} {bad}")

# --- 4. overturn -----------------------------------------------------------------------------------
st, out = r("POST", f"{BASE}/spec/evidence/{EA}/overturn", {"reason": ""})
say("overturn with no reason 422 overturn_needs_reason", st == 422 and "reason" in json.dumps(out), f"{st} {out}")
st, out = r("POST", f"{BASE}/spec/evidence/{EA}/overturn", {"reason": "   "})
say("overturn with a whitespace reason refused", st == 422, f"{st} {out}")
before = coverage(DOC).get(A, {})
st, out = r("POST", f"{BASE}/spec/evidence/{EA}/overturn", {"reason": "the commit lists yesterday too"})
after = coverage(DOC).get(A, {})
say("overturn accepted -> rejected answers overturned.from=accepted", st == 200 and out.get("review_state") == "rejected"
    and (out.get("overturned") or {}).get("from") == "accepted", f"{st} {json.dumps(out)[:300]}")
say("coverage follows the overturn", before.get("state") != after.get("state"),
    f"before={before.get('state')} after={after.get('state')}")
st, rv = r("GET", f"{BASE}/spec/evidence/{EA}/reviews")
say("reviews list both decisions oldest first, with the overturn's reason",
    st == 200 and [x["decision"] for x in rv["reviews"]] == ["accepted", "rejected"]
    and rv["reviews"][-1]["reason"] == "the commit lists yesterday too", json.dumps(rv)[:400])
st, out = r("POST", f"{BASE}/spec/evidence/{EA}/decision", {"decision": "rejected", "reason": "again"})
say("deciding the same decision twice 409 already_decided", st == 409, f"{st} {out}")
st, out = r("POST", f"{BASE}/spec/evidence/{EA}/decision", {"decision": "accepted", "reason": ""})
say("operator decision route reversing with no reason 422 (overturn needs a reason on both doors)", st == 422, f"{st} {out}")
st, out = r("POST", f"{BASE}/spec/evidence/{EA}/overturn", {"reason": "re-read it: it is fine"})
say("overturn rejected -> accepted", st == 200 and out.get("review_state") == "accepted", f"{st} {json.dumps(out)[:200]}")
st, out = r("POST", f"{BASE}/spec/evidence/ev-nope/overturn", {"reason": "x"})
say("overturn unknown piece 404", st == 404, f"{st} {out}")

# --- 5. agents decide awaiting only --------------------------------------------------------------
r("POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
runner = r("GET", f"/projects/{P}/runners")[1][0]["id"]
for name in ("builder", "checker"):
    r("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner})
st, out = r("PATCH", f"/projects/{P}/agents/checker", {"can_accept_evidence": True})
print("   grant checker:", st, json.dumps(out)[:160])
tb_run, tc_run = "run-ev-b-" + SFX, "run-ev-c-" + SFX
tb, tc = seed_run("builder", tb_run), seed_run("checker", tc_run)
st, ev_g = agent(tb, "POST", "/spec/evidence", {"identifier": G, "document": DOC, "summary": "prints total"})
say("agent evidence lands awaiting", st == 201 and ev_g.get("review_state") == "awaiting", f"{st} {json.dumps(ev_g)[:300]}")
EG = ev_g["id"]
st, out = agent(tc, "POST", f"/spec/evidence/{EG}/decision", {"decision": "accepted"})
say("decision while the recording run lives: 409 recording_run_live", st == 409, f"{st} {out}")
st, out = r("POST", f"{BASE}/spec/evidence/{EG}/overturn", {"reason": "x"})
say("operator overturn of an awaiting piece 409 not_decided", st == 409 and "not_decided" in json.dumps(out), f"{st} {out}")
end_run(tb_run)
st, out = agent(tc, "POST", f"/spec/evidence/{EG}/decision", {"decision": "accepted"})
print("   checker accept after run end:", st, json.dumps(out)[:200])
st2, out2 = agent(tc, "POST", f"/spec/evidence/{EG}/decision", {"decision": "rejected", "reason": "changed mind"})
say("agent cannot reverse a decided piece: 409 already_decided naming the operator", st2 == 409 and "operator" in json.dumps(out2),
    f"{st2} {out2}")
st, out = agent(tc, "POST", f"/spec/evidence/{EG}/overturn", {"reason": "x"})
say("the agent plane has no overturn route (404/405)", st in (404, 405), f"{st} {str(out)[:200]}")

# --- 6. reword: earlier-wording evidence never accepted -------------------------------------------
st, out = r("POST", f"{BASE}/spec/evidence", {"identifier": A, "document": DOC, "summary": "awaiting? no, operator", "covers": "full"})
st, ev_g2 = agent(tc, "POST", "/spec/evidence", {"identifier": A, "document": DOC, "summary": "checker saw it list today"})
EG2 = ev_g2.get("id")
end_run(tc_run)
st, out = r("PUT", f"{BASE}/documents/{DOC}/content", {"document": payload(alpha="It MUST list today's and tomorrow's items.")})
print("reword:", st, json.dumps(out)[:300])
pa = evidence(EA)
say("the piece recorded for the earlier wording reads for_current_wording=false", pa and pa.get("for_current_wording") is False,
    json.dumps({k: pa.get(k) for k in ("review_state", "for_current_wording")}) if pa else "missing")
cov_a = coverage(DOC).get(A, {})
print("   alpha coverage after reword:", json.dumps(cov_a)[:300])
st, out = r("POST", f"{BASE}/spec/evidence/{EG2}/decision", {"decision": "accepted"})
say("accepting an awaiting earlier-wording piece 409 evidence_stale", st == 409 and "evidence_stale" in json.dumps(out), f"{st} {out}")
st, out = r("POST", f"{BASE}/spec/evidence/{EA}/overturn", {"reason": "stale anyway"})
say("overturning a stale accepted piece to rejected is allowed", st == 200 and out.get("review_state") == "rejected", f"{st} {json.dumps(out)[:200]}")
st, out = r("POST", f"{BASE}/spec/evidence/{EA}/overturn", {"reason": "back"})
say("overturning it back to accepted 409 evidence_stale", st == 409 and "evidence_stale" in json.dumps(out), f"{st} {out}")

# --- 7. requirement story ------------------------------------------------------------------------
st, story = r("GET", f"{BASE}/spec/requirements/{A}?document={DOC}")
revs = [(x["classification"], (x["statement"] or "")[:40]) for x in story.get("revisions", [])]
say("story carries the current wording and both revisions' statements",
    st == 200 and "tomorrow" in (story["requirement"].get("statement") or "") and len(revs) >= 2, f"{st} revisions={revs}")
print("   story evidence:", [(e["id"], e["review_state"], e.get("for_current_wording")) for e in story.get("evidence", [])])

# --- 8. drift -------------------------------------------------------------------------------------
st, ev_d = r("POST", f"{BASE}/spec/evidence", {"identifier": G, "document": DOC, "summary": "total printed",
                                                "locator": "todo/other.py", "covers": "full"})
ED = ev_d["id"]
print("   drift piece footprint:", json.dumps(ev_d.get("footprint"))[:300])
commit_file("README.md", "# changed\n", "unwatched")
st, out = r("POST", f"{BASE}/spec/drift/detect")
say("an unwatched change raises no drift", st == 200 and not out.get("raised"), f"{st} {out}")
commit_file("todo/other.py", "X = 2\n", "watched")
st, out = r("POST", f"{BASE}/spec/drift/detect")
raised = out.get("raised") or []
say("a watched change raises drift", st == 200 and len(raised) >= 1, f"{st} {out}")
st, dl = r("GET", f"{BASE}/spec/drift?document={DOC}")
cands = [x for x in dl.get("candidates", dl.get("drift", [])) if x.get("state") == "candidate"] if isinstance(dl, dict) else []
print("   drift list keys:", list(dl) if isinstance(dl, dict) else dl, "candidates:", [(c["id"], c.get("evidence_id")) for c in cands])
st, out = r("POST", f"{BASE}/spec/evidence/{ED}/overturn", {"reason": "the piece was wrong all along"})
st, dl2 = r("GET", f"{BASE}/spec/drift?document={DOC}")
cands2 = [x for x in dl2.get("candidates", dl2.get("drift", [])) if x.get("state") == "candidate"]
say("drift on a piece the operator overturned to rejected is no longer an open question", not any(c.get("evidence_id") == ED for c in cands2),
    f"open after overturn={[(c['id'], c.get('evidence_id'), c.get('state')) for c in cands2]}")
st, out = r("POST", f"{BASE}/spec/drift/detect")
print("   rescan after overturn:", st, out)
# drift over a reworded requirement: EA is stale & rejected; accept-stale alpha piece? scan touches list.py
commit_file("todo/list.py", "def items():\n    return []\n", "watched list")
st, out = r("POST", f"{BASE}/spec/drift/detect")
print("   scan after list.py changed (alpha's pieces are stale):", st, out)
st, dl3 = r("GET", f"{BASE}/spec/drift?document={DOC}")
print("   drift now:", json.dumps(dl3)[:800])

print("\nSUMMARY", sum(ok for _, ok in RESULTS), "held /", len(RESULTS))
for label, ok in RESULTS:
    if not ok:
        print("  ODD:", label)
print(json.dumps({"doc": DOC, "A": A, "B": B, "G": G, "EA": EA, "EG": EG, "EG2": EG2, "ED": ED}))
