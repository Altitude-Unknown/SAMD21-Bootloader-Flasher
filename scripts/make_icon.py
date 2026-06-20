#!/usr/bin/env python3
"""Generate macOS and Windows app icons from the Altitude Unknown logo."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_LOGO = ROOT / "assets" / "icons" / "altitude-unknown-logo.png"
ICON_PNG = ROOT / "assets" / "icons" / "app_icon.png"
ICON_ICO = ROOT / "assets" / "icons" / "app_icon.ico"
ICON_ICNS = ROOT / "assets" / "icons" / "app_icon.icns"
LABEL = "FLASH"


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def make_icon_png() -> Image.Image:
    src = Image.open(SOURCE_LOGO).convert("RGBA")
    src.thumbnail((900, 900), Image.Resampling.LANCZOS)

    icon = Image.new("RGBA", (1024, 1024), (5, 8, 10, 255))
    glow = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((90, 90, 934, 934), outline=(130, 150, 160, 90), width=12)
    icon.alpha_composite(glow)

    x = (1024 - src.width) // 2
    y = 34
    icon.alpha_composite(src, (x, y))

    draw = ImageDraw.Draw(icon)
    badge = (246, 800, 778, 936)
    draw.rounded_rectangle(badge, radius=44, fill=(16, 30, 38, 238), outline=(210, 225, 230, 210), width=4)
    draw.rounded_rectangle((badge[0] + 10, badge[1] + 10, badge[2] - 10, badge[3] - 10), radius=34, outline=(61, 151, 180, 170), width=3)

    label_font = font(72)
    bbox = draw.textbbox((0, 0), LABEL, font=label_font)
    text_x = (1024 - (bbox[2] - bbox[0])) // 2
    text_y = badge[1] + ((badge[3] - badge[1]) - (bbox[3] - bbox[1])) // 2 - 8
    draw.text((text_x, text_y), LABEL, font=label_font, fill=(245, 248, 250, 255))

    ICON_PNG.parent.mkdir(parents=True, exist_ok=True)
    icon.save(ICON_PNG)
    return icon


def main() -> None:
    icon = make_icon_png()
    icon.save(ICON_ICO, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(ICON_ICNS, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])


if __name__ == "__main__":
    main()
