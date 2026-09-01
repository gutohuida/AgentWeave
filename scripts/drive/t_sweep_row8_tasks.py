"""Row 8 of the coverage matrix — TASKS, driven against a live Hub.

The row's representative path (`SURVEY.md:29`): *CRUD, board(s), transitions (declared machine),
dependencies + gate, integrations, divergences*.

`SURVEY.md` calls this the most carefully built subsystem in the Hub, and reading
`hub/hub/task_transitions.py` agrees: the map is declared once, every edge names the actor kinds
allowed to take it, the two gates are called from *inside* `apply_transition` so no caller can
route around them, and `refusal_detail` is written for a reader who has to correct itself. So the
uninteresting question is whether a legal transition works. The interesting ones are:

  (a) does EVERY illegal edge refuse in a sentence that names what would be legal from here — all
      50 of the operator's, not the two an example would pick;
  (b) does the map the product PUBLISHES to its own client (`GET /transitions/allowed`) agree,
      edge for edge, with the map it ENFORCES — a client holding a second copy is how a board
      offers a control the server refuses;
  (c) what does the board say about a task the dependency gate is holding — is the reason on the
      card, or only in the 409;
  (d) can a refusal leave anything behind.

Legs:

  1. ENTRY STATUSES — create a task in all nine statuses. Two are entry points; the other seven
     must refuse and name the two.
  2. THE LEGAL MAP, WALKED — every declared operator edge, taken for real, so leg 3's refusals are
     read against a positive control taken in the same minute against the same code.
  3. THE ILLEGAL MATRIX — all 50 non-edges for the operator. Each must 409, name the current
     status, and name EXACTLY the set the machine would allow. Then assert the task did not move.
  4. PUBLISHED vs ENFORCED — `GET /transitions/allowed` compared set-for-set with what legs 2 and
     3 measured, in both directions.
  5. THE DEPENDENCY GATE — the refusal and its structure, `rejected` reported apart from `unmet`,
     self/missing/cycle/duplicate on the declare route, 404 on removing an edge that is not there,
     and the `blocked -> in_progress` exemption that design D5 reversed a shipped rule to get.
  6. THE BOARD — `dependency_state` on a gated card, the `edges` list, the boards picker's
     `outstanding` count, and cross-project isolation.
  7. SQLITE CROSS-CHECK — every task and every transition row read straight out of the database
     read-only and compared with what the routes reported.

Operator surface only: no agent turn, no model, nothing spawned. Every task it creates is deleted
on the way out.

Run: AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=... py -3.11 scripts/drive/t_sweep_row8_tasks.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

FORBIDDEN = {"proj-5e960453", "proj-18e5d4e0"}
if P in FORBIDDEN or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)

DB = os.environ.get("AW_DB", "C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db")
PROJ = f"/projects/{P}"
TAG = os.environ.get("AW_RUN_TAG", "row8")

FAILURES = []
CREATED = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append((label, str(detail)))
    return ok


def note(label, detail=""):
    print(f"  NOTE  {label}" + (f"  — {detail}" if detail else ""))


# --------------------------------------------------------------------------------------
# The machine, restated here rather than imported.
#
# `hub/hub/task_transitions.py` is the product's declaration; a harness that imported it would
# assert the product against itself and could not catch a wrong edge. This is an independent
# transcription, read off the module by hand on 2026-09-01 — a disagreement between the two is a
# finding either way round.
# --------------------------------------------------------------------------------------

ENTRY = {"pending", "assigned"}

OPERATOR_EDGES = {
    "pending": {"assigned", "in_progress", "rejected"},
    "assigned": {"in_progress", "pending", "rejected"},
    "in_progress": {"completed", "assigned", "blocked", "rejected"},
    "blocked": {"in_progress", "assigned", "rejected"},
    "completed": {"under_review", "rejected"},
    "under_review": {"approved", "revision_needed", "rejected"},
    "revision_needed": {"in_progress", "rejected"},
    "approved": {"revision_needed"},
    "rejected": {"pending"},
}
STATUSES = sorted(OPERATOR_EDGES)

#: How to reach each status from a freshly created task, operator-only, using declared edges.
WALK = {
    "pending": [],
    "assigned": ["assigned"],
    "in_progress": ["in_progress"],
    "blocked": ["in_progress", "blocked"],
    "completed": ["in_progress", "completed"],
    "under_review": ["in_progress", "completed", "under_review"],
    "revision_needed": ["in_progress", "completed", "under_review", "revision_needed"],
    "approved": ["in_progress", "completed", "under_review", "approved"],
    "rejected": ["rejected"],
}


def make(title, **kw):
    code, body = api("POST", f"{PROJ}/tasks", {"title": title, **kw})
    if code == 201:
        CREATED.append(body["id"])
        return body
    return {"_code": code, "_body": body}


def patch(task_id, body):
    """A PATCH that reaches the transition machine.

    `blocked_reason` is filled in whenever the target is `blocked`, because `TaskUpdate`'s model
    validator refuses the body *before* the endpoint runs otherwise — which is finding F201, and is
    measured deliberately in LEG 3b rather than tripped over in every other leg.
    """
    if body.get("status") == "blocked" and "blocked_reason" not in body:
        body = {**body, "blocked_reason": "row8 probe"}
    return api("PATCH", f"{PROJ}/tasks/{task_id}", body)


def get(task_id):
    _, body = api("GET", f"{PROJ}/tasks/{task_id}")
    return body if isinstance(body, dict) else {}


def status_of(task_id):
    return get(task_id).get("status")


def transition_count(task_id):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute(
            "select count(*) from task_transitions where task_id = ?", (task_id,)
        ).fetchone()[0]
    finally:
        con.close()


def detail_text(body):
    """The refusal sentence, whichever shape the handler used.

    `main.py:406` sends `refusal.to_dict()` as `detail` for the two gates and a bare string for
    everything else, so a reader has to handle both — which is itself worth recording.
    """
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, dict):
            return d.get("message", "") or str(d)
        return str(d)
    return str(body)


def walk_to(status, title):
    """A fresh task at `status`, reached only through declared edges."""
    task = make(title, status="pending")
    if "_code" in task:
        return None
    for step in WALK[status]:
        code, body = patch(task["id"], {"status": step})
        if code != 200:
            note(f"walk to {status} broke at -> {step}", f"[{code}] {detail_text(body)[:160]}")
            return None
    return task


try:
    # ==================================================================================
    print()
    print("LEG 1 — entry statuses: a lifecycle that can be entered anywhere is not a lifecycle")
    print("=" * 78)

    for st in STATUSES:
        code, body = api("POST", f"{PROJ}/tasks", {"title": f"row8 entry {st} {TAG}", "status": st})
        if st in ENTRY:
            check(
                f"create at {st!r} is accepted", code == 201, f"[{code}] {detail_text(body)[:120]}"
            )
            if code == 201:
                CREATED.append(body["id"])
                check(
                    f"create at {st!r} stores {st!r}",
                    body.get("status") == st,
                    body.get("status"),
                )
        else:
            ok = check(f"create at {st!r} is refused", code in (409, 422), f"[{code}]")
            if ok:
                text = detail_text(body)
                check(
                    f"  the {st!r} refusal names both entry statuses",
                    all(e in text for e in sorted(ENTRY)),
                    text[:170],
                )
                if code == 422:
                    # `TaskCreate.validate_status` refuses first, so `InvalidEntryStatusError`'s
                    # declared 409 and its "reached by transitioning" sentence never reach a client
                    # on this route. Belt and braces rather than a defect — but the belt is the one
                    # the operator sees, and it is the shorter sentence.
                    note(
                        f"  create at {st!r} is refused by the SCHEMA (422), not the service (409)"
                    )

    code, body = api("POST", f"{PROJ}/tasks", {"title": f"row8 bogus {TAG}", "status": "banana"})
    check("create at an unknown status is refused", code in (409, 422), f"[{code}]")
    note("  unknown-status refusal", detail_text(body)[:200])

    # ==================================================================================
    print()
    print("LEG 2 — every declared operator edge, walked for real")
    print("=" * 78)

    walked = {}
    for frm in STATUSES:
        for to in sorted(OPERATOR_EDGES[frm]):
            task = walk_to(frm, f"row8 edge {frm}->{to} {TAG}")
            if task is None:
                check(f"{frm} -> {to}", False, "could not reach the from-status")
                continue
            code, body = patch(task["id"], {"status": to})
            ok = check(
                f"{frm} -> {to} is accepted", code == 200, f"[{code}] {detail_text(body)[:130]}"
            )
            if ok:
                check(
                    f"  and the row now reads {to!r}", body.get("status") == to, body.get("status")
                )
                walked.setdefault(frm, set()).add(to)

    # ==================================================================================
    print()
    print("LEG 3 — the illegal matrix: 50 non-edges, each refused with the map in the sentence")
    print("=" * 78)

    refused_named = {}
    for frm in STATUSES:
        illegal = [s for s in STATUSES if s != frm and s not in OPERATOR_EDGES[frm]]
        task = walk_to(frm, f"row8 illegal-from-{frm} {TAG}")
        if task is None:
            check(f"a task at {frm!r} for the illegal sweep", False, "could not reach it")
            continue
        named_here = None
        for to in illegal:
            code, body = patch(task["id"], {"status": to})
            text = detail_text(body)
            ok = check(f"{frm} -> {to} is refused 409", code == 409, f"[{code}] {text[:130]}")
            if not ok:
                continue
            check(f"  the {frm}->{to} refusal names the current status", frm in text, text[:160])
            # The sentence's own list of what IS reachable, parsed back out.
            if "available transitions are:" in text:
                listed = {
                    s.strip().strip(".").strip("'")
                    for s in text.split("available transitions are:")[1].split(",")
                }
                listed = {s for s in listed if s}
                check(
                    f"  the {frm}->{to} refusal names exactly the legal set",
                    listed == OPERATOR_EDGES[frm],
                    f"named {sorted(listed)} vs {sorted(OPERATOR_EDGES[frm])}",
                )
                named_here = listed
            else:
                check(
                    f"  the {frm}->{to} refusal names what would be legal",
                    False,
                    text[:170],
                )
        if named_here is not None:
            refused_named[frm] = named_here
        check(
            f"a task at {frm!r} is unmoved by {len(illegal)} refusals",
            status_of(task["id"]) == frm,
            status_of(task["id"]),
        )

    # A restatement of the current status is a no-op that records nothing (design D7).
    noop = walk_to("in_progress", f"row8 noop {TAG}")
    if noop:
        # Counted out of the table, because NO ROUTE READS A TASK'S TRANSITION HISTORY — see leg 8.
        before = transition_count(noop["id"])
        code, _ = patch(noop["id"], {"status": "in_progress"})
        after = transition_count(noop["id"])
        check("restating the current status is accepted", code == 200, f"[{code}]")
        check(
            "restating the current status records no transition",
            before == after,
            f"{before}->{after}",
        )

    # ==================================================================================
    print()
    print("LEG 3b — the refusal an operator gets for an ILLEGAL move to 'blocked'")
    print("=" * 78)
    print("  task-lifecycle-governance: 'A refusal MUST name the task's current status and the")
    print("  statuses reachable from it' — and the named scenario 'Work not yet started cannot be")
    print("  waiting' requires 'the refusal names what is reachable instead'.")
    print()

    for frm in [s for s in STATUSES if s != "blocked" and "blocked" not in OPERATOR_EDGES[s]]:
        task = walk_to(frm, f"row8 blocked-refusal-{frm} {TAG}")
        if task is None:
            check(f"a task at {frm!r} for the blocked-refusal leg", False, "could not reach it")
            continue
        # Exactly what an operator or a client sends: the status they want, and nothing else.
        code, body = api("PATCH", f"{PROJ}/tasks/{task['id']}", {"status": "blocked"})
        text = detail_text(body)
        check(
            f"{frm} -> blocked (no reason) is refused as ILLEGAL, not as malformed",
            code == 409,
            f"[{code}] {text[:150]}",
        )
        check(
            f"  the {frm} -> blocked refusal names what is reachable instead",
            any(t in text for t in sorted(OPERATOR_EDGES[frm])) and frm in text,
            text[:170],
        )
        # And the second attempt, with the field the first refusal demanded.
        code2, body2 = api(
            "PATCH", f"{PROJ}/tasks/{task['id']}", {"status": "blocked", "blocked_reason": "x"}
        )
        note(
            f"  {frm} -> blocked WITH a reason",
            f"[{code2}] {detail_text(body2)[:130]}",
        )
        check(
            f"  {frm} is unmoved by both attempts",
            status_of(task["id"]) == frm,
            status_of(task["id"]),
        )

    # The legal edge is unaffected either way, which is what makes this a message defect and not a
    # behaviour one.
    legal = walk_to("in_progress", f"row8 blocked-legal {TAG}")
    if legal:
        code, body = api("PATCH", f"{PROJ}/tasks/{legal['id']}", {"status": "blocked"})
        check(
            "in_progress -> blocked without a reason is refused (R5: a hand-set block says what for)",
            code == 422,
            f"[{code}]",
        )
        code, body = api(
            "PATCH",
            f"{PROJ}/tasks/{legal['id']}",
            {"status": "blocked", "blocked_reason": "waiting on the operator"},
        )
        check("in_progress -> blocked WITH a reason is accepted", code == 200, f"[{code}]")
        check(
            "  and the reason is stored on the task",
            (body or {}).get("blocked_reason") == "waiting on the operator",
            (body or {}).get("blocked_reason"),
        )

    # ==================================================================================
    print()
    print("LEG 4 — the map the product publishes vs the map it enforces")
    print("=" * 78)

    code, published = api("GET", f"{PROJ}/tasks/transitions/allowed")
    if not check(
        "GET /tasks/transitions/allowed answers", code == 200, f"[{code}] {str(published)[:200]}"
    ):
        published = {}
    check(
        "  and says which actor it is for",
        isinstance(published, dict) and published.get("actor_kind") == "operator",
        str(published)[:120] if isinstance(published, dict) else str(published)[:120],
    )
    pub_map = (published.get("transitions") or {}) if isinstance(published, dict) else {}
    check(
        "  and publishes a row for every status the machine knows",
        set(pub_map) == set(STATUSES),
        f"{sorted(pub_map)} vs {STATUSES}",
    )
    for frm in STATUSES:
        check(
            f"published[{frm!r}] matches the declared map",
            set(pub_map.get(frm, [])) == OPERATOR_EDGES[frm],
            f"{sorted(pub_map.get(frm, []))} vs {sorted(OPERATOR_EDGES[frm])}",
        )
        if frm in walked:
            check(
                f"published[{frm!r}] matches what actually succeeded",
                set(pub_map.get(frm, [])) == walked[frm],
                f"{sorted(pub_map.get(frm, []))} vs {sorted(walked[frm])}",
            )
        if frm in refused_named:
            check(
                f"published[{frm!r}] matches what the refusals named",
                set(pub_map.get(frm, [])) == refused_named[frm],
                f"{sorted(pub_map.get(frm, []))} vs {sorted(refused_named[frm])}",
            )

    # ==================================================================================
    print()
    print("LEG 5 — the dependency gate")
    print("=" * 78)

    pre = make(f"row8 prerequisite {TAG}")
    dep = make(f"row8 dependent {TAG}")
    code, body = api("POST", f"{PROJ}/tasks/{dep['id']}/dependencies", {"depends_on": pre["id"]})
    check("declaring a dependency is accepted", code == 201, f"[{code}] {detail_text(body)[:140]}")

    code, body = patch(dep["id"], {"status": "in_progress"})
    ok = check(
        "pending -> in_progress is gated by an unapproved prerequisite", code == 409, f"[{code}]"
    )
    if ok:
        d = body.get("detail") if isinstance(body, dict) else None
        check(
            "  the gate refusal is structured, not only prose",
            isinstance(d, dict) and d.get("code") == "dependency_unmet",
            str(d)[:180],
        )
        if isinstance(d, dict):
            check(
                "  it names the prerequisite by id",
                any(u.get("id") == pre["id"] for u in d.get("unmet", [])),
                str(d.get("unmet"))[:180],
            )
            check(
                "  it names the prerequisite's current status",
                any(u.get("status") == "pending" for u in d.get("unmet", [])),
                str(d.get("unmet"))[:180],
            )
        check(
            "  and it carries a sentence too",
            "not yet approved" in detail_text(body),
            detail_text(body)[:170],
        )

    code, _ = patch(dep["id"], {"status": "assigned"})
    check("assigning ahead of the prerequisite is NOT gated", code == 200, f"[{code}]")
    code, _ = patch(dep["id"], {"status": "rejected"})
    check("rejecting a gated task is NOT gated", code == 200, f"[{code}]")
    patch(dep["id"], {"status": "pending"})

    # A rejected prerequisite is reported apart from an unmet one, because the remedy differs.
    patch(pre["id"], {"status": "rejected"})
    code, body = patch(dep["id"], {"status": "in_progress"})
    d = body.get("detail") if isinstance(body, dict) else {}
    check("a rejected prerequisite still gates", code == 409, f"[{code}]")
    check(
        "  and is reported under 'rejected', not 'unmet'",
        isinstance(d, dict) and any(r.get("id") == pre["id"] for r in d.get("rejected", [])),
        str(d)[:200],
    )
    check(
        "  and the sentence names a different remedy than waiting",
        "reopen" in detail_text(body),
        detail_text(body)[:180],
    )
    patch(pre["id"], {"status": "pending"})

    # Approve the prerequisite and the gate opens.
    for step in WALK["approved"]:
        patch(pre["id"], {"status": step})
    check(
        "the prerequisite reached approved",
        status_of(pre["id"]) == "approved",
        status_of(pre["id"]),
    )
    code, _ = patch(dep["id"], {"status": "in_progress"})
    check("an approved prerequisite opens the gate", code == 200, f"[{code}]")

    # THE D5 EXEMPTION: a dependency declared while a task waits must not stop it resuming.
    resume = make(f"row8 resume {TAG}")
    patch(resume["id"], {"status": "in_progress"})
    patch(resume["id"], {"status": "blocked"})
    late = make(f"row8 late-prerequisite {TAG}")
    code, _ = api("POST", f"{PROJ}/tasks/{resume['id']}/dependencies", {"depends_on": late["id"]})
    check(
        "a dependency can be declared on a task that is already waiting", code == 201, f"[{code}]"
    )
    code, body = patch(resume["id"], {"status": "in_progress"})
    check(
        "blocked -> in_progress is EXEMPT from the gate (design D5)",
        code == 200,
        f"[{code}] {detail_text(body)[:160]}",
    )
    check(
        "  and the task is flagged rather than stopped",
        get(resume["id"]).get("dependency_state") == "running_on_regressed",
        get(resume["id"]).get("dependency_state"),
    )
    # The mirror: the same regression at the edge that BEGINS work is still refused.
    fresh = make(f"row8 fresh-vs-late {TAG}")
    api("POST", f"{PROJ}/tasks/{fresh['id']}/dependencies", {"depends_on": late["id"]})
    code, _ = patch(fresh["id"], {"status": "in_progress"})
    check(
        "  while pending -> in_progress with the same prerequisite is still refused",
        code == 409,
        f"[{code}]",
    )

    # The declare route's own refusals.
    code, body = api("POST", f"{PROJ}/tasks/{dep['id']}/dependencies", {"depends_on": dep["id"]})
    check("a task cannot depend on itself", code == 400, f"[{code}]")
    check("  and the refusal says so", "itself" in detail_text(body), detail_text(body)[:140])
    code, body = api("POST", f"{PROJ}/tasks/{dep['id']}/dependencies", {"depends_on": "task-nope"})
    check("a missing prerequisite is refused 404", code == 404, f"[{code}]")
    check(
        "  and the refusal names both ids", dep["id"] in detail_text(body), detail_text(body)[:170]
    )
    code, body = api("POST", f"{PROJ}/tasks/{pre['id']}/dependencies", {"depends_on": dep["id"]})
    check("a cycle is refused 409", code == 409, f"[{code}]")
    check(
        "  and the refusal explains the forever",
        "forever" in detail_text(body),
        detail_text(body)[:180],
    )
    code, body = api("POST", f"{PROJ}/tasks/{dep['id']}/dependencies", {"depends_on": pre["id"]})
    check("re-declaring an existing edge is a 201 restatement", code == 201, f"[{code}]")
    check("  and says it was a duplicate", str(body).find("duplicate") >= 0, str(body)[:140])
    code, _ = api("DELETE", f"{PROJ}/tasks/{dep['id']}/dependencies/task-nope")
    check("removing an edge that is not there is 404", code == 404, f"[{code}]")
    code, _ = api("DELETE", f"{PROJ}/tasks/{dep['id']}/dependencies/{pre['id']}")
    check("removing a real edge is 204", code == 204, f"[{code}]")

    # ==================================================================================
    print()
    print("LEG 6 — the board, the picker, and isolation")
    print("=" * 78)

    gated = make(f"row8 board-gated {TAG}")
    blocker = make(f"row8 board-blocker {TAG}")
    api("POST", f"{PROJ}/tasks/{gated['id']}/dependencies", {"depends_on": blocker["id"]})

    code, board = api("GET", f"{PROJ}/tasks/board")
    check("GET /tasks/board answers", code == 200, f"[{code}]")
    cards = {t["id"]: t for t in (board.get("tasks") or [])} if isinstance(board, dict) else {}
    check("the hand-made board carries the gated card", gated["id"] in cards, sorted(cards)[:4])
    if gated["id"] in cards:
        card = cards[gated["id"]]
        check(
            "the board card says WHY it cannot start (dependency_state)",
            card.get("dependency_state") == "gated",
            card.get("dependency_state"),
        )
        check(
            "the board card names the prerequisite it is waiting on",
            any(p.get("id") == blocker["id"] for p in (card.get("prerequisites") or [])),
            str(card.get("prerequisites"))[:180],
        )
    edges = {(e["task_id"], e["depends_on_task_id"]) for e in (board.get("edges") or [])}
    check(
        "the board's flat edge list carries the edge",
        (gated["id"], blocker["id"]) in edges,
        str(sorted(edges))[:200],
    )
    check(
        "every board edge has both ends on the board",
        all(a in cards and b in cards for a, b in edges),
        str([(a, b) for a, b in edges if a not in cards or b not in cards])[:200],
    )

    code, boards = api("GET", f"{PROJ}/tasks/boards")
    check("GET /tasks/boards answers", code == 200, f"[{code}]")
    rows = (boards.get("boards") or []) if isinstance(boards, dict) else []
    nodoc = [b for b in rows if b.get("spec_document_id") is None]
    check("the picker has a 'no document' board", len(nodoc) == 1, str(rows)[:200])
    if nodoc:
        live = [t for t in cards.values() if t["status"] not in ("approved", "rejected")]
        check(
            "its outstanding count excludes the terminal statuses",
            nodoc[0].get("outstanding") == len(live),
            f"picker {nodoc[0].get('outstanding')} vs board {len(live)}",
        )
        check(
            "its total matches the board",
            nodoc[0].get("total") == len(cards),
            f"picker {nodoc[0].get('total')} vs board {len(cards)}",
        )

    # Isolation: another project's task id must not be reachable through this project's routes.
    _, projects = api("GET", "/projects")
    other = next(
        (p["id"] for p in (projects if isinstance(projects, list) else []) if p["id"] != P),
        None,
    )
    if other:
        _, other_tasks = api("GET", f"/projects/{other}/tasks")
        foreign = (
            (other_tasks or [None])[0] if isinstance(other_tasks, list) and other_tasks else None
        )
        if foreign:
            code, _ = api("GET", f"{PROJ}/tasks/{foreign['id']}")
            check("a foreign task id is 404 on this project's GET", code == 404, f"[{code}]")
            code, _ = patch(foreign["id"], {"status": "in_progress"})
            check("a foreign task id is 404 on this project's PATCH", code == 404, f"[{code}]")
            code, body = api(
                "POST", f"{PROJ}/tasks/{gated['id']}/dependencies", {"depends_on": foreign["id"]}
            )
            check(
                "a cross-project dependency is refused",
                code == 404,
                f"[{code}] {detail_text(body)[:140]}",
            )
        else:
            note("no foreign task available for the isolation leg")

    # ==================================================================================
    print()
    print("LEG 7 — read the database directly and compare")
    print("=" * 78)

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = {r["id"]: r for r in con.execute("select * from tasks where project_id = ?", (P,))}
    # Paged deliberately — the unpaged call is finding F202 and is measured on its own in LEG 7b.
    listed = {}
    for page in range(0, 20):
        _, chunk = api("GET", f"{PROJ}/tasks?limit=1000&offset={page * 1000}")
        chunk = chunk if isinstance(chunk, list) else []
        listed.update({t["id"]: t for t in chunk})
        if len(chunk) < 1000:
            break
    check(
        "the route reports every task the table holds, when paged to the end",
        set(rows) == set(listed),
        f"table-only {sorted(set(rows) - set(listed))[:3]} route-only {sorted(set(listed) - set(rows))[:3]}",
    )

    # ------------------------------------------------------------------------------
    print()
    print("LEG 7b — does GET /tasks say when it truncated? (what MCP list_tasks() sends)")
    print("-" * 78)
    total = len(rows)
    _, unpaged = api("GET", f"{PROJ}/tasks")
    unpaged = unpaged if isinstance(unpaged, list) else []
    note(f"table holds {total}; the unfiltered route returned {len(unpaged)}")
    if total > 100:
        check(
            "the default page carries every task, or says it did not",
            len(unpaged) == total,
            f"{len(unpaged)} of {total}, and the body is a bare {type(unpaged).__name__} with no "
            "total, no has_more and no next",
        )
        newest = make(f"row8 FIND-ME {TAG}")
        _, again = api("GET", f"{PROJ}/tasks")
        check(
            "a task created one second ago is in the default page",
            any(t["id"] == newest["id"] for t in (again if isinstance(again, list) else [])),
            "ordered by created_at ASC and cut at 100, so the NEWEST work is what is dropped",
        )
        check(
            "  (contrast) the same task is reachable by id",
            api("GET", f"{PROJ}/tasks/{newest['id']}")[0] == 200,
        )
        _, filtered = api("GET", f"{PROJ}/tasks?agent={os.environ.get('AGENT_A', '')}")
        note(
            "  the ?agent= filter the MCP tool DOES offer narrows below the cut",
            f"{len(filtered) if isinstance(filtered, list) else filtered} rows",
        )
        # The board over the same table has no limit at all, so the two disagree.
        _, bd = api("GET", f"{PROJ}/tasks/board")
        check(
            "GET /tasks and GET /tasks/board agree about how many tasks exist",
            len(bd.get("tasks") or []) == len(unpaged),
            f"board {len(bd.get('tasks') or [])} vs list {len(unpaged)}",
        )
    else:
        note("fewer than 101 tasks in this project — LEG 7b needs more to bite", total)
    mismatch = [
        (tid, rows[tid]["status"], listed[tid]["status"])
        for tid in set(rows) & set(listed)
        if rows[tid]["status"] != listed[tid]["status"]
    ]
    check("every reported status matches its row", not mismatch, str(mismatch)[:200])

    trs = list(
        con.execute("select * from task_transitions where project_id = ? order by created_at", (P,))
    )
    check("the sweep recorded transitions", len(trs) > 0, len(trs))
    bad_actor = [t["id"] for t in trs if t["actor_kind"] != "operator"]
    check(
        "every transition this sweep made is attributed to the operator",
        not bad_actor,
        str(bad_actor)[:160],
    )
    bad_agent = [t["id"] for t in trs if t["actor_agent"] is not None or t["run_id"] is not None]
    check("no operator transition carries a run or an agent", not bad_agent, str(bad_agent)[:160])
    illegal_rows = [
        (t["from_status"], t["to_status"])
        for t in trs
        if t["to_status"] not in OPERATOR_EDGES.get(t["from_status"], set())
    ]
    check(
        "EVERY recorded transition is an edge the map declares",
        not illegal_rows,
        str(sorted(set(illegal_rows)))[:220],
    )
    origins = sorted({t["origin"] for t in trs})
    check(
        "every origin is 'actor' — nothing runtime happened here",
        origins == ["actor"],
        str(origins),
    )
    stray = [t["id"] for t in trs if t["from_status"] == t["to_status"]]
    check("no transition restates a status", not stray, str(stray)[:160])
    con.close()

    # ==================================================================================
    print()
    print("LEG 8 — what the route surface does NOT offer, read off the LIVE OpenAPI")
    print("=" * 78)

    import json as _json
    import urllib.request as _u

    from aw import HUB, KEY  # noqa: E402

    _req = _u.Request(HUB.rstrip("/") + "/openapi.json")
    _req.add_header("Authorization", "Bearer " + KEY)
    with _u.urlopen(_req, timeout=30) as _r:
        spec = _json.loads(_r.read().decode("utf-8", "replace"))
    paths = spec.get("paths", {})
    task_paths = sorted(p for p in paths if "task" in p.lower())
    check("the live OpenAPI is readable", bool(task_paths), f"{len(paths)} paths")
    note(f"{len(task_paths)} task routes on this build", str(task_paths)[:520])

    # `task_transitions` is append-only and written on every accepted move, and
    # `task_transition_service.history_for()` (`:811`) exists to read it. The machine's own
    # docstring gives the reason the operator is bound by the map at all: "every recorded history
    # therefore describes a legal sequence. That is what makes the history worth reading."
    check(
        "some route reads a task's transition history",
        any("transition" in p and "{task_id}" in p for p in task_paths),
        "no route matches */tasks/{task_id}/transitions*",
    )
    check(
        "some route deletes a task",
        any("delete" in (paths[p] or {}) for p in task_paths if p.endswith("{task_id}")),
        "no DELETE on any */tasks/{task_id}",
    )

finally:
    print()
    # There is no DELETE route for a task (leg 8), so the fixture PROJECT is what gets removed.
    _, left = api("GET", f"{PROJ}/tasks")
    print(
        f"  {len(CREATED)} tasks created; {len(left) if isinstance(left, list) else left} in the project"
    )
    print("  no DELETE /tasks/{id} exists — delete the fixture project to clean up")
    print()
    print("=" * 78)
    print(f"SUMMARY — {len(FAILURES)} failure(s)")
    print("=" * 78)
    for label, detail in FAILURES:
        print(f"  FAIL {label}  {detail[:170]}")
