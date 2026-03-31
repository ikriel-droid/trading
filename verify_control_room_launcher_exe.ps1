param(
    [string]$ExePath = "dist/windows-launcher/UpbitControlRoomLauncher/UpbitControlRoomLauncher.exe",
    [string]$OutputJson = "dist/windows-launcher/launcher-diagnostics.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedExePath = Join-Path $ProjectRoot $ExePath
$ResolvedOutputJson = Join-Path $ProjectRoot $OutputJson

if (-not (Test-Path $ResolvedExePath)) {
    throw "Launcher executable not found: $ResolvedExePath"
}

$directory = Split-Path -Parent $ResolvedOutputJson
if ($directory -and -not (Test-Path $directory)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$process = Start-Process -FilePath $ResolvedExePath -ArgumentList @("--diagnose-write", $ResolvedOutputJson) -PassThru -Wait
if ($process.ExitCode -ne 0) {
    throw "Launcher diagnostics failed."
}
$diagnostics = Get-Content -Path $ResolvedOutputJson -Raw | ConvertFrom-Json
if (-not $diagnostics.found) {
    throw "Launcher diagnostics did not detect the project root."
}
if (-not $diagnostics.scripts.launch_hidden.exists) {
    throw "Launcher diagnostics did not detect launch_control_room_hidden.cmd."
}

Write-Host ("Verified launcher executable: {0}" -f $ResolvedExePath)
