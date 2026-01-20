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

# audio.py가 생성되면 여기서 re-export됩니다
# from .audio import *  # noqa: F401, F403

__all__: list[str] = []
