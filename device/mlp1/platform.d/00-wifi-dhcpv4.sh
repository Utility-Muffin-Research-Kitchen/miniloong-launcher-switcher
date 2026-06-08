#!/bin/sh
# Ensure IPv4 comes up after Wi-Fi association in Leaf mode.
#
# Stock dhcpcd can associate and configure IPv6 but exit before installing the
# DHCPv4 lease. Jawaka's Wi-Fi settings path kicks udhcpc after explicit
# connect/recover actions; this boot hook covers the passive reboot case where
# wpa_supplicant reconnects to a saved network on its own.

IFACE="${UMRK_WIFI_IFACE:-wlan0}"
WAIT_SECONDS="${UMRK_WIFI_DHCP_WAIT_SECONDS:-75}"
GRACE_SECONDS="${UMRK_WIFI_DHCP_GRACE_SECONDS:-12}"
DHCP_TRIES="${UMRK_WIFI_DHCP_TRIES:-20}"
PIDFILE="/tmp/umrk-wifi-dhcpv4.pid"
# Off-intent marker written by Jawaka when the user turns Wi-Fi off. Persists in
# the platform state dir so the radio stays off across reboots.
WIFI_DISABLED_MARKER="${UMRK_WIFI_DISABLED_MARKER:-${UMRK_INTERNAL_DATA_PATH:-}/wifi-disabled}"

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
exit 0
