import time
import asyncio
from collections import defaultdict
from playwright.async_api import async_playwright


async def get_restaurants_menu_async(meal_type, restaurant_infos):
    """
    Playwright를 사용한 비동기 메뉴 수집
    """
    menu_infos = defaultdict(list)

    async with async_playwright() as p:
        try:
            # Chromium 브라우저 실행
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--no-zygote',
                    '--single-process',
                    '--disable-web-security',
                ]
            )

            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )

            page = await context.new_page()

            print("페이지 로딩 시작")
            await page.goto("https://www.kaist.ac.kr/kr/html/campus/053001.html",
                            wait_until='domcontentloaded',
                            timeout=30000)

            # 페이지 로드 대기
            await page.wait_for_selector(".s0503", timeout=15000)
            print("페이지 로딩 완료")

            for rest_code, rest_name in restaurant_infos:
                try:
                    print(f"{rest_name} 처리 중...")

                    # JavaScript 함수 실행
                    await page.evaluate(f"ActFodlst('{rest_code}')")
                    await asyncio.sleep(2.5)

                    # 테이블 로드 대기
                    try:
                        await page.wait_for_selector(".table", timeout=8000)
                    except:
                        print(f"{rest_name} - 테이블 로드 실패")
                        continue

                    # 헤더 파싱
                    try:
                        header_elements = await page.query_selector_all(".table thead th")
                        headers = []
                        for header in header_elements:
                            text = await header.inner_text()
                            text = text.strip()
                            if text:
                                headers.append(text)
                    except Exception as e:
                        print(f"{rest_name} - 헤더 파싱 실패: {e}")
                        continue

                    if not headers:
                        print(f"{rest_name} - 헤더 없음")
                        continue

                    # 메뉴 데이터 파싱
                    try:
                        rows = await page.query_selector_all(".table tbody tr")

                        for row in rows:
                            cells = await row.query_selector_all("td")

                            for i, cell in enumerate(cells):
                                if i < len(headers):
                                    meal_type_raw = headers[i]
                                    menu_content = (await cell.inner_text()).strip()

                                    if meal_type not in meal_type_raw:
                                        continue

                                    if not menu_content or menu_content in ["", "-", "운영안함"]:
                                        continue

                                    menu_infos[rest_name].append(menu_content)

                        print(f"{rest_name} - 메뉴 {len(menu_infos[rest_name])}개 수집")

                    except Exception as e:
                        print(f"{rest_name} - 메뉴 파싱 실패: {e}")
                        continue

                except Exception as e:
                    print(f"{rest_name} - 처리 중 에러: {e}")
                    continue

            await browser.close()
            return dict(menu_infos)

        except Exception as e:
            print(f"전체 처리 실패: {e}")
            return {}


def get_restaurants_menu(meal_type, restaurant_infos):
    """
    동기 래퍼 함수
    """
    return asyncio.run(get_restaurants_menu_async(meal_type, restaurant_infos))


def get_menus_by_meal_type(meal_type):
    """
    meal_type에 따라 해당하는 식당들의 메뉴를 조회
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
        print(f"유효하지 않은 meal_type: {meal_type}")
        return {}

    restaurants = restaurants_by_meal_type[meal_type]
    restaurant_infos = [(code, restaurant_names[code]) for code in restaurants]

    return get_restaurants_menu(meal_type, restaurant_infos)