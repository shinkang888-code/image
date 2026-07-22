# LIP — ComfyUI 기동 (D:\ComfyUI_windows_portable)
# 사용: .\scripts\start-comfy.ps1 [-LowVram] [-WaitReady]

param(
    [string]$ComfyRoot = "D:\ComfyUI_windows_portable",
    [switch]$LowVram,
    [switch]$WaitReady,
    [int]$Port = 8188,
    [int]$ReadyTimeoutSec = 180
)

$ErrorActionPreference = "Stop"
$py = Join-Path $ComfyRoot "python_embeded\python.exe"
$main = Join-Path $ComfyRoot "ComfyUI\main.py"
$bat = Join-Path $ComfyRoot "run_nvidia_gpu.bat"

if (-not (Test-Path $main)) { throw "ComfyUI main.py 없음: $main" }
if (-not (Test-Path $py)) { throw "python_embeded 없음: $py — portable 재설치 필요" }

# embed python 실행 가능 여부 (D: WD 볼륨에서 PE 손상/미동기화 사례 있음)
try {
    $p = Start-Process -FilePath $py -ArgumentList @("-c", "print(1)") -WorkingDirectory $ComfyRoot `
        -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput "$env:TEMP\lip-comfy-pycheck.txt" `
        -RedirectStandardError "$env:TEMP\lip-comfy-pycheck.err"
    if ($p.ExitCode -ne 0) {
        throw "exit $($p.ExitCode)"
    }
} catch {
    Write-Host @"
[오류] ComfyUI embed Python 이 이 PC에서 실행되지 않습니다.
  경로: $py
  원인 후보: portable 손상, WD/클라우드 미동기화, VC++ 런타임 누락

복구:
  1) D:\ComfyUI_windows_portable\update\update_comfyui_and_python_dependencies.bat
  2) 또는 https://github.com/comfyanonymous/ComfyUI/releases 에서 windows portable 재압축
  3) VC++: https://aka.ms/vc14/vc_redist.x64.exe

모델(unet/clip/vae)은 유지한 채 python_embeded 만 교체해도 됩니다.
LIP 공장 코드는 준비됨 — Comfy 기동 후: python -m lip doctor
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

$argList = @("-s", $main, "--windows-standalone-build", "--listen", "127.0.0.1", "--port", "$Port")
if ($LowVram) { $argList += "--lowvram" }

Write-Host "ComfyUI 기동: $ComfyRoot"
Write-Host "  python $($argList -join ' ')"
# bat 경유(콘솔 유지) — embed 직접 기동보다 안정적
if ((Test-Path $bat) -and -not $LowVram) {
    Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", "run_nvidia_gpu.bat") -WorkingDirectory $ComfyRoot
} else {
    $joined = ($argList | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }) -join ' '
    Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", "`"$py`" $joined") -WorkingDirectory $ComfyRoot
}

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
