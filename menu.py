import asyncio
from collections import defaultdict
from playwright.async_api import async_playwright, Browser, Playwright

# 전역 변수
_playwright: Playwright = None
_browser: Browser = None


async def init_browser():
    """브라우저 초기화 (봇 시작 시 한 번만 실행)"""
    global _playwright, _browser

    if _browser is not None:
        return

    print("Playwright 브라우저 초기화 중...")
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
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
    print("브라우저 초기화 완료")


async def close_browser():
    """브라우저 종료 (봇 종료 시 호출)"""
    global _playwright, _browser

    if _browser:
        await _browser.close()
        _browser = None

    if _playwright:
        await _playwright.stop()
        _playwright = None


async def get_restaurants_menu_async(meal_type, restaurant_infos):
    """
    Playwright를 사용한 비동기 메뉴 수집
    """
    global _browser

    # 브라우저가 초기화되지 않았으면 초기화
    if _browser is None:
        await init_browser()

    menu_infos = defaultdict(list)

    try:
        # 새 컨텍스트와 페이지 생성 (빠름)
        context = await _browser.new_context(
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

        await context.close()
        return dict(menu_infos)

    except Exception as e:
        print(f"전체 처리 실패: {e}")
        return {}


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
        print(f"유효하지 않은 meal_type: {meal_type}")
        return {}

    restaurants = restaurants_by_meal_type[meal_type]
    restaurant_infos = [(code, restaurant_names[code]) for code in restaurants]

    return await get_restaurants_menu_async(meal_type, restaurant_infos)