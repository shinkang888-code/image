# LIP × Cursor Image Engine — 하이브리드 공장 협업 기획

상태: 설계 · 2026-07-23  
연계: [`PLAN.md`](../PLAN.md) · [`fashion-lookbook-1000-plan.md`](./fashion-lookbook-1000-plan.md) · lexistyle `feat/lip-image-provider`

## 0. 한 줄 요약

**로컬 GPU(LIP/Comfy) = 대량·저원가·야간배치 엔진**  
**Cursor Image Engine = 고품질 시드·다양성 샘플·검수 기준샷 엔진**  
둘을 **같은 JobStore·같은 라이브러리 경로·같은 파일명 규약**으로 묶고, 작업 종류에 따라 **라우터가 병렬 배분**한다.

---

## 1. 왜 둘을 같이 쓰는가

| | **LIP (로컬 Comfy)** | **Cursor Image Engine** |
|--|----------------------|-------------------------|
| 정체 | `shinkang888-code/image` + ComfyUI 8GB | Cursor 에이전트 내장 이미지 툴 (Nano Banana / Gemini 계열) |
| 호출 | `python -m lip` · HTTP `/api/generate` · nodes 분산 | 에이전트가 `GenerateImage` 호출 (공개 배치 API 없음) |
| 강점 | 24h 연속, 과금 0, seed 재현, 초당 처리량, XMP/manifest 완전 통제 | 프롬프트·얼굴·다양성·에디토리얼 품질, 기획 중 즉시 시각 피드백 |
| 약점 | SDXL 실사 한계, 얼굴 일관성 LoRA 없이 약함 | 배치 API 부재, 해상도/비율 제약, 에이전트 세션 의존, 대량 비경제 |
| 적합 | 1000장 plant, PDP 물량, 야간 큐 | 프로필 기준샷, 컨셉 보드, 실패 재프롬프트, KR/다양성 QA 샘플 |

→ **동일 목표(화보 라이브러리)에 역할 분담 병렬**, 서로 대체하지 않는다.

---

## 2. 목표 아키텍처

```
                    ┌─────────────────────────────────────────┐
                    │     Lexi HQ / Dashboard (:8787 / Vercel) │
                    │     plan · weights · pause · gallery     │
                    └──────────────────┬──────────────────────┘
                                       │ JobStore (jobs.py)
                                       │ status: pending→routed→generating→optimizing→done
                    ┌──────────────────┴──────────────────────┐
                    │              Router (신규)                │
                    │  rule: job.kind / tag / priority / quota │
                    └─────────────┬───────────────┬───────────┘
                                  │               │
              ┌───────────────────▼───┐   ┌───────▼──────────────────┐
              │  Provider: comfy      │   │  Provider: cursor-image  │
              │  local-8gb · PC2      │   │  Agent bridge (세션/큐)   │
              │  RunPod (nodes.py)    │   │  GenerateImage → drop    │
              └───────────┬───────────┘   └───────────┬──────────────┘
                          │ raw PNG/bytes              │ PNG/WebP drop-in
                          └─────────────┬──────────────┘
                                        ▼
                          CPU 워커풀 (천재병렬 후반)
                          FHD/1600 · WebP+JPG · XMP · lex_ 파일명
                                        ▼
                          C:\cursor\ipplant\library\...
                          manifest.jsonl (engine=comfy|cursor)
```

핵심: **생성만 프로바이더가 다르고, 인코딩·메타·명명·매니페스트는 LIP CPU 파이프 단일 진입점** (`library.save_asset` / 동일 규약).

---

## 3. 라우팅 규칙 (협업 계약)

### 3.1 Job kind → Provider

| kind | 예 | Provider | 비고 |
|------|-----|-----------|------|
| `batch` | plant 1000, commerce 물량 | **comfy only** | Cursor 투입 금지 |
| `pilot` | 파일럿 50, 컨셉 보드 9컷 | **cursor 우선**, 부족분 comfy | 품질 기준선 |
| `identity_seed` | 프로필 20종 기준샷 1~3장 | **cursor** | 이후 comfy가 같은 look 문구로 복제 |
| `retry_quality` | comfy 실패·기형 재시도 | **cursor** (1회) → 실패 시 폐기 | 비용 캡 |
| `serve` | Studio `POST /api/generate` | **comfy** (기본), `?engine=cursor` 수동 | 동기 대기 |

### 3.2 패션화보 1000장에서의 병렬 비율 (권장)

| 구간 | Comfy | Cursor | 목적 |
|------|-------|--------|------|
| P0–P1 | 검증 5 | 기준샷 20 (프로필×1) | 아이덴티티 잠금 |
| P2 파일럿 50 | 40 | 10 | 품질 비교·프롬프트 튜닝 |
| P3–P5 물량 950 | **950** | 0~20 (불량 재시도만) | 처리량 |
| 상시 | 야간 plant | 주간 에이전트 세션 | 시간대 분리 |

**동시성:** Comfy는 GPU 직렬(이미 천재병렬). Cursor는 에이전트 세션에서 N장 순차/소량 병렬 생성 후 drop 폴더에 쌓으면 LIP ingest 워커가 CPU 파이프로 흡수 → **진짜 병렬은 “GPU 굽는 동안 Cursor가 기준샷·파일럿을 채움”**.

---

## 4. Cursor Image Engine 어댑터 설계

공개 배치 API가 없으므로 **브리지 패턴**으로 넣는다.

### 4.1 Drop-folder ingest (1차, 구현 단순)

```
C:\cursor\ipplant\inbox\cursor\
  <jobId>.png          # 에이전트가 GenerateImage 결과 저장
  <jobId>.request.json # prompt, profile, seed hint, kind
```

LIP:

```bash
python -m lip ingest --watch C:\cursor\ipplant\inbox\cursor
```

- 파일 감지 → `optimize` + XMP + `lex_aimodel-...` 명명 → `library/`  
- `manifest`에 `engine=cursor`, `provider=cursor-image`  
- JobStore `done`

에이전트 워크플로:

1. HQ/대시보드 또는 `lip jobs claim --kind identity_seed` 로 pending 목록 출력  
2. Cursor 채팅: “다음 20개 request.json 대로 이미지 생성 후 inbox에 저장”  
3. ingest가 자동 편입

### 4.2 Agent CLI bridge (2차)

```
python -m lip cursor-dispatch --kind identity_seed --limit 20
# → prompts/cursor-batch-YYYYMMDD.jsonl 생성
# Cursor Automation / 수동 에이전트가 읽고 GenerateImage 루프
```

### 4.3 제약 명시 (설계에 고정)

- Cursor 쪽 해상도/비율은 툴 기본값에 종속 → **반드시 LIP CPU cover-crop으로 1600×900 / FHD 통일**  
- seed 재현 불가 → manifest에 `cursor_run_id`만 기록, comfy seed와 분리  
- 대량(>50/세션) 금지 룰을 Router에 hard-cap

---

## 5. LIP 쪽 코드 확장 포인트 (구현 체크리스트)

| 모듈 | 변경 |
|------|------|
| `lip/providers/` (신규) | `ComfyProvider`, `CursorInboxProvider` 공통 인터페이스 `generate(job) -> bytes` |
| `lip/nodes.py` | `kind=comfy\|cursor` 필드. cursor는 base_url 대신 `inbox_dir` |
| `lip/router.py` (신규) | §3 규칙 테이블 |
| `lip/factory.py` | 엔진 선택이 ComfyClient 고정이 아니라 Provider 리스트 |
| `lip/ingest.py` (신규) | inbox watch → library |
| `lip/cli.py` | `ingest`, `cursor-dispatch`, `doctor`에 cursor inbox 헬스 |
| `lip.toml` | `[providers.cursor] enabled, inbox, max_per_day=40` |
| lexistyle `lip.ts` | 유지(comfy serve). 선택: `CURSOR_INBOX` 상태 API는 HQ 대시보드만 |

기존 `nodes add --url http://...` 멀티 GPU 경로는 **그대로** 두고, Cursor는 **이종 프로바이더**로 추가한다 (Comfy 프로토콜 강제 금지).

---

## 6. 데이터·파일명 통일

양쪽 모두 동일:

```
lex_aimodel-{g}-{nat}-{age}-{concept}-{crop}-{outfit}-{pid}-{seedOrRun}.{ext}
```

meta.json 추가 필드:

```json
{
  "engine": "comfy|cursor",
  "provider": "local-8gb|cursor-image",
  "profile": "F-KR-20A",
  "job_kind": "identity_seed"
}
```

검색: `-kr-` / `engine=cursor` 로 HQ 필터.

---

## 7. 운영 리듬 (이 PC 공장)

```
주간 (사람+Cursor 에이전트)
  · identity_seed / pilot / retry_quality
  · 프롬프트·프로필 look 문구 수정
  · 육안 검수 5%

야간·백그라운드 (LIP only)
  · python -m lip plant / fashion batch
  · Comfy --lowvram 직렬 ∥ CPU 워커 4
  · ingest로 낮에 쌓인 cursor inbox 잔량 소진
```

대시보드 KPI:

- `throughput_comfy` / `throughput_cursor`  
- `cost_proxy` (cursor 일일 장수 캡)  
- `reject_rate` by engine

---

## 8. 페이즈

| Phase | 내용 | 완료 기준 |
|-------|------|-----------|
| **H0** | 본 문서 + 라우팅 표 합의 | 리뷰 OK |
| **H1** | inbox 폴더 + `lip ingest` + manifest engine 필드 | cursor PNG 1장 → library 편입 |
| **H2** | Router kind 규칙 + cursor-dispatch JSONL | identity_seed 20 프로필 기준샷 |
| **H3** | 대시보드 엔진별 KPI · 일일 캡 | HQ에서 comfy/cursor 비율 표시 |
| **H4** | 패션 1000: P2를 하이브리드로 실행 | 파일럿 50 = 40 comfy + 10 cursor |

---

## 9. 비목표 (의도적으로 안 함)

- Cursor GenerateImage를 Comfy 대체 대량 엔진으로 쓰는 것  
- Cursor 내부 API 리버스엔지니어링  
- Vercel 서버에서 Cursor 엔진 호출 (에이전트 로컬 전제)

---

## 10. 다음 실행 명령 (합의 후)

```powershell
# H1 스케치
mkdir C:\cursor\ipplant\inbox\cursor
cd C:\cursor\image
# (구현 후) python -m lip ingest --once C:\cursor\ipplant\inbox\cursor
```

lexistyle 연동 순서(기존)는 유지:

1. image clone + Comfy + `lip doctor`  
2. `feat/lip-image-provider` 머지 · `LIP_SERVICE_URL`  
3. **추가:** Cursor inbox 브리지로 기준샷/파일럿 병렬
