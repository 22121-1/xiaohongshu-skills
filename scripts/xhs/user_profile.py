"""用户主页，对应 Go xiaohongshu/user_profile.go。"""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import unquote

from .cdp import Page
from .types import Feed, UserBasicInfo, UserInteraction, UserProfileResponse
from .urls import make_user_profile_url

logger = logging.getLogger(__name__)

_PROFILE_TAB_ALIASES = {
    "": "note",
    "note": "note",
    "notes": "note",
    "笔记": "note",
    "fav": "fav",
    "favorite": "fav",
    "favorites": "fav",
    "收藏": "fav",
    "liked": "liked",
    "like": "liked",
    "点赞": "liked",
}

# 提取用户数据的 JS
_EXTRACT_USER_DATA_JS = """
(() => {
    if (window.__INITIAL_STATE__ &&
        window.__INITIAL_STATE__.user &&
        window.__INITIAL_STATE__.user.userPageData) {
        const userPageData = window.__INITIAL_STATE__.user.userPageData;
        const data = userPageData.value !== undefined ? userPageData.value : userPageData._value;
        if (data) {
            return JSON.stringify(data);
        }
    }
    return "";
})()
"""

_EXTRACT_USER_NOTES_JS = """
(() => {
    const unwrap = value => {
        for (let i = 0; i < 4 && value && typeof value === 'object'; i++) {
            if (value.value !== undefined) value = value.value;
            else if (value._value !== undefined) value = value._value;
            else break;
        }
        return value;
    };
    const list = value => {
        value = unwrap(value);
        if (Array.isArray(value)) return value;
        if (value && typeof value === 'object' &&
            Object.keys(value).every(key => /^\\d+$/.test(key))) {
            return Object.keys(value).sort((a, b) => Number(a) - Number(b)).map(key => value[key]);
        }
        return null;
    };
    const user = window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user;
    if (!user || !user.notes) return "";
    const notes = unwrap(user.notes);
    if (!notes) return "";
    const active = unwrap(user.activeTab) || {};
    const index = Number.isInteger(active.index) ? active.index : -1;
    const group = index >= 0 ? (Array.isArray(notes) ? notes[index] : notes[String(index)]) : null;
    const records = list(group);
    const queries = unwrap(user.noteQueries);
    const query = index >= 0 ? unwrap(queries && queries[index]) : null;
    const fetchingMap = unwrap(user.isFetchingNotes);
    const fetching = index >= 0 ? unwrap(fetchingMap && fetchingMap[index]) : null;
    const statusMap = unwrap(user.userNoteFetchingStatus);
    const status = index >= 0 ? unwrap(statusMap && statusMap[index]) : null;
    const roots = document.querySelectorAll ? document.querySelectorAll('.tab-content-item') : [];
    const rootText = (roots[active.index] && roots[active.index].innerText || '').trim();
    const explicitEmpty = /(?:暂无|没有|暂未发布|仅自己可见|隐私|未公开|不可见)/.test(rootText);
    const profileMatch = location.pathname.match(/^\\/user\\/profile\\/([^/?#]+)\\/?$/);
    const failed = ['rejected', 'error', 'failed'].includes(status);
    const queryReady = query && typeof query.hasMore === 'boolean';
    const settledEmpty = records && records.length === 0 && queryReady && !query.hasMore &&
        (status === 'resolved' || explicitEmpty);
    const ready = !failed && records !== null && queryReady && fetching !== true &&
        (records.length > 0 || settledEmpty);
    return JSON.stringify({
        notes: notes,
        index: index,
        query: typeof active.query === 'string' ? active.query : '',
        profileId: profileMatch ? decodeURIComponent(profileMatch[1]) : '',
        queryUserId: query && query.userId ? String(query.userId) : '',
        hasMore: queryReady ? query.hasMore : null,
        cursor: queryReady ? String(query.cursor || '') : '',
        fetching: fetching === true,
        status: typeof status === 'string' ? status : '',
        explicitEmpty: explicitEmpty,
        failed: failed,
        ready: ready
    });
})()
"""


def normalize_profile_tab(tab: str | None) -> str:
    """将主页 tab 别名规范为页面使用的 note/fav/liked。"""
    value = (tab or "").strip().lower()
    try:
        return _PROFILE_TAB_ALIASES[value]
    except KeyError as exc:
        raise ValueError(f"未知的主页 tab {tab!r}，可选：note / fav / liked") from exc


def get_user_profile(
    page: Page,
    user_id: str,
    xsec_token: str,
    tab: str = "note",
) -> UserProfileResponse:
    """获取用户主页信息及帖子。

    Args:
        page: CDP 页面对象。
        user_id: 用户 ID。
        xsec_token: xsec_token。

    Raises:
        RuntimeError: 数据提取失败。
    """
    requested_tab = normalize_profile_tab(tab)
    url = make_user_profile_url(user_id, xsec_token, requested_tab)
    page.navigate(url)
    page.wait_for_load()
    page.wait_dom_stable()

    return _extract_user_profile_data(page, requested_tab, user_id=user_id)


def _extract_user_profile_data(
    page: Page,
    tab: str = "note",
    *,
    user_id: str | None = None,
    timeout: float = 10.0,
) -> UserProfileResponse:
    """从页面提取用户资料数据。"""
    # 等待 __INITIAL_STATE__
    _wait_for_initial_state(page)

    # 提取用户信息
    user_data_result = page.evaluate(_EXTRACT_USER_DATA_JS)
    if not user_data_result:
        raise RuntimeError("user.userPageData.value not found in __INITIAL_STATE__")

    # 提取用户帖子；列表未就绪时等待，避免把缺失分组、加载中或私密态误报为空成功。
    notes_state = _wait_for_notes_state(page, timeout=timeout)

    # 解析用户信息
    user_page_data = json.loads(user_data_result)
    basic_info = UserBasicInfo.from_dict(user_page_data.get("basicInfo", {}))
    interactions = [UserInteraction.from_dict(i) for i in user_page_data.get("interactions", [])]

    # notes 是按 tab 分组的二维结构。只读 active.index 指向的一组，避免把收藏、
    # 点赞和笔记混在一起；active.query 存在时还要与请求目标相符。
    requested_tab = normalize_profile_tab(tab)
    active_query = notes_state.get("query")
    if not isinstance(active_query, str) or not active_query.strip():
        if requested_tab != "note":
            raise RuntimeError(f"页面未确认请求的主页 tab {requested_tab!r}")
    else:
        try:
            actual_tab = normalize_profile_tab(active_query)
        except ValueError as exc:
            raise RuntimeError(f"页面返回未知的主页 tab {active_query!r}") from exc
        if actual_tab != requested_tab:
            raise RuntimeError(
                f"当前主页 tab 为 {actual_tab!r}，与请求的 {requested_tab!r} 不符"
            )

    if user_id is not None:
        actual_user_id = unquote(str(notes_state.get("profileId") or ""))
        if actual_user_id != user_id:
            raise RuntimeError(
                f"当前主页用户 {actual_user_id or '未知'!r}，与请求的 {user_id!r} 不符"
            )
        query_user_id = str(notes_state.get("queryUserId") or "")
        if query_user_id and query_user_id != user_id:
            raise RuntimeError("主页帖子分组归属用户与请求目标不符")

    active_index = notes_state.get("index", 0)
    if isinstance(active_index, bool) or not isinstance(active_index, int) or active_index < 0:
        raise RuntimeError("user.activeTab.index 无效")
    raw_feeds = _select_feed_group(notes_state.get("notes"), active_index)
    feeds = [Feed.from_dict(item) for item in raw_feeds]

    return UserProfileResponse(
        user_basic_info=basic_info,
        interactions=interactions,
        feeds=feeds,
    )


def _is_feed(value: object) -> bool:
    return isinstance(value, dict) and ("id" in value or "noteCard" in value)


def _ordered_dict_values(value: dict) -> list[object]:
    def key(item: tuple[object, object]) -> tuple[int, object]:
        name = str(item[0])
        return (0, int(name)) if name.isdigit() else (1, name)

    return [item for _, item in sorted(value.items(), key=key)]


def _select_feed_group(notes: object, active_index: int) -> list[dict]:
    """兼容数组和数字键对象，只返回 active index 对应的帖子组。"""
    if isinstance(notes, list):
        if all(_is_feed(item) for item in notes):
            if active_index != 0:
                raise RuntimeError("user.notes 缺少 active index 对应分组")
            group: object = notes
        else:
            if active_index >= len(notes):
                raise RuntimeError("user.notes 缺少 active index 对应分组")
            group = notes[active_index]
    elif isinstance(notes, dict):
        if _is_feed(notes):
            if active_index != 0:
                raise RuntimeError("user.notes 缺少 active index 对应分组")
            group = [notes]
        else:
            if str(active_index) in notes:
                group = notes[str(active_index)]
            elif active_index in notes:
                group = notes[active_index]
            else:
                raise RuntimeError("user.notes 缺少 active index 对应分组")
    else:
        raise RuntimeError("user.notes.value 数据结构无效")

    if _is_feed(group):
        candidates = [group]
    elif isinstance(group, list):
        candidates = group
    elif isinstance(group, dict):
        candidates = _ordered_dict_values(group)
    else:
        candidates = []
    return [item for item in candidates if _is_feed(item)]


def _wait_for_initial_state(page: Page, timeout: float = 10.0) -> None:
    """等待 __INITIAL_STATE__ 就绪。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = page.evaluate("window.__INITIAL_STATE__ !== undefined")
        if ready:
            return
        time.sleep(0.5)
    logger.warning("等待 __INITIAL_STATE__ 超时")


def _wait_for_notes_state(page: Page, timeout: float = 10.0) -> dict:
    """等待目标分组及其分页状态稳定；失败和未就绪不会伪装成空列表。"""
    deadline = time.monotonic() + timeout
    latest: dict | None = None
    while True:
        result = page.evaluate(_EXTRACT_USER_NOTES_JS)
        if result:
            try:
                candidate = json.loads(result)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("user.notes 返回了无效 JSON") from exc
            if not isinstance(candidate, dict):
                raise RuntimeError("user.notes 数据结构无效")
            latest = candidate
            if candidate.get("failed"):
                raise RuntimeError("网页加载用户帖子失败，请稍后重试")
            if candidate.get("ready"):
                return candidate
        if time.monotonic() >= deadline:
            detail = ""
            if latest:
                detail = (
                    f" (index={latest.get('index')!r}, fetching={latest.get('fetching')!r}, "
                    f"status={latest.get('status')!r}, hasMore={latest.get('hasMore')!r})"
                )
            raise RuntimeError(f"用户主页帖子分组未就绪；未将其当作空列表{detail}")
        time.sleep(0.25)
