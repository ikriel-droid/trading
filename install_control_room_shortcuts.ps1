param(
    [string]$ShortcutDirectory = "",
    [string]$NamePrefix = "Upbit Control Room",
    [string]$ManifestPath = "data/control-room-shortcuts.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedShortcutDirectory = if ($ShortcutDirectory) {
    $ShortcutDirectory
}
else {
    [Environment]::GetFolderPath("Desktop")
}
$ResolvedManifestPath = Join-Path $ProjectRoot $ManifestPath

if (-not $ResolvedShortcutDirectory) {
    throw "Shortcut directory could not be resolved."
}

if (-not (Test-Path $ResolvedShortcutDirectory)) {
    New-Item -ItemType Directory -Path $ResolvedShortcutDirectory -Force | Out-Null
}

$manifestDirectory = Split-Path -Parent $ResolvedManifestPath
if ($manifestDirectory -and -not (Test-Path $manifestDirectory)) {
    New-Item -ItemType Directory -Path $manifestDirectory -Force | Out-Null
}

$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$wscriptExe = Join-Path $env:SystemRoot "System32\wscript.exe"
$silentLauncher = Join-Path $ProjectRoot "launch_control_room_silent.vbs"
$statusScript = Join-Path $ProjectRoot "status_control_room.ps1"
$releaseStatusScript = Join-Path $ProjectRoot "status_control_room_release_pack.ps1"
$restartScript = Join-Path $ProjectRoot "restart_control_room.ps1"
$stopScript = Join-Path $ProjectRoot "stop_control_room.ps1"
$tailScript = Join-Path $ProjectRoot "tail_control_room_logs.ps1"

$shortcutDefinitions = @(
    @{
        name = $NamePrefix
        target = $wscriptExe
        arguments = ('"{0}"' -f $silentLauncher)
        description = "Launch the Upbit control room with the server window hidden."
        icon = ('{0},0' -f $wscriptExe)
        working_directory = $ProjectRoot
    }
    @{
        name = ('{0} Status' -f $NamePrefix)
        target = $powershellExe
        arguments = ('-ExecutionPolicy Bypass -NoExit -File "{0}"' -f $statusScript)
        description = "Show whether the control room is reachable and managed."
        icon = ('{0},0' -f $powershellExe)
        working_directory = $ProjectRoot
    }
    @{
        name = ('{0} Release Status' -f $NamePrefix)
        target = $powershellExe
        arguments = ('-ExecutionPolicy Bypass -NoExit -File "{0}"' -f $releaseStatusScript)
        description = "Show the current release-pack readiness and verification state."
        icon = ('{0},0' -f $powershellExe)
        working_directory = $ProjectRoot
    }
    @{
        name = ('{0} Restart' -f $NamePrefix)
        target = $powershellExe
        arguments = ('-ExecutionPolicy Bypass -File "{0}"' -f $restartScript)
        description = "Restart the hidden Upbit control room."
        icon = ('{0},0' -f $powershellExe)
        working_directory = $ProjectRoot
    }
    @{
        name = ('{0} Stop' -f $NamePrefix)
        target = $powershellExe
        arguments = ('-ExecutionPolicy Bypass -File "{0}"' -f $stopScript)
        description = "Stop the hidden Upbit control room."
        icon = ('{0},0' -f $powershellExe)
        working_directory = $ProjectRoot
    }
    @{
        name = ('{0} Logs' -f $NamePrefix)
        target = $powershellExe
        arguments = ('-ExecutionPolicy Bypass -NoExit -File "{0}" -Follow' -f $tailScript)
        description = "Tail the hidden Upbit control room logs."
        icon = ('{0},0' -f $powershellExe)
        working_directory = $ProjectRoot
    }
)

$shell = New-Object -ComObject WScript.Shell
$createdShortcuts = @()

foreach ($definition in $shortcutDefinitions) {
    $shortcutPath = Join-Path $ResolvedShortcutDirectory ('{0}.lnk' -f $definition.name)
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $definition.target
    $shortcut.Arguments = $definition.arguments
    $shortcut.WorkingDirectory = $definition.working_directory
    $shortcut.Description = $definition.description
    $shortcut.IconLocation = $definition.icon
    $shortcut.Save()

    $createdShortcuts += [pscustomobject]@{
        name = $definition.name
        path = $shortcutPath
        target = $definition.target
        arguments = $definition.arguments
    }
}

$manifest = [pscustomobject]@{
    shortcut_directory = $ResolvedShortcutDirectory
    name_prefix = $NamePrefix
    created_at = (Get-Date).ToString("o")
    shortcuts = $createdShortcuts
}

$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $ResolvedManifestPath -Encoding utf8

Write-Host ("Installed control room shortcuts in: {0}" -f $ResolvedShortcutDirectory)
foreach ($shortcut in $createdShortcuts) {
    Write-Host ("- {0}" -f $shortcut.path)
}
Write-Host ("Manifest: {0}" -f $ResolvedManifestPath)
