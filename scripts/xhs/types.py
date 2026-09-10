"""小红书数据类型定义，对应 Go types.go。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ========== Feed 列表 ==========


@dataclass
class ImageInfo:
    image_scene: str = ""
    url: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> ImageInfo:
        return cls(
            image_scene=d.get("imageScene", ""),
            url=d.get("url", ""),
        )


@dataclass
class VideoCapability:
    duration: int = 0  # 秒

    @classmethod
    def from_dict(cls, d: dict) -> VideoCapability:
        return cls(duration=d.get("duration", 0))


@dataclass
class Video:
    capa: VideoCapability = field(default_factory=VideoCapability)

    @classmethod
    def from_dict(cls, d: dict) -> Video:
        return cls(capa=VideoCapability.from_dict(d.get("capa", {})))


@dataclass
class Cover:
    width: int = 0
    height: int = 0
    url: str = ""
    file_id: str = ""
    url_pre: str = ""
    url_default: str = ""
    info_list: list[ImageInfo] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Cover:
        return cls(
            width=d.get("width", 0),
            height=d.get("height", 0),
            url=d.get("url", ""),
            file_id=d.get("fileId", ""),
            url_pre=d.get("urlPre", ""),
            url_default=d.get("urlDefault", ""),
            info_list=[ImageInfo.from_dict(i) for i in d.get("infoList", [])],
        )


@dataclass
class User:
    user_id: str = ""
    nickname: str = ""
    nick_name: str = ""
    avatar: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> User:
        return cls(
            user_id=d.get("userId", ""),
            nickname=d.get("nickname", ""),
            nick_name=d.get("nickName", ""),
            avatar=d.get("avatar", ""),
        )


@dataclass
class InteractInfo:
    liked: bool = False
    liked_count: str = ""
    shared_count: str = ""
    comment_count: str = ""
    collected_count: str = ""
    collected: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> InteractInfo:
        return cls(
            liked=d.get("liked", False),
            liked_count=d.get("likedCount", ""),
            shared_count=d.get("sharedCount", ""),
            comment_count=d.get("commentCount", ""),
            collected_count=d.get("collectedCount", ""),
            collected=d.get("collected", False),
        )


@dataclass
class NoteCard:
    type: str = ""
    display_title: str = ""
    user: User = field(default_factory=User)
    interact_info: InteractInfo = field(default_factory=InteractInfo)
    cover: Cover = field(default_factory=Cover)
    video: Video | None = None

    @classmethod
    def from_dict(cls, d: dict) -> NoteCard:
        video_data = d.get("video")
        return cls(
            type=d.get("type", ""),
            display_title=d.get("displayTitle", ""),
            user=User.from_dict(d.get("user", {})),
            interact_info=InteractInfo.from_dict(d.get("interactInfo", {})),
            cover=Cover.from_dict(d.get("cover", {})),
            video=Video.from_dict(video_data) if video_data else None,
        )


@dataclass
class Feed:
    xsec_token: str = ""
    id: str = ""
    model_type: str = ""
    note_card: NoteCard = field(default_factory=NoteCard)
    index: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> Feed:
        return cls(
            xsec_token=d.get("xsecToken", ""),
            id=d.get("id", ""),
            model_type=d.get("modelType", ""),
            note_card=NoteCard.from_dict(d.get("noteCard", {})),
            index=d.get("index", 0),
        )

    def to_dict(self) -> dict:
        """序列化为 JSON 兼容的字典。"""
        result: dict = {
            "id": self.id,
            "xsecToken": self.xsec_token,
            "modelType": self.model_type,
            "index": self.index,
            "displayTitle": self.note_card.display_title,
            "type": self.note_card.type,
            "user": {
                "userId": self.note_card.user.user_id,
                "nickname": self.note_card.user.nickname or self.note_card.user.nick_name,
            },
            "interactInfo": {
                "likedCount": self.note_card.interact_info.liked_count,
                "collectedCount": self.note_card.interact_info.collected_count,
                "commentCount": self.note_card.interact_info.comment_count,
                "sharedCount": self.note_card.interact_info.shared_count,
            },
        }
        from .links import make_share_url

        try:
            result["shareUrl"] = make_share_url(self.id, self.xsec_token) if self.xsec_token else ""
        except ValueError:
            # 非笔记卡片可能没有合法笔记 ID，仍保留原有序列化结果。
            result["shareUrl"] = ""
        cover = self.note_card.cover
        if cover.url or cover.url_default:
            result["cover"] = cover.url or cover.url_default
        if self.note_card.video:
            result["video"] = {"duration": self.note_card.video.capa.duration}
        return result


# ========== Feed 详情 ==========


@dataclass
class DetailImageInfo:
    width: int = 0
    height: int = 0
    url_default: str = ""
    url_pre: str = ""
    live_photo: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> DetailImageInfo:
        return cls(
            width=d.get("width", 0),
            height=d.get("height", 0),
            url_default=d.get("urlDefault", ""),
            url_pre=d.get("urlPre", ""),
            live_photo=d.get("livePhoto", False),
        )


@dataclass
class Comment:
    id: str = ""
    note_id: str = ""
    content: str = ""
    like_count: str = ""
    create_time: int = 0
    ip_location: str = ""
    liked: bool = False
    user_info: User = field(default_factory=User)
    sub_comment_count: str = ""
    sub_comment_cursor: str = ""
    sub_comment_has_more: bool | None = None
    has_more: bool | None = None
    sub_comments: list[Comment] = field(default_factory=list)
    show_tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Comment:
        return cls(
            id=d.get("id", ""),
            note_id=d.get("noteId", ""),
            content=d.get("content", ""),
            like_count=d.get("likeCount", ""),
            create_time=d.get("createTime", 0),
            ip_location=d.get("ipLocation", ""),
            liked=d.get("liked", False),
            user_info=User.from_dict(d.get("userInfo", {})),
            sub_comment_count=d.get("subCommentCount", ""),
            sub_comment_cursor=d.get("subCommentCursor", ""),
            sub_comment_has_more=(d.get("subCommentHasMore")
                                  if isinstance(d.get("subCommentHasMore"), bool) else None),
            has_more=d.get("hasMore") if isinstance(d.get("hasMore"), bool) else None,
            sub_comments=[cls.from_dict(c) for c in d.get("subComments", []) or []],
            show_tags=d.get("showTags", []) or [],
        )

    def to_dict(self) -> dict:
        result: dict = {
            "id": self.id,
            "content": self.content,
            "likeCount": self.like_count,
            "createTime": self.create_time,
            "ipLocation": self.ip_location,
            "user": {
                "userId": self.user_info.user_id,
                "nickname": self.user_info.nickname or self.user_info.nick_name,
            },
            "subCommentCount": self.sub_comment_count,
        }
        if self.sub_comments:
            result["subComments"] = [c.to_dict() for c in self.sub_comments]
        if self.sub_comment_cursor:
            result["subCommentCursor"] = self.sub_comment_cursor
        if self.sub_comment_has_more is not None:
            result["subCommentHasMore"] = self.sub_comment_has_more
        if self.has_more is not None:
            result["hasMore"] = self.has_more
        return result


@dataclass
class CommentList:
    list_: list[Comment] = field(default_factory=list)
    cursor: str = ""
    # 页面状态没有 hasMore 时不能把缺失值当成 false，否则会误报一级评论已完整。
    has_more: bool | None = None
    first_request_finished: bool | None = None

    @classmethod
    def from_dict(cls, d: dict) -> CommentList:
        return cls(
            list_=[Comment.from_dict(c) for c in d.get("list", []) or []],
            cursor=d.get("cursor", ""),
            has_more=d.get("hasMore") if isinstance(d.get("hasMore"), bool) else None,
            first_request_finished=(d.get("firstRequestFinish")
                                    if isinstance(d.get("firstRequestFinish"), bool) else None),
        )


def _parse_count(value: object) -> int | None:
    """解析页面中的计数字段；无法确认时返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def _sub_comments_complete(comments: list[Comment]) -> bool | None:
    """根据声明的回复数判断已返回回复是否完整，未知计数保持未知。"""
    if not comments:
        return None
    complete = True
    saw_known_count = False
    for comment in comments:
        reply_has_more = (
            comment.sub_comment_has_more
            if comment.sub_comment_has_more is not None
            else comment.has_more
        )
        if reply_has_more is True:
            return False
        expected = _parse_count(comment.sub_comment_count)
        if expected is None:
            if reply_has_more is False:
                saw_known_count = True
            else:
                complete = False
            continue
        saw_known_count = True
        if len(comment.sub_comments) < expected:
            return False
    return True if complete and saw_known_count else None


@dataclass
class CommentPagination:
    """评论读取范围；完整性使用三态值，None 表示页面数据不足以判断。"""

    cursor: str = ""
    has_more: bool | None = None
    first_request_finished: bool | None = None
    limit: int = 20
    loaded_root_comments: int = 0
    stopped_reason: str = "not_requested"
    root_comments_complete: bool | None = None
    sub_comments_complete: bool | None = None
    comments_complete: bool | None = None

    @classmethod
    def from_comments(
        cls,
        comments: CommentList,
        *,
        limit: int = 20,
        stopped_reason: str = "not_requested",
    ) -> CommentPagination:
        if stopped_reason in {"end", "no_comments"}:
            root_complete: bool | None = True
        elif stopped_reason == "limit" or comments.has_more is True:
            root_complete = False
        else:
            root_complete = None

        if stopped_reason == "no_comments":
            replies_complete: bool | None = True
        else:
            replies_complete = _sub_comments_complete(comments.list_)

        if root_complete is False or replies_complete is False:
            complete: bool | None = False
        elif root_complete is True and replies_complete is True:
            complete = True
        else:
            complete = None

        return cls(
            cursor=comments.cursor,
            has_more=comments.has_more,
            first_request_finished=comments.first_request_finished,
            limit=limit,
            loaded_root_comments=len(comments.list_),
            stopped_reason=stopped_reason,
            root_comments_complete=root_complete,
            sub_comments_complete=replies_complete,
            comments_complete=complete,
        )

    def to_dict(self) -> dict:
        return {
            "cursor": self.cursor,
            "has_more": self.has_more,
            "first_request_finished": self.first_request_finished,
            "limit": self.limit,
            "loaded_root_comments": self.loaded_root_comments,
            "stopped_reason": self.stopped_reason,
            "root_comments_complete": self.root_comments_complete,
            "sub_comments_complete": self.sub_comments_complete,
            "comments_complete": self.comments_complete,
        }


def _decode_json_object(value: object) -> dict[str, Any] | None:
    """解开 mediaV2 的对象或多层 JSON 字符串，不假定额外字符编码。"""
    current = value
    for _ in range(3):
        if isinstance(current, dict):
            return current
        if not isinstance(current, str) or not current.strip():
            return None
        try:
            current = json.loads(current)
        except (TypeError, ValueError):
            return None
    return current if isinstance(current, dict) else None


@dataclass
class VideoDetail:
    """详情页视频数据；媒体流用字典保留页面提供的全部编码桶。"""

    image: dict[str, Any] = field(default_factory=dict)
    capa: dict[str, Any] = field(default_factory=dict)
    media: dict[str, Any] = field(default_factory=dict)
    subtitles: dict[str, Any] | list[Any] | None = None

    @classmethod
    def from_dict(cls, d: dict) -> VideoDetail:
        media_v2 = _decode_json_object(d.get("mediaV2"))
        subtitles: dict[str, Any] | list[Any] | None = None
        if media_v2:
            video_v2 = media_v2.get("video")
            if isinstance(video_v2, dict):
                candidate = video_v2.get("subtitles")
                if isinstance(candidate, (dict, list)):
                    subtitles = candidate
        return cls(
            image=dict(d.get("image") or {}) if isinstance(d.get("image"), dict) else {},
            capa=dict(d.get("capa") or {}) if isinstance(d.get("capa"), dict) else {},
            # stream 不写死 h264/h265/av1/h266，EF4 等页面新增键也会原样保留。
            media=dict(d.get("media") or {}) if isinstance(d.get("media"), dict) else {},
            subtitles=subtitles,
        )

    def to_dict(self) -> dict:
        result: dict[str, Any] = {
            "image": self.image,
            "capa": self.capa,
            "media": self.media,
        }
        if self.subtitles is not None:
            result["subtitles"] = self.subtitles
        return result


@dataclass
class FeedDetail:
    note_id: str = ""
    xsec_token: str = ""
    title: str = ""
    desc: str = ""
    body: str = ""   # DOM 正文（干净文本，不含 [话题] 标记）
    tags: list[str] = field(default_factory=list)  # 话题标签列表
    type: str = ""
    time: int = 0
    ip_location: str = ""
    user: User = field(default_factory=User)
    interact_info: InteractInfo = field(default_factory=InteractInfo)
    image_list: list[DetailImageInfo] = field(default_factory=list)
    video: VideoDetail | None = None

    @classmethod
    def from_dict(cls, d: dict) -> FeedDetail:
        return cls(
            note_id=d.get("noteId", ""),
            xsec_token=d.get("xsecToken", ""),
            title=d.get("title", ""),
            desc=d.get("desc", ""),
            body=d.get("_domBody", ""),
            tags=d.get("_domTags", []),
            type=d.get("type", ""),
            time=d.get("time", 0),
            ip_location=d.get("ipLocation", ""),
            user=User.from_dict(d.get("user", {})),
            interact_info=InteractInfo.from_dict(d.get("interactInfo", {})),
            image_list=[DetailImageInfo.from_dict(i) for i in d.get("imageList", []) or []],
            video=VideoDetail.from_dict(d["video"]) if isinstance(d.get("video"), dict) else None,
        )

    def to_dict(self) -> dict:
        result = {
            "noteId": self.note_id,
            "title": self.title,
            "desc": self.desc,
            "body": self.body,
            "tags": self.tags,
            "type": self.type,
            "time": self.time,
            "ipLocation": self.ip_location,
            "user": {
                "userId": self.user.user_id,
                "nickname": self.user.nickname or self.user.nick_name,
            },
            "interactInfo": {
                "liked": self.interact_info.liked,
                "likedCount": self.interact_info.liked_count,
                "collectedCount": self.interact_info.collected_count,
                "collected": self.interact_info.collected,
                "commentCount": self.interact_info.comment_count,
                "sharedCount": self.interact_info.shared_count,
            },
            "imageList": [
                {
                    "width": img.width,
                    "height": img.height,
                    "urlDefault": img.url_default,
                }
                for img in self.image_list
            ],
        }
        if self.video is not None:
            result["video"] = self.video.to_dict()
        return result


@dataclass
class FeedDetailResponse:
    note: FeedDetail = field(default_factory=FeedDetail)
    comments: CommentList = field(default_factory=CommentList)
    comment_pagination: CommentPagination = field(default_factory=CommentPagination)

    @classmethod
    def from_dict(cls, d: dict) -> FeedDetailResponse:
        raw_comments = d.get("comments", {})
        if isinstance(raw_comments, list):
            raw_comments = {"list": raw_comments}
        comments = CommentList.from_dict(raw_comments if isinstance(raw_comments, dict) else {})
        response = cls(note=FeedDetail.from_dict(d.get("note", {})), comments=comments)
        pagination = d.get("comment_pagination")
        if isinstance(pagination, dict):
            response.comment_pagination = CommentPagination(
                cursor=str(pagination.get("cursor") or ""),
                has_more=(pagination.get("has_more")
                          if isinstance(pagination.get("has_more"), bool) else None),
                first_request_finished=(
                    pagination.get("first_request_finished")
                    if isinstance(pagination.get("first_request_finished"), bool)
                    else None
                ),
                limit=int(pagination.get("limit", 20)),
                loaded_root_comments=int(pagination.get("loaded_root_comments", 0)),
                stopped_reason=str(pagination.get("stopped_reason") or "not_requested"),
                root_comments_complete=pagination.get("root_comments_complete"),
                sub_comments_complete=pagination.get("sub_comments_complete"),
                comments_complete=pagination.get("comments_complete"),
            )
        else:
            response.comment_pagination = CommentPagination.from_comments(comments)
        return response

    def to_dict(self) -> dict:
        return {
            "note": self.note.to_dict(),
            "comments": [c.to_dict() for c in self.comments.list_],
            "comment_pagination": self.comment_pagination.to_dict(),
        }


# ========== 用户主页 ==========


@dataclass
class UserBasicInfo:
    gender: int = 0
    ip_location: str = ""
    desc: str = ""
    imageb: str = ""
    nickname: str = ""
    images: str = ""
    red_id: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> UserBasicInfo:
        return cls(
            gender=d.get("gender", 0),
            ip_location=d.get("ipLocation", ""),
            desc=d.get("desc", ""),
            imageb=d.get("imageb", ""),
            nickname=d.get("nickname", ""),
            images=d.get("images", ""),
            red_id=d.get("redId", ""),
        )


@dataclass
class UserInteraction:
    type: str = ""
    name: str = ""
    count: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> UserInteraction:
        return cls(
            type=d.get("type", ""),
            name=d.get("name", ""),
            count=d.get("count", ""),
        )


@dataclass
class UserProfileResponse:
    user_basic_info: UserBasicInfo = field(default_factory=UserBasicInfo)
    interactions: list[UserInteraction] = field(default_factory=list)
    feeds: list[Feed] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "basicInfo": {
                "nickname": self.user_basic_info.nickname,
                "redId": self.user_basic_info.red_id,
                "desc": self.user_basic_info.desc,
                "gender": self.user_basic_info.gender,
                "ipLocation": self.user_basic_info.ip_location,
            },
            "interactions": [
                {"type": i.type, "name": i.name, "count": i.count} for i in self.interactions
            ],
            "feeds": [f.to_dict() for f in self.feeds],
        }


# ========== 搜索 ==========


@dataclass
class FilterOption:
    """搜索筛选选项。"""

    sort_by: str = ""  # 综合|最新|最多点赞|最多评论|最多收藏
    note_type: str = ""  # 不限|视频|图文
    publish_time: str = ""  # 不限|一天内|一周内|半年内
    search_scope: str = ""  # 不限|已看过|未看过|已关注
    location: str = ""  # 不限|同城|附近


# ========== 发布 ==========


@dataclass
class PublishImageContent:
    """图文发布内容。"""

    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    image_paths: list[str] = field(default_factory=list)
    schedule_time: str | None = None  # ISO8601 格式，None 表示立即发布
    is_original: bool = False
    visibility: str = ""  # 公开可见(默认)|仅自己可见|仅互关好友可见


@dataclass
class PublishVideoContent:
    """视频发布内容。"""

    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    video_path: str = ""
    schedule_time: str | None = None  # ISO8601 格式
    visibility: str = ""  # 公开可见(默认)|仅自己可见|仅互关好友可见


# ========== 互动 ==========


@dataclass
class ActionResult:
    """通用动作响应（点赞/收藏等）。"""

    feed_id: str = ""
    success: bool = False
    message: str = ""
    status: str | None = None

    def to_dict(self) -> dict:
        result = {
            "feed_id": self.feed_id,
            "success": self.success,
            "message": self.message,
        }
        if self.status is not None:
            result["status"] = self.status
        return result


# ========== 评论加载配置 ==========


@dataclass
class CommentLoadConfig:
    """评论加载配置。"""

    click_more_replies: bool = False
    max_replies_threshold: int = 10
    max_comment_items: int = 20
    scroll_speed: str = "normal"  # slow|normal|fast

    def normalized(self) -> CommentLoadConfig:
        """将零值和负数视为未设置，防止一次详情请求无界滚动。"""
        return CommentLoadConfig(
            click_more_replies=self.click_more_replies,
            max_replies_threshold=(self.max_replies_threshold
                                   if self.max_replies_threshold > 0 else 10),
            max_comment_items=self.max_comment_items if self.max_comment_items > 0 else 20,
            scroll_speed=self.scroll_speed or "normal",
        )
