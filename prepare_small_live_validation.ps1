param(
    [string]$ConfigPath = "config.example.json",
    [string]$StatePath = "data/live-state.json",
    [string]$SelectorStatePath = "data/selector-state.json",
    [string]$EvidencePath = "dist/live-validation/small-live-validation-readiness.json",
    [string]$SupportOutputDirectory = "dist/upbit-control-room-support-live-preflight",
    [string]$SupportZipPath = "dist/upbit-control-room-support-live-preflight.zip",
    [string]$LiveProfile = "autofinish-live-main"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$BuildSupportScript = Join-Path $ProjectRoot "build_control_room_support_bundle.ps1"
$VerifySupportScript = Join-Path $ProjectRoot "verify_control_room_support_bundle.ps1"
$ResolvedEvidencePath = if ([System.IO.Path]::IsPathRooted($EvidencePath)) { $EvidencePath } else { Join-Path $ProjectRoot $EvidencePath }
$ResolvedSupportOutput = if ([System.IO.Path]::IsPathRooted($SupportOutputDirectory)) { $SupportOutputDirectory } else { Join-Path $ProjectRoot $SupportOutputDirectory }
$ResolvedSupportZip = if ([System.IO.Path]::IsPathRooted($SupportZipPath)) { $SupportZipPath } else { Join-Path $ProjectRoot $SupportZipPath }
$ResolvedConfigPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $ProjectRoot $ConfigPath }
$ResolvedStatePath = if ([System.IO.Path]::IsPathRooted($StatePath)) { $StatePath } else { Join-Path $ProjectRoot $StatePath }
$ResolvedSelectorStatePath = if ([System.IO.Path]::IsPathRooted($SelectorStatePath)) { $SelectorStatePath } else { Join-Path $ProjectRoot $SelectorStatePath }

if (-not (Test-Path $PythonExe)) {
    throw "Python virtualenv not found: $PythonExe"
}

$EvidenceDirectory = Split-Path -Parent $ResolvedEvidencePath
if ($EvidenceDirectory -and -not (Test-Path $EvidenceDirectory)) {
    New-Item -ItemType Directory -Path $EvidenceDirectory -Force | Out-Null
}

function Invoke-PythonJson {
    param(
        [string[]]$Arguments
    )

    $output = & $PythonExe -m upbit_auto_trader.main @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($Arguments -join ' ')"
    }
    return ($output -join "`n" | ConvertFrom-Json)
}

function Invoke-PowerShellScript {
    param(
        [string]$ScriptPath,
        [string[]]$Arguments
    )

    $output = & $PowerShellExe -ExecutionPolicy Bypass -File $ScriptPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PowerShell script failed: $ScriptPath"
    }
    return ($output -join "`n")
}

Push-Location $ProjectRoot
try {
    $doctor = Invoke-PythonJson -Arguments @(
        "doctor",
        "--config", $ConfigPath,
        "--state", $StatePath
    )

    $profilePreview = Invoke-PythonJson -Arguments @(
        "profile-preview",
        "--config", $ConfigPath,
        "--profile", $LiveProfile
    )

    $releaseStatus = Invoke-PythonJson -Arguments @(
        "release-status",
        "--config", $ConfigPath
    )

    $supportBuildOutput = Invoke-PowerShellScript -ScriptPath $BuildSupportScript -Arguments @(
        "-ConfigPath", $ConfigPath,
        "-StatePath", $StatePath,
        "-SelectorStatePath", $SelectorStatePath,
        "-OutputDirectory", $ResolvedSupportOutput,
        "-CreateZip",
        "-ZipPath", $ResolvedSupportZip
    )
    $supportVerifyOutput = Invoke-PowerShellScript -ScriptPath $VerifySupportScript -Arguments @(
        "-BundleDirectory", $ResolvedSupportOutput,
        "-ZipPath", $ResolvedSupportZip,
        "-RequireZip"
    )

    $privateIssues = @()
    if ($doctor.upbit.private_issues) {
        $privateIssues = @($doctor.upbit.private_issues)
    }
    $stateIssues = @()
    if (-not $doctor.state.exists) {
        $stateIssues += "live_state_missing"
    }
    elseif (-not $doctor.state.load_ok) {
        $stateIssues += "live_state_unreadable"
    }

    $payload = [ordered]@{
        generated_at = [DateTime]::UtcNow.ToString("o")
        completed = $false
        reason = "manual_live_trade_required"
        config_path = $ResolvedConfigPath
        live_profile = $LiveProfile
        runbook_path = (Join-Path $ProjectRoot "SMALL_LIVE_VALIDATION_RUNBOOK.md")
        blockers = @($privateIssues + $stateIssues)
        doctor = $doctor
        live_profile_preview = $profilePreview
        release_status = $releaseStatus
        support_bundle = [ordered]@{
            output_dir = $ResolvedSupportOutput
            zip_path = $ResolvedSupportZip
            build_stdout = $supportBuildOutput
            verify_stdout = $supportVerifyOutput
        }
        evidence_targets = [ordered]@{
            live_report = "save the generated live session report after the manual micro-order run"
            support_bundle = $ResolvedSupportZip
            release_pack_status = $releaseStatus.release_artifacts
        }
        next_manual_steps = @(
            "Populate .env with real UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY.",
            "Set upbit.live_enabled=true in the active live config only when you are ready.",
            "Prepare data/live-state.json and rerun doctor until private_ready becomes true.",
            "Use the runbook to submit one tiny live order, confirm fill or cancel behavior, run reconcile, and verify state recovery.",
            "After the manual run, build a fresh support bundle and record the final live session report path in PRODUCT_COMPLETION_CHECKLIST.md."
        )
    }

    $payload | ConvertTo-Json -Depth 100 | Set-Content -Path $ResolvedEvidencePath -Encoding utf8
    $payload | ConvertTo-Json -Depth 100
}
finally {
    Pop-Location
}
