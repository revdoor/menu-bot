"""sticker_stats.py 테스트"""
import pytest
from unittest.mock import MagicMock, AsyncMock
import discord

from sticker_stats import parse_channels, _extract_channel_id, StickerAnalyzer, create_sticker_embed, _format_sticker_ranking


@pytest.mark.unit
class TestChannelParsing:
    """채널 파싱 함수 테스트"""

    def test_parse_channels_none_returns_current(self, mock_guild, mock_channel):
        assert parse_channels(None, mock_guild, mock_channel) == [mock_channel]

    def test_parse_channels_empty_string_returns_current(self, mock_guild, mock_channel):
        assert parse_channels("", mock_guild, mock_channel) == [mock_channel]

    def test_parse_channels_with_mention_format(self, mock_guild):
        mock_channel = MagicMock()
        mock_channel.id = 123456789
        mock_guild.get_channel.return_value = mock_channel

        result = parse_channels("<#123456789>", mock_guild, MagicMock())
        assert result == [mock_channel]
        mock_guild.get_channel.assert_called_once_with(123456789)

    def test_parse_channels_with_direct_id(self, mock_guild):
        mock_channel = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        assert parse_channels("123456789", mock_guild, MagicMock()) == [mock_channel]

    def test_parse_channels_multiple_comma_separated(self, mock_guild):
        ch1, ch2 = MagicMock(), MagicMock()
        mock_guild.get_channel.side_effect = lambda cid: ch1 if cid == 111 else ch2 if cid == 222 else None

        result = parse_channels("111, 222", mock_guild, MagicMock())
        assert len(result) == 2 and ch1 in result and ch2 in result

    def test_parse_channels_invalid_format_raises_error(self, mock_guild, mock_channel):
        with pytest.raises(ValueError, match="올바르지 않은 채널 형식"):
            parse_channels("invalid_format", mock_guild, mock_channel)

    def test_parse_channels_not_found_raises_error(self, mock_guild, mock_channel):
        mock_guild.get_channel.return_value = None
        with pytest.raises(ValueError, match="채널을 찾을 수 없습니다"):
            parse_channels("999999999", mock_guild, mock_channel)


@pytest.mark.unit
class TestExtractChannelId:
    """채널 ID 추출 함수 테스트"""

    def test_extract_from_mention(self):
        assert _extract_channel_id("<#123456789>") == "123456789"

    def test_extract_from_direct_id(self):
        assert _extract_channel_id("987654321") == "987654321"

    def test_extract_invalid_format(self):
        with pytest.raises(ValueError):
            _extract_channel_id("abc123")
        with pytest.raises(ValueError):
            _extract_channel_id("#channel-name")


@pytest.mark.unit
class TestStickerAnalyzer:
    """StickerAnalyzer 클래스 테스트"""

    @pytest.fixture
    def analyzer(self, mock_guild):
        return StickerAnalyzer(mock_guild)

    @pytest.mark.asyncio
    async def test_analyzer_initialization(self, analyzer, mock_guild):
        assert analyzer.guild == mock_guild and analyzer.guild_sticker_ids == set()

    @pytest.mark.asyncio
    async def test_initialize_fetches_stickers(self, analyzer, mock_guild, mock_sticker):
        mock_sticker.id = 111
        mock_guild.fetch_stickers = AsyncMock(return_value=[mock_sticker])
        await analyzer.initialize()
        assert 111 in analyzer.guild_sticker_ids
        mock_guild.fetch_stickers.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_stats_counts_stickers(self, analyzer, mock_channel, mock_sticker):
        """스티커 통계 수집"""
        analyzer.guild_sticker_ids = {mock_sticker.id}
        msg1, msg2 = MagicMock(), MagicMock()
        msg1.stickers, msg2.stickers = [mock_sticker], []
        mock_channel.history = MagicMock(return_value=AsyncIteratorMock([msg1, msg2]))

        stats = await analyzer.collect_stats([mock_channel], limit=10)
        assert stats['total_messages'] == 2
        assert stats['messages_with_stickers'] == 1
        assert stats['sticker_counts'][mock_sticker.name] == 1

    @pytest.mark.asyncio
    async def test_collect_stats_excludes_nitro_stickers(self, analyzer, mock_channel):
        """Nitro 스티커 제외"""
        analyzer.guild_sticker_ids = {111}
        server_sticker, nitro_sticker = MagicMock(), MagicMock()
        server_sticker.id, server_sticker.name = 111, "server_sticker"
        nitro_sticker.id, nitro_sticker.name = 999, "nitro_sticker"

        msg = MagicMock()
        msg.stickers = [server_sticker, nitro_sticker]
        mock_channel.history = MagicMock(return_value=AsyncIteratorMock([msg]))

        stats = await analyzer.collect_stats([mock_channel], limit=10)
        assert "server_sticker" in stats['sticker_counts']
        assert "nitro_sticker" not in stats['sticker_counts']

    @pytest.mark.asyncio
    async def test_collect_stats_permission_error(self, analyzer, mock_channel):
        """권한 없을 때 PermissionError"""
        class AsyncIterError:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise discord.Forbidden(MagicMock(), "No permission")

        mock_channel.history = MagicMock(return_value=AsyncIterError())
        with pytest.raises(PermissionError, match="권한이 없습니다"):
            await analyzer.collect_stats([mock_channel], limit=10)


@pytest.mark.unit
class TestEmbedFormatting:
    """Embed 포맷팅 함수 테스트"""

    def test_create_sticker_embed_basic(self, mock_channel, sample_sticker_stats):
        embed = create_sticker_embed([mock_channel], sample_sticker_stats, 100, "TestUser")
        assert embed.title == "📊 스티커 사용 통계" and "TestUser" in embed.footer.text

    def test_create_sticker_embed_empty_stats(self, mock_channel):
        empty_stats = {'sticker_counts': {}, 'total_messages': 50, 'messages_with_stickers': 0}
        embed = create_sticker_embed([mock_channel], empty_stats, 50, "TestUser")
        assert "발견되지 않았습니다" in embed.description

    def test_format_sticker_ranking(self):
        sorted_stickers = [("sticker1", 10), ("sticker2", 5), ("sticker3", 2)]
        result = _format_sticker_ranking(sorted_stickers, {"sticker1": 10, "sticker2": 5, "sticker3": 2})
        assert all(x in result for x in ["sticker1", "10회", "█"])

    def test_format_sticker_ranking_empty(self):
        assert _format_sticker_ranking([], {}) == ""


# ==================== 테스트 헬퍼 ====================

class AsyncIteratorMock:
    """비동기 이터레이터 Mock"""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item
