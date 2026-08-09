#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
fixture=$(mktemp -d "${TMPDIR:-/tmp}/umrk-mount-stubs.XXXXXX")
trap 'rm -rf "$fixture"' EXIT HUP INT TERM

fake_bin="$fixture/bin"
root_view="$fixture/root-view"
state="$fixture/immutable"
mkdir -p "$fake_bin" "$root_view/mnt/sdcard/stranded" "$root_view/media/sdcard1"
: >"$state"

cat >"$fake_bin/mount" <<'EOF'
#!/bin/sh
exit 0
EOF
cat >"$fake_bin/umount" <<'EOF'
#!/bin/sh
exit 0
EOF
cat >"$fake_bin/chattr" <<'EOF'
#!/bin/sh
set -eu
mode=$1
shift
state=${UMRK_FIXTURE_STATE:?}
for target do
    [ "${UMRK_FIXTURE_FAIL_PATH:-}" != "$target" ] || exit 1
    case "$mode" in
        +i)
            grep -Fqx "$target" "$state" 2>/dev/null || printf '%s\n' "$target" >>"$state"
            ;;
        -i)
            temporary="$state.tmp.$$"
            grep -Fvx "$target" "$state" >"$temporary" 2>/dev/null || true
            mv "$temporary" "$state"
            ;;
        *) exit 2 ;;
    esac
done
EOF
cat >"$fake_bin/lsattr" <<'EOF'
#!/bin/sh
set -eu
[ "${1:-}" = -d ] && shift
target=$1
if grep -Fqx "$target" "${UMRK_FIXTURE_STATE:?}"; then
    printf '%s %s\n' '----i---------e-------' "$target"
else
    printf '%s %s\n' '----------------------' "$target"
fi
EOF
chmod 755 "$fake_bin"/*

PATH="$fake_bin:$PATH"
export PATH UMRK_FIXTURE_STATE="$state" UMRK_ROOT_VIEW="$root_view"
helper="$REPO_DIR/device/umrk-mount-stubs"

"$helper" lock
"$helper" status >"$fixture/locked-status"
grep -q '^/mnt/sdcard immutable$' "$fixture/locked-status"
grep -q '^/media/sdcard1 immutable$' "$fixture/locked-status"

"$helper" unlock
if "$helper" status >"$fixture/unlocked-status" 2>&1; then
    echo "status accepted mutable mount stubs" >&2
    exit 1
fi
grep -q '^/mnt/sdcard mutable$' "$fixture/unlocked-status"

"$helper" lock
"$helper" status >/dev/null

export UMRK_FIXTURE_FAIL_PATH="$root_view/mnt/sdcard/stranded"
if "$helper" unlock >"$fixture/unlock-failure" 2>&1; then
    echo "unlock accepted a nested chattr failure" >&2
    exit 1
fi
grep -Fq "cannot clear rootfs stub immutability: /mnt/sdcard" \
    "$fixture/unlock-failure"
grep -Fqx "$UMRK_FIXTURE_FAIL_PATH" "$state"
unset UMRK_FIXTURE_FAIL_PATH
"$helper" unlock

: >"$state"
export UMRK_FIXTURE_FAIL_PATH="$root_view/mnt/sdcard/stranded"
if "$helper" lock >"$fixture/lock-failure" 2>&1; then
    echo "lock accepted a nested chattr failure" >&2
    exit 1
fi
grep -Fq "cannot make rootfs stub immutable: /mnt/sdcard" \
    "$fixture/lock-failure"
unset UMRK_FIXTURE_FAIL_PATH

echo "mount stub fixtures: PASS"
