#!/usr/bin/env python3
"""A compositor restarted with the launcher's card LD_LIBRARY_PATH kept replaced
card libraries mapped, and every shutdown barrier then failed as busy. Run the
real session functions against a fake /proc, mount table and S49weston."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_session_log_fallback import session_functions

# Records how it was run, then stops the old compositor family like the real
# `S49weston restart` does (the clients and tee exit with Weston).
FAKE_INITD = '''#!/bin/sh
{ echo "verb=$1"; echo "cwd=$(pwd)"; env; } >"$FIXTURE/initd-$1"
[ "$1" = restart ] && rm -rf "$FIXTURE"/proc/1*
exit 0
'''


class CompositorFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.card = self.root / 'media/sdcard1'
        self.lib = self.card / '.system/leaf/platforms/mlp1/launcher/lib'
        self.lib.mkdir(parents=True)
        (self.lib / 'libz.so.1').write_text('')
        self.userdata = self.root / 'userdata'
        self.userdata.mkdir()
        (self.root / 'mountinfo').write_text(
            f'18 1 179:6 / / ro,relatime - ext4 /dev/root ro\n'
            f'22 18 0:19 / /run rw - tmpfs tmpfs rw\n'
            f'30 18 179:7 / {self.userdata} rw - ext4 /dev/mmcblk0p7 rw\n'
            f'34 18 179:129 / {self.card} rw - ext4 /dev/mmcblk1p1 rw\n')
        initd = self.root / 'S49weston'
        initd.write_text(FAKE_INITD)
        initd.chmod(0o755)
        self.hdmi = self.root / 'hdmi-status'
        self.hdmi.write_text('disconnected\n')
        self.env = dict(os.environ, FIXTURE=str(self.root),
                        UMRK_POWER_PROC=str(self.proc),
                        UMRK_POWER_MOUNTINFO=str(self.root / 'mountinfo'),
                        UMRK_WESTON_INITD=str(initd),
                        UMRK_HDMI_STATUS=str(self.hdmi))

    def tearDown(self):
        self.tmp.cleanup()

    def process(self, pid, comm, maps=(), fds=(), cwd='/', cmdline=None):
        d = self.proc / str(pid)
        (d / 'fd').mkdir(parents=True)
        (d / 'comm').write_text(comm + '\n')
        (d / 'cmdline').write_text('\0'.join(cmdline or [comm]) + '\0')
        (d / 'maps').write_text(''.join(
            f'7f00000000-7f00001000 r-xp 00000000 b3:81 1234 {path}\n' for path in maps))
        os.symlink(cwd, d / 'cwd')
        for n, target in enumerate(fds):
            os.symlink(target, d / 'fd' / str(n))

    def shell(self, body, cwd=None, **env):
        script = session_functions() + '\nwait_for_compositor() { return 0; }\n' + body
        return subprocess.run(['sh', '-c', script], env=dict(self.env, **env), cwd=cwd,
                              capture_output=True, text=True, timeout=30)

    def holders(self):
        out = self.shell('compositor_card_holders').stdout.split()
        return sorted(int(p) for p in out)

    def initd_env(self, verb):
        path = self.root / f'initd-{verb}'
        return path.read_text().splitlines() if path.exists() else None


class HolderScanTest(CompositorFixture):
    def test_the_observed_post_handoff_family(self):
        deleted = f'{self.lib}/libz.so.1 (deleted)'
        self.process(1001, 'weston')
        self.process(1002, 'weston-keyboard', maps=[f'{self.lib}/libz.so.1', '/usr/lib/libc.so.6'])
        self.process(1003, 'weston-desktop-', maps=[deleted])
        self.process(1004, 'tee', maps=[f'{self.lib}/libatomic.so.1'],
                     cmdline=['tee', '/var/log/weston.log'])
        self.assertEqual(self.holders(), [1002, 1003, 1004])

    def test_card_cwd_and_card_descriptors_count(self):
        self.process(1001, 'weston', cwd=str(self.lib.parent))
        self.process(1004, 'tee', fds=[f'{self.card}/.userdata/mlp1/logs/umrk-leaf-session.log'],
                     cmdline=['tee', '/var/log/weston.log'])
        self.assertEqual(self.holders(), [1001, 1004])

    def test_a_process_exiting_mid_scan_hides_no_later_pid(self):
        # Listed by the glob, gone before awk opens it: a dangling comm sorted
        # ahead of the compositor. BusyBox awk used to abort the whole scan here.
        gone = self.proc / '1000'
        (gone / 'fd').mkdir(parents=True)
        os.symlink(self.root / 'exited', gone / 'comm')
        self.process(1001, 'weston', maps=[f'{self.lib}/libz.so.1'])
        self.process(1002, 'weston-keyboard', maps=[f'{self.lib}/libz.so.1'])
        self.assertEqual(self.holders(), [1001, 1002])

    def test_rootfs_family_eemc_and_other_processes_are_not_holders(self):
        self.process(1001, 'weston', maps=['/usr/lib/libweston-10.so.0'])
        self.process(1002, 'weston-keyboard', fds=[f'{self.userdata}/x'])
        # Not the compositor: the daemon's own stop owns these.
        self.process(1005, 'retroarch', maps=[f'{self.lib}/libz.so.1'])
        self.process(1006, 'tee', maps=[f'{self.lib}/libz.so.1'], cmdline=['tee', '/tmp/other'])
        # A sibling mount whose name only starts like the card.
        self.process(1007, 'weston-desktop-', cwd=str(self.card) + '2')
        self.assertEqual(self.holders(), [])


class ReleaseTest(CompositorFixture):
    def test_holders_restart_weston_from_the_rootfs(self):
        self.process(1002, 'weston-keyboard', maps=[f'{self.lib}/libz.so.1 (deleted)'])
        result = self.shell('POWER_SCREEN=paused-storage; power_release_compositor; '
                            'echo "screen=[$POWER_SCREEN]"',
                            cwd=str(self.lib),
                            LD_LIBRARY_PATH=f'{self.lib}:', LD_PRELOAD=f'{self.lib}/x.so')
        self.assertIn('compositor holds an SD card (pids 1002)', result.stdout)
        self.assertIn('screen=[]', result.stdout)
        seen = self.initd_env('restart')
        self.assertIsNotNone(seen)
        self.assertIn('cwd=/', seen)
        self.assertFalse([l for l in seen if l.startswith(('LD_LIBRARY_PATH=', 'LD_PRELOAD='))])
        self.assertFalse([l for l in seen if l.startswith('WESTON_DRM_')])
        self.assertEqual(self.holders(), [])

    def test_a_connected_tv_keeps_the_panel_first_compositor(self):
        self.process(1002, 'weston-keyboard', maps=[f'{self.lib}/libz.so.1'])
        self.hdmi.write_text('connected\n')
        self.shell('power_release_compositor')
        seen = self.initd_env('restart')
        self.assertIn('WESTON_DRM_SINGLE_HEAD=1', seen)
        self.assertIn('WESTON_DRM_PRIMARY=DSI-1', seen)

    def test_a_clean_compositor_is_left_alone(self):
        self.process(1001, 'weston', maps=['/usr/lib/libweston-10.so.0'])
        result = self.shell('POWER_SCREEN=paused-storage; power_release_compositor; '
                            'echo "screen=[$POWER_SCREEN]"')
        self.assertIsNone(self.initd_env('restart'))
        self.assertIn('screen=[paused-storage]', result.stdout)

    def test_the_barrier_loop_releases_the_compositor_first(self):
        text = session_functions()
        loop = text[text.index('run_power_transition() {'):]
        loop = loop[:loop.index('\n}\n')]
        self.assertLess(loop.index('power_release_compositor'),
                        loop.index('"$POWER_TRANSITION" "$power_action"'))


class SessionStartTest(CompositorFixture):
    def test_session_starts_weston_without_its_card_environment(self):
        result = self.shell('weston_initd start', cwd=str(self.lib),
                            LD_LIBRARY_PATH=f'{self.lib}:', LD_PRELOAD=f'{self.lib}/x.so',
                            WESTON_DRM_PRIMARY='DSI-1')
        self.assertEqual(result.stdout, '')
        seen = self.initd_env('start')
        self.assertIn('verb=start', seen)
        self.assertIn('cwd=/', seen)
        self.assertFalse([l for l in seen if l.startswith(('LD_LIBRARY_PATH=', 'LD_PRELOAD='))])
        # The boot-time panel-first choice still reaches Weston.
        self.assertIn('WESTON_DRM_PRIMARY=DSI-1', seen)

    def test_no_raw_init_script_calls_remain(self):
        text = session_functions()
        calls = [l for l in text.splitlines()
                 if '/etc/init.d/S49weston' in l and not l.lstrip().startswith(('#', 'WESTON_INITD='))]
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
