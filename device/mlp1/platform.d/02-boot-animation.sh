#!/bin/sh
# Install or restore the Leaf boot animation. The early init session owns the
# visible Leaf-mode transition; this hook keeps legacy/direct paths in sync.

STAMP="/loong/textures/.umrk-boot-installed"
MODE="/loong/textures/.umrk-boot-mode"
STOCK_DIR="/loong/textures/boot.stock"
STOCK_CFG="/loong/textures/boot.cfg.stock.umrk"
DISABLED="${UMRK_BOOT_SPLASH_DISABLED_PATH:-${UMRK_INTERNAL_DATA_PATH:-${SDCARD_PATH:-/mnt/sdcard}/.umrk/${PLATFORM:-mlp1}}/boot-splash-disabled}"
SRC="${UMRK_PLATFORM_PATH:-${SYSTEM_PATH:-${SDCARD_PATH:-/mnt/sdcard}/.system/leaf/platforms/${PLATFORM:-mlp1}}}/boot-animation"

remount_rw() {
    mount -o remount,rw / 2>/dev/null ||
        mount -o remount,rw /dev/root / 2>/dev/null
}

remount_ro() {
    mount -o remount,ro / 2>/dev/null || true
}

count_pngs() {
    count="$(find "$1" -maxdepth 1 -type f -name '*.png' 2>/dev/null | wc -l | tr -d ' ')"
    case "$count" in *[!0-9]*|'') count=0 ;; esac
    printf '%s\n' "$count"
}

write_stock_cfg_fallback() {
    seq0="$(count_pngs "$STOCK_DIR/0")"
    seq1="$(count_pngs "$STOCK_DIR/1")"
    [ "$seq0" -gt 0 ] 2>/dev/null || seq0=1
    [ "$seq1" -gt 0 ] 2>/dev/null || seq1=1
    printf '{"dir":"/loong/textures/boot","bg":255,"seques":[{"num":%s,"interval":100,"wait":0,"repeat":1},{"num":%s,"interval":100,"wait":0,"repeat":-1}]}\n' \
        "$seq0" "$seq1" >/loong/textures/boot.cfg 2>/dev/null
}

restore_stock() {
    [ -d "$STOCK_DIR" ] || exit 0
    remount_rw || exit 0
    mkdir -p /loong/textures/boot/0 /loong/textures/boot/1 2>/dev/null || true
    rm -f /loong/textures/boot/0/* /loong/textures/boot/1/* 2>/dev/null
    cp "$STOCK_DIR/0/"*.png /loong/textures/boot/0/ 2>/dev/null || true
    cp "$STOCK_DIR/1/"*.png /loong/textures/boot/1/ 2>/dev/null || true
    if [ -f "$STOCK_CFG" ]; then
        cp "$STOCK_CFG" /loong/textures/boot.cfg 2>/dev/null || true
    else
        write_stock_cfg_fallback || true
    fi
    chmod 755 /loong/textures/boot /loong/textures/boot/0 /loong/textures/boot/1 2>/dev/null || true
    chmod 644 /loong/textures/boot.cfg /loong/textures/boot/0/* /loong/textures/boot/1/* 2>/dev/null || true
    printf 'stock\n' >"$MODE" 2>/dev/null || true
    remount_ro
    exit 0
}

[ -e "$DISABLED" ] && restore_stock

# Source frames not on SD card — nothing to install.
[ -d "$SRC/0" ] || exit 0

if [ "$(cat "$MODE" 2>/dev/null || true)" = "leaf" ] && [ -f "$STAMP" ]; then
    exit 0
fi

had_stock=0
[ -d "$STOCK_DIR" ] && had_stock=1

remount_rw || exit 0

# Backup stock animation if not already done.
if [ "$had_stock" -eq 0 ]; then
    cp -r /loong/textures/boot "$STOCK_DIR" 2>/dev/null
    [ -f /loong/textures/boot.cfg ] && cp /loong/textures/boot.cfg "$STOCK_CFG" 2>/dev/null
fi

# Copy new frames.
mkdir -p /loong/textures/boot/0 /loong/textures/boot/1 2>/dev/null || true
rm -f /loong/textures/boot/0/* /loong/textures/boot/1/* 2>/dev/null
cp "$SRC/0/"*.png /loong/textures/boot/0/ 2>/dev/null
cp "$SRC/1/"*.png /loong/textures/boot/1/ 2>/dev/null

# Copy config if present.
[ -f "$SRC/boot.cfg" ] && cp "$SRC/boot.cfg" /loong/textures/boot.cfg 2>/dev/null

chmod 755 /loong/textures/boot /loong/textures/boot/0 /loong/textures/boot/1 2>/dev/null || true
chmod 644 /loong/textures/boot.cfg /loong/textures/boot/0/* /loong/textures/boot/1/* 2>/dev/null || true
touch "$STAMP" 2>/dev/null || true
printf 'leaf\n' >"$MODE" 2>/dev/null || true
remount_ro
exit 0
