"""IPLANT sidecar + Schema.org ImageObject metadata (steven8kay / lexi_ai)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COPYRIGHT_HOLDER = "steven8kay"
PRODUCER = "lexi_ai/ipplant"


def iplant_line(*, category: str, subcategory: str, prompt_id: str, seed: int,
                use: str = "asset") -> str:
    """Minimal-token robot/search line."""
    return (
        f"IPLANT;v1;cat={category}.{subcategory};pid={prompt_id};"
        f"seed={seed};by={PRODUCER};c={COPYRIGHT_HOLDER};lic=db-edit;use={use}"
    )


def build_meta(
    *,
    category: str,
    subcategory: str,
    prompt_id: str,
    positive: str,
    negative: str,
    seed: int,
    local_path: str,
    engine: str = "gguf",
    source_sku: str | None = None,
    drive_file_id: str | None = None,
    share_url: str | None = None,
    width: int = 1920,
    height: int = 1080,
    use: str | None = None,
) -> dict[str, Any]:
    use = use or subcategory
    line = iplant_line(category=category, subcategory=subcategory,
                       prompt_id=prompt_id, seed=seed, use=use)
    return {
        "@context": "https://schema.org",
        "@type": "ImageObject",
        "identifier": line,
        "creator": {
            "@type": "Organization",
            "name": "lexi_ai",
            "software": "ipplant",
        },
        "copyrightHolder": {"@type": "Person", "name": COPYRIGHT_HOLDER},
        "creditText": (
            f"Produced by {PRODUCER}. "
            f"Database edit copyright {COPYRIGHT_HOLDER}."
        ),
        "encodingFormat": "image/webp",
        "width": width,
        "height": height,
        "keywords": [category, subcategory, "lexiipplant", "ipplant"],
        "dateCreated": datetime.now(timezone.utc).isoformat(),
        "isBasedOn": {
            "@type": "CreativeWork",
            "text": positive,
            "negativePrompt": negative,
            "promptId": prompt_id,
        },
        "iplant": {
            "category": category,
            "subcategory": subcategory,
            "source_sku": source_sku,
            "seed": seed,
            "engine": engine,
            "local_path": local_path,
            "drive_file_id": drive_file_id,
            "share_url": share_url,
            "line": line,
        },
    }


def write_sidecar(dest_dir: Path, meta: dict[str, Any]) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "meta.iplant.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
