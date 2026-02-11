"""
Open-LLM-VTuber Test Fixtures
공통 테스트 픽스처 및 모킹 유틸리티
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import AsyncIterator


@pytest.fixture
def mock_llm():
    """Mock LLM 응답을 위한 픽스처"""
    mock = AsyncMock()
    mock.generate.return_value = "This is a mock LLM response."
    mock.stream.return_value = async_generator(["Hello", " ", "World"])
    return mock


@pytest.fixture
def mock_tts():
    """Mock TTS 오디오를 위한 픽스처"""
    mock = AsyncMock()
    # 샘플 오디오 데이터 (빈 WAV 헤더)
    mock.generate_audio.return_value = async_generator([b'\x00' * 1024])
    return mock


@pytest.fixture
def mock_asr():
    """Mock ASR 텍스트를 위한 픽스처"""
    mock = AsyncMock()
    mock.transcribe.return_value = "This is a mock transcription."
    return mock


@pytest.fixture
def sample_config():
    """샘플 설정 딕셔너리"""
    return {
        "system": {
            "host": "0.0.0.0",
            "port": 12393,
        },
        "llm_configs": {
            "openai": {
                "api_key": "test-key",
                "model": "gpt-4o",
            }
        },
        "tts": {
            "provider": "edge_tts",
            "voice": "ko-KR-SunHiNeural",
        },
        "asr": {
            "provider": "sherpa_onnx",
        }
    }


@pytest.fixture
def mock_websocket():
    """Mock WebSocket 연결"""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock(return_value={"type": "text-input", "data": {"text": "Hello"}})
    ws.close = AsyncMock()
    return ws


async def async_generator(items: list) -> AsyncIterator:
    """비동기 제너레이터 헬퍼"""
    for item in items:
        yield item
