"""2026-10-20 Tasks x Dependencies x Worktrees sweep (scratch Hub :8170): the task machine, actor
boundaries, A->B->C dependencies, integration failure and Retry.

    AW_P=proj-... py -3.11 scripts/drive/s1020_t_tasks.py <step> [args]
"""

import json
import pathlib
import sys

from s1020_t_lib import P, q, req, show

B = f"projects/{P}"
STATE = pathlib.Path.home() / ".agentweave" / "e2e-t1020-tasks.json"
S = json.loads(STATE.read_text()) if STATE.exists() else {}


def save():
    STATE.write_text(json.dumps(S, indent=1))


def brief(t):
    return {k: t.get(k) for k in ("id", "title", "status", "assignee", "depends_on", "blocked_by", "blocking")}


def setup():
    show("PUT", f"{B}/settings", {"checks": [{"name": "tests", "command": "py -3.11 -m pytest -q"}]}, limit=400)
    st, a = req("POST", f"{B}/tasks", {"title": "A: add discount() to shop/price.py", "assignee": "alpha",
        "description": "Add `def discount(amount, pct)` to shop/price.py returning amount*(1-pct/100), with a test in tests/test_price.py. Commit it."})
    print("A", st, brief(a))
    st, b = req("POST", f"{B}/tasks", {"title": "B: label discounted totals", "assignee": "beta", "depends_on": [a["id"]],
        "description": "Add `def discounted_label(amount, pct)` to shop/labels.py that uses shop.price.discount and label(). Commit it."})
    print("B", st, brief(b))
    st, c = req("POST", f"{B}/tasks", {"title": "C: README for discounts", "assignee": "gamma", "depends_on": [b["id"]],
        "description": "Write README.md describing discount() and discounted_label(). Commit it."})
    print("C", st, brief(c))
    S.update(A=a["id"], B=b["id"], C=c["id"]); save()


def probes():
    a, b, c = S["A"], S["B"], S["C"]
    show("POST", f"{B}/tasks", {"title": "bad dep", "depends_on": ["task-nope"]}, limit=600)
    show("POST", f"{B}/tasks/{a}/dependencies", {"depends_on": c}, limit=600)   # cycle
    show("POST", f"{B}/tasks/{a}/dependencies", {"depends_on": a}, limit=600)   # self
    show("POST", f"{B}/tasks/{c}/dependencies", {"depends_on": b}, limit=600)   # duplicate
    show("DELETE", f"{B}/tasks/{c}/dependencies/task-nope", limit=600)
    show("PATCH", f"{B}/tasks/{b}", {"status": "in_progress"}, limit=900)       # B before A approved
    show("PATCH", f"{B}/tasks/{b}", {"status": "pending"}, limit=300)
    show("PATCH", f"{B}/tasks/{a}", {"title": "A: add discount() to shop/price.py (renamed)"}, limit=300)
    show("PATCH", f"{B}/tasks/{a}", {"title": "   "}, limit=600)
    show("PATCH", f"{B}/tasks/{a}", {"title": "x" * 300}, limit=600)
    show("PATCH", f"{B}/tasks/{a}", {"priority": "high"}, limit=200)
    t = req("GET", f"{B}/tasks/{a}")[1]
    print("A after priority-only PATCH: assignee", t.get("assignee"), "priority", t.get("priority"))
    show("PATCH", f"{B}/tasks/{a}", {"priority": "urgent-ish"}, limit=600)
    show("PATCH", f"{B}/tasks/{a}", {"status": "approved"}, limit=900)          # pending -> approved
    show("PATCH", f"{B}/tasks/{a}", {"status": "bogus"}, limit=600)
    show("PATCH", f"{B}/tasks/{a}", {"assignee": "nobody-here"}, limit=600)
    show("GET", f"{B}/tasks/transitions/allowed", limit=1500)


def board():
    st, bd = req("GET", f"{B}/tasks/board")
    print("board", st, json.dumps(bd, ensure_ascii=False)[:1500])
    st, bds = req("GET", f"{B}/tasks/boards")
    print("boards", st, json.dumps(bds, ensure_ascii=False)[:1500])


def story(tid):
    tid = S.get(tid, tid)
    st, s = req("GET", f"{B}/tasks/{tid}/story")
    print("story", st, json.dumps(s, ensure_ascii=False, indent=1)[:6000])
    st, tr = req("GET", f"{B}/tasks/{tid}/transitions")
    print("transitions", st, json.dumps(tr, ensure_ascii=False, indent=1)[:3000])
    for r in q("select from_status, to_status, actor_kind, actor_agent, origin, substr(created_at,12,8) t from task_transitions where task_id=? order by created_at", tid):
        print("  DB", r)


def show_tasks():
    for k in ("A", "B", "C"):
        t = req("GET", f"{B}/tasks/{S[k]}")[1]
        print(k, json.dumps(brief(t), ensure_ascii=False))
    for r in q("select id, agent, status, task_id, substr(started_at,12,8) t, error from runs where project_id=? order by started_at desc limit 8", P):
        print("  RUN", r)


if __name__ == "__main__":
    fn = globals()[sys.argv[1]]
    fn(*sys.argv[2:])
