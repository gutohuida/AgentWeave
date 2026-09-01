"""SWEEP ROW 15 — WORKTREES. Who can see the isolation, and what the conflict check is blind to.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 t_sweep_row15_worktrees.py
    AW_HUB=... AW_KEY=... py -3.11 t_sweep_row15_worktrees.py --teardown

**Prior coverage was read first and is deliberately not re-ploughed.** `t_row16_worktrees.py`
(the old row numbering) drove the mechanism on 2026-08-29 and `FINDINGS.md:8093` records the
result: two agents, two tasks, one file, each edit landing on its own task branch, `main`
untouched, and `GET /worktrees/conflicts` naming both *task* workspaces and `calc.py`. Isolation
holds. That harness prints; it asserts nothing, and it stops at the point where the conflict
report exists.

So this file starts where that one stops, and asks the questions it did not:

* **Who reads the conflict report.** `detect_conflicts` is 30 lines of pairwise `git merge-tree`
  behind `GET /projects/{p}/worktrees/conflicts`. Zero call sites under `hub/ui/src`.
* **What the report is compared against.** `detect_conflicts` (`worktrees.py:1014`) pairs every
  *provisioned* workspace with every other and nothing else — not the branch the work is going to
  be merged into.
* **What happens to the report when a task ends.** `release_task_workspace`
  (`task_transition_service.py:629`) removes the checkout and keeps the branch;
  `list_workspace_branches` excludes a branch with no checkout, and `detect_conflicts` walks
  exactly that list.
* **The route the path parameter can shadow.** `/conflicts` is declared before `/{agent}` on
  purpose. `AGENT_NAME_RE` accepts `conflicts` as an agent name.
* **Whether the un-isolated state the UI describes is reachable.** `is_writing_agent`
  (`worktrees.py:213`) reads `config["read_only"]`; `AgentSettingsPage.tsx:353` writes copy for
  both sides of it.

Two projects (one a git repository, one deliberately not), three roster agents, one
self-registered agent, and two real `claude-haiku-4-5` turns. Every fixture is created here —
including `git init` and an initial commit, without which no turn can run at all — and removed by
`--teardown`.

**Re-runnable on the state it leaves.** Every function name, task title and commit subject carries
the run tag, every count is a delta against a baseline captured in its own leg, and leg 6's commit
on the base branch is made only when the tag is not already on it.
"""

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
KEY = os.environ.get("AW_KEY", "")
if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the other trial Hub.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
DIR = os.environ.get("AW_DRIVE_DIR", "C:\\Users\\huida\\Documents\\aw-drive-row15")
DIR_NOGIT = DIR + "-nogit"
NAME = os.path.basename(DIR.rstrip("\\/"))
NAME_NOGIT = os.path.basename(DIR_NOGIT.rstrip("\\/"))
ALPHA, BETA = "alpha", "beta"
SHADOW = "conflicts"  # an agent named after the sibling route, which the router declares first
SELFREG = "readerbot"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
TARGET = "calc.py"
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))
UI_BUNDLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "hub", "hub", "static", "ui", "assets",
)
UI_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "hub", "ui", "src",
)

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(
        ("  ok   " if cond else "  FAIL ")
        + label
        + (f"  -- {detail}" if detail and not cond else "")
    )


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


# ---------------------------------------------------------------------------- fixture


def git(path, *args, check=False):
    r = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} in {path}: {r.stderr.strip()}")
    return r


def find_project(name):
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return next((p["id"] for p in rows if p.get("name") == name), None)


def project_count():
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return len(rows)


def ensure_repo(path):
    """A fixture directory that is a git repository WITH A COMMIT IN IT.

    Copied from `t_sweep_row14_accounting.py`, and not decoration: a project whose repository has
    no commits cannot run a turn — `git worktree add ... HEAD` fails with "invalid reference: HEAD"
    and `POST /agent/trigger` answers an honest 200 with `run_id: null`.

    The seeded `calc.py` is the substrate for the conflict legs: both agents are told to append to
    the same file, so their branches diverge on it.
    """
    os.makedirs(path, exist_ok=True)
    if git(path, "rev-parse", "--git-dir").returncode != 0:
        git(path, "init")
    if git(path, "rev-parse", "HEAD").returncode != 0:
        with open(os.path.join(path, TARGET), "w", encoding="utf-8") as fh:
            fh.write("def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n")
        with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("row 15 worktrees fixture\n")
        git(path, "add", TARGET, "README.md")
        git(path, "-c", "user.email=drive@local", "-c", "user.name=drive",
            "commit", "-m", "fixture: initial commit so a worktree can be added")
    head = git(path, "rev-parse", "--short", "HEAD")
    print(f"fixture repo {path} -> HEAD {head.stdout.strip() or head.stderr.strip()}")


def ensure_dir_only(path):
    """A project directory that is deliberately NOT a repository — leg 3's whole point."""
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("row 15 non-repository fixture\n")


def ensure_project(path, name, repo=True):
    found = find_project(name)
    if found:
        return found
    ensure_repo(path) if repo else ensure_dir_only(path)
    code, body = api("POST", "/projects/open", {"path": path, "name": name})
    if code >= 300:
        sys.exit(f"could not open project {name}: {code} {body}")
    return body["id"]


def ensure_runner(project):
    _, body = api("GET", f"/projects/{project}/runners")
    rows = body if isinstance(body, list) else (body or {}).get("runners") or []
    for r in rows:
        if r.get("name") == "Haiku (cheap)":
            return r["id"]
    code, body = api(
        "POST",
        f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    if code >= 300:
        sys.exit(f"could not create runner: {code} {body}")
    return body["id"]


def ensure_agent(project, name, runner):
    code, _ = api("POST", f"/projects/{project}/agents", {"name": name, "runner_id": runner})
    if code < 300:
        return name
    _, body = api("GET", f"/projects/{project}/agents")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    if any(a.get("name") == name for a in rows):
        return name
    sys.exit(f"could not create or find agent {name}: {body}")


def teardown():
    for name in (NAME, NAME_NOGIT):
        pid = find_project(name)
        if pid:
            code, _ = api("DELETE", f"/projects/{pid}")
            print(f"deleted {name} ({pid}) -> {code}")
    for path in (DIR, DIR_NOGIT):
        if os.path.isdir(path):
            # `ignore_errors=True` alone leaves `.git` behind on Windows: git marks loose objects
            # read-only and `os.remove` raises on them. Clear the bit and retry.
            def _force(func, target, _exc):
                os.chmod(target, stat.S_IWRITE)
                func(target)

            shutil.rmtree(path, onerror=_force)
            print(f"removed {path} -> exists={os.path.isdir(path)}")
    print(f"projects now: {project_count()}")


if "--teardown" in sys.argv:
    teardown()
    sys.exit(0)


P = ensure_project(DIR, NAME, repo=True)
P_NOGIT = ensure_project(DIR_NOGIT, NAME_NOGIT, repo=False)
RUNNER = ensure_runner(P)
RUNNER_NOGIT = ensure_runner(P_NOGIT)
for _name in (ALPHA, BETA, SHADOW):
    ensure_agent(P, _name, RUNNER)
ensure_agent(P_NOGIT, ALPHA, RUNNER_NOGIT)
A = f"/projects/{P}"
A_NOGIT = f"/projects/{P_NOGIT}"
print(f"fixture: {NAME}={P}  nogit={NAME_NOGIT}={P_NOGIT}  tag={TAG}")


# ---------------------------------------------------------------------------- helpers


def db_rows(sql, args=()):
    """Read the Hub's database read-only. Observation only; the Hub owns this file."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        cur = con.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        con.close()


def db_run(run_id):
    rows = db_rows("SELECT id, status, exit_code, error FROM runs WHERE id = ?", (run_id,))
    return rows[0] if rows else None


def worktrees_list(prefix=None):
    code, body = api("GET", f"{prefix or A}/worktrees")
    return code, body if isinstance(body, list) else []


def conflicts(prefix=None):
    code, body = api("GET", f"{prefix or A}/worktrees/conflicts")
    return code, body if isinstance(body, list) else body


def workspace(agent, prefix=None):
    code, body = api("GET", f"{prefix or A}/worktrees/{agent}")
    return code, body if isinstance(body, dict) else {}


def on_disk():
    """Every Hub-owned checkout directory that actually exists, straight off the filesystem."""
    found = set()
    for sub in ("worktrees", "tasks", "reviews"):
        root = os.path.join(DIR, ".agentweave", sub)
        if os.path.isdir(root):
            for entry in sorted(os.listdir(root)):
                found.add(f"{sub}/{entry}")
    return found


def branches():
    r = git(DIR, "branch", "--list", "--format=%(refname:short)")
    return [b.strip() for b in r.stdout.splitlines() if b.strip()]


def base_branch():
    _, body = api("GET", f"{A}/settings")
    return (body or {}).get("main_branch") or git(
        DIR, "rev-parse", "--abbrev-ref", "HEAD"
    ).stdout.strip()


def merge_tree_conflicts(a, b):
    """The same plumbing `_merge_tree_conflicts` runs, executed here so the endpoint's answer is
    checked against git rather than against itself."""
    r = git(DIR, "merge-tree", "--write-tree", "--name-only", a, b)
    if r.returncode == 0:
        return []
    paths = []
    for line in r.stdout.splitlines()[1:]:
        if not line.strip():
            break
        paths.append(line.strip())
    return paths


def create_task(agent, title, description):
    code, body = api(
        "POST",
        f"{A}/tasks",
        {"title": title, "description": description, "assignee": agent, "priority": "high"},
    )
    if code >= 300:
        sys.exit(f"could not create task for {agent}: {code} {body}")
    return body["id"]


def get_task(task_id):
    code, body = api("GET", f"{A}/tasks/{task_id}")
    return code, body if isinstance(body, dict) else {}


def trigger(agent, message, task_id=None, prefix=None):
    payload = {"agent": agent, "message": message}
    if task_id:
        payload["task_id"] = task_id
    code, body = api("POST", f"{prefix or A}/agent/trigger", payload, timeout=60)
    if code not in (200, 201, 202):
        return None, f"trigger {code} {str(body)[:200]}"
    run_id = (body or {}).get("run_id") or (body or {}).get("id")
    if not run_id:
        return None, f"no run started: {json.dumps(body)[:300]}"
    return run_id, "started"


def wait_runs(run_ids, wait=600):
    """Wait for every run to leave a live status. Returns {run_id: final status}."""
    deadline = time.time() + wait
    final = {}
    while time.time() < deadline and len(final) < len(run_ids):
        time.sleep(6)
        for rid in run_ids:
            if rid in final:
                continue
            row = db_run(rid)
            if row and row["status"] not in ("running", "queued", "starting"):
                final[rid] = row["status"]
    for rid in run_ids:
        final.setdefault(rid, "timeout")
    return final


def drive_to(task_id, target):
    """Walk a task to *target*, following the refusal's own list of available transitions.

    The transition machine refuses an illegal edge with a 409 that names what IS available, so
    this reads that rather than hard-coding a path the machine might not have.
    """
    seen = []
    for _ in range(6):
        code, body = get_task(task_id)
        status = body.get("status")
        seen.append(status)
        if status == target:
            return True, seen
        code, body = api("PATCH", f"{A}/tasks/{task_id}", {"status": target})
        if code < 300:
            continue
        detail = str((body or {}).get("detail") or body)
        nxt = None
        for candidate in ("in_progress", "completed", "under_review", "rejected", "assigned"):
            if candidate in detail and candidate != seen[-1]:
                nxt = candidate
                break
        if not nxt:
            return False, seen + [f"stuck: {detail[:160]}"]
        code, _ = api("PATCH", f"{A}/tasks/{task_id}", {"status": nxt})
        if code >= 300:
            return False, seen + [f"cannot reach {nxt}: {code}"]
    return False, seen


def sweep_board():
    """Leave every earlier run's task terminal before this run creates its own.

    Not tidiness. An agent holding two live tasks *chooses* between them — run 2 of this harness
    watched `beta`, bound to one task, read the other one's description off `list_tasks` and
    implement that instead — so a board left dirty by the previous run makes the next run's
    isolation assertions measure the wrong work.
    """
    _, rows = api("GET", f"{A}/tasks")
    rows = rows if isinstance(rows, list) else (rows or {}).get("tasks") or []
    stale = [
        t for t in rows
        if t.get("status") not in ("approved", "rejected")
        and t.get("assignee") in (ALPHA, BETA)
    ]
    for t in stale:
        reached, path = drive_to(t["id"], "rejected")
        note(f"swept {t['id']} ({t.get('status')})", f"{path} -> {reached}")
    return len(stale)


def bundle_text():
    if not os.path.isdir(UI_BUNDLE):
        return ""
    out = []
    for entry in os.listdir(UI_BUNDLE):
        if entry.endswith(".js"):
            with open(os.path.join(UI_BUNDLE, entry), encoding="utf-8", errors="replace") as fh:
                out.append(fh.read())
    return "\n".join(out)


def src_grep(needle, root=UI_SRC, skip_tests=True):
    hits = []
    for dirpath, _dirs, files in os.walk(root):
        if skip_tests and "__tests__" in dirpath:
            continue
        for name in files:
            if not name.endswith((".ts", ".tsx")):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if needle in line:
                        hits.append(f"{os.path.relpath(path, root)}:{i}")
    return hits


# ---------------------------------------------------------------------------- LEG 1

leg(1, "reading the worktree surface provisions nothing, and the report matches the disk")

before = on_disk()
code_list, listed = worktrees_list()
ok("GET /worktrees answers 200", code_list == 200, str(code_list))
code_conf, conf = conflicts()
ok("GET /worktrees/conflicts answers 200", code_conf == 200, str(code_conf))
code_ws, ws = workspace(ALPHA)
ok("GET /worktrees/{agent} answers 200", code_ws == 200, str(code_ws))
after = on_disk()
ok(
    "three reads of the worktree surface created nothing on disk",
    before == after,
    f"{sorted(before)} -> {sorted(after)}",
)

expected_path = os.path.join(DIR, ".agentweave", "worktrees", ALPHA)
ok(
    "an agent's reported working directory is the one this module's pure function predicts",
    os.path.normcase(ws.get("working_dir", "")) == os.path.normcase(expected_path),
    f"{ws.get('working_dir')!r} != {expected_path!r}",
)
ok(
    f"{ALPHA} is isolated on its own branch",
    ws.get("isolated") is True and ws.get("branch") == f"agentweave/{ALPHA}",
    json.dumps({k: ws.get(k) for k in ("isolated", "branch")}),
)
ok(
    "`provisioned` is the truth about the disk, not an assumption",
    ws.get("provisioned") is os.path.isdir(ws.get("working_dir") or "\0"),
    f"provisioned={ws.get('provisioned')} exists={os.path.isdir(ws.get('working_dir') or chr(0))}",
)
note("checkouts on disk", sorted(after) or "none")
note("listed by the Hub", [f"{w['kind']}/{w['name']}" for w in listed] or "none")


# ---------------------------------------------------------------------------- LEG 2

leg(2, "what the surface refuses, and the one name that eats a route")

code, body = workspace(f"ghost{TAG}")
ok(
    "an agent that does not exist is refused rather than given a workspace",
    code == 404,
    f"{code} {json.dumps(body)[:220]}",
)

code, body = api("GET", f"{A}/worktrees/user")
ok("the reserved name 'user' is refused", code == 400, str(code))

code, body = api("GET", f"{A}/worktrees/bad.name")
ok("a name that cannot be a path component is refused", code == 400, str(code))

code, body = api("GET", f"{A}/worktrees/{'x' * 40}")
ok("an over-long name is refused", code == 400, str(code))

code, body = api("GET", "/projects/proj-does-not-exist/worktrees")
ok("an unknown project is a 404", code == 404, str(code))

# The shadowing question. `conflicts` is a legal agent name and the router declares `/conflicts`
# before `/{agent}`, so this asks what an operator opening that agent's settings actually gets.
_, roster = api("GET", f"{A}/agents")
roster_names = [a.get("name") for a in (roster if isinstance(roster, list) else [])]
ok(f"an agent legally named {SHADOW!r} exists on the roster", SHADOW in roster_names,
   str(roster_names))
code, body = api("GET", f"{A}/worktrees/{SHADOW}")
is_workspace_doc = isinstance(body, dict) and body.get("agent") == SHADOW
ok(
    f"GET /worktrees/{SHADOW} answers about the agent, not the conflict list",
    is_workspace_doc,
    f"{code} returned {type(body).__name__} {json.dumps(body)[:200]}",
)


# ---------------------------------------------------------------------------- LEG 3

leg(3, "a project that is not a repository — what each endpoint is able to say about it")

code_n, listed_n = worktrees_list(A_NOGIT)
ok("the list answers 200 for a non-repository project", code_n == 200, str(code_n))
code_cn, conf_n = conflicts(A_NOGIT)
ok("conflicts answers 200 for a non-repository project", code_cn == 200, str(code_cn))
code_wn, ws_n = workspace(ALPHA, A_NOGIT)
ok(
    "the per-agent endpoint says why there is no checkout",
    bool(ws_n.get("unavailable_reason")) and ws_n.get("isolated") is False,
    json.dumps({k: ws_n.get(k) for k in ("isolated", "provisioned", "unavailable_reason")})[:300],
)
ok(
    "the list distinguishes 'not a repository' from 'no checkouts yet'",
    listed_n != [] or conf_n != [],
    f"list={listed_n!r} conflicts={conf_n!r} — both empty, the same answer a healthy empty repo gives",
)


# ---------------------------------------------------------------------------- LEG 4

leg(4, "two real turns, two tasks, one file — isolation")

note("stale tasks swept before this run", sweep_board())

fn_a, fn_b = f"mul_{TAG}", f"div_{TAG}"
tasks = {
    ALPHA: create_task(
        ALPHA,
        f"Add {fn_a} to {TARGET}",
        f"Edit {TARGET} in your working directory. Append a function `{fn_a}(a, b)` returning "
        f"`a * b` at the END of the file, in the same style as the existing add/sub. Change "
        f"nothing else. Do not run git. Reply with the final contents of {TARGET}.",
    ),
    BETA: create_task(
        BETA,
        f"Add {fn_b} to {TARGET}",
        f"Edit {TARGET} in your working directory. Append a function `{fn_b}(a, b)` returning "
        f"`a / b` at the END of the file, in the same style as the existing add/sub. Change "
        f"nothing else. Do not run git. Reply with the final contents of {TARGET}.",
    ),
}
note("tasks", tasks)

base = base_branch()
note("base branch", base)
base_target_before = git(DIR, "show", f"{base}:{TARGET}").stdout

runs = {}
for agent, tid in tasks.items():
    rid, state = trigger(agent, "Do the task you have been assigned. One small edit.", task_id=tid)
    note(f"trigger {agent}", f"{rid} {state}")
    if rid:
        runs[agent] = rid
ok("both task-bound turns started", len(runs) == 2, str(runs))
finals = wait_runs(list(runs.values()))
note("run outcomes", {a: finals.get(r) for a, r in runs.items()})

code_list, listed = worktrees_list()
task_ws = {w["name"]: w for w in listed if w["kind"] == "task"}
ok(
    "each task got a checkout of its own, listed under kind='task'",
    all(tid in task_ws for tid in tasks.values()),
    f"listed tasks {sorted(task_ws)} vs {sorted(tasks.values())}",
)
base_target_after = git(DIR, "show", f"{base}:{TARGET}").stdout
ok(
    f"neither turn touched {base}",
    base_target_after == base_target_before,
    f"{len(base_target_before)} -> {len(base_target_after)} chars",
)
landed = {}
for agent, tid in tasks.items():
    branch = f"agentweave/task/{tid}"
    landed[agent] = git(DIR, "show", f"{branch}:{TARGET}").stdout
ok(
    f"{ALPHA}'s work is on its own branch and only there",
    fn_a in landed.get(ALPHA, "") and fn_a not in landed.get(BETA, "")
    and fn_a not in base_target_after,
    f"alpha branch has {fn_a}: {fn_a in landed.get(ALPHA, '')}; "
    f"beta branch has it: {fn_a in landed.get(BETA, '')}",
)
ok(
    f"{BETA}'s work is on its own branch and only there",
    fn_b in landed.get(BETA, "") and fn_b not in landed.get(ALPHA, "")
    and fn_b not in base_target_after,
    f"beta branch has {fn_b}: {fn_b in landed.get(BETA, '')}; "
    f"alpha branch has it: {fn_b in landed.get(ALPHA, '')}",
)

code_ws, ws_a = workspace(ALPHA)
checkouts = {c["task_id"]: c for c in (ws_a.get("task_checkouts") or [])}
ok(
    f"{ALPHA}'s own endpoint lists the task it is holding, provisioned and not grandfathered",
    tasks[ALPHA] in checkouts
    and checkouts[tasks[ALPHA]].get("provisioned") is True
    and checkouts[tasks[ALPHA]].get("grandfathered") is False,
    json.dumps(list(checkouts.values()))[:300],
)


# ---------------------------------------------------------------------------- LEG 5

leg(5, "the conflict report — and whether anything in the product reads it")

code_conf, conf = conflicts()
pairs = [
    tuple(sorted(w["name"] for w in report["workspaces"])) for report in (conf or [])
]
want = tuple(sorted((tasks[ALPHA], tasks[BETA])))
ok(
    "the two diverging task checkouts are reported as a conflict",
    want in pairs,
    f"reported {pairs}",
)
report = next((r for r in (conf or []) if tuple(sorted(w["name"] for w in r["workspaces"])) == want), None)
ok(
    f"the report names {TARGET} as the conflicting path",
    bool(report) and TARGET in (report.get("paths") or []),
    json.dumps(report)[:300] if report else "no report",
)
ok(
    "the endpoint's answer agrees with git's own merge-tree",
    bool(report)
    and sorted(report.get("paths") or [])
    == sorted(
        merge_tree_conflicts(
            f"agentweave/task/{tasks[ALPHA]}", f"agentweave/task/{tasks[BETA]}"
        )
    ),
    "endpoint vs plumbing disagree",
)

# Who reads it. The route exists and is correct; the question is whether a conflict ever reaches
# an operator who is not running curl.
bundle = bundle_text()
ok("the served bundle was found and read", len(bundle) > 10_000, f"{len(bundle)} chars")
ok(
    "the worktree LIST route is in the served bundle",
    "worktrees" in bundle,
    "absent",
)
conflict_src = src_grep("worktrees/conflicts")
conflict_bundle = "worktrees/conflicts" in bundle
ok(
    "the conflict route has a call site in the shipped UI",
    bool(conflict_src) or conflict_bundle,
    f"source hits {conflict_src}; in bundle {conflict_bundle}",
)

# And whether the panel that DOES read the list is ever told to refresh.
sse_hits = src_grep("'worktrees'", root=os.path.join(UI_SRC, "hooks"))
ok(
    "some SSE event invalidates the worktrees query, so the panel updates when a checkout appears",
    bool(sse_hits),
    f"no invalidation of ['project', id, 'worktrees'] anywhere under hooks/: {sse_hits}",
)


# ---------------------------------------------------------------------------- LEG 6

leg(6, "what the conflict check is never compared against: the branch the work merges into")

marker = f"base_{TAG}"
if marker not in git(DIR, "show", f"{base}:{TARGET}").stdout:
    with open(os.path.join(DIR, TARGET), "a", encoding="utf-8") as fh:
        fh.write(f"\n\ndef {marker}(a, b):\n    return a % b\n")
    git(DIR, "add", TARGET)
    git(DIR, "-c", "user.email=drive@local", "-c", "user.name=drive",
        "commit", "-m", f"operator edit on {base} ({TAG})")
base_now = git(DIR, "show", f"{base}:{TARGET}").stdout
ok(f"{base} now carries an operator edit to {TARGET}", marker in base_now, base_now[-120:])

base_vs_alpha = merge_tree_conflicts(base, f"agentweave/task/{tasks[ALPHA]}")
base_vs_beta = merge_tree_conflicts(base, f"agentweave/task/{tasks[BETA]}")
note(f"git says {base} vs alpha's task branch conflicts on", base_vs_alpha)
note(f"git says {base} vs beta's task branch conflicts on", base_vs_beta)
ok(
    "the setup is real: git itself says both task branches now conflict with the base",
    bool(base_vs_alpha) and bool(base_vs_beta),
    f"{base_vs_alpha} / {base_vs_beta}",
)

_, conf = conflicts()
named = {w["name"] for r in (conf or []) for w in r["workspaces"]}
ok(
    "the conflict endpoint reports the divergence from the branch the work is merging into",
    base in named or any(w.get("kind") == "branch" for r in (conf or []) for w in r["workspaces"]),
    f"reported workspaces {sorted(named)} — the base branch {base!r} is not among them, "
    f"so a conflict git can already see is not reported",
)


# ---------------------------------------------------------------------------- LEG 7

leg(7, "a finished task releases its checkout — and takes its conflict off the report with it")

_, before_conf = conflicts()
before_pairs = [tuple(sorted(w["name"] for w in r["workspaces"])) for r in (before_conf or [])]
ok("the alpha/beta conflict is on the report before the release", want in before_pairs,
   str(before_pairs))

reached, path = drive_to(tasks[ALPHA], "rejected")
note("transition path", path)
ok(f"{ALPHA}'s task reached a terminal status", reached, str(path))

released_branch = f"agentweave/task/{tasks[ALPHA]}"
ok(
    "the released task's branch is kept",
    released_branch in branches(),
    f"branches {branches()}",
)
unmerged = git(DIR, "rev-list", f"{base}..{released_branch}").stdout.split()
ok(
    "the kept branch still has work that is not on the base",
    bool(unmerged),
    f"{len(unmerged)} commits",
)
_, listed_after = worktrees_list()
still_listed = [w["name"] for w in listed_after if w["kind"] == "task"]
ok(
    "the released checkout is gone from the list",
    tasks[ALPHA] not in still_listed,
    str(still_listed),
)

still_diverges = merge_tree_conflicts(released_branch, f"agentweave/task/{tasks[BETA]}")
_, after_conf = conflicts()
after_pairs = [tuple(sorted(w["name"] for w in r["workspaces"])) for r in (after_conf or [])]
note("git still says the two branches conflict on", still_diverges)
note("the endpoint now reports", after_pairs)
ok(
    "a conflict that git can still see is still reported after the checkout is released",
    (want in after_pairs) or not still_diverges,
    f"git says {still_diverges} conflict; endpoint reports {after_pairs}",
)

_, hist = api("GET", f"{A}/events/history?limit=60")
hist_rows = hist if isinstance(hist, list) else (hist or {}).get("events") or []
rel = [r for r in hist_rows if r.get("type") == "task_worktree_released"]
ok(
    "the release is recorded in the project's history",
    bool(rel),
    f"types seen: {sorted({r.get('type') for r in hist_rows})}",
)
if rel:
    note("newest release event", json.dumps(rel[0])[:400])


# ---------------------------------------------------------------------------- LEG 8

leg(8, "the isolation switch the UI declines to offer, and what the API does with it")

# `AgentSettingsPage.tsx:290` states in writing that isolation is a real stored setting
# (`config.read_only`) that nothing offers today, because flipping an agent with uncommitted work
# in its worktree to the shared checkout "would strand that work somewhere the agent no longer
# looks", and that this belongs in its own change with a decision about the existing worktree.
# The panel keeps that promise. This leg asks whether the operator API keeps it too, and what
# happens to a task-bound turn on the far side of the flip.
_, ws_before = workspace(BETA)
before_checkouts = [c["task_id"] for c in (ws_before.get("task_checkouts") or [])]
ok(
    f"{BETA} is isolated and holds a live task checkout before the flip",
    ws_before.get("isolated") is True and tasks[BETA] in before_checkouts,
    f"isolated={ws_before.get('isolated')} checkouts={before_checkouts}",
)

code, body = api("PATCH", f"{A}/agents/{BETA}", {"config": {"read_only": True}})
note("PATCH /agents with a read_only config", f"{code} {json.dumps(body)[:160]}")
_, ws_b = workspace(BETA)
ok(
    "the API refuses the flip the UI declines to offer, or protects the work it would strand",
    ws_b.get("isolated") is not False,
    f"PATCH answered {code} and {BETA} is now isolated={ws_b.get('isolated')}, "
    f"working_dir={ws_b.get('working_dir')!r}",
)
after_checkouts = [c["task_id"] for c in (ws_b.get("task_checkouts") or [])]
ok(
    f"{BETA}'s live task checkout is still on its own settings page after the flip",
    tasks[BETA] in after_checkouts,
    f"task_checkouts went {before_checkouts} -> {after_checkouts} while the directory is still "
    f"on disk: {'tasks/' + tasks[BETA] in on_disk()}",
)

# Can it be undone? Three shapes, because "clear the config" is the obvious operator move and
# `t_f219_runner_model_clear.py` already found this route's sibling answering 200 to a clear that
# changes nothing.
for attempt in ({"config": {}}, {"config": None}):
    code, body = api("PATCH", f"{A}/agents/{BETA}", attempt)
    _, probe = workspace(BETA)
    ok(
        f"PATCH {json.dumps(attempt)} either clears the config or refuses",
        probe.get("isolated") is True or code >= 300,
        f"answered {code} with config={(body or {}).get('config') if isinstance(body, dict) else body}"
        f" and isolated is still {probe.get('isolated')}",
    )

# The consequence, driven rather than argued: one real task-bound turn on the far side of a flip
# the operator can make and cannot undo by clearing.
shared_fn = f"shared_{TAG}"
root_before = open(os.path.join(DIR, TARGET), encoding="utf-8").read()
rid, state = trigger(
    BETA,
    f"Append a function `{shared_fn}(a, b)` returning `a + b` to the END of {TARGET} in your "
    f"working directory, in the same style as the existing functions. Change nothing else. "
    f"Do not run git.",
    task_id=tasks[BETA],
)
note(f"flipped {BETA}'s task-bound turn", f"{rid} {state}")
if rid:
    note("outcome", wait_runs([rid]).get(rid))
root_after = open(os.path.join(DIR, TARGET), encoding="utf-8").read()
dirty = git(DIR, "status", "--porcelain").stdout.strip()
_, listed_flipped = worktrees_list()
task_branch = f"agentweave/task/{tasks[BETA]}"
branch_tip_has = git(DIR, "show", f"{task_branch}:{TARGET}").stdout

ok(
    f"the task-bound turn did NOT write into the project checkout",
    shared_fn not in root_after,
    f"{TARGET} at the repo root now contains {shared_fn}; git status: {dirty!r}",
)
ok(
    "the turn's work is committed somewhere a later integration could merge",
    shared_fn in branch_tip_has,
    f"{task_branch} tip does not contain it; the only copy is the uncommitted one in the "
    f"project checkout",
)
ok(
    "the task still has a checkout listed after a turn on it",
    tasks[BETA] in [w["name"] for w in listed_flipped if w["kind"] == "task"],
    str([w["name"] for w in listed_flipped]),
)
note("repo root worktree state after the flipped turn", dirty or "clean")

code, body = api(
    "POST",
    f"{A}/agents/register",
    {"name": SELFREG, "contact_mode": "mcp-push", "config": {"read_only": True}},
)
note("POST /agents/register with read_only", f"{code} {json.dumps(body)[:120]}")
if code < 300:
    _, ws_r = workspace(SELFREG)
    ok(
        "a self-registered read_only agent shares the project checkout, as designed",
        ws_r.get("isolated") is False
        and os.path.normcase(ws_r.get("working_dir", "")) == os.path.normcase(DIR),
        json.dumps({k: ws_r.get(k) for k in ("isolated", "working_dir", "provisioned")}),
    )

_, roster_now = api("GET", f"{A}/agents")
roster_rows = roster_now if isinstance(roster_now, list) else []
ok(
    "the roster listing shows the setting that decides where an agent's turns run",
    any(r.get("name") == BETA and r.get("config") for r in roster_rows),
    "GET /agents carries no `config` at all, so an agent moved off isolation looks identical to "
    "every other one on the roster: "
    + json.dumps([{k: r.get(k) for k in ("name", "config")} for r in roster_rows]),
)


# ---------------------------------------------------------------------------- LEG 9

leg(9, "put the project back the way it was found")

code, body = api("PATCH", f"{A}/agents/{BETA}", {"config": {"read_only": False}})
_, ws_reset = workspace(BETA)
ok(
    f"{BETA} is isolated again — an explicit false is what the clear needed",
    ws_reset.get("isolated") is True,
    f"{code} isolated={ws_reset.get('isolated')}",
)
# The flipped turn's edit lives only in the project checkout; leave it as it was found so the next
# run's leg 6 does not commit this run's stray work onto the base branch. Run 2 of this harness did
# exactly that and spent an hour of the finding on it.
git(DIR, "checkout", "--", TARGET)
ok(
    "the project checkout is clean again",
    not [
        line for line in git(DIR, "status", "--porcelain").stdout.splitlines()
        if line.strip() and not line.strip().endswith(".agentweave/")
    ],
    git(DIR, "status", "--porcelain").stdout,
)

_, jobs = api("GET", f"{A}/jobs")
job_rows = jobs if isinstance(jobs, list) else (jobs or {}).get("jobs") or []
ok("no job was created, so none is left enabled", not any(j.get("enabled") for j in job_rows))
note("roster", [a.get("name") for a in (roster_rows or [])])
note("checkouts on disk at the end", sorted(on_disk()))
note("branches at the end", branches())


# ---------------------------------------------------------------------------- summary

print(f"\n{'=' * 70}\n{len(PASS)} passed / {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAILED: {f}")
