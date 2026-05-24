#!/usr/bin/env bash
set -euo pipefail

LINES="${1:-120}"
case "$LINES" in
    ''|*[!0-9]*)
        echo "usage: $0 [line_count]" >&2
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

"${ADB[@]}" shell "
printf '== /userdata/umrk-launcher.log ==\\n'
tail -n '$LINES' /userdata/umrk-launcher.log 2>/dev/null || true
printf '\\n== /userdata/umrk-launcher-install.log ==\\n'
tail -n '$LINES' /userdata/umrk-launcher-install.log 2>/dev/null || true
printf '\\n== /userdata/umrk-launcher-uninstall.log ==\\n'
tail -n '$LINES' /userdata/umrk-launcher-uninstall.log 2>/dev/null || true
"
