#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_DIR="$ROOT_DIR/build/package/umrk-launcher"
REMOTE_DIR="/tmp/umrk-launcher-poc"
EXIT_MS="${UMRK_POC_EXIT_MS:-8000}"

if [ ! -x "$BUNDLE_DIR/bin/loong_pangu" ]; then
    echo "missing POC binary: $BUNDLE_DIR/bin/loong_pangu" >&2
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

pangu_pid="$("${ADB[@]}" shell 'pidof loong_pangu 2>/dev/null || true' | tr -d '\r' | awk '{print $1}')"

cleanup() {
    if [ -n "${pangu_pid:-}" ]; then
        echo "Resuming stock loong_pangu pid $pangu_pid"
        "${ADB[@]}" shell "kill -CONT '$pangu_pid' 2>/dev/null || true" >/dev/null || true
    fi
    "${ADB[@]}" shell "rm -rf '$REMOTE_DIR'" >/dev/null || true
}
trap cleanup EXIT

echo "Deploying POC bundle to $REMOTE_DIR"
"${ADB[@]}" shell "rm -rf '$REMOTE_DIR' && mkdir -p '$REMOTE_DIR'"
"${ADB[@]}" push "$BUNDLE_DIR/." "$REMOTE_DIR/" >/dev/null
"${ADB[@]}" shell "chmod 755 '$REMOTE_DIR/bin/loong_pangu'"

if [ -n "${pangu_pid:-}" ]; then
    echo "Pausing stock loong_pangu pid $pangu_pid"
    "${ADB[@]}" shell "kill -STOP '$pangu_pid'"
else
    echo "No stock loong_pangu pid found; running POC without pause."
fi

echo "Running POC for ${EXIT_MS}ms"
"${ADB[@]}" shell "cd '$REMOTE_DIR' && XDG_RUNTIME_DIR=/var/run SDL_VIDEODRIVER=wayland UMRK_POC_EXIT_MS='$EXIT_MS' bin/loong_pangu"

echo "POC test completed."

