"""D-1 2026-09-13, priority 2: render what the operator SEES for F335, the review 409, and F333.

The night (2026-09-12) left three things read in the component and never rendered:

  F335  `run_divergence_resolved` is broadcast at staging time, so a review refused on dispatch
        still puts "1 open divergence on T resolved" in the live activity feed
        (`hub/ui/src/lib/eventSummary.ts:142`), and a reload drops it.
  409   a-refused-review-leaves-nothing-behind human-only 6.1 / test-guide check 1: "Dispatch a
        review from the UI" on a task whose commit was pruned -- what does the dispatch control show?
  F333  a Continue whose pass gives up the conversation's review answers "this conversation had
        nothing queued" (`AgentOutputPanel.tsx:759-769`).

Phases, by argv (default D and F): `D` = F335 + the 409 on the operator route, `Q` = F335 on a
review queued behind the reviewer's own turn and refused at delivery, `F` = F333. Real routes and the served bundle
only, no row inserts, Haiku turns, no job created. The drive database is read read-only for state.

    AW_HUB=http://127.0.0.1:80NN AW_KEY=... AW_DB=<path> AW_DRIVE_DIR=%TEMP%\\d1_0913\\render \
        SHOTDIR=... py -3.11 scripts/drive/t_d1_0913_render.py [D] [F]
"""

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import HUB, api, require_key  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the trial Hub.")
    sys.exit(1)

KEY = require_key()
DB = os.environ["AW_DB"]
BASE = pathlib.Path(os.environ["AW_DRIVE_DIR"]).resolve()
SHOTDIR = pathlib.Path(os.environ.get("SHOTDIR", str(BASE / "shots")))
SHOTDIR.mkdir(parents=True, exist_ok=True)
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
PHASES = {a.upper() for a in sys.argv[1:]} or {"D", "F"}
WK, RV, AU = f"wk{TAG}", f"rv{TAG}", f"au{TAG}"

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(("  ok   " if cond else "  FAIL ") + label + (f"  -- {detail}" if detail else ""))
    return bool(cond)


def note(label, value):
    print(f"  .. {label}: {value}")


def rows(sql, *args):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


# ---------------------------------------------------------------- fixture
ROOT = BASE / "proj"
if ROOT.exists():
    sys.exit(f"{ROOT} already exists -- a drive needs a fresh fixture")
ROOT.mkdir(parents=True)
(ROOT / "README.md").write_text(f"render drive fixture {TAG}\n", encoding="utf-8")
(ROOT / "slow_step.py").write_text(
    'import time\n\ntime.sleep(60)\nprint("slow step finished")\n', encoding="utf-8"
)


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {args} failed: {r.stderr}")
    return r.stdout.strip(), r.returncode


git("init", "-b", "main")
git("config", "user.email", "render@example.invalid")
git("config", "user.name", "render")
git("add", "README.md", "slow_step.py")
git("commit", "-q", "-m", "render drive fixture")
HEAD, _ = git("rev-parse", "HEAD")

c, proj = api("POST", "/projects/open", {"path": str(ROOT), "name": f"render-{TAG}"})
assert c in (200, 201), (c, proj)
P = proj["id"]
A = f"/projects/{P}/project"
note("project", P)
c, runner = api("POST", f"/projects/{P}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU})
assert c in (200, 201), (c, runner)
for name in (WK, RV, AU):
    c, b = api("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner["id"]})
    assert c in (200, 201), (c, b)
    api("PATCH", f"/projects/{P}/agents/{name}", {"default_permission_mode": "bypassPermissions"})


def payload(keys):
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": "d0913 render",
        "summary": "A driven fixture document for D-1 2026-09-13, complete enough to approve.",
        "problem": "The renders need requirements that evidence can name.",
        "scope": {"in_scope": ["Review dispatch"], "non_goals": ["Anything real"]},
        "requirements": [
            {
                "key": k,
                "statement": f"The subject MUST satisfy condition {k} exactly as stated here.",
                "modal": "MUST",
                "rationale": f"Condition {k} is silent when violated, so it needs stating.",
            }
            for k in keys
        ],
        "acceptance_criteria": [
            {
                "key": f"ac-{k}",
                "requirement": k,
                "given": "a fixture project",
                "when": f"condition {k} is exercised",
                "then": f"the behaviour matches {k}",
            }
            for k in keys
        ],
        "tasks": [
            {
                "key": f"t-{k}",
                "title": f"Satisfy condition {k}",
                "description": f"Implement condition {k}, covering ac-{k} with a named test.",
                "requirements": [k],
                "reviewer": "critic",
            }
            for k in keys
        ],
        "design": "Each condition is local to its own function.",
        "evidence": {"checked": ["Nothing, fixture"], "limits": ["Describes no software"]},
        "lifecycle": "Deleted with the fixture.",
        "open_questions": [],
    }


DOC = f"spec/changes/d0913-{TAG}/spec.html"
c, b = api("POST", f"{A}/documents", {"path": DOC, "title": f"d0913 {TAG}"})
assert c == 201, (c, b)
c, b = api("PUT", f"{A}/documents/{DOC}/content", {"document": payload(["fr-1", "fr-2"])})
assert c in (200, 201), (c, str(b)[:300])
IDS = b.get("identifiers") or {}
assert api("POST", f"{A}/documents/close-exploration?path={DOC}")[0] == 200
c, b = api("POST", f"{A}/documents/propose?path={DOC}")
assert c == 200 and not b.get("blocking"), (c, str(b)[:300])
assert api("POST", f"{A}/documents/phase?path={DOC}&to=approved", {"reason": ""})[0] == 200


def evidence(tid, identifier, locator, summary):
    c, ev = api(
        "POST",
        f"{A}/spec/evidence",
        {
            "identifier": identifier,
            "document": DOC,
            "task_id": tid,
            "kind": "manual_observation",
            "locator": locator,
            "summary": summary,
        },
    )
    assert c == 201, (c, str(ev)[:300])
    return ev


def runs_of(agent):
    return rows(
        "select id, status, task_id, conversation_id from runs where project_id=? and agent=? "
        "order by started_at",
        P,
        agent,
    )


def wait_running(agent, limit=60):
    t0 = time.time()
    while time.time() - t0 < limit:
        if any(r["status"] == "running" for r in runs_of(agent)):
            return True
        time.sleep(1)
    return False


def wait_idle(agent, limit=420):
    t0 = time.time()
    while time.time() - t0 < limit:
        if not any(r["status"] == "running" for r in runs_of(agent)):
            return True
        time.sleep(5)
    return False


def task_row(tid):
    return rows("select status, assignee from tasks where id=?", tid)[0]


def entry(eid):
    return rows(
        "select id, state, conversation_id, delivery_attempts, waiting_reason, abandoned_reason "
        "from inbound_queue_entries where id=?",
        eid,
    )[0]


def dispatch_review(agent, tid):
    return api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": agent,
            "review_task_id": tid,
            "message": f"Review task {tid}. Reply with one sentence and call no tool.",
        },
        timeout=90,
    )


SLOW_STEP = (
    "1) Run the command `python slow_step.py` in your workspace and wait for it to finish; it "
    "takes about a minute and prints 'slow step finished'. "
)
SEED = f"""
sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {P!r});
"""


def open_tab(page, name):
    loc = page.get_by_role("button", name=name, exact=True)
    if not loc.count():
        loc = page.get_by_text(name, exact=True)
    if loc.count():
        loc.first.click()
        page.wait_for_timeout(2500)
        return True
    return False


# ================================================================ D: F335 and the 409
if "D" in PHASES:
    print("\n=== D: a completed task with an open divergence and a pruned commit; a review refused")
    c, t = api(
        "POST",
        f"/projects/{P}/tasks",
        {"title": f"D {TAG}", "description": f"D {TAG}", "requirements": [IDS["fr-1"]]},
    )
    assert c in (200, 201), (c, t)
    TD = t["id"]
    # The card's "Start work" path: a trigger carrying task_id binds the run and moves the task.
    c, b = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": WK,
            "task_id": TD,
            "message": "Do exactly these two steps and nothing else. " + SLOW_STEP
            + "2) Reply with the single word done. Call no agentweave tool; do not call update_task.",
        },
        timeout=90,
    )
    note("worker trigger bound to TD", f"{c} {str(b)[:200]}")
    ok("the worker's bound run is running", wait_running(WK))
    note("TD while the run runs", task_row(TD))
    c, b = api("PATCH", f"/projects/{P}/tasks/{TD}", {"status": "completed"})
    ok("the operator completes TD while the bound run is still running", c == 200, f"{c} {str(b)[:200]}")
    ok("the worker's run ends", wait_idle(WK))
    time.sleep(3)
    c, divs = api("GET", f"/projects/{P}/tasks/divergences/recent?open_only=true")
    mine = [d for d in (divs or []) if d.get("task_id") == TD]
    note("open divergences on TD", json.dumps(mine)[:400])
    ok("TD carries an open divergence", bool(mine) and mine[0].get("resolved_at") is None)
    git("checkout", "-q", "-b", f"gone-{TAG}")
    git("commit", "-q", "--allow-empty", "-m", f"d0913 {TAG} a commit that will be pruned")
    GONE, _ = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    ev = evidence(TD, IDS["fr-1"], GONE, "operator observed D")
    ok("operator evidence is footprinted at the side commit", (ev.get("footprint") or {}).get("commit_sha") == GONE)
    git("branch", "-q", "-D", f"gone-{TAG}")
    git("reflog", "expire", "--expire=now", "--all")
    git("gc", "-q", "--prune=now")
    ok("the commit is gone", git("cat-file", "-e", GONE, check=False)[1] != 0)
    before = task_row(TD)
    note("TD before the dispatch", before)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(SEED)
        page.goto(HUB, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        ok("the Activity tab opens", open_tab(page, "Activity"))
        page.screenshot(path=str(SHOTDIR / f"d-{TAG}-1-activity-before.png"), full_page=True)
        line = f"open divergence on {TD} resolved"
        before_count = page.inner_text("body").count(line)
        note("feed lines naming the resolution before the dispatch", before_count)

        c, b = dispatch_review(RV, TD)
        detail = b.get("detail") if isinstance(b, dict) else b
        note("POST /agent/trigger review_task_id=TD", f"{c} {str(b)[:400]}")
        ok("the review is refused with a 409", c == 409, str(c))
        ok("... naming the missing commit", "not present in this repository" in str(detail), str(detail)[:200])
        page.wait_for_timeout(4000)
        page.screenshot(path=str(SHOTDIR / f"d-{TAG}-2-activity-after-refusal.png"), full_page=True)
        live_text = page.inner_text("body")
        live_count = live_text.count(line)
        note("feed lines naming the resolution after the refusal (live)", live_count)
        for ln in live_text.splitlines():
            if TD in ln:
                note("feed line naming TD", ln[:200])
        c, divs = api("GET", f"/projects/{P}/tasks/divergences/recent?open_only=true")
        still_open = [d for d in (divs or []) if d.get("task_id") == TD]
        ok("TD's divergence is still open after the refusal (durable record is true)", bool(still_open))
        resolved_rows = rows(
            "select id from event_logs where project_id=? and event_type='run_divergence_resolved'", P
        )
        ok("no run_divergence_resolved event row was written", not resolved_rows, str(resolved_rows))
        ok("TD equals its before-dispatch row", task_row(TD) == before, f"{before} -> {task_row(TD)}")
        # First run (09:4x) asserted the opposite and FAILED: the route's 409 comes from
        # `review_dispatch_refusal` before anything is staged, so there is no broadcast to render.
        ok(
            "the route's 409 puts no false 'resolved' line in the feed (refused before staging)",
            live_count == before_count,
            f"before={before_count} after={live_count}",
        )

        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        open_tab(page, "Activity")
        page.screenshot(path=str(SHOTDIR / f"d-{TAG}-3-activity-after-reload.png"), full_page=True)
        reload_count = page.inner_text("body").count(line)
        ok("F335: a reload drops the line", reload_count == 0, f"after reload={reload_count}")

        # The 409, where the operator would look for it. The UI has no control that sends
        # review_task_id; the only per-task agent control is the card's "Start work" menu.
        ok("the Tasks tab opens", open_tab(page, "Tasks"))
        page.screenshot(path=str(SHOTDIR / f"d-{TAG}-4-board.png"), full_page=True)
        card = page.locator(f'[aria-label="Open D {TAG}"]').first.locator("xpath=..")
        note("TD card text", card.inner_text()[:300].replace("\n", " | ") if card.count() else "ABSENT")
        menu = page.locator(f"[data-testid='task-start-work-{TD}']")
        note("TD start-work menu present", menu.count())
        items = []
        if menu.count():
            menu.first.click()
            page.wait_for_timeout(800)
            items = page.get_by_role("menuitem").all_inner_texts()
            note("TD start-work menu items", items)
            page.screenshot(path=str(SHOTDIR / f"d-{TAG}-5-start-work-menu.png"), full_page=True)
            page.keyboard.press("Escape")
        ok(
            "no menu item offers a review",
            not any("review" in i.lower() for i in items),
            str(items),
        )
        br.close()

# ================================================================ Q: F335 on the path it lives on
# Phase D showed the operator route answers a pruned commit from `review_dispatch_refusal`
# (`agent_trigger.py:1461`) BEFORE anything is staged, so no broadcast. The staging -- and the
# broadcast -- happen only at delivery: a review queued behind the reviewer's own turn, whose commit
# is pruned while it waits, is staged by the run-end re-drain and then refused.
if "Q" in PHASES:
    print("\n=== Q: a review QUEUED behind the reviewer's turn, its commit pruned while it waits")
    c, t = api(
        "POST",
        f"/projects/{P}/tasks",
        {"title": f"Q {TAG}", "description": f"Q {TAG}", "requirements": [IDS["fr-1"]]},
    )
    assert c in (200, 201), (c, t)
    TQ = t["id"]
    c, b = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": WK,
            "task_id": TQ,
            "message": "Do exactly these two steps and nothing else. " + SLOW_STEP
            + "2) Reply with the single word done. Call no agentweave tool; do not call update_task.",
        },
        timeout=90,
    )
    ok("the worker's bound run is running", wait_running(WK))
    c, b = api("PATCH", f"/projects/{P}/tasks/{TQ}", {"status": "completed"})
    ok("the operator completes TQ while the bound run runs", c == 200, str(c))
    git("checkout", "-q", "-b", f"soon-{TAG}")
    git("commit", "-q", "--allow-empty", "-m", f"d0913 {TAG} a commit pruned while the review waits")
    SOON, _ = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    evidence(TQ, IDS["fr-1"], SOON, "operator observed Q")
    ok("the worker's run ends", wait_idle(WK))
    time.sleep(3)
    c, divs = api("GET", f"/projects/{P}/tasks/divergences/recent?open_only=true")
    ok("TQ carries an open divergence", any(d.get("task_id") == TQ for d in (divs or [])))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(SEED)
        page.goto(HUB, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        ok("the Activity tab opens", open_tab(page, "Activity"))
        line = f"open divergence on {TQ} resolved"
        c, b = api(
            "POST",
            f"/projects/{P}/agent/trigger",
            {"agent": RV, "message": "Do exactly this and nothing else. " + SLOW_STEP + "2) Reply done."},
            timeout=90,
        )
        ok("the reviewer's own turn is running", wait_running(RV))
        c, q = dispatch_review(RV, TQ)
        note("review of TQ while the reviewer is busy", f"{c} {str(q)[:300]}")
        ok("the review is answered 200 queued (the commit exists)", c == 200 and q.get("status") == "queued", f"{c} {q}")
        QE = q.get("queue_entry_id")
        git("branch", "-q", "-D", f"soon-{TAG}")
        git("reflog", "expire", "--expire=now", "--all")
        git("gc", "-q", "--prune=now")
        ok("the commit is pruned while the review waits", git("cat-file", "-e", SOON, check=False)[1] != 0)
        live_before = page.inner_text("body").count(line)
        ok("the reviewer's turn ends", wait_idle(RV))
        page.wait_for_timeout(8000)
        e = entry(QE)
        note("the queued review after the run-end re-drain", json.dumps(e, default=str))
        ok(
            "the delivery refused it for the missing commit",
            e["state"] == "queued" and "not present in this repository" in (e["waiting_reason"] or ""),
            json.dumps(e, default=str),
        )
        page.screenshot(path=str(SHOTDIR / f"q-{TAG}-1-activity-after-delivery-refusal.png"), full_page=True)
        body = page.inner_text("body")
        live_after = body.count(line)
        for ln in body.splitlines():
            if TQ in ln or "divergence" in ln:
                note("feed line", ln[:200])
        c, divs = api("GET", f"/projects/{P}/tasks/divergences/recent?open_only=true")
        ok("TQ's divergence is still open", any(d.get("task_id") == TQ for d in (divs or [])))
        ok(
            "no run_divergence_resolved event row",
            not rows("select id from event_logs where project_id=? and event_type='run_divergence_resolved'", P),
        )
        # Measured 2026-09-13: the broadcast IS sent (curl on /api/v1/events captured it), and the
        # feed drops it, because `run_divergence_resolved` is not in `useSSE.ts`'s allowlist (F251).
        # This check is the tripwire for fixing F251 without F335: it fails the day the false line
        # starts rendering.
        ok(
            "no false 'resolved' line renders (F335 latent behind F251's allowlist)",
            live_after == live_before,
            f"before={live_before} after={live_after}",
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        open_tab(page, "Activity")
        page.screenshot(path=str(SHOTDIR / f"q-{TAG}-2-activity-after-reload.png"), full_page=True)
        ok("F335: a reload drops the line", page.inner_text("body").count(line) == 0)
        br.close()
    # Leave the refused entry to be given up on, as the product does; withdraw it so nothing waits.
    c, b = api("POST", f"/projects/{P}/conversations/{q.get('conversation_id')}/continue", timeout=90)
    note("continue (drains the refused review toward its give-up)", f"{c} {json.dumps(b)[:200]}")

# ================================================================ F: F333
if "F" in PHASES:
    print("\n=== F: F333 -- Continue in the UI on a conversation whose review the pass gives up")
    t0 = time.time()
    while time.time() - t0 < 420 and rows("select id from runs where project_id=? and status='running'", P):
        time.sleep(5)
    ok("nothing is running in the project before F", not rows("select id from runs where project_id=? and status='running'", P))
    c, t = api(
        "POST",
        f"/projects/{P}/tasks",
        {"title": f"F {TAG}", "description": f"F {TAG}", "requirements": [IDS["fr-2"]]},
    )
    assert c in (200, 201), (c, t)
    TF = t["id"]
    evidence(TF, IDS["fr-2"], HEAD, "operator observed F")
    for to in ("in_progress", "completed"):
        c, b = api("PATCH", f"/projects/{P}/tasks/{TF}", {"status": to})
        assert c == 200, (to, c, b)
    c, b = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AU,
            "message": (
                "Do exactly these three steps and nothing else. "
                + SLOW_STEP
                + "2) Call the tool mcp__agentweave__record_evidence with "
                f"identifier='{IDS['fr-2']}', document='{DOC}', task_id='{TF}', "
                "kind='manual_observation', locator='README.md', summary='README exists'. "
                "3) Reply with the single word done. Do not call update_task."
            ),
        },
        timeout=90,
    )
    note("1. X's turn", f"{c} {str(b)[:200]}")
    ok("X's turn is running", wait_running(AU))
    c, h = dispatch_review(AU, TF)
    note("2. H, a review of TF naming X", f"{c} {str(h)[:300]}")
    ok("H is answered 200 queued", c == 200 and h.get("status") == "queued", f"{c} {h}")
    c, m = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AU, "message": "Reply with the single word pong. Call no tool."},
        timeout=90,
    )
    note("3. M, plain", f"{c} {str(m)[:300]}")
    ok("M is answered 200 queued", c == 200 and m.get("status") == "queued", f"{c} {m}")
    H, HC = h.get("queue_entry_id"), h.get("conversation_id")
    M, MC = m.get("queue_entry_id"), m.get("conversation_id")
    ok("H and M are in different conversations", HC != MC, f"{HC} {MC}")
    ok("4. X's turn ends", wait_idle(AU))
    time.sleep(5)
    became_author = any(
        r["actor_kind"] == "agent" and r["actor"] == AU
        for r in rows("select actor_kind, actor from requirement_evidence where task_id=?", TF)
    )
    ok("X recorded evidence for TF (Haiku acted)", became_author)
    note("H after the run-end re-drain", json.dumps(entry(H), default=str))
    # Bring H to 2 attempts over the API, so the UI's Continue is the pass that gives it up.
    for _ in range(3):
        if entry(H)["delivery_attempts"] >= 2 or entry(H)["state"] != "queued":
            break
        c, r = api("POST", f"/projects/{P}/conversations/{HC}/continue", timeout=90)
        note("API continue on H's conversation", f"{c} {json.dumps(r)}")
    e = entry(H)
    note("H before the UI Continue", json.dumps(e, default=str))
    ok("H is queued at 2 attempts", e["state"] == "queued" and e["delivery_attempts"] == 2, json.dumps(e, default=str))
    ok("M is still queued", entry(M)["state"] == "queued", json.dumps(entry(M), default=str))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(SEED)
        requests = []
        page.on("response", lambda r: requests.append((r.request.method, r.url, r.status)) if "/continue" in r.url else None)
        page.goto(HUB, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.locator(f"text={AU}").first.click()
        page.wait_for_timeout(1500)
        exp = page.locator(f"[data-testid='agent-expander-{P}-{AU}']")
        if exp.count():
            exp.first.click()
            page.wait_for_timeout(2000)
        target = page.locator(f"[data-testid='rail-conversation-{HC}']")
        ok("the rail carries H's conversation", target.count() > 0)
        if target.count():
            target.first.click()
            page.wait_for_timeout(3500)
        page.screenshot(path=str(SHOTDIR / f"f-{TAG}-1-conversation-before.png"), full_page=True)
        btn = page.locator("[data-testid='conversation-continue']")
        ok("the Continue control is shown on H's conversation", btn.count() > 0)
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(4000)
        page.screenshot(path=str(SHOTDIR / f"f-{TAG}-2-after-continue.png"), full_page=True)
        notice = page.locator("[data-testid='session-continuity']")
        text = notice.first.inner_text() if notice.count() else ""
        note("the notice the operator reads", repr(text))
        note("continue responses", requests)
        e = entry(H)
        note("H after the UI Continue", json.dumps(e, default=str))
        note("M after the UI Continue", json.dumps(entry(M), default=str))
        ok("the UI's Continue gave H up", e["state"] != "queued", json.dumps(e, default=str))
        ok(
            "F333 RENDERED: the operator is told the conversation 'had nothing queued'",
            "had nothing queued" in text,
            repr(text),
        )
        ok("... and that another conversation started instead", "started instead" in text, repr(text))
        ok(
            "... and the refusal that caused the give-up is not in the notice",
            "recorded evidence for this task" not in text,
            repr(text),
        )
        br.close()
    ok("M's turn ends", wait_idle(AU))

print(f"\n{len(PASS)} ok, {len(FAIL)} fail  shots in {SHOTDIR}")
sys.exit(1 if FAIL else 0)
