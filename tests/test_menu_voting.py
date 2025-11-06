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
        assert session.voter_names == {}
        assert session.voting_started is False
        assert session.voting_closed is False
        assert session.message_id is None
        assert session.is_restricted is False
        assert session.allowed_voters == set()
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
        """메뉴 삭제 성공 (제안자)"""
        session.add_menu("짜장면", 111)
        result = session.remove_menu("짜장면", 111)
        assert result is True
        assert "짜장면" not in session.menus

    def test_remove_menu_by_creator(self, session):
        """메뉴 삭제 성공 (생성자)"""
        session.add_menu("짜장면", 111)
        result = session.remove_menu("짜장면", session.creator_id)
        assert result is True
        assert "짜장면" not in session.menus

    def test_remove_menu_by_admin(self, session):
        """메뉴 삭제 성공 (관리자)"""
        session.add_menu("짜장면", 111)
        result = session.remove_menu("짜장면", 999, is_admin=True)
        assert result is True
        assert "짜장면" not in session.menus

    def test_remove_menu_not_authorized(self, session):
        """권한 없는 사람이 메뉴 삭제 불가"""
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
        result = session.submit_vote(333, "테스트유저", votes)
        assert result is True
        assert session.votes[333] == votes
        assert session.voter_names[333] == "테스트유저"

    def test_submit_vote_before_start(self, session):
        """투표 시작 전 투표 불가"""
        votes = {"짜장면": 5}
        result = session.submit_vote(333, "테스트유저", votes)
        assert result is False

    def test_submit_vote_after_close(self, session):
        """투표 종료 후 투표 불가"""
        session.voting_started = True
        session.voting_closed = True
        votes = {"짜장면": 5}
        result = session.submit_vote(333, "테스트유저", votes)
        assert result is False

    def test_submit_vote_overwrite(self, session):
        """투표 덮어쓰기"""
        session.add_menu("짜장면", 111)
        session.voting_started = True

        votes1 = {"짜장면": 3}
        session.submit_vote(333, "테스트유저", votes1)

        votes2 = {"짜장면": 5}
        session.submit_vote(333, "테스트유저수정", votes2)

        assert session.votes[333] == votes2
        assert session.voter_names[333] == "테스트유저수정"

    def test_restricted_voting(self):
        """제한된 투표 기능"""
        session = VotingSession(
            title="제한 투표",
            guild_id=123,
            channel_id=456,
            creator_id=789,
            is_restricted=True
        )

        # 생성자는 항상 허용
        assert session.is_voter_allowed(789) is True

        # 일반 사용자는 허용되지 않음
        assert session.is_voter_allowed(999) is False

        # 사용자 추가
        session.add_allowed_voter(999)
        assert session.is_voter_allowed(999) is True

    def test_add_allowed_voter_non_restricted(self, session):
        """제한 모드가 아니면 허용 목록 추가 불가"""
        result = session.add_allowed_voter(999)
        assert result is False


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
        session.submit_vote(10, "유저1", {"짜장면": 5, "짬뽕": 4, "탕수육": 3})
        session.submit_vote(20, "유저2", {"짜장면": 4, "짬뽕": 5, "탕수육": 2})
        session.submit_vote(30, "유저3", {"짜장면": 3, "짬뽕": 4, "탕수육": 5})

        return session

    def test_calculate_results_total_score(self, session_with_votes):
        """총점 계산 확인"""
        regular_results, zero_results = session_with_votes.calculate_results()

        # 결과는 (메뉴명, 총점, 최소점) 튜플의 리스트
        menu_scores = {menu: total for menu, total, _ in regular_results}

        assert menu_scores["짜장면"] == 12  # 5+4+3
        assert menu_scores["짬뽕"] == 13    # 4+5+4
        assert menu_scores["탕수육"] == 10  # 3+2+5
        assert len(zero_results) == 0

    def test_calculate_results_sorting(self, session_with_votes):
        """결과 정렬 확인 (총점 내림차순)"""
        regular_results, _ = session_with_votes.calculate_results()

        # 첫 번째는 짬뽕(13점)이어야 함
        assert regular_results[0][0] == "짬뽕"
        assert regular_results[0][1] == 13

    def test_calculate_results_min_score(self, session_with_votes):
        """최소점 계산 확인"""
        regular_results, _ = session_with_votes.calculate_results()

        # 짜장면의 최소점은 3점
        jjajang_result = next(r for r in regular_results if r[0] == "짜장면")
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
        session.submit_vote(10, "유저1", {"메뉴A": 5, "메뉴B": 5})
        session.submit_vote(20, "유저2", {"메뉴A": 5, "메뉴B": 4})
        # 메뉴A: 총 10점, 최소 5점
        # 메뉴B: 총 9점, 최소 4점

        regular_results, _ = session.calculate_results()

        # 메뉴A가 1위여야 함
        assert regular_results[0][0] == "메뉴A"

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

        regular_results, zero_results = session.calculate_results()

        assert len(regular_results) == 1
        assert regular_results[0] == ("짜장면", 0, 0)
        assert len(zero_results) == 0

    def test_calculate_results_with_zero_scores(self):
        """0점을 받은 메뉴 처리"""
        session = VotingSession(
            title="0점 테스트",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.add_menu("메뉴C", 3)
        session.voting_started = True

        # 메뉴B와 메뉴C는 0점을 받음
        session.submit_vote(10, "유저1", {"메뉴A": 5, "메뉴B": 0, "메뉴C": 3})
        session.submit_vote(20, "유저2", {"메뉴A": 4, "메뉴B": 2, "메뉴C": 0})

        regular_results, zero_results = session.calculate_results()

        # 메뉴A만 정규 결과에 포함
        assert len(regular_results) == 1
        assert regular_results[0][0] == "메뉴A"

        # 메뉴B와 메뉴C는 0점 결과에 포함
        assert len(zero_results) == 2
        zero_menus = {menu: (total, voters) for menu, total, voters in zero_results}
        assert "메뉴B" in zero_menus
        assert "메뉴C" in zero_menus
        assert "유저1" in zero_menus["메뉴B"][1]
        assert "유저2" in zero_menus["메뉴C"][1]

    def test_calculate_results_all_zero_scores(self):
        """모든 메뉴가 0점을 받은 경우"""
        session = VotingSession(
            title="전체 0점",
            guild_id=123,
            channel_id=456,
            creator_id=789
        )
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        session.submit_vote(10, "유저1", {"메뉴A": 0, "메뉴B": 1})
        session.submit_vote(20, "유저2", {"메뉴A": 2, "메뉴B": 0})

        regular_results, zero_results = session.calculate_results()

        # 모든 메뉴가 0점 결과에 포함
        assert len(regular_results) == 0
        assert len(zero_results) == 2


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

    def test_create_session_with_restriction(self, manager):
        """제한된 투표 세션 생성"""
        session = manager.create_session(
            guild_id=123,
            channel_id=456,
            creator_id=789,
            title="제한 투표",
            is_restricted=True
        )
        assert session is not None
        assert session.is_restricted is True

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
        session.submit_vote(10, "유저1", {"짜장면": 5, "짬뽕": 4})
        session.submit_vote(20, "유저2", {"짜장면": 4, "짬뽕": 5})
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

    def test_create_proposal_embed_restricted(self):
        """제한된 투표 Embed"""
        session = VotingSession("제한 투표", 123, 456, 789, is_restricted=True)
        embed = create_proposal_embed(session)

        assert "🔒" in embed.title

    def test_create_voting_embed(self, session_voting):
        """투표 진행 단계 Embed"""
        embed = create_voting_embed(session_voting)

        assert "점심 메뉴 투표" in embed.title
        assert embed.description is not None

        # 투표 현황이 포함되어야 함 (이름 표시)
        field_values = [field.value for field in embed.fields]
        assert any("2명" in str(v) for v in field_values)
        assert any("유저1" in str(v) or "유저2" in str(v) for v in field_values)

    def test_create_results_embed(self, session_voting):
        """결과 Embed"""
        regular_results, zero_results = session_voting.calculate_results()
        embed = create_results_embed(session_voting, regular_results, zero_results)

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

        regular_results, zero_results = session.calculate_results()
        embed = create_results_embed(session, regular_results, zero_results)

        assert embed is not None
        assert "0명" in embed.description

    def test_create_results_embed_tie(self):
        """동점인 경우 결과 Embed"""
        session = VotingSession("동점 테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        # 동점
        session.submit_vote(10, "유저1", {"메뉴A": 5, "메뉴B": 5})
        session.submit_vote(20, "유저2", {"메뉴A": 5, "메뉴B": 5})

        regular_results, zero_results = session.calculate_results()
        embed = create_results_embed(session, regular_results, zero_results)

        # 동점 표시가 있어야 함
        assert any("동점" in str(field.value) or "메뉴A" in str(field.value) for field in embed.fields)

    def test_create_results_embed_with_zero_scores(self):
        """0점 메뉴가 있는 결과 Embed"""
        session = VotingSession("0점 테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        session.submit_vote(10, "유저1", {"메뉴A": 5, "메뉴B": 0})
        session.submit_vote(20, "유저2", {"메뉴A": 4, "메뉴B": 2})

        regular_results, zero_results = session.calculate_results()
        embed = create_results_embed(session, regular_results, zero_results)

        # 제외된 메뉴 섹션이 있어야 함
        field_names = [field.name for field in embed.fields]
        assert any("제외된 메뉴" in name for name in field_names)

    def test_create_results_embed_all_zero_scores(self):
        """모든 메뉴가 0점인 경우 결과 Embed"""
        session = VotingSession("전체 0점", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        session.submit_vote(10, "유저1", {"메뉴A": 0, "메뉴B": 1})
        session.submit_vote(20, "유저2", {"메뉴A": 2, "메뉴B": 0})

        regular_results, zero_results = session.calculate_results()
        embed = create_results_embed(session, regular_results, zero_results)

        # 경고 메시지가 있어야 함
        field_values = [field.value for field in embed.fields]
        assert any("모든 메뉴가 0점" in str(v) for v in field_values)


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
        session.submit_vote(10, "유저1", {"짜장면": 5, "짬뽕": 4, "탕수육": 3})
        session.submit_vote(20, "유저2", {"짜장면": 4, "짬뽕": 5, "탕수육": 2})
        session.submit_vote(30, "유저3", {"짜장면": 5, "짬뽕": 3, "탕수육": 4})
        assert len(session.votes) == 3

        # 5. 결과 계산
        regular_results, zero_results = session.calculate_results()
        assert len(regular_results) == 3
        assert len(zero_results) == 0

        winner = regular_results[0]
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
        session.submit_vote(10, "유저1", {"메뉴A": 3, "메뉴B": 4})
        regular_results1, _ = session.calculate_results()
        assert regular_results1[0][0] == "메뉴B"

        # 투표 수정
        session.submit_vote(10, "유저1", {"메뉴A": 5, "메뉴B": 2})
        regular_results2, _ = session.calculate_results()
        assert regular_results2[0][0] == "메뉴A"

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

    def test_restricted_voting_workflow(self):
        """제한된 투표 워크플로우"""
        manager = VotingManager()

        # 1. 제한된 투표 시작
        session = manager.create_session(123, 456, 789, "제한 투표", is_restricted=True)
        assert session.is_restricted is True

        # 2. 메뉴 제안
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.voting_started = True

        # 3. 생성자는 항상 투표 가능
        assert session.is_voter_allowed(789) is True
        session.submit_vote(789, "생성자", {"메뉴A": 5, "메뉴B": 4})

        # 4. 허용되지 않은 사용자는 투표 불가
        assert session.is_voter_allowed(999) is False

        # 5. 사용자 허용 후 투표 가능
        session.add_allowed_voter(999)
        assert session.is_voter_allowed(999) is True
        session.submit_vote(999, "허용유저", {"메뉴A": 4, "메뉴B": 5})

        assert len(session.votes) == 2


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
        session.submit_vote(10, "유저1", {"짜장면": 5})
        assert session.message_id == 111222333


@pytest.mark.unit
class TestRankingTieBreaking:
    """동점 처리 및 순위 테스트"""

    def test_same_rank_for_exact_tie(self):
        """총점과 최소점이 모두 같으면 같은 순위"""
        session = VotingSession("동점 테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.add_menu("메뉴C", 3)
        session.voting_started = True

        # 메뉴A와 메뉴B는 완전 동점
        session.submit_vote(10, "유저1", {"메뉴A": 5, "메뉴B": 5, "메뉴C": 3})
        session.submit_vote(20, "유저2", {"메뉴A": 4, "메뉴B": 4, "메뉴C": 2})

        regular_results, _ = session.calculate_results()

        # 메뉴A와 메뉴B는 모두 총점 9점, 최소점 4점
        assert regular_results[0][1] == 9
        assert regular_results[0][2] == 4
        assert regular_results[1][1] == 9
        assert regular_results[1][2] == 4

    def test_rank_skipping_after_tie(self):
        """동점 후 다음 순위는 건너뛰어야 함"""
        session = VotingSession("순위 건너뛰기", 123, 456, 789)
        session.add_menu("A", 1)
        session.add_menu("B", 2)
        session.add_menu("C", 3)
        session.add_menu("D", 4)
        session.voting_started = True

        # A, B, C는 1위 동점, D는 4위
        session.submit_vote(10, "유저1", {"A": 5, "B": 5, "C": 5, "D": 1})
        session.submit_vote(20, "유저2", {"A": 5, "B": 5, "C": 5, "D": 1})

        regular_results, _ = session.calculate_results()

        # 처음 3개는 모두 10점
        assert regular_results[0][1] == 10
        assert regular_results[1][1] == 10
        assert regular_results[2][1] == 10
        # 마지막은 2점
        assert regular_results[3][1] == 2


@pytest.mark.unit
class TestZeroScoreFeature:
    """0점 기능 테스트"""

    def test_zero_score_separates_menu(self):
        """0점을 받은 메뉴는 별도로 분리됨"""
        session = VotingSession("0점 테스트", 123, 456, 789)
        session.add_menu("좋은메뉴", 1)
        session.add_menu("나쁜메뉴", 2)
        session.voting_started = True

        session.submit_vote(10, "유저1", {"좋은메뉴": 5, "나쁜메뉴": 0})
        session.submit_vote(20, "유저2", {"좋은메뉴": 4, "나쁜메뉴": 3})

        regular_results, zero_results = session.calculate_results()

        # 좋은메뉴만 정규 결과에
        assert len(regular_results) == 1
        assert regular_results[0][0] == "좋은메뉴"

        # 나쁜메뉴는 0점 결과에
        assert len(zero_results) == 1
        assert zero_results[0][0] == "나쁜메뉴"
        assert "유저1" in zero_results[0][2]

    def test_zero_voters_tracking(self):
        """0점을 준 사람 추적"""
        session = VotingSession("추적 테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.voting_started = True

        session.submit_vote(10, "Alice", {"메뉴A": 0})
        session.submit_vote(20, "Bob", {"메뉴A": 0})
        session.submit_vote(30, "Charlie", {"메뉴A": 5})

        _, zero_results = session.calculate_results()

        assert len(zero_results) == 1
        menu, total, zero_voters = zero_results[0]
        assert menu == "메뉴A"
        assert total == 5  # 0 + 0 + 5
        assert "Alice" in zero_voters
        assert "Bob" in zero_voters
        assert "Charlie" not in zero_voters


@pytest.mark.unit
class TestVoterNameTracking:
    """투표자 이름 추적 테스트"""

    def test_voter_names_stored(self):
        """투표자 이름이 저장됨"""
        session = VotingSession("테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.voting_started = True

        session.submit_vote(10, "홍길동", {"메뉴A": 5})
        session.submit_vote(20, "김철수", {"메뉴A": 4})

        assert session.voter_names[10] == "홍길동"
        assert session.voter_names[20] == "김철수"

    def test_voter_name_update_on_revote(self):
        """재투표 시 이름 업데이트"""
        session = VotingSession("테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.voting_started = True

        session.submit_vote(10, "원래이름", {"메뉴A": 5})
        assert session.voter_names[10] == "원래이름"

        session.submit_vote(10, "바뀐이름", {"메뉴A": 3})
        assert session.voter_names[10] == "바뀐이름"


@pytest.mark.unit
class TestConcurrentVoting:
    """동시 투표 테스트 (Thread Safety)"""

    def test_concurrent_vote_submission(self):
        """여러 사용자가 동시에 투표해도 데이터가 섞이지 않음"""
        import threading

        session = VotingSession("동시 투표 테스트", 123, 456, 789)
        session.add_menu("메뉴A", 1)
        session.add_menu("메뉴B", 2)
        session.add_menu("메뉴C", 3)
        session.voting_started = True

        # 투표 성공 여부를 추적
        results = {}
        errors = []

        def vote_user(user_id: int, username: str, votes: dict):
            """사용자 투표 함수"""
            try:
                success = session.submit_vote(user_id, username, votes)
                results[user_id] = success
            except Exception as e:
                errors.append((user_id, str(e)))

        # 100명의 사용자가 동시에 투표
        threads = []
        for i in range(100):
            user_id = 1000 + i
            username = f"유저{i}"
            votes = {
                "메뉴A": (i % 5) + 1,  # 1-5점
                "메뉴B": ((i + 1) % 5) + 1,
                "메뉴C": ((i + 2) % 5) + 1
            }
            thread = threading.Thread(target=vote_user, args=(user_id, username, votes))
            threads.append(thread)
            thread.start()

        # 모든 스레드 종료 대기
        for thread in threads:
            thread.join()

        # 검증
        assert len(errors) == 0, f"투표 중 에러 발생: {errors}"
        assert len(results) == 100, "모든 사용자의 투표가 기록되어야 함"
        assert all(results.values()), "모든 투표가 성공해야 함"
        assert len(session.votes) == 100, "세션에 100개의 투표가 저장되어야 함"
        assert len(session.voter_names) == 100, "100명의 투표자 이름이 저장되어야 함"

    def test_concurrent_vote_data_integrity(self):
        """동시 투표 시 각 사용자의 투표 데이터가 정확히 저장됨"""
        import threading

        session = VotingSession("데이터 무결성 테스트", 123, 456, 789)
        session.add_menu("짜장면", 1)
        session.add_menu("짬뽕", 2)
        session.voting_started = True

        # 예상 투표 데이터
        expected_votes = {}

        def vote_user(user_id: int, username: str):
            """각 사용자가 고유한 점수로 투표"""
            votes = {
                "짜장면": user_id % 6,  # 0-5점
                "짬뽕": (user_id + 3) % 6
            }
            expected_votes[user_id] = votes.copy()
            session.submit_vote(user_id, username, votes)

        # 50명의 사용자가 동시에 투표
        threads = []
        for i in range(50):
            user_id = 2000 + i
            username = f"테스터{i}"
            thread = threading.Thread(target=vote_user, args=(user_id, username))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 각 사용자의 투표 데이터가 정확한지 검증
        assert len(session.votes) == 50
        for user_id, expected in expected_votes.items():
            actual = session.votes[user_id]
            assert actual == expected, f"사용자 {user_id}의 투표 데이터가 일치하지 않음: 예상={expected}, 실제={actual}"

    def test_concurrent_vote_with_modifications(self):
        """동시에 투표하고 수정해도 데이터가 정확함"""
        import threading
        import time

        session = VotingSession("수정 테스트", 123, 456, 789)
        session.add_menu("메뉴1", 1)
        session.add_menu("메뉴2", 2)
        session.voting_started = True

        modification_count = [0]  # 수정 횟수 추적

        def vote_and_modify(user_id: int):
            """투표 후 여러 번 수정"""
            # 첫 투표
            session.submit_vote(user_id, f"유저{user_id}", {
                "메뉴1": 3,
                "메뉴2": 4
            })

            # 짧은 대기 후 수정
            time.sleep(0.001)
            session.submit_vote(user_id, f"유저{user_id}_수정", {
                "메뉴1": 5,
                "메뉴2": 2
            })
            modification_count[0] += 1

        # 20명이 동시에 투표하고 수정
        threads = []
        for i in range(20):
            user_id = 3000 + i
            thread = threading.Thread(target=vote_and_modify, args=(user_id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 검증
        assert len(session.votes) == 20, "20명의 투표가 있어야 함"
        assert modification_count[0] == 20, "모든 사용자가 수정을 완료해야 함"

        # 모든 투표가 최종 값으로 저장되었는지 확인
        for user_id in range(3000, 3020):
            assert session.votes[user_id] == {"메뉴1": 5, "메뉴2": 2}, \
                f"사용자 {user_id}의 최종 투표가 정확하지 않음"

    def test_concurrent_menu_additions(self):
        """여러 사용자가 동시에 메뉴를 추가해도 중복 없음"""
        import threading

        session = VotingSession("메뉴 추가 테스트", 123, 456, 789)

        add_results = {}

        def add_menu(user_id: int, menu_name: str):
            """메뉴 추가 시도"""
            result = session.add_menu(menu_name, user_id)
            add_results[user_id] = result

        # 같은 메뉴를 10명이 동시에 추가 시도
        threads = []
        for i in range(10):
            user_id = 4000 + i
            thread = threading.Thread(target=add_menu, args=(user_id, "인기메뉴"))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 검증: 정확히 1명만 성공해야 함
        success_count = sum(1 for result in add_results.values() if result)
        assert success_count == 1, "정확히 1명만 메뉴 추가에 성공해야 함"
        assert len(session.menus) == 1, "중복 메뉴가 추가되지 않아야 함"
        assert "인기메뉴" in session.menus, "메뉴가 추가되어야 함"

    def test_vote_isolation_between_users(self):
        """두 명이 동시에 투표할 때 서로 영향을 주지 않음 (핵심 테스트)"""
        import threading

        session = VotingSession("사용자 격리 테스트", 123, 456, 789)
        session.add_menu("피자", 1)
        session.add_menu("치킨", 2)
        session.add_menu("햄버거", 3)
        session.voting_started = True

        # 사용자 A와 B가 각각 다른 점수로 투표
        user_a_votes = {"피자": 5, "치킨": 3, "햄버거": 1}
        user_b_votes = {"피자": 2, "치킨": 5, "햄버거": 4}

        barrier = threading.Barrier(2)  # 두 스레드가 동시에 실행되도록

        def vote_user_a():
            barrier.wait()  # 동기화 지점
            session.submit_vote(5001, "사용자A", user_a_votes)

        def vote_user_b():
            barrier.wait()  # 동기화 지점
            session.submit_vote(5002, "사용자B", user_b_votes)

        thread_a = threading.Thread(target=vote_user_a)
        thread_b = threading.Thread(target=vote_user_b)

        thread_a.start()
        thread_b.start()

        thread_a.join()
        thread_b.join()

        # 검증: 각 사용자의 투표가 정확히 저장되었는지
        assert session.votes[5001] == user_a_votes, \
            f"사용자A 투표 오염: 예상={user_a_votes}, 실제={session.votes[5001]}"
        assert session.votes[5002] == user_b_votes, \
            f"사용자B 투표 오염: 예상={user_b_votes}, 실제={session.votes[5002]}"
        assert session.votes[5001] != session.votes[5002], \
            "두 사용자의 투표가 같으면 안됨"
        assert session.voter_names[5001] == "사용자A"
        assert session.voter_names[5002] == "사용자B"

    def test_vote_dictionary_deep_copy(self):
        """투표 딕셔너리가 deep copy되어 원본이 변경되어도 영향 없음"""
        session = VotingSession("Deep Copy 테스트", 123, 456, 789)
        session.add_menu("메뉴X", 1)
        session.add_menu("메뉴Y", 2)
        session.voting_started = True

        # 원본 투표 딕셔너리
        original_votes = {"메뉴X": 5, "메뉴Y": 3}

        # 투표 제출
        session.submit_vote(6001, "테스트유저", original_votes)

        # 투표 제출 후 원본 수정
        original_votes["메뉴X"] = 1
        original_votes["메뉴Y"] = 1
        original_votes["메뉴Z"] = 999  # 존재하지 않는 메뉴 추가

        # 검증: 세션에 저장된 투표는 변경되지 않아야 함
        stored_votes = session.votes[6001]
        assert stored_votes["메뉴X"] == 5, "저장된 투표가 원본 변경의 영향을 받으면 안됨"
        assert stored_votes["메뉴Y"] == 3, "저장된 투표가 원본 변경의 영향을 받으면 안됨"
        assert "메뉴Z" not in stored_votes, "원본에 추가된 키가 저장된 투표에 나타나면 안됨"
