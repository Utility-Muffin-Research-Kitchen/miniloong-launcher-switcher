#!/usr/bin/env python3
"""Generate a standalone Miniloong Pocket 1 launcher-switcher SD payload."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_VER_INNER = 2147483647
DEFAULT_OTA_FILE = "launcher_probe.bin"
DEFAULT_PROBE_CONTENT = b"miniloong launcher switcher probe\n"
INSTALLER_NAME = "umrk-launcher-install.sh"
RECOVERY_NAME = "umrk-launcher-recovery.sh"
MLP1_SDCARD_PATH = "/mnt/sdcard"
RELEASE_VERSION_RE = re.compile(
    r"[0-9]+\.[0-9]+\.[0-9]+"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)

# Platform payload entries the managed installer promotes from
# releases/<id>/platforms/<platform>/ into the active platform dir. The
# coverage check at build time fails when the staged payload contains an
# entry this list does not cover, so a new payload type cannot ship
# un-promoted (v0.0.8 stranded emulators/ this way). "launcher" is promoted
# separately as the launcher payload.
PROMOTED_PLATFORM_DIRS = (
    "bin",
    "lib",
    "cores",
    "info",
    "defaults",
    "platform.d",
    "autoconfig",
    "boot-animation",
    "emulators",
    "runtime",
    "shaders",
    "i18n",
)
PROMOTED_PLATFORM_FILES = ("manifest.json",)
COMPLETION_SLEEP = "while true; do sleep 3600; done"
COMPLETION_REBOOT = (
    "reboot -f 2>/dev/null || "
    "busybox reboot -f 2>/dev/null || "
    "/sbin/reboot -f 2>/dev/null || "
    "reboot 2>/dev/null || "
    "while true; do sleep 3600; done"
)

ROOT_DIR = Path(__file__).resolve().parent
HOOK_PATH = ROOT_DIR / "device" / "S50leaf"
SESSION_PATH = ROOT_DIR / "device" / "umrk-leaf-session"
UNINSTALLER_PATH = ROOT_DIR / "device" / "umrk-launcher-switcher-uninstall.sh"
MOUNT_STUBS_PATH = ROOT_DIR / "device" / "umrk-mount-stubs"

MASK64 = (1 << 64) - 1


def _rotl64(value: int, count: int) -> int:
    value &= MASK64
    return ((value << count) & MASK64) | (value >> (64 - count))


def _fmix64(value: int) -> int:
    value ^= value >> 33
    value = (value * 0xFF51AFD7ED558CCD) & MASK64
    value ^= value >> 33
    value = (value * 0xC4CEB9FE1A85EC53) & MASK64
    value ^= value >> 33
    return value & MASK64


def murmurhash3_x64_128_digest(data: bytes, seed: int = 42) -> bytes:
    """Return MurmurHash3_x64_128 as loong_daemon formats it."""
    c1 = 0x87C37B91114253D5
    c2 = 0x4CF5AD432745937F
    h1 = seed & MASK64
    h2 = seed & MASK64

    block_count = len(data) // 16
    for index in range(block_count):
        block = data[index * 16 : (index + 1) * 16]
        k1 = int.from_bytes(block[:8], "little")
        k2 = int.from_bytes(block[8:], "little")

        k1 = (k1 * c1) & MASK64
        k1 = _rotl64(k1, 31)
        k1 = (k1 * c2) & MASK64
        h1 ^= k1

        h1 = _rotl64(h1, 27)
        h1 = (h1 + h2) & MASK64
        h1 = (h1 * 5 + 0x52DCE729) & MASK64

        k2 = (k2 * c2) & MASK64
        k2 = _rotl64(k2, 33)
        k2 = (k2 * c1) & MASK64
        h2 ^= k2

        h2 = _rotl64(h2, 31)
        h2 = (h2 + h1) & MASK64
        h2 = (h2 * 5 + 0x38495AB5) & MASK64

    tail = data[block_count * 16 :]
    k1 = 0
    k2 = 0

    for offset, value in enumerate(tail[:8]):
        k1 ^= value << (offset * 8)
    for offset, value in enumerate(tail[8:]):
        k2 ^= value << (offset * 8)

    if k2:
        k2 = (k2 * c2) & MASK64
        k2 = _rotl64(k2, 33)
        k2 = (k2 * c1) & MASK64
        h2 ^= k2

    if k1:
        k1 = (k1 * c1) & MASK64
        k1 = _rotl64(k1, 31)
        k1 = (k1 * c2) & MASK64
        h1 ^= k1

    length = len(data)
    h1 ^= length
    h2 ^= length

    h1 = (h1 + h2) & MASK64
    h2 = (h2 + h1) & MASK64

    h1 = _fmix64(h1)
    h2 = _fmix64(h2)

    h1 = (h1 + h2) & MASK64
    h2 = (h2 + h1) & MASK64

    return h1.to_bytes(8, "little") + h2.to_bytes(8, "little")


def loong_upgrade_hash(ver_inner: int, ota_file: str, ota_size: int) -> tuple[str, str]:
    hash_input = f"{ver_inner}{MLP1_SDCARD_PATH}/{ota_file}{ota_size}"
    digest = murmurhash3_x64_128_digest(hash_input.encode("utf-8"), seed=42)
    return digest.hex().upper(), hash_input


def shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def completion_command(action: str) -> str:
    if action == "sleep":
        return COMPLETION_SLEEP
    if action == "reboot":
        return COMPLETION_REBOOT
    raise SystemExit(f"unsupported completion action: {action}")


def read_required(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"missing required file: {path}")
    return path.read_text(encoding="utf-8")


def validate_release_id(value: str) -> None:
    if not value or value in {".", ".."}:
        raise SystemExit(f"unsafe --release-id value: {value!r}")
    if "/" in value or "\\" in value:
        raise SystemExit("--release-id must be a simple directory name, not a path")
    if any(ch.isspace() for ch in value):
        raise SystemExit("--release-id must not contain whitespace")
    if any(ch in ':*?"<>|' or ord(ch) < 32 for ch in value):
        raise SystemExit("--release-id contains characters unsafe for FAT32")


def validate_release_version(value: str) -> None:
    if not RELEASE_VERSION_RE.fullmatch(value or ""):
        raise SystemExit(
            "--release-version must be a semantic version such as 0.7.0 "
            "or 0.7.0-save-isolation-ota1"
        )
    if any(int(part) > 9999 for part in value.split("-", 1)[0].split("+", 1)[0].split(".")):
        raise SystemExit("--release-version component exceeds 9999")


def build_installer_script(require_adb_pinned: bool = True) -> str:
    hook = read_required(HOOK_PATH).rstrip()
    session = read_required(SESSION_PATH).rstrip()
    uninstaller = read_required(UNINSTALLER_PATH).rstrip()
    mount_stubs = read_required(MOUNT_STUBS_PATH).rstrip()
    adb_preflight = (
        "assert_adb_pinned"
        if require_adb_pinned
        else 'log_msg "ADB pinned preflight skipped"'
    )
    template = """#!/bin/sh
set -u

PLATFORM="${PLATFORM:-mlp1}"
SDCARD_PATH="${SDCARD_PATH:-__MLP1_SDCARD_PATH__}"
SYSTEM_ROOT="$SDCARD_PATH/.system/leaf"
PLATFORM_ROOT="$SYSTEM_ROOT/platforms/$PLATFORM"
USERDATA_PATH="${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}"
LOGS_PATH="${LOGS_PATH:-$USERDATA_PATH/logs}"
INTERNAL_DATA="${UMRK_INTERNAL_DATA_PATH:-$SDCARD_PATH/.umrk/$PLATFORM}"
LOG="$LOGS_PATH/umrk-launcher-install.log"
PANGU=/loong/loong_pangu
PANGU_BACKUP=/loong/loong_pangu.stock.umrk
STORAGE=/loong/loong_storage
STORAGE_BACKUP=/loong/loong_storage.stock.umrk
HOOK=/etc/init.d/S50leaf
SESSION=/usr/bin/umrk-leaf-session
HOOK_TMP=/tmp/S50leaf.umrk.$$
SESSION_TMP=/tmp/umrk-leaf-session.$$
UNINSTALL=/usr/bin/umrk-launcher-switcher-uninstall.sh
UNINSTALL_TMP=/tmp/umrk-launcher-switcher-uninstall.$$
MOUNT_STUBS=/usr/bin/umrk-mount-stubs
MOUNT_STUBS_TMP=/tmp/umrk-mount-stubs.$$

log_msg() {
    mkdir -p "$LOGS_PATH" "$INTERNAL_DATA" 2>/dev/null || true
    printf '[%s] %s\\n' "$(date '+%F %T' 2>/dev/null || echo unknown)" "$*" >>"$LOG" 2>/dev/null || true
}

cleanup_stock_payloads() {
    for root in /mnt/sdcard /media/sdcard1 "$SDCARD_PATH"; do
        [ -n "$root" ] && [ -d "$root" ] || continue
        if [ -e "$root/loong_upgrade" ]; then
            mv "$root/loong_upgrade" "$root/loong_upgrade.used" 2>/dev/null ||
                rm -f "$root/loong_upgrade" 2>/dev/null || true
        fi
        rm -f "$root/launcher_probe.bin" "$root/umrk-launcher-install.sh" 2>/dev/null || true
    done
}

fail() {
    log_msg "$*"
    cleanup_stock_payloads
    echo "$*" >&2
    exit 1
}

remount_root_rw() {
    if mount -o remount,rw / 2>>"$LOG" ||
       mount -o remount,rw /dev/root / 2>>"$LOG"; then
        log_msg "rootfs remounted rw"
        return 0
    fi
    return 1
}

assert_adb_pinned() {
    [ -x /usr/bin/adbd ] || fail "ADB support missing: /usr/bin/adbd"
    [ -x /etc/init.d/S50usb-gadget.sh ] || fail "ADB support missing: /etc/init.d/S50usb-gadget.sh"
    [ -f /etc/.usb_config ] || fail "ADB config missing: /etc/.usb_config"

    cfg="$(cat /etc/.usb_config 2>/dev/null | tr -d '\\r\\n')"
    [ "$cfg" = "usb_adb_en" ] || fail "ADB not pinned: /etc/.usb_config=$cfg"

    attrs="$(lsattr /etc/.usb_config 2>/dev/null | awk '{print $1; exit}')"
    case "$attrs" in
        *i*) ;;
        *) fail "ADB config is not immutable: $attrs" ;;
    esac
    log_msg "ADB pinned preflight passed"
}

is_old_umrk_pangu_wrapper() {
    [ -f "$PANGU" ] && grep -q "UMRK_LAUNCHER_SWITCHER_WRAPPER=1" "$PANGU" 2>/dev/null
}

is_umrk_noop_storage() {
    [ -f "$STORAGE" ] && grep -q "umrk-noop" "$STORAGE" 2>/dev/null
}

restore_old_pangu_wrapper() {
    if ! is_old_umrk_pangu_wrapper; then
        [ -x "$PANGU" ] || [ -f "$PANGU_BACKUP" ] || fail "stock pangu missing: $PANGU"
        return 0
    fi

    [ -f "$PANGU_BACKUP" ] || fail "old pangu wrapper present but backup missing: $PANGU_BACKUP"
    cp -p "$PANGU_BACKUP" "$PANGU" || fail "failed to restore stock pangu"
    chmod 755 "$PANGU" 2>/dev/null || true
    log_msg "restored stock pangu from legacy wrapper backup"
}

restore_old_storage_noop() {
    if ! is_umrk_noop_storage; then
        return 0
    fi

    [ -f "$STORAGE_BACKUP" ] || fail "old storage noop present but backup missing: $STORAGE_BACKUP"
    cp -p "$STORAGE_BACKUP" "$STORAGE" || fail "failed to restore stock storage"
    chmod 0775 "$STORAGE" 2>/dev/null || chmod 755 "$STORAGE" 2>/dev/null || true
    if pidof loong_storage >/dev/null 2>&1; then
        killall loong_storage 2>/dev/null || true
        sleep 1
    fi
    log_msg "restored stock storage from legacy noop backup"
}

log_msg "launcher switcher installer starting"
__ADB_PREFLIGHT__
remount_root_rw || fail "rootfs remount rw failed"
mv "$SDCARD_PATH/loong_upgrade" "$SDCARD_PATH/loong_upgrade.used" 2>/dev/null || true
restore_old_pangu_wrapper
restore_old_storage_noop

cat > "$HOOK_TMP" <<'UMRK_LEAF_HOOK_EOF'
__HOOK__
UMRK_LEAF_HOOK_EOF

cat > "$SESSION_TMP" <<'UMRK_LEAF_SESSION_EOF'
__SESSION__
UMRK_LEAF_SESSION_EOF

cat > "$UNINSTALL_TMP" <<'UMRK_LAUNCHER_UNINSTALL_EOF'
__UNINSTALLER__
UMRK_LAUNCHER_UNINSTALL_EOF

cat > "$MOUNT_STUBS_TMP" <<'UMRK_MOUNT_STUBS_EOF'
__MOUNT_STUBS__
UMRK_MOUNT_STUBS_EOF

chmod 755 "$HOOK_TMP" "$SESSION_TMP" "$UNINSTALL_TMP" "$MOUNT_STUBS_TMP" || fail "failed to chmod install files"
mv "$HOOK_TMP" "$HOOK" || fail "failed to install init hook"
mv "$SESSION_TMP" "$SESSION" || fail "failed to install Leaf session"
mv "$UNINSTALL_TMP" "$UNINSTALL" || fail "failed to install uninstaller"
mv "$MOUNT_STUBS_TMP" "$MOUNT_STUBS" || fail "failed to install mount-stub helper"
chmod 755 "$HOOK" "$SESSION" "$UNINSTALL" "$MOUNT_STUBS" 2>/dev/null || true
"$MOUNT_STUBS" lock || fail "failed to protect rootfs mount stubs"
touch "$INTERNAL_DATA/umrk_launcher_switcher_installed" 2>/dev/null || true
sync

log_msg "installed launcher switcher init hook"
echo "installed launcher switcher init hook"
"""
    return (
        template
        .replace("__MLP1_SDCARD_PATH__", MLP1_SDCARD_PATH)
        .replace("__ADB_PREFLIGHT__", adb_preflight)
        .replace("__HOOK__", hook)
        .replace("__SESSION__", session)
        .replace("__UNINSTALLER__", uninstaller)
        .replace("__MOUNT_STUBS__", mount_stubs)
    )


def validate_platform_payload_coverage(sd_root: Path, release_id: str,
                                       platform: str = "mlp1") -> None:
    """Fail the build when the staged release platform payload contains an
    entry the generated installer would not promote. Without this, a new
    payload directory ships in the ZIP but never reaches the active platform
    dir on install (how v0.0.8 stranded emulators/)."""
    payload = sd_root / ".system/leaf/releases" / release_id / "platforms" / platform
    if not payload.is_dir():
        return
    known = set(PROMOTED_PLATFORM_DIRS) | set(PROMOTED_PLATFORM_FILES) | {"launcher"}
    unknown = sorted(entry.name for entry in payload.iterdir()
                     if entry.name not in known)
    if unknown:
        raise SystemExit(
            "error: release platform payload contains entries the installer "
            f"does not promote: {' '.join(unknown)} "
            "(add them to PROMOTED_PLATFORM_DIRS/FILES in make_launcher_switcher_sd.py)")


def build_managed_installer_script(
    release_id: str, release_version: str | None = None
) -> str:
    validate_release_id(release_id)
    if release_version is None:
        release_version = release_id
    else:
        validate_release_version(release_version)
    hook = read_required(HOOK_PATH).rstrip()
    session = read_required(SESSION_PATH).rstrip()
    uninstaller = read_required(UNINSTALLER_PATH).rstrip()
    mount_stubs = read_required(MOUNT_STUBS_PATH).rstrip()
    template = """#!/bin/sh
set -u

PLATFORM="${PLATFORM:-mlp1}"
RELEASE_ID="__RELEASE_ID__"
RELEASE_VERSION="__RELEASE_VERSION__"
REQUESTED_SDCARD_PATH="${SDCARD_PATH:-__MLP1_SDCARD_PATH__}"

resolve_sdcard_path() {
    fallback=""
    for candidate in "$REQUESTED_SDCARD_PATH" /mnt/sdcard /media/sdcard1; do
        [ -n "$candidate" ] || continue
        [ -d "$candidate/.system/leaf/releases/$RELEASE_ID/platforms/$PLATFORM/launcher" ] || continue
        if [ -e "$candidate/.system/leaf/platforms/$PLATFORM/enabled" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
        [ -n "$fallback" ] || fallback="$candidate"
    done
    [ -n "$fallback" ] && printf '%s\n' "$fallback" && return 0
    printf '%s\n' "$REQUESTED_SDCARD_PATH"
}

SDCARD_PATH="$(resolve_sdcard_path)"
SYSTEM_ROOT="$SDCARD_PATH/.system/leaf"
RELEASE_ROOT="$SYSTEM_ROOT/releases/$RELEASE_ID"
RELEASE_PLATFORM="$RELEASE_ROOT/platforms/$PLATFORM"
RELEASE_LAUNCHER="$RELEASE_PLATFORM/launcher"
RELEASE_APPS="$RELEASE_ROOT/Apps"
MANAGED_APPS="$RELEASE_ROOT/managed-apps.txt"
ACTIVE_PLATFORM="$SYSTEM_ROOT/platforms/$PLATFORM"
ACTIVE_LAUNCHER="$ACTIVE_PLATFORM/launcher"
APPS_ROOT="$SDCARD_PATH/Apps"
USERDATA_PATH="${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}"
SHARED_USERDATA_PATH="${SHARED_USERDATA_PATH:-$SDCARD_PATH/.userdata/shared}"
LOGS_PATH="${LOGS_PATH:-$USERDATA_PATH/logs}"
INTERNAL_DATA="${UMRK_INTERNAL_DATA_PATH:-$SDCARD_PATH/.umrk/$PLATFORM}"
USER_SHADERS="${UMRK_RETROARCH_USER_SHADERS_DIR:-$INTERNAL_DATA/retroarch/.config/retroarch/shaders}"
MARKER="${UMRK_MARKER_PATH:-$ACTIVE_PLATFORM/enabled}"
LOG="$LOGS_PATH/umrk-launcher-install.log"
PANGU=/loong/loong_pangu
PANGU_BACKUP=/loong/loong_pangu.stock.umrk
STORAGE=/loong/loong_storage
STORAGE_BACKUP=/loong/loong_storage.stock.umrk
HOOK=/etc/init.d/S50leaf
SESSION=/usr/bin/umrk-leaf-session
HOOK_TMP=/tmp/S50leaf.umrk.$$
SESSION_TMP=/tmp/umrk-leaf-session.$$
UNINSTALL=/usr/bin/umrk-launcher-switcher-uninstall.sh
UNINSTALL_TMP=/tmp/umrk-launcher-switcher-uninstall.$$
MOUNT_STUBS=/usr/bin/umrk-mount-stubs
MOUNT_STUBS_TMP=/tmp/umrk-mount-stubs.$$

log_msg() {
    mkdir -p "$LOGS_PATH" "$INTERNAL_DATA" 2>/dev/null || true
    printf '[%s] %s\\n' "$(date '+%F %T' 2>/dev/null || echo unknown)" "$*" >>"$LOG" 2>/dev/null || true
}

cleanup_stock_payloads() {
    for root in /mnt/sdcard /media/sdcard1 "$SDCARD_PATH"; do
        [ -n "$root" ] && [ -d "$root" ] || continue
        if [ -e "$root/loong_upgrade" ]; then
            mv "$root/loong_upgrade" "$root/loong_upgrade.used" 2>/dev/null ||
                rm -f "$root/loong_upgrade" 2>/dev/null || true
        fi
        rm -f "$root/launcher_probe.bin" "$root/umrk-launcher-install.sh" 2>/dev/null || true
    done
}

fail() {
    log_msg "$*"
    cleanup_stock_payloads
    echo "$*" >&2
    exit 1
}

remount_root_rw() {
    if mount -o remount,rw / 2>>"$LOG" ||
       mount -o remount,rw /dev/root / 2>>"$LOG"; then
        log_msg "rootfs remounted rw"
        return 0
    fi
    return 1
}

is_old_umrk_pangu_wrapper() {
    [ -f "$PANGU" ] && grep -q "UMRK_LAUNCHER_SWITCHER_WRAPPER=1" "$PANGU" 2>/dev/null
}

is_umrk_noop_storage() {
    [ -f "$STORAGE" ] && grep -q "umrk-noop" "$STORAGE" 2>/dev/null
}

restore_old_pangu_wrapper() {
    if ! is_old_umrk_pangu_wrapper; then
        [ -x "$PANGU" ] || [ -f "$PANGU_BACKUP" ] || fail "stock pangu missing: $PANGU"
        return 0
    fi

    [ -f "$PANGU_BACKUP" ] || fail "old pangu wrapper present but backup missing: $PANGU_BACKUP"
    cp -p "$PANGU_BACKUP" "$PANGU" || fail "failed to restore stock pangu"
    chmod 755 "$PANGU" 2>/dev/null || true
    log_msg "restored stock pangu from legacy wrapper backup"
}

restore_old_storage_noop() {
    if ! is_umrk_noop_storage; then
        return 0
    fi

    [ -f "$STORAGE_BACKUP" ] || fail "old storage noop present but backup missing: $STORAGE_BACKUP"
    cp -p "$STORAGE_BACKUP" "$STORAGE" || fail "failed to restore stock storage"
    chmod 0775 "$STORAGE" 2>/dev/null || chmod 755 "$STORAGE" 2>/dev/null || true
    if pidof loong_storage >/dev/null 2>&1; then
        killall loong_storage 2>/dev/null || true
        sleep 1
    fi
    log_msg "restored stock storage from legacy noop backup"
}

validate_release() {
    [ -d "$RELEASE_ROOT" ] || fail "missing release root: $RELEASE_ROOT"
    for bin in \
        "$RELEASE_LAUNCHER/bin/loong_pangu" \
        "$RELEASE_LAUNCHER/bin/jawaka-launcher" \
        "$RELEASE_LAUNCHER/bin/jawaka-menu"; do
        [ -f "$bin" ] || fail "missing release launcher binary: $bin"
    done
    [ -f "$RELEASE_LAUNCHER/res/font.ttf" ] || fail "missing release font"
    [ -d "$RELEASE_LAUNCHER/res/themes" ] || fail "missing release themes"
    [ -d "$RELEASE_LAUNCHER/res/assets" ] || fail "missing release status assets"
    [ -d "$RELEASE_PLATFORM" ] || fail "missing release platform: $RELEASE_PLATFORM"
}

replace_dir() {
    src="$1"
    dst="$2"
    tmp="$dst.tmp.$$"
    parent="${dst%/*}"

    [ -d "$src" ] || fail "missing source directory: $src"
    mkdir -p "$parent" || fail "failed to create parent: $parent"
    rm -rf "$tmp" 2>/dev/null || true
    mv "$src" "$tmp" || fail "failed to stage $src as $tmp"
    rm -rf "$dst" || fail "failed to remove old directory: $dst"
    mv "$tmp" "$dst" || fail "failed to promote $tmp to $dst"
}

replace_file() {
    src="$1"
    dst="$2"
    tmp="$dst.tmp.$$"
    parent="${dst%/*}"

    [ -f "$src" ] || fail "missing source file: $src"
    mkdir -p "$parent" || fail "failed to create parent: $parent"
    rm -f "$tmp" 2>/dev/null || true
    mv "$src" "$tmp" || fail "failed to stage $src as $tmp"
    rm -f "$dst" || fail "failed to remove old file: $dst"
    mv "$tmp" "$dst" || fail "failed to promote $tmp to $dst"
}

migrate_legacy_downloaded_shaders() {
    legacy="$ACTIVE_PLATFORM/shaders/shaders_glsl"
    downloaded="$USER_SHADERS/shaders_glsl"
    [ -d "$legacy" ] || return 0
    [ ! -e "$downloaded" ] || return 0

    preset_count="$(find "$legacy" -type f -name '*.glslp' 2>/dev/null |
        wc -l | tr -d ' ')"
    case "$preset_count" in
        ''|*[!0-9]*) return 0 ;;
    esac
    # The former Leaf bundle had 11 standard presets in shaders_glsl. A larger
    # tree was populated by RetroArch's online updater and belongs to the user.
    [ "$preset_count" -gt 11 ] || return 0

    mkdir -p "$USER_SHADERS" || fail "failed to create user shader root"
    tmp="$downloaded.tmp.$$"
    rm -rf "$tmp" 2>/dev/null || true
    cp -R "$legacy" "$tmp" ||
        fail "failed to preserve legacy updater shader collection"
    mv "$tmp" "$downloaded" ||
        fail "failed to promote preserved updater shader collection"
    log_msg "preserved $preset_count legacy updater shader presets"
}

sync_leaf_shaders() {
    source_root="$ACTIVE_PLATFORM/shaders"
    [ -d "$source_root" ] || return 0
    [ -d "$source_root/leaf-bundled" ] ||
        fail "release shader bundle lacks leaf-bundled"
    [ -d "$source_root/leaf-recommended" ] ||
        fail "release shader bundle lacks leaf-recommended"
    mkdir -p "$USER_SHADERS/custom" ||
        fail "failed to create durable user shader directories"

    for namespace in leaf-bundled leaf-recommended; do
        src="$source_root/$namespace"
        dst="$USER_SHADERS/$namespace"
        tmp="$dst.tmp.$$"
        previous="$dst.previous.$$"
        rm -rf "$tmp" "$previous" 2>/dev/null || true
        cp -R "$src" "$tmp" ||
            fail "failed to stage $namespace shaders"
        if [ -e "$dst" ]; then
            mv "$dst" "$previous" ||
                fail "failed to back up $namespace shaders"
        fi
        if ! mv "$tmp" "$dst"; then
            [ ! -e "$previous" ] || mv "$previous" "$dst" 2>/dev/null || true
            fail "failed to promote $namespace shaders"
        fi
        rm -rf "$previous" 2>/dev/null || true
    done
    log_msg "synchronized Leaf shader namespaces to durable user state"
}

install_runtime_files() {
    cat > "$HOOK_TMP" <<'UMRK_LEAF_HOOK_EOF'
__HOOK__
UMRK_LEAF_HOOK_EOF

    cat > "$SESSION_TMP" <<'UMRK_LEAF_SESSION_EOF'
__SESSION__
UMRK_LEAF_SESSION_EOF

    cat > "$UNINSTALL_TMP" <<'UMRK_LAUNCHER_UNINSTALL_EOF'
__UNINSTALLER__
UMRK_LAUNCHER_UNINSTALL_EOF

    cat > "$MOUNT_STUBS_TMP" <<'UMRK_MOUNT_STUBS_EOF'
__MOUNT_STUBS__
UMRK_MOUNT_STUBS_EOF

    chmod 755 "$HOOK_TMP" "$SESSION_TMP" "$UNINSTALL_TMP" "$MOUNT_STUBS_TMP" || fail "failed to chmod install files"
    mv "$HOOK_TMP" "$HOOK" || fail "failed to install init hook"
    mv "$SESSION_TMP" "$SESSION" || fail "failed to install Leaf session"
    mv "$UNINSTALL_TMP" "$UNINSTALL" || fail "failed to install uninstaller"
    mv "$MOUNT_STUBS_TMP" "$MOUNT_STUBS" || fail "failed to install mount-stub helper"
    chmod 755 "$HOOK" "$SESSION" "$UNINSTALL" "$MOUNT_STUBS" 2>/dev/null || true
}

promote_managed_apps() {
    [ -f "$MANAGED_APPS" ] || return 0
    mkdir -p "$APPS_ROOT" || fail "failed to create apps root: $APPS_ROOT"

    while IFS= read -r app || [ -n "$app" ]; do
        case "$app" in
            ''|\\#*) continue ;;
            *\\\\*|/*|*//*|.|..) fail "unsafe managed app path: $app" ;;
        esac
        platform_dir="${app%%/*}"
        app_name="${app#*/}"
        if [ "$platform_dir" = "$app" ] || [ -z "$platform_dir" ] || [ -z "$app_name" ]; then
            fail "managed app path must be <platform>/<pak>: $app"
        fi
        case "$platform_dir" in
            .|..|.*|*/*) fail "unsafe managed app platform: $app" ;;
        esac
        case "$app_name" in
            .|..|.*|*/*) fail "unsafe managed app name: $app" ;;
        esac
        replace_dir "$RELEASE_APPS/$app" "$APPS_ROOT/$app"
        chmod 755 "$APPS_ROOT/$app/launch.sh" "$APPS_ROOT/$app/bin/"* 2>/dev/null || true
        log_msg "promoted managed app: $app"
    done < "$MANAGED_APPS"
}

write_release_json() {
    tmp="$INTERNAL_DATA/release.json.tmp.$$"
    installed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date '+%F %T' 2>/dev/null || echo unknown)"
    cat > "$tmp" <<EOF
{
  "schema": 1,
  "product": "leaf",
  "platform": "$PLATFORM",
  "version": "$RELEASE_VERSION",
  "release_id": "$RELEASE_ID",
  "installed_at": "$installed_at",
  "source": "managed-install"
}
EOF
    mv "$tmp" "$INTERNAL_DATA/release.json" || fail "failed to write release metadata"
}

create_public_dirs() {
    pubfile="$RELEASE_ROOT/public-dirs.txt"
    [ -f "$pubfile" ] || return 0
    while IFS= read -r pubdir || [ -n "$pubdir" ]; do
        case "$pubdir" in
            ''|\\#*) continue ;;
            */*|*..*) continue ;;
        esac
        [ -d "$SDCARD_PATH/$pubdir" ] || mkdir -p "$SDCARD_PATH/$pubdir" 2>/dev/null || true
    done < "$pubfile"
    log_msg "ensured public content roots from public-dirs.txt"
}

log_msg "managed Leaf installer starting release=$RELEASE_ID sdcard=$SDCARD_PATH requested=$REQUESTED_SDCARD_PATH"
for root in /mnt/sdcard /media/sdcard1 "$SDCARD_PATH"; do
    [ -n "$root" ] && [ -d "$root" ] || continue
    mv "$root/loong_upgrade" "$root/loong_upgrade.used" 2>/dev/null || true
done
mkdir -p "$SYSTEM_ROOT" "$ACTIVE_PLATFORM" 2>/dev/null || true
# The durable data roots MUST exist and be writable, or the install would silently
# come up with no persistent user/app data or launcher control state. Fail the
# install here (before the marker is enabled) rather than swallowing the error.
mkdir -p "$USERDATA_PATH" "$SHARED_USERDATA_PATH" "$LOGS_PATH" "$INTERNAL_DATA" \
    || fail "could not create data roots ($USERDATA_PATH, $INTERNAL_DATA)"
for _d in "$USERDATA_PATH" "$INTERNAL_DATA"; do
    if ( : >"$_d/.umrk-writetest" ) 2>/dev/null; then
        rm -f "$_d/.umrk-writetest" 2>/dev/null || true
    else
        fail "data root not writable: $_d"
    fi
done
rm -f "$MARKER" 2>/dev/null || true
rm -rf "$ACTIVE_LAUNCHER".tmp.* "$ACTIVE_PLATFORM"/*.tmp.* 2>/dev/null || true

remount_root_rw || fail "rootfs remount rw failed"
validate_release
restore_old_pangu_wrapper
restore_old_storage_noop
install_runtime_files
"$MOUNT_STUBS" lock || fail "failed to protect rootfs mount stubs"

log_msg "promoting launcher payload"
replace_dir "$RELEASE_LAUNCHER" "$ACTIVE_LAUNCHER"
mkdir -p "$ACTIVE_PLATFORM" || fail "failed to create active platform root"
migrate_legacy_downloaded_shaders
log_msg "promoting platform payload"
for payload_entry in __PROMOTED_DIRS__ __PROMOTED_FILES__; do
    rm -rf "$ACTIVE_PLATFORM/$payload_entry" 2>/dev/null || true
done
for payload_dir in __PROMOTED_DIRS__; do
    if [ -d "$RELEASE_PLATFORM/$payload_dir" ]; then
        replace_dir "$RELEASE_PLATFORM/$payload_dir" "$ACTIVE_PLATFORM/$payload_dir"
    fi
done
for payload_file in __PROMOTED_FILES__; do
    if [ -f "$RELEASE_PLATFORM/$payload_file" ]; then
        replace_file "$RELEASE_PLATFORM/$payload_file" "$ACTIVE_PLATFORM/$payload_file"
    fi
done
chmod 755 "$ACTIVE_LAUNCHER/bin/"* 2>/dev/null || true
chmod 755 "$ACTIVE_PLATFORM/bin/retroarch" "$ACTIVE_PLATFORM/cores/"*_libretro.so 2>/dev/null || true
if [ -d "$ACTIVE_PLATFORM/emulators" ]; then
    chmod -R 755 "$ACTIVE_PLATFORM/emulators" 2>/dev/null || true
fi
if [ -d "$ACTIVE_PLATFORM/platform.d" ]; then
    find "$ACTIVE_PLATFORM/platform.d" -type f -exec chmod 755 {} \\; 2>/dev/null || true
fi
sync_leaf_shaders
log_msg "promoting managed apps"
promote_managed_apps
create_public_dirs

write_release_json
touch "$INTERNAL_DATA/umrk_launcher_switcher_installed" 2>/dev/null || true
touch "$INTERNAL_DATA/release-$RELEASE_ID-installed" 2>/dev/null || true
log_msg "enabling Leaf marker"
touch "$MARKER" || fail "failed to enable Leaf marker"
cleanup_stock_payloads
sync

log_msg "managed Leaf install complete release=$RELEASE_ID"
echo "managed Leaf install complete"
"""
    return (
        template
        .replace("__MLP1_SDCARD_PATH__", MLP1_SDCARD_PATH)
        .replace("__RELEASE_ID__", release_id)
        .replace("__RELEASE_VERSION__", release_version)
        .replace("__PROMOTED_DIRS__", " ".join(PROMOTED_PLATFORM_DIRS))
        .replace("__PROMOTED_FILES__", " ".join(PROMOTED_PLATFORM_FILES))
        .replace("__HOOK__", hook)
        .replace("__SESSION__", session)
        .replace("__UNINSTALLER__", uninstaller)
        .replace("__MOUNT_STUBS__", mount_stubs)
    )


def build_recovery_script() -> str:
    template = """#!/bin/sh
set -u

PLATFORM="${PLATFORM:-mlp1}"
SDCARD_PATH="${SDCARD_PATH:-__MLP1_SDCARD_PATH__}"
SYSTEM_ROOT="$SDCARD_PATH/.system/leaf"
PLATFORM_ROOT="$SYSTEM_ROOT/platforms/$PLATFORM"
USERDATA_PATH="${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}"
LOGS_PATH="${LOGS_PATH:-$USERDATA_PATH/logs}"
INTERNAL_DATA="${UMRK_INTERNAL_DATA_PATH:-$SDCARD_PATH/.umrk/$PLATFORM}"
MARKER="${UMRK_MARKER_PATH:-$PLATFORM_ROOT/enabled}"
LOG="$LOGS_PATH/umrk-launcher-recovery.log"
HOOK=/etc/init.d/S50leaf
SESSION=/usr/bin/umrk-leaf-session
UNINSTALL=/usr/bin/umrk-launcher-switcher-uninstall.sh

log_msg() {
    mkdir -p "$LOGS_PATH" "$INTERNAL_DATA" 2>/dev/null || true
    printf '[%s] %s\\n' "$(date '+%F %T' 2>/dev/null || echo unknown)" "$*" >>"$LOG" 2>/dev/null || true
}

remount_root_rw() {
    mount -o remount,rw / 2>>"$LOG" && return 0
    mount -o remount,rw /dev/root / 2>>"$LOG"
}

log_msg "Leaf recovery starting"
mv "$SDCARD_PATH/loong_upgrade" "$SDCARD_PATH/loong_upgrade.used" 2>/dev/null || true
rm -f "$MARKER" 2>/dev/null || true
if ! remount_root_rw; then
    log_msg "rootfs remount rw failed"
fi

if [ -x "$UNINSTALL" ]; then
    "$UNINSTALL" >>"$LOG" 2>&1 || log_msg "installed uninstaller returned failure"
fi

rm -f "$HOOK" "$SESSION" "$UNINSTALL" 2>/dev/null || true
sync

log_msg "Leaf recovery complete"
echo "Leaf recovery complete"
"""
    return template.replace("__MLP1_SDCARD_PATH__", MLP1_SDCARD_PATH)


def install_command(completion_action: str = "sleep") -> str:
    completion = completion_command(completion_action)
    return (
        f"SDCARD_PATH={MLP1_SDCARD_PATH}; "
        "PLATFORM=${PLATFORM:-mlp1}; "
        "INSTALLER_ROOT=; "
        "for candidate in $SDCARD_PATH /mnt/sdcard /media/sdcard1; do "
        f"[ -f \"$candidate/{INSTALLER_NAME}\" ] || continue; "
        "INSTALLER_ROOT=$candidate; break; "
        "done; "
        "[ -n \"$INSTALLER_ROOT\" ] || INSTALLER_ROOT=$SDCARD_PATH; "
        "SYSTEM_ROOT=$SDCARD_PATH/.system/leaf; "
        "PLATFORM_ROOT=$SYSTEM_ROOT/platforms/$PLATFORM; "
        "USERDATA_PATH=${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}; "
        "LOGS_PATH=${LOGS_PATH:-$USERDATA_PATH/logs}; "
        "mkdir -p $LOGS_PATH 2>/dev/null || true; "
        "INSTALL_LOG=$LOGS_PATH/umrk-launcher-install-command.log; "
        "printf 'launcher switcher otaCommand started\\n' >$INSTALL_LOG 2>/dev/null || true; "
        f"SDCARD_PATH=$INSTALLER_ROOT sh $INSTALLER_ROOT/{INSTALLER_NAME} >>$INSTALL_LOG 2>&1; "
        "printf 'launcher switcher installer returned\\n' >>$INSTALL_LOG 2>/dev/null || true; "
        "sync; "
        f"{completion}"
    )


def recovery_command(completion_action: str = "sleep") -> str:
    completion = completion_command(completion_action)
    return (
        f"SDCARD_PATH={MLP1_SDCARD_PATH}; "
        "PLATFORM=${PLATFORM:-mlp1}; "
        "SYSTEM_ROOT=$SDCARD_PATH/.system/leaf; "
        "PLATFORM_ROOT=$SYSTEM_ROOT/platforms/$PLATFORM; "
        "USERDATA_PATH=${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}; "
        "LOGS_PATH=${LOGS_PATH:-$USERDATA_PATH/logs}; "
        "mkdir -p $LOGS_PATH 2>/dev/null || true; "
        "RECOVERY_LOG=$LOGS_PATH/umrk-launcher-recovery-command.log; "
        "printf 'launcher switcher recovery otaCommand started\\n' >$RECOVERY_LOG 2>/dev/null || true; "
        f"sh $SDCARD_PATH/{RECOVERY_NAME} >>$RECOVERY_LOG 2>&1; "
        "printf 'launcher switcher recovery returned\\n' >>$RECOVERY_LOG 2>/dev/null || true; "
        "sync; "
        f"{completion}"
    )


def probe_command() -> str:
    return (
        f"SDCARD_PATH={MLP1_SDCARD_PATH}; "
        "PLATFORM=${PLATFORM:-mlp1}; "
        "SYSTEM_ROOT=$SDCARD_PATH/.system/leaf; "
        "PLATFORM_ROOT=$SYSTEM_ROOT/platforms/$PLATFORM; "
        "USERDATA_PATH=${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}; "
        "LOGS_PATH=${LOGS_PATH:-$USERDATA_PATH/logs}; "
        "INTERNAL_DATA=${UMRK_INTERNAL_DATA_PATH:-$SDCARD_PATH/.umrk/$PLATFORM}; "
        "mkdir -p $LOGS_PATH $INTERNAL_DATA 2>/dev/null || true; "
        "LOG=$LOGS_PATH/umrk-launcher-probe.log; "
        "printf 'launcher switcher probe started\\n' >$LOG 2>/dev/null || true; "
        "touch $INTERNAL_DATA/umrk_launcher_probe_started 2>/dev/null || true; "
        "mv $SDCARD_PATH/loong_upgrade $SDCARD_PATH/loong_upgrade.used 2>/dev/null || true; "
        "sync; "
        "while true; do sleep 3600; done"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate standalone SD-root files for the MLP1 launcher switcher."
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="launcher_switcher_sd",
        help="Directory to write SD-root payload files into.",
    )
    parser.add_argument(
        "--mode",
        choices=("install", "managed-install", "probe", "recovery"),
        default="install",
        help="Payload command mode. Defaults to install.",
    )
    parser.add_argument(
        "--release-id",
        default=None,
        help="Leaf release id to promote in managed-install mode.",
    )
    parser.add_argument(
        "--release-version",
        default=None,
        help=(
            "Semantic Leaf version written to release.json in managed-install "
            "mode. Defaults to --release-id for compatibility."
        ),
    )
    parser.add_argument(
        "--no-require-adb-pinned",
        action="store_true",
        help="Skip the ADB-pinned preflight for installer generation.",
    )
    parser.add_argument(
        "--completion-action",
        choices=("sleep", "reboot"),
        default="sleep",
        help="What otaCommand does after the script returns. Defaults to sleep.",
    )
    parser.add_argument(
        "--ver-inner",
        type=int,
        default=DEFAULT_VER_INNER,
        help=f"Firmware internal version to declare. Defaults to {DEFAULT_VER_INNER}.",
    )
    parser.add_argument(
        "--ota-file",
        default=DEFAULT_OTA_FILE,
        help=f"Dummy nonzero OTA filename. Defaults to {DEFAULT_OTA_FILE}.",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="Custom otaCommand to embed. Overrides --mode.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated files.",
    )
    return parser.parse_args()


def validate_ota_file_name(name: str) -> None:
    if not name or name in {".", "..", "loong_upgrade", "loong_upgrade.used"}:
        raise SystemExit(f"unsafe --ota-file value: {name!r}")
    if "/" in name or "\\" in name:
        raise SystemExit("--ota-file must be a simple filename, not a path")


def write_text_if_allowed(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists; rerun with --force to overwrite")
    path.write_text(content, encoding="utf-8")


def write_bytes_if_allowed(path: Path, content: bytes, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists; rerun with --force to overwrite")
    path.write_bytes(content)


def write_payload(args: argparse.Namespace) -> None:
    validate_ota_file_name(args.ota_file)
    if args.ver_inner < 1:
        raise SystemExit("--ver-inner must be positive")
    if args.mode == "managed-install":
        if args.release_id is None:
            raise SystemExit("--release-id is required for --mode managed-install")
        validate_release_id(args.release_id)
        if args.release_version is not None:
            validate_release_version(args.release_version)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ota_path = output_dir / args.ota_file
    trigger_path = output_dir / "loong_upgrade"
    installer_path = output_dir / INSTALLER_NAME
    recovery_path = output_dir / RECOVERY_NAME

    write_bytes_if_allowed(ota_path, DEFAULT_PROBE_CONTENT, args.force)
    ota_hash, hash_input = loong_upgrade_hash(args.ver_inner, args.ota_file, ota_path.stat().st_size)

    if args.command is not None:
        command = args.command
    elif args.mode == "probe":
        command = probe_command()
    elif args.mode == "recovery":
        command = recovery_command(args.completion_action)
    else:
        command = install_command(args.completion_action)

    payload = {
        "verInner": args.ver_inner,
        "otaFile": args.ota_file,
        "otaHash": ota_hash,
        "otaCommand": command,
    }
    write_text_if_allowed(
        trigger_path,
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        args.force,
    )

    if args.command is None and args.mode == "install":
        write_text_if_allowed(
            installer_path,
            build_installer_script(require_adb_pinned=not args.no_require_adb_pinned),
            args.force,
        )
    elif args.command is None and args.mode == "managed-install":
        validate_platform_payload_coverage(output_dir, args.release_id)
        write_text_if_allowed(
            installer_path,
            build_managed_installer_script(args.release_id, args.release_version),
            args.force,
        )
    elif args.command is None and args.mode == "recovery":
        write_text_if_allowed(recovery_path, build_recovery_script(), args.force)
        if installer_path.exists() and args.force:
            installer_path.unlink()
    elif installer_path.exists() and args.force:
        installer_path.unlink()
    if args.mode != "recovery" and recovery_path.exists() and args.force:
        recovery_path.unlink()

    print(f"Wrote SD payload directory: {output_dir}")
    print(f"  {trigger_path}")
    print(f"  {ota_path}")
    if installer_path.exists():
        print(f"  {installer_path}")
    if recovery_path.exists():
        print(f"  {recovery_path}")
    print(f"otaHash: {ota_hash}")
    print(f"hash input: {hash_input}")
    print(f"mode: {args.mode if args.command is None else 'custom'}")
    print("Copy the generated files to the root of a FAT32 or ext4 SD card.")
    print("Do not use exFAT; stock loong_daemon ignores exFAT SD media.")


def main() -> None:
    write_payload(parse_args())


if __name__ == "__main__":
    main()
