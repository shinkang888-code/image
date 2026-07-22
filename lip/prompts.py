"""프롬프트 카탈로그 로딩 + 조합 전개 (순수함수).

catalog.json 이 정의한 축(axes)의 곱집합을 concrete 프롬프트로 전개한다.
각 프롬프트는 내용 해시로 안정적 id 를 가진다 → 재개·중복제거의 기준.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "prompts" / "catalog.json"


@dataclass(frozen=True)
class Prompt:
    id: str          # 내용 기반 안정적 id (해시)
    tag: str         # set 이름 (interior / web ...)
    positive: str
    negative: str

    def as_dict(self) -> dict:
        return {"id": self.id, "tag": self.tag, "positive": self.positive, "negative": self.negative}


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def load_catalog(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CATALOG
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _expand_set(name: str, spec: dict, quality: str, negative: str) -> Iterable[Prompt]:
    template: str = spec["template"]
    axes: dict[str, list[str]] = spec["axes"]
    # set 단위 오버라이드 — 도메인마다 화질어·네거티브가 다르다
    # (인테리어의 'natural materials' 가 상품컷에는 해로운 식).
    quality = spec.get("quality_suffix", quality)
    negative = spec.get("negative", negative)
    keys = list(axes.keys())
    for combo in itertools.product(*(axes[k] for k in keys)):
        filled = template.format(**dict(zip(keys, combo)))
        positive = f"{filled}, {quality}".strip().strip(",")
        yield Prompt(id=_hash(positive), tag=name, positive=positive, negative=negative)


def expand(catalog: dict, tags: Iterable[str] | None = None) -> list[Prompt]:
    """카탈로그를 concrete 프롬프트 리스트로 전개. tags 로 특정 set 만 선택 가능."""
    quality = catalog.get("quality_suffix", "")
    negative = catalog.get("negative", "")
    wanted = set(tags) if tags else None
    out: list[Prompt] = []
    for name, spec in catalog.get("sets", {}).items():
        if wanted and name not in wanted:
            continue
        out.extend(_expand_set(name, spec, quality, negative))
    return out


def load_prompts(path: str | Path | None = None, tags: Iterable[str] | None = None) -> list[Prompt]:
    return expand(load_catalog(path), tags)
