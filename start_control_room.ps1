param(
    [string]$Config = "config.example.json",
    [string]$State = "data/paper-state.json",
    [string]$SelectorState = "data/selector-state.json",
    [string]$Csv = "data/demo_krw_btc_15m.csv",
    [ValidateSet("paper", "live")]
    [string]$Mode = "paper",
    [string]$Host = "127.0.0.1",
    [int]$Port = 8765
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtualenv not found: $PythonExe"
}

Push-Location $ProjectRoot
try {
    & $PythonExe -m upbit_auto_trader.main web-ui `
        --config $Config `
        --state $State `
        --selector-state $SelectorState `
        --csv $Csv `
        --mode $Mode `
        --host $Host `
        --port $Port
}
finally {
    Pop-Location
}
