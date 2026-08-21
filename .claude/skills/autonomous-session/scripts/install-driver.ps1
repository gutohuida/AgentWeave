<#
.SYNOPSIS
    Install a Windows Scheduled Task that drives an autonomous session with headless `claude -p`.

.DESCRIPTION
    This is the only local driver that survives the interactive session ending.

    `ScheduleWakeup` and `CronCreate` both stop when the Claude Code session goes away -- measured
    on 2026-08-15, where an overnight run was asked for nine hours and got forty minutes. The
    machine had not slept and had not rebooted; the session simply stopped existing, taking every
    scheduled wakeup with it.

    A Scheduled Task does not care. Each firing is a brand new `claude -p` process that reads
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

.EXAMPLE
    powershell -File install-driver.ps1 -EveryMinutes 5 -UntilHHmm "10:00"

.EXAMPLE
    # Remove it
    Unregister-ScheduledTask -TaskName "AgentWeaveAutonomousSession" -Confirm:$false
#>

param(
  [string] $Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path,
  [int]    $EveryMinutes = 5,
  [string] $UntilHHmm = "10:00",
  [string] $TaskName = "AgentWeaveAutonomousSession"
)

$ErrorActionPreference = "Stop"

$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $claude) { throw "claude CLI not found on PATH; the driver has nothing to invoke." }

$stateFile = Join-Path $Repo ".claude\autonomous\STATE.json"
if (-not (Test-Path $stateFile)) {
  throw "No $stateFile. Run the autonomous-session skill first -- the driver resumes a session, it does not start one."
}

$runner = Join-Path $PSScriptRoot "run-iteration.ps1"
if (-not (Test-Path $runner)) { throw "Missing $runner" }

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
  Write-Output "Added '$ignoreLine' to .gitignore (the driver writes it mid-commit)."
}

# -NoProfile so a slow or interactive profile cannot wedge an unattended firing.
$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`" -Repo `"$Repo`" -StopAt `"$stopArg`"" `
  -WorkingDirectory $Repo

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
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
  -Description "One autonomous-session iteration per firing, via headless claude -p. Self-unregisters past $stopArg." | Out-Null

Write-Output "Installed '$TaskName': every $EveryMinutes min, stopping at $stopArg."
Write-Output "  repo:   $Repo"
Write-Output "  claude: $claude"
Write-Output "  log:    $Repo\.claude\autonomous\driver.log"
Write-Output ""
Write-Output "Remove with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Output "NOTE: MultipleInstances=IgnoreNew, so an iteration running longer than the interval"
Write-Output "      causes the next firing to be skipped rather than overlapping. That is deliberate."
