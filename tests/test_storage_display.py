#!/usr/bin/env python3
"""The boot-time SD check and repair screens: wait for Weston, pick the screen.

At boot the check starts right after S49weston, before the compositor has made
its socket. A screen started then fails silently, which left the whole check
behind a black screen. These run the real session functions with the
compositor, the runner and the screen launcher stubbed out.
"""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SESSION = (ROOT / "device/umrk-leaf-session").read_text()


def session_function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", SESSION, re.M | re.S)[0]


# pgrep answers from a flag file; each sleep counts, and the socket appears
# after the number of sleeps written in socket-after.
MOCKS = r'''
pgrep() { [ -f "$TEST_ROOT/weston-running" ]; }
sleep() {
    n=$(( $(cat "$TEST_ROOT/sleeps" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$TEST_ROOT/sleeps"
    if [ -f "$TEST_ROOT/socket-after" ] && [ "$n" -ge "$(cat "$TEST_ROOT/socket-after")" ]; then
        : > "$XDG_RUNTIME_DIR/wayland-0"
    fi
}
show_storage_display() { echo "screen $1" >> "$TEST_ROOT/events"; }
stop_storage_display() { echo "stop" >> "$TEST_ROOT/events"; }
rootfs_env() { "$@"; }
adb_is_pinned() { return 1; }
'''


class StorageDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="storage-display-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "run").mkdir()
        self.env = {**os.environ, "TEST_ROOT": str(self.root),
                    "XDG_RUNTIME_DIR": str(self.root / "run")}

    def run_sh(self, body):
        script = "\n".join([MOCKS, session_function("wait_for_compositor"), body])
        return subprocess.run(["sh", "-c", script], env=self.env,
                              capture_output=True, text=True)

    def sleeps(self):
        path = self.root / "sleeps"
        return int(path.read_text()) if path.exists() else 0

    def events(self):
        path = self.root / "events"
        return path.read_text().splitlines() if path.exists() else []

    # -- wait_for_compositor ------------------------------------------------

    def test_waits_until_weston_makes_its_socket(self):
        (self.root / "weston-running").touch()
        (self.root / "socket-after").write_text("7")
        result = self.run_sh("wait_for_compositor 80")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.sleeps(), 7)

    def test_existing_socket_needs_no_wait(self):
        (self.root / "weston-running").touch()
        (self.root / "run" / "wayland-0").touch()
        self.assertEqual(self.run_sh("wait_for_compositor 80").returncode, 0)
        self.assertEqual(self.sleeps(), 0)

    def test_no_weston_means_no_wait(self):
        self.assertNotEqual(self.run_sh("wait_for_compositor 80").returncode, 0)
        self.assertEqual(self.sleeps(), 0)

    def test_wait_is_bounded(self):
        (self.root / "weston-running").touch()
        self.assertNotEqual(self.run_sh("wait_for_compositor 80").returncode, 0)
        self.assertEqual(self.sleeps(), 80)

    # -- run_storage_repair_boot picks the screen ----------------------------

    def boot(self, runner_body):
        runner = self.root / "runner"
        runner.write_text("#!/bin/sh\n" + runner_body)
        runner.chmod(0o755)
        body = "\n".join([
            f'PLATFORM=mlp1 STORAGE_REPAIR="{runner}" FALLBACK_LOG_DIR="{self.root}/logs"',
            session_function("run_storage_repair_boot"),
            "run_storage_repair_boot",
        ])
        return self.run_sh(body)

    def test_repair_request_shows_the_repair_screen(self):
        result = self.boot('case "$1" in pending-mode) echo repair ;; pending) exit 0 ;; boot) exit 0 ;; esac\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["screen repairing", "stop"])

    def test_check_shows_the_check_screen(self):
        result = self.boot('case "$1" in pending-mode) echo check ;; pending) exit 0 ;; boot) exit 0 ;; esac\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["screen checking", "stop"])

    def test_older_runner_without_pending_mode_still_shows_checking(self):
        result = self.boot('case "$1" in pending) exit 0 ;; boot) exit 0 ;; *) exit 2 ;; esac\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["screen checking", "stop"])

    def test_nothing_pending_shows_no_screen(self):
        result = self.boot('case "$1" in boot) exit 0 ;; *) exit 1 ;; esac\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["stop"])


if __name__ == "__main__":
    unittest.main()
