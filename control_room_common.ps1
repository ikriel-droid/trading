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

function Get-ControlRoomStatus {
    param(
        [string]$Url,
        [string]$PidFile,
        [int]$Port,
        [string]$StdoutLog = "",
        [string]$StderrLog = ""
    )

    $pidValue = Get-ControlRoomPid -Path $PidFile
    $pidAlive = $false
    $pidOwned = $false
    if ($pidValue) {
        $pidAlive = Test-ProcessAlive -PidValue $pidValue
        if ($pidAlive) {
            $pidOwned = Test-ControlRoomOwnedProcess -PidValue $pidValue -ExpectedPort $Port
        }
    }

    [pscustomobject]@{
        url = $Url
        reachable = Test-ControlRoomReady -Url $Url
        pid = $pidValue
        pid_alive = $pidAlive
        pid_owned = $pidOwned
        pid_file = $PidFile
        stdout_log = $StdoutLog
        stderr_log = $StderrLog
    }
}
