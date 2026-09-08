<#
.SYNOPSIS
    Copy the Claude Code transcript corpus somewhere it will not be deleted.

.DESCRIPTION
    The harness deletes transcripts on a rolling window -- measured 2026-09-08 at roughly 29 days
    with a hard cliff: 2,091 `.jsonl` files, the oldest last written 2026-08-09, while at least 51
    earlier sessions evidenced by committed handoffs are already gone. This script keeps the bytes.

    **It copies. It does not read, parse, interpret, or analyse anything.** That distinction is the
    whole reason it exists rather than a resident tailer: the operator's decision of 2026-09-08
    (`spec-queue/DECISIONS.md`, OV-6 + OV-3) kept Witness a command rather than a daemon, on the
    grounds that a process which *reads and interprets* transcripts unattended is a larger
    disclosure than OV-1's consent covered. A file copy makes no judgement, produces no output that
    could be wrong, and fails by leaving a file missing rather than by silently misreading one.

    **Never /MIR and never /PURGE.** Deleting from the destination is the one thing this must not
    do -- the source deletes on its own schedule and the archive exists precisely to outlive it. A
    file that vanishes upstream stays here. Anyone editing the robocopy line: adding a mirror flag
    turns this script into the problem it was written to solve.

.NOTES
    Known limitation, stated rather than papered over: this keeps one copy per path, not versions.
    A source file that is rewritten *smaller* would overwrite a larger archived copy. Transcripts
    are append-only in practice, so this has not been observed -- but it is the failure mode to
    watch, and the stamp file below is what would make it visible (a total_bytes that falls).

    Destination defaults outside both the repository and `~/.claude`, so no tool that cleans either
    one can reach it, and nothing here is ever committed.

.EXAMPLE
    py -3.11 -c "print()"  # (no Python involved; this is PowerShell)
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/snapshot-corpus.ps1
#>
[CmdletBinding()]
param(
    [string]$Source      = (Join-Path $env:USERPROFILE '.claude\projects'),
    [string]$Destination = (Join-Path $env:USERPROFILE 'claude-corpus-archive\projects'),
    [string]$LogPath     = (Join-Path $env:USERPROFILE 'claude-corpus-archive\snapshot.log')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Source)) {
    Write-Error "Source corpus not found: $Source"
    exit 2
}

$stampDir = Split-Path -Parent $LogPath
if (-not (Test-Path -LiteralPath $stampDir)) {
    New-Item -ItemType Directory -Path $stampDir -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $Destination)) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
}

$started = Get-Date

# /E     include subdirectories, empty ones too
# /XO    skip a source file OLDER than the archived copy -- an extra guard against going backwards
# /R:1   one retry, /W:1 one second: a locked live file is retried next run, never blocks this one
# /NFL /NDL /NP /NJH   keep the appended log to a summary per run rather than 2,600 filenames
#
# Deliberately absent: /MIR, /PURGE. See the header.
$robo = @($Source, $Destination, '/E', '/XO', '/R:1', '/W:1', '/NFL', '/NDL', '/NP', '/NJH',
          "/LOG+:$LogPath")
& robocopy.exe @robo | Out-Null
$roboExit = $LASTEXITCODE

# Robocopy's exit code is a bit field: 0-7 are success (0 = nothing to do, 1 = files copied,
# 2 = extras present in destination -- which for this script is the normal, desired state, since
# the source deletes and we do not). 8 and above is a real failure.
$ok = ($roboExit -lt 8)

$archived = Get-ChildItem -LiteralPath $Destination -Recurse -File -ErrorAction SilentlyContinue
$sourceFiles = Get-ChildItem -LiteralPath $Source -Recurse -File -ErrorAction SilentlyContinue

$stamp = [ordered]@{
    finished_at        = (Get-Date).ToString('o')
    duration_seconds   = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    source             = $Source
    destination        = $Destination
    robocopy_exit      = $roboExit
    ok                 = $ok
    source_files       = $sourceFiles.Count
    archived_files     = $archived.Count
    archived_bytes     = ($archived | Measure-Object -Property Length -Sum).Sum
    # The number this exists for: files the archive holds that the harness has already deleted.
    # It should only ever grow. If it is 0 after the corpus has aged past the window, the copy is
    # not running, whatever the exit code says.
    kept_beyond_source = [math]::Max(0, $archived.Count - $sourceFiles.Count)
}

$stampPath = Join-Path $stampDir 'snapshot-stamp.json'
$stamp | ConvertTo-Json | Out-File -FilePath $stampPath -Encoding utf8

"[{0}] exit={1} archived={2} files, {3:N2} GB, kept_beyond_source={4}" -f `
    $stamp.finished_at, $roboExit, $stamp.archived_files,
    ($stamp.archived_bytes / 1GB), $stamp.kept_beyond_source

if (-not $ok) {
    Write-Error "robocopy failed with exit code $roboExit -- see $LogPath"
    exit 1
}
exit 0
