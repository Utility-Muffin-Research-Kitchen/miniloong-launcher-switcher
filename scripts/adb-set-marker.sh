#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
MARKER="/mnt/sdcard/.umrk-launcher"

case "$MODE" in
    on|--on|enable|--enable)
        MODE="on"
        ;;
    off|--off|disable|--disable)
        MODE="off"
        ;;
    *)
        echo "usage: $0 on|off" >&2
        exit 1
        ;;
esac

if [ -n "${ADB_SERIAL:-}" ]; then
    ADB=(adb -s "$ADB_SERIAL")
else
    serial="$(adb devices | awk 'NR>1 && $2=="device" {print $1; exit}')"
    if [ -z "${serial:-}" ]; then
        echo "No online adb device found." >&2
        exit 1
    fi
    ADB=(adb -s "$serial")
fi

echo "Using adb device: $("${ADB[@]}" get-serialno)"

"${ADB[@]}" shell "mountpoint -q /mnt/sdcard" >/dev/null || {
    echo "/mnt/sdcard is not mounted on the device." >&2
    exit 1
}

if [ "$MODE" = "on" ]; then
    "${ADB[@]}" shell "touch '$MARKER' && sync"
    echo "Marker enabled: $MARKER"
else
    "${ADB[@]}" shell "rm -f '$MARKER' && sync"
    echo "Marker disabled: $MARKER"
fi
