#!/usr/bin/env python3
"""A theme can ship in the release payload and still never reach the card.

That is how the bundled Grid View theme was stranded: the staging Makefile built
Themes/ into the payload, but no delivery path copied it anywhere. These tests
run the installer's own generated shell against a temp card, so the promotion is
proven end to end rather than assumed from the payload's existence.
"""

import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "make_launcher_switcher_sd", ROOT / "make_launcher_switcher_sd.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SCRIPT = MODULE.build_managed_installer_script("2026-09-11-gtheme01", "0.11.1")


def extract_function(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}$", SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, f"{name} missing from the generated installer"
    return match.group(0)


HARNESS = "\n".join([
    "set -u",
    'fail() { echo "FAIL: $1" >&2; exit 3; }',
    'log_msg() { echo "$1"; }',
    extract_function("replace_dir"),
    extract_function("promote_bundled_themes"),
    "promote_bundled_themes",
])


class BundledThemeWiringTests(unittest.TestCase):
    def test_installer_promotes_bundled_themes(self):
        self.assertIn("promote_bundled_themes", SCRIPT)
        self.assertIn('BUNDLED_THEMES="$RELEASE_ROOT/bundled-themes.txt"', SCRIPT)
        self.assertIn('THEMES_ROOT="$SDCARD_PATH/Themes"', SCRIPT)

    def test_promotion_runs_after_the_public_roots_exist(self):
        self.assertLess(
            SCRIPT.index("create_public_dirs\n"),
            SCRIPT.rindex("promote_bundled_themes"),
            "Themes/ must be created before a theme is promoted into it",
        )


class StaleStageTests(unittest.TestCase):
    """replace_dir stages at "<dst>.tmp.$$", which for a theme is inside the
    user's own Themes/ folder. The launcher's scanner skips only dot-names and
    accepts anything with a readable theme.json, so an interrupted install would
    leave a duplicate in the theme picker."""

    def test_stale_stage_is_swept_before_promotion(self):
        self.assertIn('rm -rf "$THEMES_ROOT"/*.tmp.*', SCRIPT)

    def test_sweep_runs_before_any_theme_is_promoted(self):
        self.assertLess(
            SCRIPT.index('rm -rf "$THEMES_ROOT"/*.tmp.*'),
            SCRIPT.rindex("promote_bundled_themes"),
        )

    def test_sweep_cannot_reach_a_real_theme(self):
        """The glob must not match a theme folder a user actually named."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for name in ("Sample", "My.Theme", "Sample.tmp.4242", "tmp.1"):
                (root / name).mkdir()
            subprocess.run(["sh", "-c", f'rm -rf "{root}"/*.tmp.* 2>/dev/null || true'],
                           check=True)
            left = sorted(p.name for p in root.iterdir())
            self.assertEqual(["My.Theme", "Sample", "tmp.1"], left)


class BundledThemePromotionTests(unittest.TestCase):
    """Runs the generated shell for real against a throwaway card."""

    def run_promotion(self, card: Path, release: Path):
        return subprocess.run(
            ["sh", "-c", HARNESS],
            env={
                "PATH": "/usr/bin:/bin",
                "RELEASE_THEMES": str(release / "Themes"),
                "BUNDLED_THEMES": str(release / "bundled-themes.txt"),
                "THEMES_ROOT": str(card / "Themes"),
            },
            capture_output=True,
            text=True,
        )

    def build_tree(self, tmp: Path, manifest: str):
        release, card = tmp / "release", tmp / "card"
        shipped = release / "Themes" / "Sample"
        shipped.mkdir(parents=True)
        (shipped / "theme.json").write_text("shipped-by-this-release")
        (release / "bundled-themes.txt").write_text(manifest)

        stale = card / "Themes" / "Sample"
        stale.mkdir(parents=True)
        (stale / "theme.json").write_text("from-an-older-release")
        (stale / "dropped.png").write_text("no longer part of the theme")
        mine = card / "Themes" / "MyTheme"
        mine.mkdir(parents=True)
        (mine / "theme.json").write_text("the user's own work")
        return release, card

    def test_shipped_theme_replaces_its_own_folder_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as raw:
            release, card = self.build_tree(Path(raw), "Sample\n")
            result = self.run_promotion(card, release)
            self.assertEqual(0, result.returncode, result.stderr)

            sample = card / "Themes" / "Sample"
            self.assertEqual("shipped-by-this-release",
                             (sample / "theme.json").read_text())
            self.assertFalse((sample / "dropped.png").exists(),
                             "a file dropped from the theme must not survive")
            self.assertEqual("the user's own work",
                             (card / "Themes" / "MyTheme" / "theme.json").read_text())

    def test_missing_manifest_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as raw:
            release, card = self.build_tree(Path(raw), "Sample\n")
            (release / "bundled-themes.txt").unlink()
            result = self.run_promotion(card, release)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("from-an-older-release",
                             (card / "Themes" / "Sample" / "theme.json").read_text())

    def test_unsafe_names_abort_the_install(self):
        for name in ("../escape", "/abs", "nested/theme", ".hidden", ".."):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as raw:
                release, card = self.build_tree(Path(raw), name + "\n")
                result = self.run_promotion(card, release)
                self.assertEqual(3, result.returncode,
                                 f"{name!r} was accepted: {result.stdout}")
                self.assertIn("unsafe bundled theme name", result.stderr)

    def test_a_manifest_naming_an_unstaged_theme_aborts(self):
        with tempfile.TemporaryDirectory() as raw:
            release, card = self.build_tree(Path(raw), "Sample\nNotStaged\n")
            result = self.run_promotion(card, release)
            self.assertEqual(3, result.returncode, result.stdout)
            self.assertIn("missing bundled theme payload", result.stderr)


if __name__ == "__main__":
    unittest.main()
