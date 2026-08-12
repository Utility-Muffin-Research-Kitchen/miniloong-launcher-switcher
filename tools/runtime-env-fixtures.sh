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
[ "$legacy_projection" = "1369841018 3345" ] || {
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
    "VIDEO_PATHS=$primary/Videos:$secondary/Videos" \
    "RECORDINGS_PATH=$primary/Recordings" \
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
            'export ROMS_PATH=/fixture/stale/Roms' \
            'export IMAGES_PATH=/fixture/stale/Images' \
            'export MUSIC_PATH=/fixture/stale/Music' \
            'export VIDEO_PATH=/fixture/stale/Videos' \
            'export RECORDINGS_PATH=/fixture/stale/Recordings' \
            'export APPS_PATH=/fixture/stale/Apps' \
            'export BIOS_PATH=/fixture/stale/BIOS' \
            'export SAVES_PATH=/fixture/stale/Saves' \
            'export STATES_PATH=/fixture/stale/States' \
            'export CHEATS_PATH=/fixture/stale/Cheats' \
            'export UMRK_ENV_VERSION=1' \
            'set_active_launcher_sd /fixture/recovered /fixture/unmounted-alternate' \
            'env'
    } >"$snippet"
    output="$(sh "$snippet")"
    rm -f "$snippet"
    for expected in \
        "SDCARD_PATHS=/fixture/recovered:/fixture/unmounted-alternate" \
        "USERDATA_PATHS=/fixture/recovered/.userdata/mlp1:/fixture/unmounted-alternate/.userdata/mlp1" \
        "SHARED_USERDATA_PATHS=/fixture/recovered/.userdata/shared:/fixture/unmounted-alternate/.userdata/shared" \
        "ROMS_PATH=/fixture/recovered/Roms" \
        "IMAGES_PATH=/fixture/recovered/Images" \
        "MUSIC_PATH=/fixture/recovered/Music" \
        "VIDEO_PATH=/fixture/recovered/Videos" \
        "RECORDINGS_PATH=/fixture/recovered/Recordings" \
        "APPS_PATH=/fixture/recovered/Apps" \
        "BIOS_PATH=/fixture/recovered/BIOS" \
        "SAVES_PATH=/fixture/recovered/Saves" \
        "STATES_PATH=/fixture/recovered/States" \
        "CHEATS_PATH=/fixture/recovered/Cheats" \
        "UMRK_ENV_VERSION=2" \
        "ROMS_PATHS=/fixture/recovered/Roms:/fixture/unmounted-alternate/Roms" \
        "IMAGES_PATHS=/fixture/recovered/Images:/fixture/unmounted-alternate/Images" \
        "MUSIC_PATHS=/fixture/recovered/Music:/fixture/unmounted-alternate/Music" \
        "VIDEO_PATHS=/fixture/recovered/Videos:/fixture/unmounted-alternate/Videos" \
        "APPS_PATHS=/fixture/recovered/Apps:/fixture/unmounted-alternate/Apps" \
        "BIOS_PATHS=/fixture/recovered/BIOS:/fixture/unmounted-alternate/BIOS" \
        "SAVES_PATHS=/fixture/recovered/Saves:/fixture/unmounted-alternate/Saves" \
        "STATES_PATHS=/fixture/recovered/States:/fixture/unmounted-alternate/States" \
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
