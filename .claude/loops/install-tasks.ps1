<#
.SYNOPSIS
    Install (or remove) the three PERSISTENT Scheduled Tasks of the AgentWeave daily loop.

.DESCRIPTION
    Five tasks make up the loop; only three of them are permanent.

      AgentWeaveResearch   07:10 daily   persistent   reads the web in `auto` mode, outside the repo
      AgentWeaveArmDay     08:55 daily   persistent   arms the day window
      AgentWeaveDayLoop    09:00-17:00   TRANSIENT    registered by ArmDay, unregisters itself at 17:00
      AgentWeaveArmNight   22:55 daily   persistent   arms the night window
      AgentWeaveNightLoop  23:00-07:00   TRANSIENT    registered by ArmNight, unregisters itself at 07:00

    The two working windows are transient by design: the iteration driver unregisters itself at its
    stop time, which is what stops a dead loop from firing forever. The arming tasks are what make
    the cycle daily.

    All three run as an INTERACTIVE logon, because `gh`'s keyring and the Claude credentials only
    resolve there. Consequence, inherited from the ai-digest routine that established this pattern:
    they only fire while the user is logged on. A logout or a Windows Update reboot to the lock
    screen skips a day; StartWhenAvailable catches a missed start once the session is back.

.PARAMETER Remove
    Unregister all five, including any transient window currently armed.

.EXAMPLE
    powershell -File install-tasks.ps1 -WhatIf     # show what would be registered
    powershell -File install-tasks.ps1
    powershell -File install-tasks.ps1 -Remove
#>

param(
  [switch] $Remove,
  [string] $Repo = "",
  [switch] $WhatIf
)

$ErrorActionPreference = "Stop"
if (-not $Repo) { $Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

$armScript      = Join-Path $Repo ".claude\loops\arm-cycle.ps1"
$researchScript = "$HOME\.claude\routines\agentweave-research\run.sh"
$gitBash        = "C:\Program Files\Git\bin\bash.exe"

$persistent = @("AgentWeaveResearch", "AgentWeaveArmDay", "AgentWeaveArmNight")
$transient  = @("AgentWeaveDayLoop", "AgentWeaveNightLoop")

if ($Remove) {
  foreach ($n in ($persistent + $transient)) {
    if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) {
      Unregister-ScheduledTask -TaskName $n -Confirm:$false
      Write-Output "removed  $n"
    } else {
      Write-Output "absent   $n"
    }
  }
  Write-Output ""
  Write-Output "The loop is off. Nothing will fire. Cycle branches and spec-queue/ are untouched."
  exit 0
}

# --- preconditions ----------------------------------------------------------------------------
foreach ($p in @($armScript, $researchScript, $gitBash)) {
  if (-not (Test-Path $p)) { throw "Missing $p" }
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  throw "claude CLI not found on PATH; every task here has nothing to invoke."
}

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -WakeToRun `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Interactive, so gh's keyring and the Claude credentials resolve. See the header.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

$plan = @(
  @{
    Name        = "AgentWeaveResearch"
    # 07:10, not 08:30. This task's guardrail DELETES new untracked files in the repo, and it cannot
    # tell a window's work from its own mess. A ~30-minute run started at 08:30 can still be
    # finishing at 09:10, by which time the day window is writing untracked files -- and the
    # guardrail would eat them. 07:10 sits after the night window ends (07:00) and leaves an hour of
    # margin before 09:00 even on a long run. run.sh also refuses to delete anything while the
    # checkout is on an autonomous branch, which is the mechanism behind this belt.
    At          = "07:10"
    Execute     = $gitBash
    Argument    = "-lc `"$($researchScript -replace '\\','/' -replace '^C:','/c')`""
    WorkingDir  = "$HOME\.claude\routines\agentweave-research"
    Description = "AgentWeave daily market and repo research. auto permission mode, cwd outside the repo, writes one markdown file the 09:00 window reads."
  },
  @{
    Name        = "AgentWeaveArmDay"
    At          = "08:55"
    Execute     = "powershell.exe"
    Argument    = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$armScript`" -Window day"
    WorkingDir  = $Repo
    Description = "Arms AgentWeaveDayLoop (09:00-17:00). Settles the cycle branch, writes STATE-day.json, registers the driver. Refuses a dirty tree."
  },
  @{
    Name        = "AgentWeaveArmNight"
    At          = "22:55"
    Execute     = "powershell.exe"
    Argument    = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$armScript`" -Window night"
    WorkingDir  = $Repo
    Description = "Arms AgentWeaveNightLoop (23:00-07:00). Settles the cycle branch, writes STATE-night.json, registers the driver. Refuses a dirty tree."
  }
)

foreach ($t in $plan) {
  $startInstant = [datetime]::ParseExact($t.At, "HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
  if ($startInstant -le (Get-Date)) { $startInstant = $startInstant.AddDays(1) }

  if ($WhatIf) {
    Write-Output ("WOULD REGISTER  {0}  daily {1} (first {2})" -f $t.Name, $t.At, $startInstant.ToString("yyyy-MM-dd HH:mm"))
    Write-Output ("                {0} {1}" -f $t.Execute, $t.Argument)
    continue
  }

  $action  = New-ScheduledTaskAction -Execute $t.Execute -Argument $t.Argument -WorkingDirectory $t.WorkingDir
  $trigger = New-ScheduledTaskTrigger -Daily -At $startInstant

  Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction SilentlyContinue
  Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description $t.Description | Out-Null
  Write-Output ("registered  {0}  daily {1}  (first firing {2})" -f $t.Name, $t.At, $startInstant.ToString("yyyy-MM-dd HH:mm"))
}

if (-not $WhatIf) {
  Write-Output ""
  Write-Output "The loop is on. It will not fire while you are logged out."
  Write-Output "  status : Get-ScheduledTaskInfo -TaskName AgentWeaveArmNight | fl NextRunTime,LastRunTime,LastTaskResult"
  Write-Output "  pause  : Disable-ScheduledTask -TaskName AgentWeaveArmNight"
  Write-Output "  off    : powershell -File `"$PSCommandPath`" -Remove"
  Write-Output "  logs   : $Repo\.claude\autonomous\driver-*.log  and  ~\.claude\routines\agentweave-research\logs\"
}
