"""Sweep row 6 - Conversations.

The representative path from the e2e-loop coverage matrix (`SURVEY.md:27`): list, rename,
release-task, chat history, lineage, titles (worker-generated). The routes are
`hub/hub/api/v1/agent_chat.py` - `conversations_router` (:56), `GET /agent/{agent}/conversations`
(:406), `PATCH .../conversations/{id}` (:464), `DELETE .../conversations/{id}/task` (:496),
archive/unarchive (:522/:546) and the two chat routes (:566/:645) - over `hub/hub/conversations.py`
and `hub/hub/conversation_titles.py`. Lineage has a schema behind it (migration
`0085_conversation_lineage`), so it is read straight out of sqlite rather than from a route that
does not expose it at all.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_sweep_row6_conversations.py <pid> <other>

Two things follow the row-5 lesson that a self-report is evidence about the reporter:

  * `lineage_id` is **not** a field of `ConversationResponse`, so every lineage claim here is
    measured against the sqlite file read-only. There is no route to ask.
  * a generated title is judged by the `conversations.title` column and the `conversation_titled`
    event, not by what a create response echoed back.

Set `AW_SKIP_TURN=1` for the refusal half alone; the title and lineage measurements need real
Haiku turns and are skipped with it.
"""

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

PID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AW_PROJECT", "")
if not PID:
    sys.exit("usage: t_sweep_row6_conversations.py <project-id> <other-project-id>")
OTHER = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("AW_OTHER_PROJECT", "")

TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))

A = f"/projects/{PID}"
B = f"/projects/{OTHER}" if OTHER else None
AGENT = os.environ.get("AW_AGENT", "r5runnerr6a")
ARCHIVED = os.environ.get("AW_ARCHIVED_AGENT", "r5archr6a")

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    shown = detail if len(detail) <= 300 else detail[:300] + f"... ({len(detail)} chars)"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" - {shown}" if shown else ""))


def detail_of(body):
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, list):
            return " | ".join(str(e.get("msg", e)) for e in d)
        if isinstance(d, dict):
            return str(d.get("message", d))
        if d is not None:
            return str(d)
    return str(body)


def names_what_would_work(text, *needles):
    low = (text or "").lower()
    return any(n.lower() in low for n in needles)


_COLUMNS = (
    "id",
    "project_id",
    "agent",
    "lifecycle",
    "title",
    "title_set_by_operator",
    "origin",
    "lineage_id",
    "task_id",
    "provider_session_id",
)


def db_conversation(conversation_id):
    """Read a conversation row directly. Read-only - the Hub owns this file."""
    if not conversation_id:
        return None
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        cur = con.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM conversations WHERE id = ?", (conversation_id,)
        )
        row = cur.fetchone()
    finally:
        con.close()
    if row is None:
        return None
    return dict(zip(_COLUMNS, row, strict=True))


def settle_agent(agent=AGENT):
    """Leave the agent idle with nothing pending. Row 5's lesson, at a new site."""
    for _ in range(30):
        _, qs = api("GET", f"{A}/questions?status=pending")
        if isinstance(qs, list):
            rows = qs
        elif isinstance(qs, dict):
            rows = qs.get("questions", [])
        else:
            rows = []
        for q in rows:
            api("POST", f"{A}/questions/{q['id']}/decline", {"reason": "row6 harness teardown"})
        api("POST", f"{A}/agent/{agent}/stop")
        _, agents = api("GET", f"{A}/agents")
        row = None
        if isinstance(agents, list):
            row = next((a for a in agents if a["name"] == agent), None)
        _, qstat = api("GET", f"{A}/queue/{agent}/status")
        if row and row.get("status") != "running" and not (qstat or {}).get("running"):
            _, entries = api("GET", f"{A}/queue/{agent}")
            for e in entries if isinstance(entries, list) else []:
                if e["state"] == "queued":
                    api("DELETE", f"{A}/queue/entries/{e['id']}")
            return True
        time.sleep(3)
    return False


def wait_idle(agent=AGENT, seconds=300):
    """Block until the agent has no run in progress and nothing waiting."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        _, qstat = api("GET", f"{A}/queue/{agent}/status")
        if isinstance(qstat, dict) and not qstat.get("running") and not qstat.get("waiting_count"):
            return True
        time.sleep(3)
    return False


print("=" * 78)
print(f"ROW 6 - CONVERSATIONS.  project: {PID}  other: {OTHER or '(none)'}  tag: {TAG}")
print("=" * 78)

# ------------------------------------------------------------------ 1. the two list surfaces

code, conv = api("GET", f"{A}/agent/{AGENT}/conversations")
check(
    "an agent that has never run lists its conversations rather than 404ing",
    code == 200,
    f"got {code}",
)

code, proj_conv = api("GET", f"{A}/conversations")
show("GET /conversations", code, proj_conv, limit=300)
check("the project-wide list answers", code == 200, f"got {code}")
check(
    "it carries the archived count the 'Show archived (N)' control needs",
    code == 200 and "archived_count" in proj_conv and "archived_by_agent" in proj_conv,
    str(proj_conv)[:200],
)

code, bad_life = api("GET", f"{A}/conversations?lifecycle=deleted")
check(
    "an unknown lifecycle filter is refused rather than silently ignored",
    code == 422,
    f"got {code}",
)
check(
    "and that refusal enumerates the three that would work",
    all(w in detail_of(bad_life) for w in ("open", "archived", "all")),
    detail_of(bad_life),
)

GHOST_AGENT = f"nosuchagent{TAG}"
code, ghost_list = api("GET", f"{A}/agent/{GHOST_AGENT}/conversations")
check(
    "REFUSAL SHAPE: an unknown agent's conversation list is indistinguishable from an empty one",
    not (code == 200 and ghost_list == []),
    f"got {code} {str(ghost_list)[:120]} - a typo'd agent name reads as 'no conversations yet'",
)

code, ghost_chat = api("GET", f"{A}/agent/{GHOST_AGENT}/chat")
entries_shown = len(ghost_chat.get("entries", [])) if isinstance(ghost_chat, dict) else "?"
check(
    "REFUSAL SHAPE: chat history for an agent that does not exist is answered 200 with an empty timeline",
    not (code == 200 and isinstance(ghost_chat, dict) and ghost_chat.get("entries") == []),
    f"got {code} entries={entries_shown}",
)

# ------------------------------------------------------------------ 2. refusals before any conversation

GHOST_CONV = "conv-000000000000"

code, r = api("PATCH", f"{A}/agent/{AGENT}/conversations/{GHOST_CONV}", {"title": "x"})
check("renaming a conversation that does not exist is refused", code == 404, f"got {code}")
check(
    "and that refusal says what would work",
    names_what_would_work(detail_of(r), "list", "/conversations", "start", "open a conversation"),
    detail_of(r),
)

code, r = api("DELETE", f"{A}/agent/{AGENT}/conversations/{GHOST_CONV}/task")
check(
    "releasing a task from a conversation that does not exist is refused",
    code == 404,
    f"got {code}",
)

code, r = api("GET", f"{A}/agent/{AGENT}/chat/{GHOST_CONV}")
check("chat history for a conversation that does not exist is refused", code == 404, f"got {code}")

code, r = api("POST", f"{A}/agent/{AGENT}/conversations/{GHOST_CONV}/archive")
check("archiving a conversation that does not exist is refused", code == 404, f"got {code}")

# ------------------------------------------------------------------ 3. a real conversation

code, trig = api(
    "POST",
    f"{A}/agent/trigger",
    {
        "agent": AGENT,
        "message": (
            "Reply with the single word: acknowledged. Do not use any tools. "
            f"Reference {TAG} so this thread is identifiable."
        ),
    },
)
show("POST /agent/trigger", code, trig, limit=300)
check("the first turn is accepted", code == 200, f"got {code}")
CONV = trig.get("conversation_id") if code == 200 else None
check("the accepted turn names the conversation it opened", bool(CONV), str(trig)[:200])

if not CONV:
    print("\nno conversation to drive - stopping here")
    sys.exit(1)

row = db_conversation(CONV)
check("the conversation exists in the database", bool(row), str(row))
check(
    "a new conversation founds its own lineage (migration 0085), measured in sqlite",
    bool(row) and row["lineage_id"] == CONV,
    f"lineage_id={row and row['lineage_id']} vs id={CONV}",
)
check(
    "it is named from its first message immediately - the rail never shows an identifier",
    bool(row) and bool(row["title"]),
    f"title={row and row['title']!r}",
)
check(
    "and that truncated title is NOT marked operator-set, so a titler may still upgrade it",
    bool(row) and not row["title_set_by_operator"],
    f"title_set_by_operator={row and row['title_set_by_operator']}",
)
check(
    "its origin records that the operator started it",
    bool(row) and row["origin"] == "operator",
    f"origin={row and row['origin']}",
)

code, listed = api("GET", f"{A}/agent/{AGENT}/conversations")
check(
    "the conversation appears in its agent's list",
    code == 200 and any(c["id"] == CONV for c in listed),
    f"got {code}",
)
listed_row = {}
if isinstance(listed, list):
    listed_row = next((c for c in listed if c["id"] == CONV), {})
check(
    "LINEAGE IS NOT EXPOSED: no route reports lineage_id, so a cutover's continuity is unobservable",
    "lineage_id" in listed_row,
    f"ConversationResponse fields: {sorted(listed_row)}",
)

code, pconv = api("GET", f"{A}/conversations")
check(
    "and in the project-wide list the rail reads",
    code == 200 and any(c["id"] == CONV for c in pconv.get("conversations", [])),
    f"got {code}",
)

# ------------------------------------------------------------------ 4. rename refusals on a real row

code, r = api("PATCH", f"{A}/agent/{AGENT}/conversations/{CONV}", {"title": "   "})
check("an all-whitespace title is refused", code == 400, f"got {code}")
check("and the refusal says why", "empty" in detail_of(r).lower(), detail_of(r))

code, r = api("PATCH", f"{A}/agent/{AGENT}/conversations/{CONV}", {"title": "x" * 500})
check("an over-long title is refused", code in (400, 422), f"got {code}")
check(
    "and the refusal names the limit that would work",
    any(ch.isdigit() for ch in detail_of(r)),
    detail_of(r),
)

code, r = api("PATCH", f"{A}/agent/{AGENT}/conversations/{CONV}", {})
check("a rename with no title at all is refused", code == 422, f"got {code}")

code, r = api("PATCH", f"{A}/agent/{ARCHIVED}/conversations/{CONV}", {"title": "wrong agent"})
check("renaming another AGENT's conversation is refused", code == 404, f"got {code}")

if B:
    code, r = api("PATCH", f"{B}/agent/{AGENT}/conversations/{CONV}", {"title": "wrong project"})
    check("renaming a conversation owned by another PROJECT is refused", code == 404, f"got {code}")
    check(
        "and the refusal does not disclose that the id exists elsewhere",
        "not found" in detail_of(r).lower() and OTHER not in detail_of(r),
        detail_of(r),
    )
    code, r = api("GET", f"{B}/agent/{AGENT}/chat/{CONV}")
    check("reading another project's conversation is refused", code == 404, f"got {code}")

# ------------------------------------------------------------------ 5. rename that works

code, renamed = api(
    "PATCH", f"{A}/agent/{AGENT}/conversations/{CONV}", {"title": f"  operator  title  {TAG}  "}
)
check("a rename is accepted", code == 200, f"got {code}")
check(
    "the title is whitespace-collapsed rather than stored verbatim",
    code == 200 and renamed.get("title") == f"operator title {TAG}",
    repr(code == 200 and renamed.get("title")),
)
check(
    "and it is recorded as operator-set, which is what protects it from the titler",
    code == 200 and renamed.get("title_set_by_operator") is True,
    str(code == 200 and renamed.get("title_set_by_operator")),
)

# ------------------------------------------------------------------ 6. release-task

code, rel = api("DELETE", f"{A}/agent/{AGENT}/conversations/{CONV}/task")
check(
    "releasing a task from a conversation that holds none is idempotent, not an error",
    code == 200,
    f"got {code}",
)
check(
    "and the response states the thread now holds no task",
    code == 200 and rel.get("task_id") is None,
    str(rel.get("task_id")),
)

code, task = api("POST", f"{A}/tasks", {"title": f"row6 task {TAG}", "description": "binding"})
TASK = task.get("id") if code in (200, 201) else None
check("a task can be created to bind against", bool(TASK), f"got {code} {detail_of(task)}")
if TASK:
    wait_idle()
    code, bound = api(
        "POST",
        f"{A}/agent/trigger",
        {"agent": AGENT, "message": f"bound {TAG}", "conversation_id": CONV, "task_id": TASK},
    )
    check(
        "a turn can bind this conversation to a task", code == 200, f"got {code} {str(bound)[:160]}"
    )
    time.sleep(3)
    row = db_conversation(CONV)
    check(
        "the binding is recorded on the conversation",
        bool(row) and row["task_id"] == TASK,
        f"task_id={row and row['task_id']}",
    )
    code, rel = api("DELETE", f"{A}/agent/{AGENT}/conversations/{CONV}/task")
    check(
        "the operator can release that binding",
        code == 200 and rel.get("task_id") is None,
        f"got {code} {rel.get('task_id')}",
    )
    row = db_conversation(CONV)
    check(
        "and the release reaches the database",
        bool(row) and row["task_id"] is None,
        f"task_id={row and row['task_id']}",
    )

# ------------------------------------------------------------------ 7. chat history

settle_agent()

code, hist = api("GET", f"{A}/agent/{AGENT}/chat/{CONV}")
check("the conversation's merged timeline answers", code == 200, f"got {code}")
entries = hist.get("entries", []) if code == 200 else []
check(
    "it holds the operator's input",
    any(e["kind"] == "operator_input" for e in entries),
    f"{len(entries)} entries",
)
check(
    "and the agent's output",
    any(e["kind"] == "agent_output" for e in entries),
    f"kinds={sorted({e['kind'] for e in entries})}",
)
check(
    "the run that produced the output is named on it - attribution recorded, not inferred",
    bool(entries) and all(e.get("run_id") for e in entries if e["kind"] == "agent_output"),
    str([e.get("run_id") for e in entries if e["kind"] == "agent_output"][:4]),
)
check(
    "STATUS: the 'Run ... (exit ...)' line is in the persisted timeline, not only on the live stream",
    any(e.get("output_kind") == "status" for e in entries),
    f"output kinds={sorted({e.get('output_kind') for e in entries if e['kind'] == 'agent_output'})}",
)

code, _ = api("GET", f"{A}/agent/{ARCHIVED}/chat/{CONV}")
check("reading this conversation under another agent's name is refused", code == 404, f"got {code}")

# ------------------------------------------------------------------ 8. archive lifecycle

code, arch = api("POST", f"{A}/agent/{AGENT}/conversations/{CONV}/archive")
check("an idle conversation can be archived", code == 200, f"got {code} {detail_of(arch)}")
check(
    "and the response says so",
    code == 200 and arch.get("lifecycle") == "archived",
    str(arch.get("lifecycle")),
)

code, open_list = api("GET", f"{A}/agent/{AGENT}/conversations")
check(
    "an archived conversation leaves the default list",
    code == 200 and not any(c["id"] == CONV for c in open_list),
    f"got {code}",
)
code, arch_list = api("GET", f"{A}/agent/{AGENT}/conversations?lifecycle=archived")
check(
    "and is exactly what ?lifecycle=archived returns",
    code == 200 and any(c["id"] == CONV for c in arch_list),
    f"got {code}",
)
code, pconv = api("GET", f"{A}/conversations")
check(
    "the project-wide archived count moves with it",
    code == 200 and pconv.get("archived_by_agent", {}).get(AGENT, 0) >= 1,
    str(pconv.get("archived_by_agent")),
)

code, r2 = api("POST", f"{A}/agent/{AGENT}/conversations/{CONV}/archive")
check(
    "archiving an already-archived conversation is not an error",
    code == 200,
    f"got {code} {detail_of(r2)}",
)

code, _ = api(
    "PATCH", f"{A}/agent/{AGENT}/conversations/{CONV}", {"title": f"renamed while archived {TAG}"}
)
check(
    "an archived conversation can still be renamed by the API",
    code == 200,
    f"got {code} - the rail offers only Unarchive here, so this is API-only reachable",
)

code, un = api("POST", f"{A}/agent/{AGENT}/conversations/{CONV}/unarchive")
check(
    "unarchive reopens it",
    code == 200 and un.get("lifecycle") == "open",
    f"got {code} {un.get('lifecycle')}",
)

# ------------------------------------------------------------------ 9. archive refused while busy

if not os.environ.get("AW_SKIP_TURN"):
    settle_agent()
    code, trig2 = api(
        "POST",
        f"{A}/agent/trigger",
        {
            "agent": AGENT,
            "message": (
                "Write a detailed 1200-word essay about the history of the astrolabe, "
                "in full prose, without using any tools."
            ),
            "conversation_id": CONV,
        },
    )
    check("a long turn into the open conversation is accepted", code == 200, f"got {code}")
    if code == 200:
        time.sleep(5)
        code, busy_arch = api("POST", f"{A}/agent/{AGENT}/conversations/{CONV}/archive")
        check(
            "archiving a conversation with a run in progress is refused", code == 409, f"got {code}"
        )
        check(
            "and that refusal says what the operator must do first",
            names_what_would_work(
                detail_of(busy_arch), "running", "in progress", "finish", "stop", "wait"
            ),
            detail_of(busy_arch),
        )
        api("POST", f"{A}/agent/{AGENT}/stop")
        wait_idle()

# ------------------------------------------------------------------ 10. worker-generated titles

CONV2 = None
if os.environ.get("AW_SKIP_TURN"):
    print("\n(title generation and cutover skipped: AW_SKIP_TURN set)")
else:
    settle_agent()
    code, settings = api("GET", f"{A}/settings")
    check("project settings can be read", code == 200, f"got {code}")
    check(
        "title generation is OFF by default - a spawn nobody asked for is never implicit",
        code == 200 and settings.get("conversation_title_mode") == "truncate",
        str(settings.get("conversation_title_mode")),
    )
    code, saved = api("PUT", f"{A}/settings", {"conversation_title_mode": "generate"})
    check("title generation can be turned on", code == 200, f"got {code} {detail_of(saved)}")
    check(
        "and the saved settings echo the mode back",
        code == 200 and saved.get("conversation_title_mode") == "generate",
        str(saved.get("conversation_title_mode")),
    )

    code, trig3 = api(
        "POST",
        f"{A}/agent/trigger",
        {
            "agent": AGENT,
            "message": (
                "In one short sentence, explain what a semaphore does in concurrent programming. "
                "Do not use any tools."
            ),
        },
    )
    check("a second conversation is opened", code == 200, f"got {code}")
    CONV2 = trig3.get("conversation_id") if code == 200 else None
    truncated = db_conversation(CONV2)
    check(
        "it starts with the truncated floor title",
        bool(truncated) and bool(truncated["title"]),
        f"title={truncated and truncated['title']!r}",
    )
    wait_idle()

    generated, deadline = None, time.time() + 150
    while time.time() < deadline:
        cur = db_conversation(CONV2)
        if cur and truncated and cur["title"] != truncated["title"]:
            generated = cur["title"]
            break
        time.sleep(3)
    check(
        "A WORKER-GENERATED TITLE ACTUALLY REPLACES THE TRUNCATED ONE",
        bool(generated),
        (
            f"still {truncated and truncated['title']!r} after 150s"
            if not generated
            else f"{truncated['title']!r} -> {generated!r}"
        ),
    )
    code, events = api("GET", f"{A}/events/history?limit=100")
    if isinstance(events, list):
        rows = events
    elif isinstance(events, dict):
        rows = events.get("events", [])
    else:
        rows = []
    check(
        "and the titling is recorded as an event rather than as a Run row",
        any(
            (e.get("event_type") or e.get("type")) == "conversation_titled"
            for e in rows
            if isinstance(e, dict)
        ),
        f"{len(rows)} recent events from GET /events/history",
    )

    if CONV2:
        api(
            "PATCH",
            f"{A}/agent/{AGENT}/conversations/{CONV2}",
            {"title": f"operator keeps this {TAG}"},
        )
        code, _ = api(
            "POST",
            f"{A}/agent/trigger",
            {
                "agent": AGENT,
                "message": "Reply with the word: done. No tools.",
                "conversation_id": CONV2,
            },
        )
        check("a further turn into that conversation is accepted", code == 200, f"got {code}")
        wait_idle()
        time.sleep(25)
        after = db_conversation(CONV2)
        check(
            "AN OPERATOR-SET TITLE SURVIVES THE NEXT TURN'S TITLER",
            bool(after) and after["title"] == f"operator keeps this {TAG}",
            f"title={after and after['title']!r}",
        )

    api("PUT", f"{A}/settings", {"conversation_title_mode": "truncate"})

# ------------------------------------------------------------------ 11. lineage across a cutover

if not os.environ.get("AW_SKIP_TURN"):
    settle_agent()
    code, runners = api("GET", f"{A}/runners")
    RUNNER = runners[0]["id"] if code == 200 and runners else None

    code, cp_off = api("POST", f"{A}/conversations/{CONV}/checkpoint")
    check(
        "a checkpoint with no checkpoint runner configured is refused rather than billed elsewhere",
        code == 409,
        f"got {code} {detail_of(cp_off)}",
    )
    check(
        "and that refusal says where to configure one",
        names_what_would_work(detail_of(cp_off), "settings", "choose"),
        detail_of(cp_off),
    )

    code, saved = api("PUT", f"{A}/settings", {"checkpoint_runner_id": RUNNER})
    check("a checkpoint runner can be configured", code == 200, f"got {code} {detail_of(saved)}")

    code, cp = api("POST", f"{A}/conversations/{CONV}/checkpoint", timeout=300)
    show("POST /conversations/{id}/checkpoint", code, cp, limit=300)
    check("a checkpoint is written on demand", code in (200, 201), f"got {code} {detail_of(cp)}")
    CP = cp.get("id") if code in (200, 201) and isinstance(cp, dict) else None

    if CP:
        before = db_conversation(CONV)
        code, cut = api("POST", f"{A}/checkpoints/{CP}/cutover", timeout=180)
        show("POST /checkpoints/{id}/cutover", code, cut, limit=300)
        check("the cutover is accepted", code == 200, f"got {code} {detail_of(cut)}")
        SUCC = cut.get("successor_conversation_id") if code == 200 else None
        check("it names the successor conversation", bool(SUCC), str(cut)[:200])
        if SUCC:
            succ = db_conversation(SUCC)
            check(
                "THE SUCCESSOR INHERITS THE PREDECESSOR'S LINEAGE, measured in sqlite",
                bool(succ) and bool(before) and succ["lineage_id"] == before["lineage_id"],
                f"succ={succ and succ['lineage_id']} pred={before and before['lineage_id']}",
            )
            check(
                "the successor is a NEW conversation id, so lineage is the only thing that survives",
                bool(succ) and succ["id"] != CONV,
                f"{SUCC} vs {CONV}",
            )
            check(
                "the predecessor is archived by the cutover",
                (db_conversation(CONV) or {}).get("lifecycle") == "archived",
                str((db_conversation(CONV) or {}).get("lifecycle")),
            )
            check(
                "the successor's title is marked operator-set so the titler cannot overwrite it",
                bool(succ) and bool(succ["title_set_by_operator"]),
                f"title={succ and succ['title']!r} set={succ and succ['title_set_by_operator']}",
            )
            code, srow = api("GET", f"{A}/agent/{AGENT}/conversations")
            listed_succ = None
            if isinstance(srow, list):
                listed_succ = next((c for c in srow if c["id"] == SUCC), None)
            check("the successor is listed for the agent", bool(listed_succ), f"got {code}")

    api("PUT", f"{A}/settings", {"checkpoint_runner_id": None})
    settle_agent()

# ------------------------------------------------------------------ summary

print()
print("=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
print(f"ROW 6 - {passed}/{len(results)} assertions passed")
for label, ok, detail in results:
    if not ok:
        print(f"  FAIL  {label}" + (f"  [{detail[:200]}]" if detail else ""))
print("=" * 78)
