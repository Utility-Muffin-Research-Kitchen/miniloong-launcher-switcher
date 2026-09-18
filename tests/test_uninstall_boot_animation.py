#!/usr/bin/env python3
"""Uninstall puts the stock boot animation back.

Leaf overwrites /loong/textures/boot on the rootfs and keeps the originals in
boot.stock. umrk-leaf-session can restore them, but only from pass_to_stock(),
and uninstall deletes that script -- so before this restore existed, recovering
to the stock launcher left the device booting with Leaf's animation and the
only code that could undo it gone. The restore therefore has to live in the
uninstaller itself, and it has to be safe in every state the card can be in.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
UNINSTALL = ROOT / "device/umrk-launcher-switcher-uninstall.sh"


def posix_shell() -> list[str]:
    for candidate in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", shutil.which("bash")):
        if not candidate or not os.access(candidate, os.X_OK):
            continue
        probe = subprocess.run([candidate, "-c", 'echo "${BASH_VERSINFO[0]}"'],
                               capture_output=True, text=True)
        if probe.stdout.strip().isdigit() and int(probe.stdout.strip()) >= 4:
            return [candidate, "--posix", "-c"]
    return ["sh", "-c"]


SHELL = posix_shell()


def restore_function() -> str:
    """The restore and its helpers, lifted out of the uninstaller so they can
    run against a sandbox instead of the real rootfs.

    Starts at count_boot_pngs, not at the restore itself: the restore calls it,
    and a block that omitted it would still "pass" -- an undefined function in
    a $() substitution yields an empty string, the integer comparison guarding
    the backup deletion errors out, and the guard silently never fires."""
    text = UNINSTALL.read_text()
    start = text.index("count_boot_pngs() {")
    end = text.index('log_msg "uninstall starting"')
    return text[start:end]


class UninstallBootAnimationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.textures = self.root / "loong/textures"
        self.boot = self.textures / "boot"
        self.stock = self.textures / "boot.stock"
        for seq in ("0", "1"):
            (self.boot / seq).mkdir(parents=True)
            (self.stock / seq).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_leaf_animation(self):
        (self.boot / "0/leaf.png").write_text("leaf frame")
        (self.boot / "1/leaf.png").write_text("leaf frame")
        (self.textures / "boot.cfg").write_text('{"dir":"leaf"}')
        (self.textures / ".umrk-boot-mode").write_text("leaf\n")
        (self.textures / ".umrk-boot-installed").write_text("")

    def write_stock_backup(self, frames0=3, frames1=2, with_cfg=True):
        for i in range(frames0):
            (self.stock / f"0/{i}.png").write_text(f"stock0-{i}")
        for i in range(frames1):
            (self.stock / f"1/{i}.png").write_text(f"stock1-{i}")
        if with_cfg:
            (self.textures / "boot.cfg.stock.umrk").write_text('{"dir":"stock"}')

    def run_restore(self) -> subprocess.CompletedProcess:
        body = f'''
PLATFORM=mlp1
log_msg() {{ :; }}
BOOT_DIR="{self.boot}"
BOOT_CFG="{self.textures}/boot.cfg"
BOOT_STOCK_DIR="{self.stock}"
BOOT_STOCK_CFG="{self.textures}/boot.cfg.stock.umrk"
BOOT_MODE="{self.textures}/.umrk-boot-mode"
BOOT_STAMP="{self.textures}/.umrk-boot-installed"
restore_stock_boot_animation
echo "rc=$?"
'''
        return subprocess.run([*SHELL, restore_function() + body],
                              capture_output=True, text=True)

    def test_restores_stock_frames_and_clears_leaf_state(self):
        self.write_leaf_animation()
        self.write_stock_backup()
        result = self.run_restore()
        self.assertIn("rc=0", result.stdout)

        self.assertFalse((self.boot / "0/leaf.png").exists(),
                         "Leaf frames survived the restore")
        self.assertEqual(sorted(p.name for p in (self.boot / "0").iterdir()),
                         ["0.png", "1.png", "2.png"])
        self.assertEqual((self.textures / "boot.cfg").read_text(), '{"dir":"stock"}')

        # Leaf's bookkeeping and the backup it guarded go with it: leaving a
        # boot.stock behind would invite a second restore with nothing to
        # restore, and a stale mode file would claim leaf on a stock device.
        self.assertFalse(self.stock.exists(), "stock backup left behind")
        self.assertFalse((self.textures / ".umrk-boot-mode").exists())
        self.assertFalse((self.textures / ".umrk-boot-installed").exists())
        self.assertFalse((self.textures / "boot.cfg.stock.umrk").exists())

    def test_already_stock_is_a_noop(self):
        self.write_stock_backup()
        (self.textures / ".umrk-boot-mode").write_text("stock\n")
        (self.boot / "0/keep.png").write_text("untouched")
        result = self.run_restore()
        self.assertIn("rc=0", result.stdout)
        self.assertTrue((self.boot / "0/keep.png").exists(),
                        "a stock device had its boot dir rewritten anyway")
        self.assertTrue(self.stock.exists(), "stock backup removed on a no-op")

    def test_missing_backup_does_not_fail_the_uninstall(self):
        # Nothing was ever replaced, or the backup is gone. Returning non-zero
        # here would make the whole uninstall report failure over a cosmetic
        # detail, and there is nothing to put back either way.
        self.write_leaf_animation()
        shutil.rmtree(self.stock)
        result = self.run_restore()
        self.assertIn("rc=0", result.stdout)
        self.assertTrue((self.boot / "0/leaf.png").exists(),
                        "frames were cleared with no backup to restore from")

    def test_rebuilds_a_cfg_when_the_saved_one_is_gone(self):
        self.write_leaf_animation()
        self.write_stock_backup(frames0=5, frames1=4, with_cfg=False)
        result = self.run_restore()
        self.assertIn("rc=0", result.stdout)
        cfg = (self.textures / "boot.cfg").read_text()
        self.assertIn('"num":5', cfg, f"first sequence count wrong: {cfg}")
        self.assertIn('"num":4', cfg, f"second sequence count wrong: {cfg}")
        # Stock shape: play through once, then loop until handoff.
        self.assertIn('"repeat":1', cfg)
        self.assertIn('"repeat":-1', cfg)

    def test_partial_restore_keeps_the_backup(self):
        # Every copy in the restore is best-effort. If the frames do not all
        # land, the backup is the only remaining copy of the stock animation
        # and must survive, or a cosmetic problem becomes unrecoverable.
        self.write_leaf_animation()
        self.write_stock_backup(frames0=3, frames1=2)
        body = f'''
PLATFORM=mlp1
log_msg() {{ :; }}
BOOT_DIR="{self.boot}"
BOOT_CFG="{self.textures}/boot.cfg"
BOOT_STOCK_DIR="{self.stock}"
BOOT_STOCK_CFG="{self.textures}/boot.cfg.stock.umrk"
BOOT_MODE="{self.textures}/.umrk-boot-mode"
BOOT_STAMP="{self.textures}/.umrk-boot-installed"
# Stand in for a write that fails partway: one frame of three arrives.
cp() {{ command cp "$@" 2>/dev/null; rm -f "{self.boot}/0/2.png" 2>/dev/null; return 0; }}
restore_stock_boot_animation
echo "rc=$?"
'''
        result = subprocess.run([*SHELL, restore_function() + body],
                                capture_output=True, text=True)
        self.assertIn("rc=1", result.stdout,
                      f"a short restore reported success: {result.stdout}{result.stderr}")
        self.assertTrue(self.stock.exists(),
                        "stock backup deleted after an incomplete restore")
        self.assertTrue((self.stock / "0/2.png").exists(),
                        "stock frames lost after an incomplete restore")

    def test_non_mlp1_platform_is_left_alone(self):
        self.write_leaf_animation()
        self.write_stock_backup()
        body = restore_function() + f'''
PLATFORM=tg5040
log_msg() {{ :; }}
BOOT_DIR="{self.boot}"
BOOT_STOCK_DIR="{self.stock}"
BOOT_MODE="{self.textures}/.umrk-boot-mode"
restore_stock_boot_animation
echo "rc=$?"
'''
        result = subprocess.run([*SHELL, body], capture_output=True, text=True)
        self.assertIn("rc=0", result.stdout)
        self.assertTrue((self.boot / "0/leaf.png").exists(),
                        "a non-MLP1 platform had its boot animation rewritten")


if __name__ == "__main__":
    unittest.main()
