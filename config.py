"""
봇 설정 및 상수 정의
"""
from datetime import timezone, timedelta
from typing import Dict, List

# 시간대 설정
KST = timezone(timedelta(hours=9))

# 네트워크 설정
REQUEST_DELAY_SECONDS = 0.5
PING_INTERVAL_SECONDS = 180
HEALTH_CHECK_PORT = 8000

# Discord 제한
DISCORD_FIELD_MAX_LENGTH = 1024
DISCORD_EMBED_MAX_FIELDS = 25
MAX_MESSAGE_HISTORY = 5000
DEFAULT_MESSAGE_HISTORY = 500

# KAIST 식당 설정
KAIST_MENU_URL = "https://www.kaist.ac.kr/kr/html/campus/053001.html"

# 식당 코드 매핑
RESTAURANT_CODES: Dict[str, str] = {
    'west': '서맛골(서측식당)',
    'east1': '동맛골(동측학생식당)',
    'east2': '동맛골(동측 교직원식당)'
}

# 식사 타입별 식당 목록
RESTAURANTS_BY_MEAL_TYPE: Dict[str, List[str]] = {
    '중식': ['west', 'east1', 'east2'],
    '석식': ['west', 'east1']
}

# 식사 시간 정보
MEAL_INFO: Dict[str, tuple[str, str]] = {
    "조식": ("🌅 조식", "08:00-09:30"),
    "중식": ("🍽️ 중식", "11:30-13:30"),
    "석식": ("🌙 석식", "17:00-19:00")
}

# 로깅 메시지
LOG_MESSAGES = {
    'cache_hit': "💾 캐시에서 메뉴 로드: {date} - {meal_type}",
    'cache_save': "💾 캐시에 저장: {date} - {meal_type}",
    'cache_delete': "🗑️ 오래된 캐시 삭제: {date}",
    'ping_success': "✓ Ping 성공 ({status})",
    'ping_warning': "⚠️ Ping 응답 이상: {status}",
    'ping_failed': "❌ Ping 실패: {error}"
}
