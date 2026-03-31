param(
    [string]$OutputDirectory = "dist/windows-launcher",
    [string]$WorkDirectory = "dist/pyinstaller-work",
    [string]$SpecDirectory = "dist/pyinstaller-spec"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedOutputDirectory = Join-Path $ProjectRoot $OutputDirectory
$ResolvedWorkDirectory = Join-Path $ProjectRoot $WorkDirectory
$ResolvedSpecDirectory = Join-Path $ProjectRoot $SpecDirectory

$targets = @($ResolvedOutputDirectory, $ResolvedWorkDirectory, $ResolvedSpecDirectory)
$removed = @()
foreach ($target in $targets) {
    if (Test-Path $target) {
        Remove-Item -Recurse -Force $target
        $removed += $target
    }
}

if ($removed.Count -eq 0) {
    Write-Host "No launcher executable artifacts were found."
    exit 0
}

Write-Host "Removed launcher executable artifacts:"
$removed | ForEach-Object { Write-Host (" - {0}" -f $_) }
