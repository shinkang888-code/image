# LIP — Lexi Image Factory (렉시 이미지 공장) 기획서

로컬 ComfyUI + **8GB GPU** 로, 이 리포의 인테리어 도메인 프롬프트를 활용해
웹사이트용 실사 이미지를 **FHD(1920×1080) · WebP/JPG** 로 **연속·병렬 생성**하는
로컬 데이터 공장.

> Lexi Draft 본체의 "실사 렌더"는 클라우드(Replicate img2img)에 의존한다
> (`apps/web/src/lib/render.ts`, `tasks/TRACK-B-render.md`).
> **LIP는 이걸 로컬로 뒤집는다** — 키·과금·네트워크 없이 내 GPU가 24시간 이미지를 찍어낸다.

---

## 1. 왜 이렇게 설계했나 — "천재병렬작업"의 정체

단일 8GB GPU는 diffusion 스텝을 **진짜로 병렬화할 수 없다** (VRAM 한 장에 모델 한 개).
그래서 "병렬"을 GPU가 아니라 **파이프라인**에서 만든다:

```
   ┌─────────────┐   raw PNG    ┌──────────────────────────────┐
   │  GPU (직렬)  │ ───────────► │  CPU 워커풀 (N 병렬)          │
   │ ComfyUI 생성 │   Queue      │  업스케일→FHD · WebP · JPG 인코딩 │
   │ 쉬지 않음    │ ◄─── 즉시    └──────────────────────────────┘
   └─────────────┘   다음 작업
```

- GPU는 **생성만** 하고 절대 인코딩·디스크 I/O를 기다리지 않는다.
- 업스케일(1344×768 → 1920×1080 Lanczos)과 WebP/JPG 인코딩은 **CPU 워커 N개**가 동시에.
- 결과: GPU 점유율 ~100% 유지 = 시간당 최대 장수. 이게 8GB 한 장으로 뽑는 처리량의 상한.

## 2. 8GB VRAM 파이프라인 — SDXL-Lightning 6스텝

| 항목 | 값 | 이유 |
|---|---|---|
| 모델 | SDXL + Lightning LoRA (또는 Lightning 병합 체크포인트) | 8GB에서 실사 최고 화질/속도 균형 |
| 네이티브 생성 | **1344×768** (16:9, ~1MP) | SDXL 네이티브 해상도, 8GB에 안전 |
| 스텝 / CFG | **6 steps / cfg 2.0** | Lightning은 4~8스텝. 장당 수 초 |
| 샘플러 | `euler` + `sgm_uniform` | Lightning 권장 조합 |
| VRAM 옵션 | ComfyUI `--lowvram` 자동 오프로드 | 8GB 여유 확보 |
| 업스케일 | 1344×768 → **1920×1080** Lanczos (CPU) | GPU 안 씀 → 파이프라인 병렬. ESRGAN은 옵션 토글 |
| 출력 | **WebP**(가장 작음) + **JPG** | 요구사항: 최소 웹포맷 + jpg |

> FHD가 20인치 이하 웹 표시에 최적(≈110 PPI)이라는 판단에 맞춰 **출력 기준을 1920×1080 고정**.
> 16:9 cover-crop으로 왜곡 없이 꽉 채움.

## 3. 프롬프트 소재 — 리포 도메인에서 파생 (조합 폭발)

`packages/ai/src/index.ts`의 인테리어 도메인 지식을 프롬프트 축으로 환원.
`prompts/catalog.json` 이 **축(axes)** 을 정의하고, `prompts.py`가 곱집합으로 전개:

```
interior:  room(거실/침실/주방/욕실/서재…) × style(모던/북유럽/미니멀…)
           × lighting(자연광/골든아워/야간…) × camera(와이드/아이레벨/코너샷…)
web:       backgrounds · banners · textures · hero (범용 웹소재)
```

room 6 × style 6 × light 4 × camera 3 = **432 인테리어 프롬프트** (+ 범용). 시드까지 곱하면 사실상 무한.
각 프롬프트는 내용 해시로 **안정적 id** → 재개(resume)·중복제거 기준.

## 4. 모듈 구조

```
lip/
  lip/config.py       TOML + env fallback (규칙3: 미설정 시 graceful)
  lip/prompts.py      catalog.json → 조합 전개 (순수함수)
  lip/workflow.py     ComfyUI API-format 그래프 빌더 (SDXL-Lightning txt2img)
  lip/comfy_client.py ComfyUI HTTP 클라이언트 (stdlib urllib, 무의존) + Mock(dry-run)
  lip/optimize.py     PIL 이미지 → FHD cover-crop → WebP + JPG (순수, 테스트됨)
  lip/manifest.py     완료 id 기록 = 재개·중복제거
  lip/factory.py      오케스트레이터: GPU직렬 ∥ CPU워커풀
  lip/cli.py          python -m lip {run,list,doctor}
  prompts/catalog.json
  workflows/sdxl_lightning_8gb.json   참고용 정적 템플릿
  tests/              unittest (stdlib) — CPU 부분 전부 통과
```

**의존성**: `Pillow` 하나만 필수 (WebP 내장). ComfyUI 통신은 stdlib `urllib`.
→ CLAUDE.md 규칙4(무의존 우선) 준수.

## 5. Graceful fallback (규칙3)

- ComfyUI 미기동/미설치 → `doctor`가 안내, `run --dry-run`으로 Mock 엔진(그라디언트)으로 파이프라인 검증.
- config 없으면 내장 기본값 + 환경변수로 동작.

## 6. 사용 흐름

```bash
pip install -r lip/requirements.txt          # Pillow만
python -m lip doctor                          # ComfyUI 연결 점검
python -m lip list --tag interior             # 전개된 프롬프트 미리보기
python -m lip run --count 200 --tag interior  # 200장 연속 생성 → out/
python -m lip run --dry-run --count 5         # GPU 없이 파이프라인 검증
```

출력: `out/<id>/image.webp`, `out/<id>/image.jpg` + `out/manifest.jsonl`.

## 7. 로드맵

- [x] CPU 파이프라인(optimize/prompts/workflow/manifest) + 테스트
- [x] ComfyUI HTTP 클라이언트 + Mock dry-run
- [x] CLI (run/list/doctor) · 재개 · 중복제거
- [x] **ESRGAN 품질 모드** (`--quality` → UpscaleModelLoader/ImageUpscaleWithModel)
- [x] **Lexi Draft 씬 → img2img 조감도 실사화** (`render`, `scene.py` — render.ts 로컬 대체)
- [x] **작업제어 대시보드** (LinkNode 이식 — `jobs.py`, `dashboard.py`)
- [x] **멀티 노드 분산 생성** (lasset 이식 — `nodes.py`)
- [x] **재시도 · takes 시드 변주** (voicebox 패턴 — `factory.py`)
- [ ] 반응형 다중 사이즈(WebP srcset) 출력 옵션
- [ ] 대시보드 SSE 실시간 스트리밍 (현재 2초 폴링)

## 8. 이식 통합 아키텍처

```
                 ┌──────────────── 작업제어 대시보드 (LinkNode) ────────────────┐
                 │  KPI · 작업큐 상태배지 · 라이브 이벤트 · 갤러리 · pause/stop  │
                 └───────────────────────────┬──────────────────────────────────┘
                                             │ JobStore (jobs.py)
   프롬프트 카탈로그 ──► Factory (GPU직렬 ∥ CPU워커풀) ──► optimize ──► out/webp+jpg
                                             │ 라운드로빈
                 ┌───────────────────────────┴──────────────────────────────────┐
                 │  Compute Node 레지스트리 (lasset) — local 8GB · PC2 · RunPod  │
                 └────────────────────────────────────────────────────────────────┘
   img2img: Scene JSON (scene.py) ─► 프롬프트 ─► ComfyUI img2img ─► FHD 실사 (render.ts 대체)
```
