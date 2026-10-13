"""A small client for driving sweeps against a scratch Hub started by hand, 2026-10-13.

The per-slice drives (d10xx_*.py) each start and stop their own Hub. A driving sweep instead keeps
one scratch Hub up across many probes, so this module only talks to it. Start the Hub from `hub/`
with DATABASE_URL naming a fresh database under testbed/ and AW_BOOTSTRAP_API_KEY set, then set
SWEEP_PORT, SWEEP_KEY and SWEEP_DB in the environment (or pass them to `configure`).
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

CFG = {
    "port": os.environ.get("SWEEP_PORT", "8110"),
    "key": os.environ.get("SWEEP_KEY", ""),
    "db": os.environ.get("SWEEP_DB", ""),
}
HAIKU = "claude-haiku-4-5-20251001"


def hub():
    return f"http://127.0.0.1:{CFG['port']}"


def call(method, path, data=None, content_type="application/json", timeout=60, token=None):
    """(status, headers, raw bytes); status 0 when the Hub cannot be reached."""
    request = urllib.request.Request(
        hub() + "/api/v1" + path, data,
        {"Authorization": "Bearer " + (token or CFG["key"]), "Content-Type": content_type},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
    except urllib.error.URLError as exc:
        return 0, {}, str(exc).encode()


def api(method, path, body=None, timeout=60, token=None):
    data = json.dumps(body).encode() if body is not None else None
    code, _, raw = call(method, path, data, timeout=timeout, token=token)
    try:
        return code, json.loads(raw or b"null")
    except ValueError:
        return code, raw.decode(errors="replace")[:2000]


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{CFG['db']}?mode=ro", uri=True)
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
        except Exception:  # noqa: BLE001 -- a file mid-write
            pass
        time.sleep(every)
    return False


def records(folder, prefix):
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.glob(f"{prefix}-*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            pass
    return out


def turn(base, agent, message, wait=6 * 60):
    """One agent turn; (run_id, status, outputs)."""
    code, run = api("POST", f"{base}/agent/trigger", {"agent": agent, "message": message})
    if code not in (200, 202):
        return None, f"trigger {code} {run}", []
    run_id = run["run_id"]
    poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0]
         not in ("running", "queued", "starting", "pending"), wait, every=2)
    status = ro("select status from runs where id=?", (run_id,))[0][0]
    outputs = ro("select kind, content, payload from agent_outputs where run_id=? "
                 "order by sequence, timestamp", (run_id,))
    return run_id, status, outputs
