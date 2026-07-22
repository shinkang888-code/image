# LIP — ComfyUI 기동
# 기본: C:\cursor\ComfyUI (venv + CUDA, D: 모델은 extra_model_paths.yaml 로 연결)
# 사용: .\scripts\start-comfy.ps1 [-LowVram] [-WaitReady]

param(
    [string]$ComfyRoot = "C:\cursor\ComfyUI",
    [switch]$LowVram,
    [switch]$WaitReady,
    [int]$Port = 8188,
    [int]$ReadyTimeoutSec = 180
)

$ErrorActionPreference = "Stop"

# Prefer new venv install; fall back to portable embed if D: exists
$venvPy = Join-Path $ComfyRoot "venv\Scripts\python.exe"
$main = Join-Path $ComfyRoot "main.py"
$portableRoot = "D:\ComfyUI_windows_portable"
$portablePy = $null
$portableMain = $null
if (Test-Path "D:\") {
    $portablePy = Join-Path $portableRoot "python_embeded\python.exe"
    $portableMain = Join-Path $portableRoot "ComfyUI\main.py"
}

$py = $null
$workDir = $null
$mainPath = $null

if ((Test-Path $venvPy) -and (Test-Path $main)) {
    $py = $venvPy
    $workDir = $ComfyRoot
    $mainPath = $main
} elseif ((Test-Path "D:\") -and (Test-Path $portablePy) -and (Test-Path $portableMain)) {
    # smoke-check portable python (이 PC에는 D: 없을 수 있음)
    try {
        $p = Start-Process -FilePath $portablePy -ArgumentList @("-c", "print(1)") -WorkingDirectory $portableRoot `
            -Wait -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput "$env:TEMP\lip-comfy-pycheck.txt" `
            -RedirectStandardError "$env:TEMP\lip-comfy-pycheck.err"
        if ($p.ExitCode -eq 0) {
            $py = $portablePy
            $workDir = $portableRoot
            $mainPath = $portableMain
        }
    } catch {}
}

if (-not $py) {
    Write-Host @"
[오류] 사용 가능한 ComfyUI Python 이 없습니다.
  기대 경로: $venvPy
  (구 portable embed 는 D: 에서 손상되어 사용하지 않음)

복구:
  cd C:\cursor\ComfyUI
  python -m venv venv
  .\venv\Scripts\pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
  .\venv\Scripts\pip install -r requirements.txt
"@
    exit 3
}

try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/system_stats" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) {
        Write-Host "ComfyUI 이미 실행 중 (port $Port)"
        exit 0
    }
} catch {}

$argList = @("-s", $mainPath, "--listen", "127.0.0.1", "--port", "$Port")
if ($LowVram) { $argList += "--lowvram" }
# portable standalone flag only for embed layout
if ($workDir -eq $portableRoot) { $argList += "--windows-standalone-build" }

Write-Host "ComfyUI 기동: $workDir"
Write-Host "  $py $($argList -join ' ')"
Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $workDir -WindowStyle Minimized

if (-not $WaitReady) {
    Write-Host "기동 요청됨. Ready 대기: -WaitReady"
    exit 0
}

$deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/system_stats" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Write-Host "ComfyUI ready → http://127.0.0.1:$Port"
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}
throw "ComfyUI ready timeout (${ReadyTimeoutSec}s)"
