"""Setup and API halves for the d1119 UI click-through (pool-edit-refusals, build-refuses-outside-pool).

Creates a scratch project on the trial Hub (:8010) with Haiku/Sonnet/Opus runners, a Builder whose
pool is Haiku (default) + Sonnet, and an approved document with three tasks: t-in recommends the
Sonnet entry (in the pool), t-out recommends Opus (not in the pool), t-plain recommends nothing.
Nothing is built. Writes the ids to the file named by argv[1]; the click-through reads them.

    py -3.11 scripts/drive/d1119_profile_pools_ui_setup.py <out.json>
"""
import json
import pathlib
import sys
import urllib.parse

import d1029_build_plan_in_spec as d

OPUS = "claude-opus-5-5"
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
DOC = "spec/changes/three-tasks/spec.json"


def task(key, entry=None):
    out = {"key": key, "title": f"Add {key}.txt", "requirements": [key], "files": [f"{key}.txt"],
           "builder": "Builder", "checker": "Checker", "description": f"Create {key}.txt."}
    if entry:
        out["builder_entry"] = entry
    return out


def main():
    root = pathlib.Path(sys.argv[1]).parent / "proj"
    root.mkdir(parents=True, exist_ok=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"d1119-ui-{d.STAMP}"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    r = {}
    for label, model in (("Haiku", HAIKU), ("Sonnet", SONNET), ("Opus", OPUS)):
        code, out = d.api("POST", f"{base}/runners", {"name": f"Claude {label}", "cli": "claude", "model": model})
        assert code in (200, 201), (code, out)
        r[label] = out["id"]
    for name in ("Builder", "Checker"):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": r["Haiku"]})
        assert code in (200, 201), (code, out)
    code, out = d.api("PATCH", f"{base}/agents/Builder", {"pool": [
        {"runner_id": r["Haiku"], "effort": None, "default": True},
        {"runner_id": r["Sonnet"], "effort": None, "default": False}]})
    print("pool set", code)

    def pool():
        _, rows = d.api("GET", f"{base}/agents")
        rows = rows if isinstance(rows, list) else rows.get("agents")
        return next(a for a in rows if a["name"] == "Builder")["pool"]

    before = json.dumps(pool(), sort_keys=True)
    # pool-edit-refusals: an effort the model does not offer; removing the default naming no other.
    code, out = d.api("PATCH", f"{base}/agents/Builder", {"pool": [
        {"runner_id": r["Haiku"], "effort": "bogus", "default": True},
        {"runner_id": r["Sonnet"], "effort": None, "default": False}]})
    print("REFUSAL-1 effort 'bogus' on Haiku:", code, str(out)[:300])
    assert code in (400, 422) and "bogus" in str(out), (code, out)
    code2, out2 = d.api("PATCH", f"{base}/agents/Builder", {"pool": [
        {"runner_id": r["Sonnet"], "effort": None, "default": False}]})
    print("REFUSAL-2 remove default:", code2, str(out2)[:300])
    assert code2 in (400, 422), (code2, out2)
    unchanged = json.dumps(pool(), sort_keys=True) == before
    print("pool unchanged:", unchanged)
    assert unchanged

    code, out = d.api("POST", f"{base}/project/documents", {"title": "Three", "kind": "change-spec", "path": DOC})
    assert code == 201, (code, out)
    doc = {
        "schema_version": 1, "kind": "change-spec", "title": "Three tasks", "summary": "Files.",
        "problem": "None.", "scope": {"in_scope": ["files"], "non_goals": ["else"]},
        "requirements": [{"key": k, "modal": "MUST", "statement": f"The repository MUST hold {k}.txt."}
                         for k in ("t-in", "t-out", "t-plain")],
        "acceptance_criteria": [{"key": f"{k}-exists", "requirement": k, "given": "the repo",
                                 "when": "read", "then": "it exists", "how_to_check": f"cat {k}.txt",
                                 "checked_by": "agent"} for k in ("t-in", "t-out", "t-plain")],
        "tasks": [task("t-in", {"runner_id": r["Sonnet"], "effort": None, "reason": "Sonnet is in the pool."}),
                  task("t-out", {"runner_id": r["Opus"], "effort": None, "reason": "Opus is not in the pool."}),
                  task("t-plain")],
        "delivery": {"mode": "flow", "agent": "Builder", "checker": "Checker",
                     "stop_when_queue_empties": True, "cron": "0 0 1 1 *",
                     "reasons": {"mode": "A flow runs independent tasks in parallel.",
                                "agent": "The seeded builder is the default for this build."}},
    }
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": doc})
    print("doc save", code, str(out)[:300])
    d.as_agent(pid, "Checker", "POST", "/spec/documents/confirm-criteria", {
        "path": DOC, "confirmations": [{"criterion": f"{k}-exists", "kind": "new"} for k in ("t-in", "t-out", "t-plain")]})
    q = urllib.parse.quote(DOC)
    _, read = d.api("GET", f"{base}/project/spec?path={q}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={q}&to=approved",
                      {"reason": "drive", "approve_anyway": True, "content_version": read.get("content_version")})
    print("approve", code, str(out)[:200])
    _, read = d.api("GET", f"{base}/project/spec?path={q}")
    print("recommended_build entries:", (read.get("recommended_build") or {}).get("task_builder_entries"))
    # build-refuses-outside-pool: Build names Opus for t-out; nothing may change.
    n0 = d.ro("select count(*) from tasks where spec_task_key in ('t-in','t-out','t-plain')")[0][0]
    code, out = d.api("POST", f"{base}/project/documents/build?path={q}", {
        "driver": "flow", "level": "reviewed", "builder": "Builder", "checker": "Checker", "landing": "main",
        "task_builder_entries": {"t-out": {"runner_id": r["Opus"], "effort": None}}})
    n1 = d.ro("select count(*) from tasks where spec_task_key in ('t-in','t-out','t-plain')")[0][0]
    print("BUILD-REFUSAL:", code, str(out)[:400], "| tasks before/after", n0, n1)
    pathlib.Path(sys.argv[1]).write_text(json.dumps({"pid": pid, "runners": r, "doc": DOC}), encoding="utf-8")


main()
