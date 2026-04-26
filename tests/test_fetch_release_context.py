import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fetch_release_context.py"
SPEC = importlib.util.spec_from_file_location("fetch_release_context", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FetchReleaseContextTests(unittest.TestCase):
    def test_main_allows_empty_issue_and_pull_artifacts(self):
        repo_url = "https://gitcode.com/Ascend/msprof-analyze"
        roadmap_url = "https://gitcode.com/Ascend/msprof-analyze/issues/5"

        repo_payload = {
            "name": "msprof-analyze",
            "default_branch": "main",
        }
        roadmap_payload = {
            "number": 5,
            "title": "[Roadmap] 2026 Q1",
            "body": "No linked issues or pulls.",
        }

        def fake_http_get(url, token, *, expect_json, quiet, log_file=None):
            self.assertEqual(token, "fake-token")
            self.assertTrue(expect_json)
            if url.endswith("/repos/Ascend/msprof-analyze"):
                return repo_payload
            if url.endswith("/repos/Ascend/msprof-analyze/issues/5"):
                return roadmap_payload
            raise AssertionError(f"Unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "release-context"
            argv = [
                "fetch_release_context.py",
                "--repo",
                repo_url,
                "--roadmap",
                roadmap_url,
                "--time-range",
                "2026Q1",
                "--output-dir",
                str(output_dir),
                "--token",
                "fake-token",
                "--quiet",
            ]

            with mock.patch.object(MODULE, "fetch_paginated", side_effect=[[], []]), \
                 mock.patch.object(MODULE, "http_get", side_effect=fake_http_get), \
                 mock.patch.object(MODULE, "fetch_optional_json", return_value=[]), \
                 mock.patch.object(MODULE, "fetch_repo_tree", return_value={"tree": []}), \
                 mock.patch.object(sys, "argv", argv):
                MODULE.main()

            self.assertEqual((output_dir / "raw" / "issue-numbers.txt").read_text(encoding="utf-8"), "")
            self.assertEqual((output_dir / "raw" / "pr-numbers.txt").read_text(encoding="utf-8"), "")
            self.assertEqual((output_dir / "raw" / "roadmap-linked-issue-numbers.txt").read_text(encoding="utf-8"), "")
            self.assertEqual((output_dir / "raw" / "roadmap-linked-pr-numbers.txt").read_text(encoding="utf-8"), "")
            self.assertEqual((output_dir / "raw" / "pr-details" / "index.txt").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
