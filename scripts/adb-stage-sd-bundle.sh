#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_ROOT="$ROOT_DIR/build/package"
BUNDLE_DIR="$BUNDLE_ROOT/umrk-launcher"
PLATFORM_DIR="$BUNDLE_ROOT/UMRK"
REMOTE_BUNDLE="/mnt/sdcard/umrk-launcher"
REMOTE_PLATFORM="/mnt/sdcard/UMRK"
MARKER="/mnt/sdcard/.umrk-launcher"
MARKER_MODE="keep"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --marker)
            MARKER_MODE="on"
            ;;
        --no-marker)
            MARKER_MODE="off"
            ;;
        *)
            echo "usage: $0 [--marker|--no-marker]" >&2
            exit 1
            ;;
    esac
    shift
done

if [ ! -x "$BUNDLE_DIR/bin/loong_pangu" ]; then
    echo "missing launcher bundle: $BUNDLE_DIR" >&2
    echo "run: make package" >&2
    exit 1
fi

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

echo "Deploying bundle to $REMOTE_BUNDLE"
"${ADB[@]}" shell "rm -rf '$REMOTE_BUNDLE'"
"${ADB[@]}" push "$BUNDLE_DIR" /mnt/sdcard/ >/dev/null
"${ADB[@]}" shell "chmod 755 '$REMOTE_BUNDLE/bin/loong_pangu' 2>/dev/null || true"

if [ -d "$PLATFORM_DIR" ]; then
    echo "Deploying platform payload to $REMOTE_PLATFORM"
    "${ADB[@]}" shell "mkdir -p '$REMOTE_PLATFORM' && rm -rf '$REMOTE_PLATFORM/mlp1'"
    "${ADB[@]}" push "$PLATFORM_DIR/." "$REMOTE_PLATFORM/" >/dev/null
fi

case "$MARKER_MODE" in
    on)
        "${ADB[@]}" shell "touch '$MARKER'"
        echo "Marker enabled: $MARKER"
        ;;
    off)
        "${ADB[@]}" shell "rm -f '$MARKER'"
        echo "Marker removed: $MARKER"
        ;;
    keep)
        echo "Marker unchanged."
        ;;
esac

"${ADB[@]}" shell sync
echo "SD bundle staged."
