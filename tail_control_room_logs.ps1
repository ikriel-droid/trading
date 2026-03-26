param(
    [ValidateSet("stdout", "stderr")]
    [string]$Stream = "stdout",
    [string]$StdoutLog = "data/control-room-server.log",
    [string]$StderrLog = "data/control-room-server.err.log",
    [int]$Lines = 80,
    [switch]$Follow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TargetPath = if ($Stream -eq "stderr") { $StderrLog } else { $StdoutLog }
$ResolvedTargetPath = Join-Path $ProjectRoot $TargetPath

if (-not (Test-Path $ResolvedTargetPath)) {
    Write-Host ("Log file does not exist yet: {0}" -f $ResolvedTargetPath)
    exit 0
}

if ($Follow) {
    Get-Content -Path $ResolvedTargetPath -Tail $Lines -Wait
    exit 0
}

Get-Content -Path $ResolvedTargetPath -Tail $Lines
