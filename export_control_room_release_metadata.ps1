param(
    [string]$OutputPath = "dist/control-room-release-metadata.json",
    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyprojectPath = Join-Path $ProjectRoot "pyproject.toml"
$ReadmePath = Join-Path $ProjectRoot "README.md"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$NodeExe = Join-Path ${env:ProgramFiles} "nodejs\node.exe"

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

function Get-ToolText {
    param(
        [string]$CommandPath,
        [string[]]$Arguments
    )

    try {
        $output = & $CommandPath @Arguments 2>$null
        if ($LASTEXITCODE -eq 0) {
            return ($output -join [Environment]::NewLine).Trim()
        }
    }
    catch {
    }
    return ""
}

function Get-GitValue {
    param(
        [string[]]$Arguments
    )

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        return ""
    }

    try {
        $output = & git -C $ProjectRoot @Arguments 2>$null
        if ($LASTEXITCODE -eq 0) {
            return ($output -join [Environment]::NewLine).Trim()
        }
    }
    catch {
    }
    return ""
}

function Get-PyprojectValue {
    param(
        [string]$Content,
        [string]$Name
    )

    $pattern = '^{0}\s*=\s*"([^"]+)"' -f [regex]::Escape($Name)
    $match = [regex]::Match($Content, $pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
    if ($match.Success) {
        return $match.Groups[1].Value
    }
    return ""
}

$pyprojectContent = if (Test-Path $PyprojectPath) { Get-Content -Path $PyprojectPath -Raw } else { "" }
$version = Get-PyprojectValue -Content $pyprojectContent -Name "version"
$projectName = Get-PyprojectValue -Content $pyprojectContent -Name "name"
$description = Get-PyprojectValue -Content $pyprojectContent -Name "description"
$requiresPython = Get-PyprojectValue -Content $pyprojectContent -Name "requires-python"

$metadata = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    project = [pscustomobject]@{
        name = $projectName
        version = $version
        description = $description
        requires_python = $requiresPython
    }
    git = [pscustomobject]@{
        branch = Get-GitValue -Arguments @("branch", "--show-current")
        head = Get-GitValue -Arguments @("rev-parse", "HEAD")
        short_head = Get-GitValue -Arguments @("rev-parse", "--short", "HEAD")
    }
    tools = [pscustomobject]@{
        python = if (Test-Path $VenvPython) { Get-ToolText -CommandPath $VenvPython -Arguments @("--version") } else { "" }
        node = if (Test-Path $NodeExe) { Get-ToolText -CommandPath $NodeExe -Arguments @("--version") } else { "" }
        git = if (Get-Command git -ErrorAction SilentlyContinue) { Get-ToolText -CommandPath "git" -Arguments @("--version") } else { "" }
    }
    entrypoints = [pscustomobject]@{
        setup = ".\\setup_control_room.cmd"
        launch_hidden = ".\\launch_control_room_hidden.cmd"
        launch_browser = ".\\launch_control_room.cmd"
        status = ".\\status_control_room.cmd"
        restart = ".\\restart_control_room.cmd"
        stop = ".\\stop_control_room.cmd"
        tail_logs = ".\\tail_control_room_logs.cmd"
        build_bundle = ".\\build_control_room_bundle.cmd -CreateZip"
        verify_bundle = ".\\verify_control_room_bundle.cmd -RequireZip"
        build_support_bundle = ".\\build_control_room_support_bundle.cmd -CreateZip"
        verify_support_bundle = ".\\verify_control_room_support_bundle.cmd -RequireZip"
    }
    key_files = [pscustomobject]@{
        readme = (Test-Path $ReadmePath)
        config_example = (Test-Path (Join-Path $ProjectRoot "config.example.json"))
        env_example = (Test-Path (Join-Path $ProjectRoot ".env.example"))
        demo_csv = (Test-Path (Join-Path $ProjectRoot "data\demo_krw_btc_15m.csv"))
        web_ui = (Test-Path (Join-Path $ProjectRoot "src\upbit_auto_trader\webui\index.html"))
    }
}

$json = $metadata | ConvertTo-Json -Depth 6

if ($OutputPath) {
    $resolvedOutputPath = Resolve-ProjectPath -Path $OutputPath
    $outputDirectory = Split-Path -Parent $resolvedOutputPath
    if ($outputDirectory -and -not (Test-Path $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }
    Set-Content -Path $resolvedOutputPath -Value $json -Encoding utf8
}

if ($AsJson -or -not $OutputPath) {
    $json
}
