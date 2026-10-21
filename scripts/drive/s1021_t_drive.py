"""2026-10-21 Tasks x Dependencies x Worktrees sweep (scratch Hub :8150): deleting a prerequisite
(F825), deleting a task with a clean or a worked checkout (F828), a failed merge's Try again (F823),
then one path per row.

    AW_P=proj-... py -3.11 scripts/drive/s1021_t_drive.py <step> [args]
"""

import json
import pathlib
import subprocess
import sys

from s1021_t_lib import HAIKU, P, e2e, q, req, show

B = f"projects/{P}"
D = pathlib.Path.home() / "Documents" / "aw-t-1021"
STATE = pathlib.Path.home() / ".agentweave" / "e2e-t1021-tasks.json"
S = json.loads(STATE.read_text()) if STATE.exists() else {}


def save():
    STATE.write_text(json.dumps(S, indent=1))


def git(*args):
    r = subprocess.run(["git", "-C", str(D), *args], capture_output=True, text=True, encoding="utf-8")
    return (r.stdout + r.stderr).strip()


def brief(t):
    keys = ("id", "title", "status", "assignee", "depends_on", "dependency_state", "prerequisites")
    return {k: t.get(k) for k in keys if k in t}


def task(title, **kw):
    st, t = req("POST", f"{B}/tasks", {"title": title, **kw})
    print("create", st, json.dumps(brief(t), ensure_ascii=False)[:400])
    return t["id"]


def events(kind, limit=5):
    for r in q(
        "select event_type, data, substr(timestamp,12,8) t from event_logs where project_id=? and event_type=? "
        "order by timestamp desc limit ?", P, kind, limit
    ):
        print(f"  EVENT {r['t']} {r['event_type']} {r['data']}")


def setup():
    (D / "shop").mkdir(exist_ok=True)
    (D / "shop" / "__init__.py").write_text("", encoding="utf-8")
    (D / "shop" / "price.py").write_text(
        "def total(items):\n    return sum(i['price'] for i in items)\n", encoding="utf-8"
    )
    (D / "shop" / "labels.py").write_text(
        'CURRENCY = "EUR"\n\n\ndef label(amount):\n    return f"{amount} {CURRENCY}"\n', encoding="utf-8"
    )
    (D / "tests").mkdir(exist_ok=True)
    (D / "tests" / "test_price.py").write_text(
        "from shop.price import total\n\n\ndef test_total():\n    assert total([{'price': 2}, {'price': 3}]) == 5\n",
        encoding="utf-8",
    )
    print(git("add", "-A"), git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "shop"))
    st, runner = req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    print("runner", st, runner.get("id"))
    S["runner"] = runner["id"]
    for name in ("alpha", "beta"):
        show("POST", f"{B}/agents", {"name": name, "runner_id": runner["id"]}, limit=200)
    show("PUT", f"{B}/settings", {"checks": [{"name": "tests", "command": "py -3.11 -m pytest -q"}]}, limit=300)
    save()


def prereq_api():
    """F825 by API: delete a prerequisite of two gated tasks; the event names both."""
    p = task("P: prerequisite to delete")
    d1 = task("D1: waits on P", depends_on=[p])
    d2 = task("D2: also waits on P", depends_on=[p])
    for d in (d1, d2):
        print("before", json.dumps(brief(req("GET", f"{B}/tasks/{d}")[1]), ensure_ascii=False))
    show("DELETE", f"{B}/tasks/{p}", limit=400)
    for d in (d1, d2):
        print("after", json.dumps(brief(req("GET", f"{B}/tasks/{d}")[1]), ensure_ascii=False))
    events("task_deleted", 2)
    st, h = req("GET", f"{B}/events/history?limit=20")
    hist = h if isinstance(h, list) else h.get("events", h)
    for ev in (hist or [])[:20]:
        if isinstance(ev, dict) and "deleted" in json.dumps(ev):
            print("  HISTORY", json.dumps(ev, ensure_ascii=False)[:500])
    show("DELETE", f"{B}/tasks/{p}", limit=300)   # again: 404
    S.update(D1=d1, D2=d2); save()


def prereq_ui_setup():
    p = task("P2: prerequisite deleted from the drawer")
    d3 = task("D3: waits on P2 (drawer)", depends_on=[p])
    S.update(P2=p, D3=d3); save()


def work_tasks():
    """Three tasks for real turns: K1 commits, K2 commits nothing, A commits and is B's prerequisite."""
    S["K1"] = task("K1: add shop/tax.py", assignee="alpha",
                   description="Create shop/tax.py with `def vat(amount): return round(amount * 0.2, 2)`. Commit it with git.")
    S["K2"] = task("K2: read-only look", assignee="beta",
                   description="Read shop/price.py and reply with one sentence about what total() does. Do not edit or create any file, do not commit.")
    S["A"] = task("A: add discount() to shop/price.py", assignee="alpha",
                  description="Add `def discount(amount, pct): return amount * (1 - pct / 100)` to shop/price.py and a test `test_discount` in tests/test_price.py. Run the tests, then commit with git.")
    S["B"] = task("B: discounted label", assignee="beta", depends_on=[S["A"]],
                  description="Add `def discounted_label(amount, pct)` to shop/labels.py that returns label(discount(amount, pct)) using shop.price.discount. Commit it with git.")
    save()


def turn(agent, key, msg):
    tid = S[key]
    rid = e2e.cmd_turn(P, agent, msg, task=tid, perm="workspace", fresh=True)
    S[f"run_{key}"] = rid; save()
    if rid:
        e2e.cmd_watch(rid, 10)
    print("TASK", json.dumps(brief(req("GET", f"{B}/tasks/{tid}")[1]), ensure_ascii=False))


def checkouts():
    print(git("worktree", "list"))
    print(git("branch", "--list", "agentweave/*", "-v"))
    st, w = req("GET", f"{B}/worktrees")
    print("GET worktrees", st, json.dumps(w, ensure_ascii=False)[:1500])


def delete(key):
    tid = S[key]
    print("checkout before:", [l for l in git("worktree", "list").splitlines() if tid in l])
    show("DELETE", f"{B}/tasks/{tid}", limit=400)
    print("checkout after:", [l for l in git("worktree", "list").splitlines() if tid in l])
    print("branch after:", git("branch", "--list", f"agentweave/task/{tid}", "-v") or "<none>")
    events("task_deleted", 1)
    events("task_checkout_kept", 3)


def hook(on):
    h = D / ".git" / "hooks" / "pre-merge-commit"
    if on == "on":
        h.write_text('#!/bin/sh\necho "policy: merges into master are frozen (hook)" >&2\nexit 1\n', encoding="utf-8")
    elif h.exists():
        h.unlink()
    print("hook", on, h.exists())


def move(key, to, **extra):
    show("PATCH", f"{B}/tasks/{S[key]}", {"status": to, **extra}, limit=1500)


def integ(key):
    show("GET", f"{B}/tasks/{S[key]}/integrations", limit=2500)
    print("master:", git("log", "--oneline", "-4", "master"))


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
