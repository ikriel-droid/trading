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
    [int]$ShutdownWaitSeconds = 5,
    [bool]$OpenBrowser = $true,
    [bool]$HiddenServerWindow = $true,
    [string]$StdoutLog = "data/control-room-server.log",
    [string]$StderrLog = "data/control-room-server.err.log",
    [string]$PidFile = "data/control-room-server.pid"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StopScript = Join-Path $ProjectRoot "stop_control_room.ps1"
$LaunchScript = Join-Path $ProjectRoot "launch_control_room.ps1"

if (-not (Test-Path $StopScript)) {
    throw "Control room stop script not found: $StopScript"
}

if (-not (Test-Path $LaunchScript)) {
    throw "Control room launch script not found: $LaunchScript"
}

& $StopScript `
    -PidFile $PidFile `
    -BindHost $BindHost `
    -Port $Port `
    -ShutdownWaitSeconds $ShutdownWaitSeconds

& $LaunchScript `
    -Config $Config `
    -State $State `
    -SelectorState $SelectorState `
    -Csv $Csv `
    -Mode $Mode `
    -BindHost $BindHost `
    -Port $Port `
    -StartupWaitSeconds $StartupWaitSeconds `
    -OpenBrowser:$OpenBrowser `
    -HiddenServerWindow:$HiddenServerWindow `
    -StdoutLog $StdoutLog `
    -StderrLog $StderrLog `
    -PidFile $PidFile
