import time
import os
import signal
import subprocess
import tempfile
import shutil
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def kill_chrome_processes():
    """기존 Chrome 프로세스 모두 종료"""
    try:
        subprocess.run(['pkill', '-9', 'chrome'], stderr=subprocess.DEVNULL)
        subprocess.run(['pkill', '-9', 'chromedriver'], stderr=subprocess.DEVNULL)
        time.sleep(1)
        print("기존 Chrome 프로세스 종료 완료")
    except Exception as e:
        print(f"Chrome 프로세스 종료 시도 중 에러 (무시 가능): {e}")


def get_driver():
    """Chrome WebDriver 인스턴스 생성"""
    # 기존 프로세스 정리
    kill_chrome_processes()

    # 임시 디렉토리 생성 (매번 새로 생성)
    temp_dir = tempfile.mkdtemp(prefix='chrome_')
    print(f"임시 디렉토리 생성: {temp_dir}")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-setuid-sandbox")

    # 명시적으로 임시 디렉토리 지정
    chrome_options.add_argument(f"--user-data-dir={temp_dir}")
    chrome_options.add_argument(f"--data-path={temp_dir}")
    chrome_options.add_argument(f"--disk-cache-dir={temp_dir}/cache")

    # 추가 최적화 옵션
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--hide-scrollbars")
    chrome_options.add_argument("--metrics-recording-only")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--safebrowsing-disable-auto-update")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--ignore-ssl-errors")

    # 메모리 제한
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")

    # Remote debugging 포트 설정
    chrome_options.add_argument("--remote-debugging-port=9222")

    # ChromeDriver 로그 비활성화
    service = Service(log_path=os.devnull)

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(30)
        print("WebDriver 생성 성공")
        return driver, temp_dir
    except Exception as e:
        print(f"WebDriver 생성 실패: {e}")
        # 실패 시 임시 디렉토리 정리
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass
        raise


def get_restaurants_menu(meal_type, restaurant_infos):
    """
    특정 meal_type에 해당하는 식당들의 메뉴를 가져옴
    """
    driver = None
    temp_dir = None
    menu_infos = defaultdict(list)

    try:
        driver, temp_dir = get_driver()
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
                time.sleep(2.5)

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
        # WebDriver 종료
        if driver:
            try:
                driver.quit()
                print("WebDriver 정상 종료")
            except Exception as e:
                print(f"WebDriver 종료 실패: {e}")

        # 임시 디렉토리 정리
        if temp_dir and os.path.exists(temp_dir):
            try:
                time.sleep(0.5)
                shutil.rmtree(temp_dir, ignore_errors=True)
                print(f"임시 디렉토리 삭제: {temp_dir}")
            except Exception as e:
                print(f"임시 디렉토리 삭제 실패: {e}")

        # 프로세스 강제 종료 (안전장치)
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