#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/adb-install"
INSTALLER="$BUILD_DIR/umrk-launcher-install.sh"
REMOTE_INSTALLER="/tmp/umrk-launcher-install.sh"

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

python3 "$ROOT_DIR/make_launcher_switcher_sd.py" --force "$BUILD_DIR" >/dev/null

echo "Pushing installer to $REMOTE_INSTALLER"
"${ADB[@]}" push "$INSTALLER" "$REMOTE_INSTALLER" >/dev/null
"${ADB[@]}" shell "chmod 755 '$REMOTE_INSTALLER'"

echo "Running installer"
"${ADB[@]}" shell "sh '$REMOTE_INSTALLER'"

echo "Installer log:"
"${ADB[@]}" shell "tail -80 /userdata/umrk-launcher-install.log 2>/dev/null || true"

echo
echo "Wrapper installed. Restart the Loong stack or reboot to exercise it:"
echo "  adb shell '/etc/init.d/S50loong restart'"

