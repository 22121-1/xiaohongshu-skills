"""草稿管理模块自身的编辑器保护与共享导航保护保持一致。"""
from pathlib import Path

import pytest

from tests.test_navigation_guard import _NODE, assert_editor_guard


@pytest.mark.skipif(not _NODE, reason="执行网页 JavaScript 回归测试需要 Node.js")
@pytest.mark.parametrize("mode,safe", [
    ("restored_image", False),
    ("rich_text_image", False),
    ("rich_text_video", False),
    ("rich_text_audio", False),
    ("selected_hidden_file", False),
    ("text", False),
    ("draft_preview", True),
    ("empty", True),
])
def test_creator_guard_preserves_editor_media(mode, safe):
    script = (Path(__file__).resolve().parents[1] / "scripts/xhs/creator_manage.js").read_text()
    assert_editor_guard("(" + script + ")({action: 'guard'})", "safe_to_navigate", mode, safe)
