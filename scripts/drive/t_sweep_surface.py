"""Full-surface sweep: everything reachable without spending an agent turn.

Rows 1-4, 7, 8, 13 and 18 of the e2e-loop coverage matrix, plus the cross-cutting question
the skill puts above all of them — **is every refusal legible?** A gate that refuses correctly and
says only "forbidden" is a defect, because the refused party's only feedback is that string.

Routes are taken from the running Hub's own `/openapi.json`, not guessed. The first pass of this
script guessed six of them and reported five false 404s — worth stating, because a sweep that
reports its own wrong turns as product defects is worse than no sweep. The one guess kept is the
`SHADOW` probe below, because a path one segment short of a real one turned out to say something
misleading.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_sweep_surface.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

RESULTS = []


def probe(row, label, method, path, body=None, expect=None):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    detail = out.get("detail") if isinstance(out, dict) else None
    RESULTS.append((row, label, code, ok, detail if isinstance(detail, str) else None))
    print(f"[{row}] {label}: {code}{'' if ok else '  <-- UNEXPECTED'}")
    if isinstance(detail, str):
        print(f"      refusal: {detail[:260]}")
    elif not ok:
        print(f"      body: {json.dumps(out, default=str)[:300]}")
    return code, out


print("=" * 78)
print("ROW 1 — projects, settings, filesystem")
print("=" * 78)
probe(1, "list projects", "GET", "/projects", expect=200)
probe(1, "read settings", "GET", f"/projects/{P}/settings", expect=200)
probe(1, "filesystem roots", "GET", "/fs/roots", expect=200)
probe(1, "list a directory", "GET", "/fs/list?path=C:/Users/huida/Documents", expect=200)
probe(1, "list a directory that does not exist", "GET", "/fs/list?path=C:/nope/nothing")
probe(1, "open a folder that does not exist", "POST", "/projects/open", {"path": "C:/nope/nothing"})
probe(1, "hop budget below one", "PUT", f"/projects/{P}/settings", {"hop_budget": -1})
probe(1, "a main branch that does not exist", "PUT", f"/projects/{P}/settings",
      {"main_branch": "no-such-branch"})

print()
print("=" * 78)
print("ROW 2 — runners, launchability, model catalog")
print("=" * 78)
probe(2, "list runners", "GET", f"/projects/{P}/runners", expect=200)
probe(2, "launchability", "GET", f"/projects/{P}/agents/launchability", expect=200)
probe(2, "create a runner with an unsupported cli", "POST", f"/projects/{P}/runners",
      {"name": "bad", "cli": "kimi"})

print()
print("=" * 78)
print("ROW 3 — agents")
print("=" * 78)
# `/agents/context` is the *charter*-content route and requires `?charter=<id>`; the
# canonical per-agent context the matrix means is `/agents/agent-context?agent=<name>`.
# The first version of this probe called the former with no query and reported its 422 as a
# product defect. Corrected 2026-08-30.
probe(3, "canonical context", "GET", f"/projects/{P}/agents/agent-context?agent=driver",
      expect=200)
probe(3, "canonical context for an agent that does not exist", "GET",
      f"/projects/{P}/agents/agent-context?agent=ghost-agent", expect=200)
probe(3, "canonical context for an illegal agent name", "GET",
      f"/projects/{P}/agents/agent-context?agent=not%20a%20name")
probe(3, "timeline for driver", "GET", f"/projects/{P}/agents/driver/timeline", expect=200)
probe(3, "archive an agent holding queued input", "POST",
      f"/projects/{P}/agents/unbound-driver/archive")
probe(3, "archive an agent with an empty queue", "POST", f"/projects/{P}/agents/driver/archive",
      expect=200)
probe(3, "trigger the agent just archived", "POST", f"/projects/{P}/agent/trigger",
      {"agent": "driver", "message": "hello", "session_mode": "new"})
probe(3, "unarchive it again", "POST", f"/projects/{P}/agents/driver/unarchive", expect=200)

print()
print("=" * 78)
print("ROW 4 — charters")
print("=" * 78)
code, charters = probe(4, "list charters", "GET", f"/projects/{P}/charters", expect=200)
if isinstance(charters, list):
    print(f"      seeded: {len(charters)} -> {[c.get('name') for c in charters][:12]}")
probe(4, "create a charter", "POST", f"/projects/{P}/charters",
      {"name": "sweep-charter", "content": "Drive the product honestly."}, expect=(200, 201))
probe(4, "create a charter with a duplicate name", "POST", f"/projects/{P}/charters",
      {"name": "sweep-charter", "content": "again"})
probe(4, "create a charter with empty content", "POST", f"/projects/{P}/charters",
      {"name": "sweep-empty", "content": ""})

print()
print("=" * 78)
print("ROW 7 — tasks and the transition machine, refusal by refusal")
print("=" * 78)
probe(7, "allowed transitions", "GET", f"/projects/{P}/tasks/transitions/allowed", expect=200)
probe(7, "SHADOW: /tasks/transitions (one path segment short)", "GET",
      f"/projects/{P}/tasks/transitions")
code, task = probe(7, "create a task", "POST", f"/projects/{P}/tasks",
                   {"title": "Sweep subject task"}, expect=(200, 201))
tid = task.get("id") if isinstance(task, dict) else None
if tid:
    probe(7, "jump straight to approved", "PATCH", f"/projects/{P}/tasks/{tid}",
          {"status": "approved"})
    probe(7, "clear the assignee with null", "PATCH", f"/projects/{P}/tasks/{tid}",
          {"assignee": None}, expect=200)
    probe(7, "assign to an agent that does not exist", "PATCH", f"/projects/{P}/tasks/{tid}",
          {"assignee": "ghost-agent"})
    probe(7, "in_progress then completed then approved by nobody", "PATCH",
          f"/projects/{P}/tasks/{tid}", {"status": "in_progress"}, expect=200)
    probe(7, "  -> completed", "PATCH", f"/projects/{P}/tasks/{tid}", {"status": "completed"},
          expect=200)
    probe(7, "  -> approved with no review and no evidence", "PATCH",
          f"/projects/{P}/tasks/{tid}", {"status": "approved"})

print()
print("=" * 78)
print("ROW 8 — dependencies")
print("=" * 78)
code, a = api("POST", f"/projects/{P}/tasks", {"title": "Sweep A"})
code, b = api("POST", f"/projects/{P}/tasks", {"title": "Sweep B"})
aid = a.get("id") if isinstance(a, dict) else None
bid = b.get("id") if isinstance(b, dict) else None
if aid and bid:
    probe(8, "B depends on A", "POST", f"/projects/{P}/tasks/{bid}/dependencies",
          {"depends_on": aid}, expect=(200, 201))
    probe(8, "A depends on B (a cycle)", "POST", f"/projects/{P}/tasks/{aid}/dependencies",
          {"depends_on": bid})
    probe(8, "a task depends on itself", "POST", f"/projects/{P}/tasks/{aid}/dependencies",
          {"depends_on": aid})
    probe(8, "depends on a task that does not exist", "POST",
          f"/projects/{P}/tasks/{bid}/dependencies", {"depends_on": "task-nope"})
    probe(8, "start B while A is unapproved", "PATCH", f"/projects/{P}/tasks/{bid}",
          {"status": "in_progress"})

print()
# ROW 9 lives in `t_sweep_spec.py`, against the routes the Hub actually publishes
# (`/projects/{id}/project/documents`, with `path` and `to` as query parameters). It was
# probed here first against guessed paths, which produced five false 404s and no information.
print("=" * 78)
print("ROW 9 — see t_sweep_spec.py")
print("=" * 78)
print("ROW 13 — questions")
print("=" * 78)
probe(13, "list questions", "GET", f"/projects/{P}/questions", expect=200)
probe(13, "answer a question that does not exist", "PATCH", f"/projects/{P}/questions/q-nope",
      {"answer": "yes"})

print()
print("=" * 78)
print("ROW 18 — accounting and budgets")
print("=" * 78)
probe(18, "project accounting", "GET", f"/projects/{P}/accounting", expect=200)
probe(18, "set a token budget", "PUT", f"/projects/{P}/settings", {"token_budget": 1000},
      expect=200)
probe(18, "set a negative token budget", "PUT", f"/projects/{P}/settings", {"token_budget": -5})
probe(18, "clear the token budget", "PUT", f"/projects/{P}/settings", {"token_budget": None},
      expect=200)

print()
print("=" * 78)
print("SUMMARY")
print("=" * 78)
unexpected = [r for r in RESULTS if not r[3]]
print(f"unexpected statuses: {len(unexpected)}")
for row, label, code, _ok, detail in unexpected:
    print(f"  [{row}] {label} -> {code}  {(detail or '')[:120]}")

REMEDY = ("try", "use ", "first", "instead", "bind", "create", "reassign", "unarchive", "correct",
          "wait", "set ", "remove", "valid", "must", "should", "run ", "choose", "available",
          "cannot depend on itself", "already", "reopen", "close")
print()
print("4xx refusals whose message names no remedy:")
for row, label, code, _ok, detail in RESULTS:
    if detail and 400 <= code < 500 and not any(w in detail.lower() for w in REMEDY):
        print(f"  [{row}] {code} {label}")
        print(f"        {detail[:200]}")
