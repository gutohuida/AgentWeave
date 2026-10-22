"""2026-10-22 Spec documents x Corpus & folding sweep, API steps (scratch Hub :8121, profile sp1022).

  doc <name> [keys]   an approved change (close, propose, approve anyway); records its tasks
  turn <name> <key> <msg>   a real Haiku turn by `builder` on the task, waited out
  task <name> <key> <status>  move a task (operator)
  cov <name>          coverage of the document
  events [n]          recent event types

    AW_P=proj-... py -3.11 scripts/drive/s1022_sp_drive.py <step> [args]
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_sp_lib import B, DOCS, P, e2e, payload, req, show  # noqa: E402

STATE = pathlib.Path.home() / ".agentweave" / "e2e-sp1022-drive.json"
S = json.loads(STATE.read_text()) if STATE.exists() else {}


def save():
    STATE.write_text(json.dumps(S, indent=1))


def doc(name, keys="alpha,beta"):
    sfx = time.strftime("%H%M%S")
    path = f"spec/changes/{name}/spec.json"
    show("POST", DOCS, {"path": path, "title": f"{name} {sfx}"}, 300)
    show("PUT", f"{DOCS}/{path}/content", {"document": payload(f"{name} {sfx}", sfx, keys=tuple(keys.split(",")))}, 300)
    show("POST", f"{DOCS}/close-exploration?path={path}", None, 200)
    show("POST", f"{DOCS}/propose?path={path}", None, 300)
    show("POST", f"{DOCS}/phase?path={path}&to=approved", {"reason": "drive", "approve_anyway": True}, 300)
    st, tasks = req("GET", f"{B}/tasks")
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
    st, t = req("GET", f"{B}/tasks/{tid}")
    print("TASK", st, {k: t.get(k) for k in ("id", "status", "assignee")})


def task(name, key, status):
    tid = S[name]["tasks"][key]
    show("PATCH", f"{B}/tasks/{tid}", {"status": status}, 1500)


def cov(name):
    path = S[name]["path"] if name in S else name
    st, c = req("GET", f"{B}/project/spec/coverage?document={path}")
    print(st)
    for r in (c.get("requirements") or []) if isinstance(c, dict) else []:
        print(" ", r.get("identifier"), r.get("state"), r.get("integration"))
    if isinstance(c, dict):
        print("  diagnostics", c.get("diagnostics"), "summary", c.get("summary"))
    else:
        print(c)


def events(n="15"):
    st, h = req("GET", f"{B}/events/history?limit={n}")
    hist = h if isinstance(h, list) else h.get("events", [])
    for ev in hist:
        print("  ", ev.get("event_type"), json.dumps(ev.get("data") or ev.get("payload"), ensure_ascii=False)[:260])


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
