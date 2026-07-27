#!/usr/bin/env python3

import importlib.util
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


class ReleaseVersionTests(unittest.TestCase):
    def test_explicit_version_is_distinct_from_release_id(self):
        script = MODULE.build_managed_installer_script(
            "2026-07-20-gabc1234", "0.7.0"
        )
        self.assertIn('RELEASE_ID="2026-07-20-gabc1234"', script)
        self.assertIn('RELEASE_VERSION="0.7.0"', script)
        self.assertIn('"version": "$RELEASE_VERSION"', script)
        self.assertIn('"release_id": "$RELEASE_ID"', script)

    def test_legacy_call_uses_release_id_as_version(self):
        script = MODULE.build_managed_installer_script("2026-07-20-gabc1234")
        self.assertIn('RELEASE_VERSION="2026-07-20-gabc1234"', script)

    def test_release_version_accepts_supported_suffixes(self):
        for value in (
            "0.7.0",
            "0.7.0-rc.1",
            "0.7.0-save-isolation-ota1",
            "0.7.0+build.4",
        ):
            with self.subTest(value=value):
                MODULE.validate_release_version(value)

    def test_release_version_rejects_unsafe_or_nonsemantic_values(self):
        for value in (
            "",
            "v0.7.0",
            "0.7",
            "2026-07-20-gabc1234",
            "0.7.0$(touch nope)",
            "10000.0.0",
        ):
            with self.subTest(value=value):
                with self.assertRaises(SystemExit):
                    MODULE.validate_release_version(value)

    def test_platform_payload_promotes_runtime_directory(self):
        with tempfile.TemporaryDirectory() as raw:
            sd_root = Path(raw)
            runtime = (
                sd_root
                / ".system/leaf/releases/candidate/platforms/mlp1/runtime"
            )
            runtime.mkdir(parents=True)
            MODULE.validate_platform_payload_coverage(sd_root, "candidate")
        self.assertIn("runtime", MODULE.PROMOTED_PLATFORM_DIRS)

    def test_platform_payload_promotes_shader_directory(self):
        with tempfile.TemporaryDirectory() as raw:
            sd_root = Path(raw)
            shaders = (
                sd_root
                / ".system/leaf/releases/candidate/platforms/mlp1/shaders"
            )
            shaders.mkdir(parents=True)
            MODULE.validate_platform_payload_coverage(sd_root, "candidate")
        self.assertIn("shaders", MODULE.PROMOTED_PLATFORM_DIRS)

    def test_managed_installer_preserves_and_syncs_shader_namespaces(self):
        script = MODULE.build_managed_installer_script("candidate")
        self.assertIn("migrate_legacy_downloaded_shaders", script)
        self.assertIn("sync_leaf_shaders", script)
        self.assertIn(
            'USER_SHADERS="${UMRK_RETROARCH_USER_SHADERS_DIR:-'
            '$INTERNAL_DATA/retroarch/.config/retroarch/shaders}"',
            script,
        )
        self.assertIn("for namespace in leaf-bundled leaf-recommended", script)
        self.assertIn('[ "$preset_count" -gt 11 ]', script)


if __name__ == "__main__":
    unittest.main()
