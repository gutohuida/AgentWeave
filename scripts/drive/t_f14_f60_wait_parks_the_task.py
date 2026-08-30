"""F14 + F60 — a task waits while its run waits, and says so afterwards.

Task 9.4/9.4a of `openspec/changes/a-task-waits-while-its-run-waits/`. Every assertion here is one
no unit test can make, because each depends on a **real agent process being suspended inside a real
tool call** while the Hub is asked what it thinks is happening:

* the task is `blocked` *while its run is still `running`* — the two states the whole change exists
  to make coexist, and which before it never could;
* the loop board says that agent is `working` the task, not merely `assigned` to it (3a);
* the conversation rail says `waiting`, and stops saying it once the wait ends (6.4);
* a run asking to move a waiting task out of `blocked` gets a 403 it can act on (2b);
* the wait ends by itself, the agent's own completion lands, and the finished task carries the
  record that the decision was taken without the operator (F60).

Haiku throughout, per the standing directive: what this asserts is that a turn starts, parks, and
resumes — not that the agent writes anything good.

Run against a Hub on 8011 started from *this* checkout. `AW_HUB` and `AW_KEY` come from `aw.py`'s
environment, so:

    AW_HUB=http://127.0.0.1:8011 AW_KEY=aw_live_0830runkey0000000000000000000 \
        py -3.11 scripts/drive/t_f14_f60_wait_parks_the_task.py
"""

import json
import os
import sys
import time

from aw import api

WORKDIR = os.environ.get("DRIVE_WORKDIR", "C:\\Users\\huida\\AppData\\Local\\Temp\\aw0830\\f14")
PROJECT_NAME = "f14-wait-parks-the-task"
HAIKU = "claude-haiku-4-5-20251001"

POLL_SECONDS = 3
WAIT_LIMIT = 60  # ~180s

FAILURES = []


def check(label, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(f"{label} [{detail}]")
    return ok


def show(label, code, body, limit=400):
    text = body if isinstance(body, str) else json.dumps(body, default=str)
    print(f"--- {label} [{code}] {text[:limit]}")
    return body


def wait_for(label, fn, limit=WAIT_LIMIT):
    for i in range(limit):
        got = fn()
        if got:
            print(f"  {label} after ~{i * POLL_SECONDS}s")
            return got
        time.sleep(POLL_SECONDS)
    print(f"  TIMEOUT waiting for {label} (~{limit * POLL_SECONDS}s)")
    return None


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def ensure_project():
    code, body = api("GET", "/projects")
    rows = body.get("projects") if isinstance(body, dict) else body
    for row in rows or []:
        if row.get("name") == PROJECT_NAME:
            return row["id"]
    os.makedirs(WORKDIR, exist_ok=True)
    code, body = api("POST", "/projects/open", {"path": WORKDIR, "name": PROJECT_NAME})
    show("POST /projects/open", code, body)
    if code >= 300:
        sys.exit("could not create project")
    return body["id"]


def ensure_runner(project):
    code, body = api("GET", f"/projects/{project}/runners")
    rows = body.get("runners") if isinstance(body, dict) else body
    for row in rows or []:
        if row.get("name") == "Haiku (cheap)":
            return row["id"]
    code, body = api(
        "POST",
        f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    show("POST /runners", code, body)
    if code >= 300:
        sys.exit("could not create runner")
    return body["id"]


def ensure_agent(project, name, runner, question_timeout):
    code, body = api(
        "POST",
        f"/projects/{project}/agents",
        {"name": name, "runner_id": runner},
    )
    if code >= 300:
        code, body = api("GET", f"/projects/{project}/agents")
        rows = body.get("agents") if isinstance(body, dict) else body
        if not any(row.get("name") == name for row in rows or []):
            sys.exit(f"could not create or find agent {name}")
    # How long this agent waits, which is also what the Hub stamps as the question's deadline.
    # Set through the operator's own settings route, never told to the Hub by the run.
    code, body = api(
        "PATCH",
        f"/projects/{project}/agents/{name}",
        {"question_timeout_seconds": question_timeout},
    )
    show(f"PATCH /agents/{name} question_timeout={question_timeout}", code, body, 200)
    return name


def make_task(project, title, assignee, loop_id=None):
    payload = {"title": title, "assignee": assignee, "status": "pending"}
    if loop_id:
        payload["loop_id"] = loop_id
    code, body = api("POST", f"/projects/{project}/tasks", payload)
    show("POST /tasks", code, body, 200)
    if code >= 300:
        sys.exit("could not create task")
    return body["id"]


def get_task(project, task_id):
    _code, body = api("GET", f"/projects/{project}/tasks/{task_id}")
    return body if isinstance(body, dict) else {}


def roster(project):
    """The roster's own view of who is doing what. There is no operator-facing runs listing, and
    this is the surface an operator actually reads, so it is the right one to assert against."""
    _code, body = api("GET", f"/projects/{project}/agents")
    rows = body.get("agents") if isinstance(body, dict) else body
    return {row.get("name"): row for row in rows or []}


def loop_summaries(project):
    _code, body = api("GET", f"/projects/{project}/loops")
    rows = body.get("loops") if isinstance(body, dict) else body
    return rows or []


def make_loop(project, agent, label):
    """A job wearing a purpose is a loop, and a loop is the only surface that renders capacity."""
    code, body = api(
        "POST",
        f"/projects/{project}/jobs",
        {
            "name": label,
            "agent": agent,
            "message": "keep going",
            "cron": "0 9 * * *",
            "purpose": "drive the wait",
            "enabled": False,
        },
    )
    show("POST /jobs (loop)", code, body, 200)
    if code >= 300:
        return None, None
    return body["id"], (body.get("loop") or {}).get("id")


def open_questions(project):
    _code, body = api("GET", f"/projects/{project}/questions")
    rows = body.get("questions") if isinstance(body, dict) else body
    return [q for q in (rows or []) if not q.get("answered") and not q.get("declined")]


def conversation_states(project):
    _code, body = api("GET", f"/projects/{project}/conversations")
    rows = body.get("conversations") if isinstance(body, dict) else body
    return {row.get("id"): row.get("attention") for row in rows or []}


def trigger(project, agent, message, task_id=None):
    payload = {"agent": agent, "message": message}
    if task_id:
        payload["task_id"] = task_id
    code, body = api("POST", f"/projects/{project}/agent/trigger", payload, timeout=30)
    show(f"POST /agent/trigger {agent}", code, body, 300)
    return code, body


# ---------------------------------------------------------------------------
# Phase A — the wait is visible while it is happening
# ---------------------------------------------------------------------------

ASK_AND_FINISH = (
    "Call the ask_user tool exactly once, with a single blocking question: "
    "'Which colour should the badge be?' with options 'red' and 'blue'. "
    "When ask_user returns, call update_task on task {task} with status 'completed'. "
    "Then reply with one short sentence saying what you did. "
    "Do not read or write any files."
)


def phase_a(project, asker, closer):
    print("\n=== PHASE A — the task parks while the run is still running ===")
    _job_id, loop_id = make_loop(project, asker, "Phase A loop")
    task_id = make_task(project, "Phase A: the work being asked about", asker, loop_id=loop_id)
    trigger(project, asker, ASK_AND_FINISH.format(task=task_id), task_id)

    parked = wait_for(
        "task parked at ask time",
        lambda: get_task(project, task_id).get("status") == "blocked",
    )
    task = get_task(project, task_id)
    check("the task is blocked while its run waits", bool(parked), task.get("status"))
    check(
        "and it says what it is waiting for",
        bool(task.get("blocked_reason")),
        str(task.get("blocked_reason"))[:80],
    )

    # THE assertion no unit test can make: the two states coexisting, observed live. Before this
    # change they never could — a task reached `blocked` only once its asking run had ended.
    asker_row = roster(project).get(asker) or {}
    check(
        "the asking agent is still RUNNING while its task is blocked",
        asker_row.get("status") == "running",
        f"{asker} status={asker_row.get('status')}, task={task.get('status')}",
    )

    # 6.4 — the conversation rail says somebody is waiting.
    states = conversation_states(project)
    check(
        "the conversation rail says waiting",
        "waiting" in states.values(),
        json.dumps(states)[:200],
    )

    # 3a — the loop board must not call an agent that is mid-turn on this exact task merely
    # `assigned` to it. `attribute` used to consult the runs only inside its `unstaffable` branch,
    # and a blocked task is never unstaffable, so for the whole wait the board said `assigned`.
    entries = [
        entry
        for summary in loop_summaries(project)
        for entry in ((summary.get("loop") or summary).get("current_tasks") or [])
        if entry.get("id") == task_id
    ]
    check(
        "the loop board says the agent is working the blocked task",
        bool(entries) and entries[0].get("agent_capacity") == "working",
        json.dumps(entries)[:200],
    )

    # 2b — a run asking to move a waiting task out of `blocked` is refused, with a message it can
    # act on. Driven with a *second* agent, because the asking one is suspended inside its own tool
    # call; the guard is at the route and does not care which run asks.
    trigger(
        project,
        closer,
        (
            f"Call update_task on task {task_id} with status 'in_progress'. "
            "Then reply with the EXACT error text the Hub returned, or 'NO ERROR' if it worked. "
            "Do not read or write any files and do not call any other tool."
        ),
    )
    still_blocked = wait_for(
        "the closer's turn ended with the task still blocked",
        lambda: (
            get_task(project, task_id).get("status") == "blocked"
            and (roster(project).get(closer) or {}).get("status") != "running"
        ),
        limit=25,
    )
    check(
        "a second run could not assert the task out of blocked",
        get_task(project, task_id).get("status") == "blocked",
        get_task(project, task_id).get("status"),
    )
    if not still_blocked:
        print("  (the closer's turn may still be running; the status check above is what counts)")

    # The answer releases it and the asker finishes.
    questions = open_questions(project)
    if questions:
        qid = questions[0]["id"]
        code, body = api(
            "PATCH", f"/projects/{project}/questions/{qid}", {"answer": "blue", "labels": ["blue"]}
        )
        show("PATCH /questions (answer)", code, body, 200)
        released = wait_for(
            "the answer released the task",
            lambda: get_task(project, task_id).get("status") != "blocked",
        )
        check("answering releases the task", bool(released), get_task(project, task_id).get("status"))
        finished = wait_for(
            "the agent completed its work",
            lambda: get_task(project, task_id).get("status") in ("completed", "under_review"),
        )
        check("the agent's own completion lands", bool(finished), get_task(project, task_id).get("status"))
        check(
            "an answered wait leaves no proceeded-without-you record",
            not get_task(project, task_id).get("proceeded_without_answer_reason"),
            str(get_task(project, task_id).get("proceeded_without_answer_reason")),
        )
    else:
        check("a question was raised", False, "none open")
    return task_id


# ---------------------------------------------------------------------------
# Phase B — the wait ends by itself, and the task says so
# ---------------------------------------------------------------------------


def phase_b(project, waiter):
    print("\n=== PHASE B — the wait expires, the work lands, and the task records it ===")
    task_id = make_task(project, "Phase B: the work nobody was asked about in time", waiter)
    trigger(project, waiter, ASK_AND_FINISH.format(task=task_id), task_id)

    parked = wait_for(
        "task parked at ask time",
        lambda: get_task(project, task_id).get("status") == "blocked",
    )
    check("the task parks", bool(parked), get_task(project, task_id).get("status"))

    released = wait_for(
        "the wait ended on its own and released the task",
        lambda: get_task(project, task_id).get("status") != "blocked",
    )
    check("an unanswered wait ends by itself", bool(released), get_task(project, task_id).get("status"))

    finished = wait_for(
        "the agent completed the work it had genuinely done",
        lambda: get_task(project, task_id).get("status") in ("completed", "under_review"),
    )
    task = get_task(project, task_id)
    check("the agent's completion is no longer refused", bool(finished), task.get("status"))
    check(
        "the finished task says the decision was taken without the operator",
        bool(task.get("proceeded_without_answer_reason")),
        str(task.get("proceeded_without_answer_reason"))[:100],
    )

    # 6.4's second half: once the wait has ended, the rail must stop saying somebody is waiting.
    states = conversation_states(project)
    check(
        "the conversation rail stops saying waiting once the wait ended",
        "waiting" not in states.values(),
        json.dumps(states)[:200],
    )

    # And it is permanent: answering afterwards must not erase the record (F60's compounding half).
    questions = open_questions(project)
    if questions:
        api(
            "PATCH",
            f"/projects/{project}/questions/{questions[0]['id']}",
            {"answer": "red", "labels": ["red"]},
        )
        time.sleep(2)
        check(
            "answering afterwards does not erase the record",
            bool(get_task(project, task_id).get("proceeded_without_answer_reason")),
            str(get_task(project, task_id).get("proceeded_without_answer_reason"))[:80],
        )
    return task_id


if __name__ == "__main__":
    project = ensure_project()
    runner = ensure_runner(project)
    # Phase A waits long enough that the operator (this script) is the one who ends it.
    asker = ensure_agent(project, "asker", runner, 600)
    closer = ensure_agent(project, "closer", runner, 600)
    # Phase B waits the shortest the Hub permits, so the expiry happens inside one drive.
    waiter = ensure_agent(project, "waiter", runner, 10)
    print(f"\nPROJECT={project} RUNNER={runner}")

    phase_a(project, asker, closer)
    phase_b(project, waiter)

    print("\n=== RESULT ===")
    if FAILURES:
        for line in FAILURES:
            print("  FAIL " + line)
        sys.exit(1)
    print("  all checks passed")
