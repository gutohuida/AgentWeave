"""Acceptance drive for the knowledge vault roadmap's `distillation` slice, 2026-10-09.

The slice's `drive` criterion (spec/changes/the-manager-distils-vault-sources-into-cited-facts/).
It starts its own Hub on :8099 with a fresh database (never :8000 or :8010), serving the bundle
built into hub/hub/static/ui. It opens a scratch git repository as the project, with a Haiku
runner, and checks, in order:

  1. PATCH /manager/jobs/vault-distillation enables the job on the Haiku runner;
  2. a tracked transcript stating two business rules among small talk is uploaded, and the upload
     answers 201 without waiting for the model;
  3. within three minutes knowledge/facts holds a fact about the 30-day return window citing the
     line that says it, and one about the 437-euro refund limit citing the line that says it;
  4. the map lists those facts as kind fact, with the transcript in their sources;
  5. the activity log has a written vault-distillation firing on Haiku for the transcript;
  6. a private rules note is distilled: its facts are at the private location, the repository
     holds only their stubs, and no file in the repository holds the note's rule;
  7. with the job disabled, a third source gets no fact and no firing;
  8. with the job enabled again, pressing Distil on that source in the Vault tab distils it;
  9. in Chromium, the transcript lists its facts, and following the refund fact's citation
     highlights the line with 437.

It fails on today's Hub at check 1 (no vault-distillation job). It stops at the first failure, so
a red run spends no model call. Run from anywhere:

    py -3.11 scripts/drive/d1016_distillation.py
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

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8099
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1016-distillation" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
JOB = "vault-distillation"
DISTIL_WAIT = 3 * 60
TRANSCRIPT = (
    "Kickoff meeting with Acme Retail, 2026-10-02.\n"
    "Present: Dana (Acme), Luis (us).\n"
    "\n"
    "Luis: thanks for having us. We plan to start with the three Lisbon stores in November.\n"
    "Dana: good. The weather has been awful this week, by the way.\n"
    "Dana: on to returns. Customers may return goods within 30 days of purchase.\n"
    "Luis: and refunds without manager approval?\n"
    "Dana: agreed, the refund limit without approval is 437 euros. Above that a manager signs.\n"
    "Luis: noted. Coffee next time is on us.\n"
)
RETURN_LINE = 6  # 1-based: "Customers may return goods within 30 days"
REFUND_LINE = 8  # 1-based: "the refund limit without approval is 437 euros"
NOTE = (
    "Internal rules, not for the client.\n"
    "Rule CANARY-9d1e: invoices above 5,000 euros need two signatures from finance.\n"
)
NOTE_MARKERS = ("CANARY-9d1e", "5,000", "5000")
THIRD = (
    "Delivery rules agreed with the Acme warehouse.\n"
    "Deliveries to stores happen only on weekdays, before 10:00 in the morning.\n"
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


def files_under(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def facts_in(folder, source_id):
    """The fact records under *folder* that cite *source_id*."""
    found = []
    for path in sorted(folder.glob("fct-*.json")) if folder.is_dir() else []:
        record = json.loads(path.read_text(encoding="utf-8"))
        if source_id in [c.get("source") for c in record.get("citations") or []] or source_id in (
            record.get("sources") or []
        ):
            found.append(record)
    return found


def cites_line(fact, source_id, line):
    return any(c.get("source") == source_id and c.get("line_start", 0) <= line <= c.get("line_end", 0)
               for c in fact.get("citations") or [])


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the distillation drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    private = TMP / "private-vault"
    tracked_facts = root / "knowledge" / "facts"
    private_facts = private / "facts"

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "distildrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, _ = api("PUT", f"{base}/vault/settings", {"private_location": str(private)})
    assert code == 200, code

    # 1: the job exists and can be enabled on the Haiku runner.
    code, job = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": True, "runner_id": haiku["id"]})
    check("1 vault-distillation is enabled on the Haiku runner",
          code == 200 and isinstance(job, dict) and job.get("enabled") is True
          and job.get("runner_id") == haiku["id"], f"{code} {str(job)[:300]}")

    # 2: the upload answers without waiting for the model.
    started = time.time()
    code, transcript = api("POST", f"{base}/vault/sources",
                           {"name": "Acme kickoff", "type": "transcript", "content": TRANSCRIPT})
    took = time.time() - started
    tid = transcript.get("id") if isinstance(transcript, dict) else None
    check("2 the transcript upload answers 201 without waiting for a model",
          code == 201 and tid and took < 5, f"{code} took={took:.1f}s {str(transcript)[:200]}")

    # 3: two cited facts.
    def two_rules():
        facts = facts_in(tracked_facts, tid)
        return (any("30" in f.get("claim", "") and cites_line(f, tid, RETURN_LINE) for f in facts)
                and any("437" in f.get("claim", "") and cites_line(f, tid, REFUND_LINE) for f in facts))

    got = poll(two_rules, DISTIL_WAIT, every=3)
    facts = facts_in(tracked_facts, tid)
    (TMP / "transcript_facts.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    check("3 the transcript's facts cite the 30-day line and the 437-euro line",
          got, f"facts={[(f.get('claim'), [(c.get('line_start'), c.get('line_end')) for c in f.get('citations', [])]) for f in facts]}")
    refund = next(f for f in facts if "437" in f.get("claim", "") and cites_line(f, tid, REFUND_LINE))

    # 4: the map lists them.
    code, vault_map = api("GET", f"{base}/vault/map")
    entries = vault_map.get("entries", []) if isinstance(vault_map, dict) else []
    (TMP / "map.json").write_text(json.dumps(vault_map, indent=2), encoding="utf-8")
    listed = {e.get("id"): e for e in entries}
    check("4 the map lists the facts as kind fact citing the transcript",
          code == 200 and listed.get(tid, {}).get("kind") == "source"
          and all(listed.get(f["id"], {}).get("kind") == "fact"
                  and tid in (listed.get(f["id"], {}).get("sources") or []) for f in facts),
          f"{code} kinds={[(e.get('id'), e.get('kind')) for e in entries]}")

    # 5: the activity log.
    code, activity = api("GET", f"{base}/manager/activity?job={JOB}")
    firings = activity.get("firings", []) if isinstance(activity, dict) else []
    check("5 a written vault-distillation firing on Haiku is in the activity log",
          code == 200 and any(f.get("outcome") == "written" and f.get("model") == HAIKU
                              and (f.get("subject") or {}).get("source") == tid for f in firings),
          f"{code} {[(f.get('outcome'), f.get('model'), f.get('subject'), f.get('detail')) for f in firings]}")

    # 6: a private note's facts stay private.
    code, note = api("POST", f"{base}/vault/sources",
                     {"name": "Finance rules", "type": "rules", "content": NOTE, "visibility": "private"})
    nid = note.get("id") if isinstance(note, dict) else None
    got = poll(lambda: len(facts_in(private_facts, nid)) >= 1, DISTIL_WAIT, every=3)
    held = facts_in(private_facts, nid)
    stubs = [tracked_facts / f"{f['id']}.json" for f in held]
    leaked = [p for p in files_under(root) if not p.startswith(".git/") and any(
        m in (root / p).read_text(encoding="utf-8", errors="replace") for m in NOTE_MARKERS)]
    check("6 the private note's facts are at the private location; the repository holds stubs only",
          code == 201 and got and stubs and all(s.is_file() for s in stubs)
          and all("claim" not in json.loads(s.read_text(encoding="utf-8")) for s in stubs if s.is_file())
          and not leaked,
          f"{code} held={[f.get('claim') for f in held]} stubs={[s.name for s in stubs]} leaked={leaked}")

    # 7: disabled, nothing happens.
    code, _ = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": False})
    assert code == 200, code
    code, third = api("POST", f"{base}/vault/sources",
                      {"name": "Delivery rules", "type": "rules", "content": THIRD})
    xid = third.get("id") if isinstance(third, dict) else None
    time.sleep(15)
    _, activity = api("GET", f"{base}/manager/activity?job={JOB}")
    fired = [f for f in activity.get("firings", []) if (f.get("subject") or {}).get("source") == xid]
    check("7 with the job disabled, a new source gets no fact and no firing",
          code == 201 and xid and not facts_in(tracked_facts, xid) and not fired,
          f"{code} facts={facts_in(tracked_facts, xid)} fired={fired}")

    # 8 and 9: the Vault tab.
    code, _ = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": True})
    assert code == 200, code
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=vault", wait_until="domcontentloaded")

        opened = poll(lambda: page.locator(f"[data-testid=vault-entry-{xid}]").count() == 1, 20)
        pressed = False
        if opened:
            page.locator(f"[data-testid=vault-entry-{xid}]").click()
            pressed = poll(lambda: page.locator("[data-testid=vault-distil]").count() == 1, 10)
            if pressed:
                page.locator("[data-testid=vault-distil]").click()
        distilled = pressed and poll(lambda: len(facts_in(tracked_facts, xid)) >= 1, DISTIL_WAIT, every=3)
        page.screenshot(path=str(SHOT) + "_distil.png", full_page=True)
        check("8 Distil in the Vault tab distils the source added while the job was off",
              distilled, f"opened={opened} pressed={pressed} facts={facts_in(tracked_facts, xid)}",
              fatal=False)

        page.locator(f"[data-testid=vault-entry-{tid}]").click()
        both = poll(lambda: all(page.locator(f"[data-testid=vault-fact-{f['id']}]").count() == 1
                                for f in facts), 15)
        page.screenshot(path=str(SHOT) + "_facts.png", full_page=True)
        lit = False
        if both:
            page.locator(f"[data-testid=vault-fact-link-{refund['id']}]").click()
            lit = poll(lambda: page.locator(
                f"[data-testid=vault-line-{REFUND_LINE}][data-highlighted=true]").count() == 1
                and "437" in page.locator(f"[data-testid=vault-line-{REFUND_LINE}]").inner_text(), 15)
        page.screenshot(path=str(SHOT) + "_citation.png", full_page=True)
        browser.close()
    check("9 the transcript lists its facts, and the refund fact's citation highlights the 437 line",
          both and lit, f"both={both} lit={lit}")


if __name__ == "__main__":
    main()
