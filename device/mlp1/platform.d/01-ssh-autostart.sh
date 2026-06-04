#!/bin/sh
# Start the Dropbear SSH server if it was previously configured.
# Runs as a platform.d boot hook — the launcher switcher wrapper executes
# this before Jawaka starts. Config and host keys are owned by the SSH
# server app under the first-SD userdata root.

PLATFORM="${PLATFORM:-mlp1}"
SDCARD_PATH="${SDCARD_PATH:-/mnt/sdcard}"
USERDATA_DIR="${USERDATA_PATH:-$SDCARD_PATH/.system/leaf/userdata/$PLATFORM}"
SSH_STATE_ROOT="${UMRK_SSH_STATE_DIR:-$USERDATA_DIR/umrk-ssh-server}"
APPS_ROOT="${APPS_PATH:-${SDCARD_PATH:-/mnt/sdcard}/Apps}"

SSH_CONFIG="$SSH_STATE_ROOT/config.ini"
SSH_HOSTKEYS="$SSH_STATE_ROOT/hostkeys"
SSH_LOG="$SSH_STATE_ROOT/logs/dropbear-autostart.log"
SSH_RUN_DIR="$SSH_STATE_ROOT/run"
SSH_PIDFILE="$SSH_RUN_DIR/dropbear.pid"

# Only start if the app has been configured at least once.
if [ ! -f "$SSH_CONFIG" ]; then
    return 0 2>/dev/null || exit 0
fi

# Find Dropbear — bundled in the SSH server app pak, or on PATH.
DROPBEAR=""
for candidate in \
    "$APPS_ROOT/SSHServer.pak/runtime/bin/dropbear" \
    /usr/sbin/dropbear \
    /usr/bin/dropbear; do
    if [ -x "$candidate" ]; then
        DROPBEAR="$candidate"
        break
    fi
done

if [ -z "$DROPBEAR" ]; then
    return 0 2>/dev/null || exit 0
fi

# Don't start if already running.
if pidof dropbear >/dev/null 2>&1; then
    return 0 2>/dev/null || exit 0
fi

# Ensure host keys exist.
if [ ! -f "$SSH_HOSTKEYS/dropbear_ed25519_host_key" ]; then
    return 0 2>/dev/null || exit 0
fi

# Read port from config (default 2222). Format: bind_address=0.0.0.0:PORT
PORT=$(grep '^bind_address=' "$SSH_CONFIG" 2>/dev/null | grep -o ':[0-9]*$' | tr -d ':')
PORT="${PORT:-2222}"

mkdir -p "$SSH_RUN_DIR" "${SSH_LOG%/*}" 2>/dev/null || true
"$DROPBEAR" -r "$SSH_HOSTKEYS/dropbear_ed25519_host_key" \
    -r "$SSH_HOSTKEYS/dropbear_rsa_host_key" \
    -p "$PORT" -P "$SSH_PIDFILE" -B >>"$SSH_LOG" 2>&1
