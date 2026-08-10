# -*- coding: utf-8 -*-
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_windows_arm64_is_not_scheduled(self):
        for workflow_name in ("build.yml", "release.yml"):
            workflow = (PROJECT_ROOT / ".github" / "workflows" / workflow_name).read_text(
                encoding="utf-8"
            )
            self.assertNotIn("windows-11-arm", workflow)

    def test_release_assets_keep_supported_arm64_targets(self):
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("AimerWT_V3.1_Beta_Windows_arm64.exe", workflow)
        self.assertNotIn("checksum_Windows_arm64.txt", workflow)
        self.assertIn("AimerWT_V3.1_Beta_Linux_arm64", workflow)
        self.assertIn("AimerWT_V3.1_Beta_macOS_arm64.zip", workflow)


if __name__ == "__main__":
    unittest.main()
