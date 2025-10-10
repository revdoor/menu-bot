import aiohttp
import asyncio
from collections import defaultdict
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import discord

# 한국 시간대
KST = timezone(timedelta(hours=9))

# 메뉴 캐시: {'2025-10-10': {'중식': {...}, '석식': {...}}}
menu_cache = {}


def get_kst_date():
    """한국 시간 기준 오늘 날짜 문자열 반환"""
    return datetime.now(KST).strftime('%Y-%m-%d')


def clean_old_cache():
    """오늘 날짜가 아닌 캐시 데이터 삭제"""
    today = get_kst_date()
    to_delete = [date for date in menu_cache.keys() if date != today]

    for date in to_delete:
        del menu_cache[date]
        print(f"🗑️ 오래된 캐시 삭제: {date}")

    if to_delete:
        print(f"✓ {len(to_delete)}개의 오래된 캐시 삭제됨")


def get_cached_menu(meal_type):
    """캐시에서 메뉴 가져오기"""
    today = get_kst_date()

    if today in menu_cache and meal_type in menu_cache[today]:
        print(f"💾 캐시에서 메뉴 로드: {today} - {meal_type}")
        return menu_cache[today][meal_type]

    return None


def save_to_cache(meal_type, menu_data):
    """메뉴를 캐시에 저장"""
    today = get_kst_date()

    if today not in menu_cache:
        menu_cache[today] = {}

    menu_cache[today][meal_type] = menu_data
    print(f"💾 캐시에 저장: {today} - {meal_type}")


async def get_restaurants_menu_async(meal_type, restaurant_infos):
    """
    aiohttp를 사용한 비동기 메뉴 수집 (Playwright 없이)
    """
    menu_infos = defaultdict(list)

    url = "https://www.kaist.ac.kr/kr/html/campus/053001.html"

    async with aiohttp.ClientSession() as session:
        for rest_code, rest_name in restaurant_infos:
            try:
                print(f"\n{'=' * 50}")
                print(f"{rest_name} ({rest_code}) 처리 중...")

                # POST 요청 데이터
                data = {
                    'dvs_cd': rest_code
                }

                # POST 요청 보내기
                async with session.post(url, data=data) as response:
                    if response.status != 200:
                        print(f"{rest_name} - HTTP 에러: {response.status}")
                        continue

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # 테이블 찾기
                    table = soup.select_one('.table')
                    if not table:
                        print(f"{rest_name} - 테이블을 찾을 수 없음")
                        continue

                    # 헤더 파싱
                    headers = []
                    header_elements = table.select('thead th')
                    for header in header_elements:
                        text = header.get_text(strip=True)
                        if text:
                            headers.append(text)

                    print(f"{rest_name} - 헤더: {headers}")

                    if not headers:
                        print(f"{rest_name} - 헤더 없음")
                        continue

                    # 메뉴 파싱
                    rows = table.select('tbody tr')
                    print(f"{rest_name} - 행 개수: {len(rows)}")

                    for row_idx, row in enumerate(rows):
                        cells = row.select('td')

                        for i, cell in enumerate(cells):
                            if i < len(headers):
                                meal_type_raw = headers[i]
                                menu_content = cell.get_text(strip=True)

                                # meal_type 매칭
                                if meal_type not in meal_type_raw:
                                    continue

                                if not menu_content or menu_content in ["", "-", "운영안함"]:
                                    continue

                                print(f"    -> ✓ 메뉴 추가: {menu_content[:50]}...")
                                menu_infos[rest_name].append(menu_content)

                    print(f"{rest_name} - 최종 수집된 메뉴 개수: {len(menu_infos[rest_name])}")

                # 요청 간 딜레이 (서버 부하 방지)
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"{rest_name} - 처리 중 에러: {e}")
                import traceback
                traceback.print_exc()
                continue

    result = dict(menu_infos)
    print(f"\n{'=' * 50}")
    print(f"최종 결과: {len(result)}개 식당")
    for rest, menus in result.items():
        print(f"  {rest}: {len(menus)}개 메뉴")

    return result


async def get_menus_by_meal_type(meal_type):
    """
    meal_type에 따라 해당하는 식당들의 메뉴를 조회 (비동기)
    """
    restaurants_by_meal_type = {
        '중식': ['west', 'east1', 'east2'],
        '석식': ['west', 'east1']
    }

    restaurant_names = {
        'west': '서맛골(서측식당)',
        'east1': '동맛골(동측학생식당)',
        'east2': '동맛골(동측 교직원식당)'
    }

    if meal_type not in restaurants_by_meal_type:
        print(f"❌ 유효하지 않은 meal_type: {meal_type}")
        return {}

    restaurants = restaurants_by_meal_type[meal_type]
    restaurant_infos = [(code, restaurant_names[code]) for code in restaurants]

    print(f"\n{'=' * 50}")
    print(f"메뉴 조회 시작 - {meal_type}")
    print(f"대상 식당: {[name for _, name in restaurant_infos]}")
    print(f"{'=' * 50}")

    return await get_restaurants_menu_async(meal_type, restaurant_infos)


def format_menu_for_discord(meal_type, menu_infos):
    """Discord 메시지 형식으로 메뉴 포맷팅"""

    meal_info = {
        "조식": ("🌅 조식", "08:00-09:30"),
        "중식": ("🍽️ 중식", "11:30-13:30"),
        "석식": ("🌙 석식", "17:00-19:00")
    }

    emoji, time_range = meal_info.get(meal_type, ("🍴", ""))

    embed = discord.Embed(
        title=f"{emoji} KAIST 오늘의 식단",
        description=f"**{meal_type}** ({time_range})\n{datetime.now().strftime('%Y년 %m월 %d일')}",
        color=discord.Color.blue()
    )

    if not menu_infos:
        embed.add_field(
            name="❌ 운영 안함",
            value="오늘은 운영하는 식당이 없습니다.",
            inline=False
        )
        return embed

    for restaurant, menus in menu_infos.items():
        menu_text = ""
        for menu in menus:
            menu_lines = menu.split('\n')
            for line in menu_lines:
                line = line.strip()
                if line and line not in ['-', '']:
                    menu_text += f"• {line}\n"

        if menu_text:
            # Discord 필드는 1024자 제한이 있으므로 필요시 자르기
            if len(menu_text) > 1024:
                menu_text = menu_text[:1021] + "..."

            embed.add_field(
                name=f"📍 {restaurant}",
                value=menu_text,
                inline=False
            )

    embed.set_footer(text="KAIST 학생식당 • 메뉴는 사정에 따라 변경될 수 있습니다")

    return embed
