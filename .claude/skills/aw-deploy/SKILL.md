---
name: aw-deploy
description: Release a new version of AgentWeave — auto-detects next version, bumps pyproject.toml files, checks if documentation needs updates, updates CHANGELOG and README, commits, pushes and creates GitHub releases via Windows PowerShell (which holds git/gh credentials), then monitors the build. Never invoke this automatically.
disable-model-invocation: true
---

Deploy a new version of AgentWeave (CLI and/or Hub).

## Usage

```
/aw-deploy                          — auto-detect next version for both
/aw-deploy <cli-version>            — CLI only, explicit version
/aw-deploy <cli-version> hub:<hub>  — both, explicit versions
/aw-deploy hub:<hub-version>        — Hub only, explicit version
```

---

## Step 1 — Read current versions

```bash
python3 -c "
import re, subprocess

# Read pyproject versions
cli_ver = re.search(r'^version = \"(.+?)\"', open('pyproject.toml').read(), re.M).group(1)
hub_ver = re.search(r'^version = \"(.+?)\"', open('hub/pyproject.toml').read(), re.M).group(1)

# Read latest published version on PyPI
import urllib.request, json
try:
    with urllib.request.urlopen('https://pypi.org/pypi/agentweave-ai/json', timeout=5) as r:
        pypi_latest = sorted(json.load(r)['releases'].keys())[-1]
except Exception:
    pypi_latest = 'unknown'

print(f'CLI  local={cli_ver}  pypi={pypi_latest}')
print(f'Hub  local={hub_ver}')

# Suggest next minor version
parts = [int(x) for x in cli_ver.split('.')]
parts[1] += 1; parts[2] = 0
print(f'Suggested CLI next: {\".\".join(str(x) for x in parts)}')

hub_parts = [int(x) for x in hub_ver.split('.')]
hub_parts[1] += 1; hub_parts[2] = 0
print(f'Suggested Hub next: {\".\".join(str(x) for x in hub_parts)}')
"
```

---

## Step 2 — Resolve target versions

Parse $ARGUMENTS:
- If `$ARGUMENTS` contains a bare semver (e.g. `0.11.0`) → that is `cli_version`
- If it contains `hub:<semver>` (e.g. `hub:0.5.0`) → that is `hub_version`
- If $ARGUMENTS is **empty**, use the suggested next versions from Step 1 for **both**
  CLI and Hub, and ask: "I'll release CLI v<suggested> and Hub v<suggested>. Confirm?"
- If only one side is specified, only bump that side.

---

## Step 3 — Pre-flight checks

Stop and report if any fail.

```bash
# 3a. Working tree must be clean
git status --short
```
If dirty, stop: "Working tree is not clean — commit or stash first."

```bash
# 3b. Must be on master
git branch --show-current
```

```bash
# 3c. Must be up to date with remote (use Windows git for authoritative remote state)
powershell.exe -Command "cd '$(wslpath -w .)'; git fetch origin; git log HEAD..origin/master --oneline"
```
If behind, stop: "Local master is behind origin/master — pull first."

```bash
# 3d. Lint
ruff check src/
```

```bash
# 3e. Tests (if tests/ exists)
[ -d tests ] && python -m pytest tests/ -q --tb=short || echo "no tests"
```

Show summary and ask: "All checks passed. Proceed?"

---

## Step 4 — Bump versions

**If releasing CLI:** edit `pyproject.toml` — replace `version = "<old>"` with `version = "<cli_version>"`.

**If releasing Hub:** edit `hub/pyproject.toml` — replace `version = "<old>"` with `version = "<hub_version>"`.

Verify:
```bash
grep '^version' pyproject.toml hub/pyproject.toml
```

---

## Step 5 — Update documentation

Review recent changes and determine if documentation needs updates:

```bash
# See what changed since last tag
git log --oneline $(git describe --tags --abbrev=0)..HEAD
```

**Check and update if needed:**
- `AGENTS.md` — New CLI commands, configuration options, or architecture changes?
- `README.md` — New features, changed usage patterns, or updated examples?
- `CLAUDE.md` / `KIMI.md` — Agent-specific context changes?
- `docs/` — New features that need user documentation?

Ask: "Any documentation updates needed for these changes?"

If yes, update the relevant files before proceeding.

---

## Step 6 — Update README.md

The README has version strings in the Repository Layout section. Update them:

```bash
python3 -c "
import re

readme = open('README.md').read()

# Replace version in Repository Layout table — CLI line
if '${cli_version}' != 'unchanged':
    readme = re.sub(
        r'(src/agentweave/\s+CLI package[^\n]*—\s*v)[0-9]+\.[0-9]+\.[0-9]+',
        r'\g<1>${cli_version}',
        readme
    )

# Replace version in Repository Layout table — Hub line
if '${hub_version}' != 'unchanged':
    readme = re.sub(
        r'(hub/\s+AgentWeave Hub[^\n]*—\s*v)[0-9]+\.[0-9]+\.[0-9]+',
        r'\g<1>${hub_version}',
        readme
    )

open('README.md', 'w').write(readme)
print('README.md updated')
"
```

Where `${cli_version}` and `${hub_version}` are the actual new version values.

---

## Step 7 — Update CHANGELOG.md

Insert a new section after the `---` on line 8. Use today's date (`YYYY-MM-DD`).

Get commit history since the last tag:
```bash
git log --oneline $(git describe --tags --abbrev=0)..HEAD
```

**Format for both:**
```markdown
## [<cli_version>] - <today>

### Added (CLI)
- <summarize CLI changes from git log>

### Added (Hub v<hub_version>)
- <summarize Hub changes from git log>

---
```

**Format for CLI-only or Hub-only:** omit the section that isn't changing.

Ask the user to review the CHANGELOG entry and confirm before proceeding.

---

## Step 8 — Commit (via Linux git)

Stage only the changed files:
```bash
git add pyproject.toml hub/pyproject.toml CHANGELOG.md README.md
git status
```

```bash
git commit -m "<message>"
```

Commit message format:
- Both:     `Bump to v<cli_version> / Hub v<hub_version>`
- CLI only: `Bump to v<cli_version>`
- Hub only: `Bump Hub to v<hub_version>`

---

## Step 9 — Push (via Windows PowerShell — has git credentials)

```bash
WIN_PATH=$(wslpath -w .)
powershell.exe -Command "cd '$WIN_PATH'; git push origin master"
```

If it fails, report the PowerShell error verbatim and stop.

---

## Step 10 — Create GitHub releases (via Windows PowerShell — has gh credentials)

**If releasing CLI:**
```bash
WIN_PATH=$(wslpath -w .)
powershell.exe -Command "cd '$WIN_PATH'; gh release create v<cli_version> --title 'AgentWeave v<cli_version>' --notes 'See CHANGELOG for details.' --latest"
```

**If releasing Hub:**
```bash
WIN_PATH=$(wslpath -w .)
powershell.exe -Command "cd '$WIN_PATH'; gh release create hub-v<hub_version> --title 'AgentWeave Hub v<hub_version>' --notes 'See CHANGELOG for details.'"
```

---

## Step 11 — Monitor build via check-build skill

Invoke the `check-build` skill to immediately show the initial CI status:

```
skill: "check-build", args: "v<cli_version> hub-v<hub_version>"
```

(Omit args for the side that wasn't released.)

Then tell the user:
> "Releases created. Run `/loop 30s /check-build v<cli_version> hub-v<hub_version>` to monitor the builds until they complete."

---

## Summary

Report:
- Versions bumped (which files)
- CHANGELOG: section added
- README: version strings updated
- Commit SHA and message
- GitHub release tags created
- CI monitoring command to run
