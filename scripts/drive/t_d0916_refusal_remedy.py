"""DRIVE 2026-09-16 -- a refusal names a remedy that works (openspec change, task 5.3).

Four fixes landed on this branch, all unit-tested green (`hub/tests/test_a_refusal_names_a_remedy_
that_works.py`), none yet driven against a real Hub:

  D1  `own_review_remedy(task)` (`scheduler.py`) -- the sentence a `completed` or `under_review`
      task's own holder is told, chosen by whether the actor asking is the operator or an agent.
  D2  `JOB_RUN_ERROR_SUMMARY_CHARS = 500` and `fit_error_summary` (`db/models.py`) clamp
      `JobRun.error_summary` at write time, and `_wedged_review_reason` (`scheduler.py`) trims a
      long quoted title so the sentence it builds fits before that clamp ever has to act.
  D4  `_guard_reviewer_is_not_the_author` (`task_transition_service.py`) refuses moving a
      `completed` task to `under_review` while its own author/completer still holds it, wording the
      refusal `"Cannot move task {id} to 'under_review' with {assignee!r} as its holder: ..."` and
      picking the remedy by `actor.is_operator`.

Three things a unit test cannot show, each requiring a live Hub and (for two of them) a real turn:

  CHECK 1  A wedged review whose task has a long title used to risk `JobRun.error_summary` growing
           past 500 characters, which `JobRunResponse`'s `max_length=500` would turn into a 500 on
           `GET /jobs/{id}/history` (a `ResponseValidationError`, not the guard's own 403/409). This
           builds that wedge by hand -- `t_f154_wedged_review.py`'s pattern, with a 256-character
           title (the product's own maximum, `TaskCreate.title`) instead of a short one -- fires
           the job so `_wedged_review_reason` writes the
           trimmed sentence into a fresh `JobRun.error_summary`, and reads the history route.

  CHECK 2  The task drawer's status menu, read in real Chromium against the served bundle (never a
           Python transcription -- `night-window.md`'s Driving section, and the F274 lesson it
           cites). A task `completed` and held by its own author is expected to still *offer*
           `under_review` (the transition map does not know who authored what) and to *refuse* it
           when clicked, rendering the guard's sentence at `task-status-refusal-{id}` next to the
           `task-land-{id}` ("Land it") button (`TaskDetailDrawer.tsx`).

  CHECK 3  The same refusal, read from a real Haiku turn's own tool result rather than guessed: the
           author agent is asked, through a real prompt using its real task tools, to move the very
           task it just completed to `under_review` itself. `_guard_reviewer_is_not_the_author`'s
           agent-actor remedy ("None of the task tools you are offered reassigns a task; the
           operator can move it on.") should come back as the `update_task` tool's own result, read
           off `GET /agent/{name}/chat` (`TimelineEntry.output_kind == "tool_result"`).

The self-held task for checks 2 and 3 is authored by a real Haiku turn, not an operator PATCH walk:
`agent_that_completed` (which the guard reads) is built from `TaskTransition.actor_agent`, which is
NULL for every edge an operator walks by hand (F167) -- so a hand-walked "completion" would not even
trip the guard this task exists to drive. The one-task-document + flow pattern from
`t_d0915_reachability.py`'s `phase_author` is reused for exactly this reason.

Real surface only. No row inserts for the guard/UI population. Every runner binds Haiku. Disables
every job it creates and confirms no job is left enabled afterward, via a direct query.

Run (from scripts/drive):
  AW_HUB=http://127.0.0.1:<port> AW_KEY=<key> AW_SHOTS=<dir> py -3.11 -u t_d0916_refusal_remedy.py
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import aw  # noqa: E402
from aw import api  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
AUTHOR = "dev"
REVIEWER = "rev"
FORBIDDEN = ("proj-5e960453", "proj-18e5d4e0")
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)
FAR_CRON = "0 4 1 1 *"

ROOT = None
P = ""
JOBS = []
VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def note(label, detail=""):
    print(f"  [obs] {label}" + (f" -- {detail}" if detail else ""))


def head(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def blob(x, limit=1200):
    return json.dumps(x, indent=1, default=str)[:limit]


def git(*args):
    p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def must(*args):
    code, out, err = git(*args)
    if code != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {err or out}")
    return out


def make_project():
    global ROOT, P
    ROOT = tempfile.mkdtemp(prefix="aw-d0916-")
    must("init", "-q")
    must("config", "user.email", "drive@example.com")
    must("config", "user.name", "Drive")
    must("checkout", "-q", "-b", "main")
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("base\n")
    must("add", "README.md")
    must("commit", "-q", "-m", "base")

    code, created = api("POST", "/projects/open", {"path": ROOT, "name": f"d0916-drive-{RUN}"})
    if code not in (200, 201):
        raise SystemExit(f"could not open the project: {code} {created}")
    P = created["id"]
    aw.P = P
    if P in FORBIDDEN:
        raise SystemExit(f"REFUSING: the Hub handed back {P}")
    code, saved = api("PUT", f"/projects/{P}/settings", {"main_branch": "main"})
    if code != 200:
        raise SystemExit(f"could not set the main branch: {code} {saved}")
    print(f"  project {P} at {ROOT}")


def ensure_runner():
    code, body = api("GET", f"/projects/{P}/runners")
    for r in body if isinstance(body, list) else []:
        if r.get("model") == HAIKU:
            return r["id"]
    code, body = api(
        "POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU}
    )
    if code >= 300:
        raise SystemExit(f"no runner: {code} {body}")
    return body["id"]


def ensure_agent(name, runner):
    code, body = api("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner})
    if code >= 300:
        code, body = api("PATCH", f"/projects/{P}/agents/{name}", {"runner_id": runner})
        if code >= 300:
            raise SystemExit(f"no agent {name}: {code} {body}")


def agents():
    code, body = api("GET", f"/projects/{P}/agents")
    return body if isinstance(body, list) else []


def statuses():
    return {a["name"]: a.get("status") for a in agents()}


def board():
    code, body = api("GET", f"/projects/{P}/tasks?limit=500")
    if isinstance(body, dict):
        body = body.get("tasks") or body.get("items") or []
    return body if isinstance(body, list) else []


def task(tid):
    return next((t for t in board() if t["id"] == tid), None)


def move(tid, status, assignee=None, expect=200):
    payload = {"status": status}
    if assignee is not None:
        payload["assignee"] = assignee
    code, body = api("PATCH", f"/projects/{P}/tasks/{tid}", payload)
    ok = code == expect
    print(f"  {'    ' if ok else 'BAD '}-> {status}" + (f" ({assignee})" if assignee else "") + f"  [{code}]")
    if not ok:
        print("      " + blob(body, 700))
        raise SystemExit(f"could not move the task to {status}")
    return body


def make_loop(name, title):
    """A loop with one task on its queue, seeded in the one call that creates it (`t_f154`'s
    pattern). `enabled=True` because `POST /jobs/{id}/run` refuses a disabled job outright."""
    body = {
        "name": name,
        "agent": AUTHOR,
        "message": "Work the task you have been given.",
        "cron": FAR_CRON,
        "enabled": True,
        "purpose": "Drive 0916: the 500-char fit.",
        "stop_when_queue_empties": True,
        "initial_tasks": [{"title": title, "description": "One line. Nothing else."}],
    }
    code, job = api("POST", f"/projects/{P}/jobs", body)
    if code != 201:
        raise SystemExit(f"could not create the loop: {code} {job}")
    JOBS.append(job["id"])
    mine = [t for t in board() if t.get("title") == title]
    if not mine:
        raise SystemExit(f"the loop seeded no task: {blob(job)}")
    return job["id"], mine[0]["id"]


def wedge(tid, assignee):
    """Drive a task by hand to `under_review` with *assignee* holding it. No turn is ever run."""
    move(tid, "assigned", AUTHOR)
    move(tid, "in_progress")
    move(tid, "completed")
    move(tid, "under_review", assignee)


def fire(job_id, label):
    code, body = api("POST", f"/projects/{P}/jobs/{job_id}/run", {})
    detail = body.get("detail") if isinstance(body, dict) else body
    print(f"  fire[{label}] -> {code}")
    print(f"      {json.dumps(detail, default=str)[:700]}")
    return code, detail


def wait_for(pred, seconds, what):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(1)
    print(f"      timed out waiting for {what}")
    return False


def settle(label, rounds=60, gap=5):
    for i in range(rounds):
        time.sleep(gap)
        busy = {n: s for n, s in statuses().items() if s not in ("idle", "offline", "error", None)}
        print(f"      [{label}] t+{(i + 1) * gap:>3}s busy={busy}")
        if i >= 1 and not busy:
            return True
    print(f"      [{label}] did not settle")
    return False


# --- CHECK 1: the 500-char fit ------------------------------------------------------------------


def check1_long_title_history():
    head("CHECK 1 -- a wedged review with a long title, then GET .../jobs/{id}/history")
    # `TaskCreate.title` caps at 256 characters (`hub/hub/schemas/tasks.py`) -- measured live here,
    # not assumed: the first run of this script tried 306 and `POST /jobs` refused the loop's own
    # `initial_tasks` entry with a 422 before any of this population could be built at all. 256 is
    # therefore the worst case the product can ever produce, which is exactly what task 2.4's own
    # unit test used (`test_wedged_review_reason_fits_500_at_a_32_char_reviewer_and_256_char_title`,
    # measured there at 552 characters unmutated) -- so this drives the same worst case for real.
    raw = (
        "Add one line documenting the extremely long-winded rationale behind why this "
        "particular README needs an update that nobody asked for, including a full paragraph of "
        "justification about repository hygiene and a second paragraph nobody will read either, "
        "plus a third clause padding this out to the real maximum"
    )
    title = (raw * 2)[:256]
    check("the title is exactly the product's own maximum, 256 characters", len(title) == 256, str(len(title)))
    job1, t1 = make_loop(f"d0916-wedge-{RUN}", title)
    print(f"  job {job1} task {t1}")
    wedge(t1, REVIEWER)
    row = task(t1)
    check(
        "the task is under_review with the reviewer on it, no live turn",
        row and row["status"] == "under_review" and row.get("assignee") == REVIEWER,
        f"{row and row['status']} / {row and row.get('assignee')}",
    )

    code, detail = fire(job1, "wedge fires")
    text = json.dumps(detail, default=str)
    check(
        "the firing answers a refusal naming the task and the reviewer, not a 500",
        code in (409,) and t1 in text and REVIEWER in text,
        f"{code} {text[:300]}",
    )

    code_h, hist = api("GET", f"/projects/{P}/jobs/{job1}/history")
    check(
        "GET .../jobs/{id}/history returns 200 after the wedged review with the long title",
        code_h == 200,
        f"{code_h} {blob(hist, 500)}",
    )
    rows = hist if isinstance(hist, list) else []
    mine = [r for r in rows if r.get("error_summary")]
    note("job runs with a non-empty error_summary", str(len(mine)))
    for r in mine[:3]:
        es = r.get("error_summary") or ""
        note(
            f"run {r.get('id')} error_summary ({len(es)} chars)",
            es[:200] + ("…[truncated for display]" if len(es) > 200 else ""),
        )
        check(
            f"run {r.get('id')}'s error_summary fits the 500-char column (D2)",
            len(es) <= 500,
            str(len(es)),
        )
    check(
        "at least one run's error_summary carries the wedge's own reason",
        any(t1 in (r.get("error_summary") or "") for r in mine)
        or any(REVIEWER in (r.get("error_summary") or "") for r in mine),
        blob([r.get("error_summary") for r in mine], 400),
    )
    api("PATCH", f"/projects/{P}/jobs/{job1}", {"enabled": False})
    return job1, t1


# --- CHECKS 2 & 3 setup: a task completed by a real turn, still held by its author ---------------


def one_task_document(target):
    payload = {
        "schema_version": 1,
        "kind": "change-spec",
        "title": f"{target} exists",
        "summary": f"One file, so there is exactly one piece of work to complete.",
        "problem": f"{target} does not exist.",
        "scope": {"in_scope": [target], "non_goals": ["anything else"]},
        "requirements": [
            {
                "key": "file",
                "statement": f"The project SHALL contain {target} holding the line ok.",
                "modal": "SHALL",
                "rationale": "A drive needs one completable task.",
            }
        ],
        "acceptance_criteria": [
            {
                "key": "file-exists",
                "requirement": "file",
                "given": "the project after the change",
                "when": f"{target} is read",
                "then": "it holds the single line ok",
            }
        ],
        "tasks": [
            {
                "key": "write-file",
                "title": f"Create {target}",
                "description": f"Create {target} in your working directory containing exactly the "
                f"line `ok`. Change nothing else. Then call update_task to mark this task "
                f"completed.",
                "requirements": ["file"],
            }
        ],
    }
    base = f"/projects/{P}/project"
    code, doc = api("POST", f"{base}/documents", {"title": payload["title"]})
    if code >= 300:
        raise SystemExit(f"create document failed: {code} {doc}")
    q = urllib.parse.quote(doc["path"], safe="")
    api("PUT", f"{base}/documents/{q}/content", {"document": payload})
    api("POST", f"{base}/documents/close-exploration?path={q}", {"reason": "drive 0916"})
    api("POST", f"{base}/documents/propose?path={q}", {"reason": "drive"})
    return doc.get("id"), q


def make_flow(doc_id):
    code, job = api(
        "POST",
        f"/projects/{P}/jobs",
        {
            "name": f"d0916-self-{RUN}",
            "agent": AUTHOR,
            "message": "Work the task you have been given. Keep the edit minimal.",
            "cron": FAR_CRON,
            "purpose": "Author one file and complete the task, held for the self-review checks.",
            "spec_document_id": doc_id,
            "stop_when_queue_empties": True,
            "enabled": True,
        },
    )
    if code != 201:
        raise SystemExit(f"could not create the flow: {code} {job}")
    JOBS.append(job["id"])
    loop_id = (job.get("loop") or {}).get("id")
    if not loop_id:
        raise SystemExit(f"the flow opted into no loop: {blob(job)}")
    return job["id"], loop_id


def setup_self_held_task():
    head("SETUP for CHECKS 2 & 3 -- a real Haiku turn completes a task, still held by its author")
    target = f"d0916_{RUN}.txt"
    doc_id, q = one_task_document(target)
    job_id, loop_id = make_flow(doc_id)
    api(
        "POST",
        f"/projects/{P}/project/documents/phase?path={q}&to=approved",
        {"reason": "drive 0916"},
    )
    time.sleep(1)
    mine = [t for t in board() if t.get("loop_id") == loop_id]
    check("the approval put one task on the flow's queue", len(mine) == 1, str(mine)[:200])
    tid = mine[0]["id"]

    code, detail = fire(job_id, "author works")
    check("the author's firing started", code == 200, str(code))
    started = wait_for(lambda: statuses().get(AUTHOR) == "running", 90, f"{AUTHOR} to start")
    check(f"{AUTHOR}'s real Haiku turn started", started, str(statuses()))
    settle("author turn")
    row = task(tid)
    check(
        "the author completed the task and still holds it",
        row and row["status"] == "completed" and row.get("assignee") == AUTHOR,
        f"{row and row['status']} / {row and row.get('assignee')}",
    )
    api("PATCH", f"/projects/{P}/jobs/{job_id}", {"enabled": False})
    return tid


# --- CHECK 2: the browser --------------------------------------------------------------------


def check2_ui_refusal(tid):
    head("CHECK 2 -- the drawer's status menu, in real Chromium against the served bundle")
    from playwright.sync_api import sync_playwright

    key = aw.require_key()
    seed = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": key, "hubUrl": aw.HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(P)});
"""
    result = {"refusal_text": None, "land_it_present": False, "menu_offered": False}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seed)
        console = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"[:200]))
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"[:200]))
        page.goto(f"{aw.HUB}/?project={P}&tab=tasks", wait_until="domcontentloaded")
        page.wait_for_timeout(3500)

        opener = page.locator(f'[data-testid="task-open-{tid}"]')
        check("the task card is reachable on the board", opener.count() > 0, str(opener.count()))
        if opener.count():
            opener.first.click()
            page.wait_for_timeout(1500)
            drawer = page.locator(f'[data-testid="task-drawer-{tid}"]')
            check("the task drawer opens", drawer.count() > 0)

            trigger = page.locator(f'[data-testid="task-status-menu-{tid}"]')
            check("the status menu trigger is present (completed has legal moves)", trigger.count() > 0)
            if trigger.count():
                trigger.first.click()
                page.wait_for_timeout(600)
                item = page.locator(f'[data-testid="task-status-menu-{tid}-under_review"]')
                result["menu_offered"] = item.count() > 0
                check(
                    "the menu offers 'Move to under review' (the map does not know who authored what)",
                    result["menu_offered"],
                    str(item.count()),
                )
                if item.count():
                    item.first.click()
                    page.wait_for_timeout(2500)

            land_button = page.locator(f'[data-testid="task-land-{tid}"]')
            result["land_it_present"] = land_button.count() > 0
            refusal = page.locator(f'[data-testid="task-status-refusal-{tid}"]')
            if refusal.count():
                result["refusal_text"] = refusal.first.inner_text()
            page.screenshot(path=str(OUT / f"d0916-drawer-{tid}.png"), full_page=True)

        print("  console:")
        for line in console[-10:]:
            print("    " + line)
        browser.close()

    check(
        "the refusal is rendered in the drawer, beside 'Land it'",
        bool(result["refusal_text"]) and result["land_it_present"],
        f"refusal={result['refusal_text']!r} land_it_present={result['land_it_present']}",
    )
    if result["refusal_text"]:
        check(
            "the refusal names the operator remedy (Land it / review_task_id), as the browser session is the operator",
            "Land it" in result["refusal_text"] and "review_task_id" in result["refusal_text"],
            result["refusal_text"],
        )
        check(
            "the refusal names the task and the holder, in D4's own wording",
            f"task {tid}" in result["refusal_text"] and AUTHOR in result["refusal_text"],
            result["refusal_text"],
        )
    return result


# --- CHECK 3: the agent's own tool result --------------------------------------------------------


def chat_entries(agent, conversation_id):
    code, body = api("GET", f"/projects/{P}/agent/{agent}/chat/{conversation_id}")
    if code != 200 or not isinstance(body, dict):
        return []
    return body.get("entries") or []


def check3_agent_turn_refusal(tid):
    head("CHECK 3 -- a real Haiku turn asked to move that same task to under_review itself")
    prompt = (
        f"Use your task tools to move task {tid} to status 'under_review' yourself right now. "
        f"Call update_task with that status. Do not do anything else, and do not ask anyone else "
        f"to do it -- attempt it directly and then stop."
    )
    code, out = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AUTHOR, "message": prompt, "session_mode": "new"},
    )
    check("the trigger was accepted", code in (200, 201, 202), f"{code} {blob(out, 300)}")
    conv = out.get("conversation_id") if isinstance(out, dict) else None
    check("a conversation_id came back", bool(conv), str(conv))
    started = wait_for(lambda: statuses().get(AUTHOR) == "running", 90, f"{AUTHOR} to start")
    check(f"{AUTHOR}'s real Haiku turn started", started, str(statuses()))
    settle("agent self-refusal turn")

    row = task(tid)
    check(
        "the task's status and assignee are unchanged by the refused attempt",
        row and row["status"] == "completed" and row.get("assignee") == AUTHOR,
        f"{row and row['status']} / {row and row.get('assignee')}",
    )

    entries = chat_entries(AUTHOR, conv) if conv else []
    tool_results = [e for e in entries if e.get("output_kind") == "tool_result"]
    note("tool_result entries in this conversation", str(len(tool_results)))
    refusal_text = None
    for e in tool_results:
        payload = e.get("payload") or {}
        text = json.dumps(payload, default=str)
        if "under_review" in text and (
            "does not reassign" in text
            or "None of the task tools" in text
            or "Cannot move task" in text
        ):
            refusal_text = text
            break
    if refusal_text is None:
        # Fall back to any tool_result mentioning the task id, and to the plain entry content.
        for e in tool_results:
            text = json.dumps(e.get("payload") or {}, default=str)
            if tid in text:
                refusal_text = text
                break
    check(
        "a tool_result naming the task carries the guard's refusal",
        bool(refusal_text) and "Cannot move task" in (refusal_text or ""),
        (refusal_text or "no matching tool_result")[:600],
    )
    if refusal_text:
        check(
            "it names the agent remedy, not the operator one -- the actor here is a run, not the operator",
            "None of the task tools you are offered reassigns a task" in refusal_text
            and "Land it" not in refusal_text,
            refusal_text[:600],
        )
    print("  full entries dump (first 20):")
    for e in entries[:20]:
        print(f"    [{e.get('output_kind') or e.get('kind')}] {json.dumps(e.get('payload') or e.get('content'), default=str)[:220]}")
    return refusal_text


def teardown():
    head("TEARDOWN -- leave no job enabled (confirmed by a direct query, not assumed)")
    for jid in set(JOBS):
        code, _ = api("PATCH", f"/projects/{P}/jobs/{jid}", {"enabled": False})
        print(f"  disable {jid} -> {code}")
    code, jobs_now = api("GET", f"/projects/{P}/jobs?include_archived=true")
    left = [j.get("id") for j in (jobs_now if isinstance(jobs_now, list) else []) if j.get("enabled")]
    check("no job left enabled (GET /jobs?include_archived=true)", not left, str(left))


def main():
    try:
        head("SETUP -- a fresh project and repository, one Haiku runner, author + reviewer agents")
        make_project()
        runner = ensure_runner()
        ensure_agent(AUTHOR, runner)
        ensure_agent(REVIEWER, runner)
        roster = statuses()
        check(
            "both agents exist and are idle before anything",
            roster.get(AUTHOR) in ("idle", None) and roster.get(REVIEWER) in ("idle", None),
            str(roster),
        )

        check1_long_title_history()
        tid = setup_self_held_task()
        check2_ui_refusal(tid)
        check3_agent_turn_refusal(tid)
    finally:
        if P:
            teardown()

    head("VERDICT")
    for label, ok, detail in VERDICTS:
        print(f"  {'OK ' if ok else 'BAD'}  {label}" + (f"  -- {detail}" if detail else ""))
    bad = [v for v in VERDICTS if not v[1]]
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)}   project {P} at {ROOT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
