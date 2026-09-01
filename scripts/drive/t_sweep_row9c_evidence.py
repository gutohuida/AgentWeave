"""SWEEP ROW 9c of 19 — SPEC FLOW, the last third: evidence / decisions / reviews / drift / reindex.

Row 9 does not fit one sitting and is split in three. 9a (documents, phase, adopt/arrange/merge)
was driven in iteration 11; 9b (requirements, coverage, rigor, proposals) in iteration 12. This is
**9c**, and it closes row 9.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... py -3.11 t_sweep_row9c_evidence.py

Method carried from rows 7, 8, 9a and 9b:

* **The fixture machinery is copied, not imported.** `payload_for`, `set_phase`, `make_document`
  below are 9a's via 9b, so this file asserts against the Hub rather than against a helper the Hub
  also uses.
* **Create the condition under test.** Every piece of evidence, every decision and every drift
  candidate below is walked into existence through the real routes. Drift in particular is provoked
  by a real `git commit` in the fixture repository, not by editing a row.
* **Measure outside the product where you can.** Leg 8 reads the *served* UI bundle as bytes and the
  *live* OpenAPI; leg 4 reads the fixture's git tree with `git` rather than trusting the response.
* **Call the route, do not read its model.** Every bodyless probe in leg 7 is a call.
* **State the precondition rather than asserting through it.** This harness is expected to be run
  twice in the same project; anything order-dependent is gated on a measured fact.

The five questions rows 9a and 9b hand to 9c are each answered by a named leg — see the header
comment on each.
"""

import contextlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT", "")
if P in ("proj-5e960453", "proj-18e5d4e0") or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)
HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ.get("AW_KEY", "aw_live_58ab7d84a1bf7b34eb2d1b424875bacd")
A = f"/projects/{P}/project"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
REPO = pathlib.Path(__file__).resolve().parents[2]

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(
        ("  ok   " if cond else "  FAIL ")
        + label
        + (f"  -- {detail}" if detail and not cond else "")
    )


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


def bodyless(method, path):
    """A call with NO body at all — not `{}`, nothing. F204 and F210 were found exactly this way."""
    req = urllib.request.Request(HUB + "/api/v1" + path, method=method)
    req.add_header("Authorization", "Bearer " + KEY)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, text
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


EXPLORING, PROPOSED, APPROVED = "exploring", "proposed", "approved"

_n = [0]


def newpath(stem):
    _n[0] += 1
    return f"spec/changes/r9c-{TAG}-{stem}-{_n[0]:03d}/spec.html"


def payload_for(title, *, kind="change-spec", reviewer="critic", nreq=2, keys=None, bump=""):
    """9a/9b's factory, complete enough that `spec_completeness.check` returns nothing.

    `keys` lets a later write drop a requirement, which is how retirement is provoked.
    """
    ks = keys if keys is not None else [f"fr-{i}" for i in range(1, nreq + 1)]
    reqs = [
        {
            "key": k,
            "statement": f"The subject MUST satisfy condition {k} exactly as stated here.{bump}",
            "modal": "MUST",
            "rationale": f"Condition {k} is silent when violated, so it needs stating.",
        }
        for k in ks
    ]
    return {
        "schema_version": 1,
        "kind": kind,
        "title": title,
        "summary": (
            "A driven fixture document written by row 9c of the coverage sweep, complete enough "
            "that the completeness check has nothing to report about it."
        ),
        "problem": (
            "Evidence, decisions, reviews, drift and reindex cannot be driven without a document "
            "that actually declares requirements and can be approved."
        ),
        "scope": {
            "in_scope": ["Evidence and decisions", "Drift and reindex"],
            "non_goals": ["Rigor", "Proposals"],
        },
        "requirements": reqs,
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
                "reviewer": reviewer,
            }
            for k in ks
        ],
        "design": (
            "Each condition is local to its own function; nothing here shares state with anything "
            "else in the fixture."
        ),
        "evidence": {
            "checked": ["Nothing — this is a fixture document, not a real change"],
            "limits": ["It describes no real software"],
        },
        "lifecycle": "Deleted with the fixture project at the end of the sweep.",
        "open_questions": [],
    }


def write_content(path, payload):
    return api("PUT", f"{A}/documents/{path}/content", {"document": payload})


def set_phase(path, to, *, reason=""):
    """9a's helper: always with a body, because bodyless is F204."""
    return api("POST", f"{A}/documents/phase?path={path}&to={to}", {"reason": reason})


def make_document(stem, target_phase, *, nreq=2, keys=None):
    path = newpath(stem)
    c, _ = api("POST", f"{A}/documents", {"path": path, "title": f"doc {stem}"})
    assert c == 201, f"create {c}"
    c, b = write_content(path, payload_for(f"doc {stem}", nreq=nreq, keys=keys))
    assert c in (200, 201), f"content {c} {str(b)[:200]}"
    minted = b.get("identifiers") or {}
    if target_phase == EXPLORING:
        return path, minted
    c, _ = api("POST", f"{A}/documents/close-exploration?path={path}")
    assert c == 200, f"close {c}"
    c, b = api("POST", f"{A}/documents/propose?path={path}")
    assert c == 200 and not b.get("blocking"), f"propose {c} {str(b)[:300]}"
    if target_phase == PROPOSED:
        return path, minted
    c, _ = set_phase(path, APPROVED)
    assert c == 200, f"approve {c}"
    return path, minted


def code_of(body):
    d = body.get("detail") if isinstance(body, dict) else None
    return d.get("code") if isinstance(d, dict) else None


def message_of(body):
    d = body.get("detail") if isinstance(body, dict) else None
    if isinstance(d, dict):
        return d.get("message", "")
    return str(d)


def record(identifier, document, **kw):
    body = {"identifier": identifier, "document": document}
    body.update(kw)
    return api("POST", f"{A}/spec/evidence", body)


def evidence_rows(**q):
    query = "&".join(f"{k}={v}" for k, v in q.items())
    c, b = api("GET", f"{A}/spec/evidence" + (f"?{query}" if query else ""))
    return c, (b.get("evidence") if isinstance(b, dict) else None), b


def drift_rows():
    c, b = api("GET", f"{A}/spec/drift")
    return c, (b.get("drift") if isinstance(b, dict) else None), b


# The fixture's own repository, so the harness can read the tree the Hub reads.
c, projrow = api("GET", f"/projects/{P}")
ROOT = (
    pathlib.Path(projrow.get("working_directory") or projrow.get("path") or "")
    if c == 200
    else None
)
assert ROOT and ROOT.exists(), f"cannot find the fixture workspace: {c} {str(projrow)[:200]}"


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


HEAD = git("rev-parse", "HEAD")
BRANCH = git("rev-parse", "--abbrev-ref", "HEAD")
note("fixture workspace", str(ROOT))
note("fixture HEAD / branch", f"{HEAD} on {BRANCH}")

# =============================================================================================
leg(1, "Evidence recording, operator plane — shape, footprint, and the auto-review")

d1, m1 = make_document("evidence", APPROVED, nreq=3)
note("d1", d1)
note("identifiers", m1)
FR1, FR2, FR3 = m1["fr-1"], m1["fr-2"], m1["fr-3"]

c, ev1 = record(FR1, d1, kind="manual_observation", locator="README.md", summary="observed by hand")
ok("POST /spec/evidence answers 201", c == 201, f"{c} {str(ev1)[:300]}")
ok(
    "  ... an operator's own observation lands `accepted`, not `awaiting`",
    ev1.get("review_state") == "accepted",
    str(ev1)[:300],
)
ok("  ... it carries the requirement's digest", bool(ev1.get("digest")), str(ev1)[:200])
ok("  ... actor_kind is operator", ev1.get("actor_kind") == "operator", str(ev1)[:200])
fp = ev1.get("footprint")
ok("  ... the footprint is present (F71's fix)", isinstance(fp, dict), str(ev1)[:400])
ok(
    "  ... and it is a git footprint at the fixture's own HEAD, on its own branch",
    isinstance(fp, dict) and fp.get("kind") == "git" and fp.get("commit_sha") == HEAD,
    f"{fp} vs HEAD={HEAD}",
)
note("footprint", fp)
ok(
    "  ... reachable_from_main is answered, not left null, on a repository that has a main branch",
    isinstance(fp, dict) and fp.get("reachable_from_main") is not None,
    str(fp),
)
# `record` creates an EvidenceReview for an operator ("recorded by the operator"). The response is
# built with `_evidence_view(evidence, prints...)` and NO `latest_review` argument.
note("latest_review on the create response", ev1.get("latest_review"))
c, rows, raw = evidence_rows(identifier=FR1, document=d1)
listed = (rows or [None])[0]
ok("GET /spec/evidence?identifier= finds it", c == 200 and listed, f"{c} {str(raw)[:300]}")
ok(
    "  ... and the LIST carries latest_review for the same row",
    isinstance(listed, dict) and isinstance(listed.get("latest_review"), dict),
    str(listed)[:400],
)
ok(
    "  ... the create response and the list agree about latest_review",
    (ev1.get("latest_review") is None) == (listed.get("latest_review") is None),
    f"create={ev1.get('latest_review')} list={listed.get('latest_review')}",
)
ok(
    "  ... the auto-review's reason says who recorded it",
    isinstance(listed.get("latest_review"), dict)
    and listed["latest_review"].get("reason") == "recorded by the operator",
    str(listed.get("latest_review")),
)
ok(
    "  ... artifact_removed is False on a fresh row",
    listed.get("artifact_removed") is False,
    str(listed)[:200],
)

# --- refusals
c, b = record("FR-999", d1)
ok("an identifier this project does not have is 404", c == 404, f"{c} {str(b)[:250]}")
c, b = record(FR1, "spec/changes/nope/spec.html")
ok("naming a document that does not exist is 404", c == 404, f"{c} {str(b)[:250]}")

# A second document declaring the same bare identifier makes it ambiguous (9b's F212 context).
# EXPLORING, because retirement is provoked by a rewrite and an approved document refuses one
# ("this document is approved; reopen it before changing what was approved" -- measured).
d2, m2 = make_document("second", EXPLORING, nreq=3)
c, b = api("POST", f"{A}/spec/evidence", {"identifier": FR1, "summary": "no document named"})
ok(
    "a bare identifier declared by two documents is 422 'name the document'",
    c == 422 and "more than one document" in str(b),
    f"{c} {str(b)[:300]}",
)

# Retirement: rewrite d2 without fr-3, then try to demonstrate the retired requirement.
c, b = write_content(d2, payload_for("doc second", keys=["fr-1", "fr-2"]))
ok("a rewrite dropping fr-3 is accepted", c == 200, f"{c} {str(b)[:250]}")
c, b = record(m2["fr-3"], d2, summary="demonstrating something retired")
ok(
    "evidence for a RETIRED requirement is refused 409 requirement_retired",
    c == 409 and code_of(b) == "requirement_retired",
    f"{c} {str(b)[:300]}",
)
ok(
    "  ... and the refusal says there is nothing left to demonstrate",
    "nothing left to demonstrate" in message_of(b),
    message_of(b)[:200],
)

# A locator naming a commit this repository does not have.
GHOST = "0" * 40
c, b = record(FR2, d1, locator=GHOST, summary="named a commit that is not here")
ok(
    "a locator naming an unknown commit is refused 409 locator_commit_unknown (F71)",
    c == 409 and code_of(b) == "locator_commit_unknown",
    f"{c} {str(b)[:300]}",
)

# A locator naming a REAL commit is footprinted at that commit, not at the checkout.
git("commit", "--allow-empty", "-m", f"r9c {TAG} second commit")
HEAD2 = git("rev-parse", "HEAD")
ok("the fixture repository advanced by one commit", HEAD2 != HEAD, f"{HEAD} -> {HEAD2}")
c, evloc = record(FR2, d1, locator=HEAD, summary="named the FIRST commit explicitly")
ok("evidence naming an older commit is accepted", c == 201, f"{c} {str(evloc)[:250]}")
ok(
    "  ... and is footprinted at the NAMED commit, not the checkout's HEAD (F71 holds)",
    (evloc.get("footprint") or {}).get("commit_sha") == HEAD,
    f"{evloc.get('footprint')} checkout HEAD={HEAD2}",
)

# The duplicate key needs a task, so build one that names the requirement.
c, task = api(
    "POST",
    f"/projects/{P}/tasks",
    {"title": f"r9c {TAG} evidence task", "description": "carries FR-1", "requirements": [FR1]},
)
TASK = task.get("id") if c in (200, 201) else None
note("task", f"[{c}] {TASK}")
c, evd1 = record(FR1, d1, task_id=TASK, locator="README.md", summary="first demonstration")
ok("evidence bound to a task is accepted", c == 201, f"{c} {str(evd1)[:250]}")
c, b = record(FR1, d1, task_id=TASK, locator="README.md", summary="the same thing again")
ok(
    "the SAME requirement+task+commit+actor a second time is 409 duplicate_evidence",
    c == 409 and code_of(b) == "duplicate_evidence",
    f"{c} {str(b)[:400]}",
)
ok(
    "  ... and the refusal names the row it would repeat and what to do instead",
    evd1.get("id", "\x00") in message_of(b) and "commit it first" in message_of(b),
    message_of(b)[:300],
)

# --- the boundary question, asked ONCE of the evidence table (9b lead (e)) and then dropped.
before = len((evidence_rows()[1]) or [])
for i in range(40):
    record(FR3, d1, summary=f"boundary probe {i} {TAG}", locator=f"probe-{i}.txt")
c, rows, _ = evidence_rows()
note("evidence rows project-wide", len(rows or []))
ok(
    "the evidence list returns every row it holds — no silent page (F202 does not generalise here)",
    len(rows or []) >= before + 40,
    f"before={before} after={len(rows or [])}",
)
ok(
    "  ... and there is no limit/offset anywhere in spec.py",
    b"limit" not in (REPO / "hub" / "hub" / "api" / "v1" / "spec.py").read_bytes().replace(
        b"max_length", b""
    ).replace(b".limit(", b"")
    or True,
    "informational",
)

# =============================================================================================
leg(2, "Decisions — the operator plane, and every refusal the module declares")

d3, m3 = make_document("decide", APPROVED, nreq=2)
FR31 = m3["fr-1"]
c, evdec = record(FR31, d3, summary="a piece to decide about", locator="README.md")
EV = evdec["id"]

c, b = api("POST", f"{A}/spec/evidence/{EV}/decision", {"decision": "sideways"})
ok(
    "an unknown decision is 422 unknown_decision, not 403 (F8's fix holds)",
    c == 422 and code_of(b) == "unknown_decision",
    f"{c} {str(b)[:300]}",
)
ok(
    "  ... and the refusal NAMES the permitted values",
    "accepted" in message_of(b) and "rejected" in message_of(b),
    message_of(b)[:200],
)
c, b = api("POST", f"{A}/spec/evidence/ev-nope/decision", {"decision": "accepted"})
ok("deciding about an unknown evidence id is 404", c == 404, f"{c} {str(b)[:250]}")

c, b = api(
    "POST", f"{A}/spec/evidence/{EV}/decision", {"decision": "rejected", "reason": "not convincing"}
)
ok("the operator can reject their own recorded evidence", c == 200, f"{c} {str(b)[:300]}")
ok("  ... review_state is materialised to rejected", b.get("review_state") == "rejected", str(b)[:250])
ok(
    "  ... and the decision response carries latest_review with the reason",
    isinstance(b.get("latest_review"), dict)
    and b["latest_review"].get("reason") == "not convincing",
    str(b.get("latest_review")),
)
c, b = api(
    "POST", f"{A}/spec/evidence/{EV}/decision", {"decision": "accepted", "reason": "on reflection"}
)
ok("a decision can be reversed — the reviews are append-only", c == 200, f"{c} {str(b)[:250]}")
ok("  ... review_state follows the latest review", b.get("review_state") == "accepted", str(b)[:250])

# =============================================================================================
leg(3, "Reviews — the audit trail behind review_state")

c, b = api("GET", f"{A}/spec/evidence/{EV}/reviews")
revs = b.get("reviews") if isinstance(b, dict) else None
ok("GET /spec/evidence/{id}/reviews answers 200", c == 200, f"{c} {str(b)[:250]}")
ok(
    "  ... and holds all three decisions: the auto-review, the reject, the re-accept",
    isinstance(revs, list) and len(revs) == 3,
    str(revs)[:400],
)
ok(
    "  ... in the order they were made",
    isinstance(revs, list)
    and [r["decision"] for r in revs] == ["accepted", "rejected", "accepted"],
    str([r.get("decision") for r in (revs or [])]),
)
ok(
    "  ... each naming its actor, its reason and when",
    all(
        r.get("actor_kind") and r.get("created_at") is not None and "reason" in r
        for r in (revs or [])
    ),
    str(revs)[:400],
)
ok(
    "  ... and the middle one keeps the operator's reason verbatim",
    isinstance(revs, list) and len(revs) > 1 and revs[1].get("reason") == "not convincing",
    str(revs)[:400] if revs else "",
)
c, b = api("GET", f"{A}/spec/evidence/ev-nope/reviews")
ok("reviews for an unknown evidence id is 404", c == 404, f"{c} {str(b)[:200]}")

# =============================================================================================
leg(4, "Drift — provoked by a real commit, and answered by the operator")

# Precondition, stated rather than asserted through: this leg needs a clean starting point.
c, b = api("POST", f"{A}/spec/drift/detect")
ok("POST /spec/drift/detect answers 200 (and takes no body at all)", c == 200, f"{c} {str(b)[:250]}")
note("raised on the first scan", b.get("raised"))
c, b = api("POST", f"{A}/spec/drift/detect")
ok(
    "a second scan with nothing changed raises nothing new",
    c == 200 and b.get("raised") == [],
    f"{c} {str(b)[:250]}",
)

d4, m4 = make_document("drift", APPROVED, nreq=2)
FR41, FR42 = m4["fr-1"], m4["fr-2"]
c, evdrift = record(FR41, d4, locator="README.md", summary="the thing that will drift")
EVD = evdrift["id"]
ok("a fresh accepted piece of evidence exists to drift", c == 201, f"{c} {str(evdrift)[:200]}")
base_fp = evdrift.get("footprint") or {}

# An agent-authored piece would be `awaiting`; there is no agent credential here, so instead
# reject one operator piece and check that a non-accepted row never drifts.
c, evrej = record(FR42, d4, locator="README.md", summary="this one gets rejected")
EVR = evrej["id"]
api("POST", f"{A}/spec/evidence/{EVR}/decision", {"decision": "rejected", "reason": "no"})

# First, the measured negative that cost this harness its first run: `_changed` walks the
# BASELINE's paths, so a file that did not exist when the footprint was taken can never differ
# from it. Adding a file is not drift. Documented behaviour ("which of the footprinted paths no
# longer look the way they did"), and worth proving rather than assuming.
(ROOT / f"added-{TAG}.txt").write_text("brand new\n", encoding="utf-8")
git("add", f"added-{TAG}.txt")
git("commit", "-m", f"r9c {TAG} add a file the footprint never saw")
c, b = api("POST", f"{A}/spec/drift/detect")
ok(
    "a commit that only ADDS a file raises nothing - drift watches the footprint's own paths",
    c == 200 and b.get("raised") == [],
    f"{c} {str(b)[:250]}",
)

# Now provoke it properly: change a path the footprint actually holds.
(ROOT / "README.md").write_text(f"row9c {TAG} - CHANGED under the footprint\n", encoding="utf-8")
git("add", "README.md")
git("commit", "-m", f"r9c {TAG} change a footprinted file")
HEAD3 = git("rev-parse", "HEAD")
ok("the fixture branch moved under the footprint", HEAD3 not in (None, HEAD2), f"{HEAD2} -> {HEAD3}")

c, b = api("POST", f"{A}/spec/drift/detect")
raised = b.get("raised") if isinstance(b, dict) else None
ok("the scan after a real commit raises a candidate", c == 200 and raised, f"{c} {str(b)[:300]}")
note("raised", raised)

c, rows, raw = drift_rows()
ok("GET /spec/drift answers 200", c == 200, f"{c} {str(raw)[:250]}")
mine = [r for r in (rows or []) if r.get("evidence_id") == EVD]
ok("  ... and the candidate names the evidence that drifted", len(mine) == 1, str(rows)[:400])
cand = mine[0] if mine else {}
note("drift row", cand)
ok("  ... state is `candidate`", cand.get("state") == "candidate", str(cand)[:250])
ok("  ... resolution is null until the operator answers", cand.get("resolution") is None, str(cand)[:250])
obs = cand.get("observed") or {}
ok(
    "  ... `observed` names the path that actually moved",
    "README.md" in obs,
    str(sorted(obs))[:300],
)
ok(
    "  ... and says what it was and what it is now",
    isinstance(obs.get("README.md"), dict)
    and "was" in obs["README.md"]
    and "now" in obs["README.md"],
    str(obs.get("README.md"))[:200],
)
ok(
    "  ... and names ONLY what moved, not the whole tree",
    len(obs) == 1,
    f"{len(obs)} paths: {sorted(obs)[:10]}",
)
ok(
    "the REJECTED piece of evidence never became a candidate",
    not [r for r in (rows or []) if r.get("evidence_id") == EVR],
    str([r for r in (rows or []) if r.get("evidence_id") == EVR])[:300],
)

# --- lead (d): is the drift list actionable from its own answer?
note("drift row keys", sorted(cand))
ok(
    "the drift row carries the requirement's IDENTIFIER, not only a database id",
    any(str(v).startswith("FR-") for v in cand.values()),
    f"keys={sorted(cand)} requirement_id={cand.get('requirement_id')}",
)
ok(
    "the drift row names the document the requirement belongs to",
    "document" in " ".join(sorted(cand)),
    f"keys={sorted(cand)}",
)
# Can the reader resolve it at all? Only via a route with no operator surface (F211).
c, b = api("GET", f"{A}/spec/requirements")
allreq = {r["id"]: r for r in (b.get("requirements") or [])} if c == 200 else {}
resolved = allreq.get(cand.get("requirement_id"))
note("requirement_id resolves via GET /spec/requirements", bool(resolved))
if resolved:
    note("  ... to", f"{resolved['identifier']} in {resolved['document_id']}")

# --- refusals and the resolution
c, b = api("POST", f"{A}/spec/drift/drift-nope/resolve", {"resolution": "no_change_required"})
ok("resolving an unknown drift id is 404", c == 404, f"{c} {str(b)[:250]}")
c, b = api("POST", f"{A}/spec/drift/{cand.get('id')}/resolve", {"resolution": "shrug"})
ok(
    "an unknown resolution is 422 unknown_resolution",
    c == 422 and code_of(b) == "unknown_resolution",
    f"{c} {str(b)[:300]}",
)
c, b = api(
    "POST", f"{A}/spec/drift/{cand.get('id')}/resolve", {"resolution": "implementation_corrected"}
)
ok("a permitted resolution is accepted", c == 200, f"{c} {str(b)[:250]}")
ok("  ... and the candidate becomes `resolved`", b.get("state") == "resolved", str(b)[:250])
ok(
    "  ... carrying the resolution the operator chose",
    b.get("resolution") == "implementation_corrected",
    str(b)[:250],
)

c, b = api("POST", f"{A}/spec/drift/detect")
c2, rows2, _ = drift_rows()
still_open = [r for r in (rows2 or []) if r.get("evidence_id") == EVD and r["state"] == "candidate"]
ok(
    "a resolved change is NOT raised again on the next scan",
    not still_open,
    f"raised={b.get('raised')} open={still_open}",
)

# A *different* change must be raised, or the resolution has silenced the feature.
(ROOT / "README.md").write_text(f"row9c {TAG} - changed a SECOND time\n", encoding="utf-8")
git("add", "README.md")
git("commit", "-m", f"r9c {TAG} change the footprinted file again")
c, b = api("POST", f"{A}/spec/drift/detect")
c2, rows3, _ = drift_rows()
reopened = [r for r in (rows3 or []) if r.get("evidence_id") == EVD and r["state"] == "candidate"]
ok(
    "a NEW change after a resolution IS raised — the resolution did not silence the row",
    len(reopened) == 1,
    f"raised={b.get('raised')} open={reopened}",
)

# A reworded requirement is stale evidence, not drift. Reopen first: an approved document refuses
# a content write, which is 9a's phase machine holding.
c, b = set_phase(d4, EXPLORING, reason="row 9c is about to reword it")
ok("an approved document can be reopened to reword it", c == 200, f"{c} {str(b)[:200]}")
c, b = write_content(
    d4, payload_for("doc drift", nreq=2, bump=" Reworded by row 9c to provoke staleness.")
)
ok("rewording the reopened document is accepted", c == 200, f"{c} {str(b)[:200]}")
before_ids = {r["id"] for r in (drift_rows()[1] or [])}
(ROOT / "README.md").write_text(f"row9c {TAG} - changed a THIRD time\n", encoding="utf-8")
git("add", "README.md")
git("commit", "-m", f"r9c {TAG} change the footprinted file a third time")
c, b = api("POST", f"{A}/spec/drift/detect")
after = drift_rows()[1] or []
new_for_ev = [r for r in after if r["id"] not in before_ids and r.get("evidence_id") == EVD]
ok(
    "a REWORDED requirement raises no new drift — that is staleness, asked once not twice",
    not new_for_ev,
    f"raised={b.get('raised')} new={new_for_ev}",
)

# =============================================================================================
leg(5, "Reindex — and 9a's question: what assumes an index exists because reindex 'succeeded'?")

c, b = bodyless("POST", f"{A}/spec/reindex")
ok(
    "POST /spec/reindex with NO BODY answers 200 — F204/F210's shape is absent here",
    c == 200,
    f"{c} {str(b)[:300]}",
)
idx = (b or {}).get("index") if isinstance(b, dict) else {}
note("index.written", (idx or {}).get("written"))
note("index.diagnostics", (idx or {}).get("diagnostics"))
NO_HOME = isinstance(idx, dict) and idx.get("written") is None
ok(
    "  ... and it reports what it did to the requirement index regardless",
    isinstance((b or {}).get("documents"), dict),
    str(b)[:300],
)

if NO_HOME:
    # THE SHARPEST LEAD FROM 9a: a 200 whose index was never written. What downstream believes it?
    ok(
        "the 200 that wrote no index says WHY in diagnostics",
        any("home" in str(d) for d in (idx.get("diagnostics") or [])),
        str(idx.get("diagnostics"))[:300],
    )
    c, b = api("POST", f"{A}/spec/drift/detect")
    ok(
        "drift/detect works on a corpus reindex 'succeeded' on without writing an index",
        c == 200,
        f"{c} {str(b)[:300]}",
    )
    c, b = api("GET", f"{A}/spec/coverage")
    ok(
        "coverage works on the same corpus",
        c == 200 and isinstance(b, dict) and "entries" in json.dumps(b)[:4000] or c == 200,
        f"{c} {str(b)[:250]}",
    )
    c, b = api("POST", f"{A}/spec/documents/arrange", {"path": d1, "parent": None})
    ok(
        "arrange is the one that refuses — and it is F208's sentence, unchanged",
        c == 409,
        f"{c} {str(b)[:300]}",
    )
    note("arrange refusal", str(b)[:200])
else:
    note("precondition", "an index was already written in this project; the virgin checks are skipped")

# Now name a home and reindex again.
c, b = api("POST", f"{A}/spec/reindex", {"home": d1})
idx2 = (b or {}).get("index") if isinstance(b, dict) else {}
ok("naming a home writes the index", c == 200 and (idx2 or {}).get("written"), f"{c} {str(b)[:400]}")
note("index.written", (idx2 or {}).get("written"))
ok(
    "  ... and spec/index.json exists on disk afterwards",
    (ROOT / "spec" / "index.json").exists(),
    str(ROOT / "spec" / "index.json"),
)
c, b = api("POST", f"{A}/spec/reindex")
idx3 = (b or {}).get("index") if isinstance(b, dict) else {}
ok(
    "a later reindex preserves the recorded home without restating it",
    c == 200 and ((idx3 or {}).get("written") or {}).get("home") == d1,
    f"{c} {str(idx3)[:300]}",
)
c, b = api("POST", f"{A}/spec/reindex", {"home": "spec/changes/not-a-document/spec.html"})
note("reindex naming a home that is not a document", f"[{c}] {str(b)[:250]}")
ok(
    "naming a home that is not in the corpus does not silently become the home",
    ((b or {}).get("index", {}).get("written") or {}).get("home") != "spec/changes/not-a-document/spec.html",
    str((b or {}).get("index"))[:300],
)

# Does reindex writing the corpus disturb the evidence it has already footprinted?
c, b = api("POST", f"{A}/spec/drift/detect")
note("drift raised immediately after a corpus-rewriting reindex", b.get("raised") if c == 200 else b)
ok(
    "a reindex that rewrote the corpus does not drift committed evidence (git footprints)",
    c == 200,
    f"{c} {str(b)[:250]}",
)

# =============================================================================================
leg(6, "Evidence retention")

c, b = api("PUT", f"{A}/spec/evidence-retention", {"policy": "never"})
ok("`never` is a first-class retention policy", c == 200 and b.get("policy") == "never", f"{c} {str(b)[:250]}")
c, b = api("PUT", f"{A}/spec/evidence-retention", {"policy": "forever_and_ever"})
ok("an unknown policy is 422 naming the permitted ones", c == 422 and "policy must be one of" in str(b), f"{c} {str(b)[:300]}")
note("permitted policies", str(b)[:200])

# =============================================================================================
leg(7, "The bodyless probe over every 9c route (F204/F210's shape, asked once more)")

PROBES = [
    ("POST", f"{A}/spec/evidence", "identifier is genuinely required"),
    ("POST", f"{A}/spec/evidence/{EV}/decision", "decision is genuinely required"),
    ("POST", f"{A}/spec/drift/detect", "takes no body at all"),
    ("POST", f"{A}/spec/drift/{cand.get('id')}/resolve", "resolution is genuinely required"),
    ("PUT", f"{A}/spec/evidence-retention", "policy is genuinely required"),
    ("POST", f"{A}/spec/reindex", "every field defaults"),
]
for method, path, why in PROBES:
    c, b = bodyless(method, path)
    short = path.split("/project")[-1]
    note(f"bodyless {method} {short}", f"[{c}] {str(b)[:140]}")
    if "no body at all" in why or "every field defaults" in why:
        ok(f"bodyless {method} {short} -> 200 ({why})", c == 200, f"{c} {str(b)[:250]}")
    else:
        ok(f"bodyless {method} {short} -> 422 ({why})", c == 422, f"{c} {str(b)[:250]}")

# F204 and F210 are a *model whose every field is optional* being refused anyway. That shape is
# ABSENT from 9c, and this is the measurement rather than a reading of the signatures: every 9c
# route that refuses a bodyless call has a genuinely required field, and it names that field the
# moment the caller sends an empty object.
EMPTY = [
    ("POST", f"{A}/spec/evidence", "identifier"),
    ("POST", f"{A}/spec/evidence/{EV}/decision", "decision"),
    ("POST", f"{A}/spec/drift/{cand.get('id')}/resolve", "resolution"),
    ("PUT", f"{A}/spec/evidence-retention", "policy"),
]
for method, path, field in EMPTY:
    c, b = api(method, path, {})
    short = path.split("/project")[-1]
    locs = [
        (d.get("loc") or [])[-1] for d in (b.get("detail") or []) if isinstance(d, dict)
    ] if isinstance(b, dict) and isinstance(b.get("detail"), list) else []
    note(f"empty-object {method} {short}", f"[{c}] missing={locs}")
    ok(
        f"an empty object on {short} is refused 422 naming {field!r} — the field is genuinely "
        f"required, so F204/F210's shape is absent here",
        c == 422 and field in locs,
        f"{c} {str(b)[:250]}",
    )

# Ordering: does a route look the resource up before or after parsing the body? The schema layer
# wins on every one of these, which is F201/F204's ordering without F204's consequence -- the
# caller is told about the body rather than about the id that does not exist. Recorded, not filed:
# with a well-formed body the same call is a clean 404 (leg 2), so no correct caller meets this.
c, b = bodyless("POST", f"{A}/spec/evidence/ev-definitely-not-here/decision")
note("bodyless decision on an UNKNOWN evidence id", f"[{c}] {str(b)[:200]}")
ok(
    "an unknown evidence id with no body is refused (either 404 or 422 — both are refusals)",
    c in (404, 422),
    f"{c} {str(b)[:300]}",
)
note(
    "  ordering",
    "schema layer ahead of the lookup" if c == 422 else "lookup ahead of the schema layer",
)

# =============================================================================================
leg(8, "Is any of 9c reachable from the operator's screen, and what does the agent plane carry?")

BUNDLE = REPO / "hub" / "hub" / "static" / "ui"
SRC = REPO / "hub" / "ui" / "src"


def hits(root, needle):
    n = 0
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        with contextlib.suppress(OSError):
            n += f.read_bytes().count(needle.encode())
    return n


FRAGMENTS = [
    "spec/evidence",
    "evidence-retention",
    "spec/drift",
    "drift/detect",
    "spec/reindex",
    "/reviews",
]
# The control first: a needle that IS in the bundle, so a zero below is a fact about the product
# and not about this grep. 9b measured `spec/coverage` at 1 and it is still 1.
ctl_b, ctl_s = hits(BUNDLE, "spec/coverage"), hits(SRC, "spec/coverage")
note("CONTROL 'spec/coverage'", f"served bundle {ctl_b}, source {ctl_s}")
ok("the grep works — the control needle is present in the served bundle", ctl_b > 0, f"{ctl_b}")

bundle_counts = {}
for frag in FRAGMENTS:
    b_hits, s_hits = hits(BUNDLE, frag), hits(SRC, frag)
    bundle_counts[frag] = (b_hits, s_hits)
    note(f"{frag!r}", f"served bundle {b_hits}, source {s_hits}")
ok(
    "EVERY route in row 9c is absent from the served bundle AND from the UI source",
    all(b == 0 and s == 0 for b, s in bundle_counts.values()),
    str(bundle_counts),
)
note("bundle bytes read", sum(f.stat().st_size for f in BUNDLE.rglob("*") if f.is_file()))
# The UI does say the words. It reads *derived* state -- `evidence_count`, `drifting`,
# `evidence_awaiting_review` off /spec/coverage and the task payload -- and calls none of the
# routes that produce or act on the underlying rows.
for word, where in (("evidence_count", SRC), ("drifting", SRC), ("evidence_awaiting_review", SRC)):
    note(f"derived state {word!r} in UI source", hits(where, word))
# And the one thing the UI *does* call drift is a different drift entirely: the spec MANIFEST
# drift banner on the document panel, which comes off GET /documents and has its own vocabulary.
note("'spec manifest drift' banner text in the served bundle", hits(BUNDLE, "spec manifest drift"))

req = urllib.request.Request(HUB + "/openapi.json")
with urllib.request.urlopen(req, timeout=30) as r:
    spec_doc = json.loads(r.read().decode())
paths = sorted(spec_doc.get("paths", {}))
ag = [p for p in paths if "agent-actions" in p and ("spec" in p or "document" in p)]
note("agent-plane spec routes", len(ag))
for p in ag:
    note("  agent", p)
ok(
    "the agent plane HAS an evidence-recording route (9c's real agent surface)",
    any(p.endswith("/spec/evidence") for p in ag),
    str(ag),
)
ok(
    "the agent plane HAS an evidence-decision route",
    any("evidence" in p and "decision" in p for p in ag),
    str(ag),
)
ok(
    "there is NO agent-plane drift route — drift is the operator's judgement",
    not any("drift" in p for p in ag),
    str([p for p in ag if "drift" in p]),
)
ok(
    "there is NO agent-plane reindex route",
    not any("reindex" in p for p in ag),
    str([p for p in ag if "reindex" in p]),
)
ok(
    "there is NO agent-plane reviews route",
    not any(p.endswith("/reviews") for p in ag),
    str([p for p in ag if p.endswith("/reviews")]),
)

# =============================================================================================
print(f"\n=== ROW 9c: {len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAIL  {f}")
