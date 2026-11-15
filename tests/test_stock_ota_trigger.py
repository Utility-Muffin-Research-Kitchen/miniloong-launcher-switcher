#!/usr/bin/env python3
"""The session hands a boot to stock only for a trigger stock will run.

Stock's loong_daemon::upgradeFromTfCard() reads /mnt/sdcard/loong_upgrade and
no other path. The session used to defer for a trigger on either card, so a
loong_upgrade left on the card mounted at /media/sdcard1 kept every boot in
stock while nothing ever ran it (seen on LoongOS 1.4.0.52, 2026-11-15).
"""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SESSION = (ROOT / "device/umrk-leaf-session").read_text()

TRIGGER = '{"verInner": 1, "otaFile": "launcher_probe.bin", "otaCommand": "true"}\n'


def session_function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", SESSION, re.M | re.S)[0]


class StockOtaTriggerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.primary = self.root / "mnt/sdcard"
        self.secondary = self.root / "media/sdcard1"
        self.primary.mkdir(parents=True)
        self.secondary.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, secondary=None):
        secondary = self.secondary if secondary is None else secondary
        script = "\n".join([
            f'log_msg() {{ echo "log: $*"; }}',
            session_function("loong_upgrade_looks_valid"),
            session_function("stock_ota_present"),
            f'STOCK_OTA_TRIGGER="{self.primary}/loong_upgrade"',
            f'SECONDARY_SD_MOUNT="{secondary}"',
            'if stock_ota_present; then echo defer; else echo leaf; fi',
        ])
        result = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_trigger_on_the_stock_path_defers(self):
        (self.primary / "loong_upgrade").write_text(TRIGGER)
        self.assertIn("defer", self.run_check())

    def test_trigger_on_both_cards_defers(self):
        # Leaf's update runner copies the trigger to both card roots because
        # the cards can swap mount points; stock runs the /mnt/sdcard copy.
        (self.primary / "loong_upgrade").write_text(TRIGGER)
        (self.secondary / "loong_upgrade").write_text(TRIGGER)
        self.assertIn("defer", self.run_check())

    def test_trigger_only_on_the_second_card_boots_leaf(self):
        (self.secondary / "loong_upgrade").write_text(TRIGGER)
        out = self.run_check()
        self.assertIn("leaf", out)
        self.assertNotIn("defer", out)
        self.assertIn("ignoring", out, "the ignored trigger was not logged")

    def test_used_or_invalid_triggers_are_ignored(self):
        (self.primary / "loong_upgrade.used").write_text(TRIGGER)
        (self.primary / "loong_upgrade").write_text("not a trigger\n")
        out = self.run_check()
        self.assertIn("leaf", out)
        self.assertNotIn("ignoring", out)

    def test_no_second_card(self):
        out = self.run_check(secondary="")
        self.assertIn("leaf", out)


if __name__ == "__main__":
    unittest.main()
