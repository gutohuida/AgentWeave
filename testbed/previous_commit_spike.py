"""DCUSW-2 spike: start a Hub from a throwaway `git worktree` of an older commit on a restored
database. Throwaway (testbed/ is not tracked); the findings are in the DCUSW-2 commit message.

Usage: py -3.11 testbed/previous_commit_spike.py <scratch dir> <prev sha> [port]
Never touches :8000 or :8010 or their databases.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
S = Path(sys.argv[1])
PREV = sys.argv[2]
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8791
DB = S / "db" / "agentweave.db"
WT = S / "previous-commit" / PREV
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def env() -> dict:
    e = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "PYTHONPATH")}
    e["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    e["AW_BOOTSTRAP_API_KEY"] = "aw_live_" + "0" * 32
    e["AW_TICKET_SECRET"] = "1" * 64
    e["AW_PORT"] = str(PORT)
    return e


def start(code_root: Path, tag: str) -> subprocess.Popen:
    # cwd = <code_root>/hub: `-m uvicorn` puts cwd first on sys.path, so `hub` is imported from
    # this tree, not from the editable install that points at the operator's checkout.
    out = open(S / f"hub-{tag}.log", "w", encoding="utf-8")
    cmd = [sys.executable, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1"]
    cmd += ["--port", str(PORT)]
    return subprocess.Popen(
        cmd, cwd=str(code_root / "hub"), env=env(), stdout=out, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
    )


def get(path: str, timeout: float = 2.0):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
        return r.status, r.read()


def wait_healthy(proc: subprocess.Popen, limit: float = 120.0) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        if proc.poll() is not None:
            return None
        try:
            if get("/health")[0] == 200:
                return time.monotonic() - t0
        except OSError:
            pass
        time.sleep(0.5)
    return None


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(10)


def head_of(db: Path) -> str:
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return ",".join(r[0] for r in c.execute("select version_num from alembic_version"))
    finally:
        c.close()


def checksum(db: Path) -> str:
    # Content checksum through a consistent read (WAL included), not the file bytes.
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return hashlib.sha256("\n".join(c.iterdump()).encode()).hexdigest()[:16]
    finally:
        c.close()


def sqlite_copy(src: Path, dst: Path) -> None:
    s = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
    finally:
        s.close()
        d.close()


def probe(tag: str) -> dict:
    _, body = get("/health")
    has_edit = b"/dashboards/{dashboard_id}/undo" in get("/openapi.json", 10)[1]
    status, page = get("/")
    return {
        "health": json.loads(body),
        "has_cda2_routes": has_edit,
        "ui_status": status,
        "ui_is_bundle": b"<div id=\"root\"" in page or b"assets/" in page,
    }


def run(code_root: Path, tag: str) -> dict:
    p = start(code_root, tag)
    took = wait_healthy(p)
    res: dict = {"tag": tag, "pid": p.pid, "healthy_after_s": took and round(took, 1)}
    if took is not None:
        res.update(probe(tag))
    res["exit"] = p.poll()
    stop(p)
    res["db_head"] = head_of(DB)
    log(json.dumps(res))
    return res


def main() -> None:
    (S / "db").mkdir(parents=True, exist_ok=True)
    assert WT.exists(), f"make the worktree first: git worktree add --detach {WT} {PREV}"

    log("1. fresh database brought up by the PREVIOUS commit's Hub (worktree)")
    run(WT, "prev-fresh")

    backup = S / "db" / "pre-update.db"
    sqlite_copy(DB, backup)
    log(f"2. backup taken, head {head_of(backup)}, checksum {checksum(backup)}")

    log("3. NEW commit's Hub (this checkout) migrates the database forward")
    run(REPO, "new")

    log("4. PREVIOUS commit's Hub on the database the new commit migrated (no restore)")
    run(WT, "prev-unrestored")

    log("5. restore the backup over the database, then PREVIOUS commit's Hub again")
    for suffix in ("-wal", "-shm"):
        Path(str(DB) + suffix).unlink(missing_ok=True)
    DB.unlink()
    sqlite_copy(backup, DB)
    before = checksum(DB)
    run(WT, "prev-restored")
    log(f"   checksum restored={before} backup={checksum(backup)}")


if __name__ == "__main__":
    main()
