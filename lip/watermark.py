"""LEXI 워터마크 — 우하단, 보일듯 말듯.

레퍼런스: Gemini 생성 이미지의 가시 워터마크는 우하단 사각 영역에 들어가고
표준 해상도 48px · 고해상 96px 규격이며, 어두운 배경에서는 밝게 / 밝은 배경에서는
어둡게 뒤집힌다. 같은 규격을 따르되 심볼 대신 'LEXI' 워드마크를 쓴다.

배경 밝기를 실제로 재서 색을 뒤집는 게 핵심이다. 고정 흰색으로 박으면
밝은 스튜디오 컷(우리 상품컷 대부분)에서 아예 안 보이거나, 반대로
어두운 컷에서 너무 튄다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

TEXT = "LEXI"
#: 마크 높이 = 이미지 높이 × 이 비율 (1080 → 48px, Gemini 표준과 동일)
HEIGHT_RATIO = 0.0445
MIN_PX, MAX_PX = 28, 96
#: 보일듯 말듯. 0.22 는 밝은 스튜디오 배경에서 또렷하게 읽혀 과했다(실측).
#: 0.14~0.18 이 "있는 줄 알면 보이는" 구간.
OPACITY = 0.16
#: 가장자리 여백 = 마크 높이 × 이 배수
MARGIN_RATIO = 1.0

_FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _corner_is_light(img: Image.Image, box: tuple[int, int, int, int]) -> bool:
    """워터마크가 놓일 자리의 평균 밝기 — 색 반전 판단용."""
    region = img.crop(box).convert("L").resize((8, 8), Image.BILINEAR)
    px = list(region.getdata())
    return (sum(px) / len(px)) > 128


def apply(img: Image.Image, *, text: str = TEXT, opacity: float = OPACITY) -> Image.Image:
    """우하단에 워터마크를 얹은 새 이미지를 돌려준다(원본 불변)."""
    base = img.convert("RGBA")
    w, h = base.size
    mark_h = max(MIN_PX, min(MAX_PX, round(h * HEIGHT_RATIO)))
    font = _font(mark_h)

    scratch = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top

    margin = round(mark_h * MARGIN_RATIO)
    x = w - tw - margin
    y = h - th - margin

    light_bg = _corner_is_light(base, (max(0, x - 8), max(0, y - 8),
                                       min(w, x + tw + 8), min(h, y + th + 8)))
    rgb = (26, 26, 26) if light_bg else (255, 255, 255)
    alpha = int(round(max(0.0, min(1.0, opacity)) * 255))

    draw.text((x - left, y - top), text, font=font, fill=(*rgb, alpha))
    return Image.alpha_composite(base, scratch).convert("RGB")
