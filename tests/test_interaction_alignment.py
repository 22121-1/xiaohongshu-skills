"""互动写入的身份绑定、单次提交和结果核验回归测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from xhs import comment, like_favorite
from xhs.errors import NoFeedDetailError

FEED = "a" * 24
USER = "b" * 24
TARGET = "c" * 24


def interact_state(feed_id=FEED, *, liked=False, collected=False, path=None):
    return json.dumps(
        {
            "pathname": path or f"/explore/{feed_id}",
            "noteDetailMap": {
                feed_id: {
                    "note": {
                        "noteId": feed_id,
                        "interactInfo": {"liked": liked, "collected": collected},
                    }
                }
            },
        }
    )


def test_interact_state_requires_exact_url_and_map_identity():
    page = Mock()
    page.evaluate.return_value = interact_state("d" * 24)
    with pytest.raises(NoFeedDetailError):
        like_favorite._get_interact_state(page, FEED)
    page.evaluate.return_value = interact_state(FEED, path=f"/explore/{'d' * 24}")
    with pytest.raises(NoFeedDetailError):
        like_favorite._get_interact_state(page, FEED)


def test_unknown_initial_like_state_never_clicks():
    page = Mock()
    page.evaluate.return_value = ""
    result = like_favorite._toggle_like(page, FEED, True)
    assert result.status == "unknown" and not result.success
    page.click_element.assert_not_called()


def test_like_unconfirmed_after_click_does_not_toggle_again(monkeypatch):
    page = Mock()
    page.evaluate.return_value = interact_state()
    page.has_element.return_value = True
    monkeypatch.setattr(like_favorite, "_wait_interact_state", lambda *a, **k: False)
    result = like_favorite._toggle_like(page, FEED, True)
    assert result.status == "unknown" and not result.success
    page.click_element.assert_called_once()


def test_favorite_click_exception_is_unknown_not_safe_to_retry():
    page = Mock()
    page.evaluate.return_value = interact_state()
    page.has_element.return_value = True
    page.click_element.side_effect = RuntimeError("bridge disconnected")
    result = like_favorite._toggle_favorite(page, FEED, True)
    assert result.status == "unknown" and not result.success
    page.click_element.assert_called_once()


def test_idempotent_like_reports_unchanged_without_click():
    page = Mock()
    page.evaluate.return_value = interact_state(liked=True)
    result = like_favorite._toggle_like(page, FEED, True)
    assert result.status == "unchanged" and result.success
    page.click_element.assert_not_called()


def test_find_checks_loaded_target_before_end(monkeypatch):
    page = Mock()
    monkeypatch.setattr(comment, "sleep_random", lambda *a: None)
    monkeypatch.setattr(comment, "_check_end_container", lambda page: True)
    target = {"id": TARGET, "root_id": TARGET, "author_id": USER}
    calls = []

    def run(page, action, feed_id, **params):
        calls.append((action, params))
        return {"found": True, "target": target}

    monkeypatch.setattr(comment, "_run_dom", run)
    assert comment._find_and_scroll_to_comment(page, FEED, TARGET, USER) == target
    assert calls[0][0] == "lookup"


def test_comment_id_lookup_never_falls_back_to_user(monkeypatch):
    page = Mock()
    monkeypatch.setattr(comment, "sleep_random", lambda *a: None)
    monkeypatch.setattr(comment, "_check_end_container", lambda page: True)
    calls = []

    def run(page, action, feed_id, **params):
        calls.append((action, params))
        return {"found": False}

    monkeypatch.setattr(comment, "_run_dom", run)
    with pytest.raises(comment.CommentError, match="未找到评论"):
        comment._find_and_scroll_to_comment(page, FEED, TARGET, USER)
    assert calls[0][1]["comment_id"] == TARGET
    assert calls[0][1]["user_id"] == ""


def test_find_expands_replies_then_rechecks(monkeypatch):
    page = Mock()
    monkeypatch.setattr(comment, "sleep_random", lambda *a: None)
    monkeypatch.setattr(comment, "_check_end_container", lambda page: False)
    target = {"id": TARGET, "root_id": "d" * 24, "author_id": USER}
    lookups = iter([{"found": False}, {"found": True, "target": target}])

    def run(page, action, feed_id, **params):
        if action == "lookup":
            return next(lookups)
        assert action == "mark_expand"
        return {"found": True, "selector": '[data-xhs-expand-token="fixture"]'}

    monkeypatch.setattr(comment, "_run_dom", run)
    assert comment._find_and_scroll_to_comment(page, FEED, TARGET, "") == target
    page.click_element.assert_called_once_with('[data-xhs-expand-token="fixture"]')


def test_submit_verification_error_is_unknown(monkeypatch):
    page = Mock()
    monkeypatch.setattr(comment, "_run_dom", Mock(side_effect=RuntimeError("cdp lost")))
    with pytest.raises(comment.CommentError) as caught:
        comment._wait_new_comment(
            page, FEED, before_ids=[], account_id=USER, content="正文", timeout=0
        )
    assert caught.value.status == "unknown"


def test_reply_uses_bound_comment_selector_and_returns_verified_id(monkeypatch):
    page = Mock()
    page.has_element.return_value = True
    monkeypatch.setattr(comment, "sleep_random", lambda *a: None)
    monkeypatch.setattr(comment, "_check_page_accessible", lambda page: None)
    target = {"id": TARGET, "root_id": TARGET, "author_id": USER}
    snapshots = {"account": {"user_id": "e" * 24}, "comments": []}
    monkeypatch.setattr(comment, "_snapshot", lambda *a: snapshots)
    monkeypatch.setattr(comment, "_find_and_scroll_to_comment", lambda *a: target)
    monkeypatch.setattr(comment, "_wait_reply_binding", lambda *a: None)
    monkeypatch.setattr(comment, "_run_dom", lambda *a, **k: {"found": True, "target": target})
    monkeypatch.setattr(comment, "_wait_new_comment", lambda *a, **k: {"id": "f" * 24})
    result = comment.reply_comment(page, FEED, "token", "回复", TARGET, USER)
    bound = f'[id="comment-{TARGET}"] {comment.REPLY_BUTTON}'
    assert page.click_element.call_args_list[0].args == (bound,)
    assert result["reply_id"] == "f" * 24
    assert result["target_comment_id"] == TARGET
