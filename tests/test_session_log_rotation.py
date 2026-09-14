#!/usr/bin/env python3
"""Session supervisor rotates, caps, and self-heals the session log.

The field failure on Leaf 0.11 was a session log one bad cluster away from
killing every shell launch: the launcher and all of its children inherit the
fd, and deleting the file by hand was the fix. Rotation must therefore:

  * move the previous log to .1 exactly once per boot (boot rotation),
  * treat an unreadable, unwritable, or oversized log as rotatable evidence
    rather than a fatal condition,
  * and keep booting in every case.
"""

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


ROTATE_BLOCK = """
if session_log_is_healthy; then
    rotate_session_log "new session"
else
    rotate_session_log "previous log unreadable, unwritable, or oversized"
fi
"""


class SessionLogRotationTest(unittest.TestCase):
    def run_shell(self, body: str, env: dict) -> subprocess.CompletedProcess:
        script = session_functions() + "\n" + body
        return subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.logs = self.root / "card/logs"
        self.logs.mkdir(parents=True)
        self.fallback = self.root / "internal/logs"
        self.log = self.logs / "umrk-leaf-session.log"
        self.env = dict(os.environ)
        self.env.update({
            "LOG": str(self.log),
            "FALLBACK_LOG_DIR": str(self.fallback),
            "FALLBACK_LOG_MAX_BYTES": "64",
            # Generous so the supervisor's own banner lines never read as
            # oversized; the oversized tests below tighten it.
            "LOG_MAX_BYTES": "65536",
        })

    def tearDown(self):
        self.logs.chmod(stat.S_IRWXU)
        self.tmp.cleanup()

    def test_healthy_log_rotates_to_exactly_one_previous(self):
        self.log.write_text("previous session\n")
        result = self.run_shell(ROTATE_BLOCK, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.with_suffix(".log.1").read_text(), "previous session\n")
        self.assertTrue(self.log.exists())
        self.assertIn("rotated: new session", self.log.read_text())

    def test_second_rotation_keeps_exactly_one_previous(self):
        self.log.write_text("first\n")
        self.run_shell(ROTATE_BLOCK, self.env)
        self.log.write_text("second\n")
        self.run_shell(ROTATE_BLOCK, self.env)
        self.assertEqual(self.log.with_suffix(".log.1").read_text(), "second\n")
        self.assertNotIn("first", self.log.read_text())

    def test_oversized_log_rotates_and_boot_continues(self):
        self.log.write_text("x" * 200)
        env = dict(self.env, LOG_MAX_BYTES="64")
        result = self.run_shell(ROTATE_BLOCK, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.with_suffix(".log.1").read_text(), "x" * 200)
        self.assertLess(self.log.stat().st_size, 200)

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_unreadable_log_rotates_and_boot_continues(self):
        self.log.write_text("cannot be read\n")
        self.log.chmod(0)
        result = self.run_shell(ROTATE_BLOCK, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.log.exists())
        self.assertFalse(self.log.is_symlink())

    def test_directory_where_the_log_belongs_rotates_and_boot_continues(self):
        self.log.mkdir(parents=True)
        result = self.run_shell(ROTATE_BLOCK, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.log.is_file(), "a fresh log file must replace the directory")

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_unwritable_log_directory_falls_back_and_boots(self):
        self.logs.chmod(stat.S_IRUSR | stat.S_IXUSR)
        body = "ensure_writable_log\n" + ROTATE_BLOCK
        result = self.run_shell(body, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        fallback_log = self.fallback / "umrk-leaf-session.log"
        # The fallback message lands in the previous log, because the boot
        # rotation then moves it aside; the fresh log carries the rotation note.
        self.assertIn(
            "is not writable; logging to",
            self.fallback.joinpath("umrk-leaf-session.log.1").read_text(),
        )
        self.assertIn("rotated: new session", fallback_log.read_text())

    def test_generation_start_rotation_uses_healthy_check(self):
        """The per-generation call in the launcher loop must rotate an
        unhealthy log rather than hand the broken fd down again."""
        self.log.write_text("y" * 200)
        body = 'session_log_is_healthy || rotate_session_log "log unreadable, unwritable, or oversized at generation start"'
        result = self.run_shell(body, dict(self.env, LOG_MAX_BYTES="64"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.with_suffix(".log.1").read_text(), "y" * 200)
        self.assertLess(self.log.stat().st_size, 200)


if __name__ == "__main__":
    unittest.main()
