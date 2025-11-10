"""
KAIST 식당 메뉴 수집 모듈

주요 기능:
- 비동기 메뉴 크롤링
- 메뉴 캐싱 (날짜별)
- Discord Embed 포맷팅
"""
import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, Optional
import discord

from config import (
    KST,
    KAIST_MENU_URL,
    REQUEST_DELAY_SECONDS,
    DISCORD_FIELD_MAX_LENGTH,
    RESTAURANT_CODES,
    RESTAURANTS_BY_MEAL_TYPE,
    MEAL_INFO,
    LOG_MESSAGES,
    MENU_PARSE_KEYWORDS
)

# 로거 설정
logger = logging.getLogger(__name__)


class MenuCache:
    """
    날짜별 메뉴 캐시 관리 클래스

    구조: 오늘 날짜만 유지 (날짜가 바뀌면 자동 초기화)
    - _current_date: 현재 캐시된 날짜
    - _menus: {식사타입: {식당명: [메뉴1, 메뉴2, ...]}}
    """

    def __init__(self):
        self._current_date: Optional[str] = None
        self._menus: Dict[str, Dict[str, list[str]]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _get_kst_date() -> str:
        """한국 시간 기준 오늘 날짜 문자열 반환"""
        return datetime.now(KST).strftime('%Y-%m-%d')

    async def get(self, meal_type: str) -> Optional[Dict[str, list[str]]]:
        """
        캐시에서 메뉴 가져오기 (날짜가 바뀌면 자동으로 캐시 초기화)

        Args:
            meal_type: 식사 타입 ('중식', '석식' 등)

        Returns:
            캐시된 메뉴 또는 None
        """
        async with self._lock:
            today = self._get_kst_date()

            # 날짜가 바뀌면 캐시 초기화
            if self._current_date != today:
                if self._current_date:
                    logger.info(LOG_MESSAGES['cache_delete'].format(date=self._current_date))
                self._current_date = today
                self._menus = {}

            # 캐시 확인
            if meal_type in self._menus:
                logger.info(LOG_MESSAGES['cache_hit'].format(date=today, meal_type=meal_type))
                return self._menus[meal_type]

            return None

    async def set(self, meal_type: str, menu_data: Dict[str, list[str]]) -> None:
        """
        메뉴를 캐시에 저장

        Args:
            meal_type: 식사 타입
            menu_data: 메뉴 데이터 {식당명: [메뉴들]}
        """
        async with self._lock:
            today = self._get_kst_date()
            self._current_date = today
            self._menus[meal_type] = menu_data
            logger.info(LOG_MESSAGES['cache_save'].format(date=today, meal_type=meal_type))


# 전역 캐시 인스턴스
_menu_cache = MenuCache()


class MenuParser:
    """HTML 파싱 및 메뉴 추출 담당 클래스"""

    @staticmethod
    def parse_headers(table) -> list[str]:
        """테이블 헤더 파싱"""
        headers = []
        header_elements = table.select('thead th')
        for header in header_elements:
            text = header.get_text(strip=True)
            if text:
                headers.append(text)
        return headers

    @staticmethod
    def extract_menu_from_keyword(text: str, keyword: str) -> str:
        """
        키워드 및 그 이후의 텍스트 추출

        Args:
            text: 전체 메뉴 텍스트
            keyword: 검색할 키워드

        Returns:
            키워드 및 그 이후의 텍스트. 키워드가 없으면 원본 텍스트 반환
        """
        if not keyword or keyword not in text:
            return text

        # 키워드 위치 찾기
        keyword_index = text.find(keyword)
        if keyword_index == -1:
            return text

        # 키워드부터 끝까지 추출
        return text[keyword_index:].strip()

    @staticmethod
    def parse_menu_rows(
        table,
        headers: list[str],
        meal_type: str,
        restaurant_name: str
    ) -> list[str]:
        """테이블에서 메뉴 행 파싱"""
        menus = []
        rows = table.select('tbody tr')

        # 식당별 키워드 가져오기
        keyword = MENU_PARSE_KEYWORDS.get(restaurant_name, None)

        for row in rows:
            cells = row.select('td')

            for i, cell in enumerate(cells):
                if i >= len(headers):
                    continue

                meal_type_raw = headers[i]
                # separator=' '를 사용하여 태그 사이에 공백 추가
                menu_content = cell.get_text(separator=' ', strip=True)

                # meal_type 매칭 및 유효성 검증
                if meal_type not in meal_type_raw:
                    continue

                if not menu_content or menu_content in ["", "-", "운영안함"]:
                    continue

                # 키워드가 있으면 키워드 이후 텍스트만 추출
                if keyword:
                    menu_content = MenuParser.extract_menu_from_keyword(menu_content, keyword)

                menus.append(menu_content)

        return menus


class MenuCollector:
    """비동기 메뉴 수집 담당 클래스"""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.parser = MenuParser()

    async def fetch_restaurant_menu(
        self,
        restaurant_code: str,
        restaurant_name: str,
        meal_type: str
    ) -> list[str]:
        """특정 식당의 메뉴 가져오기"""
        try:
            data = {'dvs_cd': restaurant_code}

            async with self.session.post(KAIST_MENU_URL, data=data) as response:
                if response.status != 200:
                    logger.warning(f"{restaurant_name} - HTTP {response.status} 에러")
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # 테이블 찾기
                table = soup.select_one('.table')
                if not table:
                    return []

                # 헤더 및 메뉴 파싱
                headers = self.parser.parse_headers(table)
                if not headers:
                    return []

                menus = self.parser.parse_menu_rows(table, headers, meal_type, restaurant_name)
                logger.debug(f"{restaurant_name}: {len(menus)}개 메뉴")

                return menus

        except aiohttp.ClientError as e:
            logger.error(f"{restaurant_name} - 네트워크 에러: {e}")
            return []
        except Exception as e:
            logger.error(f"{restaurant_name} - 에러: {e}")
            return []

    async def fetch_all_restaurants(
        self,
        meal_type: str,
        restaurant_infos: list[tuple[str, str]]
    ) -> Dict[str, list[str]]:
        """여러 식당의 메뉴를 비동기로 수집"""
        menu_infos = {}

        for rest_code, rest_name in restaurant_infos:
            menus = await self.fetch_restaurant_menu(rest_code, rest_name, meal_type)
            if menus:
                menu_infos[rest_name] = menus

            # 서버 부하 방지를 위한 딜레이
            await asyncio.sleep(REQUEST_DELAY_SECONDS)

        logger.info(f"최종 결과: {len(menu_infos)}개 식당")
        return menu_infos


async def get_menus_by_meal_type(meal_type: str) -> Dict[str, list[str]]:
    """
    meal_type에 따라 해당하는 식당들의 메뉴를 조회 (캐싱 적용)

    Args:
        meal_type: '중식' 또는 '석식'

    Returns:
        {식당명: [메뉴1, 메뉴2, ...]} 형태의 딕셔너리
    """
    # 캐시 확인 (자동으로 오래된 캐시 정리됨)
    cached = await _menu_cache.get(meal_type)
    if cached is not None:
        return cached

    # 유효성 검증
    if meal_type not in RESTAURANTS_BY_MEAL_TYPE:
        logger.error(f"❌ 유효하지 않은 meal_type: {meal_type}")
        return {}

    # 식당 정보 준비
    restaurants = RESTAURANTS_BY_MEAL_TYPE[meal_type]
    restaurant_infos = [(code, RESTAURANT_CODES[code]) for code in restaurants]

    logger.info(f"메뉴 조회: {meal_type}")

    # 메뉴 수집
    async with aiohttp.ClientSession() as session:
        collector = MenuCollector(session)
        menus = await collector.fetch_all_restaurants(meal_type, restaurant_infos)

    # 캐시에 저장
    if menus:
        await _menu_cache.set(meal_type, menus)

    return menus


def format_menu_for_discord(
    meal_type: str,
    menu_infos: Dict[str, list[str]]
) -> discord.Embed:
    """
    Discord 메시지 형식으로 메뉴 포맷팅

    Args:
        meal_type: 식사 타입
        menu_infos: 식당별 메뉴 딕셔너리

    Returns:
        Discord Embed 객체
    """
    emoji, time_range = MEAL_INFO.get(meal_type, ("🍴", ""))

    embed = discord.Embed(
        title=f"{emoji} KAIST 오늘의 식단",
        description=f"**{meal_type}** ({time_range})\n{datetime.now().strftime('%Y년 %m월 %d일')}",
        color=discord.Color.blue()
    )

    # 메뉴가 없는 경우
    if not menu_infos:
        embed.add_field(
            name="❌ 운영 안함",
            value="오늘은 운영하는 식당이 없습니다.",
            inline=False
        )
        return embed

    # 각 식당별 메뉴 추가
    for restaurant, menus in menu_infos.items():
        menu_text = _format_menu_text(menus)

        if menu_text:
            embed.add_field(
                name=f"📍 {restaurant}",
                value=menu_text,
                inline=False
            )

    embed.set_footer(text="KAIST 학생식당 • 메뉴는 사정에 따라 변경될 수 있습니다")

    return embed


def _format_menu_text(menus: list[str]) -> str:
    """메뉴 리스트를 Discord 필드 형식으로 변환"""
    menu_text = ""

    for menu in menus:
        menu_lines = menu.split('\n')
        for line in menu_lines:
            line = line.strip()
            if line and line not in ['-', '']:
                menu_text += f"• {line}\n"

    # Discord 필드 길이 제한 처리
    if len(menu_text) > DISCORD_FIELD_MAX_LENGTH:
        menu_text = menu_text[:DISCORD_FIELD_MAX_LENGTH - 3] + "..."

    return menu_text
