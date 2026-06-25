---
name: copilot-test-setup
description: Set up a local AgentWeave test environment with 3 GitHub Copilot CLI agents and a local Hub server (no Docker). Covers prerequisites, Hub DB init, project config, watchdog startup, UI build, auth setup, and teardown.
---

# Skill: copilot-test-setup

Set up a local AgentWeave test environment with 3 GitHub Copilot CLI agents and a local Hub server (no Docker).

---

## Prerequisites (verify once before running)

- **AgentWeave installed** (editable): `pip install -e ".[dev,mcp]"` from `AgentWeave/`
- **Copilot CLI installed**: run `copilot --version` → should show ≥ 1.0.63
  - Install: `npm install -g @github/copilot` (cross-platform)
  - Authenticate: `copilot login` (browser OAuth — no PAT required for local use)
- **Hub package installed**: `pip install -e .` from `AgentWeave/hub/`
- **PATH fix (Windows)**: The `agentweave-watch` and `agentweave-mcp` scripts install to the user Scripts directory which may not be in PATH. Add it:
  ```powershell
  # Find the directory
  python -c "import site; print(site.getusersitepackages())"
  # → e.g. C:\Users\<you>\AppData\Roaming\Python\Python3xx\site-packages
  # Add …\Scripts to PATH:
  $env:PATH = "C:\Users\<you>\AppData\Roaming\Python\Python3xx\Scripts;" + $env:PATH
  ```
  Or permanently add it via System → Environment Variables.

---

## Step 1: Delete any existing test directories (preserve .env token)

```powershell
# Save the token BEFORE deleting the directory (if it exists and has a real token)
$savedToken = $null
$envPath = "C:\Users\santosg\Documents\LocalProjects\git\aw-test\.env"
if (Test-Path $envPath) {
    $envContent = Get-Content $envPath -Raw
    if ($envContent -match "COPILOT_GITHUB_TOKEN=(?!PASTE_YOUR_TOKEN_HERE)(.+)") {
        $savedToken = $envContent.Trim()
        Write-Host "✅ Token saved from existing .env"
    }
}

Remove-Item -Recurse -Force "C:\Users\santosg\Documents\LocalProjects\git\aw-test" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "C:\Users\santosg\Documents\LocalProjects\git\agentweave-test3" -ErrorAction SilentlyContinue
Write-Host "Test directories deleted"
```

> **Keep `$savedToken` in scope** — it is used in Step 5 to restore the token automatically. Run Steps 1–7 in a single PowerShell session so the variable persists.

---

## Step 2: Reset and initialise the Hub database (always delete first)

```powershell
cd C:\Users\santosg\Documents\LocalProjects\git\AgentWeave\hub

# Kill any running Hub process on port 8000 before touching the DB
$existing = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $existing) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }

# Always delete the existing database for a clean slate
Remove-Item -Force "data\agentweave.db" -ErrorAction SilentlyContinue
Remove-Item -Force "data\agentweave.db-shm" -ErrorAction SilentlyContinue
Remove-Item -Force "data\agentweave.db-wal" -ErrorAction SilentlyContinue
Write-Host "Old database deleted"

# Ensure data directory exists
New-Item -ItemType Directory -Force data | Out-Null

# Run migrations (absolute path avoids "unable to open database file" error)
$env:DATABASE_URL = "sqlite+aiosqlite:///C:/Users/santosg/Documents/LocalProjects/git/AgentWeave/hub/data/agentweave.db"
python -m alembic upgrade head
Write-Host "Fresh database created"
```

---

## Step 3: Write the Hub .env file

```powershell
Set-Content "C:\Users\santosg\Documents\LocalProjects\git\AgentWeave\hub\.env" @"
DATABASE_URL=sqlite+aiosqlite:///C:/Users/santosg/Documents/LocalProjects/git/AgentWeave/hub/data/agentweave.db
AW_PORT=8000
AW_CORS_ORIGINS=http://localhost:5173,http://localhost:3000
AW_BOOTSTRAP_PROJECT_ID=proj-default
AW_BOOTSTRAP_PROJECT_NAME=Default Project
"@
```

---

## Step 4: Start the Hub server (background)

```powershell
$env:DATABASE_URL = "sqlite+aiosqlite:///C:/Users/santosg/Documents/LocalProjects/git/AgentWeave/hub/data/agentweave.db"
$env:AW_PORT = "8000"
$env:AW_CORS_ORIGINS = "http://localhost:5173,http://localhost:3000"

$hubProc = Start-Process python `
  -ArgumentList "-m", "uvicorn", "hub.main:app", "--host", "0.0.0.0", "--port", "8000" `
  -WorkingDirectory "C:\Users\santosg\Documents\LocalProjects\git\AgentWeave\hub" `
  -WindowStyle Hidden -PassThru

Write-Host "Hub PID: $($hubProc.Id)"

# Verify it's up
Start-Sleep 3
(Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing).Content
# → {"status":"ok"}
```

---

## Step 5: Create and configure the test project

```powershell
New-Item -ItemType Directory "C:\Users\santosg\Documents\LocalProjects\git\aw-test" | Out-Null
cd C:\Users\santosg\Documents\LocalProjects\git\aw-test

# Initialise session
python -m agentweave init --project "Copilot Test"
```

Then overwrite `agentweave.yml` with the 3-copilot-agent config:

```powershell
Set-Content "C:\Users\santosg\Documents\LocalProjects\git\aw-test\agentweave.yml" @"
project:
  name: Copilot Test
  mode: hierarchical
  hub_client: cli

hub:
  url: http://localhost:8000

agents:
  copilot-lead:
    runner: copilot
    roles: [tech_lead]
    env: [COPILOT_GITHUB_TOKEN]
    yolo: true
    pilot: false
    hub_client: cli

  copilot-backend:
    runner: copilot
    roles: [backend_dev]
    env: [COPILOT_GITHUB_TOKEN]
    yolo: true
    pilot: false
    hub_client: cli

  copilot-frontend:
    runner: copilot
    roles: [frontend_dev]
    env: [COPILOT_GITHUB_TOKEN]
    yolo: true
    pilot: false
    hub_client: cli
"@
```

Restore or create the `.env` with the token:

```powershell
if ($savedToken) {
    # Restore saved token automatically
    Set-Content "C:\Users\santosg\Documents\LocalProjects\git\aw-test\.env" $savedToken
    Write-Host "✅ Token restored from saved value"
} else {
    # First time — create placeholder; open in notepad to paste token
    Set-Content "C:\Users\santosg\Documents\LocalProjects\git\aw-test\.env" "COPILOT_GITHUB_TOKEN=PASTE_YOUR_TOKEN_HERE"
    Write-Host "⚠️  Token placeholder created — open in notepad and replace with real token:"
    Write-Host "    notepad C:\Users\santosg\Documents\LocalProjects\git\aw-test\.env"
}
```

---

## Step 6: Activate and register with Hub

```powershell
cd C:\Users\santosg\Documents\LocalProjects\git\aw-test
python -m agentweave activate
```

Expected output:
- `[TRANSPORT] Connected to Hub at http://localhost:8000`
- `[AGENTS] Added: copilot-lead / copilot-backend / copilot-frontend`
- `[OK] copilot-lead/backend/frontend: already configured` (MCP)
- Warnings about missing `COPILOT_GITHUB_TOKEN` are normal if using native OAuth auth

---

## Step 7: Start the watchdog

```powershell
# agentweave scripts install to the user AppData Scripts dir (NOT the system Python Scripts)
# This must be in PATH before calling agentweave start, otherwise Popen can't find agentweave-watch.exe
$env:PATH = "C:\Users\santosg\AppData\Roaming\Python\Python314\Scripts;" + $env:PATH

cd C:\Users\santosg\Documents\LocalProjects\git\aw-test
python -m agentweave start
```

> **Note (Windows):** The scripts are in `C:\Users\santosg\AppData\Roaming\Python\Python314\Scripts`, **not** `C:\Python314\Scripts`. The editable install (`pip install -e`) puts entry-point scripts in the user AppData Scripts directory. Always set PATH to this location before running `agentweave start`.

Expected: `[OK] Watchdog started in background (PID XXXXX)`

Verify:
```powershell
python -m agentweave status
# Shows: Session + 3 agents (idle) + Watchdog heartbeat
```

---

## Step 8: Build and serve the Hub UI

The Hub serves a built React UI from `hub/hub/static/ui/`. Build it fresh after any code changes to get the latest UI (including the copilot runner badge):

```powershell
cd C:\Users\santosg\Documents\LocalProjects\git\AgentWeave\hub\ui
npm install        # first time only
npm run build

# Copy build output into Hub's static dir
$dest = "C:\Users\santosg\Documents\LocalProjects\git\AgentWeave\hub\hub\static\ui"
Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item -Recurse ".\dist\*" $dest
```

Then restart the Hub server (step 4) so it serves the new files.

**Access the dashboard at:** http://localhost:8000

The UI auto-bootstraps by calling `/api/v1/setup/token` (localhost-only endpoint) to get the API key — no manual configuration needed.

> **If agents don't appear after restart:** you may have a stale API key in browser sessionStorage from a previous Hub instance. Open http://localhost:8000 in a **private/incognito window** to start fresh.

---

## Step 9: Send a test message

```powershell
cd C:\Users\santosg\Documents\LocalProjects\git\aw-test
python -m agentweave quick --to copilot-backend "List the files in this directory"
```

The watchdog will pick up the message and invoke:
```
copilot -p "<inbox prompt>" --output-format json --allow-all-tools --no-ask-user
```

Watch the logs:
```powershell
Get-Content .agentweave\logs\events.jsonl -Tail 20
```

---

## Teardown

```powershell
# Stop watchdog
cd C:\Users\santosg\Documents\LocalProjects\git\aw-test
python -m agentweave stop

# Kill Hub server (use PID saved in step 4)
Stop-Process -Id <hub-pid>
```

---

## Auth for headless/watchdog use (⚠️ important)

The Copilot CLI has **two authentication methods**:

| Method | How | Works headless? |
|--------|-----|-----------------|
| **Native OAuth** | `copilot login` — stores token in Windows Credential Manager | ⚠️ Risky |
| **PAT (recommended)** | Fine-grained PAT → `COPILOT_GITHUB_TOKEN` env var | ✅ Safe |

**Why native OAuth is risky with multiple agents:**
The watchdog may trigger several copilot agents at nearly the same time. On Windows, all of them read the same credential from Windows Credential Manager concurrently. Only the first process wins; the rest receive "No authentication information found" and exit immediately (shown as `❌` in watchdog output).

**How to create and use a PAT:**
1. Go to https://github.com/settings/personal-access-tokens/new
2. Choose **Fine-grained** token
3. Under "Permissions" → "Account permissions" → **Copilot** → set to **Read and Write**
4. Copy the token
5. Add to your test project's `.env`:

```powershell
Set-Content "C:\Users\santosg\Documents\LocalProjects\git\aw-test\.env" "COPILOT_GITHUB_TOKEN=ghp_xxxxxxxxxxxx"
```

6. Restart the watchdog so it picks up the new env var.

> The `agentweave doctor` command will warn if no token is found in the environment.
> The `agentweave.yml` `env: [COPILOT_GITHUB_TOKEN]` key tells the watchdog to forward this env var to each copilot subprocess.

---

## Known Issues & Notes

| Issue | Fix |
|-------|-----|
| `❌ copilot-frontend failed — authentication error` | Set `COPILOT_GITHUB_TOKEN` PAT (see Auth section above). Native OAuth is not safe for concurrent agents. |
| `[WinError 2] The system cannot find the file specified` on `agentweave start` | User Scripts dir not in PATH — add `C:\Users\<you>\AppData\Roaming\Python\Python3xx\Scripts` to `$env:PATH` |
| Watchdog shows "stopped (stale PID file)" but heartbeat is recent | False positive on Windows — check `watchdog.heartbeat` timestamp; if < 30s ago the watchdog is healthy |
| Agents don't appear in Hub UI | Browser has stale API key in sessionStorage from previous Hub instance. Open in **private/incognito window**, or clear sessionStorage in DevTools → Application → Session Storage → delete `agentweave-session` → reload |
| Hub UI shows outdated copilot badge | Rebuild the UI: `npm run build` in `hub/ui/`, then copy `dist/*` to `hub/hub/static/ui/` and restart Hub |
| MCP org policy error | Some GitHub org policies block third-party MCP servers; use a personal account |
| Alembic `unable to open database file` | `data/` dir missing or relative path — use absolute `DATABASE_URL` |
