param(
    [string]$ReadinessPath = "dist/live-validation/small-live-validation-readiness.json",
    [string]$OutputPath = "dist/small-live-validation-guide/Upbit-Small-Live-Validation-Guide.pptx"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$GeneratorScript = Join-Path $ProjectRoot "scripts\generate_small_live_validation_ppt.py"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtualenv not found: $PythonExe"
}

Push-Location $ProjectRoot
try {
    & $PythonExe $GeneratorScript --readiness $ReadinessPath --output $OutputPath
    if ($LASTEXITCODE -ne 0) {
        throw "generate_small_live_validation_ppt.py failed"
    }
}
finally {
    Pop-Location
}
