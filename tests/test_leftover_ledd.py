#!/usr/bin/env python3
"""A SIGKILLed Leaf daemon left its LED effects engine, jawaka-ledd, running
with the session log on the card as stdout. Crash recovery never stopped it,
and the next shutdown looped on "mount point is busy" until it was killed by
hand. Run the real session functions against real stand-in processes; only
the name lookups are faked."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from test_session_log_fallback import session_functions

# pidof answers from a table of names, listing only live pids; everything
# else is the real thing.
STUBS = '''
pidof() {
    out=""
    for name in "$@"; do
        for pid in $(cat "$FIXTURE/pidof/$name" 2>/dev/null); do
            kill -0 "$pid" 2>/dev/null && out="$out $pid"
        done
    done
    [ -n "$out" ] || return 1
    echo $out
}
pgrep() { return 1; }
'''


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class LeftoverLeddTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'pidof').mkdir()
        self.log = self.root / 'session.log'
        self.pids = []
        self.env = dict(os.environ, FIXTURE=str(self.root), LOG=str(self.log),
                        TMPDIR=str(self.root),
                        CLEAN_EXIT_SENTINEL=str(self.root / 'umrk-clean-exit'),
                        STRAGGLER_STOP_TIMEOUT_S='3')

    def tearDown(self):
        for pid in self.pids:
            if alive(pid):
                os.kill(pid, signal.SIGKILL)
        self.tmp.cleanup()

    def orphan(self, name):
        """A process reparented to init, as the killed daemon's children are,
        so init reaps it the moment it exits. pidof finds it as `name`."""
        out = subprocess.run(['sh', '-c', 'sleep 60 >/dev/null 2>&1 & echo $!'],
                             capture_output=True, text=True, check=True).stdout
        pid = int(out)
        self.pids.append(pid)
        (self.root / 'pidof' / name).write_text(f'{pid}\n')
        return pid

    def shell(self, body):
        script = session_functions() + STUBS + body
        return subprocess.run(['sh', '-c', script], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def gone(self, pid, timeout=2):
        end = time.monotonic() + timeout
        while alive(pid):
            if time.monotonic() > end:
                return False
            time.sleep(.02)
        return True

    def session_log(self):
        return self.log.read_text() if self.log.exists() else ''


class CrashRecoveryTest(LeftoverLeddTest):
    def test_crash_recovery_stops_the_killed_daemons_ledd(self):
        # Weston is still up; recovery only has the launcher to clean up.
        (self.root / 'pidof' / 'weston').write_text(f'{os.getpid()}\n')
        ledd = self.orphan('jawaka-ledd')
        result = self.shell('recover_leaf_daemon_crash')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.gone(ledd), 'jawaka-ledd survived crash recovery')
        self.assertIn(f'stopping stale launcher processes pids={ledd}', self.session_log())


class PowerPathTest(LeftoverLeddTest):
    def power_stop_workers(self):
        # The real worker stop, with the other workers recorded in order and
        # the power log kept in the fixture.
        body = '''
record() { echo "$*" >>"$FIXTURE/events"; }
stop_boot_transition() { :; }
stop_storage_display() { :; }
stop_audio_spk_keeper() { :; }
stop_wifi_workers() { :; }
stop_leaf_owned_loong() { record "stop_leaf_owned_loong ledd_alive=$(kill -0 "$LEDD" 2>/dev/null && echo yes || echo no)"; }
stop_owned_process() { :; }
power_stop_workers
'''
        script = session_functions().replace('/run/umrk-power-transition.log',
                                             str(self.root / 'power.log'))
        return subprocess.run(['sh', '-c', script + STUBS + body],
                              env=dict(self.env, LEDD=str(self.ledd)),
                              capture_output=True, text=True, timeout=30)

    def test_shutdown_stops_a_leftover_ledd_before_the_barrier(self):
        # A daemon that dies during a power request goes straight to the
        # barrier; crash recovery never runs on that path.
        self.ledd = self.orphan('jawaka-ledd')
        result = self.power_stop_workers()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.gone(self.ledd), 'jawaka-ledd still holds the card at the barrier')
        self.assertIn(f'stopping remaining jawaka-ledd pids={self.ledd}', self.session_log())
        # Stopped before loong_light, which a dying ledd thaws on its way out.
        self.assertEqual((self.root / 'events').read_text().splitlines(),
                         ['stop_leaf_owned_loong ledd_alive=no'])

    def test_shutdown_leaves_unknown_card_writers_to_the_pause(self):
        # Only the LED engine is known to write nothing that matters. Anything
        # else still pauses the shutdown rather than being killed mid-write.
        self.ledd = self.orphan('jawaka-ledd')
        runner = self.orphan('jawaka-update-runner')
        result = self.power_stop_workers()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.gone(self.ledd))
        self.assertTrue(alive(runner))


if __name__ == '__main__':
    unittest.main()
