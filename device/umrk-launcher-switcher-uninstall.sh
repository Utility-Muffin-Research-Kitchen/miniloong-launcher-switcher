#!/bin/sh
set -u

PLATFORM="${PLATFORM:-mlp1}"
SDCARD_PATH="${SDCARD_PATH:-/mnt/sdcard}"
PLATFORM_ROOT="${UMRK_PLATFORM_PATH:-${SYSTEM_PATH:-$SDCARD_PATH/.system/leaf/platforms/$PLATFORM}}"
ENV_FILE="${UMRK_ENV_FILE:-$PLATFORM_ROOT/launcher/env.sh}"
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    . "$ENV_FILE"
fi

PLATFORM_ROOT="${UMRK_PLATFORM_PATH:-${SYSTEM_PATH:-$SDCARD_PATH/.system/leaf/platforms/$PLATFORM}}"
USERDATA_DIR="${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}"
LOG_DIR="${LOGS_PATH:-$USERDATA_DIR/logs}"
LOG="${UMRK_UNINSTALL_LOG:-$LOG_DIR/umrk-launcher-uninstall.log}"
TARGET=/loong/loong_pangu
BACKUP=/loong/loong_pangu.stock.umrk
STORAGE=/loong/loong_storage
STORAGE_BACKUP=/loong/loong_storage.stock.umrk
HOOK=/etc/init.d/S50leaf
SESSION=/usr/bin/umrk-leaf-session
MOUNT_STUBS=/usr/bin/umrk-mount-stubs
STORAGE_REPAIR=/usr/bin/umrk-storage-repair
POWER_TRANSITION=/usr/bin/umrk-power-transition
STORAGE_HOLD_RULE=/etc/udev/rules.d/95-umrk-storage-hold.rules
STORAGE_RECOVERY_ASSETS=/usr/share/umrk/storage-recovery
BOOT_DIR=/loong/textures/boot
BOOT_CFG=/loong/textures/boot.cfg
BOOT_STOCK_DIR=/loong/textures/boot.stock
BOOT_STOCK_CFG=/loong/textures/boot.cfg.stock.umrk
BOOT_MODE=/loong/textures/.umrk-boot-mode
BOOT_STAMP=/loong/textures/.umrk-boot-installed

log_msg() {
    log_dir="${LOG%/*}"
    if [ "$log_dir" != "$LOG" ]; then
        mkdir -p "$log_dir" 2>/dev/null || true
    fi
    printf '[%s] %s\n' "$(date '+%F %T' 2>/dev/null || echo unknown)" "$*" >>"$LOG" 2>/dev/null || true
}

remount_root_rw() {
    mount -o remount,rw / 2>>"$LOG" && return 0
    mount -o remount,rw /dev/root / 2>>"$LOG"
}

is_umrk_noop_storage() {
    [ -f "$STORAGE" ] && grep -q "umrk-noop" "$STORAGE" 2>/dev/null
}

is_old_umrk_pangu_wrapper() {
    [ -f "$TARGET" ] && grep -q "UMRK_LAUNCHER_SWITCHER_WRAPPER=1" "$TARGET" 2>/dev/null
}

restore_stock_storage() {
    is_umrk_noop_storage || return 0

    if [ ! -f "$STORAGE_BACKUP" ]; then
        log_msg "loong_storage is noop but backup missing: $STORAGE_BACKUP"
        echo "loong_storage backup missing: $STORAGE_BACKUP" >&2
        return 1
    fi

    cp -p "$STORAGE_BACKUP" "$STORAGE" || {
        log_msg "failed to restore $STORAGE"
        echo "failed to restore $STORAGE" >&2
        return 1
    }
    chmod 0775 "$STORAGE" 2>/dev/null || chmod 755 "$STORAGE" 2>/dev/null || true
    sync

    if pidof loong_storage >/dev/null 2>&1; then
        killall loong_storage 2>/dev/null || true
        sleep 1
    fi

    log_msg "restored stock loong_storage"
    echo "restored stock loong_storage"
}

# Frame count for one boot sequence directory; 0 for a missing or odd one.
count_boot_pngs() {
    count="$(find "$1" -maxdepth 1 -type f -name '*.png' 2>/dev/null | wc -l | tr -d ' ')"
    case "$count" in *[!0-9]*|'') count=0 ;; esac
    printf '%s\n' "$count"
}

# Put the stock boot animation back. Leaf overwrites /loong/textures/boot on the
# rootfs and keeps the originals in boot.stock, and umrk-leaf-session has a
# restore of its own -- but that only runs from pass_to_stock(), and uninstall
# deletes the session script, so nothing would ever call it again. Duplicated
# here on purpose: after this script runs, this is the only copy left, the same
# reason loong_pangu and loong_storage are restored from backups right here.
#
# NOTE: this deliberately does NOT remount the rootfs read-only when it is done,
# unlike the copy in umrk-leaf-session. Stock S50loong runs `#!/bin/sh -e` and
# chmods loong_daemon before launching it; on a read-only rootfs that chmod
# fails, errexit aborts the script, loong_daemon never starts, and the device
# boots to a black screen. Uninstall hands the card straight back to stock, so
# the rootfs has to stay writable the way the kernel cmdline mounts it.
restore_stock_boot_animation() {
    [ "$PLATFORM" = "mlp1" ] || return 0

    mode="$(cat "$BOOT_MODE" 2>/dev/null || true)"
    if [ "$mode" = "stock" ] && [ -d "$BOOT_STOCK_DIR" ]; then
        log_msg "boot animation already stock"
        return 0
    fi

    if [ ! -d "$BOOT_STOCK_DIR" ]; then
        # Nothing was ever replaced, or the backup is gone. Either way there is
        # nothing to put back, and guessing would be worse than leaving it.
        log_msg "stock boot animation backup missing; leaving boot animation alone"
        return 0
    fi

    mkdir -p "$BOOT_DIR/0" "$BOOT_DIR/1" 2>/dev/null || true
    rm -f "$BOOT_DIR/0/"* "$BOOT_DIR/1/"* 2>/dev/null || true
    cp "$BOOT_STOCK_DIR/0/"*.png "$BOOT_DIR/0/" 2>/dev/null || true
    cp "$BOOT_STOCK_DIR/1/"*.png "$BOOT_DIR/1/" 2>/dev/null || true

    if [ -f "$BOOT_STOCK_CFG" ]; then
        cp "$BOOT_STOCK_CFG" "$BOOT_CFG" 2>/dev/null || true
    else
        # No saved cfg: rebuild one from the frame counts, matching the stock
        # shape (sequence 0 plays once, sequence 1 loops until handoff).
        seq0="$(count_boot_pngs "$BOOT_STOCK_DIR/0")"
        seq1="$(count_boot_pngs "$BOOT_STOCK_DIR/1")"
        [ "$seq0" -gt 0 ] 2>/dev/null || seq0=1
        [ "$seq1" -gt 0 ] 2>/dev/null || seq1=1
        printf '{"dir":"/loong/textures/boot","bg":255,"seques":[{"num":%s,"interval":100,"wait":0,"repeat":1},{"num":%s,"interval":100,"wait":0,"repeat":-1}]}\n' \
            "$seq0" "$seq1" >"$BOOT_CFG" 2>/dev/null || true
    fi

    chmod 755 "$BOOT_DIR" "$BOOT_DIR/0" "$BOOT_DIR/1" 2>/dev/null || true
    chmod 644 "$BOOT_CFG" "$BOOT_DIR/0/"* "$BOOT_DIR/1/"* 2>/dev/null || true
    sync

    # Every copy above is best-effort, so confirm the frames actually landed
    # before throwing the originals away. A full card or a write error would
    # otherwise leave the boot dir short AND delete the only copy of the stock
    # animation -- turning a cosmetic problem into an unrecoverable one.
    restored0="$(count_boot_pngs "$BOOT_DIR/0")"
    restored1="$(count_boot_pngs "$BOOT_DIR/1")"
    expected0="$(count_boot_pngs "$BOOT_STOCK_DIR/0")"
    expected1="$(count_boot_pngs "$BOOT_STOCK_DIR/1")"
    if [ "$restored0" -lt "$expected0" ] || [ "$restored1" -lt "$expected1" ]; then
        log_msg "boot animation restore incomplete ($restored0/$expected0, $restored1/$expected1); keeping backup"
        echo "boot animation restore incomplete; stock backup kept" >&2
        return 1
    fi

    # Restore confirmed: drop Leaf's bookkeeping and the backup it guarded. A
    # reinstall re-snapshots boot.stock from whatever is live at the time, so
    # removing it now costs nothing.
    rm -f "$BOOT_STAMP" "$BOOT_STOCK_CFG" 2>/dev/null || true
    rm -rf "$BOOT_STOCK_DIR" 2>/dev/null || true
    rm -f "$BOOT_MODE" 2>/dev/null || true
    sync

    log_msg "restored stock boot animation"
    echo "restored stock boot animation"
}

log_msg "uninstall starting"
if ! remount_root_rw; then
    log_msg "rootfs remount rw failed"
    echo "rootfs remount rw failed" >&2
fi
storage_restore_status=0
restore_stock_storage || storage_restore_status=$?
restore_stock_boot_animation || log_msg "boot animation restore reported failure"
stub_unlock_status=0
if [ -x "$MOUNT_STUBS" ]; then
    "$MOUNT_STUBS" unlock >>"$LOG" 2>&1 || stub_unlock_status=$?
fi

rm -f "$HOOK" "$SESSION" 2>/dev/null || true
log_msg "removed init hook/session"
echo "removed init hook/session"

# Uninstalling ends SD repair protection deliberately: pending requests and
# holds go, repair logs stay on internal storage. A card held after a failed
# repair is left exactly as mounted now; nothing here remounts it writable.
if [ -x "$STORAGE_REPAIR" ]; then
    "$STORAGE_REPAIR" uninstall-cleanup >>"$LOG" 2>&1 ||
        log_msg "storage repair cleanup reported failure"
fi
rm -f "$STORAGE_REPAIR" "$STORAGE_HOLD_RULE" "$POWER_TRANSITION" 2>/dev/null || true
rm -rf "$STORAGE_RECOVERY_ASSETS" 2>/dev/null || true
log_msg "removed SD repair runner, mount hold rule and recovery screens"
echo "removed SD repair runner and mount hold rule"

if [ "$stub_unlock_status" -eq 0 ]; then
    rm -f "$MOUNT_STUBS" 2>/dev/null || true
    log_msg "cleared rootfs mount-stub protection"
    echo "cleared rootfs mount-stub protection"
else
    log_msg "failed to clear rootfs mount-stub protection; helper retained"
    echo "failed to clear rootfs mount-stub protection; helper retained" >&2
fi

if is_old_umrk_pangu_wrapper; then
    if [ ! -f "$BACKUP" ]; then
        log_msg "legacy pangu wrapper present but backup missing: $BACKUP"
        echo "legacy pangu wrapper present but backup missing: $BACKUP" >&2
        exit 1
    fi

    cp -p "$BACKUP" "$TARGET" || {
        log_msg "failed to restore $TARGET"
        echo "failed to restore $TARGET" >&2
        exit 1
    }
    chmod 755 "$TARGET" 2>/dev/null || true
    log_msg "restored stock loong_pangu"
    echo "restored stock loong_pangu"
else
    log_msg "stock loong_pangu left untouched"
    echo "stock loong_pangu left untouched"
fi

sync

if [ "$storage_restore_status" -ne 0 ]; then
    exit "$storage_restore_status"
fi
if [ "$stub_unlock_status" -ne 0 ]; then
    exit "$stub_unlock_status"
fi
