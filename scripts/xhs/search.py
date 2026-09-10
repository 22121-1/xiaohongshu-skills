"""搜索 Feeds，对应 Go xiaohongshu/search.go。"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .cdp import Page
from .errors import NoFeedsError, XHSError
from .types import Feed, FilterOption
from .urls import make_search_url

logger = logging.getLogger(__name__)

# 筛选选项映射表：{筛选组索引: [文本, ...]}
_FILTER_OPTIONS: dict[int, list[str]] = {
    1: ["综合", "最新", "最多点赞", "最多评论", "最多收藏"],
    2: ["不限", "视频", "图文"],
    3: ["不限", "一天内", "一周内", "半年内"],
    4: ["不限", "已看过", "未看过", "已关注"],
    5: ["不限", "同城", "附近"],
}

# 从 __INITIAL_STATE__ 提取搜索结果的 JS
_EXTRACT_SEARCH_JS = """
(() => {
    const s = window.__INITIAL_STATE__?.search;
    if (!s?.feeds) return "";
    const data = s.feeds.value !== undefined ? s.feeds.value : s.feeds._value;
    return data ? JSON.stringify(data) : "";
})()
"""


def _find_internal_option(group_index: int, text: str) -> tuple[int, str]:
    """查找内部筛选选项。

    Returns:
        (filters_index, text)

    Raises:
        ValueError: 未找到匹配的选项。
    """
    options = _FILTER_OPTIONS.get(group_index)
    if not options:
        raise ValueError(f"筛选组 {group_index} 不存在")

    if text in options:
        return group_index, text

    raise ValueError(f"在筛选组 {group_index} 中未找到 '{text}'，有效值: {options}")


def _convert_filters(filter_opt: FilterOption) -> list[tuple[int, str]]:
    """将 FilterOption 转换为内部 (filters_index, text) 列表。"""
    result: list[tuple[int, str]] = []

    if filter_opt.sort_by:
        result.append(_find_internal_option(1, filter_opt.sort_by))
    if filter_opt.note_type:
        result.append(_find_internal_option(2, filter_opt.note_type))
    if filter_opt.publish_time:
        result.append(_find_internal_option(3, filter_opt.publish_time))
    if filter_opt.search_scope:
        result.append(_find_internal_option(4, filter_opt.search_scope))
    if filter_opt.location:
        result.append(_find_internal_option(5, filter_opt.location))

    return result


def search_feeds(
    page: Page,
    keyword: str,
    filter_option: FilterOption | None = None,
) -> list[Feed]:
    """搜索 Feeds。

    Args:
        page: CDP 页面对象。
        keyword: 搜索关键词。
        filter_option: 可选筛选条件。

    Raises:
        NoFeedsError: 没有捕获到搜索结果。
        ValueError: 筛选选项无效。
    """
    internal_filters = _convert_filters(filter_option) if filter_option else []
    search_url = make_search_url(keyword)
    page.navigate(search_url)
    page.wait_for_load()
    page.wait_dom_stable()

    # 等待 __INITIAL_STATE__.search.feeds 有数据
    _wait_for_search_feeds(page, keyword=keyword)

    if internal_filters:
        _apply_filters(page, internal_filters, keyword=keyword)

    # 提取搜索结果
    result = page.evaluate(_EXTRACT_SEARCH_JS)
    if not result:
        raise NoFeedsError()

    feeds_data = json.loads(result)
    return [Feed.from_dict(f) for f in feeds_data if f.get("modelType") == "note"]


def _wait_for_search_feeds(page: Page, timeout: float = 15.0, *, keyword: str = "") -> None:
    """只有加载完成才读取列表；零结果是有效结果，加载失败不当作空列表。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = page.evaluate("""(() => {
            const s = window.__INITIAL_STATE__?.search;
            const u = v => v?.value ?? v?._value ?? v;
            return {state: u(s?.state), keyword: u(s?.searchContext)?.keyword,
                ready: location.pathname === "/search_result" && Array.isArray(u(s?.feeds))};
        })()""")
        if isinstance(state, dict):
            if state.get("state") in {"error", "failed", "fail"}:
                raise XHSError("搜索加载失败")
            if (state.get("ready") and state.get("state") == "success"
                    and (not keyword or state.get("keyword") == keyword)):
                return
        time.sleep(0.2)
    raise XHSError("搜索结果未确认加载完成")


_FILTER_LABELS = {1: "排序依据", 2: "笔记类型", 3: "发布时间", 4: "搜索范围", 5: "位置距离"}
_FILTER_SCRIPT = Path(__file__).with_name("search_filters.js").read_text(encoding="utf-8")


def _apply_filters(page: Page, filters: list[tuple[int, str]], *, keyword: str = "") -> None:
    params = {"filters": [[_FILTER_LABELS[index], text] for index, text in filters],
              "keyword": keyword}
    try:
        result = page.evaluate(f"({_FILTER_SCRIPT})({json.dumps(params, ensure_ascii=False)})")
    except Exception as exc:
        raise ValueError(f"应用筛选失败: {exc}") from exc
    if not isinstance(result, dict) or result.get("verified") is not True:
        raise ValueError("筛选未确认成功，未返回结果")
    _wait_for_search_feeds(page, keyword=keyword)
