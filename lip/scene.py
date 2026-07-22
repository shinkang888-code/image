"""Lexi Draft Scene JSON → 실사 프롬프트 (로컬 render.ts 대체 보조).

apps/web/src/lib/render.ts 는 3D 캔버스 스냅샷 + 프롬프트를 클라우드 img2img 로 보낸다.
LIP 은 이를 로컬 ComfyUI img2img 로 대체한다. 이 모듈은 Scene JSON 에서 프롬프트를
자동 합성한다 (packages/ai 의 인테리어 도메인 지식과 동일한 축을 순수 변환으로 파생).

Scene 은 CLAUDE.md 규칙1대로 단일 소스 — 여기서도 순수 함수로만 파생한다.
"""
from __future__ import annotations

import json
from pathlib import Path

# 카탈로그 id → 사람이 읽는 가구 라벨 (packages/core catalog 대응, 없으면 id 그대로)
ITEM_LABELS = {
    "sofa": "a sofa",
    "bed": "a bed",
    "table": "a dining table",
    "chair": "chairs",
    "desk": "a desk",
    "wardrobe": "a wardrobe",
    "bookshelf": "a bookshelf",
    "kitchen_island": "a kitchen island",
    "vanity": "a bathroom vanity",
    "coffee_table": "a coffee table",
}

QUALITY = ("photorealistic interior rendering, ultra realistic, natural materials, "
           "soft realistic lighting, high detail, architectural photography, 8k")
NEGATIVE = ("lowres, blurry, distorted perspective, warped walls, cartoon, cgi, "
            "watermark, text, deformed furniture")


def _humanize_item(catalog_id: str) -> str:
    return ITEM_LABELS.get(catalog_id, catalog_id.replace("_", " "))


def scene_to_prompt(scene: dict, style: str = "modern minimalist") -> str:
    """Scene dict → img2img positive 프롬프트."""
    rooms = scene.get("roomMeta") or []
    walls = scene.get("walls") or []
    items = scene.get("items") or []

    room_count = len(rooms) if rooms else max(1, len(walls) // 4)
    parts = [f"interior of a {room_count}-room apartment" if room_count > 1
             else "interior of a room"]
    parts.append(f"{style} style")

    labels = []
    seen = set()
    for it in items:
        cid = it.get("catalogId", "")
        if cid and cid not in seen:
            seen.add(cid)
            labels.append(_humanize_item(cid))
    if labels:
        parts.append("furnished with " + ", ".join(labels[:8]))

    parts.append(QUALITY)
    return ", ".join(parts)


def load_scene(path: str | Path) -> dict:
    """.lexi.json 또는 Scene JSON 파일 로드."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
