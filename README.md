# Miniloong Launcher Switcher

Standalone launcher replacement installer for the Miniloong Pocket 1.

This project is intentionally separate from `miniloong-adb-keeper`. It reuses
the known `loong_upgrade` SD update mechanism, but it has its own payload
generator, installer, logs, wrapper, POC launcher, and recovery scripts.

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
/mnt/sdcard/.umrk-launcher
/mnt/sdcard/umrk-launcher/bin/loong_pangu
```

If both exist, it remounts the SD card as executable and execs:

```text
/mnt/sdcard/umrk-launcher/bin/loong_pangu
```

When the marker is present, the wrapper first remounts `/mnt/sdcard` with
`exec` while preserving the stock mount options. When the marker is absent or
the wrapper falls back to stock, it best-effort restores the StockOS `noexec`
SD mount. If the marker is absent, the SD card is absent, remounting fails, or
the bundle is incomplete, it starts the stock GUI. The wrapper starts the stock
backup through a temporary `loong_pangu` symlink so the process still looks like
the normal stock GUI to stock supervision code.

## Build

The POC launcher is an SDL2 Wayland program built with the MLP1 toolchain in:

```text
/Volumes/Storage/UMRK/mlp1-toolchain
```

Build the launcher bundle and SD payload:

```sh
cd /Volumes/Storage/UMRK/miniloong-launcher-switcher
make package
make sd-payload
```

The SD-root payload is written to:

```text
build/sd/
  loong_upgrade
  launcher_probe.bin
  umrk-launcher-install.sh
  umrk-launcher/bin/loong_pangu
```

To include the runtime marker in the generated SD directory:

```sh
make sd-payload-marked
```

Build a Jawaka-backed launcher bundle and fresh-install SD payload:

```sh
make jawaka-sd-payload
```

The Jawaka payload installs the switcher wrapper and stages:

```text
build/sd/
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
make jawaka-sd-payload-marked
```

Do not use exFAT for install media. The stock daemon ignores exFAT SD cards for
this update path.

## ADB Tests

Run the POC without installing the wrapper:

```sh
make adb-poc-test
```

This pushes the POC to `/tmp`, pauses the running stock `loong_pangu`, runs the
POC with `SDL_VIDEODRIVER=wayland`, then resumes the stock process.

Install the wrapper over ADB:

```sh
make adb-install-wrapper
```

Stage the launcher bundle on the mounted SD card and enable the marker:

```sh
make adb-stage-sd-bundle
adb shell '/etc/init.d/S50loong restart'
```

Stage the launcher bundle without activating it:

```sh
make adb-stage-sd-bundle-no-marker
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

Stage the Jawaka bundle over ADB without activating it:

```sh
make adb-stage-jawaka-sd-bundle-no-marker
```

Stage and activate the Jawaka bundle over ADB:

```sh
make adb-stage-jawaka-sd-bundle
make adb-restart-loong
```

The installed switcher wrapper has crash-loop protection. If the marker is
present and the custom launcher path is entered repeatedly within a short
window, it disables the marker and starts stock. Remount failure also disables
the marker immediately, because the direct-SD Jawaka path cannot run safely
while `/mnt/sdcard` is `noexec`.

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
/userdata/umrk-launcher-install.log
/mnt/sdcard/umrk-launcher-install.log
/userdata/umrk-launcher.log
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
