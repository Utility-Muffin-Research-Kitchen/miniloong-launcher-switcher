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
        _umrk_default_system_rel="UMRK/$PLATFORM"
        _umrk_default_launcher_rel="umrk-launcher"
        _umrk_default_runtime="${TMPDIR:-/tmp}/jawaka-runtime"
        _umrk_default_internal="/userdata"
        ;;
    tg5040|tg5050|my355)
        _umrk_default_sd="/mnt/SDCARD"
        _umrk_default_system_rel=".system/$PLATFORM"
        _umrk_default_launcher_rel=".system/$PLATFORM"
        _umrk_default_runtime="${TMPDIR:-/tmp}/umrk-runtime-$PLATFORM"
        _umrk_default_internal=""
        ;;
    mac)
        _umrk_default_sd="./mock-sdcard"
        _umrk_default_system_rel="UMRK/$PLATFORM"
        _umrk_default_launcher_rel="umrk-launcher"
        _umrk_default_runtime="${TMPDIR:-/tmp}/jawaka-${USER:-user}"
        _umrk_default_internal=""
        ;;
    *)
        _umrk_default_sd="/mnt/SDCARD"
        _umrk_default_system_rel="UMRK/$PLATFORM"
        _umrk_default_launcher_rel="umrk-launcher"
        _umrk_default_runtime="${TMPDIR:-/tmp}/umrk-runtime-$PLATFORM"
        _umrk_default_internal=""
        ;;
esac

umrk_env_default SDCARD_PATH "$_umrk_default_sd"
umrk_env_default SYSTEM_PATH "$SDCARD_PATH/$_umrk_default_system_rel"
umrk_env_default UMRK_PLATFORM_PATH "$SYSTEM_PATH"
umrk_env_default UMRK_LAUNCHER_PATH "$SDCARD_PATH/$_umrk_default_launcher_rel"
umrk_env_default UMRK_BIN_PATH "$UMRK_LAUNCHER_PATH/bin"

umrk_env_default USERDATA_PATH "$SDCARD_PATH/.userdata/$PLATFORM"
umrk_env_default SHARED_USERDATA_PATH "$SDCARD_PATH/.userdata/shared"
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

if [ -n "$_umrk_default_internal" ]; then
    umrk_env_default UMRK_INTERNAL_DATA_PATH "$_umrk_default_internal"
else
    umrk_env_default UMRK_INTERNAL_DATA_PATH "$USERDATA_PATH"
fi

umrk_env_default UMRK_RETROARCH_BIN "$SYSTEM_PATH/bin/retroarch"
umrk_env_default JAWAKA_SDCARD_ROOT "$SDCARD_PATH"
umrk_env_default JAWAKA_RUNTIME_DIR "$UMRK_RUNTIME_PATH"
umrk_env_default JAWAKA_RETROARCH_BIN "$UMRK_RETROARCH_BIN"
umrk_env_default JAWAKA_RETROARCH_CORES_DIR "$CORES_PATH"

unset _umrk_name _umrk_value _umrk_current _umrk_default_sd
unset _umrk_default_system_rel _umrk_default_launcher_rel
unset _umrk_default_runtime _umrk_default_internal
