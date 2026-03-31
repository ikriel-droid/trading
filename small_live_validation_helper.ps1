param(
    [ValidateSet("", "status", "edit-env", "create-live-config", "edit-live-config", "enable-live", "disable-live", "bootstrap", "run-market-validation", "generate-guide", "open-guide", "open-readiness", "open-runbook", "open-checklist")]
    [string]$Action = "",
    [string]$ConfigPath = "config.live.micro.json",
    [string]$Market = "KRW-BTC",
    [double]$BuyKrw = 6000.0,
    [string]$Confirm = ""
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
$MarketValidationScript = Join-Path $ProjectRoot "run_small_live_market_validation.ps1"
$GuideScript = Join-Path $ProjectRoot "generate_small_live_validation_ppt.ps1"
$DefaultLiveStatePath = Join-Path $ProjectRoot "data\live-state.json"
$DefaultMarketValidationSummaryPath = Join-Path $ProjectRoot "dist\live-validation\live-market-validation-summary.json"

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
    $lines += "실거래 준비 도우미 상태"
    $lines += ""
    $lines += "프로젝트: $ProjectRoot"
    $lines += "대상 종목: $ResolvedMarket"
    $lines += "실거래 설정 파일: $ResolvedConfigPath"
    $lines += ".env 파일 존재: $([bool](Test-Path $EnvPath))"
    $lines += "실거래 설정 존재: $([bool](Test-Path $ResolvedConfigPath))"
    $lines += "안내 PPT 존재: $([bool](Test-Path $GuidePath))"
    $lines += "준비 상태 파일 존재: $([bool](Test-Path $ReadinessPath))"

    if ($readiness) {
        $lines += ""
        $lines += "현재 막히는 항목:"
        if ($readiness.blockers -and @($readiness.blockers).Count -gt 0) {
            foreach ($item in @($readiness.blockers)) {
                $lines += " - $item"
            }
        }
        else {
            $lines += " - 없음"
        }

        $releaseStatus = ""
        if ($readiness.release_status -and $readiness.release_status.release_artifacts) {
            $releaseStatus = [string]$readiness.release_status.release_artifacts.status
        }
        if ($releaseStatus) {
            $lines += ""
            $lines += "배포 상태: $releaseStatus"
        }
    }
    else {
        $lines += ""
        $lines += "아직 준비 상태 파일이 없습니다."
        $lines += "먼저 쉬운 준비 실행을 눌러 주세요."
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
        [string]$ResolvedMarket,
        [double]$RequestedBuyKrw = 6000.0,
        [string]$ConfirmText = ""
    )

    switch ($RequestedAction) {
        "status" {
            return Get-StatusText -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket
        }
        "edit-env" {
            $path = Ensure-EnvFile
            Open-FileInEditor -Path $path
            return ".env 파일을 메모장으로 열었습니다."
        }
        "create-live-config" {
            $path = Ensure-LiveConfigFile -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket
            Open-FileInEditor -Path $path
            return "실거래 설정 파일을 만들거나 열었습니다."
        }
        "edit-live-config" {
            $path = Ensure-LiveConfigFile -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket
            Open-FileInEditor -Path $path
            return "실거래 설정 파일을 열었습니다."
        }
        "enable-live" {
            Set-LiveEnabledValue -ResolvedConfigPath $ResolvedConfigPath -Enabled $true -ResolvedMarket $ResolvedMarket | Out-Null
            return "실거래 스위치를 켰습니다."
        }
        "disable-live" {
            Set-LiveEnabledValue -ResolvedConfigPath $ResolvedConfigPath -Enabled $false -ResolvedMarket $ResolvedMarket | Out-Null
            return "실거래 스위치를 껐습니다."
        }
        "bootstrap" {
            Ensure-LiveConfigFile -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket | Out-Null
            $output = Invoke-ProjectPowerShell -ScriptPath $BootstrapScript -Arguments @(
                "-ConfigPath", $ResolvedConfigPath,
                "-Market", $ResolvedMarket
            )
            return "쉬운 준비를 끝냈습니다.`r`n`r`n$output"
        }
        "run-market-validation" {
            Ensure-LiveConfigFile -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket | Out-Null
            if ($ConfirmText -ne "LIVE") {
                throw "시장가 검증을 취소했습니다. 실제 실행할 때만 LIVE 를 입력해 주세요."
            }
            $buyKrwText = $RequestedBuyKrw.ToString([System.Globalization.CultureInfo]::InvariantCulture)
            $output = Invoke-ProjectPowerShell -ScriptPath $MarketValidationScript -Arguments @(
                "-ConfigPath", $ResolvedConfigPath,
                "-StatePath", $DefaultLiveStatePath,
                "-Market", $ResolvedMarket,
                "-BuyKrw", $buyKrwText,
                "-Confirm", $ConfirmText
            )
            return $output
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
            return "안내 PPT를 만들었습니다.`r`n`r`n$output"
        }
        "open-guide" {
            if (-not (Test-Path (Get-LatestGuidePath))) {
                Invoke-ProjectPowerShell -ScriptPath $GuideScript -Arguments @() | Out-Null
            }
            Open-FileDefault -Path (Get-LatestGuidePath)
            return "안내 PPT를 열었습니다."
        }
        "open-readiness" {
            Open-FileInEditor -Path $ReadinessPath
            return "준비 상태 파일을 열었습니다."
        }
        "open-runbook" {
            Open-FileInEditor -Path $RunbookPath
            return "실행 안내 문서를 열었습니다."
        }
        "open-checklist" {
            Open-FileInEditor -Path $ChecklistPath
            return "완료 체크리스트를 열었습니다."
        }
        default {
            throw "Unsupported action: $RequestedAction"
        }
    }
}

$ResolvedConfigPath = Resolve-ProjectPath $ConfigPath
$ResolvedMarket = $Market

if ($Action) {
    $result = Invoke-HelperAction -RequestedAction $Action -ResolvedConfigPath $ResolvedConfigPath -ResolvedMarket $ResolvedMarket -RequestedBuyKrw $BuyKrw -ConfirmText $Confirm
    Write-Output $result
    return
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName Microsoft.VisualBasic

$form = New-Object System.Windows.Forms.Form
$form.Text = "업비트 실거래 준비 도우미"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(980, 700)
$form.BackColor = [System.Drawing.Color]::FromArgb(244, 250, 249)

$title = New-Object System.Windows.Forms.Label
$title.Text = "실거래 소액 검증 도우미"
$title.Font = New-Object System.Drawing.Font('Malgun Gothic', 18, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(24, 20)
$title.Size = New-Object System.Drawing.Size(420, 38)
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "복잡한 터미널 명령 대신 아래 버튼만 눌러서 준비와 검증을 진행할 수 있습니다."
$subtitle.Font = New-Object System.Drawing.Font('Malgun Gothic', 10)
$subtitle.Location = New-Object System.Drawing.Point(26, 58)
$subtitle.Size = New-Object System.Drawing.Size(560, 24)
$form.Controls.Add($subtitle)

$marketLabel = New-Object System.Windows.Forms.Label
$marketLabel.Text = "대상 종목"
$marketLabel.Location = New-Object System.Drawing.Point(28, 100)
$marketLabel.Size = New-Object System.Drawing.Size(60, 22)
$form.Controls.Add($marketLabel)

$marketBox = New-Object System.Windows.Forms.TextBox
$marketBox.Location = New-Object System.Drawing.Point(90, 97)
$marketBox.Size = New-Object System.Drawing.Size(160, 24)
$marketBox.Text = $ResolvedMarket
$form.Controls.Add($marketBox)

$configLabel = New-Object System.Windows.Forms.Label
$configLabel.Text = "실거래 설정"
$configLabel.Location = New-Object System.Drawing.Point(280, 100)
$configLabel.Size = New-Object System.Drawing.Size(90, 22)
$form.Controls.Add($configLabel)

$configBox = New-Object System.Windows.Forms.TextBox
$configBox.Location = New-Object System.Drawing.Point(372, 97)
$configBox.Size = New-Object System.Drawing.Size(420, 24)
$configBox.Text = $ConfigPath
$form.Controls.Add($configBox)

$statusBox = New-Object System.Windows.Forms.TextBox
$statusBox.Location = New-Object System.Drawing.Point(28, 364)
$statusBox.Size = New-Object System.Drawing.Size(908, 266)
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

    $summary = "완료되었습니다."
    $detailLines = @()

    switch ($RequestedAction) {
        "bootstrap" {
            $readiness = Read-Readiness
            $summary = "쉬운 준비를 끝냈습니다."
            $detailLines += "실행: 쉬운 준비 실행"
            $detailLines += "준비 상태 파일: $ReadinessPath"
            if ($readiness -and $readiness.blockers -and @($readiness.blockers).Count -gt 0) {
                $summary = "쉬운 준비는 끝났지만 아직 막히는 항목이 있습니다."
                $detailLines += ""
                $detailLines += "남아 있는 차단 항목:"
                foreach ($item in @($readiness.blockers)) {
                    $detailLines += " - $item"
                }
            }
            else {
                $summary = "쉬운 준비가 끝났고, 막히는 항목이 없습니다."
                $detailLines += ""
                $detailLines += "남아 있는 차단 항목: 없음"
            }
        }
        "generate-guide" {
            $summary = "안내 PPT를 만들었습니다."
            $detailLines += "실행: 안내 PPT 만들기"
            $detailLines += "최신 PPT: $(Get-LatestGuidePath)"
        }
        "run-market-validation" {
            $summary = "시장가 소액 검증을 끝냈습니다."
            $detailLines += "실행: 시장가 소액 검증"
            try {
                $parsed = $RawResult | ConvertFrom-Json
                $detailLines += "대상 종목: $($parsed.market)"
                $detailLines += "매수 금액: $($parsed.buy_krw) KRW"
                $detailLines += "검증 요약: $($parsed.validation_summary_path)"
                $detailLines += "세션 리포트: $($parsed.session_report_json_path)"
                $detailLines += "지원 번들: $($parsed.support_bundle_zip_path)"
                $detailLines += "배포 상태: $($parsed.release_status_json_path)"
            }
            catch {
                $detailLines += "원본 출력:"
                $detailLines += $RawResult.Trim()
            }
        }
        default {
            $summary = (($RawResult -split "(`r`n|`n)")[0]).Trim()
            if (-not $summary) {
                $summary = "완료되었습니다."
            }
            $detailLines += "실행: $RequestedAction"
            $detailLines += $summary
        }
    }

    if ($RawResult -and $RequestedAction -notin @("bootstrap", "generate-guide", "run-market-validation")) {
        $detailLines += ""
        $detailLines += "원본 출력:"
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
        $status += "마지막 실행"
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
        if ($RequestedAction -eq "run-market-validation") {
            $budgetInput = [Microsoft.VisualBasic.Interaction]::InputBox(
                "이번 한 번의 실거래 확인에 사용할 아주 작은 원화 금액을 입력해 주세요.",
                "시장가 검증 금액",
                "6000"
            )
            if ([string]::IsNullOrWhiteSpace($budgetInput)) {
                $script:LastActionSummary = "시장가 검증을 취소했습니다."
                $script:LastActionDetail = "원화 금액을 입력하기 전에 취소했습니다."
                Refresh-StatusBox
                return
            }

            $budget = 0.0
            $parsedBudget = [double]::TryParse(
                $budgetInput,
                [System.Globalization.NumberStyles]::Float,
                [System.Globalization.CultureInfo]::InvariantCulture,
                [ref]$budget
            )
            if (-not $parsedBudget) {
                $parsedBudget = [double]::TryParse($budgetInput, [ref]$budget)
            }
            if (-not $parsedBudget -or $budget -le 0) {
                throw "6000 같은 올바른 원화 금액을 입력해 주세요."
            }

            $confirmInput = [Microsoft.VisualBasic.Interaction]::InputBox(
                "이 동작은 업비트에 실제 시장가 매수 1회와 시장가 매도 1회를 보냅니다.`r`n`r`n계속하려면 LIVE 를 그대로 입력하세요.",
                "실제 주문 확인",
                ""
            )
            if ($confirmInput -ne "LIVE") {
                $script:LastActionSummary = "시장가 검증을 취소했습니다."
                $script:LastActionDetail = "확인 입력값이 LIVE 가 아니었습니다."
                Refresh-StatusBox
                return
            }

            $result = Invoke-HelperAction -RequestedAction $RequestedAction -ResolvedConfigPath $resolvedConfig -ResolvedMarket $marketBox.Text -RequestedBuyKrw $budget -ConfirmText $confirmInput
        }
        else {
            $result = Invoke-HelperAction -RequestedAction $RequestedAction -ResolvedConfigPath $resolvedConfig -ResolvedMarket $marketBox.Text -RequestedBuyKrw $BuyKrw -ConfirmText $Confirm
        }
        Set-ActionFeedback -RequestedAction $RequestedAction -RawResult $result
        Refresh-StatusBox
        [System.Windows.Forms.MessageBox]::Show($script:LastActionSummary, "완료", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
    }
    catch {
        $script:LastActionSummary = "실행 중 문제가 발생했습니다."
        $script:LastActionDetail = $_.Exception.Message
        Refresh-StatusBox
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "문제 발생", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
}

$buttonSpecs = @(
    @{ Text = ".env 열기"; X = 28; Y = 150; Action = "edit-env" },
    @{ Text = "실거래 설정 열기"; X = 188; Y = 150; Action = "create-live-config" },
    @{ Text = "실거래 켜기"; X = 428; Y = 150; Action = "enable-live" },
    @{ Text = "실거래 끄기"; X = 548; Y = 150; Action = "disable-live" },
    @{ Text = "쉬운 준비 실행"; X = 668; Y = 150; Action = "bootstrap" },
    @{ Text = "안내 PPT 열기"; X = 28; Y = 208; Action = "open-guide" },
    @{ Text = "안내 PPT 만들기"; X = 188; Y = 208; Action = "generate-guide" },
    @{ Text = "준비 상태 보기"; X = 348; Y = 208; Action = "open-readiness" },
    @{ Text = "실행 안내 열기"; X = 508; Y = 208; Action = "open-runbook" },
    @{ Text = "체크리스트 열기"; X = 668; Y = 208; Action = "open-checklist" },
    @{ Text = "시장가 검증 실행"; X = 28; Y = 266; Action = "run-market-validation" }
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
$info.Text = "권장 순서: 1) .env 열기  2) 실거래 설정 열기  3) 실거래 켜기  4) 쉬운 준비 실행  5) 시장가 검증 실행"
$info.Location = New-Object System.Drawing.Point(190, 274)
$info.Size = New-Object System.Drawing.Size(900, 24)
$info.Font = New-Object System.Drawing.Font('Malgun Gothic', 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($info)

$info2 = New-Object System.Windows.Forms.Label
$info2.Text = "시장가 검증 실행은 아주 작은 원화 금액을 물어본 뒤, 마지막에 LIVE 를 입력해야 실제 주문을 보냅니다."
$info2.Location = New-Object System.Drawing.Point(190, 298)
$info2.Size = New-Object System.Drawing.Size(900, 22)
$info2.Font = New-Object System.Drawing.Font('Malgun Gothic', 9)
$form.Controls.Add($info2)

Refresh-StatusBox
[void]$form.ShowDialog()
