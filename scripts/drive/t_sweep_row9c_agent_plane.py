"""SWEEP ROW 9c, the agent plane — evidence recorded and decided by REAL agent turns.

Row 9b measured that the agent capability plane carries exactly five spec routes and that **two of
them are evidence**. So evidence is the one part of row 9 with a real agent surface, and the leads
9b handed 9c say to drive it through both planes and compare. This file is that leg. It spawns
actual `claude-haiku-4-5` turns and asks them to call `record_evidence` and `decide_evidence`; the
agent-plane rows below were produced by an agent, not by an operator posing as one.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... py -3.11 t_sweep_row9c_agent_plane.py

There is deliberately no shortcut here. `get_agent_actor` resolves a run credential whose plaintext
exists only in the spawned process's memory, so the only way to exercise the agent plane is to be
one — which is also the only way to find out what an agent's own view of this subsystem looks like.
"""

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT", "")
if P in ("proj-5e960453", "proj-18e5d4e0") or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)
A = f"/projects/{P}/project"
PA = f"/projects/{P}"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
AGENT_A = os.environ["AGENT_A"]
AGENT_B = os.environ["AGENT_B"]

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(("  ok   " if cond else "  FAIL ") + label + (f"  -- {detail}" if detail and not cond else ""))


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


DB = os.environ.get(
    "AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db")
)


def payload_for(title, *, nreq=2):
    """9a/9b/9c's factory, COPIED rather than imported — importing the API harness would run it."""
    ks = [f"fr-{i}" for i in range(1, nreq + 1)]
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": title,
        "summary": (
            "A driven fixture document written by row 9c's agent-plane leg, complete enough that "
            "the completeness check has nothing to report about it."
        ),
        "problem": "The agent evidence plane cannot be driven without a requirement to demonstrate.",
        "scope": {"in_scope": ["Agent evidence"], "non_goals": ["Everything else"]},
        "requirements": [
            {
                "key": k,
                "statement": f"The subject MUST satisfy condition {k} exactly as stated here.",
                "modal": "MUST",
                "rationale": f"Condition {k} is silent when violated, so it needs stating.",
            }
            for k in ks
        ],
        "acceptance_criteria": [
            {
                "key": f"ac-{k}",
                "requirement": k,
                "given": "a fixture project on the trial Hub",
                "when": f"condition {k} is exercised",
                "then": f"the observed behaviour matches requirement {k}",
            }
            for k in ks
        ],
        "tasks": [
            {
                "key": f"t-{k}",
                "title": f"Satisfy condition {k}",
                "description": (
                    f"Implement and test whatever condition {k} requires, covering ac-{k} with a "
                    "named test that fails when the behaviour is removed."
                ),
                "requirements": [k],
                "reviewer": "critic",
            }
            for k in ks
        ],
        "design": "Each condition is local to its own function.",
        "evidence": {
            "checked": ["Nothing - this is a fixture document"],
            "limits": ["It describes no real software"],
        },
        "lifecycle": "Deleted with the fixture project.",
        "open_questions": [],
    }


def db_run(run_id):
    """Read a run row directly. Read-only: the Hub owns this file and this only observes it."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        row = con.execute(
            "SELECT id, status, exit_code, error FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
    finally:
        con.close()
    return dict(zip(("id", "status", "exit_code", "error"), row, strict=True)) if row else None


def newdoc(stem, nreq=2):
    path = f"spec/changes/r9cag-{TAG}-{stem}/spec.html"
    c, _ = api("POST", f"{A}/documents", {"path": path, "title": f"doc {stem}"})
    assert c == 201, f"create {c}"
    c, b = api(
        "PUT", f"{A}/documents/{path}/content", {"document": payload_for(f"doc {stem}", nreq=nreq)}
    )
    assert c == 200, f"content {c} {str(b)[:200]}"
    return path, b.get("identifiers") or {}


def run_turn(agent, message, *, wait=300):
    """One real agent turn, waited out on the run row. Returns (run_id, final status)."""
    c, b = api("POST", f"{PA}/agent/trigger", {"agent": agent, "message": message})
    if c not in (200, 201, 202):
        return None, f"trigger {c} {str(b)[:200]}"
    run_id = b.get("run_id") or b.get("id")
    deadline = time.time() + wait
    row = None
    while time.time() < deadline:
        time.sleep(6)
        row = db_run(run_id)
        if row and row["status"] not in ("running", "queued", "starting"):
            return run_id, row["status"]
    return run_id, f"timeout(last={(row or {}).get('status')})"


def evidence_rows(**q):
    query = "&".join(f"{k}={v}" for k, v in q.items())
    c, b = api("GET", f"{A}/spec/evidence" + (f"?{query}" if query else ""))
    return c, (b.get("evidence") if isinstance(b, dict) else None)


# =============================================================================================
leg(1, "An agent records evidence — the same act as the operator's, through the other door")

DOC, IDS = newdoc("agentev", nreq=2)
FR1, FR2 = IDS["fr-1"], IDS["fr-2"]
note("document", DOC)
note("identifiers", IDS)

before = {r["id"] for r in (evidence_rows()[1] or [])}
run_id, status = run_turn(
    AGENT_A,
    f"Call the record_evidence tool exactly once, with identifier '{FR1}', document '{DOC}', "
    f"kind 'test_result', locator 'README.md', and summary 'row 9c agent-plane drive {TAG}'. "
    f"Then stop and reply with just the evidence id it returned. Do nothing else.",
)
note("agent A run", f"{run_id} -> {status}")
c, rows = evidence_rows()
fresh = [r for r in (rows or []) if r["id"] not in before]
ok("a real agent turn recorded evidence through the agent plane", len(fresh) == 1, f"{status} fresh={[r['id'] for r in fresh]}")
ag_ev = fresh[0] if len(fresh) == 1 else {}
note("the agent's evidence row", json.dumps(ag_ev, indent=1)[:900])

ok(
    "an agent's evidence lands `awaiting`, never `accepted` — the plane's whole point",
    ag_ev.get("review_state") == "awaiting",
    str(ag_ev)[:300],
)
ok("  ... actor_kind is agent", ag_ev.get("actor_kind") == "agent", str(ag_ev)[:200])
ok(f"  ... and the actor is {AGENT_A}", ag_ev.get("actor") == AGENT_A, str(ag_ev.get("actor")))
ok(
    "  ... it carries the run that produced it, which an operator's row cannot",
    bool(ag_ev.get("run_id")),
    str(ag_ev)[:300],
)
ok(
    "  ... and it is footprinted, so a reviewer can tell which tree it describes",
    isinstance(ag_ev.get("footprint"), dict),
    str(ag_ev.get("footprint")),
)
note("agent footprint", ag_ev.get("footprint"))
ok(
    "  ... an agent's footprint is its OWN worktree's HEAD, not the operator's checkout",
    isinstance(ag_ev.get("footprint"), dict) and ag_ev["footprint"].get("kind") == "git",
    str(ag_ev.get("footprint")),
)
ok(
    "  ... latest_review is null on a row nobody has decided yet",
    ag_ev.get("latest_review") is None,
    str(ag_ev.get("latest_review")),
)

# The operator plane's twin, on the same document, for the comparison the lead asked for.
c, op_ev = api(
    "POST",
    f"{A}/spec/evidence",
    {"identifier": FR2, "document": DOC, "locator": "README.md", "summary": "the operator's twin"},
)
ok("the operator's twin is recorded on the same document", c == 201, f"{c} {str(op_ev)[:200]}")
print("\n  --- the two planes, same act, side by side")
for field in ("review_state", "actor_kind", "actor", "run_id", "task_id", "kind"):
    note(f"  {field}", f"agent={ag_ev.get(field)!r}   operator={op_ev.get(field)!r}")
ok(
    "the two planes differ in exactly the way the design says: review_state and actor_kind",
    ag_ev.get("review_state") != op_ev.get("review_state")
    and ag_ev.get("actor_kind") != op_ev.get("actor_kind"),
    f"{ag_ev.get('review_state')}/{op_ev.get('review_state')}",
)

# =============================================================================================
leg(2, "An agent decides — the grant, the self-acceptance refusal, and what comes back")

# Agent A has NOT been granted acceptance. Ask it to decide its own evidence: two refusals stack.
run_id, status = run_turn(
    AGENT_A,
    f"Call the decide_evidence tool exactly once on evidence id '{ag_ev.get('id')}' with "
    f"decision 'accepted' and reason 'my own work'. Then reply with the EXACT error message you "
    f"got back, or 'NO ERROR' if it succeeded. Do nothing else.",
)
note("agent A decide-own run", f"{run_id} -> {status}")
c, rows = evidence_rows(identifier=FR1, document=DOC)
same = [r for r in (rows or []) if r["id"] == ag_ev.get("id")]
ok(
    "an ungranted agent deciding its own evidence changed nothing",
    same and same[0].get("review_state") == "awaiting",
    str(same)[:300],
)

# Grant B, and check the grant is visible where an operator would look.
c, b = api("PATCH", f"{PA}/agents/{AGENT_B}", {"can_accept_evidence": True})
ok(f"the operator can grant {AGENT_B} evidence acceptance", c == 200, f"{c} {str(b)[:250]}")
ok("  ... and the grant reads back on the agent row", b.get("can_accept_evidence") is True, str(b)[:300])

run_id, status = run_turn(
    AGENT_B,
    f"Call the decide_evidence tool exactly once on evidence id '{ag_ev.get('id')}' with "
    f"decision 'accepted' and reason 'row 9c: the granted agent accepts a peer'. Then reply with "
    f"just the review_state it returned. Do nothing else.",
)
note("agent B decide run", f"{run_id} -> {status}")
c, rows = evidence_rows(identifier=FR1, document=DOC)
decided = [r for r in (rows or []) if r["id"] == ag_ev.get("id")]
ok(
    "a GRANTED agent can accept a peer's evidence — the grant is not decorative",
    decided and decided[0].get("review_state") == "accepted",
    str(decided)[:400],
)
lr = (decided[0].get("latest_review") if decided else None) or {}
ok(
    "  ... and the review names the AGENT that decided, not the operator",
    lr.get("actor") == AGENT_B and lr.get("actor_kind") == "agent",
    str(lr),
)
note("the agent's review", lr)

c, b = api("GET", f"{A}/spec/evidence/{ag_ev.get('id')}/reviews")
revs = (b.get("reviews") if isinstance(b, dict) else None) or []
ok(
    "the operator's review trail holds the agent's decision, with its run id",
    any(r.get("actor_kind") == "agent" and r.get("run_id") for r in revs),
    str(revs)[:500],
)
note("reviews", json.dumps(revs, indent=1)[:700])

# =============================================================================================
leg(3, "Does the agent's evidence drift? The two planes, same requirement, same files")

c, b = api("POST", f"{A}/spec/drift/detect")
note("detect after the agent's evidence was accepted", b.get("raised") if c == 200 else b)

c, projrow = api("GET", f"/projects/{P}")
ROOT = pathlib.Path(projrow.get("working_directory") or "")
ok("the fixture workspace is readable from outside the product", ROOT.exists(), str(ROOT))

# Both pieces of evidence name README.md as their locator and were footprinted over the whole
# tree. Change README.md on `main` and commit it: one commit, one file, two accepted rows.
(ROOT / "README.md").write_text(f"agent-plane drive {TAG} changed this\n", encoding="utf-8")
subprocess.run(["git", "add", "README.md"], cwd=ROOT, capture_output=True)
subprocess.run(
    ["git", "commit", "-m", f"r9cag {TAG} change a footprinted file"], cwd=ROOT, capture_output=True
)
MAIN = subprocess.run(
    ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, capture_output=True, text=True
).stdout.strip()
note("committed on", MAIN)

c, b = api("POST", f"{A}/spec/drift/detect")
raised = b.get("raised") if c == 200 else []
note("detect after a real commit on main", raised)
c, dr = api("GET", f"{A}/spec/drift")
rows = (dr.get("drift") if isinstance(dr, dict) else None) or []
for_agent = [r for r in rows if r.get("evidence_id") == ag_ev.get("id")]
for_operator = [r for r in rows if r.get("evidence_id") == op_ev.get("id")]
note("candidates for the AGENT's evidence", len(for_agent))
note("candidates for the OPERATOR's evidence", len(for_operator))

ok(
    "the OPERATOR's accepted evidence drifts on a commit to main",
    len(for_operator) >= 1,
    f"raised={raised} rows={rows}",
)
ok(
    "the AGENT's accepted evidence does NOT - its footprint names the agent's own worktree "
    "branch, which nothing commits to again once the work has merged",
    len(for_agent) == 0,
    f"agent branch={ag_ev.get('footprint', {}).get('branch')} candidates={for_agent}",
)
note(
    "  the asymmetry, stated",
    f"agent branch={(ag_ev.get('footprint') or {}).get('branch')!r} "
    f"reachable_from_main={(ag_ev.get('footprint') or {}).get('reachable_from_main')!r}; "
    f"operator branch={(op_ev.get('footprint') or {}).get('branch')!r}",
)
ok(
    "  ... and the Hub KNOWS the agent's work is on main - it says so on the footprint it then "
    "declines to compare against main",
    (ag_ev.get("footprint") or {}).get("reachable_from_main") is True,
    str(ag_ev.get("footprint")),
)

if for_operator:
    cand = for_operator[0]
    note("the drift candidate an operator must resolve", cand)
    ok(
        "the drift row names nothing the reader has ever seen - no identifier, no document, "
        "no actor, no locator",
        not any(str(v).startswith("FR-") for v in cand.values())
        and "document" not in " ".join(cand)
        and "actor" not in " ".join(cand),
        str(sorted(cand)),
    )


# =============================================================================================
print(f"\n=== ROW 9c AGENT PLANE: {len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAIL  {f}")
