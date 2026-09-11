from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_cli_module():
    path = Path(__file__).parents[1] / "scripts" / "cli.py"
    spec = importlib.util.spec_from_file_location("xhs_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_publish_command_still_parses() -> None:
    parser = _load_cli_module().build_parser()
    args = parser.parse_args(
        [
            "publish",
            "--title-file",
            "/tmp/title",
            "--content-file",
            "/tmp/body",
            "--images",
            "/tmp/a.png",
        ]
    )
    assert args.command == "publish"
    assert args.func.__name__ == "cmd_publish"


def test_new_social_write_commands_default_to_dry_run() -> None:
    parser = _load_cli_module().build_parser()
    follow = parser.parse_args(["follow-user", "--user-id", "u", "--xsec-token", "t"])
    message = parser.parse_args(
        [
            "send-message",
            "--recipient-profile-url",
            "https://example.test",
            "--content-file",
            "/tmp/body",
        ]
    )
    assert follow.execute is False
    assert message.execute is False
