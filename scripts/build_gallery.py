"""Copy ipplant library WebP into web/library and write gallery-index.json."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

SRC = Path(r"C:\cursor\ipplant\library")
DST = Path(__file__).resolve().parents[1] / "web" / "library"
INDEX = Path(__file__).resolve().parents[1] / "web" / "gallery-index.json"


def dest_name(webp: Path) -> Path:
    rel = webp.relative_to(SRC)
    if webp.name.lower() == "image.webp" and len(rel.parts) >= 2:
        return Path(*rel.parts[:-1]).with_suffix(".webp")
    return rel


def title_of(rel: Path) -> str:
    stem = rel.stem
    if stem.startswith("lex_"):
        return stem[4:].replace("-", " ")
    return stem


def main() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    items = []
    for webp in sorted(SRC.rglob("*.webp")):
        rel = dest_name(webp)
        out = DST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(webp, out)
        parts = rel.parts
        category = parts[0] if parts else "other"
        subcategory = parts[1] if len(parts) > 1 else "misc"
        items.append(
            {
                "id": rel.as_posix().rsplit(".", 1)[0],
                "src": "/library/" + rel.as_posix(),
                "category": category,
                "subcategory": subcategory,
                "title": title_of(rel),
                "bytes": webp.stat().st_size,
            }
        )
    cats: dict[str, dict[str, int]] = {}
    for it in items:
        cats.setdefault(it["category"], {})
        cats[it["category"]][it["subcategory"]] = cats[it["category"]].get(it["subcategory"], 0) + 1
    payload = {
        "product": "lexiipplant",
        "count": len(items),
        "bytes": sum(i["bytes"] for i in items),
        "categories": cats,
        "items": items,
    }
    INDEX.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    mb = payload["bytes"] / (1024 * 1024)
    print(f"gallery: {payload['count']} webp, {mb:.1f} MB -> {DST}")


if __name__ == "__main__":
    main()
