"""
같이먹자 기능 - 같이 먹을 사람 모집 시스템

주요 클래스:
- EatTogetherSession: 모집 세션 데이터 관리
- EatTogetherManager: 여러 세션 관리
- EatTogetherView: 참여/출발 버튼 UI
"""
import logging
from typing import Dict, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

import discord
from discord.ui import Button, View

logger = logging.getLogger(__name__)


@dataclass
class EatTogetherSession:
    """같이먹자 세션 데이터"""
    food_name: str  # 먹을 음식 이름
    guild_id: int
    channel_id: int
    creator_id: int
    message_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)

    # 참여자 목록 {user_id}
    participants: Set[int] = field(default_factory=set)

    # 출발 여부
    departed: bool = False

    def __post_init__(self):
        """초기화 후 생성자는 자동으로 참여자에 추가"""
        self.participants.add(self.creator_id)

    def add_participant(self, user_id: int) -> bool:
        """
        참여자 추가

        Args:
            user_id: 사용자 ID

        Returns:
            성공 여부 (이미 출발했으면 False)
        """
        if self.departed:
            return False
        self.participants.add(user_id)
        return True

    def remove_participant(self, user_id: int) -> bool:
        """
        참여자 제거 (생성자는 제거 불가)

        Args:
            user_id: 사용자 ID

        Returns:
            성공 여부 (생성자이거나 출발했으면 False)
        """
        if self.departed or user_id == self.creator_id:
            return False
        if user_id in self.participants:
            self.participants.remove(user_id)
            return True
        return False

    def can_depart(self, user_id: int) -> bool:
        """
        출발 가능 여부 확인 (생성자만 가능)

        Args:
            user_id: 사용자 ID

        Returns:
            출발 가능 여부
        """
        return user_id == self.creator_id and not self.departed

    def mark_departed(self) -> bool:
        """
        출발 처리

        Returns:
            성공 여부 (이미 출발했으면 False)
        """
        if self.departed:
            return False
        self.departed = True
        return True


class EatTogetherManager:
    """같이먹자 세션 관리자"""

    def __init__(self):
        # {(guild_id, session_id): EatTogetherSession}
        # session_id는 같은 guild에서 여러 세션을 동시에 열 수 있도록 함
        self.sessions: Dict[tuple[int, int], EatTogetherSession] = {}
        self._next_session_id: Dict[int, int] = {}  # {guild_id: next_id}

    def create_session(
        self,
        guild_id: int,
        channel_id: int,
        creator_id: int,
        food_name: str
    ) -> tuple[int, EatTogetherSession]:
        """
        새 같이먹자 세션 생성

        Args:
            guild_id: 길드 ID
            channel_id: 채널 ID
            creator_id: 생성자 사용자 ID
            food_name: 먹을 음식 이름

        Returns:
            (session_id, 생성된 세션) 튜플
        """
        # 다음 세션 ID 생성
        if guild_id not in self._next_session_id:
            self._next_session_id[guild_id] = 0

        session_id = self._next_session_id[guild_id]
        self._next_session_id[guild_id] += 1

        session = EatTogetherSession(
            food_name=food_name,
            guild_id=guild_id,
            channel_id=channel_id,
            creator_id=creator_id
        )

        self.sessions[(guild_id, session_id)] = session
        return session_id, session

    def get_session(self, guild_id: int, session_id: int) -> Optional[EatTogetherSession]:
        """
        세션 가져오기

        Args:
            guild_id: 길드 ID
            session_id: 세션 ID

        Returns:
            세션 (없으면 None)
        """
        return self.sessions.get((guild_id, session_id))

    def close_session(self, guild_id: int, session_id: int) -> bool:
        """
        세션 종료

        Args:
            guild_id: 길드 ID
            session_id: 세션 ID

        Returns:
            성공 여부 (세션이 없으면 False)
        """
        key = (guild_id, session_id)
        if key in self.sessions:
            del self.sessions[key]
            return True
        return False

    def get_active_sessions(self, guild_id: int) -> list[tuple[int, EatTogetherSession]]:
        """
        해당 길드의 활성 세션 목록 가져오기

        Args:
            guild_id: 길드 ID

        Returns:
            [(session_id, session), ...] 리스트
        """
        return [
            (sid, session)
            for (gid, sid), session in self.sessions.items()
            if gid == guild_id
        ]


def create_eat_together_embed(session: EatTogetherSession, guild: discord.Guild) -> discord.Embed:
    """
    같이먹자 Embed 생성

    Args:
        session: 같이먹자 세션
        guild: Discord 길드

    Returns:
        Discord Embed
    """
    if session.departed:
        embed = discord.Embed(
            title=f"🚀 {session.food_name} 출발!",
            description=f"**{session.food_name}** 먹으러 출발했습니다!",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title=f"🍽️ 같이 {session.food_name} 먹을 사람?",
            description=f"**{session.food_name}** 같이 먹을 사람을 모집합니다!",
            color=discord.Color.blue()
        )

    # 참여자 목록 생성
    participant_mentions = []
    for user_id in session.participants:
        member = guild.get_member(user_id)
        if member:
            participant_mentions.append(member.mention)
        else:
            participant_mentions.append(f"<@{user_id}>")

    participants_text = "\n".join(participant_mentions) if participant_mentions else "없음"

    embed.add_field(
        name=f"👥 참여자 ({len(session.participants)}명)",
        value=participants_text,
        inline=False
    )

    if not session.departed:
        embed.set_footer(text="'참여!' 버튼을 눌러 참여하세요. 생성자는 '출발!' 버튼으로 출발할 수 있습니다.")

    return embed


class EatTogetherView(View):
    """같이먹자 버튼 뷰"""

    def __init__(self, session_id: int, session: EatTogetherSession, manager: EatTogetherManager):
        super().__init__(timeout=None)
        self.session_id = session_id
        self.session = session
        self.manager = manager

        # 출발했으면 버튼 비활성화
        if session.departed:
            self.join_button.disabled = True
            self.depart_button.disabled = True

    @discord.ui.button(
        label="참여!",
        style=discord.ButtonStyle.success,
        custom_id="eat_together_join_btn",
        emoji="✋"
    )
    async def join_button(self, interaction: discord.Interaction, button: Button):
        """참여 버튼"""
        # 세션 존재 확인
        session = self.manager.get_session(self.session.guild_id, self.session_id)
        if not session:
            await interaction.response.send_message(
                "❌ 세션이 만료되었습니다.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        # 이미 참여 중인지 확인
        if user_id in session.participants:
            # 참여 취소 처리
            if session.remove_participant(user_id):
                await interaction.response.send_message(
                    f"👋 **{session.food_name}** 모임에서 나갔습니다.",
                    ephemeral=True
                )
                logger.info(f"{interaction.user.name}님이 '{session.food_name}' 모임에서 나감")
            else:
                await interaction.response.send_message(
                    "❌ 생성자는 모임에서 나갈 수 없습니다!",
                    ephemeral=True
                )
                return
        else:
            # 참여 처리
            if session.add_participant(user_id):
                await interaction.response.send_message(
                    f"✅ **{session.food_name}** 모임에 참여했습니다!",
                    ephemeral=True
                )
                logger.info(f"{interaction.user.name}님이 '{session.food_name}' 모임에 참여")
            else:
                await interaction.response.send_message(
                    "❌ 이미 출발한 모임입니다!",
                    ephemeral=True
                )
                return

        # Embed 업데이트
        updated_embed = create_eat_together_embed(session, interaction.guild)
        await interaction.message.edit(embed=updated_embed)

    @discord.ui.button(
        label="출발!",
        style=discord.ButtonStyle.primary,
        custom_id="eat_together_depart_btn",
        emoji="🚀"
    )
    async def depart_button(self, interaction: discord.Interaction, button: Button):
        """출발 버튼"""
        # 세션 존재 확인
        session = self.manager.get_session(self.session.guild_id, self.session_id)
        if not session:
            await interaction.response.send_message(
                "❌ 세션이 만료되었습니다.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        # 생성자 확인
        if not session.can_depart(user_id):
            if user_id != session.creator_id:
                await interaction.response.send_message(
                    "❌ 모임을 시작한 사람만 출발할 수 있습니다!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ 이미 출발했습니다!",
                    ephemeral=True
                )
            return

        # 출발 처리
        session.mark_departed()

        # Embed 업데이트 및 버튼 비활성화
        updated_embed = create_eat_together_embed(session, interaction.guild)

        # 버튼 비활성화
        self.join_button.disabled = True
        self.depart_button.disabled = True

        await interaction.response.edit_message(embed=updated_embed, view=self)

        # 참여자들에게 멘션
        participant_mentions = " ".join([f"<@{uid}>" for uid in session.participants])
        await interaction.followup.send(
            f"🚀 **{session.food_name}** 먹으러 출발! {participant_mentions}"
        )

        logger.info(f"'{session.food_name}' 모임 출발 (참여자: {len(session.participants)}명)")
