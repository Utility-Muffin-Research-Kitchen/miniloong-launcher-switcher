#!/bin/sh
# Ensure IPv4 comes up after Wi-Fi association in Leaf mode.
#
# Stock dhcpcd can associate and configure IPv6 but exit before installing the
# DHCPv4 lease. Jawaka's Wi-Fi settings path kicks udhcpc after explicit
# connect/recover actions; this boot hook covers the passive reboot case where
# wpa_supplicant reconnects to a saved network on its own.
#
# Neither of those paths covers waking from suspend: the kernel resumes the
# radio and wpa_supplicant silently reassociates (possibly to a *different*
# saved network than the one active before sleep) without going through
# Jawaka's UI and without a reboot, so nothing re-requests a lease. The
# interface is left holding whatever IPv4 address (and routes) it had before
# suspending — wpa_state reports COMPLETED, so the UI shows connected, but the
# address is stale and traffic doesn't route. This is invisible until the
# user manually disconnects/reconnects through Jawaka. platform.d hooks only
# run once per session start (see run_platform_hooks in umrk-leaf-session), so
# resume_watch_loop below is a long-lived background daemon rather than a
# one-shot check, watching for the kernel's own resume record on /dev/kmsg.

IFACE="${UMRK_WIFI_IFACE:-wlan0}"
WAIT_SECONDS="${UMRK_WIFI_DHCP_WAIT_SECONDS:-75}"
GRACE_SECONDS="${UMRK_WIFI_DHCP_GRACE_SECONDS:-12}"
DHCP_TRIES="${UMRK_WIFI_DHCP_TRIES:-20}"
PIDFILE="/tmp/umrk-wifi-dhcpv4.pid"
# Off-intent marker written by Jawaka when the user turns Wi-Fi off. Persists in
# the platform state dir so the radio stays off across reboots.
WIFI_DISABLED_MARKER="${UMRK_WIFI_DISABLED_MARKER:-${UMRK_INTERNAL_DATA_PATH:-}/wifi-disabled}"
# Resume-watch tunables. Kept separate from the boot-path ones above so a
# device profile can tune association wait vs. resume settle independently.
RESUME_PIDFILE="/tmp/umrk-wifi-resume-watch.pid"
RESUME_SETTLE_SECONDS="${UMRK_WIFI_RESUME_SETTLE_SECONDS:-20}"
RESUME_MARK="PM: suspend exit"
# This device's deep suspend resets CLOCK_MONOTONIC to near-zero on resume
# instead of pausing it (visible as kernel log timestamps jumping from
# thousands of seconds back to ~0 across the same suspend/resume pair), and
# the Realtek RTL8723DS driver has logged internal scan-queue errors
# ("Free disconnecting network of scanned_queue failed due to pwlan ==
# NULL") during the same suspend/resume window. Either can leave
# wpa_supplicant wedged in wpa_state=SCANNING with no self-recovery — and in
# practice, even a *freshly restarted* wpa_supplicant process (new PID, no
# leftover timer state) has stayed wedged for several minutes afterward, so
# this isn't purely a wpa_supplicant-side problem; the radio/driver itself
# can need real time (or repeated nudges) to come back after a resume.
# RECONNECT_KICK_SECONDS/RESTART_SETTLE_SECONDS size each individual
# recovery attempt below; MAX_RECOVERY_SECONDS bounds how long the loop in
# resume_reconnect keeps retrying before giving up.
RECONNECT_KICK_SECONDS="${UMRK_WIFI_RECONNECT_KICK_SECONDS:-10}"
RESTART_SETTLE_SECONDS="${UMRK_WIFI_RESTART_SETTLE_SECONDS:-20}"
MAX_RECOVERY_SECONDS="${UMRK_WIFI_MAX_RECOVERY_SECONDS:-180}"
WPA_SUPPLICANT_CONF="${UMRK_WPA_SUPPLICANT_CONF:-/var/run/wpa_supplicant/wpa_supplicant.conf}"
WPA_SUPPLICANT_PIDFILE="${UMRK_WPA_SUPPLICANT_PIDFILE:-/run/wpa_supplicant.${IFACE}.pid}"

has_ipv4() {
    ip -4 addr show "$IFACE" 2>/dev/null | grep -q ' inet '
}

wpa_state() {
    wpa_cli -i "$IFACE" status 2>/dev/null | sed -n 's/^wpa_state=//p' | head -n 1
}

# Dump association/link detail so a failed connect is diagnosable from the SD
# log without live ADB. Filters the passphrase out of wpa_cli status.
dump_wifi_diag() {
    echo "wifi-dhcpv4: --- diag ($1) ---"
    wpa_cli -i "$IFACE" status 2>/dev/null |
        grep -ivE '^(psk|sae_password|password|pmk)=' |
        sed 's/^/wifi-dhcpv4: status: /'
    ip -4 addr show "$IFACE" 2>/dev/null | sed 's/^/wifi-dhcpv4: addr: /'
    echo "wifi-dhcpv4: --- end diag ---"
}

# True if the user turned Wi-Fi off (marker present). Guarded so an unset state
# path never matches a stray "/wifi-disabled".
wifi_off_intended() {
    [ -n "${UMRK_INTERNAL_DATA_PATH:-}" ] && [ -e "$WIFI_DISABLED_MARKER" ]
}

# Keep the radio off: stock S40network may have re-upped wlan0 and reconnected
# before this hook runs (it is S40, we are inside S50leaf), so undo that. No
# stock watchdog runs in Leaf mode, so the interface-down sticks.
enforce_wifi_off() {
    echo "wifi-dhcpv4: Wi-Fi disabled by user setting; keeping radio off"
    command -v wpa_cli >/dev/null 2>&1 &&
        wpa_cli -i "$IFACE" disconnect >/dev/null 2>&1
    pids="$(pidof wpa_supplicant 2>/dev/null || true)"
    [ -n "$pids" ] && kill $pids 2>/dev/null || true
    command -v ifconfig >/dev/null 2>&1 &&
        ifconfig "$IFACE" down 2>/dev/null || true
}

# Kill any udhcpc instances already bound to $IFACE. Used before both the
# initial lease request and every resume-triggered renewal so a stale client
# from a prior association (or a prior resume) never races a fresh one.
kill_stale_udhcpc() {
    pids="$(pgrep -f "udhcpc .*-i $IFACE" 2>/dev/null || true)"
    [ -n "$pids" ] && kill $pids 2>/dev/null || true
}

run_worker() {
    i=0
    trap 'rm -f "$PIDFILE"' EXIT INT TERM

    if ! command -v ip >/dev/null 2>&1 ||
       ! command -v wpa_cli >/dev/null 2>&1 ||
       ! command -v udhcpc >/dev/null 2>&1; then
        echo "wifi-dhcpv4: missing ip, wpa_cli, or udhcpc; skipping"
        return 0
    fi

    while [ "$i" -lt "$WAIT_SECONDS" ]; do
        if has_ipv4; then
            echo "wifi-dhcpv4: $IFACE already has IPv4"
            return 0
        fi

        state="$(wpa_state)"
        if [ "$state" = "COMPLETED" ]; then
            break
        fi

        sleep 1
        i=$((i + 1))
    done

    if [ "$(wpa_state)" != "COMPLETED" ]; then
        echo "wifi-dhcpv4: $IFACE did not associate within ${WAIT_SECONDS}s; skipping DHCPv4"
        dump_wifi_diag "assoc-timeout"
        return 0
    fi

    if has_ipv4; then
        echo "wifi-dhcpv4: $IFACE already has IPv4 after association"
        return 0
    fi

    i=0
    while [ "$i" -lt "$GRACE_SECONDS" ]; do
        sleep 1
        if has_ipv4; then
            echo "wifi-dhcpv4: $IFACE got IPv4 from stock DHCP during grace period"
            return 0
        fi
        i=$((i + 1))
    done

    echo "wifi-dhcpv4: requesting DHCPv4 lease on $IFACE"
    udhcpc -t "$DHCP_TRIES" -n -i "$IFACE"
    rc=$?

    if has_ipv4; then
        echo "wifi-dhcpv4: IPv4 ready on $IFACE"
        ip -4 addr show "$IFACE" 2>/dev/null | sed 's/^/wifi-dhcpv4: /'
        ip -4 route 2>/dev/null | sed 's/^/wifi-dhcpv4: /'
    else
        echo "wifi-dhcpv4: DHCPv4 did not install an address on $IFACE (rc=$rc)"
        dump_wifi_diag "dhcp-fail"
    fi
}

# Jawaka's own manual "connect to this network" path (jw_wifi_connect in
# wifi_mlp1.c) uses `select_network <id>`, which per wpa_supplicant semantics
# disables every *other* configured network as a side effect — then Jawaka
# calls `save_config`, persisting that to wpa_supplicant.conf on disk. So
# connecting to the hotspot leaves the home network saved as disabled=1, and
# vice versa. That's not a timer/driver problem at all: `reconnect` only
# considers enabled networks, so no amount of kicking or restarting
# wpa_supplicant can bring back a network its own saved config has marked
# disabled — a restart reloads that exact same file. Jawaka has its own
# recovery function for this (jw_wifi_recover) and its first step is
# `enable_network all` before reconnecting; do the same here, unconditionally
# and before anything else, since it's cheap and is the actual fix rather
# than a nudge. save_config persists the re-enable back to
# wpa_supplicant.conf itself (mirroring Jawaka's own connect path, which
# saves after every select_network) — without it, restart_wpa_supplicant's
# later daemon restart would just reload the same disabled entry off disk
# and undo this.
reenable_all_networks() {
    wpa_cli -i "$IFACE" enable_network all >/dev/null 2>&1
    wpa_cli -i "$IFACE" save_config >/dev/null 2>&1
}

# Nudge a wedged wpa_supplicant back into scanning/associating without a full
# restart. Cheap, and sufficient for the milder cases.
kick_reconnect() {
    echo "wifi-dhcpv4: resume: $IFACE stuck in $(wpa_state); nudging with wpa_cli reconnect"
    reenable_all_networks
    wpa_cli -i "$IFACE" reconnect >/dev/null 2>&1
}

# Full reset: wpa_supplicant's scan/retry timers are scheduled off
# CLOCK_MONOTONIC, and this device's suspend resets that clock instead of
# pausing it, which can wedge the daemon in wpa_state=SCANNING with no
# self-recovery. Restarting it re-reads the same saved config from disk (no
# data loss) and gives it a fresh timer baseline against the post-resume
# clock. wpa_cli reconnect alone (kick_reconnect) does not help when the
# daemon's own timer loop is the thing that's stuck.
#
# Restarting wpa_supplicant alone is not always enough: this device's Realtek
# RTL8723DS driver has logged "Free disconnecting network of scanned_queue
# failed due to pwlan == NULL" during suspend, which is the kernel driver's
# own internal scan-queue state, not wpa_supplicant's. A userspace daemon
# restart can't fix a stuck kernel driver — it just issues new scan requests
# to the same broken queue and gets the same non-answer. Cycling the netdev
# itself (down/up) forces the driver to tear down and rebuild that state,
# so it runs first, before wpa_supplicant is restarted against a clean
# interface.
reset_wifi_interface() {
    echo "wifi-dhcpv4: resume: cycling $IFACE to clear driver-level scan state"
    ip link set "$IFACE" down 2>/dev/null || true
    sleep 2
    ip link set "$IFACE" up 2>/dev/null || true
    sleep 2
}

restart_wpa_supplicant() {
    echo "wifi-dhcpv4: resume: $IFACE still stuck in $(wpa_state) after reconnect kick; restarting wpa_supplicant"
    pids="$(pidof wpa_supplicant 2>/dev/null || true)"
    [ -n "$pids" ] && kill $pids 2>/dev/null || true
    i=0
    while [ -n "$(pidof wpa_supplicant 2>/dev/null || true)" ] && [ "$i" -lt 5 ]; do
        sleep 1
        i=$((i + 1))
    done
    reset_wifi_interface
    wpa_supplicant -B -i "$IFACE" -c "$WPA_SUPPLICANT_CONF" -P "$WPA_SUPPLICANT_PIDFILE" >/dev/null 2>&1
}

# Force a fresh DHCPv4 lease after a resume, regardless of whether $IFACE
# already appears to have an address. A stale-but-present lease from before
# suspend is exactly the failure mode this loop exists to catch, so
# has_ipv4() (which only asks "is there any address", not "is it valid for
# the network we're on now") can't gate this the way it gates run_worker's
# boot-time path. Re-associating to the same network still gets a cheap,
# harmless renewal.
resume_reconnect() {
    # Unconditional and first: see reenable_all_networks above for why. If the
    # network that was active before suspend got disabled by a select_network
    # elsewhere (e.g. switching to/from a different saved network), nothing
    # below this line would ever be able to reconnect to it otherwise.
    reenable_all_networks

    i=0
    while [ "$i" -lt "$RESUME_SETTLE_SECONDS" ]; do
        [ "$(wpa_state)" = "COMPLETED" ] && break
        sleep 1
        i=$((i + 1))
    done
    total_elapsed=$i

    # A single kick+restart pass was not always enough in practice: a
    # brand-new wpa_supplicant process (fresh timers, fresh config re-read)
    # has still sat wedged for several minutes after some resumes before
    # clearing on its own or via a manual reconnect through Jawaka. Since a
    # kick or restart is cheap and harmless if the radio isn't ready yet,
    # keep retrying — escalating from a soft kick to a full interface+daemon
    # restart — for up to MAX_RECOVERY_SECONDS rather than giving up after
    # one pass, so this loop covers "just needed more time" as well as
    # "needed an explicit nudge" without having to know which one it is.
    attempt=0
    while [ "$(wpa_state)" != "COMPLETED" ] && [ "$total_elapsed" -lt "$MAX_RECOVERY_SECONDS" ]; do
        if wifi_off_intended; then
            echo "wifi-dhcpv4: resume: Wi-Fi turned off mid-recovery; stopping retries"
            return 0
        fi

        attempt=$((attempt + 1))
        if [ "$attempt" -eq 1 ]; then
            kick_reconnect
            wait_secs="$RECONNECT_KICK_SECONDS"
        else
            restart_wpa_supplicant
            wait_secs="$RESTART_SETTLE_SECONDS"
        fi

        i=0
        while [ "$i" -lt "$wait_secs" ]; do
            [ "$(wpa_state)" = "COMPLETED" ] && break
            sleep 1
            i=$((i + 1))
        done
        total_elapsed=$((total_elapsed + i))
    done

    if [ "$(wpa_state)" != "COMPLETED" ]; then
        echo "wifi-dhcpv4: resume: $IFACE did not reassociate after ${total_elapsed}s across $attempt recovery attempt(s)"
        dump_wifi_diag "resume-assoc-timeout"
        return 0
    fi

    echo "wifi-dhcpv4: resume: $IFACE reassociated after ${total_elapsed}s ($attempt recovery attempt(s)); renewing DHCPv4 lease"
    kill_stale_udhcpc
    udhcpc -t "$DHCP_TRIES" -n -i "$IFACE"
    rc=$?

    if has_ipv4; then
        echo "wifi-dhcpv4: resume: IPv4 ready on $IFACE"
        ip -4 addr show "$IFACE" 2>/dev/null | sed 's/^/wifi-dhcpv4: resume: /'
    else
        echo "wifi-dhcpv4: resume: DHCPv4 did not install an address on $IFACE (rc=$rc)"
        dump_wifi_diag "resume-dhcp-fail"
    fi
}

# Long-lived: blocks on /dev/kmsg for the kernel's own suspend-exit record and
# re-checks DHCP each time. A fresh /dev/kmsg open may first replay whatever
# is still in the ring buffer (e.g. this boot's own entry, or a stale one if
# the hook is (re)started while the system is already up) before blocking on
# genuinely new records — a spurious extra renewal from that is harmless.
resume_watch_loop() {
    trap 'rm -f "$RESUME_PIDFILE"' EXIT INT TERM

    if ! command -v ip >/dev/null 2>&1 ||
       ! command -v wpa_cli >/dev/null 2>&1 ||
       ! command -v udhcpc >/dev/null 2>&1 ||
       [ ! -r /dev/kmsg ]; then
        echo "wifi-dhcpv4: resume-watch: missing ip, wpa_cli, udhcpc, or /dev/kmsg; not watching"
        return 0
    fi

    while IFS= read -r kmsg_line; do
        case "$kmsg_line" in
            *"$RESUME_MARK"*)
                if wifi_off_intended; then
                    echo "wifi-dhcpv4: resume-watch: Wi-Fi off by user setting; skipping renewal"
                    continue
                fi
                echo "wifi-dhcpv4: resume-watch: resume detected, checking $IFACE"
                resume_reconnect
                ;;
        esac
    done < /dev/kmsg
}

# Honor the off-intent before doing any DHCP work: keep the radio off and bail.
if wifi_off_intended; then
    enforce_wifi_off
    exit 0
fi

old_pid="$(cat "$PIDFILE" 2>/dev/null || true)"
if [ -n "$old_pid" ] && [ -d "/proc/$old_pid" ]; then
    exit 0
fi

run_worker &
echo "$!" > "$PIDFILE" 2>/dev/null || true

old_resume_pid="$(cat "$RESUME_PIDFILE" 2>/dev/null || true)"
if [ -z "$old_resume_pid" ] || [ ! -d "/proc/$old_resume_pid" ]; then
    resume_watch_loop &
    echo "$!" > "$RESUME_PIDFILE" 2>/dev/null || true
fi

exit 0
