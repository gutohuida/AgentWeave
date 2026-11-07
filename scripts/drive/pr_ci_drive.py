"""Acceptance drive for `the-pr-s-ci-is-the-full-check` (spdoc-45c8f455b7cc), 2026-11-07.

The change's `drive` task, written before the build of the rest: on master it fails at its first
step, because the project setting 'the PR's CI is the full check' does not exist (the settings
route forbids unknown fields; hub/hub/api/v1/projects.py). It drives a Hub it starts itself on
AW_DRIVE_PORT (default 8010) over a FRESH database under the drive's temp directory (AW_DRIVE_DB
overrides), so no trial project's loops wake beside it. The Hub's PATH carries slice 1's `gh.exe`
shim (scripts/drive/gh_shim.cs), which logs every `gh` call the Hub makes, and a stub `claude` that
fails every turn, so the operator's hand (`Build.work`) is the only builder.

The repository is the scratch one, https://github.com/gutohuida/agentweave-pr-scratch: its
workflow `ci` has one job, `ci-check`, which branch protection on `main` marks required, and which
fails when a file named `FAIL` is at the root. Both projects are clones of it, each with one
landing-phase check that appends a line to its own marker file, so whether it ran is read from the
disk, not from any route.

  ON (pr_landing + the CI setting on, interval 1 minute, cutoff 30):
    1. t1 (one README line) approved -> pushed, a draft PR; the landing check never ran (ac-no-local,
       first half). CI on the head concludes on GitHub -> the build shows it within one interval
       (ac-pending, the concluding case) as passed naming the head commit, and so does t1
       (ac-passed). The PR is still a draft: t2 is not pushed (ac-ready's 'until then').
       Then 150 s in which nobody acts: the Hub makes no `gh` call (ac-pending, 'no interval asks
       follow until a new push').
    2. t2 adds the `FAIL` marker, approved -> pushed; while CI is pending the PR stays a draft
       (ac-ready, pending half). `ci-check` fails, main is green -> the PR is a draft, t2 is sent
       back, its notes name `ci-check` and a GitHub link to it (ac-failed).
    3. t2's fix removes the marker, approved again -> pushed; CI passes -> the PR is marked ready
       (ac-ready), t2 reads CI passed naming the new head (ac-passed).
  OFF (pr_landing on, the CI setting off): t1 approved -> the landing check ran, then the PR
    exists (ac-no-local, second half).

Not driven here, by the spec's own Check lines: the cutoff case of ac-pending (a Hub test with a
controllable clock; a real run cannot be made to never conclude), and ac-failed's 'ready PR' start
(under FR-8 a PR whose head was just pushed is a draft while its CI is pending, so the drive checks
the PR is a draft after the failure). Throughout, none of the Hub's `gh` calls is a merge, approval,
base change or protection change (slice 1's audit, `pr_landing_drive.is_banned`).

The contract the build is expected to meet, which this drive reads (names chosen here, by the
drive, for the Hub tasks to implement):
  project settings (PUT /projects/{id}/settings): `pr_ci_full_check` (bool),
    `pr_ci_check_names` (list of str), `pr_ci_interval_minutes` (int), `pr_ci_cutoff_minutes` (int);
  the build read (GET /project/spec?path=..., `builds[]`): `pull_request.ci` =
    {`state`: pending | passed | failed | failing_on_main | superseded | not_finished,
     `head_sha`, `checks`: [{`name`, `state`, `url`}], `last_asked_at`, `error`};
  a task's CI: `ci` = {`state`, `head_sha`, ...} on GET /tasks/{id}, or on GET /tasks/{id}/checks
    (top level, or inside its `landing`); the drive accepts any of the three.
  A CI send-back is the task at `revision_needed` with `notes` naming each failing check and its
  GitHub link.

    py -3.11 scripts/drive/pr_ci_drive.py          # AW_DRIVE_KEEP=1 leaves the PRs open
    AW_DRIVE_ONLY=on|off runs one half (`off` is slice 1's behaviour and passes on master)
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pr_landing_drive as prl  # noqa: E402 -- slice 1's drive: the Hub, the gh shim, the helpers
from pr_landing_drive import api, check, poll, run  # noqa: E402

STAMP = prl.STAMP
TMP = prl.TMP.parent.parent / "drive-pr-ci" / STAMP
# slice 1's start_hub and audit_calls read these from their own module
prl.TMP, prl.calls_log = TMP, TMP / "gh-calls.jsonl"
prl.DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or TMP / "agentweave.db")
calls_log = prl.calls_log

SCRATCH = "gutohuida/agentweave-pr-scratch"
MAIN = "main"
REQUIRED = "ci-check"
MARKER = "FAIL"
README = "testbed/README.md"
BUILDER, CHECKER = prl.BUILDER, prl.CHECKER
INTERVAL_MIN, CUTOFF_MIN = 1, 30
# GitHub's run takes ~20-40 s after the push, then the Hub's next ask is at most one interval away.
CI_WAIT = 600


def hub_calls():
    if not calls_log.exists():
        return []
    return [json.loads(line)["argv"] for line in calls_log.read_text(encoding="utf-8").splitlines()]


def github_check(root, sha):
    """`ci-check` on *sha* as GitHub reports it, read by the drive's own `gh` (not the shim):
    (status, conclusion, completed_at, html_url) or None before the run exists."""
    runs = prl.gh_json(root, "api", f"repos/{SCRATCH}/commits/{sha}/check-runs")
    for row in runs.get("check_runs") or []:
        if row.get("name") == REQUIRED:
            return row.get("status"), row.get("conclusion"), row.get("completed_at"), row.get(
                "html_url")
    return None


def payload(title):
    def task(key, req, what):
        return {"key": key, "title": what, "requirements": [req], "files": [README, MARKER],
                "description": f"{what}. Change nothing else.", "builder": BUILDER,
                "reviewer": CHECKER}
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": "Two small changes to the scratch repository.",
        "problem": "Drive the PR's CI as the full check.",
        "scope": {"in_scope": [README, MARKER], "non_goals": ["Anything else"]},
        "requirements": [{"key": k, "modal": "MUST",
                          "statement": f"The scratch repository MUST carry change {k}."}
                         for k in ("one", "two")],
        "acceptance_criteria": [{"key": f"has-{k}", "requirement": k, "given": "the repository",
                                 "when": "CI runs", "then": f"it has {k} and ci-check passes",
                                 "how_to_check": "the PR's ci-check", "checked_by": "agent"}
                                for k in ("one", "two")],
        "tasks": [task("t1", "one", f"Append drive-{STAMP}-one to {README}"),
                  task("t2", "two", f"Append drive-{STAMP}-two to {README}")],
        "delivery": {"mode": "flow", "agent": BUILDER, "builders": [BUILDER], "level": "reviewed",
                     "stop_when_queue_empties": True, "cron": "0 0 1 1 *",
                     "reasons": {"mode": "Two tasks.", "agent": "Default."}},
    }


class Project:
    """A clone of the scratch repository opened as a project, PR landing on, one landing check."""

    def __init__(self, label, ci_on):
        self.label = label
        self.root = TMP / f"proj-{label}"
        self.marker = TMP / f"landing-check-ran-{label}.txt"
        run(TMP, "git", "clone", "-q", f"https://github.com/{SCRATCH}.git", str(self.root))
        run(self.root, "git", "config", "user.email", "d@example.invalid")
        run(self.root, "git", "config", "user.name", "drive")
        code, project = api("POST", "/projects/open",
                            {"path": str(self.root), "name": f"prci-{label}-{STAMP}"})
        check(f"{label}: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
        self.base = f"/projects/{project['id']}"
        api("PATCH", self.base, {"main_branch": MAIN})
        probe = (f'py -3.11 -c "import pathlib; p = pathlib.Path(r\'{self.marker}\'); '
                 f"p.open('a').write('ran\\n')\"")
        code, out = api("PUT", f"{self.base}/settings", {
            "allow_agent_jobs": True, "pr_landing": True,
            "checks": [{"name": "landing-probe", "command": probe, "phase": "landing",
                        "timeout_seconds": 60}]})
        check(f"{label}: PR landing on, a landing-phase check configured", code == 200,
              f"{code} {str(out)[:300]}", fatal=True)
        if ci_on:
            code, out = api("PUT", f"{self.base}/settings", {
                "pr_ci_full_check": True, "pr_ci_check_names": [],
                "pr_ci_interval_minutes": INTERVAL_MIN, "pr_ci_cutoff_minutes": CUTOFF_MIN})
            check(f"{label}: 'the PR's CI is the full check' turned on, interval {INTERVAL_MIN}, "
                  f"cutoff {CUTOFF_MIN}", code == 200 and (out or {}).get("pr_ci_full_check")
                  is True, f"{code} {str(out)[:400]}", fatal=True)
        code, runner = api("POST", f"{self.base}/runners",
                           {"name": "Haiku", "cli": "claude", "model": prl.HAIKU})
        check(f"{label}: a Haiku runner", code in (200, 201), f"{code} {runner}", fatal=True)
        for name in (BUILDER, CHECKER):
            code, out = api("POST", f"{self.base}/agents", {"name": name, "runner_id": runner["id"]})
            check(f"{label}: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    def landing_check_ran(self):
        return self.marker.exists()


class Build(prl.Build):
    """slice 1's build, on a scratch project, whose tasks change files the drive names."""

    def __init__(self, project, label):
        saved = prl.payload
        prl.payload = payload
        try:
            super().__init__({"base": project.base, "root": str(project.root)}, label)
        finally:
            prl.payload = saved
        self.project = project

    def change(self, key, edit, note):
        """The builder's part by hand (slice 1's `work`, generalised): *edit* changes the task's
        worktree, which is committed, the task completed and its evidence recorded."""
        task = self.tasks[key]
        wt = self.project.root / ".agentweave" / "tasks" / task["id"]
        if not (wt / README).exists():
            code, out = api("POST", f"{self.project.base}/agent/trigger",
                            {"agent": BUILDER, "task_id": task["id"],
                             "message": "drive: provision this task's worktree"})
            check(f"{self.label}: {key} worktree provisioned by a turn",
                  poll(lambda: (wt / README).exists(), 120, 2), f"{code} {str(out)[:300]}",
                  fatal=True)
            time.sleep(10)
        edit(wt)

        def commit():
            try:
                tracked = run(wt, "git", "ls-files", "--", MARKER)
                paths = [README] + ([MARKER] if tracked or (wt / MARKER).exists() else [])
                run(wt, "git", "add", "-A", "--", *paths)
                run(wt, "git", "-c", "user.email=d@example.invalid", "-c", "user.name=drive",
                    "commit", "-q", "-m", f"drive: {key} {note}")
                return True
            except RuntimeError as exc:
                if "index.lock" not in str(exc):
                    raise
                return False

        check(f"{self.label}: {key} committed ({note})", poll(commit, 120, 3), fatal=True)
        head = run(wt, "git", "rev-parse", "HEAD")
        self.set_status(key, "completed")
        code, out = api("POST", f"{self.project.base}/project/spec/evidence",
                        {"identifier": self.ids[key], "document": self.doc, "task_id": task["id"],
                         "kind": "manual_observation", "commit": head, "covers": "full",
                         "summary": f"drive: {key} {note}"})
        check(f"{self.label}: {key} evidence accepted at {head[:8]}",
              code == 201 and out.get("review_state") == "accepted", f"{code} {str(out)[:300]}")
        return head

    def approve_and_push(self, key):
        """Approve *key* and wait until its commits are on the PR's branch on GitHub; the PR's
        head after the push."""
        before = self.gh_pr("headRefOid").get("headRefOid") if self.pr().get("url") else None
        self.approve(key)

        def moved():
            if not self.pr().get("url"):
                return None
            head = self.gh_pr("headRefOid").get("headRefOid")
            return head if head and head != before else None

        head = poll(moved, 600, 5)
        check(f"{self.label}: {key}'s approval reached the PR's branch", bool(head),
              f"pr {self.pr()}", fatal=True)
        return head

    def ci(self):
        return (self.pr() or {}).get("ci") or (self.view() or {}).get("ci") or {}

    def task_ci(self, key):
        task_id = self.tasks[key]["id"]
        _, row = api("GET", f"{self.project.base}/tasks/{task_id}")
        if isinstance(row, dict) and row.get("ci"):
            return row["ci"]
        _, checks = api("GET", f"{self.project.base}/tasks/{task_id}/checks")
        checks = checks if isinstance(checks, dict) else {}
        return checks.get("ci") or (checks.get("landing") or {}).get("ci") or {}

    def task(self, key):
        return api("GET", f"{self.project.base}/tasks/{self.tasks[key]['id']}")[1] or {}

    def is_draft(self):
        return self.gh_pr("isDraft").get("isDraft")


def append_line(line):
    def edit(wt):
        path = wt / README
        path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + f"\n{line}\n",
                        encoding="utf-8")
    return edit


def add_marker(wt):
    (wt / MARKER).write_text("drive: ci-check fails while this file exists\n", encoding="utf-8")


def remove_marker(wt):
    (wt / MARKER).unlink(missing_ok=True)


def wait_github(root, sha):
    """Until GitHub's `ci-check` on *sha* has concluded: (conclusion, completed_at, url)."""
    row = poll(lambda: (lambda r: r if r and r[0] == "completed" else None)(github_check(root, sha)),
               CI_WAIT, 10)
    return (row[1], row[2], row[3]) if row else (None, None, None)


def lag_seconds(completed_at):
    stamp = time.mktime(time.strptime(completed_at, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    return time.time() - stamp


def drive_on(state):
    proj = Project("on", ci_on=True)
    state["projects"].append(proj)
    root = proj.root
    main_sha = run(root, "git", "rev-parse", f"origin/{MAIN}")
    main_ci = github_check(root, main_sha)
    check("setup: main is green on GitHub (its ci-check succeeded)",
          bool(main_ci) and main_ci[1] == "success", f"main {main_sha[:8]}: {main_ci}", fatal=True)

    build = Build(proj, "on")
    state["builds"].append(build)

    # --- 1. t1 passes: pushed without the local landing check, CI read on the interval ---------
    build.change("t1", append_line(f"drive-{STAMP}-on-t1"), "appends its line")
    head1 = build.approve_and_push("t1")
    check("ac-no-local: setting on -> t1 reached the PR's branch and no landing-phase check ran",
          head1 and not proj.landing_check_ran(), f"head {head1}; marker {proj.marker} exists: "
          f"{proj.landing_check_ran()}")
    check("ac-ready: t2 not pushed yet -> the PR is a draft", build.is_draft() is True,
          str(build.gh_pr("isDraft", "url")))
    conclusion, completed_at, url = wait_github(root, head1)
    check("ac-pending: GitHub concluded ci-check on t1's head", conclusion == "success",
          f"{conclusion} at {completed_at}", fatal=True)
    shown = poll(lambda: build.ci() if build.ci().get("state") == "passed" else None,
                 INTERVAL_MIN * 60 + 90, 3)
    lag = lag_seconds(completed_at)
    check(f"ac-pending: the build shows the result within one interval ({INTERVAL_MIN} min) of "
          "GitHub concluding it, nobody acting", bool(shown) and lag <= INTERVAL_MIN * 60 + 45,
          f"shown after {lag:.0f}s: {build.ci()}")
    check("ac-passed: the build reads CI passed naming the head commit",
          bool(shown) and shown.get("head_sha") == head1
          and any(c.get("name") == REQUIRED and c.get("state") in ("passed", "success")
                  and str(c.get("url", "")).startswith("https://github.com/")
                  for c in shown.get("checks") or []), f"head {head1}; ci {shown}")
    t1_ci = build.task_ci("t1")
    check("ac-passed: t1 reads CI passed naming the head commit",
          t1_ci.get("state") == "passed" and t1_ci.get("head_sha") == head1, f"{t1_ci}")
    check("ac-ready: CI passed but t2 not pushed -> the PR stays a draft", build.is_draft() is True)
    quiet_from = len(hub_calls())
    time.sleep(INTERVAL_MIN * 60 * 2.5)
    quiet = hub_calls()[quiet_from:]
    check("ac-pending: CI concluded and nobody acting -> no ask for 2.5 intervals",
          not quiet, f"{len(quiet)} gh calls: {[' '.join(a) for a in quiet][:6]}")

    # --- 2. t2 adds the marker: CI fails, main is green -> PR draft, t2 sent back --------------
    build.change("t2", add_marker, "adds the FAIL marker")
    head2 = build.approve_and_push("t2")
    pending = github_check(root, head2)
    check("ac-ready: every task pushed, CI pending -> the PR stays a draft",
          build.is_draft() is True and (pending is None or pending[0] != "completed"),
          f"github {pending}; isDraft {build.is_draft()}")
    conclusion, completed_at, fail_url = wait_github(root, head2)
    check("ac-failed: GitHub's ci-check failed on t2's head", conclusion == "failure",
          f"{conclusion} {fail_url}", fatal=True)
    sent = poll(lambda: (lambda t: t if t.get("status") == "revision_needed" else None)(
        build.task("t2")), INTERVAL_MIN * 60 + 120, 5)
    notes = (sent or {}).get("notes") or ""
    links = re.findall(rf"https://github\.com/{re.escape(SCRATCH)}/\S+", notes)
    check("ac-failed: t2 is sent back naming ci-check with a link to it",
          bool(sent) and REQUIRED in notes and bool(links),
          f"status {(sent or build.task('t2')).get('status')}; notes {notes[:600]!r}")
    check("ac-failed: the PR is back to (or still) a draft", build.is_draft() is True)
    failed = build.ci()
    check("ac-failed: the build reads CI failed (not 'failing on main too') on t2's head",
          failed.get("state") == "failed" and failed.get("head_sha") == head2, f"{failed}")
    check("ac-failed: t1 is not sent back", build.task("t1").get("status") == "approved",
          build.task("t1").get("status"))

    # --- 3. t2's fix: CI passes -> PR ready ---------------------------------------------------
    build.change("t2", remove_marker, "removes the FAIL marker")
    head3 = build.approve_and_push("t2")
    draft_while_pending = build.is_draft()
    conclusion, completed_at, _ = wait_github(root, head3)
    check("ac-ready: the fix's CI pending -> the PR stays a draft", draft_while_pending is True,
          f"isDraft {draft_while_pending}")
    check("ac-ready: GitHub's ci-check passed on the fix", conclusion == "success", conclusion,
          fatal=True)
    ready = poll(lambda: build.is_draft() is False, INTERVAL_MIN * 60 + 90, 5)
    check("ac-ready: every task pushed and CI passed -> the PR is marked ready", bool(ready),
          str(build.gh_pr("isDraft", "url")))
    t2_ci = build.task_ci("t2")
    check("ac-passed: t2 reads CI passed naming the new head",
          t2_ci.get("state") == "passed" and t2_ci.get("head_sha") == head3, f"{t2_ci}")


def drive_off(state):
    proj = Project("off", ci_on=False)
    state["projects"].append(proj)
    build = Build(proj, "off")
    state["builds"].append(build)
    build.change("t1", append_line(f"drive-{STAMP}-off-t1"), "appends its line")
    head = build.approve_and_push("t1")
    check("ac-no-local: setting off -> the landing-phase check ran before t1 was pushed",
          bool(head) and proj.landing_check_ran(), f"head {head}; marker {proj.marker}")


def tidy(state):
    for build in state.get("builds", []):
        code, _ = api("POST", f"{build.project.base}/project/builds/{build.build_id}/stop")
        print(f"stopped build {build.build_id}: {code}")
        url = (build.pr() or {}).get("url")
        if url and not os.environ.get("AW_DRIVE_KEEP"):
            subprocess.run(["gh", "pr", "close", url, "--delete-branch"], capture_output=True)
            print(f"closed {url}")


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    proc = prl.start_hub()
    state = {"projects": [], "builds": []}
    try:
        only = os.environ.get("AW_DRIVE_ONLY")
        if only != "off":
            drive_on(state)
        if only != "on":
            drive_off(state)
    except prl.Stop:
        pass
    finally:
        try:
            prl.audit_calls()
            tidy(state)
        finally:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    bad = [name for name, ok in prl.results if not ok]
    print(f"\n{len(prl.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
