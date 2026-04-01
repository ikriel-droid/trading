param(
    [string]$ConfigPath = "config.live.micro.json",
    [string]$StatePath = "data/live-state.json",
    [string]$CsvPath = "",
    [string]$Market = "",
    [int]$Count = 200,
    [string]$SelectorStatePath = "data/selector-state.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$PrepareScript = Join-Path $ProjectRoot "prepare_small_live_validation.ps1"
$BootstrapScript = Join-Path $ProjectRoot "scripts\bootstrap_small_live_validation_state.py"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtualenv not found: $PythonExe"
}

$ResolvedConfigPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $ProjectRoot $ConfigPath }
if (-not (Test-Path $ResolvedConfigPath)) {
    throw "Config file not found: $ResolvedConfigPath"
}

$ConfigJson = Get-Content $ResolvedConfigPath -Raw | ConvertFrom-Json
$ResolvedMarket = if ($Market) { $Market } else { [string]$ConfigJson.market }
if (-not $ResolvedMarket) {
    throw "Market could not be resolved from config or -Market."
}

if (-not $CsvPath) {
    $Slug = $ResolvedMarket.ToLower().Replace("-", "_")
    $CandleUnit = 240
    if ($ConfigJson.upbit -and $ConfigJson.upbit.candle_unit) {
        $CandleUnit = [int]$ConfigJson.upbit.candle_unit
    }
    $CsvPath = "data/live_{0}_{1}m.csv" -f $Slug, $CandleUnit
}

Push-Location $ProjectRoot
try {
    $syncArgs = @(
        "-m",
        "upbit_auto_trader.main",
        "sync-candles",
        "--config", $ConfigPath,
        "--csv", $CsvPath,
        "--market", $ResolvedMarket,
        "--count", $Count
    )
    & $PythonExe @syncArgs
    if ($LASTEXITCODE -ne 0) {
        throw "sync-candles failed"
    }

    $bootstrapArgs = @(
        $BootstrapScript,
        "--config", $ConfigPath,
        "--state", $StatePath,
        "--csv", $CsvPath,
        "--market", $ResolvedMarket
    )
    & $PythonExe @bootstrapArgs
    if ($LASTEXITCODE -ne 0) {
        throw "bootstrap_small_live_validation_state.py failed"
    }

    & $PowerShellExe -ExecutionPolicy Bypass -File $PrepareScript `
        -ConfigPath $ConfigPath `
        -StatePath $StatePath `
        -SelectorStatePath $SelectorStatePath
    if ($LASTEXITCODE -ne 0) {
        throw "prepare_small_live_validation.ps1 failed"
    }
}
finally {
    Pop-Location
}
