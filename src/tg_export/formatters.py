"""Convert Telegram message entities to HTML matching Desktop's export format."""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from telethon.tl.types import (
    MessageEntityBankCard,
    MessageEntityBlockquote,
    MessageEntityBold,
    MessageEntityBotCommand,
    MessageEntityCashtag,
    MessageEntityCode,
    MessageEntityCustomEmoji,
    MessageEntityEmail,
    MessageEntityHashtag,
    MessageEntityItalic,
    MessageEntityMention,
    MessageEntityMentionName,
    MessageEntityPhone,
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

    # Telegram entity offsets/lengths are UTF-16 code units; Python str is code
    # points. Translate via a prebuilt index so supplementary-plane chars
    # (emoji, etc.) don't misalign entity boundaries. Skip when text is BMP-only.
    translate = _make_u16_translator(text)

    root = _Node(start=0, end=len(text))
    translated = [
        (e, translate(e.offset), translate(e.offset + e.length)) for e in entities
    ]
    translated.sort(key=lambda t: (t[1], -(t[2] - t[1])))

    for entity, py_start, py_end in translated:
        _insert_entity_range(root, entity, py_start, py_end)

    return _render_node(root, text)


def _make_u16_translator(text: str):
    """Return fn mapping UTF-16 unit offset → Python char index for `text`."""
    text_len = len(text)
    if not any(ord(ch) > 0xFFFF for ch in text):
        def translate_bmp(u16_pos: int) -> int:
            if u16_pos <= 0:
                return 0
            if u16_pos >= text_len:
                return text_len
            return u16_pos
        return translate_bmp

    idx: list[int] = []
    for i, ch in enumerate(text):
        idx.append(i)
        if ord(ch) > 0xFFFF:
            idx.append(i)
    idx.append(text_len)
    idx_len = len(idx)

    def translate(u16_pos: int) -> int:
        if u16_pos <= 0:
            return 0
        if u16_pos >= idx_len:
            return text_len
        return idx[u16_pos]
    return translate


def _insert_entity_range(parent: _Node, entity: object, e_start: int, e_end: int) -> None:
    """Insert an entity into the tree at already-translated Python char indices."""
    node = _Node(start=e_start, end=e_end, entity=entity)

    # Try to insert into an existing child
    for child in parent.children:
        if child.start <= e_start and child.end >= e_end:
            _insert_entity_range(child, entity, e_start, e_end)
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
        case MessageEntityEmail():
            return f'<a href="mailto:{html.escape(raw_text, quote=True)}">{inner_html}</a>'
        case MessageEntityPhone():
            return f'<a href="tel:{html.escape(raw_text, quote=True)}">{inner_html}</a>'
        case MessageEntityHashtag():
            return f'<a href="" onclick="return ShowHashtag({_js_str(raw_text)})">{inner_html}</a>'
        case MessageEntityCashtag():
            return f'<a href="" onclick="return ShowCashtag({_js_str(raw_text)})">{inner_html}</a>'
        case MessageEntityBotCommand():
            return f'<a href="" onclick="return ShowBotCommand({_js_str(raw_text)})">{inner_html}</a>'
        case MessageEntityBankCard():
            return inner_html
        case MessageEntitySpoiler():
            return f'<span class="spoiler hidden" onclick="ShowSpoiler(this)"><span aria-hidden="true">{inner_html}</span></span>'
        case MessageEntityCustomEmoji():
            return inner_html
        case _:
            return inner_html


def _js_str(s: str) -> str:
    """Escape a string for use inside a JS single-quoted literal in an HTML attribute."""
    escaped = s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
    return "'" + html.escape(escaped, quote=True) + "'"


def _text_to_html(text: str) -> str:
    """Convert plain text to HTML, preserving whitespace and newlines."""
    escaped = html.escape(text)
    return escaped.replace("\n", "<br>\n")
