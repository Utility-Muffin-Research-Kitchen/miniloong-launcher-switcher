#!/bin/sh
set -u

PLATFORM="${PLATFORM:-mlp1}"
SDCARD_PATH="${SDCARD_PATH:-/mnt/sdcard}"
ENV_FILE="${UMRK_ENV_FILE:-$SDCARD_PATH/.system/leaf/launcher/env.sh}"
if [ -f "$ENV_FILE" ]; then
    . "$ENV_FILE"
fi

USERDATA_DIR="${USERDATA_PATH:-$SDCARD_PATH/.system/leaf/userdata/$PLATFORM}"
LOG_DIR="${LOGS_PATH:-$USERDATA_DIR/logs}"
LOG="${UMRK_UNINSTALL_LOG:-$LOG_DIR/umrk-launcher-uninstall.log}"
TARGET=/loong/loong_pangu
BACKUP=/loong/loong_pangu.stock.umrk
STORAGE=/loong/loong_storage
STORAGE_BACKUP=/loong/loong_storage.stock.umrk
HOOK=/etc/init.d/S50leaf
SESSION=/usr/bin/umrk-leaf-session

log_msg() {
    log_dir="${LOG%/*}"
    if [ "$log_dir" != "$LOG" ]; then
        mkdir -p "$log_dir" 2>/dev/null || true
    fi
    printf '[%s] %s\n' "$(date '+%F %T' 2>/dev/null || echo unknown)" "$*" >>"$LOG" 2>/dev/null || true
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

log_msg "uninstall starting"
storage_restore_status=0
restore_stock_storage || storage_restore_status=$?

rm -f "$HOOK" "$SESSION" 2>/dev/null || true
log_msg "removed init hook/session"
echo "removed init hook/session"

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
