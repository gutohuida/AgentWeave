"""Acceptance drive for `a-build-lands-as-one-pull-request`, 2026-11-06.

The change's `drive` task (spdoc-79cf34c56bbe), written before the build of the rest: it fails on
master because the landing 'pull request' does not exist (the Build route accepts only `main` and
`nowhere`; hub/hub/api/v1/spec.py). It drives a Hub it starts itself on AW_DRIVE_PORT (default
8010, the trial profile's database; never :8000) against a clone of THIS repository's GitHub
remote, with the user's own `gh` login. The Hub is started with a `gh.exe` shim (scripts/drive/gh_shim.cs,
compiled with the .NET csc; checked to log a bare `gh` call) first on its PATH that
appends every call to `gh-calls.jsonl` and then runs the real `gh`, so the call list is the Hub's
own and nothing else's.

The operator records and (automatically) accepts evidence for each task's requirement at its
commit before approving it: in a flow, accepted evidence decides what approval pushes.

Two builds, each of two tasks that change only `testbed/README.md` (one appended line each), on
the project with PR landing turned on and the Build request naming landing `pull_request`:

  A. build 1: first task approved -> a DRAFT PR against master from the build branch (draft-ac1);
     second task approved -> its commit is on the same PR; the PR reads ready; the second task is
     sent back -> draft; approved again -> ready (ready-ac1); the PR's title is the spec's title
     and its body names the spec path, every requirement id, the accepted evidence ids and each
     task with its state (desc-ac1); the build card and a task show the link, 'draft' and the
     last-asked time (sh-ac1).
  B. build 2: its PR is closed without merging (`gh pr close`); the operator opens the build ->
     its tasks read not landed and the build branch is still on GitHub and locally (mc-ac1).
  Then the HUMAN STEP (below). After it, build 1's tasks read landed naming GitHub's merge commit
  (mc-ac2) and the local main equals GitHub's main (lm-ac1).
  Throughout: no recorded `gh` call is a merge, a review approval, a base change or a
  branch-protection change (nm-ac1). lm-ac2 (checked-out main with an uncommitted change) and the
  refused-push card (second half of sh-ac1) are hub tests, not drive steps: they would need the
  operator's own checkout dirtied or GitHub made to refuse a push.

HUMAN STEP -- guide
  The drive prints "HUMAN STEP", the URL of PR 1 and waits for Enter.
    1. Open the URL. It should be READY (not draft), base master, changing only testbed/README.md.
    2. Merge it on GitHub ("Squash and merge" or "Merge pull request"; either is fine).
    3. In AgentWeave, open the build and press 'check now' (the drive also presses it for you
       afterwards by calling the same route, so pressing it yourself is optional).
    4. Come back to the terminal and press Enter. The drive then checks mc-ac2 and lm-ac1.
  Delete the two remote branches afterwards if you want them gone (`gh pr list --state all`).
  Set AW_DRIVE_NO_HUMAN=1 to stop after the automated steps, leaving the PR unmerged.

Routes the drive assumes for what the build adds (the build's tasks create them; adjust here if
they land under other names): project setting `pr_landing` (PUT /projects/{id}/settings), build
landing `pull_request` (POST /project/documents/build), build read GET /project/builds/{id}
(`pull_request: {url, number, state, last_asked_at, error}`, tasks each with `pull_request` and
`landed`), and POST /project/builds/{id}/check-now.

    py -3.11 scripts/drive/pr_landing_drive.py
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get("AW_DRIVE_PORT") or 8010)
HUB = f"http://127.0.0.1:{PORT}"
PROFILE = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial"
DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or PROFILE / "agentweave.db")
KEY = (PROFILE / "bootstrap-key.txt").read_text(encoding="utf-8").strip()
STAMP = time.strftime("%H%M%S")
TMP = pathlib.Path(tempfile.gettempdir()) / "drive-pr-landing" / STAMP
# The agents are bound to a model that does not exist: Build starts the flow at once, and a real
# turn would race the drive's hand-made commit in the same worktree. A turn on this model fails
# before it touches anything, so the operator's hand (Build.work) is the only builder.
HAIKU = "drive-no-such-model"
BUILDER, CHECKER = "Builder", "Checker"
README = "testbed/README.md"
results = []
calls_log = TMP / "gh-calls.jsonl"


class Stop(Exception):
    pass


def check(name, ok, detail="", fatal=False):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


def api(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:4000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except urllib.error.URLError as exc:
        return 0, str(exc)


def run(cwd, *args, check_rc=True):
    out = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check_rc and out.returncode:
        raise RuntimeError(f"{' '.join(args)} -> {out.returncode}: {out.stderr.strip()}")
    return out.stdout.strip()


def gh_json(cwd, *args):
    return json.loads(run(cwd, "gh", *args))


def poll(fn, secs=30.0, every=1.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            value = fn()
            if value:
                return value
        except Exception:  # noqa: BLE001 -- not there yet
            pass
        time.sleep(every)
    return None


def build_shim(shim, real):
    """A real gh.exe (CreateProcess finds only .exe, and cmd.exe's %* garbles quotes and
    newlines in a PR body) that logs each call to gh-calls.jsonl and then runs the real gh."""
    csc = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if not csc.exists():
        sys.exit(f"{csc} is missing; the drive builds its gh shim with it")
    out = subprocess.run([str(csc), "/nologo", f"/out:{shim / 'gh.exe'}",
                          str(pathlib.Path(__file__).with_name("gh_shim.cs"))],
                         capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"building the gh shim failed: {out.stdout} {out.stderr}")


def start_hub():
    if api("GET", "/projects")[0] == 200:
        sys.exit(f"a Hub already answers on :{PORT}; the drive needs its own, started with the "
                 "gh shim on PATH. Stop it or set AW_DRIVE_PORT.")
    TMP.mkdir(parents=True, exist_ok=True)
    real = shutil.which("gh")
    if not real:
        sys.exit("the GitHub CLI (gh) is not installed or not on PATH")
    shim = TMP / "shim"
    shim.mkdir()
    build_shim(shim, real)
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["GH_SHIM_LOG"], env["GH_SHIM_REAL"] = str(calls_log), real
    env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    # Windows resolves a bare exe name on the parent's PATH, not on the env handed to the child, so
    # the probe names the file the Hub's PATH finds first: the shim.
    probe = subprocess.run([shutil.which("gh", path=env["PATH"]) or "gh", "--version"],
                           capture_output=True, text=True, env=env)
    if probe.returncode or not calls_log.exists() or "--version" not in calls_log.read_text(
            encoding="utf-8"):
        proc.kill()
        sys.exit("the gh shim does not log a plain subprocess.run(['gh', ...]); the drive cannot "
                 "audit the Hub's calls")
    calls_log.unlink()
    if not poll(lambda: api("GET", "/projects")[0] == 200, 120, 2):
        proc.kill()
        sys.exit(f"the Hub did not come up; see {TMP / 'hub.log'}")
    return proc


def payload(title):
    def task(key, req, line):
        return {"key": key, "title": f"Append {line}", "requirements": [req], "files": [README],
                "description": f"Append the line `{line}` to {README}. Change nothing else.",
                "builder": BUILDER, "reviewer": CHECKER}
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": "Two one-line changes to the testbed README.",
        "problem": "Drive the PR landing.",
        "scope": {"in_scope": [README], "non_goals": ["Anything else"]},
        "requirements": [{"key": k, "modal": "MUST",
                          "statement": f"The testbed README MUST carry the line {k}."}
                         for k in ("one", "two")],
        "acceptance_criteria": [{"key": f"has-{k}", "requirement": k, "given": "the README",
                                 "when": "it is read", "then": f"it has {k}",
                                 "how_to_check": f"grep {k} {README}", "checked_by": "agent"}
                                for k in ("one", "two")],
        "tasks": [task("t1", "one", f"drive-{STAMP}-one"),
                  task("t2", "two", f"drive-{STAMP}-two")],
        "delivery": {"mode": "flow", "agent": BUILDER, "builders": [BUILDER], "level": "reviewed",
                     "landing": "pull_request", "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "Two tasks.", "agent": "Default."}},
    }


class Build:
    """One document built with landing 'pull request', its two tasks and their worktrees."""

    def __init__(self, ctx, label):
        self.ctx, self.label = ctx, label
        self.title = f"PR landing drive {label} {STAMP}"
        self.doc = f"spec/changes/pr-drive-{label}-{STAMP}/spec.json"
        base, quoted = ctx["base"], urllib.parse.quote(self.doc)
        code, out = api("POST", f"{base}/project/documents",
                        {"title": self.title, "kind": "change-spec", "path": self.doc})
        check(f"{label}: document created", code == 201, f"{code} {out}", fatal=True)
        code, out = api("PUT", f"{base}/project/documents/{self.doc}/content",
                        {"document": payload(self.title)})
        check(f"{label}: document saves", code == 200, f"{code} {str(out)[:400]}", fatal=True)
        _, read = api("GET", f"{base}/project/spec?path={quoted}")
        version = read.get("content_version") if isinstance(read, dict) else None
        code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                        {"reason": "drive", "approve_anyway": True, "content_version": version})
        check(f"{label}: document approved", code == 200, f"{code} {str(out)[:400]}", fatal=True)
        code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                        {"driver": "flow", "level": "reviewed", "builders": [BUILDER],
                         "landing": "pull_request"})
        check(f"{label}: Build accepts landing 'pull request'", code == 200,
              f"{code} {str(out)[:600]}", fatal=True)
        self.build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
        _, tasks = api("GET", f"{base}/tasks?limit=200")
        rows = tasks["tasks"] if isinstance(tasks, dict) else tasks
        _, spec = api("GET", f"{base}/project/spec?path={quoted}")
        reqs = (spec or {}).get("requirements") or []
        self.ids = dict(zip(("t1", "t2"), (r["identifier"] for r in reqs)))  # authored order
        self.revisions = 0
        self.tasks = {t["spec_task_key"]: t for t in rows
                      if t.get("spec_document_id") and t.get("build_id") == self.build_id}
        check(f"{label}: build {self.build_id} carries t1 and t2", set(self.tasks) == {"t1", "t2"},
              str(sorted(self.tasks)), fatal=True)

    def view(self):
        return api("GET", f"{self.ctx['base']}/project/builds/{self.build_id}")[1]

    def pr(self):
        return (self.view() or {}).get("pull_request") or {}

    def gh_pr(self, *fields):
        url = self.pr().get("url")
        return gh_json(self.ctx["root"], "pr", "view", url, "--json", ",".join(fields)) if url else {}

    def work(self, key, line=None):
        """The builder's part, done by the operator's hand: one line in the task's worktree,
        committed, the task completed. The Hub's checks and the reviewer's verdict are skipped:
        the operator sets `approved` through the task route."""
        task = self.tasks[key]
        wt = pathlib.Path(self.ctx["root"]) / ".agentweave" / "tasks" / task["id"]
        line = line or f"drive-{STAMP}-{self.label}-{key}"
        text = (wt / README).read_text(encoding="utf-8")
        if line not in text:
            (wt / README).write_text(text.rstrip("\n") + f"\n{line}\n", encoding="utf-8")
            run(wt, "git", "add", README)
            run(wt, "git", "-c", "user.email=d@example.invalid", "-c", "user.name=drive",
                "commit", "-q", "-m", f"drive: {key}")
        head = run(wt, "git", "rev-parse", "HEAD")
        api("PATCH", f"{self.ctx['base']}/tasks/{task['id']}", {"status": "completed"})
        # Operator-recorded evidence is accepted on arrival; in a flow accepted evidence at the
        # task's commit is what approval pushes (and what the PR description names).
        code, out = api("POST", f"{self.ctx['base']}/project/spec/evidence",
                        {"identifier": self.ids[key], "document": self.doc, "task_id": task["id"],
                         "kind": "manual_observation", "commit": head, "covers": "full",
                         "summary": f"drive: {key} appended its line to {README}"})
        check(f"{self.label}: {key} evidence recorded and accepted at {head[:8]}",
              code == 201 and (out.get("review_state") == "accepted"), f"{code} {str(out)[:300]}")

    def set_status(self, key, status, **extra):
        return api("PATCH", f"{self.ctx['base']}/tasks/{self.tasks[key]['id']}",
                   {"status": status, **extra})

    def approve(self, key):
        code, out = self.set_status(key, "approved")
        check(f"{self.label}: {key} approved", code == 200, f"{code} {str(out)[:300]}")
        # Pushing happens after the landing-phase checks, so give it time.
        poll(lambda: self.pr().get("url") or self.pr().get("error"), 600, 5)


def drive(state):
    root = TMP / "proj"
    run(TMP, "git", "clone", "-q", "--depth", "50", "https://github.com/gutohuida/AgentWeave.git",
        str(root))
    run(root, "git", "config", "user.email", "d@example.invalid")
    run(root, "git", "config", "user.name", "drive")
    main_name = run(root, "git", "rev-parse", "--abbrev-ref", "HEAD")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"prdrive-{STAMP}"})
    check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    ctx = {"base": base, "root": str(root)}
    state.update(base=base, root=str(root))
    api("PATCH", base, {"main_branch": main_name})
    code, out = api("PUT", f"{base}/settings", {"allow_agent_jobs": True, "pr_landing": True})
    check("setup: PR landing turned on", code == 200, f"{code} {str(out)[:300]}", fatal=True)
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    check("setup: a Haiku runner", code in (200, 201), f"{code} {runner}", fatal=True)
    for name in (BUILDER, CHECKER):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    one = Build(ctx, "a")
    state["builds"] = [one]
    # draft-ac1
    one.work("t1")
    one.approve("t1")
    pr = one.gh_pr("isDraft", "baseRefName", "headRefName", "commits")
    check("draft-ac1: a draft PR against master from the build branch exists",
          pr and pr["isDraft"] and pr["baseRefName"] == main_name,
          f"{one.pr()} {str(pr)[:300]}", fatal=True)
    n_first = len(pr["commits"])
    one.work("t2")
    one.approve("t2")
    pr = one.gh_pr("isDraft", "commits", "number")
    check("draft-ac1: the second task's commit is on the same PR",
          len(pr["commits"]) > n_first and one.pr().get("number") == pr["number"],
          f"commits {n_first}->{len(pr['commits'])}")
    # ready-ac1
    states = [one.gh_pr("isDraft")["isDraft"]]
    one.set_status("t2", "revision_needed", reason_class="defect", notes="drive: sent back")
    poll(lambda: one.gh_pr("isDraft")["isDraft"], 120, 3)
    states.append(one.gh_pr("isDraft")["isDraft"])
    one.work("t2", f"drive-{STAMP}-a-t2-again")
    one.approve("t2")
    poll(lambda: not one.gh_pr("isDraft")["isDraft"], 600, 5)
    states.append(one.gh_pr("isDraft")["isDraft"])
    check("ready-ac1: ready, then draft after the send-back, then ready", states == [False, True, False],
          f"isDraft sequence {states}")
    # desc-ac1
    pr = one.gh_pr("title", "body")
    body = pr.get("body", "")
    _, evidence = api("GET", f"{base}/project/spec/evidence?document={urllib.parse.quote(one.doc)}")
    ev_ids = [e["id"] for e in (evidence if isinstance(evidence, list) else
                                (evidence or {}).get("evidence", [])) if e.get("review_state") == "accepted"]
    reqs = list(one.ids.values()) or ["FR-1", "FR-2"]
    missing = [x for x in [one.doc, *reqs, *ev_ids, "t1", "t2"] if x not in body]
    # each task's line must carry a state word, not just the key
    state_words = ("pending", "assigned", "in_progress", "completed", "under_review", "approved",
                   "revision_needed", "pushed", "landed", "passed")
    missing += [f"state of {k}" for k in ("t1", "t2")
                if not any(k in ln and any(w in ln.lower() for w in state_words)
                           for ln in body.splitlines())]
    check("desc-ac1: title is the spec's; body names spec path, requirement ids, accepted evidence "
          "ids and each task with its state", pr.get("title") == one.title and not missing
          and bool(ev_ids), f"title {pr.get('title')!r}; missing from body {missing}; "
          f"accepted evidence ids {ev_ids}")
    # sh-ac1
    view = one.view() or {}
    card = view.get("pull_request") or {}
    task_card = ((api("GET", f"{base}/tasks/{one.tasks['t1']['id']}")[1]) or {}).get("pull_request") or {}
    check("sh-ac1: the build card and a task show the link, state and last-asked time",
          all(c.get("url") and c.get("state") in ("draft", "ready") and c.get("last_asked_at")
              for c in (card, task_card)), f"build {card}; task {task_card}")

    # mc-ac1: a second PR, closed on GitHub.
    two = Build(ctx, "b")
    state["builds"].append(two)
    two.work("t1")
    two.approve("t1")
    url2 = two.pr().get("url")
    check("mc-ac1: build 2 has a PR", bool(url2), str(two.pr()), fatal=True)
    branch2 = two.gh_pr("headRefName")["headRefName"]
    run(root, "gh", "pr", "close", url2)
    api("POST", f"{base}/project/builds/{two.build_id}/check-now")
    view = two.view() or {}
    landed = [(t.get("key"), t.get("landed")) for t in (view.get("tasks") or [])]
    remote = run(root, "git", "ls-remote", "--heads", "origin", branch2)
    local = run(root, "git", "branch", "--list", branch2) or run(root, "git", "branch", "-a", "--list", f"*{branch2}")
    check("mc-ac1: build 2's tasks read not landed; the branch is on GitHub and locally",
          view.get("pull_request", {}).get("state") == "closed"
          and all(not v for _, v in landed) and bool(landed) and bool(remote) and bool(local),
          f"state {view.get('pull_request')}; tasks {landed}; remote {bool(remote)} local {bool(local)}")

    # The human step.
    url1 = one.pr().get("url")
    print(f"\nHUMAN STEP\n  1. Merge PR 1 on GitHub: {url1}\n  2. Press 'check now' on the build in "
          "AgentWeave\n  3. Press Enter here.\n", flush=True)
    if os.environ.get("AW_DRIVE_NO_HUMAN"):
        print("AW_DRIVE_NO_HUMAN set: stopping before the merge checks")
        return
    input()
    api("POST", f"{base}/project/builds/{one.build_id}/check-now")
    view = one.view() or {}
    tasks = view.get("tasks") or []
    merge = run(root, "gh", "pr", "view", url1, "--json", "mergeCommit,state")
    merge = json.loads(merge)
    sha = (merge.get("mergeCommit") or {}).get("oid", "")
    check("mc-ac2: build 1's tasks read landed, naming GitHub's merge commit",
          merge["state"] == "MERGED" and bool(tasks)
          and all(t.get("landed") and sha and sha in json.dumps(t.get("landed")) for t in tasks),
          f"merge {sha}; tasks {[(t.get('key'), t.get('landed')) for t in tasks]}")
    run(root, "git", "fetch", "-q", "origin", main_name)
    ok = poll(lambda: run(root, "git", "rev-parse", main_name) == run(root, "git", "rev-parse",
                                                                      f"origin/{main_name}"), 30)
    check("lm-ac1: the local main equals GitHub's main", bool(ok),
          f"local {run(root, 'git', 'rev-parse', main_name)} remote "
          f"{run(root, 'git', 'rev-parse', f'origin/{main_name}')}")


def is_banned(argv):
    """FR-12: is this `gh` call a merge, approval, base change or protection change? Banned by
    operation, not substring: opening, editing, drafting, readying and reading a PR are allowed."""
    a = [str(x).lower() for x in argv]
    flat = " ".join(a)
    if a[:2] == ["pr", "merge"] or "protection" in flat or "rulesets" in flat:
        return True
    if a[:2] == ["pr", "review"]:
        return any(x in ("--approve", "-a") for x in a)
    if a[:2] == ["pr", "edit"]:
        return any(x in ("--base", "-b") or x.startswith("--base=") for x in a)
    if a[:1] == ["api"]:
        method = "get"
        for i, x in enumerate(a):
            if x in ("-x", "--method") and i + 1 < len(a):
                method = a[i + 1]
            elif x.startswith("--method="):
                method = x.split("=", 1)[1]
            elif x.startswith("-x") and len(x) > 2:
                method = x[2:]
        path = next((x for x in a[1:] if "/" in x and not x.startswith("-")), "")
        if re.search(r"/merge(?!\w)", path):
            return True
        if re.search(r"/reviews(/|$)", path) and method != "get" and "approve" in flat:
            return True
        if method in ("patch", "put") and re.search(r"(^|\s)(-f|--field|--raw-field)\s+base=", flat):
            return True
        if method in ("patch", "put") and re.search(r"\"base\"\s*:", flat):
            return True
    return False


def audit_calls():
    calls = [json.loads(line)["argv"] for line in calls_log.read_text(encoding="utf-8").splitlines()
             ] if calls_log.exists() else []
    print(f"\nthe Hub's gh calls ({len(calls)}), from the shim, minus the drive's own:")
    for argv in calls:
        print("  gh " + " ".join(argv))
    banned = [" ".join(a) for a in calls if is_banned(a)]
    check("nm-ac1: none of the Hub's gh calls is a merge, approval, base change or "
          "branch-protection change", bool(calls) and not banned,
          f"{len(calls)} calls; offending {banned}" if calls else "no gh call recorded at all")


def tidy(state):
    base = state.get("base")
    for build in state.get("builds", []):
        code, _ = api("POST", f"{base}/project/builds/{build.build_id}/stop")
        print(f"stopped build {build.build_id}: {code}")


def main():
    proc = start_hub()
    state = {}
    try:
        drive(state)
    except Stop:
        pass
    finally:
        try:
            audit_calls()
            tidy(state)
        finally:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
