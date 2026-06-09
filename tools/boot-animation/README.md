# Boot animation generator (MLP1)

Generates the custom boot animation frames that ship in
`device/mlp1/boot-animation/` and get installed on-device by
`device/mlp1/platform.d/02-boot-animation.sh`.

In-repo so the generator + source assets are backed up and reproducible.

## What it does

`generate.py` takes the **deconstructed Leaf mark** (`assets/deconstructed.png`
— two leaf halves + a detached stem, separated by negative-space gaps; also the
docs-site logo) and renders a short **assembly** animation that settles into a
gentle **breath**:

- `0/0.png .. 0/11.png` — sequence 0: the three pieces fly in from apart and
  assemble (12 frames, plays once).
- `1/0.png .. 1/7.png` — sequence 1: the assembled leaf breathes via a pulsing
  green glow (8 frames, loops).
- `boot.cfg` — the MLP1 boot config (`bg:0`, seq0 `repeat:0`, seq1 `repeat:-1`).

Frames are landscape 960x720 (the user orientation); the MLP1 boot system rotates
them to the portrait panel (Weston isn't up yet during boot). The animation is
dismissed by jawakad the instant the launcher renders its first frame
(`device_mlp1.c jw__mlp1_frontend_ready`), so its visible length equals launcher
startup time — it isn't on a timer.

The breath here intentionally matches the launcher's default LED ring (a subdued
`#0B2800` green breath), so the device breathes consistently from boot into the
launcher.

## Usage

```sh
cd tools/boot-animation
python3 generate.py            # needs Pillow (PIL) + numpy; writes to ./output/
# preview ./output/0/*.png and ./output/1/*.png, then stage into the device payload:
cp output/0/*.png   ../../device/mlp1/boot-animation/0/
cp output/1/*.png   ../../device/mlp1/boot-animation/1/
cp output/boot.cfg  ../../device/mlp1/boot-animation/boot.cfg
git add ../../device/mlp1/boot-animation && git commit
```

To change the mark: drop a new RGBA PNG in `assets/`, point `SRC` at it, and (if
its colours differ) update the `COLORS` map used to split it into pieces. Tune
`ASSEMBLY_FRAMES`, `START` offsets, `LEAF` size, or the glow to taste.

`generate_synthwave.py` is the previous synthwave-spritesheet + wordmark
generator, preserved as an alternative.

## On-device install

Leaf mode copies `SD:/.system/leaf/platforms/mlp1/boot-animation/{0,1}/*.png`
and `boot.cfg` into `/loong/textures/boot/` before starting Jawaka, then starts
`/loong/loong_transition` directly because the `S50leaf` boot path bypasses
stock `S50loong`. Stock animation is backed up to `/loong/textures/boot.stock`
and `/loong/textures/boot.cfg.stock.umrk`; a mode marker
(`/loong/textures/.umrk-boot-mode`) avoids re-copying while the desired mode is
already active.

When Leaf passes through to stock, the session restores the stock backup before
returning to `S50loong`. The compatibility `platform.d/02-boot-animation.sh`
keeps older/direct paths in sync. To disable Leaf's boot splash, Jawaka writes
`.system/leaf/platforms/mlp1/state/boot-splash-disabled`.

---

## NOTE FOR HELAAS

1. **All assets are original work** — `deconstructed.png`, `synthwave_spritesheet.png`,
   `synthwave_loop.ogg`, `Leaf.png`, and `dweezil.png` are all original, free to
   ship and redistribute, no third-party content.

2. **`output/` is gitignored** — only the source (`generate.py` + `assets/`) is
   tracked here; the rendered frames are committed under
   `device/mlp1/boot-animation/` (the SD-staged copy). Keep those two in sync
   when regenerating.

3. Placed under `tools/` (not `device/`) on purpose — the big source assets must
   not get staged onto the SD card.

4. The deconstructed-leaf animation is the current default; `generate_synthwave.py`
   is the prior synthwave version if you ever want to switch back or offer a choice.
