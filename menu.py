import aiohttp
import asyncio
from collections import defaultdict
from bs4 import BeautifulSoup


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


# Playwright 관련 함수들 (호환성 유지 - 더미 함수)
async def init_browser():
    """더미 함수 - Playwright 사용 안 함"""
    print("✓ 경량 버전: 브라우저 초기화 불필요")
    return True


async def close_browser():
    """더미 함수 - Playwright 사용 안 함"""
    print("✓ 경량 버전: 브라우저 종료 불필요")
    pass