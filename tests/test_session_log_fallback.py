#!/usr/bin/env python3
"""Session supervisor keeps logging, and keeps starting Leaf, when the card
holding the session log is read-only.

On a read-only launcher card `"$BUNDLE_BIN" >>"$LOG"` fails at the redirection,
so the daemon never starts and the loop retries forever. ensure_writable_log
must move LOG to internal storage before that happens."""

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / "device/umrk-leaf-session"


def session_functions() -> str:
    text = SESSION.read_text()
    start = text.index("log_msg() {")
    end = text.index("case \"${1:-start}\" in")
    return text[start:end]


class SessionLogFallbackTest(unittest.TestCase):
    def run_shell(self, body: str, env: dict) -> subprocess.CompletedProcess:
        script = session_functions() + "\n" + body
        return subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.card_logs = self.root / "card/logs"
        self.card_logs.mkdir(parents=True)
        self.fallback = self.root / "internal/logs"
        self.env = dict(os.environ)
        self.env.update({
            "LOG": str(self.card_logs / "umrk-leaf-session.log"),
            "FALLBACK_LOG_DIR": str(self.fallback),
            "FALLBACK_LOG_MAX_BYTES": "64",
        })

    def tearDown(self):
        self.card_logs.chmod(stat.S_IRWXU)
        self.tmp.cleanup()

    def test_writable_card_keeps_its_log(self):
        result = self.run_shell('ensure_writable_log; printf "%s" "$LOG"', self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.env["LOG"])
        self.assertFalse(self.fallback.exists())

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_read_only_card_moves_log_to_internal_storage(self):
        (self.card_logs / "umrk-leaf-session.log").write_text("old\n")
        self.card_logs.chmod(stat.S_IRUSR | stat.S_IXUSR)
        (self.card_logs / "umrk-leaf-session.log").chmod(stat.S_IRUSR)
        result = self.run_shell(
            'ensure_writable_log; printf "%s|%s" "$LOG" "$UMRK_LAUNCHER_LOG"; '
            'sh -c "echo daemon started" >>"$LOG" 2>&1', self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        fallback_log = self.fallback / "umrk-leaf-session.log"
        self.assertEqual(result.stdout, f"{fallback_log}|{fallback_log}")
        content = fallback_log.read_text()
        self.assertIn("is not writable; logging to", content)
        self.assertIn("daemon started", content)

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_fallback_rotates_once_over_the_cap(self):
        self.fallback.mkdir(parents=True)
        (self.fallback / "umrk-leaf-session.log").write_text("x" * 200)
        (self.card_logs / "umrk-leaf-session.log").write_text("")
        (self.card_logs / "umrk-leaf-session.log").chmod(stat.S_IRUSR)
        self.card_logs.chmod(stat.S_IRUSR | stat.S_IXUSR)
        result = self.run_shell("ensure_writable_log", self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.fallback / "umrk-leaf-session.log.1").read_text(), "x" * 200)
        self.assertNotIn("x" * 200, (self.fallback / "umrk-leaf-session.log").read_text())

    def test_secondary_remount_keeps_a_read_only_card_read_only(self):
        mounts = self.root / "mounts"
        mounts.write_text(f"/dev/mmcblk1 {self.root}/sd1 vfat ro,nosuid,nodev,errors=remount-ro 0 0\n")
        calls = self.root / "calls"
        body = f'''
PLATFORM=mlp1
SECONDARY_SD_MOUNT="{self.root}/sd1"
mountpoint_is_mounted() {{ return 0; }}
awk() {{ command awk "$@" "{mounts}" 2>/dev/null || command awk "$@"; }}
mount() {{ echo "mount $*" >>"{calls}"; }}
remount_secondary_sd_exec
'''
        # awk here reads /proc/mounts; point it at the fixture instead.
        script = session_functions().replace("/proc/mounts", str(mounts)) + body
        result = subprocess.run(["sh", "-c", script], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("remount,ro,exec,nosuid,nodev", calls.read_text())
        self.assertNotIn("remount,rw", calls.read_text())


if __name__ == "__main__":
    unittest.main()
