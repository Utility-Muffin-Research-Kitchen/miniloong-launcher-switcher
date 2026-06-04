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

if [ ! -f "$BACKUP" ]; then
    log_msg "backup missing: $BACKUP"
    echo "backup missing: $BACKUP" >&2
    exit 1
fi

cp -p "$BACKUP" "$TARGET" || {
    log_msg "failed to restore $TARGET"
    echo "failed to restore $TARGET" >&2
    exit 1
}
chmod 755 "$TARGET" 2>/dev/null || true
sync

log_msg "restored stock loong_pangu"
echo "restored stock loong_pangu"

if [ "$storage_restore_status" -ne 0 ]; then
    exit "$storage_restore_status"
fi
