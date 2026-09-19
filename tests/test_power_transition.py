#!/usr/bin/env python3
"""Exercise the actual rootfs power barrier with simulated kernel mount state."""
import os
from pathlib import Path
import subprocess
import tempfile
import threading
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
pause_recording() { :; }
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
        for action, reason in (('poweroff', 'low-battery'), ('reboot', 'menu')):
            self.assertIn('--socket|/tmp/jawaka-runtime/jawakad.sock|request|'
                          '{"type":"platform-action","action":"%s","value":0,"reason":"%s"}|'
                          % (action, reason), calls)
        env['UMRK_BIN_PATH'] = str(self.root/'missing')
        result = subprocess.run(['sh', '-c', session_functions() + 'prepare_loong_power_handoff'],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)


FORCE_FAKE = r'''#!/usr/bin/env python3
import os, sys, time
from pathlib import Path
root = Path(os.environ['FORCE_FIXTURE'])
name = Path(sys.argv[0]).name
now = (root/'uptime').read_text().split()[0]
with (root/'events').open('a') as f: f.write(f'{now} {name} {" ".join(sys.argv[1:])}\n')
if name == 'sync' and os.environ.get('FORCE_SYNC') == 'hang':
    time.sleep(30)
elif name == 'dmesg':
    kmsg = root/'kmsg'
    text = kmsg.read_text() if kmsg.exists() else ''
    sys.stdout.write(text)
    if os.environ.get('FORCE_REMOUNT') == 'confirm' and (root/'sysrq-trigger').exists():
        sys.stdout.write('sysrq: Emergency Remount complete\n')
'''


class ForceTest(unittest.TestCase):
    """The forced power-off after a paused shutdown must reach the kernel call
    within 5.0 s of the press, whatever the flush and remount do."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        bin_dir = self.root/'bin'; bin_dir.mkdir()
        for name in ('sync', 'dmesg', 'busybox'):
            p = bin_dir/name; p.write_text(FORCE_FAKE); p.chmod(0o755)
        self.t0 = time.monotonic()
        self.stop = False
        self.write_uptime()
        self.clock = threading.Thread(target=self.tick, daemon=True)
        self.clock.start()
        self.env = dict(os.environ, FORCE_FIXTURE=str(self.root),
                        PATH=f'{bin_dir}:{os.environ["PATH"]}',
                        UMRK_POWER_UPTIME=str(self.root/'uptime'),
                        UMRK_POWER_KMSG=str(self.root/'kmsg'),
                        UMRK_POWER_SYSRQ_ENABLE=str(self.root/'sysrq'),
                        UMRK_POWER_SYSRQ_TRIGGER=str(self.root/'sysrq-trigger'))

    def tearDown(self):
        self.stop = True
        self.clock.join()
        self.tmp.cleanup()

    def write_uptime(self):
        tmp = self.root/'uptime.tmp'
        tmp.write_text(f'{1000 + time.monotonic() - self.t0:.2f} 0.00\n')
        tmp.replace(self.root/'uptime')

    def tick(self):
        while not self.stop:
            self.write_uptime()
            time.sleep(0.01)

    def force(self, held_s=2.0, **extra):
        press = int((1000 + time.monotonic() - self.t0 - held_s) * 100)
        log = self.root/'force.log'
        with log.open('w') as out:
            subprocess.run([str(HELPER), 'force', 'poweroff', str(press)],
                           env=dict(self.env, **extra), stdout=out, stderr=out,
                           timeout=20)
        result = subprocess.CompletedProcess([], 0, log.read_text(), '')
        events = (self.root/'events').read_text().splitlines()
        power = [e for e in events if ' busybox ' in e]
        self.assertEqual(len(power), 1, result.stdout + result.stderr)
        at, _, args = power[0].split(' ', 2)
        return float(at) * 100 - press, args, result

    def test_hung_flush_and_unconfirmed_remount_still_meet_the_deadline(self):
        elapsed_cs, args, result = self.force(FORCE_SYNC='hang', FORCE_REMOUNT='never')
        self.assertEqual(args, 'poweroff -f')
        self.assertLessEqual(elapsed_cs, 510, result.stdout)
        self.assertIn('flush still running', result.stdout)
        self.assertIn('not confirmed', result.stdout)

    def test_order_is_nonce_flush_sysrq_then_power(self):
        elapsed_cs, args, result = self.force(FORCE_REMOUNT='confirm')
        self.assertLess(elapsed_cs, 300, result.stdout)
        self.assertIn('emergency read-only remount complete', result.stdout)
        self.assertIn('umrk-force-', (self.root/'kmsg').read_text())
        self.assertEqual((self.root/'sysrq').read_text(), '1\n')
        # The trigger file keeps only the last write; the log shows all three.
        self.assertEqual((self.root/'sysrq-trigger').read_text(), 's\n')

    def test_late_force_skips_waits(self):
        # Force decided late (already 4.9 s after the press) goes straight on.
        elapsed_cs, _, result = self.force(held_s=4.9, FORCE_SYNC='hang', FORCE_REMOUNT='never')
        self.assertLessEqual(elapsed_cs, 530, result.stdout)

if __name__ == '__main__': unittest.main()
