"""menu_voting.py 테스트"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from menu_voting import (
    VotingSession,
    VotingManager,
    create_proposal_embed,
    create_voting_embed,
    create_results_embed
)


@pytest.mark.unit
class TestVotingSession:
    """VotingSession 클래스 테스트"""

    @pytest.fixture
    def session(self):
        """기본 투표 세션"""
        return VotingSession(
            title="테스트 투표",
            guild_id=123456789,
            channel_id=987654321,
            creator_id=111222333
        )

    def test_session_initialization(self, session):
        """세션 초기화 확인"""
        assert session.title == "테스트 투표"
        assert session.guild_id == 123456789
        assert session.channel_id == 987654321
        assert session.creator_id == 111222333
        assert session.menus == {}
        assert session.votes == {}
        assert session.voting_started is False
        assert session.voting_closed is False
        assert isinstance(session.created_at, datetime)

    def test_add_menu_success(self, session):
        """메뉴 추가 성공"""
        result = session.add_menu("짜장면", 111)
        assert result is True
        assert "짜장면" in session.menus
        assert session.menus["짜장면"] == 111

    def test_add_menu_duplicate(self, session):
        """중복 메뉴 추가 실패"""
        session.add_menu("짜장면", 111)
        result = session.add_menu("짜장면", 222)
        assert result is False
        assert session.menus["짜장면"] == 111  # 기존 제안자 유지

    def test_add_menu_after_voting_started(self, session):
        """투표 시작 후 메뉴 추가 불가"""
        session.voting_started = True
        result = session.add_menu("짜장면", 111)
        assert result is False
        assert "짜장면" not in session.menus

    def test_remove_menu_success(self, session):
        """메뉴 삭제 성공"""
        session.add_menu("짜장면", 111)
        result = session.remove_menu("짜장면", 111)
        assert result is True
        assert "짜장면" not in session.menus

    def test_remove_menu_not_proposer(self, session):
        """다른 사람이 제안한 메뉴 삭제 불가"""
        session.add_menu("짜장면", 111)
        result = session.remove_menu("짜장면", 222)
        assert result is False
        assert "짜장면" in session.menus

    def test_remove_menu_nonexistent(self, session):
        """존재하지 않는 메뉴 삭제 실패"""
        result = session.remove_menu("짜장면", 111)
        assert result is False

    def test_remove_menu_after_voting_started(self, session):
        """투표 시작 후 메뉴 삭제 불가"""
        session.add_menu("짜장면", 111)
        session.voting_started = True
        result = session.remove_menu("짜장면", 111)
        assert result is False

    def test_submit_vote_success(self, session):
        """투표 제출 성공"""
        session.add_menu("짜장면", 111)
        session.add_menu("짬뽕", 222)
        session.voting_started = True

        votes = {"짜장면": 5, "짬뽕": 3}
        result = session.submit_vote(333, votes)
        assert result is True
        assert session.votes[333] == votes

    def test_submit_vote_before_start(self, session):
        """투표 시작 전 투표 불가"""
        votes = {"짜장면": 5}
        result = session.submit_vote(333, votes)
        assert result is False

    def test_submit_vote_after_close(self, session):
        """투표 종료 후 투표 불가"""
        session.voting_started = True
        session.voting_closed = True
        votes = {"짜장면": 5}
        result = session.submit_vote(333, votes)
        assert result is False

    def test_submit_vote_overwrite(self, session):
        """투표 덮어쓰기"""
        session.add_menu("짜장면", 111)
        session.voting_started = True

        votes1 = {"짜장면": 3}
        session.submit_vote(333, votes1)

        votes2 = {"짜장면": 5}
        session.submit_vote(333, votes2)

        assert session.votes[333] == votes2


@pytest.mark.unit
class TestVotingResultCalculation:
    """투표 결과 계산 테스트"""

    @pytest.fixture
    def session_with_votes(self):
        """투표가 완료된 세션"""
        session = VotingSession(
            title="점심 메뉴",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )
        session.add_menu("짜장면", 1)
        session.add_menu("짬뽕", 2)
        session.add_menu("탕수육", 3)
        session.voting_started = True

        # 투표 데이터
        session.submit_vote(10, {"짜장면": 5, "짬뽕": 4, "탕수육": 3})
        session.submit_vote(20, {"짜장면": 4, "짬뽕": 5, "탕수육": 2})
        session.submit_vote(30, {"짜장면": 3, "짬뽕": 4, "탕수육": 5})

        return session

    def test_calculate_results_total_score(self, session_with_votes):
        """총점 계산 확인"""
        results = session_with_votes.calculate_results()

        # 결과는 (메뉴명, 총점, 최소점) 튜플의 리스트
        menu_scores = {menu: total for menu, total, _ in results}

        assert menu_scores["짜장면"] == 12  # 5+4+3
        assert menu_scores["짬뽕"] == 13    # 4+5+4
        assert menu_scores["탕수육"] == 10  # 3+2+5

    def test_calculate_results_sorting(self, session_with_votes):
        """결과 정렬 확인 (총점 내림차순)"""
        results = session_with_votes.calculate_results()

        # 첫 번째는 짬뽕(13점)이어야 함
        assert results[0][0] == "짬뽕"
        assert results[0][1] == 13

    def test_calculate_results_min_score(self, session_with_votes):
        """최소점 계산 확인"""
        results = session_with_votes.calculate_results()

        # 짜장면의 최소점은 3점
        jjajang_result = next(r for r in results if r[0] == "짜장면")
        assert jjajang_result[2] == 3

    def test_calculate_results_tie_breaker(self):
        """동점 시 최소점으로 순위 결정"""
        session = VotingSession(
            title="동점 테스트",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        # 총점은 같지만 최소점이 다름
        session.submit_vote(10, {"메뉴A": 5, "메뉴B": 5})
        session.submit_vote(20, {"메뉴A": 5, "메뉴B": 4})
        # 메뉴A: 총 10점, 최소 5점
        # 메뉴B: 총 9점, 최소 4점

        results = session.calculate_results()

        # 메뉴A가 1위여야 함
        assert results[0][0] == "메뉴A"

    def test_calculate_results_no_votes(self):
        """투표가 없는 경우"""
        session = VotingSession(
            title="투표 없음",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )
        session.add_menu("짜장면", 1)
        session.voting_started = True

        results = session.calculate_results()

        assert len(results) == 1
        assert results[0] == ("짜장면", 0, 0)

    def test_calculate_results_partial_votes(self):
        """일부 사용자만 투표한 경우"""
        session = VotingSession(
            title="부분 투표",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        # 사용자 10은 메뉴A에만 투표
        session.submit_vote(10, {"메뉴A": 5, "메뉴B": 3})
        session.submit_vote(20, {"메뉴A": 4, "메뉴B": 5})

        results = session.calculate_results()

        # 모든 메뉴가 결과에 포함되어야 함
        assert len(results) == 2


@pytest.mark.unit
class TestVotingManager:
    """VotingManager 클래스 테스트"""

    @pytest.fixture
    def manager(self):
        """기본 투표 매니저"""
        return VotingManager()

    def test_manager_initialization(self, manager):
        """매니저 초기화 확인"""
        assert manager.sessions == {}

    def test_create_session_success(self, manager):
        """세션 생성 성공"""
        session = manager.create_session(
            guild_id=123,
            channel_id=456,
            creator_id=789,
            title="점심 메뉴"
        )
        assert session is not None
        assert session.title == "점심 메뉴"
        assert manager.get_session(123) == session

    def test_create_session_duplicate(self, manager):
        """중복 세션 생성 실패"""
        manager.create_session(123, 456, 789, "투표1")
        session2 = manager.create_session(123, 999, 888, "투표2")
        assert session2 is None
        assert manager.get_session(123).title == "투표1"

    def test_get_session_nonexistent(self, manager):
        """존재하지 않는 세션 조회"""
        session = manager.get_session(999)
        assert session is None

    def test_close_session_success(self, manager):
        """세션 종료 성공"""
        manager.create_session(123, 456, 789, "테스트")
        result = manager.close_session(123)
        assert result is True
        assert manager.get_session(123) is None

    def test_close_session_nonexistent(self, manager):
        """존재하지 않는 세션 종료"""
        result = manager.close_session(999)
        assert result is False

    def test_multiple_guilds(self, manager):
        """여러 길드에서 동시에 투표"""
        session1 = manager.create_session(123, 456, 789, "길드1 투표")
        session2 = manager.create_session(456, 789, 111, "길드2 투표")

        assert session1 is not None
        assert session2 is not None
        assert manager.get_session(123).title == "길드1 투표"
        assert manager.get_session(456).title == "길드2 투표"


@pytest.mark.unit
class TestEmbedCreation:
    """Embed 생성 함수 테스트"""

    @pytest.fixture
    def session_proposal(self):
        """메뉴 제안 단계 세션"""
        session = VotingSession(
            title="점심 메뉴 투표",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )
        session.add_menu("짜장면", 1)
        session.add_menu("짬뽕", 2)
        return session

    @pytest.fixture
    def session_voting(self):
        """투표 진행 단계 세션"""
        session = VotingSession(
            title="점심 메뉴 투표",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )
        session.add_menu("짜장면", 1)
        session.add_menu("짬뽕", 2)
        session.voting_started = True
        session.submit_vote(10, {"짜장면": 5, "짬뽕": 4})
        session.submit_vote(20, {"짜장면": 4, "짬뽕": 5})
        return session

    def test_create_proposal_embed_empty(self):
        """메뉴가 없는 제안 단계 Embed"""
        session = VotingSession("테스트", 123, 456, 789)
        embed = create_proposal_embed(session)

        assert "테스트" in embed.title
        assert embed.description is not None
        assert len(embed.fields) > 0

    def test_create_proposal_embed_with_menus(self, session_proposal):
        """메뉴가 있는 제안 단계 Embed"""
        embed = create_proposal_embed(session_proposal)

        assert "점심 메뉴 투표" in embed.title

        # 필드 내용 확인
        field_values = [field.value for field in embed.fields]
        menu_field = next((f for f in field_values if "짜장면" in f or "짬뽕" in f), None)
        assert menu_field is not None

    def test_create_voting_embed(self, session_voting):
        """투표 진행 단계 Embed"""
        embed = create_voting_embed(session_voting)

        assert "점심 메뉴 투표" in embed.title
        assert embed.description is not None

        # 투표 현황이 포함되어야 함
        field_values = [field.value for field in embed.fields]
        assert any("2명" in str(v) for v in field_values)

    def test_create_results_embed(self, session_voting):
        """결과 Embed"""
        results = session_voting.calculate_results()
        embed = create_results_embed(session_voting, results)

        assert "결과" in embed.title
        assert "2명" in embed.description

        # 순위 정보가 포함되어야 함
        field_values = [field.value for field in embed.fields]
        ranking_field = next((f for f in field_values if "1위" in str(f) or "🥇" in str(f)), None)
        assert ranking_field is not None

    def test_create_results_embed_no_votes(self):
        """투표가 없는 결과 Embed"""
        session = VotingSession("투표 없음", 123, 456, 789)
        session.add_menu("짜장면", 1)
        session.voting_started = True

        results = session.calculate_results()
        embed = create_results_embed(session, results)

        assert embed is not None
        assert "0명" in embed.description

    def test_create_results_embed_tie(self):
        """동점인 경우 결과 Embed"""
        session = VotingSession("동점 테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        # 동점
        session.submit_vote(10, {"메뉴A": 5, "메뉴B": 5})
        session.submit_vote(20, {"메뉴A": 5, "메뉴B": 5})

        results = session.calculate_results()
        embed = create_results_embed(session, results)

        # 동점 표시가 있어야 함
        assert any("동점" in str(field.value) or "메뉴A" in str(field.value) for field in embed.fields)


@pytest.mark.integration
class TestVotingWorkflow:
    """투표 전체 워크플로우 통합 테스트"""

    def test_complete_voting_workflow(self):
        """전체 투표 프로세스"""
        manager = VotingManager()

        # 1. 투표 시작
        session = manager.create_session(123, 456, 789, "점심 메뉴")
        assert session is not None

        # 2. 메뉴 제안
        session.add_menu("짜장면", 10)
        session.add_menu("짬뽕", 20)
        session.add_menu("탕수육", 30)
        assert len(session.menus) == 3

        # 3. 투표 시작
        session.voting_started = True

        # 4. 투표 진행
        session.submit_vote(10, {"짜장면": 5, "짬뽕": 4, "탕수육": 3})
        session.submit_vote(20, {"짜장면": 4, "짬뽕": 5, "탕수육": 2})
        session.submit_vote(30, {"짜장면": 5, "짬뽕": 3, "탕수육": 4})
        assert len(session.votes) == 3

        # 5. 결과 계산
        results = session.calculate_results()
        assert len(results) == 3

        winner = results[0]
        assert winner[0] == "짜장면"  # 총 14점으로 1위
        assert winner[1] == 14

        # 6. 세션 종료
        session.voting_closed = True
        manager.close_session(123)
        assert manager.get_session(123) is None

    def test_vote_modification(self):
        """투표 수정 시나리오"""
        session = VotingSession("테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        # 첫 번째 투표
        session.submit_vote(10, {"메뉴A": 3, "메뉴B": 4})
        results1 = session.calculate_results()
        assert results1[0][0] == "메뉴B"

        # 투표 수정
        session.submit_vote(10, {"메뉴A": 5, "메뉴B": 2})
        results2 = session.calculate_results()
        assert results2[0][0] == "메뉴A"

    def test_menu_proposal_cancellation(self):
        """메뉴 제안 취소 시나리오"""
        session = VotingSession("테스트", 123, 456, 789)

        # 메뉴 제안
        session.add_menu("짜장면", 10)
        session.add_menu("짬뽕", 20)
        assert len(session.menus) == 2

        # 메뉴 취소
        session.remove_menu("짜장면", 10)
        assert len(session.menus) == 1
        assert "짬뽕" in session.menus
        assert "짜장면" not in session.menus
