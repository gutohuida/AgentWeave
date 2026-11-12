"""Acceptance drive for `where-each-task-stands-is-visible-on-the-board` WETSV-1 (FR-9, 10, 11, 14,
15, 16): one true stage per card, read from real state, with its time at stage and what it waits on.

Starts its own Hub from source on :8112 with a fresh database (never :8000 or :8010), from the
checkout named by `--root` (default: this one), so the same script runs on the pre-build commit for
the baseline and on the build for the pass. Every check prints one line

    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>

`reached` is whether the drive got the situation set up and could look; `failed_at_assertion` is
whether the behaviour was then absent. Rows the Hub only writes from inside (landings, bound runs,
questions, prerequisites) are seeded through the models; the card is read in a real Chromium; the
ac-live landing is the Hub's own: an approved task with a real branch lands on main.

    py -3.11 scripts/drive/dwetsv1_stage_on_card.py [--root PATH] [--skip-wait]
"""

import argparse
import pathlib
import tempfile
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ap = argparse.ArgumentParser()
ap.add_argument("--root", default=str(HERE.parents[1]))
ap.add_argument("--skip-wait", action="store_true", help="skip the two-minute ac-time-advances wait")
ARGS = ap.parse_args()
ROOT = pathlib.Path(ARGS.root).resolve()

import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8112
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.REPO = ROOT
d.TMP = pathlib.Path(tempfile.gettempdir()) / "dwetsv1" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"

sys.path.insert(0, str(ROOT / "hub"))
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from hub.db.models import Question, Run, Task, TaskDependency, TaskLanding  # noqa: E402

LINES = []
_n = iter(range(1, 10_000))


def line(key, reached, failed, detail):
    LINES.append(f"check {key}: reached={'yes' if reached else 'no'} "
                 f"failed_at_assertion={'yes' if failed else 'no'} -- {detail}")
    print(LINES[-1], flush=True)


def seed(pid, *rows):
    eng = create_engine(f"sqlite:///{d.DB.as_posix()}")
    with Session(eng) as s:
        s.add_all(rows)
        s.commit()
    eng.dispose()


def task(pid, title, status, **kw):
    n = next(_n)
    tid = f"task-wd-{n}"
    seed(pid, Task(id=tid, project_id=pid, title=title, status=status, **kw))
    return tid


def landing(pid, tid, state, **kw):
    n = next(_n)
    seed(pid, TaskLanding(id=f"landing-wd-{n}", project_id=pid, task_id=tid, state=state,
                          order_key=float(n), **kw))


def routerow(pid, tid):
    code, body = d.api("GET", f"/projects/{pid}/tasks")
    rows = [t for t in body["tasks"] if t["id"] == tid] if code == 200 else []
    return rows[0] if rows else {}


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "wetsv1"})
    assert code in (200, 201), (code, project)
    pid = project["id"]

    now = datetime.now(timezone.utc)
    # One task in each stage the board has to tell apart.
    t = {}
    t["not_started"] = task(pid, "stage not started", "pending")
    t["working"] = task(pid, "stage working", "in_progress", assignee="D")
    t["bystander"] = task(pid, "stage bystander", "assigned", assignee="D")  # D runs on `working`
    seed(pid, Run(id=f"run-wd-{next(_n)}", project_id=pid, agent="D", status="running",
                  task_id=t["working"]))
    t["asking"] = task(pid, "stage asking", "in_progress", assignee="A")
    seed(pid, Question(id=f"q-wd-{next(_n)}", project_id=pid, from_agent="Q", question="which?",
                       blocking=True, blocked_task_id=t["asking"]))
    t["prereq"] = task(pid, "stage prereq", "in_progress", readable_id="AW-7")
    t["gated"] = task(pid, "stage gated", "pending")
    seed(pid, TaskDependency(id=f"dep-wd-{next(_n)}", project_id=pid, task_id=t["gated"],
                             depends_on_task_id=t["prereq"]))
    t["review"] = task(pid, "stage review", "completed", updated=now - timedelta(days=2))
    t["under_review"] = task(pid, "stage under review", "under_review")
    t["sent_back"] = task(pid, "stage sent back", "revision_needed")
    t["approved"] = task(pid, "stage approved", "approved")
    t["checking"] = task(pid, "stage checking", "approved")
    landing(pid, t["checking"], "checking")
    t["landed"] = task(pid, "stage landed", "approved")
    landing(pid, t["landed"], "landed", landed_sha="abcdef1234567890")
    t["held"] = task(pid, "stage held", "approved")
    landing(pid, t["held"], "held", reason="check lint is failing")
    t["notlanded"] = task(pid, "stage not landed", "approved")
    landing(pid, t["notlanded"], "not_landed", reason="the checkout has uncommitted changes")
    t["closed"] = task(pid, "stage closed", "rejected")
    # A fresh one for the advance check, entered a minute and a half ago.
    t["fresh"] = task(pid, "stage fresh", "completed", updated=now - timedelta(seconds=90))
    # The task for ac-live is created through the Hub, with a real branch it can land.
    code, made = d.api("POST", f"/projects/{pid}/tasks", {"title": "live landing"})
    assert code in (200, 201), (code, made)
    live = made["id"]

    rows = {k: routerow(pid, v) for k, v in t.items()}

    # ---- route-level checks
    reached = bool(rows["checking"])
    line("ac-approved-not-on-main", reached, rows["checking"].get("stage") != "checking",
         f"approved task with a checking landing reads stage={rows['checking'].get('stage')!r}")
    line("ac-working-only-bound", reached,
         not (rows["working"].get("stage") == "working"
              and rows["bystander"].get("stage") == "not_started"),
         f"bound={rows['working'].get('stage')!r} bystander={rows['bystander'].get('stage')!r}")

    # ---- the board in a real browser
    seedjs = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
              "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seedjs)
        page.goto(f"{d.HUB}/?project={pid}", wait_until="domcontentloaded")
        page.get_by_test_id("project-tab-tasks").first.click()
        board = d.poll(lambda: page.get_by_test_id(f"task-open-{t['review']}").count() >= 1, 30)

        def stage_text(tid):
            loc = page.get_by_test_id(f"task-stage-{tid}")
            return loc.first.inner_text() if loc.count() else ""

        def one(tid):  # the stage chips inside this card
            return page.get_by_test_id(f"task-open-{tid}").locator("[data-testid^='task-stage-']:not([data-testid*='-detail-']):not([data-testid*='-age-']):not([data-testid*='-waits-'])").count()

        texts = {k: stage_text(v) for k, v in t.items()}
        distinct = len({texts[k] for k in ("not_started", "working", "review", "under_review", "sent_back", "approved", "checking", "landed", "held", "notlanded", "asking")})
        line("ac-every-stage", board, not (distinct == 11 and all(one(t[k]) == 1 for k in texts if k != "closed")),
             f"{distinct}/11 distinct stage labels; sample={ {k: texts[k][:28] for k in ('working','checking','landed')} }")
        line("ac-detail", board,
             not ("abcdef1" in texts["landed"] and "lint" in
                  (page.get_by_test_id(f"task-stage-waits-on-{t['held']}").inner_text()
                   if page.get_by_test_id(f"task-stage-waits-on-{t['held']}").count() else "")
                  and "uncommitted" in texts["notlanded"]),
             f"landed={texts['landed'][:40]!r} held-waits={page.get_by_test_id('task-stage-waits-on-' + t['held']).count()} notlanded={texts['notlanded'][:60]!r}")
        age = lambda k: (page.get_by_test_id(f"task-stage-age-{t[k]}").inner_text()  # noqa: E731
                         if page.get_by_test_id(f"task-stage-age-{t[k]}").count() else "")
        line("ac-time-at-stage", board,
             not (bool(rows["checking"].get("stage_since")) and "2 days" in age("review")
                  and ("min" in age("checking") or "now" in age("checking"))),
             f"route stage_since={rows['checking'].get('stage_since')!r}; review card={age('review')!r}")

        def waits(k):
            loc = page.get_by_test_id(f"task-stage-waits-on-{t[k]}")
            return loc.first.inner_text() if loc.count() else ""

        line("ac-waits-on", board,
             not ("Q" in waits("asking") and "AW-7" in waits("gated") and waits("working") == ""),
             f"asking={waits('asking')!r} gated={waits('gated')!r} working={waits('working')!r}")

        # ac-time-advances: the 90-second-old card reads 1 min; two minutes later 3 min, no reload.
        first = age("fresh").strip(" ·")
        if ARGS.skip_wait:
            line("ac-time-advances", board, True, "skipped (--skip-wait)")
        else:
            time.sleep(125)
            second = age("fresh").strip(" ·")
            line("ac-time-advances", board and first == "1 min", not (first == "1 min" and second == "3 min"),
                 f"before={first!r} after two minutes, no reload={second!r}")

        # ac-live: approve a task with a real branch; its card must read On main within 5 s.
        branch = f"agentweave/task/{live}"
        d.git(root, "checkout", "-q", "-b", branch)
        (root / "live.txt").write_text("live\n", encoding="utf-8")
        d.git(root, "add", "live.txt")
        d.git(root, "commit", "-q", "-m", "live work")
        d.git(root, "checkout", "-q", "main")
        page.reload(wait_until="domcontentloaded")
        page.get_by_test_id("project-tab-tasks").first.click()
        d.poll(lambda: page.get_by_test_id(f"task-open-{live}").count() >= 1, 30)
        for step in ("in_progress", "completed", "under_review"):
            code, out = d.api("PATCH", f"/projects/{pid}/tasks/{live}", {"status": step})
            print("  step", step, code, str(out)[:150] if code != 200 else "")
        code, out = d.api("PATCH", f"/projects/{pid}/tasks/{live}", {"status": "approved"})
        t0 = time.time()
        got = d.poll(lambda: "on main" in stage_text(live).lower(), 5)
        elapsed = time.time() - t0
        row = routerow(pid, live)
        line("ac-live", out is not None and code in (200, 201), not got,
             f"approve->{code} {str(out)[:200]}; card={stage_text(live)[:40]!r} after {elapsed:.1f}s, route stage={row.get('stage')!r}; "
             "not-on-main count is WETSV-2's, not shown by this task")
        page.screenshot(path=str(d.TMP / "board.png"), full_page=True)
        browser.close()


d.drive = drive

if __name__ == "__main__":
    try:
        d.main()
    finally:
        print("\n".join(LINES))
