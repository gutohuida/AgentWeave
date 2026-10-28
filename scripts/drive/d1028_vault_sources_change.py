"""Acceptance drive for `vault-sources-can-be-edited-replaced-and-archived`, 2026-10-28.

The change's `ac-drive` criterion (spec/changes/vault-sources-can-be-edited-replaced-and-archived/).
It starts its own Hub on :8099 with a fresh database (never :8000 or :8010), serving the bundle
built into hub/hub/static/ui. It opens a scratch git repository as the project, with a Haiku
runner and agent, enables vault-distillation on that runner, and checks, in order:

  1. a tracked text source 'Problems' (F-1 and F-2, both open) and a second, 'Old notes', are
     distilled into facts (a real Haiku worker);
  2. a real Haiku agent turn is told to mark F-1 cleared in the vault and archive 'Old notes'.
     Its tool call is answered without error, 'Problems' holds 'F-1 the map is slow: cleared',
     and the entry's changes name the agent and its run;
  3. a background distillation of 'Problems' fires without anyone pressing Distil;
  4. the operator presses Distil on 'Problems' again. Afterwards the map lists a fact that F-1 is
     cleared; the earlier 'F-1 open' fact is still listed, with superseded_by the source and
     superseded_at set, and its vault_read says it was superseded; the F-2 fact keeps its id;
  5. 'Old notes' and its facts are absent from vault_map; vault_read of it answers archived true;
  6. the next turn's Knowledge vault line counts the entries the map now holds, one source and its
     facts fewer than before.

On today's master the agent has no edit tool, so it fails at check 2. It stops at the first
failure, so a red run spends only the distillations and the one agent turn. Run from anywhere:

    py -3.11 scripts/drive/d1028_vault_sources_change.py
"""

import json
import os
import pathlib
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8099
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
# Outside the checkout: the Hub refuses to register a project nested in a task checkout.
TMP = pathlib.Path(tempfile.gettempdir()) / "drive1028-vault-sources-change" / STAMP
DB = TMP / "hub.db"
HAIKU = "claude-haiku-4-5-20251001"
AGENT = "Scout"
JOB = "vault-distillation"
DISTIL_WAIT = 3 * 60
TURN_WAIT = 6 * 60
OPEN = "F-1 the map is slow: open"
CLEARED = "F-1 the map is slow: cleared"
F2 = "F-2 the tab flickers: open"
# The header gives the worker context to draw a fact from each terse line; the two lines
# themselves are ac-drive's.
PROBLEMS = (
    "Known problems with the app. The team must know which are open, because every open "
    "problem blocks the release.\n"
    f"{OPEN}\n{F2}\n"
)
OLD_NOTES = "The old office was on Rua Augusta. It closed in 2024 and the team moved.\n"
EDIT_TURN = (
    "Two chores in the project's knowledge vault. First, the source named 'Problems' lists "
    "F-1 as open; it has been fixed, so change that line in the vault so that it reads "
    f"exactly '{CLEARED}' (keep the F-2 line as it is). Second, archive the source named "
    "'Old notes': nobody needs it any more. Use the vault tools, not files in the repository, "
    "then say what you did in one sentence."
)
LINE_TURN = (
    "Quote, word for word, the single line of your context that begins with 'This project has "
    "a knowledge vault with'. Do not call any tool."
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
        except Exception:  # noqa: BLE001 -- a row not yet written or a file mid-write
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


def vault_map(base):
    code, body = api("GET", f"{base}/vault/map")
    return code, (body.get("entries", []) if isinstance(body, dict) else [])


def facts_of(entries, source_id):
    return [e for e in entries if e.get("kind") == "fact" and source_id in (e.get("sources") or [])]


def claim(entry):
    return entry.get("opening") or ""


def firings(base, source_id):
    _, activity = api("GET", f"{base}/manager/activity?job={JOB}&limit=200")
    found = activity.get("firings", []) if isinstance(activity, dict) else []
    return [f for f in found if (f.get("subject") or {}).get("source") == source_id]


def turn(base, message):
    """One real agent turn; returns (run id, its outputs)."""
    code, run = api("POST", f"{base}/agent/trigger", {"agent": AGENT, "message": message})
    check(f"the turn starts ({message[:30]}...)", code in (200, 202), f"{code} {run}")
    run_id = run["run_id"]
    ended = poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0]
                 not in ("running", "queued", "starting"), TURN_WAIT)
    check("the turn ends", ended, run_id)
    outputs = ro("select kind, content, payload from agent_outputs where run_id=? "
                 "order by sequence, timestamp", (run_id,))
    return run_id, outputs


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the vault change drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "vaultchange"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, out = api("POST", f"{base}/agents", {"name": AGENT, "runner_id": haiku["id"]})
    assert code in (200, 201), (code, out)
    code, job = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": True, "runner_id": haiku["id"]})
    assert code == 200 and job.get("enabled") is True, (code, job)

    # 1: both sources are distilled into facts.
    code, problems = api("POST", f"{base}/vault/sources",
                         {"name": "Problems", "type": "note", "content": PROBLEMS})
    code2, old = api("POST", f"{base}/vault/sources",
                     {"name": "Old notes", "type": "note", "content": OLD_NOTES})
    assert code == 201 and code2 == 201, (code, problems, code2, old)
    pr, oid = problems["id"], old["id"]

    def distilled():
        _, entries = vault_map(base)
        mine = facts_of(entries, pr)
        return (any("F-1" in claim(f) or "map" in claim(f).lower() for f in mine)
                and any("F-2" in claim(f) or "flicker" in claim(f).lower() for f in mine)
                and facts_of(entries, oid))

    got = poll(distilled, DISTIL_WAIT, every=3)
    _, before = vault_map(base)
    (TMP / "map_before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    open_fact = next((f for f in facts_of(before, pr) if "F-1" in claim(f) or "map" in claim(f).lower()), None)
    f2_fact = next((f for f in facts_of(before, pr) if "F-2" in claim(f) or "flicker" in claim(f).lower()), None)
    old_facts = facts_of(before, oid)
    check("1 'Problems' and 'Old notes' are distilled: an F-1 fact, an F-2 fact, a fact of the old notes",
          got and open_fact and f2_fact and old_facts,
          f"{[(e.get('id'), e.get('kind'), claim(e)[:60]) for e in before]}")
    fired_before = len(firings(base, pr))

    # 2: the agent's turn changes the vault.
    run_id, outputs = turn(base, EDIT_TURN)
    (TMP / "outputs.json").write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")
    tools = [f"{content}{payload}" for kind, content, payload in outputs if kind == "tool_use"]
    results_text = [f"{content}{payload}" for kind, content, payload in outputs if kind == "tool_result"]
    ours = [t for t in tools if pr in t and "vault_read" not in t and "vault_map" not in t]
    errored = [r for r in results_text if re.search(r'"?(status|code)"?\W{0,3}(4\d\d|5\d\d)', r)]
    check("2a the agent made a vault tool call on 'Problems' beyond reading it, and none was refused",
          ours and not errored, f"calls={[t[:160] for t in ours]} errors={[r[:160] for r in errored]}")
    _, entry = api("GET", f"{base}/vault/entries/{pr}")
    text = (entry or {}).get("content") or ""
    check("2b 'Problems' holds 'F-1 the map is slow: cleared' and still holds the F-2 line",
          CLEARED in text and F2 in text and OPEN not in text, f"text={text!r}")
    changes = (entry or {}).get("changes") or []
    recorded = json.dumps(changes)
    check("2c a change is recorded naming the agent and its run",
          changes and AGENT in recorded and run_id in recorded, f"changes={recorded[:400]}")

    # 3: a background distillation fires on its own after the edit.
    fired = poll(lambda: len(firings(base, pr)) > fired_before, DISTIL_WAIT, every=3)
    check("3 a distillation of 'Problems' fired after the edit without anyone pressing Distil",
          fired, f"before={fired_before} now={len(firings(base, pr))}")

    # 4: the operator presses Distil again.
    settled = len(firings(base, pr))
    code, queued = api("POST", f"{base}/vault/sources/{pr}/distil")
    check("4a pressing Distil on 'Problems' is accepted", code == 202, f"{code} {queued}")
    poll(lambda: len(firings(base, pr)) > settled, DISTIL_WAIT, every=3)
    time.sleep(5)

    def cleared_fact_listed():
        _, entries = vault_map(base)
        return any(not f.get("superseded_at") and "cleared" in claim(f).lower()
                   and ("F-1" in claim(f) or "map" in claim(f).lower()) for f in facts_of(entries, pr))

    check("4b the map lists a fact that F-1 is cleared", poll(cleared_fact_listed, DISTIL_WAIT, every=3))
    _, after = vault_map(base)
    (TMP / "map_after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    old_open = next((e for e in after if e.get("id") == open_fact["id"]), None)
    code, read_open = api("GET", f"{base}/vault/entries/{open_fact['id']}")
    check("4c the earlier 'F-1 open' fact is listed with superseded_by the source and superseded_at set",
          old_open and old_open.get("superseded_by") == pr and old_open.get("superseded_at"),
          f"{old_open}")
    check("4d its vault_read says it was superseded",
          code == 200 and "superseded" in json.dumps(read_open).lower(), f"{code} {str(read_open)[:300]}")
    f2_now = next((e for e in after if e.get("id") == f2_fact["id"]), None)
    check("4e the F-2 fact keeps its id and is not superseded",
          f2_now and not f2_now.get("superseded_at"), f"{f2_now}")

    # 5: 'Old notes' and its facts left the map; the entry still reads, archived.
    ids = {e.get("id") for e in after}
    gone = [oid] + [f["id"] for f in old_facts]
    check("5a 'Old notes' and its facts are absent from vault_map",
          not any(i in ids for i in gone), f"still listed: {[i for i in gone if i in ids]}")
    code, read_old = api("GET", f"{base}/vault/entries/{oid}")
    check("5b vault_read of 'Old notes' answers archived true",
          code == 200 and isinstance(read_old, dict) and read_old.get("archived") is True,
          f"{code} {str(read_old)[:300]}")

    # 6: the next turn's vault line counts what the map holds now.
    expected = len(after)
    _, line_outputs = turn(base, LINE_TURN)
    said = " ".join(c or "" for kind, c, _p in line_outputs if kind not in ("tool_use", "tool_result"))
    counted = re.search(r"knowledge vault with (\d+) entr", said)
    check("6 the next turn's vault line counts one source and its facts fewer than before",
          counted and int(counted.group(1)) == expected < len(before),
          f"line={said[:200]!r} map_now={expected} map_before={len(before)}")


if __name__ == "__main__":
    main()

# Expected on master: fails at step 2 (the agent has no vault edit or archive tool), so steps 3-6
# never get their precondition. It passes only once FR-2, FR-8 and FR-10 are built.
