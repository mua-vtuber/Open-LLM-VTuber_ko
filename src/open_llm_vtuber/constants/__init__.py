"""
Open-LLM-VTuber 상수 모듈.

이 모듈은 코드베이스 전체에서 사용되는 중앙 집중식 상수 정의를 제공합니다.
오디오 처리, 네트워크 설정 및 기타 시스템 전반의 값들을 포함합니다.

매직 넘버를 명명된 상수로 대체하여 코드 가독성과 유지보수성을 향상시킵니다.

사용 예시:
    from src.open_llm_vtuber.constants.audio import (
        WAV_HEADER_SIZE_BYTES,
        INT16_TO_FLOAT32_DIVISOR,
        FLOAT32_TO_INT16_MULTIPLIER,
    )
"""

# audio.py에서 오디오 관련 상수 re-export
from .audio import (
    WAV_HEADER_SIZE_BYTES,
    INT16_TO_FLOAT32_DIVISOR,
    FLOAT32_TO_INT16_MULTIPLIER,
    VAD_WINDOW_SIZE_16KHZ,
    VAD_WINDOW_SIZE_8KHZ,
)

__all__: list[str] = [
    # audio.py 상수
    "WAV_HEADER_SIZE_BYTES",
    "INT16_TO_FLOAT32_DIVISOR",
    "FLOAT32_TO_INT16_MULTIPLIER",
    "VAD_WINDOW_SIZE_16KHZ",
    "VAD_WINDOW_SIZE_8KHZ",
]
