param(
    [string]$BundleDirectory = "dist/upbit-control-room-bundle",
    [string]$ZipPath = "dist/upbit-control-room-bundle.zip"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedBundleDirectory = Join-Path $ProjectRoot $BundleDirectory
$ResolvedZipPath = Join-Path $ProjectRoot $ZipPath

$removed = @()

if (Test-Path $ResolvedBundleDirectory) {
    Remove-Item -Recurse -Force $ResolvedBundleDirectory
    $removed += $ResolvedBundleDirectory
}

if (Test-Path $ResolvedZipPath) {
    Remove-Item -Force $ResolvedZipPath
    $removed += $ResolvedZipPath
}

if ($removed.Count -eq 0) {
    Write-Host "No control room bundle artifacts were found."
    exit 0
}

Write-Host "Removed control room bundle artifacts:"
foreach ($path in $removed) {
    Write-Host ("- {0}" -f $path)
}
