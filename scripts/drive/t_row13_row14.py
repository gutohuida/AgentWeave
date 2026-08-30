"""Rows 13 (Questions) and 14 (Permissions) — driven with a real agent turn.

Both rows were left "partial"/"not reached" by the 2026-08-28 sweep for want of a live
turn. They are the two operator-in-the-loop surfaces, and CLAUDE.md is explicit that
there is deliberately *no backstop* behind either: an agent that needs an answer calls
`ask_user`, and a turn that ends without calling it has ended. So the only way to know
they work is to make an agent call them.

Cheap runner (Haiku) throughout, per the operator's standing directive: what these rows
assert is that a turn *starts, blocks on the operator, and resumes with the answer* —
not that the agent writes anything good.

Run `t_row13_questions.py` first; it creates the project, runner and agent.
"""

import os
import sys
import time

from aw import api
from t_row13_questions import PROJECT_NAME, ensure_agent, ensure_project, ensure_runner, show

NOTE_NAME = "drive-note-{}.txt".format(os.environ.get("DRIVE_TAG", "x"))

POLL_SECONDS = 4
WAIT_LIMIT = 40  # ~160s; a Haiku turn that has not asked by then is not going to


def wait_for(label, fn, limit=WAIT_LIMIT):
    """Poll fn() until it returns something truthy. Returns None on timeout."""
    for i in range(limit):
        got = fn()
        if got:
            print(f"  {label} after ~{i * POLL_SECONDS}s")
            return got
        time.sleep(POLL_SECONDS)
    print(f"  TIMEOUT waiting for {label} (~{limit * POLL_SECONDS}s)")
    return None


def open_questions(project):
    code, body = api("GET", f"/projects/{project}/questions")
    rows = body.get("questions") if isinstance(body, dict) else body
    # The question schema has no `status` string: openness is `answered`/`declined`
    # booleans, with `asker_waiting` saying whether a run is actually blocked on it.
    # Filtering on a `status` that does not exist made row 13 read as "no question
    # was ever raised" when the question was sitting right there, blocking.
    return [q for q in (rows or []) if not q.get("answered") and not q.get("declined")]


def agent_status(project, agent):
    _, body = api("GET", f"/projects/{project}/agents")
    for row in body if isinstance(body, list) else body.get("agents") or []:
        if row.get("name") == agent:
            return row.get("status")
    return "?"


def wait_idle(project, agent, limit=WAIT_LIMIT):
    """Both rows trigger the same agent, and a busy agent's trigger only queues.

    Row 14 read FAIL for 160 seconds on 2026-08-30 because row 13's run had not finished: its
    trigger answered `status: "queued", waiting_reason: "agent is already running"`, so no
    permission card could exist and the row blamed the product for the harness's sequencing.
    """
    for _ in range(limit):
        if agent_status(project, agent) != "running":
            return True
        time.sleep(POLL_SECONDS)
    return False


def row13(project, agent):
    print("\n=== ROW 13 — Questions: ask_user blocks a run, an answer releases it ===")
    # Every open question in the project, before this row asks for one. A drive that ran earlier
    # in the same project leaves its own questions open, and matching "the first open question"
    # answered a peer's question and called row 13 passing (2026-08-30). Openness is not enough:
    # the question has to be NEW and it has to be from the agent under test.
    already = {q["id"] for q in open_questions(project)}
    wait_idle(project, agent)
    code, body = api(
        "POST",
        f"/projects/{project}/agent/trigger",
        {
            "agent": agent,
            "message": (
                "Call the ask_user tool exactly once with a single question: "
                "'Which colour should the badge be?' with options 'red' and 'blue'. "
                "When you get the answer back, reply with only the word you were given, "
                "nothing else. Do not read or write any files."
            ),
        },
    )
    show("POST /agent/trigger", code, body)
    if code >= 300:
        return "TRIGGER REFUSED"

    def fresh_question():
        rows = [
            q
            for q in open_questions(project)
            if q["id"] not in already and q.get("from_agent") == agent
        ]
        return rows[0] if rows else None

    q = wait_for("question appeared", fresh_question)
    if not q:
        return "FAIL — no question was ever raised"
    print("  question: {}".format(str(q.get("prompt") or q.get("text") or q)[:160]))

    code, body = api(
        "PATCH",
        "/projects/{}/questions/{}".format(project, q["id"]),
        {"answer": "blue", "labels": ["blue"]},
    )
    show("PATCH answer question", code, body)
    if code >= 300:
        return f"FAIL — could not answer the question: {body}"

    settled = wait_for(
        "question left the open list",
        lambda: not [x for x in open_questions(project) if x["id"] == q["id"]],
    )
    return "PASS — question raised and answered" if settled else "FAIL — question stayed open"


def row14(project, agent):
    print("\n=== ROW 14 — Permissions: manual posture produces a decision card ===")
    if not wait_idle(project, agent):
        return "SKIPPED - the agent never went idle after row 13"
    code, body = api(
        "POST",
        f"/projects/{project}/agent/trigger",
        {
            "agent": agent,
            "message": (
                "Write the single line 'drive touched this' to a new file named "
                f"{NOTE_NAME} in the project root, using the Write tool. Then stop."
            ),
            # Posture travels in `overrides`, keyed `permission_mode` — the same map the
            # composer's Permissions pill fills (modelCatalog.ts:56, AgentOutputPanel.tsx:328).
            # A top-level "permission_mode" is NOT a field on TriggerAgentRequest; sending one
            # returns 200 and is silently dropped, and the run proceeds unsupervised.
            "overrides": {"permission_mode": "manual"},
        },
    )
    show("POST /agent/trigger (manual)", code, body)
    if code >= 300:
        return f"TRIGGER REFUSED — {body}"

    def pending():
        c, b = api("GET", f"/projects/{project}/permission-requests")
        rows = b.get("permission_requests") if isinstance(b, dict) else b
        return [r for r in (rows or []) if not r.get("decided_at") and not r.get("decision")]

    req = wait_for("permission card appeared", lambda: (pending() or [None])[0])
    if not req:
        return "FAIL — no permission request was ever raised"
    print(f"  card: {str(req)[:220]}")

    code, body = api(
        "POST",
        "/projects/{}/permission-requests/{}/decide".format(project, req["id"]),
        # `{"allow": true}` (`PermissionDecision`, permissions.py:25-26) - NOT
        # `{"decision": "allow"}`, which this harness sent until 2026-08-30 and which the route
        # correctly refuses 422 naming both the missing field and the forbidden one. The card
        # itself had already appeared in 12s; only the decision was malformed.
        {"allow": True},
    )
    show("POST decide allow", code, body)
    if code >= 300:
        return f"FAIL — could not decide the card: {body}"

    cleared = wait_for(
        "card left the pending list",
        lambda: not [x for x in pending() if x["id"] == req["id"]],
    )
    return "PASS — card raised and allowed" if cleared else "FAIL — card stayed pending"


if __name__ == "__main__":
    p = ensure_project()
    r = ensure_runner(p)
    a = ensure_agent(p, "asker", r)
    print(f"project={p} runner={r} agent=asker ({a})\n")

    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    results = []
    if which in ("13", "both"):
        results.append(("row 13 questions", row13(p, "asker")))
    if which in ("14", "both"):
        results.append(("row 14 permissions", row14(p, "asker")))

    print("\n" + "=" * 60)
    for name, verdict in results:
        print(f"{name:<22} {verdict}")
    print(f"project under test: {PROJECT_NAME} ({p})")
