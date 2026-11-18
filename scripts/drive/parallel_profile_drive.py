"""Acceptance drive for `one-profile-runs-many-turns-at-once-on-different-tasks` (OPMR-1).

Drives one Haiku-bound profile through the six steps the change document's acceptance-drive task
names, as an operator does: REST only, no row inserts. Run state is read through the operator's
read-only dashboard query route; worktrees and branches are asked of git itself.

  1 switch    turn the project's "profiles run in parallel" switch on, and read it back on
  2 tasks     an approved document with two independent tasks, both for the one builder profile
  3 flow      one flow firing; both tasks' runs of that profile are running at the same time
              (FR-3 ac-two-tasks-at-once, FR-4 ac-flow-two-offers)
  4 chats     two new operator chats with the profile run together, each in its own worktree on
              `thread/<profile>/<thread>` created from the main branch; each turn's commit is on
              its own thread branch only; each chat's Changes view and the worktree listing show
              that branch; neither chat's file is in the other's tree
              (FR-8 ac-separate-trees, FR-9 ac-two-chats, FR-13 ac-thread-branch, FR-17)
  5 serial    a second message to a running chat waits, and starts only after the first turn
              ends; never two running runs of that chat (FR-6 ac-conversation-serial)
  6 stop      two running chats; stopping the OLDER one by its run stops only that run, and the
              other ends completed (FR-10 ac-stop-one). The older one deliberately: today's Stop
              stops the profile's newest run, so choosing the newest could pass by accident.

Exits 0 when every step holds, otherwise non-zero with `FAILED at step <n> (<name>)` naming the
first step that did not. A manual drive, not one of the project's checks.

Never :8000. A scratch Hub started from this checkout (`e2e.py hub-up <profile> <port>`) or the
trial Hub :8010, with a project of its own -- the drive creates documents, a flow and chats there:

  # once: a fixture project, a Haiku runner, the profile and a checker for its build
  AW_HUB=http://127.0.0.1:8171 py -3.11 -u scripts/drive/parallel_profile_drive.py setup
  # then, with the AW_PROJECT that printed
  AW_HUB=... AW_PROJECT=proj-... py -3.11 -u scripts/drive/parallel_profile_drive.py run

`run --keep-going` carries on past a failing step (spending Haiku turns) to show how each later
step fails on its own; the exit code still names the first failing step. `AW_SWITCH_FIELD`
overrides the switch's settings field name (`profiles_run_in_parallel`).
"""

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import aw  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
AGENT = os.environ.get("AW_AGENT") or "solo"
CHECKER = os.environ.get("AW_CHECKER") or "solo-check"
SWITCH = os.environ.get("AW_SWITCH_FIELD") or "profiles_run_in_parallel"
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
FIXTURE = pathlib.Path(
    os.environ.get("AW_FIXTURE") or pathlib.Path.home() / "Documents" / "aw-opmr-drive"
)
POSTURE = {"permission_mode": "workspace"}
#: How long each turn holds itself open, so two of them overlap long enough to be seen together.
HOLD_SECONDS = int(os.environ.get("AW_HOLD_SECONDS") or 75)

P = ""
ROOT = ""
MAIN = ""


class StepError(Exception):
    pass


# ---------------------------------------------------------------------------
# Plumbing


def ensure_hub_and_key():
    hub = aw.require_hub().rstrip("/")
    if hub.endswith(":8000"):
        raise SystemExit(":8000 is the operator's real instance. Never drive it.")
    if not aw.KEY:
        # A fresh profile hands its key out on loopback, as `e2e.py key()` reads it.
        with urllib.request.urlopen(hub + "/api/v1/setup/token", timeout=10) as r:
            aw.KEY = json.loads(r.read())["api_key"]


def api(method, path, body=None):
    if path.startswith("~"):
        path = f"/projects/{P}" + path[1:]
    return aw.api(method, path, body)


def must(label, method, path, body=None):
    code, out = api(method, path, body)
    print(f"  {label}: {code}")
    if code >= 300:
        raise StepError(f"{label} -> {code}: {json.dumps(out, default=str)[:600]}")
    return out


def head(text):
    print("\n" + "=" * 78 + "\n" + text + "\n" + "=" * 78, flush=True)


def ok(label, cond, detail=""):
    print(
        f"  [{'OK ' if cond else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""), flush=True
    )
    if not cond:
        raise StepError(f"{label}" + (f" -- {detail}" if detail else ""))


#: The document's criteria this drive checks, in the order the steps reach them, with the
#: requirement each serves. A criterion is *reached* when its own assertions run: a step's setup
#: failing first leaves the criteria after it unreached, and the summary says so.
CHECKS = [
    ("ac-two-tasks-at-once", "FR-3"),
    ("ac-flow-two-offers", "FR-4"),
    ("ac-two-chats", "FR-9"),
    ("ac-separate-trees", "FR-8"),
    ("ac-thread-branch", "FR-13"),
    ("ac-thread-visible", "FR-17"),
    ("ac-conversation-serial", "FR-6"),
    ("ac-stop-one", "FR-10"),
]


def criterion(state, key, fn):
    """Run one criterion's assertions; its first failing one is recorded, not raised, so the
    step's other criteria still run."""
    try:
        fn()
    except StepError as exc:
        state.setdefault("checks", {})[key] = (False, str(exc))
        print(f"  -> {key} failed")
    else:
        state.setdefault("checks", {})[key] = (True, "")
        print(f"  -> {key} held")


def raise_failed(state, keys):
    bad = [f"{k}: {state['checks'][k][1]}" for k in keys if not state["checks"].get(k, (1,))[0]]
    if bad:
        raise StepError("; ".join(bad))


def git(*args):
    r = subprocess.run(
        ["git", "-C", ROOT, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return r.returncode, (r.stdout or "").strip()


def query(sql):
    """Rows of a read-only query over this project's data, as dicts."""
    code, out = api("POST", "~/dashboards/query", {"sql": sql})
    if code >= 300 or not isinstance(out, dict):
        raise StepError(f"run query refused: {code} {out}")
    return [dict(zip(out["columns"], row, strict=True)) for row in out["rows"]]


def lit(value):
    return "'" + str(value).replace("'", "''") + "'"


def runs(where):
    return query(
        "select id, agent, task_id, conversation_id, status, snapshot_commit_sha, started_at, "
        f"ended_at from runs where agent = {lit(AGENT)} and ({where}) order by started_at"
    )


def settle(timeout=1200):
    """Wait until the profile has no running run and no queued input, so a step that follows a
    failed one (under --keep-going) measures only its own turns."""

    def idle():
        busy = runs("status = 'running'")
        queued = query(
            f"select id from inbound_queue_entries where agent = {lit(AGENT)} "
            "and state = 'queued'"
        )
        return not busy and not queued

    if not idle():
        print("  waiting for the profile's leftover turns to finish")
        wait_until("profile idle", idle, timeout, gap=5)


def ids_sql(ids):
    return "(" + ", ".join(lit(i) for i in ids) + ")" if ids else "('')"


def wait_until(label, probe, timeout, gap=2):
    """Poll *probe* until it answers truthy; returns its answer, or None after *timeout*."""
    end = time.time() + timeout
    while time.time() < end:
        got = probe()
        if got:
            return got
        time.sleep(gap)
    print(f"      ({label}: not within {timeout}s)")
    return None


def wait_ended(ids, timeout=900):
    if not ids:
        return []

    def probe():
        rows = runs(f"id in {ids_sql(ids)}")
        return rows if rows and all(r["status"] != "running" for r in rows) else None

    return wait_until("runs ended", probe, timeout, gap=5) or runs(f"id in {ids_sql(ids)}")


def trigger(message, conversation_id=None, task_id=None):
    body = {"agent": AGENT, "message": message, "overrides": POSTURE}
    if conversation_id:
        body["conversation_id"] = conversation_id
    if task_id:
        body["task_id"] = task_id
    code, out = api("POST", "~/agent/trigger", body)
    brief = (
        {k: out.get(k) for k in ("status", "run_id", "conversation_id", "waiting_reason", "detail")}
        if isinstance(out, dict)
        else out
    )
    print(
        f"  trigger {AGENT}{' in ' + conversation_id if conversation_id else ' (new chat)'}: "
        f"{code} {json.dumps(brief, default=str)[:400]}"
    )
    if code >= 300:
        raise StepError(f"trigger refused: {code} {out}")
    return out


def held_turn(filename, line):
    return (
        f"Create a file named `{filename}` in your current working directory containing exactly "
        f"the line `{line}`. Then run the shell command "
        f'`py -3.11 -c "import time; time.sleep({HOLD_SECONDS})"` and wait for it to finish. '
        "Do not run git and change nothing else. Reply with the single word done."
    )


def worktrees():
    """`git worktree list --porcelain`, as [{path, branch, head}], branch None when detached."""
    _, out = git("worktree", "list", "--porcelain")
    rows, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line.strip():
            if cur:
                rows.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur = {"path": line[9:], "branch": None, "head": None}
        elif line.startswith("HEAD "):
            cur["head"] = line[5:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].removeprefix("refs/heads/")
    return rows


def holding(filename):
    return [w for w in worktrees() if (pathlib.Path(w["path"]) / filename).is_file()]


# ---------------------------------------------------------------------------
# Setup


def cmd_setup():
    global P
    ensure_hub_and_key()
    FIXTURE.mkdir(parents=True, exist_ok=True)
    if not (FIXTURE / ".git").is_dir():
        (FIXTURE / "README.md").write_text("# parallel-profile drive fixture\n", encoding="utf-8")
        for args in (
            ["init", "-q", "-b", "master"],
            ["add", "README.md"],
            [
                "-c",
                "user.name=drive",
                "-c",
                "user.email=drive@localhost",
                "commit",
                "-q",
                "-m",
                "init",
            ],
        ):
            subprocess.run(["git", "-C", str(FIXTURE), *args], check=True)
    P = must("open project", "POST", "/projects/open", {"path": str(FIXTURE)})["id"]
    must("main branch", "PUT", "~/settings", {"main_branch": "master"})
    _, runners = api("GET", "~/runners")
    runner = next(
        (r for r in runners or [] if r.get("cli") == "claude" and r.get("model") == HAIKU), None
    ) or must(
        "haiku runner",
        "POST",
        "~/runners",
        {"name": "haiku (drive)", "cli": "claude", "model": HAIKU},
    )
    for name in (AGENT, CHECKER):
        code, out = api("POST", "~/agents", {"name": name, "runner_id": runner["id"]})
        print(f"  agent {name}: {code}")
        if code == 409:
            must(f"rebind {name}", "PATCH", f"~/agents/{name}", {"runner_id": runner["id"]})
        elif code >= 300:
            raise SystemExit(f"agent {name}: {code} {out}")
        must(
            f"{name} posture", "PATCH", f"~/agents/{name}", {"default_permission_mode": "workspace"}
        )
    print(f"\nAW_PROJECT={P}\nfixture {FIXTURE}")


# ---------------------------------------------------------------------------
# The steps


def preflight():
    global ROOT, MAIN
    head("PRE. Preconditions")
    if not P:
        raise SystemExit("set AW_PROJECT (run `setup` first)")
    project = must("project", "GET", "~")
    ROOT = project.get("working_directory") or project.get("path") or ""
    settings = must("settings", "GET", "~/settings")
    MAIN = settings.get("main_branch") or ""
    if not MAIN or git("rev-parse", "--verify", MAIN)[0] != 0:
        raise SystemExit(f"project {P} has no main branch git knows ({MAIN!r})")
    # Spec documents are written in the project directory itself, so step 2's own document shows
    # up as untracked `spec/` on every later run; anything else is somebody's work.
    dirty = [
        ln for ln in git("status", "--porcelain")[1].splitlines() if not ln.startswith("?? spec/")
    ]
    if dirty:
        raise SystemExit(f"{ROOT} has uncommitted changes: {dirty}")
    _, roster = api("GET", "~/agents")
    me = next((a for a in roster or [] if a.get("name") == AGENT), None)
    if not me or not me.get("runner_id"):
        raise SystemExit(f"profile {AGENT!r} must exist and be bound (run `setup`)")
    settle()
    print(f"  root {ROOT}, main {MAIN}, profile {AGENT} (checker {CHECKER}), run tag {RUN}")
    return settings


def step_switch(state):
    before = must("read settings", "GET", "~/settings")
    state["switch_before"] = before.get(SWITCH)
    code, out = api("PUT", "~/settings", {SWITCH: True})
    print(f"  turn {SWITCH} on: {code} {json.dumps(out, default=str)[:300] if code >= 300 else ''}")
    after = must("read settings back", "GET", "~/settings")
    ok(
        f"the projects API reports {SWITCH} on",
        after.get(SWITCH) is True,
        f"PUT answered {code}; read back {SWITCH}={after.get(SWITCH, '<absent>')!r}",
    )
    state["switched"] = True


def document_payload():
    tasks = []
    for word in ("left", "right"):
        tasks.append(
            {
                "key": f"write-{word}",
                "title": f"Write {word}_{RUN}.txt",
                "description": held_turn(f"{word}_{RUN}.txt", word).replace(
                    "Reply with the single word done.",
                    "Then move your task to completed with the AgentWeave update_task tool.",
                ),
                "requirements": [word],
                "builder": AGENT,
                "checker": CHECKER,
                "files": [f"{word}_{RUN}.txt"],
                "depends_on": [],
            }
        )
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": f"Parallel drive {RUN}: two independent files",
        "summary": "Two independent one-file tasks for one builder, so a flow has two to start.",
        "problem": "The drive needs two ready tasks for one profile.",
        "scope": {"in_scope": ["two text files"], "non_goals": ["anything else"]},
        "requirements": [
            {
                "key": w,
                "modal": "MUST",
                "statement": f"The project MUST hold {w}_{RUN}.txt.",
                "rationale": "Drive fixture.",
            }
            for w in ("left", "right")
        ],
        "acceptance_criteria": [
            {
                "key": f"{w}-exists",
                "requirement": w,
                "given": "the change built",
                "when": f"{w}_{RUN}.txt is read",
                "then": f"it holds the line {w}",
            }
            for w in ("left", "right")
        ],
        "tasks": tasks,
        "design": "Two files, independent.",
        "lifecycle": "One-off drive fixture.",
        "delivery": {
            "mode": "flow",
            "agent": AGENT,
            "builder": AGENT,
            "checker": CHECKER,
            "cron": "0 4 1 1 *",
            "stop_when_queue_empties": True,
            "reasons": {"mode": "drive"},
        },
    }


def step_tasks(state):
    doc = must("create document", "POST", "~/project/documents", {"title": f"Parallel drive {RUN}"})
    q = urllib.parse.quote(doc["path"], safe="")
    state["doc_path"] = doc["path"]
    must(
        "write content", "PUT", f"~/project/documents/{q}/content", {"document": document_payload()}
    )
    api("POST", f"~/project/documents/close-exploration?path={q}", {"reason": "drive"})
    api("POST", f"~/project/documents/propose?path={q}", {"reason": "drive"})
    read = must("read it back", "GET", f"~/project/spec?path={q}")
    built = must(
        "approve and build (flow, one builder)",
        "POST",
        f"~/project/documents/approve-and-build?path={q}",
        {
            "reason": "drive",
            "approve_anyway": True,
            "driver": "flow",
            "content_version": read.get("content_version"),
            "delivery_agent": AGENT,
            "builders": [AGENT],
            "builder": AGENT,
            "checker": CHECKER,
            "landing": "nowhere",
        },
    )
    print("      build_outcome: " + json.dumps(built.get("build_outcome"), default=str)[:700])
    _, board = api("GET", "~/tasks?limit=1000")
    mine = [t for t in aw.task_rows(board) if f"_{RUN}.txt" in (t.get("title") or "")]
    state["tasks"] = [t["id"] for t in mine]
    ok(
        "approval laid out two tasks",
        len(mine) == 2,
        str([(t.get("readable_id"), t.get("status"), t.get("assignee")) for t in mine]),
    )
    ok(
        "both are for the one builder profile",
        all((t.get("builder") or t.get("assignee")) == AGENT for t in mine),
        str([(t.get("readable_id"), t.get("builder"), t.get("assignee")) for t in mine]),
    )
    _, jobs = api("GET", "~/jobs")
    flow = next(
        (
            j
            for j in jobs or []
            if (j.get("loop") or {}).get("spec_document_id") == doc.get("id")
            or j.get("spec_document_id") == doc.get("id")
        ),
        None,
    )
    state["job_id"] = flow.get("id") if flow else None
    ok("the build created its flow", bool(flow), f"jobs: {[j.get('id') for j in jobs or []]}")


def step_flow(state):
    t1, t2 = state["tasks"]
    started = runs(f"task_id in {ids_sql([t1, t2])}")
    if not started:
        must("fire the flow once", "POST", f"~/jobs/{state['job_id']}/run", {})

    def both_running():
        rows = runs(f"task_id in {ids_sql([t1, t2])} and status = 'running'")
        return rows if {r["task_id"] for r in rows} == {t1, t2} else None

    seen = wait_until("both task runs running", both_running, timeout=240)
    rows = runs(f"task_id in {ids_sql([t1, t2])}")
    state["flow_runs"] = [r["id"] for r in rows]

    def two_at_once():
        ok(
            "two runs of the one profile are running at once, one per task",
            bool(seen),
            "runs: " + str([(r["task_id"], r["status"]) for r in rows]),
        )

    def two_offers():
        ok(
            "one flow firing started both of the builder's tasks",
            {r["task_id"] for r in rows} == {t1, t2} and bool(seen),
            "runs: " + str([(r["task_id"], r["status"]) for r in rows]),
        )

    criterion(state, "ac-two-tasks-at-once", two_at_once)
    criterion(state, "ac-flow-two-offers", two_offers)
    raise_failed(state, ("ac-two-tasks-at-once", "ac-flow-two-offers"))


def step_chats(state):
    code, master_head = git("rev-parse", MAIN)
    names = {k: f"chat{k}_{RUN}.txt" for k in ("A", "B")}
    out_a = trigger(held_turn(names["A"], "chat A"))
    out_b = trigger(held_turn(names["B"], "chat B"))
    state["chat_A"], state["chat_B"] = out_a["conversation_id"], out_b["conversation_id"]
    ok("two new chats are two conversations", state["chat_A"] != state["chat_B"])

    def two_chats():
        ok(
            "chat B starts at once while chat A runs (not queued)",
            out_b.get("status") == "running" and out_b.get("run_id"),
            f"status={out_b.get('status')!r} waiting_reason={out_b.get('waiting_reason')!r}",
        )
        ids = [out_a["run_id"], out_b["run_id"]]

        def both_running():
            rows = runs(f"id in {ids_sql(ids)} and status = 'running'")
            return rows if len(rows) == 2 else None

        ok(
            "both chats' runs are running together",
            bool(wait_until("both chats running", both_running, 60)),
        )

    criterion(state, "ac-two-chats", two_chats)

    # Whether chat B ran at once or waited its turn, both chats have a writing turn before the
    # worktree, branch and Changes checks below read what those turns left -- so those checks
    # reach their own assertions even where chat B was queued.
    def chat_run(conv):
        rows = runs(f"conversation_id = {lit(conv)}")
        return rows[0]["id"] if rows else None

    ids = [
        wait_until(f"a run of {conv}", lambda c=conv: chat_run(c), HOLD_SECONDS * 4 + 300)
        for conv in (state["chat_A"], state["chat_B"])
    ]
    ok("both chats got a run", all(ids), str(ids))
    ended = wait_ended(ids)
    ok(
        "both chat turns completed",
        all(r["status"] == "completed" for r in ended),
        str([(r["conversation_id"], r["status"]) for r in ended]),
    )
    seen_trees = {}
    for key in ("A", "B"):
        trees = holding(names[key])
        ok(
            f"chat {key}'s file is in a worktree",
            bool(trees),
            str([(w["path"], w["branch"]) for w in trees]),
        )
        seen_trees[key] = trees

    def separate_trees():
        for key in ("A", "B"):
            ok(
                f"chat {key}'s file is in exactly one worktree",
                len(seen_trees[key]) == 1,
                str([(w["path"], w["branch"]) for w in seen_trees[key]]),
            )
        a, b = seen_trees["A"][0], seen_trees["B"][0]
        ok(
            "the two chats worked in different worktrees on different branches",
            a["path"] != b["path"] and a["branch"] != b["branch"],
            f"A {a['path']} on {a['branch']}; B {b['path']} on {b['branch']}",
        )
        for key, other in (("A", "B"), ("B", "A")):
            tree = seen_trees[other][0]["path"]
            ok(
                f"chat {key}'s file is not visible in chat {other}'s tree",
                not (pathlib.Path(tree) / names[key]).exists(),
                tree,
            )

    criterion(state, "ac-separate-trees", separate_trees)

    def thread_branch():
        for key, conv in (("A", state["chat_A"]), ("B", state["chat_B"])):
            tree = seen_trees[key][0]
            branch = tree["branch"] or ""
            ok(
                f"chat {key}'s worktree is on a thread branch of {AGENT}",
                branch.startswith(f"thread/{AGENT}/"),
                f"{tree['path']} on {branch or 'no branch'}",
            )
            ok(
                f"chat {key}'s worktree is not the project's own checkout",
                pathlib.Path(tree["path"]).resolve() != pathlib.Path(ROOT).resolve(),
                tree["path"],
            )
            _, first = git("rev-list", "--reverse", f"{MAIN}..{branch}")
            first = first.splitlines()[0] if first else ""
            _, parent = git("rev-parse", f"{first}^") if first else (1, "")
            ok(
                f"{branch} was created from {MAIN}'s head",
                first and parent == master_head,
                f"first commit {first[:12]} parent {parent[:12]}, {MAIN} was {master_head[:12]}",
            )
            run = next(r for r in ended if r["conversation_id"] == conv)
            sha = run.get("snapshot_commit_sha") or ""
            _, holders = (
                git("branch", "--contains", sha, "--format=%(refname:short)") if sha else (1, "")
            )
            ok(
                f"chat {key}'s end-of-turn commit is on {branch} only",
                sha and holders.split() == [branch],
                f"{sha[:12]} on {holders.split()}",
            )

    criterion(state, "ac-thread-branch", thread_branch)

    def thread_visible():
        for key, conv in (("A", state["chat_A"]), ("B", state["chat_B"])):
            branch = seen_trees[key][0]["branch"]
            changes = must(f"chat {key}'s Changes view", "GET", f"~/conversations/{conv}/changes")
            turn_files = [f.get("path") for f in changes.get("turn") or []]
            ok(
                f"chat {key}'s Changes view shows a thread branch of {AGENT} and its own file",
                (changes.get("branch") or "").startswith(f"thread/{AGENT}/")
                and changes.get("branch") == branch
                and names[key] in turn_files,
                f"branch={changes.get('branch')!r} worktree branch={branch!r} turn={turn_files}",
            )
        listing = must("worktree listing", "GET", "~/worktrees")
        branches = {w.get("branch") for w in listing.get("worktrees") or []}
        ok(
            "the worktree listing includes two thread worktrees of the profile",
            len({b for b in branches if b and b.startswith(f"thread/{AGENT}/")}) >= 2,
            str(sorted(b for b in branches if b)),
        )

    criterion(state, "ac-thread-visible", thread_visible)
    raise_failed(
        state, ("ac-two-chats", "ac-separate-trees", "ac-thread-branch", "ac-thread-visible")
    )


def step_serial(state):
    conv = state.get("chat_A")
    if not conv:
        # Step 4 did not leave a chat (it failed before opening one): open one here.
        opened = trigger("Reply with the single word ready.")
        conv = opened["conversation_id"]
        wait_ended([opened["run_id"]] if opened.get("run_id") else [])
    first = trigger(held_turn(f"serial1_{RUN}.txt", "first"), conversation_id=conv)
    ok(
        "the first turn of the chat started",
        first.get("status") == "running",
        str(first.get("status")),
    )

    def serial():
        second = trigger(held_turn(f"serial2_{RUN}.txt", "second"), conversation_id=conv)
        ok(
            "a second message to the running chat waits",
            second.get("status") == "queued",
            f"status={second.get('status')!r} run_id={second.get('run_id')!r}",
        )
        peak, first_end, second_start = 0, None, None
        end = time.time() + 900
        while time.time() < end:
            rows = runs(
                f"conversation_id = {lit(conv)} and id != {lit(first['run_id'])} "
                f"and started_at >= (select started_at from runs where id = "
                f"{lit(first['run_id'])})"
            )
            mine = runs(f"id = {lit(first['run_id'])}") + rows
            peak = max(peak, sum(1 for r in mine if r["status"] == "running"))
            if mine[0]["status"] != "running" and first_end is None:
                first_end = mine[0]["ended_at"]
            if rows and second_start is None:
                second_start = rows[0]["started_at"]
            if rows and all(r["status"] != "running" for r in mine):
                break
            time.sleep(3)
        ok("never two running runs of that chat", peak <= 1, f"peak={peak}")
        ok(
            "the second turn started only after the first ended",
            bool(second_start and first_end and str(second_start) >= str(first_end)),
            f"first ended {first_end}, second started {second_start}",
        )

    criterion(state, "ac-conversation-serial", serial)
    raise_failed(state, ("ac-conversation-serial",))


def step_stop(state):
    def stop_one():
        older = trigger(held_turn(f"stopC_{RUN}.txt", "chat C"))
        newer = trigger(held_turn(f"stopD_{RUN}.txt", "chat D"))
        ids = [older.get("run_id"), newer.get("run_id")]
        ok(
            "two chats are running",
            all(ids) and newer.get("status") == "running",
            f"older={older.get('status')!r} newer={newer.get('status')!r} "
            f"waiting_reason={newer.get('waiting_reason')!r}",
        )
        wait_until(
            "both running",
            lambda: len(runs(f"id in {ids_sql(ids)} and status = 'running'")) == 2,
            60,
        )
        time.sleep(10)
        code, out = api(
            "POST",
            f"~/agent/{AGENT}/stop?run_id={ids[0]}&conversation_id=" f"{older['conversation_id']}",
            {"run_id": ids[0], "conversation_id": older["conversation_id"]},
        )
        print(f"  stop the older run {ids[0]}: {code} {json.dumps(out, default=str)[:300]}")
        ended = {r["id"]: r["status"] for r in wait_ended(ids)}
        ok(
            "the chosen run ended stopped",
            ended.get(ids[0]) == "stopped",
            f"{ids[0]}: {ended.get(ids[0])}",
        )
        ok(
            "the other run ended completed",
            ended.get(ids[1]) == "completed",
            f"{ids[1]}: {ended.get(ids[1])}",
        )

    criterion(state, "ac-stop-one", stop_one)
    raise_failed(state, ("ac-stop-one",))


STEPS = [
    (1, "switch", step_switch),
    (2, "tasks", step_tasks),
    (3, "flow", step_flow),
    (4, "chats", step_chats),
    (5, "serial", step_serial),
    (6, "stop", step_stop),
]


def cmd_run(keep_going):
    ensure_hub_and_key()
    preflight()
    state, failures = {}, []
    try:
        for number, name, fn in STEPS:
            head(f"STEP {number}. {name}")
            if number == 3 and not state.get("tasks"):
                print("  skipped: step 2 laid out no tasks")
                failures.append((number, name, "skipped: step 2 laid out no tasks"))
                continue
            settle()
            try:
                fn(state)
            except StepError as exc:
                failures.append((number, name, str(exc)))
                print(f"  ** step {number} ({name}) failed: {exc}")
                if not keep_going:
                    break
    finally:
        head("CLEANUP")
        if state.get("job_id"):
            api("PATCH", f"~/jobs/{state['job_id']}", {"enabled": False})
            code, _ = api("POST", f"~/jobs/{state['job_id']}/archive", {})
            print(f"  flow {state['job_id']} disabled and archived: {code}")
        if state.get("switched"):
            code, _ = api("PUT", "~/settings", {SWITCH: bool(state.get("switch_before"))})
            print(f"  {SWITCH} restored to {bool(state.get('switch_before'))}: {code}")
    head("RESULT")
    checks = state.get("checks", {})
    for key, req in CHECKS:
        if key in checks:
            held, why = checks[key]
            print(
                f"  check {key}: reached=yes failed_at_assertion={'no' if held else 'yes'} "
                f"-- {req}: " + ("held" if held else why)
            )
        else:
            print(f"  check {key}: reached=no failed_at_assertion=no -- {req}: not reached")
    if not failures:
        print("  every step held")
        return 0
    for number, name, why in failures:
        print(f"  step {number} ({name}): {why}")
    number, name, _ = failures[0]
    print(f"\nFAILED at step {number} ({name})")
    return number


def main(argv):
    global P
    P = aw.P
    if not argv or argv[0] not in ("setup", "run"):
        print(__doc__)
        return 2
    if argv[0] == "setup":
        cmd_setup()
        return 0
    return cmd_run("--keep-going" in argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
