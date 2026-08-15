<#
.SYNOPSIS
    One autonomous-session iteration, as a fresh headless `claude -p` process.

.DESCRIPTION
    Invoked by the Scheduled Task installed by install-driver.ps1. Holds nothing between firings --
    all continuity lives in .claude/autonomous/STATE.json and the log, which is precisely what makes
    the arrangement survive a session, a logout, or a crash.

    Refuses to run past the stop time and unregisters the task, so an unattended run ends by itself
    rather than because someone noticed.
#>

param(
  [Parameter(Mandatory = $true)][string] $Repo,
  [string] $UntilHHmm = "10:00",
  [string] $TaskName = "AgentWeaveAutonomousSession"
)

$ErrorActionPreference = "Stop"
$logFile = Join-Path $Repo ".claude\autonomous\driver.log"

function Write-Log([string] $Message) {
  $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $logFile -Value $line -Encoding utf8
  Write-Output $line
}

# --- stop condition -----------------------------------------------------------------------------
$stopAt = [datetime]::ParseExact($UntilHHmm, "HH:mm", $null)
if ((Get-Date) -ge $stopAt -and (Get-Date).Hour -ge $stopAt.Hour) {
  Write-Log "Past $UntilHHmm - unregistering '$TaskName' and stopping."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

$stateFile = Join-Path $Repo ".claude\autonomous\STATE.json"
if (-not (Test-Path $stateFile)) {
  Write-Log "No STATE.json - nothing to resume. Stopping."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

# --- the prompt ---------------------------------------------------------------------------------
# Deliberately short. Everything the iteration needs to know is on disk; restating it here would
# create a second source of truth that drifts from the file the session actually maintains.
$prompt = @'
Continue the autonomous work session. You are a fresh process with no memory of previous
iterations - everything you need is on disk.

1. Read .claude/autonomous/STATE.json for position, and the newest entry of the log in
   .claude/autonomous/ for context.
2. Verify the branch and `git log` match what STATE.json claims. Reconcile in the log if not.
3. Do exactly the one unit of work named in `next_action`, sized to finish in this turn.
4. Verify it: run the tests, drive the real surface. A passing suite is not proof of behaviour.
5. Append a log entry, rewrite STATE.json (including next_action and last_heartbeat), then
   commit and push. Never end an iteration with a dirty tree.

Honour the limits recorded in STATE.json. Stay on the autonomous branch. If a decision is
genuinely the user's, add it to decisions_for_user rather than guessing.
'@

Set-Location $Repo
Write-Log "--- iteration start ---"

# --permission-mode bypassPermissions: nobody is present to answer a prompt, and a firing that
# blocks on one silently consumes its whole window. The branch isolation is what makes this
# acceptable; do not use this driver on a branch that matters.
& claude -p $prompt --permission-mode bypassPermissions 2>&1 | ForEach-Object { Write-Log $_ }
$code = $LASTEXITCODE

Write-Log "--- iteration end (exit $code) ---"
exit $code
