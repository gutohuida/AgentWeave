"""Drive for TPBCD-5 of `a-two-profile-build-cannot-deadlock-and-a-stall-says-so`, 2026-11-21.

`d1121_f1199_two_profile_flow.py`'s two-profile flow (Developer builds, QA's message thread completes
the task and records its evidence), with one change: the **first** QA review turn of the task ends
without a verdict. It asks whether the paths TPBCD-2 did not touch -- the wedge predicate
`assignee_produced_the_work`, `run_divergence`'s restaff exclusion and `task_is_claimable_by`,
all by agent name -- let the flow carry the review on into another QA thread, or refuse every QA
thread because one QA thread authored the work.

The reviewer is told to tell first from later turns by the task's notes: a review turn that finds no
`SEEN` in them writes `SEEN` and ends with no verdict; one that finds it approves.

Setup (fatal): a QA thread authored the task outside a review; a QA review thread then ended without
a verdict.

  W1  after the silent review, another review of the task is queued for QA into a lineage that is
      neither an authoring one nor the silent review's
  W2  that thread gives the task a verdict
  W3  no `review_unstaffed` stall is opened for the task

Hub: as the base drive (AW_HUB/AW_KEY/AW_DB, else its own on AW_DRIVE_PORT, default 8033).

    py -3.11 scripts/drive/d1121_tpbcd5_silent_review.py
"""

import os
import sys
import time

import d1121_f1199_two_profile_flow as base

d = base.d
d.TMP = d.TMP.parent.parent / "drive1121-tpbcd5-silent-review" / d.STAMP
if base.OWN_HUB:
    d.DB = d.TMP / "agentweave.db"
QA = base.QA
CHECKS = ("W1", "W2", "W3")
FIRINGS = 10

base.DESCRIPTION = base.DESCRIPTION.replace(
    "- Reviewer (a review turn of this task): run `cat hello.txt`; where it reads `hello`, accept "
    "the evidence with your own reproduction at the current commit and approve the task.",
    "- Reviewer (a review turn of this task): first call get_task on this task and read its "
    "`notes`. If they do NOT contain the word SEEN: call update_task on this task with notes "
    "`SEEN` and NO status, record nothing, decide nothing, send no message, and end your turn -- "
    "this review deliberately gives no verdict. If the notes DO contain SEEN: run `cat "
    "hello.txt`; where it reads `hello`, accept the evidence with your own reproduction at the "
    "current commit and approve the task.",
)
assert "SEEN" in base.DESCRIPTION

# AUTHOR=developer: the control case -- Developer builds, records the evidence and completes the
# task itself, so no QA thread authored it, and only the silent review is left to exclude anybody.
DEVELOPER_AUTHORS = os.environ.get("AUTHOR") == "developer"
if DEVELOPER_AUTHORS:
    start = base.DESCRIPTION.index("- Builder (Developer):")
    end = base.DESCRIPTION.index("- Reviewer (a review turn")
    base.DESCRIPTION = (
        base.DESCRIPTION[:start]
        + "- Builder (Developer): create hello.txt holding `hello`, then `git add hello.txt` and "
        "`git commit -m hello`, then call record_evidence for requirement `hello` (document "
        f"{base.DOC}) with this task's id, command `cat hello.txt`, its output and covers `full`, "
        "then move this task to completed. Send no message to QA.\n"
        + base.DESCRIPTION[end:]
    )
    _check = d.check

    def check(name, ok, detail="", fatal=False):
        # The base drive's precondition is the opposite of this case's.
        if name.startswith("setup: a QA thread completed the task"):
            return _check(name + " (control: expected none)", not ok, detail)
        return _check(name, ok, detail, fatal)

    d.check = check

baseline = {}


def covered(key, reached, ok=False, detail=""):
    baseline[key] = {"reached": bool(reached), "passed": bool(reached and ok), "detail": detail}
    name = f"silent-review-restaffed {key}"
    d.check(name if reached else f"{name} (not reached)", bool(reached and ok), detail)


def verdict_runs():
    return {r for (r,) in d.ro("select run_id from task_transitions where to_status in "
                               "('approved', 'revision_needed', 'rejected') and run_id is not null")}


def _setup_and_fire(state):
    """Runs the base drive's setup by calling it with its checks replaced, then reads the result."""
    real_covered = base.covered
    base.covered = lambda *a, **k: None  # the base drive's R1/V1/S1/G1 are not this drive's checks
    real_firings = base.FIRINGS
    base.FIRINGS = FIRINGS
    try:
        base.drive(state)
    finally:
        base.covered = real_covered
        base.FIRINGS = real_firings
    task = state.get("task")
    if task is None:
        rows = d.ro("select t.id from tasks t join spec_documents s on t.spec_document_id = s.id "
                    "where s.path = ? order by t.created_at desc limit 1", (base.DOC,))
        task = rows[0][0]
    pid = d.ro("select project_id from tasks where id = ?", (task,))[0][0]
    job = d.ro("select l.job_id from loops l join tasks t on t.loop_id = l.id where t.id = ?",
               (task,))[0][0]
    # Keep firing until a verdict or a review_unstaffed stall settles it.
    for _ in range(FIRINGS):
        status = d.ro("select status from tasks where id = ?", (task,))[0][0]
        if status in base.VERDICTS or base.unstaffed(task):
            break
        d.fire(state["base"], job)
        d.wait_idle(pid)
        status = d.ro("select status from tasks where id = ?", (task,))[0][0]
        print(f"  after firing: task {status}; review_unstaffed {base.unstaffed(task)}", flush=True)
    evaluate(task)


def evaluate(task):
    facts = base.authoring(task)
    authored = {base.lineage_of_run(run) for run in facts}
    entries = base.review_entries(task)
    verdicts = verdict_runs()
    silent = [e for e in entries if e[3] and e[3] not in verdicts]
    d.check("setup: a QA review thread ended without a verdict", bool(silent),
            f"QA review entries (id, state, lineage, run): {entries}", fatal=True)
    first_silent = entries.index(silent[0])
    silent_lineage = silent[0][2]
    later = [e for e in entries[first_silent + 1:]
             if e[2] is not None and e[2] not in authored and e[2] != silent_lineage]
    covered("W1", True, bool(later),
            f"entries {entries}; authoring lineages {sorted(map(str, authored))}; silent "
            f"lineage {silent_lineage}")
    rows = d.ro("select to_status, run_id, actor_agent from task_transitions where task_id = ? "
                "and to_status in ('approved', 'revision_needed', 'rejected') order by sequence",
                (task,))
    later_lineages = {e[2] for e in later}
    by_later = [v for v in rows if v[2] == QA and v[1]
                and base.lineage_of_run(v[1]) in later_lineages]
    covered("W2", bool(later), bool(by_later), f"verdicts {rows}; by the later thread {by_later}")
    stalls = base.unstaffed(task)
    other = d.ro("select id, cause, reason from stalls where task_id = ?", (task,))
    covered("W3", True, not stalls, f"review_unstaffed {stalls}; every stall of the task {other}")


def main():
    d.TMP.mkdir(parents=True, exist_ok=True)
    proc = None
    if base.OWN_HUB:
        if d.api("GET", "/projects")[0] != 0:
            sys.exit(f"something already answers on :{d.PORT}")
        proc = d.start_hub()
    print(f"Hub {d.HUB} database {d.DB}", flush=True)
    state = {}
    started = time.time()
    try:
        _setup_and_fire(state)
    except d.Stop:
        pass
    finally:
        try:
            base.tidy(state)
        finally:
            d.stop_hub(proc)
    print(f"\nper-check ({int(time.time() - started)}s):")
    for key in CHECKS:
        row = baseline.get(key)
        if row is None:
            print(f"check {key}: reached=no -- setup stopped before it")
            continue
        print(f"check {key}: reached={'yes' if row['reached'] else 'no'} "
              f"passed={'yes' if row['passed'] else 'no'} -- {row['detail'][:900]}")
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed 2026-11-21 on agentweave/task/task-6c5053bba72b (TPBCD-2's thread exclusion merged in,
# the three name-based paths untouched), each on its own new Hub:
#   run 161537 (:8041, 85 s), exit 0. QA's message run-fb87fb69412b (lineage conv-3341eaaeb6ca)
#   completed the task and recorded evidence; review thread conv-5449db34dea7 wrote SEEN and gave no
#   verdict (div-be2030a60246: policy review, surfaced -- QA is the declared checker); the next
#   firing's wedge arm (`assignee_produced_the_work`, QA by name) queued conv-8d7f4f6e2d84, which
#   approved. W1-W3 pass, no stall. By thread that arm would not fire: so the paths stay by name.
#   AUTHOR=developer, run 162727 (:8042, 71 s), exit 1. Developer authored everything; review thread
#   conv-b9d6d8379bf4 went silent and stall-60f99ea1235b (review_unstaffed: "QA is named ... and is
#   not reviewing it ... Ask QA again") opened. The designed declared-reviewer surfacing
#   (run_divergence D4), not exclusion: FR-3 does not cover it.
