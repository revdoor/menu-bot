"""pytest 공통 설정 및 fixtures"""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import discord
except ImportError:
    raise ImportError(
        "discord.py가 설치되지 않았습니다.\n"
        "실행: pip install -r requirements-dev.txt"
    )


# ==================== Discord Mock Fixtures ====================

@pytest.fixture
def mock_guild():
    """Mock Discord Guild"""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.get_channel = MagicMock(return_value=None)
    guild.fetch_stickers = AsyncMock(return_value=[])
    return guild


@pytest.fixture
def mock_channel():
    """Mock Discord TextChannel"""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 987654321
    channel.name = "test-channel"
    channel.mention = "<#987654321>"
    return channel


@pytest.fixture
def mock_voice_client():
    """Mock Discord VoiceClient"""
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_connected = MagicMock(return_value=True)
    vc.is_playing = MagicMock(return_value=False)
    vc.disconnect = AsyncMock()
    vc.stop = MagicMock()
    vc.play = MagicMock()
    vc.channel = MagicMock()
    vc.channel.mention = "<#123>"
    return vc


@pytest.fixture
def mock_sticker():
    """Mock Discord Sticker"""
    sticker = MagicMock(spec=discord.Sticker)
    sticker.id = 555666777
    sticker.name = "test_sticker"
    return sticker


# ==================== 테스트 데이터 Fixtures ====================

@pytest.fixture
def sample_menu_data():
    """샘플 메뉴 데이터"""
    return {
        '서맛골(서측식당)': ['김치찌개\n밥\n김치', '된장찌개\n밥\n깍두기'],
        '동맛골(동측학생식당)': ['불고기\n밥\n나물', '제육볶음\n밥\n김치']
    }


@pytest.fixture
def sample_html_menu():
    """샘플 HTML 메뉴 테이블"""
    return """
    <table class="table">
        <thead><tr><th>중식</th><th>석식</th></tr></thead>
        <tbody><tr><td>김치찌개<br>밥<br>김치</td><td>불고기<br>밥<br>나물</td></tr></tbody>
    </table>
    """


@pytest.fixture
def sample_sticker_stats():
    """샘플 스티커 통계 데이터"""
    return {
        'sticker_counts': {'test_sticker_1': 10, 'test_sticker_2': 5, 'test_sticker_3': 3},
        'total_messages': 100,
        'messages_with_stickers': 18
    }
