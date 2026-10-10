"""Acceptance drive for the knowledge vault roadmap's `contradictions` slice, 2026-10-09.

The slice's `drive` criterion (spec/changes/sources-that-disagree-are-pointed-out/). It starts its
own Hub on :8099 with a fresh database (never :8000 or :8010), serving the bundle built into
hub/hub/static/ui. It opens a scratch git repository as the project, with a Haiku runner that
distils and a Haiku agent, and checks, in order:

  1. a transcript dated 2026-10-01 setting the refund limit to 300 euros is uploaded first, and the
     map lists its date;
  2. its facts are distilled;
  3. a transcript dated 2026-09-01 setting the limit to 437 euros is uploaded second; within three
     minutes an open contradiction pairs a 437 fact with a 300 fact, the 300 one presumed although
     its source was uploaded first;
  4. the map marks both disputed, the 300 one presumed, and the 437 fact's card says it is disputed
     and names the 300 fact;
  5. the activity log has a written facts_written firing;
  6. the agent, asked the refund limit, reads the vault (vault_map or vault_read; the map carries
     the flags, so either tells it) and answers 300, saying it is disputed;
  7. in Chromium, the contradiction is resolved choosing the 300 fact with a note; it is then
     resolved, a decision source exists, the 437 fact is superseded by it and nothing is disputed.

It fails on today's Hub at check 1 (no dated field: 422). It stops at the first failure, so a red
run spends no model call. Run from anywhere:

    py -3.11 scripts/drive/d1017_contradictions.py
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
TMP = REPO / "testbed" / "drive1017-contradictions" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
JOB = "vault-distillation"
AGENT = "helper"
WAIT = 3 * 60
NEWER = (
    "Follow-up meeting with Acme Retail, 2026-10-01.\n"
    "Present: Dana (Acme), Luis (us).\n"
    "Dana: we reviewed refunds with finance last week.\n"
    "Dana: from now on, the refund limit without manager approval is 300 euros.\n"
    "Luis: understood, we will lower it in the build.\n"
)
OLDER = (
    "Kickoff meeting with Acme Retail, 2026-09-01.\n"
    "Present: Dana (Acme), Luis (us).\n"
    "Luis: thanks for having us. The weather is lovely today.\n"
    "Dana: agreed, the refund limit without manager approval is 437 euros.\n"
    "Luis: noted.\n"
)
QUESTION = (
    "According to the project's knowledge vault, what is the refund limit without manager "
    "approval for Acme? Answer with the number and currency, and say whether it is disputed."
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


def records(folder, prefix):
    if not folder.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob(f"{prefix}-*.json"))]


def facts_of(root, source_id):
    return [f for f in records(root / "knowledge" / "facts", "fct")
            if source_id in (f.get("sources") or [])]


def refund(facts, number):
    return [f for f in facts if number in f.get("claim", "")]


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the contradictions drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "contradrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, out = api("POST", f"{base}/agents", {"name": AGENT, "runner_id": haiku["id"]})
    assert code in (200, 201), (code, out)
    code, job = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": True, "runner_id": haiku["id"]})
    assert code == 200, (code, job)

    # 1: the newer meeting first, with its date.
    code, newer = api("POST", f"{base}/vault/sources",
                      {"name": "Acme follow-up", "type": "transcript", "content": NEWER,
                       "dated": "2026-10-01"})
    nid = newer.get("id") if isinstance(newer, dict) else None
    _, vault_map = api("GET", f"{base}/vault/map")
    listed = {e.get("id"): e for e in (vault_map or {}).get("entries", [])} if isinstance(vault_map, dict) else {}
    check("1 a source dated 2026-10-01 is uploaded and listed with its date",
          code == 201 and nid and listed.get(nid, {}).get("dated") == "2026-10-01",
          f"{code} {str(newer)[:300]}")

    # 2: its facts.
    got = poll(lambda: refund(facts_of(root, nid), "300"), WAIT, every=3)
    check("2 the newer meeting's 300-euro fact is distilled", got,
          f"facts={[f.get('claim') for f in facts_of(root, nid)]}")

    # 3: the older meeting, uploaded second, contradicts it.
    code, older = api("POST", f"{base}/vault/sources",
                      {"name": "Acme kickoff", "type": "transcript", "content": OLDER,
                       "dated": "2026-09-01"})
    oid = older.get("id") if isinstance(older, dict) else None
    folder = root / "knowledge" / "contradictions"

    def the_pair():
        new300 = {f["id"] for f in refund(facts_of(root, nid), "300")}
        old437 = {f["id"] for f in refund(facts_of(root, oid), "437")}
        for record in records(folder, "ctr"):
            pair = set(record.get("facts") or [])
            if record.get("status") == "open" and pair & new300 and pair & old437:
                return record
        return None

    poll(lambda: the_pair() is not None, WAIT, every=3)
    pair = the_pair()
    every = records(folder, "ctr")
    (TMP / "contradictions.json").write_text(json.dumps(every, indent=2), encoding="utf-8")
    presumed_300 = bool(pair) and pair.get("presumed") in {f["id"] for f in refund(facts_of(root, nid), "300")}
    check("3 an open contradiction pairs the 437 fact with the 300 fact, the 300 one presumed",
          code == 201 and pair and presumed_300,
          f"{code} contradictions={[(c.get('facts'), c.get('presumed'), c.get('status')) for c in every]}")
    cid = pair["id"]
    fact300 = pair["presumed"]
    fact437 = next(f for f in pair["facts"] if f != fact300)

    # 4: disputed everywhere an agent looks.
    _, vault_map = api("GET", f"{base}/vault/map")
    listed = {e.get("id"): e for e in vault_map.get("entries", [])}
    _, card = api("GET", f"{base}/vault/entries/{fact437}")
    content = (card or {}).get("content") or "" if isinstance(card, dict) else ""
    (TMP / "card437.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    check("4 both facts are disputed, the 300 one presumed, and the 437 card says so",
          listed.get(fact300, {}).get("disputed") is True and listed.get(fact437, {}).get("disputed") is True
          and listed.get(fact300, {}).get("presumed") is True and listed.get(fact437, {}).get("presumed") is False
          and "disputed" in content.lower() and fact300 in content,
          f"300={listed.get(fact300)} 437={listed.get(fact437)} card={content[:300]!r}")

    # 5: the check's firing.
    _, activity = api("GET", f"{base}/manager/activity?job={JOB}")
    firings = activity.get("firings", []) if isinstance(activity, dict) else []
    check("5 a written facts_written firing is in the activity log",
          any(f.get("trigger") == "facts_written" and f.get("outcome") == "written" for f in firings),
          f"{[(f.get('trigger'), f.get('outcome'), f.get('detail')) for f in firings]}")

    # 6: an agent is told the newer limit.
    code, run = api("POST", f"{base}/agent/trigger", {"agent": AGENT, "message": QUESTION})
    check("6a the turn starts", code in (200, 202), f"{code} {run}")
    run_id = run["run_id"]
    ended = poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0]
                 not in ("running", "queued", "starting"), 6 * 60)
    check("6b the turn ends", ended, run_id)
    outputs = ro("select kind, content, payload from agent_outputs where run_id=? "
                 "order by sequence, timestamp", (run_id,))
    (TMP / "outputs.json").write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")
    # vault_map carries disputed and presumed, so an agent that stops at the map has been told;
    # what is checked is what it answers (first run, 110016: map only, answered 300 and disputed).
    called = any(tool in f"{content}{payload}" for _kind, content, payload in outputs
                 for tool in ("vault_read", "vault_map"))
    replies = [c or "" for kind, c, _p in outputs if kind not in ("tool_use", "tool_result")]
    said = any("300" in reply and "disputed" in reply.lower() for reply in replies)
    check("6c the run reads the vault and answers 300, saying it is disputed", called and said,
          f"called={called} said={said} reply={' '.join(replies)[-300:]!r}")

    # 7: the operator resolves it in the Vault tab.
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=vault", wait_until="domcontentloaded")
        shown = poll(lambda: page.locator(f"[data-testid=vault-contradiction-{cid}]").count() == 1, 20)
        page.screenshot(path=str(SHOT) + "_contradiction.png", full_page=True)
        if shown:
            page.locator(f"[data-testid=vault-resolve-{cid}-stands]").select_option(fact300)
            page.locator(f"[data-testid=vault-resolve-{cid}-note]").fill(
                "Finance lowered the limit at the October follow-up.")
            page.locator(f"[data-testid=vault-resolve-{cid}-submit]").click()
        resolved = shown and poll(lambda: (api("GET", f"{base}/vault/contradictions")[1] or {})
                                  .get("contradictions", [{}])[0].get("status") == "resolved", 15)
        page.screenshot(path=str(SHOT) + "_resolved.png", full_page=True)
        browser.close()
    _, listing = api("GET", f"{base}/vault/contradictions")
    record = next((c for c in (listing or {}).get("contradictions", []) if c.get("id") == cid), {})
    resolution = record.get("resolution") or {}
    _, vault_map = api("GET", f"{base}/vault/map")
    listed = {e.get("id"): e for e in vault_map.get("entries", [])}
    decision = listed.get(resolution.get("decision") or "", {})
    check("7 resolved in the tab: a decision source, the 437 fact superseded by it, nothing disputed",
          shown and resolved and resolution.get("stands") == fact300 and decision.get("type") == "decision"
          and listed.get(fact437, {}).get("superseded_by") == decision.get("id")
          and not listed.get(fact437, {}).get("disputed") and not listed.get(fact300, {}).get("disputed"),
          f"shown={shown} resolved={resolved} record={record} decision={decision} 437={listed.get(fact437)}")


if __name__ == "__main__":
    main()
