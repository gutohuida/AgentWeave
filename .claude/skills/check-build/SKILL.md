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

Download to a temp file then parse (avoids stdin/heredoc conflicts):

```bash
curl -s -o /tmp/aw_gh_runs.json \
  "https://api.github.com/repos/gutohuida/AgentWeave/actions/runs?per_page=30" \
  -H "Accept: application/vnd.github+json"

python3 <<'PYEOF'
import json
from datetime import datetime, timezone

# Tags to filter on (set from $ARGUMENTS — replace this list when calling)
args = set()  # e.g. {"v0.10.0", "hub-v0.4.0"} — populated below

import sys
raw_args = "$ARGUMENTS".strip()
if raw_args:
    args = set(raw_args.split())

data = json.load(open("/tmp/aw_gh_runs.json"))
runs = data.get("workflow_runs", [])

seen = {}
for r in runs:
    wf = r.get("path", "").split("/")[-1]
    title = r.get("display_title", "") or ""
    branch = r.get("head_branch", "") or ""
    if not args or any(a in title or a in branch for a in args):
        if wf not in seen:
            seen[wf] = r

# Fallback: show latest per workflow if no tag matches
if not seen:
    for r in runs:
        wf = r.get("path", "").split("/")[-1]
        if wf not in seen:
            seen[wf] = r

tracked = ["publish.yml", "hub-image.yml", "ci.yml"]
now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
print(f"GitHub Actions — AgentWeave build status (checked at {now})\n")

all_done = True
any_failed = False

for wf in tracked:
    r = seen.get(wf)
    if not r:
        print(f"  {wf:<22} ⬜ no runs found")
        continue
    status     = r["status"]
    conclusion = r["conclusion"]
    ref        = r.get("head_branch") or (r.get("head_commit") or {}).get("id", "")[:7]
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
    print("BUILD_COMPLETE_SUCCESS" if not any_failed else "BUILD_COMPLETE_FAILURE")
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

