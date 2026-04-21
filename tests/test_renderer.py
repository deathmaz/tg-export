"""Tests for HTML rendering and message grouping."""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tg_export.models import ChannelInfo, ExportConfig, ExportedMessage, MessageGroup
from tg_export.renderer import HtmlRenderer, format_utc_offset


def _msg(
    id: int,
    sender_name: str = "Alice",
    sender_id: int = 100,
    date: datetime | None = None,
    is_service: bool = False,
    service_text: str | None = None,
    forwarded_from: str | None = None,
    text_html: str = "Hello",
) -> ExportedMessage:
    if date is None:
        date = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    return ExportedMessage(
        id=id,
        date=date,
        sender_name=sender_name,
        sender_id=sender_id,
        text_html=text_html,
        is_service=is_service,
        service_text=service_text,
        forwarded_from=forwarded_from,
    )


def _make_renderer() -> HtmlRenderer:
    return HtmlRenderer(Path("/tmp/test"), ExportConfig())


class TestMessageGrouping:
    def test_single_message(self):
        renderer = _make_renderer()
        msgs = [_msg(1)]
        groups = renderer._group_messages(msgs)
        # date separator + message
        assert len(groups) == 2
        assert groups[0]["type"] == "date_separator"
        assert isinstance(groups[1], MessageGroup)
        assert groups[1].joined is False

    def test_same_sender_within_window_joins(self):
        renderer = _make_renderer()
        t1 = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 15, 10, 0, 30, tzinfo=timezone.utc)
        msgs = [_msg(1, date=t1), _msg(2, date=t2)]
        groups = renderer._group_messages(msgs)
        # date separator + msg1 + msg2
        assert len(groups) == 3
        assert groups[1].joined is False
        assert groups[2].joined is True

    def test_same_sender_outside_window_not_joined(self):
        renderer = _make_renderer()
        t1 = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 15, 10, 5, 0, tzinfo=timezone.utc)  # 5 min later
        msgs = [_msg(1, date=t1), _msg(2, date=t2)]
        groups = renderer._group_messages(msgs)
        assert groups[1].joined is False
        assert groups[2].joined is False

    def test_different_sender_not_joined(self):
        renderer = _make_renderer()
        t = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        msgs = [
            _msg(1, sender_name="Alice", sender_id=100, date=t),
            _msg(2, sender_name="Bob", sender_id=200, date=t + timedelta(seconds=10)),
        ]
        groups = renderer._group_messages(msgs)
        assert groups[1].joined is False
        assert groups[2].joined is False

    def test_forwarded_message_not_joined(self):
        renderer = _make_renderer()
        t = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        msgs = [
            _msg(1, date=t),
            _msg(2, date=t + timedelta(seconds=10), forwarded_from="Someone"),
        ]
        groups = renderer._group_messages(msgs)
        assert groups[2].joined is False

    def test_date_separator_inserted(self):
        renderer = _make_renderer()
        t1 = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 16, 10, 0, tzinfo=timezone.utc)
        msgs = [_msg(1, date=t1), _msg(2, date=t2)]
        groups = renderer._group_messages(msgs)
        separators = [g for g in groups if isinstance(g, dict) and g.get("type") == "date_separator"]
        assert len(separators) == 2
        assert "January 15" in separators[0]["date"]
        assert "January 16" in separators[1]["date"]

    def test_date_separator_resets_grouping(self):
        renderer = _make_renderer()
        t1 = datetime(2025, 1, 15, 23, 59, 50, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 16, 0, 0, 5, tzinfo=timezone.utc)  # Within 60s but different day
        msgs = [_msg(1, date=t1), _msg(2, date=t2)]
        groups = renderer._group_messages(msgs)
        msg_groups = [g for g in groups if isinstance(g, MessageGroup)]
        # Both should be not joined since date separator resets grouping
        assert msg_groups[0].joined is False
        assert msg_groups[1].joined is False

    def test_service_message(self):
        renderer = _make_renderer()
        msgs = [_msg(1, is_service=True, service_text="joined the group")]
        groups = renderer._group_messages(msgs)
        services = [g for g in groups if isinstance(g, dict) and g.get("type") == "service"]
        assert len(services) == 1
        assert services[0]["text"] == "joined the group"

    def test_service_message_resets_grouping(self):
        renderer = _make_renderer()
        t = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        msgs = [
            _msg(1, date=t),
            _msg(2, date=t + timedelta(seconds=10), is_service=True, service_text="pinned"),
            _msg(3, date=t + timedelta(seconds=20)),
        ]
        groups = renderer._group_messages(msgs)
        msg_groups = [g for g in groups if isinstance(g, MessageGroup)]
        # msg3 should not be joined because service message interrupted
        assert msg_groups[1].joined is False

    def test_initials_single_name(self):
        renderer = _make_renderer()
        msgs = [_msg(1, sender_name="Alice")]
        groups = renderer._group_messages(msgs)
        msg_group = [g for g in groups if isinstance(g, MessageGroup)][0]
        assert msg_group.initials == "A"

    def test_initials_two_names(self):
        renderer = _make_renderer()
        msgs = [_msg(1, sender_name="Alice Smith")]
        groups = renderer._group_messages(msgs)
        msg_group = [g for g in groups if isinstance(g, MessageGroup)][0]
        assert msg_group.initials == "AS"

    def test_joined_message_no_initials(self):
        renderer = _make_renderer()
        t = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        msgs = [_msg(1, date=t), _msg(2, date=t + timedelta(seconds=10))]
        groups = renderer._group_messages(msgs)
        msg_groups = [g for g in groups if isinstance(g, MessageGroup)]
        assert msg_groups[0].initials == "A"
        assert msg_groups[1].initials == ""  # Joined, no initials

    def test_empty_messages(self):
        renderer = _make_renderer()
        groups = renderer._group_messages([])
        assert groups == []

    def test_none_sender_id_not_joined(self):
        renderer = _make_renderer()
        t = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        msgs = [
            _msg(1, sender_id=None, date=t),
            _msg(2, sender_id=None, date=t + timedelta(seconds=10)),
        ]
        groups = renderer._group_messages(msgs)
        msg_groups = [g for g in groups if isinstance(g, MessageGroup)]
        # None sender_id should not be joined
        assert msg_groups[1].joined is False


class TestHtmlRendering:
    def test_render_channel_creates_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir))
            renderer = HtmlRenderer(output_dir, config)
            renderer.copy_static_assets()

            channel = ChannelInfo(id=1, title="Test", message_count=2)
            msgs = [
                _msg(1, date=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)),
                _msg(2, date=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc)),
            ]
            chat_dir = output_dir / "chats" / "chat_1"
            chat_dir.mkdir(parents=True)
            renderer.render_channel(channel, msgs, chat_dir)

            assert (chat_dir / "messages.html").exists()

    def test_render_creates_multiple_pages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir), msgs_per_page=5)
            renderer = HtmlRenderer(output_dir, config)
            renderer.copy_static_assets()

            channel = ChannelInfo(id=1, title="Test", message_count=12)
            msgs = [
                _msg(i, date=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc))
                for i in range(12)
            ]
            chat_dir = output_dir / "chats" / "chat_1"
            chat_dir.mkdir(parents=True)
            renderer.render_channel(channel, msgs, chat_dir)

            assert (chat_dir / "messages.html").exists()
            assert (chat_dir / "messages2.html").exists()
            assert (chat_dir / "messages3.html").exists()
            assert not (chat_dir / "messages4.html").exists()

    def test_render_index_with_explicit_channels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir))
            renderer = HtmlRenderer(output_dir, config)
            renderer.copy_static_assets()

            channels = [
                ChannelInfo(id=1, title="Channel One", username="ch1", message_count=100),
                ChannelInfo(id=2, title="Channel Two", message_count=50),
            ]
            renderer.render_index(channels)

            index_html = (output_dir / "export_results.html").read_text()
            assert "Channel One" in index_html
            assert "Channel Two" in index_html
            assert "100 messages" in index_html

    def test_render_index_from_saved_metadata(self):
        """Index should list all previously exported channels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir))
            renderer = HtmlRenderer(output_dir, config)

            # Simulate two separate exports
            ch1 = ChannelInfo(id=1, title="First Channel", username="first", message_count=10)
            chat_dir1 = output_dir / "chats" / "chat_1"
            chat_dir1.mkdir(parents=True)
            renderer.save_channel_meta(ch1, chat_dir1)

            ch2 = ChannelInfo(id=2, title="Second Channel", message_count=20)
            chat_dir2 = output_dir / "chats" / "chat_2"
            chat_dir2.mkdir(parents=True)
            renderer.save_channel_meta(ch2, chat_dir2)

            # Render index without passing channels — should discover both
            renderer.render_index()

            index_html = (output_dir / "export_results.html").read_text()
            assert "First Channel" in index_html
            assert "Second Channel" in index_html
            assert "10 messages" in index_html
            assert "20 messages" in index_html

    def test_render_index_empty_chats_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir))
            renderer = HtmlRenderer(output_dir, config)
            renderer.copy_static_assets()

            renderer.render_index()

            index_html = (output_dir / "export_results.html").read_text()
            assert "Exported Data" in index_html

    def test_static_assets_copied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir))
            renderer = HtmlRenderer(output_dir, config)
            renderer.copy_static_assets()

            assert (output_dir / "css" / "style.css").exists()
            assert (output_dir / "js" / "script.js").exists()

    def test_html_contains_tdesktop_classes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir))
            renderer = HtmlRenderer(output_dir, config)
            renderer.copy_static_assets()

            channel = ChannelInfo(id=1, title="Test", message_count=1)
            msgs = [_msg(1)]
            chat_dir = output_dir / "chats" / "chat_1"
            chat_dir.mkdir(parents=True)
            renderer.render_channel(channel, msgs, chat_dir)

            html = (chat_dir / "messages.html").read_text()
            assert "message default clearfix" in html
            assert "pull_left userpic_wrap" in html
            assert "from_name" in html
            assert "page_header" in html
            assert "page_body chat_page" in html

    def test_html_renders_timestamps_in_configured_tz(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir), timezone="Europe/Berlin")
            renderer = HtmlRenderer(output_dir, config)
            renderer.copy_static_assets()

            channel = ChannelInfo(id=1, title="Test", message_count=1)
            # 10:00 UTC on 2025-06-01 = 12:00 Berlin (CEST, UTC+02:00)
            msg_date = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)
            msgs = [_msg(1, date=msg_date)]
            chat_dir = output_dir / "chats" / "chat_1"
            chat_dir.mkdir(parents=True)
            renderer.render_channel(channel, msgs, chat_dir)

            html = (chat_dir / "messages.html").read_text()
            assert "12:00" in html  # Berlin HH:MM
            assert "01.06.2025 12:00:00 UTC+02:00" in html  # tooltip
            assert "June 01, 2025" in html  # date separator in Berlin

    def test_date_separator_rolls_with_tz(self):
        """A message at 22:00 UTC falls on next calendar day in Berlin — separator must reflect that."""
        renderer = HtmlRenderer(Path("/tmp"), ExportConfig(timezone="Europe/Berlin"))
        # 2025-06-01 22:00 UTC = 2025-06-02 00:00 Berlin
        msgs = [_msg(1, date=datetime(2025, 6, 1, 22, 0, tzinfo=timezone.utc))]
        groups = renderer._group_messages(msgs)
        sep = [g for g in groups if isinstance(g, dict) and g.get("type") == "date_separator"][0]
        assert sep["date"] == "June 02, 2025"

    def test_format_utc_offset(self):
        from zoneinfo import ZoneInfo
        berlin = ZoneInfo("Europe/Berlin")
        dt = datetime(2025, 6, 1, 12, 0, tzinfo=berlin)  # CEST +02:00
        assert format_utc_offset(dt) == "UTC+02:00"
        dt_utc = datetime(2025, 6, 1, tzinfo=timezone.utc)
        assert format_utc_offset(dt_utc) == "UTC+00:00"
        # Negative offset
        ny = ZoneInfo("America/New_York")
        dt_ny = datetime(2025, 6, 1, tzinfo=ny)  # EDT -04:00
        assert format_utc_offset(dt_ny) == "UTC-04:00"

    def test_html_contains_pagination_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = ExportConfig(output_dir=str(output_dir), msgs_per_page=2)
            renderer = HtmlRenderer(output_dir, config)
            renderer.copy_static_assets()

            channel = ChannelInfo(id=1, title="Test", message_count=4)
            msgs = [
                _msg(i, date=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc))
                for i in range(4)
            ]
            chat_dir = output_dir / "chats" / "chat_1"
            chat_dir.mkdir(parents=True)
            renderer.render_channel(channel, msgs, chat_dir)

            page1 = (chat_dir / "messages.html").read_text()
            assert "messages2.html" in page1
            assert "Older messages" in page1

            page2 = (chat_dir / "messages2.html").read_text()
            assert "messages.html" in page2
            assert "Newer messages" in page2
