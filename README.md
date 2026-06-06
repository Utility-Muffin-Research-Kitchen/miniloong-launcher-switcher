# Miniloong Launcher Switcher

Standalone launcher replacement installer for the Miniloong Pocket 1.

This project is intentionally separate from `miniloong-adb-keeper`. It reuses
the known `loong_upgrade` SD update mechanism, and owns the payload generator,
installer, init hook, device defaults, and recovery payloads.

It does **not** build the launcher itself. The launcher payload (Jawaka binaries
plus Catastrophe/RetroArch/cores assets) is assembled and staged by the sibling
`Leaf` repo. See `Leaf` for `make stage-jawaka`, `make assemble-jawaka`, and
the end-user release ZIP targets.

## Contract

The switcher installs one early init hook and one session supervisor:

```text
/etc/init.d/S50leaf
/usr/bin/umrk-leaf-session
```

It does not replace `/loong/loong_pangu` or `/loong/loong_storage`. The legacy
direct SD installer mode still requires ADB to be pinned first by
`miniloong-adb-keeper` and refuses unless `/etc/.usb_config` is `usb_adb_en`
and immutable. Leaf's public release ZIP flow uses the managed installer mode,
which can install Leaf before ADB is pinned; Jawaka's Network settings can
enable ADB from the device UI later.

At boot, `S50leaf` runs before stock `S50loong`. If the Leaf marker and bundle
are ready, the hook blocks `rcS`, starts only the minimal Leaf-owned runtime,
and runs:

```text
UMRK_BIN_PATH/loong_pangu
```

If the marker is absent, a stock `loong_upgrade` payload is present, the SD
cannot be remounted `exec`, or the bundle is incomplete, the hook exits `0` so
stock boot continues into `S50loong`. ADB is optional for entering Leaf mode: if
Jawaka has written the Leaf ADB restore marker, the hook repairs
`/etc/.usb_config` with the immutable `usb_adb_en` pin before starting USB ADB;
otherwise it continues without USB ADB so the user can enable it from Settings.

On MLP1, if `/mnt/sdcard` does not contain the marker/bundle and
`/media/sdcard1` does, the session treats `/media/sdcard1` as the active Leaf
SD for that boot. This recovers from two-card boots where StockOS assigns the
UMRK card to the secondary mount.

Leaf mode deliberately skips stock `loong_daemon`, `loong_storage`,
`loong_service`, `loong_input`, and stock `loong_pangu`. It starts USB ADB only
when ADB is pinned, then starts PulseAudio, `loong_power`, and `loong_light`,
then Jawaka. Jawaka's
`Exit to Stock` menu item writes a tmpfs sentinel; the session cleans up
Leaf-owned processes and exits, allowing the same boot to continue into stock.

## Build an End-User Install ZIP

The preferred way to build a device installation package is from the sibling
`Leaf` repo:

```sh
cd ../Leaf
make bootstrap
make -C ../mlp1-toolchain image
make release-zips DEVICE=mlp1
```

This generates:

```text
Leaf/build/release/leaf-mlp1-sd-<release_id>.zip
Leaf/build/release/leaf-mlp1-recovery-<release_id>.zip
```

The install ZIP extracts directly to the SD-card root and installs Leaf through
the stock `loong_upgrade` path without requiring ADB first. The update screen
may sit at 50 percent while files are copying; public release payloads reboot
the device when installation or recovery completes. The installer auto-activates
Leaf after a successful managed install and does not silently enable or pin
ADB. The recovery ZIP uses the same stock update mechanism to disable Leaf and
remove the installed hook/session while preserving SD-card user content.

To choose the release id:

```sh
make release-zips DEVICE=mlp1 RELEASE_ID=2026-06-05-test1
```

Do not use exFAT for install media. The stock daemon ignores exFAT SD cards for
this update path.

## Build the Low-Level SD Payload

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
  .system/leaf/
    launcher/
      bin/loong_pangu
      bin/jawaka-launcher
      bin/jawaka-menu
      res/
    platforms/mlp1/
      manifest.json
      defaults/
```

It does not enable the runtime marker by default. To generate a marked payload
for trusted one-card activation:

```sh
make sd-payload-marked BUNDLE_ROOT=../build/stage/mlp1/package
```

This direct payload path is mostly useful for switcher development and ADB
tests. For an end-user device installation package, use Leaf's
`make release-zips DEVICE=mlp1` flow instead.

Do not use exFAT for install media. The stock daemon ignores exFAT SD cards for
this update path.

## ADB Tests

ADB deploy/control helpers live in `Leaf`. The compatibility targets in this
repo delegate there when a sibling `Leaf` checkout is available.

First apply `miniloong-adb-keeper` and verify ADB is pinned:

```sh
adb shell 'cat /etc/.usb_config; lsattr /etc/.usb_config'
```

Expected:

```text
usb_adb_en
----i...
```

Install the init hook over ADB:

```sh
make adb-install-wrapper
```

Stage the launcher bundle on the active Leaf SD card and enable the marker
(point `BUNDLE_ROOT` at the assembled payload):

```sh
make adb-stage-sd-bundle BUNDLE_ROOT=../build/stage/mlp1/package
adb reboot
```

ADB staging defaults `REMOTE_SDCARD_PATH` to `auto`. It resolves the mounted
card with `.system/leaf/platforms/mlp1/enabled` and/or
`.system/leaf/platforms/mlp1/launcher/bin/loong_pangu`, uses the only mounted SD on one-card
boots, and fails instead of guessing when two mounted cards are ambiguous. For
first-time two-card staging or an intentional override, pass
`REMOTE_SDCARD_PATH=/mnt/sdcard` or
`REMOTE_SDCARD_PATH=/media/sdcard1`.

Stage the launcher bundle without activating it:

```sh
make adb-stage-sd-bundle-no-marker BUNDLE_ROOT=../build/stage/mlp1/package
```

Toggle activation and reboot to exercise the init hook:

```sh
make adb-enable-marker
adb reboot

make adb-disable-marker
adb reboot
```

Test stock fallback by removing the marker:

```sh
scripts/adb-stage-sd-bundle.sh --no-marker
adb reboot
```

Tail switcher logs:

```sh
make adb-tail-logs
```

To stage directly from Leaf (assemble + push + activate in one step):

```sh
make -C ../Leaf stage-jawaka DEVICE=mlp1
```

The installed init hook has crash-loop protection. If the marker is present and
the custom launcher path is entered repeatedly within a short window, it
disables the marker and passes boot to stock. Remount failure also disables the
marker immediately, because the direct-SD Jawaka path cannot run safely while
the SD-card mount is `noexec`. Runtime `SDCARD_PATH` still defaults to
`/mnt/sdcard`; deploy-time `REMOTE_SDCARD_PATH` defaults to auto-resolution.

## SD Install

Copy the contents of `build/sd/` to the root of a FAT32 or ext4 SD card:

```sh
cp -R build/sd/. "/Volumes/SDCARD_NAME/"
sync
diskutil eject "/Volumes/SDCARD_NAME"
```

Boot the MLP1 with the SD inserted. The device will enter the stock update
screen while the installer runs. In the direct low-level installer mode, the
installer renames `loong_upgrade` to `loong_upgrade.used`, verifies pinned ADB,
restores any legacy UMRK `loong_pangu`/`loong_storage` wrappers, installs the
init hook/session, then returns to the stock update command path, which
intentionally sleeps forever to avoid a full upgrade attempt. Power off after
install, then boot normally.

Logs:

```text
LOGS_PATH/umrk-launcher-install-command.log
LOGS_PATH/umrk-launcher-install.log
LOGS_PATH/umrk-launcher-uninstall.log
LOGS_PATH/umrk-leaf-session.log
```

## Recovery

Over ADB:

```sh
make adb-uninstall-wrapper
adb reboot
```

Or directly:

```sh
adb shell '/usr/bin/umrk-launcher-switcher-uninstall.sh'
```

The uninstall script removes `/etc/init.d/S50leaf` and
`/usr/bin/umrk-leaf-session`. New hook installs leave stock Loong binaries
untouched. If an older UMRK install replaced `/loong/loong_pangu` or
`/loong/loong_storage`, uninstall restores them from their `.stock.umrk`
backups.
