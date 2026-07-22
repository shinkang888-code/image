"""websource 가중 배치 — 천재병렬(GPU 직렬 ∥ CPU 병렬)로 라이브러리를 채운다.

GPU 는 단일 카드에서 diffusion 을 병렬화할 수 없다(이 리포의 출발 전제).
따라서 GPU 는 쉼 없이 직렬로 굽고, **워터마크·리사이즈·AVIF/WebP 인코딩·XMP·
파일쓰기는 CPU 워커풀에서 메모리 한도까지 병렬로** 소화한다.
"""
from __future__ import annotations

import io
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from . import library
from .prompts import Prompt, expand, load_catalog
from .taxonomy import _largest_remainder

CATALOG = Path(__file__).resolve().parent.parent / "prompts" / "websource-business.json"


@dataclass
class BatchResult:
    saved: int
    failed: int
    by_sub: dict[str, int]


def subcategory_weights(catalog: dict) -> dict[str, float]:
    """카탈로그 각 세트의 `_w` 를 가중치로 읽는다(없으면 균등)."""
    sets = catalog.get("sets", {})
    return {name: float(spec.get("_w", 1)) for name, spec in sets.items()}


def plan(total: int, catalog: dict) -> dict[str, int]:
    """총량 → 소분류별 장수. 최대잔여법이라 합계가 정확히 total 이다."""
    return _largest_remainder(total, subcategory_weights(catalog))


def pick_prompts(catalog: dict, sub: str, count: int) -> list[Prompt]:
    """조합 공간에서 균등 간격으로 뽑는다 — 앞쪽 조합만 쏠리지 않게."""
    pool = expand(catalog, tags=[sub])
    if not pool or count <= 0:
        return []
    if count <= len(pool):
        step = len(pool) / count
        return [pool[int(i * step)] for i in range(count)]
    # 풀보다 많으면 순환 복제
    reps, rem = divmod(count, len(pool))
    return pool * reps + pool[:rem]


def run_batch(
    total: int,
    *,
    client,
    build_workflow: Callable,
    profile,
    out_root: str | Path,
    workers: int = 8,
    base_seed: int = 0,
    engine_label: str = "krea2t-q3km",
    catalog_path: str | Path | None = None,
    resume: bool = True,
    log: Callable[[str], None] = print,
) -> BatchResult:
    catalog = load_catalog(catalog_path or CATALOG)
    quotas = plan(total, catalog)
    log(f"배분: {', '.join(f'{k}={v}' for k, v in quotas.items() if v)}  (합계 {sum(quotas.values())})")

    jobs: list[tuple[str, Prompt, int]] = []
    for sub, n in quotas.items():
        for i, p in enumerate(pick_prompts(catalog, sub, n)):
            jobs.append((sub, p, base_seed + i))

    # 재개 — 이미 구운 (소분류, 프롬프트, 시드)는 건너뛴다.
    # 장시간 배치가 중간에 죽어도 처음부터 다시 굽지 않는다. 산출물은 장당
    # 즉시 디스크에 쓰이므로(library.save_asset) 매니페스트가 곧 진행 상황이다.
    if resume:
        done = library.done_keys(out_root)
        if done:
            before = len(jobs)
            jobs = [j for j in jobs if (j[0], j[1].id, j[2]) not in done]
            if before != len(jobs):
                log(f"재개: 이미 완료된 {before - len(jobs)}장 건너뜀 → 남은 {len(jobs)}장")

    q: "queue.Queue[tuple[str, Prompt, int, bytes] | None]" = queue.Queue(maxsize=workers * 2)
    lock = threading.Lock()
    saved = 0
    failed = 0
    by_sub: dict[str, int] = {}

    def worker() -> None:
        nonlocal saved, failed
        while True:
            item = q.get()
            try:
                if item is None:
                    return
                sub, p, seed, raw = item
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                rec = library.save_asset(
                    img, root=out_root, category="websource", subcategory=sub,
                    prompt=p.positive, negative=p.negative, prompt_id=p.id,
                    seed=seed, engine=engine_label,
                    headline_en=_headline(sub),
                )
                library.append_manifest(out_root, rec)
                with lock:
                    saved += 1
                    by_sub[sub] = by_sub.get(sub, 0) + 1
                    sizes = " ".join(f"{k} {v // 1024}KB" for k, v in rec.bytes.items())
                    log(f"  [{saved}/{len(jobs)}] {sub}/{Path(rec.files['avif']).name}  ({sizes})")
            except Exception as ex:                     # noqa: BLE001 — 한 장 실패로 배치를 멈추지 않는다
                with lock:
                    failed += 1
                log(f"  ! 저장 실패: {ex}")
            finally:
                q.task_done()

    pool = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in pool:
        t.start()

    try:
        for sub, p, seed in jobs:
            wf = build_workflow(p.positive, p.negative, seed, profile)
            try:
                raw = client.generate(wf)               # GPU 직렬 구간
            except Exception as ex:                     # noqa: BLE001
                with lock:
                    failed += 1
                log(f"  ! 생성 실패 {sub}/{p.id}: {ex}")
                continue
            q.put((sub, p, seed, raw))
    finally:
        for _ in pool:
            q.put(None)
        for t in pool:
            t.join()

    return BatchResult(saved=saved, failed=failed, by_sub=by_sub)


#: 소분류별 기본 영문 헤드라인 — 텍스트 레이어용(이미지에는 굽지 않는다).
_HEADLINES = {
    "storefront": "Visit Our Store",
    "interior": "A Space Made For You",
    "service_scene": "Crafted With Care",
    "team": "The People Behind The Work",
    "office": "Where Ideas Take Shape",
    "industry": "Built On Expertise",
    "product_shot": "Made Fresh Daily",
    "promo_banner": "Limited Time Offer",
    "blog_thumb": "Insights & Updates",
    "hero_abstract": "Grow With Confidence",
    "texture_bg": "",
    "icon_scene": "",
}


def _headline(sub: str) -> str:
    return _HEADLINES.get(sub, "")
