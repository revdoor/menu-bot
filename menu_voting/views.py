"""
메뉴 투표 시스템 UI 컴포넌트

주요 클래스:
- MenuProposalView: 메뉴 제안 단계 뷰
- VotingView: 투표 진행 단계 뷰
- VotingFormView: 투표 폼 뷰
- ScoreSelectView: 점수 선택 뷰
"""
import logging
from typing import Dict, Optional
from copy import deepcopy

import discord
from discord.ui import Button, Select, View

from .models import VotingSession, VotingManager
from .embeds import create_voting_embed, create_results_embed
from .constants import (
    VOTING_FORM_TIMEOUT,
    MAX_SELECT_OPTIONS,
    MIN_MENU_COUNT,
    MIN_SCORE,
    MAX_SCORE,
    SCORE_LABELS,
    SCORE_EMOJIS,
)

logger = logging.getLogger(__name__)


def _check_session_exists(session: VotingSession, manager: VotingManager) -> bool:
    """
    세션 존재 확인 헬퍼 함수

    Args:
        session: 확인할 세션
        manager: 투표 매니저

    Returns:
        세션이 존재하면 True
    """
    return manager.get_session(session.guild_id) is not None


async def _handle_orphaned_message(interaction: discord.Interaction) -> None:
    """
    고아 메시지 처리 헬퍼 함수

    Args:
        interaction: Discord Interaction
    """
    await interaction.response.send_message(
        "❌ 세션이 만료되었습니다. 이 메시지를 삭제합니다.",
        ephemeral=True
    )
    try:
        await interaction.message.delete()
        logger.info(f"고아 투표 메시지 삭제: message_id={interaction.message.id}")
    except Exception:
        pass


def _log_voting_results(
    title: str,
    regular_results: list[tuple[str, int, int]],
    zero_results: list[tuple[str, int, list[str]]],
    voter_count: int
) -> None:
    """
    투표 결과 로깅

    Args:
        title: 투표 제목
        regular_results: 일반 메뉴 결과
        zero_results: 0점 메뉴 결과
        voter_count: 투표 참여자 수
    """
    logger.info(f"투표 종료: {title} (참여자 {voter_count}명)")

    if regular_results:
        logger.info("=== 투표 결과 ===")
        for idx, (menu, total, min_score) in enumerate(regular_results, 1):
            logger.info(f"{idx}위. {menu} - 총점: {total}점, 최소점: {min_score}점")

    if zero_results:
        logger.info("=== 제외된 메뉴 (0점 포함) ===")
        for menu, total, zero_voters in zero_results:
            voters_str = ", ".join(zero_voters) if zero_voters else "없음"
            logger.info(f"{menu} - 총점: {total}점, 0점 준 사람: {voters_str}")


class MenuProposalView(View):
    """메뉴 제안 단계의 뷰"""

    def __init__(self, session: VotingSession, manager: VotingManager):
        super().__init__(timeout=None)
        self.session = session
        self.manager = manager

    @discord.ui.button(
        label="제안 마감 및 투표 시작",
        style=discord.ButtonStyle.primary,
        custom_id="close_proposals_btn"
    )
    async def close_proposals(self, interaction: discord.Interaction, button: Button):
        """제안 마감 버튼"""
        # 세션 존재 확인
        if not _check_session_exists(self.session, self.manager):
            await _handle_orphaned_message(interaction)
            return

        # 권한 확인
        if interaction.user.id != self.session.creator_id:
            await interaction.response.send_message(
                "❌ 투표를 시작한 사람만 제안을 마감할 수 있습니다!",
                ephemeral=True
            )
            return

        # 최소 메뉴 개수 확인
        if len(self.session.menus) < MIN_MENU_COUNT:
            await interaction.response.send_message(
                f"❌ 최소 {MIN_MENU_COUNT}개 이상의 메뉴가 필요합니다!",
                ephemeral=True
            )
            return

        # 투표 시작
        self.session.voting_started = True

        # 기존 메시지는 "제안 마감됨"으로 변경
        menu_list = "\n".join([f"• {menu}" for menu in self.session.menus.keys()])
        closed_embed = discord.Embed(
            title=f"✅ {self.session.title} - 제안 마감",
            description=f"메뉴 제안이 마감되었습니다.\n투표가 시작되었습니다!",
            color=discord.Color.green()
        )
        closed_embed.add_field(
            name=f"최종 메뉴 목록 ({len(self.session.menus)}개)",
            value=menu_list,
            inline=False
        )

        await interaction.response.edit_message(embed=closed_embed, view=None)

        # 새로운 투표 메시지 전송
        voting_embed = create_voting_embed(self.session, interaction.guild)
        voting_view = VotingView(self.session, self.manager)

        voting_message = await interaction.followup.send(
            embed=voting_embed,
            view=voting_view,
            wait=True
        )

        # 새 메시지 ID 저장
        self.session.message_id = voting_message.id

        logger.info(f"투표 시작: {self.session.title} ({len(self.session.menus)}개 메뉴)")

    @discord.ui.button(
        label="투표 취소",
        style=discord.ButtonStyle.danger,
        custom_id="cancel_voting_btn"
    )
    async def cancel_voting(self, interaction: discord.Interaction, button: Button):
        """투표 취소 버튼"""
        # 세션 존재 확인
        if not _check_session_exists(self.session, self.manager):
            await _handle_orphaned_message(interaction)
            return

        # 권한 확인
        if interaction.user.id != self.session.creator_id:
            await interaction.response.send_message(
                "❌ 투표를 시작한 사람만 취소할 수 있습니다!",
                ephemeral=True
            )
            return

        # 세션 종료
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

    @discord.ui.button(
        label="투표하기",
        style=discord.ButtonStyle.success,
        custom_id="start_vote_btn"
    )
    async def start_vote(self, interaction: discord.Interaction, button: Button):
        """투표하기 버튼"""
        # 세션 존재 확인
        if not _check_session_exists(self.session, self.manager):
            await _handle_orphaned_message(interaction)
            return

        # 투표 종료 확인
        if self.session.voting_closed:
            await interaction.response.send_message(
                "❌ 이미 종료된 투표입니다!",
                ephemeral=True
            )
            return

        # 투표 권한 확인
        if not self.session.is_voter_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ 이 투표는 제한된 투표입니다. 투표 생성자에게 허용을 요청하세요!",
                ephemeral=True
            )
            return

        # 기존 투표 내역이 있는 경우 (수정 모드)
        if interaction.user.id in self.session.votes:
            # Deep copy를 사용하여 기존 투표 내역 복사 (참조 공유 방지)
            existing_votes = deepcopy(self.session.votes[interaction.user.id])
            form_view = VotingFormView(
                self.session,
                self.manager,
                interaction.user.id,
                interaction.user.display_name,
                existing_votes
            )

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

        # 처음 투표하는 경우 (순차 모드)
        menu_list = list(self.session.menus.keys())
        first_menu = menu_list[0]

        sequential_view = SequentialVotingView(
            self.session,
            self.manager,
            interaction.user.id,
            interaction.user.display_name,
            menu_list,
            current_index=0,
            votes={}
        )

        await interaction.response.send_message(
            f"📊 **{self.session.title}** 투표\n\n"
            f"**{first_menu}**에 대한 점수를 선택하세요:\n"
            f"(1/{ len(menu_list)})",
            ephemeral=True,
            view=sequential_view
        )

    @discord.ui.button(
        label="투표 종료 및 결과 보기",
        style=discord.ButtonStyle.danger,
        custom_id="close_vote_btn"
    )
    async def close_vote(self, interaction: discord.Interaction, button: Button):
        """투표 종료 버튼"""
        # 세션 존재 확인
        if not _check_session_exists(self.session, self.manager):
            await _handle_orphaned_message(interaction)
            return

        # 권한 확인
        if interaction.user.id != self.session.creator_id:
            await interaction.response.send_message(
                "❌ 투표를 시작한 사람만 종료할 수 있습니다!",
                ephemeral=True
            )
            return

        # 투표 참여자 확인
        if len(self.session.votes) == 0:
            await interaction.response.send_message(
                "❌ 아직 투표한 사람이 없습니다!",
                ephemeral=True
            )
            return

        # 투표 종료
        self.session.voting_closed = True

        # 기존 메시지는 "투표 종료됨"으로 변경
        closed_embed = discord.Embed(
            title=f"✅ {self.session.title} - 투표 종료",
            description=f"투표가 종료되었습니다.\n총 **{len(self.session.votes)}명**이 참여했습니다.",
            color=discord.Color.gold()
        )

        menu_list = "\n".join([f"• {menu}" for menu in self.session.menus.keys()])
        closed_embed.add_field(
            name=f"메뉴 목록 ({len(self.session.menus)}개)",
            value=menu_list,
            inline=False
        )

        await interaction.response.edit_message(embed=closed_embed, view=None)

        # 결과 계산
        regular_results, zero_results = self.session.calculate_results()

        # 새로운 결과 메시지 전송 (랜덤 선택 버튼 포함)
        results_embed = create_results_embed(self.session, regular_results, zero_results)

        # 1위 메뉴가 여러 개인 경우에만 랜덤 선택/재투표 버튼 표시
        results_view = None
        if regular_results:
            winner_score = regular_results[0][1]
            winner_min_score = regular_results[0][2]
            winners = [r for r in regular_results if r[1] == winner_score and r[2] == winner_min_score]
            if len(winners) > 1:
                results_view = ResultsView(regular_results, self.session, self.manager)

        # 참여자 멘션 생성
        voter_mentions = " ".join([f"<@{user_id}>" for user_id in self.session.votes.keys()])
        mention_message = f"🏆 **투표 결과 발표!** {voter_mentions}"

        if results_view:
            await interaction.followup.send(content=mention_message, embed=results_embed, view=results_view)
        else:
            await interaction.followup.send(content=mention_message, embed=results_embed)

        # 결과 로깅
        _log_voting_results(self.session.title, regular_results, zero_results, len(self.session.votes))

        # 세션 정리
        self.manager.close_session(self.session.guild_id)

        logger.info(f"투표 종료: {self.session.title} (참여자 {len(self.session.votes)}명)")


class SequentialVotingView(View):
    """순차 투표 뷰 (처음 투표할 때 사용)"""

    def __init__(
        self,
        session: VotingSession,
        manager: VotingManager,
        user_id: int,
        username: str,
        menu_list: list[str],
        current_index: int,
        votes: Dict[str, int]
    ):
        super().__init__(timeout=VOTING_FORM_TIMEOUT)
        self.session = session
        self.manager = manager
        self.user_id = user_id
        self.username = username
        self.menu_list = menu_list
        self.current_index = current_index
        self.votes = votes

        # 현재 메뉴에 대한 점수 선택 Select 추가
        self._add_score_select()

    def _add_score_select(self):
        """점수 선택 Select 추가"""
        current_menu = self.menu_list[self.current_index]

        options = [
            discord.SelectOption(
                label=f"{score}점 - {SCORE_LABELS[score]}",
                value=str(score),
                emoji=SCORE_EMOJIS[score]
            )
            for score in range(MIN_SCORE, MAX_SCORE + 1)
        ]

        select = Select(
            placeholder=f"{current_menu} - 점수를 선택하세요",
            options=options,
            custom_id=f"select_score_sequential_{self.user_id}",  # user_id로 고유하게
            row=0
        )

        async def callback(interaction: discord.Interaction):
            score = int(select.values[0])
            current_menu = self.menu_list[self.current_index]
            # View 내부 딕셔너리이므로 직접 수정 가능
            self.votes[current_menu] = score

            # 다음 메뉴로 이동
            next_index = self.current_index + 1

            # 모든 메뉴에 투표 완료
            if next_index >= len(self.menu_list):
                # 투표 제출 전에 수정 모드인지 확인 (로깅용)
                was_existing_vote = self.user_id in self.session.votes

                # 투표 제출 (submit_vote 내부에서 deepcopy 수행)
                self.session.submit_vote(self.user_id, self.username, self.votes)

                # 투표 내역 텍스트 생성
                vote_text = "\n".join([f"• {menu}: {s}점" for menu, s in self.votes.items()])

                await interaction.response.edit_message(
                    content=f"✅ **투표가 완료되었습니다!**\n\n{vote_text}",
                    view=None
                )

                # 투표 결과 로깅 (제출 전 상태 기준)
                vote_details = ", ".join([f"{menu}:{score}점" for menu, score in self.votes.items()])
                action = "수정" if was_existing_vote else "제출"
                logger.info(f"투표 {action}: {self.username} (user_id={self.user_id}) - {vote_details}")

                # 메인 투표 메시지 업데이트
                await self._update_main_message(interaction)
                return

            # 다음 메뉴로 계속
            next_menu = self.menu_list[next_index]
            # 같은 사용자의 View이므로 같은 딕셔너리 참조 전달
            next_view = SequentialVotingView(
                self.session,
                self.manager,
                self.user_id,
                self.username,
                self.menu_list,
                next_index,
                self.votes
            )

            # 진행 상황 표시
            voted_text = "\n".join([f"✓ {m}: {s}점" for m, s in self.votes.items()])

            await interaction.response.edit_message(
                content=f"📊 **{self.session.title}** 투표\n\n"
                        f"**투표 완료:**\n{voted_text}\n\n"
                        f"**{next_menu}**에 대한 점수를 선택하세요:\n"
                        f"({next_index + 1}/{len(self.menu_list)})",
                view=next_view
            )

        select.callback = callback
        self.add_item(select)

    async def _update_main_message(self, interaction: discord.Interaction):
        """메인 투표 메시지 업데이트"""
        if not self.session.message_id:
            return

        try:
            # 투표 진행 중이면 투표 Embed 업데이트
            if self.session.voting_started and not self.session.voting_closed:
                updated_embed = create_voting_embed(self.session, interaction.guild)
                await interaction.followup.edit_message(self.session.message_id, embed=updated_embed)
                logger.info(f"투표 현황 업데이트: {len(self.session.votes)}명 투표 완료")
        except Exception as e:
            logger.warning(f"메인 메시지 업데이트 실패: {e}")


class VotingFormView(View):
    """투표 폼 뷰 (수정 모드: 메뉴 선택 -> 점수 선택)"""

    def __init__(
        self,
        session: VotingSession,
        manager: VotingManager,
        user_id: int,
        username: str,
        existing_votes: Optional[Dict[str, int]] = None
    ):
        super().__init__(timeout=VOTING_FORM_TIMEOUT)
        self.session = session
        self.manager = manager
        self.user_id = user_id
        self.username = username
        # existing_votes는 이미 start_vote()에서 deepcopy된 상태이므로 그대로 사용
        self.user_votes: Dict[str, int] = existing_votes if existing_votes else {}
        # 수정 모드 여부: 세션에 이미 이 사용자의 투표가 있는지 확인
        self.is_edit_mode = user_id in session.votes

        # 메뉴 선택 Select 추가
        self._add_menu_select()

        # 투표 완료 버튼
        self._add_submit_button()

    def _add_menu_select(self):
        """메뉴 선택 Select 추가"""
        menu_list = list(self.session.menus.keys())

        # 수정 모드면 모든 메뉴 표시, 아니면 아직 투표하지 않은 메뉴만
        if self.is_edit_mode:
            available_menus = menu_list
        else:
            available_menus = [m for m in menu_list if m not in self.user_votes]

        if not available_menus:
            return

        # Select 옵션 생성 (최대 25개)
        options = []
        for menu in available_menus[:MAX_SELECT_OPTIONS]:
            # 수정 모드면 현재 점수 표시
            if self.is_edit_mode and menu in self.user_votes:
                description = f"현재: {self.user_votes[menu]}점"
            else:
                description = f"{menu}에 점수를 부여하세요"

            options.append(
                discord.SelectOption(
                    label=menu,
                    value=menu,
                    description=description
                )
            )

        placeholder = "수정할 메뉴를 선택하세요" if self.is_edit_mode else "점수를 부여할 메뉴를 선택하세요"

        select = Select(
            placeholder=placeholder,
            options=options,
            custom_id=f"select_menu_{self.user_id}",  # user_id로 고유하게
            row=0
        )

        async def callback(interaction: discord.Interaction):
            selected_menu = select.values[0]

            # 점수 선택 뷰로 전환
            score_view = ScoreSelectView(
                self.session,
                self.manager,
                self.user_id,
                self.username,
                selected_menu,
                self.user_votes
            )

            current_score_text = ""
            if self.is_edit_mode and selected_menu in self.user_votes:
                current_score_text = f"\n현재 점수: **{self.user_votes[selected_menu]}점**\n"

            await interaction.response.edit_message(
                content=f"📊 **{self.session.title}**\n\n"
                        f"**{selected_menu}**에 대한 점수를 선택하세요:{current_score_text}",
                view=score_view
            )

        select.callback = callback
        self.add_item(select)

    def _add_submit_button(self):
        """투표 완료 버튼 추가"""
        # 수정 모드면 항상 활성화, 아니면 모든 메뉴에 투표했을 때만 활성화
        is_complete = len(self.user_votes) >= len(self.session.menus)
        is_disabled = not (self.is_edit_mode or is_complete)

        if self.is_edit_mode:
            label = "투표 수정 완료"
        else:
            label = f"투표 완료 ({len(self.user_votes)}/{len(self.session.menus)})"

        button = Button(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id=f"submit_vote_{self.user_id}",  # user_id로 고유하게
            row=1,
            disabled=is_disabled
        )

        async def callback(interaction: discord.Interaction):
            # 수정 모드가 아닌 경우만 모든 메뉴에 투표했는지 확인
            if not self.is_edit_mode and len(self.user_votes) < len(self.session.menus):
                await interaction.response.send_message(
                    f"❌ 모든 메뉴에 점수를 부여해주세요! (현재: {len(self.user_votes)}/{len(self.session.menus)})",
                    ephemeral=True
                )
                return

            # 투표 제출 전에 수정 모드인지 확인 (로깅용)
            was_existing_vote = self.user_id in self.session.votes

            # 투표 제출
            self.session.submit_vote(self.user_id, self.username, self.user_votes)

            # 투표 내역 텍스트 생성
            vote_text = "\n".join([f"• {menu}: {score}점" for menu, score in self.user_votes.items()])

            success_message = "✅ **투표가 수정되었습니다!**" if self.is_edit_mode else "✅ **투표가 완료되었습니다!**"

            await interaction.response.edit_message(
                content=f"{success_message}\n\n{vote_text}",
                view=None
            )

            # 투표 결과 로깅 (제출 전 상태 기준)
            vote_details = ", ".join([f"{menu}:{score}점" for menu, score in self.user_votes.items()])
            action = "수정" if was_existing_vote else "제출"
            logger.info(f"투표 {action}: {self.username} (user_id={self.user_id}) - {vote_details}")

            # 메인 투표 메시지 업데이트
            await self._update_main_message(interaction)

        button.callback = callback
        self.add_item(button)

    async def _update_main_message(self, interaction: discord.Interaction):
        """메인 투표 메시지 업데이트"""
        if not self.session.message_id:
            return

        try:
            # 투표 진행 중이면 투표 Embed 업데이트
            if self.session.voting_started and not self.session.voting_closed:
                updated_embed = create_voting_embed(self.session, interaction.guild)
                await interaction.followup.edit_message(self.session.message_id, embed=updated_embed)
                logger.info(f"투표 현황 업데이트: {len(self.session.votes)}명 투표 완료")
        except Exception as e:
            logger.warning(f"메인 메시지 업데이트 실패: {e}")


class ScoreSelectView(View):
    """점수 선택 뷰"""

    def __init__(
        self,
        session: VotingSession,
        manager: VotingManager,
        user_id: int,
        username: str,
        menu_name: str,
        current_votes: Dict[str, int]
    ):
        super().__init__(timeout=VOTING_FORM_TIMEOUT)
        self.session = session
        self.manager = manager
        self.user_id = user_id
        self.username = username
        self.menu_name = menu_name
        self.current_votes = current_votes

        # 점수 선택 Select 추가
        self._add_score_select()

    def _add_score_select(self):
        """점수 선택 Select 추가"""
        options = [
            discord.SelectOption(
                label=f"{score}점 - {SCORE_LABELS[score]}",
                value=str(score),
                emoji=SCORE_EMOJIS[score]
            )
            for score in range(MIN_SCORE, MAX_SCORE + 1)
        ]

        select = Select(
            placeholder=f"{self.menu_name} - 점수를 선택하세요",
            options=options,
            custom_id=f"select_score_{self.user_id}",  # user_id로 고유하게
            row=0
        )

        async def callback(interaction: discord.Interaction):
            score = int(select.values[0])
            # View 내부 딕셔너리이므로 직접 수정 가능
            self.current_votes[self.menu_name] = score

            # 다시 메뉴 선택 뷰로 돌아가기
            # 같은 사용자의 View이므로 같은 딕셔너리 참조 전달
            menu_view = VotingFormView(
                self.session,
                self.manager,
                self.user_id,
                self.username,
                self.current_votes
            )
            # is_edit_mode는 VotingFormView 생성자에서 자동으로 판단됨

            # 진행 상황 텍스트
            voted_text = "\n".join([f"✓ {m}: {s}점" for m, s in self.current_votes.items()])

            # 수정 모드 여부를 실시간으로 확인 (세션에 이미 투표가 있는지)
            is_editing = self.user_id in self.session.votes

            if is_editing:
                # 수정 모드: 기존 투표 내역 표시
                await interaction.response.edit_message(
                    content=f"📊 **{self.session.title}** 투표\n\n"
                            f"**현재 투표 내역:**\n{voted_text}\n\n"
                            f"ℹ️ 다른 메뉴를 수정하려면 아래에서 선택하세요.\n"
                            f"수정을 마쳤다면 '투표 수정 완료' 버튼을 누르세요.",
                    view=menu_view
                )
            else:
                # 일반 모드: 진행 상황 표시
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


class ResultsView(View):
    """투표 결과 뷰 (랜덤 선택 및 재투표 버튼 포함)"""

    def __init__(
        self,
        regular_results: list[tuple[str, int, int]],
        session: VotingSession,
        manager: VotingManager
    ):
        super().__init__(timeout=None)
        self.regular_results = regular_results
        self.session = session
        self.manager = manager

    @discord.ui.button(
        label="🎲 1위 메뉴 중 랜덤 선택",
        style=discord.ButtonStyle.primary,
        custom_id="random_select_btn",
        row=0
    )
    async def random_select(self, interaction: discord.Interaction, button: Button):
        """1위 메뉴 중 랜덤 선택 버튼"""
        import random

        # 1위 메뉴들 찾기
        if not self.regular_results:
            await interaction.response.send_message(
                "❌ 선택할 메뉴가 없습니다!",
                ephemeral=True
            )
            return

        winner_score = self.regular_results[0][1]
        winner_min_score = self.regular_results[0][2]
        winners = [
            r[0] for r in self.regular_results
            if r[1] == winner_score and r[2] == winner_min_score
        ]

        # 랜덤 선택
        selected_menu = random.choice(winners)

        # 결과 메시지 생성
        result_embed = discord.Embed(
            title="🎲 랜덤 선택 결과",
            description=f"# 🎯 {selected_menu}",
            color=discord.Color.green()
        )

        if len(winners) > 1:
            other_winners = [w for w in winners if w != selected_menu]
            result_embed.add_field(
                name="후보 메뉴",
                value=", ".join(winners),
                inline=False
            )

        # 새 메시지로 전송
        await interaction.response.send_message(embed=result_embed)

        # 두 버튼 모두 비활성화
        for child in self.children:
            if isinstance(child, Button):
                child.disabled = True

        button.label = "✅ 랜덤 선택 완료"
        await interaction.message.edit(view=self)

        logger.info(f"랜덤 선택 완료: {selected_menu} (후보: {len(winners)}개)")

    @discord.ui.button(
        label="🔄 1위 메뉴 재투표",
        style=discord.ButtonStyle.secondary,
        custom_id="revote_btn",
        row=0
    )
    async def revote(self, interaction: discord.Interaction, button: Button):
        """1위 메뉴 재투표 버튼"""
        # 1위 메뉴들 찾기
        winner_score = self.regular_results[0][1]
        winner_min_score = self.regular_results[0][2]
        winners = [
            r[0] for r in self.regular_results
            if r[1] == winner_score and r[2] == winner_min_score
        ]

        # 기존 세션 정보 저장 (세션은 이미 투표 종료 시 삭제됨)
        guild_id = self.session.guild_id
        channel_id = self.session.channel_id
        is_restricted = self.session.is_restricted
        allowed_voters = self.session.allowed_voters.copy() if self.session.is_restricted else set()
        original_title = self.session.title

        # 새로운 투표 세션 생성 (1위 메뉴들로만)
        new_session = self.manager.create_session(
            guild_id=guild_id,
            channel_id=channel_id,
            creator_id=interaction.user.id,
            title=f"[재투표] {original_title}",
            is_restricted=is_restricted
        )

        # 재투표에서도 기존 투표자들이 투표할 수 있도록 설정
        if is_restricted:
            for voter_id in allowed_voters:
                new_session.allow_voter(voter_id)

        # 1위 메뉴들만 추가
        for menu_name in winners:
            new_session.add_menu(menu_name, interaction.user.id)

        # 투표 시작
        new_session.voting_started = True

        # 투표 embed 생성
        voting_embed = create_voting_embed(new_session)
        voting_view = VotingView(new_session, self.manager)

        # 응답 전송
        await interaction.response.send_message(
            content=f"🔄 **1위 메뉴들로 재투표를 시작합니다!**\n"
                    f"후보: {', '.join(winners)}",
            embed=voting_embed,
            view=voting_view
        )

        # 두 버튼 모두 비활성화
        for child in self.children:
            if isinstance(child, Button):
                child.disabled = True

        button.label = "✅ 재투표 시작됨"
        await interaction.message.edit(view=self)

        logger.info(f"재투표 시작: {len(winners)}개 메뉴 ({', '.join(winners)})")
