#!/usr/bin/env python3
"""A theme can ship in the release payload and still never reach the card.

That is how the bundled Grid View theme was stranded: the staging Makefile built
Themes/ into the payload, but no delivery path copied it anywhere. These tests
run the installer's own generated shell against a temp card, so the promotion is
proven end to end rather than assumed from the payload's existence.
"""

import importlib.util
import os
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
    extract_function("promote_bundled_themes"),
    "promote_bundled_themes",
])

# The one line of the install sequence that clears a stage left by an
# interrupted run, taken from the generated script rather than retyped.
SWEEP = next((l for l in SCRIPT.splitlines()
              if l.startswith('rm -rf "$THEME_STAGE_ROOT"') and "||" in l), None)


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
    """Themes/ holds user-owned folders and reserves no naming pattern, so the
    installer must never leave anything there for a later run to guess about,
    and must never sweep it by shape. It stages on its own ground instead."""

    def test_nothing_is_swept_out_of_the_themes_root(self):
        for line in SCRIPT.splitlines():
            stripped = line.strip()
            if stripped.startswith("rm -rf") and "$THEMES_ROOT" in stripped:
                self.assertIn(
                    '"$THEMES_ROOT/$theme"', stripped,
                    f"only an explicitly named theme may be removed: {stripped}")

    def test_the_stage_lives_outside_the_themes_root(self):
        self.assertIn('THEME_STAGE_ROOT="$SYSTEM_ROOT/theme-stage"', SCRIPT)

    def test_an_interrupted_stage_is_cleared_and_themes_untouched(self):
        self.assertIsNotNone(SWEEP, "no stage cleanup in the generated installer")
        """A real leftover stage, cleared without reaching user content."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            stage, themes = root / "system" / "theme-stage", root / "Themes"
            (stage / "Sample").mkdir(parents=True)
            (stage / "Sample" / "theme.json").write_text("interrupted")
            for name in ("My.tmp.Theme", "Holiday.tmp.2026", "Sample"):
                (themes / name).mkdir(parents=True)
                (themes / name / "theme.json").write_text("{}")
                (themes / name / "custom-art.png").write_bytes(b"user fixture")

            subprocess.run(["sh", "-c", SWEEP], check=True,
                           env={**os.environ, "THEME_STAGE_ROOT": str(stage),
                                "THEMES_ROOT": str(themes)})

            self.assertFalse(stage.exists(), "the owned stage must be removed")
            self.assertEqual(["Holiday.tmp.2026", "My.tmp.Theme", "Sample"],
                             sorted(p.name for p in themes.iterdir()))
            for name in ("My.tmp.Theme", "Holiday.tmp.2026"):
                self.assertEqual(b"user fixture",
                                 (themes / name / "custom-art.png").read_bytes())


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
                "THEME_STAGE_ROOT": str(card / "system" / "theme-stage"),
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
        # Names chosen to include the shapes an ownership-guessing sweep would
        # have destroyed: ".tmp." is not reserved, and a user may well use it.
        for name in ("MyTheme", "My.tmp.Theme", "Holiday.tmp.2026"):
            mine = card / "Themes" / name
            mine.mkdir(parents=True)
            (mine / "theme.json").write_text("the user's own work")
            (mine / "custom-art.png").write_bytes(b"user fixture")
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
            for name in ("MyTheme", "My.tmp.Theme", "Holiday.tmp.2026"):
                self.assertEqual("the user's own work",
                                 (card / "Themes" / name / "theme.json").read_text(),
                                 f"{name} must survive promotion")
                self.assertEqual(b"user fixture",
                                 (card / "Themes" / name / "custom-art.png").read_bytes())
            self.assertFalse((card / "system" / "theme-stage").exists(),
                             "the stage must not be left behind")

    def test_missing_manifest_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as raw:
            release, card = self.build_tree(Path(raw), "Sample\n")
            (release / "bundled-themes.txt").unlink()
            result = self.run_promotion(card, release)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("from-an-older-release",
                             (card / "Themes" / "Sample" / "theme.json").read_text())
            for name in ("My.tmp.Theme", "Holiday.tmp.2026"):
                self.assertTrue((card / "Themes" / name).is_dir(),
                                f"{name} must survive a release with no manifest")

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
