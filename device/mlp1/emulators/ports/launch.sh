#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
PLATFORM_ROOT="$(CDPATH= cd "$SCRIPT_DIR/../.." && pwd)"
retroarch_link_created=0
retroarch_wrapper=""
ports_bind_mounted=0

cleanup() {
    if [ "$retroarch_link_created" = "1" ]; then
        rm -f /usr/bin/retroarch 2>/dev/null || true
    fi
    if [ -n "$retroarch_wrapper" ]; then
        rm -f "$retroarch_wrapper" 2>/dev/null || true
    fi
    if [ "$ports_bind_mounted" = "1" ]; then
        umount /roms/ports 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

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
ports_dir="$(CDPATH= cd "$(dirname "$port_script")" && pwd)"
roms_dir="$(CDPATH= cd "$ports_dir/.." && pwd)"
export HOME="$pm_data"
export XDG_DATA_HOME="$pm_data"
export PORTMASTER_CONTROLFOLDER="${PORTMASTER_CONTROLFOLDER:-$pm_data/PortMaster}"
export PORTMASTER_ROMS_DIRECTORY="${PORTMASTER_ROMS_DIRECTORY:-${roms_dir#/}}"
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
export UMRK_RETROARCH_CONFIG="$pm_data/.config/retroarch/retroarch.cfg"

write_retroarch_config() {
    mkdir -p "$pm_data/.config/retroarch" "$pm_data/BIOS" "$pm_data/saves" \
        "$pm_data/states" "$pm_data/logs"

    tmp_config="$UMRK_RETROARCH_CONFIG.tmp.$$"
    if [ -f "$PLATFORM_ROOT/defaults/retroarch.cfg" ]; then
        cp "$PLATFORM_ROOT/defaults/retroarch.cfg" "$tmp_config"
    else
        {
            printf '%s\n' 'config_save_on_exit = "false"'
            printf '%s\n' 'video_driver = "gl"'
            printf '%s\n' 'video_context_driver = "sdl_gl"'
            printf '%s\n' 'audio_driver = "pulse"'
            printf '%s\n' 'input_driver = "sdl2"'
            printf '%s\n' 'input_joypad_driver = "sdl2"'
            printf '%s\n' 'menu_driver = "rgui"'
            printf '%s\n' 'video_fullscreen = "true"'
            printf '%s\n' 'pause_nonactive = "false"'
        } >"$tmp_config"
    fi

    {
        printf '\n'
        printf 'system_directory = "%s/BIOS"\n' "$pm_data"
        printf 'savefile_directory = "%s/saves"\n' "$pm_data"
        printf 'savestate_directory = "%s/states"\n' "$pm_data"
        printf 'libretro_directory = "%s/cores"\n' "$PLATFORM_ROOT"
        printf 'libretro_info_path = "%s/info"\n' "$PLATFORM_ROOT"
        printf 'rgui_browser_directory = "%s"\n' "$ports_dir"
        printf '%s\n' 'config_save_on_exit = "false"'
        printf '%s\n' 'pause_nonactive = "false"'
        printf '%s\n' 'check_firmware_before_loading = "false"'
        printf '%s\n' 'load_dummy_on_core_shutdown = "false"'
    } >>"$tmp_config"

    mv "$tmp_config" "$UMRK_RETROARCH_CONFIG"
}

write_retroarch_wrapper() {
    retroarch_wrapper="/tmp/leaf-portmaster-retroarch.$$"
    cat >"$retroarch_wrapper" <<'SH'
#!/bin/sh
set -eu

real_ra="${UMRK_RETROARCH_BIN:?}"
config="${UMRK_RETROARCH_CONFIG:?}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/var/run}"
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-wayland}"

has_config=0
for arg in "$@"; do
    if [ "$arg" = "--config" ] || [ "$arg" = "-c" ]; then
        has_config=1
    fi
done

if [ "$has_config" = "1" ]; then
    exec "$real_ra" "$@"
fi

if [ "${UMRK_RETROARCH_VERBOSE:-0}" = "1" ]; then
    exec "$real_ra" --verbose --config "$config" "$@"
fi

exec "$real_ra" --config "$config" "$@"
SH
    chmod 755 "$retroarch_wrapper"
}

if [ -x "$UMRK_RETROARCH_BIN" ] && [ ! -e /usr/bin/retroarch ]; then
    write_retroarch_config
    write_retroarch_wrapper
    if ln -s "$retroarch_wrapper" /usr/bin/retroarch 2>/dev/null; then
        retroarch_link_created=1
    fi
fi

if [ ! -e /usr/bin/retroarch ]; then
    echo "ports launcher: RetroArch missing: $UMRK_RETROARCH_BIN" >&2
    exit 69
fi

if [ -d "$ports_dir" ] && [ ! -d /roms/ports ]; then
    mkdir -p /roms/ports 2>/dev/null || true
fi

if [ -d "$ports_dir" ] &&
   ! awk '$2 == "/roms/ports" { found = 1 } END { exit found ? 0 : 1 }' /proc/mounts; then
    if mount --bind "$ports_dir" /roms/ports 2>/dev/null; then
        ports_bind_mounted=1
    fi
fi

cd "$ports_dir"
/usr/bin/bash "$port_script"
