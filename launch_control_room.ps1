param(
    [string]$Config = "config.example.json",
    [string]$State = "data/paper-state.json",
    [string]$SelectorState = "data/selector-state.json",
    [string]$Csv = "data/demo_krw_btc_15m.csv",
    [ValidateSet("paper", "live")]
    [string]$Mode = "paper",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [int]$StartupWaitSeconds = 20,
    [switch]$OpenBrowser = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $ProjectRoot "start_control_room.ps1"
$ServerUrl = "http://{0}:{1}" -f $BindHost, $Port

if (-not (Test-Path $StartScript)) {
    throw "Control room starter not found: $StartScript"
}

$process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @(
        "-NoExit",
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
    ) `
    -WorkingDirectory $ProjectRoot `
    -PassThru

$ready = $false
for ($index = 0; $index -lt $StartupWaitSeconds; $index++) {
    Start-Sleep -Seconds 1
    try {
        Invoke-WebRequest -UseBasicParsing "$ServerUrl/" -TimeoutSec 2 | Out-Null
        $ready = $true
        break
    }
    catch {
    }
}

if (-not $ready) {
    throw "Control room did not start within $StartupWaitSeconds seconds. Check the server window that was opened."
}

if ($OpenBrowser) {
    Start-Process $ServerUrl | Out-Null
}

Write-Host ("Control room is ready: {0}" -f $ServerUrl)
Write-Host ("Server window PID: {0}" -f $process.Id)
