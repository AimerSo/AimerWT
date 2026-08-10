# -*- coding: utf-8 -*-

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.build import EXE_DISPLAY_NAME
from scripts.prepare_release_assets import prepare_release_asset


class PrepareReleaseAssetsTests(unittest.TestCase):
    def test_windows_asset_gets_unique_name_and_matching_checksum(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist_dir = root / "dist"
            output_dir = root / "release-assets"
            source = dist_dir / f"{EXE_DISPLAY_NAME}.exe"
            source.parent.mkdir()
            source.write_bytes(b"windows-build")

            target, checksum = prepare_release_asset(
                "Windows",
                "amd64",
                dist_dir=dist_dir,
                output_dir=output_dir,
            )

            self.assertEqual(target.name, "AimerWT_V3.1_Beta_Windows_amd64.exe")
            self.assertEqual(checksum.name, "checksum_Windows_amd64.txt")
            expected_hash = hashlib.sha256(b"windows-build").hexdigest()
            checksum_text = checksum.read_text(encoding="utf-8")
            self.assertIn(f"File: {target.name}", checksum_text)
            self.assertIn(f"SHA256: {expected_hash}", checksum_text)

    def test_linux_asset_keeps_executable_without_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist_dir = root / "dist"
            output_dir = root / "release-assets"
            source = dist_dir / EXE_DISPLAY_NAME
            source.parent.mkdir()
            source.write_bytes(b"linux-build")

            target, checksum = prepare_release_asset(
                "Linux",
                "arm64",
                dist_dir=dist_dir,
                output_dir=output_dir,
            )

            self.assertEqual(target.name, "AimerWT_V3.1_Beta_Linux_arm64")
            self.assertTrue(target.is_file())
            self.assertTrue(checksum.is_file())


if __name__ == "__main__":
    unittest.main()
