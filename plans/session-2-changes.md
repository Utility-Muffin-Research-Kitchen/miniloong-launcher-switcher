# Session 2 Changes — Launcher Switcher

Date: 2026-05-29/30
Author: Geekstrada

## Wrapper Changes (`device/loong_pangu.wrapper`)

### loong_storage neutralization

The stock `loong_storage` daemon repeatedly remounts `/mnt/sdcard` as read-only,
breaking SQLite writes, file transfers, and app staging. `loong_daemon` respawns
`loong_storage` via `keepStorageAliveEv`, so killing it alone is not enough.

The wrapper now stops `loong_storage` on boot and replaces the binary with a
no-op sleeper script when launching the custom launcher path. The original is
preserved as `/loong/loong_storage.stock.umrk` for uninstall/recovery.

This runs only when the marker is present (custom launcher active). Stock
fallback does not touch `loong_storage`.

### platform.d boot hook support

The wrapper now executes platform boot scripts from
`/mnt/sdcard/UMRK/<platform>/platform.d/*.sh` in sorted order before launching
Jawaka. Scripts must be executable. Each script's output is appended to the
launcher log.

This provides a clean extension point for device-specific boot tasks without
modifying the wrapper itself.

### Default theme changed to Jawaka-Vertical

`Jawaka-Tabs` only displays systems that fit in the tab bar, hiding most of the
library. Changed the wrapper default to `Jawaka-Vertical` which shows all
systems in a scrollable list.

## New Files

### `device/mlp1/platform.d/01-ssh-autostart.sh`

Platform boot script that starts the Dropbear SSH server automatically if the
SSH Server app has been previously configured. Reads config from
`/userdata/umrk-ssh-server/config.ini`, uses host keys from the app's keystore,
and starts Dropbear on the configured port (default 2222).

Only runs if:
- `config.ini` exists (app was configured at least once)
- Dropbear binary is found (bundled in SSHServer.pak or on PATH)
- Host keys have been generated
- Dropbear is not already running

### `device/mlp1/defaults/systems.json` updates

Added system definitions for:
- **SEGACD** (Sega CD) — `genesis_plus_gx` core, supports bin/chd/cue/iso
- **NEOGEO** (Neo Geo) — `fbneo` core, zip/7z archives

## Jawaka Footer Hint Changes (`cmd/jawaka-launcher/main.c`, `cmd/jawaka-menu/main.c`)

### Platform-aware button text

Added `JW_HINT` and `JW_HINT_DEVICE` macros to both launcher and menu source
files. On device (`CAT_PLATFORM_IS_DEVICE`), `JW_HINT` returns NULL so
Catastrophe uses canonical button names ("A", "L2", "MENU") instead of desktop
keyboard shortcuts (";", "t", "H"). `JW_HINT_DEVICE` allows explicit
device-specific overrides (e.g. "L2/R2" for combined trigger hint).

### Combined L2/R2 tab hint

Replaced separate L2 and R2 "Tab" hints with a single combined "L2/R2 Tab"
item. Reduces footer item count and eliminates overflow on narrower views.

### Consistent footer layout

Standardized all footer blocks across all views (tabbed, vertical, horizontal,
coverflow, game browser, search, menu):

- **Left group** (`is_confirm = false`): Navigation (↑↓ or ←→), L2/R2 Tab,
  X Search, MENU Menu
- **Right group** (`is_confirm = true`): B Back, A Select/Launch — A always
  rightmost

### Footer overflow fix

Reduced tabbed non-settings footer from 6 to 4 items (dropped Menu and Rescan
which are accessible via the Menu button) to eliminate `+2` overflow on the
960px MLP1 display.

## Hardware Findings

Documented during testing, relevant for platform logic:

- **Backlight**: sysfs at `/sys/class/backlight/backlight/brightness`, range
  0-255. Usable OSD range is 25-55; below 25 = black, above 55 = no visible
  change. Direct sysfs writes conflict with `loong_power` daemon.
- **LED controller**: AW20036 at `/sys/class/leds/aw20036_led/`. Supports RGB,
  brightness, effects, imax. Only `loong_light` can drive it; direct writes
  ineffective. Only RAINBOW and BREATH modes in stock binary.
- **SD card mount**: Stock mounts as `ro,noexec`. Wrapper remounts `rw,exec`.
  `loong_storage` fights this — now neutralized.
- **USB**: ADB over Wi-Fi works (port 5555). USB gadget mode does not enumerate
  on at least one unit despite `usb_adb_en` being pinned.
- **Boot quirk**: Device won't boot when charging cable is in bottom USB-C port.
