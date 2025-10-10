import asyncio
from collections import defaultdict
from playwright.async_api import async_playwright, Browser, Playwright

# 전역 변수
_playwright: Playwright = None
_browser: Browser = None


async def init_browser():
    """브라우저 초기화 (봇 시작 시 한 번만 실행)"""
    global _playwright, _browser

    if _browser is not None and _browser.is_connected():
        print("브라우저 이미 초기화됨")
        return

    # 기존 브라우저가 있지만 연결이 끊어진 경우 정리
    if _browser is not None:
        try:
            await _browser.close()
        except:
            pass
        _browser = None

    if _playwright is not None:
        try:
            await _playwright.stop()
        except:
            pass
        _playwright = None

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
            '--disable-accelerated-2d-canvas',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-breakpad',
            '--disable-component-extensions-with-background-pages',
            '--disable-extensions',
            '--disable-features=TranslateUI,BlinkGenPropertyTrees',
            '--disable-ipc-flooding-protection',
            '--disable-renderer-backgrounding',
            '--enable-features=NetworkService,NetworkServiceInProcess',
            '--force-color-profile=srgb',
            '--hide-scrollbars',
            '--metrics-recording-only',
            '--mute-audio',
        ]
    )
    print("브라우저 초기화 완료")


async def close_browser():
    """브라우저 종료 (봇 종료 시 호출)"""
    global _playwright, _browser

    if _browser:
        try:
            await _browser.close()
        except:
            pass
        _browser = None
        print("브라우저 종료됨")

    if _playwright:
        try:
            await _playwright.stop()
        except:
            pass
        _playwright = None
        print("Playwright 종료됨")


async def get_restaurants_menu_async(meal_type, restaurant_infos):
    """
    Playwright를 사용한 비동기 메뉴 수집
    """
    global _browser

    # 브라우저 상태 확인 및 재초기화
    if _browser is None or not _browser.is_connected():
        print("브라우저 초기화 필요 (연결 끊김 또는 None)")
        await init_browser()

    menu_infos = defaultdict(list)
    context = None
    page = None

    try:
        # 새 컨텍스트와 페이지 생성
        print("새 브라우저 컨텍스트 생성 중...")
        context = await _browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            ignore_https_errors=True,
        )

        print("새 페이지 생성 중...")
        page = await context.new_page()

        # 타임아웃 설정
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(30000)

        print(f"페이지 로딩 시작 - meal_type: {meal_type}")
        await page.goto(
            "https://www.kaist.ac.kr/kr/html/campus/053001.html",
            wait_until='domcontentloaded',
            timeout=30000
        )

        # 페이지 로드 대기
        await page.wait_for_selector(".s0503", timeout=15000)
        print("페이지 로딩 완료")

        for rest_code, rest_name in restaurant_infos:
            try:
                print(f"\n{'=' * 50}")
                print(f"{rest_name} ({rest_code}) 처리 중...")

                # JavaScript 함수 실행
                await page.evaluate(f"ActFodlst('{rest_code}')")
                await asyncio.sleep(3)

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

                        for i, cell in enumerate(cells):
                            if i < len(headers):
                                meal_type_raw = headers[i]
                                menu_content = (await cell.inner_text()).strip()

                                # meal_type 매칭 확인
                                if meal_type not in meal_type_raw:
                                    continue

                                if not menu_content or menu_content in ["", "-", "운영안함"]:
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

    finally:
        # 리소스 정리
        if page:
            try:
                await page.close()
                print("페이지 닫힘")
            except:
                pass

        if context:
            try:
                await context.close()
                print("컨텍스트 닫힘")
            except:
                pass


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

    # 재시도 로직 추가
    max_retries = 2
    for attempt in range(max_retries):
        try:
            result = await get_restaurants_menu_async(meal_type, restaurant_infos)
            if result:  # 결과가 있으면 반환
                return result
            print(f"시도 {attempt + 1}/{max_retries}: 결과 없음")
        except Exception as e:
            print(f"시도 {attempt + 1}/{max_retries} 실패: {e}")
            if attempt < max_retries - 1:
                print("브라우저 재초기화 시도...")
                await close_browser()
                await asyncio.sleep(2)
                await init_browser()
                await asyncio.sleep(2)

    return {}