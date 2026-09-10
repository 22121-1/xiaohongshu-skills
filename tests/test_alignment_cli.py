"""CLI must not hide unknown mutations behind exit code 0."""
import argparse
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cli
from xhs import comment, like_favorite, user_profile
from xhs.types import ActionResult


@pytest.mark.parametrize('command,func,flag', [
    ('cmd_like_feed', 'like_feed', 'unlike'), ('cmd_favorite_feed', 'favorite_feed', 'unfavorite'),
])
def test_unknown_interaction_has_nonzero_exit(monkeypatch, command, func, flag):
    browser, page = Mock(), Mock()
    monkeypatch.setattr(cli, '_connect', lambda _: (browser, page))
    monkeypatch.setattr(
        like_favorite, func, lambda *_: ActionResult(success=False, status='unknown'),
    )
    output = Mock()
    monkeypatch.setattr(cli, '_output', output)
    args = argparse.Namespace(feed_id='a'*24, xsec_token='token', **{flag:False})
    getattr(cli, command)(args)
    assert output.call_args.kwargs['exit_code'] == 2
    assert output.call_args.args[0]['status'] == 'unknown'
    browser.close.assert_called_once()


def test_comment_receipt_is_preserved(monkeypatch):
    browser, page = Mock(), Mock()
    monkeypatch.setattr(cli, '_connect', lambda _: (browser, page))
    receipt = {'success':True, 'comment_id':'c', 'account_id':'a', 'status':'success'}
    monkeypatch.setattr(comment, 'post_comment', lambda *_: receipt)
    output = Mock()
    monkeypatch.setattr(cli, '_output', output)
    cli.cmd_post_comment(argparse.Namespace(feed_id='f',xsec_token='t',content='text'))
    assert output.call_args.args[0] == receipt


def test_existing_profile_command_receives_selected_tab(monkeypatch):
    monkeypatch.setattr(cli, '_connect', lambda _: (Mock(), Mock()))
    call = Mock(return_value=Mock(to_dict=lambda:{}))
    monkeypatch.setattr(user_profile, 'get_user_profile', call)
    monkeypatch.setattr(cli, '_output', Mock())
    cli.cmd_user_profile(argparse.Namespace(user_id='a'*24,xsec_token='t',tab='liked'))
    assert call.call_args.kwargs['tab'] == 'liked'


def test_comment_default_limit_is_bounded():
    args = cli.build_parser().parse_args(['get-feed-detail','--feed-id','a'*24,'--xsec-token','t',
                                        '--load-all-comments'])
    assert args.max_comment_items == 20
