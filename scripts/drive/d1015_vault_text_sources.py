"""Acceptance drive for the knowledge vault roadmap's `vault-text-sources` slice, 2026-10-09.

The slice's `drive` criterion (spec/changes/a-vault-the-operator-fills-with-text-and-agents-can-read/).
It starts its own Hub on :8099 with a fresh database (never :8000 or :8010), serving the bundle
built into hub/hub/static/ui. It opens a scratch git repository as the project, with a Haiku agent,
and checks, in order:

  1. GET /vault/settings answers 200 with the defaults: no private location, tracked;
  2. PUT /vault/settings with a private location inside the repository answers 400 and changes
     nothing; one outside it answers 200 and is read back;
  3. a tracked transcript is uploaded (201). knowledge/sources/<id>.md holds the text byte for
     byte, with its .json beside it;
  4. a private note is uploaded (201). Its text is at the private location, the repository holds
     only knowledge/sources/<id>.json, and that stub contains none of the text;
  5. GET /vault/map lists both, the note first (newest first). The transcript's opening is its
     first line;
  6. the agent is asked what refund limit the meeting agreed. Its turn names the vault in one line
     and no entry, so it finds the transcript through vault_map. Its run calls vault_read with the
     transcript's id (437 sits past the map's opening lines), and its reply says 437;
  7. in Chromium, the Vault tab lists both entries and opening the transcript shows its text.

It fails on today's Hub at check 1 (no /vault route). It stops at the first failure, so a red run
spends no agent turn. Run from anywhere:

    py -3.11 scripts/drive/d1015_vault_text_sources.py
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
TMP = REPO / "testbed" / "drive1015-vault-text-sources" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
AGENT = "helper"
TRANSCRIPT = (
    "Kickoff meeting with Acme Retail, 2026-10-02.\n"
    "Present: Dana (Acme), Luis (us).\n"
    "\n"
    # Agenda and small talk first, so the number sits past the map's 300-character opening and
    # the agent has to read the entry to find it.
    "Agenda: introductions, store rollout schedule, returns and refunds, next steps.\n"
    "Luis: thanks for having us. We plan to start with the three Lisbon stores in November.\n"
    "Dana: good, the Porto stores follow in January once the Lisbon ones are stable.\n"
    "Luis: we will send the rollout plan by Friday, with a contact person for each store.\n"
    "Dana: on to returns. Customers may return goods within 30 days.\n"
    "Luis: and refunds without manager approval?\n"
    "Dana: agreed, the refund limit without approval is 437 euros. Above that a manager signs.\n"
    "Luis: noted, we will build the approval step for anything above it.\n"
)
NOTE = "Private aside: Acme's procurement contact prefers calls on Tuesdays. CANARY-7f3c\n"
QUESTION = (
    "According to the project's knowledge vault, what refund limit without manager approval did "
    "the Acme kickoff meeting agree? Answer with the number and currency."
)
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


def files_under(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the vault drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    private = TMP / "private-vault"

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "vaultdrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, out = api("POST", f"{base}/agents", {"name": AGENT, "runner_id": haiku["id"]})
    assert code in (200, 201), (code, out)

    # 1: the defaults, before anything is chosen.
    code, got = api("GET", f"{base}/vault/settings")
    check("1 GET /vault/settings answers the defaults: no private location, tracked",
          code == 200 and isinstance(got, dict) and got.get("private_location") is None
          and got.get("default_visibility") == "tracked" and got.get("effective_private_location"),
          f"{code} {str(got)[:300]}")

    # 2: inside the repository is refused; outside is stored.
    inside = root / "private"
    code, refused = api("PUT", f"{base}/vault/settings", {"private_location": str(inside)})
    _, after = api("GET", f"{base}/vault/settings")
    check("2a a private location inside the repository is refused and nothing changes",
          code == 400 and after.get("private_location") is None, f"{code} {str(refused)[:300]}")
    code, stored = api("PUT", f"{base}/vault/settings", {"private_location": str(private)})
    _, after = api("GET", f"{base}/vault/settings")
    check("2b a private location outside it is stored and read back",
          code == 200 and pathlib.Path(after.get("private_location") or "") == private,
          f"{code} {str(stored)[:300]} read={after}")

    # 3: a tracked transcript.
    code, transcript = api("POST", f"{base}/vault/sources",
                           {"name": "Acme kickoff", "type": "transcript", "content": TRANSCRIPT})
    tid = transcript.get("id") if isinstance(transcript, dict) else None
    sources = root / "knowledge" / "sources"
    md, meta = sources / f"{tid}.md", sources / f"{tid}.json"
    check("3 a tracked transcript is written to knowledge/sources, text byte for byte, metadata beside it",
          code == 201 and tid and md.is_file() and meta.is_file()
          and md.read_bytes() == TRANSCRIPT.encode("utf-8"),
          f"{code} {str(transcript)[:300]} files={files_under(root / 'knowledge') if (root / 'knowledge').exists() else []}")

    # 4: a private note: text outside the repository, a stub inside it.
    code, note = api("POST", f"{base}/vault/sources",
                     {"name": "Acme contact habits", "type": "note", "content": NOTE,
                      "visibility": "private"})
    nid = note.get("id") if isinstance(note, dict) else None
    in_repo = files_under(root / "knowledge") if (root / "knowledge").exists() else []
    leaked = [p for p in files_under(root) if not p.startswith(".git/")
              and "CANARY-7f3c" in (root / p).read_text(encoding="utf-8", errors="replace")]
    private_files = files_under(private) if private.exists() else []
    check("4 a private note's text is only at the private location; the repository holds its stub",
          code == 201 and nid and f"sources/{nid}.md" in private_files
          and f"sources/{nid}.json" in in_repo and f"sources/{nid}.md" not in in_repo and not leaked,
          f"{code} repo={in_repo} private={private_files} leaked={leaked}")

    # 5: the map.
    code, vault_map = api("GET", f"{base}/vault/map")
    entries = vault_map.get("entries", []) if isinstance(vault_map, dict) else []
    ids = [e.get("id") for e in entries]
    first_line = TRANSCRIPT.splitlines()[0]
    opening = next((e.get("opening") for e in entries if e.get("id") == tid), None) or ""
    (TMP / "map.json").write_text(json.dumps(vault_map, indent=2), encoding="utf-8")
    check("5 the map lists both, newest first, with the transcript's opening lines",
          code == 200 and ids == [nid, tid] and opening.startswith(first_line)
          and "437" not in opening,  # else the map alone answers check 6
          f"{code} ids={ids} opening={opening[:120]!r}")

    # 6: a Haiku agent finds the answer through the vault.
    code, run = api("POST", f"{base}/agent/trigger", {"agent": AGENT, "message": QUESTION})
    check("6a the turn starts", code in (200, 202), f"{code} {run}")
    run_id = run["run_id"]
    ended = poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0]
                 not in ("running", "queued", "starting"), 6 * 60)
    check("6b the turn ends", ended, run_id)
    outputs = ro("select kind, content, payload from agent_outputs where run_id=? "
                 "order by sequence, timestamp", (run_id,))
    (TMP / "outputs.json").write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")
    called = any("vault_read" in f"{content}{payload}" and tid in f"{content}{payload}"
                 for _kind, content, payload in outputs)
    said = any("437" in (content or "") for kind, content, _payload in outputs
               if kind not in ("tool_use", "tool_result"))
    check("6c the run calls vault_read with the transcript's id and answers 437",
          called and said, f"called={called} said={said} kinds={[o[0] for o in outputs]}")

    # 7: what the operator sees.
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=vault", wait_until="domcontentloaded")
        listed = poll(lambda: page.locator(f"[data-testid=vault-entry-{tid}]").count() == 1
                      and page.locator(f"[data-testid=vault-entry-{nid}]").count() == 1, 20)
        page.screenshot(path=str(SHOT) + "_vault_list.png", full_page=True)
        shown = False
        if listed:
            page.locator(f"[data-testid=vault-entry-{tid}]").click()
            shown = poll(lambda: "437 euros" in page.locator("[data-testid=vault-entry-text]")
                         .inner_text(), 15)
        page.screenshot(path=str(SHOT) + "_vault_entry.png", full_page=True)
        browser.close()
    check("7 the Vault tab lists both entries and shows the transcript's text",
          listed and shown, f"listed={listed} shown={shown}")


if __name__ == "__main__":
    main()
