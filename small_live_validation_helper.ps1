param(
    [ValidateSet("", "status", "edit-env", "create-live-config", "edit-live-config", "enable-live", "disable-live", "bootstrap", "generate-guide", "open-guide", "open-readiness", "open-runbook", "open-checklist")]
    [string]$Action = "",
    [string]$ConfigPath = "config.live.micro.json",
    [string]$Market = "KRW-BTC"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$EnvExamplePath = Join-Path $ProjectRoot ".env.example"
$EnvPath = Join-Path $ProjectRoot ".env"
$ConfigExamplePath = Join-Path $ProjectRoot "config.example.json"
$ReadinessPath = Join-Path $ProjectRoot "dist\live-validation\small-live-validation-readiness.json"
$GuidePath = Join-Path $ProjectRoot "dist\small-live-validation-guide\Upbit-Small-Live-Validation-Guide.pptx"
$RunbookPath = Join-Path $ProjectRoot "SMALL_LIVE_VALIDATION_RUNBOOK.md"
$ChecklistPath = Join-Path $ProjectRoot "PRODUCT_COMPLETION_CHECKLIST.md"
$BootstrapScript = Join-Path $ProjectRoot "bootstrap_small_live_validation.ps1"
$GuideScript = Join-Path $ProjectRoot "generate_small_live_validation_ppt.ps1"

function Resolve-ProjectPath {
    param([string]$PathValue)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $ProjectRoot $PathValue
}

function Write-Utf8NoBomFile {
    param(
        [string]$Path,
        [string]$Content
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Ensure-EnvFile {
    if (-not (Test-Path $EnvPath)) {
        Copy-Item $EnvExamplePath $EnvPath -Force
    }
    return $EnvPath
}

function Ensure-LiveConfigFile {
    param(
        [string]$ResolvedConfigPath,
        [string]$ResolvedMarket
    )

    if (-not (Test-Path $ResolvedConfigPath)) {
        Copy-Item $ConfigExamplePath $ResolvedConfigPath -Force
    }

    $payload = Get-Content $ResolvedConfigPath -Raw | ConvertFrom-Json
    $payload.market = $ResolvedMarket
    if (-not $payload.upbit) {
        $payload | Add-Member -NotePropertyName upbit -NotePropertyValue ([pscustomobject]@{}) -Force
    }
    $payload.upbit.market = $ResolvedMarket
    if ($null -eq $payload.upbit.live_enabled) {
        $payload.upbit | Add-Member -NotePropertyName live_enabled -NotePropertyValue $false -Force
    }

    Write-Utf8NoBomFile -Path $ResolvedConfigPath -Content ($payload | ConvertTo-Json -Depth 100)
    return $ResolvedConfigPath
}

function Set-LiveEnabledValue {
    param(
        [string]$ResolvedConfigPath,
        [bool]$Enabled,
        [string]$ResolvedMarket
    )

    Ensure-LiveConfigFile -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket | Out-Null
    $payload = Get-Content $ResolvedConfigPath -Raw | ConvertFrom-Json
    $payload.market = $ResolvedMarket
    $payload.upbit.market = $ResolvedMarket
    $payload.upbit.live_enabled = $Enabled
    Write-Utf8NoBomFile -Path $ResolvedConfigPath -Content ($payload | ConvertTo-Json -Depth 100)
    return $ResolvedConfigPath
}

function Read-Readiness {
    if (-not (Test-Path $ReadinessPath)) {
        return $null
    }
    $raw = [System.IO.File]::ReadAllText($ReadinessPath)
    if ($raw.Length -gt 0 -and $raw[0] -eq [char]0xFEFF) {
        $raw = $raw.Substring(1)
    }
    return $raw | ConvertFrom-Json
}

function Get-StatusText {
    param(
        [string]$ResolvedConfigPath,
        [string]$ResolvedMarket
    )

    $readiness = Read-Readiness
    $lines = @()
    $lines += "Small Live Helper Status"
    $lines += ""
    $lines += "Project: $ProjectRoot"
    $lines += "Market: $ResolvedMarket"
    $lines += "Live config: $ResolvedConfigPath"
    $lines += ".env exists: $([bool](Test-Path $EnvPath))"
    $lines += "Live config exists: $([bool](Test-Path $ResolvedConfigPath))"
    $lines += "Guide PPT exists: $([bool](Test-Path $GuidePath))"
    $lines += "Readiness exists: $([bool](Test-Path $ReadinessPath))"

    if ($readiness) {
        $lines += ""
        $lines += "Current blockers:"
        if ($readiness.blockers -and @($readiness.blockers).Count -gt 0) {
            foreach ($item in @($readiness.blockers)) {
                $lines += " - $item"
            }
        }
        else {
            $lines += " - none"
        }

        $releaseStatus = ""
        if ($readiness.release_status -and $readiness.release_status.release_artifacts) {
            $releaseStatus = [string]$readiness.release_status.release_artifacts.status
        }
        if ($releaseStatus) {
            $lines += ""
            $lines += "Release status: $releaseStatus"
        }
    }
    else {
        $lines += ""
        $lines += "No readiness file yet."
        $lines += "Run Easy Prep first."
    }

    return ($lines -join [Environment]::NewLine)
}

function Invoke-ProjectPowerShell {
    param(
        [string]$ScriptPath,
        [string[]]$Arguments
    )
    $output = & $PowerShellExe -ExecutionPolicy Bypass -File $ScriptPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Script failed: $ScriptPath"
    }
    return ($output -join [Environment]::NewLine)
}

function Open-FileInEditor {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "File not found: $Path"
    }
    Start-Process notepad.exe -ArgumentList $Path | Out-Null
}

function Open-FileDefault {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "File not found: $Path"
    }
    Start-Process $Path | Out-Null
}

function Open-ExplorerSelect {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "File not found: $Path"
    }
    Start-Process explorer.exe -ArgumentList "/select,`"$Path`"" | Out-Null
}

function Get-LatestGuidePath {
    $guideDir = Split-Path -Parent $GuidePath
    if (-not (Test-Path $guideDir)) {
        return $GuidePath
    }
    $matches = Get-ChildItem -Path $guideDir -Filter "Upbit-Small-Live-Validation-Guide*.pptx" -File | Sort-Object LastWriteTime -Descending
    if ($matches -and $matches.Count -gt 0) {
        return $matches[0].FullName
    }
    return $GuidePath
}

function Invoke-HelperAction {
    param(
        [string]$RequestedAction,
        [string]$ResolvedConfigPath,
        [string]$ResolvedMarket
    )

    switch ($RequestedAction) {
        "status" {
            return Get-StatusText -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket
        }
        "edit-env" {
            $path = Ensure-EnvFile
            Open-FileInEditor -Path $path
            return ".env opened in Notepad."
        }
        "create-live-config" {
            $path = Ensure-LiveConfigFile -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket
            Open-FileInEditor -Path $path
            return "Live config created or opened."
        }
        "edit-live-config" {
            $path = Ensure-LiveConfigFile -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket
            Open-FileInEditor -Path $path
            return "Live config opened."
        }
        "enable-live" {
            Set-LiveEnabledValue -ResolvedConfigPath $ResolvedConfigPath -Enabled $true -ResolvedMarket $ResolvedMarket | Out-Null
            return "upbit.live_enabled set to true."
        }
        "disable-live" {
            Set-LiveEnabledValue -ResolvedConfigPath $ResolvedConfigPath -Enabled $false -ResolvedMarket $ResolvedMarket | Out-Null
            return "upbit.live_enabled set to false."
        }
        "bootstrap" {
            Ensure-LiveConfigFile -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket | Out-Null
            $output = Invoke-ProjectPowerShell -ScriptPath $BootstrapScript -Arguments @(
                "-ConfigPath", $ResolvedConfigPath,
                "-Market", $ResolvedMarket
            )
            return "Easy prep finished.`r`n`r`n$output"
        }
        "generate-guide" {
            $output = Invoke-ProjectPowerShell -ScriptPath $GuideScript -Arguments @()
            $guideOutputPath = $GuidePath
            try {
                $parsed = $output | ConvertFrom-Json
                if ($parsed -and $parsed.pptx_path) {
                    $guideOutputPath = [string]$parsed.pptx_path
                }
            }
            catch {
                $guideOutputPath = Get-LatestGuidePath
            }
            Open-ExplorerSelect -Path $guideOutputPath
            return "Guide PPT generated.`r`n`r`n$output"
        }
        "open-guide" {
            if (-not (Test-Path (Get-LatestGuidePath))) {
                Invoke-ProjectPowerShell -ScriptPath $GuideScript -Arguments @() | Out-Null
            }
            Open-FileDefault -Path (Get-LatestGuidePath)
            return "Guide PPT opened."
        }
        "open-readiness" {
            Open-FileInEditor -Path $ReadinessPath
            return "Readiness file opened."
        }
        "open-runbook" {
            Open-FileInEditor -Path $RunbookPath
            return "Runbook opened."
        }
        "open-checklist" {
            Open-FileInEditor -Path $ChecklistPath
            return "Checklist opened."
        }
        default {
            throw "Unsupported action: $RequestedAction"
        }
    }
}

$ResolvedConfigPath = Resolve-ProjectPath $ConfigPath
$ResolvedMarket = $Market

if ($Action) {
    $result = Invoke-HelperAction -RequestedAction $Action -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket
    Write-Output $result
    return
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Upbit Small Live Helper"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(980, 700)
$form.BackColor = [System.Drawing.Color]::FromArgb(244, 250, 249)

$title = New-Object System.Windows.Forms.Label
$title.Text = "Upbit Small Live Validation"
$title.Font = New-Object System.Drawing.Font('Malgun Gothic', 18, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(24, 20)
$title.Size = New-Object System.Drawing.Size(420, 38)
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "Use buttons instead of typing long terminal commands."
$subtitle.Font = New-Object System.Drawing.Font('Malgun Gothic', 10)
$subtitle.Location = New-Object System.Drawing.Point(26, 58)
$subtitle.Size = New-Object System.Drawing.Size(560, 24)
$form.Controls.Add($subtitle)

$marketLabel = New-Object System.Windows.Forms.Label
$marketLabel.Text = "Market"
$marketLabel.Location = New-Object System.Drawing.Point(28, 100)
$marketLabel.Size = New-Object System.Drawing.Size(60, 22)
$form.Controls.Add($marketLabel)

$marketBox = New-Object System.Windows.Forms.TextBox
$marketBox.Location = New-Object System.Drawing.Point(90, 97)
$marketBox.Size = New-Object System.Drawing.Size(160, 24)
$marketBox.Text = $ResolvedMarket
$form.Controls.Add($marketBox)

$configLabel = New-Object System.Windows.Forms.Label
$configLabel.Text = "Live Config"
$configLabel.Location = New-Object System.Drawing.Point(280, 100)
$configLabel.Size = New-Object System.Drawing.Size(90, 22)
$form.Controls.Add($configLabel)

$configBox = New-Object System.Windows.Forms.TextBox
$configBox.Location = New-Object System.Drawing.Point(372, 97)
$configBox.Size = New-Object System.Drawing.Size(420, 24)
$configBox.Text = $ConfigPath
$form.Controls.Add($configBox)

$statusBox = New-Object System.Windows.Forms.TextBox
$statusBox.Location = New-Object System.Drawing.Point(28, 340)
$statusBox.Size = New-Object System.Drawing.Size(908, 290)
$statusBox.Multiline = $true
$statusBox.ReadOnly = $true
$statusBox.ScrollBars = "Vertical"
$statusBox.Font = New-Object System.Drawing.Font('Consolas', 10)
$form.Controls.Add($statusBox)

$script:LastActionSummary = ""
$script:LastActionDetail = ""

function Set-ActionFeedback {
    param(
        [string]$RequestedAction,
        [string]$RawResult
    )

    $summary = "Done."
    $detailLines = @()

    switch ($RequestedAction) {
        "bootstrap" {
            $readiness = Read-Readiness
            $summary = "Easy Prep finished."
            $detailLines += "Action: Run Easy Prep"
            $detailLines += "Readiness file: $ReadinessPath"
            if ($readiness -and $readiness.blockers -and @($readiness.blockers).Count -gt 0) {
                $summary = "Easy Prep finished. There are still blockers."
                $detailLines += ""
                $detailLines += "Remaining blockers:"
                foreach ($item in @($readiness.blockers)) {
                    $detailLines += " - $item"
                }
            }
            else {
                $summary = "Easy Prep finished. No blockers found."
                $detailLines += ""
                $detailLines += "Remaining blockers: none"
            }
        }
        "generate-guide" {
            $summary = "Guide PPT generated."
            $detailLines += "Action: Build PPT"
            $detailLines += "Latest PPT: $(Get-LatestGuidePath)"
        }
        default {
            $summary = (($RawResult -split "(`r`n|`n)")[0]).Trim()
            if (-not $summary) {
                $summary = "Done."
            }
            $detailLines += "Action: $RequestedAction"
            $detailLines += $summary
        }
    }

    if ($RawResult -and $RequestedAction -notin @("bootstrap", "generate-guide")) {
        $detailLines += ""
        $detailLines += "Raw output:"
        $detailLines += $RawResult.Trim()
    }

    $script:LastActionSummary = $summary
    $script:LastActionDetail = ($detailLines -join [Environment]::NewLine).Trim()
}

function Refresh-StatusBox {
    $resolvedConfig = Resolve-ProjectPath $configBox.Text
    $status = Get-StatusText -ResolvedConfigPath $resolvedConfig -ResolvedMarket $marketBox.Text
    if ($script:LastActionDetail) {
        $status += [Environment]::NewLine
        $status += [Environment]::NewLine
        $status += "Last action"
        $status += [Environment]::NewLine
        $status += "-----------"
        $status += [Environment]::NewLine
        $status += $script:LastActionDetail
    }
    $statusBox.Text = $status
}

function Invoke-UiAction {
    param([string]$RequestedAction)
    try {
        $resolvedConfig = Resolve-ProjectPath $configBox.Text
        $result = Invoke-HelperAction -RequestedAction $RequestedAction -ResolvedConfigPath $resolvedConfig -ResolvedMarket $marketBox.Text
        Set-ActionFeedback -RequestedAction $RequestedAction -RawResult $result
        Refresh-StatusBox
        [System.Windows.Forms.MessageBox]::Show($script:LastActionSummary, "Done", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
    }
    catch {
        $script:LastActionSummary = "Action failed."
        $script:LastActionDetail = $_.Exception.Message
        Refresh-StatusBox
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
}

$buttonSpecs = @(
    @{ Text = "Open .env"; X = 28; Y = 150; Action = "edit-env" },
    @{ Text = "Create/Open Config"; X = 188; Y = 150; Action = "create-live-config" },
    @{ Text = "LIVE ON"; X = 428; Y = 150; Action = "enable-live" },
    @{ Text = "LIVE OFF"; X = 548; Y = 150; Action = "disable-live" },
    @{ Text = "Run Easy Prep"; X = 668; Y = 150; Action = "bootstrap" },
    @{ Text = "Open PPT"; X = 28; Y = 208; Action = "open-guide" },
    @{ Text = "Build PPT"; X = 188; Y = 208; Action = "generate-guide" },
    @{ Text = "Open Readiness"; X = 348; Y = 208; Action = "open-readiness" },
    @{ Text = "Open Runbook"; X = 508; Y = 208; Action = "open-runbook" },
    @{ Text = "Open Checklist"; X = 668; Y = 208; Action = "open-checklist" }
)

foreach ($spec in $buttonSpecs) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $spec.Text
    $button.Location = New-Object System.Drawing.Point($spec.X, $spec.Y)
    $button.Size = New-Object System.Drawing.Size(140, 40)
    $button.BackColor = [System.Drawing.Color]::FromArgb(13, 148, 136)
    $button.ForeColor = [System.Drawing.Color]::White
    $button.FlatStyle = "Flat"
    $button.Tag = $spec.Action
    $button.Add_Click({
        Invoke-UiAction -RequestedAction $this.Tag
    })
    $form.Controls.Add($button)
}

$info = New-Object System.Windows.Forms.Label
$info.Text = "Recommended order: 1) Open .env  2) Create/Open Config  3) LIVE ON  4) Run Easy Prep  5) Open PPT"
$info.Location = New-Object System.Drawing.Point(30, 276)
$info.Size = New-Object System.Drawing.Size(900, 24)
$info.Font = New-Object System.Drawing.Font('Malgun Gothic', 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($info)

$info2 = New-Object System.Windows.Forms.Label
$info2.Text = "Real-money order execution should still be confirmed manually by you."
$info2.Location = New-Object System.Drawing.Point(30, 300)
$info2.Size = New-Object System.Drawing.Size(900, 22)
$info2.Font = New-Object System.Drawing.Font('Malgun Gothic', 9)
$form.Controls.Add($info2)

Refresh-StatusBox
[void]$form.ShowDialog()
