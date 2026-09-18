#!/usr/bin/env python3
"""Exercise the actual rootfs power barrier with simulated kernel mount state."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from test_session_log_fallback import session_functions

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'device/umrk-power-transition'
FAKE = '''#!/usr/bin/env python3
import os, sys, time
from pathlib import Path
root = Path(os.environ['POWER_FIXTURE'])
name = Path(sys.argv[0]).name
with (root/'events').open('a') as f: f.write(name + ' ' + ' '.join(sys.argv[1:]) + '\\n')
mode = os.environ.get('POWER_MODE', '')
if name == 'lockfile-create':
    if mode == 'busy-lock': sys.exit(1)
    (root/'locked').touch()
elif name == 'lockfile-remove':
    (root/'locked').unlink(missing_ok=True)
elif name == 'sync':
    if mode == 'flush-fail': sys.exit(1)
    if mode == 'slow-flush' and len(sys.argv) > 1:
        while not (root/'release').exists(): time.sleep(.01)
    if mode == 'late-writer' and len(sys.argv) == 1:
        p = root/'mountinfo'; p.write_text(p.read_text().replace('ro', 'rw'))
elif name == 'mount':
    if mode == 'busy-writer': sys.exit(1)
    p = root/'mountinfo'; rows = p.read_text().splitlines()
    for i, row in enumerate(rows):
        f = row.split()
        if f[4] == sys.argv[-1]:
            f[5] = 'ro'
            if mode != 'rw-superblock': f[-1] = 'ro'
            if mode == 'card-swap': f[2] = '179:999'
            rows[i] = ' '.join(f)
    p.write_text('\\n'.join(rows) + '\\n')
elif name == 'busybox':
    assert (root/'locked').exists(), 'power after releasing mount exclusion'
else: sys.exit(2)
'''

class PowerTransitionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        bin_dir = self.root/'bin'; bin_dir.mkdir()
        for name in ('sync', 'mount', 'busybox', 'lockfile-create', 'lockfile-remove'):
            p = bin_dir/name; p.write_text(FAKE); p.chmod(0o755)
        (self.root/'mountinfo').write_text(
            '18 1 179:6 / / rw,relatime - ext4 /dev/root rw\n'
            '22 18 0:19 / /run rw - tmpfs tmpfs rw\n'
            '33 18 179:96 / /mnt/sdcard rw - vfat /dev/mmcblk3 rw\n'
            '34 18 179:128 / /media/sdcard1 rw - vfat /dev/mmcblk1 rw\n')
        self.env = dict(os.environ, POWER_FIXTURE=str(self.root),
                        UMRK_POWER_MOUNTINFO=str(self.root/'mountinfo'),
                        UMRK_USBMOUNT_LOCK=str(self.root/'.mount'),
                        PATH=str(bin_dir)+':'+os.environ['PATH'])
    def tearDown(self): self.tmp.cleanup()
    def events(self): return (self.root/'events').read_text()
    def run_barrier(self, mode='', action='reboot'):
        return subprocess.run(['sh', str(HELPER), action],
                              env=dict(self.env, POWER_MODE=mode), capture_output=True, text=True)
    def test_success_orders_power_after_closure_and_flush(self):
        for action in ('reboot', 'poweroff'):
            result = self.run_barrier(action=action)
            # The fake command returns; real power must never return. Fail closed.
            self.assertNotEqual(result.returncode, 0)
            lines = self.events().splitlines()
            self.assertIn('busybox '+action+' -f', lines)
            power = lines.index('busybox '+action+' -f')
            self.assertEqual(lines[power-1], 'sync ')
            self.assertFalse((self.root/'locked').exists())
    def test_no_power_on_failure(self):
        for mode in ('busy-lock', 'flush-fail', 'busy-writer', 'rw-superblock', 'card-swap', 'late-writer'):
            with self.subTest(mode=mode):
                # reset fixture for each distinct failure
                self.tearDown(); self.setUp()
                result = self.run_barrier(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('busybox ', self.events())
    def test_slow_flush_has_no_power_deadline(self):
        proc = subprocess.Popen(['sh', str(HELPER), 'reboot'],
                                env=dict(self.env, POWER_MODE='slow-flush'),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            end = time.monotonic() + 3
            while time.monotonic() < end:
                if (self.root/'events').exists() and 'sync -f' in self.events(): break
                time.sleep(.01)
            time.sleep(.6)  # longer than the old 400 ms emergency-remount delay
            self.assertIsNone(proc.poll())
            self.assertNotIn('busybox ', self.events())
            (self.root/'release').touch()
            proc.communicate(timeout=5)
            self.assertIn('busybox reboot -f', self.events())
        finally:
            if proc.poll() is None: proc.kill(); proc.communicate()
    def test_invalid_action_never_touches_mounts(self):
        self.assertNotEqual(self.run_barrier(action='bad').returncode, 0)
        self.assertFalse((self.root/'events').exists())

    def test_animation_cleanup_matches_executable_and_stops_orphans(self):
        # An old boot animation has no tracked PID. Recovery's 16-character
        # process name is truncated by Linux comm, so only exe is authoritative.
        (self.root/'display.pid').write_text('301\n')
        body = '''
readlink() { case "$1" in /proc/301/exe|/proc/302/exe) echo /loong/loong_transition ;; *) echo /usr/bin/unrelated ;; esac; }
kill() { echo "kill $*"; }
sleep() { :; }
wait() { echo "wait $*"; }
pidof() { echo '302 999'; }
log_msg() { :; }
stop_storage_display
stop_boot_transition
'''
        result = subprocess.run(['sh', '-c', session_functions() + body],
                                env=dict(self.env, STORAGE_DISPLAY_PID=str(self.root/'display.pid'),
                                         BOOT_TRANSITION_PID=str(self.root/'missing.pid')),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for pid in ('301', '302'):
            self.assertIn('kill '+pid, result.stdout)
            self.assertIn('wait '+pid, result.stdout)
        self.assertNotIn('999', result.stdout)

    def test_clean_power_handoff_retires_durable_crash_count(self):
        crash = self.root/'crashes'
        crash.write_text('100 2\n')
        # Run the real cleanup/handoff, replacing only hardware worker actions
        # and the final exec target. The latter must replace the old shell.
        script = session_functions().replace('/run/umrk-power-transition.log', str(self.root/'power.log'))
        script = script.replace('/usr/bin/umrk-leaf-session power-transition', '/usr/bin/true power-transition')
        script += '''
stop_boot_transition() { :; }
stop_storage_display() { :; }
stop_audio_spk_keeper() { :; }
stop_wifi_workers() { :; }
stop_leaf_owned_loong() { :; }
stop_owned_process() { :; }
show_storage_display() { :; }
wait_recording_converters() { :; }
finish_power_transition reboot
echo old-shell-returned
'''
        result = subprocess.run(['sh', '-c', script], env=dict(self.env, CRASH_STATE=str(crash)),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(crash.exists())
        self.assertNotIn('old-shell-returned', (self.root/'power.log').read_text())

    def test_stop_returns_once_the_process_exits(self):
        # Fixed sleeps used to spend ~2 s of the power button's 6 s PMIC budget.
        body = '''
sleep 30 &
pid=$!
start=$(date +%s)
stop_pid "$pid" 200
wait "$pid" 2>/dev/null
echo "elapsed=$(( $(date +%s) - start ))"
pid_running "$pid" && echo still-running
'''
        result = subprocess.run(['sh', '-c', session_functions() + body], env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertIn('elapsed=0', result.stdout, result.stderr)
        self.assertNotIn('still-running', result.stdout)

    def test_low_battery_poweroff_is_handed_to_jawakad(self):
        # Stock loong_power runs system("poweroff"); BusyBox would only signal a
        # PID 1 that is blocked in rcS. Its PATH must reach jawakad's handoff.
        ctl = self.root/'launcher/bin/jawaka-platformctl'
        ctl.parent.mkdir(parents=True)
        ctl.write_text('#!/bin/sh\nprintf "%s|" "$@" >>"$CTL_LOG"\n')
        ctl.chmod(0o755)
        env = dict(self.env, TMPDIR=str(self.root), UMRK_BIN_PATH=str(ctl.parent),
                   JAWAKA_RUNTIME_DIR='/tmp/jawaka-runtime', CTL_LOG=str(self.root/'ctl.log'))
        body = '''
prepare_loong_power_handoff || exit 9
PATH="$LOONG_POWER_HANDOFF_DIR:$PATH" sh -c poweroff
PATH="$LOONG_POWER_HANDOFF_DIR:$PATH" sh -c reboot
'''
        result = subprocess.run(['sh', '-c', session_functions() + body], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = (self.root/'ctl.log').read_text()
        for action in ('poweroff', 'reboot'):
            self.assertIn('--socket|/tmp/jawaka-runtime/jawakad.sock|request|'
                          '{"type":"platform-action","action":"%s","value":0}|' % action, calls)
        env['UMRK_BIN_PATH'] = str(self.root/'missing')
        result = subprocess.run(['sh', '-c', session_functions() + 'prepare_loong_power_handoff'],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__': unittest.main()
