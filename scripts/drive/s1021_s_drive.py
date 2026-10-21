"""2026-10-21 Spec documents x Corpus & folding sweep (scratch Hub :8150, profile s1021): an approved
change whose two tasks were worked by real Haiku turns (one commits, one does not), for deleting the
document with kept work (F828) and from the phase bar (F829, s1021_s_ui.py).

    AW_E2E_STATE=C:/Users/huida/.agentweave/e2e-s1021.json AW_P=proj-... \
        py -3.11 scripts/drive/s1021_s_drive.py <step> [args]
"""

import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1019_spec_lib import e2e, payload, request  # noqa: E402

P = os.environ["AW_P"]
B = f"/projects/{P}"
D = pathlib.Path.home() / "Documents" / "aw-s-1021"
STATE = pathlib.Path.home() / ".agentweave" / "e2e-s1021-drive.json"
S = json.loads(STATE.read_text()) if STATE.exists() else {}


def save():
    STATE.write_text(json.dumps(S, indent=1))


def git(*args):
    r = subprocess.run(["git", "-C", str(D), *args], capture_output=True, text=True, encoding="utf-8")
    return (r.stdout + r.stderr).strip()


def show(method, path, body=None, limit=2000):
    st, out = request(method, path, body)
    print(f"{method} {path} -> {st}\n  {json.dumps(out, ensure_ascii=False)[:limit]}")
    return st, out


def doc(name):
    """An approved change named `name`, with tasks t-alpha and t-beta; prints the task ids."""
    sfx = time.strftime("%H%M%S")
    path = f"spec/changes/{name}/spec.json"
    base = f"{B}/project/documents"
    show("POST", base, {"path": path, "title": f"{name} {sfx}"}, 300)
    show("PUT", f"{base}/{path}/content", {"document": payload(f"{name} {sfx}", sfx, keys=("alpha", "beta"))}, 300)
    show("POST", f"{base}/close-exploration?path={path}", None, 200)
    show("POST", f"{base}/propose?path={path}", None, 300)
    show("POST", f"{base}/phase?path={path}&to=approved", {"reason": "drive", "approve_anyway": True}, 300)
    st, tasks = request("GET", f"{B}/tasks")
    mine = {t["spec_task_key"]: t["id"] for t in tasks["tasks"] if sfx in t["title"]}
    print("tasks:", mine)
    S[name] = {"path": path, "tasks": mine}
    save()


def turn(name, key, msg):
    tid = S[name]["tasks"][key]
    rid = e2e.cmd_turn(P, "builder", msg, task=tid, perm="workspace", fresh=True)
    S[name][f"run_{key}"] = rid
    save()
    if rid:
        e2e.cmd_watch(rid, 10)
    st, t = request("GET", f"{B}/tasks/{tid}")
    print("TASK", st, {k: t.get(k) for k in ("id", "status", "assignee")})


def checkouts():
    print(git("worktree", "list"))
    print(git("branch", "--list", "agentweave/*", "-v"))


def delete_api(name):
    path = S[name]["path"]
    checkouts()
    show("DELETE", f"{B}/project/documents/{path}", None, 3000)
    checkouts()
    events()


def events(n=8):
    st, h = request("GET", f"{B}/events/history?limit=40")
    hist = h if isinstance(h, list) else h.get("events", [])
    for ev in [e for e in hist if any(w in json.dumps(e) for w in ("deleted", "checkout_kept"))][:n]:
        print("  EVENT", json.dumps(ev, ensure_ascii=False)[:500])


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
