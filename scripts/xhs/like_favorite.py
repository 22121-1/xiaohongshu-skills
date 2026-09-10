"""点赞/收藏操作，对应 Go xiaohongshu/like_favorite.go。"""

from __future__ import annotations

import json
import logging
import time

from .cdp import Page
from .errors import NoFeedDetailError
from .selectors import COLLECT_BUTTON, LIKE_BUTTON
from .types import ActionResult
from .urls import make_feed_detail_url

logger = logging.getLogger(__name__)

# 从 __INITIAL_STATE__ 读取互动状态的 JS
_GET_INTERACT_STATE_JS = """
(() => {
    if (window.__INITIAL_STATE__ &&
        window.__INITIAL_STATE__.note &&
        window.__INITIAL_STATE__.note.noteDetailMap) {
        return JSON.stringify({
            pathname: location.pathname,
            noteDetailMap: window.__INITIAL_STATE__.note.noteDetailMap,
        });
    }
    return "";
})()
"""


def _get_interact_state(page: Page, feed_id: str) -> tuple[bool, bool]:
    """读取笔记的点赞/收藏状态。

    Returns:
        (liked, collected)

    Raises:
        NoFeedDetailError: 无法获取状态。
    """
    try:
        result = page.evaluate(_GET_INTERACT_STATE_JS)
    except Exception as exc:
        raise NoFeedDetailError() from exc
    if not result:
        raise NoFeedDetailError()

    try:
        state = json.loads(result) if isinstance(result, str) else result
    except (TypeError, json.JSONDecodeError) as exc:
        raise NoFeedDetailError() from exc
    if not isinstance(state, dict):
        raise NoFeedDetailError()
    pathname = state.get("pathname")
    if pathname not in {f"/explore/{feed_id}", f"/discovery/item/{feed_id}"}:
        raise NoFeedDetailError()
    note_detail_map = state.get("noteDetailMap")
    if not isinstance(note_detail_map, dict):
        raise NoFeedDetailError()

    # 只能使用请求的 feed。即使映射里只有一条记录，也可能是单页应用残留的
    # 上一篇笔记；回退会读取错误状态，并把后续切换施加到当前页面。
    detail = note_detail_map.get(feed_id)
    if not isinstance(detail, dict):
        raise NoFeedDetailError()
    note = detail.get("note")
    if not isinstance(note, dict):
        raise NoFeedDetailError()
    note_id = note.get("noteId") or note.get("id")
    if note_id and str(note_id) != feed_id:
        raise NoFeedDetailError()
    interact = note.get("interactInfo")
    if not isinstance(interact, dict):
        raise NoFeedDetailError()
    liked = interact.get("liked")
    collected = interact.get("collected")
    if not isinstance(liked, bool) or not isinstance(collected, bool):
        raise NoFeedDetailError()
    return liked, collected


def _prepare_page(page: Page, feed_id: str, xsec_token: str) -> None:
    """导航到 feed 详情页。"""
    url = make_feed_detail_url(feed_id, xsec_token)
    page.navigate(url)
    page.wait_for_load()
    page.wait_dom_stable()
    time.sleep(1)


# ========== 点赞 ==========


def like_feed(page: Page, feed_id: str, xsec_token: str) -> ActionResult:
    """点赞笔记（幂等：已点赞则跳过）。"""
    _prepare_page(page, feed_id, xsec_token)
    return _toggle_like(page, feed_id, target_liked=True)


def unlike_feed(page: Page, feed_id: str, xsec_token: str) -> ActionResult:
    """取消点赞（幂等：未点赞则跳过）。"""
    _prepare_page(page, feed_id, xsec_token)
    return _toggle_like(page, feed_id, target_liked=False)


def _toggle_like(page: Page, feed_id: str, target_liked: bool) -> ActionResult:
    """执行点赞/取消点赞操作。"""
    action_name = "点赞" if target_liked else "取消点赞"

    try:
        liked, _ = _get_interact_state(page, feed_id)
    except NoFeedDetailError:
        logger.error("feed %s 无法确认当前点赞状态，未点击", feed_id)
        return ActionResult(
            feed_id=feed_id,
            success=False,
            message=f"{action_name}未确认：无法读取当前笔记的点赞状态，未执行点击",
            status="unknown",
        )

    # 幂等检查
    if liked == target_liked:
        logger.info("feed %s 已%s，跳过", feed_id, action_name)
        return ActionResult(
            feed_id=feed_id, success=True, message=f"已{action_name}", status="unchanged"
        )

    if not page.has_element(LIKE_BUTTON):
        return ActionResult(
            feed_id=feed_id,
            success=False,
            message=f"{action_name}失败：未找到点赞按钮",
            status="failed",
        )
    try:
        page.click_element(LIKE_BUTTON)
    except Exception as exc:
        logger.exception("feed %s 点击点赞按钮失败", feed_id)
        return ActionResult(
            feed_id=feed_id,
            success=False,
            message=f"{action_name}未确认：点击阶段异常（{exc}），请先重新读取状态再决定是否重试",
            status="unknown",
        )
    if _wait_interact_state(page, feed_id, target_liked, pick_like=True):
        logger.info("feed %s %s成功", feed_id, action_name)
        return ActionResult(
            feed_id=feed_id, success=True, message=f"{action_name}成功", status="success"
        )
    logger.error("feed %s %s后状态未确认；为避免反向切换，不重复点击", feed_id, action_name)
    return ActionResult(
        feed_id=feed_id,
        success=False,
        message=f"{action_name}未确认：点击后状态未达到预期，请先重新读取状态再决定是否重试",
        status="unknown",
    )


# ========== 收藏 ==========


def favorite_feed(page: Page, feed_id: str, xsec_token: str) -> ActionResult:
    """收藏笔记（幂等：已收藏则跳过）。"""
    _prepare_page(page, feed_id, xsec_token)
    return _toggle_favorite(page, feed_id, target_collected=True)


def unfavorite_feed(page: Page, feed_id: str, xsec_token: str) -> ActionResult:
    """取消收藏（幂等：未收藏则跳过）。"""
    _prepare_page(page, feed_id, xsec_token)
    return _toggle_favorite(page, feed_id, target_collected=False)


def _wait_collect_button(page: Page, timeout: float = 5.0, interval: float = 0.2) -> bool:
    """等待收藏按钮出现。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.has_element(COLLECT_BUTTON):
            return True
        time.sleep(interval)
    return False


def _wait_interact_state(
    page: Page,
    feed_id: str,
    target: bool,
    *,
    pick_like: bool,
    timeout: float = 4.0,
    interval: float = 0.3,
) -> bool:
    """短轮询验证互动状态；读不到或超时都保留为未确认。"""
    deadline = time.monotonic() + timeout
    while True:
        try:
            liked, collected = _get_interact_state(page, feed_id)
            if (liked if pick_like else collected) == target:
                return True
        except NoFeedDetailError:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def _toggle_favorite(page: Page, feed_id: str, target_collected: bool) -> ActionResult:
    """执行收藏/取消收藏操作。"""
    action_name = "收藏" if target_collected else "取消收藏"

    try:
        _, collected = _get_interact_state(page, feed_id)
    except NoFeedDetailError:
        logger.error("feed %s 无法确认当前收藏状态，未点击", feed_id)
        return ActionResult(
            feed_id=feed_id,
            success=False,
            message=f"{action_name}未确认：无法读取当前笔记的收藏状态，未执行点击",
            status="unknown",
        )

    # 幂等检查
    if collected == target_collected:
        logger.info("feed %s 已%s，跳过", feed_id, action_name)
        return ActionResult(
            feed_id=feed_id, success=True, message=f"已{action_name}", status="unchanged"
        )

    if not _wait_collect_button(page, timeout=5.0):
        logger.error("feed %s 未找到收藏按钮: %s", feed_id, COLLECT_BUTTON)
        return ActionResult(
            feed_id=feed_id,
            success=False,
            message=f"{action_name}失败：未找到收藏按钮",
            status="failed",
        )

    try:
        page.click_element(COLLECT_BUTTON)
    except Exception as exc:
        logger.exception("feed %s 点击收藏按钮失败", feed_id)
        return ActionResult(
            feed_id=feed_id,
            success=False,
            message=f"{action_name}未确认：点击阶段异常（{exc}），请先重新读取状态再决定是否重试",
            status="unknown",
        )
    if _wait_interact_state(page, feed_id, target_collected, pick_like=False):
        logger.info("feed %s %s成功", feed_id, action_name)
        return ActionResult(
            feed_id=feed_id, success=True, message=f"{action_name}成功", status="success"
        )
    logger.error("feed %s %s后状态未确认；为避免反向切换，不重复点击", feed_id, action_name)
    return ActionResult(
        feed_id=feed_id,
        success=False,
        message=f"{action_name}未确认：点击后状态未达到预期，请先重新读取状态再决定是否重试",
        status="unknown",
    )
