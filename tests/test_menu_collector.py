"""menu_collector.py 테스트"""
import pytest
from unittest.mock import patch
from bs4 import BeautifulSoup

from menu_collector import MenuCache, MenuParser, format_menu_for_discord, _format_menu_text


@pytest.mark.unit
class TestMenuCache:
    """MenuCache 클래스 테스트"""

    @pytest.fixture
    def cache(self):
        """각 테스트마다 새로운 캐시 인스턴스 생성"""
        return MenuCache()

    @pytest.mark.asyncio
    async def test_cache_initialization(self, cache):
        """캐시 초기화"""
        assert cache._current_date is None
        assert cache._menus == {}

    @pytest.mark.asyncio
    async def test_get_empty_cache(self, cache):
        """빈 캐시에서 get하면 None 반환"""
        assert await cache.get('중식') is None

    @pytest.mark.asyncio
    async def test_set_and_get_cache(self, cache, sample_menu_data):
        """캐시 저장 및 조회"""
        await cache.set('중식', sample_menu_data)
        assert await cache.get('중식') == sample_menu_data

    @pytest.mark.asyncio
    async def test_multiple_meal_types(self, cache, sample_menu_data):
        """여러 식사 타입 캐싱"""
        dinner_data = {'식당1': ['메뉴A', '메뉴B']}

        await cache.set('중식', sample_menu_data)
        await cache.set('석식', dinner_data)

        assert await cache.get('중식') == sample_menu_data
        assert await cache.get('석식') == dinner_data

    @pytest.mark.asyncio
    @patch('menu_collector.MenuCache._get_kst_date')
    async def test_cache_invalidation_on_date_change(self, mock_get_date, cache, sample_menu_data):
        """날짜가 바뀌면 캐시 초기화"""
        mock_get_date.return_value = '2025-10-30'
        await cache.set('중식', sample_menu_data)
        assert await cache.get('중식') == sample_menu_data

        # 날짜 변경
        mock_get_date.return_value = '2025-10-31'
        assert await cache.get('중식') is None


@pytest.mark.unit
class TestMenuParser:
    """MenuParser 클래스 테스트"""

    @pytest.fixture
    def parser(self):
        return MenuParser()

    def test_parse_headers(self, parser, sample_html_menu):
        """HTML 테이블 헤더 파싱"""
        table = BeautifulSoup(sample_html_menu, 'html.parser').select_one('.table')
        headers = parser.parse_headers(table)
        assert '중식' in headers and '석식' in headers

    def test_parse_headers_empty_table(self, parser):
        """빈 테이블 처리"""
        html = '<table class="table"><thead></thead></table>'
        table = BeautifulSoup(html, 'html.parser').select_one('.table')
        assert parser.parse_headers(table) == []

    def test_parse_menu_rows(self, parser, sample_html_menu):
        """메뉴 행 파싱"""
        table = BeautifulSoup(sample_html_menu, 'html.parser').select_one('.table')
        headers = parser.parse_headers(table)
        menus = parser.parse_menu_rows(table, headers, '중식')
        assert len(menus) > 0 and '김치찌개' in menus[0]

    def test_parse_menu_rows_skip_invalid(self, parser):
        """유효하지 않은 메뉴 제외"""
        html = """
        <table class="table">
            <thead><tr><th>중식</th></tr></thead>
            <tbody>
                <tr><td>-</td></tr>
                <tr><td>운영안함</td></tr>
                <tr><td>김치찌개</td></tr>
            </tbody>
        </table>
        """
        table = BeautifulSoup(html, 'html.parser').select_one('.table')
        headers = parser.parse_headers(table)
        menus = parser.parse_menu_rows(table, headers, '중식')
        assert menus == ['김치찌개']


@pytest.mark.unit
class TestMenuFormatting:
    """메뉴 포맷팅 함수 테스트"""

    def test_format_menu_text_basic(self):
        """기본 메뉴 텍스트 포맷팅"""
        result = _format_menu_text(['김치찌개\n밥\n김치', '된장찌개\n밥'])
        assert all(item in result for item in ['• 김치찌개', '• 밥', '• 김치', '• 된장찌개'])

    def test_format_menu_text_filters_empty_lines(self):
        """빈 줄 제거"""
        result = _format_menu_text(['김치찌개\n\n밥', '-\n김치'])
        assert result.count('•') == 3  # '-'는 필터링됨

    def test_format_menu_text_length_limit(self):
        """길이 제한 (1024자)"""
        result = _format_menu_text(['메뉴' * 500])
        assert len(result) <= 1024

    def test_format_menu_for_discord_empty(self):
        """빈 메뉴 처리"""
        embed = format_menu_for_discord('중식', {})
        assert any('운영 안함' in field.name or '운영 안함' in field.value for field in embed.fields)

    def test_format_menu_for_discord_with_data(self, sample_menu_data):
        """메뉴 데이터가 있을 때 Embed 생성"""
        embed = format_menu_for_discord('중식', sample_menu_data)
        assert 'KAIST' in embed.title and '식단' in embed.title

        field_names = [field.name for field in embed.fields]
        assert any('서맛골' in name for name in field_names)
        assert any('동맛골' in name for name in field_names)
        assert embed.footer.text is not None
