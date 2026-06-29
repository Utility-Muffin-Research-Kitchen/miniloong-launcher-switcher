#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
PLATFORM_ROOT="$(CDPATH= cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$PLATFORM_ROOT/launcher/env.sh" ]; then
    . "$PLATFORM_ROOT/launcher/env.sh"
fi

port_script="${1:-${JAWAKA_GAME_ROM_ABS:-}}"
if [ -z "$port_script" ]; then
    echo "ports launcher: missing port script path" >&2
    exit 64
fi

case "$port_script" in
    /*) ;;
    *) port_script="${SDCARD_PATH:-/mnt/sdcard}/$port_script" ;;
esac

if [ ! -f "$port_script" ]; then
    echo "ports launcher: script not found: $port_script" >&2
    exit 66
fi

case "$port_script" in
    */Roms/PORTS/*.sh|*/Roms/Ports/*.sh|*/Roms/ports/*.sh) ;;
    *)
        echo "ports launcher: refusing non-PortMaster script: $port_script" >&2
        exit 65
        ;;
esac

pm_data="${USERDATA_PATH:-${SDCARD_PATH:-/mnt/sdcard}/.userdata/${PLATFORM:-mlp1}}/portmaster"
export HOME="$pm_data"
export XDG_DATA_HOME="$pm_data"
export PORTMASTER_CONTROLFOLDER="${PORTMASTER_CONTROLFOLDER:-$pm_data/PortMaster}"
export PORTMASTER_LEAF_DEVICE_INFO=1
export CFW_NAME="${CFW_NAME:-Leaf}"
export DEVICE_NAME="${DEVICE_NAME:-Miniloong Pocket 1}"
export DEVICE_CPU="${DEVICE_CPU:-RK3566}"
export DEVICE_ARCH="${DEVICE_ARCH:-aarch64}"
export DEVICE_HAS_ARMHF="${DEVICE_HAS_ARMHF:-N}"
export DEVICE_HAS_AARCH64="${DEVICE_HAS_AARCH64:-Y}"
export DEVICE_HAS_X86="${DEVICE_HAS_X86:-N}"
export DEVICE_HAS_X86_64="${DEVICE_HAS_X86_64:-N}"
export DISPLAY_WIDTH="${DISPLAY_WIDTH:-960}"
export DISPLAY_HEIGHT="${DISPLAY_HEIGHT:-720}"
export DISPLAY_ORIENTATION="${DISPLAY_ORIENTATION:-0}"
export ASPECT_X="${ASPECT_X:-4}"
export ASPECT_Y="${ASPECT_Y:-3}"
export ANALOG_STICKS="${ANALOG_STICKS:-2}"
export ANALOGSTICKS="${ANALOGSTICKS:-2}"
export UMRK_RETROARCH_BIN="${UMRK_RETROARCH_BIN:-$PLATFORM_ROOT/bin/retroarch}"

cd "$(dirname "$port_script")"
exec /usr/bin/bash "$port_script"
