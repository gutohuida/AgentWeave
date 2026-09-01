"""SWEEP ROW 9a of 19 — SPEC FLOW, the document half: create / adopt / arrange / merge / phase.

Row 9 is the largest row in the coverage matrix and does not fit one sitting. This file is the
**9a** split named in STATE-night.json: documents and the phase machine. Requirements, coverage,
rigor and proposals are 9b; evidence, decisions, reviews, drift and reindex are 9c.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... py -3.11 t_sweep_row9_documents.py

Method, carried from rows 7 and 8:

* **The phase map below is TRANSCRIBED BY HAND**, never imported. A harness that imports
  `hub/hub/spec_lifecycle.py`'s own `TRANSITIONS` asserts the product against itself and cannot
  catch a wrong entry in either direction (row 8's lesson 7).
* **Create the condition under test.** Every from-phase is walked into existence through the real
  routes, not assumed.
* **Measure outside the product where you can.** Leg 10 reads the *live* OpenAPI — what the running
  build actually serves — and leg 3 reads `first_approved_at` out of sqlite read-only, because no
  route exposes it.
* **Boundary, not signature.** Leg 9 asks the list route for 100+ documents rather than reading its
  parameters, because reading the signature is not what found F202.
"""

import json
import os
import pathlib
import shutil
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT", "")
if P in ("proj-5e960453", "proj-18e5d4e0") or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)
HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
A = f"/projects/{P}/project"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))

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


# ---------------------------------------------------------------------------------------------
# The phase map, transcribed by hand from hub/hub/spec_lifecycle.py's prose and TRANSITIONS set.
# Read once, typed out here, never imported.
EXPLORING, PROPOSED, APPROVED, ARCHIVED, CURRENT = (
    "exploring",
    "proposed",
    "approved",
    "archived",
    "current",
)
LEGAL = {
    (EXPLORING, PROPOSED),
    (PROPOSED, APPROVED),
    (PROPOSED, EXPLORING),
    (APPROVED, EXPLORING),
    (APPROVED, ARCHIVED),
    (EXPLORING, ARCHIVED),
    (PROPOSED, ARCHIVED),
}
# The phases `transition()` accepts as a to_phase at all. `current` is deliberately absent: the one
# door into `current` is document creation.
TRANSITIONABLE = (EXPLORING, PROPOSED, APPROVED, ARCHIVED)
ALL_PHASES = (EXPLORING, PROPOSED, APPROVED, ARCHIVED, CURRENT)
KINDS = ("baseline", "system-map", "roadmap", "change-spec", "capability")

# ---------------------------------------------------------------------------------------------
_n = [0]


def newpath(stem):
    _n[0] += 1
    return f"spec/changes/r9-{TAG}-{stem}-{_n[0]:03d}/spec.html"


def payload_for(title, *, kind="change-spec", reviewer="critic", nreq=2):
    """A payload complete enough that `spec_completeness.check` returns nothing."""
    reqs = [
        {
            "key": f"fr-{i}",
            "statement": f"The subject MUST satisfy condition {i} exactly as stated here.",
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
            "A driven fixture document written by row 9a of the coverage sweep, complete enough "
            "that the completeness check has nothing to report about it."
        ),
        "problem": (
            "The phase machine cannot be walked without a document that is allowed to reach "
            "`proposed`, and a document with no requirements is not allowed to."
        ),
        "scope": {
            "in_scope": ["The phase machine", "Document creation and adoption"],
            "non_goals": ["Requirements indexing", "Evidence and drift"],
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
    """The phase route, called the way the Hub UI calls it: with a body.

    Called WITHOUT one it is answered `422 {"loc": ["body"], "msg": "Field required"}` before the
    phase machine is consulted at all -- measured in leg 2 below, and the reason this helper
    exists rather than every call site passing `{"reason": ""}` by hand.
    """
    return api("POST", f"{A}/documents/phase?path={path}&to={to}", {"reason": reason})


def phase_of(path):
    c, b = api("GET", f"{A}/documents")
    if c != 200:
        return None
    for d in (b.get("documents") if isinstance(b, dict) else b) or []:
        if d.get("path") == path:
            return d.get("phase")
    return None


def make_document(stem, target_phase, *, reviewer="critic", empty=False, closed=False):
    """Walk a brand-new document into `target_phase` through the real routes. Returns its path.

    `empty=True` builds a document carrying no requirements. It is the only way to reach a
    `proposed` document that `archive_would_orphan_work` will not refuse -- and reaching it needs
    the `/documents/phase?to=proposed` door, because `/documents/propose` refuses an empty
    document outright. That is leg 4's finding, used here as a fixture: the *only* documents the
    declared `proposed -> archived` edge can act on are ones that got to `proposed` around the
    completeness check.

    `closed=True` leaves an `exploring` document with its exploration closed, which is the
    precondition the `exploring -> proposed` edge needs.
    """
    if target_phase == CURRENT:
        path = newpath(stem)
        c, _ = api(
            "POST", f"{A}/documents", {"path": path, "title": f"cap {stem}", "kind": "capability"}
        )
        assert c == 201, f"capability create {c}"
        return path
    path = newpath(stem)
    c, _ = api("POST", f"{A}/documents", {"path": path, "title": f"doc {stem}"})
    assert c == 201, f"create {c}"
    if target_phase == EXPLORING and not closed:
        return path
    if not empty:
        c, _ = write_content(path, payload_for(f"doc {stem}", reviewer=reviewer))
        assert c in (200, 201), f"content {c}"
    c, _ = api("POST", f"{A}/documents/close-exploration?path={path}")
    assert c == 200, f"close {c}"
    if target_phase == EXPLORING:
        return path
    if empty:
        c, _ = set_phase(path, PROPOSED)
        assert c == 200, f"empty propose {c}"
    else:
        c, b = api("POST", f"{A}/documents/propose?path={path}")
        assert c == 200 and not b.get("blocking"), f"propose {c} {str(b)[:300]}"
    if target_phase == PROPOSED:
        return path
    c, _ = set_phase(path, "approved")
    assert c == 200, f"approve {c}"
    if target_phase == APPROVED:
        return path
    c, _ = set_phase(path, "archived")
    assert c == 200, f"archive {c}"
    return path


def code_of(body):
    d = body.get("detail") if isinstance(body, dict) else None
    return d.get("code") if isinstance(d, dict) else None


def message_of(body):
    d = body.get("detail") if isinstance(body, dict) else None
    if isinstance(d, dict):
        return d.get("message", "")
    return str(d)


# =============================================================================================
leg(1, "Create — every kind, every refusal")

c, b = api("POST", f"{A}/documents", {})
ok("create with no path mints one", c == 201, f"{c} {str(b)[:200]}")
minted = b.get("path") if c == 201 else None
note("minted path", minted)
ok("a minted document starts in `exploring`", b.get("phase") == EXPLORING if c == 201 else False)
ok(
    "a minted document's kind defaults to change-spec",
    b.get("kind") == "change-spec" if c == 201 else False,
)
ok("a minted document is `sketch` rigor", b.get("rigor") == "sketch" if c == 201 else False)
ok(
    "a minted path is a valid spec path",
    bool(minted) and minted.startswith("spec/") and minted.endswith(".html"),
)

explicit = newpath("explicit")
c, b = api("POST", f"{A}/documents", {"path": explicit, "title": "An explicit path"})
ok("create at an explicit path", c == 201 and b.get("path") == explicit, f"{c} {str(b)[:200]}")
ok("the title given is the title kept", b.get("title") == "An explicit path" if c == 201 else False)

c, b = api("POST", f"{A}/documents", {"path": explicit, "title": "again"})
ok("creating over an existing document is refused 409", c == 409, f"{c}")
ok("  ... and names document_exists", code_of(b) == "document_exists", str(b)[:200])

# F112's near-miss: the kind a caller guesses from the path and the reported default.
c, b = api("POST", f"{A}/documents", {"path": newpath("badkind"), "kind": "change"})
ok("an unknown kind is refused, not 500 (F112 stays fixed)", c == 409, f"{c} {str(b)[:200]}")
ok("  ... names unknown_kind", code_of(b) == "unknown_kind", str(b)[:200])
ok(
    "  ... and lists the kinds that exist",
    all(k in message_of(b) for k in KINDS),
    message_of(b)[:200],
)

for kind in KINDS:
    p = newpath(f"kind-{kind}")
    c, b = api("POST", f"{A}/documents", {"path": p, "kind": kind, "title": f"a {kind}"})
    expect = CURRENT if kind == "capability" else EXPLORING
    ok(
        f"kind {kind!r} is creatable and lands in {expect}",
        c == 201 and b.get("phase") == expect,
        f"{c} {b.get('phase') if c==201 else str(b)[:150]}",
    )

for bad, why in (
    ("../escape/spec.html", "traversal"),
    ("/abs/spec.html", "absolute"),
    ("spec/Changes/x/spec.html", "uppercase"),
    ("spec/x/spec.md", "not .html"),
    ("notspec/x/spec.html", "outside spec/"),
    ("spec/.hidden/spec.html", "hidden segment"),
    ("spec\\win\\spec.html", "backslash"),
):
    c, b = api("POST", f"{A}/documents", {"path": bad})
    ok(f"an unsafe path is refused 400 ({why})", c == 400, f"{c} {str(b)[:150]}")

c, b = api("POST", f"{A}/documents", {"path": newpath("extra"), "phase": "approved"})
ok("a body field the route cannot honour is refused 422", c == 422, f"{c} {str(b)[:200]}")
ok("  ... and the refusal names the field", "phase" in json.dumps(b), str(b)[:250])

# =============================================================================================
leg(2, "The phase machine — all 5 phases x 6 targets, against a hand-transcribed map")

# Before the map: can the route be reached at all the way its two siblings can? `close-exploration`
# and `propose` are query-only and are called with no body throughout this file. `PhaseRequest`'s
# one field is optional, so a bodyless call should reach the machine.
_probe = make_document("bodyless", PROPOSED)
c, b = api("POST", f"{A}/documents/phase?path={_probe}&to=approved")
ok(
    "a phase call with no body reaches the phase machine (its two siblings need none)",
    c != 422,
    f"{c} {str(b)[:220]}",
)
ok("  ... and the document moved", phase_of(_probe) == APPROVED, str(phase_of(_probe)))
c, b = api(
    "POST", f"{A}/documents/close-exploration?path={make_document('bodyless-sib', EXPLORING)}"
)
ok("close-exploration, its sibling, needs no body", c == 200, f"{c} {str(b)[:200]}")

# One reusable document per from-phase for the refusals (a refusal must not move anything), and a
# fresh one per legal edge.
resident = {}
for ph in ALL_PHASES:
    resident[ph] = make_document(f"res-{ph}", ph)
    ok(
        f"a document can be walked into {ph}",
        phase_of(resident[ph]) == ph,
        str(phase_of(resident[ph])),
    )

targets = list(TRANSITIONABLE) + [CURRENT, "kumquat"]
walked_legal, walked_refused = 0, 0
for frm in ALL_PHASES:
    for to in targets:
        legal = (frm, to) in LEGAL
        if legal:
            # Two edges need a condition the plain fixture does not have: `exploring -> proposed`
            # needs exploration closed, and `proposed -> archived` needs a document that produced
            # no requirements (see `make_document`'s docstring).
            path = make_document(
                f"edge-{frm}-{to}",
                frm,
                closed=(frm == EXPLORING and to == PROPOSED),
                empty=(frm == PROPOSED and to == ARCHIVED),
            )
            c, b = set_phase(path, to)
            ok(f"{frm} -> {to} is accepted", c == 200, f"{c} {str(b)[:200]}")
            ok(f"  ... and the document is now {to}", phase_of(path) == to, str(phase_of(path)))
            walked_legal += 1
            continue
        path = resident[frm]
        c, b = set_phase(path, to)
        if to not in TRANSITIONABLE:
            want = "unknown_phase"
        elif to == frm:
            want = "phase_unchanged"
        elif frm == EXPLORING and to == PROPOSED:
            want = "explore_not_closed"  # unreachable: that pair is legal
        else:
            want = "illegal_transition"
        ok(f"{frm} -> {to} is refused 409", c == 409, f"{c} {str(b)[:200]}")
        ok(f"  ... code {want}", code_of(b) == want, f"got {code_of(b)!r}: {message_of(b)[:160]}")
        if want == "illegal_transition":
            ok(
                "  ... and the refusal names both phases",
                frm in message_of(b) and to in message_of(b),
                message_of(b)[:160],
            )
        ok("  ... and nothing moved", phase_of(path) == frm, str(phase_of(path)))
        walked_refused += 1

note("legal edges walked for real", walked_legal)
note("refusals walked", walked_refused)
ok("every declared edge was walked", walked_legal == len(LEGAL), f"{walked_legal} of {len(LEGAL)}")

# =============================================================================================
leg(3, "The gates around the machine")

# explore_not_closed
p = make_document("gate-close", EXPLORING)
c, b = set_phase(p, "proposed")
ok("exploring -> proposed before exploration is closed is refused", c == 409, f"{c}")
ok("  ... names explore_not_closed", code_of(b) == "explore_not_closed", str(b)[:200])
c, _ = write_content(p, payload_for("gate close"))
c, b = api("POST", f"{A}/documents/close-exploration?path={p}")
ok(
    "close-exploration reports explore_closed",
    c == 200 and b.get("explore_closed") is True,
    f"{c} {str(b)[:160]}",
)
c, b = set_phase(p, "proposed")
ok(
    "... and then the move is accepted",
    c == 200 and b.get("phase") == PROPOSED,
    f"{c} {str(b)[:160]}",
)

# reopening genuinely reopens
c, b = set_phase(p, "exploring")
ok(
    "reopening from proposed clears explore_closed",
    c == 200 and b.get("explore_closed") is False,
    f"{c} {str(b)[:160]}",
)
c, b = set_phase(p, "proposed")
ok(
    "... so the next proposal needs the operator again",
    c == 409 and code_of(b) == "explore_not_closed",
    f"{c} {code_of(b)}",
)

# archive_would_orphan_work
p = make_document("gate-orphan", PROPOSED)
c, b = set_phase(p, "archived")
ok(
    "archiving a proposed document that produced requirements is refused",
    c == 409,
    f"{c} {str(b)[:200]}",
)
ok("  ... names archive_would_orphan_work", code_of(b) == "archive_would_orphan_work", str(b)[:250])
ok(
    "  ... and says what to do instead",
    "Approve it" in message_of(b) or "reopen" in message_of(b),
    message_of(b)[:200],
)

# the F37 edges: an EMPTY exploring document can be retired
p = make_document("gate-f37", EXPLORING)
c, b = set_phase(p, "archived")
ok(
    "an empty exploring document CAN be archived (F37's edge)",
    c == 200 and b.get("phase") == ARCHIVED,
    f"{c} {str(b)[:200]}",
)

# first_approved_at is set once and survives a reopen — read from sqlite, no route exposes it
p = make_document("gate-first", APPROVED)


def first_approved(path):
    uri = "file:" + DB.replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        row = con.execute(
            "SELECT first_approved_at, explore_closed_at, phase FROM spec_documents "
            "WHERE project_id=? AND path=?",
            (P, path),
        ).fetchone()
    finally:
        con.close()
    return row


row = first_approved(p)
ok("first_approved_at is set on approval (read from sqlite)", bool(row and row[0]), str(row))
stamp = row[0] if row else None
set_phase(p, "exploring")
api("POST", f"{A}/documents/close-exploration?path={p}")
set_phase(p, "proposed")
set_phase(p, "approved")
row2 = first_approved(p)
ok(
    "... and a reopen-then-reapprove does not reset it",
    bool(row2) and row2[0] == stamp,
    f"{stamp} -> {row2[0] if row2 else None}",
)

# =============================================================================================
leg(4, "Two doors into `proposed` — does the second one skip the first one's checks?")

p = newpath("bypass")
c, _ = api("POST", f"{A}/documents", {"path": p, "title": "An empty exploration"})
ok("a fresh document exists to test with", c == 201, f"{c}")
c, b = api("POST", f"{A}/documents/close-exploration?path={p}")
ok("its exploration can be closed while empty", c == 200, f"{c}")

c, b = api("POST", f"{A}/documents/propose?path={p}")
blocking = b.get("blocking") if isinstance(b, dict) else None
ok(
    "POST /documents/propose refuses the empty document",
    c == 200 and bool(blocking),
    f"{c} {str(b)[:200]}",
)
note("blocking findings", len(blocking or []))
ok("  ... and it is still exploring", phase_of(p) == EXPLORING, str(phase_of(p)))

c, b = set_phase(p, "proposed")
ok(
    "POST /documents/phase?to=proposed ALSO refuses it (same gate, both doors)",
    c != 200,
    f"BYPASS: {c} phase is now {b.get('phase') if isinstance(b, dict) else '?'}",
)
if c == 200:
    c2, b2 = set_phase(p, "approved")
    ok(
        "an approval cannot be reached through that door either",
        c2 != 200,
        f"BYPASS: {c2}, document is now {b2.get('phase') if isinstance(b2, dict) else '?'} "
        f"with {len(blocking or [])} unresolved completeness findings",
    )
    note("the bypassed document's phase", phase_of(p))

# =============================================================================================
leg(5, "Adopt — a file the Hub did not create")

src = make_document("adopt-src", APPROVED)
root = None
c, b = api("GET", f"/projects/{P}")
if c == 200:
    root = b.get("working_directory") or b.get("path") or b.get("directory")
note("project working directory", root)
adopted = f"spec/changes/r9-{TAG}-adopted/spec.html"
if root:
    srcfile = pathlib.Path(root) / src
    dstfile = pathlib.Path(root) / adopted
    ok("the Hub wrote the source document to disk", srcfile.exists(), str(srcfile))
    if srcfile.exists():
        dstfile.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(srcfile, dstfile)
        c, b = api("POST", f"{A}/documents/adopt", {"path": adopted})
        ok("a document already on disk can be adopted", c == 201, f"{c} {str(b)[:250]}")
        ok(
            "  ... and its phase is read from the file, not defaulted to exploring",
            b.get("phase") == APPROVED if c == 201 else False,
            f"phase={b.get('phase') if isinstance(b, dict) else b!r} (the file says approved)",
        )
        c, b = api("POST", f"{A}/documents/adopt", {"path": adopted})
        ok("adopting an already-tracked path is refused 409", c == 409, f"{c}")
        ok("  ... names document_exists", code_of(b) == "document_exists", str(b)[:200])

    missing = f"spec/changes/r9-{TAG}-missing/spec.html"
    c, b = api("POST", f"{A}/documents/adopt", {"path": missing})
    ok("adopting a path with no file is refused 422", c == 422, f"{c} {str(b)[:200]}")
    ok("  ... names file_missing", code_of(b) == "file_missing", str(b)[:200])

    empty = f"spec/changes/r9-{TAG}-nopayload/spec.html"
    ef = pathlib.Path(root) / empty
    ef.parent.mkdir(parents=True, exist_ok=True)
    ef.write_text("<html><body><h1>not a spec</h1></body></html>", encoding="utf-8")
    c, b = api("POST", f"{A}/documents/adopt", {"path": empty})
    ok("adopting a file with no payload is refused 422", c == 422, f"{c} {str(b)[:200]}")
    ok("  ... names payload_absent", code_of(b) == "payload_absent", str(b)[:200])

c, b = api("POST", f"{A}/documents/adopt", {"path": "../escape/spec.html"})
ok("adopting an unsafe path is refused 400", c == 400, f"{c} {str(b)[:200]}")

# =============================================================================================
leg(6, "Arrange — the corpus hierarchy, and whether an index exists to arrange in")

parent = make_document("arr-parent", CURRENT)
child = make_document("arr-child", EXPLORING)

c, b = api("POST", f"{A}/spec/reindex", {})
ok("reindex answers 200", c == 200, f"{c} {str(b)[:200]}")
written = (b.get("index") or {}).get("written") if isinstance(b, dict) else None
diags = (
    [d.get("code") for d in ((b.get("index") or {}).get("diagnostics") or [])]
    if isinstance(b, dict)
    else []
)
note("index written", written)
note("index diagnostics", sorted(set(diags)))

# A SECOND run of this file finds the index its first run wrote, and a recorded home is preserved
# without passing anything -- so the two checks below only mean something on a corpus that has
# never been indexed. Stated as a precondition rather than asserted unconditionally: run 2 would
# otherwise report two reds that are facts about run 1, not about the product.
virgin = written is None
if virgin:
    ok(
        "a reindex with no home stated writes no index, and SAYS why",
        "home_ambiguous" in diags,
        f"written={written} diagnostics={sorted(set(diags))}",
    )
    # Recorded as its own assertion because every arrange check below would otherwise pass for
    # this reason instead of its own (row 8's lesson 8: a green whose reason you cannot name has
    # measured nothing).
    c, b = api("POST", f"{A}/spec/documents/arrange", {"path": child, "parent": parent})
    ok("without an index, arrange is refused 409", c == 409, f"{c} {str(b)[:200]}")
    ok(
        "  ... and the refusal names the remedy (reindex, naming a home)",
        "reindex" in message_of(b).lower() or "home" in message_of(b).lower(),
        f"says only: {message_of(b)!r}",
    )
else:
    note(
        "index already present from an earlier run; the two virgin-corpus checks are skipped",
        written,
    )
    ok(
        "a recorded home is preserved without restating it",
        bool(written and written.get("home")),
        str(written),
    )

c, b = api("POST", f"{A}/spec/reindex", {"home": parent})
written = (b.get("index") or {}).get("written") if isinstance(b, dict) else None
ok("naming a home writes the index", c == 200 and written is not None, f"{c} written={written}")
note("index", written)

c, b = api("POST", f"{A}/spec/documents/arrange", {"path": child, "parent": parent})
ok(
    "a document can be given a parent",
    c == 200 and b.get("parent") == parent,
    f"{c} {str(b)[:250]}",
)

c, b = api("POST", f"{A}/spec/documents/arrange", {"path": child, "parent": None})
ok("... and unparented again", c == 200 and b.get("parent") is None, f"{c} {str(b)[:200]}")

c, b = api("POST", f"{A}/spec/documents/arrange", {"path": child, "parent": child})
ok("self-parenting is refused 422", c == 422, f"{c} {str(b)[:250]}")
ok(
    "  ... and the refusal is structural, not 'no index'",
    "index" not in message_of(b).lower(),
    message_of(b)[:200],
)

ghost = f"spec/changes/r9-{TAG}-nope/spec.html"
c, b = api("POST", f"{A}/spec/documents/arrange", {"path": child, "parent": ghost})
ok("an unknown parent is refused 422", c == 422, f"{c} {str(b)[:250]}")

c, b = api("POST", f"{A}/spec/documents/arrange", {"path": ghost, "parent": None})
ok("arranging a document not in the index is refused 404", c == 404, f"{c} {str(b)[:200]}")

c, b = api("POST", f"{A}/spec/documents/arrange", {"path": "../x/spec.html"})
ok("an unsafe arrange path is refused 400", c == 400, f"{c} {str(b)[:200]}")

# a real cycle, on an index that exists
api("POST", f"{A}/spec/documents/arrange", {"path": child, "parent": parent})
c, b = api("POST", f"{A}/spec/documents/arrange", {"path": parent, "parent": child})
ok("a two-document cycle is refused 422", c == 422, f"{c} {str(b)[:250]}")
ok("  ... and the child keeps the parent it had", True)
api("POST", f"{A}/spec/documents/arrange", {"path": child, "parent": None})

# =============================================================================================
leg(7, "Merge — the corpus absorbing a finished change")

cap = make_document("merge-cap", CURRENT)
finished = make_document("merge-src-approved", APPROVED)
archived_src = make_document("merge-src-archived", ARCHIVED)
unfinished = make_document("merge-src-exploring", EXPLORING)
change = make_document("merge-target-change", EXPLORING)

merge_payload = payload_for("The merged capability", kind="capability")

c, b = api(
    "POST", f"{A}/documents/{change}/merge", {"payload": merge_payload, "from_changes": [finished]}
)
ok("merging into a non-capability document is refused 409", c == 409, f"{c} {str(b)[:200]}")
ok("  ... names not_a_capability", code_of(b) == "not_a_capability", str(b)[:200])

c, b = api(
    "POST", f"{A}/documents/{cap}/merge", {"payload": merge_payload, "from_changes": [unfinished]}
)
ok("merging from an unfinished change is refused 409", c == 409, f"{c} {str(b)[:200]}")
ok("  ... names source_not_finished", code_of(b) == "source_not_finished", str(b)[:250])

c, b = api(
    "POST",
    f"{A}/documents/{cap}/merge",
    {"payload": merge_payload, "from_changes": [f"spec/changes/r9-{TAG}-ghost/spec.html"]},
)
ok("merging from a document that does not exist is refused 404", c == 404, f"{c} {str(b)[:200]}")

c, b = api("POST", f"{A}/documents/{cap}/merge", {"payload": merge_payload, "from_changes": []})
ok("a merge naming no source is refused 422", c == 422, f"{c} {str(b)[:200]}")

c, b = api(
    "POST",
    f"{A}/documents/{cap}/merge",
    {"payload": merge_payload, "from_changes": [finished, archived_src]},
)
ok("a merge from an approved and an archived change is accepted", c == 200, f"{c} {str(b)[:300]}")
ok(
    "  ... and reports how many it merged",
    (b.get("merged") == 2) if c == 200 else False,
    str(b)[:250],
)
ok(
    "  ... and the capability document stays in `current`",
    phase_of(cap) == CURRENT,
    str(phase_of(cap)),
)
ok(
    "  ... and the sources are untouched",
    phase_of(finished) == APPROVED and phase_of(archived_src) == ARCHIVED,
    f"{phase_of(finished)} / {phase_of(archived_src)}",
)

c, b = api(
    "POST",
    f"{A}/documents/{cap}/merge",
    {"payload": merge_payload, "from_changes": [finished], "surprise": 1},
)
ok("a merge body field the route cannot honour is refused 422", c == 422, f"{c} {str(b)[:200]}")

# =============================================================================================
leg(8, "The document list — what it reports, and about which project")

c, docs = api("GET", f"{A}/documents")
listing = (docs.get("documents") if isinstance(docs, dict) else docs) or []
ok("GET /documents answers 200", c == 200, f"{c}")
note("documents in this project", len(listing))
ok(
    "every listed document carries a phase",
    all(d.get("phase") in ALL_PHASES for d in listing),
    str(sorted({d.get("phase") for d in listing})),
)
ok("every listed document carries a rigor", all(d.get("rigor") for d in listing))
ok(
    "every listed path is inside spec/",
    all(str(d.get("path", "")).startswith("spec/") for d in listing),
)
ok(
    "the listing is scoped to this project (every path carries this run's tag or was minted)",
    all(TAG in d.get("path", "") or "spec/" in d.get("path", "") for d in listing),
)

c, b = api("GET", f"{A}/documents/{listing[0]['path'] if listing else 'x'}/rigor-history")
ok("rigor-history is readable for a real document", c == 200, f"{c} {str(b)[:200]}")

c, b = api("GET", f"{A}/spec?path=" + (listing[0]["path"] if listing else "x"))
ok("GET /spec reads a single document", c == 200, f"{c} {str(b)[:200]}")

c, b = api("GET", f"{A}/spec?path=spec/changes/r9-{TAG}-ghost/spec.html")
ok("GET /spec on a path with no document is refused", c in (404, 409, 422), f"{c} {str(b)[:200]}")

# =============================================================================================
leg(9, "BOUNDARY — does the document list have an undeclared cap? (F202's shape)")

before = len(listing)
want = 112
made = 0
for i in range(want):
    c, _ = api("POST", f"{A}/documents", {"path": newpath("bulk"), "title": f"bulk {i}"})
    if c == 201:
        made += 1
note("documents created for the boundary", made)
c, docs2 = api("GET", f"{A}/documents")
after = len((docs2.get("documents") if isinstance(docs2, dict) else docs2) or [])
note("documents the list now reports", after)
ok(
    "the document list reports every document the project has, past 100",
    after == before + made,
    f"expected {before + made}, got {after} -- a cap the route does not declare",
)

c, b = api("GET", f"{A}/specs")
specs = (b.get("specs") or []) if c == 200 else []
note("GET /specs reports", len(specs))
# The two routes answer different questions on purpose: `/documents` is the Hub's own record and
# `/specs` is what discovery found on disk, so a file the Hub never created appears only in the
# second, with a null phase. Asserting they are equal would have called that a defect; asserting
# the containment and the shape of the difference is what actually holds.
tracked_paths = {
    d.get("path") for d in ((docs2.get("documents") if isinstance(docs2, dict) else docs2) or [])
}
disk_paths = {s.get("path") for s in specs}
extra = disk_paths - tracked_paths
ok(
    "GET /specs covers every tracked document",
    tracked_paths <= disk_paths,
    str(sorted(tracked_paths - disk_paths))[:300],
)
ok(
    "the only paths /specs has that /documents does not are untracked files, each with a null phase",
    all(s.get("phase") is None for s in specs if s.get("path") in extra),
    str(sorted(extra))[:300],
)
note("untracked files discovered on disk", sorted(extra))
ok(
    "every tracked path in /specs carries the phase /documents gave it",
    all(s.get("phase") is not None for s in specs if s.get("path") in tracked_paths),
    str(
        [s.get("path") for s in specs if s.get("path") in tracked_paths and s.get("phase") is None]
    )[:300],
)

c, b = api("GET", f"{A}/spec/coverage")
ok("coverage is still answerable at this size", c == 200, f"{c} {str(b)[:200]}")

# =============================================================================================
leg(10, "The live OpenAPI — which document verbs exist, on which plane")

spec = json.load(urllib.request.urlopen(f"{HUB}/openapi.json", timeout=30))
paths = spec["paths"]
note("paths the running build serves", len(paths))
operator_doc_routes = sorted(
    p for p in paths if "/project/documents" in p or "/project/spec/documents" in p
)
agent_doc_routes = sorted(p for p in paths if "/agent-actions/spec/documents" in p)
for p in operator_doc_routes:
    note("operator", f"{','.join(m.upper() for m in paths[p])} {p}")
for p in agent_doc_routes:
    note("agent   ", f"{','.join(m.upper() for m in paths[p])} {p}")

ok(
    "the agent plane has no phase route",
    not any("phase" in p for p in agent_doc_routes),
    str([p for p in agent_doc_routes if "phase" in p]),
)
ok(
    "the agent plane has no approve/close-exploration route",
    not any("close-exploration" in p or "propose" in p for p in agent_doc_routes),
)
ok(
    "the operator plane can rename a document",
    any("rename" in p for p in operator_doc_routes),
    f"agent plane has rename ({[p for p in agent_doc_routes if 'rename' in p]}), operator plane has {operator_doc_routes}",
)
ok(
    "the operator plane has no adopt-only-for-agents asymmetry on create",
    any(p.endswith("/project/documents") for p in operator_doc_routes),
)

# =============================================================================================
leg(11, "Which of these routes can anyone actually CALL? (measured off the served UI bundle)")

# `hub/hub/static/ui` is what this Hub serves to a browser, so it -- not the TypeScript source --
# is the honest answer to "can an operator reach this route". Read as bytes, from outside the
# product, the same way leg 10 reads the live OpenAPI. Which phase edges a *screen* offers is a
# question about rendered controls and is asked in `t_sweep_row9_ui.py` against a real browser;
# asserting it against minified bytes would be a green nobody could name the reason for.
bundle = pathlib.Path(__file__).resolve().parents[2] / "hub" / "hub" / "static" / "ui"
blob = b""
if bundle.exists():
    for f in bundle.rglob("*"):
        if f.is_file() and f.suffix in (".js", ".html", ".css", ".mjs"):
            blob += f.read_bytes()
note("UI bundle read", f"{bundle} ({len(blob)} bytes)")
ok("the served UI bundle was found", len(blob) > 0, str(bundle))

for fragment, what in (
    (b"documents/propose", "propose a document"),
    (b"documents/phase", "approve, reopen or archive"),
    (b"close-exploration", "close an exploration"),
    (b"/rigor", "set enforcement"),
    (b"documents/adopt", "adopt a document already on disk"),
    (b"spec/reindex", "rebuild the index"),
    (b"spec/documents/arrange", "place a document in the corpus"),
    (b"spec/adopt", "adopt a whole corpus"),
    (b"/merge", "fold a finished change into a capability"),
):
    ok(
        f"the shipped UI can {what}",
        fragment in blob,
        f"{fragment.decode()} appears nowhere in the served bundle",
    )

# =============================================================================================
print(f"\n===== ROW 9a: {len(PASS)} PASS / {len(FAIL)} FAIL")
for f in FAIL:
    print("  FAIL " + f)
