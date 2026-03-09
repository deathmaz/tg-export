"""Tests for pagination logic."""
from datetime import datetime, timezone

import pytest

from tg_export.models import ExportedMessage
from tg_export.pagination import build_page_info, paginate_messages


def _msg(id: int) -> ExportedMessage:
    """Create a minimal message for testing."""
    return ExportedMessage(
        id=id,
        date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        date_full="",
        date_short="",
        sender_name="Test",
        sender_id=1,
        text_html="msg",
    )


class TestPaginateMessages:
    def test_empty(self):
        pages = paginate_messages([], 100)
        assert pages == [[]]

    def test_single_page(self):
        msgs = [_msg(i) for i in range(5)]
        pages = paginate_messages(msgs, 100)
        assert len(pages) == 1
        assert len(pages[0]) == 5

    def test_exact_fit(self):
        msgs = [_msg(i) for i in range(10)]
        pages = paginate_messages(msgs, 10)
        assert len(pages) == 1
        assert len(pages[0]) == 10

    def test_multiple_pages(self):
        msgs = [_msg(i) for i in range(25)]
        pages = paginate_messages(msgs, 10)
        assert len(pages) == 3
        assert len(pages[0]) == 10
        assert len(pages[1]) == 10
        assert len(pages[2]) == 5

    def test_one_per_page(self):
        msgs = [_msg(i) for i in range(3)]
        pages = paginate_messages(msgs, 1)
        assert len(pages) == 3
        assert all(len(p) == 1 for p in pages)

    def test_preserves_order(self):
        msgs = [_msg(i) for i in range(5)]
        pages = paginate_messages(msgs, 3)
        assert pages[0][0].id == 0
        assert pages[0][2].id == 2
        assert pages[1][0].id == 3


class TestBuildPageInfo:
    def test_single_page(self):
        info = build_page_info(1, 1)
        assert info.filename == "messages.html"
        assert info.has_prev is False
        assert info.has_next is False
        assert info.prev_url is None
        assert info.next_url is None

    def test_first_of_many(self):
        info = build_page_info(1, 5)
        assert info.filename == "messages.html"
        assert info.has_prev is False
        assert info.has_next is True
        assert info.next_url == "messages2.html"

    def test_middle_page(self):
        info = build_page_info(3, 5)
        assert info.filename == "messages3.html"
        assert info.has_prev is True
        assert info.has_next is True
        assert info.prev_url == "messages2.html"
        assert info.next_url == "messages4.html"

    def test_last_page(self):
        info = build_page_info(5, 5)
        assert info.filename == "messages5.html"
        assert info.has_prev is True
        assert info.has_next is False
        assert info.prev_url == "messages4.html"
        assert info.next_url is None

    def test_second_page_links_to_messages_html(self):
        info = build_page_info(2, 3)
        assert info.prev_url == "messages.html"

    def test_page_number_stored(self):
        info = build_page_info(4, 10)
        assert info.page_number == 4
