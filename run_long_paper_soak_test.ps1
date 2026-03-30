param(
    [string]$Config = "config.example.json",
    [string]$Csv = "data/demo_krw_btc_15m.csv",
    [string]$State = "data/paper-state-soak.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectRoot "scripts\run_long_paper_soak_test.py"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtualenv not found: $PythonExe"
}

Push-Location $ProjectRoot
try {
    & $PythonExe $ScriptPath `
        --config $Config `
        --csv $Csv `
        --state $State
}
finally {
    Pop-Location
}
