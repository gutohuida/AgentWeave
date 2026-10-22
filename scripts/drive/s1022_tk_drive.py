"""2026-10-22 day sweep: Tasks x Dependencies x Worktrees & integration, scratch Hub
(hub-up tk1022 8114). Phases:

  setup    project under testbed/drive1022t (shop package + test), haiku runner, alpha + beta,
           a `tests` check, an approved change document whose tasks chain (t-label after
           t-discount) and share files without saying so (t-tax beside t-discount), hand chain H1->H2->H3
  deps     dependency refusals: a cycle, self, unknown id, a duplicate; remove/re-add by route
  stall    S: beta's turn on S changes nothing (divergence), then the operator blocks S
  work     alpha's turn on t-discount: code, test, commit, record_evidence (awaiting review)
  fail     a pre-merge-commit hook refuses; approve t-discount -> merge failed, retryable
  dep      trigger beta on t-label while its prerequisite's merge is not in (F835)
  unhook   remove the hook (the Retry is pressed in the browser)
  skip     approve a task with no work -> a skip a retry cannot clear (F905)
  state    every task as the list returns it

  py -3.11 scripts/drive/s1022_tk_drive.py <phase>
"""

import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-tk1022.json")
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.environ.setdefault("AW_E2E_ROOT", str(ROOT / "testbed" / "drive1022t"))
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = ROOT / "testbed" / "scratch" / "s1022_tk_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
LIVE = ("running", "queued", "starting", "pending")
HAIKU = "claude-haiku-4-5-20251001"
DOC = "spec/changes/shop-discount/spec.json"


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def api(method, path, body=None):
    if path.startswith("~"):
        path = f"/projects/{S['P']}" + path[1:]
    return e2e.request(method, path, body)


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:2500]}", flush=True)


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def git(*args):
    r = subprocess.run(["git", "-C", S["DIR"], *args], capture_output=True, text=True, encoding="utf-8")
    return (r.stdout + r.stderr).strip()


def brief(t):
    keys = ("id", "title", "status", "assignee", "dependency_state", "blocked_reason", "has_open_divergence",
            "latest_integration")
    out = {k: t.get(k) for k in keys if t.get(k) is not None}
    out["pre"] = [(p["title"], p["status"]) for p in t.get("prerequisites") or []]
    return out


def task(key):
    return api("GET", f"~/tasks/{S[key]}")[1]


def trigger(agent, message, task_id=None, perm="workspace"):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    if task_id:
        body["task_id"] = task_id
    st, res = api("POST", "~/agent/trigger", body)
    say(f"trigger {agent} -> {st}", {k: res.get(k) for k in ("run_id", "status", "waiting_reason", "detail")})
    return res


def wait_run(run_id, secs=600):
    end = time.time() + secs
    while time.time() < end:
        rows = ro("select status from runs where id=?", (run_id,))
        if rows and rows[0]["status"] not in LIVE:
            return rows[0]["status"]
        time.sleep(3)
    return "still-running"


def walk(key, *statuses):
    for to in statuses:
        st, res = api("PATCH", f"~/tasks/{S[key]}", {"status": to})
        say(f"{key} -> {to}: {st}", brief(res) if st == 200 else res)


def phase_setup():
    d = pathlib.Path(os.environ["AW_E2E_ROOT"]) / "aw-tk1022"
    (d / "shop").mkdir(parents=True, exist_ok=True)
    (d / "tests").mkdir(exist_ok=True)
    (d / "shop" / "__init__.py").write_text("", encoding="utf-8")
    (d / "shop" / "price.py").write_text("def total(items):\n    return sum(i['price'] for i in items)\n", encoding="utf-8")
    (d / "shop" / "labels.py").write_text(
        'CURRENCY = "EUR"\n\n\ndef label(amount):\n    return f"{amount} {CURRENCY}"\n', encoding="utf-8")
    (d / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (d / "tests" / "test_price.py").write_text(
        "from shop.price import total\n\n\ndef test_total():\n    assert total([{'price': 2}, {'price': 3}]) == 5\n",
        encoding="utf-8")
    S["P"] = e2e.cmd_setup("aw-tk1022")
    S["DIR"] = str(d)
    save()
    st, rn = api("POST", "~/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    say("runner", (st, rn.get("id")))
    for name in ("alpha", "beta"):
        st, out = api("POST", "~/agents", {"name": name, "runner_id": rn["id"]})
        say(f"agent {name}", (st, out.get("name") if isinstance(out, dict) else out))
    st, out = api("PUT", "~/settings", {"checks": [{"name": "tests", "command": "py -3.11 -m pytest -q"}]})
    say("checks", (st, out.get("checks") if isinstance(out, dict) else out))
    reqs = [
        {"key": "discount", "statement": "shop.price MUST offer discount(amount, pct) returning amount reduced by pct percent.", "modal": "MUST"},
        {"key": "label", "statement": "shop.labels MUST offer discounted_label(amount, pct) labelling the discounted amount.", "modal": "MUST"},
        {"key": "tax", "statement": "shop.price MUST offer vat(amount) returning 20 percent of amount, rounded to cents.", "modal": "MUST"},
    ]
    doc = {
        "schema_version": 1, "kind": "change-spec", "title": "Shop discounts",
        "scope": {"in_scope": ["shop package"], "non_goals": ["currencies"]},
        "requirements": reqs,
        "acceptance_criteria": [
            {"key": "c-discount", "requirement": "discount", "given": "100", "when": "discount(100, 10)", "then": "90.0",
             "how_to_check": "py -3.11 -m pytest -q"},
            {"key": "c-label", "requirement": "label", "given": "100", "when": "discounted_label(100, 10)", "then": "'90.0 EUR'",
             "how_to_check": "py -3.11 -m pytest -q"},
            {"key": "c-tax", "requirement": "tax", "given": "10", "when": "vat(10)", "then": "2.0",
             "how_to_check": "py -3.11 -m pytest -q"},
        ],
        "tasks": [
            {"key": "t-discount", "title": "Add discount()", "description": "Add discount() to shop/price.py with a test.",
             "requirements": ["discount"], "files": ["shop/price.py", "tests/test_price.py"]},
            {"key": "t-label", "title": "Add discounted_label()", "description": "Add discounted_label() to shop/labels.py.",
             "requirements": ["label"], "files": ["shop/labels.py"], "depends_on": ["t-discount"]},
            {"key": "t-tax", "title": "Add vat()", "description": "Add vat() to shop/price.py.",
             "requirements": ["tax"], "files": ["shop/price.py"]},
        ],
        "delivery": {"mode": "none"},
    }
    st, out = api("POST", "~/project/documents", {"path": DOC, "title": "Shop discounts"})
    say("doc create", (st, out.get("path") if isinstance(out, dict) else out))
    st, out = api("PUT", f"~/project/documents/{DOC}/content", {"document": doc})
    say("doc write", (st, {k: v for k, v in out.items() if k not in ("document", "html")} if isinstance(out, dict) else out))
    for step in ("close-exploration", "propose"):
        st, out = api("POST", f"~/project/documents/{step}?path={DOC}")
        say(step, (st, {k: out.get(k) for k in ("phase", "blocking", "warnings")} if isinstance(out, dict) else out))
    st, out = api("POST", f"~/project/documents/phase?path={DOC}&to=approved", {"reason": "drive", "approve_anyway": True})
    say("approve anyway", (st, out.get("phase") if isinstance(out, dict) else out))
    st, tasks = api("GET", "~/tasks")
    for t in tasks["tasks"]:
        if t.get("spec_task_key"):
            S[t["spec_task_key"]] = t["id"]
    for key, title, deps in (("H1", "H1: start of a hand chain", []), ("H2", "H2: after H1", ["H1"]),
                             ("H3", "H3: after H2", ["H2"])):
        st, t = api("POST", "~/tasks", {"title": title, "depends_on": [S[d] for d in deps]})
        say(f"create {key}", (st, brief(t) if st == 201 else t))
        S[key] = t["id"]
    st, t = api("POST", "~/tasks", {"title": "S: say OK and stop", "assignee": "beta",
                                    "description": "Reply with the single word OK. Change nothing, update no task."})
    S["S"] = t["id"]
    st, t = api("POST", "~/tasks", {"title": "N: nothing to merge", "assignee": "alpha"})
    S["N"] = t["id"]
    save()
    say("ids", S)


def phase_deps():
    st, res = api("POST", f"~/tasks/{S['H1']}/dependencies", {"depends_on": S["H3"]})
    say("cycle H1 needs H3", (st, res))
    st, res = api("POST", f"~/tasks/{S['H1']}/dependencies", {"depends_on": S["H1"]})
    say("self", (st, res))
    st, res = api("POST", f"~/tasks/{S['H1']}/dependencies", {"depends_on": "task-nope"})
    say("unknown", (st, res))
    st, res = api("POST", f"~/tasks/{S['H3']}/dependencies", {"depends_on": S["H2"]})
    say("duplicate", (st, res))
    st, res = api("POST", f"~/tasks/{S['H3']}/dependencies", {"depends_on": S["t-tax"]})
    say("H3 also needs t-tax (cross-document)", (st, res))
    st, res = api("PATCH", f"~/tasks/{S['H2']}", {"status": "in_progress"})
    say("start H2 while H1 pending", (st, res))
    for k in ("H1", "H2", "H3"):
        say(k, brief(task(k)))


def phase_stall():
    res = trigger("beta", "Reply with the single word OK. Do not call any tool and do not change any task.", S["S"])
    rid = res.get("run_id")
    say("run", wait_run(rid))
    S["run_S"] = rid
    save()
    say("S after the turn", brief(task("S")))
    st, res = api("PATCH", f"~/tasks/{S['S']}", {"status": "blocked", "blocked_reason": "Which currency should OK use?"})
    say("block S", (st, brief(res) if st == 200 else res))
    st, rec = api("GET", "~/tasks/divergences/recent")
    say("divergences", rec)


def phase_work():
    msg = (
        "Work on your task. In shop/price.py add `def discount(amount, pct): return amount * (1 - pct / 100)`. "
        "In tests/test_price.py add `test_discount` asserting discount(100, 10) == 90.0. "
        "Run `py -3.11 -m pytest -q`, then commit both files with git. "
        "Then record evidence for requirement 'discount' with the AgentWeave record_evidence tool, naming your commit. "
        "Finally move your task to completed."
    )
    walk("t-discount", "assigned")
    st, _ = api("PATCH", f"~/tasks/{S['t-discount']}", {"assignee": "alpha"})
    res = trigger("alpha", msg, S["t-discount"])
    rid = res.get("run_id")
    say("run", wait_run(rid, 900))
    S["run_work"] = rid
    save()
    say("t-discount", brief(task("t-discount")))
    st, cov = api("GET", f"~/project/spec/coverage?path={DOC}")
    say("coverage", (st, cov))
    say("evidence rows", ro("select id, requirement_id, decision, run_id from requirement_evidence"))


def phase_fail():
    hook = pathlib.Path(S["DIR"]) / ".git" / "hooks" / "pre-merge-commit"
    hook.write_text('#!/bin/sh\necho "policy: merges into master are frozen (hook)" >&2\nexit 1\n', encoding="utf-8")
    say("t-discount before", brief(task("t-discount")))
    st, allowed = api("GET", "~/tasks/transitions/allowed")
    for to in ("under_review", "approved"):
        st, res = api("PATCH", f"~/tasks/{S['t-discount']}", {"status": to})
        say(f"-> {to}", (st, brief(res) if st == 200 else res))
    st, res = api("GET", f"~/tasks/{S['t-discount']}/integrations")
    say("integrations", (st, res))


def phase_dep():
    say("t-label", brief(task("t-label")))
    api("PATCH", f"~/tasks/{S['t-label']}", {"assignee": "beta"})
    res = trigger("beta", "Work on your task: add `def discounted_label(amount, pct): return label(discount(amount, pct))` "
                  "to shop/labels.py (import discount from shop.price), then commit with git. Then move your task to completed.",
                  S["t-label"])
    S["dep_trigger"] = res
    save()
    say("queue", ro("select id, agent, status, substr(coalesce(waiting_reason,''),1,400) w from agent_queue_entries order by created_at desc limit 3")
        if ro("select name from sqlite_master where name='agent_queue_entries'") else "no table")


def phase_unhook():
    hook = pathlib.Path(S["DIR"]) / ".git" / "hooks" / "pre-merge-commit"
    if hook.exists():
        hook.unlink()
    say("hook gone", not hook.exists())


def phase_after():
    say("t-discount", brief(task("t-discount")))
    say("t-label", brief(task("t-label")))
    say("runs", ro("select id, agent, status, task_id, substr(created_at,12,8) t from runs order by created_at desc limit 5"))
    say("master", git("log", "--oneline", "-4", "master"))


def phase_skip():
    walk("N", "assigned", "in_progress", "completed", "under_review", "approved")
    st, res = api("GET", f"~/tasks/{S['N']}/integrations")
    say("N integrations", (st, res))
    say("N", brief(task("N")))
    st, res = api("POST", f"~/tasks/{S['N']}/integrations/retry")
    say("retry N anyway", (st, res))


def phase_state():
    st, tasks = api("GET", "~/tasks")
    for t in tasks["tasks"]:
        say(t["id"], brief(t))


if __name__ == "__main__":
    globals()["phase_" + sys.argv[1]]()
