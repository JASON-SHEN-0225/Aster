"""生成 Aster 品牌图标（PNG 与 ICO）。"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
OUT.mkdir(parents=True, exist_ok=True)


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def gradient(size: int, left: tuple[int, int, int], right: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x / size * 0.65 + y / size * 0.35)
            px[x, y] = (
                lerp(left[0], right[0], t),
                lerp(left[1], right[1], t),
                lerp(left[2], right[2], t),
            )
    return img


def star_points(cx: float, cy: float, outer: float, inner: float, points: int = 4) -> list[tuple[float, float]]:
    result = []
    for i in range(points * 2):
        angle = -math.pi / 2 + i * math.pi / points
        radius = outer if i % 2 == 0 else inner
        result.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return result


def make_icon(size: int = 1024, maskable: bool = False) -> Image.Image:
    scale = 4
    s = size * scale
    bg = gradient(s, (18, 22, 48), (6, 10, 20)).convert("RGBA")
    # 极光光晕
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(
        (int(-s * 0.15), int(-s * 0.25), int(s * 0.95), int(s * 0.85)),
        fill=(108, 92, 231, 90),
    )
    gd.ellipse(
        (int(s * 0.25), int(s * 0.35), int(s * 1.15), int(s * 1.05)),
        fill=(0, 212, 255, 70),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(int(s * 0.08)))
    bg.alpha_composite(glow)

    # 圆角遮罩
    radius = int(s * 0.22)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=radius, fill=255)
    bg.putalpha(mask)

    draw = ImageDraw.Draw(bg, "RGBA")
    cx = cy = s / 2
    # 轨道
    orbit = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    od = ImageDraw.Draw(orbit)
    od.ellipse(
        (int(cx - s * 0.37), int(cy - s * 0.16), int(cx + s * 0.37), int(cy + s * 0.16)),
        outline=(255, 255, 255, 120),
        width=max(2, int(s * 0.008)),
    )
    orbit = orbit.rotate(-28, resample=Image.BICUBIC, center=(cx, cy))
    bg.alpha_composite(orbit)

    # 四角星
    outer = s * (0.30 if maskable else 0.34)
    inner = outer * 0.27
    pts = star_points(cx, cy, outer, inner)
    # 发光
    glow_star = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sd = ImageDraw.Draw(glow_star)
    sd.polygon(pts, fill=(255, 255, 255, 220))
    glow_star = glow_star.filter(ImageFilter.GaussianBlur(int(s * 0.035)))
    bg.alpha_composite(glow_star)
    draw = ImageDraw.Draw(bg, "RGBA")
    draw.polygon(pts, fill=(255, 255, 255, 255))
    # 中心微小星芒
    spark = star_points(cx, cy, outer * 0.14, outer * 0.04)
    draw.polygon(spark, fill=(0, 212, 255, 255))
    # 点缀
    for dx, dy, r in ((0.33, 0.72, 0.008), (0.72, 0.31, 0.006), (0.68, 0.7, 0.004)):
        draw.ellipse(
            (cx + s * dx - s * r, cy + s * dy - s * r, cx + s * dx + s * r, cy + s * dy + s * r),
            fill=(255, 255, 255, 180),
        )
    return bg.resize((size, size), Image.LANCZOS).convert("RGB")


if __name__ == "__main__":
    icon = make_icon(1024)
    icon.save(OUT / "aster.png")
    make_icon(512).save(OUT / "aster-512.png")
    make_icon(192).save(OUT / "aster-192.png")
    make_icon(512, maskable=True).save(OUT / "aster-maskable-512.png")
    icon.save(
        OUT / "aster.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("icons written to", OUT)
