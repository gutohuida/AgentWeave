---
name: aw-deploy
description: Release a new version of AgentWeave — bumps versions, updates CHANGELOG, commits, tags, and creates GitHub releases to trigger PyPI and Docker Hub publishing. Never invoke this automatically.
disable-model-invocation: true
---

Deploy a new version of AgentWeave (CLI and/or Hub).

## Usage

```
/aw-deploy <cli-version>                  — CLI only (e.g. 0.7.0)
/aw-deploy <cli-version> hub:<hub-version> — both (e.g. 0.7.0 hub:0.3.0)
/aw-deploy hub:<hub-version>              — Hub only (e.g. hub:0.3.0)
```

Parse $ARGUMENTS to extract:
- `cli_version`: the new CLI version (semver, e.g. `0.7.0`) — present if not Hub-only
- `hub_version`: the new Hub version (semver, e.g. `0.3.0`) — present if prefixed with `hub:`

If $ARGUMENTS is empty or does not contain a version, ask:
> "What version should I release? Usage: `/aw-deploy <cli-version>` or `/aw-deploy <cli-version> hub:<hub-version>`"

---

## Step 1 — Pre-flight checks

Run all of these before making any changes. Stop and report if any fail.

```bash
# 1a. Git working tree must be clean
git status --short
```
If any uncommitted changes exist, stop: "Working tree is not clean — commit or stash changes before releasing."

```bash
# 1b. Must be on master branch
git branch --show-current
```
If not on `master`, stop: "Not on master branch."

```bash
# 1c. Must be up to date with remote
git fetch origin
git log HEAD..origin/master --oneline
```
If remote has commits we don't have, stop: "Local master is behind origin/master — pull first."

```bash
# 1d. Run lint
ruff check src/
```

```bash
# 1e. Run tests if tests/ directory exists
[ -d tests ] && python -m pytest tests/ -q --tb=short || echo "no tests"
```

Show the user a summary of all checks and ask: "All checks passed. Proceed with release?"

---

## Step 2 — Confirm current and new versions

Read the current versions:
```bash
grep '^version' pyproject.toml | head -1
grep '^version' hub/pyproject.toml | head -1
```

Display a clear before/after table:

| Package | Current | New |
|---------|---------|-----|
| agentweave-ai (CLI) | `<current>` | `<cli_version or unchanged>` |
| agentweave-hub (Hub) | `<current>` | `<hub_version or unchanged>` |

Ask: "Does this look correct?"

---

## Step 3 — Bump versions

Only bump what was requested.

**If releasing CLI:**
Edit `pyproject.toml` — change `version = "<old>"` to `version = "<cli_version>"` under `[project]`.

**If releasing Hub:**
Edit `hub/pyproject.toml` — change `version = "<old>"` to `version = "<hub_version>"` under `[project]`.

Verify the edits:
```bash
grep '^version' pyproject.toml
grep '^version' hub/pyproject.toml
```

---

## Step 4 — Update CHANGELOG.md

Open `CHANGELOG.md`. After the `---` separator below the file header (line 8), insert a new section.

Use today's date in `YYYY-MM-DD` format.

**Format for both CLI + Hub release:**
```markdown
## [<cli_version>] - <today>

### Added (CLI)
- <summarize CLI changes since last release — read recent commits with: git log --oneline <last_cli_tag>..HEAD>

### Added (Hub v<hub_version>)
- <summarize Hub changes since last release>

---
```

**Format for CLI-only:**
```markdown
## [<cli_version>] - <today>

### Added
- <summarize changes>

---
```

**Format for Hub-only:**
```markdown
## [<hub_version>] - <today> (Hub)

### Added (Hub)
- <summarize Hub changes>

---
```

To get the commit history since the last tag:
```bash
git log --oneline $(git describe --tags --abbrev=0)..HEAD
```

Ask the user to review the CHANGELOG entry and confirm or provide corrections before proceeding.

---

## Step 5 — Commit

Stage only the version and changelog files:
```bash
git add pyproject.toml hub/pyproject.toml CHANGELOG.md
git status
```

Build the commit message based on what's being released:
- Both: `Bump to v<cli_version> / Hub v<hub_version>`
- CLI only: `Bump to v<cli_version>`
- Hub only: `Bump Hub to v<hub_version>`

```bash
git commit -m "<message>"
```

---

## Step 6 — Push

```bash
git push origin master
```

---

## Step 7 — Create GitHub releases (triggers CI publishing)

**If releasing CLI** — creates a GitHub release tagged `v<cli_version>`:
- This triggers `.github/workflows/publish.yml` → builds wheel + sdist → uploads to PyPI
```bash
gh release create v<cli_version> \
  --title "AgentWeave v<cli_version>" \
  --notes "See [CHANGELOG](https://github.com/gutohuida/AgentWeave/blob/master/CHANGELOG.md) for details." \
  --latest
```

**If releasing Hub** — creates a GitHub release tagged `hub-v<hub_version>`:
- This triggers `.github/workflows/hub-image.yml` → builds Docker image → pushes to `ghcr.io/gutohuida/agentweave-hub`
```bash
gh release create hub-v<hub_version> \
  --title "AgentWeave Hub v<hub_version>" \
  --notes "See [CHANGELOG](https://github.com/gutohuida/AgentWeave/blob/master/CHANGELOG.md) for details."
```

---

## Step 8 — Verify publishing

After creating releases, verify the CI workflows started:
```bash
gh run list --limit 5
```

Show the user the workflow run URLs and report:
- CLI release: PyPI publish workflow triggered? → package will be at `https://pypi.org/project/agentweave-ai/`
- Hub release: Docker image workflow triggered? → image will be at `ghcr.io/gutohuida/agentweave-hub:<hub_version>`

---

## Summary

Report what was done:
- Versions bumped: which files changed
- CHANGELOG: section added for which versions
- Commit: SHA and message
- Tags created: `v<cli_version>` and/or `hub-v<hub_version>`
- Workflows triggered: links to CI runs
