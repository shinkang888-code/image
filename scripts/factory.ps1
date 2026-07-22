# LIP 이미지 공장 — ComfyUI 기동 + doctor + 연속 생성
# 사용:
#   .\scripts\factory.ps1
#   .\scripts\factory.ps1 -Count 10 -Tag interior -Dashboard
#   .\scripts\factory.ps1 -DryRun -Count 3

param(
    [int]$Count = 5,
    [string[]]$Tag = @(),
    [switch]$Dashboard,
    [switch]$DryRun,
    [switch]$Quality,
    [int]$Takes = 0,
    [switch]$LowVram,
    [string]$Config = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path "lip.toml") -and (Test-Path "lip.example.toml")) {
    Copy-Item "lip.example.toml" "lip.toml"
    Write-Host "lip.toml 생성 (lip.example.toml 복사)"
}

if (-not $DryRun) {
    & "$Root\scripts\start-comfy.ps1" -WaitReady -LowVram:$LowVram
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$pyArgs = @("-m", "lip", "doctor")
if ($Config) { $pyArgs += @("--config", $Config) }
& python @pyArgs
if (-not $DryRun -and $LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) {
    Write-Host "doctor 실패 (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}
# exit 2 = 모델 경고 — 계속 시도할 수 있으나 실패 가능

$run = @("-m", "lip", "run", "--count", "$Count")
if ($Config) { $run += @("--config", $Config) }
if ($DryRun) { $run += "--dry-run" }
if ($Dashboard) { $run += "--dashboard" }
if ($Quality) { $run += "--quality" }
if ($Takes -gt 0) { $run += @("--takes", "$Takes") }
foreach ($t in $Tag) { $run += @("--tag", $t) }

Write-Host ("python " + ($run -join " "))
& python @run
exit $LASTEXITCODE
