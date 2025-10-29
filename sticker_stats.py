"""
Discord 스티커 사용 통계 분석 모듈

주요 기능:
- 채널 파싱 및 검증
- 스티커 사용 통계 수집
- Discord Embed 포맷팅
"""
from typing import Dict, List, Optional, Any
import discord

from config import DISCORD_EMBED_MAX_FIELDS


class ChannelParser:
    """채널 멘션 파싱 담당 클래스"""

    @staticmethod
    def parse_channels(
        채널들: Optional[str],
        guild: discord.Guild,
        current_channel: discord.TextChannel
    ) -> List[discord.TextChannel]:
        """
        채널 문자열을 파싱하여 채널 리스트 반환

        Args:
            채널들: 쉼표로 구분된 채널 멘션 또는 ID
            guild: Discord 길드
            current_channel: 현재 채널 (기본값)

        Returns:
            파싱된 채널 리스트

        Raises:
            ValueError: 잘못된 채널 형식이거나 채널을 찾을 수 없을 때
        """
        if not 채널들:
            return [current_channel]

        channels = []
        channel_mentions = [ch.strip() for ch in 채널들.split(',') if ch.strip()]

        for mention in channel_mentions:
            channel_id = ChannelParser._extract_channel_id(mention)

            channel = guild.get_channel(int(channel_id))
            if not channel:
                raise ValueError(f"채널을 찾을 수 없습니다: {mention}")

            channels.append(channel)

        return channels

    @staticmethod
    def _extract_channel_id(mention: str) -> str:
        """채널 멘션에서 ID 추출"""
        # <#123456789> 형태
        if mention.startswith('<#') and mention.endswith('>'):
            return mention[2:-1]
        # 숫자만 있는 경우 (ID 직접 입력)
        elif mention.isdigit():
            return mention
        else:
            raise ValueError(f"올바르지 않은 채널 형식: {mention}")


class StickerAnalyzer:
    """스티커 사용 통계 분석 담당 클래스"""

    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.guild_sticker_ids: set = set()

    async def initialize(self) -> None:
        """서버 스티커 목록 초기화"""
        guild_stickers = await self.guild.fetch_stickers()
        self.guild_sticker_ids = {sticker.id for sticker in guild_stickers}
        print(f"서버 스티커 수: {len(self.guild_sticker_ids)}개")

    async def collect_stats(
        self,
        channels: List[discord.TextChannel],
        limit: int
    ) -> Dict[str, Any]:
        """
        채널들에서 스티커 사용 통계 수집

        Args:
            channels: 분석할 채널 리스트
            limit: 각 채널당 확인할 최대 메시지 수

        Returns:
            {
                'sticker_counts': {스티커명: 사용횟수},
                'total_messages': 전체 메시지 수,
                'messages_with_stickers': 스티커 포함 메시지 수
            }

        Raises:
            PermissionError: 채널 읽기 권한이 없을 때
        """
        sticker_counts = {}
        total_messages = 0
        messages_with_stickers = 0

        for channel in channels:
            try:
                async for message in channel.history(limit=limit):
                    total_messages += 1

                    if message.stickers:
                        for sticker in message.stickers:
                            # 서버 스티커만 포함 (Nitro 스티커 제외)
                            if sticker.id in self.guild_sticker_ids:
                                messages_with_stickers += 1
                                sticker_name = sticker.name
                                sticker_counts[sticker_name] = sticker_counts.get(sticker_name, 0) + 1

            except discord.Forbidden:
                raise PermissionError(f"{channel.mention} 채널을 읽을 권한이 없습니다.")
            except Exception as e:
                print(f"채널 {channel.name} 읽기 중 에러: {e}")

        return {
            'sticker_counts': sticker_counts,
            'total_messages': total_messages,
            'messages_with_stickers': messages_with_stickers
        }


class StickerStatsFormatter:
    """스티커 통계를 Discord Embed로 포맷팅하는 클래스"""

    @staticmethod
    def create_embed(
        channels: List[discord.TextChannel],
        stats: Dict[str, Any],
        limit: int,
        requester_name: str
    ) -> discord.Embed:
        """
        스티커 통계 Embed 생성

        Args:
            channels: 분석한 채널 리스트
            stats: collect_stats에서 반환된 통계 데이터
            limit: 각 채널당 확인한 메시지 수
            requester_name: 요청자 이름

        Returns:
            Discord Embed 객체
        """
        channel_list = ", ".join([ch.mention for ch in channels])
        sticker_counts = stats['sticker_counts']
        total_messages = stats['total_messages']
        messages_with_stickers = stats['messages_with_stickers']

        embed = discord.Embed(
            title="📊 스티커 사용 통계",
            description=f"**분석 채널**: {channel_list}\n**메시지 수**: {total_messages}개 (채널당 최대 {limit}개)",
            color=discord.Color.blue()
        )

        # 스티커가 없는 경우
        if not sticker_counts:
            embed.description = f"{channel_list}\n최근 {total_messages}개 메시지에서 서버 스티커가 발견되지 않았습니다."
            return embed

        # 통계 요약
        embed.add_field(
            name="📈 요약",
            value=f"스티커가 포함된 메시지: {messages_with_stickers}개\n서로 다른 스티커 종류: {len(sticker_counts)}개",
            inline=False
        )

        # 스티커 순위
        sorted_stickers = sorted(sticker_counts.items(), key=lambda x: x[1], reverse=True)
        sticker_list_text = StickerStatsFormatter._format_ranking(sorted_stickers, sticker_counts)

        embed.add_field(
            name="🏆 스티커 순위",
            value=sticker_list_text if sticker_list_text else "스티커 없음",
            inline=False
        )

        # 나머지 스티커 표시
        if len(sorted_stickers) > DISCORD_EMBED_MAX_FIELDS:
            embed.add_field(
                name="ℹ️ 기타",
                value=f"그 외 {len(sorted_stickers) - DISCORD_EMBED_MAX_FIELDS}개의 스티커가 더 있습니다.",
                inline=False
            )

        embed.set_footer(text=f"요청자: {requester_name} | 서버 스티커만 포함")

        return embed

    @staticmethod
    def _format_ranking(sorted_stickers: List[tuple], sticker_counts: Dict[str, int]) -> str:
        """스티커 순위를 텍스트로 포맷팅"""
        if not sticker_counts:
            return ""

        max_count = max(sticker_counts.values())
        sticker_list_text = ""

        for idx, (sticker_name, count) in enumerate(sorted_stickers[:DISCORD_EMBED_MAX_FIELDS], 1):
            # 막대 그래프 효과
            bar_length = min(int(count / max_count * 10), 10)
            bar = "█" * bar_length
            sticker_list_text += f"`{idx:2d}.` **{sticker_name}**: {count}회 {bar}\n"

        return sticker_list_text
