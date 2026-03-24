param(
    [Parameter(Mandatory = $true)]
    [string]$Profile,
    [string]$Config = "config.example.json"
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
    & $PythonExe -m upbit_auto_trader.main profile-start `
        --config $Config `
        --profile $Profile
}
finally {
    Pop-Location
}
