#!/bin/sh
# UMRK runtime path contract.
#
# Source this file from launchers, paks, and platform scripts. Existing
# environment values win; this file only fills missing variables.

umrk_env_default() {
    _umrk_name="$1"
    _umrk_value="$2"
    eval "_umrk_current=\${$_umrk_name:-}"
    if [ -z "$_umrk_current" ]; then
        export "$_umrk_name=$_umrk_value"
    else
        export "$_umrk_name"
    fi
}

umrk_env_default UMRK_ENV_VERSION "1"

if [ -n "${JAWAKA_SDCARD_ROOT:-}" ] && [ -z "${SDCARD_PATH:-}" ]; then
    export SDCARD_PATH="$JAWAKA_SDCARD_ROOT"
fi
if [ -n "${JAWAKA_RUNTIME_DIR:-}" ] && [ -z "${UMRK_RUNTIME_PATH:-}" ]; then
    export UMRK_RUNTIME_PATH="$JAWAKA_RUNTIME_DIR"
fi
if [ -n "${JAWAKA_RETROARCH_BIN:-}" ] && [ -z "${UMRK_RETROARCH_BIN:-}" ]; then
    export UMRK_RETROARCH_BIN="$JAWAKA_RETROARCH_BIN"
fi
if [ -n "${JAWAKA_RETROARCH_CORES_DIR:-}" ] && [ -z "${CORES_PATH:-}" ]; then
    export CORES_PATH="$JAWAKA_RETROARCH_CORES_DIR"
fi

umrk_env_default PLATFORM "mlp1"
umrk_env_default DEVICE "$PLATFORM"

case "$PLATFORM" in
    mlp1)
        _umrk_default_sd="/mnt/sdcard"
        _umrk_default_system_rel=".system/leaf/platforms/$PLATFORM"
        _umrk_default_launcher_rel=".system/leaf/platforms/$PLATFORM/launcher"
        _umrk_default_runtime="${TMPDIR:-/tmp}/jawaka-runtime"
        _umrk_default_internal_rel=".system/leaf/platforms/$PLATFORM/state"
        ;;
    tg5040|tg5050|my355)
        _umrk_default_sd="/mnt/SDCARD"
        _umrk_default_system_rel=".system/leaf/platforms/$PLATFORM"
        _umrk_default_launcher_rel=".system/leaf/platforms/$PLATFORM/launcher"
        _umrk_default_runtime="${TMPDIR:-/tmp}/umrk-runtime-$PLATFORM"
        _umrk_default_internal_rel=".system/leaf/platforms/$PLATFORM/state"
        ;;
    mac)
        _umrk_default_sd="./mock-sdcard"
        _umrk_default_system_rel=".system/leaf/platforms/$PLATFORM"
        _umrk_default_launcher_rel=".system/leaf/platforms/$PLATFORM/launcher"
        _umrk_default_runtime="${TMPDIR:-/tmp}/jawaka-${USER:-user}"
        _umrk_default_internal_rel=".system/leaf/platforms/$PLATFORM/state"
        ;;
    *)
        _umrk_default_sd="/mnt/SDCARD"
        _umrk_default_system_rel=".system/leaf/platforms/$PLATFORM"
        _umrk_default_launcher_rel=".system/leaf/platforms/$PLATFORM/launcher"
        _umrk_default_runtime="${TMPDIR:-/tmp}/umrk-runtime-$PLATFORM"
        _umrk_default_internal_rel=".system/leaf/platforms/$PLATFORM/state"
        ;;
esac

umrk_env_default SDCARD_PATH "$_umrk_default_sd"
umrk_env_default SYSTEM_PATH "$SDCARD_PATH/$_umrk_default_system_rel"
umrk_env_default UMRK_PLATFORM_PATH "$SYSTEM_PATH"
umrk_env_default UMRK_LAUNCHER_PATH "$SDCARD_PATH/$_umrk_default_launcher_rel"
umrk_env_default UMRK_BIN_PATH "$UMRK_LAUNCHER_PATH/bin"
umrk_env_default UMRK_ENV_FILE "$UMRK_LAUNCHER_PATH/env.sh"

umrk_env_default USERDATA_PATH "$SYSTEM_PATH/userdata"
umrk_env_default SHARED_USERDATA_PATH "$SDCARD_PATH/.system/leaf/shared/userdata"
umrk_env_default LOGS_PATH "$USERDATA_PATH/logs"
umrk_env_default ROMS_PATH "$SDCARD_PATH/Roms"
umrk_env_default IMAGES_PATH "$SDCARD_PATH/Images"
umrk_env_default APPS_PATH "$SDCARD_PATH/Apps"
umrk_env_default BIOS_PATH "$SDCARD_PATH/BIOS"
umrk_env_default SAVES_PATH "$SDCARD_PATH/Saves"
umrk_env_default STATES_PATH "$SDCARD_PATH/States"
umrk_env_default CHEATS_PATH "$SDCARD_PATH/Cheats"
umrk_env_default CORES_PATH "$SYSTEM_PATH/cores"
umrk_env_default INFO_PATH "$SYSTEM_PATH/info"
umrk_env_default UMRK_RUNTIME_PATH "$_umrk_default_runtime"

case "$PLATFORM" in
    mlp1)
        umrk_env_default UMRK_SECONDARY_SDCARD_PATH "/media/sdcard1"
        umrk_env_default UMRK_SSH_PRIMARY_IFACE "wlan0"
        _umrk_sdcard_paths="$SDCARD_PATH:$UMRK_SECONDARY_SDCARD_PATH"
        _umrk_roms_paths="$ROMS_PATH:$UMRK_SECONDARY_SDCARD_PATH/Roms"
        _umrk_images_paths="$IMAGES_PATH:$UMRK_SECONDARY_SDCARD_PATH/Images"
        _umrk_apps_paths="$APPS_PATH:$UMRK_SECONDARY_SDCARD_PATH/Apps"
        _umrk_bios_paths="$BIOS_PATH:$UMRK_SECONDARY_SDCARD_PATH/BIOS"
        _umrk_saves_paths="$SAVES_PATH:$UMRK_SECONDARY_SDCARD_PATH/Saves"
        _umrk_states_paths="$STATES_PATH:$UMRK_SECONDARY_SDCARD_PATH/States"
        _umrk_cheats_paths="$CHEATS_PATH:$UMRK_SECONDARY_SDCARD_PATH/Cheats"
        ;;
    *)
        _umrk_sdcard_paths="$SDCARD_PATH"
        _umrk_roms_paths="$ROMS_PATH"
        _umrk_images_paths="$IMAGES_PATH"
        _umrk_apps_paths="$APPS_PATH"
        _umrk_bios_paths="$BIOS_PATH"
        _umrk_saves_paths="$SAVES_PATH"
        _umrk_states_paths="$STATES_PATH"
        _umrk_cheats_paths="$CHEATS_PATH"
        ;;
esac

umrk_env_default SDCARD_PATHS "$_umrk_sdcard_paths"
umrk_env_default ROMS_PATHS "$_umrk_roms_paths"
umrk_env_default IMAGES_PATHS "$_umrk_images_paths"
umrk_env_default APPS_PATHS "$_umrk_apps_paths"
umrk_env_default BIOS_PATHS "$_umrk_bios_paths"
umrk_env_default SAVES_PATHS "$_umrk_saves_paths"
umrk_env_default STATES_PATHS "$_umrk_states_paths"
umrk_env_default CHEATS_PATHS "$_umrk_cheats_paths"

umrk_env_default UMRK_INTERNAL_DATA_PATH "$SDCARD_PATH/$_umrk_default_internal_rel"
umrk_env_default UMRK_MARKER_PATH "$SYSTEM_PATH/enabled"
umrk_env_default UMRK_ADB_MARKER_PATH "$UMRK_INTERNAL_DATA_PATH/adb-enabled"

umrk_env_default UMRK_RETROARCH_BIN "$SYSTEM_PATH/bin/retroarch"
# RetroArch's HOME-based config dir: where it reads per-core configs and
# AUTOMATIC shader presets (global.glslp etc). RA does not auto-load the global
# `video_shader` cfg value at boot, so apps that want a shader to auto-apply
# (e.g. Fugazi's global CRT) drop a preset here. jawakad launches RetroArch with
# HOME = the SD state dir (jw_retroarch_state_dir = UMRK_INTERNAL_DATA_PATH/
# retroarch), so RA's whole config tree lives on the SD card.
umrk_env_default UMRK_RETROARCH_CONFIG_DIR "$UMRK_INTERNAL_DATA_PATH/retroarch/.config/retroarch/config"
umrk_env_default JAWAKA_SDCARD_ROOT "$SDCARD_PATH"
umrk_env_default JAWAKA_RUNTIME_DIR "$UMRK_RUNTIME_PATH"
umrk_env_default JAWAKA_RETROARCH_BIN "$UMRK_RETROARCH_BIN"
umrk_env_default JAWAKA_RETROARCH_CORES_DIR "$CORES_PATH"
umrk_env_default UMRK_AUDIO_OUTPUT "SPEAKER"
umrk_env_default UMRK_AUDIO_DEVICE "default"
umrk_env_default JAWAKA_AUDIO_OUTPUT "$UMRK_AUDIO_OUTPUT"
umrk_env_default JAWAKA_AUDIO_DEVICE "$UMRK_AUDIO_DEVICE"
# Resident same-core switch experiment cap:
#   0 disables resident content switching
#   1 keeps the current safe default
#   -1 or "unlimited" removes the per-RetroArch-process cap
umrk_env_default JAWAKA_RESIDENT_SWITCH_MAX "1"
umrk_env_default CAT_THEMES_DIR "$UMRK_LAUNCHER_PATH/res/themes"
umrk_env_default CAT_FONTS_DIR "$UMRK_LAUNCHER_PATH/res"
umrk_env_default CAT_STATUS_ASSETS_DIR "$UMRK_LAUNCHER_PATH/res/assets"
umrk_env_default CAT_THEME_NAME "Jawaka-Tabs"
umrk_env_default CAT_FONT_PATH "fonts/SpaceGrotesk/SpaceGrotesk-Regular.ttf"
# Status-bar / hint chrome for direct/manual pak launches. jawakad overrides
# these with the live persisted prefs; these defaults match the launcher's own.
umrk_env_default CAT_STATUS_SHOW_WIFI "1"
umrk_env_default CAT_STATUS_SHOW_BLUETOOTH "1"
umrk_env_default CAT_STATUS_BT_STATE "0"
umrk_env_default CAT_STATUS_SHOW_BATTERY "1"
umrk_env_default CAT_STATUS_SHOW_BATTERY_LEVEL "0"
umrk_env_default CAT_STATUS_CLOCK "24"
umrk_env_default CAT_SHOW_HINTS "1"

unset _umrk_name _umrk_value _umrk_current _umrk_default_sd
unset _umrk_default_system_rel _umrk_default_launcher_rel
unset _umrk_default_runtime _umrk_default_internal_rel
unset _umrk_sdcard_paths _umrk_roms_paths _umrk_images_paths _umrk_apps_paths
unset _umrk_bios_paths _umrk_saves_paths _umrk_states_paths _umrk_cheats_paths
