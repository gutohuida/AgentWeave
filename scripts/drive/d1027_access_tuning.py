"""Acceptance drive for the knowledge vault roadmap's `access-tuning` slice, 2026-10-12.

The slice's `drive` criterion (spec/changes/the-vault-map-is-shaped-by-what-agents-ask-for/).
It starts its own Hub on a free port in 8110-8139 with a fresh database (never :8000 or :8010),
serving the bundle built into hub/hub/static/ui. It opens a scratch git repository as the project,
with a Haiku runner and one agent, uploads three sources oldest to newest (A, B, C) and writes
three fact files beside them: A1 (older) and A2 (newer) citing A, B1 citing B. It checks, in order:

  1. before any read the map is C, B, B1, A, A2, A1, every entry with fetches 0 and
     last_fetched_at null;
  2. a Haiku turn told to vault_read A1 twice and B once does so;
  3. the operator's read of C through the dashboard route answers 200;
  4. the operator's map now carries fetches A1 2, B 1 and 0 elsewhere (C included: the
     operator's read and the maps do not count), with last_fetched_at set exactly on A1 and B;
  5. the map is A, A1, A2, B, B1, C;
  6. the agents' map (read with a run credential) lists the same entries in the same order
     with the same counts;
  7. in Chromium the Vault page lists the entries in that order, shows 2 on A1 and 1 on B and
     no count elsewhere, and A1 selected says it was read 2 times (shot_counts.png).

It fails on today's Hub at check 1 (map entries carry no fetches). It stops at the first
failure, so a red run spends no model call. Run from anywhere:

    py -3.11 scripts/drive/d1027_access_tuning.py
"""

import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1027-access-tuning" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
AGENT = "helper"
SOURCES = {
    "A": ("Acme refund policy", "Meeting with Acme, 2026-10-01.\nDana: the refund limit is 300 euros.\n"
          "Dana: refunds above it need a manager.\n"),
    "B": ("Acme delivery terms", "Call with Acme, 2026-10-03.\nLuis: deliveries leave on Tuesdays.\n"),
    "C": ("Acme invoicing", "Email from Acme, 2026-10-05.\nInvoices are due within 30 days.\n"),
}
FACTS = {  # written in this order, so A1 is older than A2
    "A1": ("A", "The refund limit for Acme is 300 euros.", "Dana: the refund limit is 300 euros.", 2),
    "A2": ("A", "Acme refunds above the limit need a manager.", "Dana: refunds above it need a manager.", 3),
    "B1": ("B", "Acme deliveries leave on Tuesdays.", "Luis: deliveries leave on Tuesdays.", 2),
}
results = []


def free_port():
    for port in range(8110, 8140):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit("no free port in 8110-8139")


PORT = free_port()
HUB = f"http://127.0.0.1:{PORT}"


class Stop(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=True):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


def api(method, path, body=None, timeout=60, key=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + (key or KEY), "Content-Type": "application/json"}, method=method,
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
    print(f"hub on :{PORT}, artefacts {TMP}", flush=True)
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


def write_fact(root, source_id, claim, quote, line):
    """A tracked fact record beside the source, as distillation writes one (vault.add_fact)."""
    fact_id = "fct-" + secrets.token_hex(6)
    meta = {
        "id": fact_id,
        "kind": "fact",
        "claim": claim,
        "citations": [{"source": source_id, "quote": quote, "line_start": line, "line_end": line}],
        "sources": [source_id],
        "visibility": "tracked",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
        "holder": None,
        "made_by": {"job": "d1027", "model": None},
    }
    folder = root / "knowledge" / "facts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{fact_id}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return fact_id


def observer_token(pid):
    """A running run's credential, minted straight into the scratch database the way the Hub's
    tests do, so the drive can read the agents' map route without a model call."""
    sys.path.insert(0, str(REPO / "hub"))
    # Importing the Hub's models loads its settings, which refuse to guess a database.
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.agent_auth import hash_run_token
    from hub.db.models import Run

    token = "aw_run_" + secrets.token_urlsafe(24)
    engine = create_engine(f"sqlite:///{DB.as_posix()}")
    with Session(engine) as session:
        session.add(Run(id="run-d1027-" + secrets.token_hex(4), project_id=pid, agent=AGENT,
                        status="running", turn_depth=0, capability_token_hash=hash_run_token(token)))
        session.commit()
    engine.dispose()
    return token


def vault_reads():
    """The entry id of every 200 the agents' entry route answered at offset 0, from the Hub's
    access log: what the agent asked for, independent of what the Hub counted. (Agents call tools
    through aw-tool with a JSON file, so the run's outputs do not reliably carry the id.)"""
    log = (TMP / "hub.log").read_text(encoding="utf-8", errors="replace")
    pattern = r'"GET /api/v1/agent-actions/vault/entries/([\w-]+)(?:\?offset=0)? HTTP/1\.1" 200'
    return re.findall(pattern, log)


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the access-tuning drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "accessdrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, out = api("POST", f"{base}/agents", {"name": AGENT, "runner_id": haiku["id"]})
    assert code in (200, 201), (code, out)

    ids = {}
    for label, (name, content) in SOURCES.items():
        code, source = api("POST", f"{base}/vault/sources",
                           {"name": name, "type": "transcript", "content": content})
        assert code == 201, (code, source)
        ids[label] = source["id"]
        time.sleep(1.1)  # distinct created_at, so newest-first is A, B, C reversed
    for label, (home, claim, quote, line) in FACTS.items():
        ids[label] = write_fact(root, ids[home], claim, quote, line)
        time.sleep(1.1)  # write_fact stamps whole seconds
    names = {entry_id: label for label, entry_id in ids.items()}
    (TMP / "ids.json").write_text(json.dumps(ids, indent=2), encoding="utf-8")

    def operator_map():
        code, body = api("GET", f"{base}/vault/map")
        assert code == 200, (code, body)
        return body["entries"]

    def labelled(entries):
        return [names.get(e.get("id"), e.get("id")) for e in entries]

    # 1: before any read, today's order and every count 0.
    before = operator_map()
    (TMP / "map_before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    check("1 before any read the map is C, B, B1, A, A2, A1 with fetches 0 and last_fetched_at null",
          labelled(before) == ["C", "B", "B1", "A", "A2", "A1"]
          and all(e.get("fetches") == 0 and "last_fetched_at" in e and e["last_fetched_at"] is None
                  for e in before),
          f"order={labelled(before)} fetches={[(names.get(e['id']), e.get('fetches', 'absent')) for e in before]}")

    # 2: the agent reads A1 twice and B once.
    code, run = api("POST", f"{base}/agent/trigger", {"agent": AGENT, "message": (
        f"Use the knowledge vault tool vault_read exactly three times, one call at a time: first "
        f"vault_read with entry_id {ids['A1']}, then vault_read with entry_id {ids['A1']} again, then "
        f"vault_read with entry_id {ids['B']}. Do not call vault_map or any other tool. Then reply "
        "'done'.")})
    check("2a the turn starts", code in (200, 202), f"{code} {run}")
    run_id = run["run_id"]
    ended = poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0]
                 not in ("running", "queued", "starting"), 6 * 60)
    check("2b the turn ends", ended, run_id)
    outputs = ro("select kind, content, payload from agent_outputs where run_id=? "
                 "order by sequence, timestamp", (run_id,))
    (TMP / "outputs.json").write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")
    reads = [names.get(r, r) for r in vault_reads()]
    check("2c the run called vault_read on A1 twice and B once", sorted(reads) == ["A1", "A1", "B"],
          f"reads={reads}")

    # 3: the operator reads C through the dashboard route.
    code, body = api("GET", f"{base}/vault/entries/{ids['C']}")
    check("3 the operator's read of C answers 200", code == 200, f"{code} {str(body)[:200]}")

    # 4: counts.
    after = operator_map()
    (TMP / "map_after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    counts = {names.get(e["id"]): e.get("fetches") for e in after}
    stamped = {names.get(e["id"]) for e in after if e.get("last_fetched_at")}
    check("4 fetches are A1 2, B 1 and 0 elsewhere (C too); last_fetched_at set on A1 and B only",
          counts == {"A": 0, "A1": 2, "A2": 0, "B": 1, "B1": 0, "C": 0} and stamped == {"A1", "B"},
          f"counts={counts} stamped={stamped}")

    # 5: order.
    check("5 the map is A, A1, A2, B, B1, C", labelled(after) == ["A", "A1", "A2", "B", "B1", "C"],
          f"order={labelled(after)}")

    # 6: the agents' map agrees.
    token = observer_token(pid)
    code, agents_map = api("GET", "/agent-actions/vault/map", key=token)
    agents = (agents_map or {}).get("entries", []) if isinstance(agents_map, dict) else []
    check("6 the agents' map has the same order and counts",
          code == 200 and [(e["id"], e.get("fetches")) for e in agents]
          == [(e["id"], e.get("fetches")) for e in after],
          f"{code} agents={[(names.get(e.get('id')), e.get('fetches')) for e in agents]} {str(agents_map)[:200]}")

    # 7: the Vault page.
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=vault", wait_until="domcontentloaded")
        shown = poll(lambda: page.locator(f"[data-testid=vault-fetches-{ids['A1']}]").count() == 1, 20)
        listed = page.eval_on_selector_all(
            "[data-testid^='vault-entry-']",
            "els => els.map(e => e.dataset.testid.slice('vault-entry-'.length))")
        badges = {label: (page.locator(f"[data-testid=vault-fetches-{ids[label]}]").inner_text().strip()
                          if page.locator(f"[data-testid=vault-fetches-{ids[label]}]").count() else None)
                  for label in ids}
        selected = ""
        if shown:
            page.locator(f"[data-testid=vault-entry-{ids['A1']}]").click()
            poll(lambda: page.locator("[data-testid=vault-entry-fetches]").count() == 1, 10)
            if page.locator("[data-testid=vault-entry-fetches]").count():
                selected = page.locator("[data-testid=vault-entry-fetches]").inner_text()
        page.screenshot(path=str(SHOT) + "_counts.png", full_page=True)
        browser.close()
    order = [names.get(i) for i in listed if i in names]
    check("7 the Vault page lists A, A1, A2, B, B1, C with 2 on A1, 1 on B and no other count, "
          "and A1 selected says 2",
          shown and order == ["A", "A1", "A2", "B", "B1", "C"]
          and badges == {"A": None, "A1": "2", "A2": None, "B": "1", "B1": None, "C": None}
          and "2" in selected,
          f"shown={shown} order={order} badges={badges} selected={selected!r}")


if __name__ == "__main__":
    main()
