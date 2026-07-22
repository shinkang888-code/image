"""Lexi IPlant taxonomy — websource / commerce / aimodel + weight allocation."""
from __future__ import annotations

from dataclasses import dataclass


# Default top-level weights (commerce-leaning factory)
DEFAULT_WEIGHTS: dict[str, float] = {
    "websource": 30.0,
    "commerce": 40.0,
    "aimodel": 30.0,
}

# Subcategory weights (normalized within parent)
SUB_WEIGHTS: dict[str, dict[str, float]] = {
    "websource": {
        "hero": 25, "banner": 20, "logo": 10,
        "ui_screen": 25, "bg": 15, "icon_scene": 5,
    },
    "commerce": {
        "pack_hero": 25, "label": 20, "pdp": 25,
        "detail": 15, "lifestyle": 15,
    },
    "aimodel": {
        "female_lookbook": 30, "male_lookbook": 25,
        "product_wear": 25, "beauty": 10, "diversity": 10,
    },
}

# Map subcategory → catalog set name (prompts/catalog.json)
SUB_TO_CATALOG: dict[str, str] = {
    "hero": "web", "banner": "web", "logo": "web",
    "ui_screen": "web", "bg": "web", "icon_scene": "web",
    "pack_hero": "product", "label": "product", "pdp": "product",
    "detail": "detail", "lifestyle": "lifestyle",
    "female_lookbook": "model", "male_lookbook": "model",
    "product_wear": "model", "beauty": "model", "diversity": "model",
}


@dataclass(frozen=True)
class Quota:
    category: str
    subcategory: str
    count: int

    @property
    def key(self) -> str:
        return f"{self.category}.{self.subcategory}"


def _largest_remainder(total: int, weights: dict[str, float]) -> dict[str, int]:
    if total <= 0 or not weights:
        return {k: 0 for k in weights}
    s = sum(weights.values()) or 1.0
    raw = {k: total * (v / s) for k, v in weights.items()}
    floors = {k: int(v) for k, v in raw.items()}
    rem = total - sum(floors.values())
    order = sorted(raw.keys(), key=lambda k: (raw[k] - floors[k]), reverse=True)
    for k in order[:rem]:
        floors[k] += 1
    return floors


def alloc(total: int, weights: dict[str, float] | None = None,
          sub_weights: dict[str, dict[str, float]] | None = None) -> list[Quota]:
    """Allocate exact `total` across category.subcategory using largest remainder."""
    w = dict(weights or DEFAULT_WEIGHTS)
    sw = sub_weights or SUB_WEIGHTS
    top = _largest_remainder(total, w)
    out: list[Quota] = []
    for cat, n in top.items():
        subs = sw.get(cat, {"default": 100.0})
        parts = _largest_remainder(n, {k: float(v) for k, v in subs.items()})
        for sub, c in parts.items():
            if c > 0:
                out.append(Quota(category=cat, subcategory=sub, count=c))
    return out


def ai_recommend_weights(goal: str = "commerce") -> dict[str, float]:
    """Simple preset recommender for dashboard mode A."""
    g = (goal or "commerce").lower()
    if g in ("site", "web", "websource"):
        return {"websource": 50.0, "commerce": 30.0, "aimodel": 20.0}
    if g in ("model", "lookbook", "aimodel"):
        return {"websource": 20.0, "commerce": 30.0, "aimodel": 50.0}
    if g in ("balanced", "equal"):
        return {"websource": 34.0, "commerce": 33.0, "aimodel": 33.0}
    return dict(DEFAULT_WEIGHTS)


def catalog_tag_for(subcategory: str) -> str:
    return SUB_TO_CATALOG.get(subcategory, "web")
