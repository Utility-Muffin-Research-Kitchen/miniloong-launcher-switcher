# Miniloong Launcher Switcher

Standalone launcher replacement installer for the Miniloong Pocket 1.

This project is intentionally separate from `miniloong-adb-keeper`. It reuses
the known `loong_upgrade` SD update mechanism, and owns the payload generator,
installer, logs, wrapper, device defaults, and recovery scripts.

It does **not** build the launcher itself. The launcher payload (Jawaka binaries
plus Catastrophe/RetroArch/cores assets) is assembled by the UMRK workspace
orchestrator; this repo wraps that payload into an installable SD/ADB bundle.
See the workspace `make stage-jawaka` / `make assemble-jawaka`.

## Contract

The switcher replaces only the visible GUI entrypoint:

```text
/loong/loong_pangu
```

The installer saves the stock binary as:

```text
/loong/loong_pangu.stock.umrk
```

At boot, the wrapper checks:

```text
UMRK_MARKER_PATH
UMRK_BIN_PATH/loong_pangu
```

If both exist, it remounts the SD card as executable and execs:

```text
UMRK_BIN_PATH/loong_pangu
```

When the marker is present, the wrapper first remounts `SDCARD_PATH` with
`exec` while preserving the stock mount options. When the marker is absent or
the wrapper falls back to stock, it best-effort restores the StockOS `noexec`
SD mount. If the marker is absent, the SD card is absent, remounting fails, or
the bundle is incomplete, it starts the stock GUI. The wrapper starts the stock
backup through a temporary `loong_pangu` symlink so the process still looks like
the normal stock GUI to stock supervision code.

## Build the SD payload

First assemble the launcher payload from the workspace (builds Jawaka and
gathers Catastrophe/RetroArch/cores into `build/stage/mlp1/package`):

```sh
make assemble-jawaka
```

Then wrap it into an SD-root OTA install payload, pointing `BUNDLE_ROOT` at the
assembled tree:

```sh
cd miniloong-launcher-switcher
make sd-payload BUNDLE_ROOT=../build/stage/mlp1/package
```

The SD-root payload is written to:

```text
build/sd/
  loong_upgrade
  launcher_probe.bin
  umrk-launcher-install.sh
  umrk-launcher/
    bin/loong_pangu
    bin/jawaka-launcher
    bin/jawaka-menu
    res/
  UMRK/mlp1/
    manifest.json
    defaults/
```

It does not enable the runtime marker by default. To generate a marked payload
for trusted one-card activation:

```sh
make sd-payload-marked BUNDLE_ROOT=../build/stage/mlp1/package
```

Do not use exFAT for install media. The stock daemon ignores exFAT SD cards for
this update path.

## ADB Tests

Install the wrapper over ADB:

```sh
make adb-install-wrapper
```

Stage the launcher bundle on the mounted SD card and enable the marker
(point `BUNDLE_ROOT` at the assembled payload):

```sh
make adb-stage-sd-bundle BUNDLE_ROOT=../build/stage/mlp1/package
adb shell '/etc/init.d/S50loong restart'
```

Stage the launcher bundle without activating it:

```sh
make adb-stage-sd-bundle-no-marker BUNDLE_ROOT=../build/stage/mlp1/package
```

Toggle activation and restart the stock Loong stack:

```sh
make adb-enable-marker
make adb-restart-loong

make adb-disable-marker
make adb-restart-loong
```

Test stock fallback by removing the marker:

```sh
scripts/adb-stage-sd-bundle.sh --no-marker
adb shell '/etc/init.d/S50loong restart'
```

Tail switcher logs:

```sh
make adb-tail-logs
```

To stage directly from the workspace (assemble + push + activate in one step):

```sh
make stage-jawaka DEVICE=mlp1
```

The installed switcher wrapper has crash-loop protection. If the marker is
present and the custom launcher path is entered repeatedly within a short
window, it disables the marker and starts stock. Remount failure also disables
the marker immediately, because the direct-SD Jawaka path cannot run safely
while the SD-card mount is `noexec`.
MLP1 defaults `SDCARD_PATH` to `/mnt/sdcard`; override `REMOTE_SDCARD_PATH`
for ADB staging tests when needed.

## SD Install

Copy the contents of `build/sd/` to the root of a FAT32 or ext4 SD card:

```sh
cp -R build/sd/. "/Volumes/SDCARD_NAME/"
sync
diskutil eject "/Volumes/SDCARD_NAME"
```

Boot the MLP1 with the SD inserted. The device will enter the stock update
screen while the installer runs. The installer renames `loong_upgrade` to
`loong_upgrade.used`, writes logs, installs the wrapper, then returns to the
stock update command path, which intentionally sleeps forever to avoid a full
upgrade attempt. Power off after install, then boot normally.

Logs:

```text
UMRK_INTERNAL_DATA_PATH/umrk-launcher-install.log
SDCARD_PATH/umrk-launcher-install.log
UMRK_INTERNAL_DATA_PATH/umrk-launcher.log
```

## Recovery

Over ADB:

```sh
make adb-uninstall-wrapper
adb shell '/etc/init.d/S50loong restart'
```

Or directly:

```sh
adb shell '/usr/bin/umrk-launcher-switcher-uninstall.sh'
```

The uninstall script restores `/loong/loong_pangu` from
`/loong/loong_pangu.stock.umrk`.
