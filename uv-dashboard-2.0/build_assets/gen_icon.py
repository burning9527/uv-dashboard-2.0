#!/usr/bin/env python3
"""Generate a premium gradient-geometric app icon for UV Dashboard 2.0.

Design: purple-blue diagonal gradient (#6B7CED -> #4F6BED) base, split into
two subtle facets by an anti-diagonal with a crisp highlight line. No text.
Rounded corners with transparent outside, exported as a macOS .iconset then
compiled to .icns via `iconutil`.
"""
import os
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = HERE  # gen_icon.py already lives inside build_assets
ICONSET = os.path.join(OUT_DIR, "AppIcon.iconset")
ICNS = os.path.join(OUT_DIR, "AppIcon.icns")

S = 1024
RADIUS = int(S * 0.224)  # ~22% corner radius

# Brand gradient endpoints (RGB)
A = np.array([107, 124, 237], dtype=float)  # #6B7CED  top-left
B = np.array([79, 107, 237], dtype=float)   # #4F6BED  bottom-right


def build_master():
    xs = np.linspace(0, 1, S)
    ys = np.linspace(0, 1, S)
    X, Y = np.meshgrid(xs, ys)          # X: column(0..1) Y: row(0..1)
    t = (X + Y) / 2.0                    # diagonal gradient param
    base = np.zeros((S, S, 3), dtype=float)
    for c in range(3):
        base[:, :, c] = A[c] + (B[c] - A[c]) * t

    # Anti-diagonal geometric division: upper-left lighter, lower-right darker
    upper = (Y <= 1 - X)
    white_a, black_a = 0.10, 0.12
    out = base.copy()
    out[upper] = out[upper] * (1 - white_a) + 255 * white_a
    out[~upper] = out[~upper] * (1 - black_a)

    # Specular sheen near top for premium feel
    sheen = np.clip(1.0 - Y * 1.4, 0, 1) ** 2
    out = out + sheen[:, :, None] * 18.0

    arr = np.clip(out, 0, 255).astype(np.uint8)
    im = Image.fromarray(arr, "RGB")
    d = ImageDraw.Draw(im, "RGBA")

    # Crisp anti-diagonal highlight line (from bottom-left to top-right)
    d.line([(0, S), (S, 0)], fill=(255, 255, 255, 85), width=4)

    # Subtle accent: a small floating rounded square (data panel) lower-right
    a0 = int(S * 0.62)
    sz = int(S * 0.21)
    d.rounded_rectangle(
        [a0, a0, a0 + sz, a0 + sz],
        radius=int(sz * 0.22),
        fill=(255, 255, 255, 34),
        outline=(255, 255, 255, 80),
        width=3,
    )

    # Rounded-corner transparency mask
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S, S], radius=RADIUS, fill=255)
    alpha = np.array(mask)
    rgba = np.dstack([np.array(im), alpha])
    return Image.fromarray(rgba, "RGBA")


def main():
    os.makedirs(ICONSET, exist_ok=True)
    master = build_master()

    specs = [
        (16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
        (256, 1), (256, 2), (512, 1), (512, 2),
    ]
    for size, scale in specs:
        px = size * scale
        thumb = master.resize((px, px), Image.LANCZOS)
        name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
        thumb.save(os.path.join(ICONSET, name))
        print("wrote", name)

    # Compile to icns
    os.system(f'iconutil -c icns "{ICONSET}" -o "{ICNS}"')
    print("compiled ->", ICNS)


if __name__ == "__main__":
    main()
