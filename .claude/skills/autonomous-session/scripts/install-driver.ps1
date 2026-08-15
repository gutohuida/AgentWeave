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
    Interval between iterations. Keep it longer than a typical iteration or firings overlap;
    15 is a reasonable floor for real work.

.PARAMETER UntilHHmm
    Local wall-clock time to stop, e.g. "10:00". The task unregisters itself past this.

.PARAMETER TaskName
    Scheduled Task name. Also used to find and remove it again.

.EXAMPLE
    powershell -File install-driver.ps1 -EveryMinutes 15 -UntilHHmm "10:00"

.EXAMPLE
    # Remove it
    Unregister-ScheduledTask -TaskName "AgentWeaveAutonomousSession" -Confirm:$false
#>

param(
  [string] $Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path,
  [int]    $EveryMinutes = 15,
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

# -NoProfile so a slow or interactive profile cannot wedge an unattended firing.
$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`" -Repo `"$Repo`" -UntilHHmm `"$UntilHHmm`"" `
  -WorkingDirectory $Repo

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)

# WakeToRun: the machine staying awake is the one precondition the driver cannot supply itself.
# StartWhenAvailable: a missed firing runs late rather than being skipped silently.
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -WakeToRun `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
  -Description "One autonomous-session iteration per firing, via headless claude -p. Self-unregisters past $UntilHHmm." | Out-Null

Write-Output "Installed '$TaskName': every $EveryMinutes min, stopping after $UntilHHmm."
Write-Output "  repo:   $Repo"
Write-Output "  claude: $claude"
Write-Output "  log:    $Repo\.claude\autonomous\driver.log"
Write-Output ""
Write-Output "Remove with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Output "NOTE: MultipleInstances=IgnoreNew, so an iteration running longer than the interval"
Write-Output "      causes the next firing to be skipped rather than overlapping. That is deliberate."
