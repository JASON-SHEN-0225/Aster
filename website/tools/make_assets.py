"""生成官网静态图片素材。

用法：python website/tools/make_assets.py

输入：项目根目录的 assets/aster.png 与 docs/screenshots/*.png
输出：website/assets/img/*.webp、favicon、apple-touch-icon、og.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "website" / "assets" / "img"
OUT.mkdir(parents=True, exist_ok=True)

FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_LATIN = "C:/Windows/Fonts/segoeuib.ttf"

BG = (10, 16, 27)


def font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=index)


def rounded_icon(size: int) -> Image.Image:
    """把 App 图标缩放到 size，再套上圆角（源图四角是黑色实心）。"""
    src = Image.open(ROOT / "assets" / "aster.png").convert("RGBA")
    src = src.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255
    )
    src.putalpha(mask)
    return src


def save_favicons() -> None:
    icon = rounded_icon(512)

    for size in (32, 180, 192, 512):
        img = icon.resize((size, size), Image.LANCZOS)
        if size == 180:  # iOS 主屏图标不透明
            base = Image.new("RGBA", (size, size), BG + (255,))
            inner = img.resize((int(size * 0.86),) * 2, Image.LANCZOS)
            base.alpha_composite(inner, ((size - inner.width) // 2,) * 2)
            img = base.convert("RGB")
        img.save(OUT / f"icon-{size}.png", optimize=True)

    icon.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("favicon / apple-touch-icon ok")


def convert_screenshots() -> None:
    used = {
        "gui-home", "gui-dark", "gui-devices", "gui-settings",
        "mobile-home", "mobile-uploading", "mobile-offer",
    }
    for path in sorted((ROOT / "docs" / "screenshots").glob("*.png")):
        if path.stem not in used:
            continue
        img = Image.open(path).convert("RGB")
        target = OUT / f"{path.stem}.webp"
        img.save(target, "WEBP", quality=88, method=6)
        print(f"{path.name:26s} {path.stat().st_size / 1024:7.1f} KB -> "
              f"{target.stat().st_size / 1024:6.1f} KB")


def glow(size: tuple[int, int], color: tuple[int, int, int], alpha: int,
         center: tuple[float, float], radius: float) -> Image.Image:
    """在一张透明图上画一个柔和的径向光斑。"""
    w, h = size
    layer = Image.new("L", size, 0)
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    steps = 18
    for i in range(steps, 0, -1):
        r = radius * i / steps
        a = int(alpha * (1 - i / steps) ** 1.6)
        draw.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], fill=a)
    layer = layer.filter(ImageFilter.GaussianBlur(radius / 3))
    tint = Image.new("RGBA", size, color + (0,))
    tint.putalpha(layer)
    return tint


def gradient_text(size: tuple[int, int], text: str, fnt: ImageFont.FreeTypeFont,
                  start: tuple[int, int, int], end: tuple[int, int, int],
                  offset: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).text(offset, text, font=fnt, fill=255)

    grad = Image.new("RGBA", size)
    pixels = grad.load()
    w, h = size
    for y in range(h):
        for x in range(w):
            t = min(1.0, max(0.0, (x * 0.9 + y * 0.1) / w))
            pixels[x, y] = tuple(
                int(start[i] + (end[i] - start[i]) * t) for i in range(3)
            ) + (255,)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def make_og() -> None:
    w, h = 1200, 630
    card = Image.new("RGB", (w, h), BG).convert("RGBA")
    card.alpha_composite(glow((w, h), (76, 154, 255), 120, (905, 170), 540))
    card.alpha_composite(glow((w, h), (56, 214, 184), 95, (1120, 560), 440))
    card.alpha_composite(glow((w, h), (76, 154, 255), 55, (80, 600), 380))

    # 细网格
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, w, 60):
        gd.line([(x, 0), (x, h)], fill=(255, 255, 255, 8), width=1)
    for y in range(0, h, 60):
        gd.line([(0, y), (w, y)], fill=(255, 255, 255, 8), width=1)
    card.alpha_composite(grid)

    # 右侧 App 图标 + 光晕
    icon = rounded_icon(300)
    halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    halo_src = icon.resize((400, 400), Image.LANCZOS)
    halo.paste(halo_src, (785, 110), halo_src)
    halo = halo.filter(ImageFilter.GaussianBlur(58))
    card.alpha_composite(halo)
    card.alpha_composite(icon, (838, 158))

    draw = ImageDraw.Draw(card)

    # 顶部标识
    draw.text((88, 78), "ASTER  /  星流", font=font(FONT_BOLD, 24),
              fill=(56, 214, 184))

    # 标题（渐变）
    title_font = font(FONT_BOLD, 76)
    title = "把文件，交给星流。"
    title_img = gradient_text((w, 140), title, title_font,
                              (240, 247, 255), (120, 232, 214), (88, 6))
    card.alpha_composite(title_img, (84, 176))

    draw = ImageDraw.Draw(card)
    draw.text((90, 330), "局域网文件互传 · 零中转 · 零上传 · 零账号",
              font=font(FONT_REG, 30), fill=(168, 182, 202))

    # 分隔线
    line = Image.new("RGBA", (520, 2))
    for x in range(520):
        t = x / 520
        line.putpixel((x, 0), (76, 154, 255, int(200 * (1 - t))) )
    card.alpha_composite(line, (90, 404))

    draw = ImageDraw.Draw(card)
    draw.text((90, 440), "Windows 10 / 11   ·   Android   ·   Web",
              font=font(FONT_REG, 24), fill=(126, 142, 165))
    draw.text((90, 496), "v2.0.0", font=font(FONT_LATIN, 24), fill=(76, 154, 255))
    draw.text((190, 496), "·  MIT License", font=font(FONT_LATIN, 22), fill=(126, 142, 165))
    draw.text((90, 546), "asterdrop.cn", font=font(FONT_LATIN, 26), fill=(233, 239, 249))

    card.convert("RGB").save(OUT / "og.png", optimize=True)
    print("og.png ok")


def main() -> None:
    save_favicons()
    convert_screenshots()
    make_og()
    print("done ->", OUT)


if __name__ == "__main__":
    main()
