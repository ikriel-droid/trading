param(
    [string]$PidFile = "data/control-room-server.pid",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [int]$ShutdownWaitSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CommonScript = Join-Path $ProjectRoot "control_room_common.ps1"
$ResolvedPidFile = Join-Path $ProjectRoot $PidFile
$ServerUrl = "http://{0}:{1}" -f $BindHost, $Port

if (-not (Test-Path $CommonScript)) {
    throw "Control room helper not found: $CommonScript"
}

. $CommonScript

$pidValue = Get-ControlRoomPid -Path $ResolvedPidFile
$wasReachable = Test-ControlRoomReady -Url $ServerUrl

if ($pidValue) {
    if (-not (Test-ProcessAlive -PidValue $pidValue)) {
        Write-Host ("Control room PID file was stale: {0}" -f $pidValue)
    }
    elseif (Test-ControlRoomOwnedProcess -PidValue $pidValue -ExpectedPort $Port) {
        try {
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
            Write-Host ("Stopped control room PID: {0}" -f $pidValue)
        }
        catch {
            Write-Host ("Control room PID was not stoppable: {0}" -f $pidValue)
        }
    }
    else {
        Write-Host ("PID file does not point to a managed control room process: {0}" -f $pidValue)
    }
}
elseif (-not $wasReachable) {
    Write-Host "Control room is not running."
}

Remove-Item -Force $ResolvedPidFile -ErrorAction SilentlyContinue

for ($index = 0; $index -lt $ShutdownWaitSeconds; $index++) {
    if (-not (Test-ControlRoomReady -Url $ServerUrl)) {
        Write-Host ("Control room stopped: {0}" -f $ServerUrl)
        exit 0
    }
    Start-Sleep -Seconds 1
}

throw ("Control room still responds at {0}. Check for another manually started server." -f $ServerUrl)
