"""tts_manager.py 테스트"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from tts_manager import TTSSession, TTSManager


@pytest.mark.unit
class TestTTSSession:
    """TTSSession 클래스 테스트"""

    @pytest.fixture
    def session(self, mock_voice_client):
        """TTS 세션 인스턴스"""
        return TTSSession(mock_voice_client, channel_id=123)

    def test_session_initialization(self, session, mock_voice_client):
        assert session.voice_client == mock_voice_client
        assert session.channel_id == 123
        assert session.queue == []

    def test_is_connected_true(self, session, mock_voice_client):
        mock_voice_client.is_connected.return_value = True
        assert session.is_connected() is True

    def test_is_connected_false(self, session, mock_voice_client):
        mock_voice_client.is_connected.return_value = False
        assert session.is_connected() is False

    def test_is_connected_none_client(self):
        session = TTSSession(None, channel_id=123)
        assert session.is_connected() is False

    def test_add_to_queue(self, session):
        session.add_to_queue("Hello")
        session.add_to_queue("World")
        assert session.queue == ["Hello", "World"]

    def test_is_playing(self, session, mock_voice_client):
        mock_voice_client.is_playing.return_value = True
        assert session.is_playing() is True


@pytest.mark.unit
class TestTTSManager:
    """TTSManager 클래스 테스트"""

    @pytest.fixture
    def manager(self):
        return TTSManager()

    def test_manager_initialization(self, manager):
        assert manager._sessions == {}

    def test_get_session_none_when_not_exists(self, manager):
        assert manager.get_session(guild_id=123) is None

    def test_create_session(self, manager, mock_voice_client):
        session = manager.create_session(123, mock_voice_client, 456)
        assert isinstance(session, TTSSession)
        assert session.voice_client == mock_voice_client
        assert session.channel_id == 456

    def test_create_session_stores_in_manager(self, manager, mock_voice_client):
        manager.create_session(123, mock_voice_client, 456)
        assert 123 in manager._sessions and manager.get_session(123) is not None

    def test_remove_session(self, manager, mock_voice_client):
        manager.create_session(123, mock_voice_client, 456)
        manager.remove_session(123)
        assert manager.get_session(123) is None

    def test_remove_session_nonexistent(self, manager):
        manager.remove_session(999)  # 에러 없이 통과해야 함

    @pytest.mark.asyncio
    async def test_disconnect_session_success(self, manager, mock_voice_client):
        """세션 연결 해제 성공"""
        manager.create_session(123, mock_voice_client, 456)
        mock_voice_client.is_connected.return_value = True
        mock_voice_client.disconnect = AsyncMock()

        result = await manager.disconnect_session(123)

        assert result is True
        mock_voice_client.disconnect.assert_called_once()
        assert manager.get_session(123) is None

    @pytest.mark.asyncio
    async def test_disconnect_session_not_found(self, manager):
        """존재하지 않는 세션 연결 해제"""
        result = await manager.disconnect_session(999)

        assert result is False

    @pytest.mark.asyncio
    @patch('tts_manager.TTSManager._play_tts')
    async def test_play_queue_processes_items(
        self,
        mock_play_tts,
        manager,
        mock_voice_client
    ):
        """큐의 항목들을 순차적으로 재생"""
        mock_play_tts.return_value = None

        session = manager.create_session(123, mock_voice_client, 456)
        session.add_to_queue("Text 1")
        session.add_to_queue("Text 2")

        await manager.play_queue(123)

        # _play_tts가 2번 호출되었는지 확인
        assert mock_play_tts.call_count == 2

        # 큐가 비워졌는지 확인
        assert len(session.queue) == 0

    @pytest.mark.asyncio
    async def test_play_queue_no_session(self, manager):
        """세션이 없으면 아무것도 안 함"""
        await manager.play_queue(999)  # 에러 없이 통과해야 함

    @pytest.mark.asyncio
    @pytest.mark.slow
    @patch('tts_manager.gTTS')
    @patch('tts_manager.discord.FFmpegPCMAudio')
    @patch('tts_manager.os.remove')
    async def test_play_tts_creates_audio(
        self,
        mock_remove,
        mock_ffmpeg,
        mock_gtts,
        manager,
        mock_voice_client
    ):
        """TTS 음성 생성 및 재생 (통합 테스트)"""
        # Setup mocks
        mock_tts_instance = MagicMock()
        mock_gtts.return_value = mock_tts_instance
        mock_voice_client.is_connected.return_value = True
        # 재생이 끝나도록 설정: 첫 번째는 stop 체크용, 두 번째는 재생 대기 루프용
        mock_voice_client.is_playing.side_effect = [False, False]

        # Execute
        await TTSManager._play_tts(mock_voice_client, "Test text")

        # Verify
        mock_gtts.assert_called_once_with(text="Test text", lang='ko')
        mock_tts_instance.save.assert_called_once()
        mock_voice_client.play.assert_called_once()
        # 파일이 정리되었는지 확인
        mock_remove.assert_called_once()
