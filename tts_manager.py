"""
Discord TTS (Text-to-Speech) 관리 모듈

주요 기능:
- TTS 세션 관리
- 음성 재생 큐 처리
- gTTS를 이용한 한국어 음성 생성
"""
import os
import tempfile
import asyncio
import traceback
from typing import Dict, List, Optional

import discord
from gtts import gTTS


class TTSSession:
    """TTS 세션 관리 클래스"""

    def __init__(self, voice_client: discord.VoiceClient, channel_id: int):
        """
        Args:
            voice_client: Discord 음성 클라이언트
            channel_id: TTS로 읽을 텍스트 채널 ID
        """
        self.voice_client = voice_client
        self.channel_id = channel_id
        self.queue: List[str] = []
        self.lock = asyncio.Lock()

    def is_connected(self) -> bool:
        """음성 채널 연결 상태 확인"""
        return self.voice_client and self.voice_client.is_connected()

    def add_to_queue(self, text: str) -> None:
        """재생 큐에 텍스트 추가"""
        self.queue.append(text)
        print(f"TTS 큐에 추가: '{text}' (큐 크기: {len(self.queue)})")

    def has_queued_items(self) -> bool:
        """큐에 대기 중인 항목이 있는지 확인"""
        return len(self.queue) > 0

    def is_playing(self) -> bool:
        """현재 재생 중인지 확인"""
        return self.voice_client and self.voice_client.is_playing()


class TTSManager:
    """TTS 세션 관리자 - 서버별 TTS 세션을 관리하는 싱글톤 클래스"""

    def __init__(self):
        self._sessions: Dict[int, TTSSession] = {}

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
        channel_id: int
    ) -> TTSSession:
        """
        새 TTS 세션 생성

        Args:
            guild_id: Discord 길드 ID
            voice_client: 음성 클라이언트
            channel_id: TTS 텍스트 채널 ID

        Returns:
            생성된 TTSSession
        """
        session = TTSSession(voice_client, channel_id)
        self._sessions[guild_id] = session
        return session

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
                text = session.queue.pop(0)
                await TTSManager._play_tts(session.voice_client, text)

    @staticmethod
    async def _play_tts(voice_client: discord.VoiceClient, text: str) -> None:
        """
        TTS 음성 생성 및 재생

        Args:
            voice_client: Discord 음성 클라이언트
            text: 읽을 텍스트
        """
        if not voice_client or not voice_client.is_connected():
            print(f"음성 클라이언트가 연결되지 않음")
            return

        temp_filename = None

        try:
            print(f"TTS 생성 중: '{text}'")

            # gTTS로 음성 파일 생성
            tts = gTTS(text=text, lang='ko')

            # 임시 파일에 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                temp_filename = fp.name
                tts.save(temp_filename)

            # 이전 재생 중지
            if voice_client.is_playing():
                voice_client.stop()

            # 재생
            audio_source = discord.FFmpegPCMAudio(temp_filename)
            voice_client.play(audio_source)

            # 재생 완료 대기
            while voice_client.is_playing():
                await asyncio.sleep(0.1)

            print(f"TTS 재생 완료: '{text}'")

        except Exception as e:
            print(f"TTS 재생 중 에러: {e}")
            traceback.print_exc()

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

        if session.voice_client and session.voice_client.is_connected():
            await session.voice_client.disconnect()

        self.remove_session(guild_id)
        return True
