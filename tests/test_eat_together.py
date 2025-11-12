"""
같이먹자 시스템 테스트
"""
import pytest
from eat_together import EatTogetherSession, EatTogetherManager


class TestEatTogetherSession:
    """EatTogetherSession 클래스 테스트"""

    def test_session_creation(self):
        """세션 생성 테스트"""
        session = EatTogetherSession(
            food_name="짜장면",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )

        assert session.food_name == "짜장면"
        assert session.guild_id == 123
        assert session.channel_id == 456
        assert session.creator_id == 789
        assert 789 in session.participants  # 생성자는 자동 참여
        assert len(session.participants) == 1
        assert not session.departed

    def test_add_participant(self):
        """참여자 추가 테스트"""
        session = EatTogetherSession(
            food_name="피자",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )

        # 새 참여자 추가
        result = session.add_participant(999)
        assert result is True
        assert 999 in session.participants
        assert len(session.participants) == 2

        # 이미 있는 참여자 (중복 추가는 set이므로 무시됨)
        result = session.add_participant(999)
        assert result is True
        assert len(session.participants) == 2

    def test_add_participant_after_departure(self):
        """출발 후 참여자 추가 불가 테스트"""
        session = EatTogetherSession(
            food_name="치킨",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )

        session.mark_departed()
        result = session.add_participant(999)
        assert result is False
        assert 999 not in session.participants

    def test_remove_participant(self):
        """참여자 제거 테스트"""
        session = EatTogetherSession(
            food_name="짬뽕",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )

        # 참여자 추가
        session.add_participant(999)
        assert 999 in session.participants

        # 참여자 제거
        result = session.remove_participant(999)
        assert result is True
        assert 999 not in session.participants

    def test_remove_participant_creator(self):
        """생성자 제거 불가 테스트"""
        session = EatTogetherSession(
            food_name="탕수육",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )

        # 생성자는 제거 불가
        result = session.remove_participant(789)
        assert result is False
        assert 789 in session.participants

    def test_remove_participant_after_departure(self):
        """출발 후 참여자 제거 불가 테스트"""
        session = EatTogetherSession(
            food_name="돈까스",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )

        session.add_participant(999)
        session.mark_departed()

        result = session.remove_participant(999)
        assert result is False
        assert 999 in session.participants

    def test_can_depart(self):
        """출발 가능 여부 테스트"""
        session = EatTogetherSession(
            food_name="라면",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )

        # 생성자는 출발 가능
        assert session.can_depart(789) is True

        # 다른 사람은 출발 불가
        session.add_participant(999)
        assert session.can_depart(999) is False

        # 이미 출발한 경우
        session.mark_departed()
        assert session.can_depart(789) is False

    def test_mark_departed(self):
        """출발 처리 테스트"""
        session = EatTogetherSession(
            food_name="김치찌개",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )

        assert not session.departed

        result = session.mark_departed()
        assert result is True
        assert session.departed

        # 중복 출발 불가
        result = session.mark_departed()
        assert result is False


class TestEatTogetherManager:
    """EatTogetherManager 클래스 테스트"""

    def test_create_session(self):
        """세션 생성 테스트"""
        manager = EatTogetherManager()

        session_id, session = manager.create_session(
            guild_id=123,
            channel_id=456,
            creator_id=789,
            food_name="햄버거"
        )

        assert session_id == 0
        assert session.food_name == "햄버거"
        assert session.guild_id == 123
        assert session.channel_id == 456
        assert session.creator_id == 789

    def test_create_multiple_sessions(self):
        """여러 세션 생성 테스트"""
        manager = EatTogetherManager()

        # 같은 길드에서 여러 세션 생성 가능
        session_id1, session1 = manager.create_session(123, 456, 789, "짜장면")
        session_id2, session2 = manager.create_session(123, 456, 999, "짬뽕")

        assert session_id1 == 0
        assert session_id2 == 1
        assert session1.food_name == "짜장면"
        assert session2.food_name == "짬뽕"

    def test_get_session(self):
        """세션 가져오기 테스트"""
        manager = EatTogetherManager()

        session_id, _ = manager.create_session(123, 456, 789, "피자")

        retrieved = manager.get_session(123, session_id)
        assert retrieved is not None
        assert retrieved.food_name == "피자"

        # 없는 세션
        none_session = manager.get_session(123, 999)
        assert none_session is None

    def test_close_session(self):
        """세션 종료 테스트"""
        manager = EatTogetherManager()

        session_id, _ = manager.create_session(123, 456, 789, "치킨")

        result = manager.close_session(123, session_id)
        assert result is True

        # 종료된 세션은 가져올 수 없음
        retrieved = manager.get_session(123, session_id)
        assert retrieved is None

        # 없는 세션 종료
        result = manager.close_session(123, 999)
        assert result is False

    def test_get_active_sessions(self):
        """활성 세션 목록 가져오기 테스트"""
        manager = EatTogetherManager()

        # 여러 세션 생성
        sid1, _ = manager.create_session(123, 456, 789, "짜장면")
        sid2, _ = manager.create_session(123, 456, 999, "짬뽕")
        sid3, _ = manager.create_session(456, 789, 111, "탕수육")

        # guild_id=123의 활성 세션 목록
        active = manager.get_active_sessions(123)
        assert len(active) == 2
        assert all(gid == 123 for _, session in active for gid in [session.guild_id])

        # 하나 종료
        manager.close_session(123, sid1)
        active = manager.get_active_sessions(123)
        assert len(active) == 1

        # guild_id=456의 활성 세션 목록
        active = manager.get_active_sessions(456)
        assert len(active) == 1
        assert active[0][0] == sid3
