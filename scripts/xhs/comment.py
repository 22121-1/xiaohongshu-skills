"""笔记评论与回复；提交前绑定目标，提交后核验新记录。"""

from __future__ import annotations

import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any

from .cdp import Page
from .feed_detail import _check_end_container, _check_page_accessible
from .human import sleep_random
from .selectors import (
    COMMENT_INPUT_FIELD,
    COMMENT_INPUT_TRIGGER,
    COMMENT_SUBMIT_BUTTON,
    REPLY_BUTTON,
)
from .urls import make_feed_detail_url

logger = logging.getLogger(__name__)
_SCRIPT = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")


class CommentError(RuntimeError):
    """评论操作错误；status 区分未执行与提交结果未知。"""

    def __init__(self, message: str, *, status: str = "failed") -> None:
        super().__init__(message)
        self.status = status


def _run_dom(page: Page, action: str, feed_id: str, **params: Any) -> dict:
    """运行评论页只读/标记脚本，并统一检查页面和账号身份。"""
    payload = {"action": action, "feed_id": feed_id, **params}
    value = page.evaluate(f"({_SCRIPT})({json.dumps(payload, ensure_ascii=False)})")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CommentError("评论页返回了无法识别的数据") from exc
    if not isinstance(value, dict):
        raise CommentError("评论页返回了无法识别的数据")
    if value.get("error") or value.get("__xhs_error"):
        raise CommentError(value.get("error") or value["__xhs_error"])
    return value


def _snapshot(page: Page, feed_id: str) -> dict:
    state = _run_dom(page, "snapshot", feed_id)
    if not state.get("ready"):
        raise CommentError("评论页尚未就绪")
    account = state.get("account") or {}
    if not account.get("user_id"):
        raise CommentError("无法确认当前登录账号身份")
    return state


def _wait_new_comment(
    page: Page,
    feed_id: str,
    *,
    before_ids: list[str],
    account_id: str,
    content: str,
    target: dict | None = None,
    timeout: float = 8.0,
    interval: float = 0.3,
) -> dict:
    """只接受提交后新增、属于当前账号且正文和回复对象相符的记录。"""
    deadline = time.monotonic() + timeout
    params: dict[str, Any] = {
        "before_ids": before_ids,
        "account_id": account_id,
        "content": content,
    }
    if target:
        params.update(
            target_id=target["id"],
            target_root_id=target["root_id"],
            target_user_id=target.get("author_id", ""),
        )
    while True:
        try:
            state = _run_dom(page, "verify_new", feed_id, **params)
        except Exception as exc:
            raise CommentError(
                f"提交后读取评论失败，结果未确认：{exc}；请勿直接重发", status="unknown"
            ) from exc
        if state.get("verified"):
            return state["comment"]
        if state.get("ambiguous"):
            raise CommentError(
                "提交后出现多条无法区分的新同文评论，结果未确认；请勿重复发送",
                status="unknown",
            )
        if time.monotonic() >= deadline:
            kind = "回复" if target else "评论"
            raise CommentError(
                f"{kind}提交结果未确认：未找到同时匹配新 ID、当前账号、正文"
                + ("和回复对象" if target else "")
                + "的记录；请先重新读取评论，勿直接重发",
                status="unknown",
            )
        time.sleep(interval)


def _wait_reply_binding(
    page: Page,
    feed_id: str,
    target: dict,
    *,
    timeout: float = 3.0,
    interval: float = 0.2,
) -> None:
    """等待编辑器显示与目标评论一致的回复提示。"""
    if not target.get("author_name"):
        raise CommentError("目标评论缺少作者昵称，无法确认回复编辑器绑定")
    deadline = time.monotonic() + timeout
    while True:
        state = _run_dom(
            page,
            "reply_binding",
            feed_id,
            target_author=target["author_name"],
            target_content=target.get("content", ""),
        )
        if state.get("bound"):
            return
        if time.monotonic() >= deadline:
            raise CommentError("回复编辑器未显示目标作者和正文，未发送回复")
        time.sleep(interval)


def post_comment(page: Page, feed_id: str, xsec_token: str, content: str) -> dict:
    """发表评论，并核验新增评论 ID、作者账号及正文。"""
    url = make_feed_detail_url(feed_id, xsec_token)
    logger.info("打开 feed 详情页: %s", url)
    page.navigate(url)
    page.wait_for_load()
    page.wait_dom_stable()
    sleep_random(800, 1500)
    _check_page_accessible(page)

    # 在任何写入前确认目标笔记和当前登录账号。
    _snapshot(page, feed_id)
    if not page.has_element(COMMENT_INPUT_TRIGGER):
        raise CommentError("未找到评论输入框，该帖子可能不支持评论或网页端不可访问")
    page.click_element(COMMENT_INPUT_TRIGGER)
    sleep_random(400, 800)
    page.wait_for_element(COMMENT_INPUT_FIELD, timeout=5)
    if not _run_dom(page, "post_binding", feed_id).get("bound"):
        raise CommentError("评论编辑器仍绑定到某条回复目标，未发送一级评论")
    page.input_content_editable(COMMENT_INPUT_FIELD, content)
    sleep_random(600, 1200)

    # 输入期间页面状态可能变化；以提交前最后一次快照作为去重基线。
    if not _run_dom(page, "post_binding", feed_id).get("bound"):
        raise CommentError("提交前评论编辑器切换为回复模式，未发送一级评论")
    before = _snapshot(page, feed_id)
    before_ids = [str(item.get("id", "")) for item in before["comments"] if item.get("id")]
    try:
        page.click_element(COMMENT_SUBMIT_BUTTON)
    except Exception as exc:
        raise CommentError(
            f"评论提交阶段异常，结果未确认：{exc}；请勿直接重发", status="unknown"
        ) from exc
    sleep_random(800, 1500)
    comment = _wait_new_comment(
        page,
        feed_id,
        before_ids=before_ids,
        account_id=before["account"]["user_id"],
        content=content,
    )
    logger.info("评论发送并核验成功: feed=%s comment=%s", feed_id, comment["id"])
    return {
        "success": True,
        "status": "success",
        "feed_id": feed_id,
        "comment_id": comment["id"],
        "account_id": before["account"]["user_id"],
    }


def reply_comment(
    page: Page,
    feed_id: str,
    xsec_token: str,
    content: str,
    comment_id: str = "",
    user_id: str = "",
) -> dict:
    """回复唯一目标评论，并核验新增回复的作者、正文和回复对象。"""
    if not comment_id and not user_id:
        raise ValueError("comment_id 和 user_id 至少提供一个")
    url = make_feed_detail_url(feed_id, xsec_token)
    logger.info("打开 feed 详情页进行回复: %s", url)
    page.navigate(url)
    page.wait_for_load()
    page.wait_dom_stable()
    sleep_random(800, 1500)
    _check_page_accessible(page)
    sleep_random(1500, 2500)
    account = _snapshot(page, feed_id)["account"]

    target = _find_and_scroll_to_comment(page, feed_id, comment_id, user_id)
    sleep_random(800, 1500)
    target_id = target["id"]
    reply_selector = f"[id={_js_str('comment-' + target_id)}] {REPLY_BUTTON}"
    if not page.has_element(reply_selector):
        raise CommentError(f"目标评论 {target_id} 内未找到回复按钮")
    page.click_element(reply_selector)
    sleep_random(800, 1500)
    _wait_reply_binding(page, feed_id, target)
    page.wait_for_element(COMMENT_INPUT_FIELD, timeout=5)
    page.input_content_editable(COMMENT_INPUT_FIELD, content)
    sleep_random(600, 1200)

    # 提交前按已解析出的 comment_id 和作者重新绑定，绝不退化为全局回复按钮。
    rebound = _run_dom(
        page,
        "lookup",
        feed_id,
        comment_id=target_id,
        expected_user_id=target.get("author_id", ""),
    )
    rebound_target = rebound.get("target") if rebound.get("found") else None
    if not rebound_target or rebound_target.get("root_id") != target["root_id"]:
        raise CommentError("提交前目标评论已变化，未发送回复")
    _wait_reply_binding(page, feed_id, target)
    before = _snapshot(page, feed_id)
    if before["account"]["user_id"] != account["user_id"]:
        raise CommentError("提交前登录账号身份已变化，未发送回复")
    before_ids = [str(item.get("id", "")) for item in before["comments"] if item.get("id")]
    try:
        page.click_element(COMMENT_SUBMIT_BUTTON)
    except Exception as exc:
        raise CommentError(
            f"回复提交阶段异常，结果未确认：{exc}；请勿直接重发", status="unknown"
        ) from exc
    sleep_random(1500, 2500)
    reply = _wait_new_comment(
        page,
        feed_id,
        before_ids=before_ids,
        account_id=account["user_id"],
        content=content,
        target=target,
    )
    logger.info("回复评论成功并已核验: target=%s reply=%s", target_id, reply["id"])
    return {
        "success": True,
        "status": "success",
        "feed_id": feed_id,
        "reply_id": reply["id"],
        "comment_id": reply["id"],
        "target_comment_id": target_id,
        "account_id": account["user_id"],
    }


def _find_and_scroll_to_comment(
    page: Page,
    feed_id: str,
    comment_id: str,
    user_id: str,
    max_attempts: int = 100,
    max_expands: int = 30,
) -> dict:
    """先查当前 DOM，再展开楼中楼，最后才判断到底并继续滚动。"""
    logger.info("开始查找评论 - commentID: %s, userID: %s", comment_id, user_id)
    page.scroll_element_into_view(".comments-container")
    sleep_random(800, 1500)
    last_count = -1
    stagnant = 0
    expands = 0

    for attempt in range(max_attempts + 1):
        found = _run_dom(
            page,
            "lookup",
            feed_id,
            comment_id=comment_id,
            user_id="" if comment_id else user_id,
            expected_user_id=user_id if comment_id and user_id else "",
        )
        if found.get("found"):
            target = found["target"]
            if not target.get("id") or not target.get("root_id"):
                raise CommentError("目标评论缺少稳定 ID，未执行回复")
            logger.info("找到目标评论（下滚 %d 次）: %s", attempt, target["id"])
            return target

        if expands < max_expands:
            token = secrets.token_hex(12)
            expansion = _run_dom(page, "mark_expand", feed_id, token=token)
            if expansion.get("found"):
                page.click_element(expansion["selector"])
                expands += 1
                sleep_random(500, 1000)
                continue

        # 已加载的目标和可展开楼中楼都查过后，才允许用“到底”结束。
        if _check_end_container(page):
            logger.info("已到达评论底部，未找到目标评论")
            break
        if attempt >= max_attempts:
            break
        current_count = page.get_elements_count(".comment-item")
        if current_count != last_count:
            last_count = current_count
            stagnant = 0
        else:
            stagnant += 1
            if stagnant >= 10:
                logger.info("评论数量停滞超过 10 次")
                break
        if current_count > 0:
            page.scroll_nth_element_into_view(".comment-item", current_count - 1)
            sleep_random(200, 500)
        page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
        sleep_random(600, 1200)

    raise CommentError(f"未找到评论 (commentID: {comment_id}, userID: {user_id})")


def _js_str(value: str) -> str:
    """将 Python 字符串转为可用于 CSS 属性选择器的 JS 字符串字面量。"""
    return json.dumps(value)
