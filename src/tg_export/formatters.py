"""Convert Telegram message entities to HTML matching Desktop's export format."""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from telethon.tl.types import (
    MessageEntityBlockquote,
    MessageEntityBold,
    MessageEntityCode,
    MessageEntityCustomEmoji,
    MessageEntityHashtag,
    MessageEntityItalic,
    MessageEntityMention,
    MessageEntityMentionName,
    MessageEntityPre,
    MessageEntitySpoiler,
    MessageEntityStrike,
    MessageEntityTextUrl,
    MessageEntityUnderline,
    MessageEntityUrl,
)


@dataclass
class _Node:
    """A node in the entity tree for handling overlapping entities."""
    start: int
    end: int
    entity: object | None = None  # None for the root node
    children: list[_Node] = field(default_factory=list)
    text: str = ""


def format_message_text(text: str, entities: list | None) -> str:
    """Convert message text + entities to HTML matching Telegram Desktop format."""
    if not text:
        return ""
    if not entities:
        return _text_to_html(text)

    # Build a tree of entities to handle overlapping ranges
    root = _Node(start=0, end=len(text))
    sorted_entities = sorted(entities, key=lambda e: (e.offset, -e.length))

    for entity in sorted_entities:
        _insert_entity(root, entity)

    return _render_node(root, text)


def _insert_entity(parent: _Node, entity: object) -> None:
    """Insert an entity into the tree, handling nesting."""
    e_start = entity.offset
    e_end = entity.offset + entity.length
    node = _Node(start=e_start, end=e_end, entity=entity)

    # Try to insert into an existing child
    for child in parent.children:
        if child.start <= e_start and child.end >= e_end:
            _insert_entity(child, entity)
            return

    # Insert at this level, potentially adopting existing children
    adopted = []
    remaining = []
    for child in parent.children:
        if e_start <= child.start and e_end >= child.end:
            adopted.append(child)
        else:
            remaining.append(child)

    node.children = adopted
    remaining.append(node)
    remaining.sort(key=lambda n: n.start)
    parent.children = remaining


def _render_node(node: _Node, full_text: str) -> str:
    """Render a node and its children to HTML."""
    if not node.children:
        # Leaf node - just render the text
        segment = full_text[node.start:node.end]
        inner = _text_to_html(segment)
    else:
        # Build inner HTML from children and text gaps between them
        parts = []
        pos = node.start
        for child in node.children:
            if child.start > pos:
                parts.append(_text_to_html(full_text[pos:child.start]))
            parts.append(_render_node(child, full_text))
            pos = child.end
        if pos < node.end:
            parts.append(_text_to_html(full_text[pos:node.end]))
        inner = "".join(parts)

    if node.entity is None:
        return inner  # Root node

    return _wrap_entity(node.entity, inner, full_text[node.start:node.end])


def _wrap_entity(entity: object, inner_html: str, raw_text: str) -> str:
    """Wrap inner HTML with the appropriate tag for the entity type."""
    match entity:
        case MessageEntityBold():
            return f"<strong>{inner_html}</strong>"
        case MessageEntityItalic():
            return f"<em>{inner_html}</em>"
        case MessageEntityCode():
            return f"<code>{inner_html}</code>"
        case MessageEntityPre():
            lang = getattr(entity, "language", "") or ""
            if lang:
                return f'<pre><code class="language-{html.escape(lang)}">{inner_html}</code></pre>'
            return f"<pre>{inner_html}</pre>"
        case MessageEntityUnderline():
            return f"<u>{inner_html}</u>"
        case MessageEntityStrike():
            return f"<s>{inner_html}</s>"
        case MessageEntityBlockquote():
            return f"<blockquote>{inner_html}</blockquote>"
        case MessageEntityTextUrl():
            url = html.escape(entity.url, quote=True)
            return f'<a href="{url}">{inner_html}</a>'
        case MessageEntityUrl():
            url = html.escape(raw_text, quote=True)
            return f'<a href="{url}">{inner_html}</a>'
        case MessageEntityMention():
            username = raw_text.lstrip("@")
            return f'<a href="https://t.me/{html.escape(username)}">{inner_html}</a>'
        case MessageEntityMentionName():
            return f'<a href="tg://user?id={entity.user_id}">{inner_html}</a>'
        case MessageEntityHashtag():
            return inner_html
        case MessageEntitySpoiler():
            return f'<span class="spoiler hidden" onclick="ShowSpoiler(this)">{inner_html}</span>'
        case MessageEntityCustomEmoji():
            return inner_html
        case _:
            return inner_html


def _text_to_html(text: str) -> str:
    """Convert plain text to HTML, preserving whitespace and newlines."""
    escaped = html.escape(text)
    return escaped.replace("\n", "<br>\n")
