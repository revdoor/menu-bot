"""config.py 테스트"""
import pytest
from config import (
    KST, REQUEST_DELAY_SECONDS, PING_INTERVAL_SECONDS, HEALTH_CHECK_PORT,
    DISCORD_FIELD_MAX_LENGTH, DISCORD_EMBED_MAX_FIELDS,
    MAX_MESSAGE_HISTORY, DEFAULT_MESSAGE_HISTORY,
    KAIST_MENU_URL, RESTAURANT_CODES, RESTAURANTS_BY_MEAL_TYPE, MEAL_INFO
)


@pytest.mark.unit
class TestConstants:
    """상수 값 테스트"""

    def test_kst_timezone_offset(self):
        import datetime
        assert KST.utcoffset(datetime.datetime.now()) == datetime.timedelta(hours=9)

    def test_network_constants(self):
        assert REQUEST_DELAY_SECONDS > 0 and PING_INTERVAL_SECONDS > 0
        assert isinstance(HEALTH_CHECK_PORT, int) and 1024 <= HEALTH_CHECK_PORT <= 65535

    def test_discord_limits(self):
        assert DISCORD_FIELD_MAX_LENGTH == 1024 and DISCORD_EMBED_MAX_FIELDS == 25
        assert MAX_MESSAGE_HISTORY > DEFAULT_MESSAGE_HISTORY


@pytest.mark.unit
class TestRestaurantConfig:
    """식당 설정 테스트"""

    def test_restaurant_codes_not_empty(self):
        assert len(RESTAURANT_CODES) > 0
        assert all(isinstance(code, str) for code in RESTAURANT_CODES.keys())
        assert all(isinstance(name, str) for name in RESTAURANT_CODES.values())

    def test_restaurants_by_meal_type_structure(self):
        assert '중식' in RESTAURANTS_BY_MEAL_TYPE and '석식' in RESTAURANTS_BY_MEAL_TYPE
        for meal_type, restaurants in RESTAURANTS_BY_MEAL_TYPE.items():
            assert all(code in RESTAURANT_CODES for code in restaurants)

    def test_meal_info_structure(self):
        import re
        pattern = re.compile(r'^\d{2}:\d{2}-\d{2}:\d{2}$')
        for meal_type, (emoji, time_range) in MEAL_INFO.items():
            assert isinstance(emoji, str) and len(emoji) > 0
            assert pattern.match(time_range), f"Invalid time format: {time_range}"


@pytest.mark.unit
class TestURLs:
    """URL 설정 테스트"""

    def test_kaist_menu_url_format(self):
        assert KAIST_MENU_URL.startswith('https://') and 'kaist.ac.kr' in KAIST_MENU_URL
        assert len(KAIST_MENU_URL) > 0


@pytest.mark.unit
class TestConstantTypes:
    """상수 타입 검증"""

    def test_request_delay_is_positive_number(self):
        assert isinstance(REQUEST_DELAY_SECONDS, (int, float)) and REQUEST_DELAY_SECONDS > 0

    def test_message_history_limits_are_valid(self):
        assert isinstance(MAX_MESSAGE_HISTORY, int) and isinstance(DEFAULT_MESSAGE_HISTORY, int)
        assert MAX_MESSAGE_HISTORY > 0 and DEFAULT_MESSAGE_HISTORY > 0
        assert MAX_MESSAGE_HISTORY >= DEFAULT_MESSAGE_HISTORY

    def test_restaurant_codes_consistency(self):
        for code, name in RESTAURANT_CODES.items():
            assert code.replace('_', '').isalnum()
            assert len(name.strip()) > 0
