param(
    [string]$OutputDirectory = "dist/fresh-environment-validation",
    [int]$Port = 8876,
    [int]$PaperSteps = 40
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$BuildBundleScript = Join-Path $ProjectRoot "build_control_room_bundle.ps1"

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

function Invoke-FreshPowerShellFile {
    param(
        [string]$WorkspaceRoot,
        [string]$ScriptRelativePath,
        [string[]]$Arguments = @()
    )

    $scriptPath = Join-Path $WorkspaceRoot $ScriptRelativePath
    if (-not (Test-Path $scriptPath)) {
        throw "Workspace script not found: $scriptPath"
    }

    Push-Location $WorkspaceRoot
    try {
        & $PowerShellExe -ExecutionPolicy Bypass -File $scriptPath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Fresh-workspace script failed: $ScriptRelativePath"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-FreshPowerShellCapture {
    param(
        [string]$WorkspaceRoot,
        [string]$ScriptRelativePath,
        [string[]]$Arguments = @()
    )

    $scriptPath = Join-Path $WorkspaceRoot $ScriptRelativePath
    if (-not (Test-Path $scriptPath)) {
        throw "Workspace script not found: $scriptPath"
    }

    Push-Location $WorkspaceRoot
    try {
        $output = & $PowerShellExe -ExecutionPolicy Bypass -File $scriptPath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Fresh-workspace script failed: $ScriptRelativePath"
        }
        return $output
    }
    finally {
        Pop-Location
    }
}

function Invoke-FreshPython {
    param(
        [string]$WorkspaceRoot,
        [string[]]$Arguments
    )

    $pythonExe = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        throw "Fresh-workspace python not found: $pythonExe"
    }

    Push-Location $WorkspaceRoot
    try {
        & $pythonExe @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Fresh-workspace python command failed."
        }
    }
    finally {
        Pop-Location
    }
}

function Stop-WorkspaceProcesses {
    param(
        [string]$WorkspaceRoot
    )

    if (-not (Test-Path $WorkspaceRoot)) {
        return
    }

    $escapedWorkspace = [Regex]::Escape($WorkspaceRoot)
    $candidates = Get-CimInstance Win32_Process | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath -match $escapedWorkspace) -or
        ($_.CommandLine -and $_.CommandLine -match $escapedWorkspace)
    }

    foreach ($candidate in $candidates) {
        if ($candidate.ProcessId -eq $PID) {
            continue
        }
        try {
            Stop-Process -Id $candidate.ProcessId -Force -ErrorAction Stop
        }
        catch {
        }
    }

    Start-Sleep -Milliseconds 400
}

$ResolvedOutputDirectory = Resolve-ProjectPath -Path $OutputDirectory
$BundleDirectory = Join-Path $ResolvedOutputDirectory "source-bundle"
$BundleZipPath = Join-Path $ResolvedOutputDirectory "source-bundle.zip"
$WorkspaceRoot = Join-Path $ResolvedOutputDirectory "workspace"
$EvidenceDirectory = Join-Path $ResolvedOutputDirectory "evidence"
$StatusJsonPath = Join-Path $EvidenceDirectory "fresh-control-room-status.json"
$ReleaseStatusJsonPath = Join-Path $EvidenceDirectory "fresh-release-status.json"
$SummaryPath = Join-Path $ResolvedOutputDirectory "fresh-environment-validation-summary.json"

$FreshPidFile = "data/fresh-control-room.pid"
$FreshStdoutLog = "data/fresh-control-room.log"
$FreshStderrLog = "data/fresh-control-room.err.log"
$SupportBundleDirectory = "dist/clean-run-support"
$SupportBundleZipPath = "dist/clean-run-support.zip"
$ReleasePackDirectory = "dist/clean-run-release-pack"
$ReleasePackZipPath = "dist/clean-run-release-pack.zip"

if (Test-Path $ResolvedOutputDirectory) {
    $existingWorkspaceRoot = Join-Path $ResolvedOutputDirectory "workspace"
    $existingStopScript = Join-Path $existingWorkspaceRoot "stop_control_room.ps1"
    if (Test-Path $existingStopScript) {
        try {
            Invoke-FreshPowerShellFile -WorkspaceRoot $existingWorkspaceRoot -ScriptRelativePath "stop_control_room.ps1" -Arguments @(
                "-PidFile", $FreshPidFile,
                "-BindHost", "127.0.0.1",
                "-Port", $Port.ToString()
            )
        }
        catch {
        }
    }
    Stop-WorkspaceProcesses -WorkspaceRoot $existingWorkspaceRoot
    Remove-Item -Recurse -Force $ResolvedOutputDirectory
}
New-Item -ItemType Directory -Path $ResolvedOutputDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $EvidenceDirectory -Force | Out-Null

& $PowerShellExe -ExecutionPolicy Bypass -File $BuildBundleScript -OutputDirectory $BundleDirectory -CreateZip -ZipPath $BundleZipPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build the source control-room bundle."
}

New-Item -ItemType Directory -Path $WorkspaceRoot -Force | Out-Null
Expand-Archive -Path $BundleZipPath -DestinationPath $WorkspaceRoot -Force

Invoke-FreshPowerShellFile -WorkspaceRoot $WorkspaceRoot -ScriptRelativePath "setup_control_room.ps1" -Arguments @("-ForceEnvTemplate")

Invoke-FreshPython -WorkspaceRoot $WorkspaceRoot -Arguments @(
    "-m",
    "upbit_auto_trader.main",
    "run-loop",
    "--config", "config.example.json",
    "--mode", "paper",
    "--state", "data/paper-state.json",
    "--replay-csv", "data/demo_krw_btc_240m.csv",
    "--max-steps", $PaperSteps.ToString()
)

try {
    Invoke-FreshPowerShellFile -WorkspaceRoot $WorkspaceRoot -ScriptRelativePath "launch_control_room.ps1" -Arguments @(
        "-Config", "config.example.json",
        "-State", "data/paper-state.json",
        "-SelectorState", "data/selector-state.json",
        "-Csv", "data/demo_krw_btc_240m.csv",
        "-Mode", "paper",
        "-BindHost", "127.0.0.1",
        "-Port", $Port.ToString(),
        "-HiddenServerWindow",
        "-StdoutLog", $FreshStdoutLog,
        "-StderrLog", $FreshStderrLog,
        "-PidFile", $FreshPidFile
    )

    $statusJson = Invoke-FreshPowerShellCapture -WorkspaceRoot $WorkspaceRoot -ScriptRelativePath "status_control_room.ps1" -Arguments @(
        "-PidFile", $FreshPidFile,
        "-StdoutLog", $FreshStdoutLog,
        "-StderrLog", $FreshStderrLog,
        "-BindHost", "127.0.0.1",
        "-Port", $Port.ToString(),
        "-AsJson"
    )
    Set-Content -Path $StatusJsonPath -Value ($statusJson -join [Environment]::NewLine) -Encoding utf8

    $releaseStatusJson = Invoke-FreshPython -WorkspaceRoot $WorkspaceRoot -Arguments @(
        "-m",
        "upbit_auto_trader.main",
        "release-status",
        "--config", "config.example.json"
    )
    Set-Content -Path $ReleaseStatusJsonPath -Value ($releaseStatusJson -join [Environment]::NewLine) -Encoding utf8

    Invoke-FreshPowerShellFile -WorkspaceRoot $WorkspaceRoot -ScriptRelativePath "build_control_room_support_bundle.ps1" -Arguments @(
        "-ConfigPath", "config.example.json",
        "-StatePath", "data/paper-state.json",
        "-SelectorStatePath", "data/selector-state.json",
        "-OutputDirectory", $SupportBundleDirectory,
        "-CreateZip",
        "-ZipPath", $SupportBundleZipPath
    )
    Invoke-FreshPowerShellFile -WorkspaceRoot $WorkspaceRoot -ScriptRelativePath "verify_control_room_support_bundle.ps1" -Arguments @(
        "-BundleDirectory", $SupportBundleDirectory,
        "-ZipPath", $SupportBundleZipPath,
        "-RequireZip"
    )

    Invoke-FreshPowerShellFile -WorkspaceRoot $WorkspaceRoot -ScriptRelativePath "build_control_room_release_pack.ps1" -Arguments @(
        "-OutputDirectory", $ReleasePackDirectory,
        "-IncludeSupportBundle",
        "-CreateZip",
        "-ZipPath", $ReleasePackZipPath,
        "-ConfigPath", "config.example.json",
        "-StatePath", "data/paper-state.json",
        "-SelectorStatePath", "data/selector-state.json"
    )
    Invoke-FreshPowerShellFile -WorkspaceRoot $WorkspaceRoot -ScriptRelativePath "verify_control_room_release_pack.ps1" -Arguments @(
        "-PackDirectory", $ReleasePackDirectory,
        "-ZipPath", $ReleasePackZipPath,
        "-RequireZip",
        "-RequireSupportBundle"
    )
}
finally {
    try {
        Invoke-FreshPowerShellFile -WorkspaceRoot $WorkspaceRoot -ScriptRelativePath "stop_control_room.ps1" -Arguments @(
            "-PidFile", $FreshPidFile,
            "-BindHost", "127.0.0.1",
            "-Port", $Port.ToString()
        )
    }
    catch {
    }
}

$ResolvedFreshSupportBundleZip = Join-Path $WorkspaceRoot $SupportBundleZipPath
$ResolvedFreshReleasePackZip = Join-Path $WorkspaceRoot $ReleasePackZipPath
$ResolvedFreshReleasePackDirectory = Join-Path $WorkspaceRoot $ReleasePackDirectory

$summary = [pscustomobject]@{
    validated_at = (Get-Date).ToString("o")
    clean_workspace = $WorkspaceRoot
    source_bundle_zip = $BundleZipPath
    control_room_status_json = $StatusJsonPath
    release_status_json = $ReleaseStatusJsonPath
    support_bundle_zip = $ResolvedFreshSupportBundleZip
    release_pack_zip = $ResolvedFreshReleasePackZip
    release_pack_directory = $ResolvedFreshReleasePackDirectory
    notes = @(
        "Validated on a clean extracted workspace from the generated release bundle.",
        "Confirmed setup, launch, status, release-status, support-bundle, and release-pack flows."
    )
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -Path $SummaryPath -Encoding utf8

Write-Host ("Fresh environment deployment validated: {0}" -f $SummaryPath)
Write-Host ("Support bundle: {0}" -f $ResolvedFreshSupportBundleZip)
Write-Host ("Release pack: {0}" -f $ResolvedFreshReleasePackZip)
