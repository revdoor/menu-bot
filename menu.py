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
        print("브라우저 이미 초기화됨")
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
        print("브라우저 종료됨")

    if _playwright:
        await _playwright.stop()
        _playwright = None
        print("Playwright 종료됨")


async def get_restaurants_menu_async(meal_type, restaurant_infos):
    """
    Playwright를 사용한 비동기 메뉴 수집
    """
    global _browser

    # 브라우저가 초기화되지 않았으면 초기화
    if _browser is None:
        print("브라우저 초기화 필요")
        await init_browser()

    menu_infos = defaultdict(list)

    try:
        # 새 컨텍스트와 페이지 생성
        context = await _browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        page = await context.new_page()

        print(f"페이지 로딩 시작 - meal_type: {meal_type}")
        await page.goto("https://www.kaist.ac.kr/kr/html/campus/053001.html",
                        wait_until='domcontentloaded',
                        timeout=30000)

        # 페이지 로드 대기
        await page.wait_for_selector(".s0503", timeout=15000)
        print("페이지 로딩 완료")

        for rest_code, rest_name in restaurant_infos:
            try:
                print(f"\n{'=' * 50}")
                print(f"{rest_name} ({rest_code}) 처리 중...")

                # JavaScript 함수 실행
                await page.evaluate(f"ActFodlst('{rest_code}')")
                await asyncio.sleep(3)  # 약간 더 여유있게

                # 테이블 로드 대기
                try:
                    await page.wait_for_selector(".table", timeout=10000)
                except Exception as e:
                    print(f"{rest_name} - 테이블 로드 실패: {e}")
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

                    print(f"{rest_name} - 헤더: {headers}")

                except Exception as e:
                    print(f"{rest_name} - 헤더 파싱 실패: {e}")
                    continue

                if not headers:
                    print(f"{rest_name} - 헤더 없음")
                    continue

                # 메뉴 데이터 파싱
                try:
                    rows = await page.query_selector_all(".table tbody tr")
                    print(f"{rest_name} - 행 개수: {len(rows)}")

                    for row_idx, row in enumerate(rows):
                        cells = await row.query_selector_all("td")
                        print(f"  행 {row_idx} - 셀 개수: {len(cells)}")

                        for i, cell in enumerate(cells):
                            if i < len(headers):
                                meal_type_raw = headers[i]
                                menu_content = (await cell.inner_text()).strip()

                                print(f"    셀 [{i}] - 헤더: '{meal_type_raw}', 내용 길이: {len(menu_content)}")

                                # meal_type 매칭 확인 (대소문자 무시, 공백 제거)
                                if meal_type not in meal_type_raw:
                                    print(f"    -> meal_type '{meal_type}'이 '{meal_type_raw}'에 없음. 스킵")
                                    continue

                                if not menu_content or menu_content in ["", "-", "운영안함"]:
                                    print(f"    -> 빈 메뉴 또는 운영안함. 스킵")
                                    continue

                                print(f"    -> ✓ 메뉴 추가: {menu_content[:50]}...")
                                menu_infos[rest_name].append(menu_content)

                    print(f"{rest_name} - 최종 수집된 메뉴 개수: {len(menu_infos[rest_name])}")

                except Exception as e:
                    print(f"{rest_name} - 메뉴 파싱 실패: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            except Exception as e:
                print(f"{rest_name} - 처리 중 에러: {e}")
                import traceback
                traceback.print_exc()
                continue

        await context.close()

        result = dict(menu_infos)
        print(f"\n{'=' * 50}")
        print(f"최종 결과: {len(result)}개 식당")
        for rest, menus in result.items():
            print(f"  {rest}: {len(menus)}개 메뉴")

        return result

    except Exception as e:
        print(f"전체 처리 실패: {e}")
        import traceback
        traceback.print_exc()
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
        print(f"❌ 유효하지 않은 meal_type: {meal_type}")
        return {}

    restaurants = restaurants_by_meal_type[meal_type]
    restaurant_infos = [(code, restaurant_names[code]) for code in restaurants]

    print(f"\n{'=' * 50}")
    print(f"메뉴 조회 시작 - {meal_type}")
    print(f"대상 식당: {[name for _, name in restaurant_infos]}")
    print(f"{'=' * 50}")

    return await get_restaurants_menu_async(meal_type, restaurant_infos)