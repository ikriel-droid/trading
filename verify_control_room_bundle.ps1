param(
    [string]$BundleDirectory = "dist/upbit-control-room-bundle",
    [string]$ZipPath = "dist/upbit-control-room-bundle.zip",
    [switch]$RequireZip
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedBundleDirectory = Join-Path $ProjectRoot $BundleDirectory
$ResolvedZipPath = Join-Path $ProjectRoot $ZipPath
$ManifestPath = Join-Path $ResolvedBundleDirectory "bundle-manifest.json"

$requiredPaths = @(
    "README.md",
    ".env.example",
    "config.example.json",
    "pyproject.toml",
    "release-metadata.json",
    "release-notes.md",
    "setup_control_room.cmd",
    "launch_control_room_hidden.cmd",
    "status_control_room.cmd",
    "stop_control_room.cmd",
    "restart_control_room.cmd",
    "tail_control_room_logs.cmd",
    "build_control_room_bundle.cmd",
    "src/upbit_auto_trader/main.py",
    "src/upbit_auto_trader/ui.py",
    "src/upbit_auto_trader/webui/index.html",
    "src/upbit_auto_trader/webui/app.js",
    "data/demo_krw_btc_15m.csv"
)

if (-not (Test-Path $ResolvedBundleDirectory)) {
    throw "Bundle directory does not exist: $ResolvedBundleDirectory"
}

if (-not (Test-Path $ManifestPath)) {
    throw "Bundle manifest does not exist: $ManifestPath"
}

$manifest = Get-Content -Path $ManifestPath -Raw | ConvertFrom-Json
if (-not $manifest.files -or $manifest.file_count -lt 1) {
    throw "Bundle manifest is missing file entries."
}

foreach ($relativePath in $requiredPaths) {
    $targetPath = Join-Path $ResolvedBundleDirectory $relativePath
    if (-not (Test-Path $targetPath)) {
        throw "Required bundle file is missing: $targetPath"
    }
}

if ($manifest.file_count -ne @($manifest.files).Count) {
    throw "Bundle manifest file_count does not match the listed files."
}

foreach ($entry in $manifest.files) {
    $targetPath = Join-Path $ResolvedBundleDirectory $entry.path
    if (-not (Test-Path $targetPath)) {
        throw "Bundle manifest references a missing file: $targetPath"
    }

    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $targetPath).Hash
    if ($actualHash -ne $entry.sha256) {
        throw "Bundle checksum mismatch: $($entry.path)"
    }
}

if ($RequireZip -and -not (Test-Path $ResolvedZipPath)) {
    throw "Bundle zip does not exist: $ResolvedZipPath"
}

Write-Host ("Bundle verified: {0}" -f $ResolvedBundleDirectory)
Write-Host ("Manifest files: {0}" -f $manifest.file_count)
if ($RequireZip) {
    Write-Host ("Bundle zip: {0}" -f $ResolvedZipPath)
}
