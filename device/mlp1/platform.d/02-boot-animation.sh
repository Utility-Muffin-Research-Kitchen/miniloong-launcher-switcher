#!/bin/sh
# Install custom boot animation on first run. Copies frames from the SD card
# to the rootfs boot texture directory. Skips if already installed (stamp file).
# Runs on every boot but the copy only happens once.

STAMP="/loong/textures/.umrk-boot-installed"
SRC="${UMRK_PLATFORM_PATH:-${SYSTEM_PATH:-${SDCARD_PATH:-/mnt/sdcard}/.system/leaf/platforms/${PLATFORM:-mlp1}}}/boot-animation"

# Already installed — nothing to do.
[ -f "$STAMP" ] && exit 0

# Source frames not on SD card — nothing to install.
[ -d "$SRC/0" ] || exit 0

mount -o remount,rw / 2>/dev/null ||
    mount -o remount,rw /dev/root / 2>/dev/null ||
    exit 0

# Backup stock animation if not already done.
if [ ! -d /loong/textures/boot.stock ]; then
    cp -r /loong/textures/boot /loong/textures/boot.stock 2>/dev/null
fi

# Copy new frames.
rm -f /loong/textures/boot/0/* /loong/textures/boot/1/* 2>/dev/null
cp "$SRC/0/"*.png /loong/textures/boot/0/ 2>/dev/null
cp "$SRC/1/"*.png /loong/textures/boot/1/ 2>/dev/null

# Copy config if present.
[ -f "$SRC/boot.cfg" ] && cp "$SRC/boot.cfg" /loong/textures/boot.cfg 2>/dev/null

touch "$STAMP" 2>/dev/null || true
mount -o remount,ro / 2>/dev/null || true
exit 0
