"""Row 7 of the coverage matrix — INBOUND QUEUE, driven against a live Hub.

The row's representative path (`SURVEY.md:28`): *per-agent durable queue, hop budget, turn
delivery cap, withdraw*. The hop budget's own chain is driven by `t_row6_hop_chain.py`, which
already exists and needs two real agent turns to produce a hop at all; this file drives everything
else, and in particular the one mechanism nothing has ever measured live — **the turn delivery
cap**. `turn_scheduler.py:129` slices the selected entries with `[:cap]`, and no drive has yet
asked whether a drain of four entries under a cap of two actually reaches the agent as two turns
of two, or whether the other half is silently dropped.

Legs:

1. settings — defaults, the four validation refusals, and what a *partial* PATCH does to the
   fields it did not mention
2. a nonexistent agent, and an invalid `state` filter (F194's shape, one router over)
3. cross-project entry ids on `release` and `withdraw`
4. withdrawal from a queue that is actually holding, and whether the withdrawn entry stays visible
5. **the turn delivery cap**, with a distinct word per entry so what reached the model can be read
   out of the agent's own output rather than inferred
6. the F114 contrast: an unbound agent must accumulate input without burning delivery attempts
7. sqlite cross-check — every entry the route reported, read straight out of
   `inbound_queue_entries` read-only, compared field by field

Every setting this file changes is restored on the way out, including on failure.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=... AGENT_A=... AGENT_B=... AGENT_UNBOUND=...
     py -3.11 scripts/drive/t_sweep_row7_queue.py
"""

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

FORBIDDEN = {"proj-5e960453", "proj-18e5d4e0"}
if P in FORBIDDEN or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)

A = os.environ["AGENT_A"]
B = os.environ["AGENT_B"]
UNBOUND = os.environ["AGENT_UNBOUND"]
DB = os.environ.get("AW_DB", "C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db")
PROJ = f"/projects/{P}"

POLL = 4
LIMIT = 45
FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append((label, str(detail)))
    return ok


def note(label, detail=""):
    print(f"  NOTE  {label}" + (f"  — {detail}" if detail else ""))


def queue(agent, state=None):
    path = f"{PROJ}/queue/{agent}" + (f"?state={state}" if state else "")
    _, body = api("GET", path)
    return body if isinstance(body, list) else []


def queued(agent):
    return [e for e in queue(agent) if e.get("state") == "queued"]


def status(agent):
    _, body = api("GET", f"{PROJ}/queue/{agent}/status")
    return body if isinstance(body, dict) else {}


def roster():
    _, body = api("GET", f"{PROJ}/agents")
    return {r["name"]: r for r in (body if isinstance(body, list) else [])}


def wait_idle(agents, limit=LIMIT):
    for _ in range(limit):
        rows = roster()
        if all((rows.get(a) or {}).get("status") != "running" for a in agents):
            return True
        time.sleep(POLL)
    return False


def wait_until(label, fn, limit=LIMIT):
    for i in range(limit):
        got = fn()
        if got:
            print(f"    {label} after ~{i * POLL}s")
            return got
        time.sleep(POLL)
    print(f"    TIMEOUT waiting for {label} (~{limit * POLL}s)")
    return None


def settle(agents):
    """Row 5's first lesson: leave nothing running and nothing queued before asserting.

    Copied from `t_sweep_row6_conversations.py:105`, which is where the lesson was paid for.
    """
    for _ in range(30):
        _, qs = api("GET", f"{PROJ}/questions?status=pending")
        rows = (
            qs
            if isinstance(qs, list)
            else (qs.get("questions", []) if isinstance(qs, dict) else [])
        )
        for q in rows:
            api("POST", f"{PROJ}/questions/{q['id']}/decline", {"reason": "row7 harness settling"})
        for agent in agents:
            api("POST", f"{PROJ}/agent/{agent}/stop")
        current = roster()
        if all((current.get(a) or {}).get("status") != "running" for a in agents):
            for agent in agents:
                for e in queued(agent):
                    api("DELETE", f"{PROJ}/queue/entries/{e['id']}")
            return True
        time.sleep(3)
    return False


def db_entries():
    """Read the queue table outside the product. Read-only URI; the Hub owns the writes."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, agent, state, hop_depth, delivery_attempts, abandoned_reason,"
            " delivered_in_run_id, content, sequence"
            " FROM inbound_queue_entries WHERE project_id = ? ORDER BY sequence",
            (P,),
        ).fetchall()
        return {r["id"]: dict(r) for r in rows}
    finally:
        con.close()


def run_output(agent, run_id):
    """Everything the agent emitted on one run. `run_id` is a column on the output rows."""
    _, body = api("GET", f"{PROJ}/agents/{agent}/output?limit=500")
    rows = body if isinstance(body, list) else body.get("outputs") or []
    return "\n".join(str(r.get("content") or "") for r in rows if r.get("run_id") == run_id)


_, ORIGINAL = api("GET", f"{PROJ}/queue/settings")
ORIGINAL = dict(ORIGINAL) if isinstance(ORIGINAL, dict) else {}
print(f"queue settings on entry: {ORIGINAL}")


def restore():
    if ORIGINAL:
        code, _ = api("PATCH", f"{PROJ}/queue/settings", ORIGINAL)
        print(f"  restored queue settings -> {code}  {ORIGINAL}")


settle([A, B, UNBOUND])

try:
    print()
    print("=" * 78)
    print("LEG 1 — queue settings: defaults, refusals, and what a partial PATCH costs")
    print("=" * 78)
    check(
        "GET /queue/settings answers with all four fields",
        set(ORIGINAL) == {"hop_budget", "turn_delivery_cap", "agent_budget", "allow_agent_jobs"},
        str(sorted(ORIGINAL)),
    )
    for label, body in (
        ("hop_budget 0", {**ORIGINAL, "hop_budget": 0}),
        ("hop_budget -1", {**ORIGINAL, "hop_budget": -1}),
        ("turn_delivery_cap 0", {**ORIGINAL, "turn_delivery_cap": 0}),
        ("agent_budget -5", {**ORIGINAL, "agent_budget": -5}),
    ):
        code, out = api("PATCH", f"{PROJ}/queue/settings", body)
        text = str(out)
        check(f"PATCH settings refuses {label}", code in (400, 422), f"{code} {text[:120]}")
        check(
            f"  ...and the refusal for {label} says what WOULD be accepted",
            "greater than or equal" in text or "ge=" in text or ">=" in text,
            text[:160],
        )

    # A PATCH that names only some fields. `QueueSettings` gives `agent_budget` a default of 8 and
    # `allow_agent_jobs` a default of False, so a body that omits them is *valid* — the question is
    # what happens to the values already stored.
    api(
        "PATCH",
        f"{PROJ}/queue/settings",
        {**ORIGINAL, "agent_budget": 25, "allow_agent_jobs": True},
    )
    _, before = api("GET", f"{PROJ}/queue/settings")
    print(f"    stored before the partial PATCH: {before}")
    code, after = api(
        "PATCH",
        f"{PROJ}/queue/settings",
        {
            "hop_budget": before.get("hop_budget"),
            "turn_delivery_cap": before.get("turn_delivery_cap"),
        },
    )
    _, reread = api("GET", f"{PROJ}/queue/settings")
    print(f"    PATCH {{hop_budget, turn_delivery_cap}} -> {code}; stored now: {reread}")
    check(
        "a PATCH that omits agent_budget leaves it alone",
        reread.get("agent_budget") == 25,
        f"25 -> {reread.get('agent_budget')}",
    )
    check(
        "a PATCH that omits allow_agent_jobs leaves it alone",
        reread.get("allow_agent_jobs") is True,
        f"True -> {reread.get('allow_agent_jobs')}",
    )
    api("PATCH", f"{PROJ}/queue/settings", ORIGINAL)

    # The same four columns are written by `PUT /projects/{id}/settings`, whose model declares
    # `Field(ge=1, le=1000)` (`projects.py:76-78`). This route declares only `ge=1`
    # (`inbound_queue.py:48-52`). So there is a range one route accepts and the other cannot even
    # serialise — and the response model of the settings route is what turns that into a 500.
    code, _ = api("PATCH", f"{PROJ}/queue/settings", {**ORIGINAL, "hop_budget": 1001})
    print(f"    PATCH /queue/settings hop_budget=1001 -> {code}")
    settings_code, settings_body = api("GET", f"{PROJ}/settings")
    put_code, put_body = api("PUT", f"{PROJ}/settings", {"hop_budget": ORIGINAL["hop_budget"]})
    api("PATCH", f"{PROJ}/queue/settings", ORIGINAL)  # the only route that can put it back
    check(
        "the two routes over these columns agree about the accepted range",
        code in (400, 422),
        f"the queue route answered {code} to a value PUT /projects/{{id}}/settings refuses (le=1000)",
    )
    check(
        "  ...and the project settings page can still be READ afterwards",
        settings_code == 200,
        f"GET /projects/{{id}}/settings -> {settings_code} {str(settings_body)[:80]}",
    )
    check(
        "  ...and the operator can put the value back from the settings route",
        put_code == 200,
        f"PUT /projects/{{id}}/settings -> {put_code} {str(put_body)[:80]}",
    )
    _, back = api("GET", f"{PROJ}/settings")
    check(
        "the fixture is repaired", isinstance(back, dict) and "hop_budget" in back, str(back)[:100]
    )

    print()
    print("=" * 78)
    print("LEG 2 — an agent that does not exist, and a state filter that is not a state")
    print("=" * 78)
    ghost = "no-such-agent-row7"
    code, body = api("GET", f"{PROJ}/queue/{ghost}")
    print(f"    GET /queue/{ghost} -> {code} {str(body)[:120]}")
    check(
        "GET /queue/{agent} refuses an agent that does not exist",
        code == 404,
        f"{code} {str(body)[:120]}",
    )
    code, body = api("GET", f"{PROJ}/queue/{ghost}/status")
    print(f"    GET /queue/{ghost}/status -> {code} {str(body)[:160]}")
    check(
        "GET /queue/{agent}/status refuses an agent that does not exist",
        code == 404,
        f"{code} {str(body)[:140]}",
    )
    code, body = api("GET", f"{PROJ}/queue/{A}?state=bogus")
    print(f"    GET /queue/{A}?state=bogus -> {code} {str(body)[:160]}")
    check("an invalid state filter is refused", code == 400, str(code))
    check(
        "  ...and the refusal names the states that ARE valid",
        all(word in str(body) for word in ("queued", "delivered", "withdrawn")),
        str(body)[:160],
    )

    print()
    print("=" * 78)
    print("LEG 3 — an entry id from another project")
    print("=" * 78)
    code, other = api(
        "POST", f"{PROJ}/agent/trigger", {"agent": UNBOUND, "message": "cross-project probe"}
    )
    foreign_entry = other.get("queue_entry_id") if isinstance(other, dict) else None
    print(f"    parked an entry on the unbound agent: {foreign_entry} ({other.get('status')!r})")
    _, projects = api("GET", "/projects")
    others = [
        x["id"]
        for x in (projects if isinstance(projects, list) else [])
        if x["id"] not in FORBIDDEN and x["id"] != P
    ]
    if foreign_entry and others:
        victim = others[0]
        code, body = api("DELETE", f"/projects/{victim}/queue/entries/{foreign_entry}")
        print(f"    DELETE it as project {victim} -> {code} {str(body)[:160]}")
        check("withdrawing another project's entry is refused", code >= 400, str(code))
        check(
            "  ...and the refusal does not claim the entry was delivered",
            "delivered" not in str(body).lower(),
            str(body)[:160],
        )
        code, body = api("POST", f"/projects/{victim}/queue/entries/{foreign_entry}/release")
        print(f"    RELEASE it as project {victim} -> {code} {str(body)[:160]}")
        check("releasing another project's entry is refused", code >= 400, str(code))
        check(
            "  ...and that refusal does not claim it was delivered either",
            "delivered" not in str(body).lower(),
            str(body)[:160],
        )
        still = [e for e in queue(UNBOUND) if e["id"] == foreign_entry]
        check(
            "the entry is untouched in its own project",
            bool(still) and still[0].get("state") == "queued",
            repr(still and still[0].get("state")),
        )
    else:
        note("cross-project leg skipped", f"entry={foreign_entry} others={len(others)}")

    print()
    print("=" * 78)
    print("LEG 3b — release refusals on entries the hop budget is NOT holding")
    print("=" * 78)
    if foreign_entry:
        code, body = api("POST", f"{PROJ}/queue/entries/{foreign_entry}/release")
        print(f"    release a hop-0 entry -> {code} {str(body)[:220]}")
        check("release refuses an entry inside the hop budget", code == 409, str(code))
        check(
            "  ...and says the hop budget is not what is holding it",
            "hop budget" in str(body).lower(),
            str(body)[:160],
        )
        check(
            "  ...and points at where the real reason is",
            "status" in str(body).lower(),
            str(body)[:160],
        )
    code, body = api("POST", f"{PROJ}/queue/entries/entry-doesnotexist/release")
    check("release refuses an id that does not exist", code == 409, f"{code} {str(body)[:120]}")
    code, body = api("DELETE", f"{PROJ}/queue/entries/entry-doesnotexist")
    check("withdraw refuses an id that does not exist", code == 409, f"{code} {str(body)[:120]}")

    print()
    print("=" * 78)
    print("LEG 4 — withdrawal from a queue that is actually holding")
    print("=" * 78)
    code, busy = api(
        "POST",
        f"{PROJ}/agent/trigger",
        {
            "agent": A,
            "session_mode": "new",
            "message": "Reply with only the word BUSY. Do not read or write any files.",
        },
    )
    conv = busy.get("conversation_id") if isinstance(busy, dict) else None
    print(f"    occupying {A} -> {code} status={busy.get('status')!r} conv={conv}")
    code, extra = api(
        "POST",
        f"{PROJ}/agent/trigger",
        {"agent": A, "conversation_id": conv, "message": "WITHDRAWN-MESSAGE must never be seen."},
    )
    wid = extra.get("queue_entry_id") if isinstance(extra, dict) else None
    print(f"    queued behind it: {wid} status={extra.get('status')!r}")
    if check(
        "the second message queued rather than starting",
        extra.get("status") == "queued",
        str(extra)[:140],
    ):
        st = status(A)
        check(
            "the status route counts it as waiting", st.get("waiting_count", 0) >= 1, str(st)[:140]
        )
        check(
            "  ...and names the running turn as the reason",
            "running" in str(st.get("waiting_reason") or "").lower(),
            repr(st.get("waiting_reason")),
        )
        code, out = api("DELETE", f"{PROJ}/queue/entries/{wid}")
        check("a held entry can be withdrawn", code == 200, f"{code} {str(out)[:120]}")
        rows = {e["id"]: e for e in queue(A)}
        check(
            "the withdrawn entry is still listed",
            wid in rows,
            "it vanished from GET /queue/{agent}",
        )
        check(
            "  ...in state 'withdrawn', never delivered",
            rows.get(wid, {}).get("state") == "withdrawn"
            and rows.get(wid, {}).get("delivered_in_run_id") is None,
            str(rows.get(wid))[:160],
        )
        check(
            "  ...and an operator withdrawal carries no abandoned_reason",
            rows.get(wid, {}).get("abandoned_reason") is None,
            repr(rows.get(wid, {}).get("abandoned_reason")),
        )
        filtered = {e["id"] for e in queue(A, state="withdrawn")}
        check("?state=withdrawn finds it", wid in filtered, str(sorted(filtered))[:160])
        code, out = api("DELETE", f"{PROJ}/queue/entries/{wid}")
        check("withdrawing it twice is refused", code == 409, f"{code} {str(out)[:120]}")
        _, chat = api("GET", f"{PROJ}/agent/{A}/chat")
        tl = [
            e
            for e in (chat.get("entries") if isinstance(chat, dict) else []) or []
            if e.get("id") == wid
        ]
        print(f"    timeline row for the withdrawn entry: {str(tl)[:200]}")
        # Deliberate, and checked as such rather than asserted the other way round. The timeline
        # query keys its withdrawn branch on `abandoned_reason IS NOT NULL`
        # (`agent_chat.py:262-269`), whose comment says why: an entry the *Hub* dropped must stay
        # in the thread (F87), an entry the *operator* withdrew was never seen and its removal is
        # what they asked for. An earlier version of this file asserted the opposite and would
        # have filed a design decision as a defect.
        check(
            "an entry the operator withdrew leaves the conversation timeline",
            not tl,
            f"still present: {str(tl)[:160]}",
        )
    wait_idle([A])

    print()
    print("=" * 78)
    print("LEG 5 — the turn delivery cap, measured on a real drain")
    print("=" * 78)
    settle([A])
    code, _ = api("PATCH", f"{PROJ}/queue/settings", {**ORIGINAL, "turn_delivery_cap": 2})
    check("the turn delivery cap can be set to 2", code == 200, str(code))
    code, first = api(
        "POST",
        f"{PROJ}/agent/trigger",
        {
            "agent": A,
            "session_mode": "new",
            "message": "Reply with only the word START. Do not read or write any files.",
        },
    )
    conv = first.get("conversation_id")
    first_run = first.get("run_id")
    print(f"    occupying turn -> {code} run={first_run} conv={conv}")
    WORDS = ["ALPHA", "BETA", "GAMMA", "DELTA"]
    parked = []
    for w in WORDS:
        code, out = api(
            "POST",
            f"{PROJ}/agent/trigger",
            {
                "agent": A,
                "conversation_id": conv,
                "message": f"Reply with only the word {w}. Do not read or write any files.",
            },
        )
        parked.append((w, out.get("queue_entry_id"), out.get("status")))
    print(f"    parked behind it: {parked}")
    check(
        "all four follow-ups queued rather than starting",
        all(s == "queued" for _, _, s in parked),
        str(parked)[:200],
    )

    def all_settled():
        rows = queue(A)
        ids = {eid for _, eid, _ in parked}
        mine = [e for e in rows if e["id"] in ids]
        if len(mine) != len(ids):
            return None
        if any(e.get("state") == "queued" for e in mine):
            return None
        return mine

    drained = wait_until("all four parked entries left the queue", all_settled, limit=60)
    wait_idle([A], limit=60)
    if drained is None:
        drained = [e for e in queue(A) if e["id"] in {eid for _, eid, _ in parked}]
    groups = {}
    for e in drained:
        groups.setdefault(e.get("delivered_in_run_id"), []).append(e)
    for rid, members in groups.items():
        words = [w for w, eid, _ in parked if any(m["id"] == eid for m in members)]
        print(f"    run {rid}: {len(members)} entries {words}")
    check(
        "every entry was delivered rather than dropped",
        all(e.get("state") == "delivered" for e in drained),
        str([(e["id"], e.get("state"), e.get("abandoned_reason")) for e in drained])[:240],
    )
    check(
        "no run carried more entries than the cap allows",
        all(len(m) <= 2 for rid, m in groups.items() if rid),
        str({rid: len(m) for rid, m in groups.items()}),
    )
    check(
        "the cap actually split the drain into more than one turn",
        len([rid for rid in groups if rid]) >= 2,
        str({rid: len(m) for rid, m in groups.items()}),
    )
    # What reached the model, read out of its own output rather than inferred from the grouping.
    for rid, members in groups.items():
        if not rid or len(members) < 2:
            continue
        text = run_output(A, rid).upper()
        words = [w for w, eid, _ in parked if any(m["id"] == eid for m in members)]
        seen = [w for w in words if w in text]
        print(f"    run {rid} output mentions {seen} of {words}")
        check(
            f"both entries batched into run {rid} reached the agent",
            len(seen) == len(words),
            f"saw {seen}, batched {words}",
        )
    api("PATCH", f"{PROJ}/queue/settings", ORIGINAL)

    print()
    print("=" * 78)
    print("LEG 6 — F114's contrast: an unbound agent accumulates, it does not lose")
    print("=" * 78)
    settle([UNBOUND])
    ids = []
    for i in range(4):
        code, out = api(
            "POST", f"{PROJ}/agent/trigger", {"agent": UNBOUND, "message": f"unbound probe {i}"}
        )
        ids.append(out.get("queue_entry_id") if isinstance(out, dict) else None)
        time.sleep(1)
    rows = {e["id"]: e for e in queue(UNBOUND)}
    seen = [(rows.get(i, {}).get("state"), rows.get(i, {}).get("delivery_attempts")) for i in ids]
    print(f"    after four schedules: {seen}")
    check(
        "four messages to an unbound agent are all still queued",
        all(s == "queued" for s, _ in seen),
        str(seen),
    )
    check("and none of them burned a delivery attempt", all(a == 0 for _, a in seen), str(seen))
    st = status(UNBOUND)
    print(f"    status: {st}")
    check(
        "the status route names the missing runner",
        "runner" in str(st.get("waiting_reason") or "").lower(),
        repr(st.get("waiting_reason")),
    )
    check(
        "  ...and says what would clear it",
        "bind" in str(st.get("waiting_reason") or "").lower(),
        repr(st.get("waiting_reason")),
    )

    print()
    print("=" * 78)
    print("LEG 7 — sqlite cross-check: the route against the table it reads")
    print("=" * 78)
    table = db_entries()
    mismatches = []
    checked = 0
    for agent in (A, B, UNBOUND):
        for e in queue(agent):
            row = table.get(e["id"])
            if row is None:
                mismatches.append((e["id"], "absent from inbound_queue_entries"))
                continue
            checked += 1
            for field in (
                "state",
                "hop_depth",
                "delivery_attempts",
                "abandoned_reason",
                "delivered_in_run_id",
            ):
                if (row[field] if field != "abandoned_reason" else row[field]) != e.get(field):
                    mismatches.append((e["id"], f"{field}: db={row[field]!r} api={e.get(field)!r}"))
    print(f"    compared {checked} entries against the table")
    check(
        "every field the route reports matches the row it came from",
        not mismatches,
        str(mismatches)[:300],
    )
    orphans = [
        eid
        for eid, row in table.items()
        if row["agent"] in (A, B, UNBOUND)
        and eid not in {e["id"] for agent in (A, B, UNBOUND) for e in queue(agent)}
    ]
    check("the route hides no entry the table holds", not orphans, str(orphans)[:200])

finally:
    wait_idle([A, B, UNBOUND])
    restore()
    for agent in (A, B, UNBOUND):
        for e in queued(agent):
            code, _ = api("DELETE", f"{PROJ}/queue/entries/{e['id']}")
            print(f"  drained leftover {agent} entry {e['id']} -> {code}")
    print()
    print("=" * 78)
    print(f"SUMMARY — {len(FAILURES)} failure(s)")
    print("=" * 78)
    for label, detail in FAILURES:
        print(f"  FAIL {label}  {detail[:170]}")
