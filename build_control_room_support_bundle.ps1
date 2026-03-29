param(
    [string]$ConfigPath = "config.example.json",
    [string]$StatePath = "data/paper-state.json",
    [string]$SelectorStatePath = "data/selector-state.json",
    [string]$OutputDirectory = "dist/upbit-control-room-support",
    [switch]$CreateZip,
    [string]$ZipPath = "dist/upbit-control-room-support.zip",
    [int]$MaxSessionReports = 4,
    [int]$MaxJobArtifacts = 12
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $ProjectRoot ".env"
$StatusScript = Join-Path $ProjectRoot "status_control_room.ps1"
$SnapshotScript = Join-Path $ProjectRoot "snapshot_control_room_environment.ps1"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$JobHistoryPath = Join-Path $ProjectRoot "data\webui-job-history.jsonl"
$SessionReportsDir = Join-Path $ProjectRoot "data\session-reports"
$WebuiJobsDir = Join-Path $ProjectRoot "data\webui-jobs"
$SensitiveNamePattern = "(?i)(secret|access[_-]?key|api[_-]?key|token|webhook|password)"

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
$ResolvedConfigPath = Resolve-ProjectPath -Path $ConfigPath
$ResolvedStatePath = Resolve-ProjectPath -Path $StatePath
$ResolvedSelectorStatePath = Resolve-ProjectPath -Path $SelectorStatePath

function Ensure-Directory {
    param(
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Add-FileToManifest {
    param(
        [string]$AbsolutePath,
        [string]$RelativePath,
        [System.Collections.ArrayList]$ManifestEntries
    )

    if (-not (Test-Path $AbsolutePath)) {
        return
    }

    $item = Get-Item $AbsolutePath
    [void]$ManifestEntries.Add([pscustomobject]@{
        path = $RelativePath
        size = $item.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -Path $AbsolutePath).Hash
    })
}

function Copy-IntoSupportBundle {
    param(
        [string]$SourcePath,
        [string]$RelativePath,
        [System.Collections.ArrayList]$ManifestEntries
    )

    if (-not (Test-Path $SourcePath)) {
        return $false
    }

    $destinationPath = Join-Path $ResolvedOutputDirectory $RelativePath
    $destinationDirectory = Split-Path -Parent $destinationPath
    if ($destinationDirectory) {
        Ensure-Directory -Path $destinationDirectory
    }
    Copy-Item -Path $SourcePath -Destination $destinationPath -Force
    Add-FileToManifest -AbsolutePath $destinationPath -RelativePath $RelativePath -ManifestEntries $ManifestEntries
    return $true
}

function Write-TextIntoSupportBundle {
    param(
        [string]$Content,
        [string]$RelativePath,
        [System.Collections.ArrayList]$ManifestEntries
    )

    $destinationPath = Join-Path $ResolvedOutputDirectory $RelativePath
    $destinationDirectory = Split-Path -Parent $destinationPath
    if ($destinationDirectory) {
        Ensure-Directory -Path $destinationDirectory
    }
    Set-Content -Path $destinationPath -Value $Content -Encoding utf8
    Add-FileToManifest -AbsolutePath $destinationPath -RelativePath $RelativePath -ManifestEntries $ManifestEntries
}

function Test-SensitiveName {
    param(
        [string]$Name
    )

    if (-not $Name) {
        return $false
    }
    return $Name -match $SensitiveNamePattern
}

function Redact-JsonValue {
    param(
        [object]$Value,
        [string]$PropertyName = ""
    )

    if ($null -eq $Value) {
        return $null
    }

    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        $result = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) {
            if (Test-SensitiveName -Name $property.Name) {
                $result[$property.Name] = "<redacted>"
            }
            else {
                $result[$property.Name] = Redact-JsonValue -Value $property.Value -PropertyName $property.Name
            }
        }
        return [pscustomobject]$result
    }

    if ($Value -is [System.Collections.IDictionary]) {
        $result = [ordered]@{}
        foreach ($key in $Value.Keys) {
            $keyName = [string]$key
            if (Test-SensitiveName -Name $keyName) {
                $result[$keyName] = "<redacted>"
            }
            else {
                $result[$keyName] = Redact-JsonValue -Value $Value[$key] -PropertyName $keyName
            }
        }
        return [pscustomobject]$result
    }

    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        $items = @()
        foreach ($item in $Value) {
            $items += Redact-JsonValue -Value $item -PropertyName $PropertyName
        }
        return $items
    }

    if ((Test-SensitiveName -Name $PropertyName) -and "$Value".Length -gt 0) {
        return "<redacted>"
    }

    return $Value
}

function Write-RedactedJsonFile {
    param(
        [string]$SourcePath,
        [string]$RelativePath,
        [System.Collections.ArrayList]$ManifestEntries
    )

    if (-not (Test-Path $SourcePath)) {
        return
    }

    $raw = Get-Content -Path $SourcePath -Raw
    $parsed = $raw | ConvertFrom-Json
    $redacted = Redact-JsonValue -Value $parsed
    $json = $redacted | ConvertTo-Json -Depth 100
    Write-TextIntoSupportBundle -Content $json -RelativePath $RelativePath -ManifestEntries $ManifestEntries
}

function Write-RedactedEnvFile {
    param(
        [string]$SourcePath,
        [string]$RelativePath,
        [System.Collections.ArrayList]$ManifestEntries
    )

    if (-not (Test-Path $SourcePath)) {
        Write-TextIntoSupportBundle -Content ".env is not present in the project root." -RelativePath $RelativePath -ManifestEntries $ManifestEntries
        return
    }

    $lines = Get-Content -Path $SourcePath
    $redactedLines = foreach ($line in $lines) {
        if ($line -match '^\s*#' -or $line -notmatch '=') {
            $line
            continue
        }

        $parts = $line -split '=', 2
        $name = $parts[0]
        $value = if ($parts.Count -gt 1) { $parts[1] } else { "" }
        if ((Test-SensitiveName -Name $name) -and $value.Trim().Length -gt 0) {
            "{0}=<redacted>" -f $name
        }
        else {
            $line
        }
    }

    Write-TextIntoSupportBundle -Content ($redactedLines -join [Environment]::NewLine) -RelativePath $RelativePath -ManifestEntries $ManifestEntries
}

function Copy-LatestFilesFromDirectory {
    param(
        [string]$SourceDirectory,
        [string]$RelativeDirectory,
        [int]$Count,
        [System.Collections.ArrayList]$ManifestEntries
    )

    if (-not (Test-Path $SourceDirectory)) {
        return
    }

    $files = Get-ChildItem -Path $SourceDirectory -File | Sort-Object LastWriteTime -Descending | Select-Object -First $Count
    foreach ($file in $files) {
        Copy-IntoSupportBundle -SourcePath $file.FullName -RelativePath (Join-Path $RelativeDirectory $file.Name) -ManifestEntries $ManifestEntries | Out-Null
    }
}

if (Test-Path $ResolvedOutputDirectory) {
    Remove-Item -Recurse -Force $ResolvedOutputDirectory
}
Ensure-Directory -Path $ResolvedOutputDirectory

$manifestEntries = New-Object System.Collections.ArrayList

Write-RedactedJsonFile -SourcePath $ResolvedConfigPath -RelativePath "inputs\config.redacted.json" -ManifestEntries $manifestEntries
Write-RedactedEnvFile -SourcePath $EnvPath -RelativePath "inputs\env.redacted.txt" -ManifestEntries $manifestEntries

Copy-IntoSupportBundle -SourcePath $ResolvedStatePath -RelativePath "inputs\paper-state.json" -ManifestEntries $manifestEntries | Out-Null
Copy-IntoSupportBundle -SourcePath ($ResolvedStatePath + ".bak") -RelativePath "inputs\paper-state.json.bak" -ManifestEntries $manifestEntries | Out-Null
Copy-IntoSupportBundle -SourcePath $ResolvedSelectorStatePath -RelativePath "inputs\selector-state.json" -ManifestEntries $manifestEntries | Out-Null
Copy-IntoSupportBundle -SourcePath $JobHistoryPath -RelativePath "diagnostics\webui-job-history.jsonl" -ManifestEntries $manifestEntries | Out-Null

$logFiles = @(
    "data\control-room-server.log",
    "data\control-room-server.err.log",
    "data\web-ui-manual-stdout.log",
    "data\web-ui-manual-stderr.log",
    "data\web-ui-detached-stdout.log",
    "data\web-ui-detached-stderr.log",
    "data\trade-journal.jsonl"
)
foreach ($relativeLogPath in $logFiles) {
    $sourcePath = Join-Path $ProjectRoot $relativeLogPath
    Copy-IntoSupportBundle -SourcePath $sourcePath -RelativePath (Join-Path "logs" (Split-Path -Leaf $relativeLogPath)) -ManifestEntries $manifestEntries | Out-Null
}

Copy-LatestFilesFromDirectory -SourceDirectory $SessionReportsDir -RelativeDirectory "reports" -Count $MaxSessionReports -ManifestEntries $manifestEntries
Copy-LatestFilesFromDirectory -SourceDirectory $WebuiJobsDir -RelativeDirectory "jobs" -Count $MaxJobArtifacts -ManifestEntries $manifestEntries

if (Test-Path $StatusScript) {
    try {
        $statusJson = & $PowerShellExe -ExecutionPolicy Bypass -File $StatusScript -AsJson
        Write-TextIntoSupportBundle -Content $statusJson -RelativePath "diagnostics\control-room-status.json" -ManifestEntries $manifestEntries
    }
    catch {
        Write-TextIntoSupportBundle -Content $_.Exception.Message -RelativePath "diagnostics\control-room-status.error.txt" -ManifestEntries $manifestEntries
    }
}

if (Test-Path $SnapshotScript) {
    try {
        $snapshotOutput = & $PowerShellExe -ExecutionPolicy Bypass -File $SnapshotScript -ConfigPath $ConfigPath -StatePath $StatePath -SelectorStatePath $SelectorStatePath -AsJson
        Write-TextIntoSupportBundle -Content ($snapshotOutput -join [Environment]::NewLine) -RelativePath "diagnostics\environment-snapshot.json" -ManifestEntries $manifestEntries
    }
    catch {
        Write-TextIntoSupportBundle -Content $_.Exception.Message -RelativePath "diagnostics\environment-snapshot.error.txt" -ManifestEntries $manifestEntries
    }
}

if (Test-Path $PythonExe) {
    try {
        $doctorArgs = @("-m", "upbit_auto_trader.main", "doctor", "--config", $ConfigPath)
        if (Test-Path $ResolvedStatePath) {
            $doctorArgs += @("--state", $StatePath)
        }
        if (Test-Path $ResolvedSelectorStatePath) {
            $doctorArgs += @("--selector-state", $SelectorStatePath)
        }
        $doctorOutput = & $PythonExe @doctorArgs
        Write-TextIntoSupportBundle -Content ($doctorOutput -join [Environment]::NewLine) -RelativePath "diagnostics\doctor.json" -ManifestEntries $manifestEntries
    }
    catch {
        Write-TextIntoSupportBundle -Content $_.Exception.Message -RelativePath "diagnostics\doctor.error.txt" -ManifestEntries $manifestEntries
    }
}
else {
    Write-TextIntoSupportBundle -Content ".venv\\Scripts\\python.exe is not available." -RelativePath "diagnostics\doctor.error.txt" -ManifestEntries $manifestEntries
}

$manifest = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    output_directory = $ResolvedOutputDirectory
    file_count = $manifestEntries.Count
    files = $manifestEntries
}

$manifestPath = Join-Path $ResolvedOutputDirectory "support-manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $manifestPath -Encoding utf8

if ($CreateZip) {
    $zipDirectory = Split-Path -Parent $ResolvedZipPath
    if ($zipDirectory) {
        Ensure-Directory -Path $zipDirectory
    }
    Remove-Item -Force $ResolvedZipPath -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $ResolvedOutputDirectory "*") -DestinationPath $ResolvedZipPath
    Write-Host ("Created support bundle zip: {0}" -f $ResolvedZipPath)
}

Write-Host ("Created support bundle: {0}" -f $ResolvedOutputDirectory)
Write-Host ("Included files: {0}" -f $manifestEntries.Count)
