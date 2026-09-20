#!/usr/bin/env python3
"""Run the real stock hand-off with stubbed hardware steps and fake proc records."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SESSION = (ROOT / "device/umrk-leaf-session").read_text()

# Hardware and rootfs steps that pass_to_stock performs around the audio hand-off.
STUBS = "\n".join(f"{name}() {{ :; }}" for name in (
    "log_msg", "stop_boot_transition", "restore_stock_boot_animation",
    "stop_audio_spk_keeper", "stop_wifi_workers", "kill_stale_custom_launcher",
    "stop_leaf_owned_loong", "restore_stock_rumble", "restore_sd_noexec",
    "remount_root_rw"))

# kill records its arguments. A SIGTERM makes the fake process a zombie unless
# the test marks it as ignoring TERM; SIGKILL always does.
MOCKS = r'''
kill() {
    echo "kill $*" >> "$TEST_ROOT/events"
    pid="${2:-$1}"
    case "$1" in
        -9) echo "State: Z (zombie)" > "$TEST_ROOT/proc/$pid/status" ;;
        *) [ -f "$TEST_ROOT/ignore-term" ] ||
               echo "State: Z (zombie)" > "$TEST_ROOT/proc/$1/status" ;;
    esac
}
sleep() { echo sleep >> "$TEST_ROOT/events"; }
'''


def session_function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", SESSION, re.M | re.S)[0]


class StockHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stock-handoff-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pidfile = self.root / "umrk-leaf-pulseaudio.pid"
        self.env = {**os.environ, "TEST_ROOT": str(self.root)}

    def proc(self, pid, comm):
        directory = self.root / "proc" / str(pid)
        directory.mkdir(parents=True)
        (directory / "comm").write_text(comm + "\n")
        (directory / "status").write_text("State: S (sleeping)\n")

    def handoff(self):
        body = "\n".join([
            STUBS, MOCKS, f'OWNED_PULSE_PID="{self.pidfile}"',
            *(session_function(name) for name in (
                "pid_running", "stop_pid", "stop_owned_process", "pass_to_stock")),
            'pass_to_stock "exit-to-stock requested"',
        ])
        # Redirect only proc reads into fixtures; production has no test switch.
        body = body.replace("/proc/", f"{self.root}/proc/")
        result = subprocess.run(["sh", "-c", body], env=self.env, text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.root / "events"
        return events.read_text().splitlines() if events.exists() else []

    def test_exit_to_stock_stops_leaf_pulseaudio(self):
        self.proc(4242, "pulseaudio")
        self.pidfile.write_text("4242\n")
        events = self.handoff()
        self.assertIn("kill 4242", events)
        self.assertNotIn("kill -9 4242", events)
        self.assertFalse(self.pidfile.exists())

    def test_slow_pulseaudio_gets_two_seconds_before_sigkill(self):
        self.proc(4242, "pulseaudio")
        self.pidfile.write_text("4242\n")
        (self.root / "ignore-term").touch()
        events = self.handoff()
        self.assertEqual(events.count("sleep"), 40)
        self.assertEqual(events[-1], "kill -9 4242")

    def test_pulseaudio_not_started_by_leaf_is_left_alone(self):
        # Without a Leaf pidfile, or when the PID now belongs to something else,
        # the hand-off must not stop another process.
        self.proc(4242, "pulseaudio")
        self.assertEqual(self.handoff(), [])
        self.proc(5151, "loong_pangu")
        self.pidfile.write_text("5151\n")
        self.assertEqual(self.handoff(), [])


if __name__ == "__main__":
    unittest.main()
