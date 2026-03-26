param(
    [string]$PidFile = "data/control-room-server.pid",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [int]$ShutdownWaitSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedPidFile = Join-Path $ProjectRoot $PidFile
$ServerUrl = "http://{0}:{1}" -f $BindHost, $Port

function Test-ControlRoomReady {
    param(
        [string]$Url
    )

    try {
        Invoke-WebRequest -UseBasicParsing "$Url/" -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Get-ControlRoomPid {
    param(
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    $raw = (Get-Content $Path -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $raw) {
        return $null
    }

    $pidValue = 0
    if ([int]::TryParse($raw.Trim(), [ref]$pidValue)) {
        return $pidValue
    }
    return $null
}

function Test-ProcessAlive {
    param(
        [int]$PidValue
    )

    if ($PidValue -le 0) {
        return $false
    }

    try {
        $null = Get-Process -Id $PidValue -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Get-ProcessCommandLine {
    param(
        [int]$PidValue
    )

    if ($PidValue -le 0) {
        return $null
    }

    try {
        $processRecord = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $PidValue) -ErrorAction Stop
        return $processRecord.CommandLine
    }
    catch {
        return $null
    }
}

function Test-ControlRoomOwnedProcess {
    param(
        [int]$PidValue,
        [int]$ExpectedPort
    )

    $commandLine = Get-ProcessCommandLine -PidValue $PidValue
    if (-not $commandLine) {
        return $false
    }

    return ($commandLine -like "*start_control_room.ps1*") -and ($commandLine -like ("*-Port* {0}*" -f $ExpectedPort))
}

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
