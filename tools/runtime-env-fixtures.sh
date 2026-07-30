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

# Project the v2 result onto the complete pre-existing v1 key set. This CRC and
# byte count were captured from the v1 producer for the fixture roots above;
# filtering permits only the documented version change and two new PATH-2 keys.
legacy_projection="$(
    printf '%s\n' "$env_output" |
        grep -Ev '^(_|PWD|SHLVL|UMRK_ENV_VERSION|USERDATA_PATHS|SHARED_USERDATA_PATHS)=' |
        LC_ALL=C sort |
        cksum
)"
[ "$legacy_projection" = "3712759435 3192" ] || {
    echo "v1 runtime environment projection changed: $legacy_projection" >&2
    exit 1
}

for expected in \
    "UMRK_ENV_VERSION=2" \
    "SDCARD_PATH=$primary" \
    "USERDATA_PATH=$primary/.userdata/mlp1" \
    "SHARED_USERDATA_PATH=$primary/.userdata/shared" \
    "SAVES_PATH=$primary/Saves" \
    "STATES_PATH=$primary/States" \
    "SDCARD_PATHS=$primary:$secondary" \
    "USERDATA_PATHS=$primary/.userdata/mlp1:$secondary/.userdata/mlp1" \
    "SHARED_USERDATA_PATHS=$primary/.userdata/shared:$secondary/.userdata/shared" \
    "ROMS_PATHS=$primary/Roms:$secondary/Roms" \
    "IMAGES_PATHS=$primary/Images:$secondary/Images" \
    "MUSIC_PATHS=$primary/Music:$secondary/Music" \
    "APPS_PATHS=$primary/Apps:$secondary/Apps" \
    "BIOS_PATHS=$primary/BIOS:$secondary/BIOS" \
    "SAVES_PATHS=$primary/Saves:$secondary/Saves" \
    "STATES_PATHS=$primary/States:$secondary/States" \
    "CHEATS_PATHS=$primary/Cheats:$secondary/Cheats"; do
    printf '%s\n' "$env_output" | grep -F -x "$expected" >/dev/null
done

invalid_output="$(
    env -i PLATFORM=mlp1 SDCARD_PATH="$primary" \
        UMRK_SECONDARY_SDCARD_PATH="$secondary" \
        USERDATA_PATHS=/wrong-card/.userdata/mlp1 \
        sh -c '. "$1"; env' sh "$repo_dir/device/umrk-env.sh"
)"
printf '%s\n' "$invalid_output" | grep -F -x "UMRK_ENV_VERSION=1" >/dev/null

one_card_output="$(
    env -i PLATFORM=mac SDCARD_PATH="$primary" \
        sh -c '. "$1"; env' sh "$repo_dir/device/umrk-env.sh"
)"
for expected in \
    "UMRK_ENV_VERSION=2" \
    "SDCARD_PATHS=$primary" \
    "USERDATA_PATHS=$primary/.userdata/mac" \
    "SHARED_USERDATA_PATHS=$primary/.userdata/shared" \
    "SAVES_PATHS=$primary/Saves" \
    "STATES_PATHS=$primary/States"; do
    printf '%s\n' "$one_card_output" | grep -F -x "$expected" >/dev/null
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
        "USERDATA_PATHS=/fixture/recovered/.userdata/mlp1:/fixture/unmounted-alternate/.userdata/mlp1" \
        "SHARED_USERDATA_PATHS=/fixture/recovered/.userdata/shared:/fixture/unmounted-alternate/.userdata/shared" \
        "MUSIC_PATHS=/fixture/recovered/Music:/fixture/unmounted-alternate/Music" \
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
