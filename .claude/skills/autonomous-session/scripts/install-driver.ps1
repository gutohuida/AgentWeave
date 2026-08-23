<#
.SYNOPSIS
    Install a Windows Scheduled Task that drives an autonomous Claude or Codex session.

.DESCRIPTION
    This is the only local driver that survives the interactive session ending.

    `ScheduleWakeup` and `CronCreate` both stop when the Claude Code session goes away -- measured
    on 2026-08-15, where an overnight run was asked for nine hours and got forty minutes. The
    machine had not slept and had not rebooted; the session simply stopped existing, taking every
    scheduled wakeup with it.

    A Scheduled Task does not care. Each firing is a brand new agent process that reads
    .claude/autonomous/STATE.json, performs one iteration, commits, pushes, and exits. Nothing is
    held in memory between iterations, which is exactly what makes it survivable.

    A cloud schedule would also survive, but cannot reach a local Hub, local runtimes, or the local
    checkout -- so it is not an option for work that drives this product.

.PARAMETER Repo
    Repository root. Defaults to this script's grandparent-of-grandparent.

.PARAMETER EveryMinutes
    Interval between iterations. Make it SHORTER than a typical iteration, not longer -- the
    settings below use MultipleInstances IgnoreNew, so a firing that lands mid-iteration is
    dropped by the scheduler and cannot overlap. The interval therefore does not bound how long
    an iteration may take; it only bounds how long the driver sits idle after one ends.

    Measured 2026-08-21, run 2, at 15 minutes: iterations ran 4-19 minutes, roughly 40% of
    firings were dropped mid-iteration, and each drop cost up to a full interval of idle time.
    Lengthening the interval makes that worse. 5 is a good default.

.PARAMETER UntilHHmm
    Local wall-clock time to stop, e.g. "10:00". Resolved here to an absolute instant; a time
    already past today is taken to mean tomorrow. The task unregisters itself past it.

.PARAMETER TaskName
    Scheduled Task name. Also used to find and remove it again.

.PARAMETER Runner
    Agent CLI to invoke. `auto` reads STATE.json.runner and falls back to `claude` for legacy state.

.PARAMETER PermissionMode
    Permission posture. `auto` reads STATE.json.permission_mode and falls back to
    `unattended-full-access` for legacy state. Overnight runs must never select a posture that can
    ask the absent operator a question.

.PARAMETER StartAtHHmm
    Wall-clock time of the first firing, HH:mm. A time that has already passed today means
    tomorrow, so arming at night for a morning start does the obvious thing. Omit to start a
    minute from now, which is the attended case.

.EXAMPLE
    powershell -File install-driver.ps1 -EveryMinutes 5 -UntilHHmm "10:00"

.EXAMPLE
    # Armed at night, works through the morning
    powershell -File install-driver.ps1 -StartAtHHmm "08:00" -UntilHHmm "12:00"

.EXAMPLE
    # Remove it
    Unregister-ScheduledTask -TaskName "AgentWeaveAutonomousSession" -Confirm:$false
#>

param(
  [string] $Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path,
  [int]    $EveryMinutes = 5,
  [string] $UntilHHmm = "10:00",
  [string] $StartAtHHmm = "",
  [string] $TaskName = "AgentWeaveAutonomousSession",
  [ValidateSet("auto", "claude", "codex")]
  [string] $Runner = "auto",
  [ValidateSet("auto", "unattended-full-access", "workspace-contained")]
  [string] $PermissionMode = "auto"
)

$ErrorActionPreference = "Stop"

$stateFile = Join-Path $Repo ".claude\autonomous\STATE.json"
if (-not (Test-Path $stateFile)) {
  throw "No $stateFile. Run the autonomous-session skill first -- the driver resumes a session, it does not start one."
}

try { $state = Get-Content $stateFile -Raw | ConvertFrom-Json } catch {
  throw "STATE.json is not valid JSON: $($_.Exception.Message)"
}

$stateRunner = if ($state.runner) { ([string]$state.runner).ToLowerInvariant() } else { "claude" }
$statePermissionMode = if ($state.permission_mode) { ([string]$state.permission_mode).ToLowerInvariant() } else { "unattended-full-access" }

$resolvedRunner = if ($Runner -eq "auto") { $stateRunner } else { $Runner }
$resolvedPermissionMode = if ($PermissionMode -eq "auto") { $statePermissionMode } else { $PermissionMode }

if ($resolvedRunner -notin @("claude", "codex")) {
  throw "STATE.json runner '$resolvedRunner' is unsupported; expected claude or codex."
}
if ($resolvedPermissionMode -notin @("unattended-full-access", "workspace-contained")) {
  throw "STATE.json permission_mode '$resolvedPermissionMode' is unsupported."
}
if ($Runner -ne "auto" -and $state.runner -and $resolvedRunner -ne $stateRunner) {
  throw "-Runner $Runner contradicts STATE.json runner '$stateRunner'. Update the state during prep instead of overriding it at arm time."
}
if ($PermissionMode -ne "auto" -and $state.permission_mode -and $resolvedPermissionMode -ne $statePermissionMode) {
  throw "-PermissionMode $PermissionMode contradicts STATE.json permission_mode '$statePermissionMode'."
}
if ($resolvedRunner -eq "claude" -and $resolvedPermissionMode -ne "unattended-full-access") {
  throw "Claude workspace-contained mode is not implemented; use unattended-full-access or select Codex."
}

$agentCommand = Get-Command $resolvedRunner -ErrorAction SilentlyContinue
if (-not $agentCommand) { throw "$resolvedRunner CLI not found on PATH; the driver has nothing to invoke." }
$agentExecutable = $agentCommand.Source

if ($EveryMinutes -lt 1) { throw "EveryMinutes must be at least 1." }

$insideWorkTree = (& git -C $Repo rev-parse --is-inside-work-tree 2>$null)
if ($LASTEXITCODE -ne 0 -or $insideWorkTree -ne "true") {
  throw "$Repo is not a Git working tree."
}
$currentBranch = (& git -C $Repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or -not $currentBranch) { throw "Could not resolve the current Git branch." }
if ($state.branch -and $currentBranch -ne [string]$state.branch) {
  throw "Current branch '$currentBranch' does not match STATE.json branch '$($state.branch)'."
}
if ($currentBranch -notlike "autonomous/*") {
  throw "Refusing to arm on '$currentBranch'; autonomous runs require a disposable autonomous/* branch."
}

$iterationScript = Join-Path $PSScriptRoot "run-iteration.ps1"
if (-not (Test-Path $iterationScript)) { throw "Missing $iterationScript" }

# Resolve the wall-clock stop time to an absolute instant here, where "now" is known. A time that
# has already passed today means the operator meant tomorrow -- which is the overnight case, and
# the one that silently self-cancelled when the runner parsed HH:mm against today's date.
$stopInstant = [datetime]::ParseExact($UntilHHmm, "HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
if ($stopInstant -le (Get-Date)) { $stopInstant = $stopInstant.AddDays(1) }
$stopArg = $stopInstant.ToString("yyyy-MM-ddTHH:mm:ss")

# The log is written by this script while the agent it launches is committing, so a tracked log
# guarantees a dirty tree at every iteration boundary -- the one thing the skill tells iterations
# never to leave behind.
$gitignore = Join-Path $Repo ".gitignore"
$ignoreLine = ".claude/autonomous/driver.log"
if (-not (Test-Path $gitignore) -or -not (Select-String -Path $gitignore -SimpleMatch $ignoreLine -Quiet)) {
  Add-Content -Path $gitignore -Value $ignoreLine -Encoding ascii
  throw "Added '$ignoreLine' to .gitignore. Commit it, then run the installer again so the first firing starts clean."
}

$dirty = @(& git -C $Repo status --short)
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the Git working tree." }
if ($dirty.Count -gt 0) {
  throw "Refusing to arm with a dirty tree:`n$($dirty -join [Environment]::NewLine)"
}

# -NoProfile so a slow or interactive profile cannot wedge an unattended firing.
$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$iterationScript`" -Repo `"$Repo`" -StopAt `"$stopArg`" -TaskName `"$TaskName`" -Runner `"$resolvedRunner`" -PermissionMode `"$resolvedPermissionMode`" -AgentExecutable `"$agentExecutable`"" `
  -WorkingDirectory $Repo

# Same "already passed today means tomorrow" rule the stop time uses, for the same reason: an
# operator arming at 22:00 for an 08:00 start means the morning, and a trigger resolved against
# today's date would be in the past and fire immediately -- which for an unattended run is the
# difference between working while they sleep and working while they are still deciding.
if ($StartAtHHmm) {
  $startInstant = [datetime]::ParseExact($StartAtHHmm, "HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
  if ($startInstant -le (Get-Date)) { $startInstant = $startInstant.AddDays(1) }
  if ($startInstant -ge $stopInstant) {
    throw "Start $($startInstant.ToString('yyyy-MM-dd HH:mm')) is not before stop $($stopInstant.ToString('yyyy-MM-dd HH:mm')); the run would have no window."
  }
} else {
  $startInstant = (Get-Date).AddMinutes(1)
}

$trigger = New-ScheduledTaskTrigger -Once -At $startInstant `
  -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)

# WakeToRun: the machine staying awake is the one precondition the driver cannot supply itself.
# StartWhenAvailable: a firing missed because the machine was asleep runs late rather than being
# skipped -- which is NOT the same as the IgnoreNew drop below, and does not cover it.
#
# MultipleInstances IgnoreNew is what makes a short interval safe and a long one pointless: two
# iterations can never run at once, because the scheduler refuses to start the second. Note that
# the refusal is SILENT -- it writes nothing to driver.log, so a dropped firing looks in the log
# exactly like a firing that never happened. Diagnose by comparing trigger times against the
# "--- iteration start/end ---" pairs, not by looking for an error.
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -WakeToRun `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
  -Description "One autonomous-session iteration per firing, via headless $resolvedRunner. Self-unregisters past $stopArg." | Out-Null

Write-Output "Installed '$TaskName': first firing $($startInstant.ToString('yyyy-MM-dd HH:mm')), every $EveryMinutes min, stopping at $stopArg."
Write-Output "  repo:   $Repo"
Write-Output "  runner: $resolvedRunner ($agentExecutable)"
Write-Output "  mode:   $resolvedPermissionMode"
Write-Output "  log:    $Repo\.claude\autonomous\driver.log"
Write-Output ""
Write-Output "Remove with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Output "NOTE: MultipleInstances=IgnoreNew, so an iteration running longer than the interval"
Write-Output "      causes the next firing to be skipped rather than overlapping. That is deliberate."
