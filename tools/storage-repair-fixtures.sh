#!/bin/sh
# Stubbed checks for device/umrk-storage-repair: the real control flow against
# fake mount/fsck/sync/lock commands and fixture sysfs, devfs and procfs trees.
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
RUNNER="$REPO_DIR/device/umrk-storage-repair"
fixture=$(mktemp -d "${TMPDIR:-/tmp}/umrk-storage-repair.XXXXXX")
trap 'rm -rf "$fixture"' EXIT HUP INT TERM

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

fake_bin="$fixture/bin"
mkdir -p "$fake_bin"

cat >"$fake_bin/mount" <<'SH'
#!/bin/sh
# mount -t TYPE -o OPTS DEV MP | mount -o remount,OPTS MP
echo "mount $*" >>"$FAKE_EVENTS"
[ "${FAKE_MOUNT_FAIL:-0}" = 1 ] && [ "${1:-}" = -t ] && exit 32
if [ "${1:-}" = -o ]; then
    case "$2" in
        remount,rw) exit 0 ;;
        remount,ro)
            awk -v mp="$3" '$2 == mp { sub(/^rw/, "ro", $4) } { print }' "$FAKE_MOUNTS" >"$FAKE_MOUNTS.tmp"
            mv "$FAKE_MOUNTS.tmp" "$FAKE_MOUNTS"
            exit 0 ;;
    esac
    exit 0
fi
[ "${1:-}" = -t ] || exit 2
opts="$4"; dev="$5"; mp="$6"
case ",$opts," in *,ro,*) access=ro ;; *) access=rw ;; esac
echo "$dev $mp $2 $access,$opts 0 0" >>"$FAKE_MOUNTS"
SH

cat >"$fake_bin/umount" <<'SH'
#!/bin/sh
echo "umount $*" >>"$FAKE_EVENTS"
[ "${FAKE_UMOUNT_BUSY:-0}" = 1 ] && exit 1
awk -v mp="$1" '$2 != mp' "$FAKE_MOUNTS" >"$FAKE_MOUNTS.tmp"
mv "$FAKE_MOUNTS.tmp" "$FAKE_MOUNTS"
SH

cat >"$fake_bin/fsck.fat" <<'SH'
#!/bin/sh
echo "fsck $*" >>"$FAKE_EVENTS"
echo "fsck.fat 4.2 (2021-01-31)"
echo "Cannot initialize conversion from codepage 850 to ANSI_X3.4-1968: Invalid argument"
case "$1" in
    -a)
        [ -n "${FAKE_REPAIR_OUTPUT:-}" ] && printf '%b' "$FAKE_REPAIR_OUTPUT"
        exit "${FAKE_REPAIR_RC:-0}" ;;
    -n)
        [ "${2:-}" != -v ] || exit "${FAKE_PRECHECK_RC:-1}"
        [ -n "${FAKE_VERIFY_OUTPUT:-}" ] && printf '%b' "$FAKE_VERIFY_OUTPUT"
        exit "${FAKE_VERIFY_RC:-0}" ;;
esac
exit 2
SH

cat >"$fake_bin/timeout" <<'SH'
#!/bin/sh
# timeout -k GRACE LIMIT CMD...
shift 3
case "$*" in
    *" -a "*) [ "${FAKE_TIMEOUT_REPAIR:-0}" = 1 ] && { "$@" >/dev/null 2>&1; exit 124; } ;;
    *" -n "*) [ "${FAKE_TIMEOUT_VERIFY:-0}" = 1 ] && { "$@" >/dev/null 2>&1; exit 124; } ;;
esac
exec "$@"
SH

cat >"$fake_bin/sync" <<'SH'
#!/bin/sh
case "${1:-}" in
    */results/*.summary.tmp.*)
        [ -f "$UMRK_USBMOUNT_LOCK.lock" ] || exit 1
        [ "${FAKE_RESULT_SYNC_FAIL:-0}" != 1 ] || exit 1 ;;
    */request.tmp.*) [ "${FAKE_REQUEST_SYNC_FAIL:-0}" != 1 ] || exit 1 ;;
esac
if [ "$#" -eq 0 ]; then
    echo "sync" >>"$FAKE_EVENTS"
    [ "${FAKE_SYNC_FAIL:-0}" = 1 ] && exit 1
fi
exit 0
SH

cat >"$fake_bin/lockfile-create" <<'SH'
#!/bin/sh
eval "last=\${$#}"
[ "${FAKE_LOCK_FAIL:-0}" = 1 ] && exit 1
: >"$last.lock"
SH
cat >"$fake_bin/lockfile-remove" <<'SH'
#!/bin/sh
rm -f "$1.lock"
SH
cat >"$fake_bin/blkid" <<'SH'
#!/bin/sh
if [ "$#" -eq 0 ]; then
    printf '%b' "${FAKE_BLKID:-}"
else
    printf '%b' "${FAKE_BLKID:-}" | grep "^$1:" || true
fi
SH
cat >"$fake_bin/df" <<'SH'
#!/bin/sh
echo "Filesystem 1K-blocks Used Available Use% Mounted on"
echo "/dev/mmcblk0p12 4900000 900000 ${FAKE_DF_FREE:-3800000} 19% /userdata"
SH
cat >"$fake_bin/pidof" <<'SH'
#!/bin/sh
[ "${FAKE_FSCK_ALIVE:-0}" = 1 ] && {
    if [ "${FAKE_TIMEOUT_REPAIR:-0}" = 1 ]; then
        grep -q '^fsck -a' "$FAKE_EVENTS" || exit 1
    else
        grep -q '^fsck -n' "$FAKE_EVENTS" || exit 1
    fi
} && { echo 4242; exit 0; }
exit 1
SH
chmod 755 "$fake_bin"/*

reset_fixture() {
    root="$fixture/case"
    rm -rf "$root"
    mkdir -p "$root/state" "$root/by-uuid" "$root/sys/mmcblk1/device" "$root/sys/mmcblk3/device" \
        "$root/sys/mmcblk0" "$root/power/ac" "$root/power/usb" "$root/mnt/sdcard" \
        "$root/media/sdcard1" "$root/etc" "$root/run"
    echo SD >"$root/sys/mmcblk1/device/type"
    echo SD >"$root/sys/mmcblk3/device/type"
    echo 0 >"$root/sys/mmcblk1/ro"
    echo 0 >"$root/sys/mmcblk3/ro"
    echo 1 >"$root/power/ac/online"
    echo 0 >"$root/power/usb/online"
    ln -s ../../mmcblk1 "$root/by-uuid/22A4-0814"
    ln -s ../../mmcblk3 "$root/by-uuid/04B1-0820"
    ln -s ../../mmcblk0p12 "$root/by-uuid/166f00b1-1621-4d9f-b6cb-5ff8b0f8b13b"
    cat >"$root/mounts" <<MOUNTS
/dev/mmcblk0p12 /userdata ext4 rw,relatime 0 0
/dev/mmcblk3 $root/mnt/sdcard vfat rw,nosuid,nodev,errors=remount-ro 0 0
MOUNTS
    : >"$root/events"

    export PATH="$fake_bin:$PATH"
    export UMRK_STORAGE_REPAIR_DIR="$root/state"
    export UMRK_STORAGE_CHECKED_DIR="$root/run/checked"
    export UMRK_STORAGE_INTERNAL_MOUNT=/userdata
    export UMRK_STORAGE_HOLD_FLAG="$root/etc/umrk-storage-hold-active"
    export UMRK_FSCK_FAT="$fake_bin/fsck.fat"
    export UMRK_BY_UUID_DIR="$root/by-uuid"
    export UMRK_SYS_CLASS_BLOCK="$root/sys"
    export UMRK_PROC_MOUNTS="$root/mounts"
    export UMRK_POWER_SUPPLY_DIR="$root/power"
    export UMRK_USBMOUNT_LOCK="$root/run/.mount"
    export UMRK_STORAGE_MOUNT_POINTS="$root/mnt/sdcard $root/media/sdcard1"
    export UMRK_STORAGE_ASSUME_BLOCK=1
    export FAKE_MOUNTS="$root/mounts" FAKE_EVENTS="$root/events"
    unset FAKE_MOUNT_FAIL FAKE_UMOUNT_BUSY FAKE_REPAIR_RC FAKE_VERIFY_RC FAKE_REPAIR_OUTPUT \
        FAKE_VERIFY_OUTPUT FAKE_TIMEOUT_REPAIR FAKE_TIMEOUT_VERIFY FAKE_SYNC_FAIL FAKE_LOCK_FAIL \
        FAKE_BLKID FAKE_DF_FREE FAKE_FSCK_ALIVE FAKE_RESULT_SYNC_FAIL FAKE_REQUEST_SYNC_FAIL FAKE_PRECHECK_RC 2>/dev/null || true
    export FAKE_BLKID='/dev/mmcblk1: LABEL="MLPPRDLEAF" UUID="22A4-0814" TYPE="vfat"\n/dev/mmcblk3: LABEL="MLPPRDROMS" UUID="04B1-0820" TYPE="vfat"\n'
    STATE="$root/state"
}

request_launcher() {
    "$RUNNER" request --uuid 22A4-0814 --source launcher_sd --fs-type vfat \
        --device /dev/mmcblk1 --mode "${1:-repair}"
}

summary_value() {
    id=$(cat "$STATE/last-result")
    awk -v key="$1" 'index($0, key "=") == 1 { print substr($0, length(key) + 2) }' \
        "$STATE/results/$id.summary"
}

expect_outcome() {
    [ "$(summary_value outcome)" = "$1" ] || fail "$2: outcome $(summary_value outcome), expected $1"
    [ ! -f "$STATE/request" ] || fail "$2: request left behind"
}

expect_no_fsck() {
    ! grep -q '^fsck' "$root/events" || fail "$1: fsck ran"
}

# ── Request validation ──────────────────────────────────────────────────────
reset_fixture
if "$RUNNER" request --uuid '../x' --source launcher_sd --fs-type vfat --device /dev/mmcblk1 2>"$root/err"; then
    fail "accepted an invalid UUID"
fi
grep -q unknown-identity "$root/err" || fail "invalid UUID reason"
if "$RUNNER" request --uuid 22A4-0814 --source launcher_sd --fs-type exfat --device /dev/mmcblk1 2>"$root/err"; then
    fail "accepted exFAT"
fi
grep -q exfat-not-validated "$root/err" || fail "exFAT reason"
echo 0 >"$root/power/ac/online"
if request_launcher 2>"$root/err"; then fail "accepted a request without power"; fi
grep -q power-required "$root/err" || fail "power reason"
echo 1 >"$root/power/ac/online"
export FAKE_DF_FREE=100
if request_launcher 2>"$root/err"; then fail "accepted full internal storage"; fi
grep -q internal-storage-unavailable "$root/err" || fail "internal storage reason"
unset FAKE_DF_FREE
if "$RUNNER" request --uuid 166f00b1-1621-4d9f-b6cb-5ff8b0f8b13b --source launcher_sd \
    --fs-type vfat --device /dev/mmcblk0p12 2>"$root/err"; then
    fail "accepted internal eMMC"
fi
grep -q not-found "$root/err" || fail "internal eMMC reason"
id=$(request_launcher) || fail "valid request refused"
[ -f "$STATE/request" ] || fail "request not written"
grep -qx "state=pending" "$STATE/holds/22A4-0814" || fail "pending hold not written"
[ -e "$UMRK_STORAGE_HOLD_FLAG" ] || fail "rootfs hold flag not set"
grep -qx "request_id=$id" "$STATE/request" || fail "request id mismatch"
if request_launcher 2>"$root/err"; then fail "accepted a second request"; fi
grep -q busy "$root/err" || fail "second request reason"
[ "$("$RUNNER" gate-udev 22A4-0814)" = hold ] || fail "gate did not hold the requested card"
[ -z "$("$RUNNER" gate-udev 04B1-0820)" ] || fail "gate held an unrelated card"
"$RUNNER" pending || fail "pending not reported"

# ── Clean check ─────────────────────────────────────────────────────────────
"$RUNNER" boot >/dev/null
expect_outcome clean "clean repair"
[ "$(summary_value mount_state)" = read-write ] || fail "clean repair not mounted writable"
grep -q "^/dev/mmcblk1 $root/media/sdcard1 vfat rw," "$root/mounts" || fail "clean repair mount point"
[ ! -f "$STATE/holds/22A4-0814" ] || fail "clean repair kept the hold"
[ ! -e "$UMRK_STORAGE_HOLD_FLAG" ] || fail "rootfs hold flag not cleared"
[ ! -e "$root/run/.mount.lock" ] || fail "mount lock left held"
grep -q '^fsck -a -v /dev/mmcblk1' "$root/events" || fail "repair pass flags"
grep -q '^fsck -n /dev/mmcblk1' "$root/events" || fail "verification pass flags"

# ── Repaired, with changes parsed from the repair pass only ─────────────────
reset_fixture
echo "/dev/mmcblk1 $root/media/sdcard1 vfat ro,nosuid,nodev,errors=remount-ro 0 0" >>"$root/mounts"
request_launcher >/dev/null
export FAKE_REPAIR_RC=1
# Shapes copied from dosfstools 4.2 output on an MLP1 fixture image.
export FAKE_REPAIR_OUTPUT='FATs differ but appear to be intact.\n  Using first FAT.\n/Saves\n  Contains a free cluster (8). Assuming EOF.\n/Images/GBA/Golden Sun.png\n  Contains a free cluster (310354). Assuming EOF.\n/Images/GBA/Golden Sun.png\n  File size is 539979 bytes, cluster chain length is 0 bytes.\n  Truncating file to 0 bytes.\n/Roms/PSX/Final Fantasy VII\n  Duplicate directory entry.\n  First    Size 0 bytes, date 08:16:54 Sep 07 2026\n  Second   Size 0 bytes, date 08:16:54 Sep 07 2026\n  Auto-renaming second.\n  Renamed to FSCK0000.000\n/Old\n Start does point to root directory. Deleting dir. \nReclaiming unconnected clusters.\nReclaimed 220 unused clusters (112640 bytes) in 2 chains.\nDirty bit is set. Fs was not properly unmounted and some data may be corrupt.\n Automatically removing dirty bit.\nFree cluster summary wrong (0 vs. really 127739)\n  Auto-correcting.\n\n*** Filesystem was changed ***\nWriting changes.\n'
export FAKE_VERIFY_OUTPUT='/Images/GBA/Other.png\n  Truncating file to 0 bytes.\n'
"$RUNNER" boot >/dev/null
expect_outcome repaired "repaired"
grep -q "^umount $root/media/sdcard1" "$root/events" || fail "mounted card was not unmounted first"
[ "$(summary_value reported_changes)" = 6 ] || fail "reported change count $(summary_value reported_changes)"
[ "$(summary_value changes_complete)" = false ] || fail "repaired result claimed complete changes"
id=$(cat "$STATE/last-result")
grep -q '"kind":"truncated","path":"/Images/GBA/Golden Sun.png","new_size":0' "$STATE/results/$id.json" ||
    fail "truncation not reported"
grep -q '"kind":"renamed","path":"/Roms/PSX/Final Fantasy VII","renamed_to":"FSCK0000.000"' "$STATE/results/$id.json" || fail "rename not reported with its new name"
[ "$(grep -o '"path":"/Images/GBA/Golden Sun.png"' "$STATE/results/$id.json" | wc -l | tr -d ' ')" = 1 ] || fail "truncated file reported more than once"
grep -q '"label": "MLPPRDLEAF"' "$STATE/results/$id.json" || fail "label not recorded"
grep -q '"kind":"deleted","path":"/Old"' "$STATE/results/$id.json" || fail "deleted directory not reported"
grep -q '"kind":"salvaged","path":"/FSCK0001.REC"' "$STATE/results/$id.json" || fail "salvaged chains not reported"
grep -q '"kind":"shortened","path":"/Saves"' "$STATE/results/$id.json" || fail "free-cluster shortening not reported"
! grep -q 'Other.png' "$STATE/results/$id.json" || fail "verification proposal reported as applied"
grep -q 'Cannot initialize conversion' "$STATE/results/$id.log" || fail "full log not kept"
if command -v python3 >/dev/null 2>&1; then
    python3 -m json.tool "$STATE/results/$id.json" >/dev/null || fail "result JSON is invalid"
fi

# ── Check-only mode never reports proposals ─────────────────────────────────
reset_fixture
request_launcher check >/dev/null
export FAKE_VERIFY_RC=1
export FAKE_VERIFY_OUTPUT='/Images/GBA/Other.png\n  Truncating file to 0 bytes.\n'
"$RUNNER" boot >/dev/null
expect_outcome verify-failed "check-only dirty"
[ "$(summary_value reported_changes)" = 0 ] || fail "check-only reported changes"
! grep -q '^fsck -a' "$root/events" || fail "check-only ran a repair"
grep -qx "state=failed" "$STATE/holds/22A4-0814" || fail "check-only failure did not hold"

# ── Failures keep the hold and the card read-only ───────────────────────────
reset_fixture
request_launcher >/dev/null
export FAKE_REPAIR_RC=4
"$RUNNER" boot >/dev/null
expect_outcome failed "fatal repair exit"
grep -qx "state=failed" "$STATE/holds/22A4-0814" || fail "fatal repair lost the hold"
grep -q "^/dev/mmcblk1 .* vfat ro," "$root/mounts" || fail "failed repair not mounted read-only"
! grep -q "^/dev/mmcblk1 .* vfat rw," "$root/mounts" || fail "failed repair mounted writable"
[ -e "$UMRK_STORAGE_HOLD_FLAG" ] || fail "failed repair cleared the rootfs flag"
"$RUNNER" has-failed-hold || fail "has-failed-hold after failure"
[ "$("$RUNNER" gate-udev 22A4-0814)" = hold ] || fail "gate released a failed card"
rm "$root/by-uuid/22A4-0814"
if "$RUNNER" has-failed-hold; then fail "has-failed-hold counted a removed card"; fi
# A daemon/session restart in this boot does not retry automatically.
: >"$root/events"
ln -s ../../mmcblk1 "$root/by-uuid/22A4-0814"
"$RUNNER" boot >/dev/null
expect_no_fsck "boot after failure"

reset_fixture
request_launcher >/dev/null
export FAKE_VERIFY_RC=1
"$RUNNER" boot >/dev/null
expect_outcome verify-failed "dirty verification"
grep -qx "state=failed" "$STATE/holds/22A4-0814" || fail "dirty verification lost the hold"

reset_fixture
request_launcher >/dev/null
export FAKE_SYNC_FAIL=1
"$RUNNER" boot >/dev/null
expect_outcome failed "sync failure"
grep -q '^fsck -a' "$root/events" || fail "sync case did not repair"
! grep -q '^fsck -n /dev' "$root/events" || fail "verification ran after failed sync"

reset_fixture
request_launcher >/dev/null
echo 0 >"$root/power/ac/online"
"$RUNNER" boot >/dev/null
expect_outcome power-required "no power at boot"
expect_no_fsck "no power at boot"

reset_fixture
echo "/dev/mmcblk1 $root/media/sdcard1 vfat ro,nosuid 0 0" >>"$root/mounts"
request_launcher >/dev/null
export FAKE_UMOUNT_BUSY=1
"$RUNNER" boot >/dev/null
expect_outcome busy "busy card"
expect_no_fsck "busy card"

reset_fixture
request_launcher >/dev/null
rm "$root/by-uuid/22A4-0814"
"$RUNNER" boot >/dev/null
expect_outcome not-found "missing card"
expect_no_fsck "missing card"

# The by-uuid link still names mmcblk1, but another card is in the slot now.
reset_fixture
export FAKE_BLKID='/dev/mmcblk1: LABEL="SPARE" UUID="5B1E-77C2" TYPE="vfat"\n'
if request_launcher 2>"$root/err"; then fail "accepted a request for a replaced card"; fi
grep -q not-found "$root/err" || fail "replaced card reason"
reset_fixture
request_launcher >/dev/null
export FAKE_BLKID='/dev/mmcblk1: LABEL="SPARE" UUID="5B1E-77C2" TYPE="vfat"\n'
"$RUNNER" boot >/dev/null
expect_outcome not-found "stale UUID link"
expect_no_fsck "stale UUID link"
! grep -q '^mount -t' "$root/events" || fail "stale UUID link: mounted the replacement card"
grep -qx "state=failed" "$STATE/holds/22A4-0814" || fail "stale UUID link released the hold"

reset_fixture
request_launcher >/dev/null
export FAKE_BLKID='/dev/mmcblk1: UUID="22A4-0814" TYPE="vfat"\n/dev/mmcblk3: UUID="22A4-0814" TYPE="vfat"\n'
"$RUNNER" boot >/dev/null
expect_outcome ambiguous "duplicate UUID"
expect_no_fsck "duplicate UUID"
grep -qx "state=failed" "$STATE/holds/22A4-0814" || fail "duplicate UUID released the hold"

reset_fixture
request_launcher >/dev/null
export FAKE_BLKID='/dev/mmcblk1: UUID="22A4-0814" TYPE="exfat"\n'
"$RUNNER" boot >/dev/null
expect_outcome unsupported "changed filesystem type"
expect_no_fsck "changed filesystem type"

reset_fixture
rm "$root/by-uuid/22A4-0814"
ln -s ../../mmcblk1p1 "$root/by-uuid/22A4-0814"
export FAKE_BLKID='/dev/mmcblk1p1: UUID="22A4-0814" TYPE="vfat"\n'
"$RUNNER" request --uuid 22A4-0814 --source secondary_sd --fs-type vfat \
    --device /dev/mmcblk1p1 >/dev/null || fail "partition request refused"
"$RUNNER" boot >/dev/null
expect_outcome clean "partition card"
grep -q '^fsck -a -v /dev/mmcblk1p1' "$root/events" || fail "partition device not repaired"

reset_fixture
request_launcher >/dev/null
export FAKE_MOUNT_FAIL=1
"$RUNNER" boot >/dev/null
expect_outcome remount-failed "remount failure"
grep -qx "state=failed" "$STATE/holds/22A4-0814" || fail "remount failure lost the hold"

reset_fixture
request_launcher >/dev/null
export FAKE_TIMEOUT_REPAIR=1
"$RUNNER" boot >/dev/null
expect_outcome timed-out "timeout"
grep -qx "state=failed" "$STATE/holds/22A4-0814" || fail "timeout lost the hold"

reset_fixture
request_launcher >/dev/null
export FAKE_TIMEOUT_REPAIR=1 FAKE_FSCK_ALIVE=1
"$RUNNER" boot >/dev/null
expect_outcome timed-out "timeout with live process"
[ "$(summary_value mount_state)" = unmounted ] || fail "live fsck: card not left unmounted"
! grep -q '^mount -t' "$root/events" || fail "mount attempted while fsck alive"

# ── Interruption and malformed state ────────────────────────────────────────
reset_fixture
request_launcher >/dev/null
sed 's/^attempts=0$/attempts=1/' "$STATE/request" >"$STATE/request.new"
mv "$STATE/request.new" "$STATE/request"
"$RUNNER" boot >/dev/null
expect_outcome clean "interrupted attempt checked clean"
[ "$(summary_value origin)" = automatic-check ] || fail "interrupted repair not checked"
! grep -q '^fsck -a' "$root/events" || fail "interrupted repair repeated modifications"
grep -q '^outcome=interrupted$' "$STATE"/results/*.summary || fail "interrupted result lost"

reset_fixture
request_launcher >/dev/null
printf 'request_id=$(reboot)\nuuid=22A4-0814\n' >"$STATE/request"
# A malformed request does not authorize modification; the old hold can be checked.
"$RUNNER" boot >/dev/null
! grep -q '^fsck -a' "$root/events" || fail "malformed request modified card"
[ -f "$STATE/request.invalid" ] || fail "malformed request not set aside"

reset_fixture
request_launcher >/dev/null
export FAKE_LOCK_FAIL=1
if "$RUNNER" boot >/dev/null; then fail "boot accepted missing mount lock"; fi
[ -f "$STATE/request" ] || fail "lock failure lost request"
expect_no_fsck "mount lock unavailable"

# ── Holds without internal storage, and uninstall ───────────────────────────
reset_fixture
: >"$UMRK_STORAGE_HOLD_FLAG"
rm -rf "$STATE"
[ "$("$RUNNER" gate-udev 04B1-0820)" = hold ] || fail "gate released cards without internal state"

# Startup must present recovery whenever boot repair could not run.
reset_fixture
if "$RUNNER" has-failed-hold; then fail "has-failed-hold with no holds"; fi
request_launcher >/dev/null
export FAKE_DF_FREE=100
if "$RUNNER" boot >/dev/null; then fail "boot accepted full internal storage"; fi
expect_no_fsck "boot with full internal storage"
"$RUNNER" has-failed-hold || fail "has-failed-hold ignored a request that could not run"
unset FAKE_DF_FREE
"$RUNNER" has-failed-hold || fail "has-failed-hold ignored a pending hold"

reset_fixture
request_launcher >/dev/null
awk '$2 != "/userdata"' "$root/mounts" >"$root/mounts.new" && mv "$root/mounts.new" "$root/mounts"
if "$RUNNER" boot >/dev/null; then fail "boot accepted missing internal storage"; fi
expect_no_fsck "boot without internal storage"
"$RUNNER" has-failed-hold || fail "has-failed-hold without internal storage"

reset_fixture
request_launcher >/dev/null
"$RUNNER" uninstall-cleanup >/dev/null
[ ! -f "$STATE/request" ] && [ ! -d "$STATE/holds" ] || fail "uninstall left holds"
[ ! -e "$UMRK_STORAGE_HOLD_FLAG" ] || fail "uninstall left the rootfs flag"

# PC repair keeps the UUID. Only the next real boot should release its hold.
reset_fixture
request_launcher check >/dev/null
export FAKE_VERIFY_RC=1
"$RUNNER" boot >/dev/null
rm -rf "$UMRK_STORAGE_CHECKED_DIR"
unset FAKE_VERIFY_RC
echo 0 >"$root/power/ac/online"
: >"$root/events"
"$RUNNER" pending || fail "automatic check not advertised"
"$RUNNER" boot >/dev/null
expect_outcome clean "PC repaired same UUID"
[ "$(summary_value origin)" = automatic-check ] || fail "automatic origin missing"
[ ! -f "$STATE/holds/22A4-0814" ] || fail "PC repair kept hold"
grep -q '^fsck -n /dev/mmcblk1' "$root/events" || fail "PC repair wasn't verified"
! grep -q '^fsck -a' "$root/events" || fail "PC repair ran modifying fsck"
[ -f "$STATE/last-results/22A4-0814" ] || fail "per-card result absent"

# Battery permits an explicit check but still refuses modifying repair.
reset_fixture
echo 0 >"$root/power/ac/online"
request_launcher check >/dev/null || fail "battery check refused"
"$RUNNER" boot >/dev/null
expect_outcome clean "battery check"

# Both held cards get independent results; normal cards get no offline scan.
reset_fixture
"$RUNNER" boot >/dev/null
expect_no_fsck "healthy normal boot"
mkdir -p "$STATE/holds"
for card in 22A4-0814 04B1-0820; do
    printf 'state=failed\nrequest_id=old\n' >"$STATE/holds/$card"
done
"$RUNNER" boot >/dev/null
[ "$(grep -c '^fsck -n' "$root/events")" = 2 ] || fail "dual card check count"
for card in 22A4-0814 04B1-0820; do
    [ ! -f "$STATE/holds/$card" ] || fail "dual check kept hold"
    result=$(cat "$STATE/last-results/$card")
    grep -qx "uuid=$card" "$STATE/results/$result.summary" || fail "wrong card result"
done

# A failed result commit restores read-only access and blocks normal startup.
reset_fixture
request_launcher check >/dev/null
export FAKE_RESULT_SYNC_FAIL=1
if "$RUNNER" boot >/dev/null; then fail "result failure allowed startup"; fi
[ -f "$STATE/holds/22A4-0814" ] || fail "result failure lost hold"
! grep -q '^/dev/mmcblk1 .* vfat rw,' "$root/mounts" || fail "result failure left card writable"
[ ! -f "$UMRK_USBMOUNT_LOCK.lock" ] || fail "result failure leaked lock"

reset_fixture
mkdir -p "$STATE/holds"
printf 'state=failed\nrequest_id=older\n' >"$STATE/holds/22A4-0814"
export FAKE_REQUEST_SYNC_FAIL=1
if request_launcher check >/dev/null 2>&1; then fail "broken publication accepted"; fi
grep -qx 'request_id=older' "$STATE/holds/22A4-0814" || fail "publication replaced older hold"

# A checker surviving a read-only timeout must never be mounted underneath.
reset_fixture
request_launcher check >/dev/null
export FAKE_TIMEOUT_VERIFY=1 FAKE_FSCK_ALIVE=1
"$RUNNER" boot >/dev/null
expect_outcome timed-out "verification timeout with live checker"
[ "$(summary_value mount_state)" = unmounted ] || fail "live checker mounted"
! grep -q '^mount -t' "$root/events" || fail "mounted during verification"

reset_fixture
request_launcher >/dev/null
export FAKE_PRECHECK_RC=0
"$RUNNER" boot >/dev/null
expect_outcome clean "fresh repair already clean"
! grep -q '^fsck -a' "$root/events" || fail "already clean card modified"

# ── Paused-shutdown pre-arm ─────────────────────────────────────────────────
# A paused shutdown holds every card it could not prove closed, including one
# whose identity is gone, and keeps an older hold exactly as it was.
reset_fixture
mkdir -p "$STATE/holds"
printf 'state=failed\nrequest_id=older\n' >"$STATE/holds/22A4-0814"
"$RUNNER" pre-arm paused-shutdown 22A4-0814 04B1-0820 5555-AAAA || fail "pre-arm refused"
grep -qx 'request_id=older' "$STATE/holds/22A4-0814" || fail "pre-arm replaced an older hold"
! grep -q '^trigger=' "$STATE/holds/22A4-0814" || fail "pre-arm relabelled an older hold"
for card in 04B1-0820 5555-AAAA; do
    grep -qx 'state=unverified' "$STATE/holds/$card" || fail "pre-arm state for $card"
    grep -qx 'trigger=paused-shutdown' "$STATE/holds/$card" || fail "pre-arm trigger for $card"
done
[ -e "$UMRK_STORAGE_HOLD_FLAG" ] || fail "pre-arm did not set the rootfs hold flag"
[ ! -e "$root/run/.mount.lock" ] || fail "pre-arm leaked the mount lock"
[ "$("$RUNNER" gate-udev 04B1-0820)" = hold ] || fail "gate ignored a pre-armed card"
if "$RUNNER" pre-arm '../x' 04B1-0820 2>/dev/null; then fail "pre-arm accepted a bad trigger"; fi
if "$RUNNER" pre-arm paused-shutdown '../x' 2>/dev/null; then fail "pre-arm reported a bad UUID durable"; fi

# The next boot checks a pre-armed card read-only, releases it when clean and
# records why it was held.
rm -f "$STATE/holds/22A4-0814" "$STATE/holds/5555-AAAA"
"$RUNNER" boot >/dev/null
expect_outcome clean "pre-armed card check"
[ "$(summary_value trigger)" = paused-shutdown ] || fail "pre-arm trigger not in the result"
[ "$(summary_value origin)" = automatic-check ] || fail "pre-armed check origin"
[ ! -f "$STATE/holds/04B1-0820" ] || fail "clean pre-armed card kept its hold"
grep -q '^fsck -n /dev/mmcblk3' "$root/events" || fail "pre-armed card not checked read-only"
! grep -q '^fsck -a' "$root/events" || fail "pre-armed card was repaired automatically"

# Without writable internal storage nothing is claimed durable.
reset_fixture
export FAKE_DF_FREE=100
if "$RUNNER" pre-arm paused-shutdown 04B1-0820 2>/dev/null; then
    fail "pre-arm claimed success without internal storage"
fi
unset FAKE_DF_FREE

echo "storage repair fixtures: PASS"
