param(
    [string]$OutputDirectory = "dist/upbit-control-room-release-pack",
    [switch]$IncludeSupportBundle,
    [switch]$CreateZip,
    [string]$ZipPath = "dist/upbit-control-room-release-pack.zip",
    [string]$ConfigPath = "config.example.json",
    [string]$StatePath = "data/paper-state.json",
    [string]$SelectorStatePath = "data/selector-state.json",
    [string]$SupportBundleDirectory = "",
    [string]$SupportBundleZipPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ReleaseMetadataScript = Join-Path $ProjectRoot "export_control_room_release_metadata.ps1"
$ReleaseNotesScript = Join-Path $ProjectRoot "export_control_room_release_notes.ps1"
$BuildBundleScript = Join-Path $ProjectRoot "build_control_room_bundle.ps1"
$VerifyBundleScript = Join-Path $ProjectRoot "verify_control_room_bundle.ps1"
$BuildSupportBundleScript = Join-Path $ProjectRoot "build_control_room_support_bundle.ps1"
$VerifySupportBundleScript = Join-Path $ProjectRoot "verify_control_room_support_bundle.ps1"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

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

function Ensure-Directory {
    param(
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-EntryHash {
    param(
        [string]$Path,
        [string]$RelativePath
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    [pscustomobject]@{
        path = $RelativePath
        sha256 = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash
    }
}

if (Test-Path $ResolvedOutputDirectory) {
    Remove-Item -Recurse -Force $ResolvedOutputDirectory
}
Ensure-Directory -Path $ResolvedOutputDirectory

$releaseBundleDir = Join-Path $ResolvedOutputDirectory "release-bundle"
$releaseBundleZip = Join-Path $ResolvedOutputDirectory "release-bundle.zip"
$supportBundleDir = if ($SupportBundleDirectory) {
    Resolve-ProjectPath -Path $SupportBundleDirectory
}
else {
    Join-Path $ResolvedOutputDirectory "support-bundle"
}
$supportBundleZip = if ($SupportBundleZipPath) {
    Resolve-ProjectPath -Path $SupportBundleZipPath
}
else {
    Join-Path $ResolvedOutputDirectory "support-bundle.zip"
}
$metadataPath = Join-Path $ResolvedOutputDirectory "release-metadata.json"
$notesPath = Join-Path $ResolvedOutputDirectory "release-notes.md"
$manifestPath = Join-Path $ResolvedOutputDirectory "release-pack-manifest.json"

& $PowerShellExe -ExecutionPolicy Bypass -File $ReleaseMetadataScript -OutputPath $metadataPath | Out-Null
& $PowerShellExe -ExecutionPolicy Bypass -File $ReleaseNotesScript -OutputPath $notesPath | Out-Null

& $PowerShellExe -ExecutionPolicy Bypass -File $BuildBundleScript -OutputDirectory $releaseBundleDir -CreateZip -ZipPath $releaseBundleZip | Out-Null
& $PowerShellExe -ExecutionPolicy Bypass -File $VerifyBundleScript -BundleDirectory $releaseBundleDir -ZipPath $releaseBundleZip -RequireZip | Out-Null

$manifestEntries = @()
$metadataEntry = Get-EntryHash -Path $metadataPath -RelativePath "release-metadata.json"
if ($metadataEntry) { $manifestEntries += $metadataEntry }
$notesEntry = Get-EntryHash -Path $notesPath -RelativePath "release-notes.md"
if ($notesEntry) { $manifestEntries += $notesEntry }
$releaseBundleEntry = Get-EntryHash -Path $releaseBundleZip -RelativePath "release-bundle.zip"
if ($releaseBundleEntry) { $manifestEntries += $releaseBundleEntry }

if ($IncludeSupportBundle) {
    & $PowerShellExe -ExecutionPolicy Bypass -File $BuildSupportBundleScript `
        -ConfigPath $ConfigPath `
        -StatePath $StatePath `
        -SelectorStatePath $SelectorStatePath `
        -OutputDirectory $supportBundleDir `
        -CreateZip `
        -ZipPath $supportBundleZip | Out-Null
    & $PowerShellExe -ExecutionPolicy Bypass -File $VerifySupportBundleScript -BundleDirectory $supportBundleDir -ZipPath $supportBundleZip -RequireZip | Out-Null
    $supportBundleEntry = Get-EntryHash -Path $supportBundleZip -RelativePath "support-bundle.zip"
    if ($supportBundleEntry) { $manifestEntries += $supportBundleEntry }
}

$manifest = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    output_directory = $ResolvedOutputDirectory
    includes_support_bundle = [bool]$IncludeSupportBundle
    files = $manifestEntries
}

$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding utf8

if ($CreateZip) {
    $zipDirectory = Split-Path -Parent $ResolvedZipPath
    if ($zipDirectory) {
        Ensure-Directory -Path $zipDirectory
    }
    Remove-Item -Force $ResolvedZipPath -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $ResolvedOutputDirectory "*") -DestinationPath $ResolvedZipPath
    Write-Host ("Created release pack zip: {0}" -f $ResolvedZipPath)
}

Write-Host ("Created control room release pack: {0}" -f $ResolvedOutputDirectory)
Write-Host ("Included support bundle: {0}" -f ([bool]$IncludeSupportBundle))
