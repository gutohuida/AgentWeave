"""Acceptance drive for `the-settings-that-gate-collaboration-are-on-the-project-page` (R2 / F379), 2026-10-08.

Starts its own Hub on :8097 with a fresh database (never :8000 or :8010), serving the bundle built into
hub/hub/static/ui, opens a project with two agents that never run, and drives the Overview in Chromium:

  1. the Collaboration block reads "Off" for agents may start flows;
  2. a settings change made over the API (another surface) flips it to "On" with no reload (FR-10);
  3. clicking one agent's evidence chip grants that agent only (FR-4);
  4. one agent's details expand to the built-in posture and the 120s/240s fallbacks (FR-5);
  5. Settings shows its groups in order, has no token budget input, and saves without token_budget (FR-6, FR-7).

Fails on the tree before the build at step 1 (no block). Run from anywhere:

    py -3.11 scripts/drive/d1008_project_page_settings.py
"""

import json
import os
import pathlib
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8097
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1008-projectpage" / STAMP
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    return bool(ok)


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]
    except urllib.error.URLError as exc:
        return 0, str(exc)


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs=15.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render; try again
            pass
        time.sleep(0.25)
    return False


def start_hub():
    TMP.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP / 'hub.db').as_posix()}"
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
    finally:
        stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    sys.exit(1 if bad else 0)


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("project page drive\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "pagedrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, runner)
    for name in ("alpha", "beta"):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        assert code in (200, 201), (name, code, out)
    code, out = api("PATCH", f"{base}/agents/alpha", {"can_accept_evidence": True})
    assert code == 200, (code, out)
    _, settings = api("GET", f"{base}/settings")
    assert settings["allow_agent_jobs"] is False, settings

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=overview", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        flows = page.locator("[data-testid=collab-row-flows]")
        if not check("Overview has a Collaboration block reading Off for agents may start flows",
                     poll(lambda: flows.count() == 1 and "Off" in flows.inner_text(), 10),
                     flows.inner_text() if flows.count() else "no [data-testid=collab-row-flows]"):
            page.screenshot(path=str(SHOT) + "_1.png")
            return

        code, _ = api("PUT", f"{base}/settings", {"allow_agent_jobs": True})
        check("a settings change from another surface flips it to On without a reload",
              code == 200 and poll(lambda: "On" in flows.inner_text()), flows.inner_text())

        chip = page.locator("[data-testid=agent-grant-beta-can_accept_evidence]")
        check("beta's evidence chip renders off, alpha's on",
              chip.get_attribute("aria-pressed") == "false"
              and page.locator("[data-testid=agent-grant-alpha-can_accept_evidence]").get_attribute("aria-pressed")
              == "true")
        chip.click()

        def granted():
            rows = {a["name"]: a for a in api("GET", f"{base}/agents")[1]}
            return rows["beta"]["can_accept_evidence"] and not rows["beta"]["can_recall"]
        check("clicking beta's evidence chip grants beta evidence only", poll(granted))

        details = page.locator("[data-testid=agent-details-beta]")
        check("beta's details start collapsed", details.count() == 0 or not details.is_visible())
        page.locator("[data-testid=agent-details-toggle-beta]").click()
        # Settled, not first paint: the runner list is fetched when the details open (a read taken
        # at once said "None bound" for a bound agent -- the defect this drive found).
        poll(lambda: details.is_visible() and "Haiku" in details.inner_text(), 10)
        text = details.inner_text() if details.count() else ""
        check("expanded details show the built-in posture, the bound runner and the 120s/240s fallbacks",
              "built-in default" in text.lower() and "Haiku" in text and "None bound" not in text
              and "120" in text and "240" in text, text.replace("\n", " | "))
        check("alpha's details stay collapsed",
              page.locator("[data-testid=agent-details-alpha]").count() == 0
              or not page.locator("[data-testid=agent-details-alpha]").is_visible())
        page.screenshot(path=str(SHOT) + "_overview.png", full_page=True)

        page.goto(f"{HUB}/?project={pid}&tab=environment&section=settings", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        # textContent, not innerText: the headings are uppercased by CSS.
        headings = page.locator("[data-testid=settings-group-heading]").all_text_contents()
        check("Settings groups read Collaboration, Integration, Checkpointing, Conversations, Project",
              [h.strip() for h in headings] == ["Collaboration", "Integration", "Checkpointing", "Conversations",
                                                "Project"], str(headings))
        check("Settings renders no token budget input", page.get_by_label("Token budget", exact=True).count() == 0)
        page.get_by_label("Hop budget").fill("9")
        with page.expect_request(lambda r: r.method == "PUT" and r.url.endswith("/settings")) as sent:
            page.get_by_role("button", name="Save settings").click()
        body = json.loads(sent.value.post_data or "{}")
        check("a Settings save sends no token_budget, and the hop budget lands",
              "token_budget" not in body
              and poll(lambda: api("GET", f"{base}/settings")[1].get("hop_budget") == 9), str(sorted(body)))
        page.screenshot(path=str(SHOT) + "_settings.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
