#!/usr/bin/env python3
"""Run the real paused-shutdown shell code against fake input, proc and storage."""
import fcntl
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from test_session_log_fallback import session_functions

ROOT = Path(__file__).resolve().parents[1]

# `timeout` is not on every host. This one has the same exit status contract.
FAKE_TIMEOUT = r'''#!/usr/bin/env python3
import subprocess, sys
try:
    sys.exit(subprocess.run(sys.argv[2:], timeout=float(sys.argv[1])).returncode)
except subprocess.TimeoutExpired:
    sys.exit(124)
'''


# BusyBox `flock -n FILE PROG...` on the device; flock(2) semantics here too.
FAKE_FLOCK = r'''#!/usr/bin/env python3
import fcntl, os, subprocess, sys
assert sys.argv[1] == '-n'
fd = os.open(sys.argv[2], os.O_RDONLY)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(1)
sys.exit(subprocess.run(sys.argv[3:]).returncode)
'''


def key_event(value, code=116, kind=1):
    return struct.pack('<qqHHi', 0, 0, kind, code, value)


class PauseFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name, text in (('timeout', FAKE_TIMEOUT), ('flock', FAKE_FLOCK)):
            fake = self.bin / name
            fake.write_text(text)
            fake.chmod(0o755)
        self.t0 = time.monotonic()
        self.stop = False
        self.write_uptime()
        self.clock = threading.Thread(target=self.tick, daemon=True)
        self.clock.start()
        (self.root / 'run').mkdir()
        (self.root / 'logs').mkdir()
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                        UMRK_POWER_UPTIME=str(self.root / 'uptime'),
                        UMRK_POWER_STATE_DIR=str(self.root / 'run'),
                        UMRK_POWER_PROC=str(self.root / 'proc'),
                        EVENTS=str(self.root / 'events'))

    def tearDown(self):
        self.stop = True
        self.clock.join()
        self.tmp.cleanup()

    def write_uptime(self):
        tmp = self.root / 'uptime.tmp'
        tmp.write_text(f'{1000 + time.monotonic() - self.t0:.2f} 0.00\n')
        tmp.replace(self.root / 'uptime')

    def tick(self):
        while not self.stop:
            self.write_uptime()
            time.sleep(0.01)

    def shell(self, body, timeout=30, **env):
        prefix = f'''
LOG="{self.root}/session.log"
FALLBACK_LOG_DIR="{self.root}/logs"
STORAGE_REPAIR="{self.root}/bin/umrk-storage-repair"
POWER_TRANSITION="{self.root}/bin/umrk-power-transition"
TMPDIR="{self.root}"
'''
        stubs = '''
record() { echo "$*" >>"$EVENTS"; }
show_storage_display() { record "screen $1"; }
stop_storage_display() { record "screen-off"; }
'''
        script = prefix + session_functions() + stubs + body
        return subprocess.run(['sh', '-c', script], env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=timeout)

    def events(self):
        path = self.root / 'events'
        return path.read_text().splitlines() if path.exists() else []


class PowerPromptTest(PauseFixture):
    """The prompt reads real input_event records from the power key."""

    def prompt(self, schedule, seconds=3, hold=1):
        fifo = self.root / 'pwrkey'
        os.mkfifo(fifo)
        writer = os.open(fifo, os.O_RDWR)

        def feed():
            for delay, data in schedule:
                time.sleep(delay)
                os.write(writer, data)
        feeder = threading.Thread(target=feed, daemon=True)
        feeder.start()
        started = time.monotonic()
        result = self.shell(f'power_prompt {seconds} {hold}', UMRK_POWER_KEY_DEVICE=str(fifo))
        elapsed = time.monotonic() - started
        feeder.join()
        os.close(writer)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip(), elapsed

    def test_tap(self):
        answer, _ = self.prompt([(0.3, key_event(1)), (0.2, key_event(0, code=0, kind=0)),
                                 (0.2, key_event(0))])
        self.assertEqual(answer, 'tap')

    def test_hold_acts_at_two_seconds_while_still_held(self):
        answer, elapsed = self.prompt([(0.3, key_event(1))], seconds=5)
        self.assertTrue(answer.startswith('hold '), answer)
        self.assertGreaterEqual(elapsed, 2.2)
        self.assertLess(elapsed, 3.5)

    def test_hold_without_force_is_a_tap_on_release(self):
        answer, elapsed = self.prompt([(0.2, key_event(1)), (2.5, key_event(0))], seconds=5, hold=0)
        self.assertEqual(answer, 'tap')
        self.assertGreaterEqual(elapsed, 2.6)

    def test_release_from_an_earlier_press_and_other_keys_are_ignored(self):
        answer, elapsed = self.prompt([(0.2, key_event(0)), (0.1, key_event(1, code=115)),
                                       (0.1, key_event(0, code=115))], seconds=1)
        self.assertEqual(answer, 'timeout')
        self.assertGreaterEqual(elapsed, 0.9)

    def test_missing_device_times_out(self):
        result = self.shell('power_prompt 1 1', UMRK_POWER_KEY_DEVICE=str(self.root / 'none'))
        self.assertEqual(result.stdout.strip(), 'timeout')


class IncompleteRecordTest(PauseFixture):
    """What the daemon could not prove stopped, checked without signalling."""

    def setUp(self):
        super().setUp()
        self.req = self.root / 'req'
        self.req.mkdir()
        self.lease = self.root / 'generation.lease'
        self.lease.write_text('')

    def state(self, record):
        (self.req / 'incomplete').write_text(record)
        return self.shell(f'power_incomplete_state "{self.req}"; echo $?').stdout.strip()

    def test_a_held_lease_remains_until_released(self):
        record = f'reason=unverified-service\nservice=org.umrk.ssh pgid=0 lease={self.lease}\n'
        fd = os.open(self.lease, os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX)
        self.assertEqual(self.state(record), '1')
        os.close(fd)
        self.assertEqual(self.state(record), '0')

    def test_game_pid_checks_identity_not_just_the_number(self):
        proc = self.root / 'proc' / '4242'
        proc.mkdir(parents=True)
        # Fields after "(comm) ": state is 1st, starttime is the 20th.
        rest = ['S'] + ['0'] * 18 + ['777'] + ['0'] * 5
        (proc / 'stat').write_text('4242 (retroarch) ' + ' '.join(rest) + '\n')
        self.assertEqual(self.state('reason=game-child\ngame pid=4242 start=777\n'), '1')
        self.assertEqual(self.state('reason=game-child\ngame pid=4242 start=778\n'), '0')
        rest[0] = 'Z'
        (proc / 'stat').write_text('4242 (retroarch) ' + ' '.join(rest) + '\n')
        self.assertEqual(self.state('reason=game-child\ngame pid=4242 start=777\n'), '0')

    def test_group_scan_when_the_lease_is_gone(self):
        # Fields after "(comm) ": state, ppid, pgrp.
        member = self.root / 'proc' / '5001'
        member.mkdir(parents=True)
        (member / 'stat').write_text('5001 (dropbear) S 1 5000 ' + '0 ' * 40 + '\n')
        record = 'reason=unverified-service\nservice=org.umrk.ssh pgid=5000 lease=/gone\n'
        self.assertEqual(self.state(record), '1')
        (member / 'stat').write_text('5001 (dropbear) Z 1 5000 ' + '0 ' * 40 + '\n')
        self.assertEqual(self.state(record), '0')

    def test_unreadable_records_cannot_be_retried(self):
        self.assertEqual(self.shell(f'power_incomplete_state "{self.req}"; echo $?').stdout.strip(), '2')
        self.assertEqual(self.state('reason=cleanup-failed\n'), '2')
        self.assertEqual(self.state('reason=unverified-service\nsomething else\n'), '2')
        self.assertEqual(self.state('reason=unverified-service\nservice=x pgid=0 lease=/none\n'), '2')


class PauseLoopTest(PauseFixture):
    """Pause decisions with the prompt, pre-arm and power helper stubbed."""

    def run_pause(self, body, answers=(), prearm='ok', **env):
        (self.root / 'answers').write_text(''.join(a + '\n' for a in answers))
        stubs = f'''
power_prompt() {{
    record "prompt $*"
    answer="$(head -n 1 "{self.root}/answers")"
    sed -i.bak 1d "{self.root}/answers"
    echo "${{answer:-timeout}}"
}}
power_unproven_cards() {{ echo 22A4-0814; }}
force_power_transition() {{ record "force $*"; exit 0; }}
'''
        pre = self.bin / 'umrk-storage-repair'
        pre.write_text(f'#!/bin/sh\necho "pre-arm $*" >>"{self.root}/events"\n'
                       f'[ "{prearm}" = ok ]\n')
        pre.chmod(0o755)
        return self.shell(stubs + body, **env)

    def test_storage_offers_force_only_after_a_failed_retry(self):
        self.run_pause('pause_storage poweroff 0', answers=['timeout'] * 5)
        events = self.events()
        self.assertIn('screen paused-storage', events)
        self.assertIn('prompt 2 0', events)
        self.assertNotIn('prompt 2 1', events)
        self.assertIn('pre-arm pre-arm paused-shutdown 22A4-0814', events)

        (self.root / 'events').unlink()
        self.run_pause('pause_storage poweroff 1', answers=['timeout', 'hold 12345'])
        events = self.events()
        self.assertIn('screen paused-storage-force', events)
        self.assertIn('screen forcing', events)
        self.assertEqual(events[-1], 'force poweroff 12345')

    def test_failed_prearm_never_forces(self):
        self.run_pause('pause_storage poweroff 1', answers=['hold 1'] + ['timeout'] * 4,
                       prearm='failed')
        events = self.events()
        self.assertIn('screen paused-storage', events)
        self.assertNotIn('screen paused-storage-force', events)
        self.assertTrue(all(e != 'prompt 2 1' for e in events))
        self.assertFalse(any(e.startswith('force') for e in events))

    def test_tap_and_adb_marker_retry(self):
        result = self.run_pause('pause_storage reboot 1; echo returned', answers=['tap'])
        self.assertIn('returned', result.stdout)
        (self.root / 'run' / 'umrk-power-retry').write_text('')
        result = self.run_pause('pause_storage reboot 1; echo returned')
        self.assertIn('returned', result.stdout)
        self.assertFalse((self.root / 'run' / 'umrk-power-retry').exists())

    def test_app_pause_needs_proof_or_a_hold(self):
        req = self.root / 'req'
        req.mkdir()
        lease = self.root / 'generation.lease'
        lease.write_text('')
        (req / 'incomplete').write_text(
            f'reason=unverified-service\nservice=org.umrk.ssh pgid=0 lease={lease}\n')
        fd = os.open(lease, os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX)
        result = self.run_pause(f'pause_app "{req}"; echo continued', answers=['tap', 'hold 5'])
        os.close(fd)
        events = self.events()
        self.assertIn('screen paused-app', events)
        self.assertEqual(events.count('prompt 2 1'), 2)
        self.assertIn('continued', result.stdout)
        self.assertIn('user override', result.stdout)

    def test_app_pause_continues_on_its_own_when_the_app_is_gone(self):
        req = self.root / 'req'
        req.mkdir()
        lease = self.root / 'generation.lease'
        lease.write_text('')
        (req / 'incomplete').write_text(
            f'reason=unverified-service\nservice=org.umrk.ssh pgid=0 lease={lease}\n')
        result = self.run_pause(f'pause_app "{req}"; echo continued')
        self.assertIn('every recorded app is gone', result.stdout)
        self.assertFalse(any(e.startswith('prompt') for e in self.events()))

    def test_app_pause_without_prearm_offers_no_override(self):
        req = self.root / 'req'
        req.mkdir()
        (req / 'incomplete').write_text('reason=cleanup-failed\n')
        # Taps re-check and a hold is refused, so the loop keeps waiting.
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_pause(f'pause_app "{req}"', answers=['tap', 'hold 9'], prearm='failed',
                           timeout=3)
        events = self.events()
        self.assertIn('screen paused-no-force', events)
        self.assertNotIn('prompt 2 1', events)

    def test_critical_battery_gives_way_only_when_discharging(self):
        supply = self.root / 'supply' / 'battery'
        supply.mkdir(parents=True)
        (supply / 'capacity').write_text('2\n')
        (supply / 'status').write_text('Charging\n')
        env = dict(UMRK_POWER_SUPPLY_DIR=str(self.root / 'supply'), UMRK_POWER_CRITICAL_CAPACITY='3')
        self.run_pause('pause_storage poweroff 0', answers=['timeout'] * 5, **env)
        self.assertFalse(any(e.startswith('force') for e in self.events()))
        (self.root / 'events').unlink()
        (supply / 'status').write_text('Discharging\n')
        self.run_pause('pause_storage poweroff 0', **env)
        self.assertTrue(self.events()[-1].startswith('force poweroff '))
        # Off unless a measured cutoff is configured.
        (self.root / 'events').unlink()
        env['UMRK_POWER_CRITICAL_CAPACITY'] = ''
        self.run_pause('pause_storage poweroff 0', answers=['timeout'] * 5, **env)
        self.assertFalse(any(e.startswith('force') for e in self.events()))


class CardSnapshotTest(PauseFixture):
    """Cards at risk come from the shutdown-start snapshot, not the current slots."""

    def test_unproven_cards(self):
        dev = self.root / 'dev'
        dev.mkdir()
        for name in ('mmcblk0p12', 'mmcblk1', 'mmcblk3'):
            (dev / name).write_text('')
        by_uuid = self.root / 'by-uuid'
        by_uuid.mkdir()
        os.symlink(dev / 'mmcblk0p12', by_uuid / 'internal-uuid')
        os.symlink(dev / 'mmcblk1', by_uuid / '22A4-0814')
        os.symlink(dev / 'mmcblk3', by_uuid / '04B1-0820')
        mountinfo = self.root / 'mountinfo'
        mountinfo.write_text(
            f'30 1 179:12 / /userdata rw - ext4 {dev}/mmcblk0p12 rw\n'
            f'33 1 179:96 / /mnt/sdcard rw - vfat {dev}/mmcblk1 rw\n'
            f'34 1 179:128 / /media/sdcard1 rw - vfat {dev}/mmcblk3 rw\n')
        env = dict(UMRK_BY_UUID_DIR=str(by_uuid), UMRK_POWER_MOUNTINFO=str(mountinfo))
        self.shell('power_snapshot_cards', **env)
        snapshot = (self.root / 'run' / 'umrk-power-cards').read_text()
        self.assertIn('22A4-0814', snapshot)
        self.assertIn('04B1-0820', snapshot)
        self.assertNotIn('internal-uuid', snapshot)
        # One card closed cleanly (read-only superblock), the other was removed.
        mountinfo.write_text(
            f'33 1 179:96 / /mnt/sdcard ro - vfat {dev}/mmcblk1 ro\n')
        os.unlink(by_uuid / '04B1-0820')
        unproven = self.shell('power_unproven_cards', **env).stdout.split()
        self.assertEqual(unproven, ['04B1-0820'])
        # A read-only bind of a writable superblock is not closed.
        mountinfo.write_text(
            f'33 1 179:96 / /mnt/sdcard ro - vfat {dev}/mmcblk1 rw\n')
        self.assertIn('22A4-0814', self.shell('power_unproven_cards', **env).stdout.split())


if __name__ == '__main__':
    unittest.main()
