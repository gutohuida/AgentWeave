"""Build a replica of the operator's Terra project for UI drives (decision vis-D6).

Reads `:8000`'s database **read-only** (`mode=ro`, SQLite backup API) and Terra's repository
(`git clone --no-hardlinks`, then every branch fetched), and writes only under
`~/.agentweave/hub/profiles/terra-replica/` and `~/Documents/aw-replica/`. Nothing is written to
`:8000`'s database or to the real Terra folder.

The copy is made inert before any Hub opens it:
  - its operator credential is replaced by a fresh one (the copy must not carry `:8000`'s key);
  - every job, manager job and loop is switched off, persisted scheduler jobs are dropped, and
    queued inbound entries are withdrawn;
  - every agent loses its runner, so nothing can start a turn even if a control is pressed;
  - Terra points at the clone (marker written, path key recomputed); any other project points at
    an empty scratch folder.

    py -3.11 scripts/drive/terra_replica.py            # build (replaces an older replica)
    py -3.11 scripts/drive/terra_replica.py --up 8130  # build, then start a Hub on it

Prints the Hub URL, the database path and the operator key for the drive to use.
"""

import json
import os
import pathlib
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.request

HOME = pathlib.Path.home()
SOURCE_DB = HOME / ".agentweave" / "hub" / "data" / "agentweave.db"
PROFILE = HOME / ".agentweave" / "hub" / "profiles" / "terra-replica"
DB = PROFILE / "agentweave.db"
ROOT = HOME / "Documents" / "aw-replica"
TERRA_ID = "proj-cd006955cbe2"
REPO = pathlib.Path(__file__).resolve().parents[2]
PY311 = os.environ.get("AW_PY311") or str(
    HOME / "AppData" / "Local" / "Programs" / "Python" / "Python311" / "python.exe"
)
STATE = HOME / ".agentweave" / "e2e-replica.json"

sys.path.insert(0, str(REPO / "hub"))
from hub.project_workspace import canonical_path_key  # noqa: E402


def _force_remove(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def copy_database():
    PROFILE.mkdir(parents=True, exist_ok=True)
    for stale in PROFILE.glob("agentweave.db*"):
        stale.unlink()
    source = sqlite3.connect(SOURCE_DB.as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(DB)
    source.backup(target)
    source.close()
    return target


def clone_repositories(projects):
    if ROOT.exists():
        shutil.rmtree(ROOT, onerror=_force_remove)
    ROOT.mkdir(parents=True)
    bindings = {}
    for project_id, name, directory in projects:
        if project_id == TERRA_ID:
            dest = ROOT / "Terra"
            git("clone", "-q", "--no-hardlinks", directory, str(dest))
            git("fetch", "-q", "origin", "+refs/heads/*:refs/heads/*", "--update-head-ok", cwd=dest)
            git("checkout", "-q", "master", cwd=dest)
            # The Hub reads spec documents from the working tree, and Terra's has documents git
            # never saw (an untracked change read "wording could not be read" on the clone).
            source_spec = pathlib.Path(directory) / "spec"
            if source_spec.is_dir():
                shutil.copytree(source_spec, dest / "spec", dirs_exist_ok=True)
        else:
            dest = ROOT / f"empty-{project_id}"
            dest.mkdir()
        marker = dest / ".agentweave" / "project.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"version": 1, "project_id": project_id}), encoding="utf-8")
        bindings[project_id] = dest
    return bindings


def make_inert(con, bindings):
    key = f"aw_live_{secrets.token_hex(16)}"
    con.execute("delete from operator_credentials")
    con.execute(
        "insert into operator_credentials (id, label, revoked, created_at) values (?, ?, 0, ?)",
        (key, "terra-replica", time.strftime("%Y-%m-%d %H:%M:%S")),
    )
    con.execute("update ai_jobs set enabled = 0")
    con.execute("update manager_jobs set enabled = 0")
    con.execute(
        "update loops set stopped_at = coalesce(stopped_at, ?), "
        "stop_reason = coalesce(stop_reason, 'replica')",
        (time.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    con.execute("delete from apscheduler_jobs")
    con.execute(
        "update inbound_queue_entries set state = 'withdrawn', withdrawn_at = ? where state = 'queued'",
        (time.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    con.execute("update agents set runner_id = null")
    for project_id, dest in bindings.items():
        con.execute(
            "update projects set working_directory = ?, path_key = ?, directory_state = 'available' "
            "where id = ?",
            (str(dest), canonical_path_key(dest), project_id),
        )
    con.commit()
    return key


def start_hub(port):
    env = dict(os.environ)
    env["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(DB).replace("\\", "/")
    log = pathlib.Path(os.environ.get("TEMP", str(HOME))) / f"agentweave-hub-{port}.log"
    flags = 0x00000008 | 0x00000200 | 0x01000000 if os.name == "nt" else 0
    cmd = [PY311, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1", "--port", str(port)]
    with open(log, "ab") as out:
        proc = subprocess.Popen(cmd, cwd=REPO / "hub", env=env, stdout=out, stderr=out,
                                creationflags=flags)
    url = f"http://127.0.0.1:{port}"
    for _ in range(90):
        try:
            with urllib.request.urlopen(url + "/health", timeout=2):
                break
        except OSError:
            time.sleep(1)
    else:
        raise SystemExit(f"replica Hub did not come up; read {log}")
    return url, proc.pid, log


def main():
    if "--up" in sys.argv:
        port = sys.argv[sys.argv.index("--up") + 1]
        if port in ("8000", "8010"):
            raise SystemExit("8000 is the operator's and 8010 is the trial Hub")
    con = copy_database()
    projects = con.execute("select id, name, working_directory from projects").fetchall()
    bindings = clone_repositories(projects)
    key = make_inert(con, bindings)
    con.close()
    print("DB=" + str(DB))
    print("KEY=" + key)
    for project_id, dest in bindings.items():
        print(f"PROJECT {project_id} -> {dest}")
    if "--up" in sys.argv:
        url, pid, log = start_hub(port)
        STATE.write_text(json.dumps({"hub": url, "db": str(DB), "pid": pid, "port": int(port),
                                     "log": str(log), "key": key}), encoding="utf-8")
        print("HUB=" + url, "PID=" + str(pid), "LOG=" + str(log))


if __name__ == "__main__":
    main()
