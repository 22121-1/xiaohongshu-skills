"""关注、通知与私信的独立 CLI 实现。

所有写操作默认 dry-run，只有调用方明确传入 execute=True 才会点击页面控件。
本模块不修改发布、搜索、评论、点赞或收藏链路。
"""

from __future__ import annotations

import json
import time
from typing import Any

from .cdp import Page
from .urls import MESSAGE_URL, NOTIFICATION_URL, make_user_profile_url


def _js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _navigate(page: Page, url: str) -> None:
    page.navigate(url)
    page.wait_for_load()
    page.wait_dom_stable()


def _visible_button_state(page: Page, pattern: str) -> dict[str, Any]:
    """返回可见按钮的文本；页面结构变化时不猜测点击目标。"""
    return page.evaluate(
        f"""
        (() => {{
          const re = new RegExp({_js(pattern)});
          const candidates = Array.from(document.querySelectorAll(
            'button,[role="button"],a,[tabindex]'
          ));
          const el = candidates.find((node) => {{
            const rect = node.getBoundingClientRect();
            const style = window.getComputedStyle(node);
            const text = (node.innerText || node.textContent || '').trim();
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' &&
              style.display !== 'none' && re.test(text);
          }});
            return el ?
              {{ found: true, text: (el.innerText || el.textContent || '').trim() }} :
            {{ found: false, text: '' }};
        }})()
        """
    ) or {"found": False, "text": ""}


def _click_visible_button(page: Page, pattern: str) -> bool:
    """仅点击匹配文本的可见按钮；没有唯一目标即返回 False。"""
    return bool(
        page.evaluate(
            f"""
            (() => {{
              const re = new RegExp({_js(pattern)});
              const candidates = Array.from(document.querySelectorAll(
                'button,[role="button"],a,[tabindex]'
              )).filter((node) => {{
                const rect = node.getBoundingClientRect();
                const style = window.getComputedStyle(node);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' &&
                  style.display !== 'none' &&
                  re.test((node.innerText || node.textContent || '').trim());
              }});
              if (candidates.length !== 1) return false;
              candidates[0].scrollIntoView({{ block: 'center' }});
              candidates[0].click();
              return true;
            }})()
            """
        )
    )


def follow_user(
    page: Page,
    user_id: str,
    xsec_token: str,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    """检查或关注用户；未显式 execute 时绝不点击。"""
    _navigate(page, make_user_profile_url(user_id, xsec_token))
    before = _visible_button_state(page, r"^(关注|已关注)$")
    if not before.get("found"):
        return {
            "success": False,
            "status": "unverified",
            "message": "未找到可核验的关注按钮",
        }
    if before.get("text") == "已关注":
        return {"success": True, "status": "following", "message": "已关注"}
    if not execute:
        return {
            "success": True,
            "status": "ready",
            "message": "已核验可关注；未传 --execute，未执行关注",
        }
    if not _click_visible_button(page, r"^关注$"):
        return {
            "success": False,
            "status": "unverified",
            "message": "关注按钮不唯一或不可点击",
        }
    time.sleep(1)
    after = _visible_button_state(page, r"^(关注|已关注)$")
    if after.get("text") == "已关注":
        return {"success": True, "status": "following", "message": "关注成功"}
    return {
        "success": False,
        "status": "unverified",
        "message": "点击后未核验到已关注状态",
    }


def _read_cards(page: Page, kind: str, limit: int) -> list[dict[str, str]]:
    """读取可见卡片的短文本，不滚动、不展开、不发送任何动作。"""
    selector = (
        '[class*="notification" i],[class*="notice" i],[class*="message" i],'
        '[class*="conversation" i],[class*="chat" i]'
    )
    return page.evaluate(
        f"""
        (() => {{
          const selector = {_js(selector)};
          const limit = {_js(limit)};
          const seen = new Set();
          const cards = [];
          for (const node of document.querySelectorAll(selector)) {{
            const rect = node.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) continue;
            const text = (node.innerText || node.textContent || '').trim().replace(/\\s+/g, ' ');
            if (!text || text.length < 2 || seen.has(text)) continue;
            seen.add(text);
            cards.push({{ text: text.slice(0, 500) }});
            if (cards.length >= limit) break;
          }}
          return cards;
        }})()
        """
    ) or []


def list_notifications(page: Page, limit: int = 20) -> dict[str, Any]:
    """只读取通知页已加载内容；不标记已读、不滚动加载。"""
    _navigate(page, NOTIFICATION_URL)
    return {
        "success": True,
        "kind": "notifications",
        "items": _read_cards(page, "notifications", limit),
    }


def list_inbox(page: Page, limit: int = 20) -> dict[str, Any]:
    """只读取收件箱已加载会话摘要；不打开会话、不标记已读。"""
    _navigate(page, MESSAGE_URL)
    return {"success": True, "kind": "inbox", "items": _read_cards(page, "inbox", limit)}


def send_message(
    page: Page,
    recipient_profile_url: str,
    content: str,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    """从对方公开主页进入私信；默认只核验，发送必须显式 execute。"""
    if not content.strip():
        raise ValueError("私信内容不能为空")
    _navigate(page, recipient_profile_url)
    if not _visible_button_state(page, r"^私信$").get("found"):
        return {"success": False, "status": "unverified", "message": "未找到私信入口"}
    if not execute:
        return {
            "success": True,
            "status": "ready",
            "message": "已核验私信入口；未传 --execute，未发送",
        }
    if not _click_visible_button(page, r"^私信$"):
        return {
            "success": False,
            "status": "unverified",
            "message": "私信入口不唯一或不可点击",
        }
    time.sleep(1)
    editor = '[contenteditable="true"]'
    if not page.has_element(editor):
        return {
            "success": False,
            "status": "unverified",
            "message": "未找到私信输入框",
        }
    page.input_content_editable(editor, content)
    if not _click_visible_button(page, r"^发送$"):
        return {
            "success": False,
            "status": "unverified",
            "message": "发送按钮不唯一或不可点击",
        }
    return {
        "success": True,
        "status": "sent",
        "message": "私信已发起，待后续页面或会话核验",
    }
