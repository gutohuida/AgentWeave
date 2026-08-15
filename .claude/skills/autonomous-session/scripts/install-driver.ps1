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
    Local wall-clock time to stop, e.g. "10:00". Resolved here to an absolute instant; a time
    already past today is taken to mean tomorrow. The task unregisters itself past it.

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
# StartWhenAvailable: a missed firing runs late rather than being skipped silently.
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
