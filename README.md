# LIP — Lexi Image Factory (렉시 이미지 공장)

로컬 **ComfyUI + 8GB GPU** 로 웹사이트용 실사 이미지를 **FHD(1920×1080) · WebP/JPG** 로
**연속·병렬 생성**하는 데이터 공장. 클라우드/API 키/과금 없이 내 GPU 한 장으로 돌린다.

> 이 리포(`shinkang888-code/image`)는 LIP 독립 프로젝트다. 원래 Lexi Draft 리포의 `lip/`
> 서브프로젝트로 시작해(클라우드 `render.ts` 의 로컬 대체) 독립 리포로 승격됐다.
> 설계 배경·VRAM 전략·로드맵은 [`PLAN.md`](./PLAN.md) 참고.

## 핵심 아이디어 — "천재병렬작업"
단일 8GB GPU 는 diffusion 을 병렬화 못 한다 → **GPU 는 생성만 직렬로 쉼 없이**,
**FHD 업스케일 + WebP/JPG 인코딩은 CPU 워커풀에서 병렬**. GPU 가 I/O 를 안 기다려 처리량 최대.

## 빠른 시작 (이 PC)

기본 엔진은 **Krea GGUF** (`C:\cursor\ComfyUI\models`) —
sonsu / linkr 작가·전시 배치와 동일 그래프.

```powershell
pip install -r requirements.txt
Copy-Item lip.example.toml lip.toml   # 이미 있으면 생략
.\scripts\factory.ps1 -Count 5 -Tag interior -LowVram
# 또는 단계별:
.\scripts\start-comfy.ps1 -WaitReady -LowVram
python -m lip doctor
python -m lip run --count 5 --tag interior
python -m lip run --dashboard --count 50   # http://localhost:8787
```

| 경로 | 역할 |
|------|------|
| `D:\ComfyUI_windows_portable` | ComfyUI 본체 + Krea GGUF / Qwen TE / VAE |
| `lip.toml` `[gpu] engine=gguf` | LIP → Comfy HTTP (`127.0.0.1:8188`) |
| `scripts/start-comfy.ps1` | Comfy 기동·ready 대기 |
| `scripts/factory.ps1` | 기동 + doctor + 연속 생성 원샷 |

**런타임 (권장)**: `C:\cursor\ComfyUI` (venv + CUDA).  
**모델**: `D:\ComfyUI_windows_portable\ComfyUI\models` (`extra_model_paths.yaml` 연결).  
D:는 WD USB 외장 HDD — 끊김/Delayed Write 시 생성을 멈추고, USB 절전을 끈 뒤 재시도.

## 엔진

| engine | 모델 | 용도 |
|--------|------|------|
| **gguf** (기본 lip.toml) | `krea2_turbo-Q3_K_M.gguf` + Qwen CLIP/VAE | 작가·전시·범용 (지금 설치본) |
| **sdxl** | `sdxl_lightning_4step.safetensors` | 인테리어 실사 고속 (별도 다운로드) |

SDXL 전환 시 `lip.toml`:
```toml
[gpu]
engine = "sdxl"
checkpoint = "sdxl_lightning_4step.safetensors"  # HF에 6step 없음 → 4 또는 8
width = 1344
height = 768
steps = 4
cfg = 2.0
sampler = "euler"
scheduler = "sgm_uniform"
```
체크포인트: `D:\ComfyUI_windows_portable\ComfyUI\models\checkpoints\`

## 설치
```bash
pip install -r requirements.txt      # Pillow 하나만. 통신은 stdlib. Python 3.11+
```

## 사용
```bash
python -m lip doctor                          # 노드·모델 점검
python -m lip list --tag interior             # 전개된 프롬프트 미리보기
python -m lip run --count 200 --tag interior  # 200장 연속 생성 → out/
python -m lip run --dashboard                 # 작업제어 대시보드와 함께 공장 가동
python -m lip run --quality --takes 3         # ESRGAN 고화질 + 프롬프트당 3장 변주
python -m lip run --dry-run --count 5          # GPU 없이 Mock 엔진으로 파이프라인 검증
python -m lip serve                            # 생성 서비스(외부 앱 주문 창구) — 아래 참조
```

### 프롬프트 세트

| tag | 조합 | 용도 |
|---|---:|---|
| `product` | 288 | 커머스 상품컷 — 누끼/스튜디오, PDP 히어로 |
| `detail` | 36 | 매크로 디테일컷 — 소재·마감 블록 |
| `lifestyle` | 60 | 연출·사용장면 — 홈 배너·카드뉴스·릴스 배경 |
| `model` | 36 | 착용컷 — 얼굴은 프레임 밖 크롭(카탈로그 관례) |
| `interior` | 432 | 인테리어 실사 |
| `web` | 72 | 웹 배경·배너 |

set 마다 `quality_suffix`·`negative` 를 따로 둘 수 있다(없으면 전역값). 인테리어의
`natural materials` 같은 화질어가 상품컷에 새지 않게 하는 장치다.

### LEXI Studio 연동 — 생성 서비스

```bash
python -m lip serve                 # 기본 8788. 노드 오프라인이면 mock 으로 graceful 기동
python -m lip serve --strict        # 실 GPU 없으면 기동 거부
python -m lip serve --dry-run       # 강제 mock
```

| 라우트 | 설명 |
|---|---|
| `GET /api/health` | 엔진·모델·노드 상태 (프로바이더 선택 판단용) |
| `POST /api/generate` | `{prompt, seed?, negative?, tag?}` → 이미지 1장 생성 |
| `GET /img/<id>/<file>` | 생성물 (`image.webp` / `image.jpg`) |

LEXI(lexistyle) 쪽에 `LIP_SERVICE_URL=http://localhost:8788` 을 넣으면
`src/lib/images/providers/lip.ts` 가 이 창구로 주문하고, 받은 이미지를
`optimizeAndStore` 가 내려받아 PDP 파이프라인에 태운다. 같은 (프롬프트, 시드)는
캐시 히트로 다시 굽지 않는다. GPU 는 프로세스 락으로 직렬화된다.

### 작업제어 대시보드 (LinkNode 이식)
```bash
python -m lip run --dashboard    # → http://localhost:8787
```

### 멀티 노드 분산 생성 (lasset 이식)
```bash
python -m lip nodes add --name gpu2 --url http://192.168.0.20:8188
python -m lip nodes list
```

### 조감도 실사화 — img2img (SDXL 전용)
```bash
python -m lip render --image snapshot.png --scene plan.lexi.json --style scandinavian
```
`engine=gguf` 일 때는 img2img 미지원 → `engine=sdxl` 로 전환.

출력:
```
out/<prompt-id>/image.webp
out/<prompt-id>/image.jpg
out/manifest.jsonl
```

## 설정
`lip.example.toml` → `lip.toml`. 환경변수(`LIP_COMFY_HOST`, `LIP_ENGINE`, `LIP_WORKERS` …)가 파일보다 우선.

## 구조
```
lip/
  workflow.py     SDXL + GGUF(Krea) 그래프 빌더
  comfy_client.py ComfyUI HTTP + Mock
  factory.py      GPU 직렬 ∥ CPU 워커풀
  service.py      생성 서비스 HTTP 창구 (LEXI Studio 연동)
  jobs.py / dashboard.py / nodes.py
scripts/
  start-comfy.ps1 ComfyUI 기동
  factory.ps1     공장 원샷
workflows/
  krea_gguf_8gb.json
  sdxl_lightning_8gb*.json
```

## 다른 리포에서 이식한 것
| 출처 | 이식 내용 |
|---|---|
| **LinkNode** | 작업큐·KPI 대시보드 → `jobs.py`, `dashboard.py` |
| **lasset** | Compute Node 레지스트리 → `nodes.py` |
| **voicebox** | 재시도·takes → `factory.py` |
| **sonsu / linkr** | Krea GGUF 작가·전시 그래프 → `workflow.build_workflow_gguf` |

## 테스트
```bash
python -m unittest discover -s tests
```
