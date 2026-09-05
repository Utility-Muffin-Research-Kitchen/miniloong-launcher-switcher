#!/usr/bin/env python3
"""Run the real shell control flow with fake radio commands and proc records."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = (ROOT / "device/mlp1/platform.d/00-wifi-dhcpv4.sh").read_text()
DEFINITIONS, STARTUP = HOOK.split("# Separate invocations", 1)
SESSION = (ROOT / "device/umrk-leaf-session").read_text()
MOCKS = r'''
record() { echo "$*" >> "$TEST_ROOT/events"; }
wpa_cli() { record "wpa_cli $*"; }
wpa_state() { cat "$TEST_ROOT/state"; }
wpa_supplicant() {
    record supplicant-start
    touch "$TEST_ROOT/radio-up"
    echo COMPLETED > "$TEST_ROOT/state"
    [ "$OFF_AT" != start ] || touch "$WIFI_DISABLED_MARKER"
    return 0
}
ip() {
    record "ip $*"
    case "$*" in
        'link set wlan0 down') rm -f "$TEST_ROOT/radio-up" ;;
        'link set wlan0 up') touch "$TEST_ROOT/radio-up" ;;
    esac
}
ifconfig() { record "ifconfig $*"; rm -f "$TEST_ROOT/radio-up"; }
udhcpc() { record dhcp; touch "$TEST_ROOT/lease"; }
has_ipv4() { test -f "$TEST_ROOT/lease"; }
pidof() {
    case "$1" in
        wpa_supplicant) [ ! -f "$TEST_ROOT/old-wpa" ] || echo 99 ;;
        udhcpc) echo '401 402 403' ;;
    esac
}
kill() {
    record "kill $*"
    if [ "$*" = '-9 99' ] && [ "$STUCK" != 1 ]; then
        rm -f "$TEST_ROOT/old-wpa"
    fi
}
sleep_count=0
sleep() {
    if [ "$1" = 2 ]; then
        sleep_count=$((sleep_count + 1))
        [ "$OFF_AT" != "sleep-$sleep_count" ] || touch "$WIFI_DISABLED_MARKER"
    fi
}
'''


def session_function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", SESSION, re.M | re.S)[0]


class WifiResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wifi-resume-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {
            **os.environ,
            "TEST_ROOT": str(self.root),
            "TMPDIR": str(self.root),
            "UMRK_INTERNAL_DATA_PATH": str(self.root),
            "UMRK_WIFI_DISABLED_MARKER": str(self.root / "wifi-disabled"),
            "UMRK_WIFI_RESUME_SETTLE_SECONDS": "1",
            "UMRK_WIFI_RECONNECT_KICK_SECONDS": "1",
            "UMRK_WIFI_RESTART_SETTLE_SECONDS": "1",
            "UMRK_WIFI_MAX_RECOVERY_SECONDS": "4",
            "UMRK_WIFI_DHCP_GRACE_SECONDS": "0",
            "OFF_AT": "",
            "STUCK": "0",
        }
        (self.root / "state").write_text("DISCONNECTED\n")
        self.proc(401, "/sbin/udhcpc", "-i", "wlan0")
        self.proc(402, "/sbin/udhcpc", "-i", "wlan01")
        self.proc(403, "/sbin/udhcpc", "-iwlan0")

    def proc(self, pid, *args):
        directory = self.root / "proc" / str(pid)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "cmdline").write_bytes(b"\0".join(a.encode() for a in args) + b"\0")

    def run_shell(self, body, *, startup=False):
        source = DEFINITIONS + MOCKS + body
        if startup:
            source += "\n# Separate invocations" + STARTUP
        # Redirect only proc reads into fixtures; production needs no test switches.
        source = source.replace("/proc/", f"{self.root}/proc/")
        script = self.root / "00-wifi-dhcpv4.sh"
        script.write_text(source)
        script.chmod(0o755)
        result = subprocess.run([str(script)], env=self.env, text=True,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def events(self):
        path = self.root / "events"
        return path.read_text().splitlines() if path.exists() else []

    def test_off_at_boot_still_starts_watcher(self):
        (self.root / "wifi-disabled").touch()
        self.run_shell('''
run_worker() { record boot; }
resume_watch_loop() { record watcher; }
''', startup=True)
        self.assertIn("watcher", self.events())
        self.assertNotIn("boot", self.events())
        self.assertNotIn("dhcp", self.events())

    def test_worker_identity_and_independent_startup(self):
        self.proc(101, "/bin/sh", "/old/platform.d/00-wifi-dhcpv4.sh", "--boot-worker")
        self.proc(102, "sleep", "1000")  # A reused watcher PID.
        (self.root / "umrk-wifi-dhcpv4.pid").write_text("101\n")
        (self.root / "umrk-wifi-resume-watch.pid").write_text("102\n")
        self.run_shell('''
run_worker() { record boot; }
resume_watch_loop() { record watcher; }
''', startup=True)
        self.assertEqual(self.events(), ["watcher"])
        self.proc(102, "/bin/sh", "/old/platform.d/00-wifi-dhcpv4.sh", "--resume-watch")
        self.run_shell('''
worker_running 102 --resume-watch || exit 1
worker_running 101 --resume-watch && exit 1
worker_running invalid --resume-watch && exit 1
exit 0
''')

    def test_both_lease_paths_replace_only_matching_dhcp_clients(self):
        (self.root / "state").write_text("COMPLETED\n")
        for call in ("run_worker", "resume_reconnect"):
            with self.subTest(call=call):
                # The second request must run even with the first lease present.
                self.run_shell(call)
                self.assertIn("kill 401", self.events())
                self.assertIn("kill 403", self.events())
                self.assertNotIn("kill 402", self.events())
                self.assertIn("dhcp", self.events())
                (self.root / "events").unlink()

    def test_turning_off_during_recovery_leaves_radio_off(self):
        for point in ("sleep-1", "sleep-2", "start", "dhcp"):
            with self.subTest(point=point):
                self.env["OFF_AT"] = point
                (self.root / "state").write_text("DISCONNECTED\n")
                (self.root / "wifi-disabled").unlink(missing_ok=True)
                (self.root / "events").unlink(missing_ok=True)
                body = "resume_reconnect"
                if point == "dhcp":
                    body = 'kill_stale_udhcpc() { touch "$WIFI_DISABLED_MARKER"; }\n' + body
                self.run_shell(body)
                self.assertTrue((self.root / "wifi-disabled").exists())
                self.assertFalse((self.root / "radio-up").exists())
                self.assertNotIn("dhcp", self.events())
                if point.startswith("sleep"):
                    self.assertNotIn("supplicant-start", self.events())

    def test_restart_waits_for_old_supplicant_to_die(self):
        for stuck in ("0", "1"):
            with self.subTest(stuck=stuck):
                self.env["STUCK"] = stuck
                (self.root / "old-wpa").touch()
                (self.root / "events").unlink(missing_ok=True)
                self.run_shell("restart_wpa_supplicant || :")
                events = self.events()
                self.assertIn("kill -9 99", events)
                if stuck == "1":
                    self.assertNotIn("supplicant-start", events)
                    self.assertNotIn("ip link set wlan0 up", events)
                else:
                    self.assertLess(events.index("kill -9 99"), events.index("supplicant-start"))

    def test_missing_supplicant_and_failed_start_still_retry(self):
        self.run_shell('''
wpa_cli() { return 1; }
starts=0
wpa_supplicant() {
    starts=$((starts + 1))
    record "start-$starts"
    [ "$starts" -gt 1 ] || return 1
    echo COMPLETED > "$TEST_ROOT/state"
}
resume_reconnect
''')
        self.assertIn("start-2", self.events())
        self.assertIn("dhcp", self.events())

    def test_session_teardown_stops_only_verified_workers(self):
        self.proc(101, "/bin/sh", "/old/platform.d/00-wifi-dhcpv4.sh", "--boot-worker")
        self.proc(102, "/bin/sh", "/old/platform.d/00-wifi-dhcpv4.sh", "--resume-watch")
        self.proc(103, "sleep", "1000")
        stubs = "\n".join(f"{name}() {{ :; }}" for name in (
            "log_msg", "stop_boot_transition", "restore_stock_boot_animation",
            "stop_audio_spk_keeper", "kill_stale_custom_launcher",
            "stop_leaf_owned_loong", "restore_stock_rumble", "restore_sd_noexec",
            "remount_root_rw"))
        for action, watcher in (("leaf_stop", 102), ("pass_to_stock", 103)):
            with self.subTest(action=action):
                (self.root / "umrk-wifi-dhcpv4.pid").write_text("101\n")
                (self.root / "umrk-wifi-resume-watch.pid").write_text(f"{watcher}\n")
                (self.root / "events").unlink(missing_ok=True)
                self.run_shell(stubs + "\n" + session_function("stop_wifi_workers")
                               + "\n" + session_function(action) + f"\n{action}")
                self.assertIn("kill 101", self.events())
                if watcher == 102:
                    self.assertIn("kill 102", self.events())
                self.assertNotIn("kill 103", self.events())
                self.assertFalse((self.root / "umrk-wifi-resume-watch.pid").exists())


if __name__ == "__main__":
    unittest.main()
