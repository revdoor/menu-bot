"""
메뉴 투표 시스템 유틸리티 함수

주요 기능:
- 투표 메시지 업데이트
"""
import logging

import discord

from .models import VotingSession
from .embeds import create_proposal_embed, create_voting_embed

logger = logging.getLogger(__name__)


async def update_voting_message(interaction: discord.Interaction, session: VotingSession) -> None:
    """
    투표 메시지 업데이트

    Args:
        interaction: Discord Interaction
        session: 투표 세션

    Note:
        - 제안 단계: create_proposal_embed 사용
        - 투표 단계: create_voting_embed 사용
        - message_id가 없으면 업데이트 불가
    """
    if not session.message_id:
        logger.warning(f"메시지 업데이트 실패: message_id가 없음 (세션: {session.title})")
        return

    try:
        # 투표 시작 전이면 제안 Embed, 시작 후면 투표 Embed
        if session.voting_started:
            updated_embed = create_voting_embed(session, interaction.guild)
            logger.debug("투표 진행 중 Embed 생성")
        else:
            updated_embed = create_proposal_embed(session)
            logger.debug(f"제안 단계 Embed 생성 (메뉴 수: {len(session.menus)})")
            logger.debug(f"새 Embed 필드 수: {len(updated_embed.fields)}")
            if updated_embed.fields:
                logger.debug(f"첫 번째 필드 값: {updated_embed.fields[0].value[:100]}")

        # followup.edit_message로 원본 투표 메시지 수정 (View 유지됨)
        logger.debug(f"followup.edit_message() 호출 - message_id: {session.message_id}")
        await interaction.followup.edit_message(session.message_id, embed=updated_embed)
        logger.info(f"✅ 메시지 업데이트 완료: {session.title} (메뉴: {len(session.menus)}개)")
    except discord.NotFound:
        logger.error(f"메시지 업데이트 실패: 메시지를 찾을 수 없음 (message_id: {session.message_id})")
    except discord.Forbidden:
        logger.error(f"메시지 업데이트 실패: 권한 없음 (message_id: {session.message_id})")
    except Exception as e:
        logger.error(f"메시지 업데이트 실패: {e}", exc_info=True)
