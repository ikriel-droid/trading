param(
    [switch]$InstallShortcuts,
    [string]$ShortcutDirectory = "",
    [string]$ShortcutNamePrefix = "Upbit Control Room",
    [string]$ShortcutManifestPath = "data/control-room-shortcuts.json",
    [switch]$ForceEnvTemplate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$EnvPath = Join-Path $ProjectRoot ".env"
$InstallShortcutsScript = Join-Path $ProjectRoot "install_control_room_shortcuts.ps1"

function Get-BootstrapPython {
    $candidates = @()
    $localPython312 = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
    if (Test-Path $localPython312) {
        $candidates += [pscustomobject]@{
            command = $localPython312
            prefix_args = @()
            label = $localPython312
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{
            command = "py"
            prefix_args = @("-3.12")
            label = "py -3.12"
        }
        $candidates += [pscustomobject]@{
            command = "py"
            prefix_args = @("-3")
            label = "py -3"
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{
            command = "python"
            prefix_args = @()
            label = "python"
        }
    }

    foreach ($candidate in $candidates) {
        try {
            $versionText = & $candidate.command @($candidate.prefix_args + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"))
            if ($LASTEXITCODE -eq 0 -and $versionText) {
                $version = [version]$versionText.Trim()
                if ($version -ge [version]"3.12") {
                    return $candidate
                }
            }
        }
        catch {
        }
    }

    throw "Python 3.12+ was not found. Install Python 3.12 and run this script again."
}

if (-not (Test-Path $VenvPython)) {
    $bootstrapPython = Get-BootstrapPython
    Write-Host ("Creating virtual environment with: {0}" -f $bootstrapPython.label)
    Push-Location $ProjectRoot
    try {
        & $bootstrapPython.command @($bootstrapPython.prefix_args + @("-m", "venv", ".venv"))
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
            throw "Failed to create virtual environment."
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host ("Using existing virtual environment: {0}" -f $VenvPython)
}

Write-Host "Installing editable package into the virtual environment..."
Push-Location $ProjectRoot
try {
    & $VenvPython -m pip install -e .
    if ($LASTEXITCODE -ne 0) {
        throw "Editable install failed."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $EnvExample)) {
    throw ".env.example not found: $EnvExample"
}

if ($ForceEnvTemplate -or -not (Test-Path $EnvPath)) {
    Copy-Item -Path $EnvExample -Destination $EnvPath -Force
    Write-Host ("Prepared environment file: {0}" -f $EnvPath)
}
else {
    Write-Host ("Keeping existing environment file: {0}" -f $EnvPath)
}

if ($InstallShortcuts) {
    if (-not (Test-Path $InstallShortcutsScript)) {
        throw "Shortcut installer not found: $InstallShortcutsScript"
    }

    $shortcutArgs = @(
        "-NamePrefix", $ShortcutNamePrefix,
        "-ManifestPath", $ShortcutManifestPath
    )
    if ($ShortcutDirectory) {
        $shortcutArgs += @("-ShortcutDirectory", $ShortcutDirectory)
    }

    & $InstallShortcutsScript @shortcutArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Shortcut installation failed."
    }
}

Write-Host ""
Write-Host "Control room setup is ready."
Write-Host "Next steps:"
Write-Host "1. Fill in .env if you plan to use live features."
Write-Host "2. Start the UI with .\\launch_control_room_hidden.cmd"
Write-Host "3. Check status with .\\status_control_room.cmd"
