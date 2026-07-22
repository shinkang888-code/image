"""P0: fashion lookbook sample — 5 shots, searchable filenames."""
from __future__ import annotations

import dataclasses
import io
import json
import sys
from pathlib import Path

from PIL import Image

from lip.comfy_client import ComfyClient, MockComfyClient
from lip.config import load_config
from lip.library import append_manifest, AssetRecord
from lip.manifest import Manifest
from lip.optimize import OutputSpec, optimize
from lip import naming, seo, watermark
from lip.workflow import build_workflow

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "prompts" / "fashion-lookbook-profiles.json"


def pid_compact(pid: str) -> str:
    return pid.replace("-", "")


def build_prompt(data: dict, job: dict) -> tuple[str, str, dict]:
    p = {x["id"]: x for x in data["profiles"]}[job["profile"]]
    positive = (
        f"editorial fashion lookbook photo of an adult {p['gender_word']} ({p['age']}), "
        f"identity locked: {p['look']}, same person, "
        f"wearing {job['outfit']}, {data['crops'][job['crop']]}, "
        f"{data['concepts'][job['concept']]}, {data['quality_suffix']}"
    )
    meta = {
        "g": p["g"], "nat": p["nat"], "age": p["age"],
        "concept": job["concept"], "crop": job["crop"],
        "outfit_slug": job["outfit_slug"],
        "pid": pid_compact(p["id"]), "profile": p["id"],
        "seed": job["seed"],
    }
    return positive, data["negative"], meta


def search_slug(meta: dict) -> str:
    return (
        f"aimodel-{meta['g']}-{meta['nat']}-{meta['age']}-"
        f"{meta['concept']}-{meta['crop']}-{meta['outfit_slug']}-"
        f"{meta['pid']}-{meta['seed']}"
    )


def save_searchable(
    img: Image.Image, *, out_root: Path, positive: str, negative: str,
    meta: dict, engine: str,
) -> AssetRecord:
    from datetime import datetime, timezone

    slug = search_slug(meta)
    sub = "female_lookbook" if meta["g"] == "f" else "male_lookbook"
    xmp = seo.build_xmp(seo.ImageMeta(
        category="aimodel", subcategory=sub, prompt=positive,
        recipe="fashion-v1", engine=engine, seed=meta["seed"],
        caption=f"{meta['profile']} {meta['concept']} {meta['outfit_slug']}",
    ))
    stamped = watermark.apply(img)
    encoded = optimize(
        stamped, OutputSpec(target=(1600, 900)),
        formats=("webp", "jpg"), xmp=xmp,
    )
    out_dir = naming.asset_dir(out_root, "aimodel", sub)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for e in encoded:
        path = naming.unique_path(out_dir / f"{naming.PREFIX}{slug}.{e.fmt}")
        path.write_bytes(e.data)
        files[e.fmt] = str(path)
        sizes[e.fmt] = e.bytes_len

    rec = AssetRecord(
        category="aimodel", subcategory=sub, slug=slug,
        prompt_id=f"fashion-{meta['pid']}-{meta['seed']}",
        seed=meta["seed"], prompt=positive, negative=negative,
        engine=engine, recipe="fashion-v1",
        headline_en=slug, files=files, bytes=sizes,
        width=1600, height=900,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    side = out_dir / f"{naming.PREFIX}{slug}.meta.json"
    payload = dataclasses.asdict(rec)
    payload["fashion"] = meta
    payload["search_slug"] = slug
    side.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    append_manifest(out_root, rec)
    return rec


def main() -> int:
    dry = "--dry-run" in sys.argv
    cfg = load_config()
    data = json.loads(PROFILES.read_text(encoding="utf-8"))
    out_root = Path(cfg.out_dir)
    if dry:
        client = MockComfyClient((cfg.profile.width, cfg.profile.height))
    else:
        client = ComfyClient(base_url=f"http://{cfg.comfy_host}")
        if not client.ping():
            print("Comfy offline — abort (or pass --dry-run)")
            return 1

    ok = 0
    for i, job in enumerate(data["sample5"], 1):
        positive, negative, meta = build_prompt(data, job)
        slug = search_slug(meta)
        print(f"[{i}/5] {naming.PREFIX}{slug}.webp  seed={meta['seed']}")
        # skip if already done
        man = Manifest(out_root / "manifest.jsonl")
        if man.has(f"fashion-{meta['pid']}-{meta['seed']}", meta["seed"]):
            print("  skip (manifest)")
            ok += 1
            continue
        wf = build_workflow(positive, negative, meta["seed"], cfg.profile)
        raw = client.generate(wf)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        rec = save_searchable(
            img, out_root=out_root, positive=positive, negative=negative,
            meta=meta, engine=cfg.profile.engine,
        )
        print(f"  OK {rec.files.get('webp')}")
        ok += 1

    print(f"P0 done: {ok}/5 → {out_root / 'library' / 'aimodel'}")
    return 0 if ok == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
