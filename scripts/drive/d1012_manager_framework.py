"""Acceptance drive for the knowledge vault roadmap's `manager-framework` slice, 2026-10-09.

The slice's `drive` criterion (spec/changes/the-hubs-background-jobs-are-configured-on-a-manager-page/).
Starts its own Hub on :8099 with a fresh database (never :8000 or :8010), serving the bundle built
into hub/hub/static/ui, opens a project with a Haiku agent and a second runner whose model is
Sonnet 5, and checks, in order:

  1. GET /manager/jobs answers 200 with conversation-titles first, disabled, nothing chosen;
  2. PATCH /manager/jobs/conversation-titles {enabled, runner_id: the Sonnet runner, model: Haiku}
     answers 200 with the job as sent; GET /settings reports conversation_title_mode "generate" and
     that runner (the compatibility mapping);
  3. a turn in a new conversation with a short message ends, and within 90 s GET /manager/activity
     holds one conversation-titles firing for that conversation: outcome "written", the Sonnet
     runner, model Haiku, no agent field, a duration; the conversation's title is the firing's
     detail and differs from the message; exactly one Run row exists for that conversation;
  4. with the job disabled, a second conversation keeps its message as its title and gets no firing;
  5. in Chromium, Environment > Manager shows the job and at least one firing, and Environment >
     Settings shows no "Conversation title runner" control.

Haiku does the titling even though the runner's model is Sonnet: the job's model wins, which is the
point of check 3, and keeps the drive's spend on Haiku.

Fails on today's Hub at check 1 (no /manager route). Stops at the first failure, so a red run spends
no agent turn. Run from anywhere:

    py -3.11 scripts/drive/d1012_manager_framework.py
"""

import json
import os
import pathlib
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8099
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1012-manager-framework" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"
AGENT = "helper"
JOB = "conversation-titles"
FIRST = "Suggest a name for a small bakery that sells sourdough."
SECOND = "Reply with the single word: ok."
results = []


class Stop(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=True):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]
    except urllib.error.URLError as exc:
        return 0, str(exc)


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs=15.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render or a row not yet written
            pass
        time.sleep(0.5)
    return False


def start_hub():
    TMP.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 90):
        proc.kill()
        sys.exit(f"hub did not come up; see {TMP / 'hub.log'}")
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def main():
    proc = start_hub()
    try:
        drive()
    except Stop:
        pass
    finally:
        stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


def turn(base, message, minutes=6):
    """One turn in a new conversation; returns its conversation id once the run has ended."""
    code, run = api("POST", f"{base}/agent/trigger", {"agent": AGENT, "message": message})
    check(f"the turn for {message[:30]!r} starts", code in (200, 202), f"{code} {run}")
    run_id, conversation = run["run_id"], run["conversation_id"]
    ended = poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0]
                 not in ("running", "queued", "starting"), minutes * 60)
    check(f"the turn for {message[:30]!r} ends", ended, run_id)
    return conversation


def firings(base, conversation):
    code, body = api("GET", f"{base}/manager/activity?job={JOB}")
    if code != 200 or not isinstance(body, dict):
        return []
    return [f for f in body.get("firings", []) if (f.get("subject") or {}).get("conversation_id")
            == conversation or f.get("subject") == conversation]


def title_of(conversation):
    rows = ro("select title from conversations where id=?", (conversation,))
    return rows[0][0] if rows else None


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the manager drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "managerdrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, sonnet = api("POST", f"{base}/runners", {"name": "Sonnet", "cli": "claude", "model": SONNET})
    assert code in (200, 201), (code, sonnet)
    code, out = api("POST", f"{base}/agents", {"name": AGENT, "runner_id": haiku["id"]})
    assert code in (200, 201), (code, out)

    # 1: the job list, before anything is chosen.
    code, got = api("GET", f"{base}/manager/jobs")
    jobs = got.get("jobs", []) if isinstance(got, dict) else []
    first = jobs[0] if jobs else {}
    check("1 GET /manager/jobs lists conversation-titles first, disabled, nothing chosen",
          code == 200 and first.get("key") == JOB and first.get("enabled") is False
          and first.get("runner_id") is None and first.get("model") is None,
          f"{code} {str(got)[:300]}")

    # 2: the operator chooses a runner and a different model; the settings route agrees.
    code, job = api("PATCH", f"{base}/manager/jobs/{JOB}",
                    {"enabled": True, "runner_id": sonnet["id"], "model": HAIKU})
    check("2a PATCH the job answers it as sent",
          code == 200 and isinstance(job, dict) and job.get("enabled") is True
          and job.get("runner_id") == sonnet["id"] and job.get("model") == HAIKU,
          f"{code} {str(job)[:300]}")
    code, settings = api("GET", f"{base}/settings")
    check("2b GET /settings reports generate and the job's runner",
          code == 200 and settings.get("conversation_title_mode") == "generate"
          and settings.get("conversation_title_runner_id") == sonnet["id"],
          f"{code} mode={settings.get('conversation_title_mode') if isinstance(settings, dict) else settings}")

    # 3: a new conversation is titled by the job's runner and model, and the firing says so.
    conversation = turn(base, FIRST)
    poll(lambda: firings(base, conversation), 90)
    found = firings(base, conversation)
    fired = found[0] if found else {}
    (TMP / "firing.json").write_text(json.dumps(found, indent=2), encoding="utf-8")
    check("3a one firing for the conversation: written, the Sonnet runner, model Haiku, no agent",
          len(found) == 1 and fired.get("outcome") == "written"
          and fired.get("runner_id") == sonnet["id"] and fired.get("model") == HAIKU
          and not fired.get("agent") and isinstance(fired.get("duration_ms"), int),
          f"firings={str(found)[:400]}")
    title = title_of(conversation)
    check("3b the title is the firing's, not the message",
          title and title == fired.get("detail") and title != FIRST, f"title={title!r}")
    runs = ro("select count(*) from runs where conversation_id=?", (conversation,))[0][0]
    check("3c exactly one Run row for that conversation", runs == 1, f"runs={runs}")

    # 4: disabled, the floor: the message is the title and nothing fires.
    code, _ = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": False})
    check("4a the job can be turned off", code == 200, str(code))
    second = turn(base, SECOND)
    time.sleep(20)
    check("4b the second conversation keeps its message as its title, with no firing",
          title_of(second) == SECOND and not firings(base, second),
          f"title={title_of(second)!r} firings={firings(base, second)}")

    # 5: what the operator sees.
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=environment&section=manager",
                  wait_until="domcontentloaded")
        shown = poll(lambda: page.locator(f"[data-testid=manager-job-{JOB}]").count() == 1
                     and page.locator("[data-testid^=manager-firing-]").count() >= 1, 20)
        page.screenshot(path=str(SHOT) + "_manager.png", full_page=True)
        page.goto(f"{HUB}/?project={pid}&tab=environment&section=settings",
                  wait_until="domcontentloaded")
        poll(lambda: page.get_by_label("Project name").count() == 1, 15)
        leftover = page.get_by_label("Conversation title runner").count()
        page.screenshot(path=str(SHOT) + "_settings.png", full_page=True)
        browser.close()
    check("5 Environment > Manager shows the job and a firing; Settings has no title runner control",
          shown and leftover == 0, f"manager shown={shown} title controls left={leftover}")


if __name__ == "__main__":
    main()
