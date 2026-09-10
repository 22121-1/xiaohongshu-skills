from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from xhs.export import to_markdown
from xhs.feed_detail import _extract_feed_detail
from xhs.types import (
    ActionResult,
    CommentList,
    CommentLoadConfig,
    CommentPagination,
    FeedDetail,
)
from xhs.urls import make_user_profile_url
from xhs.user_profile import (
    _EXTRACT_USER_NOTES_JS,
    _extract_user_profile_data,
    normalize_profile_tab,
)


def _comment(
    comment_id: str,
    *,
    reply_count: str = "0",
    replies: list[dict] | None = None,
    replies_more: bool | None = None,
):
    result = {
        "id": comment_id,
        "content": comment_id,
        "subCommentCount": reply_count,
        "subComments": replies or [],
    }
    if replies_more is not None:
        result.update(subCommentHasMore=replies_more, subCommentCursor="reply-cursor")
    return result


def test_comment_config_zero_and_negative_values_are_bounded_to_twenty():
    assert CommentLoadConfig().normalized().max_comment_items == 20
    config = CommentLoadConfig(max_comment_items=-1, max_replies_threshold=0).normalized()
    assert config.max_comment_items == 20
    assert config.max_replies_threshold == 10
    explicit = CommentLoadConfig(max_comment_items=1, max_replies_threshold=2).normalized()
    assert explicit.max_comment_items == 1
    assert explicit.max_replies_threshold == 2


def test_comment_pagination_never_uses_root_has_more_to_claim_replies_complete():
    comments = CommentList.from_dict({
        "cursor": "next",
        "hasMore": False,
        "list": [_comment("root", reply_count="2")],
    })
    pagination = CommentPagination.from_comments(comments, stopped_reason="end")
    assert pagination.root_comments_complete is True
    assert pagination.sub_comments_complete is False
    assert pagination.comments_complete is False
    assert pagination.to_dict()["has_more"] is False

    unknown = CommentList.from_dict({"list": [_comment("root", reply_count="未知")]})
    metadata = CommentPagination.from_comments(unknown, stopped_reason="end").to_dict()
    assert metadata["has_more"] is None
    assert metadata["sub_comments_complete"] is None
    assert metadata["comments_complete"] is None

    explicit = CommentList.from_dict({
        "list": [_comment("root", reply_count="1", replies_more=True)],
    })
    serialized = explicit.list_[0].to_dict()
    assert serialized["subCommentHasMore"] is True
    assert serialized["subCommentCursor"] == "reply-cursor"
    assert CommentPagination.from_comments(
        explicit, stopped_reason="end",
    ).sub_comments_complete is False


def test_detail_output_strictly_truncates_batch_overshoot_to_limit():
    comments = [_comment(str(index)) for index in range(23)]
    page = Mock()
    page.evaluate.side_effect = [
        json.dumps({"note": {"note": {"noteId": "note-1"}, "comments": {
            "list": comments, "hasMore": False, "cursor": "cursor-1",
        }}}),
        {"body": "正文", "tags": ["话题"]},
    ]
    result = _extract_feed_detail(page, "note", comment_limit=20).to_dict()
    assert len(result["comments"]) == 20
    assert result["comment_pagination"] == {
        "cursor": "cursor-1",
        "has_more": False,
        "first_request_finished": None,
        "limit": 20,
        "loaded_root_comments": 20,
        "stopped_reason": "limit",
        "root_comments_complete": False,
        "sub_comments_complete": True,
        "comments_complete": False,
    }


def test_feed_detail_preserves_every_stream_bucket_and_decodes_nested_media_v2():
    subtitles = {"source": [{"url": "https://example.com/zh.srt", "language": "zh"}]}
    media_v2 = json.dumps(json.dumps({"video": {"subtitles": subtitles}}))
    streams = {
        "h264": [{"masterUrl": "https://example.com/h264.mp4"}],
        "EF4": [{"masterUrl": "https://example.com/ef4.mp4", "unknown": 7}],
        "future-codec": [{"masterUrl": "https://example.com/future.mp4"}],
    }
    result = FeedDetail.from_dict({
        "noteId": "note-1",
        "video": {"media": {"videoId": 9, "stream": streams}, "mediaV2": media_v2},
    }).to_dict()
    assert result["video"]["media"]["stream"] == streams
    assert result["video"]["subtitles"] == subtitles


def test_bad_media_v2_does_not_drop_video_streams():
    result = FeedDetail.from_dict({
        "video": {
            "media": {"stream": {"EF4": [{"masterUrl": "https://example.com/v.mp4"}]}},
            "mediaV2": "not-json",
        },
    }).to_dict()
    assert "subtitles" not in result["video"]
    assert "EF4" in result["video"]["media"]["stream"]


@pytest.mark.parametrize("value, expected", [
    ("", "note"), ("notes", "note"), ("收藏", "fav"),
    ("FAVORITES", "fav"), (" like ", "liked"),
])
def test_profile_tab_aliases(value, expected):
    assert normalize_profile_tab(value) == expected


def test_profile_url_only_adds_tab_for_non_default_and_encodes_token():
    base = make_user_profile_url("uid", "a+b&c", "note")
    assert parse_qs(urlsplit(base).query)["xsec_token"] == ["a+b&c"]
    assert "tab" not in parse_qs(urlsplit(base).query)
    favorite = parse_qs(urlsplit(make_user_profile_url("uid", "token", "fav")).query)
    assert favorite["tab"] == ["fav"]
    assert favorite["subTab"] == ["note"]


def test_profile_reads_only_active_group_and_rejects_wrong_tab():
    page = Mock()
    user_page = {"basicInfo": {"nickname": "作者"}, "interactions": []}
    notes_state = {
        "notes": {
            "0": {"0": {"id": "own", "modelType": "note"}},
            "1": {
                "0": {"id": "favorite-a", "modelType": "note"},
                "1": {"id": "favorite-b", "modelType": "note"},
            },
            "2": {"0": {"id": "liked", "modelType": "note"}},
        },
        "index": 1,
        "query": "fav",
        "ready": True,
    }
    page.evaluate.side_effect = [True, json.dumps(user_page), json.dumps(notes_state)]
    result = _extract_user_profile_data(page, "fav")
    assert [feed.id for feed in result.feeds] == ["favorite-a", "favorite-b"]

    page.evaluate.side_effect = [True, json.dumps(user_page), json.dumps(notes_state)]
    with pytest.raises(RuntimeError, match="不符"):
        _extract_user_profile_data(page, "liked")


def test_profile_missing_group_and_non_default_query_are_not_empty_successes():
    page = Mock()
    user_page = {"basicInfo": {}, "interactions": []}
    missing = {
        "notes": {"0": {}}, "index": 1, "query": "fav", "ready": False,
        "fetching": False, "status": "resolved", "hasMore": False,
    }
    page.evaluate.side_effect = [True, json.dumps(user_page), json.dumps(missing)]
    with pytest.raises(RuntimeError, match="未就绪"):
        _extract_user_profile_data(page, "fav", timeout=0)

    no_query = {"notes": {"1": {}}, "index": 1, "query": "", "ready": True}
    page.evaluate.side_effect = [True, json.dumps(user_page), json.dumps(no_query)]
    with pytest.raises(RuntimeError, match="未确认"):
        _extract_user_profile_data(page, "fav", timeout=0)


def test_profile_rejects_redirected_identity_and_query_owner():
    page = Mock()
    user_page = {"basicInfo": {}, "interactions": []}
    state = {
        "notes": {"0": {}}, "index": 0, "query": "note", "ready": True,
        "profileId": "different", "queryUserId": "target",
    }
    page.evaluate.side_effect = [True, json.dumps(user_page), json.dumps(state)]
    with pytest.raises(RuntimeError, match="当前主页用户"):
        _extract_user_profile_data(page, "note", user_id="target", timeout=0)

    state.update(profileId="target", queryUserId="different")
    page.evaluate.side_effect = [True, json.dumps(user_page), json.dumps(state)]
    with pytest.raises(RuntimeError, match="归属用户"):
        _extract_user_profile_data(page, "note", user_id="target", timeout=0)


def test_actual_profile_probe_requires_group_pagination_and_settled_empty_state():
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node.js unavailable")
    runner = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = input.cases.map(item => {
  const context = {
    window: {__INITIAL_STATE__: {user: item.user}},
    location: {pathname: '/user/profile/target'},
    document: {querySelectorAll: () => [{innerText: ''}, {innerText: item.body || ''}]}
  };
  return JSON.parse(vm.runInNewContext(input.script, context));
});
process.stdout.write(JSON.stringify(results));
"""

    user = {
        "activeTab": {"query": "fav", "index": 1},
        "notes": {"0": {"0": {"id": "note"}}, "1": {"0": {"id": "fav"}}},
        "noteQueries": {"1": {"hasMore": False, "userId": "target"}},
        "isFetchingNotes": {"1": False},
        "userNoteFetchingStatus": {"1": "resolved"},
    }
    pending = json.loads(json.dumps(user))
    pending["notes"]["1"] = {}
    pending["userNoteFetchingStatus"]["1"] = "pending"
    completed = subprocess.run(
        [executable, "-e", runner],
        input=json.dumps({"script": _EXTRACT_USER_NOTES_JS, "cases": [
            {"user": user}, {"user": pending},
            {"user": pending, "body": "该用户暂无公开笔记"},
        ]}),
        text=True,
        capture_output=True,
        check=True,
    )
    ready, loading, empty = json.loads(completed.stdout)
    assert ready["ready"] is True
    assert ready["profileId"] == "target" and ready["queryUserId"] == "target"
    assert loading["ready"] is False
    assert empty["ready"] is True

def test_video_and_subtitle_urls_are_readable_in_markdown_without_download():
    data = {
        "note": {
            "title": "视频",
            "video": {
                "media": {"stream": {
                    "EF6": [],
                    "EF4": [{
                        "width": 1920,
                        "height": 1080,
                        "masterUrl": "https://example.com/video.mp4",
                        "backupUrls": ["https://example.com/backup.mp4"],
                    }],
                }},
                "subtitles": {
                    "source": [{"language": "zh", "url": "https://example.com/zh.srt"}],
                },
            },
        },
        "comments": [],
        "comment_pagination": {"comments_complete": None},
    }
    text = to_markdown(data)
    assert "EF4 / 1 / 1920x1080" in text
    assert "EF6：页面返回空档位" in text
    assert "<https://example.com/video.mp4>" in text
    assert "<https://example.com/backup.mp4>" in text
    assert "<https://example.com/zh.srt>" in text
    assert "未下载视频" in text and "未下载字幕" in text


def test_action_result_status_is_optional_and_keeps_existing_fields():
    assert "status" not in ActionResult(feed_id="1", success=True).to_dict()
    assert ActionResult(feed_id="1", success=True, status="unchanged").to_dict() == {
        "feed_id": "1",
        "success": True,
        "message": "",
        "status": "unchanged",
    }
