"""Screenshots for FR-11 (mock-live) of `the-spec-process-uses-what-the-hub-already-knows`
(spdoc-f28755f7a656), task SPUWH-6, 2026-11-24.

It reuses what `premortem_woven.py` left behind (a written, answered pre-mortem and a conversation
bound to the document): a copy of that drive's database, served by a fresh Hub from this checkout on
its own port, over that drive's scratch project. It then

  1. uploads a transcript that backs the document's /health requirement without being cited by it,
     and waits for the vault distillation (Haiku) to make its facts;
  2. asks for a spec-vault check of the document (Haiku) and waits for it to end, written, naming
     at least one possible backing fact in GET /vault/warnings, with no warning about it;
  3. shoots the full spec page and the conversation's side panel, light and dark, at 1600 and 760,
     each scrolled to the possible fact (page) and to the Pre-mortem heading (both).

Both jobs are switched off again before the Hub stops. Run from anywhere:

    py -3.11 scripts/drive/spuwh6_mock_live_shots.py --from ~/.agentweave/hub/profiles/drive8037/20261124-011804
"""

import argparse
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%Y%m%d-%H%M%S")
WAIT = 4 * 60
JOB, DISTIL = "spec-vault-check", "vault-distillation"
SOURCE_NAME = "Uptime checker setup call"
SOURCE = (
    "Call with the operations team about the uptime checker, 2026-11-20.\n"
    "Present: Priya (operations), Luis (us).\n"
    "Priya: the uptime checker polls GET /health on the hello service every 30 seconds.\n"
    "Priya: it treats the service as up only when /health answers 200 with the plain-text body ok.\n"
    "Luis: understood, /health will answer 200 with ok.\n"
)


def free_port():
    for port in range(8051, 8080):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit("no free port in 8051-8079")


PORT = free_port()
HUB = f"http://127.0.0.1:{PORT}"
OUT = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / f"drive{PORT}" / STAMP
DB = OUT / "agentweave.db"


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


def poll(fn, secs=15.0, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render or a file mid-write
            pass
        time.sleep(every)
    return False


def start_hub(source):
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("agentweave.db", "agentweave.db-wal", "agentweave.db-shm"):
        if (source / name).is_file():
            shutil.copy2(source / name, OUT / name)
    env = {k: v for k, v in os.environ.items() if not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(OUT / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    # A copied database keeps the credential it was made with, which the bootstrap key does not
    # replace: read it from the Hub's localhost-only setup route.
    def credential():
        global KEY
        with urllib.request.urlopen(HUB + "/api/v1/setup/token", timeout=5) as response:
            KEY = json.loads(response.read())["api_key"]
        return True

    if not poll(credential, 90) or api("GET", "/projects")[0] != 200:
        proc.kill()
        sys.exit(f"hub did not come up; see {OUT / 'hub.log'}")
    return proc


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="source", required=True, type=pathlib.Path)
    args = parser.parse_args()
    print(f"hub on :{PORT}, artefacts {OUT}", flush=True)
    proc = start_hub(args.source.expanduser())
    base = None
    try:
        con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
        pid, root = con.execute("select id, working_directory from projects").fetchone()
        convs = [c for (c,) in con.execute("select id from conversations order by created_at")]
        haiku = con.execute("select id from runners where name='Haiku'").fetchone()[0]
        con.close()
        base = f"/projects/{pid}"
        root = pathlib.Path(root)
        doc = next(str(p.relative_to(root).as_posix()) for p in (root / "spec").rglob("spec.json"))
        for job in (DISTIL, JOB):
            code, out = api("PATCH", f"{base}/manager/jobs/{job}", {"enabled": True, "runner_id": haiku})
            assert code == 200, (job, code, out)

        code, out = api("POST", f"{base}/vault/sources",
                        {"name": SOURCE_NAME, "type": "transcript", "content": SOURCE, "dated": "2026-11-20"})
        assert code == 201, (code, out)
        source_id = out["id"]
        facts_dir = root / "knowledge" / "facts"

        def facts():
            return [json.loads(p.read_text(encoding="utf-8")) for p in facts_dir.glob("fct-*.json")
                    if source_id in (json.loads(p.read_text(encoding="utf-8")).get("sources") or [])]

        assert poll(lambda: facts(), WAIT, every=3), "no facts distilled"
        print("facts:", [f.get("claim") for f in facts()], flush=True)

        quoted = urllib.parse.quote(doc)
        code, out = api("POST", f"{base}/vault/warnings/check?path={quoted}", {})
        assert code == 202, (code, out)

        def ended():
            _, activity = api("GET", f"{base}/manager/activity?job={JOB}")
            return [f for f in (activity or {}).get("firings", []) if f.get("outcome")]

        assert poll(lambda: ended(), WAIT, every=3), "the check did not end"
        code, warnings = api("GET", f"{base}/vault/warnings?path={quoted}")
        save("firings.json", ended())
        save("warnings.json", warnings)
        print("firing:", [(f.get("outcome"), f.get("detail")) for f in ended()], flush=True)
        print("warnings:", json.dumps(warnings)[:800], flush=True)
        code, uses = api("GET", f"{base}/vault/fact-uses")
        save("fact_uses.json", uses)
        possible = (warnings or {}).get("possible_facts") or []
        assert possible, "the check named no possible backing fact"
        shoot(pid, doc, convs, possible)
    finally:
        if base:
            for job in (JOB, DISTIL):
                api("PATCH", f"{base}/manager/jobs/{job}", {"enabled": False})
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def shoot(pid, doc, convs, possible):
    from playwright.sync_api import sync_playwright

    seen = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for mode in ("light", "dark"):
            for width in (1600, 760):
                seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
                        "localStorage.setItem('agentweave-selected-project', %r);"
                        "localStorage.setItem('agentweave-prefs', JSON.stringify({mode: %r}));"
                        % (KEY, HUB, pid, mode))
                context = browser.new_context(viewport={"width": width, "height": 1000})
                context.add_init_script(seed)
                page = context.new_page()
                # The full spec page, opened from the tree (d1025's recipe).
                page.goto(f"{HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
                target = page.locator(f'[data-testid="spec-tree-document-{doc}"]')
                poll(lambda: page.locator("[data-testid^=spec-tree-directory-]").count() > 0, 20)
                closed = page.locator("[data-testid^=spec-tree-directory-][aria-expanded=false]")
                for _ in range(6):
                    if target.count() or not closed.count():
                        break
                    closed.first.click()
                    page.wait_for_timeout(300)
                poll(lambda: target.count() == 1, 10)
                if target.count() == 1:
                    target.click()
                facts_box = page.get_by_test_id("spec-possible-facts")
                shown = poll(lambda: facts_box.count() >= 1, 20)
                key = f"page_{mode}_{width}"
                seen[key] = {"possible_shown": facts_box.count(),
                             "text": facts_box.first.inner_text() if shown else ""}
                if shown:
                    facts_box.first.scroll_into_view_if_needed()
                    page.wait_for_timeout(600)
                page.screenshot(path=str(OUT / f"specpage_{mode}_{width}_possible.png"))
                heading = page.get_by_role("heading", name=re.compile(r"^Pre-mortem"))
                if heading.count():
                    heading.first.scroll_into_view_if_needed()
                    page.wait_for_timeout(600)
                    box = heading.first.bounding_box()
                    seen[key]["premortem_heading_height"] = box["height"] if box else None
                page.screenshot(path=str(OUT / f"specpage_{mode}_{width}_premortem.png"))

                # The conversation's side panel, on its Document tab.
                conv = convs[-1]
                page.goto(f"{HUB}/?project={pid}&agent=Author&conversation={conv}")
                page.wait_for_selector("[data-testid=conversation-header]", timeout=30000)
                page.wait_for_timeout(2500)
                pane = page.get_by_test_id("document-pane")
                if not pane.count():
                    page.keyboard.press("Control+Alt+B")
                    page.wait_for_timeout(1500)
                tab = pane.get_by_role("radio", name=re.compile(r"^Document"))
                key = f"panel_{mode}_{width}"
                seen[key] = {"pane": pane.count()}
                if tab.count():
                    tab.first.click()
                    page.wait_for_timeout(1500)
                    seen[key]["possible_shown"] = pane.get_by_test_id("spec-possible-facts").count()
                    req = pane.get_by_text(re.compile(r"^FR-3$"))
                    if req.count():
                        req.first.scroll_into_view_if_needed()
                        page.wait_for_timeout(500)
                    page.screenshot(path=str(OUT / f"panel_{mode}_{width}_requirements.png"))
                    heading = pane.get_by_role("heading", name=re.compile(r"^Pre-mortem"))
                    if heading.count():
                        heading.first.scroll_into_view_if_needed()
                        page.wait_for_timeout(600)
                        box = heading.first.bounding_box()
                        seen[key]["premortem_heading_height"] = box["height"] if box else None
                        seen[key]["premortem_heading"] = " ".join(heading.first.inner_text().split())
                    page.screenshot(path=str(OUT / f"panel_{mode}_{width}_premortem.png"))
                context.close()
        browser.close()
    save("shots.json", seen)
    print(json.dumps(seen, indent=2), flush=True)


if __name__ == "__main__":
    main()
