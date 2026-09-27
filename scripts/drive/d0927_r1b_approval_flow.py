"""r1b drive (2026-09-27): a document says how it will be built, and approval starts it. Task 4.2.

Fresh Hub, fresh project, agents author/builder/worker on Haiku. Explore a tiny change-spec with a
real Haiku turn and check the author asks how the work will be built; propose; archive `worker` and
see the stale strip appear in Chromium without reloading; approve choosing `builder`; check the
flow, its next run and the report; confirm the phase bar shows the flow, not Start a flow….
Optional: a second document with delivery mode "none" -> approve -> no flow, pointer text shown.

AW_HUB, AW_KEY, SHOT (screenshot path prefix) must be set. Never :8000/:8010.
"""
import datetime
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, require_hub, require_key  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = require_hub()
KEY = require_key()
assert not HUB.endswith((":8000", ":8010"))
HAIKU = "claude-haiku-4-5-20251001"
TERMINAL = ("completed", "failed", "stopped", "interrupted")

R = []


def v(label, ok, detail=""):
    R.append(ok)
    print("  [%s] %s  %s" % ("OK " if ok else "BAD", label, detail))


def shot(pg, name):
    pg.screenshot(path=os.environ["SHOT"] + name + ".png")


def poll(fn, secs=20, step=1.0):
    for i in range(int(secs / step)):
        if fn():
            return round(i * step, 2)
        time.sleep(step)
    return None


def poll_page(pg, fn, secs=20):
    for i in range(int(secs * 4)):
        if fn():
            return round(i * 0.25, 2)
        pg.wait_for_timeout(250)
    return None


# ---------------------------------------------------------------------------
# Setup: a throwaway project, one runner on Haiku, three agents.
# ---------------------------------------------------------------------------
TAG = time.strftime("%H%M%S")
root = pathlib.Path.home() / "Documents" / ("drive-0927-r1b-" + TAG)
root.mkdir(parents=True)
(root / "README.md").write_text("r1b drive\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "d@example.invalid"],
    ["git", "config", "user.name", "d"],
    ["git", "add", "."],
    ["git", "commit", "-m", "initial"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

c, proj = api("POST", "/projects/open", {"path": str(root), "name": "r1b-" + TAG})
assert c in (200, 201), proj
PID = proj["id"]
A = "/projects/%s" % PID
S = A + "/project"
print("project", PID, root)

c, rn = api("POST", A + "/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
assert c == 201, rn
for n in ("author", "builder", "worker"):
    c, b = api("POST", A + "/agents", {"name": n, "runner_id": rn["id"]})
    assert c == 201, b
print("agents ready: author, builder, worker")

SEED = (
    "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r})); "
    "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, PID)
)


def open_page(browser, url):
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    pg.add_init_script(SEED)
    pg.goto(HUB + url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    return pg


# ---------------------------------------------------------------------------
# Trigger helpers.
# ---------------------------------------------------------------------------
def trigger(agent, message, path, conversation_id=None):
    body = {
        "agent": agent,
        "session_mode": "new",
        "spec_document": path,
        "message": message,
        "overrides": {"permission_mode": "bypassPermissions"},
    }
    if conversation_id:
        body["conversation_id"] = conversation_id
        del body["session_mode"]
    c, t = api("POST", A + "/agent/trigger", body)
    print("  trigger", agent, c, t if not isinstance(t, dict) else {k: t.get(k) for k in ("run_id", "conversation_id")})
    return c, t


def resolve_path(doc_id, fallback_path):
    """A change-spec document's path can change mid-exploration: the author is told to call
    `rename_spec_document` once it knows the subject, then `submit_spec_document` with the renamed
    path (`agents.py`'s tool prose). A harness that keeps using the path a document was *created*
    at 404s every route from here on — this resolves the document's *current* path by its durable
    id instead."""
    c, listing = api("GET", S + "/documents")
    if c == 200 and isinstance(listing, dict):
        for entry in listing.get("documents", []):
            if entry.get("id") == doc_id:
                return entry.get("path", fallback_path)
    return fallback_path


def wait_and_read(agent, run_id, timeout=150):
    """Poll the agent's chat until `run_id` reaches a terminal status; return (status, text)."""
    deadline = time.time() + timeout
    status = "timeout"
    while time.time() < deadline:
        c, chat = api("GET", A + "/agent/%s/chat" % agent)
        if isinstance(chat, dict):
            rf = (chat.get("runs") or {}).get(run_id)
            if rf is not None and rf.get("status") in TERMINAL:
                status = rf.get("status")
                break
        time.sleep(4)
    c, chat = api("GET", A + "/agent/%s/chat" % agent)
    entries = chat.get("entries") or [] if isinstance(chat, dict) else []
    text = "\n".join(
        e.get("content", "")
        for e in entries
        if e.get("run_id") == run_id and e.get("kind") == "agent_output" and e.get("output_kind") == "text"
    )
    return status, text


# ---------------------------------------------------------------------------
# 1. Explore a tiny document with a real Haiku author; check it asks how the
#    work will be built; answer as operator (flow, worker, stop when empty).
# ---------------------------------------------------------------------------
print("\n== 1. explore, real Haiku turns ==")
c, doc = api("POST", S + "/documents", {"title": "Add a CONTRIBUTING line"})
assert c == 201, doc
path = doc["path"]
doc_id = doc["id"]
print("document", path, doc_id)

c, t1 = trigger(
    "author",
    "I want to make a tiny change: add a CONTRIBUTING.md file to this repository with one line "
    "saying pull requests are welcome. Interview me about it before you write anything, the way "
    "the exploring phase asks you to.",
    path,
)
run1 = t1.get("run_id") if isinstance(t1, dict) else None
conv = t1.get("conversation_id") if isinstance(t1, dict) else None
turn1_text = ""
if run1:
    status1, turn1_text = wait_and_read("author", run1)
    print("turn 1 status:", status1)
else:
    print("turn 1: no run_id in response — trigger may have queued instead of running", t1)

print("----- author reply 1 -----")
print(turn1_text[:2000] or "(empty)")
print("-----")

lower1 = turn1_text.lower()
asked_how_built = any(
    kw in lower1
    for kw in ("how it will be built", "how will this be built", "flow", "delivery", "stop when")
)
v("1. author's reply asks how the work will be built", asked_how_built, turn1_text[:300].replace("\n", " | "))

# Answer as operator, in the same conversation, and ask it to submit now.
delivery_via_agent = False
if conv:
    c, t2 = trigger(
        "author",
        "Let's use a flow. Default agent: worker. Stop it when the queue empties. Every 5 minutes "
        "is a fine cadence. Please write the whole document now with submit_spec_document — "
        "requirements, acceptance criteria, one task, and that delivery.",
        path,
        conversation_id=conv,
    )
    run2 = t2.get("run_id") if isinstance(t2, dict) else None
    turn2_text = ""
    if run2:
        status2, turn2_text = wait_and_read("author", run2)
        print("turn 2 status:", status2)
        print("----- author reply 2 -----")
        print(turn2_text[:1500] or "(empty)")
        print("-----")
    else:
        print("turn 2: no run_id in response", t2)
else:
    print("turn 1 produced no conversation_id; skipping the answer turn")

# The author may have renamed the document once it knew the subject (the tool prose tells it to).
# Everything from here on has to use the CURRENT path, not the one the document was created at.
created_path = path
path = resolve_path(doc_id, path)
if path != created_path:
    print("document renamed: %r -> %r" % (created_path, path))

c, spec_after_turns = api("GET", S + "/spec?path=" + path)
delivery_status_after_turns = (
    spec_after_turns.get("delivery_status") if isinstance(spec_after_turns, dict) else None
)
print("delivery_status after Haiku's turns:", delivery_status_after_turns)
delivery_via_agent = bool(delivery_status_after_turns) and delivery_status_after_turns.get("state") != "absent"
v(
    "2. document carries a delivery after the agent's own turns",
    delivery_via_agent,
    str(delivery_status_after_turns),
)

# ---------------------------------------------------------------------------
# Harness fallback: if Haiku did not manage a complete, delivery-bearing
# payload in two turns, seed one directly through the same content route the
# UI's editor uses, so the drive can still reach propose/approve. Recorded
# honestly either way in FINDINGS.md, not silently patched over.
# ---------------------------------------------------------------------------
used_fallback = False
if not delivery_via_agent:
    used_fallback = True
    print("FALLBACK: seeding a complete payload with delivery directly via PUT .../content")
    payload = {
        "schema_version": 1,
        "kind": "change-spec",
        "title": "Add a CONTRIBUTING line",
        "summary": "Add a one-line CONTRIBUTING.md so a new contributor knows pull requests are welcome.",
        "problem": "The repository has no CONTRIBUTING file, so a new contributor does not know pull "
        "requests are welcome.",
        "scope": {"in_scope": ["CONTRIBUTING.md"], "non_goals": ["Any other document"]},
        "requirements": [
            {
                "key": "r1",
                "statement": "The repository MUST contain a CONTRIBUTING.md that says pull requests "
                "are welcome.",
                "modal": "MUST",
            }
        ],
        "acceptance_criteria": [
            {
                "key": "c1",
                "requirement": "r1",
                "given": "the repository",
                "when": "CONTRIBUTING.md is read",
                "then": "it says pull requests are welcome",
            }
        ],
        "tasks": [
            {
                "key": "t1",
                "title": "Add CONTRIBUTING.md",
                "description": "Create CONTRIBUTING.md with one line welcoming pull requests.",
                "requirements": ["r1"],
            }
        ],
        "algorithms": [],
        "design": "",
        "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off",
        "open_questions": [],
        "delivery": {
            "mode": "flow",
            "agent": "worker",
            "stop_when_queue_empties": True,
            "cron": "*/5 * * * *",
        },
    }
    c, b = api("PUT", S + "/documents/%s/content" % path, {"document": payload})
    print("  seeded content:", c, str(b)[:200])
    v("2b. harness fallback wrote a delivery-bearing payload", c == 200, str(c))

# ---------------------------------------------------------------------------
# 2. Close exploration, propose.
# ---------------------------------------------------------------------------
print("\n== 2. close exploration, propose ==")
c, b = api("POST", S + "/documents/close-exploration?path=" + path)
v("3. close-exploration", c == 200, str(c))
c, b = api("POST", S + "/documents/propose?path=" + path)
print("  propose:", c, str(b)[:400])
v("4. propose succeeds with delivery present", c == 200 and (b.get("phase") == "proposed"), str(b)[:300])

# ---------------------------------------------------------------------------
# 3. Chromium: open the document, archive `worker`, see the stale strip
#    appear WITHOUT reloading.
# ---------------------------------------------------------------------------
print("\n== 3. Chromium: stale strip on archive, no reload ==")
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = open_page(browser, "/?project=%s&tab=spec&document=%s" % (PID, path.replace("/", "%2F")))
    shot(pg, "_r1b_1_proposed")
    v(
        "5. no stale strip before archiving worker",
        pg.locator("[data-testid=delivery-stale-strip]").count() == 0,
    )

    c, b = api("POST", A + "/agents/worker/archive")
    v("6. archive worker via API", c == 200, str(c))

    t_stale = poll_page(pg, lambda: pg.locator("[data-testid=delivery-stale-strip]").count() == 1, secs=20)
    strip_text = pg.locator("[data-testid=delivery-stale-strip]").inner_text() if t_stale is not None else ""
    v(
        "7. stale strip appears WITHOUT reloading, naming worker as archived",
        t_stale is not None and "worker" in strip_text and "archived" in strip_text.lower(),
        "after %ss: %r" % (t_stale, strip_text.replace("\n", " | ")),
    )
    shot(pg, "_r1b_2_stale")

    # -----------------------------------------------------------------
    # 4. Choose builder in the strip, Approve.
    # -----------------------------------------------------------------
    print("\n== 4. approve, choosing builder ==")
    choice = pg.locator("[data-testid=delivery-agent-choice]")
    v("8. agent choice select offers builder", "builder" in choice.inner_text())
    choice.select_option("builder")
    pg.get_by_role("button", name="Approve", exact=False).first.click()

    t_report = poll_page(pg, lambda: pg.locator("[data-testid=spec-approval-report]").count() == 1, secs=20)
    v("9. approval report renders", t_report is not None, "after %ss" % t_report)
    shot(pg, "_r1b_3_approved")

    report_text = pg.locator("[data-testid=spec-approval-report]").inner_text() if t_report is not None else ""
    print("report text:", report_text.replace("\n", " | "))
    v(
        "10. report names a flow message mentioning builder",
        pg.locator("[data-testid=approval-flow-message]").count() > 0
        and "builder" in report_text.lower(),
        report_text.replace("\n", " | "),
    )
    v(
        "11. report shows the created task",
        pg.locator("[data-testid=approval-created]").count() == 1,
        pg.locator("[data-testid=approval-created]").inner_text() if pg.locator("[data-testid=approval-created]").count() else "",
    )
    v(
        "12. report carries no 'use Start a flow… above' pointer (a flow was created)",
        pg.locator("[data-testid=approval-start-flow-pointer]").count() == 0,
    )

    t_flow_link = poll_page(pg, lambda: pg.locator("[data-testid=spec-flow-link]").count() == 1, secs=20)
    flow_link_text = pg.locator("[data-testid=spec-flow-link]").inner_text() if t_flow_link is not None else ""
    v(
        "13. phase bar shows Flow: <name>, not Start a flow…",
        t_flow_link is not None
        and pg.locator("[data-testid=spec-start-flow]").count() == 0
        and "Flow:" in flow_link_text,
        "after %ss: %r" % (t_flow_link, flow_link_text),
    )
    shot(pg, "_r1b_4_flow_in_bar")
    browser.close()

# ---------------------------------------------------------------------------
# 4b. Confirm the flow on the Hub side: agent builder, enabled, next_run on
#     the next 5-minute boundary, no run started yet.
# ---------------------------------------------------------------------------
c, loops = api("GET", A + "/loops")
mine = [l for l in loops if l.get("spec_document_id") == doc_id] if isinstance(loops, list) else []
v("14. exactly one loop declares the document", len(mine) == 1, str([(l.get("id"), l.get("agent")) for l in mine]))
loop = mine[0] if mine else {}
v("15. the loop's agent is builder", loop.get("agent") == "builder", str(loop.get("agent")))

c, jobs = api("GET", A + "/jobs")
# `LoopSummary` (the `/loops` shape) carries no `job_id` -- only `JobResponse.loop.spec_document_id`
# ties a job back to its document, so the job is found from that side, not the other.
job = (
    next((j for j in jobs if (j.get("loop") or {}).get("spec_document_id") == doc_id), None)
    if isinstance(jobs, list)
    else None
)
v("16. the flow's job exists and is enabled", bool(job) and job.get("enabled") is True, str(job and job.get("enabled")))
next_run = job.get("next_run") if job else None
v("17. next_run is set (the next cron tick)", bool(next_run), str(next_run))
if next_run:
    nr = datetime.datetime.fromisoformat(next_run.replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    v(
        "18. next_run is within the next ~5 minutes (no immediate firing)",
        now <= nr <= now + datetime.timedelta(minutes=6),
        "next_run=%s now=%s" % (next_run, now.isoformat()),
    )
v("19. no run has started yet", job is not None and (job.get("run_count") in (0, None) and not job.get("last_run")), str(job and (job.get("run_count"), job.get("last_run"))))

c, spec_final = api("GET", S + "/spec?path=" + path)
outcome = spec_final.get("approval_outcome") if isinstance(spec_final, dict) else None
v("20. GET /spec returns approval_outcome with flow state 'created'", bool(outcome) and outcome.get("flow", {}).get("state") == "created", str(outcome and outcome.get("flow")))

# ---------------------------------------------------------------------------
# 5. Optional, cheap (no agent turn): a second document with delivery mode
#    "none" -> approve -> report says no flow, phase bar offers
#    Start a flow…, and the pointer text shows.
# ---------------------------------------------------------------------------
print("\n== 5. optional: a mode-none delivery ==")
c, doc2 = api("POST", S + "/documents", {"title": "Add a SECURITY line"})
path2 = doc2["path"]
payload2 = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "Add a SECURITY line",
    "summary": "Add a one-line SECURITY.md.",
    "problem": "The repository has no SECURITY file.",
    "scope": {"in_scope": ["SECURITY.md"], "non_goals": ["Everything else"]},
    "requirements": [
        {"key": "r1", "statement": "The repository MUST contain a SECURITY.md.", "modal": "MUST"}
    ],
    "acceptance_criteria": [
        {
            "key": "c1",
            "requirement": "r1",
            "given": "the repository",
            "when": "SECURITY.md is read",
            "then": "it exists",
        }
    ],
    "tasks": [
        {
            "key": "t1",
            "title": "Add SECURITY.md",
            "description": "Create SECURITY.md.",
            "requirements": ["r1"],
        }
    ],
    "algorithms": [],
    "design": "",
    "evidence": {"checked": [], "limits": []},
    "lifecycle": "one-off",
    "open_questions": [],
    "delivery": {"mode": "none"},
}
c, b = api("PUT", S + "/documents/%s/content" % path2, {"document": payload2})
v("21. second document seeded with delivery mode none", c == 200, str(c))
api("POST", S + "/documents/close-exploration?path=" + path2)
c, b = api("POST", S + "/documents/propose?path=" + path2)
v("22. second document proposes", c == 200 and b.get("phase") == "proposed", str(b)[:200])

with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = open_page(browser, "/?project=%s&tab=spec&document=%s" % (PID, path2.replace("/", "%2F")))
    pg.get_by_role("button", name="Approve", exact=False).first.click()
    t_report2 = poll_page(pg, lambda: pg.locator("[data-testid=spec-approval-report]").count() == 1, secs=20)
    shot(pg, "_r1b_5_none_report")
    report2_text = pg.locator("[data-testid=spec-approval-report]").inner_text() if t_report2 is not None else ""
    print("second report:", report2_text.replace("\n", " | "))
    v(
        "23. report says no flow was started",
        "no flow" in report2_text.lower(),
        report2_text.replace("\n", " | "),
    )
    v(
        "24. report shows the Start a flow… pointer once",
        pg.locator("[data-testid=approval-start-flow-pointer]").count() == 1,
    )
    v(
        "25. phase bar offers Start a flow… (exactly once)",
        pg.locator("[data-testid=spec-start-flow]").count() == 1,
    )
    browser.close()

c, spec2_final = api("GET", S + "/spec?path=" + path2)
outcome2 = spec2_final.get("approval_outcome") if isinstance(spec2_final, dict) else None
v(
    "26. GET /spec's approval_outcome for doc2 has flow state 'none'",
    bool(outcome2) and outcome2.get("flow", {}).get("state") == "none",
    str(outcome2 and outcome2.get("flow")),
)

# ---------------------------------------------------------------------------
# Teardown: disable/archive every job in this profile.
# ---------------------------------------------------------------------------
print("\n== teardown ==")
c, jobs = api("GET", A + "/jobs")
for j in jobs if isinstance(jobs, list) else []:
    if j.get("enabled"):
        cc, bb = api("PATCH", A + "/jobs/" + j["id"], {"enabled": False})
        print("  disabled job", j["id"], cc)
    cc, bb = api("POST", A + "/jobs/%s/archive" % j["id"])
    print("  archived job", j["id"], cc)

print("\nRESULT %d/%d  fallback_used=%s" % (sum(R), len(R), used_fallback))
