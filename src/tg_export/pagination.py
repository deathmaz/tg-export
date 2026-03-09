"""Paginate messages into pages for HTML rendering."""
from __future__ import annotations

from tg_export.models import ExportedMessage, PageInfo


def paginate_messages(
    messages: list[ExportedMessage], msgs_per_page: int
) -> list[list[ExportedMessage]]:
    """Split messages into pages of approximately msgs_per_page each."""
    if not messages:
        return [[]]
    pages = []
    for i in range(0, len(messages), msgs_per_page):
        pages.append(messages[i : i + msgs_per_page])
    return pages


def build_page_info(page_number: int, total_pages: int) -> PageInfo:
    """Build pagination info for a given page, matching tdesktop naming."""
    # tdesktop: messages.html, messages2.html, messages3.html, ...
    filename = "messages.html" if page_number == 1 else f"messages{page_number}.html"

    has_prev = page_number > 1
    has_next = page_number < total_pages

    prev_url = None
    if has_prev:
        prev_url = "messages.html" if page_number == 2 else f"messages{page_number - 1}.html"

    next_url = None
    if has_next:
        next_url = f"messages{page_number + 1}.html"

    return PageInfo(
        page_number=page_number,
        filename=filename,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=prev_url,
        next_url=next_url,
    )
