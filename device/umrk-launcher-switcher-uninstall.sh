#!/bin/sh
set -u

INTERNAL_DATA="${UMRK_INTERNAL_DATA_PATH:-/userdata}"
LOG="${UMRK_UNINSTALL_LOG:-$INTERNAL_DATA/umrk-launcher-uninstall.log}"
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
