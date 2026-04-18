"""Tests for message entity to HTML formatting."""
from tg_export.formatters import format_message_text

from telethon.tl.types import (
    MessageEntityBankCard,
    MessageEntityBold,
    MessageEntityBlockquote,
    MessageEntityBotCommand,
    MessageEntityCashtag,
    MessageEntityCode,
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


class TestFormatPlainText:
    def test_empty_string(self):
        assert format_message_text("", None) == ""

    def test_no_entities(self):
        assert format_message_text("Hello world", None) == "Hello world"

    def test_empty_entities(self):
        assert format_message_text("Hello world", []) == "Hello world"

    def test_newlines(self):
        result = format_message_text("line1\nline2", None)
        assert result == "line1<br>\nline2"

    def test_html_escaping(self):
        result = format_message_text("<script>alert('xss')</script>", None)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_ampersand_escaping(self):
        result = format_message_text("A & B", None)
        assert result == "A &amp; B"


class TestFormatSingleEntity:
    def test_bold(self):
        entities = [MessageEntityBold(offset=0, length=5)]
        result = format_message_text("Hello world", entities)
        assert result == "<strong>Hello</strong> world"

    def test_italic(self):
        entities = [MessageEntityItalic(offset=6, length=5)]
        result = format_message_text("Hello world", entities)
        assert result == "Hello <em>world</em>"

    def test_code(self):
        entities = [MessageEntityCode(offset=0, length=4)]
        result = format_message_text("code here", entities)
        assert result == "<code>code</code> here"

    def test_pre(self):
        entities = [MessageEntityPre(offset=0, length=10, language="")]
        result = format_message_text("code block", entities)
        assert result == "<pre>code block</pre>"

    def test_pre_with_language(self):
        entities = [MessageEntityPre(offset=0, length=10, language="python")]
        result = format_message_text("print('hi')", entities)
        assert 'class="language-python"' in result
        assert "<pre><code" in result

    def test_underline(self):
        entities = [MessageEntityUnderline(offset=0, length=5)]
        result = format_message_text("Hello", entities)
        assert result == "<u>Hello</u>"

    def test_strikethrough(self):
        entities = [MessageEntityStrike(offset=0, length=5)]
        result = format_message_text("Hello", entities)
        assert result == "<s>Hello</s>"

    def test_blockquote(self):
        entities = [MessageEntityBlockquote(offset=0, length=5)]
        result = format_message_text("quote", entities)
        assert result == "<blockquote>quote</blockquote>"

    def test_spoiler(self):
        entities = [MessageEntitySpoiler(offset=0, length=7)]
        result = format_message_text("spoiler", entities)
        assert 'class="spoiler hidden"' in result
        assert "ShowSpoiler" in result

    def test_text_url(self):
        entities = [MessageEntityTextUrl(offset=0, length=5, url="https://example.com")]
        result = format_message_text("Click", entities)
        assert result == '<a href="https://example.com">Click</a>'

    def test_text_url_escapes_quotes(self):
        entities = [MessageEntityTextUrl(offset=0, length=5, url='https://example.com/"test"')]
        result = format_message_text("Click", entities)
        assert "&quot;" in result

    def test_plain_url(self):
        url = "https://example.com"
        entities = [MessageEntityUrl(offset=0, length=len(url))]
        result = format_message_text(url, entities)
        assert f'<a href="{url}">{url}</a>' == result

    def test_mention(self):
        entities = [MessageEntityMention(offset=0, length=5)]
        result = format_message_text("@user", entities)
        assert 'href="https://t.me/user"' in result

    def test_mention_name(self):
        entities = [MessageEntityMentionName(offset=0, length=4, user_id=12345)]
        result = format_message_text("John", entities)
        assert 'href="tg://user?id=12345"' in result

    def test_email(self):
        entities = [MessageEntityEmail(offset=0, length=15)]
        result = format_message_text("foo@example.com", entities)
        assert result == '<a href="mailto:foo@example.com">foo@example.com</a>'

    def test_phone(self):
        entities = [MessageEntityPhone(offset=0, length=12)]
        result = format_message_text("+14155552671", entities)
        assert result == '<a href="tel:+14155552671">+14155552671</a>'

    def test_hashtag(self):
        entities = [MessageEntityHashtag(offset=0, length=5)]
        result = format_message_text("#news", entities)
        assert "ShowHashtag('#news')" in result
        assert ">#news</a>" in result

    def test_cashtag(self):
        entities = [MessageEntityCashtag(offset=0, length=4)]
        result = format_message_text("$TSL", entities)
        assert "ShowCashtag" in result
        assert ">$TSL</a>" in result

    def test_bot_command(self):
        entities = [MessageEntityBotCommand(offset=0, length=6)]
        result = format_message_text("/start", entities)
        assert "ShowBotCommand" in result
        assert ">/start</a>" in result

    def test_bank_card(self):
        entities = [MessageEntityBankCard(offset=0, length=16)]
        result = format_message_text("4111111111111111", entities)
        assert result == "4111111111111111"


class TestFormatMultipleEntities:
    def test_two_separate_entities(self):
        entities = [
            MessageEntityBold(offset=0, length=5),
            MessageEntityItalic(offset=6, length=5),
        ]
        result = format_message_text("Hello World", entities)
        assert result == "<strong>Hello</strong> <em>World</em>"

    def test_adjacent_entities(self):
        entities = [
            MessageEntityBold(offset=0, length=5),
            MessageEntityItalic(offset=5, length=5),
        ]
        result = format_message_text("HelloWorld", entities)
        assert result == "<strong>Hello</strong><em>World</em>"

    def test_entity_in_middle(self):
        entities = [MessageEntityBold(offset=6, length=5)]
        result = format_message_text("Hello brave world", entities)
        assert result == "Hello <strong>brave</strong> world"


class TestFormatNestedEntities:
    def test_bold_inside_italic(self):
        # "Hello world" - entire thing italic, "world" also bold
        entities = [
            MessageEntityItalic(offset=0, length=11),
            MessageEntityBold(offset=6, length=5),
        ]
        result = format_message_text("Hello world", entities)
        assert result == "<em>Hello <strong>world</strong></em>"

    def test_code_inside_bold(self):
        entities = [
            MessageEntityBold(offset=0, length=10),
            MessageEntityCode(offset=4, length=4),
        ]
        result = format_message_text("use code ok", entities)
        assert "<strong>" in result
        assert "<code>code</code>" in result

    def test_link_with_bold_text(self):
        entities = [
            MessageEntityTextUrl(offset=0, length=10, url="https://example.com"),
            MessageEntityBold(offset=0, length=10),
        ]
        result = format_message_text("Click here", entities)
        assert "href" in result
        assert "<strong>" in result


class TestFormatEdgeCases:
    def test_entity_at_end(self):
        entities = [MessageEntityBold(offset=6, length=5)]
        result = format_message_text("Hello world", entities)
        assert result == "Hello <strong>world</strong>"

    def test_entity_covers_entire_text(self):
        entities = [MessageEntityBold(offset=0, length=5)]
        result = format_message_text("Hello", entities)
        assert result == "<strong>Hello</strong>"

    def test_text_with_special_chars_in_entity(self):
        entities = [MessageEntityBold(offset=0, length=3)]
        result = format_message_text("A&B rest", entities)
        assert result == "<strong>A&amp;B</strong> rest"

    def test_newline_inside_entity(self):
        entities = [MessageEntityBold(offset=0, length=11)]
        result = format_message_text("line1\nline2", entities)
        assert "<strong>" in result
        assert "<br>" in result

    def test_unicode_text(self):
        result = format_message_text("Hello! 🎉", None)
        assert "🎉" in result

    def test_unicode_with_entity(self):
        # Bold on the emoji
        text = "Hi 🎉"
        entities = [MessageEntityBold(offset=3, length=2)]
        result = format_message_text(text, entities)
        assert "<strong>" in result

    def test_utf16_offset_after_emoji(self):
        # UTF-16: "🎉" = 2 units, " there" starts at unit 2. Python chars: "🎉"=1, " there" starts at 1.
        text = "🎉 there"
        entities = [MessageEntityBold(offset=3, length=5)]
        result = format_message_text(text, entities)
        assert result == "🎉 <strong>there</strong>"

    def test_utf16_entity_spans_emoji(self):
        # Bold covers the emoji: UTF-16 offset=0, length=2 (just the emoji)
        text = "🎉x"
        entities = [MessageEntityBold(offset=0, length=2)]
        result = format_message_text(text, entities)
        assert result == "<strong>🎉</strong>x"

    def test_utf16_mixed_bmp_and_emoji(self):
        # "Hi 🎉 bold" — bold on "bold" at UTF-16 offset=6, length=4
        text = "Hi 🎉 bold"
        entities = [MessageEntityBold(offset=6, length=4)]
        result = format_message_text(text, entities)
        assert result == "Hi 🎉 <strong>bold</strong>"
