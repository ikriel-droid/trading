param(
    [string]$PackDirectory = "dist/upbit-control-room-release-pack",
    [string]$ZipPath = "dist/upbit-control-room-release-pack.zip"
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

$removed = @()

if (Test-Path $ResolvedPackDirectory) {
    Remove-Item -Recurse -Force $ResolvedPackDirectory
    $removed += $ResolvedPackDirectory
}

if (Test-Path $ResolvedZipPath) {
    Remove-Item -Force $ResolvedZipPath
    $removed += $ResolvedZipPath
}

if ($removed.Count -eq 0) {
    Write-Host "No control room release pack artifacts were found."
    exit 0
}

Write-Host "Removed control room release pack artifacts:"
foreach ($path in $removed) {
    Write-Host ("- {0}" -f $path)
}
