# AI 패션화보 1000장 작업 기획

상태: P0 샘플 검증 · 작성 2026-07-23  
엔진: LIP (`C:\cursor\image`) + ComfyUI 8GB · 천재병렬  
출력: `C:\cursor\ipplant\library\aimodel\`

## 1. 목표

| 항목 | 값 |
|------|-----|
| 총량 | **1000장** (WebP+JPG, 1600×900 web / FHD 옵션) |
| 성별 | 여성 **550** (55%) · 남성 **450** (45%) |
| 국적 | 한국인 **600** (60%) · 기타 **400** (40%) |
| 얼굴 | **노출** (화보·브랜드용). 기존 catalog `face out of frame` 과 별도 세트 |
| 일관성 | 프로필 20종 × `identitySeed` — 같은 look 문구로 여러 컨셉 |

## 2. 국적 배분 (기타 40% 세분)

| 코드 | 그룹 | 장수 | % |
|------|------|------|---|
| `kr` | 한국인 | 600 | 60 |
| `jp` | 일본 | 80 | 8 |
| `cn` | 중국 | 60 | 6 |
| `sea` | 동남아 (VN/TH/PH/ID) | 80 | 8 |
| `sa` | 남아시아 (IN) | 40 | 4 |
| `eu` | 서유럽/백인 | 60 | 6 |
| `af` | 흑인/아프리카계 | 40 | 4 |
| `lat` | 라틴계 | 40 | 4 |

성별은 각 국적 버킷 안에서도 **F:M ≈ 55:45**.

## 3. 컨셉 9종

| ID | 컨셉 | 장수 | 용도 |
|----|------|------|------|
| `studio` | Studio Editorial | 180 | 뉴트럴 백드롭 룩북 |
| `street` | Urban Street | 160 | 도시·서울 거리 |
| `cafe` | Cafe Lifestyle | 120 | 라이프·PDP |
| `office` | Smart Casual | 120 | 오피스 |
| `outer` | Seasonal Outer | 120 | 코트·패딩 |
| `resort` | Resort / Travel | 100 | 여행·리조트 |
| `night` | Night Out | 80 | 이브닝 |
| `beauty` | Beauty Closeup | 60 | 하프·뷰티 |
| `wear` | Product Wear | 60 | 착용 디테일 |

## 4. 프로필 설계 (identitySeed)

프롬프트 고정 블록 예:

```
identity: {look}, East Asian Korean adult woman in her 20s,
same person across shots, natural skin texture, editorial fashion model
```

| Profile ID | G | Nat | Age | 주력 |
|------------|---|-----|-----|------|
| F-KR-20A … F-KR-40A | F | kr | 20–40 | 스튜디오·카페·오피스·이브닝·아우터 |
| M-KR-20A … M-KR-40A | M | kr | 20–40 | 스트릿·오피스·캐주얼·테일러드 |
| F/M + jp/cn/sea/sa/eu/af/lat | — | — | 20–30 | 다양성 버킷 대표 1–2명씩 |

전체 20종 상세 look 문구는 `prompts/fashion-lookbook-profiles.json` 참고.

## 5. 검색형 파일명

```
lex_aimodel-{g}-{nat}-{age}-{concept}-{crop}-{outfit}-{pid}-{seed}.webp
```

예:

```
lex_aimodel-f-kr-20s-studio-full-linen-blazer-FKR20A-10042.webp
```

| 토큰 | 의미 | 검색 예 |
|------|------|---------|
| `g` | `f` / `m` | `lex_aimodel-f-` |
| `nat` | `kr` `jp` `sea` … | `-kr-` |
| `age` | `20s` `30s` `40s` | `-20s-` |
| `concept` | studio/street/… | `-studio-` |
| `crop` | `full` `half` `detail` | `-half-` |
| `outfit` | 의상 슬러그 | `linen-blazer` |
| `pid` | 프로필 ID 압축 | `FKR20A` |
| `seed` | 시드 | 재현 |

경로: `library/aimodel/female_lookbook/` 또는 `male_lookbook/`  
사이드카: 동일 stem `.meta.json` (프롬프트 전문·국적·프로필).

## 6. 실행 페이즈

| Phase | 작업 | 장수 | ETA (base 20step) |
|-------|------|------|-------------------|
| **P0** | 샘플 5장 LIVE (남/여·KR/기타·컨셉 섞음) | 5 | **완료 2026-07-23** (~14s/장 warm) |
| **P1** | 프로필 JSON + 파일명 빌더 + catalog 세트 | — | 0.5일 |
| **P2** | 파일럿 50장 · 검수 게이트 | 50 | ~12분 |
| **P3** | 배치 A — KR 중심 | 300 | ~1.2h |
| **P4** | 배치 B — 다양성 | 300 | ~1.2h |
| **P5** | 배치 C + 실패 재시도·리포트 | 350 | ~1.4h |

실측(모델 워밍 후): **~14초/장**. 1000장 ≈ **4시간**. Lightning 4step 시 추가 단축.

### 배치 명령 (예정)

```powershell
cd C:\cursor\image
.\scripts\start-comfy.ps1 -WaitReady -LowVram
python -m lip fashion --plan prompts/fashion-lookbook-1000.plan.json --dashboard
# 또는 plant 확장:
python -m lip plant --total 1000 --weights aimodel:100 --catalog prompts/fashion-lookbook.json
```

## 7. 품질 게이트

**자동 거부:** 손 기형, 얼굴 붕괴, 워터마크/텍스트, manifest 중복, 파일명 규약 위반  
**수동:** 배치당 5% 샘플링, 프로필당 일관성 3컷, PDP 크롭 적합성  
**법적:** XMP `trainedAlgorithmicMedia` + 저작권 귀속 (기존 LIP seo 파이프)

## 8. P0 샘플 5장 스펙

| # | Profile | Nat | Concept | Crop | Outfit |
|---|---------|-----|---------|------|--------|
| 1 | F-KR-20A | kr | studio | full | linen blazer |
| 2 | M-KR-30A | kr | office | half | charcoal suit jacket |
| 3 | F-SEA-20A | sea | resort | full | white linen dress |
| 4 | M-EU-30A | eu | street | full | denim jacket |
| 5 | F-AF-20A | af | beauty | half | black turtleneck |

성공 기준: 5/5 저장, 파일명 파싱 가능, meta.json 존재, 육안 통과 ≥4/5.

### P0 결과 (완료)

| # | 파일 | 결과 |
|---|------|------|
| 1 | `lex_aimodel-f-kr-20s-studio-full-linen-blazer-FKR20A-10001` | OK · KR 여성 스튜디오 |
| 2 | `lex_aimodel-m-kr-30s-office-half-charcoal-suit-MKR30A-10002` | OK · KR 남성 오피스 |
| 3 | `lex_aimodel-f-sea-20s-resort-full-linen-dress-FSEA20A-10003` | OK · 동남아 리조트 |
| 4 | `lex_aimodel-m-eu-30s-street-full-denim-jacket-MEU30A-10004` | OK · 유럽 스트릿 |
| 5 | `lex_aimodel-f-af-20s-beauty-half-black-turtleneck-FAF20A-10005` | OK · 아프리카계 뷰티 |

경로: `C:\cursor\ipplant\library\aimodel\{female,male}_lookbook\`  
재실행: `PYTHONPATH=C:\cursor\image python scripts/run_fashion_sample5.py`
