# Boot animation generator (MLP1)

Generates the custom boot animation frames that ship in
`device/mlp1/boot-animation/` and get installed on-device by
`device/mlp1/platform.d/02-boot-animation.sh`.

This used to live only on Eric's machine (untracked). It's now in-repo so the
generator + source assets are backed up and reproducible.

## What it does

`generate.py` takes the synthwave spritesheet (8 frames) + a logo/text PNG,
erases the original NEXTUI text, composites the logo across the top, and writes
8 landscape PNG frames per sequence + `boot.cfg`. The MLP1 boot system rotates
landscape frames to the portrait panel (Weston isn't up yet during boot).

## Usage

```sh
cd tools/boot-animation
python3 generate.py            # needs Pillow (PIL); writes to ./output/
# preview ./output/0/*.png, then stage into the SD/device asset dir:
cp output/0/*.png   ../../device/mlp1/boot-animation/0/
cp output/1/*.png   ../../device/mlp1/boot-animation/1/
cp output/boot.cfg  ../../device/mlp1/boot-animation/boot.cfg
git add ../../device/mlp1/boot-animation && git commit
```

To change the logo: drop a new RGBA PNG in `assets/`, point `LOGO_PATH` at it,
and tune `logo_target_w` (size, fraction of frame width) / `dy` (top margin).
Current logo is `Leaf.png` (the "Leaf" CFW identity); `dweezil.png` is the prior one.

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

Heads-up on a couple of things here:

1. **All assets are original work.** `synthwave_spritesheet.png`,
   `synthwave_loop.ogg`, `Leaf.png`, and `dweezil.png` are all original work —
   100% part of this repo, no third-party content, free to ship and redistribute.

2. **`output/` is gitignored** — only the source (`generate.py` + `assets/`) is
   tracked here; the rendered frames are committed under
   `device/mlp1/boot-animation/` (the SD-staged copy). Keep those two in sync
   when regenerating.

3. Placed under `tools/` (not `device/`) on purpose — the big source assets must
   not get staged onto the SD card. Could spin out into its own repo later if you
   prefer; folded in here for now to keep generator + output together.
