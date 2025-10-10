import time
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def get_restaurants_menu(meal_type, restaurant_infos):
    # meal_type: str
    # restaurants: List[Tuple[str, str]] (식당 코드, 식당 이름)
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=chrome_options)

    menu_infos = defaultdict(list)

    try:
        driver.get("https://www.kaist.ac.kr/kr/html/campus/053001.html")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "s0503"))
        )

        for rest_code, rest_name in restaurant_infos:
            try:
                driver.execute_script(f"ActFodlst('{rest_code}')")
                time.sleep(2)

                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".table"))
                    )
                except:
                    continue

                try:
                    header_elements = driver.find_elements(By.CSS_SELECTOR, ".table thead th")
                    headers = [header.text.strip() for header in header_elements if header.text.strip()]
                except:
                    continue

                if not headers:
                    continue

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

                except Exception as e:
                    continue

            except Exception as e:
                continue

        return menu_infos

    except Exception as e:
        return None

    finally:
        driver.quit()


def get_menus_by_meal_type(meal_type):
    restaurants_by_meal_type = {
        '중식': ['west', 'east1', 'east2'],
        '석식': ['west', 'east1']
    }

    restaurant_names = {
        'west': '서맛골(서측식당)',
        'east1': '동맛골(동측학생식당)',
        'east2': '동맛골(동측 교직원식당)'
    }

    restaurants = restaurants_by_meal_type[meal_type]

    return get_restaurants_menu(meal_type, [(code, restaurant_names[code]) for code in restaurants])
