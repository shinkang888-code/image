"""라이브러리 기록기 — 워터마크 → 라벨링 → 저장 → 매니페스트.

산출물 한 장이 거치는 전 과정을 한 곳에 모은다. 공장(factory)이든 서비스든
여기를 통해서만 파일을 쓰게 해서 "해시 파일명·메타 없는 산출물"이 새는 경로를
없앤다(명세 a364a6e).

    library/<category>/<sub>/lex_<slug>-NN-<variant>.<ext>
    library/<category>/<sub>/lex_<slug>-NN.meta.json      (사이드카)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from . import naming, seo, watermark
from .optimize import OutputSpec, avif_available, optimize

#: 20인치 화면 기준. 1600x900 이 실사용 상한이고 그 이상은 대역폭 낭비다.
WEB_TARGET = (1600, 900)
#: AVIF 우선(가능 시). 이 PC Pillow 미지원이면 webp+jpg 로 천재병렬 유지.
WEB_FORMATS = ("avif", "webp") if avif_available() else ("webp", "jpg")


@dataclass
class AssetRecord:
    category: str
    subcategory: str
    slug: str
    prompt_id: str
    seed: int
    prompt: str
    negative: str
    engine: str
    recipe: str
    headline_en: str          # 텍스트 레이어에 얹을 영문 카피(이미지에는 굽지 않음)
    files: dict[str, str]     # {"avif": path, "webp": path}
    bytes: dict[str, int]
    width: int
    height: int
    created_at: str


def save_asset(
    img: Image.Image,
    *,
    root: str | Path,
    category: str,
    subcategory: str,
    prompt: str,
    negative: str,
    prompt_id: str,
    seed: int,
    engine: str,
    recipe: str = "r1",
    headline_en: str = "",
    caption: str = "",
    license_url: str = "https://lexi.ai/license",
    variant: str = "web",
    index: int | None = None,
    target: tuple[int, int] = WEB_TARGET,
    formats: tuple[str, ...] = WEB_FORMATS,
    apply_watermark: bool = True,
) -> AssetRecord:
    """한 장을 라이브러리에 기록한다. 워터마크·XMP·명명이 전부 여기서 걸린다."""
    from datetime import datetime, timezone

    slug = naming.slugify(prompt)
    meta = seo.ImageMeta(
        category=category, subcategory=subcategory, prompt=prompt,
        recipe=recipe, engine=engine, seed=seed,
        caption=caption or headline_en, license_url=license_url,
    )
    xmp = seo.build_xmp(meta)

    stamped = watermark.apply(img) if apply_watermark else img
    encoded = optimize(stamped, OutputSpec(target=target), formats=formats, xmp=xmp)

    out_dir = naming.asset_dir(root, category, subcategory)
    out_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for e in encoded:
        path = naming.unique_path(
            out_dir / naming.filename(slug, variant, e.fmt, index=index)
        )
        path.write_bytes(e.data)
        files[e.fmt] = str(path)
        sizes[e.fmt] = e.bytes_len

    rec = AssetRecord(
        category=category, subcategory=subcategory, slug=slug,
        prompt_id=prompt_id, seed=seed, prompt=prompt, negative=negative,
        engine=engine, recipe=recipe, headline_en=headline_en,
        files=files, bytes=sizes, width=target[0], height=target[1],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    # 사이드카 — 프롬프트 원문·네거티브까지 남긴다. 파일 내부 XMP 는 상한이 있어
    # 잘릴 수 있으므로, 원문 보존은 이쪽이 진실이다.
    side = out_dir / f"{naming.PREFIX}{slug}{f'-{index:02d}' if index is not None else ''}.meta.json"
    naming.unique_path(side).write_text(
        json.dumps(asdict(rec), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return rec


def append_manifest(root: str | Path, rec: AssetRecord) -> None:
    path = Path(root) / "library" / "manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")


def done_keys(root: str | Path) -> set[tuple[str, str, int]]:
    """이미 구운 (소분류, prompt_id, seed) 집합 — 배치 재개용.

    산출물은 장당 즉시 디스크에 쓰이고 매니페스트도 장당 append 되므로,
    프로세스가 죽어도 여기까지가 보존된 진행 상황이다.
    """
    path = Path(root) / "library" / "manifest.jsonl"
    out: set[tuple[str, str, int]] = set()
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                out.add((r["subcategory"], r["prompt_id"], int(r["seed"])))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return out


def report(root: str | Path) -> dict[str, dict[str, int]]:
    """카테고리/소분류별 개수 집계 (탐색기·리포트용)."""
    path = Path(root) / "library" / "manifest.jsonl"
    out: dict[str, dict[str, int]] = {}
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.setdefault(r["category"], {})
            out[r["category"]][r["subcategory"]] = (
                out[r["category"]].get(r["subcategory"], 0) + 1
            )
    return out
