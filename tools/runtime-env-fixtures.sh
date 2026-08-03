#!/bin/sh
set -eu

repo_dir="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
primary="/fixture/primary"
secondary="/fixture/secondary-not-mounted"

env_output="$(
    env -i PLATFORM=mlp1 SDCARD_PATH="$primary" \
        UMRK_SECONDARY_SDCARD_PATH="$secondary" \
        sh -c '. "$1"; env' sh "$repo_dir/device/umrk-env.sh"
)"

for expected in \
    "SDCARD_PATHS=$primary:$secondary" \
    "ROMS_PATHS=$primary/Roms:$secondary/Roms" \
    "IMAGES_PATHS=$primary/Images:$secondary/Images" \
    "MUSIC_PATHS=$primary/Music:$secondary/Music" \
    "VIDEO_PATHS=$primary/Videos:$secondary/Videos" \
    "RECORDINGS_PATH=$primary/Recordings" \
    "APPS_PATHS=$primary/Apps:$secondary/Apps" \
    "BIOS_PATHS=$primary/BIOS:$secondary/BIOS" \
    "SAVES_PATHS=$primary/Saves:$secondary/Saves" \
    "STATES_PATHS=$primary/States:$secondary/States" \
    "CHEATS_PATHS=$primary/Cheats:$secondary/Cheats"; do
    printf '%s\n' "$env_output" | grep -F -x "$expected" >/dev/null
done

check_recovery_function() {
    source_file="$1"
    snippet="$repo_dir/build/runtime-env-function.$$"
    mkdir -p "$repo_dir/build"
    {
        printf '%s\n' '#!/bin/sh' \
            'PLATFORM=mlp1' \
            'SECONDARY_SD_MOUNT=/fixture/default-secondary' \
            'mountpoint_is_mounted() { return 1; }' \
            'log_msg() { :; }' \
            'refresh_paths() { :; }' \
            'load_env_file() { :; }'
        sed -n '/^set_active_launcher_sd()/,/^recover_launcher_sd_mount()/p' \
            "$source_file" | sed '$d'
        printf '%s\n' \
            'set_active_launcher_sd /fixture/recovered /fixture/unmounted-alternate' \
            'env'
    } >"$snippet"
    output="$(sh "$snippet")"
    rm -f "$snippet"
    for expected in \
        "SDCARD_PATHS=/fixture/recovered:/fixture/unmounted-alternate" \
        "MUSIC_PATHS=/fixture/recovered/Music:/fixture/unmounted-alternate/Music" \
        "VIDEO_PATHS=/fixture/recovered/Videos:/fixture/unmounted-alternate/Videos" \
        "RECORDINGS_PATH=/fixture/recovered/Recordings" \
        "CHEATS_PATHS=/fixture/recovered/Cheats:/fixture/unmounted-alternate/Cheats"; do
        printf '%s\n' "$output" | grep -F -x "$expected" >/dev/null
    done
}

check_recovery_function "$repo_dir/device/loong_pangu.wrapper"
check_recovery_function "$repo_dir/device/umrk-leaf-session"

for script in \
    "$repo_dir/device/loong_pangu.wrapper" \
    "$repo_dir/device/umrk-leaf-session" \
    "$repo_dir/device/umrk-env.sh" \
    "$repo_dir/device/mlp1/emulators/ports/launch.sh"; do
    sh -n "$script"
done

echo "runtime environment fixtures: PASS"
