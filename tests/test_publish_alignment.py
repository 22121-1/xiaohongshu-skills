from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cli
from xhs import publish, publish_video
from xhs.errors import AccountRiskControlError, PublishError
from xhs.types import PublishImageContent, PublishVideoContent

SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=SHANGHAI)


class ConfirmationPage:
    def __init__(self, *, result: dict | None = None, url: str = "/publish/publish") -> None:
        self.result = result
        self.url = url

    def evaluate(self, expression: str):
        if expression == "window.__xhsPublishResult":
            return self.result
        if expression == "window.location.href":
            return self.url
        raise AssertionError(f"unexpected expression: {expression}")


class ImagePublishPage:
    def __init__(self) -> None:
        self.fire_count = 0

    def evaluate(self, expression: str):
        if "dispatchEvent(new CustomEvent('publish'" in expression:
            self.fire_count += 1
            return "fired"
        raise AssertionError(f"unexpected expression: {expression}")


def test_publish_timeout_is_explicitly_unconfirmed_and_never_retries(monkeypatch) -> None:
    page = ConfirmationPage()
    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(publish.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(publish.time, "sleep", lambda _seconds: None)

    with pytest.raises(publish.PublishUnconfirmedError, match=r"发布结果未确认.*未自动重试") as exc:
        publish._wait_for_publish_confirmation(page, timeout=1.0)

    assert exc.value.status == "unknown"


def test_publish_confirmation_accepts_trusted_success_route() -> None:
    page = ConfirmationPage(url="https://creator.xiaohongshu.com/publish/success")

    publish._wait_for_publish_confirmation(page, timeout=1.0)


def test_publish_confirmation_does_not_treat_arbitrary_navigation_as_success(
    monkeypatch,
) -> None:
    page = ConfirmationPage(url="https://creator.xiaohongshu.com/404")
    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(publish.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(publish.time, "sleep", lambda _seconds: None)

    with pytest.raises(publish.PublishUnconfirmedError):
        publish._wait_for_publish_confirmation(page, timeout=1.0)


def test_publish_confirmation_rejects_success_path_on_another_host(monkeypatch) -> None:
    page = ConfirmationPage(url="https://example.com/publish/success")
    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(publish.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(publish.time, "sleep", lambda _seconds: None)

    with pytest.raises(publish.PublishUnconfirmedError):
        publish._wait_for_publish_confirmation(page, timeout=1.0)


def test_publish_confirmation_preserves_api_risk_detection() -> None:
    page = ConfirmationPage(result={"source": "xhr", "code": -9136, "msg": "禁止发笔记"})

    with pytest.raises(AccountRiskControlError, match="禁止发笔记"):
        publish._wait_for_publish_confirmation(page, timeout=1.0)


@pytest.mark.parametrize(
    "result",
    [
        {"source": "xhr", "code": 1001, "success": True, "msg": "校验失败"},
        {"source": "fetch", "code": 0, "success": False, "msg": "提交失败"},
    ],
)
def test_publish_confirmation_prioritizes_explicit_failure(result: dict) -> None:
    with pytest.raises(PublishError, match="发布失败"):
        publish._raise_for_publish_result(result)


def test_unrecognized_publish_feedback_remains_unknown() -> None:
    with pytest.raises(publish.PublishUnconfirmedError, match="无法识别的反馈") as exc:
        publish._raise_for_publish_result({"source": "xhr", "msg": "处理中"})

    assert exc.value.status == "unknown"


def test_cli_preserves_unknown_publish_status(monkeypatch) -> None:
    def fail(_args) -> None:
        raise publish.PublishUnconfirmedError("发布结果未确认")

    parser = Mock()
    parser.parse_args.return_value = SimpleNamespace(func=fail)
    output = Mock()
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    monkeypatch.setattr(cli, "_output", output)

    cli.main()

    output.assert_called_once_with(
        {"success": False, "error": "发布结果未确认", "status": "unknown"},
        exit_code=2,
    )


def test_image_publish_feedback_failure_does_not_fire_twice(monkeypatch) -> None:
    page = ImagePublishPage()
    monkeypatch.setattr(publish, "_install_publish_result_capture", lambda _page: None)
    monkeypatch.setattr(
        publish,
        "_wait_for_publish_confirmation",
        Mock(side_effect=publish.PublishUnconfirmedError("发布结果未确认")),
    )

    with pytest.raises(publish.PublishUnconfirmedError):
        publish.click_publish_button(page)

    assert page.fire_count == 1


def test_image_publish_dispatch_exception_is_unknown_and_never_retries(monkeypatch) -> None:
    page = Mock()
    page.evaluate.side_effect = RuntimeError("连接中断")
    monkeypatch.setattr(publish, "_install_publish_result_capture", lambda _page: None)
    wait_for_confirmation = Mock()
    monkeypatch.setattr(publish, "_wait_for_publish_confirmation", wait_for_confirmation)

    with pytest.raises(publish.PublishUnconfirmedError, match=r"操作可能已触发.*未自动重试") as exc:
        publish.click_publish_button(page)

    assert exc.value.status == "unknown"
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert page.evaluate.call_count == 1
    wait_for_confirmation.assert_not_called()


def test_publish_confirmation_feedback_read_exception_is_unknown() -> None:
    page = Mock()
    page.evaluate.side_effect = RuntimeError("读取反馈失败")

    with pytest.raises(publish.PublishUnconfirmedError, match="读取发布反馈") as exc:
        publish._wait_for_publish_confirmation(page, timeout=1.0)

    assert exc.value.status == "unknown"
    assert isinstance(exc.value.__cause__, RuntimeError)


def test_publish_confirmation_url_read_exception_is_unknown() -> None:
    page = Mock()
    page.evaluate.side_effect = [None, RuntimeError("读取地址失败")]

    with pytest.raises(publish.PublishUnconfirmedError, match="读取发布后页面地址") as exc:
        publish._wait_for_publish_confirmation(page, timeout=1.0)

    assert exc.value.status == "unknown"
    assert isinstance(exc.value.__cause__, RuntimeError)


@pytest.mark.parametrize(
    "result",
    [
        {"source": "xhr", "code": False},
        {"source": "xhr", "code": False, "success": True},
    ],
)
def test_boolean_publish_code_is_unknown(result: dict) -> None:
    with pytest.raises(publish.PublishUnconfirmedError, match="无法识别的业务码"):
        publish._raise_for_publish_result(result)


@pytest.mark.parametrize("result", [None, [], "not-json"])
def test_non_mapping_publish_feedback_is_unknown(result: object) -> None:
    with pytest.raises(publish.PublishUnconfirmedError, match="反馈格式无法识别"):
        publish._raise_for_publish_result(result)


@pytest.mark.parametrize(
    ("scheduled", "error"),
    [
        ("2026-09-10T12:59:59+08:00", "至少在1小时后"),
        ("2026-09-24T12:00:01+08:00", "不能超过14天"),
        ("2026-09-10T14:00:00", "必须包含明确时区"),
    ],
)
def test_schedule_time_rejects_invalid_window_or_missing_timezone(
    scheduled: str, error: str
) -> None:
    with pytest.raises(PublishError, match=error):
        publish._validate_schedule_time(scheduled, now=NOW)


@pytest.mark.parametrize(
    "scheduled",
    [
        "2026-09-10T13:00:00+08:00",
        "2026-09-24T12:00:00+08:00",
    ],
)
def test_schedule_time_accepts_inclusive_one_hour_to_fourteen_day_window(
    scheduled: str,
) -> None:
    assert publish._validate_schedule_time(scheduled, now=NOW) is not None


def test_schedule_time_converts_to_explicit_publish_page_timezone() -> None:
    scheduled = publish._validate_schedule_time("2026-09-10T06:00:00Z", now=NOW)

    assert scheduled == datetime(2026, 9, 10, 14, 0, tzinfo=SHANGHAI)
    assert scheduled is not None
    assert scheduled.utcoffset() == timedelta(hours=8)


@pytest.mark.parametrize(
    "content",
    [
        PublishImageContent(
            image_paths=["/unused/image.png"],
            schedule_time="2026-09-10T14:00:00",
        ),
        PublishVideoContent(
            video_path="/unused/video.mp4",
            schedule_time="2026-09-10T14:00:00",
        ),
    ],
)
def test_schedule_validation_happens_before_navigation_for_both_publish_flows(
    content: PublishImageContent | PublishVideoContent,
) -> None:
    page = Mock()

    with pytest.raises(PublishError, match="明确时区"):
        if isinstance(content, PublishImageContent):
            publish.fill_publish_form(page, content)
        else:
            publish_video.fill_publish_video_form(page, content)

    page.navigate.assert_not_called()


def test_explicit_original_failure_stops_form_completion(monkeypatch) -> None:
    page = Mock()
    monkeypatch.setattr(publish.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(publish, "_check_title_max_length", lambda _page: None)
    monkeypatch.setattr(publish, "_find_content_element", lambda _page: ".editor")
    monkeypatch.setattr(publish, "_check_content_max_length", lambda _page: None)
    monkeypatch.setattr(publish, "_set_visibility", lambda _page, _visibility: None)
    monkeypatch.setattr(
        publish,
        "_set_original",
        Mock(side_effect=RuntimeError("原创控件失败")),
    )

    with pytest.raises(PublishError, match=r"已请求原创，中止发布.*原创控件失败"):
        publish._fill_publish_form(page, "标题", "正文", [], None, True, "")


def test_video_publish_feedback_failure_does_not_click_twice(monkeypatch) -> None:
    page = Mock()
    monkeypatch.setattr(publish_video, "_wait_for_publish_button_clickable", lambda _page: None)
    monkeypatch.setattr(publish_video, "_install_publish_result_capture", lambda _page: None)
    monkeypatch.setattr(
        publish_video,
        "_wait_for_publish_confirmation",
        Mock(side_effect=PublishError("发布结果未确认")),
    )

    with pytest.raises(PublishError, match="发布结果未确认"):
        publish_video.click_publish_video_button(page)

    page.click_element.assert_called_once_with(publish_video.PUBLISH_BUTTON)


def test_video_publish_click_exception_is_unknown_and_never_retries(monkeypatch) -> None:
    page = Mock()
    page.click_element.side_effect = RuntimeError("连接中断")
    monkeypatch.setattr(publish_video, "_wait_for_publish_button_clickable", lambda _page: None)
    monkeypatch.setattr(publish_video, "_install_publish_result_capture", lambda _page: None)
    wait_for_confirmation = Mock()
    monkeypatch.setattr(publish_video, "_wait_for_publish_confirmation", wait_for_confirmation)

    with pytest.raises(publish.PublishUnconfirmedError, match=r"操作可能已触发.*未自动重试") as exc:
        publish_video.click_publish_video_button(page)

    assert exc.value.status == "unknown"
    assert isinstance(exc.value.__cause__, RuntimeError)
    page.click_element.assert_called_once_with(publish_video.PUBLISH_BUTTON)
    wait_for_confirmation.assert_not_called()


def test_subsequent_image_upload_targets_an_image_accept_input(tmp_path, monkeypatch) -> None:
    # 真实页面快照中，视频输入框 accept 为视频扩展；切到可见图文标签后，
    # 图片输入框 accept 为 .jpg,.jpeg,.png,.webp 且带 multiple。
    image_paths = [tmp_path / "first.jpg", tmp_path / "second.jpg"]
    for path in image_paths:
        path.touch()
    page = Mock()
    monkeypatch.setattr(publish, "_wait_for_upload_complete", lambda _page, _count: None)
    monkeypatch.setattr(publish.time, "sleep", lambda _seconds: None)

    publish._upload_images(page, [str(path) for path in image_paths])

    assert page.set_file_input.call_args_list[0].args[0] == publish.UPLOAD_INPUT
    subsequent_selector = page.set_file_input.call_args_list[1].args[0]
    assert subsequent_selector == publish.IMAGE_FILE_INPUT
    assert 'accept*=".jpg"' in subsequent_selector
    assert subsequent_selector != 'input[type="file"]'
