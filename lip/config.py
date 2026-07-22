"""설정 — TOML + 환경변수 fallback (CLAUDE.md 규칙3: 미설정 시 graceful).

우선순위: 명시 인자 > 환경변수(LIP_*) > config.toml > 내장 기본값.
config 파일이 없어도 내장 기본값으로 정상 동작한다.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .optimize import OutputSpec
from .workflow import GpuProfile, gguf_profile


@dataclass
class Config:
    comfy_host: str = "127.0.0.1:8188"
    out_dir: Path = field(default_factory=lambda: Path("out"))
    catalog: Path | None = None
    workers: int = 4            # CPU 인코딩 병렬도 (GPU 는 항상 직렬 1)
    formats: tuple[str, ...] = ("webp", "jpg")
    base_seed: int = 0
    quality: bool = False       # True = ESRGAN 고화질 업스케일 (GPU)
    takes: int = 1              # 프롬프트당 시드 변주 장수 (voicebox takes)
    retries: int = 1            # 생성 실패 재시도 횟수
    dashboard_port: int = 8787
    profile: GpuProfile = field(default_factory=GpuProfile)
    output: OutputSpec = field(default_factory=OutputSpec)

    @property
    def nodes_file(self) -> Path:
        return Path(self.out_dir) / "nodes.json"


def _env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(f"LIP_{key}", default)


def load_config(path: str | Path | None = None) -> Config:
    data: dict = {}
    p = Path(path) if path else Path("lip.toml")
    if p.exists():
        with open(p, "rb") as f:
            data = tomllib.load(f)

    cfg = Config()
    comfy = data.get("comfy", {})
    factory = data.get("factory", {})
    gpu = data.get("gpu", {})
    out = data.get("output", {})

    cfg.comfy_host = _env("COMFY_HOST") or comfy.get("host", cfg.comfy_host)
    cfg.out_dir = Path(_env("OUT_DIR") or factory.get("out_dir", cfg.out_dir))
    if factory.get("catalog"):
        cfg.catalog = Path(factory["catalog"])
    cfg.workers = int(_env("WORKERS") or factory.get("workers", cfg.workers))
    if factory.get("formats"):
        cfg.formats = tuple(factory["formats"])
    cfg.base_seed = int(_env("BASE_SEED") or factory.get("base_seed", cfg.base_seed))
    cfg.quality = str(_env("QUALITY") or gpu.get("quality", cfg.quality)).lower() in ("1", "true", "yes")
    cfg.takes = int(_env("TAKES") or factory.get("takes", cfg.takes))
    cfg.retries = int(_env("RETRIES") or factory.get("retries", cfg.retries))
    cfg.dashboard_port = int(_env("DASHBOARD_PORT") or factory.get("dashboard_port", cfg.dashboard_port))

    engine = (_env("ENGINE") or gpu.get("engine") or "sdxl").lower()
    if engine == "gguf":
        g = gguf_profile()
        cfg.profile = gguf_profile(
            unet=gpu.get("unet", g.unet),
            clip=gpu.get("clip", g.clip),
            clip_type=gpu.get("clip_type", g.clip_type),
            vae=gpu.get("vae", g.vae),
            width=int(gpu.get("width", g.width)),
            height=int(gpu.get("height", g.height)),
            steps=int(gpu.get("steps", g.steps)),
            cfg=float(gpu.get("cfg", g.cfg)),
            sampler=gpu.get("sampler", g.sampler),
            scheduler=gpu.get("scheduler", g.scheduler),
            checkpoint=gpu.get("checkpoint", g.checkpoint),
            upscale_model=gpu.get("upscale_model", g.upscale_model),
        )
    else:
        cfg.profile = GpuProfile(
            engine="sdxl",
            checkpoint=gpu.get("checkpoint", cfg.profile.checkpoint),
            unet=gpu.get("unet", cfg.profile.unet),
            clip=gpu.get("clip", cfg.profile.clip),
            clip_type=gpu.get("clip_type", cfg.profile.clip_type),
            vae=gpu.get("vae", cfg.profile.vae),
            width=int(gpu.get("width", cfg.profile.width)),
            height=int(gpu.get("height", cfg.profile.height)),
            steps=int(gpu.get("steps", cfg.profile.steps)),
            cfg=float(gpu.get("cfg", cfg.profile.cfg)),
            sampler=gpu.get("sampler", cfg.profile.sampler),
            scheduler=gpu.get("scheduler", cfg.profile.scheduler),
            upscale_model=gpu.get("upscale_model", cfg.profile.upscale_model),
        )

    cfg.output = OutputSpec(
        target=tuple(out.get("target", cfg.output.target)),
        webp_quality=int(out.get("webp_quality", cfg.output.webp_quality)),
        webp_method=int(out.get("webp_method", cfg.output.webp_method)),
        jpg_quality=int(out.get("jpg_quality", cfg.output.jpg_quality)),
    )
    return cfg
