---
name: check-build
description: Check GitHub Actions CI build status for AgentWeave (publish.yml → PyPI, hub-image.yml → Docker, ci.yml → tests/lint/type-check). Usable standalone with /loop or callable from other skills. Accepts optional tag filters (e.g. "v0.10.0 hub-v0.4.0"). ci.yml is always shown from the latest master push regardless of tag filter.
---

Check the status of GitHub Actions CI builds for the AgentWeave repository.

## Callable interface (for other skills)

Other skills may invoke this skill via the Skill tool:
```
skill: "check-build", args: "v<cli_version> hub-v<hub_version>"
```
Returns the status table + one of: `BUILD_COMPLETE_SUCCESS`, `BUILD_COMPLETE_FAILURE`, or `BUILD_RUNNING`.

---

## Step 1 — Fetch all workflow runs

```bash
curl -s -o /tmp/aw_gh_runs.json \
  "https://api.github.com/repos/gutohuida/AgentWeave/actions/runs?per_page=40" \
  -H "Accept: application/vnd.github+json"
```

---

## Step 2 — Parse and display

Run this Python script (substitute $ARGUMENTS literally):

```python
import json, urllib.request
from datetime import datetime, timezone

raw_args = "$ARGUMENTS".strip()
args = set(raw_args.split()) if raw_args else set()

data = json.load(open("/tmp/aw_gh_runs.json"))
runs = data.get("workflow_runs", [])

# --- Build per-workflow "seen" maps ---
# For publish.yml and hub-image.yml: filter by tag args if provided
# For ci.yml: ALWAYS use the latest master push run (it triggers on branch push, not tags)
tag_seen = {}   # publish.yml, hub-image.yml
ci_run   = None

for r in runs:
    wf     = r.get("path", "").split("/")[-1]
    title  = r.get("display_title", "") or ""
    branch = r.get("head_branch", "") or ""

    if wf == "ci.yml":
        if ci_run is None and branch == "master":
            ci_run = r
        continue

    matches = (not args) or any(a in title or a in branch for a in args)
    if matches and wf not in tag_seen:
        tag_seen[wf] = r

# Fallback for tag workflows if nothing matched
if not tag_seen:
    for r in runs:
        wf = r.get("path", "").split("/")[-1]
        if wf != "ci.yml" and wf not in tag_seen:
            tag_seen[wf] = r

tag_seen["ci.yml"] = ci_run  # may be None

# --- Print table ---
tracked = ["publish.yml", "hub-image.yml", "ci.yml"]
now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
print(f"GitHub Actions — AgentWeave build status (checked at {now})\n")

all_done   = True
any_failed = False
failed_runs = []

for wf in tracked:
    r = tag_seen.get(wf)
    if not r:
        print(f"  {wf:<22} ⬜ no runs found")
        continue
    status     = r["status"]
    conclusion = r["conclusion"]
    ref        = r.get("head_branch") or (r.get("head_commit") or {}).get("id", "")[:7]
    url        = r["html_url"]
    run_id     = r["id"]
    if status != "completed":
        symbol = "🔄 running "; all_done = False
    elif conclusion == "success":
        symbol = "✅ success "
    elif conclusion in ("failure", "cancelled"):
        symbol = "❌ failure "; any_failed = True; failed_runs.append((wf, run_id, url))
    else:
        symbol = "⏭ skipped "
    print(f"  {wf:<22} {symbol}  {ref:<18} {url}")

# --- For any failed run, fetch job-level details ---
if failed_runs:
    print()
    print("── Failure details ──────────────────────────────────────")
    for wf, run_id, url in failed_runs:
        jobs_url = f"https://api.github.com/repos/gutohuida/AgentWeave/actions/runs/{run_id}/jobs"
        req = urllib.request.Request(jobs_url, headers={"Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                jobs = json.load(resp).get("jobs", [])
        except Exception as e:
            print(f"  [{wf}] could not fetch jobs: {e}")
            continue
        for job in jobs:
            if job.get("conclusion") in ("failure", "cancelled"):
                jname = job["name"]
                jurl  = job["html_url"]
                print(f"\n  [{wf}] job failed: {jname}")
                print(f"  {jurl}")
                for step in job.get("steps", []):
                    if step.get("conclusion") in ("failure",):
                        print(f"    step: {step['name']}  →  {step['conclusion']}")

print()
if all_done:
    print("BUILD_COMPLETE_SUCCESS" if not any_failed else "BUILD_COMPLETE_FAILURE")
else:
    print("BUILD_RUNNING")
```

Save the script to `/tmp/aw_check.py` and run it:
```bash
python3 /tmp/aw_check.py
```

---

## Step 3 — Interpret and report

- **`BUILD_COMPLETE_SUCCESS`** — all workflows passed. Print: "All builds passed."
  If called from a loop, tell the user they can stop it.

- **`BUILD_COMPLETE_FAILURE`** — all done, at least one failed.
  The failure details section above names the exact job and step.
  Print: "BUILD FAILED — see details above."
  If called from a loop, tell the user to stop it and fix the reported issue.

- **`BUILD_RUNNING`** — at least one workflow still in progress.
  Print: "Still running — will check again on next interval."
