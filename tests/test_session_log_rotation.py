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
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / "device/umrk-leaf-session"


def posix_shell() -> list[str]:
    """The device runs this script as sh, which is bash 5 in POSIX mode: a
    failed redirection on a special built-in exits the whole shell there. macOS
    /bin/sh (bash 3.2) does not, so prefer a modern bash in --posix mode when
    one is installed and fall back to sh otherwise."""
    for candidate in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", shutil.which("bash")):
        if not candidate or not os.access(candidate, os.X_OK):
            continue
        probe = subprocess.run([candidate, "-c", 'echo "${BASH_VERSINFO[0]}"'],
                               capture_output=True, text=True)
        if probe.stdout.strip().isdigit() and int(probe.stdout.strip()) >= 4:
            return [candidate, "--posix", "-c"]
    return ["sh", "-c"]


SHELL = posix_shell()


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
        return subprocess.run([*SHELL, script], env=env, capture_output=True, text=True)

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
        for directory in (self.logs, self.root / "locked"):
            if directory.exists():
                directory.chmod(stat.S_IRWXU)
        self.tmp.cleanup()

    def assertPrevious(self, expected: str) -> None:
        # The health check appends one real byte (a newline) before rotating:
        # that is how an EIO log is told apart from a healthy one.
        self.assertEqual(self.log.with_suffix(".log.1").read_text().rstrip("\n"),
                         expected.rstrip("\n"))

    def test_healthy_log_rotates_to_exactly_one_previous(self):
        self.log.write_text("previous session\n")
        result = self.run_shell(ROTATE_BLOCK, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertPrevious("previous session\n")
        self.assertTrue(self.log.exists())
        self.assertIn("rotated: new session", self.log.read_text())

    def test_second_rotation_keeps_exactly_one_previous(self):
        self.log.write_text("first\n")
        self.run_shell(ROTATE_BLOCK, self.env)
        self.log.write_text("second\n")
        self.run_shell(ROTATE_BLOCK, self.env)
        self.assertPrevious("second\n")
        self.assertNotIn("first", self.log.read_text())

    def test_oversized_log_rotates_and_boot_continues(self):
        self.log.write_text("x" * 200)
        env = dict(self.env, LOG_MAX_BYTES="64")
        result = self.run_shell(ROTATE_BLOCK, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertPrevious("x" * 200)
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
        body = ROTATE_BLOCK + 'ensure_usable_log\necho "LOG=$LOG"\n'
        result = self.run_shell(body, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        fallback_log = self.fallback / "umrk-leaf-session.log"
        self.assertIn(f"LOG={fallback_log}", result.stdout)
        # Rotation ran against the card first and could not write there; the
        # fallback then carries the decision.
        self.assertIn("is not writable; logging to", fallback_log.read_text())

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_rotation_on_a_read_only_directory_does_not_exit_the_supervisor(self):
        """sh is bash in POSIX mode on the device: a failed redirection on the
        ':' special built-in exits the whole shell, not just the command."""
        self.logs.chmod(stat.S_IRUSR | stat.S_IXUSR)
        result = self.run_shell('rotate_session_log "read-only card"\necho alive\n', self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("alive", result.stdout)

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_no_writable_log_anywhere_boots_on_dev_null(self):
        self.logs.chmod(stat.S_IRUSR | stat.S_IXUSR)
        locked = self.root / "locked"
        locked.mkdir()
        locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
        env = dict(self.env, FALLBACK_LOG_DIR=str(locked / "logs"))
        body = (ROTATE_BLOCK + 'ensure_usable_log\necho "LOG=$LOG"\n'
                # A later generation must leave /dev/null alone.
                'session_log_is_healthy || echo unhealthy\n'
                'rotate_session_log "generation"\nensure_usable_log\necho "again LOG=$LOG"\n')
        result = self.run_shell(body, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOG=/dev/null", result.stdout)
        self.assertIn("again LOG=/dev/null", result.stdout)
        self.assertNotIn("unhealthy", result.stdout)
        self.assertTrue(Path("/dev/null").exists())

    def test_generation_start_rotation_uses_healthy_check(self):
        """The per-generation call in the launcher loop must rotate an
        unhealthy log rather than hand the broken fd down again."""
        self.log.write_text("y" * 200)
        body = 'session_log_is_healthy || rotate_session_log "log unreadable, unwritable, or oversized at generation start"'
        result = self.run_shell(body, dict(self.env, LOG_MAX_BYTES="64"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertPrevious("y" * 200)
        self.assertLess(self.log.stat().st_size, 200)

    def test_fallback_that_opens_but_rejects_writes_uses_dev_null(self):
        self.log.mkdir()  # Unusable card log, including when running as root.
        self.fallback.mkdir(parents=True)
        fallback_log = self.fallback / "umrk-leaf-session.log"
        fallback_log.write_text("previous log\n")
        # A zero-byte append succeeds under this limit, but a real write fails.
        # Ignore SIGXFSZ so the shell observes the write error, like ENOSPC.
        result = self.run_shell(
            'trap "" XFSZ\nulimit -f 0\nensure_usable_log\n'
            'printf "%s|%s" "$LOG" "$UMRK_LAUNCHER_LOG"\n'
            'printf "daemon started\\n" >>"$LOG"\n', self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "/dev/null|/dev/null")
        self.assertEqual(fallback_log.read_text(), "previous log\n")


if __name__ == "__main__":
    unittest.main()
