param(
    [string]$OutputDirectory = "dist/windows-launcher",
    [string]$WorkDirectory = "dist/pyinstaller-work",
    [string]$SpecDirectory = "dist/pyinstaller-spec",
    [string]$ExeName = "UpbitControlRoomLauncher"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$EntryScript = Join-Path $ProjectRoot "src\upbit_auto_trader\control_room_launcher.py"
$ResolvedOutputDirectory = Join-Path $ProjectRoot $OutputDirectory
$ResolvedWorkDirectory = Join-Path $ProjectRoot $WorkDirectory
$ResolvedSpecDirectory = Join-Path $ProjectRoot $SpecDirectory
$ExeDirectory = Join-Path $ResolvedOutputDirectory $ExeName
$ExePath = Join-Path $ExeDirectory ($ExeName + ".exe")

if (-not (Test-Path $PythonExe)) {
    throw ".venv\\Scripts\\python.exe not found. Run setup_control_room.cmd first."
}

if (-not (Test-Path $EntryScript)) {
    throw "Launcher entry script not found: $EntryScript"
}

& $PythonExe -m pip install pyinstaller | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install or update PyInstaller."
}

Remove-Item -Recurse -Force $ResolvedOutputDirectory, $ResolvedWorkDirectory, $ResolvedSpecDirectory -ErrorAction SilentlyContinue

Push-Location $ProjectRoot
try {
    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --noconsole `
        --onedir `
        --name $ExeName `
        --distpath $ResolvedOutputDirectory `
        --workpath $ResolvedWorkDirectory `
        --specpath $ResolvedSpecDirectory `
        --paths (Join-Path $ProjectRoot "src") `
        $EntryScript
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $ExePath)) {
    throw "Launcher executable was not created: $ExePath"
}

Write-Host ("Built launcher executable: {0}" -f $ExePath)
