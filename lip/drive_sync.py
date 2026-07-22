"""Best-effort Google Drive sync stub for lpplant/.

Set GOOGLE_APPLICATION_CREDENTIALS + IPLANT_DRIVE_FOLDER_ID to enable.
Without credentials, copies WebP into C:\\cursor\\ipplant\\lpplant-sync\\ for manual Drive upload.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

IPLANT = Path(os.environ.get("IPLANT_ROOT", r"C:\cursor\ipplant"))


def sync_webp_to_staging(library_root: Path | None = None) -> int:
    root = library_root or (IPLANT / "library")
    staging = IPLANT / "lpplant-sync"
    staging.mkdir(parents=True, exist_ok=True)
    n = 0
    for webp in root.rglob("image.webp"):
        # library/cat/sub/id/image.webp → staging/cat/sub/id.webp
        rel = webp.relative_to(root)
        cat, sub, aid = rel.parts[0], rel.parts[1], rel.parts[2]
        dest = staging / cat / sub / f"{aid}.webp"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(webp, dest)
        n += 1
    # Also copy inventory
    inv = IPLANT / "reports" / "inventory.json"
    if inv.exists():
        shutil.copy2(inv, staging / "inventory.json")
    print(f"staged {n} webp → {staging} (upload this folder to Google Drive/lpplant)")
    return n


if __name__ == "__main__":
    sync_webp_to_staging()
