"""发布读回补丁的零依赖回归检查，可直接用 python3 执行。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cli
from xhs import publish
from xhs.bridge import BridgePage


class PublishReadbackTests(unittest.TestCase):
    def test_find_content_editor_uses_visible_unique_marker(self) -> None:
        page = Mock()
        page.evaluate.return_value = "[data-xhs-cli-content-editor='true']"
        self.assertEqual(
            publish._find_content_element(page),
            "[data-xhs-cli-content-editor='true']",
        )
        expression = page.evaluate.call_args.args[0]
        self.assertIn("getBoundingClientRect", expression)
        self.assertIn("contenteditable='true'", expression)

    def test_find_content_editor_rejects_hidden_only_dom(self) -> None:
        page = Mock()
        page.evaluate.return_value = ""
        with self.assertRaises(publish.PublishError):
            publish._find_content_element(page)

    def test_tiptap_fallback_reads_visible_editor(self) -> None:
        page = Mock()
        page.get_element_text.return_value = ""
        page.evaluate.return_value = "Tiptap 正文"
        self.assertEqual(cli._read_publish_editor(page, "div.ql-editor"), "Tiptap 正文")

    def test_normalize_platform_topic_entity_text(self) -> None:
        self.assertEqual(
            cli._normalize_publish_editor_text(
                "测试正文\n#话题A[话题]# #话题B[话题]# "
            ),
            "测试正文#话题A#话题B",
        )

    def test_verify_requires_platform_topic_entities(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            title_file = Path(temp_dir) / "title.txt"
            body_file = Path(temp_dir) / "body.txt"
            title_file.write_text("测试标题", encoding="utf-8")
            body_file.write_text("测试正文", encoding="utf-8")
            page = Mock()
            page.get_element_attribute.return_value = "测试标题"
            page.get_elements_count.return_value = 1
            captured: list[tuple[dict, int]] = []
            args = SimpleNamespace(
                title_file=str(title_file),
                content_file=str(body_file),
                tags=["话题A", "话题B"],
                expected_image_count=1,
                bridge_url="ws://unused",
            )
            with patch("cli._connect_existing", return_value=(Mock(), page)), \
                 patch(
                     "cli._read_publish_editor",
                     return_value="测试正文\n#话题A[话题]# #话题B[话题]# ",
                 ), \
                 patch("cli._read_publish_topic_entities", return_value=["话题A", "话题B"]), \
                 patch("xhs.publish._find_content_element", return_value=".editor"), \
                 patch("cli._output", side_effect=lambda data, exit_code=0: captured.append((data, exit_code))):
                cli.cmd_verify_publish_form(args)
            self.assertTrue(captured[0][0]["success"])
            self.assertEqual(captured[0][1], 0)

    def test_verify_rejects_raw_topic_text_even_when_spaced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            title_file = Path(temp_dir) / "title.txt"
            body_file = Path(temp_dir) / "body.txt"
            title_file.write_text("测试标题", encoding="utf-8")
            body_file.write_text("测试正文", encoding="utf-8")
            page = Mock()
            page.get_element_attribute.return_value = "测试标题"
            page.get_elements_count.return_value = 1
            captured: list[tuple[dict, int]] = []
            args = SimpleNamespace(
                title_file=str(title_file),
                content_file=str(body_file),
                tags=["话题A", "话题B"],
                expected_image_count=1,
                bridge_url="ws://unused",
            )
            with patch("cli._connect_existing", return_value=(Mock(), page)), \
                 patch("cli._read_publish_editor", return_value="测试正文\n#话题A #话题B "), \
                 patch("cli._read_publish_topic_entities", return_value=[]), \
                 patch("xhs.publish._find_content_element", return_value=".editor"), \
                 patch("cli._output", side_effect=lambda data, exit_code=0: captured.append((data, exit_code))):
                cli.cmd_verify_publish_form(args)
            self.assertFalse(captured[0][0]["success"])
            self.assertFalse(captured[0][0]["topics_match_and_separated"])
            self.assertFalse(captured[0][0]["topics_recognized_as_entities"])
            self.assertEqual(captured[0][1], 2)

    def test_topic_reader_accepts_platform_marker_without_stable_dom_attributes(self) -> None:
        page = Mock()
        page.evaluate.return_value = []
        with patch(
            "cli._read_publish_editor",
            return_value="#话题A[话题]# #话题B[话题]#",
        ):
            self.assertEqual(
                cli._read_publish_topic_entities(page, ".editor"),
                ["话题A", "话题B"],
            )

    def test_single_topic_uses_real_debugger_click(self) -> None:
        page = Mock()
        page.has_element.return_value = True
        with patch("xhs.publish.time.sleep"), patch(
            "xhs.publish.random.uniform", return_value=0
        ):
            publish._input_single_tag(page, ".editor", "微恐故事")
        page.click_element_by_text.assert_called_once()
        page.click_element.assert_not_called()

    def test_input_tags_inserts_space_after_every_topic(self) -> None:
        page = Mock()
        page.evaluate.return_value = 1
        with patch("xhs.publish._input_single_tag"), patch("xhs.publish.time.sleep"):
            publish._input_tags(page, ".editor", ["A", "B"])
        spaces = [call for call in page.type_text.call_args_list if call.args == (" ",)]
        self.assertEqual(len(spaces), 2)

    def test_bridge_falls_back_to_debugger_input_when_readback_differs(self) -> None:
        page = BridgePage.__new__(BridgePage)
        page._call = Mock(return_value={"text": ""})
        page.evaluate = Mock()
        page.type_text = Mock()
        page.get_element_text = Mock(return_value="正文")
        page.input_content_editable(".editor", "正文")
        page.type_text.assert_called_once_with("正文", delay_ms=20)


if __name__ == "__main__":
    unittest.main()
