---
name: aw-check-ci
description: This skill should be used when the user asks to "check CI", "check if deploy passed", "check GitHub Actions", "monitor CI/CD", "check if the release passed", "check workflows", "fix CI errors", or says "/aw-check-ci". Checks GitHub Actions workflow runs, and if any have failed it diagnoses the failure, fixes the code, commits, and pushes again. Designed to be used with /loop to poll and auto-fix until all workflows pass.
disable-model-invocation: true
---

Check CI/CD status for AgentWeave GitHub Actions workflows. If anything failed, diagnose, fix, commit, and push.

## Usage

```
/aw-check-ci              — check, fix if needed, and report
/loop 2m /aw-check-ci     — poll every 2 minutes, auto-fixing until all pass
```

---

## Step 1 — Get latest commit and tags

```bash
git log -1 --format="%H %s"
git describe --tags --match "v*" --abbrev=0 2>/dev/null || echo "no-cli-tag"
git describe --tags --match "hub-v*" --abbrev=0 2>/dev/null || echo "no-hub-tag"
```

---

## Step 2 — Check workflow runs

```bash
gh run list --limit 10 --json databaseId,name,status,conclusion,headBranch,headSha,createdAt,url \
  | jq -r '.[] | [.name, .status, (.conclusion // "pending"), .headBranch, .createdAt, .url] | @tsv'
```

For each run:
- `status`: `queued` | `in_progress` | `completed`
- `conclusion`: `success` | `failure` | `cancelled` | `skipped` | `null` (still running)

---

## Step 3 — Check specific workflows by name

```bash
gh run list --workflow=ci.yml --limit 3 --json databaseId,name,status,conclusion,headSha,url
gh run list --workflow=publish.yml --limit 3 --json databaseId,name,status,conclusion,headSha,url
gh run list --workflow=hub-image.yml --limit 3 --json databaseId,name,status,conclusion,headSha,url
```

---

## Step 4 — Display status table

| Workflow | Status | Conclusion | Branch/Tag | Time |
|----------|--------|------------|------------|------|
| CI | ... | ... | master | ... |
| Publish (PyPI) | ... | ... | v... | ... |
| Hub Docker | ... | ... | hub-v... | ... |

---

## Step 5 — Handle each outcome

### All green
Report: "All CI/CD workflows passed. Deploy successful."
- PyPI: `pip install agentweave-ai==<version>` available within ~2 minutes
- Docker: `ghcr.io/gutohuida/agentweave-hub:<version>` available
- **Stop here** — do not loop further if invoked via `/loop`.

### Still running (queued or in_progress)
Report: "Workflows in progress — waiting for results."
- Do not attempt any fixes.
- If using `/loop`, the next iteration will check again.

### Failure detected — proceed to Step 6

---

## Step 6 — Diagnose the failure

Fetch full logs for every failed run:

```bash
gh run view <databaseId> --log-failed 2>/dev/null | tail -100
```

Also run the failing checks locally to get the exact error:

**If CI / lint failed:**
```bash
ruff check src/
black --check src/
mypy src/
```

**If CI / tests failed:**
```bash
python -m pytest tests/ -v --tb=long 2>&1 | tail -60
```

**If Hub tests failed:**
```bash
cd hub && python -m pytest tests/ -v --tb=long 2>&1 | tail -60
cd ..
```

**If publish (PyPI) failed:**
```bash
python -m build
```

**If Hub Docker build failed:**
Read the Docker build log from `gh run view --log-failed` — look for the failing `RUN` step.

Identify the root cause before making any changes.

---

## Step 7 — Fix the problem

Apply the minimal fix needed. Common cases:

**Ruff lint error** → fix the flagged lines in `src/`

**Black formatting** → run auto-fix:
```bash
black src/
```

**Mypy type error** → fix the type annotation in the relevant file

**Test failure** → read the test, understand the assertion, fix the source or the test

**Build error** → fix `pyproject.toml` or missing files

**Docker build error** → fix the relevant line in `hub/Dockerfile`

After fixing, run the check locally to confirm it passes before committing:
```bash
ruff check src/ && black --check src/ && mypy src/
# or
python -m pytest tests/ -q --tb=short
```

---

## Step 8 — Commit and push the fix

Stage only the files that were changed:
```bash
git add <changed files>
git status
```

Commit with a descriptive message:
```bash
git commit -m "Fix CI: <one-line description of what was fixed>"
```

Push:
```bash
git push origin master
```

Report: "Fix committed and pushed. New CI run will start shortly — checking again on next loop iteration."

---

## Step 9 — Re-check after push (if not using /loop)

If not already in a `/loop`, wait ~15 seconds and check again:
```bash
gh run list --limit 5 --json databaseId,name,status,conclusion,headBranch,createdAt,url \
  | jq -r '.[] | [.name, .status, (.conclusion // "pending"), .headBranch, .createdAt] | @tsv'
```

Report the new run status and suggest `/loop 2m /aw-check-ci` if still running.

---

## Notes

- CI runs on every push to `master` (3 OSes × 5 Python versions = 15 matrix jobs)
- PyPI publish only runs when a `v*` release tag is created
- Hub Docker only runs when a `hub-v*` tag is created or `hub/` files change on master
- Workflows take 3–10 minutes — use `/loop 2m /aw-check-ci` to monitor automatically
- Only commit and push if there is a genuine fix — do not push empty or no-op commits
- If the same failure repeats after a fix attempt, stop and explain what was tried rather than looping infinitely
