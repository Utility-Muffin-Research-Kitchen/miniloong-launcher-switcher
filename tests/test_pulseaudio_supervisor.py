#!/usr/bin/env python3
"""The kernel SIGKILLs PulseAudio when its realtime IO thread overruns
RLIMIT_RTTIME, and the session started it only once, so audio stayed off until
reboot. Run the real supervisor and stop against a stand-in daemon; only the
/proc lookups and pidof are faked."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from test_session_log_fallback import session_functions

# The stand-in records how it was started and keeps a fake /proc comm entry
# for stop_owned_process, then becomes a sleep under the same pid. FAKE_EXIT
# makes it exit at once instead, like a daemon that cannot start.
DAEMON = '''#!/bin/sh
mkdir -p "$FIXTURE/proc/$$"
echo pulseaudio >"$FIXTURE/proc/$$/comm"
echo "$$ args=$* config=${PULSE_CONFIG-unset} home=${PULSE_HOME-unset}" >>"$FIXTURE/starts"
[ -z "$FAKE_EXIT" ] || exit "$FAKE_EXIT"
exec sleep 60
'''

STUBS = '''
pid_running() {
    kill -0 "$1" 2>/dev/null || return 1
    case "$(ps -o stat= -p "$1" 2>/dev/null)" in *Z*) return 1 ;; esac
}
pidof() { [ -f "$FIXTURE/other-pulseaudio" ] && echo 9999; }
starts() { cat "$FIXTURE/starts" 2>/dev/null | wc -l | tr -d ' '; }
until_starts() {
    i=0
    while [ "$(starts)" -lt "$1" ] && [ "$i" -lt 100 ]; do sleep .05; i=$((i + 1)); done
}
daemon() { sed -n "${1}p" "$FIXTURE/starts" | cut -d' ' -f1; }
'''


class PulseAudioSupervisorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.defaults = self.root / 'platform' / 'defaults'
        self.defaults.mkdir(parents=True)
        (self.defaults / 'pulse-default.pa').write_text('')
        (self.defaults / 'pulse-daemon.conf').write_text('')
        self.fake = self.root / 'bin' / 'pulseaudio'
        self.fake.parent.mkdir()
        self.fake.write_text(DAEMON)
        self.fake.chmod(0o755)
        self.log = self.root / 'session.log'
        self.pidfile = self.root / 'umrk-leaf-pulseaudio.pid'
        self.env = dict(os.environ, FIXTURE=str(self.root), LOG=str(self.log),
                        PULSE_RESTART_DELAY_S='0')
        self.addCleanup(self.kill_daemons)

    def kill_daemons(self):
        starts = self.root / 'starts'
        for line in starts.read_text().splitlines() if starts.exists() else []:
            try:
                os.kill(int(line.split()[0]), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def shell(self, body, **env):
        script = session_functions().replace('/usr/bin/pulseaudio', str(self.fake))
        script = script.replace('/proc/', f'{self.root}/proc/')
        script = '\n'.join([f'OWNED_PULSE_PID="{self.pidfile}"',
                            f'PLATFORM_ROOT="{self.root / "platform"}"',
                            script, STUBS, body])
        result = subprocess.run(['sh', '-c', script], env=dict(self.env, **env),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def starts(self):
        return (self.root / 'starts').read_text().splitlines()

    def session_log(self):
        return self.log.read_text() if self.log.exists() else ''

    def test_killed_daemon_is_restarted_with_leaf_config(self):
        out = self.shell('''
start_pulseaudio_if_needed
until_starts 1
kill -9 "$(daemon 1)"
until_starts 2
echo "pidfile=$(cat "$OWNED_PULSE_PID") second=$(daemon 2)"
stop_pulseaudio
''')
        self.assertEqual(len(self.starts()), 2)
        second = self.starts()[1].split()[0]
        self.assertIn(f'pidfile={second} second={second}', out)
        self.assertIn('pulseaudio killed by signal 9; restarting', self.session_log())
        for line in self.starts():
            self.assertIn(f'args=-nF {self.defaults}/pulse-default.pa', line)
            self.assertIn(f'config={self.defaults}/pulse-daemon.conf', line)
            self.assertIn('home=/userdata/.pulse', line)

    def test_stock_daemon_config_when_leaf_ships_none(self):
        # PULSE_CONFIG naming a missing file would drop /etc/pulse/daemon.conf
        # for PulseAudio's compiled-in defaults, exit-idle-time 20 among them.
        (self.defaults / 'pulse-daemon.conf').unlink()
        self.shell('start_pulseaudio_if_needed; until_starts 1; stop_pulseaudio')
        self.assertIn('config=unset', self.starts()[0])

    def test_stop_ends_supervision_and_the_daemon(self):
        out = self.shell('''
start_pulseaudio_if_needed
sup=$PULSE_SUPERVISOR_PID
until_starts 1
stop_pulseaudio
kill -0 "$(daemon 1)" 2>/dev/null && echo daemon-alive
kill -0 "$sup" 2>/dev/null && echo supervisor-alive
sleep .3
echo "starts=$(starts)"
''')
        self.assertNotIn('alive', out)
        self.assertIn('starts=1', out)
        self.assertFalse(self.pidfile.exists())

    def test_stop_reaches_a_daemon_the_pidfile_does_not_name_yet(self):
        # A stop landing between the supervisor's fork and its pidfile write
        # finds the previous pid; the supervisor's trap must hand over the new one.
        out = self.shell('''
start_pulseaudio_if_needed
until_starts 1
echo 1 >"$OWNED_PULSE_PID"
stop_pulseaudio
kill -0 "$(daemon 1)" 2>/dev/null && echo daemon-alive
echo done
''')
        self.assertIn('done', out)
        self.assertNotIn('daemon-alive', out)

    def test_stop_while_waiting_to_restart_starts_nothing(self):
        # The supervisor sleeps in the foreground between runs, so its TERM trap
        # waits; stop_pid's SIGKILL must still leave no daemon behind.
        out = self.shell('''
start_pulseaudio_if_needed
until_starts 1
kill -9 "$(daemon 1)"
sleep .2
stop_pulseaudio
sleep 1.3
echo "starts=$(starts)"
''', PULSE_RESTART_DELAY_S='1')
        self.assertIn('starts=1', out)

    def test_gives_up_on_a_daemon_that_cannot_start(self):
        self.shell('''
start_pulseaudio_if_needed
wait "$PULSE_SUPERVISOR_PID"
''', FAKE_EXIT='1', PULSE_QUICK_EXIT_LIMIT='3')
        self.assertEqual(len(self.starts()), 3)
        self.assertIn('pulseaudio exited with status 1; it keeps exiting soon after start, '
                      'leaving it stopped', self.session_log())

    def test_another_daemon_is_not_doubled(self):
        self.shell('''
start_pulseaudio_if_needed
until_starts 1
: >"$FIXTURE/other-pulseaudio"
kill -9 "$(daemon 1)"
wait "$PULSE_SUPERVISOR_PID"
''')
        self.assertEqual(len(self.starts()), 1)
        self.assertIn('another pulseaudio is running, not restarting', self.session_log())


if __name__ == '__main__':
    unittest.main()
