param(
    [string]$PackDirectory = "dist/upbit-control-room-release-pack",
    [string]$ZipPath = "dist/upbit-control-room-release-pack.zip",
    [switch]$RequireZip,
    [switch]$RequireSupportBundle
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

$ResolvedPackDirectory = Resolve-ProjectPath -Path $PackDirectory
$ResolvedZipPath = Resolve-ProjectPath -Path $ZipPath
$ManifestPath = Join-Path $ResolvedPackDirectory "release-pack-manifest.json"

$requiredPaths = @(
    "release-metadata.json",
    "release-notes.md",
    "release-bundle.zip",
    "release-pack-manifest.json"
)

if (-not (Test-Path $ResolvedPackDirectory)) {
    throw "Release pack directory does not exist: $ResolvedPackDirectory"
}

if (-not (Test-Path $ManifestPath)) {
    throw "Release pack manifest does not exist: $ManifestPath"
}

$manifest = Get-Content -Path $ManifestPath -Raw | ConvertFrom-Json
if (-not $manifest.files -or @($manifest.files).Count -lt 1) {
    throw "Release pack manifest is missing file entries."
}

foreach ($relativePath in $requiredPaths) {
    $targetPath = Join-Path $ResolvedPackDirectory $relativePath
    if (-not (Test-Path $targetPath)) {
        throw "Required release pack file is missing: $targetPath"
    }
}

if ($RequireSupportBundle) {
    $supportZipPath = Join-Path $ResolvedPackDirectory "support-bundle.zip"
    if (-not (Test-Path $supportZipPath)) {
        throw "Support bundle zip is required but missing: $supportZipPath"
    }
    if (-not $manifest.includes_support_bundle) {
        throw "Release pack manifest does not record support bundle inclusion."
    }
}

foreach ($entry in $manifest.files) {
    $targetPath = Join-Path $ResolvedPackDirectory $entry.path
    if (-not (Test-Path $targetPath)) {
        throw "Release pack manifest references a missing file: $targetPath"
    }

    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $targetPath).Hash
    if ($actualHash -ne $entry.sha256) {
        throw "Release pack checksum mismatch: $($entry.path)"
    }
}

if ($RequireZip -and -not (Test-Path $ResolvedZipPath)) {
    throw "Release pack zip does not exist: $ResolvedZipPath"
}

Write-Host ("Release pack verified: {0}" -f $ResolvedPackDirectory)
Write-Host ("Manifest files: {0}" -f @($manifest.files).Count)
if ($RequireZip) {
    Write-Host ("Release pack zip: {0}" -f $ResolvedZipPath)
}
