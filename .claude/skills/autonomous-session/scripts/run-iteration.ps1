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
  [string] $LogFile = ".claude\autonomous\driver.log",
  # Repo-relative model/effort routing and metering settings (Claude runner only). Absent file =
  # the previous behaviour exactly: STATE's top-level model, the user's default effort, no caps.
  [string] $PolicyFile = ".claude\loops\usage-policy.json",
  # The GitHub CLI used to read the branch's CI verdict before launching. Empty = `gh` on PATH;
  # "none" skips the read (the prompt then says the verdict is unavailable).
  [string] $GhExecutable = ""
)

$ErrorActionPreference = "Stop"

# See the matching guard in install-driver.ps1. An absolute path here joins onto $Repo a second
# time and yields a path that never exists, which this script reports as "nothing to resume" and
# then unregisters the task over -- indistinguishable, in the log, from finishing the queue.
if ([System.IO.Path]::IsPathRooted($StateFile)) { throw "-StateFile must be repo-relative, not absolute: $StateFile" }
if ([System.IO.Path]::IsPathRooted($LogFile))   { throw "-LogFile must be repo-relative, not absolute: $LogFile" }
if ([System.IO.Path]::IsPathRooted($PolicyFile)) { throw "-PolicyFile must be repo-relative, not absolute: $PolicyFile" }

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

# --- close-out briefing -------------------------------------------------------------------------
# Opt-in through STATE's `closeout` object (operator, 2026-10-10: "when the loop is going to close,
# generate [a briefing] and make it available for me"). Runs once, at whichever end comes first --
# the clock or an empty queue -- just before the task unregisters. A separate invocation because
# every iteration runs with --strict-mcp-config, which hides the claude.ai Docs connector the
# briefing is published through; and a headless process has no Artifact tool (measured 2026-10-10).
# A marker keyed by the stop instant makes it once-only: written BEFORE the invocation, so a
# briefing that fails is logged, not retried into every later firing.
function Invoke-Closeout($closeState, [string] $reason) {
  if (-not ($closeState -and $closeState.closeout)) { return }
  $leaf = [System.IO.Path]::GetFileNameWithoutExtension($StateFile)
  $suffix = if ($leaf -match '^STATE-(.+)$') { "-" + $Matches[1] } else { "" }
  $marker = Join-Path (Split-Path (Join-Path $Repo $StateFile)) (".closeout" + $suffix)
  if ((Test-Path $marker) -and ((Get-Content $marker -Raw).Trim() -eq $StopAt)) {
    Write-Log "Close-out briefing already ran for this window - skipping."
    return
  }
  [System.IO.File]::WriteAllText($marker, $StopAt, $script:LogEncoding)
  $closeModel = if ($closeState.closeout.model) { [string]$closeState.closeout.model } else { "sonnet" }
  $closeSkill = if ($closeState.closeout.skill) { [string]$closeState.closeout.skill } else { ".claude/skills/night-briefing/SKILL.md" }
  $stateRel = $StateFile -replace '\\', '/'
  $closePrompt = "The autonomous loop driven by $stateRel has ended ($reason). Write its close-out briefing: " +
    "read $closeSkill and follow its 'Close-out mode' section exactly, with $stateRel as the state file. " +
    "The operator is away; nobody can answer a question, and you must not merge, fix or re-run anything."
  Write-Log "--- close-out briefing start (model=$closeModel, $reason) ---"
  $prevPref = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $out = New-Object System.Collections.Generic.List[string]
  try {
    $env:AW_AUTONOMOUS = "1"
    try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}
    Set-Location $Repo
    & $AgentExecutable -p $closePrompt --model $closeModel --output-format json --permission-mode bypassPermissions --max-budget-usd 10 2>&1 | ForEach-Object {
      if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Log ([string]$_) } else { $out.Add([string]$_) }
    }
    $closeCode = $LASTEXITCODE
  } finally { $ErrorActionPreference = $prevPref }
  $parsedClose = $null
  try { $parsedClose = ($out -join "`n") | ConvertFrom-Json -ErrorAction Stop } catch {}
  if ($parsedClose) {
    foreach ($line in ([string]$parsedClose.result -split "`r?`n")) { Write-Log $line }
    Write-Log ('--- close-out briefing end (exit {0}, ${1:N2} list) ---' -f $closeCode, [double]$parsedClose.total_cost_usd)
  } else {
    foreach ($line in $out) { Write-Log $line }
    Write-Log "--- close-out briefing end (exit $closeCode, no result JSON) ---"
  }
}

# --- stop condition -----------------------------------------------------------------------------
$stopAtInstant = [datetime]::Parse($StopAt, [System.Globalization.CultureInfo]::InvariantCulture)
if ((Get-Date) -ge $stopAtInstant) {
  $closeState = $null
  try { $closeState = Get-Content (Join-Path $Repo $StateFile) -Raw | ConvertFrom-Json } catch {}
  Invoke-Closeout $closeState "the clock ran out at $StopAt"
  Write-Log "Past $stopAtInstant - unregistering '$TaskName' and stopping."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

$stateFilePath = Join-Path $Repo $StateFile
# Forward slashes, because the prompt below is read by an agent that will type this path into
# tools where a backslash is an escape.
$stateRelative = $StateFile -replace '\\', '/'

# The branch lock, derived from the state file so this script needs no window parameter and the
# legacy single-window layout keeps working: STATE-day.json -> .heartbeat-day, STATE.json ->
# .heartbeat. Two windows sharing one lock would spend the day standing down for each other.
# Computed here rather than inside the heartbeat gate below, because the prompt names it even when
# the gate is disabled with -HeartbeatGraceMinutes 0.
$stateLeaf = [System.IO.Path]::GetFileNameWithoutExtension($StateFile)
$lockSuffix = if ($stateLeaf -match '^STATE-(.+)$') { "-" + $Matches[1] } else { "" }
$heartbeatPath = Join-Path (Split-Path $stateFilePath) (".heartbeat" + $lockSuffix)
$lockRelative = ((Split-Path $stateRelative -Parent) -replace '\\', '/') + "/.heartbeat" + $lockSuffix

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
  Invoke-Closeout $state "the queue finished"
  Write-Log "STATE.json has no next_action - queue complete. Unregistering '$TaskName'."
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  exit 0
}

# --- stand down for a live session --------------------------------------------------------------
# Deliberately does NOT unregister: the session this is backing up may die at any moment, and the
# next firing is what picks the work up. Standing down is a skip, not a stop.
#
# The lock is an untracked sidecar next to the state file -- `.heartbeat-day`, `.heartbeat-night` --
# holding one ISO instant and nothing else. It used to be the `last_heartbeat` field inside the
# TRACKED state json, which meant claiming and releasing the branch dirtied the tree and had to be
# committed: half of every day's commits were that protocol, and none of them carried work. Nothing
# ever required the lock to be in git. This driver reads it off the local disk, and a lock shared
# through a remote would be actively wrong -- it guards one working tree, not the repository.
#
# The old field is still honoured when the sidecar is absent, so a state file written by the
# previous arrangement (or by hand) still holds the branch instead of silently losing the lock.
if ($HeartbeatGraceMinutes -gt 0) {
  $heartbeat = $null
  $heartbeatSource = ""
  if (Test-Path $heartbeatPath) {
    try {
      $heartbeat = (Get-Content $heartbeatPath -Raw).Trim()
      $heartbeatSource = "sidecar"
    } catch { Write-Log "Could not read $heartbeatPath - falling back to the state file." }
  }
  if (-not $heartbeat) {
    try {
      $heartbeat = (Get-Content $stateFilePath -Raw | ConvertFrom-Json).last_heartbeat
      if ($heartbeat) { $heartbeatSource = "legacy state field" }
    } catch {
      Write-Log "STATE.json did not parse - proceeding, since a backup that defers to a file it cannot read is no backup."
    }
  }
  if ($heartbeat) {
    Write-Log "Branch lock read from the $heartbeatSource."
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

# --- usage policy: routing, caps, and the limit cool-down ---------------------------------------
# Every call of both windows ran on Opus at high effort until 2026-09-15, when the weekly limit
# stopped fitting. The policy file routes each queue item to a model and an effort (spec rounds on
# Opus, builds on Sonnet -- operator, 2026-09-15). Per field, the first source that sets it wins:
# the item's own model/effort, then the first policy rule whose regex matches the item id, then the
# policy default, then STATE's top-level model. Claude runner only; Codex keeps STATE's model.
$policy = $null
$policyPath = Join-Path $Repo $PolicyFile
if ($Runner -eq "claude" -and (Test-Path $policyPath)) {
  try { $policy = Get-Content $policyPath -Raw | ConvertFrom-Json } catch {
    Write-Log "$PolicyFile did not parse - refusing to launch on a route nobody chose."
    exit 2
  }
}
$windowName = if ($lockSuffix) { $lockSuffix.TrimStart('-') } else { "default" }
$limitSidecar = Join-Path (Split-Path $stateFilePath) (".limit-hit" + $lockSuffix)

# A usage-limit refusal writes a cool-down instant. Until it passes, a firing exits here without a
# model call: firing into a spent limit every five minutes buys nothing, and a 5-hour limit resets
# inside a window, so the window must pause rather than unregister.
if (Test-Path $limitSidecar) {
  try {
    $retryAfter = [datetimeoffset]::Parse(((Get-Content $limitSidecar -TotalCount 1).Trim()), [System.Globalization.CultureInfo]::InvariantCulture)
    if ([datetimeoffset]::Now -lt $retryAfter) {
      Write-Log ("Usage limit cool-down until {0} - not launching." -f $retryAfter.ToString("yyyy-MM-ddTHH:mm:sszzz"))
      exit 0
    }
  } catch { Write-Log "Unreadable $limitSidecar - ignoring it." }
}

$currentItemId = if ($state.current) { ([string]$state.current).Trim() } else { "" }
$currentItem = $null
if ($currentItemId -and $state.queue) {
  $currentItem = @($state.queue) | Where-Object { $_.id -eq $currentItemId } | Select-Object -First 1
}
$routeModel = ""; $modelFrom = ""; $routeEffort = ""; $effortFrom = ""
if ($currentItem -and $currentItem.model)  { $routeModel = ([string]$currentItem.model).Trim();   $modelFrom = "item" }
if ($currentItem -and $currentItem.effort) { $routeEffort = ([string]$currentItem.effort).Trim(); $effortFrom = "item" }
if ($policy) {
  $rule = $null
  if ($currentItemId) {
    foreach ($candidate in @($policy.routing)) {
      if (-not ($candidate -and $candidate.match)) { continue }
      try { $hit = $currentItemId -match [string]$candidate.match } catch {
        Write-Log "Policy rule /$($candidate.match)/ is not a valid regex - skipping it."
        continue
      }
      if ($hit) { $rule = $candidate; break }
    }
  }
  if ($rule) {
    if (-not $modelFrom -and $rule.model)   { $routeModel = ([string]$rule.model).Trim();   $modelFrom = "rule" }
    if (-not $effortFrom -and $rule.effort) { $routeEffort = ([string]$rule.effort).Trim(); $effortFrom = "rule" }
  }
  if ($policy.default) {
    if (-not $modelFrom -and $policy.default.model)   { $routeModel = ([string]$policy.default.model).Trim();   $modelFrom = "default" }
    if (-not $effortFrom -and $policy.default.effort) { $routeEffort = ([string]$policy.default.effort).Trim(); $effortFrom = "default" }
  }
}
if (-not $modelFrom -and $stateModel) { $routeModel = $stateModel; $modelFrom = "state" }
if ($routeEffort -and @("low", "medium", "high", "xhigh", "max") -notcontains $routeEffort.ToLowerInvariant()) {
  Write-Log "Effort '$routeEffort' (from $effortFrom) is not a Claude effort level - dropping it."
  $routeEffort = ""; $effortFrom = ""
}

# --- the branch's CI verdict ---------------------------------------------------------------------
# Read here, by the driver, and put at the top of the prompt. The playbooks told every firing to
# read it first, and three nights in a row the firings did not: measured 2026-09-22 (16 commits onto
# red), 2026-09-29 (40 consecutive red pushes) and 2026-10-02 (26). A rule the agent has to remember
# failed three times; a verdict already in front of it cannot be skipped. The firing still decides
# how to fix a red branch -- the driver only reports, it does not reschedule (operator, 2026-10-03).
#
# One `gh run list` call in a job with a timeout, so an unreachable GitHub costs a minute rather than
# hanging the window. Any failure to read degrades to "unavailable", never to a refusal to launch.
$failWords = @("failure", "cancelled", "timed_out", "startup_failure", "action_required")
function Get-ShaVerdict($runs) {
  if (-not $runs) { return "no run" }
  $unfinished = @($runs | Where-Object { $_.status -ne "completed" })
  if ($unfinished.Count -gt 0) { return [string]$unfinished[0].status }
  foreach ($w in $failWords) { if (@($runs | Where-Object { $_.conclusion -eq $w }).Count -gt 0) { return $w } }
  $other = @($runs | Where-Object { $_.conclusion -ne "success" })
  if ($other.Count -gt 0) { return [string]$other[0].conclusion }
  return "success"
}
function Get-CiBlock {
  $ErrorActionPreference = "Continue"   # a native stderr line must degrade, not throw
  if ($GhExecutable -eq "none") { return @{ word = "unavailable"; red = $false; text = "the driver was told not to read it" } }
  $gh = $GhExecutable
  if (-not $gh) {
    $ghCommand = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $ghCommand) { return @{ word = "unavailable"; red = $false; text = "gh is not on PATH" } }
    $gh = $ghCommand.Source
  }
  $tip = (& git -C $Repo rev-parse HEAD 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $tip) { return @{ word = "unavailable"; red = $false; text = "the branch has no commit" } }
  $tip = ([string]$tip).Trim()
  $job = Start-Job -ScriptBlock {
    param($exe, $repo, $branch)
    Set-Location $repo
    & $exe run list --branch $branch --limit 20 --json databaseId,headSha,status,conclusion,createdAt 2>$null
  } -ArgumentList $gh, $Repo, $currentBranch
  $done = Wait-Job $job -Timeout 60
  if (-not $done) {
    Stop-Job $job; Remove-Job $job -Force
    return @{ word = "unavailable"; red = $false; text = "gh run list did not answer within 60 s" }
  }
  $raw = (Receive-Job $job -ErrorAction SilentlyContinue | Out-String)
  Remove-Job $job -Force
  # PowerShell 5.1's ConvertFrom-Json emits a JSON array as ONE object; piping it on unrolls it.
  try { $parsed = $raw | ConvertFrom-Json -ErrorAction Stop; $runs = @($parsed | ForEach-Object { $_ }) } catch {
    return @{ word = "unavailable"; red = $false; text = "gh run list returned no readable JSON" }
  }
  $runs = @($runs | Sort-Object { [string]$_.createdAt } -Descending)
  $tipShort = $tip.Substring(0, [Math]::Min(7, $tip.Length))
  $tipWord = Get-ShaVerdict @($runs | Where-Object { $_.headSha -eq $tip })
  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("- Branch tip ${tipShort}: **$tipWord**.")
  $hung = @($runs | Where-Object { $_.headSha -eq $tip -and $_.status -ne "completed" -and $_.createdAt -and
    ([datetimeoffset]::Now - [datetimeoffset]::Parse([string]$_.createdAt, [System.Globalization.CultureInfo]::InvariantCulture)).TotalMinutes -gt 60 })
  if ($hung.Count -gt 0) { $lines.Add("- The tip's run $($hung[0].databaseId) has been unfinished for over 60 minutes: treat it as HUNG (F394), not pending.") }
  $redWord = ""; $redSha = ""; $redRun = ""
  if ($failWords -contains $tipWord) {
    $redWord = $tipWord; $redSha = $tipShort
    $redRun = [string](@($runs | Where-Object { $_.headSha -eq $tip -and $_.conclusion -eq $tipWord })[0].databaseId)
  } elseif ($tipWord -ne "success") {
    # The tip is still running (or never ran). A window that pushes every ~15 minutes against a
    # ~20-minute CI run sees an unfinished tip most of the time, so the newest finished verdict is
    # the one that says whether the branch is red.
    foreach ($sha in @($runs | ForEach-Object { $_.headSha } | Select-Object -Unique)) {
      if ($sha -eq $tip) { continue }
      $shaRuns = @($runs | Where-Object { $_.headSha -eq $sha })
      if (@($shaRuns | Where-Object { $_.status -ne "completed" }).Count -gt 0) { continue }
      $w = Get-ShaVerdict $shaRuns
      $short = ([string]$sha).Substring(0, [Math]::Min(7, ([string]$sha).Length))
      $lines.Add("- Newest finished run: ${short}: **$w**.")
      if ($failWords -contains $w) {
        $redWord = $w; $redSha = $short
        $redRun = [string](@($shaRuns | Where-Object { $_.conclusion -eq $w })[0].databaseId)
      }
      break
    }
  }
  return @{ word = $tipWord; red = [bool]$redWord; text = ($lines -join "`n"); redWord = $redWord; redSha = $redSha; redRun = $redRun; tip = $tipShort }
}
try { $ci = Get-CiBlock } catch { $ci = @{ word = "unavailable"; red = $false; text = "reading it threw: $_" } }
if ($ci.word -eq "unavailable") {
  $ciPrompt = "CI verdict: unavailable to the driver ($($ci.text)). Read it yourself with " +
    "``gh run list --branch $currentBranch --limit 5`` before next_action, and write gh's word in your log entry's first line."
  Write-Log "CI verdict unavailable: $($ci.text)"
} else {
  $ciPrompt = "CI, read by the driver just before launching you (``gh run list --branch $currentBranch``):`n" + $ci.text + "`n" +
    "Write the tip's word, exactly as above, in your log entry's first line."
  if ($ci.red) {
    $ciPrompt += "`n`n**CI is red ($($ci.redWord) on $($ci.redSha)). Fixing it is this firing's unit of work and replaces " +
      "next_action.** Read the failing job with ``gh run view $($ci.redRun) --log-failed`` and classify from its FAILED/ERROR " +
      "lines. Only if a commit pushed after $($ci.redSha) already fixes exactly that failure, say so in the log and do " +
      "next_action instead. Never push product work onto a branch you know is red."
  }
  Write-Log ("CI: tip {0} {1}{2}" -f $ci.tip, $ci.word, $(if ($ci.red) { " - RED ($($ci.redWord) on $($ci.redSha), run $($ci.redRun)); prompt says fix first" } else { "" }))
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
5. Append a log entry, rewrite STATE.json (next_action, queue, iteration), then commit and push.
   Never end an iteration with a dirty tree.
6. When the queue is finished, set next_action to null. That is what makes the driver unregister
   itself instead of spending a whole model invocation per firing to rediscover there is nothing
   to do. A prose next_action that says "stand down" does not do this and costs a full invocation
   every time it fires.

The branch lock is the untracked file <<LOCK>>. The driver that launched you writes it before
you start and deletes it after you exit -- do not write, refresh or delete it yourself, and do not
write a `last_heartbeat` field into STATE.json; that field is retired.

Stamp every timestamp from PowerShell (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz') or Python's
datetime.now().astimezone(). Git Bash `date` on this machine prints UTC but labels it +0100.

Usage is budgeted: this subscription's weekly limit is shared with the operator. Read files by
section - Grep for the heading you need, then Read with offset/limit - not whole; that includes the
log, whose newest entry you locate by its heading. Keep `current` equal to the queue id that
next_action names: the driver chooses the next firing's model and effort from that item. Keep each
queue item's detail short and put results in the log, not in STATE.json. Run subagents in the
foreground.

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
                  Replace('<<LOG>>', $stateLogFile).
                  Replace('<<LOCK>>', $lockRelative)

# The CI verdict goes first, ahead of the standing instructions, because it can replace next_action.
# Added after the token expansion so nothing gh returned can be mistaken for a token.
$prompt = $ciPrompt + "`n`n" + $prompt

Set-Location $Repo
$startedIso = Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz"

# The driver holds the branch lock for exactly the child's lifetime. It used to ask the agent to
# write, refresh and delete it; measured 2026-09-29 night, 42 firings in a row never touched it and
# every one logged "Heartbeat is ~1,800 min old - assuming the session died", reading a sidecar
# left on 09-28 at 23:51. The gate above was doing nothing. A driver killed mid-run leaves the lock
# behind, and the next firing takes over once it is older than -HeartbeatGraceMinutes; a firing
# that is merely long is already covered by the task's MultipleInstances=IgnoreNew.
try { [System.IO.File]::WriteAllText($heartbeatPath, $startedIso + [Environment]::NewLine, $script:LogEncoding) } catch {
  Write-Log "Could not write the branch lock $lockRelative - continuing without it: $_"
}
if ($Runner -eq "claude") {
  $routeLabel = "model={0}({1}) effort={2}({3}) item={4}" -f $(if ($routeModel) { $routeModel } else { "cli-default" }), $modelFrom,
    $(if ($routeEffort) { $routeEffort } else { "cli-default" }), $effortFrom, $(if ($currentItemId) { $currentItemId } else { "-" })
  Write-Log "--- iteration start ($Runner, $PermissionMode, $routeLabel) ---"
} else {
  Write-Log "--- iteration start ($Runner, $PermissionMode) ---"
}

# Nobody is present to answer a prompt. The full-access modes below are deliberately explicit:
# branch isolation protects Git history, but it is not a machine sandbox. Use this driver only
# after prep has established the limits and the operator has accepted that posture.
# Native CLIs legitimately write progress to stderr. Windows PowerShell wraps those lines as
# NativeCommandError records; with ErrorActionPreference=Stop, the first one aborts the wrapper.
# Keep strict handling for the driver itself, but allow the child process to stream both channels
# and use its exit code as the authority.
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$claudeStdout = New-Object System.Collections.Generic.List[string]
try {
  if ($Runner -eq "claude") {
    # --output-format json makes the run report its own usage (total_cost_usd, and modelUsage,
    # which unlike `usage` includes subagents). The price is that nothing streams: stdout is one
    # JSON line at the end, so it is collected here and its `result` text logged afterwards.
    $claudeArgs = @("-p", $prompt)
    if ($routeModel)  { $claudeArgs += @("--model", $routeModel) }
    if ($routeEffort) { $claudeArgs += @("--effort", $routeEffort) }
    $claudeArgs += @("--output-format", "json", "--permission-mode", "bypassPermissions")
    if ($policy -and $policy.max_budget_usd_per_iteration) {
      $claudeArgs += @("--max-budget-usd", ([string]$policy.max_budget_usd_per_iteration))
    }
    if ($policy -and $policy.claude_extra_args) { $claudeArgs += @($policy.claude_extra_args | ForEach-Object { [string]$_ }) }
    # AW_AUTONOMOUS is the contract with .claude/hooks: guards that must never touch an
    # interactive session key on it.
    $env:AW_AUTONOMOUS = "1"
    if ($policy -and $policy.env) {
      foreach ($pair in $policy.env.PSObject.Properties) { Set-Item -Path ("env:" + $pair.Name) -Value ([string]$pair.Value) }
    }
    # Decode the child's stdout as UTF-8, or every non-ASCII character in the result is mangled
    # through the OEM codepage on its way into the log.
    try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}
    & $AgentExecutable @claudeArgs 2>&1 | ForEach-Object {
      if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Log ([string]$_) } else { $claudeStdout.Add([string]$_) }
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
  Remove-Item $heartbeatPath -ErrorAction SilentlyContinue
}

if ($Runner -ne "claude") {
  Write-Log "--- iteration end (exit $code) ---"
  exit $code
}

# --- the result, the ledger, and the limit ------------------------------------------------------
$autonomousDir = Split-Path $stateFilePath
$rawOut = ($claudeStdout -join "`n")
try { [System.IO.File]::WriteAllText((Join-Path $autonomousDir (".last-result" + $lockSuffix + ".json")), $rawOut, $script:LogEncoding) } catch {}

$result = $null
foreach ($candidateJson in @($rawOut, ($claudeStdout | Where-Object { $_.TrimStart().StartsWith("{") } | Select-Object -Last 1))) {
  if (-not $candidateJson) { continue }
  try {
    $parsed = $candidateJson | ConvertFrom-Json -ErrorAction Stop
    if ($parsed -and $parsed.type -eq "result") { $result = $parsed; break }
  } catch {}
}
if ($result) {
  foreach ($line in ([string]$result.result -split "`r?`n")) { Write-Log $line }
} else {
  foreach ($line in $claudeStdout) { Write-Log $line }
}

# The operator's statusline persists the plan's real rate-limit percentages to this file whenever
# an interactive session renders; headless runs never render one. Carried into the ledger so a
# week of rows can be read against the weekly bar.
#
# Nothing renders a statusline overnight, so the file goes stale: measured 2026-09-29 night, all 42
# rows carried the 19:20 snapshot (7-day 29%) while real use climbed to 37% by morning. A stale
# snapshot is recorded as stale -- its instant kept in `snapshot_captured_at`, the percentages
# dropped -- rather than passed off as a reading taken during this iteration.
$snapshot = $null
$snapshotCapturedAt = $null
$snapshotPath = Join-Path $env:USERPROFILE ".claude\usage-snapshot.json"
if (Test-Path $snapshotPath) { try { $snapshot = Get-Content $snapshotPath -Raw | ConvertFrom-Json } catch {} }
if ($snapshot) {
  try {
    $snapshotCapturedAt = [string]$snapshot.captured_at
    $snapshotAge = ([datetimeoffset]::Parse($startedIso, [System.Globalization.CultureInfo]::InvariantCulture) -
      [datetimeoffset]::Parse($snapshotCapturedAt, [System.Globalization.CultureInfo]::InvariantCulture)).TotalMinutes
    if ($snapshotAge -gt 30) { $snapshot = $null }
  } catch { $snapshot = $null }
}

$modelUsage = [ordered]@{}
if ($result -and $result.modelUsage) {
  foreach ($pair in $result.modelUsage.PSObject.Properties) {
    $u = $pair.Value
    $modelUsage[$pair.Name] = [ordered]@{
      cost_usd = $u.costUSD; input = $u.inputTokens; output = $u.outputTokens
      cache_read = $u.cacheReadInputTokens; cache_write = $u.cacheCreationInputTokens
    }
  }
}
$row = [ordered]@{
  started          = $startedIso
  ended            = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
  window           = $windowName
  state_file       = $stateRelative
  branch           = $currentBranch
  iteration        = $state.iteration
  item             = $currentItemId
  model            = $routeModel
  model_from       = $modelFrom
  effort           = $routeEffort
  effort_from      = $effortFrom
  exit_code        = $code
  parsed           = [bool]$result
  subtype          = $(if ($result) { $result.subtype } else { $null })
  is_error         = $(if ($result) { [bool]$result.is_error } else { $null })
  api_error_status = $(if ($result) { $result.api_error_status } else { $null })
  num_turns        = $(if ($result) { $result.num_turns } else { $null })
  duration_ms      = $(if ($result) { $result.duration_ms } else { $null })
  total_cost_usd   = $(if ($result) { $result.total_cost_usd } else { $null })
  subagents        = $(if ($result -and $result.subagent_stats) { $result.subagent_stats.spawned } else { $null })
  model_usage      = $modelUsage
  snapshot         = $snapshot
  snapshot_captured_at = $snapshotCapturedAt
  ci_verdict       = $ci.word
  ci_red           = [bool]$ci.red
}
try {
  [System.IO.File]::AppendAllText((Join-Path $autonomousDir "usage-ledger.jsonl"), (($row | ConvertTo-Json -Compress -Depth 8) + [Environment]::NewLine), $script:LogEncoding)
} catch { Write-Log "Could not append to usage-ledger.jsonl: $_" }

# A usage-limit refusal pauses the window rather than ending it (see the cool-down gate above).
# Matched only on an error result, so a model that merely writes about limits cannot trip it.
$limitText = ""
if ($result -and $result.is_error -and ([string]$result.result -match '(?i)hit your .{0,40}limit')) {
  $limitText = [string]$result.result
} elseif (-not $result) {
  $limitText = [string]($claudeStdout | Where-Object { $_ -match '(?i)hit your .{0,40}limit' } | Select-Object -First 1)
}
if ($limitText) {
  $cooldown = 60
  if ($policy -and $policy.limit_cooldown_minutes) { $cooldown = [int]$policy.limit_cooldown_minutes }
  $retryAt = (Get-Date).AddMinutes($cooldown).ToString("yyyy-MM-ddTHH:mm:sszzz")
  [System.IO.File]::WriteAllText($limitSidecar, $retryAt + [Environment]::NewLine + $limitText.Trim() + [Environment]::NewLine, $script:LogEncoding)
  Write-Log "USAGE LIMIT HIT - pausing this window until $retryAt instead of firing into it: $($limitText.Trim())"
} elseif ($result -and (Test-Path $limitSidecar)) {
  Remove-Item $limitSidecar -ErrorAction SilentlyContinue
}

$costLabel = if ($result -and $null -ne $result.total_cost_usd) { '${0:N2} list' -f [double]$result.total_cost_usd } else { "cost unknown" }
$turnsLabel = if ($result) { "$($result.num_turns) turns, $($result.subtype)" } else { "no result JSON" }
Write-Log "--- iteration end (exit $code, $costLabel, $turnsLabel) ---"
exit $code
