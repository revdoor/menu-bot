"""
메뉴 투표 시스템

주요 기능:
- 메뉴 제안 수집
- 투표 진행 (1-5점 점수 부여)
- 점수 집계 및 결과 계산
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import discord
from discord import app_commands
from discord.ui import Button, Select, View

logger = logging.getLogger(__name__)


@dataclass
class VotingSession:
    """투표 세션 데이터"""
    title: str
    guild_id: int
    channel_id: int
    creator_id: int
    created_at: datetime = field(default_factory=datetime.now)

    # 제안된 메뉴들 {메뉴명: 제안자_id}
    menus: Dict[str, int] = field(default_factory=dict)

    # 투표 데이터 {user_id: {메뉴명: 점수}}
    votes: Dict[int, Dict[str, int]] = field(default_factory=dict)

    # 투표 진행 중인지
    voting_started: bool = False

    # 투표 완료 여부
    voting_closed: bool = False

    def add_menu(self, menu_name: str, proposer_id: int) -> bool:
        """메뉴 제안 추가"""
        if self.voting_started:
            return False
        if menu_name in self.menus:
            return False
        self.menus[menu_name] = proposer_id
        return True

    def remove_menu(self, menu_name: str, user_id: int) -> bool:
        """메뉴 제안 삭제 (제안자만 가능)"""
        if self.voting_started:
            return False
        if menu_name not in self.menus:
            return False
        if self.menus[menu_name] != user_id:
            return False
        del self.menus[menu_name]
        return True

    def submit_vote(self, user_id: int, votes: Dict[str, int]) -> bool:
        """투표 제출"""
        if not self.voting_started or self.voting_closed:
            return False
        self.votes[user_id] = votes
        return True

    def calculate_results(self) -> List[Tuple[str, int, int]]:
        """
        투표 결과 계산

        Returns:
            List of (메뉴명, 총점, 최소점) 튜플을 점수 순으로 정렬
        """
        menu_scores = {}
        menu_min_scores = {}

        for menu_name in self.menus:
            scores = []
            for user_votes in self.votes.values():
                if menu_name in user_votes:
                    scores.append(user_votes[menu_name])

            if scores:
                menu_scores[menu_name] = sum(scores)
                menu_min_scores[menu_name] = min(scores)
            else:
                menu_scores[menu_name] = 0
                menu_min_scores[menu_name] = 0

        # 총점 내림차순, 동점이면 최소점 내림차순으로 정렬
        results = [
            (menu, menu_scores[menu], menu_min_scores[menu])
            for menu in self.menus
        ]
        results.sort(key=lambda x: (x[1], x[2]), reverse=True)

        return results


class VotingManager:
    """투표 세션 관리"""

    def __init__(self):
        self.sessions: Dict[int, VotingSession] = {}

    def create_session(
        self,
        guild_id: int,
        channel_id: int,
        creator_id: int,
        title: str
    ) -> Optional[VotingSession]:
        """새 투표 세션 생성"""
        if guild_id in self.sessions:
            return None

        session = VotingSession(
            title=title,
            guild_id=guild_id,
            channel_id=channel_id,
            creator_id=creator_id
        )
        self.sessions[guild_id] = session
        return session

    def get_session(self, guild_id: int) -> Optional[VotingSession]:
        """투표 세션 가져오기"""
        return self.sessions.get(guild_id)

    def close_session(self, guild_id: int) -> bool:
        """투표 세션 종료"""
        if guild_id in self.sessions:
            del self.sessions[guild_id]
            return True
        return False


# UI 컴포넌트들

class MenuProposalView(View):
    """메뉴 제안 단계의 뷰"""

    def __init__(self, session: VotingSession, manager: VotingManager):
        super().__init__(timeout=None)
        self.session = session
        self.manager = manager

    @discord.ui.button(label="제안 마감 및 투표 시작", style=discord.ButtonStyle.primary, custom_id="close_proposals")
    async def close_proposals(self, interaction: discord.Interaction, button: Button):
        """제안 마감 버튼"""
        # 세션 생성자만 마감 가능
        if interaction.user.id != self.session.creator_id:
            await interaction.response.send_message(
                "❌ 투표를 시작한 사람만 제안을 마감할 수 있습니다!",
                ephemeral=True
            )
            return

        # 최소 2개 이상의 메뉴 필요
        if len(self.session.menus) < 2:
            await interaction.response.send_message(
                "❌ 최소 2개 이상의 메뉴가 필요합니다!",
                ephemeral=True
            )
            return

        self.session.voting_started = True

        # 버튼 비활성화
        button.disabled = True
        button.label = "제안 마감됨"
        button.style = discord.ButtonStyle.secondary

        # 투표 뷰로 변경
        new_view = VotingView(self.session, self.manager)

        # 메시지 업데이트
        embed = create_voting_embed(self.session)
        await interaction.response.edit_message(embed=embed, view=new_view)

        logger.info(f"투표 시작: {self.session.title} ({len(self.session.menus)}개 메뉴)")

    @discord.ui.button(label="투표 취소", style=discord.ButtonStyle.danger, custom_id="cancel_voting")
    async def cancel_voting(self, interaction: discord.Interaction, button: Button):
        """투표 취소 버튼"""
        if interaction.user.id != self.session.creator_id:
            await interaction.response.send_message(
                "❌ 투표를 시작한 사람만 취소할 수 있습니다!",
                ephemeral=True
            )
            return

        self.manager.close_session(self.session.guild_id)

        embed = discord.Embed(
            title="❌ 투표 취소됨",
            description=f"**{self.session.title}** 투표가 취소되었습니다.",
            color=discord.Color.red()
        )

        await interaction.response.edit_message(embed=embed, view=None)
        logger.info(f"투표 취소: {self.session.title}")


class VotingView(View):
    """투표 진행 단계의 뷰"""

    def __init__(self, session: VotingSession, manager: VotingManager):
        super().__init__(timeout=None)
        self.session = session
        self.manager = manager

    @discord.ui.button(label="투표하기", style=discord.ButtonStyle.success, custom_id="start_vote")
    async def start_vote(self, interaction: discord.Interaction, button: Button):
        """투표하기 버튼"""
        if self.session.voting_closed:
            await interaction.response.send_message(
                "❌ 이미 종료된 투표입니다!",
                ephemeral=True
            )
            return

        # 이미 투표한 경우 기존 투표 내역 복원
        if interaction.user.id in self.session.votes:
            existing_votes = self.session.votes[interaction.user.id]
            form_view = VotingFormView(
                self.session,
                self.manager,
                interaction.user.id,
                existing_votes
            )

            # 기존 투표 내역 텍스트
            vote_text = "\n".join([f"✓ {m}: {s}점" for m, s in existing_votes.items()])

            await interaction.response.send_message(
                f"📊 **{self.session.title}** 투표\n\n"
                f"**기존 투표 내역:**\n{vote_text}\n\n"
                f"ℹ️ 다시 투표하시면 이전 투표가 덮어씌워집니다.\n"
                f"투표를 수정하려면 아래에서 메뉴를 선택하세요.",
                ephemeral=True,
                view=form_view
            )
            return

        # 처음 투표하는 경우
        form_view = VotingFormView(self.session, self.manager, interaction.user.id)
        await interaction.response.send_message(
            f"📊 **{self.session.title}** 투표\n각 메뉴에 점수를 부여해주세요 (1점=최저, 5점=최고)",
            ephemeral=True,
            view=form_view
        )

    @discord.ui.button(label="투표 종료 및 결과 보기", style=discord.ButtonStyle.danger, custom_id="close_vote")
    async def close_vote(self, interaction: discord.Interaction, button: Button):
        """투표 종료 버튼"""
        if interaction.user.id != self.session.creator_id:
            await interaction.response.send_message(
                "❌ 투표를 시작한 사람만 종료할 수 있습니다!",
                ephemeral=True
            )
            return

        if len(self.session.votes) == 0:
            await interaction.response.send_message(
                "❌ 아직 투표한 사람이 없습니다!",
                ephemeral=True
            )
            return

        self.session.voting_closed = True

        # 결과 계산
        results = self.session.calculate_results()

        # 결과 Embed 생성
        embed = create_results_embed(self.session, results)

        await interaction.response.edit_message(embed=embed, view=None)

        # 세션 종료
        self.manager.close_session(self.session.guild_id)

        logger.info(f"투표 종료: {self.session.title} (참여자 {len(self.session.votes)}명)")


class VotingFormView(View):
    """투표 폼 뷰 (2단계 방식: 메뉴 선택 -> 점수 선택)"""

    def __init__(
        self,
        session: VotingSession,
        manager: VotingManager,
        user_id: int,
        existing_votes: Optional[Dict[str, int]] = None
    ):
        super().__init__(timeout=300)  # 5분 타임아웃
        self.session = session
        self.manager = manager
        self.user_id = user_id
        self.user_votes: Dict[str, int] = existing_votes.copy() if existing_votes else {}

        # 메뉴 선택 Select 추가
        self._add_menu_select()

        # 투표 완료 버튼
        self._add_submit_button()

    def _add_menu_select(self):
        """메뉴 선택 Select 추가"""
        menu_list = list(self.session.menus.keys())

        # 아직 투표하지 않은 메뉴들
        remaining_menus = [m for m in menu_list if m not in self.user_votes]

        if not remaining_menus:
            return

        # Select 옵션 생성 (최대 25개)
        options = []
        for menu in remaining_menus[:25]:
            options.append(
                discord.SelectOption(
                    label=menu,
                    value=menu,
                    description=f"{menu}에 점수를 부여하세요"
                )
            )

        select = Select(
            placeholder="점수를 부여할 메뉴를 선택하세요",
            options=options,
            custom_id="select_menu",
            row=0
        )

        async def callback(interaction: discord.Interaction):
            selected_menu = select.values[0]

            # 점수 선택 뷰로 전환
            score_view = ScoreSelectView(
                self.session,
                self.manager,
                self.user_id,
                selected_menu,
                self.user_votes
            )

            await interaction.response.edit_message(
                content=f"📊 **{self.session.title}**\n\n"
                        f"**{selected_menu}**에 대한 점수를 선택하세요:",
                view=score_view
            )

        select.callback = callback
        self.add_item(select)

    def _add_submit_button(self):
        """투표 완료 버튼 추가"""
        button = Button(
            label=f"투표 완료 ({len(self.user_votes)}/{len(self.session.menus)})",
            style=discord.ButtonStyle.success,
            custom_id="submit_vote",
            row=1,
            disabled=(len(self.user_votes) < len(self.session.menus))
        )

        async def callback(interaction: discord.Interaction):
            # 모든 메뉴에 투표했는지 확인
            if len(self.user_votes) < len(self.session.menus):
                await interaction.response.send_message(
                    f"❌ 모든 메뉴에 점수를 부여해주세요! (현재: {len(self.user_votes)}/{len(self.session.menus)})",
                    ephemeral=True
                )
                return

            # 투표 제출
            self.session.submit_vote(self.user_id, self.user_votes)

            # 투표 내역 텍스트 생성
            vote_text = "\n".join([f"• {menu}: {score}점" for menu, score in self.user_votes.items()])

            await interaction.response.edit_message(
                content=f"✅ **투표가 완료되었습니다!**\n\n{vote_text}",
                view=None
            )
            logger.info(f"투표 제출: user_id={self.user_id} - {len(self.user_votes)}개 메뉴")

        button.callback = callback
        self.add_item(button)


class ScoreSelectView(View):
    """점수 선택 뷰"""

    def __init__(
        self,
        session: VotingSession,
        manager: VotingManager,
        user_id: int,
        menu_name: str,
        current_votes: Dict[str, int]
    ):
        super().__init__(timeout=300)
        self.session = session
        self.manager = manager
        self.user_id = user_id
        self.menu_name = menu_name
        self.current_votes = current_votes

        # 점수 선택 Select 추가
        self._add_score_select()

    def _add_score_select(self):
        """점수 선택 Select 추가"""
        options = [
            discord.SelectOption(label="1점 - 매우 별로", value="1", emoji="1️⃣"),
            discord.SelectOption(label="2점 - 별로", value="2", emoji="2️⃣"),
            discord.SelectOption(label="3점 - 보통", value="3", emoji="3️⃣"),
            discord.SelectOption(label="4점 - 좋음", value="4", emoji="4️⃣"),
            discord.SelectOption(label="5점 - 매우 좋음", value="5", emoji="5️⃣"),
        ]

        select = Select(
            placeholder=f"{self.menu_name} - 점수를 선택하세요",
            options=options,
            custom_id="select_score",
            row=0
        )

        async def callback(interaction: discord.Interaction):
            score = int(select.values[0])
            self.current_votes[self.menu_name] = score

            # 다시 메뉴 선택 뷰로 돌아가기
            menu_view = VotingFormView(
                self.session,
                self.manager,
                self.user_id,
                self.current_votes
            )

            # 진행 상황 텍스트
            voted_text = "\n".join([f"✓ {m}: {s}점" for m, s in self.current_votes.items()])
            remaining = len(self.session.menus) - len(self.current_votes)

            await interaction.response.edit_message(
                content=f"📊 **{self.session.title}** 투표\n\n"
                        f"**투표 완료한 메뉴:**\n{voted_text}\n\n"
                        f"남은 메뉴: **{remaining}개**\n"
                        f"{'모든 메뉴에 점수를 부여했습니다! 아래 버튼을 눌러 투표를 완료하세요.' if remaining == 0 else '계속해서 다른 메뉴를 선택하세요.'}",
                view=menu_view
            )

        select.callback = callback
        self.add_item(select)


# Embed 생성 함수들

def create_proposal_embed(session: VotingSession) -> discord.Embed:
    """메뉴 제안 단계 Embed"""
    embed = discord.Embed(
        title=f"📝 {session.title}",
        description="메뉴를 제안해주세요! `/메뉴제안 <메뉴명>` 명령어를 사용하세요.",
        color=discord.Color.blue()
    )

    if session.menus:
        menu_list = "\n".join([f"• {menu}" for menu in session.menus.keys()])
        embed.add_field(
            name=f"제안된 메뉴 ({len(session.menus)}개)",
            value=menu_list,
            inline=False
        )
    else:
        embed.add_field(
            name="제안된 메뉴",
            value="아직 제안된 메뉴가 없습니다.",
            inline=False
        )

    embed.set_footer(text="최소 2개 이상의 메뉴가 필요합니다.")

    return embed


def create_voting_embed(session: VotingSession) -> discord.Embed:
    """투표 진행 단계 Embed"""
    embed = discord.Embed(
        title=f"🗳️ {session.title}",
        description="아래 '투표하기' 버튼을 눌러 투표에 참여하세요!",
        color=discord.Color.green()
    )

    menu_list = "\n".join([f"• {menu}" for menu in session.menus.keys()])
    embed.add_field(
        name=f"메뉴 목록 ({len(session.menus)}개)",
        value=menu_list,
        inline=False
    )

    embed.add_field(
        name="투표 현황",
        value=f"{len(session.votes)}명 투표 완료",
        inline=True
    )

    embed.set_footer(text="각 메뉴에 1-5점을 부여해주세요")

    return embed


def create_results_embed(
    session: VotingSession,
    results: List[Tuple[str, int, int]]
) -> discord.Embed:
    """투표 결과 Embed"""
    embed = discord.Embed(
        title=f"🏆 {session.title} - 결과",
        description=f"총 {len(session.votes)}명이 투표에 참여했습니다.",
        color=discord.Color.gold()
    )

    if not results:
        embed.add_field(
            name="결과",
            value="투표 결과가 없습니다.",
            inline=False
        )
        return embed

    # 1위 메뉴
    winner_score = results[0][1]
    winner_min_score = results[0][2]
    winners = [r for r in results if r[1] == winner_score and r[2] == winner_min_score]

    if len(winners) == 1:
        winner_text = f"# 🥇 {winners[0][0]}\n**총점: {winners[0][1]}점** (최소점: {winners[0][2]}점)"
    else:
        winner_names = ", ".join([w[0] for w in winners])
        winner_text = f"# 🥇 {winner_names}\n**총점: {winner_score}점** (최소점: {winner_min_score}점)\n_(동점)_"

    embed.add_field(
        name="🎯 최종 선택",
        value=winner_text,
        inline=False
    )

    # 전체 순위
    ranking_text = ""
    for idx, (menu, total, min_score) in enumerate(results, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, "  ")
        ranking_text += f"{medal} {idx}위. **{menu}** - {total}점 (최소: {min_score}점)\n"

    embed.add_field(
        name="📊 전체 순위",
        value=ranking_text,
        inline=False
    )

    # 상세 투표 내역
    detailed_votes = []
    for menu, _, _ in results[:3]:  # 상위 3개만 표시
        scores = []
        for user_votes in session.votes.values():
            if menu in user_votes:
                scores.append(user_votes[menu])

        if scores:
            score_dist = ", ".join([str(s) for s in sorted(scores, reverse=True)])
            detailed_votes.append(f"**{menu}**: {score_dist}")

    if detailed_votes:
        embed.add_field(
            name="📈 상위 메뉴 점수 분포",
            value="\n".join(detailed_votes),
            inline=False
        )

    embed.set_footer(text=f"투표 기간: {session.created_at.strftime('%Y-%m-%d %H:%M')}")

    return embed
