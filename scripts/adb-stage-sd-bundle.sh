#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Payload location. Defaults to this repo's own build output, but the workspace
# orchestrator overrides it to stage a centrally-assembled payload.
BUNDLE_ROOT="${BUNDLE_ROOT:-$ROOT_DIR/build/package}"
BUNDLE_DIR="$BUNDLE_ROOT/umrk-launcher"
PLATFORM_DIR="$BUNDLE_ROOT/UMRK"
REMOTE_SDCARD_PATH="${REMOTE_SDCARD_PATH:-/mnt/sdcard}"
REMOTE_LAUNCHER_PATH="${REMOTE_LAUNCHER_PATH:-${REMOTE_BUNDLE:-$REMOTE_SDCARD_PATH/umrk-launcher}}"
REMOTE_UMRK_PATH="${REMOTE_UMRK_PATH:-${REMOTE_PLATFORM:-$REMOTE_SDCARD_PATH/UMRK}}"
REMOTE_PLATFORM_PATH="${REMOTE_PLATFORM_PATH:-$REMOTE_UMRK_PATH/mlp1}"
MARKER="${UMRK_MARKER_PATH:-$REMOTE_SDCARD_PATH/.umrk-launcher}"
MARKER_MODE="keep"
PLATFORM_MODE="replace"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --marker)
            MARKER_MODE="on"
            ;;
        --no-marker)
            MARKER_MODE="off"
            ;;
        --merge-platform)
            PLATFORM_MODE="merge"
            ;;
        *)
            echo "usage: $0 [--marker|--no-marker] [--merge-platform]" >&2
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

"${ADB[@]}" shell "mountpoint -q '$REMOTE_SDCARD_PATH'" >/dev/null || {
    echo "$REMOTE_SDCARD_PATH is not mounted on the device." >&2
    exit 1
}

echo "Deploying bundle to $REMOTE_LAUNCHER_PATH"
"${ADB[@]}" shell "rm -rf '$REMOTE_LAUNCHER_PATH' && mkdir -p '$REMOTE_LAUNCHER_PATH'"
"${ADB[@]}" push "$BUNDLE_DIR/." "$REMOTE_LAUNCHER_PATH/" >/dev/null
"${ADB[@]}" shell "chmod 755 '$REMOTE_LAUNCHER_PATH/bin/loong_pangu' 2>/dev/null || true"

if [ -d "$PLATFORM_DIR" ]; then
    echo "Deploying platform payload to $REMOTE_UMRK_PATH ($PLATFORM_MODE)"
    if [ "$PLATFORM_MODE" = "replace" ]; then
        "${ADB[@]}" shell "mkdir -p '$REMOTE_UMRK_PATH' && rm -rf '$REMOTE_PLATFORM_PATH'"
    else
        "${ADB[@]}" shell "mkdir -p '$REMOTE_UMRK_PATH'"
    fi
    "${ADB[@]}" push "$PLATFORM_DIR/." "$REMOTE_UMRK_PATH/" >/dev/null
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
