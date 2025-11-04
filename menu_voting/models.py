"""
메뉴 투표 시스템 데이터 모델

주요 클래스:
- VotingSession: 투표 세션 데이터 관리
- VotingManager: 여러 길드의 투표 세션 관리
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

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

    # 투표 진행 상태
    voting_started: bool = False
    voting_closed: bool = False

    # 메인 투표 메시지 ID (갱신용)
    message_id: Optional[int] = None

    def add_menu(self, menu_name: str, proposer_id: int) -> bool:
        """
        메뉴 제안 추가

        Args:
            menu_name: 메뉴 이름
            proposer_id: 제안자 사용자 ID

        Returns:
            성공 여부 (투표 시작 후 또는 중복 메뉴면 False)
        """
        if self.voting_started:
            return False
        if menu_name in self.menus:
            return False
        self.menus[menu_name] = proposer_id
        return True

    def remove_menu(self, menu_name: str, user_id: int, is_admin: bool = False) -> bool:
        """
        메뉴 제안 삭제 (제안자 또는 관리자만 가능)

        Args:
            menu_name: 메뉴 이름
            user_id: 삭제 요청자 사용자 ID
            is_admin: 관리자 여부 (True면 제안자 확인 생략)

        Returns:
            성공 여부 (투표 시작 후, 메뉴 없음, 권한 없음이면 False)
        """
        if self.voting_started:
            return False
        if menu_name not in self.menus:
            return False
        # 관리자가 아니면 제안자만 삭제 가능
        if not is_admin and self.menus[menu_name] != user_id:
            return False
        del self.menus[menu_name]
        return True

    def submit_vote(self, user_id: int, votes: Dict[str, int]) -> bool:
        """
        투표 제출

        Args:
            user_id: 투표자 사용자 ID
            votes: 메뉴별 점수 딕셔너리

        Returns:
            성공 여부 (투표 미시작 또는 종료 시 False)
        """
        if not self.voting_started or self.voting_closed:
            return False
        self.votes[user_id] = votes
        return True

    def calculate_results(self) -> List[Tuple[str, int, int]]:
        """
        투표 결과 계산

        Returns:
            List of (메뉴명, 총점, 최소점) 튜플을 점수 순으로 정렬
            - 1차: 총점 내림차순
            - 2차: 최소점 내림차순 (동점 처리)
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
    """투표 세션 관리자"""

    def __init__(self):
        # {guild_id: VotingSession}
        self.sessions: Dict[int, VotingSession] = {}

    def create_session(
        self,
        guild_id: int,
        channel_id: int,
        creator_id: int,
        title: str
    ) -> Optional[VotingSession]:
        """
        새 투표 세션 생성

        Args:
            guild_id: 길드 ID
            channel_id: 채널 ID
            creator_id: 생성자 사용자 ID
            title: 투표 제목

        Returns:
            생성된 세션 (이미 세션이 있으면 None)
        """
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
        """
        투표 세션 가져오기

        Args:
            guild_id: 길드 ID

        Returns:
            세션 (없으면 None)
        """
        return self.sessions.get(guild_id)

    def close_session(self, guild_id: int) -> bool:
        """
        투표 세션 종료

        Args:
            guild_id: 길드 ID

        Returns:
            성공 여부 (세션이 없으면 False)
        """
        if guild_id in self.sessions:
            del self.sessions[guild_id]
            return True
        return False
