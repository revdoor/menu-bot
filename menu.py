import time
import os
import signal
import subprocess
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def kill_chrome_processes():
    """기존 Chrome 프로세스 모두 종료"""
    try:
        # Chrome 프로세스 찾아서 종료
        subprocess.run(['pkill', '-9', 'chrome'], stderr=subprocess.DEVNULL)
        subprocess.run(['pkill', '-9', 'chromedriver'], stderr=subprocess.DEVNULL)
        time.sleep(1)
        print("기존 Chrome 프로세스 종료 완료")
    except Exception as e:
        print(f"Chrome 프로세스 종료 시도 중 에러 (무시 가능): {e}")


def cleanup_temp_dirs():
    """임시 디렉토리 정리"""
    try:
        import shutil
        temp_pattern = '/tmp/chrome-data-*'
        for temp_dir in subprocess.run(
                ['find', '/tmp', '-maxdepth', '1', '-name', 'chrome-data-*'],
                capture_output=True,
                text=True
        ).stdout.strip().split('\n'):
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        print("임시 디렉토리 정리 완료")
    except Exception as e:
        print(f"임시 디렉토리 정리 실패 (무시 가능): {e}")


def get_driver():
    """Chrome WebDriver 인스턴스 생성"""
    # 기존 프로세스 정리
    kill_chrome_processes()
    cleanup_temp_dirs()

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-setuid-sandbox")

    # 메모리 최적화
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--metrics-recording-only")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--safebrowsing-disable-auto-update")

    # 캐시 및 데이터 디렉토리 설정
    chrome_options.add_argument("--disk-cache-size=1")
    chrome_options.add_argument("--media-cache-size=1")

    # user-data-dir 사용하지 않기
    chrome_options.add_argument("--disable-features=TranslateUI")
    chrome_options.add_argument("--disable-features=BlinkGenPropertyTrees")

    # Remote debugging 비활성화
    chrome_options.add_argument("--remote-debugging-port=0")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(30)
        print("WebDriver 생성 성공")
        return driver
    except Exception as e:
        print(f"WebDriver 생성 실패: {e}")
        raise


def get_restaurants_menu(meal_type, restaurant_infos):
    """
    특정 meal_type에 해당하는 식당들의 메뉴를 가져옴
    """
    driver = None
    menu_infos = defaultdict(list)

    try:
        driver = get_driver()
        print("페이지 로딩 시작")
        driver.get("https://www.kaist.ac.kr/kr/html/campus/053001.html")

        # 페이지 로드 대기
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "s0503"))
        )
        print("페이지 로딩 완료")

        for rest_code, rest_name in restaurant_infos:
            try:
                print(f"{rest_name} 처리 중...")

                # 식당 선택 (JavaScript 실행)
                driver.execute_script(f"ActFodlst('{rest_code}')")
                time.sleep(2.5)  # 조금 더 대기

                # 테이블 로드 대기
                try:
                    WebDriverWait(driver, 8).until(
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

        return dict(menu_infos)

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

            # 종료 후 프로세스 강제 종료 (안전장치)
            time.sleep(0.5)
            kill_chrome_processes()


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