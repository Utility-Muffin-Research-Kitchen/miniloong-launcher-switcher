#!/usr/bin/env python3
"""Generate MLP1 boot animation from synthwave spritesheet + logo text.

Source assets in assets/:
  synthwave_spritesheet.png  — 8192x768, 8 frames horizontal (1024x768 each)
  Leaf.png                   — RGBA logo/text with transparency (top banner)
  synthwave.cfg              — frame_count=8, fps=10

Output in output/:
  0/                         — sequence 0: intro (plays a few times)
  1/                         — sequence 1: loop (repeats)
  boot.cfg                   — MLP1 boot animation config

MLP1 boot frames are landscape PNG; the boot animation system rotates to the
portrait panel (Weston isn't running yet during boot).
"""
from PIL import Image, ImageDraw
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
OUT_DIR = os.path.join(SCRIPT_DIR, "output")

SHEET_PATH = os.path.join(ASSETS_DIR, "synthwave_spritesheet.png")
LOGO_PATH = os.path.join(ASSETS_DIR, "Leaf.png")

# MLP1 boot animation system handles display rotation internally (stock frames
# are landscape). Output at full landscape resolution — the system scales and
# rotates to fit the portrait panel.
FRAME_W = 960
FRAME_H = 720

# Spritesheet layout
SHEET_FRAME_W = 1024
SHEET_FRAME_H = 768
FRAME_COUNT = 8

# NEXTUI text region to paint over (approximate, in source frame coords)
NEXTUI_REGION = (0, 0, 1024, 180)

def main():
    print("Loading assets...")
    sheet = Image.open(SHEET_PATH).convert("RGBA")
    logo = Image.open(LOGO_PATH).convert("RGBA")
    # Trim transparent padding so placement is exact (the PNG has top/side
    # margins that otherwise push the visible text down).
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)

    # Split spritesheet into frames
    frames = []
    for i in range(FRAME_COUNT):
        x = i * SHEET_FRAME_W
        frame = sheet.crop((x, 0, x + SHEET_FRAME_W, SHEET_FRAME_H))
        frames.append(frame)
    print(f"Split {len(frames)} frames")

    # Erase NEXTUI text region by sampling the background color from the
    # dark area at the top of each frame and painting over it
    cleaned = []
    for frame in frames:
        f = frame.copy()
        # Sample background color from top-left corner (dark sky area)
        bg = f.getpixel((10, NEXTUI_REGION[3] + 5))
        draw = ImageDraw.Draw(f)
        draw.rectangle(NEXTUI_REGION, fill=bg)
        cleaned.append(f)
    print("Cleaned NEXTUI text from frames")

    # Scale logo text to fit (preserve aspect ratio). Sized smaller than the
    # frame width so the (tall) logo sits clear above the sun rather than
    # overlapping it.
    logo_target_w = int(SHEET_FRAME_W * 0.52)
    logo_scale = logo_target_w / logo.width
    logo_target_h = int(logo.height * logo_scale)
    logo_resized = logo.resize((logo_target_w, logo_target_h), Image.LANCZOS)
    print(f"Logo scaled to {logo_target_w}x{logo_target_h}")

    # Composite logo onto each cleaned frame (centered, near the top)
    composited = []
    for frame in cleaned:
        comp = frame.copy()
        dx = (SHEET_FRAME_W - logo_target_w) // 2
        dy = int(SHEET_FRAME_H * 0.03)   # small top margin from the trimmed logo
        comp.paste(logo_resized, (dx, dy), logo_resized)
        composited.append(comp)
    print("Composited logo text")

    # Generate boot sequences. Source is landscape 1024x768; output landscape
    # FRAME_WxFRAME_H — the boot animation system handles rotation to portrait.
    for seq, count in [(0, 8), (1, 8)]:
        seq_dir = os.path.join(OUT_DIR, str(seq))
        os.makedirs(seq_dir, exist_ok=True)
        for i in range(count):
            src = composited[i % FRAME_COUNT]
            resized = src.resize((FRAME_W, FRAME_H), Image.LANCZOS)
            rgb = Image.new("RGB", (FRAME_W, FRAME_H), (0, 0, 0))
            rgb.paste(resized, mask=resized.split()[3] if resized.mode == "RGBA" else None)
            rgb.save(os.path.join(seq_dir, f"{i}.png"))
        print(f"Sequence {seq}: {count} frames")

    # Write boot.cfg. 8 unique frames, interval=100 (~10fps). Sequence 0 plays
    # 5 times (repeat=4), sequence 1 loops forever until Jawaka takes over.
    cfg = '{"dir":"/loong/textures/boot","bg":255,"seques":[{"num":8,"interval":100,"wait":0,"repeat":4},{"num":8,"interval":100,"wait":0,"repeat":-1}]}'
    with open(os.path.join(OUT_DIR, "boot.cfg"), "w") as f:
        f.write(cfg)

    print(f"Done! Output at: {OUT_DIR}")

if __name__ == "__main__":
    main()
