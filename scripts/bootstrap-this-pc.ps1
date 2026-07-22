# Lexi IPlant factory bootstrap — this PC (RTX 4060 Ti 8GB)
# 천재병렬: GPU(Comfy) 직렬 ∥ CPU WebP/JPG 인코딩 병렬
# 사용:
#   .\scripts\bootstrap-this-pc.ps1 -DownloadCheckpoint
#   .\scripts\bootstrap-this-pc.ps1 -DownloadCheckpoint -PlantTotal 5 -DryRun
#   .\scripts\bootstrap-this-pc.ps1 -DownloadCheckpoint -PlantTotal 100
param(
  [switch]$SkipComfyStart,
  [switch]$DownloadCheckpoint,
  [int]$PlantTotal = 0,
  [switch]$DryRun,
  [switch]$PreferLightning
)
$ErrorActionPreference = "Stop"
$ImageRoot = "C:\cursor\image"
$ComfyRoot = "C:\cursor\ComfyUI"
$CkptDir = Join-Path $ComfyRoot "models\checkpoints"
$IplantRoot = "C:\cursor\ipplant"

New-Item -ItemType Directory -Force -Path $IplantRoot, $CkptDir | Out-Null
if (-not (Test-Path "$ImageRoot\lip.toml") -and (Test-Path "$ImageRoot\lip.example.toml")) {
  Copy-Item "$ImageRoot\lip.example.toml" "$ImageRoot\lip.toml"
  Write-Host "lip.toml 생성"
}

function Get-CkptSizeMB([string]$name) {
  $p = Join-Path $CkptDir $name
  if (Test-Path $p) { return [math]::Round((Get-Item $p).Length / 1MB) }
  return 0
}

if ($DownloadCheckpoint) {
  $lightning = "sdxl_lightning_4step.safetensors"
  $base = "sd_xl_base_1.0.safetensors"
  $gotLightning = (Get-CkptSizeMB $lightning) -gt 1000

  if ($PreferLightning -or -not $gotLightning) {
    Write-Host "HF: ByteDance/SDXL-Lightning → $lightning"
    try {
      hf download ByteDance/SDXL-Lightning $lightning --local-dir $CkptDir
      $gotLightning = (Get-CkptSizeMB $lightning) -gt 1000
    } catch {
      Write-Host "Lightning 다운로드 실패(HF 일시장애 가능): $($_.Exception.Message)"
    }
  }

  if (-not $gotLightning) {
    Write-Host "폴백: stabilityai SDXL base → $base (steps/cfg 는 lip.toml 에서 조정)"
    if ((Get-CkptSizeMB $base) -lt 1000) {
      hf download stabilityai/stable-diffusion-xl-base-1.0 $base --local-dir $CkptDir
    }
    $toml = Join-Path $ImageRoot "lip.toml"
    if (Test-Path $toml) {
      $txt = Get-Content $toml -Raw
      if ($txt -match 'checkpoint\s*=\s*"sdxl_lightning') {
        $txt = $txt -replace 'checkpoint\s*=\s*"[^"]+"', "checkpoint = `"$base`""
        $txt = $txt -replace 'steps\s*=\s*\d+', 'steps = 20'
        $txt = $txt -replace 'cfg\s*=\s*[\d.]+', 'cfg = 7.0'
        Set-Content -Path $toml -Value $txt -Encoding utf8
        Write-Host "lip.toml → checkpoint=$base steps=20 cfg=7.0"
      }
    }
  } else {
    Write-Host "Lightning 체크포인트 OK ($((Get-CkptSizeMB $lightning)) MB)"
  }
}

if (-not $SkipComfyStart -and -not $DryRun) {
  & "$ImageRoot\scripts\start-comfy.ps1" -WaitReady -LowVram
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Set-Location $ImageRoot
python -m lip doctor
$docExit = $LASTEXITCODE

if ($PlantTotal -gt 0) {
  $pyArgs = @("-m", "lip", "plant", "--total", "$PlantTotal", "--weights", "websource:30,commerce:40,aimodel:30")
  if ($DryRun) { $pyArgs += "--dry-run" }
  Write-Host ("python " + ($pyArgs -join " "))
  python @pyArgs
  exit $LASTEXITCODE
}

exit $docExit
