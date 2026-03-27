---
name: check-build
description: Check GitHub Actions CI build status for AgentWeave (publish.yml → PyPI, hub-image.yml → Docker). Usable standalone with /loop or callable from other skills. Accepts an optional tag filter (e.g. "v0.10.0" or "hub-v0.4.0 v0.10.0").
---

Check the status of GitHub Actions CI builds for the AgentWeave repository.

## Callable interface (for other skills)

Other skills may invoke this skill via the Skill tool:
```
skill: "check-build", args: "v<cli_version> hub-v<hub_version>"
```
When called this way, filter runs to only the specified tags and return the
result table + one of: `BUILD_COMPLETE_SUCCESS`, `BUILD_COMPLETE_FAILURE`, or `BUILD_RUNNING`.

---

## Step 1 — Parse arguments

$ARGUMENTS may contain one or more ref filters (e.g. `v0.10.0`, `hub-v0.4.0`).
If empty, show the latest run for each tracked workflow.

---

## Step 2 — Fetch workflow runs

```bash
curl -s "https://api.github.com/repos/gutohuida/AgentWeave/actions/runs?per_page=30" \
  -H "Accept: application/vnd.github+json" | python3 - <<'PYEOF'
import sys, json
from datetime import datetime

data = json.load(sys.stdin)
runs = data.get("workflow_runs", [])

# Track the most recent run per workflow file name
seen = {}
for r in runs:
    wf = r.get("path", "").split("/")[-1]  # e.g. "publish.yml"
    if wf not in seen:
        seen[wf] = r

tracked = ["publish.yml", "hub-image.yml", "ci.yml"]
now = datetime.utcnow().strftime("%H:%M:%S UTC")
print(f"GitHub Actions — AgentWeave build status (checked at {now})\n")

all_done = True
any_failed = False

for wf in tracked:
    r = seen.get(wf)
    if not r:
        print(f"  {wf:<22} ⬜ no runs found")
        continue
    status     = r["status"]       # queued / in_progress / completed
    conclusion = r["conclusion"]   # success / failure / cancelled / skipped / None
    ref        = r.get("head_branch") or r.get("head_commit", {}).get("id", "")[:7]
    url        = r["html_url"]
    if status != "completed":
        symbol = "🔄 running "
        all_done = False
    elif conclusion == "success":
        symbol = "✅ success "
    elif conclusion in ("failure", "cancelled"):
        symbol = "❌ failure "
        any_failed = True
    else:
        symbol = "⏭ skipped "
    print(f"  {wf:<22} {symbol}  {ref:<18} {url}")

print()
if all_done:
    if any_failed:
        print("BUILD_COMPLETE_FAILURE")
    else:
        print("BUILD_COMPLETE_SUCCESS")
else:
    print("BUILD_RUNNING")
PYEOF
```

---

## Step 3 — Interpret and report

- **`BUILD_COMPLETE_SUCCESS`** — all workflows finished successfully.
  Print: "All builds passed. You can stop the loop."

- **`BUILD_COMPLETE_FAILURE`** — all done but at least one failed.
  Print: "BUILD FAILED — check the links above for details."
  Tell the user to stop the loop.

- **`BUILD_RUNNING`** — at least one workflow still in progress.
  Print: "Still running — will check again on next interval."

---

## Tag filtering (when $ARGUMENTS is set)

If $ARGUMENTS contains specific tags (e.g. `v0.10.0 hub-v0.4.0`), add this filter
to the Python script: before populating `seen`, skip runs where
`r.get("head_branch") not in args and not any(t["name"] in args for t in r.get("tags", []))`.
Use the `head_sha` and compare against the tag's commit if needed. A simpler approach:
filter by checking if `r["display_title"]` or `r["head_branch"]` contains any of the tags.
