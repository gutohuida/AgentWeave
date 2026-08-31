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
  [int] $HeartbeatGraceMinutes = 25,
  # Repo-relative state file and driver log. Defaults reproduce the single-window arrangement
  # exactly. A checkout running more than one daily window gives each its own pair, or the second
  # window reads the first's queue and repeats work already done and pushed.
  [string] $StateFile = ".claude\autonomous\STATE.json",
  [string] $LogFile = ".claude\autonomous\driver.log"
)

$ErrorActionPreference = "Stop"

# See the matching guard in install-driver.ps1. An absolute path here joins onto $Repo a second
# time and yields a path that never exists, which this script reports as "nothing to resume" and
# then unregisters the task over -- indistinguishable, in the log, from finishing the queue.
if ([System.IO.Path]::IsPathRooted($StateFile)) { throw "-StateFile must be repo-relative, not absolute: $StateFile" }
if ([System.IO.Path]::IsPathRooted($LogFile))   { throw "-LogFile must be repo-relative, not absolute: $LogFile" }

$driverLogPath = Join-Path $Repo $LogFile

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
  [System.IO.File]::AppendAllText($driverLogPath, $line + [Environment]::NewLine, $script:LogEncoding)
  Write-Output $line
}

# --- stop condition -----------------------------------------------------------------------------
$stopAtInstant = [datetime]::Parse($StopAt, [System.Globalization.CultureInfo]::InvariantCulture)
if ((Get-Date) -ge $stopAtInstant) {
  Write-Log "Past $stopAtInstant - unregistering '$TaskName' and stopping."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

$stateFilePath = Join-Path $Repo $StateFile
# Forward slashes, because the prompt below is read by an agent that will type this path into
# tools where a backslash is an escape.
$stateRelative = $StateFile -replace '\\', '/'
if (-not (Test-Path $stateFilePath)) {
  Write-Log "No $stateRelative - nothing to resume. Stopping."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

try { $state = Get-Content $stateFilePath -Raw | ConvertFrom-Json } catch {
  Write-Log "STATE.json did not parse - refusing to launch an unattended agent."
  exit 2
}
$stateRunner = if ($state.runner) { ([string]$state.runner).ToLowerInvariant() } else { "claude" }
$statePermissionMode = if ($state.permission_mode) { ([string]$state.permission_mode).ToLowerInvariant() } else { "unattended-full-access" }
# STATE.json records the model prep agreed with the operator, and without this it was decoration:
# a headless CLI with no -m falls back to the user's own default. Measured 2026-08-26 -- the
# operator selected Sonnet 5, ~/.claude/settings.json says "opus[1m]", and every firing of an
# eight-hour run would have been Opus. Absent from the state file, keep the CLI default.
$stateModel = if ($state.model) { ([string]$state.model).Trim() } else { "" }
# Which log this window writes. The prompt used to send the agent at the DIRECTORY, which held one
# log when only one window existed and now holds two live ones plus every finished run's. Naming it
# is the difference between reading your own last entry and reading the other window's.
$stateLogFile = if ($state.log_file) { ([string]$state.log_file).Trim() } else { ".claude/autonomous/" }
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
  try { $heartbeat = (Get-Content $stateFilePath -Raw | ConvertFrom-Json).last_heartbeat } catch {
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

# The prompt is a literal here-string so nothing inside it can be interpolated by accident. The one
# thing that legitimately varies per window is which state file to read, so name it explicitly --
# an agent told to read STATE.json on a checkout holding two of them will pick the wrong one, and
# then commit a queue position belonging to the other window.
# Tokenise, then expand once. Substituting the paths directly is order-dependent and silently wrong
# in the legacy single-window case: the full-path replace is a no-op there, so a following bare
# `STATE.json` replace rewrites the path's own tail and yields
# .claude/autonomous/.claude/autonomous/STATE.json. Measured 2026-09-01 while adding this.
$prompt = $prompt.Replace('.claude/autonomous/STATE.json', '<<STATE>>').
                  Replace('STATE.json', '<<STATE>>').
                  Replace('.claude/autonomous/ for context.', '<<LOG>> for context.').
                  Replace('<<STATE>>', $stateRelative).
                  Replace('<<LOG>>', $stateLogFile)

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
    if ($stateModel) {
      & $AgentExecutable -p $prompt --model $stateModel --permission-mode bypassPermissions 2>&1 | ForEach-Object { Write-Log $_ }
    } else {
      & $AgentExecutable -p $prompt --permission-mode bypassPermissions 2>&1 | ForEach-Object { Write-Log $_ }
    }
  } elseif ($PermissionMode -eq "unattended-full-access") {
    # Pipe the prompt and close stdin explicitly. A Scheduled Task has no interactive stdin, and
    # Codex otherwise waits to see whether inherited stdin contains an additional input block.
    $codexModel = if ($stateModel) { @("-m", $stateModel) } else { @() }
    $prompt | & $AgentExecutable exec --ephemeral --color never --cd $Repo @codexModel --dangerously-bypass-approvals-and-sandbox - 2>&1 | ForEach-Object { Write-Log $_ }
  } else {
    $codexModel = if ($stateModel) { @("-m", $stateModel) } else { @() }
    $prompt | & $AgentExecutable --ask-for-approval never exec --ephemeral --color never --cd $Repo @codexModel --sandbox workspace-write - 2>&1 | ForEach-Object { Write-Log $_ }
  }
  $code = $LASTEXITCODE
} finally {
  $ErrorActionPreference = $previousErrorActionPreference
}

Write-Log "--- iteration end (exit $code) ---"
exit $code
