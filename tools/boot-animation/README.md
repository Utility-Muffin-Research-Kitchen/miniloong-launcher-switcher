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

## On-device install (handled by platform.d/02-boot-animation.sh)

First boot copies `SD:/UMRK/mlp1/boot-animation/{0,1}/*.png` + `boot.cfg` into
`/loong/textures/boot/` (+ `/loong/textures/boot.cfg`). Stock animation is backed
up to `/loong/textures/boot.stock`; a stamp (`/loong/textures/.umrk-boot-installed`)
prevents re-copy. To re-install after updating frames: delete the stamp, or copy
manually (remount `/` rw first).

---

## NOTE FOR HELAAS

Heads-up on a couple of things here:

1. **Asset licensing — please sanity-check before we treat this as public-redist.**
   `Leaf.png` / `dweezil.png` are our own text art. But
   `synthwave_spritesheet.png` and `synthwave_loop.ogg` came from an external
   source (origin not fully documented). Since this repo is public, we should
   confirm they're redistributable (or swap them for known-licensed assets, the
   way Catastrophe replaced the NextUI preview sprites). Flagging rather than
   blocking — your call on provenance.

2. **`output/` is gitignored** — only the source (`generate.py` + `assets/`) is
   tracked here; the rendered frames are committed under
   `device/mlp1/boot-animation/` (the SD-staged copy). Keep those two in sync
   when regenerating.

3. Placed under `tools/` (not `device/`) on purpose — the big source assets must
   not get staged onto the SD card. Could spin out into its own repo later if you
   prefer; folded in here for now to keep generator + output together.
