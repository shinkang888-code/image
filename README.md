# LIP — Lexi Image Factory (렉시 이미지 공장)

로컬 **ComfyUI + 8GB GPU** 로 웹사이트용 실사 이미지를 **FHD(1920×1080) · WebP/JPG** 로
**연속·병렬 생성**하는 데이터 공장. 클라우드/API 키/과금 없이 내 GPU 한 장으로 돌린다.

> 이 리포(`shinkang888-code/image`)는 LIP 독립 프로젝트다. 원래 Lexi Draft 리포의 `lip/`
> 서브프로젝트로 시작해(클라우드 `render.ts` 의 로컬 대체) 독립 리포로 승격됐다.
> 설계 배경·VRAM 전략·로드맵은 [`PLAN.md`](./PLAN.md) 참고.

## 핵심 아이디어 — "천재병렬작업"
단일 8GB GPU 는 diffusion 을 병렬화 못 한다 → **GPU 는 생성만 직렬로 쉼 없이**,
**FHD 업스케일 + WebP/JPG 인코딩은 CPU 워커풀에서 병렬**. GPU 가 I/O 를 안 기다려 처리량 최대.

## 설치
```bash
pip install -r requirements.txt      # Pillow 하나만. 통신은 stdlib. Python 3.11+
```

## ComfyUI 준비 (8GB)
1. [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 설치 후 `python main.py --lowvram` 로 기동 (기본 `127.0.0.1:8188`).
2. SDXL-Lightning 체크포인트를 `ComfyUI/models/checkpoints/` 에 배치
   (예: `sdxl_lightning_6step.safetensors`). `lip.toml [gpu] checkpoint` 와 파일명을 맞춘다.

## 사용
```bash
python -m lip doctor                          # 노드 연결·설정 점검
python -m lip list --tag interior             # 전개된 프롬프트 미리보기 (504개)
python -m lip run --count 200 --tag interior  # 200장 연속 생성 → out/
python -m lip run --dashboard                 # 작업제어 대시보드와 함께 공장 가동
python -m lip run --quality --takes 3         # ESRGAN 고화질 + 프롬프트당 3장 변주
python -m lip run --dry-run --count 5          # GPU 없이 Mock 엔진으로 파이프라인 검증
```

### 작업제어 대시보드 (LinkNode 이식)
```bash
python -m lip run --dashboard    # → http://localhost:8787
```
KPI(총/완료/진행/실패/분당처리/총용량) · 작업 큐(상태 배지) · Compute Node 상태 ·
태그 분포 · 라이브 이벤트 피드 · 최근 생성물 갤러리 · 일시정지/재개/중지 제어. 2초 폴링, 무의존.

### 멀티 노드 분산 생성 (lasset 이식)
아무 ComfyUI 호환 URL(로컬 8GB, 두 번째 PC, RunPod 등)을 등록해 8GB 한 장을 넘어 분산:
```bash
python -m lip nodes add --name gpu2 --url http://192.168.0.20:8188
python -m lip nodes add --name runpod --url https://xxx-8188.proxy.runpod.net
python -m lip nodes list          # 활성 노드에 라운드로빈 분산
```

### 조감도 실사화 — img2img (로컬 render.ts 대체)
Lexi Draft 3D 스냅샷 또는 Scene JSON 을 로컬에서 실사 렌더:
```bash
python -m lip render --image snapshot.png --scene plan.lexi.json --style scandinavian
python -m lip render --image snapshot.png --prompt "modern living room" --denoise 0.55 --quality
```

출력:
```
out/<prompt-id>/image.webp   # 가장 작은 웹포맷 (FHD)
out/<prompt-id>/image.jpg    # 호환용 (FHD)
out/manifest.jsonl           # 완료 기록 = 재개·중복제거 기준
```
중단 후 같은 명령을 다시 실행하면 `manifest.jsonl` 을 읽어 **이어서** 생성한다.

## 설정
`lip.example.toml` → `lip.toml` 로 복사해 수정. 파일 없이도 내장 기본값으로 동작하며,
환경변수(`LIP_COMFY_HOST`, `LIP_WORKERS`, `LIP_OUT_DIR` …)가 파일보다 우선한다.

## 구조
```
lip/
  lip/config.py       설정 (TOML + env fallback)
  lip/prompts.py      catalog.json → 조합 전개 (순수함수)
  lip/workflow.py     ComfyUI API-format 그래프 빌더 (SDXL-Lightning)
  lip/comfy_client.py ComfyUI HTTP 클라이언트 (stdlib) + Mock(dry-run)
  lip/optimize.py     FHD cover-crop → WebP + JPG (순수)
  lip/manifest.py     재개·중복제거
  lip/factory.py      오케스트레이터 (GPU 직렬 ∥ CPU 워커풀 · 멀티노드 · 재시도 · takes)
  lip/jobs.py         작업제어 코어 — 작업큐·이벤트·제어 (LinkNode 명령큐 이식)
  lip/nodes.py        Compute Node 레지스트리 (lasset 이식)
  lip/dashboard.py    작업제어 대시보드 서버 (LinkNode 대시보드 이식, stdlib)
  lip/scene.py        Scene JSON → 실사 프롬프트 (로컬 render.ts 대체)
  lip/cli.py          python -m lip {doctor,list,run,render,nodes,dashboard}
  prompts/catalog.json
  workflows/          참고용 정적 워크플로우
  tests/              unittest (stdlib) — 33개 통과
```

## 다른 리포에서 이식한 것
| 출처 | 이식 내용 |
|---|---|
| **LinkNode** (하드웨어 관제 콘솔) | 명령큐 생명주기(pending→…→done/failed/cancelled)·KPI 대시보드·라이브 이벤트 피드·제어 → `jobs.py`, `dashboard.py` |
| **lasset** (Game Asset Studio) | provider-agnostic Compute Node 레지스트리(멀티 ComfyUI 분산) → `nodes.py` |
| **voicebox** (AI 음성 스튜디오) | 비동기 큐·실패 재시도·takes(시드 변주) 패턴 → `factory.py` |

## 테스트
```bash
python -m unittest discover -s tests
```
