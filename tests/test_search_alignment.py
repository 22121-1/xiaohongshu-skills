"""Search invalid-input, empty-result and non-note filtering regression checks."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from xhs import feeds, search
from xhs.errors import XHSError
from xhs.types import FilterOption


def test_invalid_filters_never_navigate():
    page = Mock()
    with pytest.raises(ValueError):
        search.search_feeds(page, 'test', FilterOption(sort_by='wrong'))
    page.navigate.assert_not_called()


@pytest.mark.parametrize('items,expected', [([], []), ([
    {'id': 'a', 'modelType': 'note'}, {'id': 'b', 'modelType': 'live_v2'},
    {'id': 'c', 'modelType': 'hot_query'},
    {'id': 'd', 'modelType': 'note', 'noteCard': {'type': 'video'}},
], ['a', 'd'])])
def test_search_completed_results_only_contain_notes(items, expected):
    page = Mock()
    page.evaluate.side_effect = [
        {'state': 'success', 'ready': True, 'keyword': 'test'}, json.dumps(items),
    ]
    assert [f.id for f in search.search_feeds(page, 'test')] == expected


def test_failed_search_is_not_empty_success():
    page = Mock()
    page.evaluate.return_value = {'state': 'error', 'ready': True}
    with pytest.raises(XHSError, match='加载失败'):
        search.search_feeds(page, 'test')


def test_feed_filter_preserves_video_and_excludes_cards(monkeypatch):
    monkeypatch.setattr(feeds.time, 'sleep', lambda *_: None)
    page = Mock()
    page.evaluate.return_value = json.dumps([
        {'id': 'a', 'modelType': 'live_v2'},
        {'id': 'b', 'modelType': 'note', 'noteCard': {'type': 'video'}},
    ])
    assert [f.id for f in feeds.list_feeds(page)] == ['b']


def test_filter_unconfirmed_result_is_error():
    page = Mock()
    page.evaluate.return_value = None
    with pytest.raises(ValueError, match='未确认'):
        search._apply_filters(page, [(1, '最新')])


def test_stale_keyword_does_not_count_as_loaded(monkeypatch):
    page = Mock()
    page.evaluate.return_value = {'state': 'success', 'ready': True, 'keyword': 'old'}
    ticks = iter([0, 0, 20])
    monkeypatch.setattr(search.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(search.time, 'sleep', lambda _: None)
    with pytest.raises(XHSError, match='未确认'):
        search._wait_for_search_feeds(page, keyword='requested')
