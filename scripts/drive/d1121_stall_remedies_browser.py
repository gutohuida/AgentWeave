"""Drive of `a-two-profile-build-cannot-deadlock-and-a-stall-says-so`, task `stall-surfaces`
(TPBCD-4), 2026-11-21: a stall reads Stalled and offers its remedies (FR-7, FR-8, FR-9).

The stall is reached the way `unstaffed-names-missing-runner` reaches it, by nothing but the
product: a fresh Hub started from this checkout's `hub/` on a new database (AW_DRIVE_PORT, default
8041; never :8000 or :8010), three Haiku profiles -- Developer (builder), QA (checker), QA2 -- and
an approved two-task change built as a flow at Reviewed. QA's runner is unbound after Build, so when
Developer completes each task the flow cannot staff its review and opens a `review_unstaffed` stall
naming the missing runner. The drive fires the flow itself (its cron is yearly). About two Haiku
build turns and one Haiku review turn.

Checks, each reached or not and passed or failed at its own assertion:

  stalled-build-header-and-card   the build page header shows Stalled with its icon and not Running;
                                  T1's board card shows Stalled with its icon and not Ready for
                                  review or Running
  stall-remedy-controls-work      both controls are on the build page, the Overview notice and the
                                  card; 'Name a different checker' on T1's card naming QA2 ends T1's
                                  stall and queues QA2's review of T1; 'Review it yourself' on the
                                  build page for T2 opens the operator's review of T2 (the task
                                  drawer, with Land it); neither changes the page's address
  stall-notice-sentence-case      every stall notice shown starts with a capital and holds no conv-
                                  or task- identifier, and names QA

Screenshots of the build page, the board and the Overview at 1440 and 900 in dark and light, and at
420 (narrow) in both, go to testbed/ui-judge/d1121-stall-remedies/<HHMMSS>/. Exits 1 if any check
failed.

    py -3.11 scripts/drive/d1121_stall_remedies_browser.py
"""

import os
import pathlib
import re
import secrets
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1029_build_plan_in_spec as d  # noqa: E402
from uiharness import Judge  # noqa: E402

d.TMP = d.TMP.parent.parent / "drive1121-stall-remedies" / d.STAMP
d.PORT = int(os.environ.get("AW_DRIVE_PORT") or 8041)
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.KEY = "aw_live_" + secrets.token_hex(16)
d.DB = d.TMP / "agentweave.db"

HAIKU = "claude-haiku-5-5"
DOC = "spec/changes/two-greetings/spec.json"
DEV, QA, QA2 = "Developer", "QA", "QA2"
YEARLY = "0 0 1 1 *"
FIRINGS = 8
WIDTHS = ((1440, 940), (900, 900), (420, 860))
MODES = ("dark", "light")
IDS = re.compile(r"\b(task|conv)-[0-9a-f]{6,}\b")
CHECKS = ("stalled-build-header-and-card", "stall-remedy-controls-work", "stall-notice-sentence-case")
baseline = {}


def covered(key, reached, ok=False, detail=""):
    baseline[key] = {"reached": bool(reached), "passed": bool(reached and ok), "detail": detail}
    d.check(key if reached else f"{key} (not reached)", bool(reached and ok), detail)


def description(name):
    return (
        f"Create {name}.txt at the repository root holding the single line `{name}`, then "
        f"`git add {name}.txt` and `git commit -m {name}`. Call record_evidence for requirement "
        f"`{name}` (document {DOC}) with this task's id, command `cat {name}.txt`, its output and "
        "covers `full`. Then move this task to completed and end your turn.\n"
        f"Reviewer: run `cat {name}.txt`; where it reads `{name}`, accept the evidence with your "
        "own reproduction at the current commit and approve the task."
    )


def payload():
    names = ("hello", "goodbye")
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Two greetings",
        "summary": "The repository says hello and goodbye.", "problem": "It says neither.",
        "scope": {"in_scope": ["hello.txt", "goodbye.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": n, "modal": "MUST",
                          "statement": f"The repository MUST hold {n}.txt reading {n}."}
                         for n in names],
        "acceptance_criteria": [{
            "key": f"says-{n}", "requirement": n, "given": "the repository",
            "when": f"{n}.txt is read", "then": f"it reads {n}",
            "how_to_check": f"cat {n}.txt", "checked_by": "agent"} for n in names],
        "tasks": [{"key": n, "title": f"Add {n}.txt", "description": description(n),
                   "requirements": [n], "files": [f"{n}.txt"],
                   "builder": DEV, "checker": QA} for n in names],
        "delivery": {"mode": "flow", "agent": DEV, "checker": QA,
                     "stop_when_queue_empties": True, "cron": YEARLY,
                     "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def open_stalls(task_id):
    return d.ro("select id, reason from stalls where cause = 'review_unstaffed' and task_id = ? "
                "and ended_at is null", (task_id,))


def setup(state):
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"d1121s-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state.update(pid=pid, base=base)
    d.api("PATCH", base, {"main_branch": "main"})
    code, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    d.check("setup: a Haiku runner", code in (200, 201), f"{code} {runner}", fatal=True)
    for name in (DEV, QA, QA2):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    quoted = urllib.parse.quote(DOC)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": "Two greetings", "kind": "change-spec", "path": DOC})
    d.check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    d.check("setup: the document is saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    d.as_agent(pid, QA2, "POST", "/spec/documents/confirm-criteria", {
        "path": DOC, "confirmations": [{"criterion": c, "kind": "new"}
                                       for c in ("says-hello", "says-goodbye")]})
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": read.get("content_version")})
    d.check("setup: the document is approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                      {"driver": "flow", "level": "reviewed", "builder": DEV, "checker": QA,
                       "landing": "main"})
    d.check("setup: the document is built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    state["build"] = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    # The checker loses its runner (unstaffed-names-missing-runner).
    code, out = d.api("PATCH", f"{base}/agents/{QA}", {"runner_id": None})
    d.check("setup: QA's runner is unbound", code == 200, f"{code} {str(out)[:300]}", fatal=True)
    rows = d.ro("select t.id, t.readable_id, t.spec_task_key, t.loop_id from tasks t join "
                "spec_documents s on t.spec_document_id = s.id where s.project_id = ? and "
                "s.path = ? order by t.spec_task_key desc", (pid, DOC))
    d.check("setup: both tasks materialised", len(rows) == 2, f"{rows}", fatal=True)
    state["tasks"] = {key: (tid, ref) for tid, ref, key, _ in rows}
    job = d.ro("select job_id from loops where id = ?", (rows[0][3],))[0][0]
    print(f"project {pid} root {root}\n  tasks {state['tasks']} job {job}", flush=True)
    for _ in range(FIRINGS):
        d.fire(base, job)
        d.wait_idle(pid)
        stalled = {key: open_stalls(tid) for key, (tid, _) in state["tasks"].items()}
        statuses = {key: d.ro("select status from tasks where id = ?", (tid,))[0][0]
                    for key, (tid, _) in state["tasks"].items()}
        print(f"  after firing: {statuses}; open review stalls {stalled}", flush=True)
        if all(stalled.values()):
            break
    reasons = [r for (tid, _) in state["tasks"].values() for _, r in open_stalls(tid)]
    d.check("setup: each task has an open review_unstaffed stall naming QA's missing runner",
            len(reasons) >= 2 and all("QA" in r and "no runner" in r for r in reasons),
            f"{reasons}", fatal=True)


def drive(state):
    setup(state)
    pid, build = state["pid"], state["build"]
    (t1, ref1), (t2, ref2) = state["tasks"]["hello"], state["tasks"]["goodbye"]
    build_q = f"tab=spec&view=build&focus={build}"
    with Judge("d1121-stall-remedies", hub=d.HUB, key=d.KEY) as judge:
        def at(query, width=1440, height=940, mode="dark"):
            page = judge.page(pid, mode=mode, width=width, height=height, query=query)
            # The app holds an event stream open, so the network never idles: each step waits for
            # the element it reads instead.
            page.wait_for_load_state("load")
            return page

        # FR-7 and FR-9 on the build page.
        page = at(build_q)
        state_el = page.get_by_test_id("build-state")
        state_el.wait_for(timeout=20000)
        header = page.locator("header.aw-bv-header")
        page.get_by_role("region", name=f"Stalled: {ref1}").wait_for(timeout=20000)
        build_ok = (state_el.inner_text().strip() == "Stalled"
                    and state_el.locator("svg").count() == 1
                    and "Running" not in header.inner_text())
        notices = [page.get_by_role("region", name=f"Stalled: {r}") for r in (ref1, ref2)]
        notice_texts = [n.locator(".aw-stall-notice-text").inner_text() for n in notices]
        build_controls = all(
            n.get_by_role("button", name=f"Name a different checker for {r}").count() == 1
            and n.get_by_role("button", name=f"Review {r} yourself").count() == 1
            for n, r in zip(notices, (ref1, ref2)))
        page.context.close()

        # FR-7 on the board card.
        page = at("tab=tasks")
        card = page.locator(f"article[data-task-id='{t1}']")
        card.wait_for(timeout=20000)
        stage = card.get_by_test_id(f"task-stage-{t1}")
        page.wait_for_function(
            "id => document.querySelector(`article[data-task-id='${id}']`)?.dataset.stalled === 'true'",
            arg=t1, timeout=20000)
        stage_text = stage.inner_text()
        card_ok = ("Stalled" in stage_text and stage.locator("svg").count() >= 1
                   and "Ready for review" not in stage_text and "Running" not in stage_text)
        card_controls = (card.get_by_role("button", name=f"Name a different checker for {ref1}").count() == 1
                         and card.get_by_role("button", name=f"Review {ref1} yourself").count() == 1)
        page.context.close()
        covered("stalled-build-header-and-card", True, build_ok and card_ok,
                f"header state {build_ok}; card stage '{stage_text.strip()}' -> {card_ok}")

        # The Overview notice.
        page = at("tab=overview")
        rows = page.locator("li", has_text="Nobody can review a task")
        rows.first.wait_for(timeout=20000)
        # The controls are named for the task once the task list has answered.
        page.get_by_role("button", name=f"Review {ref2} yourself").wait_for(timeout=20000)
        overview_controls = all(
            page.get_by_role("button", name=name).count() == 1
            for r in (ref1, ref2)
            for name in (f"Name a different checker for {r}", f"Review {r} yourself"))
        overview_texts = [rows.nth(i).locator(".aw-ov-need-detail").inner_text()
                          for i in range(rows.count())]
        page.context.close()

        shown = notice_texts + overview_texts
        covered("stall-notice-sentence-case", True,
                bool(shown) and all(t[:1].isupper() and not IDS.search(t) and "QA" in t
                                    for t in shown),
                f"notices shown: {shown}")

        # Screens, before anything is clicked.
        for name, query in (("build", build_q), ("board", "tab=tasks"), ("overview", "tab=overview")):
            for width, height in WIDTHS:
                for mode in MODES:
                    page = at(query, width, height, mode)
                    page.wait_for_timeout(3000)
                    judge.shot(page, f"{name}_{width}_{mode}", full_page=True)
                    page.context.close()

        # FR-8, first run: 'Name a different checker' on T1's card.
        page = at("tab=tasks")
        card = page.locator(f"article[data-task-id='{t1}']")
        card.get_by_role("button", name=f"Name a different checker for {ref1}").wait_for(timeout=20000)
        before = page.url
        card.get_by_role("button", name=f"Name a different checker for {ref1}").click()
        card.get_by_role("button", name=f"Make {QA2} the checker of {ref1}").click()
        # The Hub's answer is said beside the controls and in a toast; the stall then ends, and
        # the card leaves Stalled for its stage with the controls.
        said = page.locator(".aw-toast-title", has_text=f"{QA2} checks {ref1}")
        said.wait_for(timeout=30000)
        said_text = said.locator("xpath=..").inner_text().replace(chr(10), " ")
        page.wait_for_function(
            "id => document.querySelector(`article[data-task-id='${id}']`)?.dataset.stalled !== 'true'",
            arg=t1, timeout=30000)
        judge.shot(page, "board_named_checker", full_page=True)
        stayed = page.url == before
        page.context.close()
        ended = d.poll(lambda: not open_stalls(t1), 20)
        queued = d.ro("select id, state from inbound_queue_entries where review_task_id = ? and "
                      "agent = ?", (t1, QA2))
        named = d.ro("select people from builds where id = ?", (build,))

        # FR-8, the other run: 'Review it yourself' on the build page, for T2.
        page = at(build_q)
        notice = page.get_by_role("region", name=f"Stalled: {ref2}")
        notice.wait_for(timeout=20000)
        before2 = page.url
        notice.get_by_role("button", name=f"Review {ref2} yourself").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for(timeout=20000)
        land = dialog.get_by_test_id(f"task-land-{t2}").count() == 1
        judge.shot(page, "build_review_yourself", full_page=False)
        stayed2 = page.url == before2
        page.context.close()

        covered("stall-remedy-controls-work", True,
                build_controls and card_controls and overview_controls and ended and bool(queued)
                and land and stayed and stayed2,
                f"controls: build {build_controls}, card {card_controls}, overview "
                f"{overview_controls}; named QA2: said '{said_text}', T1's stall ended {ended}, "
                f"QA2 review entries {queued}, build people {str(named)[:300]}, address kept "
                f"{stayed}; review yourself: drawer with Land it {land}, address kept {stayed2}")
        if judge.errors:
            print(f"  page errors: {judge.errors[:5]}")


def tidy(state):
    base, build = state.get("base"), state.get("build")
    if base and build:
        code, _ = d.api("POST", f"{base}/project/builds/{build}/stop")
        print(f"stopped build {build}: {code}")


def main():
    d.TMP.mkdir(parents=True, exist_ok=True)
    if d.api("GET", "/projects")[0] != 0:
        sys.exit(f"something already answers on :{d.PORT}; choose another AW_DRIVE_PORT")
    proc = d.start_hub()
    print(f"Hub {d.HUB} database {d.DB}", flush=True)
    state = {}
    started = time.time()
    try:
        drive(state)
    except d.Stop:
        pass
    finally:
        try:
            tidy(state)
        finally:
            d.stop_hub(proc)
    print(f"\nper-check result ({int(time.time() - started)}s):")
    for key in CHECKS:
        row = baseline.get(key)
        if row is None:
            print(f"check {key}: reached=no -- setup stopped before it")
            continue
        print(f"check {key}: reached={'yes' if row['reached'] else 'no'} "
              f"passed={'yes' if row['passed'] else 'no'} -- {row['detail'][:700]}")
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
