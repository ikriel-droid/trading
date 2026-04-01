param(
    [string]$Config = "config.example.json",
    [string]$State = "data/paper-state.json",
    [string]$SelectorState = "data/selector-state.json",
    [string]$Csv = "data/demo_krw_btc_240m.csv",
    [ValidateSet("paper", "live")]
    [string]$Mode = "paper",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [int]$StartupWaitSeconds = 20,
    [switch]$OpenBrowser = $true,
    [switch]$HiddenServerWindow,
    [string]$StdoutLog = "data/control-room-server.log",
    [string]$StderrLog = "data/control-room-server.err.log",
    [string]$PidFile = "data/control-room-server.pid"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $ProjectRoot "start_control_room.ps1"
$CommonScript = Join-Path $ProjectRoot "control_room_common.ps1"
$ServerUrl = "http://{0}:{1}" -f $BindHost, $Port
$ResolvedStdoutLog = Join-Path $ProjectRoot $StdoutLog
$ResolvedStderrLog = Join-Path $ProjectRoot $StderrLog
$ResolvedPidFile = Join-Path $ProjectRoot $PidFile

if (-not (Test-Path $StartScript)) {
    throw "Control room starter not found: $StartScript"
}

if (-not (Test-Path $CommonScript)) {
    throw "Control room helper not found: $CommonScript"
}

. $CommonScript

if (Test-ControlRoomReady -Url $ServerUrl) {
    $existingPid = Get-ControlRoomPid -Path $ResolvedPidFile
    if ($OpenBrowser) {
        Start-Process $ServerUrl | Out-Null
    }
    Write-Host ("Control room already running: {0}" -f $ServerUrl)
    if ($existingPid) {
        Write-Host ("Existing PID: {0}" -f $existingPid)
    }
    exit 0
}

$existingPid = Get-ControlRoomPid -Path $ResolvedPidFile
if ($existingPid -and (Test-ProcessAlive -PidValue $existingPid)) {
    if (Test-ControlRoomOwnedProcess -PidValue $existingPid -ExpectedPort $Port) {
        Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 300
    }
    else {
        Write-Host ("Ignoring stale PID file that points to another process: {0}" -f $existingPid)
    }
}
Remove-Item -Force $ResolvedPidFile -ErrorAction SilentlyContinue

$argumentList = @(
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $StartScript,
    "-Config",
    $Config,
    "-State",
    $State,
    "-SelectorState",
    $SelectorState,
    "-Csv",
    $Csv,
    "-Mode",
    $Mode,
    "-BindHost",
    $BindHost,
    "-Port",
    $Port.ToString()
)

if (-not $HiddenServerWindow) {
    $argumentList = @("-NoExit") + $argumentList
}

$startProcessParams = @{
    FilePath = "powershell.exe"
    ArgumentList = $argumentList
    WorkingDirectory = $ProjectRoot
    PassThru = $true
}

if ($HiddenServerWindow) {
    $logDirectory = Split-Path -Parent $ResolvedStdoutLog
    if (-not (Test-Path $logDirectory)) {
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    }
    Remove-Item -Force $ResolvedStdoutLog, $ResolvedStderrLog -ErrorAction SilentlyContinue
    $startProcessParams.WindowStyle = "Hidden"
    $startProcessParams.RedirectStandardOutput = $ResolvedStdoutLog
    $startProcessParams.RedirectStandardError = $ResolvedStderrLog
}

$process = Start-Process @startProcessParams
Set-Content -Path $ResolvedPidFile -Value $process.Id -Encoding ascii

$ready = $false
for ($index = 0; $index -lt $StartupWaitSeconds; $index++) {
    Start-Sleep -Seconds 1
    if (Test-ControlRoomReady -Url $ServerUrl) {
        $ready = $true
        break
    }
}

if (-not $ready) {
    if ($HiddenServerWindow) {
        throw "Control room did not start within $StartupWaitSeconds seconds. Check $ResolvedStdoutLog and $ResolvedStderrLog."
    }
    throw "Control room did not start within $StartupWaitSeconds seconds. Check the server window that was opened."
}

if ($OpenBrowser) {
    Start-Process $ServerUrl | Out-Null
}

Write-Host ("Control room is ready: {0}" -f $ServerUrl)
Write-Host ("Server window PID: {0}" -f $process.Id)
if ($HiddenServerWindow) {
    Write-Host ("Server logs: {0} | {1}" -f $ResolvedStdoutLog, $ResolvedStderrLog)
    Write-Host ("PID file: {0}" -f $ResolvedPidFile)
}
