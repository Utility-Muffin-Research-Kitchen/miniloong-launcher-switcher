#!/usr/bin/env python3
"""USB ADB at Leaf boot: restore the pin, then start the gadget.

LoongOS 1.4.0.52 removed /etc/init.d/S50usb-gadget.sh, and stock S40network
deletes /etc/.usb_config on every boot unless it is immutable, so a freshly
flashed rootfs has neither. These run the real session functions and boot
block, and the legacy installer's ADB preflight, against a fake rootfs:
/usr/bin and /etc point into a temp dir, and mount, chattr, lsattr and pidof
are stubs.
"""

import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SESSION = (ROOT / "device/umrk-leaf-session").read_text()
SPEC = importlib.util.spec_from_file_location(
    "make_launcher_switcher_sd", ROOT / "make_launcher_switcher_sd.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def function(source, name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", source, re.M | re.S)[0]


# The two ADB steps of the Leaf boot, verbatim.
BOOT_ADB = re.search(
    r"^    if adb_restore_requested && ! adb_is_pinned; then\n.*?"
    r"^        log_msg \"ADB not pinned; continuing Leaf mode without USB ADB\"\n    fi\n",
    SESSION, re.M | re.S)[0]

# chattr keeps the immutable bit as a flag file beside the config, which
# lsattr reports the way e2fsprogs prints it. pidof sees adbd once the fake
# gadget has started it.
MOCKS = r'''
record() { echo "$*" >> "$TEST_ROOT/events"; }
log_msg() { record "log $*"; }
fail() { record "fail $*"; exit 1; }
mount() { record "mount $*"; [ ! -f "$TEST_ROOT/mount-fails" ]; }
chattr() {
    record "chattr $*"
    case "$1" in
        +i) : > "$2.immutable" ;;
        -i) rm -f "$2.immutable" ;;
    esac
}
lsattr() {
    [ -e "$1" ] || return 1
    if [ -f "$1.immutable" ]; then echo "----i---------e----- $1"
    else echo "--------------e----- $1"; fi
}
pidof() { [ -f "$TEST_ROOT/adbd-running" ]; }
sleep() { :; }
sync() { :; }
'''

GADGET = '''#!/bin/sh
echo "usb-gadget $*" >> "$TEST_ROOT/events"
[ ! -f "$TEST_ROOT/gadget-fails" ] || exit 1
[ -f "$TEST_ROOT/adbd-never-starts" ] || : > "$TEST_ROOT/adbd-running"
'''


class UsbAdbTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="usb-adb-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ("usr/bin", "etc/init.d"):
            (self.root / directory).mkdir(parents=True)
        self.config = self.root / "etc/.usb_config"
        self.marker = self.root / "adb-enabled"
        self.gadget = self.executable("usr/bin/usb-gadget", GADGET)
        self.executable("usr/bin/adbd", "#!/bin/sh\nexit 0\n")
        self.env = {**os.environ, "TEST_ROOT": str(self.root)}

    def executable(self, relative, text):
        path = self.root / relative
        path.write_text(text)
        path.chmod(0o755)
        return path

    # A LoongOS 1.4.0.52 rootfs once S40network has run: no init script, and
    # no config unless it was pinned.
    def pinned(self):
        self.config.write_text("usb_adb_en\n")
        Path(f"{self.config}.immutable").touch()

    def immutable(self):
        return Path(f"{self.config}.immutable").exists()

    def run_sh(self, body, source=None):
        functions = [function(SESSION, name) for name in (
            "adb_tools_present", "adb_is_pinned", "adb_restore_requested",
            "remount_root_rw", "pin_adb", "wait_for_adbd", "start_usb_adb")]
        script = "\n".join([
            MOCKS, f'LOG="{self.root}/session.log"', f'ADB_MARKER="{self.marker}"',
            *(functions if source is None else [source]), body])
        # Only the rootfs paths move into the fixture; production has no switch.
        script = (script.replace("/usr/bin/", f"{self.root}/usr/bin/")
                  .replace("/etc/", f"{self.root}/etc/"))
        result = subprocess.run(["sh", "-c", script], env=self.env, text=True,
                                capture_output=True, timeout=10)
        events = self.root / "events"
        return result, events.read_text().splitlines() if events.exists() else []

    def boot(self):
        result, events = self.run_sh(BOOT_ADB)
        self.assertEqual(result.returncode, 0, result.stderr)
        return events

    # -- boot ---------------------------------------------------------------

    def test_restore_marker_pins_a_freshly_flashed_rootfs(self):
        self.marker.touch()
        events = self.boot()
        self.assertTrue(self.config.is_file(), events)
        self.assertEqual(self.config.read_text(), "usb_adb_en\n")
        self.assertTrue(self.immutable())
        self.assertIn("log ADB restore marker present; pinning ADB", events)
        self.assertNotIn("log ADB restore failed; continuing Leaf mode without USB ADB", events)
        self.assertIn("usb-gadget start", events)
        self.assertFalse(any("verification failed" in e for e in events), events)

    def test_pinned_rootfs_without_init_script_starts_the_gadget(self):
        self.pinned()
        events = self.boot()
        self.assertEqual(events, ["log starting usb gadget", "usb-gadget start"])

    def test_restore_marker_repins_a_mutable_config(self):
        self.config.write_text("usb_adb_en\n")
        self.marker.touch()
        events = self.boot()
        self.assertTrue(self.immutable())
        self.assertIn("usb-gadget start", events)

    def test_no_marker_leaves_usb_alone(self):
        events = self.boot()
        self.assertFalse(self.config.exists())
        self.assertEqual(events, ["log ADB not pinned; continuing Leaf mode without USB ADB"])

    def test_read_only_rootfs_continues_without_adb(self):
        self.marker.touch()
        (self.root / "mount-fails").touch()
        events = self.boot()
        self.assertFalse(self.config.exists())
        self.assertFalse(any(e.startswith("chattr") for e in events), events)
        self.assertIn("log ADB restore failed; continuing Leaf mode without USB ADB", events)
        self.assertNotIn("usb-gadget start", events)

    # -- tools --------------------------------------------------------------

    def test_init_script_without_gadget_binary_is_not_enough(self):
        self.executable("etc/init.d/S50usb-gadget.sh", "#!/bin/sh\nexit 0\n")
        self.gadget.unlink()
        self.pinned()
        self.marker.touch()
        result, events = self.run_sh("adb_is_pinned || echo unpinned; pin_adb || echo unpinnable")
        self.assertEqual(result.stdout.split(), ["unpinned", "unpinnable"])
        self.assertEqual(events, [])

    def test_gadget_start_failure_is_reported(self):
        self.pinned()
        (self.root / "gadget-fails").touch()
        events = self.boot()
        self.assertIn("log usb-gadget start failed", events)
        self.assertIn("log ADB startup verification failed; continuing Leaf mode", events)

    def test_missing_adbd_is_reported(self):
        self.pinned()
        (self.root / "adbd-never-starts").touch()
        events = self.boot()
        self.assertIn("log adbd did not appear after usb gadget start", events)

    def test_session_never_runs_the_removed_init_script(self):
        code = [line for line in SESSION.splitlines() if not line.lstrip().startswith("#")]
        self.assertFalse([line for line in code if "S50usb-gadget" in line])

    # -- legacy installer preflight ------------------------------------------

    def preflight(self):
        source = function(MODULE.build_installer_script(), "assert_adb_pinned")
        result, events = self.run_sh("assert_adb_pinned", source)
        return result.returncode, events

    def test_installer_preflight_accepts_a_pinned_1_4_0_52_rootfs(self):
        self.pinned()
        status, events = self.preflight()
        self.assertEqual(status, 0, events)
        self.assertEqual(events, ["log ADB pinned preflight passed"])

    def test_installer_preflight_needs_the_gadget_binary(self):
        self.pinned()
        self.executable("etc/init.d/S50usb-gadget.sh", "#!/bin/sh\nexit 0\n")
        self.gadget.unlink()
        status, events = self.preflight()
        self.assertEqual(status, 1)
        self.assertEqual(len(events), 1)
        self.assertRegex(events[0], r"^fail ADB support missing: .*/usr/bin/usb-gadget$")


if __name__ == "__main__":
    unittest.main()
