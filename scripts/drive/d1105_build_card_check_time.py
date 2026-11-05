"""Acceptance drive, 2026-11-05: the build card accounts for a parallel build's check runs
(`the-build-card-shows-where-check-time-went`, FR-2 and FR-5 `drive-live`).

A fresh project on the trial Hub :8010 with a check that takes ~25 s, and a Reviewed flow build of two
tasks, each by its own builder (Haiku turns). While both tasks are still being built the drive asks the
Hub to run each task's checks, so the runs overlap building; the flow then reviews, approves and lands
both. At the end:

  runs overlapped   the two check runs started before either task left building
  checks total      the card's Checks figure (running + waiting, from `/builds/{id}/figures`) equals the
                    sum of the check runs' durations read from each task's `/checks` route
  landing wait      the card carries a landing-wait figure, and the page shows the Checks meter

On master the figures route has `checks.{runs, passed, failed, seconds}` only: no running or waiting
split, no timed-out count, no landing wait, so the second and third groups FAIL there -- that is the
point. Expected on master: the checks total, landing wait and page checks fail; setup and overlap pass.

The figures' key names are the tally task's to pick, so they are found by name below rather than fixed:
a leaf under `checks` whose path holds `running` or `waiting`, and any non-null leaf whose path holds
`landing`.

Starts the trial Hub from this checkout unless one is already on :8010. Cleans up after itself: the
build is stopped, the flow's job archived, the scratch project's directory removed.

    py -3.11 scripts/drive/d1105_build_card_check_time.py
"""

import shutil
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d
from playwright.sync_api import sync_playwright

d.TMP = d.TMP.parent.parent / "drive1105-build-card-check-time" / d.STAMP
DOC = "spec/changes/two-notes/spec.json"
B1, B2, CHECKER = "BuilderOne", "BuilderTwo", "Checker"
LIMIT = 25 * 60  # a Haiku build+review+land of two tasks takes 10-20 min; the log prints progress
SECONDS_PER_CHECK = 25
TOLERANCE = 2.0  # seconds: timestamps are stored to the microsecond, the figure rounds


def payload():
    tasks = []
    for n, builder in ((1, B1), (2, B2)):
        tasks.append({
            "key": f"t{n}", "title": f"Write note {n}", "requirements": [f"note{n}"],
            "description": f"Create NOTE{n}.md holding the single line `note{n}`, then move this task "
                           "to completed. Change nothing else.",
            "files": [f"NOTE{n}.md"], "builder": builder, "reviewer": CHECKER,
        })
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Two notes",
        "summary": "Two files.", "problem": "There are no notes.",
        "scope": {"in_scope": ["NOTE1.md", "NOTE2.md"], "non_goals": ["Anything else"]},
        "requirements": [{"key": f"note{n}", "modal": "MUST", "statement": f"NOTE{n}.md MUST exist."}
                         for n in (1, 2)],
        "acceptance_criteria": [{
            "key": f"exists{n}", "requirement": f"note{n}", "given": "the repository", "when": "listed",
            "then": f"NOTE{n}.md is there", "how_to_check": "ls", "checked_by": "agent"} for n in (1, 2)],
        "tasks": tasks,
        "delivery": {"mode": "flow", "agent": B1, "checker": CHECKER, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def leaves(value, path=""):
    """`(path, number-or-None)` for every scalar leaf of a JSON value."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield from leaves(inner, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            yield from leaves(inner, f"{path}[{i}]")
    else:
        yield path, value


def seconds_between(start, end):
    from datetime import datetime

    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def main():
    hub = d.start_hub()
    root = d.TMP / "proj"
    state = {}
    try:
        root.mkdir(parents=True)
        d.git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
        d.git(root, "add", ".")
        d.git(root, "commit", "-q", "-m", "seed")
        code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"cardchecks-{d.STAMP}"})
        d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
        pid = project["id"]
        base = f"/projects/{pid}"
        d.api("PATCH", base, {"main_branch": "main"})
        sleeper = f'"{sys.executable}" -c "import time; time.sleep({SECONDS_PER_CHECK})"'
        code, out = d.api("PUT", f"{base}/settings", {"checks": [{
            "name": "slow", "command": sleeper, "timeout_seconds": 120}]})
        d.check("setup: a slow check", code == 200, f"{code} {str(out)[:400]}", fatal=True)
        code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
        d.check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
        for name in (B1, B2, CHECKER):
            code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
            d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

        quoted = urllib.parse.quote(DOC)
        code, out = d.api("POST", f"{base}/project/documents",
                          {"title": "Two notes", "kind": "change-spec", "path": DOC})
        d.check("setup: document created", code == 201, f"{code} {out}", fatal=True)
        code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
        d.check("setup: document saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
        code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                          {"reason": "drive", "approve_anyway": True,
                           "content_version": read.get("content_version")})
        d.check("setup: document approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                          {"driver": "flow", "level": "reviewed", "builders": [B1, B2],
                           "checker": CHECKER, "landing": "main"})
        d.check("setup: built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
        rows = d.ro("select t.id, t.loop_id from tasks t join spec_documents s on t.spec_document_id=s.id "
                    "where s.project_id=? and s.path=?", (pid, DOC))
        d.check("setup: two tasks", len(rows) == 2, str(rows), fatal=True)
        tasks = [r[0] for r in rows]
        loop = rows[0][1]
        job = d.ro("select job_id from loops where id=?", (loop,))[0][0]
        state.update(base=base, build_id=build_id, job=job, root=root)
        print(f"project {pid} build {build_id} tasks {tasks} loop {loop} job {job}", flush=True)

        def status(task):
            return d.ro("select status from tasks where id=?", (task,))[0][0]

        # Both tasks must be mid-build when their check runs are asked for. Fire until both are handed
        # out, then request the runs at once.
        d.fire(base, job)
        overlapped = d.poll(lambda: all(status(t) in ("assigned", "in_progress") for t in tasks)
                            and all(d.handouts(t, review=False) for t in tasks), 60)
        d.check("overlap: both tasks are being built", overlapped, str([status(t) for t in tasks]))
        asked = {}
        for task in tasks:
            code, out = d.api("POST", f"{base}/tasks/{task}/checks/run")
            asked[task] = (code, status(task))
        d.check("overlap: both check runs accepted while building",
                all(c == 202 and s in ("assigned", "in_progress") for c, s in asked.values()), str(asked))

        start = time.time()
        while time.time() - start < LIMIT:
            for _ in range(int(4 * 60 / 3)):
                if not d.runs_busy(pid):
                    break
                time.sleep(3)
            print(f"  {int(time.time() - start)}s {[status(t) for t in tasks]}", flush=True)
            if d.ro("select ending_state from loops where id=?", (loop,))[0][0]:
                break
            d.fire(base, job)
            time.sleep(5)
        d.check("both tasks approved", all(status(t) == "approved" for t in tasks),
                str([status(t) for t in tasks]))
        landed = d.ro("select count(*) from task_landings where task_id in (?, ?)", tuple(tasks))[0][0]
        d.check("both tasks landed on main", landed >= 2, f"{landed} landing rows")

        durations = []
        for task in tasks:
            _, out = d.api("GET", f"{base}/tasks/{task}/checks")
            for run in out.get("runs") or []:
                if run.get("started_at") and run.get("ended_at"):
                    durations.append(seconds_between(run["started_at"], run["ended_at"]))
        total = sum(durations)
        d.check("the check-run route lists the runs", len(durations) >= 2, str(durations))

        code, figures = d.api("GET", f"{base}/project/builds/{build_id}/figures")
        d.check("the figures route answers", code == 200, f"{code} {str(figures)[:300]}", fatal=True)
        found = list(leaves(figures.get("checks") or {}))
        running = [v for p, v in found if "running" in p and isinstance(v, (int, float))]
        waiting = [v for p, v in found if "waiting" in p]
        d.check("checks: the figures split running and waiting", bool(running) and bool(waiting),
                f"checks = {figures.get('checks')}")
        card_total = sum(running) + sum(v for v in waiting if isinstance(v, (int, float)))
        d.check("checks: the card's Checks total equals the sum of the check-run durations",
                bool(running) and abs(card_total - total) <= TOLERANCE,
                f"card {card_total:.1f}s, check-run route {total:.1f}s over {len(durations)} runs")
        d.check("checks: the timed-out count is reported",
                any("timed" in p for p, _ in found), f"checks = {figures.get('checks')}")
        landing = [(p, v) for p, v in leaves({k: v for k, v in figures.items() if k != "checks"})
                   if "landing" in p and v is not None]
        landing += [(p, v) for p, v in found if "landing" in p and v is not None]
        d.check("landing: the card carries a landing wait", bool(landing), str(figures)[:500])

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.add_init_script(
                f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {d.KEY!r}, "
                f"hubUrl: {d.HUB!r}}}));"
                f"localStorage.setItem('agentweave-selected-project', {pid!r});")
            page.goto(f"{d.HUB}/?project={pid}&tab=spec&spec={quoted}", wait_until="domcontentloaded")
            try:
                page.get_by_text("Wall time").first.wait_for(timeout=30000)
                text = page.locator("body").inner_text()
                # The wall bar's legend also says "Checks", so look for the meter itself: a bar
                # of its own (role=img) titled Checks, with running and waiting as parts.
                labels = [x for x in page.get_by_role("img").evaluate_all(
                    "els => els.map(e => e.getAttribute('aria-label') || '')")
                    if x.lower().startswith("checks")]
                meter = labels[0] if labels else ""
                d.check("page: a Checks meter of its own is drawn, with running and waiting parts",
                        "running" in meter.lower() and "waiting" in meter.lower(), f"{labels}")
                parts = meter_seconds(meter)
                got = sum(parts.get(k, 0) for k in ("running", "waiting"))
                d.check("page: the Checks meter's running + waiting parts add up to the check-run route's sum",
                        {"running"} <= parts.keys() and abs(got - total) <= TOLERANCE + 1,
                        f"meter {meter!r} parts {parts}, route {total:.1f}s")
                d.check("page: the landing wait is shown",
                        page.get_by_text("landing wait", exact=False).count() > 0, text[:300])
            except Exception as exc:  # noqa: BLE001 -- reported as the check's detail
                d.check("page: the build card renders", False, str(exc)[:300])
            page.screenshot(path=str(d.TMP / "card.png"), full_page=True)
            d.check("no page errors", not errors, str(errors[:3]))
            browser.close()
    except d.Stop:
        pass
    finally:
        tidy(state)
        d.stop_hub(hub)
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    for name in bad:
        print("  FAILED:", name)
    sys.exit(1 if bad else 0)


def meter_seconds(label):
    """`{part: seconds}` from a Bar's aria-label such as `Checks: Running 22s, Waiting 1m 5s`.

    Durations use hub/ui/src/lib/format.ts formatDuration: `Ns`, `Nm Ns`, `Nh Nm`. A part whose figure
    is not a duration (`unknown`) is left out. Matching whole words keeps `6s` from reading as `16s`.
    """
    import re

    out = {}
    for name, figure in re.findall(r"(\w[\w ]*?) (\d+h \d+m|\d+m \d+s|\d+s)(?=,|$)", label.split(":", 1)[-1]):
        h = re.fullmatch(r"(\d+)h (\d+)m", figure)
        m = re.fullmatch(r"(\d+)m (\d+)s", figure)
        sec = (int(h[1]) * 3600 + int(h[2]) * 60 if h else
               int(m[1]) * 60 + int(m[2]) if m else int(figure[:-1]))
        out[name.strip().lower()] = sec
    return out


def tidy(state):
    """Stop the build, archive the flow's job, and remove the scratch checkout this drive made."""
    base = state.get("base")
    if base:
        if state.get("build_id"):
            code, _ = d.api("POST", f"{base}/project/builds/{state['build_id']}/stop")
            print(f"stopped build {state['build_id']}: {code}")
        if state.get("job"):
            code, _ = d.api("POST", f"{base}/jobs/{state['job']}/archive")
            print(f"archived job {state['job']}: {code}")
    if state.get("root"):
        shutil.rmtree(state["root"], ignore_errors=True)


if __name__ == "__main__":
    main()
