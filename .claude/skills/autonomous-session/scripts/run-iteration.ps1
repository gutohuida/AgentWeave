<#
.SYNOPSIS
    One autonomous-session iteration, as a fresh headless Claude or Codex process.

.DESCRIPTION
    Invoked by the Scheduled Task installed by install-driver.ps1. Holds nothing between firings --
    all continuity lives in .claude/autonomous/STATE.json and the log, which is precisely what makes
    the arrangement survive a session, a logout, or a crash.

    Refuses to run past the stop time and unregisters the task, so an unattended run ends by itself
    rather than because someone noticed.
#>

param(
  [Parameter(Mandatory = $true)][string] $Repo,
  # An absolute instant, not a wall-clock time. install-driver.ps1 computes it, because only the
  # installer knows "now" and can decide whether 07:00 means this morning or tomorrow morning.
  # An HH:mm parsed here would resolve to *today*, so a run installed at 23:00 to stop at 07:00
  # would consider itself already finished and unregister on its first firing -- which is the
  # overnight case, the one this whole driver exists for.
  [Parameter(Mandatory = $true)][string] $StopAt,
  [string] $TaskName = "AgentWeaveAutonomousSession",
  [ValidateSet("claude", "codex")]
  [string] $Runner = "claude",
  [ValidateSet("unattended-full-access", "workspace-contained")]
  [string] $PermissionMode = "unattended-full-access",
  [string] $AgentExecutable = "",
  # How recently STATE.json must have been touched for this firing to conclude a live session is
  # already doing the work and stand down. The driver is often installed as a *backup* to an
  # interactive session rather than instead of one; without this, both write to the same branch and
  # the headless one commits the interactive one's half-finished tree. Set to 0 to disable.
  [int] $HeartbeatGraceMinutes = 25
)

$ErrorActionPreference = "Stop"
$logFile = Join-Path $Repo ".claude\autonomous\driver.log"

if (-not $AgentExecutable) {
  $agentCommand = Get-Command $Runner -ErrorAction SilentlyContinue
  if (-not $agentCommand) { throw "$Runner CLI not found on PATH." }
  $AgentExecutable = $agentCommand.Source
}
if (-not (Test-Path $AgentExecutable)) { throw "Agent executable not found: $AgentExecutable" }
if ($Runner -eq "claude" -and $PermissionMode -ne "unattended-full-access") {
  throw "Claude workspace-contained mode is not implemented."
}

# UTF-8 without a BOM. `Add-Content -Encoding utf8` on Windows PowerShell 5.1 writes one, and it
# lands at the head of the file where it is invisible in an editor and shows up as a stray glyph
# in every downstream reader.
$script:LogEncoding = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string] $Message) {
  $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  [System.IO.File]::AppendAllText($logFile, $line + [Environment]::NewLine, $script:LogEncoding)
  Write-Output $line
}

# --- stop condition -----------------------------------------------------------------------------
$stopAtInstant = [datetime]::Parse($StopAt, [System.Globalization.CultureInfo]::InvariantCulture)
if ((Get-Date) -ge $stopAtInstant) {
  Write-Log "Past $stopAtInstant - unregistering '$TaskName' and stopping."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

$stateFile = Join-Path $Repo ".claude\autonomous\STATE.json"
if (-not (Test-Path $stateFile)) {
  Write-Log "No STATE.json - nothing to resume. Stopping."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

try { $state = Get-Content $stateFile -Raw | ConvertFrom-Json } catch {
  Write-Log "STATE.json did not parse - refusing to launch an unattended agent."
  exit 2
}
$stateRunner = if ($state.runner) { ([string]$state.runner).ToLowerInvariant() } else { "claude" }
$statePermissionMode = if ($state.permission_mode) { ([string]$state.permission_mode).ToLowerInvariant() } else { "unattended-full-access" }
if ($stateRunner -ne $Runner -or $statePermissionMode -ne $PermissionMode) {
  Write-Log "Driver settings ($Runner/$PermissionMode) disagree with STATE.json ($stateRunner/$statePermissionMode). Stopping."
  exit 2
}
$currentBranch = (& git -C $Repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or -not $currentBranch) {
  Write-Log "Could not resolve the current Git branch. Stopping."
  exit 2
}
if ($state.branch -and $currentBranch -ne [string]$state.branch) {
  Write-Log "Current branch '$currentBranch' does not match STATE.json branch '$($state.branch)'. Stopping."
  exit 2
}

# A completed queue must stop before spending another model invocation. The prior firing owns the
# atomic transition to next_action=null; MultipleInstances=IgnoreNew guarantees we cannot observe
# its half-written state while it is still running.
if (-not $state.next_action) {
  Write-Log "STATE.json has no next_action - queue complete. Unregistering '$TaskName'."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

# --- stand down for a live session --------------------------------------------------------------
# Deliberately does NOT unregister: the session this is backing up may die at any moment, and the
# next firing is what picks the work up. Standing down is a skip, not a stop.
if ($HeartbeatGraceMinutes -gt 0) {
  $heartbeat = $null
  try { $heartbeat = (Get-Content $stateFile -Raw | ConvertFrom-Json).last_heartbeat } catch {
    Write-Log "STATE.json did not parse - proceeding, since a backup that defers to a file it cannot read is no backup."
  }
  if ($heartbeat) {
    try {
      $age = ([datetimeoffset]::Now - [datetimeoffset]::Parse($heartbeat, [System.Globalization.CultureInfo]::InvariantCulture)).TotalMinutes
      if ($age -lt $HeartbeatGraceMinutes) {
        Write-Log ("Heartbeat is {0:N1} min old (grace {1}) - a live session holds the branch. Standing down." -f $age, $HeartbeatGraceMinutes)
        exit 0
      }
      Write-Log ("Heartbeat is {0:N1} min old (grace {1}) - assuming the session died. Taking over." -f $age, $HeartbeatGraceMinutes)
    } catch {
      Write-Log "last_heartbeat '$heartbeat' is not a parseable instant - proceeding as though absent."
    }
  }
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
6. LAST of all, once everything is pushed: set last_heartbeat to an instant ~40 minutes in the
   past and commit that one-line change. This releases the branch so the very next firing picks
   the work up instead of standing down against your own heartbeat and idling a cycle. Do this
   ONLY at the end -- while you are still working, keep refreshing last_heartbeat to now, which
   is what keeps an interactive session and this driver off each other.

Stamp every timestamp from PowerShell (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz') or Python's
datetime.now().astimezone(). Git Bash `date` on this machine prints UTC but labels it +0100, so a
heartbeat written from it lands an hour in the future and stalls the loop until real time catches up.

Honour the limits recorded in STATE.json. Stay on the autonomous branch. If a decision is
genuinely the user's, add it to decisions_for_user rather than guessing.
'@

Set-Location $Repo
Write-Log "--- iteration start ($Runner, $PermissionMode) ---"

# Nobody is present to answer a prompt. The full-access modes below are deliberately explicit:
# branch isolation protects Git history, but it is not a machine sandbox. Use this driver only
# after prep has established the limits and the operator has accepted that posture.
# Native CLIs legitimately write progress to stderr. Windows PowerShell wraps those lines as
# NativeCommandError records; with ErrorActionPreference=Stop, the first one aborts the wrapper.
# Keep strict handling for the driver itself, but allow the child process to stream both channels
# and use its exit code as the authority.
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  if ($Runner -eq "claude") {
    & $AgentExecutable -p $prompt --permission-mode bypassPermissions 2>&1 | ForEach-Object { Write-Log $_ }
  } elseif ($PermissionMode -eq "unattended-full-access") {
    # Pipe the prompt and close stdin explicitly. A Scheduled Task has no interactive stdin, and
    # Codex otherwise waits to see whether inherited stdin contains an additional input block.
    $prompt | & $AgentExecutable exec --ephemeral --color never --cd $Repo --dangerously-bypass-approvals-and-sandbox - 2>&1 | ForEach-Object { Write-Log $_ }
  } else {
    $prompt | & $AgentExecutable --ask-for-approval never exec --ephemeral --color never --cd $Repo --sandbox workspace-write - 2>&1 | ForEach-Object { Write-Log $_ }
  }
  $code = $LASTEXITCODE
} finally {
  $ErrorActionPreference = $previousErrorActionPreference
}

Write-Log "--- iteration end (exit $code) ---"
exit $code
