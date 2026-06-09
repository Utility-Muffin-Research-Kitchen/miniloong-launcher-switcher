#!/usr/bin/env python3
"""Generate the MLP1 Leaf boot animation: a "deconstructed leaf" that assembles,
then settles into a gentle breath.

Source asset:
  assets/deconstructed.png   — the Leaf duotone mark (two halves + detached stem,
                               separated by negative-space gaps; also the docs logo)

Output (./output/, gitignored):
  0/0.png .. 0/11.png        — sequence 0: assembly intro (12 frames, plays once)
  1/0.png .. 1/7.png         — sequence 1: breathing loop (8 frames, repeats)
  boot.cfg                   — MLP1 boot animation config

Frames are landscape 960x720 (the user orientation); the MLP1 boot system rotates
them to the portrait panel. The animation is dismissed by jawakad the instant the
launcher renders its first frame, so its visible length == launcher startup time.

The previous synthwave generator is preserved as generate_synthwave.py.
"""
from PIL import Image
import numpy as np
import os
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(SCRIPT_DIR, "assets", "deconstructed.png")
OUT = os.path.join(SCRIPT_DIR, "output")

FRAME_W, FRAME_H = 960, 720       # landscape; boot system rotates to the panel
ASSEMBLY_FRAMES = 12              # sequence 0 (plays once)
LOOP_FRAMES = 8                   # sequence 1 (breathing, repeats)
LEAF = 540                        # rendered leaf size (square source)

# The three pieces, by colour (matches deconstructed.png).
COLORS = {"light": (142, 210, 127), "dark": (47, 125, 79), "stem": (26, 71, 42)}
# Where each piece starts (offset from its final spot, in px) before sliding home.
# Halves split apart along the seam's perpendicular; the stem drops from above.
START = {"light": (-360, -200), "dark": (360, 200), "stem": (0, -300)}

# Dark base + soft green glow for the background.
BG_BASE = np.array([15, 22, 14], float)
BG_GLOW = np.array([60, 120, 55], float)


def smoothstep(x):
    return x * x * (3 - 2 * x)


def split_pieces(src_path):
    im = Image.open(src_path).convert("RGBA")
    arr = np.array(im).astype(np.int32)
    rgb, alpha = arr[:, :, :3], arr[:, :, 3]
    opaque = alpha > 80
    nearest = np.argmin(
        np.stack([((rgb - np.array(c)) ** 2).sum(2) for c in COLORS.values()]), 0)
    pieces = {}
    for i, name in enumerate(COLORS):
        mask = opaque & (nearest == i)
        out = arr.copy()
        out[~mask] = 0
        layer = Image.fromarray(out.astype(np.uint8), "RGBA")
        pieces[name] = layer.resize((LEAF, LEAF), Image.LANCZOS)
    return pieces


def glow(strength):
    yy, xx = np.mgrid[0:FRAME_H, 0:FRAME_W]
    r = np.sqrt(((xx - FRAME_W / 2) / (FRAME_W * 0.5)) ** 2 +
                ((yy - FRAME_H / 2) / (FRAME_H * 0.55)) ** 2)
    g = np.clip(1 - r, 0, 1) ** 2 * strength
    img = BG_BASE[None, None, :] + g[:, :, None] * BG_GLOW[None, None, :]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def paste(base, layer, xy, opacity, scale=1.0):
    if opacity <= 0:
        return
    img = layer
    if scale != 1.0:
        s = int(LEAF * scale)
        img = layer.resize((s, s), Image.LANCZOS)
        xy = (xy[0] + (LEAF - s) // 2, xy[1] + (LEAF - s) // 2)
    if opacity < 1:
        img = img.copy()
        img.putalpha(img.split()[3].point(lambda p: int(p * opacity)))
    base.alpha_composite(img, xy)


def main():
    pieces = split_pieces(SRC)
    leaf_x, leaf_y = (FRAME_W - LEAF) // 2, (FRAME_H - LEAF) // 2

    def assembly_frame(t):
        e = smoothstep(t / (ASSEMBLY_FRAMES - 1))
        base = glow(0.5)
        for name in ("dark", "light", "stem"):
            ox, oy = START[name]
            x = leaf_x + int(ox * (1 - e))
            y = leaf_y + int(oy * (1 - e))
            delay = 0 if name != "stem" else 2          # stem lands slightly later
            op = min(1.0, max(0, (t - delay + 1)) / 3.0)
            paste(base, pieces[name], (x, y), op, 0.85 + 0.15 * e)
        return base.convert("RGB")

    def loop_frame(t):
        strength = 0.5 + 0.45 * (0.5 + 0.5 * math.sin(2 * math.pi * t / LOOP_FRAMES))
        base = glow(strength)
        for name in ("dark", "light", "stem"):
            paste(base, pieces[name], (leaf_x, leaf_y), 1.0)
        return base.convert("RGB")

    for seq, fn, n in [("0", assembly_frame, ASSEMBLY_FRAMES),
                       ("1", loop_frame, LOOP_FRAMES)]:
        d = os.path.join(OUT, seq)
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        for i in range(n):
            fn(i).save(os.path.join(d, f"{i}.png"))
        print(f"sequence {seq}: {n} frames")

    cfg = ('{"dir":"/loong/textures/boot","bg":0,"seques":['
           '{"num":%d,"interval":100,"wait":0,"repeat":0},'
           '{"num":%d,"interval":100,"wait":0,"repeat":-1}]}'
           % (ASSEMBLY_FRAMES, LOOP_FRAMES))
    with open(os.path.join(OUT, "boot.cfg"), "w") as f:
        f.write(cfg)
    print(f"Done. Output at: {OUT}")


if __name__ == "__main__":
    main()
