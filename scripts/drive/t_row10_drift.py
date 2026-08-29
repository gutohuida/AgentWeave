"""T-ROW10-DRIFT: drive the requirement-drift loop end to end, operator side.

Row 10 of TESTPLAN.md was never driven: evidence is recorded and accepted, then the ground under
it moves, and the operator is asked whether the specification or the implementation was wrong.
Every assertion here names an artefact and an exact status code.

Needs its own throwaway git repository (created by the caller):
    C:\\Users\\huida\\Documents\\drive-drift-0829, branch `main`, one seed commit.

Run:
    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_row10_drift.py
"""

import subprocess
import sys
from pathlib import Path

from aw import api, show

REPO = Path(r"C:\Users\huida\Documents\drive-drift-0829")
NAME = "drive-drift-0829"

VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'GOOD' if ok else 'BAD '}] {label}" + (f" -- {detail}" if detail else ""))


def git(*args):
    r = subprocess.run(
        ["git", *args], cwd=str(REPO), capture_output=True, text=True, timeout=60
    )
    if r.returncode != 0:
        print(f"  git {' '.join(args)} -> {r.returncode}: {r.stderr.strip()}")
    return r.stdout.strip()


# Every run must write content no earlier run produced: a file that returns to its footprinted
# blob is NOT drift, which is correct behaviour but silently turns an assertion vacuous. The nonce
# is the repo's own commit count, so each run's blobs are new.
def nonce():
    return len(
        subprocess.run(
            ["git", "log", "--oneline"], cwd=str(REPO), capture_output=True, text=True
        ).stdout.splitlines()
    )


N = nonce()


def cart(variant):
    """The one place cart.py's content is written, stamped with the run's nonce."""
    return "\n".join(
        [
            f"def discount(total, pct):  # run {N}",
            f"    return {variant}",
            "",
        ]
    )


# ---------------------------------------------------------------------------
# 0. The project
# ---------------------------------------------------------------------------
code, body = api("POST", "/projects/open", {"path": str(REPO), "name": NAME})
if code in (200, 201):
    P = body["id"]
else:
    code2, listing = api("GET", "/projects")
    matches = [p for p in listing if p.get("working_directory") == str(REPO)] if code2 == 200 else []
    if not matches:
        show("create project FAILED", code, body)
        sys.exit(1)
    P = matches[0]["id"]
print(f"project {P}  ({NAME})")

# ---------------------------------------------------------------------------
# 1. A document with one requirement, one criterion, one task -- approved so the
#    requirement is real and a task exists to hang evidence off.
# ---------------------------------------------------------------------------
code, doc = api("POST", f"/projects/{P}/project/documents", {"title": "drift drive"})
check("create document -> 201", code == 201, f"got {code}")
path = doc["path"]

payload = {
    "schema_version": 1,
    "kind": doc["kind"],
    "title": "drift drive",
    "summary": "Drive the evidence -> accept -> ground moves -> drift -> resolve loop.",
    "problem": "Row 10 of the test plan was never driven live.",
    "scope": {"in_scope": ["cart.discount"], "non_goals": ["Anything else in the repo"]},
    "requirements": [
        {
            "key": "discount-is-percentage",
            "statement": "discount MUST treat pct as a percentage, not a fraction.",
            "modal": "MUST",
        }
    ],
    "acceptance_criteria": [
        {
            "key": "pct-is-percent",
            "requirement": "discount-is-percentage",
            "given": "a total of 100 and a pct of 10",
            "when": "discount runs",
            "then": "it returns 90",
        }
    ],
    "tasks": [
        {
            "key": "verify-discount",
            "title": "Verify discount treats pct as a percentage",
            "description": "Record evidence naming cart.py.",
            "requirements": ["discount-is-percentage"],
        }
    ],
    "algorithms": [],
    "design": "",
    "evidence": {"checked": [], "limits": []},
    "lifecycle": "one-off",
    "open_questions": [],
}
code, res = api("PUT", f"/projects/{P}/project/documents/{path}/content", {"document": payload})
check("write content -> 200", code == 200, f"got {code}: {str(res)[:200]}")
# The requirement's identifier is minted by the Hub (FR-1), not the key the document used.
REQ = (res.get("identifiers") or {}).get("discount-is-percentage") if code == 200 else None
check("write content mints an identifier for the requirement", REQ is not None, str(res)[:160])
code, res = api("POST", f"/projects/{P}/project/documents/close-exploration?path={path}")
check("close-exploration -> 200", code == 200, f"got {code}")
code, res = api("POST", f"/projects/{P}/project/documents/propose?path={path}")
check("propose -> 200", code == 200, f"got {code}")
code, res = api(
    "POST",
    f"/projects/{P}/project/documents/phase?path={path}&to=approved",
    {"reason": "drift drive"},
)
check("phase -> approved -> 200", code == 200, f"got {code}: {str(res)[:200]}")
task_id = res["tasks_created"][0]
print(f"task {task_id}")

# ---------------------------------------------------------------------------
# 2. Evidence, recorded by the operator against the seed commit, then accepted.
# ---------------------------------------------------------------------------
(REPO / "cart.py").write_text(cart('total * (1 - pct / 100)'), encoding="utf-8")
git("add", "cart.py")
git("-c", "user.email=drive@local", "-c", "user.name=drive", "commit", "-q", "-m", f"seed for run {N}")
seed = git("rev-parse", "HEAD")
code, ev = api(
    "POST",
    f"/projects/{P}/project/spec/evidence",
    {
        "identifier": REQ,
        "summary": "discount(100, 10) == 90 at the seed commit.",
        "kind": "test_result",
        "locator": "cart.py",
        "task_id": task_id,
        "document": path,
    },
)
check("record evidence -> 201", code == 201, f"got {code}: {str(ev)[:200]}")
ev_id = ev.get("id") if isinstance(ev, dict) else None
REQ_ROW = ev.get("requirement_id") if isinstance(ev, dict) else None
fp = (ev or {}).get("footprint") or {}
check(
    "footprint is git, on branch main, at the seed commit",
    fp.get("kind") == "git" and fp.get("branch") == "main" and fp.get("commit_sha") == seed,
    f"kind={fp.get('kind')} branch={fp.get('branch')} sha={str(fp.get('commit_sha'))[:8]} seed={seed[:8]}",
)

code, res = api(
    "POST",
    f"/projects/{P}/project/spec/evidence/{ev_id}/decision",
    {"decision": "accepted", "reason": "operator drive"},
)
check("accept evidence -> 200", code == 200, f"got {code}: {str(res)[:200]}")
check("review_state now accepted", (res or {}).get("review_state") == "accepted", str(res)[:160])
check(
    "operator-recorded evidence was ALREADY accepted on arrival (drift only ever sees accepted rows)",
    (ev or {}).get("review_state") == "accepted",
    f"review_state at record time: {(ev or {}).get('review_state')}",
)


def mine(raised):
    """Only the candidates raised for THIS run's evidence.

    An earlier run's evidence sits in the same project with an older baseline, so every scan
    legitimately raises rows that have nothing to do with this one. Asserting `raised == []`
    made the harness fail against the product being right.
    """
    if not raised:
        return []
    code, listing = api("GET", f"/projects/{P}/project/spec/drift")
    if code != 200:
        return [f"HTTP {code}"]
    by_id = {r["id"]: r for r in listing.get("drift") or []}
    return [d for d in raised if (by_id.get(d) or {}).get("evidence_id") == ev_id]


def coverage_state():
    code, body = api("GET", f"/projects/{P}/project/spec/coverage")
    if code != 200:
        return f"HTTP {code}"
    rows = body.get("requirements") or body.get("coverage") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    for row in rows:
        if isinstance(row, dict) and row.get("requirement_id") == REQ_ROW:
            return row.get("state") or row.get("coverage")
    return f"unrecognised shape: {str(body)[:200]}"


check("coverage reads verified after acceptance", coverage_state() == "verified", coverage_state())

# ---------------------------------------------------------------------------
# 3. Nothing has moved -- detect must raise nothing.
# ---------------------------------------------------------------------------
code, res = api("POST", f"/projects/{P}/project/spec/drift/detect")
check("detect with an unchanged tree -> 200, nothing raised for this evidence", code == 200 and mine(res.get("raised")) == [], f"got {code}: {res}")

# ---------------------------------------------------------------------------
# 4. Move the ground: change the footprinted file and commit it on the same branch.
# ---------------------------------------------------------------------------
(REPO / "cart.py").write_text(cart('total * (1 - pct)'), encoding="utf-8")
git("add", "cart.py")
git("-c", "user.email=drive@local", "-c", "user.name=drive", "commit", "-q", "-m", "pct is a fraction now")
moved_sha = git("rev-parse", "HEAD")
check("the repo moved on branch main", moved_sha != seed and git("rev-parse", "--abbrev-ref", "HEAD") == "main", moved_sha[:8])

code, res = api("POST", f"/projects/{P}/project/spec/drift/detect")
raised = mine(res.get("raised")) if code == 200 else None
check("detect after the change -> 200, exactly one candidate for this evidence", code == 200 and isinstance(raised, list) and len(raised) == 1, f"got {code}: {res}")
drift_id = raised[0] if raised else None

code, listing = api("GET", f"/projects/{P}/project/spec/drift")
rows = listing.get("drift") if code == 200 else []
row = next((r for r in rows if r["id"] == drift_id), None) if rows else None
check("GET /spec/drift lists it as a candidate", code == 200 and row is not None and row["state"] == "candidate", str(row)[:200])
observed = (row or {}).get("observed") or {}
check(
    "observed names cart.py and only cart.py, with was/now blob ids",
    list(observed) == ["cart.py"] and set(observed.get("cart.py", {})) == {"was", "now"} and observed["cart.py"]["was"] != observed["cart.py"]["now"],
    str(observed)[:240],
)
check("the candidate hangs off the accepted evidence", (row or {}).get("evidence_id") == ev_id, f"{(row or {}).get('evidence_id')} vs {ev_id}")
check("coverage now reads drifting", coverage_state() == "drifting", coverage_state())

# A second scan must not ask the same question twice.
code, res = api("POST", f"/projects/{P}/project/spec/drift/detect")
check("a second scan raises nothing while the candidate is open", code == 200 and mine(res.get("raised")) == [], f"got {code}: {res}")

# ---------------------------------------------------------------------------
# 5. Resolving it -- the refusal first, then the answer.
# ---------------------------------------------------------------------------
code, res = api("POST", f"/projects/{P}/project/spec/drift/{drift_id}/resolve", {"resolution": "whatever"})
check(
    "an unknown resolution -> 422 naming unknown_resolution",
    code == 422 and (res.get("detail") or {}).get("code") == "unknown_resolution",
    f"got {code}: {str(res)[:200]}",
)
code, res = api("POST", f"/projects/{P}/project/spec/drift/nope-not-a-drift/resolve", {"resolution": "no_change_required"})
check("an unknown drift id -> 404", code == 404, f"got {code}: {str(res)[:160]}")

code, res = api(
    "POST", f"/projects/{P}/project/spec/drift/{drift_id}/resolve", {"resolution": "implementation_corrected"}
)
check(
    "resolve -> 200, state resolved, resolution recorded",
    code == 200 and res.get("state") == "resolved" and res.get("resolution") == "implementation_corrected",
    f"got {code}: {str(res)[:200]}",
)
check("coverage stops reading drifting once resolved", coverage_state() != "drifting", coverage_state())

# ---------------------------------------------------------------------------
# 6. The resolution must hold: the SAME change must not be re-raised, and a NEW
#    change must be.
# ---------------------------------------------------------------------------
code, res = api("POST", f"/projects/{P}/project/spec/drift/detect")
check(
    "a scan after resolving does not re-raise the same change",
    code == 200 and mine(res.get("raised")) == [],
    f"got {code}: {res}",
)

(REPO / "cart.py").write_text(cart('round(total * (1 - pct / 100), 2)'), encoding="utf-8")
git("add", "cart.py")
git("-c", "user.email=drive@local", "-c", "user.name=drive", "commit", "-q", "-m", "round it")
code, res = api("POST", f"/projects/{P}/project/spec/drift/detect")
check(
    "moving the ground AGAIN raises a fresh candidate",
    code == 200 and len(mine(res.get("raised"))) == 1,
    f"got {code}: {res}",
)
second = mine(res.get("raised"))[0] if mine(res.get("raised")) else None
check("the fresh candidate is a different row", second is not None and second != drift_id, f"{second} vs {drift_id}")

# ---------------------------------------------------------------------------
# 7. A file that was NOT footprinted moving must not raise anything (the footprint
#    is the whole tree today, so this is the documented over-reach: assert what it
#    actually does rather than what the model says).
# ---------------------------------------------------------------------------
code, res = api("POST", f"/projects/{P}/project/spec/drift/{second}/resolve", {"resolution": "no_change_required"})
check("resolve the second candidate -> 200", code == 200 and res.get("state") == "resolved", f"got {code}: {str(res)[:160]}")
(REPO / f"unrelated-{N}.txt").write_text(
    f"nothing to do with the requirement, run {N}\n", encoding="utf-8"
)
git("add", f"unrelated-{N}.txt")
git("-c", "user.email=drive@local", "-c", "user.name=drive", "commit", "-q", "-m", "an unrelated file")
code, res = api("POST", f"/projects/{P}/project/spec/drift/detect")
check(
    "adding an UNRELATED file raises nothing (footprint compares only footprinted paths)",
    code == 200 and mine(res.get("raised")) == [],
    f"got {code}: {res} -- if this raised, _changed is comparing added paths too",
)

# ---------------------------------------------------------------------------
# 8. Putting the file back the way the footprint recorded it is NOT drift. Found by
#    accident on the first run of this harness -- a second run rewrote cart.py to a
#    blob an earlier run had already produced, and the scan correctly said nothing.
# ---------------------------------------------------------------------------
(REPO / "cart.py").write_text(cart('total * (1 - pct / 100)'), encoding="utf-8")
git("add", "cart.py")
git("-c", "user.email=drive@local", "-c", "user.name=drive", "commit", "-q", "-m", "back to the footprinted content")
code, res = api("POST", f"/projects/{P}/project/spec/drift/detect")
check(
    "reverting the file to its footprinted blob raises nothing",
    code == 200 and mine(res.get("raised")) == [],
    f"got {code}: {res}",
)
code, listing = api("GET", f"/projects/{P}/project/spec/drift")
open_now = (
    [
        r
        for r in (listing.get("drift") or [])
        if r["state"] == "candidate" and r["evidence_id"] == ev_id
    ]
    if code == 200
    else None
)
check("no candidate of THIS run's evidence is left open", open_now == [], str(open_now)[:200])

# ---------------------------------------------------------------------------
print()
bad = [v for v in VERDICTS if not v[1]]
print(f"{len(VERDICTS) - len(bad)}/{len(VERDICTS)} good")
for label, _, detail in bad:
    print(f"  BAD: {label} -- {detail}")
print(f"project {P}, repo {REPO}")
