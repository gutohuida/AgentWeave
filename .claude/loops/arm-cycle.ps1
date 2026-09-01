<#
.SYNOPSIS
    Arm one daily window of the AgentWeave development loop.

.DESCRIPTION
    The iteration driver installed by autonomous-session UNREGISTERS ITSELF at its stop time. That
    is correct for a one-off overnight run and fatal for a daily loop: without something to arm it
    again, "every day" is a manual ritual, which is the thing the loop exists to remove.

    So each window gets a small persistent Scheduled Task that runs this script five minutes before
    the window opens. This script settles the cycle branch, writes that window's STATE file, and
    calls install-driver.ps1. It is the only thing in the arrangement that runs every single day.

    It is deliberately conservative. A dirty tree, an unresolvable branch, or a missing playbook
    leaves the window UNARMED and says why -- a skipped day costs one day, and a window armed onto
    a tree it does not understand costs the morning.

.PARAMETER Window
    day   09:00-17:00, fills: drives, spec loops, review page.
    night 23:00-07:00, fixes: implements what is approved and what is in the backlog.

.PARAMETER DryRun
    Do everything except mutate git and register the task. Prints what it would do.

.EXAMPLE
    powershell -File arm-cycle.ps1 -Window day -DryRun

.EXAMPLE
    # what the persistent Scheduled Task runs
    powershell -NoProfile -ExecutionPolicy Bypass -File arm-cycle.ps1 -Window night
#>

param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("day", "night")]
  [string] $Window,
  [string] $Repo = "",
  [string] $Model = "opus",
  [int]    $EveryMinutes = 5,
  # Override the window's standard hours. Only for a one-off catch-up run armed by hand -- the
  # daily arming tasks pass neither, and a window that quietly moved would be worse than no window.
  [string] $StartAt = "",
  [string] $Until = "",
  [switch] $DryRun
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot is EMPTY during param-default evaluation in Windows PowerShell 5.1 when the script
# has a mandatory parameter -- measured 2026-09-01. install-driver.ps1 gets away with the same
# idiom in its own param block only because it has no mandatory parameters. Resolve it here, in the
# body, where $PSScriptRoot is populated.
if (-not $Repo) { $Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

# --- window definitions ---------------------------------------------------------------------
$windows = @{
  day = @{
    StartAt   = "09:00"
    Until     = "17:00"
    TaskName  = "AgentWeaveDayLoop"
    StateFile = ".claude\autonomous\STATE-day.json"
    LogFile   = ".claude\autonomous\driver-day.log"
    Playbook  = ".claude/loops/day-window.md"
    Purpose   = "FILL. Drive the product, take findings and research candidates through the full three-round spec loop into openspec/changes/, and write the review page the operator approves from. This window does NOT implement."
  }
  night = @{
    StartAt   = "23:00"
    Until     = "07:00"
    TaskName  = "AgentWeaveNightLoop"
    StateFile = ".claude\autonomous\STATE-night.json"
    LogFile   = ".claude\autonomous\driver-night.log"
    Playbook  = ".claude/loops/night-window.md"
    Purpose   = "FIX. Read spec-queue/APPROVALS.md, then build: backlog first (unarchived changes, then open findings by severity), then APPROVED rows. Drive every change before closing its queue item. This window does NOT write new proposals."
  }
}
$w = $windows[$Window]
if ($StartAt) { $w.StartAt = $StartAt }
if ($Until)   { $w.Until   = $Until }

function Say([string] $m) { Write-Output ("[arm-{0}] {1}" -f $Window, $m) }

# git writes ordinary progress to stderr -- "Already on 'master'", "Switched to a new branch".
# Windows PowerShell wraps every stderr line as a NativeCommandError, and with
# ErrorActionPreference=Stop the FIRST one aborts this script. Measured 2026-09-01: arming died on
# `git checkout master` when it was already on master, before creating anything. run-iteration.ps1
# carries a comment about the same trap; this is the same lesson learned twice.
# Exit code is the authority, never the presence of stderr output.
# Takes an ARRAY, never loose arguments: PowerShell binds a bare `-b` as a parameter name of this
# function, not as a git flag, and the call fails before git runs. Measured 2026-09-01, one attempt
# after the stderr trap below.
function Invoke-Git {
  param([string[]] $GitArgs)
  $previous = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & git -C $Repo @GitArgs 2>&1 | ForEach-Object { Say "  git: $_" }
    return $LASTEXITCODE
  } finally { $ErrorActionPreference = $previous }
}

# --- preconditions --------------------------------------------------------------------------
$playbookPath = Join-Path $Repo ($w.Playbook -replace '/', '\')
if (-not (Test-Path $playbookPath)) { throw "Missing playbook $playbookPath. Refusing to arm a window with no instructions." }

$installer = Join-Path $PSScriptRoot "..\skills\autonomous-session\scripts\install-driver.ps1"
if (-not (Test-Path $installer)) { throw "Missing installer $installer" }
$installer = (Resolve-Path $installer).Path

$insideWorkTree = (& git -C $Repo rev-parse --is-inside-work-tree 2>$null)
if ($LASTEXITCODE -ne 0 -or $insideWorkTree -ne "true") { throw "$Repo is not a Git working tree." }

# A dirty tree is the operator's, or a window that died mid-iteration. Either way it is not ours to
# commit over, and the driver refuses to arm on one anyway. Skip the day loudly.
$dirty = @(& git -C $Repo status --short)
if ($dirty.Count -gt 0) {
  Say "REFUSING: working tree is dirty. Leaving this window unarmed."
  $dirty | ForEach-Object { Say "    $_" }
  exit 3
}

# --- settle the cycle branch ------------------------------------------------------------------
# One branch per cycle-since-last-merge, dated by when it was cut. Fresh when the previous one is
# merged (a reused fixed name accumulates the last run's scratch); continued when it is not, so a
# few unmerged days do not strand the loop on a master that is missing them.
$today = (Get-Date -Format "yyyy-MM-dd")
$targetBranch = "autonomous/$today-daily"

$existing = @(& git -C $Repo for-each-ref --format='%(refname:short)' --sort=-committerdate 'refs/heads/autonomous/*-daily')
$merged   = @(& git -C $Repo branch --merged master --format='%(refname:short)')
$openCycle = $existing | Where-Object { $merged -notcontains $_ } | Select-Object -First 1

if ($openCycle) {
  $targetBranch = $openCycle
  $cutFrom = "(continuing; previous cycle is unmerged)"
} else {
  $cutFrom = "master"
}

$currentBranch = (& git -C $Repo branch --show-current).Trim()
Say "current branch  : $currentBranch"
Say "cycle branch    : $targetBranch  $cutFrom"

if ($DryRun) {
  Say "DRY RUN: would checkout/create $targetBranch, write $($w.StateFile), and register $($w.TaskName) $($w.StartAt)-$($w.Until) every $EveryMinutes min on model $Model."
  exit 0
}

if ($currentBranch -ne $targetBranch) {
  $known = @(& git -C $Repo branch --list $targetBranch)
  if ($known.Count -gt 0) {
    if ((Invoke-Git @('checkout', $targetBranch)) -ne 0) { throw "Could not checkout existing $targetBranch." }
  } else {
    # Only if we are not already there -- `git checkout master` on master succeeds but prints to
    # stderr, which used to be fatal here.
    if ($currentBranch -ne "master") {
      if ((Invoke-Git @('checkout', 'master')) -ne 0) { throw "Could not checkout master to cut the cycle branch from." }
    }
    if ((Invoke-Git @('checkout', '-b', $targetBranch)) -ne 0) { throw "Could not create $targetBranch." }
  }
}

$parentSha = (& git -C $Repo rev-parse --short master).Trim()

# --- write this window's state ------------------------------------------------------------------
# stop_at is informational for the agent; the driver enforces the real stop from the absolute
# instant install-driver.ps1 computes. Both are written so a reader of the file alone is not misled.
$stopInstant = [datetime]::ParseExact($w.Until, "HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
if ($stopInstant -le (Get-Date)) { $stopInstant = $stopInstant.AddDays(1) }

$logName = ".claude/autonomous/$today-$Window-log.md"
$state = [ordered]@{
  purpose           = $w.Purpose
  playbook          = $w.Playbook
  runner            = "claude"
  model             = $Model
  permission_mode   = "unattended-full-access"
  branch            = $targetBranch
  parent_branch     = "master"
  parent_sha        = $parentSha
  stop_at           = $stopInstant.ToString("yyyy-MM-ddTHH:mm:sszzz")
  iteration         = 0
  log_file          = $logName
  findings_file     = "scripts/drive/FINDINGS.md"
  approvals_file    = "spec-queue/APPROVALS.md"
  current           = "compose"
  next_action       = "Read $($w.Playbook) in full, then do its 'Iteration 1 - compose the queue' section: settle the branch, read what the other window did, and write a full queue into $($w.StateFile -replace '\\','/'). Do no other work this iteration."
  queue             = @(
    [ordered]@{ id = "compose"; status = "open"; title = "Compose this window's queue from the playbook"; detail = "The playbook at $($w.Playbook) is the authority. Do not improvise a queue from memory; a fresh process has none." }
  )
  decisions_for_user = @()
  limits            = @(
    "Stay on the cycle branch. No commits, merges or rebases onto master. Never auto-merge.",
    "Nothing outward-facing: no publish, no release, no PR or issue creation, no force-push, no history rewriting. Push, do not open PRs.",
    "Nothing destructive: no deleting projects, databases, or kept reproductions.",
    "Do not browse the open web. Research is AgentWeaveResearch's job, in a process that keeps the permission classifier.",
    "Every claim is measured or labelled unverified.",
    "Decisions that are genuinely the operator's go to decisions_for_user, not guessed.",
    "Stage explicit paths, never git add -A. Never commit kimichanges.md or kimiwork.md.",
    "Tests under py -3.11, never bare python. black needs --target-version py311.",
    "Never drive against proj-5e960453 or proj-18e5d4e0. Port 8000 is the operator's real usage and must never be touched.",
    "Every real agent turn in a drive binds claude-haiku-4-5. Never leave a job enabled."
  )
}

$statePath = Join-Path $Repo $w.StateFile
New-Item -ItemType Directory -Force -Path (Split-Path $statePath) | Out-Null
# UTF-8 without a BOM: a BOM at the head of a JSON file breaks strict parsers downstream.
[System.IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
Say "wrote $($w.StateFile)"

$logPath = Join-Path $Repo ($logName -replace '/', '\')
if (-not (Test-Path $logPath)) {
  $header = "# $today $Window window`r`n`r`nNewest entry at the BOTTOM. Playbook: ``$($w.Playbook)``.`r`n`r`nArmed $(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz') on ``$targetBranch`` (parent master@$parentSha), model $Model.`r`n"
  [System.IO.File]::WriteAllText($logPath, $header, (New-Object System.Text.UTF8Encoding($false)))
  Say "opened $logName"
}

if ((Invoke-Git @('add', '--', $w.StateFile, $logName)) -ne 0) { throw "Could not stage the state file and log." }
if ((Invoke-Git @('commit', '-q', '-m', "arm($Window): $today cycle on $targetBranch")) -ne 0) {
  Say "nothing to commit (state unchanged) -- continuing."
}

# Publish the branch with an upstream, so the window's own `git push` every iteration works without
# it having to discover that there is no upstream yet. Non-fatal: an unpushed branch still works
# locally, and a window that cannot push says so in its log.
if ((Invoke-Git @('push', '-u', 'origin', $targetBranch)) -ne 0) {
  Say "WARNING: could not push $targetBranch. The window will still run, but its work is local only."
}

# --- register the driver --------------------------------------------------------------------
& powershell -NoProfile -ExecutionPolicy Bypass -File $installer `
  -Repo $Repo -EveryMinutes $EveryMinutes `
  -StartAtHHmm $w.StartAt -UntilHHmm $w.Until `
  -TaskName $w.TaskName -StateFile $w.StateFile -LogFile $w.LogFile 2>&1 | ForEach-Object { Say $_ }

if ($LASTEXITCODE -ne 0) { Say "installer exited $LASTEXITCODE -- window NOT armed."; exit $LASTEXITCODE }
Say "armed."
