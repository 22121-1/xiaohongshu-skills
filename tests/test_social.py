from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from xhs.social import follow_user


class FakePage:
    def __init__(self, states: list[dict[str, Any]]) -> None:
        self.states = states
        self.navigated: list[str] = []
        self.clicks = 0

    def navigate(self, url: str) -> None:
        self.navigated.append(url)

    def wait_for_load(self) -> None:
        pass

    def wait_dom_stable(self) -> None:
        pass

    def evaluate(self, expression: str) -> Any:
        if "candidates.length !== 1" in expression:
            self.clicks += 1
            return True
        return self.states.pop(0)


def test_follow_user_is_dry_run_by_default() -> None:
    page = FakePage([{"found": True, "text": "关注"}])

    result = follow_user(page, "user", "token")

    assert result["status"] == "ready"
    assert page.clicks == 0
    assert page.navigated


def test_follow_user_executes_only_with_explicit_flag(monkeypatch) -> None:
    monkeypatch.setattr("xhs.social.time.sleep", lambda _: None)
    page = FakePage(
        [
            {"found": True, "text": "关注"},
            {"found": True, "text": "已关注"},
        ]
    )

    result = follow_user(page, "user", "token", execute=True)

    assert result["status"] == "following"
    assert page.clicks == 1
