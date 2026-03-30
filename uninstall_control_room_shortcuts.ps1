param(
    [string]$ShortcutDirectory = "",
    [string]$NamePrefix = "Upbit Control Room",
    [string]$ManifestPath = "data/control-room-shortcuts.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedManifestPath = Join-Path $ProjectRoot $ManifestPath
$ResolvedShortcutDirectory = if ($ShortcutDirectory) {
    $ShortcutDirectory
}
elseif (Test-Path $ResolvedManifestPath) {
    try {
        $manifestData = Get-Content -Path $ResolvedManifestPath -Raw | ConvertFrom-Json
        $manifestData.shortcut_directory
    }
    catch {
        [Environment]::GetFolderPath("Desktop")
    }
}
else {
    [Environment]::GetFolderPath("Desktop")
}

$removedPaths = @()

if (Test-Path $ResolvedManifestPath) {
    try {
        $manifest = Get-Content -Path $ResolvedManifestPath -Raw | ConvertFrom-Json
        foreach ($shortcut in $manifest.shortcuts) {
            if (Test-Path $shortcut.path) {
                Remove-Item -Force $shortcut.path
                $removedPaths += $shortcut.path
            }
        }
    }
    catch {
    }
}

if (-not $removedPaths -and $ResolvedShortcutDirectory) {
    $fallbackNames = @(
        $NamePrefix,
        ('{0} Status' -f $NamePrefix),
        ('{0} Release Status' -f $NamePrefix),
        ('{0} Restart' -f $NamePrefix),
        ('{0} Stop' -f $NamePrefix),
        ('{0} Logs' -f $NamePrefix)
    )
    foreach ($name in $fallbackNames) {
        $shortcutPath = Join-Path $ResolvedShortcutDirectory ('{0}.lnk' -f $name)
        if (Test-Path $shortcutPath) {
            Remove-Item -Force $shortcutPath
            $removedPaths += $shortcutPath
        }
    }
}

Remove-Item -Force $ResolvedManifestPath -ErrorAction SilentlyContinue

if ($removedPaths) {
    Write-Host "Removed control room shortcuts:"
    foreach ($path in $removedPaths) {
        Write-Host ("- {0}" -f $path)
    }
}
else {
    Write-Host "No control room shortcuts were found to remove."
}
