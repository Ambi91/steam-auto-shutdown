#!/usr/bin/env python3
"""Generate the app icon in every format the builds need.

Needs Pillow (a build-time tool only, the app itself has no dependencies):
    pip install pillow
    python tools/make_icons.py

Outputs:
    assets/icon.png      512 px, used for the app window
    assets/icon.ico      Windows executable
    assets/icon.icns     macOS app bundle
    packaging/msix/Assets/*.png   Microsoft Store (MSIX) logos
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 1024  # master size; everything is drawn big and scaled down for smooth edges

BG_TOP = (30, 41, 59)      # slate
BG_BOTTOM = (15, 23, 42)
WHITE = (255, 255, 255)
GREEN = (34, 197, 94)


def master(rounded=True):
    """The icon: a power symbol whose vertical stroke is a green download arrow."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        k = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(BG_TOP, BG_BOTTOM)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22) if rounded else 0, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    cx, cy, r, w = S / 2, S * 0.54, S * 0.29, int(S * 0.075)
    # Ring with a gap at the top (power symbol).
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-50, end=230, fill=WHITE, width=w)
    for ang in (-50, 230):  # round the ring ends
        import math
        a = math.radians(ang)
        ex, ey = cx + (r - w / 2) * math.cos(a), cy + (r - w / 2) * math.sin(a)
        d.ellipse([ex - w / 2, ey - w / 2, ex + w / 2, ey + w / 2], fill=WHITE)
    # Download arrow in place of the vertical power stroke.
    top, tip = S * 0.16, S * 0.56
    d.rounded_rectangle([cx - w / 2, top, cx + w / 2, tip - S * 0.08], radius=w / 2, fill=GREEN)
    hw = S * 0.13
    d.polygon([(cx - hw, tip - S * 0.13), (cx + hw, tip - S * 0.13), (cx, tip + S * 0.03)], fill=GREEN)
    return img


def fit(img, w, h, scale=0.8, bg=None):
    """Place the icon centred on a w×h canvas (for the wide/tile Store logos)."""
    canvas = Image.new("RGBA", (w, h), bg or (0, 0, 0, 0))
    side = int(min(w, h) * scale)
    canvas.alpha_composite(img.resize((side, side), Image.LANCZOS), ((w - side) // 2, (h - side) // 2))
    return canvas


def main():
    icon = master()
    (ROOT / "assets").mkdir(exist_ok=True)
    icon.resize((512, 512), Image.LANCZOS).save(ROOT / "assets/icon.png")
    icon.save(ROOT / "assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(ROOT / "assets/icon.icns")

    out = ROOT / "packaging/msix/Assets"
    out.mkdir(parents=True, exist_ok=True)
    full = master(rounded=False)  # Windows tiles look better edge to edge
    targets = {
        "StoreLogo.png": (50, 50, 1.0),
        "Square44x44Logo.png": (44, 44, 1.0),
        "Square150x150Logo.png": (150, 150, 1.0),
        "Wide310x150Logo.png": (310, 150, 0.8),
    }
    for name, (w, h, sc) in targets.items():
        for scale in (100, 200):
            pw, ph = w * scale // 100, h * scale // 100
            img = fit(icon if sc < 1 else full, pw, ph, sc, bg=BG_BOTTOM + (255,) if sc < 1 else None)
            stem, ext = name.rsplit(".", 1)
            img.save(out / (name if scale == 100 else f"{stem}.scale-{scale}.{ext}"))
    # Taskbar/Start icon without a plate (the "unplated" variant Windows prefers).
    for size in (16, 24, 32, 48, 256):
        icon.resize((size, size), Image.LANCZOS).save(
            out / f"Square44x44Logo.targetsize-{size}_altform-unplated.png")
    print("Icons written.")


if __name__ == "__main__":
    main()
