param(
    [string]$ConfigPath = "config.example.json",
    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = if ($env:PYTHON_EXE) {
    $env:PYTHON_EXE
}
else {
    Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
$ResolvedConfigPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) {
    [System.IO.Path]::GetFullPath($ConfigPath)
}
else {
    Join-Path $ProjectRoot $ConfigPath
}

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

if (-not (Test-Path $ResolvedConfigPath)) {
    throw "Config file not found: $ResolvedConfigPath"
}

$json = & $PythonExe -m upbit_auto_trader.main release-status --config $ResolvedConfigPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$payload = $json | ConvertFrom-Json
if ($AsJson) {
    $payload | ConvertTo-Json -Depth 6
    exit 0
}

$artifacts = $payload.release_artifacts
$checklist = $payload.checklist

Write-Host ("Config: {0}" -f $payload.config_path)
Write-Host ("Status: {0}" -f $artifacts.status)
Write-Host ("Ready for distribution: {0}" -f $payload.ready_for_distribution)
Write-Host ("Verification: {0}" -f $artifacts.verification_status)
if ($artifacts.verified_at) {
    Write-Host ("Verified at: {0}" -f $artifacts.verified_at)
}
Write-Host ("Recommended stage: {0}" -f $payload.recommended_stage)
Write-Host ("Checklist detail: {0}" -f $checklist.detail)
Write-Host ("Checklist action: {0}" -f $checklist.action)
Write-Host ("Pack directory: {0}" -f $artifacts.pack_directory)
Write-Host ("Pack zip: {0}" -f $artifacts.zip_path)
Write-Host ("Manifest: {0}" -f $artifacts.manifest_path)
Write-Host ("Verification report: {0}" -f $artifacts.verification_path)
if ($artifacts.issues.Count -gt 0) {
    Write-Host ("Issues: {0}" -f (($artifacts.issues -join ", ")))
}
if ($artifacts.verification_issues.Count -gt 0) {
    Write-Host ("Verification issues: {0}" -f (($artifacts.verification_issues -join ", ")))
}
