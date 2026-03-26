param(
    [string]$PidFile = "data/control-room-server.pid",
    [string]$StdoutLog = "data/control-room-server.log",
    [string]$StderrLog = "data/control-room-server.err.log",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CommonScript = Join-Path $ProjectRoot "control_room_common.ps1"
$ResolvedPidFile = Join-Path $ProjectRoot $PidFile
$ResolvedStdoutLog = Join-Path $ProjectRoot $StdoutLog
$ResolvedStderrLog = Join-Path $ProjectRoot $StderrLog
$ServerUrl = "http://{0}:{1}" -f $BindHost, $Port

if (-not (Test-Path $CommonScript)) {
    throw "Control room helper not found: $CommonScript"
}

. $CommonScript

$status = Get-ControlRoomStatus `
    -Url $ServerUrl `
    -PidFile $ResolvedPidFile `
    -Port $Port `
    -StdoutLog $ResolvedStdoutLog `
    -StderrLog $ResolvedStderrLog

if ($AsJson) {
    $status | ConvertTo-Json -Depth 4
    exit 0
}

Write-Host ("Control room URL: {0}" -f $status.url)
Write-Host ("Reachable: {0}" -f $status.reachable)
Write-Host ("PID: {0}" -f ($(if ($null -ne $status.pid) { $status.pid } else { "none" })))
Write-Host ("PID alive: {0}" -f $status.pid_alive)
Write-Host ("Managed PID: {0}" -f $status.pid_owned)
Write-Host ("PID file: {0}" -f $status.pid_file)
Write-Host ("Stdout log: {0}" -f $status.stdout_log)
Write-Host ("Stderr log: {0}" -f $status.stderr_log)
