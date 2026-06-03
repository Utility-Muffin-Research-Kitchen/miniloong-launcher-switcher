#!/bin/sh
set -u

PLATFORM="${PLATFORM:-mlp1}"
SDCARD_PATH="${SDCARD_PATH:-/mnt/sdcard}"
ENV_FILE="${UMRK_ENV_FILE:-$SDCARD_PATH/umrk-launcher/env.sh}"
if [ -f "$ENV_FILE" ]; then
    . "$ENV_FILE"
fi

USERDATA_DIR="${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}"
LOG_DIR="${LOGS_PATH:-$USERDATA_DIR/logs}"
LOG="${UMRK_UNINSTALL_LOG:-$LOG_DIR/umrk-launcher-uninstall.log}"
TARGET=/loong/loong_pangu
BACKUP=/loong/loong_pangu.stock.umrk

log_msg() {
    log_dir="${LOG%/*}"
    if [ "$log_dir" != "$LOG" ]; then
        mkdir -p "$log_dir" 2>/dev/null || true
    fi
    printf '[%s] %s\n' "$(date '+%F %T' 2>/dev/null || echo unknown)" "$*" >>"$LOG" 2>/dev/null || true
}

log_msg "uninstall starting"

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
