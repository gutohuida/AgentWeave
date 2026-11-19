"""Acceptance drive for `a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`, 2026-11-19.

The change's first task (spdoc-31be9e283cb2, task `acceptance-drive`), written before the build. It
covers criterion `drive-two-models-one-build` (FR-7, with FR-12's run record) on a scratch project
with real turns: a Builder profile whose pool holds Claude Haiku (default) and Claude Sonnet, a
Haiku-bound Checker, and an approved two-task document whose tasks are independent. `t-sonnet`
recommends the Sonnet entry for its builder; `t-plain` recommends nothing. The operator builds it as
a flow at Reviewed, landing on main, leaving the prefilled choices: the drive sends exactly the
per-task entries the document's recommended build reads back, as the Build dialog does. The drive
then fires the flow until both tasks are approved and checks:

  P1  the agents API shows Builder's pool: Haiku and Sonnet, Haiku the default
  P2  the document's recommended build names the Sonnet entry for t-sonnet's builder, none for
      t-plain's
  S1  every builder run of t-sonnet records the Sonnet runner and model, in the runs read and in its
      trace, and t-sonnet landed (approved, sonnet.txt on main)
  S2  every builder run of t-plain records the Haiku runner and model, in the runs read and in its
      trace, and t-plain landed (approved, plain.txt on main)
  M1  the model record credits t-sonnet to a Sonnet model and t-plain to a Haiku model

No check is a guard. Landing and the Haiku task's model are what today's code already does, so they
are checked inside S1/S2 beside the recorded runner, which today's run row does not carry (the
design's rule: unchanged behaviour is checked inside a check that also needs the new pool).

The contract the drive assumes, for the builders of `pool-model` and `launch-path` to meet or to
adjust here in one place (`set_pool`, `run_reads`, `trace_names`):
  - the pool is set by PATCH /agents/{name} {"pool": [{"runner_id", "effort", "default"}]} and read
    back as `pool` on the agent's row in GET /agents, entries shaped as hub/ui/src/api/agentPool.ts;
  - a spec task recommends its builder's entry as `builder_entry: {"runner_id", "effort"}`, read
    back as `recommended_build.task_builder_entries[<key>]`;
  - a run's read (GET /runs/{run_id}, else the agent timeline's run facts) carries the runner id
    and the model it launched with, and the run's trace root names both in its attributes.

Each check is reported as reached or not, and as passed or failed at its own assertion, in the
per-check baseline printed at the end (`check <key>: reached=<yes|no> failed_at_assertion=<yes|no>
-- <detail>`). A check whose setup did not happen reads `not reached`, never `failed`.

Scratch Hub: the trial Hub on AW_DRIVE_PORT (default 8010), reused when one answers there and
otherwise started from this checkout's `hub/` on AW_DRIVE_DB (default: the trial profile's
database). Never :8000. The flow's cron fires once a year; the drive fires it itself. About four
turns (two builds, two reviews; one of them Sonnet when the pool works), 10-25 minutes.

    py -3.11 scripts/drive/d1119_profile_pools.py
"""

import json
import subprocess
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent.parent / "drive1119-profile-pools" / d.STAMP
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
DOC = "spec/changes/two-models/spec.json"
BUILDER, CHECKER = "Builder", "Checker"
T_SONNET, T_PLAIN = "t-sonnet", "t-plain"
FILES = {T_SONNET: "sonnet.txt", T_PLAIN: "plain.txt"}
YEARLY = "0 0 1 1 *"
FIRINGS = 6
CHECKS = ("P1", "P2", "S1", "S2", "M1")

# The per-check baseline: key -> {"criterion", "reached", "passed", "detail"}.
baseline = {}


def covered(key, reached, ok=False, detail=""):
    """One covered check. Not reached is reported as such and never counted as its assertion."""
    baseline[key] = {"reached": bool(reached), "passed": bool(reached and ok), "detail": detail}
    name = f"drive-two-models-one-build {key}"
    d.check(name if reached else f"{name} (not reached)", bool(reached and ok), detail)


def payload(sonnet_runner_id, with_entry=True):
    def task(key, words):
        out = {
            "key": key, "title": f"Add {FILES[key]}", "requirements": [key],
            "files": [FILES[key]], "builder": BUILDER, "checker": CHECKER,
            "description": (
                f"Create the file {FILES[key]} at the repository root holding the single line "
                f"`{words}`. Commit it: `git add {FILES[key]}` then `git commit -m {key}`. Then "
                f"call record_evidence for the requirement this task serves (document {DOC}) with "
                f"command `cat {FILES[key]}`, its output, and covers `full`. Then move this task "
                "to completed. Change nothing else.\n\nTo the reviewer: run "
                f"`cat {FILES[key]}`; where it reads `{words}`, accept the evidence with your own "
                "reproduction at the current commit and approve."),
        }
        return out

    sonnet = task(T_SONNET, "sonnet")
    if with_entry:
        sonnet["builder_entry"] = {"runner_id": sonnet_runner_id, "effort": None}
        sonnet["builder_entry_reason"] = "The drive: this task is built on Sonnet."
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Two models",
        "summary": "Two files.", "problem": "There are no files.",
        "scope": {"in_scope": list(FILES.values()), "non_goals": ["Anything else"]},
        "requirements": [
            {"key": key, "modal": "MUST", "statement": f"The repository MUST hold {name}."}
            for key, name in FILES.items()],
        "acceptance_criteria": [{
            "key": f"{key}-exists", "requirement": key, "given": "the repository",
            "when": f"{name} is read", "then": "it holds one line", "how_to_check": f"cat {name}",
            "checked_by": "agent"} for key, name in FILES.items()],
        "tasks": [sonnet, task(T_PLAIN, "plain")],
        "delivery": {"mode": "flow", "agent": BUILDER, "checker": CHECKER,
                     "stop_when_queue_empties": True, "cron": YEARLY,
                     "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def agent_row(base, name):
    code, out = d.api("GET", f"{base}/agents")
    rows = out if isinstance(out, list) else (out or {}).get("agents") or []
    return next((r for r in rows if isinstance(r, dict) and r.get("name") == name), None)


def set_pool(base, name, entries):
    """The pool, through the agents API (contract assumed above)."""
    return d.api("PATCH", f"{base}/agents/{name}", {"pool": entries})


def builder_runs(task_id):
    return [r for (r,) in d.ro("select id from runs where task_id=? and agent=? "
                               "order by started_at", (task_id, BUILDER))]


def run_reads(base, run_id):
    """What the runs API says of one run: GET /runs/{id}, else the agent timeline's run facts."""
    code, out = d.api("GET", f"{base}/runs/{run_id}")
    if code == 200 and isinstance(out, dict):
        return "runs", out
    _, timeline = d.api("GET", f"{base}/agents/{BUILDER}/timeline")
    facts = ((timeline or {}).get("runs") or {}).get(run_id) if isinstance(timeline, dict) else None
    return f"timeline (GET /runs/{{id}} answered {code})", facts


def names(value, runner_id, model):
    """The read names the runner record and the model it launched with, as values of its own."""
    flat = json.dumps(value or {})
    return f'"{runner_id}"' in flat and f'"{model}"' in flat


def trace_names(base, run_id, runner_id, model):
    code, trace = d.api("GET", f"{base}/traces/by-run/{run_id}")
    attributes = ((trace or {}).get("root") or {}).get("attributes") if code == 200 else None
    return names(attributes, runner_id, model), code, attributes


def run_check(base, key, task_id, runner_id, model, root):
    runs = builder_runs(task_id)
    if not runs:
        return False, f"{key}: no builder run"
    seen, ok = [], True
    for run in runs:
        source, read = run_reads(base, run)
        in_runs = names(read, runner_id, model)
        in_trace, code, attrs = trace_names(base, run, runner_id, model)
        ok = ok and in_runs and in_trace
        recorded = {k: v for k, v in (attrs or {}).items() if "model" in k or "runner" in k}
        seen.append(f"{run}: {source} names runner+model {in_runs} "
                    f"(read {json.dumps(read)[:240]}); trace {code} names them {in_trace} "
                    f"(model/runner attributes {recorded})")
    status = d.ro("select status from tasks where id=?", (task_id,))[0][0]
    on_main = subprocess.run(["git", "show", f"main:{FILES[key]}"], cwd=root,
                             capture_output=True, text=True).returncode == 0
    landed = status == "approved" and on_main
    return ok and landed, (f"want runner {runner_id} model {model}; task {status}, "
                           f"{FILES[key]} on main {on_main}; " + " | ".join(seen))


def credited(record, task_id):
    for row in (record or {}).get("models") or []:
        if any(t.get("task_id") == task_id for t in row.get("tasks") or []):
            return row.get("model")
    return None


def drive(state):
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"d1119-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state["base"] = base
    d.api("PATCH", base, {"main_branch": "main"})
    runners = {}
    for label, model in (("Haiku", HAIKU), ("Sonnet", SONNET)):
        code, out = d.api("POST", f"{base}/runners", {"name": label, "cli": "claude", "model": model})
        d.check(f"setup: a {label} runner", code in (200, 201), f"{code} {out}", fatal=True)
        runners[label] = out["id"]
    for name in (BUILDER, CHECKER):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runners["Haiku"]})
        d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    # P1: Builder's pool is Haiku (default) and Sonnet.
    code, out = set_pool(base, BUILDER, [
        {"runner_id": runners["Haiku"], "effort": None, "default": True},
        {"runner_id": runners["Sonnet"], "effort": None, "default": False}])
    pool = (agent_row(base, BUILDER) or {}).get("pool")
    got = sorted((e.get("runner_id"), bool(e.get("default"))) for e in pool or [])
    want = sorted([(runners["Haiku"], True), (runners["Sonnet"], False)])
    covered("P1", True, got == want,
            f"PATCH pool answered {code} {str(out)[:200]}; GET agents pool {pool!r}")

    # The document, saved with t-sonnet's recommendation. A save that refuses the field is saved
    # again without it, so the drive goes on to show what the runs record.
    quoted = urllib.parse.quote(DOC)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": "Two models", "kind": "change-spec", "path": DOC})
    d.check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content",
                      {"document": payload(runners["Sonnet"])})
    unread = [b for b in (out or {}).get("blocking") or [] if b.get("code") == "unknown_field"
              and "builder_entry" in str(b.get("where"))] if isinstance(out, dict) else []
    if code != 200 or unread:
        # Today's schema has no such field: it is kept, but blocks approval as unread.
        print(f"  the save with builder_entry answered {code}, blocking {unread}; saving without it")
        code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content",
                          {"document": payload(runners["Sonnet"], with_entry=False)})
    d.check("setup: the document is saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    code, out = d.as_agent(pid, CHECKER, "POST", "/spec/documents/confirm-criteria", {
        "path": DOC, "confirmations": [{"criterion": f"{key}-exists", "kind": "new"}
                                       for key in FILES]})
    d.check("setup: the criteria are confirmed", code == 200, f"{code} {str(out)[:400]}")
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": read.get("content_version")})
    d.check("setup: the document is approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)

    # P2: the recommended build carries t-sonnet's entry; Build sends it, as the dialog prefills.
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    entries = ((read or {}).get("recommended_build") or {}).get("task_builder_entries")
    prefilled = {k: v for k, v in (entries or {}).items() if v}
    covered("P2", True,
            (prefilled.get(T_SONNET) or {}).get("runner_id") == runners["Sonnet"]
            and T_PLAIN not in prefilled,
            f"recommended_build.task_builder_entries {entries!r}")
    build = {"driver": "flow", "level": "reviewed", "builder": BUILDER, "checker": CHECKER,
             "landing": "main"}
    if prefilled:
        build["task_builder_entries"] = prefilled
    code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}", build)
    d.check("setup: the document is built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    state["build"] = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    rows = d.ro("select t.id, t.spec_task_key, t.loop_id from tasks t join spec_documents s "
                "on t.spec_document_id=s.id where s.project_id=? and s.path=?", (pid, DOC))
    tasks = {key: tid for tid, key, _ in rows}
    job = d.ro("select job_id from loops where id=?", (rows[0][2],))[0][0]
    print(f"project {pid} root {root}\n  tasks {tasks} job {job}\n  runners {runners}", flush=True)

    # The flow runs both tasks through build and review.
    for _ in range(FIRINGS):
        d.fire(base, job)
        d.wait_idle(pid)
        states = dict(d.ro("select spec_task_key, status from tasks where id in (?, ?)",
                           (tasks[T_SONNET], tasks[T_PLAIN])))
        print(f"  after firing: {states}", flush=True)
        if all(s == "approved" for s in states.values()):
            break
    # Landing follows approval; give the integration a moment.
    d.poll(lambda: all(subprocess.run(["git", "show", f"main:{f}"], cwd=root,
                                      capture_output=True).returncode == 0
                       for f in FILES.values()), 120, every=5)

    built = {key: bool(builder_runs(tid)) for key, tid in tasks.items()}
    ok, detail = run_check(base, T_SONNET, tasks[T_SONNET], runners["Sonnet"], SONNET, root)
    covered("S1", built[T_SONNET], ok, detail)
    ok, detail = run_check(base, T_PLAIN, tasks[T_PLAIN], runners["Haiku"], HAIKU, root)
    covered("S2", built[T_PLAIN], ok, detail)

    code, record = d.as_agent(pid, CHECKER, "GET", "/model-record")
    sonnet_model = credited(record, tasks[T_SONNET])
    plain_model = credited(record, tasks[T_PLAIN])
    covered("M1", code == 200 and all(built.values()),
            "sonnet" in str(sonnet_model) and "haiku" in str(plain_model),
            f"model record {code}: {T_SONNET} credited to {sonnet_model}, "
            f"{T_PLAIN} credited to {plain_model}")


def tidy(state):
    base, build = state.get("base"), state.get("build")
    if base and build:
        code, _ = d.api("POST", f"{base}/project/builds/{build}/stop")
        print(f"stopped build {build}: {code}")


def main():
    proc = d.start_hub()
    state = {}
    d.TMP.mkdir(parents=True, exist_ok=True)
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
    print(f"\nper-check baseline ({int(time.time() - started)}s):")
    for key in CHECKS:
        row = baseline.get(key)
        if row is None:
            print(f"check {key}: reached=no failed_at_assertion=no -- setup stopped before it")
            continue
        failed = row["reached"] and not row["passed"]
        print(f"check {key}: reached={'yes' if row['reached'] else 'no'} "
              f"failed_at_assertion={'yes' if failed else 'no'} -- {row['detail'][:400]}")
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on pre-build code (branch agentweave/task/task-b876e0dc350b at 7bf67a5, master 11e13e2's
# line), 2026-11-19, run 100157 (artefacts drive1119-profile-pools/100157, 173 s, four Haiku turns).
# Every check is reached and fails at its own assertion:
#   P1  PATCH /agents/Builder {"pool": [...]} answered 400 "Unknown agent field(s): pool"; GET
#       agents carries no pool.
#   P2  the save kept t-sonnet's builder_entry but blocked approval on it as unknown_field, so the
#       drive saved without it; recommended_build has no task_builder_entries.
#   S1  t-sonnet was built and landed (approved, sonnet.txt on main) on Haiku: GET /runs/{id} is 404,
#       the timeline's run facts name no runner or model, and the trace root names
#       gen_ai.request.model claude-haiku-5-5 and aw.runner.cli claude, never the Sonnet runner.
#   S2  t-plain landed on Haiku, but neither the run read nor the trace names its runner record.
#   M1  the model record credits both t-sonnet and t-plain to claude-haiku-5-5.
# The first run (095850) stopped at approval on two setup rules the drive now meets: the unknown
# builder_entry field blocks approval, and criteria need an agent's confirmation.
