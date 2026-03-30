param(
    [string]$OutputDirectory = "dist/upbit-control-room-bundle",
    [switch]$CreateZip,
    [string]$ZipPath = "dist/upbit-control-room-bundle.zip"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$ReleaseMetadataScript = Join-Path $ProjectRoot "export_control_room_release_metadata.ps1"
$ReleaseNotesScript = Join-Path $ProjectRoot "export_control_room_release_notes.ps1"

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

$ResolvedOutputDirectory = Resolve-ProjectPath -Path $OutputDirectory
$ResolvedZipPath = Resolve-ProjectPath -Path $ZipPath

$filesToCopy = @(
    ".env.example",
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "config.example.json",
    "start_control_room.ps1",
    "launch_control_room.ps1",
    "launch_control_room.cmd",
    "launch_control_room_hidden.cmd",
    "launch_control_room_silent.vbs",
    "status_control_room.ps1",
    "status_control_room.cmd",
    "status_control_room_release_pack.ps1",
    "status_control_room_release_pack.cmd",
    "stop_control_room.ps1",
    "stop_control_room.cmd",
    "restart_control_room.ps1",
    "restart_control_room.cmd",
    "tail_control_room_logs.ps1",
    "tail_control_room_logs.cmd",
    "setup_control_room.ps1",
    "setup_control_room.cmd",
    "install_control_room_shortcuts.ps1",
    "install_control_room_shortcuts.cmd",
    "uninstall_control_room_shortcuts.ps1",
    "uninstall_control_room_shortcuts.cmd",
    "control_room_common.ps1",
    "complete_remaining.sh",
    "complete_remaining.ps1",
    "complete_remaining.cmd",
    "build_control_room_bundle.ps1",
    "build_control_room_bundle.cmd",
    "build_control_room_support_bundle.ps1",
    "build_control_room_support_bundle.cmd",
    "verify_control_room_bundle.ps1",
    "verify_control_room_bundle.cmd",
    "clean_control_room_bundle.ps1",
    "clean_control_room_bundle.cmd",
    "verify_control_room_support_bundle.ps1",
    "verify_control_room_support_bundle.cmd",
    "clean_control_room_support_bundle.ps1",
    "clean_control_room_support_bundle.cmd",
    "build_control_room_release_pack.ps1",
    "build_control_room_release_pack.cmd",
    "verify_control_room_release_pack.ps1",
    "verify_control_room_release_pack.cmd",
    "clean_control_room_release_pack.ps1",
    "clean_control_room_release_pack.cmd",
    "validate_fresh_environment_deployment.ps1",
    "validate_fresh_environment_deployment.cmd",
    "export_control_room_release_metadata.ps1",
    "export_control_room_release_metadata.cmd",
    "export_control_room_release_notes.ps1",
    "export_control_room_release_notes.cmd",
    "snapshot_control_room_environment.ps1",
    "snapshot_control_room_environment.cmd",
    "start_profile.ps1",
    "src/upbit_auto_trader/__init__.py",
    "src/upbit_auto_trader/backtest.py",
    "src/upbit_auto_trader/brokers/__init__.py",
    "src/upbit_auto_trader/brokers/upbit.py",
    "src/upbit_auto_trader/config.py",
    "src/upbit_auto_trader/datafeed.py",
    "src/upbit_auto_trader/doctor.py",
    "src/upbit_auto_trader/indicators.py",
    "src/upbit_auto_trader/jobs.py",
    "src/upbit_auto_trader/main.py",
    "src/upbit_auto_trader/models.py",
    "src/upbit_auto_trader/notifier.py",
    "src/upbit_auto_trader/optimizer.py",
    "src/upbit_auto_trader/presets.py",
    "src/upbit_auto_trader/profiles.py",
    "src/upbit_auto_trader/reporting.py",
    "src/upbit_auto_trader/risk.py",
    "src/upbit_auto_trader/runtime.py",
    "src/upbit_auto_trader/scanner.py",
    "src/upbit_auto_trader/selector.py",
    "src/upbit_auto_trader/strategy.py",
    "src/upbit_auto_trader/ui.py",
    "src/upbit_auto_trader/websocket_client.py",
    "src/upbit_auto_trader/webui/app.js",
    "src/upbit_auto_trader/webui/index.html",
    "src/upbit_auto_trader/webui/styles.css",
    "data/demo_krw_btc_15m.csv"
)

if (Test-Path $ResolvedOutputDirectory) {
    Remove-Item -Recurse -Force $ResolvedOutputDirectory
}
New-Item -ItemType Directory -Path $ResolvedOutputDirectory -Force | Out-Null

$copiedFiles = @()
$manifestFiles = @()

foreach ($relativePath in $filesToCopy) {
    $sourcePath = Join-Path $ProjectRoot $relativePath
    if (-not (Test-Path $sourcePath)) {
        throw "Bundle source file not found: $sourcePath"
    }

    $destinationPath = Join-Path $ResolvedOutputDirectory $relativePath
    $destinationDirectory = Split-Path -Parent $destinationPath
    if ($destinationDirectory -and -not (Test-Path $destinationDirectory)) {
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    }

    Copy-Item -Path $sourcePath -Destination $destinationPath -Force
    $copiedFiles += $relativePath
    $manifestFiles += [pscustomobject]@{
        path = $relativePath
        sha256 = (Get-FileHash -Algorithm SHA256 -Path $destinationPath).Hash
    }
}

$manifest = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    project_root = $ProjectRoot
    output_directory = $ResolvedOutputDirectory
    file_count = $copiedFiles.Count
    files = $manifestFiles
}

$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $ResolvedOutputDirectory "bundle-manifest.json") -Encoding utf8

if (Test-Path $ReleaseMetadataScript) {
    & $PowerShellExe `
        -ExecutionPolicy Bypass `
        -File $ReleaseMetadataScript `
        -OutputPath (Join-Path $ResolvedOutputDirectory "release-metadata.json") | Out-Null
}

if (Test-Path $ReleaseNotesScript) {
    & $PowerShellExe `
        -ExecutionPolicy Bypass `
        -File $ReleaseNotesScript `
        -OutputPath (Join-Path $ResolvedOutputDirectory "release-notes.md") | Out-Null
}

if ($CreateZip) {
    $zipDirectory = Split-Path -Parent $ResolvedZipPath
    if ($zipDirectory -and -not (Test-Path $zipDirectory)) {
        New-Item -ItemType Directory -Path $zipDirectory -Force | Out-Null
    }
    Remove-Item -Force $ResolvedZipPath -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $ResolvedOutputDirectory "*") -DestinationPath $ResolvedZipPath
    Write-Host ("Created bundle zip: {0}" -f $ResolvedZipPath)
}

Write-Host ("Created control room bundle: {0}" -f $ResolvedOutputDirectory)
Write-Host ("Copied files: {0}" -f $copiedFiles.Count)
