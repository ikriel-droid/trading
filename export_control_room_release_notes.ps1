param(
    [string]$OutputPath = "dist/control-room-release-notes.md",
    [switch]$Print
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$MetadataScript = Join-Path $ProjectRoot "export_control_room_release_metadata.ps1"
$resolvedOutputPath = Join-Path $ProjectRoot $OutputPath

if (-not (Test-Path $MetadataScript)) {
    throw "Release metadata script not found: $MetadataScript"
}

$metadataJson = & $env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe `
    -ExecutionPolicy Bypass `
    -File $MetadataScript `
    -AsJson

$metadata = $metadataJson | ConvertFrom-Json

$lines = @(
    "# Control Room Release Notes",
    "",
    ("Generated: {0}" -f $metadata.generated_at),
    "",
    "## Project",
    "",
    ("- Name: `{0}`" -f $metadata.project.name),
    ("- Version: `{0}`" -f $metadata.project.version),
    ("- Description: {0}" -f $metadata.project.description),
    ("- Required Python: `{0}`" -f $metadata.project.requires_python),
    "",
    "## Git",
    "",
    ("- Branch: `{0}`" -f $metadata.git.branch),
    ("- Commit: `{0}`" -f $metadata.git.head),
    ("- Short commit: `{0}`" -f $metadata.git.short_head),
    "",
    "## Manual Launch Policy",
    "",
    "- App launch stays manual.",
    "- No Windows logon auto-start task is included.",
    "- Primary runtime entry is the hidden-window launcher.",
    "",
    "## Primary Commands",
    "",
    ("- Setup: `{0}`" -f $metadata.entrypoints.setup),
    ("- Launch hidden: `{0}`" -f $metadata.entrypoints.launch_hidden),
    ("- Launch with browser window: `{0}`" -f $metadata.entrypoints.launch_browser),
    ("- Status: `{0}`" -f $metadata.entrypoints.status),
    ("- Restart: `{0}`" -f $metadata.entrypoints.restart),
    ("- Stop: `{0}`" -f $metadata.entrypoints.stop),
    ("- Tail logs: `{0}`" -f $metadata.entrypoints.tail_logs),
    "",
    "## Distribution Commands",
    "",
    ("- Build release bundle: `{0}`" -f $metadata.entrypoints.build_bundle),
    ("- Verify release bundle: `{0}`" -f $metadata.entrypoints.verify_bundle),
    ("- Build support bundle: `{0}`" -f $metadata.entrypoints.build_support_bundle),
    ("- Verify support bundle: `{0}`" -f $metadata.entrypoints.verify_support_bundle),
    "",
    "## Tool Versions",
    "",
    ("- Python: `{0}`" -f $metadata.tools.python),
    ("- Node: `{0}`" -f $metadata.tools.node),
    ("- Git: `{0}`" -f $metadata.tools.git),
    "",
    "## Key Files",
    "",
    ("- README present: `{0}`" -f $metadata.key_files.readme),
    ("- Config example present: `{0}`" -f $metadata.key_files.config_example),
    ("- Env example present: `{0}`" -f $metadata.key_files.env_example),
    ("- Demo CSV present: `{0}`" -f $metadata.key_files.demo_csv),
    ("- Web UI present: `{0}`" -f $metadata.key_files.web_ui),
    "",
    "## Validation To Re-Run",
    "",
    "- `@'` / `compileall` snippet via `.venv\\Scripts\\python.exe`",
    "- `node --check src\\upbit_auto_trader\\webui\\app.js`",
    "- `.venv\\Scripts\\python.exe -m unittest discover -s tests`",
    "",
    "## Notes",
    "",
    "- The control room is packaged for manual Windows use.",
    "- Release/support bundles already support checksum verification.",
    "- Support bundle generation redacts sensitive config and env values."
)

$content = $lines -join [Environment]::NewLine

$outputDirectory = Split-Path -Parent $resolvedOutputPath
if ($outputDirectory -and -not (Test-Path $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}
Set-Content -Path $resolvedOutputPath -Value $content -Encoding utf8

if ($Print) {
    $content
}
