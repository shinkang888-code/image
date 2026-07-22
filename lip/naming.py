"""파일명·경로 규약 (명세 §7, a364a6e).

산출물을 해시 파일명으로 두지 않는다. 파일명 자체가 검색 신호이고,
카테고리 탐색기·재태깅·저작권 추적이 전부 이름 규약 위에서 돈다.

    library/<category>/<sub>/lex_<slug>-<variant>.<ext>
    예) library/websource/storefront/lex_cafe-storefront-evening-01-hero.webp
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

PREFIX = "lex_"
MAX_SLUG = 48

#: 슬러그에서 걷어낼 촬영 상용어 — 이름 길이만 먹고 변별력이 없다.
_STOP = {
    "a", "an", "the", "of", "on", "in", "at", "with", "and", "or", "for",
    "photo", "photography", "shot", "image", "view", "background",
    "professional", "commercial", "quality", "high", "detail", "sharp",
    "focus", "clean", "soft", "studio", "seamless",
}


def slugify(text: str, *, max_len: int = MAX_SLUG) -> str:
    """자유 텍스트 → 영문 소문자 하이픈 슬러그."""
    s = unicodedata.normalize("NFKD", text)
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _STOP]
    # 단어 경계에서 자른다 — 문자 단위로 자르면 'brick-fac' 같은 조각이 남아
    # 파일명이 검색 신호로도, 사람이 읽기에도 못 쓰게 된다.
    out: list[str] = []
    length = 0
    for word in words:
        add = len(word) + (1 if out else 0)
        if length + add > max_len:
            break
        out.append(word)
        length += add
    slug = "-".join(out).strip("-")
    return slug or "asset"


def filename(slug: str, variant: str, ext: str, *, index: int | None = None) -> str:
    """lex_<slug>[-NN]-<variant>.<ext>"""
    n = f"-{index:02d}" if index is not None else ""
    return f"{PREFIX}{slug}{n}-{variant}.{ext.lstrip('.')}"


def asset_dir(root: str | Path, category: str, subcategory: str) -> Path:
    return Path(root) / "library" / category / subcategory


def asset_path(
    root: str | Path,
    *,
    category: str,
    subcategory: str,
    slug: str,
    variant: str,
    ext: str,
    index: int | None = None,
) -> Path:
    return asset_dir(root, category, subcategory) / filename(slug, variant, ext, index=index)


def unique_path(path: Path) -> Path:
    """같은 이름이 있으면 -2, -3 … 을 붙인다(덮어쓰기 금지)."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for n in range(2, 1000):
        cand = path.with_name(f"{stem}-{n}{suffix}")
        if not cand.exists():
            return cand
    raise RuntimeError(f"이름 충돌을 해소하지 못했습니다: {path}")
