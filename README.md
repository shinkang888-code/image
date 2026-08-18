# Lexi IPlant (lexiipplant)

로컬 **ComfyUI** 이미지 공장 + **Neon 인덱스** + **Vercel 웹 콘솔**.  
생산 파이프라인: `lexi_ai/ipplant` · DB 편집 저작권: `steven8kay`

## 천재병렬
GPU(Comfy) 직렬 생성 ∥ CPU WebP/JPG 인코딩 병렬.

## 카테고리 가중 생성
- **websource** — 사이트 배너·로고·UI 실사
- **commerce** — CJ 드롭시핑 기반 패키지/라벨/PDP
- **aimodel** — AI 화보·상품 모델

```powershell
python -m lip plant --total 100 --dry-run
python -m lip plant --total 1000 --weights websource:30,commerce:40,aimodel:30
```

출력: `C:\cursor\ipplant\library\<category>\<sub>\<id>\image.webp|jpg` + `meta.iplant.json`

IPLANT 메타 라인 예:
`IPLANT;v1;cat=commerce.pdp;pid=…;by=lexi_ai/ipplant;c=steven8kay;lic=db-edit;use=pdp`

## 웹 갤러리 / 대시보드
공개 URL: https://ipcow.vercel.app (썸네일 갤러리) · https://ipcow.vercel.app/dashboard (공장 콘솔)

```powershell
python scripts/build_gallery.py   # C:\cursor\ipplant\library → web/library
npm install
vercel --prod --yes
```

Sources(가중치) | Console(작업) | Studio(미리보기·공유링크)

## Agent (클라우드 job → 로컬 공장)
```powershell
$env:IPLANT_API="https://<your-vercel>.vercel.app"
$env:IPLANT_AGENT_TOKEN="..."
python -m lip agent --dry-run
```

## Drive
WebP 마스터는 `My Drive/lpplant/` 로 동기화(에이전트/수동). Neon `share_url`에 링크 저장.

## 기존 LIP CLI
`doctor` / `run` / `serve` / `nodes` / `dashboard` 유지.
