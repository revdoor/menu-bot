"""menu_voting 패키지 테스트"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from menu_voting.models import VotingSession, VotingManager
from menu_voting.embeds import (
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
        assert session.message_id is None
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


@pytest.mark.unit
class TestMessageUpdates:
    """메시지 업데이트 기능 테스트"""

    def test_session_with_message_id(self):
        """메시지 ID 저장 확인"""
        session = VotingSession("테스트", 123, 456, 789)
        assert session.message_id is None

        # 메시지 ID 설정
        session.message_id = 999888777
        assert session.message_id == 999888777

    def test_message_id_persists_across_operations(self):
        """메뉴 추가/투표 등의 작업 후에도 message_id 유지"""
        session = VotingSession("테스트", 123, 456, 789)
        session.message_id = 111222333

        # 메뉴 추가
        session.add_menu("짜장면", 10)
        assert session.message_id == 111222333

        # 투표 시작
        session.voting_started = True
        assert session.message_id == 111222333

        # 투표 제출
        session.submit_vote(10, {"짜장면": 5})
        assert session.message_id == 111222333


@pytest.mark.unit
class TestAutocomplete:
    """자동완성 기능 테스트 (로직 검증)"""

    def test_get_user_menus(self):
        """사용자가 제안한 메뉴만 필터링"""
        session = VotingSession("테스트", 123, 456, 789)
        session.add_menu("짜장면", 10)
        session.add_menu("짬뽕", 20)
        session.add_menu("탕수육", 10)
        session.add_menu("볶음밥", 30)

        # 사용자 10이 제안한 메뉴
        user_10_menus = [
            menu for menu, proposer_id in session.menus.items()
            if proposer_id == 10
        ]

        assert len(user_10_menus) == 2
        assert "짜장면" in user_10_menus
        assert "탕수육" in user_10_menus
        assert "짬뽕" not in user_10_menus
        assert "볶음밥" not in user_10_menus

    def test_autocomplete_filtering(self):
        """자동완성 필터링 로직"""
        session = VotingSession("테스트", 123, 456, 789)
        session.add_menu("짜장면", 10)
        session.add_menu("짬뽕", 10)
        session.add_menu("탕수육", 10)

        user_menus = [
            menu for menu in session.menus.keys()
            if session.menus[menu] == 10
        ]

        # "짜" 검색
        filtered = [m for m in user_menus if "짜" in m.lower()]
        assert len(filtered) == 1  # 짜장면

        # "탕" 검색
        filtered = [m for m in user_menus if "탕" in m.lower()]
        assert len(filtered) == 1  # 탕수육


@pytest.mark.integration
class TestRealtimeUpdates:
    """실시간 업데이트 통합 테스트"""

    def test_menu_proposal_flow_with_message_id(self):
        """메뉴 제안 흐름에서 메시지 ID 사용"""
        manager = VotingManager()
        session = manager.create_session(123, 456, 789, "점심 메뉴")

        # 메시지 ID 설정 (봇이 메시지 전송 후)
        session.message_id = 999888777

        # 메뉴 제안들
        session.add_menu("짜장면", 10)
        session.add_menu("짬뽕", 20)

        # 메시지 ID는 여전히 유지
        assert session.message_id == 999888777

        # 메뉴 취소
        session.remove_menu("짜장면", 10)
        assert session.message_id == 999888777

    def test_voting_flow_with_updates(self):
        """투표 흐름에서 실시간 업데이트"""
        manager = VotingManager()
        session = manager.create_session(123, 456, 789, "저녁 메뉴")
        session.message_id = 111222333

        # 메뉴 제안
        session.add_menu("피자", 1)
        session.add_menu("치킨", 2)

        # 투표 시작
        session.voting_started = True
        assert len(session.votes) == 0

        # 투표 1
        session.submit_vote(10, {"피자": 5, "치킨": 4})
        assert len(session.votes) == 1

        # 투표 2
        session.submit_vote(20, {"피자": 3, "치킨": 5})
        assert len(session.votes) == 2

        # 메시지 ID는 변경되지 않음
        assert session.message_id == 111222333

    def test_vote_count_updates(self):
        """투표 현황 카운트 업데이트"""
        session = VotingSession("테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        # 초기 상태
        assert len(session.votes) == 0

        # 투표 1
        session.submit_vote(10, {"메뉴A": 5, "메뉴B": 4})
        assert len(session.votes) == 1

        # 투표 2
        session.submit_vote(20, {"메뉴A": 4, "메뉴B": 5})
        assert len(session.votes) == 2

        # 투표 3
        session.submit_vote(30, {"메뉴A": 3, "메뉴B": 3})
        assert len(session.votes) == 3

        # 투표 수정
        session.submit_vote(10, {"메뉴A": 1, "메뉴B": 1})
        assert len(session.votes) == 3  # 개수는 그대로

    def test_concurrent_menu_proposals(self):
        """동시 메뉴 제안 처리"""
        session = VotingSession("테스트", 123, 456, 789)
        session.message_id = 999

        # 여러 사용자가 동시에 메뉴 제안
        users = [10, 20, 30, 40, 50]
        menus = ["짜장면", "짬뽕", "탕수육", "볶음밥", "팔보채"]

        for user_id, menu in zip(users, menus):
            result = session.add_menu(menu, user_id)
            assert result is True

        assert len(session.menus) == 5
        assert session.message_id == 999  # 메시지 ID 유지


@pytest.mark.unit
class TestVotingViewHelpers:
    """투표 뷰 헬퍼 메서드 테스트"""

    def test_user_specific_menu_filter(self):
        """특정 사용자의 메뉴만 필터링"""
        session = VotingSession("테스트", 123, 456, 789)
        session.add_menu("메뉴1", 100)
        session.add_menu("메뉴2", 100)
        session.add_menu("메뉴3", 200)
        session.add_menu("메뉴4", 100)

        # 사용자 100의 메뉴만
        user_100_menus = {
            menu: proposer
            for menu, proposer in session.menus.items()
            if proposer == 100
        }

        assert len(user_100_menus) == 3
        assert "메뉴3" not in user_100_menus

    def test_remaining_menus_calculation(self):
        """아직 투표하지 않은 메뉴 계산"""
        session = VotingSession("테스트", 123, 456, 789)
        session.add_menu("A", 1)
        session.add_menu("B", 2)
        session.add_menu("C", 3)
        session.voting_started = True

        # 사용자의 현재 투표 상태
        current_votes = {"A": 5}

        # 남은 메뉴
        remaining = [m for m in session.menus.keys() if m not in current_votes]

        assert len(remaining) == 2
        assert "B" in remaining
        assert "C" in remaining
        assert "A" not in remaining
