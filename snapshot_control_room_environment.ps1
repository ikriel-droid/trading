param(
    [string]$ConfigPath = "config.example.json",
    [string]$StatePath = "data/paper-state.json",
    [string]$SelectorStatePath = "data/selector-state.json",
    [switch]$AsJson,
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedConfigPath = Join-Path $ProjectRoot $ConfigPath
$ResolvedStatePath = Join-Path $ProjectRoot $StatePath
$ResolvedSelectorStatePath = Join-Path $ProjectRoot $SelectorStatePath
$EnvPath = Join-Path $ProjectRoot ".env"
$StatusScript = Join-Path $ProjectRoot "status_control_room.ps1"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$NodeExe = Join-Path ${env:ProgramFiles} "nodejs\node.exe"

function Invoke-ToolCapture {
    param(
        [string]$Command,
        [string[]]$Arguments = @()
    )

    try {
        $output = & $Command @Arguments 2>$null
        $exitCode = $LASTEXITCODE
        return [pscustomobject]@{
            ok = ($exitCode -eq 0)
            exit_code = $exitCode
            text = ($output -join [Environment]::NewLine)
        }
    }
    catch {
        return [pscustomobject]@{
            ok = $false
            exit_code = -1
            text = $_.Exception.Message
        }
    }
}

function Get-OptionalVersion {
    param(
        [string]$CommandPath,
        [string[]]$Arguments
    )

    if (-not (Test-Path $CommandPath) -and -not (Get-Command $CommandPath -ErrorAction SilentlyContinue)) {
        return $null
    }

    $capture = Invoke-ToolCapture -Command $CommandPath -Arguments $Arguments
    if (-not $capture.ok) {
        return $null
    }
    return $capture.text.Trim()
}

function Get-GitSnapshot {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        return $null
    }

    $branch = Invoke-ToolCapture -Command "git" -Arguments @("-C", $ProjectRoot, "branch", "--show-current")
    $head = Invoke-ToolCapture -Command "git" -Arguments @("-C", $ProjectRoot, "rev-parse", "HEAD")
    $status = Invoke-ToolCapture -Command "git" -Arguments @("-C", $ProjectRoot, "status", "--short")

    [pscustomobject]@{
        branch = if ($branch.ok) { $branch.text.Trim() } else { "" }
        head = if ($head.ok) { $head.text.Trim() } else { "" }
        worktree_clean = ($status.ok -and [string]::IsNullOrWhiteSpace($status.text))
        changed_file_count = if ($status.ok -and -not [string]::IsNullOrWhiteSpace($status.text)) { @($status.text -split "`r?`n").Count } else { 0 }
    }
}

function Get-ControlRoomStatusSnapshot {
    if (-not (Test-Path $StatusScript)) {
        return $null
    }

    $capture = Invoke-ToolCapture -Command $env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe -Arguments @(
        "-ExecutionPolicy", "Bypass",
        "-File", $StatusScript,
        "-AsJson"
    )
    if (-not $capture.ok -or [string]::IsNullOrWhiteSpace($capture.text)) {
        return [pscustomobject]@{
            error = $capture.text
        }
    }

    try {
        return $capture.text | ConvertFrom-Json
    }
    catch {
        return [pscustomobject]@{
            error = "Failed to parse control-room status JSON."
            raw = $capture.text
        }
    }
}

$osInfo = Get-CimInstance Win32_OperatingSystem
$computerInfo = Get-CimInstance Win32_ComputerSystem
$gitSnapshot = Get-GitSnapshot
$controlRoomStatus = Get-ControlRoomStatusSnapshot
$pipList = if (Test-Path $VenvPython) {
    Invoke-ToolCapture -Command $VenvPython -Arguments @("-m", "pip", "list", "--format=json")
} else {
    $null
}

$pipPackages = @()
if ($pipList -and $pipList.ok -and -not [string]::IsNullOrWhiteSpace($pipList.text)) {
    try {
        $pipPackages = $pipList.text | ConvertFrom-Json
    }
    catch {
        $pipPackages = @()
    }
}

$snapshot = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    project_root = $ProjectRoot
    user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    machine = [pscustomobject]@{
        computer_name = $env:COMPUTERNAME
        manufacturer = $computerInfo.Manufacturer
        model = $computerInfo.Model
        logical_processors = $computerInfo.NumberOfLogicalProcessors
        total_physical_memory_bytes = [int64]$computerInfo.TotalPhysicalMemory
    }
    os = [pscustomobject]@{
        caption = $osInfo.Caption
        version = $osInfo.Version
        build_number = $osInfo.BuildNumber
        architecture = $osInfo.OSArchitecture
        last_boot_up_time = $osInfo.LastBootUpTime
    }
    tools = [pscustomobject]@{
        python = Get-OptionalVersion -CommandPath $VenvPython -Arguments @("--version")
        node = Get-OptionalVersion -CommandPath $NodeExe -Arguments @("--version")
        git = $gitSnapshot
        pip_package_count = @($pipPackages).Count
        pip_packages = $pipPackages
    }
    files = [pscustomobject]@{
        config_exists = (Test-Path $ResolvedConfigPath)
        state_exists = (Test-Path $ResolvedStatePath)
        state_backup_exists = (Test-Path ($ResolvedStatePath + ".bak"))
        selector_state_exists = (Test-Path $ResolvedSelectorStatePath)
        env_exists = (Test-Path $EnvPath)
        webui_jobs_exists = (Test-Path (Join-Path $ProjectRoot "data\webui-jobs"))
        session_reports_exists = (Test-Path (Join-Path $ProjectRoot "data\session-reports"))
    }
    control_room = $controlRoomStatus
}

$json = $snapshot | ConvertTo-Json -Depth 8

if ($OutputPath) {
    $resolvedOutputPath = Join-Path $ProjectRoot $OutputPath
    $outputDirectory = Split-Path -Parent $resolvedOutputPath
    if ($outputDirectory -and -not (Test-Path $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }
    Set-Content -Path $resolvedOutputPath -Value $json -Encoding utf8
}

if ($AsJson -or -not $OutputPath) {
    $json
}
