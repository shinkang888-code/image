"""이미지 최적화 — raw 생성물 → FHD(1920×1080) cover-crop → WebP + JPG.

순수 함수 위주. GPU 를 쓰지 않으므로 CPU 워커풀에서 병렬 실행된다 (factory.py).
요구사항: '가장 작은 웹포맷(WebP) + jpg' 를 FHD 로 출력.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

FHD = (1920, 1080)


@dataclass(frozen=True)
class OutputSpec:
    target: tuple[int, int] = FHD
    webp_quality: int = 80      # WebP 는 같은 화질에서 JPG보다 25~35% 작음
    webp_method: int = 6        # 0(빠름)~6(최소용량). 공장은 용량 우선
    jpg_quality: int = 82
    jpg_progressive: bool = True


@dataclass(frozen=True)
class EncodedImage:
    fmt: str          # "webp" | "jpg"
    data: bytes
    size: tuple[int, int]
    bytes_len: int


def cover_resize(img: Image.Image, target: tuple[int, int] = FHD) -> Image.Image:
    """target 비율에 맞춰 중앙 cover-crop 후 정확히 target 크기로 리사이즈 (왜곡 0)."""
    tw, th = target
    sw, sh = img.size
    scale = max(tw / sw, th / sh)          # 짧은 축을 채우도록
    nw, nh = round(sw * scale), round(sh * scale)
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def _encode(img: Image.Image, fmt: str, spec: OutputSpec) -> EncodedImage:
    buf = io.BytesIO()
    if fmt == "webp":
        img.save(buf, format="WEBP", quality=spec.webp_quality, method=spec.webp_method)
    elif fmt == "jpg":
        img.convert("RGB").save(
            buf, format="JPEG", quality=spec.jpg_quality,
            progressive=spec.jpg_progressive, optimize=True,
        )
    else:
        raise ValueError(f"unsupported format: {fmt}")
    data = buf.getvalue()
    return EncodedImage(fmt=fmt, data=data, size=img.size, bytes_len=len(data))


def optimize(
    raw: bytes | Image.Image,
    spec: OutputSpec | None = None,
    formats: tuple[str, ...] = ("webp", "jpg"),
) -> list[EncodedImage]:
    """raw 이미지(bytes 또는 PIL) → FHD cover-crop → 지정 포맷들로 인코딩."""
    spec = spec or OutputSpec()
    img = raw if isinstance(raw, Image.Image) else Image.open(io.BytesIO(raw))
    img = img.convert("RGB")
    fhd = cover_resize(img, spec.target)
    return [_encode(fhd, fmt, spec) for fmt in formats]
