import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "generate_release_note.py"
SPEC = importlib.util.spec_from_file_location("generate_release_note", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class GenerateReleaseNoteTests(unittest.TestCase):
    def test_parse_time_range_quarter_uses_real_month_end(self):
        self.assertEqual(MODULE.parse_time_range("2026Q1"), ("2026-01-01", "2026-03-31"))
        self.assertEqual(MODULE.parse_time_range("2024-02"), ("2024-02-01", "2024-02-29"))

    def test_filter_by_time_includes_full_end_date(self):
        items = [
            {"created_at": "2026-03-31T23:59:59+00:00"},
            {"created_at": "2026-04-01T00:00:00+00:00"},
        ]
        filtered = MODULE.filter_by_time(items, "2026-01-01", "2026-03-31")
        self.assertEqual(len(filtered), 1)

    def test_classify_item_distinguishes_feature_change_bug(self):
        feature = {"title": "[Feature]: nputrace支持异步解析", "body": "", "labels": []}
        change = {"title": "docs: 优化主页readme", "body": "", "labels": []}
        bugfix = {"title": "[Bug]: monitor.save() 路径不存在时不会创建目录", "body": "", "labels": []}

        self.assertEqual(MODULE.classify_item(feature), "feature")
        self.assertEqual(MODULE.classify_item(change), "doc")
        self.assertEqual(MODULE.classify_item(bugfix), "bugfix")

    def test_infer_support_matrix_extracts_versions_and_dependencies(self):
        readme = """
        支持 Atlas 200I/500 A2 推理产品。
        Ubuntu 22.04, openEuler 22.03。
        Python版本：3.7.5 及以上
        依赖 sqlite3 与 prometheus。
        """
        docs = "CANN版本：8.2.RC1；PyTorch版本：2.1 及以上"
        rows = MODULE.infer_support_matrix(readme, docs)
        as_dict = {name: (version, note) for name, version, note in rows}

        self.assertIn("Atlas 200I", as_dict["产品型号"][0])
        self.assertIn("Ubuntu 22.04", as_dict["操作系统"][0])
        self.assertEqual(as_dict["CANN版本"][0], "8.2.RC1")
        self.assertEqual(as_dict["Python版本"][0], "3.7.5 及以上")
        self.assertIn("SQLite3", as_dict["依赖三方库"][0])

    def test_describe_bugfix_infers_scope(self):
        item = {"title": "monitor save file bugfix", "body": ""}
        description, scope = MODULE.describe_bugfix(item, [])
        self.assertIn("monitor save file bugfix", description.lower())
        self.assertIn("文件输出", scope)

    def test_generate_release_note_renders_meaningful_sections(self):
        repo = {"description": "昇腾 AI 场景的轻量性能采集与监控"}
        issues = [
            {
                "number": 2,
                "title": "[Feature]: npumonitor支持按算子名筛选",
                "body": "支持按算子名筛选，便于缩小分析范围。",
                "html_url": "https://gitcode.com/Ascend/msmonitor/issues/2",
                "created_at": "2026-01-05T00:00:00+00:00",
                "labels": [],
            },
            {
                "number": 6,
                "title": "[Bug]: monitor.save()中路径为合法但不存在的路径时，不会进行目录创建",
                "body": "修复结果保存路径不存在时未创建目录的问题。",
                "html_url": "https://gitcode.com/Ascend/msmonitor/issues/6",
                "created_at": "2026-02-05T00:00:00+00:00",
                "labels": [],
            },
        ]
        pulls = [
            {
                "number": 38,
                "title": "npu-monitor支持按算子名称进行筛选",
                "body": "- 支持按算子名称进行筛选，减少无关数据干扰。",
                "html_url": "https://gitcode.com/Ascend/msmonitor/merge_requests/38",
                "created_at": "2026-01-15T00:00:00+00:00",
                "labels": [],
                "user": {"login": "alice", "name": "Alice"},
            },
            {
                "number": 47,
                "title": "monitor save file bugfix",
                "body": "修复 monitor save file 场景下目录不存在时保存失败的问题。",
                "html_url": "https://gitcode.com/Ascend/msmonitor/merge_requests/47",
                "created_at": "2026-02-15T00:00:00+00:00",
                "labels": [],
                "user": {"login": "bob", "name": "Bob"},
            },
        ]
        roadmap = {
            "title": "[Roadmap] msMonitor Roadmap 2026 Q1",
            "body": "- npumonitor\n- nputrace\n- 轻量API采集模块",
        }
        releases = [{"tag_name": "tag_MindStudio_26.0.0.B100_001", "created_at": "2026-04-01T00:00:00+00:00"}]

        def fake_fetch_raw_file(_owner, _repo, file_path, _token):
            if file_path == "README.md":
                return "支持 Atlas 200I/500 A2 推理产品。\nPython版本：3.7.5 及以上\n依赖 sqlite3。"
            return ""

        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "MindStudio-Monitor-26.0.0-release-note.md"
            with mock.patch.object(MODULE, "fetch_repo", return_value=repo), \
                 mock.patch.object(MODULE, "fetch_issues", return_value=issues), \
                 mock.patch.object(MODULE, "fetch_pulls", return_value=pulls), \
                 mock.patch.object(MODULE, "fetch_issue_detail", return_value=roadmap), \
                 mock.patch.object(MODULE, "fetch_raw_file", side_effect=fake_fetch_raw_file), \
                 mock.patch.object(MODULE, "fetch_releases", return_value=releases), \
                 mock.patch.object(MODULE, "fetch_tags", return_value=[]):
                content = MODULE.generate_release_note(
                    output_file=str(output),
                    repo_url="https://gitcode.com/Ascend/msmonitor",
                    roadmap_url="https://gitcode.com/Ascend/msmonitor/issues/5",
                    time_range="2026Q1",
                    token="fake-token",
                    version="26.0.0",
                )

        self.assertIn("发布日期：2026-04-01", content)
        self.assertIn("tag_MindStudio_26.0.0.B100_001", content)
        self.assertIn("支持按算子名称进行筛选", content)
        self.assertIn("结果保存与本地文件输出场景", content)
        self.assertNotIn("请补充", content)


if __name__ == "__main__":
    unittest.main()
