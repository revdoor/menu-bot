"""
메뉴 투표 시스템 Embed 생성 함수

주요 기능:
- 제안 단계 Embed 생성
- 투표 단계 Embed 생성
- 결과 Embed 생성
"""
import logging
from typing import List, Tuple

import discord

from .models import VotingSession
from .constants import RANK_EMOJIS, MAX_DETAILED_RESULTS

logger = logging.getLogger(__name__)


def create_proposal_embed(session: VotingSession) -> discord.Embed:
    """
    메뉴 제안 단계 Embed 생성

    Args:
        session: 투표 세션

    Returns:
        제안 단계 Embed
    """
    title = f"📝 {session.title}"
    if session.is_restricted:
        title += " 🔒"

    description = "메뉴를 제안해주세요! `/메뉴제안 <메뉴명>` 명령어를 사용하세요."
    if session.is_restricted:
        description += "\n\n🔒 **제한된 투표**: 투표 생성자가 허용한 사람만 투표할 수 있습니다."

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )

    logger.debug(f"제안된 메뉴: {session.menus}")

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

    footer_text = "최소 2개 이상의 메뉴가 필요합니다."
    if session.is_restricted:
        footer_text += " | 🔒 제한된 투표"

    embed.set_footer(text=footer_text)

    return embed


def create_voting_embed(session: VotingSession) -> discord.Embed:
    """
    투표 진행 단계 Embed 생성

    Args:
        session: 투표 세션

    Returns:
        투표 진행 Embed
    """
    title = f"🗳️ {session.title}"
    if session.is_restricted:
        title += " 🔒"

    description = "아래 '투표하기' 버튼을 눌러 투표에 참여하세요!"
    if session.is_restricted:
        description += "\n\n🔒 **제한된 투표**: 투표 생성자가 허용한 사람만 투표할 수 있습니다."

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green()
    )

    menu_list = "\n".join([f"• {menu}" for menu in session.menus.keys()])
    embed.add_field(
        name=f"메뉴 목록 ({len(session.menus)}개)",
        value=menu_list,
        inline=False
    )

    # 투표 현황 - 투표자 이름 표시
    voter_count = len(session.votes)
    if voter_count > 0:
        voter_names = ", ".join(session.voter_names.values())
        status_text = f"{voter_count}명 투표 완료\n{voter_names}"
    else:
        status_text = "아직 투표한 사람이 없습니다"

    embed.add_field(
        name="투표 현황",
        value=status_text,
        inline=False
    )

    footer_text = "각 메뉴에 1-5점을 부여해주세요"
    if session.is_restricted:
        allowed_count = len(session.allowed_voters) + 1  # +1은 생성자
        footer_text += f" | 🔒 허용된 인원: {allowed_count}명"

    embed.set_footer(text=footer_text)

    return embed


def create_results_embed(
    session: VotingSession,
    regular_results: List[Tuple[str, int, int]],
    zero_results: List[Tuple[str, int, List[str]]]
) -> discord.Embed:
    """
    투표 결과 Embed 생성

    Args:
        session: 투표 세션
        regular_results: 일반 메뉴 결과 [(메뉴명, 총점, 최소점), ...]
        zero_results: 0점 메뉴 결과 [(메뉴명, 총점, [0점 준 사람들]), ...]

    Returns:
        결과 Embed
    """
    embed = discord.Embed(
        title=f"🏆 {session.title} - 결과",
        description=f"총 {len(session.votes)}명이 투표에 참여했습니다.",
        color=discord.Color.gold()
    )

    if not regular_results and not zero_results:
        embed.add_field(
            name="결과",
            value="투표 결과가 없습니다.",
            inline=False
        )
        return embed

    # 일반 메뉴 결과만 있는 경우
    if regular_results:
        # 1위 메뉴 강조
        _add_winner_field(embed, regular_results)

        # 전체 순위
        _add_ranking_field(embed, regular_results)

        # 상세 투표 내역 (상위 3개만)
        _add_detailed_votes_field(embed, session, regular_results)
    elif zero_results:
        # 모든 메뉴가 0점을 받은 경우
        embed.add_field(
            name="🎯 최종 선택",
            value="⚠️ 모든 메뉴가 0점을 포함하여 순위에서 제외되었습니다.",
            inline=False
        )

    # 0점 메뉴가 있는 경우 별도 표시
    if zero_results:
        _add_zero_score_menus_field(embed, zero_results)

    embed.set_footer(text=f"투표 기간: {session.created_at.strftime('%Y-%m-%d %H:%M')}")

    return embed


def _add_winner_field(embed: discord.Embed, results: List[Tuple[str, int, int]]) -> None:
    """
    1위 메뉴 필드 추가 (내부 헬퍼)

    Args:
        embed: Embed 객체
        results: 결과 리스트
    """
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


def _add_ranking_field(embed: discord.Embed, results: List[Tuple[str, int, int]]) -> None:
    """
    전체 순위 필드 추가 (내부 헬퍼)

    Args:
        embed: Embed 객체
        results: 결과 리스트
    """
    ranking_text = ""
    current_rank = 1
    prev_total = None
    prev_min = None

    for idx, (menu, total, min_score) in enumerate(results, 1):
        # 이전 메뉴와 총점과 최소점이 모두 같으면 동점 처리
        if prev_total is not None and prev_min is not None:
            if total != prev_total or min_score != prev_min:
                current_rank = idx

        medal = RANK_EMOJIS.get(current_rank, "  ")
        ranking_text += f"{medal} {current_rank}위. **{menu}** - {total}점 (최소: {min_score}점)\n"

        prev_total = total
        prev_min = min_score

    embed.add_field(
        name="📊 전체 순위",
        value=ranking_text,
        inline=False
    )


def _add_detailed_votes_field(
    embed: discord.Embed,
    session: VotingSession,
    results: List[Tuple[str, int, int]]
) -> None:
    """
    상세 투표 내역 필드 추가 (내부 헬퍼)

    Args:
        embed: Embed 객체
        session: 투표 세션
        results: 결과 리스트
    """
    detailed_votes = []
    for menu, _, _ in results[:MAX_DETAILED_RESULTS]:
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


def _add_zero_score_menus_field(
    embed: discord.Embed,
    zero_results: List[Tuple[str, int, List[str]]]
) -> None:
    """
    0점 메뉴 필드 추가 (내부 헬퍼)

    Args:
        embed: Embed 객체
        zero_results: 0점 메뉴 결과 [(메뉴명, 총점, [0점 준 사람들]), ...]
    """
    zero_text = ""
    for menu, total_score, zero_voters in zero_results:
        voter_names = ", ".join(zero_voters) if zero_voters else "없음"
        zero_text += f"**{menu}** (총점: {total_score}점) - 0점을 준 사람: {voter_names}\n"

    embed.add_field(
        name="❌ 제외된 메뉴 (0점 포함)",
        value=zero_text,
        inline=False
    )
