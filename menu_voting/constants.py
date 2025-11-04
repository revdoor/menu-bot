"""
메뉴 투표 시스템 상수 정의
"""

# 타임아웃 설정
VOTING_FORM_TIMEOUT = 300  # 5분 (초 단위)

# Discord 제한
MAX_SELECT_OPTIONS = 25  # Discord Select 최대 옵션 수
MAX_EMBED_FIELD_LENGTH = 1024  # Discord Embed 필드 최대 길이

# 투표 제약
MIN_MENU_COUNT = 2  # 투표 시작을 위한 최소 메뉴 개수
MIN_SCORE = 1  # 최소 점수
MAX_SCORE = 5  # 최대 점수

# 점수 레이블
SCORE_LABELS = {
    1: "매우 별로",
    2: "별로",
    3: "보통",
    4: "좋음",
    5: "매우 좋음",
}

# 점수 이모지
SCORE_EMOJIS = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
}

# 순위 이모지
RANK_EMOJIS = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
}

# 결과 표시 제한
MAX_DETAILED_RESULTS = 3  # 상세 점수 분포를 보여줄 최대 메뉴 수
