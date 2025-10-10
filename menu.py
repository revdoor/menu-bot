import time
import uuid
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def get_driver():
    """Chrome WebDriver 인스턴스 생성"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-software-rasterizer")

    # 매번 고유한 user-data-dir 생성하여 충돌 방지
    unique_dir = f'/tmp/chrome-data-{uuid.uuid4()}'
    chrome_options.add_argument(f'--user-data-dir={unique_dir}')

    # 추가 안정성 옵션
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--disable-setuid-sandbox")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"WebDriver 생성 실패: {e}")
        raise


def get_restaurants_menu(meal_type, restaurant_infos):
    """
    특정 meal_type에 해당하는 식당들의 메뉴를 가져옴

    Args:
        meal_type: str - 식사 종류 (중식, 석식)
        restaurant_infos: List[Tuple[str, str]] - (식당 코드, 식당 이름) 리스트

    Returns:
        dict - {식당명: [메뉴들]} 형태의 딕셔너리
    """
    driver = None
    menu_infos = defaultdict(list)

    try:
        driver = get_driver()
        driver.get("https://www.kaist.ac.kr/kr/html/campus/053001.html")

        # 페이지 로드 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "s0503"))
        )

        for rest_code, rest_name in restaurant_infos:
            try:
                # 식당 선택
                driver.execute_script(f"ActFodlst('{rest_code}')")
                time.sleep(2)

                # 테이블 로드 대기
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".table"))
                    )
                except:
                    print(f"{rest_name} - 테이블 로드 실패")
                    continue

                # 헤더 파싱
                try:
                    header_elements = driver.find_elements(By.CSS_SELECTOR, ".table thead th")
                    headers = [header.text.strip() for header in header_elements if header.text.strip()]
                except Exception as e:
                    print(f"{rest_name} - 헤더 파싱 실패: {e}")
                    continue

                if not headers:
                    print(f"{rest_name} - 헤더 없음")
                    continue

                # 메뉴 데이터 파싱
                try:
                    rows = driver.find_elements(By.CSS_SELECTOR, ".table tbody tr")

                    for row in rows:
                        cells = row.find_elements(By.TAG_NAME, "td")

                        for i, cell in enumerate(cells):
                            if i < len(headers):
                                meal_type_raw = headers[i]
                                menu_content = cell.text.strip()

                                # 해당 meal_type인지 확인
                                if meal_type not in meal_type_raw:
                                    continue

                                # 유효한 메뉴인지 확인
                                if not menu_content or menu_content in ["", "-", "운영안함"]:
                                    continue

                                menu_infos[rest_name].append(menu_content)

                except Exception as e:
                    print(f"{rest_name} - 메뉴 파싱 실패: {e}")
                    continue

            except Exception as e:
                print(f"{rest_name} - 처리 중 에러: {e}")
                continue

        return dict(menu_infos)  # defaultdict를 일반 dict로 변환

    except Exception as e:
        print(f"전체 처리 실패: {e}")
        return {}

    finally:
        if driver:
            try:
                driver.quit()
                print("WebDriver 정상 종료")
            except Exception as e:
                print(f"WebDriver 종료 실패: {e}")


def get_menus_by_meal_type(meal_type):
    """
    meal_type에 따라 해당하는 식당들의 메뉴를 조회

    Args:
        meal_type: str - '중식' 또는 '석식'

    Returns:
        dict - {식당명: [메뉴들]} 형태의 딕셔너리
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

    # 유효한 meal_type인지 확인
    if meal_type not in restaurants_by_meal_type:
        print(f"유효하지 않은 meal_type: {meal_type}")
        return {}

    restaurants = restaurants_by_meal_type[meal_type]
    restaurant_infos = [(code, restaurant_names[code]) for code in restaurants]

    return get_restaurants_menu(meal_type, restaurant_infos)
