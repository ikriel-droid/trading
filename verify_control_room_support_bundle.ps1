param(
    [string]$BundleDirectory = "dist/upbit-control-room-support",
    [string]$ZipPath = "dist/upbit-control-room-support.zip",
    [switch]$RequireZip
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-ProjectPath {
    param(
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $ProjectRoot
    }

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    return Join-Path $ProjectRoot $Path
}

$ResolvedBundleDirectory = Resolve-ProjectPath -Path $BundleDirectory
$ResolvedZipPath = Resolve-ProjectPath -Path $ZipPath
$ManifestPath = Join-Path $ResolvedBundleDirectory "support-manifest.json"

$requiredPaths = @(
    "inputs\config.redacted.json",
    "inputs\env.redacted.txt",
    "diagnostics\control-room-status.json",
    "diagnostics\environment-snapshot.json",
    "support-manifest.json"
)

if (-not (Test-Path $ResolvedBundleDirectory)) {
    throw "Support bundle directory does not exist: $ResolvedBundleDirectory"
}

if (-not (Test-Path $ManifestPath)) {
    throw "Support bundle manifest does not exist: $ManifestPath"
}

$manifest = Get-Content -Path $ManifestPath -Raw | ConvertFrom-Json
if (-not $manifest.files -or $manifest.file_count -lt 1) {
    throw "Support bundle manifest is missing file entries."
}

foreach ($relativePath in $requiredPaths) {
    $targetPath = Join-Path $ResolvedBundleDirectory $relativePath
    if (-not (Test-Path $targetPath)) {
        throw "Required support bundle file is missing: $targetPath"
    }
}

if ($manifest.file_count -ne @($manifest.files).Count) {
    throw "Support bundle manifest file_count does not match the listed files."
}

foreach ($entry in $manifest.files) {
    $targetPath = Join-Path $ResolvedBundleDirectory $entry.path
    if (-not (Test-Path $targetPath)) {
        throw "Support bundle manifest references a missing file: $targetPath"
    }

    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $targetPath).Hash
    if ($actualHash -ne $entry.sha256) {
        throw "Support bundle checksum mismatch: $($entry.path)"
    }
}

if ($RequireZip -and -not (Test-Path $ResolvedZipPath)) {
    throw "Support bundle zip does not exist: $ResolvedZipPath"
}

Write-Host ("Support bundle verified: {0}" -f $ResolvedBundleDirectory)
Write-Host ("Manifest files: {0}" -f $manifest.file_count)
if ($RequireZip) {
    Write-Host ("Support bundle zip: {0}" -f $ResolvedZipPath)
}
