"""
Discord TTS (Text-to-Speech) 관리 모듈

주요 기능:
- TTS 세션 관리
- 음성 재생 큐 처리
- edge-tts를 이용한 다양한 한국어 음성 생성
- 사용자별 보이스 설정
"""
import os
import re
import logging
import tempfile
import asyncio
import traceback
from typing import Dict, Optional

import discord
import edge_tts
from edge_tts.exceptions import NoAudioReceived


# URL 패턴 (http, https, www로 시작하는 링크)
URL_PATTERN = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s<>"{}|\\^`\[\]]+'
)

# 이모지 패턴 (유니코드 이모지 범위 - 한글 범위 제외)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # 이모티콘
    "\U0001F300-\U0001F5FF"  # 기호 & 픽토그램
    "\U0001F680-\U0001F6FF"  # 교통 & 지도
    "\U0001F700-\U0001F77F"  # 연금술 기호
    "\U0001F780-\U0001F7FF"  # 기하학적 도형 확장
    "\U0001F800-\U0001F8FF"  # 보조 화살표-C
    "\U0001F900-\U0001F9FF"  # 보조 기호 및 픽토그램
    "\U0001FA00-\U0001FA6F"  # 체스 기호
    "\U0001FA70-\U0001FAFF"  # 기호 및 픽토그램 확장-A
    "\U00002702-\U000027B0"  # 딩뱃
    "\U0001F004-\U0001F0CF"  # 마작, 카드
    "\U00002600-\U000026FF"  # 기타 기호
    "\U00002700-\U000027BF"  # 딩뱃
    "\U0000FE00-\U0000FE0F"  # 변형 선택자
    "\U0001F1E0-\U0001F1FF"  # 국기 (지역 지표 기호)
    "\U0001F200-\U0001F251"  # 기타 기호 (한글 범위 이후만)
    "]+",
    flags=re.UNICODE
)

# Discord 커스텀 이모지 패턴 <:name:id> 또는 <a:name:id>
DISCORD_EMOJI_PATTERN = re.compile(r'<a?:\w+:\d+>')

# 일본어 감지 패턴 (히라가나, 가타카나)
JAPANESE_PATTERN = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')

# 한글 초성 -> 발음 매핑
CHOSEONG_TO_PRONUNCIATION = {
    'ㄱ': '그', 'ㄲ': '끄', 'ㄴ': '느', 'ㄷ': '드', 'ㄸ': '뜨',
    'ㄹ': '르', 'ㅁ': '므', 'ㅂ': '브', 'ㅃ': '쁘', 'ㅅ': '스',
    'ㅆ': '쓰', 'ㅇ': '응', 'ㅈ': '즈', 'ㅉ': '쯔', 'ㅊ': '츠',
    'ㅋ': '크', 'ㅌ': '트', 'ㅍ': '프', 'ㅎ': '흐',
}

# 한글 모음 -> 발음 매핑
JUNGSEONG_TO_PRONUNCIATION = {
    'ㅏ': '아', 'ㅐ': '애', 'ㅑ': '야', 'ㅒ': '얘', 'ㅓ': '어',
    'ㅔ': '에', 'ㅕ': '여', 'ㅖ': '예', 'ㅗ': '오', 'ㅘ': '와',
    'ㅙ': '왜', 'ㅚ': '외', 'ㅛ': '요', 'ㅜ': '우', 'ㅝ': '워',
    'ㅞ': '웨', 'ㅟ': '위', 'ㅠ': '유', 'ㅡ': '으', 'ㅢ': '의',
    'ㅣ': '이',
}


def convert_jamo_to_pronunciation(text: str) -> str:
    """
    한글 자모(초성/모음)를 발음으로 변환

    예: ㅋㅋㅋ -> 크크크, ㅎㅎ -> 흐흐

    Args:
        text: 원본 텍스트

    Returns:
        자모가 발음으로 변환된 텍스트
    """
    result = []
    for char in text:
        if char in CHOSEONG_TO_PRONUNCIATION:
            result.append(CHOSEONG_TO_PRONUNCIATION[char])
        elif char in JUNGSEONG_TO_PRONUNCIATION:
            result.append(JUNGSEONG_TO_PRONUNCIATION[char])
        else:
            result.append(char)
    return ''.join(result)


def preprocess_text_for_tts(text: str) -> str:
    """
    TTS를 위한 텍스트 전처리

    - URL을 '링크'로 대체
    - 이모지 제거 (유니코드 및 Discord 커스텀 이모지)
    - 읽을 수 있는 문자가 없으면 빈 문자열 반환

    Args:
        text: 원본 텍스트

    Returns:
        전처리된 텍스트 (읽을 내용이 없으면 빈 문자열)
    """
    # URL을 '링크'로 대체
    text = URL_PATTERN.sub('링크', text)

    # Discord 커스텀 이모지 제거
    text = DISCORD_EMOJI_PATTERN.sub('', text)

    # 유니코드 이모지 제거
    text = EMOJI_PATTERN.sub('', text)

    # 한글 자모(초성/모음)를 발음으로 변환 (예: ㅋㅋㅋ -> 크크크)
    text = convert_jamo_to_pronunciation(text)

    # 연속된 공백 정리
    text = re.sub(r'\s+', ' ', text).strip()

    # 읽을 수 있는 문자(한글, 영문, 숫자, 일본어, 한자)가 있는지 확인
    if not re.search(r'[가-힣a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text):
        return ''

    return text

# 로거 설정
logger = logging.getLogger(__name__)


class TTSQueueItem:
    """TTS 큐 아이템 - 텍스트와 사용자 정보를 함께 저장"""

    def __init__(self, text: str, user_id: int):
        self.text = text
        self.user_id = user_id


# 사용 가능한 보이스 목록 (voice_id, 표시명)
# edge-tts 한국어/일본어 보이스
AVAILABLE_VOICES = {
    # 한국어
    'sunhi': ('ko-KR-SunHiNeural', '선히 (여성)'),
    'injoon': ('ko-KR-InJoonNeural', '인준 (남성)'),
    'hyunsu': ('ko-KR-HyunsuMultilingualNeural', '현수 (남성)'),
    # 일본어
    'nanami': ('ja-JP-NanamiNeural', '나나미 (여성)'),
    'keita': ('ja-JP-KeitaNeural', '케이타 (남성)'),
}

# 기본 보이스
DEFAULT_VOICE = 'ko-KR-SunHiNeural'
DEFAULT_JAPANESE_VOICE = 'ja-JP-NanamiNeural'


def is_japanese_text(text: str) -> bool:
    """텍스트에 일본어(히라가나/가타카나)가 포함되어 있는지 확인"""
    return bool(JAPANESE_PATTERN.search(text))


class TTSSession:
    """TTS 세션 관리 클래스"""

    def __init__(
        self,
        voice_client: discord.VoiceClient,
        channel_id: int,
        voice_config_channel_id: Optional[int] = None
    ):
        """
        Args:
            voice_client: Discord 음성 클라이언트
            channel_id: TTS로 읽을 텍스트 채널 ID
            voice_config_channel_id: 보이스 설정을 저장하는 채널 ID (선택)
        """
        self.voice_client = voice_client
        self.channel_id = channel_id
        self.voice_config_channel_id = voice_config_channel_id
        self.queue: list[TTSQueueItem] = []
        self.lock = asyncio.Lock()
        # 사용자별 보이스 설정 캐시 {user_id: voice_id}
        self._voice_cache: Dict[int, str] = {}

    def is_connected(self) -> bool:
        """음성 채널 연결 상태 확인"""
        return bool(self.voice_client) and self.voice_client.is_connected()

    def add_to_queue(self, text: str, user_id: int) -> None:
        """재생 큐에 텍스트 추가"""
        item = TTSQueueItem(text, user_id)
        self.queue.append(item)

    def is_playing(self) -> bool:
        """현재 재생 중인지 확인"""
        return bool(self.voice_client) and self.voice_client.is_playing()

    def get_user_voice(self, user_id: int) -> str:
        """사용자의 보이스 설정 반환 (캐시에서)"""
        return self._voice_cache.get(user_id, DEFAULT_VOICE)

    def set_user_voice(self, user_id: int, voice_id: str) -> None:
        """사용자의 보이스 설정 저장 (캐시에)"""
        self._voice_cache[user_id] = voice_id


class TTSManager:
    """TTS 세션 관리자 - 서버별 TTS 세션을 관리하는 싱글톤 클래스"""

    def __init__(self):
        self._sessions: Dict[int, TTSSession] = {}
        # 마지막 TTS 설정 저장 (세션 재생성용)
        # {guild_id: {'channel_id': int, 'voice_channel_id': int, 'voice_config_channel_id': int|None}}
        self._last_config: Dict[int, dict] = {}

    def get_session(self, guild_id: int) -> Optional[TTSSession]:
        """
        세션 가져오기

        Args:
            guild_id: Discord 길드 ID

        Returns:
            TTSSession 또는 None
        """
        return self._sessions.get(guild_id)

    def create_session(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient,
        channel_id: int,
        voice_config_channel_id: Optional[int] = None
    ) -> TTSSession:
        """
        새 TTS 세션 생성

        Args:
            guild_id: Discord 길드 ID
            voice_client: 음성 클라이언트
            channel_id: TTS 텍스트 채널 ID
            voice_config_channel_id: 보이스 설정 채널 ID (선택)

        Returns:
            생성된 TTSSession
        """
        session = TTSSession(voice_client, channel_id, voice_config_channel_id)
        self._sessions[guild_id] = session

        # 마지막 설정 저장 (세션 재생성용)
        self._last_config[guild_id] = {
            'channel_id': channel_id,
            'voice_channel_id': voice_client.channel.id,
            'voice_config_channel_id': voice_config_channel_id,
        }

        return session

    def get_last_config(self, guild_id: int) -> Optional[dict]:
        """마지막 TTS 설정 반환"""
        return self._last_config.get(guild_id)

    def clear_last_config(self, guild_id: int) -> None:
        """마지막 TTS 설정 삭제"""
        if guild_id in self._last_config:
            del self._last_config[guild_id]

    def remove_session(self, guild_id: int) -> None:
        """
        세션 제거

        Args:
            guild_id: Discord 길드 ID
        """
        if guild_id in self._sessions:
            del self._sessions[guild_id]

    async def play_queue(self, guild_id: int) -> None:
        """
        TTS 큐를 순차적으로 재생

        Args:
            guild_id: Discord 길드 ID
        """
        session = self.get_session(guild_id)
        if not session:
            return

        async with session.lock:
            while session.queue:
                item = session.queue.pop(0)
                # 사용자별 보이스 설정 조회
                voice_id = session.get_user_voice(item.user_id)
                await TTSManager._play_tts(session.voice_client, item.text, voice_id)

    @staticmethod
    async def _play_tts(
        voice_client: discord.VoiceClient,
        text: str,
        voice_id: str = DEFAULT_VOICE
    ) -> None:
        """
        TTS 음성 생성 및 재생 (edge-tts 사용)

        Args:
            voice_client: Discord 음성 클라이언트
            text: 읽을 텍스트
            voice_id: edge-tts 보이스 ID (기본값: ko-KR-SunHiNeural)
        """
        if not voice_client or not voice_client.is_connected():
            logger.warning(f"음성 클라이언트가 연결되지 않음")
            return

        # 텍스트 전처리 (이모지 제거, URL 대체, 자모 변환)
        processed_text = preprocess_text_for_tts(text)

        # 전처리 결과가 다를 때만 로그
        if processed_text != text:
            logger.info(f"TTS: '{text}' -> '{processed_text}'")

        if not processed_text:
            return

        # 일본어 텍스트면 일본어 보이스로 전환
        if is_japanese_text(processed_text) and not voice_id.startswith('ja-'):
            voice_id = DEFAULT_JAPANESE_VOICE

        temp_filename = None

        try:
            # 임시 파일 경로 생성
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                temp_filename = fp.name

            # edge-tts로 음성 파일 생성
            communicate = edge_tts.Communicate(processed_text, voice_id)
            await communicate.save(temp_filename)

            # 이전 재생 중지
            if voice_client.is_playing():
                voice_client.stop()

            # 재생
            audio_source = discord.FFmpegPCMAudio(temp_filename)
            voice_client.play(audio_source)

            # 재생 완료 대기
            while voice_client.is_playing():
                await asyncio.sleep(0.1)

        except NoAudioReceived:
            # 현재 보이스로 변환 실패 시 기본 보이스로 재시도
            if voice_id != DEFAULT_VOICE:
                logger.warning(f"TTS 변환 실패 (NoAudioReceived), 기본 보이스로 재시도: '{processed_text}'")
                try:
                    communicate = edge_tts.Communicate(processed_text, DEFAULT_VOICE)
                    await communicate.save(temp_filename)

                    if voice_client.is_playing():
                        voice_client.stop()

                    audio_source = discord.FFmpegPCMAudio(temp_filename)
                    voice_client.play(audio_source)

                    while voice_client.is_playing():
                        await asyncio.sleep(0.1)
                except NoAudioReceived:
                    logger.warning(f"TTS 변환 불가 (NoAudioReceived): '{processed_text}'")
            else:
                logger.warning(f"TTS 변환 불가 (NoAudioReceived): '{processed_text}'")

        except Exception as e:
            logger.error(f"TTS 재생 중 에러: {e}", exc_info=True)

        finally:
            # 임시 파일 삭제
            if temp_filename:
                try:
                    os.remove(temp_filename)
                except:
                    pass

    async def disconnect_session(self, guild_id: int) -> bool:
        """
        세션의 음성 채널 연결 해제

        Args:
            guild_id: Discord 길드 ID

        Returns:
            성공 여부
        """
        session = self.get_session(guild_id)
        if not session:
            return False

        voice_client = session.voice_client

        # 세션 먼저 제거 (on_voice_state_update에서 재연결 방지)
        self.remove_session(guild_id)

        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()

        return True

    async def load_voice_settings(
        self,
        guild_id: int,
        config_channel: discord.TextChannel
    ) -> int:
        """
        설정 채널에서 보이스 설정을 로드하여 세션 캐시에 저장

        메시지 형식: "user_id|voice_key"
        예: "123456789|en_us"

        Args:
            guild_id: 길드 ID
            config_channel: 설정 채널

        Returns:
            로드된 설정 개수
        """
        session = self.get_session(guild_id)
        if not session:
            return 0

        count = 0
        # 사용자별로 가장 최신 설정만 유지하기 위해 dict에 저장
        user_settings: Dict[int, str] = {}

        try:
            # 채널의 메시지를 읽어서 설정 파싱 (최근 100개)
            async for message in config_channel.history(limit=100):
                content = message.content.strip()
                if '|' not in content:
                    continue

                try:
                    parts = content.split('|')
                    if len(parts) != 2:
                        continue

                    user_id_str, voice_key = parts
                    user_id = int(user_id_str)

                    # 이미 해당 사용자의 설정이 있으면 건너뜀 (최신 것만 사용)
                    if user_id in user_settings:
                        continue

                    if voice_key in AVAILABLE_VOICES:
                        user_settings[user_id] = voice_key

                except (ValueError, KeyError):
                    continue

            # 캐시에 설정 적용
            for user_id, voice_key in user_settings.items():
                voice_id, _ = AVAILABLE_VOICES[voice_key]
                session.set_user_voice(user_id, voice_id)
                count += 1

            logger.info(f"보이스 설정 로드 완료: {count}개 (guild={guild_id})")

        except Exception as e:
            logger.error(f"보이스 설정 로드 실패: {e}", exc_info=True)

        return count

    async def save_voice_setting(
        self,
        config_channel: discord.TextChannel,
        user_id: int,
        voice_key: str
    ) -> bool:
        """
        보이스 설정을 채널에 저장

        Args:
            config_channel: 설정 채널
            user_id: 사용자 ID
            voice_key: 보이스 키 (예: 'ko', 'en_us')

        Returns:
            성공 여부
        """
        if voice_key not in AVAILABLE_VOICES:
            return False

        try:
            # 설정 메시지 전송
            await config_channel.send(f"{user_id}|{voice_key}")
            logger.info(f"보이스 설정 저장: user={user_id}, voice={voice_key}")
            return True

        except Exception as e:
            logger.error(f"보이스 설정 저장 실패: {e}", exc_info=True)
            return False
