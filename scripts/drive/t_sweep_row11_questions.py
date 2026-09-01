"""SWEEP ROW 11 of 19 — QUESTIONS: ask, answer, decline, and the lists the operator reads.

Rows 1-8, 9a/9b/9c and 10 are done. This is row 11 — the five routes in
`hub/hub/api/v1/questions.py` (POST, GET, GET/{id}, PATCH/{id}, POST/{id}/decline), driven from
the operator plane.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... AW_PROJECT_B=proj-... \
        py -3.11 t_sweep_row11_questions.py

**Row 11 has prior coverage under an older numbering and this file deliberately does not repeat
it.** `t_row13_questions.py` (setup), `t_row13_operator_question.py` (a blocking and a
non-blocking operator question, and whether the answer is delivered), `t_row13_timeout.py` (a real
agent's blocking question expiring) and `t_row19_crash_question.py` (a question outliving a Hub
crash) all exist and all still pass their own ground. What none of them touches is:

* the **decline** route in any form — it is the newest of the five and has never been driven;
* what the two lists the operator actually reads contain **after** a decline;
* whether the two resolutions are **symmetric** (decline-after-answer is refused; is the reverse?);
* schema refusals, pagination bounds, cross-project isolation and bodyless probes on this router.

Method carried from rows 7-10:

* **The fixture machinery is copied, not imported.** Nothing here calls a Hub helper the Hub also
  calls; every fact is read back off a real HTTP response.
* **Create the condition under test** through the real routes. No row inserts.
* **Call the route, do not read its model.**
* **Read the reason for every GREEN**, not just every red.
* **State the precondition** rather than asserting through it — this file is expected to be run
  twice in the same project, so every list assertion is scoped to ids this run created.

No agent turn and no job: this half of row 11 is entirely the operator plane, so there is nothing
to leave enabled. The batch half needs a real run and lives in `t_sweep_row11_batch.py`.
"""

import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT", "")
PB = os.environ.get("AW_PROJECT_B", "")
if P in ("proj-5e960453", "proj-18e5d4e0") or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)
HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ.get("AW_KEY", "aw_live_58ab7d84a1bf7b34eb2d1b424875bacd")
TAG = os.environ.get("AW_RUN_TAG") or __import__("time").strftime("%H%M%S")
REPO = pathlib.Path(__file__).resolve().parents[2]
A = f"/projects/{P}"
AGENT = os.environ.get("AGENT_A", "asker")

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
    """A call with NO body at all — not `{}`, nothing. F204/F210 were found exactly this way."""
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


def ask(stem, **over):
    """The operator-plane create. Every field the schema demands, so an omission is deliberate."""
    body = {
        "from_agent": AGENT,
        "question": f"r11-{TAG}-{stem}: which way should this go?",
        "blocking": False,
        "header": "Direction",
        "multi_select": False,
        "options": [
            {"label": "left", "description": "go left, which costs nothing"},
            {"label": "right", "description": "go right, which costs a rebuild"},
        ],
    }
    body.update(over)
    return api("POST", f"{A}/questions", body)


MINE = re.compile(rf"^r11-{TAG}-")


def mine(rows):
    return [r for r in rows if isinstance(r, dict) and MINE.match(r.get("question", ""))]


note("project", P)
note("project B", PB or "(not set — isolation leg will be skipped)")

# =============================================================================================
leg(1, "Create: what a question is when it is made, and what the create response says")

code, q1 = ask("crud")
ok("POST /questions creates a question", code == 201, f"{code} {str(q1)[:300]}")
Q1 = q1["id"]
note("question id", Q1)
ok("it is not answered", q1.get("answered") is False, repr(q1.get("answered")))
ok("it is not declined", q1.get("declined") is False, repr(q1.get("declined")))
ok("declined_at is null", q1.get("declined_at") is None, repr(q1.get("declined_at")))
# An unbatched question reports batch_size 1 so a reader never special-cases it (schema comment).
ok("an unbatched question reports batch_size 1", q1.get("batch_size") == 1, repr(q1.get("batch_size")))
ok("...and carries no batch id", q1.get("batch_id") is None, repr(q1.get("batch_id")))
ok("the options it was given come back", len(q1.get("options") or []) == 2, str(q1.get("options"))[:200])
# F80's field. The operator route passes created_by_run_id=None, and design D5 says an unknown
# asker is *presumed* waiting rather than guessed inert.
ok(
    "asker_waiting is True for a question with no recorded asker (design D5)",
    q1.get("asker_waiting") is True,
    repr(q1.get("asker_waiting")),
)

code, got = api("GET", f"{A}/questions/{Q1}")
ok("GET /questions/{id} answers 200", code == 200, str(got)[:200])
ok(
    "the detail route agrees with the create response on every field",
    {k: got.get(k) for k in q1} == q1,
    str({k: (q1[k], got.get(k)) for k in q1 if got.get(k) != q1[k]})[:300],
)
code, b = api("GET", f"{A}/questions/q-nosuch{TAG}")
ok("an unknown question id is 404", code == 404, f"{code} {b}")

# =============================================================================================
leg(2, "Schema refusals — the structure `ask_user` is forced to supply is enforced here too")

refusals = [
    ("one option", {"options": [{"label": "only", "description": "x"}]}),
    ("nine options", {"options": [{"label": f"o{i}", "description": "x"} for i in range(9)]}),
    ("an empty label", {"options": [{"label": "", "description": "x"}, {"label": "b", "description": "y"}]}),
]
for name, over in refusals:
    code, b = ask("refuse", **over)
    ok(f"a question with {name} is refused", code == 422, f"{code} {str(b)[:200]}")

for name, drop in (("header", "header"), ("multi_select", "multi_select"), ("options", "options")):
    body = {
        "from_agent": AGENT,
        "question": f"r11-{TAG}-missing-{name}",
        "header": "Direction",
        "multi_select": False,
        "options": [{"label": "a", "description": "x"}, {"label": "b", "description": "y"}],
    }
    body.pop(drop)
    code, b = api("POST", f"{A}/questions", body)
    ok(f"a question with no {name} is refused", code == 422, f"{code} {str(b)[:200]}")

code, b = ask("extra", **{"nonsense_field": 1})
ok("an undeclared field is refused (extra=forbid)", code == 422, f"{code} {str(b)[:200]}")

# =============================================================================================
leg(3, "Bodyless probes on every mutating route (F204/F210's shape)")

# `POST /{id}/decline` is deliberately NOT in this loop. It takes no body, so bodyless is its
# *normal* call and probing it here would decline Q1 before the "nothing was half-applied" check
# below — which would then be asserting against this harness's own action rather than the
# product's. Row 10 nearly manufactured a false finding the same way; it is called after the
# check instead.
probes = [
    ("POST", f"{A}/questions"),
    ("PATCH", f"{A}/questions/{Q1}"),
]
for method, path in probes:
    code, b = bodyless(method, path)
    note(f"bodyless {method} {path.split('/')[-1]}", f"{code} {str(b)[:120]}")

code, b = bodyless("POST", f"{A}/questions")
ok("a bodyless POST is refused, not defaulted", code == 422, f"{code} {str(b)[:200]}")
code, b = bodyless("PATCH", f"{A}/questions/{Q1}")
ok("a bodyless PATCH is refused, not treated as an empty answer", code == 422, f"{code} {str(b)[:200]}")

code, after = api("GET", f"{A}/questions/{Q1}")
ok(
    "the refused calls left the question exactly as it was",
    after.get("answered") is False and after.get("declined") is False,
    str(after)[:200],
)

# Now the third route. It takes no body at all, so bodyless is its *normal* call — and this is
# the one probe that must succeed.
code, declined = bodyless("POST", f"{A}/questions/{Q1}/decline")
ok("POST /{id}/decline needs no body and is accepted", code == 200, f"{code} {str(declined)[:300]}")

# =============================================================================================
leg(4, "Decline — the route that has never been driven")

ok("the declined question reports declined", declined.get("declined") is True, repr(declined.get("declined")))
ok("...with a timestamp", bool(declined.get("declined_at")), repr(declined.get("declined_at")))
ok("...and is still not answered", declined.get("answered") is False, repr(declined.get("answered")))
ok("...and carries no answer", declined.get("answer") in (None, ""), repr(declined.get("answer")))

code, kept = api("GET", f"{A}/questions/{Q1}")
# "The row is kept, not deleted: that the operator was asked and chose not to answer is exactly
# the kind of thing the record exists to hold." — decline_question's docstring.
ok("the row is kept, not deleted", code == 200, f"{code} {str(kept)[:200]}")
ok("the detail route reports the decline too", kept.get("declined") is True, repr(kept.get("declined")))

first_at = declined.get("declined_at")
code, again = bodyless("POST", f"{A}/questions/{Q1}/decline")
ok("declining twice is accepted, not a conflict (documented as idempotent)", code == 200, f"{code} {str(again)[:200]}")
ok(
    "...and the second decline does not move the timestamp",
    again.get("declined_at") == first_at,
    f"{first_at} -> {again.get('declined_at')}",
)

code, b = bodyless("POST", f"{A}/questions/q-nosuch{TAG}/decline")
ok("declining an unknown question is 404", code == 404, f"{code} {b}")

# =============================================================================================
leg(5, "The two lists the operator's Questions page actually reads")

# QuestionsPanel.tsx:86-87 — `useQuestions(false)` renders "Unanswered", `useQuestions(true)`
# renders the collapsed "Answered" block. Those two calls are the whole page, so between them they
# have to account for every question. A declined one is resolved: the operator saw it and chose not
# to answer, and `decline_question` exists precisely so it stops "sitting at the head of the queue".
code, unanswered = api("GET", f"{A}/questions?answered=false")
code2, answered = api("GET", f"{A}/questions?answered=true")
ok("GET /questions?answered=false answers 200", code == 200, str(unanswered)[:200])
ok("GET /questions?answered=true answers 200", code2 == 200, str(answered)[:200])
in_un = [r["id"] for r in mine(unanswered)]
in_an = [r["id"] for r in mine(answered)]
note("this run's questions in the Unanswered list", in_un)
note("this run's questions in the Answered list", in_an)
ok(
    "a DECLINED question has left the list the panel labels 'Unanswered'",
    Q1 not in in_un,
    f"{Q1} is still returned by ?answered=false after two declines — QuestionsPanel.tsx:151 "
    f"filters only on `blocking` and `asker_waiting`, and no component reads `declined` at all",
)
ok(
    "...and it is accounted for somewhere on the page",
    Q1 in in_un or Q1 in in_an,
    f"{Q1} appears in neither list",
)

code, unfiltered = api("GET", f"{A}/questions")
ok("the unfiltered list contains it", Q1 in [r["id"] for r in mine(unfiltered)], str(len(unfiltered)))

# =============================================================================================
leg(6, "Answer and decline are two resolutions of one question — are they symmetric?")

code, q2 = ask("answer-first")
Q2 = q2["id"]
code, answered2 = api("PATCH", f"{A}/questions/{Q2}", {"answer": "left", "labels": ["left"]})
ok("PATCH answers a question", code == 200, f"{code} {str(answered2)[:300]}")
ok("the answer comes back", answered2.get("answer") == "left", repr(answered2.get("answer")))
ok("the labels come back as a list", answered2.get("answer_labels") == ["left"], repr(answered2.get("answer_labels")))
ok("...with a timestamp", bool(answered2.get("answered_at")), repr(answered2.get("answered_at")))

code, refused = bodyless("POST", f"{A}/questions/{Q2}/decline")
ok("declining an ANSWERED question is refused", code == 409, f"{code} {str(refused)[:200]}")
ok(
    "...and the refusal says why, in the operator's terms",
    "discard a decision" in str(refused),
    str(refused)[:300],
)
code, still = api("GET", f"{A}/questions/{Q2}")
ok("the refused decline left the answer intact", still.get("answer") == "left" and still.get("declined") is False, str(still)[:200])

# The reverse. `answer_question` never looks at `question.declined`, so this is the mirror of the
# 409 above and the product has to decide the same way twice: a decline is a decision too.
code, q3 = ask("decline-first")
Q3 = q3["id"]
code, _ = bodyless("POST", f"{A}/questions/{Q3}/decline")
ok("precondition: the question is declined", code == 200, str(code))
code, answered3 = api("PATCH", f"{A}/questions/{Q3}", {"answer": "right", "labels": ["right"]})
note("PATCH of a declined question", f"{code} {str(answered3)[:200]}")
ok(
    "answering a DECLINED question is refused, as declining an answered one is",
    code == 409,
    f"{code} — the mirror refusal exists; this one does not, so the same pair of operator actions "
    f"is a conflict in one order and silently accepted in the other",
)
code, both = api("GET", f"{A}/questions/{Q3}")
ok(
    "no question ends up both answered and declined",
    not (both.get("answered") and both.get("declined")),
    f"answered={both.get('answered')} declined={both.get('declined')} "
    f"answer={both.get('answer')!r} — `ask_user` reads these as three distinct outcomes "
    f"(mcp_server.py:338-343) and this row satisfies two of them at once",
)

# =============================================================================================
leg(7, "What does answering a declined question actually DO — is it inert, or does it act?")

# The state above is only a curiosity if nothing downstream reads it. `answer_question` does not
# stop at the row: it calls `_deliver_batch_if_complete`, which queues the answer as depth-zero
# operator input and calls `schedule_agent`. So the question is whether the operator's answer to a
# question they already closed reaches the agent as work.
code, entries = api("GET", f"{A}/queue/{AGENT}")
queued = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
# Scoped to THIS run's tag. Matching the bare stem would count the previous run's entry too,
# and this file is expected to be run twice in one project.
for_q3 = [e for e in queued if f"r11-{TAG}-decline-first" in json.dumps(e)]
note("queue entries for the asking agent", len(queued))
note("entries whose content is the declined question's answer", len(for_q3))
if for_q3:
    note("the text queued for the agent", json.dumps(for_q3[0].get("content"))[:300])
ok(
    "answering an already-declined question queues nothing for the agent",
    not for_q3,
    f"{len(for_q3)} queue entry(ies) — the agent was told to act on a decision the operator had "
    f"already closed, and `ask_user` had already returned declined=True for it",
)

# The control: an ordinary answer to a question that was never declined SHOULD queue, and it is
# only worth reading the red above if this green holds.
code, q4 = ask("plain-answer")
Q4 = q4["id"]
api("PATCH", f"{A}/questions/{Q4}", {"answer": "left", "labels": ["left"]})
code, entries2 = api("GET", f"{A}/queue/{AGENT}")
for_q4 = [e for e in entries2 if isinstance(e, dict) and f"r11-{TAG}-plain-answer" in json.dumps(e)]
ok(
    "control: an ordinary answer DOES queue, so the check above measures the right thing",
    len(for_q4) >= 1,
    f"{len(for_q4)} — if this is 0 the delivery path is off for another reason and the red above "
    f"proves nothing",
)

# =============================================================================================
leg(8, "Pagination bounds on the list route")

code, b = api("GET", f"{A}/questions?limit=0")
ok("limit=0 is refused rather than clamped", code == 422, f"{code} {str(b)[:150]}")
code, b = api("GET", f"{A}/questions?limit=1001")
ok("limit=1001 is refused rather than clamped", code == 422, f"{code} {str(b)[:150]}")
code, b = api("GET", f"{A}/questions?offset=-1")
ok("a negative offset is refused", code == 422, f"{code} {str(b)[:150]}")
code, one = api("GET", f"{A}/questions?limit=1")
ok("limit=1 returns exactly one row", isinstance(one, list) and len(one) == 1, str(one)[:150])
code, page = api("GET", f"{A}/questions?limit=2&offset=0")
code, page2 = api("GET", f"{A}/questions?limit=2&offset=1")
ok(
    "offset shifts the window by one row",
    isinstance(page, list) and isinstance(page2, list) and len(page) == 2 and page[1]["id"] == page2[0]["id"],
    f"{[r['id'] for r in page]} vs {[r['id'] for r in page2]}",
)

# =============================================================================================
leg(9, "Cross-project isolation on all five routes")

if not PB:
    note("skipped", "AW_PROJECT_B is not set")
else:
    B = f"/projects/{PB}"
    code, b = api("GET", f"{B}/questions/{Q1}")
    ok("project B cannot read project A's question", code == 404, f"{code} {str(b)[:150]}")
    code, b = api("PATCH", f"{B}/questions/{Q1}", {"answer": "x", "labels": []})
    ok("project B cannot answer project A's question", code == 404, f"{code} {str(b)[:150]}")
    code, b = bodyless("POST", f"{B}/questions/{Q1}/decline")
    ok("project B cannot decline project A's question", code == 404, f"{code} {str(b)[:150]}")
    code, blist = api("GET", f"{B}/questions")
    ok(
        "project B's list does not contain project A's questions",
        isinstance(blist, list) and Q1 not in [r["id"] for r in blist],
        str(blist)[:200],
    )
    code, after = api("GET", f"{A}/questions/{Q1}")
    ok(
        "and none of those refusals changed anything in project A",
        after.get("declined") is True and after.get("answered") is False,
        str(after)[:200],
    )

# =============================================================================================
leg(10, "Is every route the operator needs reachable from the served bundle?")

BUNDLE = REPO / "hub" / "hub" / "static" / "ui"
SRC = REPO / "hub" / "ui" / "src"


def hits(root, pattern, exts):
    n = 0
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in exts:
            continue
        if "__tests__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found = len(re.findall(pattern, text))
        if found:
            n += found
            files.append(path.name)
    return n, files


# Written as a caller has to write it, not as a word that appears in prose. Row 10 nearly
# manufactured a false stale-bundle finding by matching a word from a comment.
decline_src, decline_files = hits(SRC, r"questions/\$\{[^}]+\}/decline", {".ts", ".tsx"})
decline_bundle, _ = hits(BUNDLE, r"questions/\$\{[^}]+\}/decline", {".js"})
note("POST /decline call sites", f"source {decline_src} ({decline_files}), bundle {decline_bundle}")
ok(
    "the decline route is reachable from the served bundle (F215/F225's shape is ABSENT here)",
    decline_src > 0 and decline_bundle > 0,
    f"source {decline_src}, bundle {decline_bundle}",
)

# Reachable is not the same as reachable from the screen named after the feature.
panel = (SRC / "components" / "questions" / "QuestionsPanel.tsx").read_text(encoding="utf-8")
panel_declines = len(re.findall(r"[Dd]eclin", panel))
note("mentions of 'declin' in QuestionsPanel.tsx", panel_declines)
reads_declined, reads_files = hits(SRC / "components", r"\.declined\b|declined\s*[?)]", {".tsx"})
note("components that read a question's `declined` flag", f"{reads_declined} ({reads_files})")
ok(
    "the Questions page can decline a question, or at least shows that one was declined",
    panel_declines > 0,
    "QuestionsPanel.tsx never mentions decline — the only call site is AgentOutputPanel's "
    "in-run card, so a question declined there is invisible as declined everywhere else",
)

req = urllib.request.Request(HUB + "/openapi.json")
with urllib.request.urlopen(req, timeout=30) as r:
    spec_doc = json.loads(r.read().decode())
row11 = sorted(p for p in spec_doc.get("paths", {}) if "/questions" in p)
note("row 11 routes in the live OpenAPI", len(row11))
for p in row11:
    note("  ", p)

# =============================================================================================
print(f"\n=== ROW 11 (operator plane): {len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAIL  {f}")
