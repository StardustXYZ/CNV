"""Draw the icons of CNV: the white clapperboard on the purple gradient of the web app.

Writes into android/app/src/main/res/ the classic icon (old Android versions), the two
layers of the adaptive icon (Android shapes it as a circle, squircle…), the single-colour
version for themed icons (Android 13+) and the small white icon of the notifications; into
web/ the icons of the browser version (tab, home screen, maskable). The PNG files are
committed, so this runs only when the icon changes. Needs Pillow (pip install pillow).

Usage, from the mobile/ folder:
    python tools/crea_icone.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

RES = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "res"
WEB = Path(__file__).resolve().parent.parent / "web"
SUPERSAMPLE = 4  # drawn bigger, then reduced: smooth edges

TOP = (184, 132, 252)  # gradient of the web icon (phone/icons/icon-512.png)
BOTTOM = (127, 79, 255)
WHITE = (255, 255, 255, 255)
LAVENDER = (217, 200, 255, 255)
NAVY = (42, 27, 77, 255)
CLEAR = (0, 0, 0, 0)

# Density folder -> scale (classic icon 48 px, adaptive layers 108 px at mdpi)
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}

# The clapperboard is designed on a 512 grid, where it spans x 93-417 and y 128-412
GLYPH_CENTRE = (255, 270)


def gradient(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(size - 1, 1)
        draw.line([(0, y), (size, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,))
    return img


def clapperboard(size: int, scale: float, mono: bool = False) -> Image.Image:
    """The clapperboard alone, centred on a transparent square of ``size`` px.

    ``scale`` is the share of the square taken by the 512 grid; ``mono`` draws the
    single-colour version: white, with the dark and lavender parts cut out.
    """
    big = size * SUPERSAMPLE
    unit = big * scale / 512
    ox = big / 2 - GLYPH_CENTRE[0] * unit
    oy = big / 2 - GLYPH_CENTRE[1] * unit

    def box(x0, y0, x1, y1):
        return [ox + x0 * unit, oy + y0 * unit, ox + x1 * unit, oy + y1 * unit]

    img = Image.new("RGBA", (big, big), CLEAR)
    draw = ImageDraw.Draw(img)
    dark = CLEAR if mono else NAVY

    # Board with its two lines
    draw.rounded_rectangle(box(100, 218, 412, 412), radius=24 * unit, fill=WHITE)
    for y in (280, 345):
        draw.rounded_rectangle(box(135, y, 377, y + 17), radius=8.5 * unit, fill=CLEAR if mono else LAVENDER)

    # Top bar: drawn flat with its diagonal stripes, then tilted and placed
    w, h = round(316 * unit), round(62 * unit)
    bar = Image.new("RGBA", (w, h), CLEAR)
    bar_draw = ImageDraw.Draw(bar)
    bar_draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=10 * unit, fill=WHITE)
    stripe = 37 * unit
    mask = Image.new("L", (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)
    x = -h
    while x < w + h:
        mask_draw.polygon([(x, h), (x + h * 0.9, 0), (x + h * 0.9 + stripe, 0), (x + stripe, h)], fill=255)
        x += stripe * 2
    rounded = Image.new("L", (w, h), 0)
    ImageDraw.Draw(rounded).rounded_rectangle([0, 0, w - 1, h - 1], radius=10 * unit, fill=255)
    stripes = Image.new("RGBA", (w, h), dark)
    bar.paste(stripes, (0, 0), Image.composite(mask, Image.new("L", (w, h), 0), rounded))
    tilted = bar.rotate(-8.5, resample=Image.BICUBIC, expand=True)
    cx, cy = ox + 260 * unit, oy + 180 * unit
    img.alpha_composite(tilted, (round(cx - tilted.width / 2), round(cy - tilted.height / 2)))

    # Hinge
    r = 16 * unit
    hx, hy = ox + 108 * unit, oy + 205 * unit
    draw.ellipse([hx - r, hy - r, hx + r, hy + r], fill=WHITE if mono else NAVY)

    return img.resize((size, size), Image.LANCZOS)


def classic(size: int) -> Image.Image:
    """The full icon of old Android versions: rounded purple square with the clapperboard."""
    mask = Image.new("L", (size * SUPERSAMPLE,) * 2, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size * SUPERSAMPLE - 1, size * SUPERSAMPLE - 1],
                                           radius=size * SUPERSAMPLE * 0.22, fill=255)
    icon = Image.new("RGBA", (size, size), CLEAR)
    icon.paste(gradient(size), (0, 0), mask.resize((size, size), Image.LANCZOS))
    icon.alpha_composite(clapperboard(size, 0.92))
    return icon


def main() -> None:
    for name, density in DENSITIES.items():
        folder = RES / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        classic(round(48 * density)).save(folder / "ic_launcher.png", optimize=True)
        layer = round(108 * density)
        gradient(layer).save(folder / "ic_launcher_background.png", optimize=True)
        # Only the middle 66 of 108 is always visible: the clapperboard stays inside it
        clapperboard(layer, 0.70).save(folder / "ic_launcher_foreground.png", optimize=True)
        clapperboard(layer, 0.70, mono=True).save(folder / "ic_launcher_monochrome.png", optimize=True)
        # Notifications: 24 dp, white on transparent (Android colours it), almost edge to edge
        small = RES / f"drawable-{name}"
        small.mkdir(parents=True, exist_ok=True)
        clapperboard(round(24 * density), 0.92, mono=True).save(small / "ic_notifica.png", optimize=True)

    adaptive = RES / "mipmap-anydpi-v26"
    adaptive.mkdir(parents=True, exist_ok=True)
    (adaptive / "ic_launcher.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@mipmap/ic_launcher_background" />\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n'
        '    <monochrome android:drawable="@mipmap/ic_launcher_monochrome" />\n'
        "</adaptive-icon>\n",
        encoding="utf-8",
    )

    # Browser: the full icon, and the "maskable" one the system cuts to its own shape
    (WEB / "icons").mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        classic(size).save(WEB / "icons" / f"Icon-{size}.png", optimize=True)
        maskable = gradient(size).convert("RGBA")
        maskable.alpha_composite(clapperboard(size, 0.70))  # inside the safe circle
        maskable.save(WEB / "icons" / f"Icon-maskable-{size}.png", optimize=True)
    classic(32).save(WEB / "favicon.png", optimize=True)
    print(f"Icone salvate in {RES} e {WEB}")


if __name__ == "__main__":
    main()
