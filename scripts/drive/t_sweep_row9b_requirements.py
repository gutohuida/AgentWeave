"""SWEEP ROW 9b of 19 — SPEC FLOW, the requirements half: requirements / coverage / rigor / proposals.

Row 9 does not fit one sitting and is split in three. 9a (documents, phase, adopt/arrange/merge)
was driven in iteration 11. This is **9b**. Evidence, decisions, reviews, drift and reindex are 9c.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... py -3.11 t_sweep_row9b_requirements.py

Method carried from rows 7, 8 and 9a:

* **The fixture machinery is copied from 9a, not imported from the product.** `payload_for`,
  `set_phase` and `make_document` below are 9a's, so this file asserts against the Hub rather than
  against a helper the Hub also uses.
* **Create the condition under test.** Every rigor, every retirement and every proposal below is
  walked into existence through the real routes.
* **Measure outside the product where you can.** Leg 6 reads the *served* UI bundle as bytes and
  leg 7 reads the *live* OpenAPI — what this build actually serves, not what the source says.
* **Boundary, not signature.** Leg 1 asks `GET /spec/requirements` for 120 requirements rather than
  reading its parameters, because reading the signature is not what found F202.
* **Call the route, do not read its model.** Every bodyless probe below is a call.
"""

import contextlib
import json
import os
import pathlib
import re
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
    """A call with NO body at all — not `{}`, nothing. F204 was found exactly this way."""
    req = urllib.request.Request(HUB + "/api/v1" + path, method=method)
    req.add_header("Authorization", "Bearer " + KEY)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
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
SKETCH, CONTRACT, GATE = "sketch", "contract", "gate"

_n = [0]


def newpath(stem):
    _n[0] += 1
    return f"spec/changes/r9b-{TAG}-{stem}-{_n[0]:03d}/spec.html"


def payload_for(title, *, kind="change-spec", reviewer="critic", nreq=2, bump=""):
    """9a's factory, complete enough that `spec_completeness.check` returns nothing.

    `bump` perturbs every requirement statement, which is how a proposal is provoked at
    `contract`/`gate` rigor without changing the set of keys.
    """
    reqs = [
        {
            "key": f"fr-{i}",
            "statement": f"The subject MUST satisfy condition {i} exactly as stated here.{bump}",
            "modal": "MUST",
            "rationale": f"Condition {i} is silent when violated, so it needs stating.",
        }
        for i in range(1, nreq + 1)
    ]
    return {
        "schema_version": 1,
        "kind": kind,
        "title": title,
        "summary": (
            "A driven fixture document written by row 9b of the coverage sweep, complete enough "
            "that the completeness check has nothing to report about it."
        ),
        "problem": (
            "Requirements, coverage, rigor and proposals cannot be driven without a document that "
            "actually declares requirements and can be promoted."
        ),
        "scope": {
            "in_scope": ["Requirements and coverage", "Rigor and proposals"],
            "non_goals": ["Evidence review", "Drift and reindex"],
        },
        "requirements": reqs,
        "acceptance_criteria": [
            {
                "key": f"ac-{i}",
                "requirement": f"fr-{i}",
                "given": "a fixture project on the trial Hub",
                "when": f"condition {i} is exercised",
                "then": f"the observed behaviour matches requirement fr-{i}",
            }
            for i in range(1, nreq + 1)
        ],
        "tasks": [
            {
                "key": f"t-{i}",
                "title": f"Satisfy condition {i}",
                "description": (
                    f"Implement and test whatever condition {i} requires, covering ac-{i} with a "
                    "named test that fails when the behaviour is removed."
                ),
                "requirements": [f"fr-{i}"],
                "reviewer": reviewer,
            }
            for i in range(1, nreq + 1)
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


def doc_row(path):
    c, b = api("GET", f"{A}/documents")
    if c != 200:
        return None
    for d in (b.get("documents") if isinstance(b, dict) else b) or []:
        if d.get("path") == path:
            return d
    return None


def make_document(stem, target_phase, *, nreq=2, empty=False):
    path = newpath(stem)
    c, _ = api("POST", f"{A}/documents", {"path": path, "title": f"doc {stem}"})
    assert c == 201, f"create {c}"
    if not empty:
        c, b = write_content(path, payload_for(f"doc {stem}", nreq=nreq))
        assert c in (200, 201), f"content {c} {str(b)[:200]}"
    if target_phase == EXPLORING:
        return path
    c, _ = api("POST", f"{A}/documents/close-exploration?path={path}")
    assert c == 200, f"close {c}"
    c, b = api("POST", f"{A}/documents/propose?path={path}")
    assert c == 200 and not b.get("blocking"), f"propose {c} {str(b)[:300]}"
    if target_phase == PROPOSED:
        return path
    c, _ = set_phase(path, APPROVED)
    assert c == 200, f"approve {c}"
    return path


def code_of(body):
    d = body.get("detail") if isinstance(body, dict) else None
    return d.get("code") if isinstance(d, dict) else None


def message_of(body):
    d = body.get("detail") if isinstance(body, dict) else None
    if isinstance(d, dict):
        return d.get("message", "")
    return str(d)


def requirements(**q):
    query = "&".join(f"{k}={v}" for k, v in q.items())
    c, b = api("GET", f"{A}/spec/requirements" + (f"?{query}" if query else ""))
    return c, (b.get("requirements") if isinstance(b, dict) else None), b


# =============================================================================================
leg(1, "Requirements — minting, listing, filtering, retirement, and the boundary")

d1 = make_document("index", EXPLORING, nreq=3)
row1 = doc_row(d1)
note("d1", d1)
c, b = write_content(d1, payload_for("doc index", nreq=3))
minted = b.get("identifiers") if c == 200 else {}
ok(
    "a content write reports the identifiers it minted",
    isinstance(minted, dict) and len(minted) == 3,
    f"{c} {str(b)[:200]}",
)
note("identifiers", minted)

c, rows, raw = requirements(document=d1)
ok("GET /spec/requirements?document= answers 200", c == 200, f"{c} {str(raw)[:200]}")
ok(
    "  ... and returns exactly the document's three requirements",
    rows is not None and len(rows) == 3,
    str(rows)[:200],
)
by_key = {r["key"]: r for r in (rows or [])}
ok(
    "  ... keyed by the payload's own keys",
    set(by_key) == {"fr-1", "fr-2", "fr-3"},
    str(sorted(by_key))[:200],
)
ok(
    "  ... each carries the identifier the write reported",
    all(by_key[k]["identifier"] == minted.get(k) for k in by_key) if by_key and minted else False,
    f"{by_key} vs {minted}",
)
ok("  ... each is `active`", all(r["state"] == "active" for r in (rows or [])), str(rows)[:200])
ok("  ... each carries a digest", all(bool(r["digest"]) for r in (rows or [])), str(rows)[:200])
ok(
    "  ... each carries an anchor into the document",
    all(bool(r["anchor"]) for r in (rows or [])),
    str([r["anchor"] for r in (rows or [])])[:200],
)
ok(
    "  ... each names its own document",
    all(r["document_id"] == (row1 or {}).get("id") for r in (rows or [])),
    f"{[r['document_id'] for r in (rows or [])]} vs {(row1 or {}).get('id')}",
)
ok(
    "  ... ordered by identifier",
    [r["identifier"] for r in (rows or [])] == sorted(r["identifier"] for r in (rows or [])),
    str(rows)[:200],
)

d2 = make_document("second", EXPLORING, nreq=2)
c, rows2, _ = requirements(document=d2)
ok(
    "a second document's requirements are its own",
    rows2 is not None and len(rows2) == 2,
    str(rows2)[:200],
)
# Identifiers are minted PER DOCUMENT (hub/hub/spec_index.py:349 says so), so this overlap is the
# design, not a defect. Recorded as an observation because everything in leg 2 follows from it.
overlap = {r["identifier"] for r in (rows2 or [])} & {r["identifier"] for r in (rows or [])}
note("identifiers a second document shares with the first", sorted(overlap))
ok(
    "identifiers are per-document, so two documents share them",
    bool(overlap),
    "no overlap -- the minting may have changed",
)

c, all_rows, _ = requirements()
ok(
    "the unfiltered list is project-wide",
    all_rows is not None and len(all_rows) >= 5,
    str(len(all_rows or []))[:40],
)

c, b = api("GET", f"{A}/spec/requirements?document=spec/changes/nope-{TAG}/spec.html")
ok("an unknown document is refused 404, not silently ignored", c == 404, f"{c} {str(b)[:200]}")

# Retire one: rewrite d1's payload with fr-3 dropped.
retired_identifier = by_key.get("fr-3", {}).get("identifier")
c, b = write_content(d1, payload_for("doc index", nreq=2))
ok("dropping a requirement from the payload is accepted", c == 200, f"{c} {str(b)[:200]}")
c, rows, _ = requirements(document=d1)
states = {r["identifier"]: r["state"] for r in (rows or [])}
ok(
    "  ... and the dropped requirement is retired, not deleted",
    states.get(retired_identifier) == "retired",
    str(states)[:200],
)
c, rows, _ = requirements(document=d1, include_retired="false")
ok(
    "include_retired=false hides it",
    retired_identifier not in {r["identifier"] for r in (rows or [])},
    str(rows)[:200],
)
ok("  ... and keeps the other two", len(rows or []) == 2, str(rows)[:200])
c, rows, _ = requirements(document=d1, include_retired="true")
ok(
    "include_retired=true shows it again",
    retired_identifier in {r["identifier"] for r in (rows or [])},
)
c, rows, _ = requirements(document=d1)
ok(
    "the default is include_retired=true",
    retired_identifier in {r["identifier"] for r in (rows or [])},
    str(rows)[:200],
)

# The boundary question F202 taught. 120 requirements in one document.
big = make_document("boundary", EXPLORING, nreq=1)
c, b = write_content(big, payload_for("boundary", nreq=120))
ok("a 120-requirement document writes", c == 200, f"{c} {str(b)[:300]}")
c, rows, _ = requirements(document=big)
ok(
    "GET /spec/requirements returns all 120 — no undeclared cap",
    len(rows or []) == 120,
    f"returned {len(rows or [])}",
)
c, all_rows, _ = requirements()
note("project-wide requirement count", len(all_rows or []))
ok(
    "  ... and the project-wide list is not capped either",
    len(all_rows or []) >= 125,
    str(len(all_rows or [])),
)

# =============================================================================================
leg(2, "Requirement detail — identifiers are per-DOCUMENT, and what that costs the reader")

# THE PRECONDITION, stated rather than asserted through. Run 1 of this harness assumed identifiers
# were project-unique and produced seven reds that were facts about the harness, not the product:
# `spec_index.resolve` (hub/hub/spec_index.py:349) says identifiers are minted per document, so
# every document in this fixture declares `FR-1`. A project-unique identifier therefore only exists
# above the requirement count of every other document — leg 1's 120-requirement document supplies
# one.
c, all_rows, _ = requirements()
# MEASURED, not assumed. Run 2 of this harness inherits run 1's documents, so "the 119th
# requirement of the biggest document" stops being unique the moment the harness runs twice --
# which is exactly how run 2 produced seven reds that were facts about run 1. Identifiers are
# minted `FR-<n>` by position, so uniqueness is bought by out-sizing every document already there.
from collections import Counter  # noqa: E402 - local to the measurement it serves

seen_counts = Counter(r["identifier"] for r in (all_rows or []))
highest = max(
    (
        int(m.group(1))
        for m in (re.match(r"FR-(\d+)$", r["identifier"]) for r in (all_rows or []))
        if m
    ),
    default=0,
)
uniqdoc = make_document("unique", EXPLORING, nreq=1)
c, b = write_content(uniqdoc, payload_for("unique", nreq=highest + 4))
ok("a document out-sizing every other in the project writes", c == 200, f"{c} {str(b)[:250]}")
c, big_rows, _ = requirements(document=uniqdoc)
c, all_rows, _ = requirements()
seen_counts = Counter(r["identifier"] for r in (all_rows or []))
uniques = [r["identifier"] for r in (big_rows or []) if seen_counts[r["identifier"]] == 1]
unique = uniques[0] if uniques else None
other_unique = uniques[1] if len(uniques) > 1 else None
unique_key = next((r["key"] for r in (big_rows or []) if r["identifier"] == unique), None)
ok(
    "a project-unique identifier exists to test with",
    bool(unique) and bool(other_unique),
    f"{len(uniques)} unique identifiers in the out-sized document",
)
note("project-unique identifier", f"{unique} (key {unique_key})")

c, b = api("GET", f"{A}/spec/requirements/{unique}")
ok(
    "GET /spec/requirements/{identifier} answers 200 for an unambiguous one",
    c == 200,
    f"{c} {str(b)[:200]}",
)
det = b.get("requirement") if c == 200 else {}
ok(
    "  ... and the requirement block matches the list entry",
    det.get("identifier") == unique and det.get("key") == unique_key,
    str(det)[:200],
)
ok(
    "  ... reports `tasks`, `evidence` and `coverage` keys",
    all(k in (b or {}) for k in ("tasks", "evidence", "coverage")),
    str(list(b or {}))[:200],
)
cov = (b or {}).get("coverage")
ok(
    "  ... coverage is present rather than null for an indexed requirement",
    cov is not None,
    str(b)[:300],
)
ok(
    "  ... and coverage never states a state without an integration answer",
    isinstance(cov, dict) and "state" in cov and "integration" in cov,
    str(cov)[:200],
)
note("coverage of a fresh requirement", cov)
ok(
    "  ... with no work linked, the fresh requirement is `unserved`",
    (cov or {}).get("state") == "unserved",
    str(cov)[:200],
)
ok(
    "  ... and its tasks list is empty",
    (b or {}).get("tasks") == [],
    str((b or {}).get("tasks"))[:200],
)

c, b = api("GET", f"{A}/spec/requirements/AW-R-NOPE-{TAG}")
ok("an unknown identifier is 404", c == 404, f"{c} {str(b)[:200]}")
ok("  ... and says the project has no such requirement", "no requirement" in str(b), str(b)[:200])

# The ambiguity is DESIGNED — resolve() refuses rather than choosing, which is right. What this
# measures is how much of the surface that leaves usable.
target = by_key["fr-1"]["identifier"]
c, b = api("GET", f"{A}/spec/requirements/{target}")
ok(
    "a bare identifier declared by two documents is refused 422, not guessed",
    c == 422,
    f"{c} {str(b)[:200]}",
)
ok("  ... and says to name the document", "name the document" in str(b), str(b)[:200])
dup = [r for r in (all_rows or []) if r["identifier"] == target]
note(f"documents declaring {target}", len(dup))
ok(
    "EVERY document in this project declares FR-1 — so the bare-identifier route is unusable here",
    len(dup) >= 5,
    str(len(dup)),
)

c, b = api("GET", f"{A}/spec/requirements/{target}?document={d1}")
ok(
    "naming the document disambiguates it",
    c == 200 and (b.get("requirement") or {}).get("identifier") == target,
    f"{c} {str(b)[:200]}",
)
ok(
    "  ... and returns THAT document's requirement",
    (
        (b.get("requirement") or {}).get("document_id") == (row1 or {}).get("id")
        if c == 200
        else False
    ),
    str(b)[:250],
)
c, b2 = api("GET", f"{A}/spec/requirements/{target}?document={d2}")
ok(
    "naming a DIFFERENT document returns a DIFFERENT requirement of the same name",
    c == 200 and (b2.get("requirement") or {}).get("id") != (b.get("requirement") or {}).get("id"),
    f"{c} {str(b2)[:200]}",
)

c, b = api("GET", f"{A}/spec/requirements/{retired_identifier}?document={d1}")
ok("a RETIRED requirement is still reachable by identifier", c == 200, f"{c} {str(b)[:200]}")
note("retired requirement coverage", (b or {}).get("coverage"))
ok(
    "  ... and reports its retired state",
    ((b or {}).get("requirement") or {}).get("state") == "retired",
    str(b)[:200],
)
retired_cov = (b or {}).get("coverage") or {}
ok(
    "  ... but is NOT given the `unserved` coverage state",
    retired_cov.get("state") != "unserved",
    "the detail route reports a retired requirement as `unserved`, while "
    "requirement_links.unserved() excludes retired rows precisely because "
    "'a requirement nobody has to build any more is not unserved, it is over'",
)

# Link a task by naming the UNIQUE identifier, and watch the navigation close.
c, task = api(
    "POST",
    f"/projects/{P}/tasks",
    {
        "title": f"row9b link {TAG}",
        "description": "links a requirement by identifier",
        "requirements": [unique],
    },
)
ok("a task naming an unambiguous identifier is created", c in (200, 201), f"{c} {str(task)[:200]}")
tid = task.get("id") if c in (200, 201) else None
c, b = api("GET", f"{A}/spec/requirements/{unique}")
tasks_seen = [t["id"] for t in ((b or {}).get("tasks") or [])]
ok(
    "  ... and the requirement now names the task that serves it",
    tid in tasks_seen,
    f"{tasks_seen} vs {tid}",
)
cov = (b or {}).get("coverage")
ok(
    "  ... and it is no longer `unserved`",
    isinstance(cov, dict) and cov.get("state") != "unserved",
    str(cov)[:200],
)
note("coverage once a task links it", cov)

# And the contrast: a task naming an AMBIGUOUS identifier. The link cannot be made — does the
# operator find that out, or does the task just quietly serve nothing?
c, task2 = api(
    "POST",
    f"/projects/{P}/tasks",
    {
        "title": f"row9b ambiguous {TAG}",
        "description": "names FR-1, which five documents declare",
        "requirements": [target],
    },
)
ok(
    "a task naming an AMBIGUOUS identifier is still created",
    c in (200, 201),
    f"{c} {str(task2)[:200]}",
)
note(
    "what the create response says about the reference",
    {k: v for k, v in (task2 or {}).items() if "requirement" in k or "unresolved" in k},
)
ok(
    "  ... and the response says somewhere that the reference did not resolve",
    "unresolved" in str(task2).lower() or "ambiguous" in str(task2).lower(),
    str(task2)[:400],
)

# =============================================================================================
leg(3, "Coverage — the project total and one document's, from one implementation")

c, b = api("GET", f"{A}/spec/coverage")
ok("GET /spec/coverage answers 200 project-wide", c == 200, f"{c} {str(b)[:200]}")
proj_cov = b if c == 200 else {}
ok(
    "  ... reports `requirements`, `totals`, `integration` and `unserved`",
    all(k in proj_cov for k in ("requirements", "totals", "integration", "unserved")),
    str(list(proj_cov))[:200],
)
entries = proj_cov.get("requirements") or []
note("project coverage totals", proj_cov.get("totals"))
note("project integration totals", proj_cov.get("integration"))
ok(
    "  ... every entry carries BOTH a state and an integration answer",
    all("state" in e and "integration" in e for e in entries),
    str(entries[:2])[:300],
)
ok(
    "  ... the state totals sum to the number of entries",
    sum((proj_cov.get("totals") or {}).values()) == len(entries),
    f"{proj_cov.get('totals')} vs {len(entries)}",
)
ok(
    "  ... the integration totals sum to the same number",
    sum((proj_cov.get("integration") or {}).values()) == len(entries),
    f"{proj_cov.get('integration')} vs {len(entries)}",
)
ok(
    "  ... `unserved` is a list of identifiers",
    isinstance(proj_cov.get("unserved"), list)
    and all(isinstance(x, str) for x in proj_cov["unserved"]),
)
unserved_list = proj_cov.get("unserved") or []
ok(
    "  ... the linked requirement is NOT in unserved",
    unique not in unserved_list,
    str(unserved_list)[:200],
)
ok("  ... an unlinked one IS", other_unique in unserved_list, f"{other_unique} not in unserved")

# `unserved` is a list of bare identifiers, and identifiers are per-DOCUMENT. So in any project
# with more than one document the list carries duplicates that name different requirements, with
# nothing to tell them apart -- while the sibling `requirements` entries in the SAME response each
# carry a `document_id`.
counts = Counter(unserved_list)
worst, worst_n = counts.most_common(1)[0] if counts else (None, 0)
note("most-repeated identifier in `unserved`", f"{worst} x {worst_n}")
ok(
    "`unserved` carries no document, so a repeated identifier is unresolvable",
    worst_n == 1,
    f"{worst} appears {worst_n} times with nothing to tell the copies apart",
)
ok(
    "  ... while the sibling `requirements` entries in the same response DO carry document_id",
    all("document_id" in e for e in entries),
)
if worst_n > 1:
    c2, b2 = api("GET", f"{A}/spec/requirements/{worst}")
    note(
        "feeding the most-repeated unserved identifier back to the detail route",
        f"{c2} {str(b2)[:160]}",
    )
    ok(
        "  ... and an identifier taken FROM unserved can be looked up",
        c2 == 200,
        f"{c2} {str(b2)[:200]}",
    )

retired_in_unserved = counts.get(retired_identifier, 0)
active_same_name = len(
    [
        r
        for r in (all_rows or [])
        if r["identifier"] == retired_identifier and r["state"] == "active"
    ]
)
ok(
    "  ... retired requirements are excluded from unserved (measured against the ACTIVE twins of the same name)",
    retired_in_unserved == active_same_name,
    f"{retired_identifier}: {retired_in_unserved} in unserved, {active_same_name} active rows share the name",
)

c, b = api("GET", f"{A}/spec/coverage?document={d1}")
ok("GET /spec/coverage?document= answers 200", c == 200, f"{c} {str(b)[:200]}")
doc_entries = (b or {}).get("requirements") or []
ok(
    "  ... and is scoped to that document",
    0 < len(doc_entries) < len(entries),
    f"{len(doc_entries)} of {len(entries)}",
)
ok(
    "  ... reporting the same state for a shared requirement as the project view does",
    next((e["state"] for e in doc_entries if e.get("identifier") == target), None)
    == next((e["state"] for e in entries if e.get("identifier") == target), None),
)

c, b = api("GET", f"{A}/spec/coverage?document=spec/changes/nope-{TAG}/spec.html")
ok("coverage of an unknown document is 404", c == 404, f"{c} {str(b)[:200]}")

# =============================================================================================
leg(4, "Rigor — the operator's alone, compare-and-swap, and what promotion refuses")

rd = make_document("rigor", EXPLORING, nreq=2)
before = doc_row(rd)
ok("a fresh document is `sketch`", (before or {}).get("rigor") == SKETCH, str(before)[:200])

# Not F204's shape: `RigorRequest.rigor` is genuinely required, so refusing a bodyless call for a
# missing body is the right answer. What is worth checking is the NEXT step in -- an empty object,
# where FastAPI can name the field that is missing.
c, b = bodyless("POST", f"{A}/documents/{rd}/rigor")
note("bodyless rigor", f"{c} {str(b)[:200]}")
ok(
    "a bodyless rigor call is refused (its model has a required field)",
    c == 422,
    f"{c} {str(b)[:200]}",
)
c, b = api("POST", f"{A}/documents/{rd}/rigor", {})
ok(
    "an EMPTY-object rigor call names the field it wants, not `body`",
    c == 422 and "rigor" in str(b),
    f"{c} {str(b)[:250]}",
)

c, b = api("POST", f"{A}/documents/{rd}/rigor", {"rigor": "strict"})
ok("an unknown rigor is refused 409", c == 409, f"{c} {str(b)[:200]}")
ok("  ... naming unknown_rigor", code_of(b) == "unknown_rigor", str(b)[:200])
ok(
    "  ... and listing the rigors that exist",
    all(r in message_of(b) for r in (SKETCH, CONTRACT, GATE)),
    message_of(b)[:200],
)

c, b = api("POST", f"{A}/documents/{rd}/rigor", {"rigor": SKETCH})
ok("setting the rigor it already has is refused 409", c == 409, f"{c} {str(b)[:200]}")
ok("  ... naming rigor_unchanged", code_of(b) == "rigor_unchanged", str(b)[:200])

empty = newpath("emptyrigor")
api("POST", f"{A}/documents", {"path": empty, "title": "no payload"})
c, b = api("POST", f"{A}/documents/{empty}/rigor", {"rigor": CONTRACT})
ok("promoting a document with no payload is refused 409", c == 409, f"{c} {str(b)[:250]}")
ok("  ... naming document_not_enforceable", code_of(b) == "document_not_enforceable", str(b)[:200])
blocking = (
    (b.get("detail") or {}).get("blocking")
    if isinstance(b, dict) and isinstance(b.get("detail"), dict)
    else None
)
ok(
    "  ... and listing what blocks it, in words the operator can act on",
    isinstance(blocking, list) and len(blocking) >= 1,
    str(blocking)[:250],
)
note("promotion blockers", blocking)

c, b = api("POST", f"{A}/documents/{empty}/rigor", {"rigor": SKETCH})
ok(
    "but DEMOTING the same unreadable document is not refused for enforceability",
    code_of(b) != "document_not_enforceable",
    f"{c} {str(b)[:200]}",
)

digest_before = (doc_row(rd) or {}).get("content_digest")
ok(
    "the document view exposes the digest a CAS caller needs",
    bool(digest_before),
    str(doc_row(rd))[:200],
)

c, b = api(
    "POST",
    f"{A}/documents/{rd}/rigor",
    {"rigor": CONTRACT, "expected_digest": "0" * 64, "reason": "wrong digest"},
)
ok("a rigor change on a STALE digest is refused 409", c == 409, f"{c} {str(b)[:200]}")
ok("  ... naming stale_digest", code_of(b) == "stale_digest", str(b)[:200])
ok(
    "  ... and the rigor did not move",
    (doc_row(rd) or {}).get("rigor") == SKETCH,
    str(doc_row(rd))[:200],
)

c, b = api(
    "POST",
    f"{A}/documents/{rd}/rigor",
    {"rigor": CONTRACT, "expected_digest": digest_before, "reason": "promote for the sweep"},
)
ok("a rigor change on the CURRENT digest lands", c == 200, f"{c} {str(b)[:250]}")
ok(
    "  ... and the document reports the new rigor",
    (b or {}).get("rigor") == CONTRACT if c == 200 else False,
    str(b)[:200],
)
ok("  ... which the list route agrees with", (doc_row(rd) or {}).get("rigor") == CONTRACT)

# The F207-shaped question: is omitting the digest a second door past the compare-and-swap?
race = make_document("race", EXPLORING, nreq=2)
stale = (doc_row(race) or {}).get("content_digest")
write_content(race, payload_for("doc race", nreq=2, bump=" Edited underneath the reader."))
fresh = (doc_row(race) or {}).get("content_digest")
ok(
    "an edit underneath a reader changes the digest",
    stale and fresh and stale != fresh,
    f"{stale} -> {fresh}",
)
c, b = api("POST", f"{A}/documents/{race}/rigor", {"rigor": CONTRACT, "expected_digest": stale})
ok(
    "the loser of the race is refused",
    c == 409 and code_of(b) == "stale_digest",
    f"{c} {str(b)[:200]}",
)
c, b = api("POST", f"{A}/documents/{race}/rigor", {"rigor": CONTRACT})
ok(
    "OMITTING the digest promotes the same document the CAS just protected",
    c == 200,
    f"{c} {str(b)[:250]}",
)
note("omitted-digest promotion", f"{c} rigor now {(doc_row(race) or {}).get('rigor')}")

c, b = api("GET", f"{A}/documents/{rd}/rigor-history")
events = (b or {}).get("events") if c == 200 else None
ok("GET .../rigor-history answers 200", c == 200, f"{c} {str(b)[:200]}")
ok(
    "  ... with the one accepted change and no refusals",
    isinstance(events, list) and len(events) == 1,
    str(events)[:300],
)
ev = (events or [{}])[0]
ok("  ... naming from and to", ev.get("from") == SKETCH and ev.get("to") == CONTRACT, str(ev)[:200])
ok("  ... naming the operator as actor", ev.get("actor_kind") == "operator", str(ev)[:200])
ok("  ... carrying the reason given", ev.get("reason") == "promote for the sweep", str(ev)[:200])
ok("  ... and a timestamp", bool(ev.get("created_at")), str(ev)[:200])

# Demotion keeps everything.
reqs_before = {r["identifier"] for r in (requirements(document=rd)[1] or [])}
c, b = api("POST", f"{A}/documents/{rd}/rigor", {"rigor": GATE, "reason": "up to gate"})
ok("contract -> gate is accepted for an enforceable document", c == 200, f"{c} {str(b)[:250]}")
c, b = api("POST", f"{A}/documents/{rd}/rigor", {"rigor": SKETCH, "reason": "back down"})
ok("gate -> sketch (a two-step demotion) is accepted", c == 200, f"{c} {str(b)[:250]}")
reqs_after = {r["identifier"] for r in (requirements(document=rd)[1] or [])}
ok(
    "  ... and demotion destroys no requirement rows",
    reqs_after == reqs_before and len(reqs_after) > 0,
    f"{reqs_before} -> {reqs_after}",
)
c, b = api("GET", f"{A}/documents/{rd}/rigor-history")
ok("  ... and the history keeps every step", len((b or {}).get("events") or []) == 3, str(b)[:300])
ok(
    "  ... in order",
    [e["to"] for e in ((b or {}).get("events") or [])] == [CONTRACT, GATE, SKETCH],
    str([e["to"] for e in ((b or {}).get("events") or [])]),
)

c, b = api("GET", f"{A}/documents/spec/changes/nope-{TAG}/spec.html/rigor-history")
ok("rigor-history of an unknown document is 404", c == 404, f"{c} {str(b)[:200]}")

# =============================================================================================
leg(5, "Proposals — what a contract-rigor write produces, and the two decisions on it")

pd = make_document("proposal", EXPLORING, nreq=2)
c, b = api("POST", f"{A}/documents/{pd}/rigor", {"rigor": CONTRACT, "reason": "so writes propose"})
ok("the proposal fixture reaches contract rigor", c == 200, f"{c} {str(b)[:250]}")

c, b = api("GET", f"{A}/documents/{pd}/proposals")
ok(
    "a contract document with no submissions has no proposals",
    c == 200 and (b or {}).get("proposals") == [],
    f"{c} {str(b)[:200]}",
)

live_before = api("GET", f"{A}/spec?path={pd}")[1].get("content")
c, b = write_content(pd, payload_for("doc proposal", nreq=2, bump=" One clause added."))
ok(
    "a write at contract rigor answers with proposals, not identifiers",
    c == 200 and "proposals" in (b or {}) and "identifiers" not in (b or {}),
    f"{c} {str(b)[:300]}",
)
proposed_units = (b or {}).get("proposals") or []
note(
    "proposals created",
    [(p.get("unit_kind"), p.get("unit_key"), p.get("change_kind")) for p in proposed_units],
)
ok("  ... one per changed unit", len(proposed_units) >= 2, str(proposed_units)[:300])
live_after = api("GET", f"{A}/spec?path={pd}")[1].get("content")
ok("  ... and the LIVE document is untouched", live_before == live_after, "content changed")

# Resubmitting the SAME submission. `_propose` diffs against the LIVE document, which the first
# submission never touched -- so the second submission is still a change and proposes again.
c, b = write_content(pd, payload_for("doc proposal", nreq=2, bump=" One clause added."))
ok("resubmitting the identical submission is not an error", c == 200, f"{c} {str(b)[:250]}")
second_units = (b or {}).get("proposals") or []
note("second identical submission proposed", len(second_units))
ok(
    "a resubmission of the SAME edit proposes nothing new",
    second_units == [],
    f"it created {len(second_units)} more proposals for units already pending: "
    f"{[(u.get('unit_key'), u.get('change_kind')) for u in second_units]}",
)

# A submission truly identical to what is STORED does propose nothing -- the documented case,
# checked here so the red above is not mistaken for that one.
sketchdoc = make_document("nochange", EXPLORING, nreq=2)
api("POST", f"{A}/documents/{sketchdoc}/rigor", {"rigor": CONTRACT})
c, b = write_content(sketchdoc, payload_for("doc nochange", nreq=2))
ok(
    "a submission identical to the STORED document proposes nothing",
    (b or {}).get("proposals") == [],
    str(b)[:300],
)
ok("  ... and names what it left unchanged", bool((b or {}).get("unchanged")), str(b)[:300])

c, b = api("GET", f"{A}/documents/{pd}/proposals")
pending = (b or {}).get("proposals") or []
note("pending proposals after two identical submissions", len(pending))
ok(
    "GET .../proposals lists the pending ones",
    len(pending) == len(proposed_units) + len(second_units),
    f"{len(pending)}",
)
by_unit = {}
for pr in pending:
    by_unit.setdefault(pr["unit_key"], []).append(pr["id"])
ok(
    "no unit has two pending proposals at once",
    all(len(v) == 1 for v in by_unit.values()),
    str({k: len(v) for k, v in by_unit.items()}),
)
ok(
    "  ... each with a status of pending",
    all(p.get("status") == "pending" for p in pending),
    str(pending[:1])[:300],
)
ok(
    "  ... each naming its proposer",
    all(p.get("proposer_actor_kind") for p in pending),
    str(pending[:1])[:300],
)
ok(
    "  ... each with resolved_at still null",
    all(p.get("resolved_at") is None for p in pending),
    str(pending[:1])[:200],
)
ok(
    "  ... ordered by creation",
    [p["created_at"] for p in pending] == sorted(p["created_at"] for p in pending),
)

first, second = pending[0], pending[1]

c, b = bodyless("POST", f"{A}/documents/{pd}/proposals/{first['id']}/accept")
ok(
    "accept with NO body is answered about the proposal (every ProposalDecision field is optional)",
    not (c == 422 and "body" in str(b)),
    f"{c} {str(b)[:250]}",
)
note("bodyless accept", f"{c} {str(b)[:200]}")
c, b = bodyless("POST", f"{A}/documents/{pd}/proposals/{second['id']}/reject")
ok(
    "reject with NO body is answered about the proposal (every ProposalDecision field is optional)",
    not (c == 422 and "body" in str(b)),
    f"{c} {str(b)[:250]}",
)
note("bodyless reject", f"{c} {str(b)[:200]}")

state_now = {
    p["id"]: p["status"]
    for p in (api("GET", f"{A}/documents/{pd}/proposals")[1] or {}).get("proposals", [])
}
note("after the two bodyless probes, still pending", sorted(state_now.values()))

c, b = api(
    "POST",
    f"{A}/documents/{pd}/proposals/{first['id']}/accept",
    {"reason": "looks right", "expected_digest": "0" * 64},
)
ok("accepting on a stale digest is refused 409", c == 409, f"{c} {str(b)[:250]}")
note("stale accept", f"{c} {code_of(b)}")

digest_now = (doc_row(pd) or {}).get("content_digest")
c, b = api(
    "POST",
    f"{A}/documents/{pd}/proposals/{first['id']}/accept",
    {"reason": "looks right", "expected_digest": digest_now},
)
ok("accepting on the current digest lands", c == 200, f"{c} {str(b)[:300]}")
accepted = (b or {}).get("proposal") or {}
ok("  ... the proposal reports accepted", accepted.get("status") == "accepted", str(accepted)[:250])
ok("  ... with a resolved_at", bool(accepted.get("resolved_at")), str(accepted)[:250])
ok(
    "  ... naming who resolved it",
    bool(accepted.get("resolved_by_actor_name")),
    str(accepted)[:250],
)
ok(
    "  ... and keeping the reason the operator gave for accepting",
    accepted.get("resolution_reason") == "looks right",
    f"resolution_reason is {accepted.get('resolution_reason')!r} -- the route declares `reason` "
    "on ProposalDecision and never passes it to accept_proposal(), while reject does",
)
live_now = api("GET", f"{A}/spec?path={pd}")[1].get("content")
ok(
    "  ... and the LIVE document has changed",
    live_now != live_after,
    "content unchanged after an accept",
)

c, b = api("POST", f"{A}/documents/{pd}/proposals/{first['id']}/accept", {"reason": "again"})
ok("accepting the same proposal twice is refused 409", c == 409, f"{c} {str(b)[:250]}")

# The twin the resubmission created for the SAME unit is still pending. What does accepting it do?
twin = next(
    (pr for pr in pending if pr["unit_key"] == first["unit_key"] and pr["id"] != first["id"]), None
)
if twin is None:
    note("no duplicate twin existed for this unit", first["unit_key"])
else:
    note("accepting the duplicate twin of an already-accepted unit", twin["id"])
    c, b = api("POST", f"{A}/documents/{pd}/proposals/{twin['id']}/accept", {"reason": "the twin"})
    note("twin accept", f"{c} {str(b)[:200]}")
    ok(
        "the twin of an accepted unit is not silently re-applied",
        c != 200,
        f"{c} -- a duplicate proposal for a unit already accepted applied again",
    )

c, b = api(
    "POST", f"{A}/documents/{pd}/proposals/{second['id']}/reject", {"reason": "not this one"}
)
ok("rejecting a pending proposal lands", c == 200, f"{c} {str(b)[:250]}")
rejected = (b or {}).get("proposal") or {}
ok("  ... reporting rejected", rejected.get("status") == "rejected", str(rejected)[:250])
ok(
    "  ... with the reason kept",
    rejected.get("resolution_reason") == "not this one",
    str(rejected)[:250],
)
c, b = api("POST", f"{A}/documents/{pd}/proposals/{second['id']}/reject", {"reason": "twice"})
ok("rejecting it twice is refused 409", c == 409, f"{c} {str(b)[:250]}")

c, b = api("GET", f"{A}/documents/{pd}/proposals")
ok(
    "resolved proposals leave the pending list",
    all(p["id"] not in (first["id"], second["id"]) for p in ((b or {}).get("proposals") or [])),
    str(b)[:300],
)

other = make_document("otherdoc", EXPLORING, nreq=2)
c, b = api(
    "POST", f"{A}/documents/{other}/proposals/{first['id']}/accept", {"reason": "wrong document"}
)
ok("a proposal id under the WRONG document is 404", c == 404, f"{c} {str(b)[:250]}")
c, b = api("POST", f"{A}/documents/{pd}/proposals/prop-nope/reject", {"reason": "nope"})
ok("an unknown proposal id is 404", c == 404, f"{c} {str(b)[:250]}")

# Does a sketch-rigor write still write, rather than propose? The contrast case.
c, b = write_content(d2, payload_for("doc second", nreq=2, bump=" Sketch writes go straight in."))
ok(
    "a write at SKETCH rigor still writes, and reports identifiers",
    c == 200 and "identifiers" in (b or {}),
    f"{c} {str(b)[:300]}",
)

# =============================================================================================
leg(6, "Is any of this reachable from the operator's screen? (the F206 measurement, repeated)")

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
    "rigor-history",
    "spec/requirements",
    "spec/coverage",
    "/proposals",
    "/rigor",
]
for frag in FRAGMENTS:
    b_hits, s_hits = hits(BUNDLE, frag), hits(SRC, frag)
    note(f"{frag!r}", f"served bundle {b_hits}, source {s_hits}")
    ok(
        f"the served UI references {frag!r} at least once",
        b_hits > 0,
        f"bundle {b_hits}, src {s_hits}",
    )

# =============================================================================================
leg(7, "The live OpenAPI — which of 9b's routes exist on the agent plane")

req = urllib.request.Request(HUB + "/openapi.json")
with urllib.request.urlopen(req, timeout=30) as r:
    spec_doc = json.loads(r.read().decode())
paths = sorted(spec_doc.get("paths", {}))
op = [p for p in paths if "/project/" in p and ("spec" in p or "documents" in p)]
ag = [p for p in paths if "agent-actions" in p and ("spec" in p or "document" in p)]
note("operator spec routes", len(op))
note("agent-plane spec routes", len(ag))
for p in ag:
    note("  agent", p)
ok(
    "there is NO agent-plane rigor route (an agent cannot lower a gate blocking it)",
    not any("rigor" in p for p in ag),
    str([p for p in ag if "rigor" in p]),
)
ok(
    "there is NO agent-plane proposal-decision route",
    not any("proposals" in p and ("accept" in p or "reject" in p) for p in ag),
    str([p for p in ag if "proposals" in p]),
)
note(
    "agent-plane requirements/coverage routes",
    [p for p in ag if "requirement" in p or "coverage" in p],
)

# =============================================================================================
print(f"\n===== row 9b: {len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL " + f)
