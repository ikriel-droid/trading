param(
    [string]$ConfigPath = "config.live.micro.json",
    [string]$StatePath = "data/live-state.json",
    [string]$Market = "KRW-BTC",
    [double]$BuyKrw = 6000.0,
    [double]$PollSeconds = 1.0,
    [double]$MaxWaitSeconds = 30.0,
    [int]$KeepLatestReports = 20,
    [string]$OutputPath = "dist/live-validation/live-market-validation-summary.json",
    [string]$SupportZipPath = "dist/upbit-control-room-support-live-validation.zip",
    [string]$Confirm = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Confirm -ne "LIVE") {
    throw "run_small_live_market_validation.ps1 requires -Confirm LIVE"
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$BuildSupportScript = Join-Path $ProjectRoot "build_control_room_support_bundle.ps1"

function Resolve-ProjectPath {
    param([string]$PathValue)
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $ProjectRoot
    }
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }
    return Join-Path $ProjectRoot $PathValue
}

function Ensure-Directory {
    param([string]$PathValue)
    if (-not (Test-Path $PathValue)) {
        New-Item -ItemType Directory -Path $PathValue -Force | Out-Null
    }
}

function Invoke-PythonMainJson {
    param([string[]]$Arguments)
    $output = & $PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: python $($Arguments -join ' ')"
    }
    return (($output -join [Environment]::NewLine) | ConvertFrom-Json)
}

if (-not (Test-Path $PythonExe)) {
    throw ".venv\\Scripts\\python.exe not found. Run setup_control_room.cmd first."
}

$ResolvedConfigPath = Resolve-ProjectPath $ConfigPath
$ResolvedStatePath = Resolve-ProjectPath $StatePath
$ResolvedOutputPath = Resolve-ProjectPath $OutputPath
$ResolvedSupportZipPath = Resolve-ProjectPath $SupportZipPath
$OutputDirectory = Split-Path -Parent $ResolvedOutputPath
Ensure-Directory $OutputDirectory
Ensure-Directory (Split-Path -Parent $ResolvedSupportZipPath)

$configPayload = Get-Content $ResolvedConfigPath -Raw | ConvertFrom-Json
$candleUnit = 15
if ($configPayload.upbit -and $configPayload.upbit.candle_unit) {
    $candleUnit = [int]$configPayload.upbit.candle_unit
}
$marketSlug = $Market.ToLower().Replace("-", "_")
$ResolvedWarmupCsv = Resolve-ProjectPath ("data/live_{0}_{1}m.csv" -f $marketSlug, $candleUnit)
$ValidationResultPath = Join-Path $OutputDirectory "live-market-validation-result.json"
$ReleaseStatusPath = Join-Path $OutputDirectory "live-market-validation-release-status.json"

$validationResult = Invoke-PythonMainJson -Arguments @(
    "-m", "upbit_auto_trader.main",
    "run-live-market-validation",
    "--config", $ResolvedConfigPath,
    "--state", $ResolvedStatePath,
    "--market", $Market,
    "--warmup-csv", $ResolvedWarmupCsv,
    "--buy-krw", $BuyKrw.ToString([System.Globalization.CultureInfo]::InvariantCulture),
    "--poll-seconds", $PollSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture),
    "--max-wait-seconds", $MaxWaitSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture),
    "--confirm", "LIVE"
)
$validationResult | ConvertTo-Json -Depth 100 | Set-Content -Path $ValidationResultPath -Encoding utf8

$sessionReport = Invoke-PythonMainJson -Arguments @(
    "-m", "upbit_auto_trader.main",
    "session-report",
    "--config", $ResolvedConfigPath,
    "--state", $ResolvedStatePath,
    "--mode", "live",
    "--label", "live-market-validation",
    "--keep-latest", "$KeepLatestReports"
)

& $PowerShellExe -ExecutionPolicy Bypass -File $BuildSupportScript `
    -ConfigPath $ResolvedConfigPath `
    -StatePath $ResolvedStatePath `
    -CreateZip `
    -ZipPath $ResolvedSupportZipPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "build_control_room_support_bundle.ps1 failed"
}

$releaseStatus = Invoke-PythonMainJson -Arguments @(
    "-m", "upbit_auto_trader.main",
    "release-status",
    "--config", $ResolvedConfigPath
)
$releaseStatus | ConvertTo-Json -Depth 100 | Set-Content -Path $ReleaseStatusPath -Encoding utf8

$summary = [ordered]@{
    kind = "small_live_market_validation"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    market = $Market
    buy_krw = [math]::Round($BuyKrw, 2)
    validation_result_path = $ValidationResultPath
    validation_summary_path = $ResolvedOutputPath
    session_report_json_path = [string]$sessionReport.json_path
    session_report_html_path = [string]$sessionReport.html_path
    support_bundle_zip_path = $ResolvedSupportZipPath
    release_status_json_path = $ReleaseStatusPath
    release_artifacts_status = if ($releaseStatus.release_artifacts) { [string]$releaseStatus.release_artifacts.status } else { "" }
    trade_count = if ($validationResult.summary) { [int]$validationResult.summary.trade_count } else { 0 }
    final_equity = if ($validationResult.summary) { [double]$validationResult.summary.equity } else { 0.0 }
}

$summary | ConvertTo-Json -Depth 100 | Set-Content -Path $ResolvedOutputPath -Encoding utf8
$summary | ConvertTo-Json -Depth 100
