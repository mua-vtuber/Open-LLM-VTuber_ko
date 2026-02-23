"""
우선순위 규칙 모듈

채팅 입력과 음성 대화 간의 우선순위를 설정하고 관리합니다.
스트리머가 상황에 따라 어떤 입력을 우선 처리할지 설정할 수 있으며,
동시 입력 발생 시 충돌 없이 자연스럽게 처리합니다.
"""

import os
from enum import Enum
from typing import Any, Dict, Optional
from loguru import logger


class InputSource(str, Enum):
    """입력 소스 타입"""

    CHAT = "chat"  # 채팅 메시지
    VOICE = "voice"  # 음성 입력
    SUPERCHAT = "superchat"  # 슈퍼챗/후원 메시지


class PriorityMode(str, Enum):
    """
    우선순위 처리 모드

    각 모드는 채팅과 음성 입력이 동시에 발생했을 때
    어떤 입력을 우선 처리할지 결정합니다.
    """

    CHAT_FIRST = "chat_first"  # 채팅 우선
    VOICE_FIRST = "voice_first"  # 음성 우선
    SUPERCHAT_PRIORITY = "superchat_priority"  # 슈퍼챗만 우선, 나머지는 음성 우선
    BALANCED = "balanced"  # 균형 모드 (선착순)


class PriorityRules:
    """
    우선순위 규칙 설정 클래스

    채팅과 음성 입력 간의 우선순위 규칙을 관리하고,
    동시 입력 발생 시 처리 방식을 결정합니다.
    """

    def __init__(self):
        """환경변수에서 우선순위 규칙을 로드합니다."""

        # 우선순위 모드 (기본값: BALANCED)
        mode_str = os.getenv("PRIORITY_MODE", "balanced")
        try:
            self.priority_mode: PriorityMode = PriorityMode(mode_str)
        except ValueError:
            # 잘못된 값이면 기본값 사용
            self.priority_mode = PriorityMode.BALANCED

        # 동시 입력 발생 시 대기 시간 (초 단위, 기본값: 2초)
        # 이 시간 동안 다른 입력이 없으면 현재 입력을 처리
        self.wait_time: float = float(os.getenv("PRIORITY_WAIT_TIME", "2.0"))

        # 중단 허용 여부 (기본값: False)
        # True일 경우 우선순위가 높은 입력이 들어오면 현재 처리 중단
        self.allow_interruption: bool = os.getenv(
            "PRIORITY_ALLOW_INTERRUPTION", "false"
        ).lower() in ("true", "1", "yes")

        # 슈퍼챗 항상 우선 처리 (기본값: True)
        # 모든 모드에서 슈퍼챗은 항상 최우선 처리
        self.superchat_always_priority: bool = os.getenv(
            "PRIORITY_SUPERCHAT_ALWAYS", "true"
        ).lower() in ("true", "1", "yes")

        # 음성 대화 중 채팅 큐 대기 시간 (초 단위, 기본값: 5초)
        # 음성 대화 중일 때 채팅을 큐에 얼마나 대기시킬지
        self.voice_active_chat_delay: float = float(
            os.getenv("PRIORITY_VOICE_ACTIVE_CHAT_DELAY", "5.0")
        )

        # 채팅 응답 중 음성 입력 대기 시간 (초 단위, 기본값: 3초)
        # 채팅 응답 중일 때 음성 입력을 얼마나 대기시킬지
        self.chat_active_voice_delay: float = float(
            os.getenv("PRIORITY_CHAT_ACTIVE_VOICE_DELAY", "3.0")
        )

    def get_priority_value(
        self, source: InputSource, is_processing: Optional[InputSource] = None
    ) -> int:
        """
        입력 소스에 대한 우선순위 값을 계산합니다.

        Args:
            source: 입력 소스 타입
            is_processing: 현재 처리 중인 입력 소스 (None이면 대기 중)

        Returns:
            int: 우선순위 값 (높을수록 우선 처리)
        """
        # 슈퍼챗은 항상 최우선
        if source == InputSource.SUPERCHAT and self.superchat_always_priority:
            return 100

        # 현재 처리 중인 입력이 없는 경우
        if is_processing is None:
            if self.priority_mode == PriorityMode.CHAT_FIRST:
                return 80 if source == InputSource.CHAT else 70
            elif self.priority_mode == PriorityMode.VOICE_FIRST:
                return 80 if source == InputSource.VOICE else 70
            elif self.priority_mode == PriorityMode.SUPERCHAT_PRIORITY:
                # 슈퍼챗 제외하고는 음성 우선
                return 80 if source == InputSource.VOICE else 70
            else:  # BALANCED
                return 75  # 모두 동일한 우선순위

        # 현재 처리 중인 입력이 있는 경우
        # 중단 허용 여부에 따라 다르게 처리
        if not self.allow_interruption:
            # 중단 불허: 현재 처리 중인 입력이 더 높은 우선순위
            return 50

        # 중단 허용: 모드에 따라 우선순위 결정
        if self.priority_mode == PriorityMode.CHAT_FIRST:
            if source == InputSource.CHAT and is_processing == InputSource.VOICE:
                return 90  # 채팅이 음성 중단 가능
            return 50
        elif self.priority_mode == PriorityMode.VOICE_FIRST:
            if source == InputSource.VOICE and is_processing == InputSource.CHAT:
                return 90  # 음성이 채팅 중단 가능
            return 50
        elif self.priority_mode == PriorityMode.SUPERCHAT_PRIORITY:
            # 슈퍼챗 외에는 음성이 우선
            if source == InputSource.VOICE and is_processing == InputSource.CHAT:
                return 90
            return 50
        else:  # BALANCED
            # 균형 모드에서는 중단 불가
            return 50

    def get_delay_time(
        self, source: InputSource, is_processing: Optional[InputSource] = None
    ) -> float:
        """
        입력 소스에 대한 대기 시간을 계산합니다.

        Args:
            source: 입력 소스 타입
            is_processing: 현재 처리 중인 입력 소스

        Returns:
            float: 대기 시간 (초)
        """
        # 슈퍼챗은 대기 없음
        if source == InputSource.SUPERCHAT and self.superchat_always_priority:
            return 0.0

        # 현재 처리 중인 입력이 없으면 기본 대기 시간
        if is_processing is None:
            return self.wait_time

        # 음성 대화 중 채팅이 들어온 경우
        if is_processing == InputSource.VOICE and source == InputSource.CHAT:
            return self.voice_active_chat_delay

        # 채팅 응답 중 음성이 들어온 경우
        if is_processing == InputSource.CHAT and source == InputSource.VOICE:
            return self.chat_active_voice_delay

        return self.wait_time

    def should_interrupt(
        self, new_source: InputSource, current_source: InputSource
    ) -> bool:
        """
        새로운 입력이 현재 처리를 중단시켜야 하는지 판단합니다.

        Args:
            new_source: 새로 들어온 입력 소스
            current_source: 현재 처리 중인 입력 소스

        Returns:
            bool: 중단해야 하면 True, 아니면 False
        """
        # 중단 불허 설정인 경우
        if not self.allow_interruption:
            # 슈퍼챗만 예외
            return (
                new_source == InputSource.SUPERCHAT and self.superchat_always_priority
            )

        # 슈퍼챗은 항상 중단 가능
        if new_source == InputSource.SUPERCHAT and self.superchat_always_priority:
            return True

        # 모드별 중단 규칙
        if self.priority_mode == PriorityMode.CHAT_FIRST:
            return (
                new_source == InputSource.CHAT and current_source == InputSource.VOICE
            )
        elif self.priority_mode == PriorityMode.VOICE_FIRST:
            return (
                new_source == InputSource.VOICE and current_source == InputSource.CHAT
            )
        elif self.priority_mode == PriorityMode.SUPERCHAT_PRIORITY:
            # 슈퍼챗 외에는 음성이 채팅 중단 가능
            return (
                new_source == InputSource.VOICE and current_source == InputSource.CHAT
            )
        else:  # BALANCED
            # 균형 모드에서는 중단 불가
            return False

    def validate(self) -> bool:
        """
        설정 값의 유효성을 검사합니다.

        Returns:
            bool: 모든 설정이 유효하면 True, 아니면 False
        """
        if self.wait_time < 0:
            return False

        if self.voice_active_chat_delay < 0:
            return False

        if self.chat_active_voice_delay < 0:
            return False

        # PriorityMode enum 값 확인
        if not isinstance(self.priority_mode, PriorityMode):
            return False

        return True

    def to_dict(self) -> dict:
        """
        규칙을 딕셔너리로 변환합니다.

        Returns:
            dict: 규칙 설정 정보
        """
        return {
            "priority_mode": self.priority_mode.value,
            "wait_time": self.wait_time,
            "allow_interruption": self.allow_interruption,
            "superchat_always_priority": self.superchat_always_priority,
            "voice_active_chat_delay": self.voice_active_chat_delay,
            "chat_active_voice_delay": self.chat_active_voice_delay,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PriorityRules":
        """
        딕셔너리로부터 PriorityRules 객체를 생성합니다.

        Args:
            data: 규칙 설정 정보

        Returns:
            PriorityRules: 생성된 규칙 객체
        """
        rules = cls()

        if "priority_mode" in data:
            try:
                rules.priority_mode = PriorityMode(data["priority_mode"])
            except ValueError:
                pass  # 기본값 유지

        if "wait_time" in data:
            rules.wait_time = float(data["wait_time"])

        if "allow_interruption" in data:
            rules.allow_interruption = bool(data["allow_interruption"])

        if "superchat_always_priority" in data:
            rules.superchat_always_priority = bool(data["superchat_always_priority"])

        if "voice_active_chat_delay" in data:
            rules.voice_active_chat_delay = float(data["voice_active_chat_delay"])

        if "chat_active_voice_delay" in data:
            rules.chat_active_voice_delay = float(data["chat_active_voice_delay"])

        return rules

    def update_from_dict(self, data: Dict[str, Any]) -> bool:
        """
        딕셔너리에서 규칙을 업데이트합니다.
        None이 아닌 필드만 업데이트합니다.

        Args:
            data: 업데이트할 필드들의 딕셔너리

        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            # priority_mode 업데이트
            if "priority_mode" in data and data["priority_mode"] is not None:
                try:
                    self.priority_mode = PriorityMode(data["priority_mode"])
                except ValueError:
                    logger.error(
                        f"Invalid priority_mode value: {data['priority_mode']}"
                    )
                    return False

            # wait_time 업데이트 (범위: 0 ~ 30)
            if "wait_time" in data and data["wait_time"] is not None:
                wait_time = float(data["wait_time"])
                if wait_time < 0 or wait_time > 30:
                    logger.error(f"wait_time out of range: {wait_time}")
                    return False
                self.wait_time = wait_time

            # allow_interruption 업데이트
            if "allow_interruption" in data and data["allow_interruption"] is not None:
                self.allow_interruption = bool(data["allow_interruption"])

            # superchat_always_priority 업데이트
            if (
                "superchat_always_priority" in data
                and data["superchat_always_priority"] is not None
            ):
                self.superchat_always_priority = bool(data["superchat_always_priority"])

            # voice_active_chat_delay 업데이트 (범위: 0 ~ 60)
            if (
                "voice_active_chat_delay" in data
                and data["voice_active_chat_delay"] is not None
            ):
                voice_delay = float(data["voice_active_chat_delay"])
                if voice_delay < 0 or voice_delay > 60:
                    logger.error(f"voice_active_chat_delay out of range: {voice_delay}")
                    return False
                self.voice_active_chat_delay = voice_delay

            # chat_active_voice_delay 업데이트 (범위: 0 ~ 60)
            if (
                "chat_active_voice_delay" in data
                and data["chat_active_voice_delay"] is not None
            ):
                chat_delay = float(data["chat_active_voice_delay"])
                if chat_delay < 0 or chat_delay > 60:
                    logger.error(f"chat_active_voice_delay out of range: {chat_delay}")
                    return False
                self.chat_active_voice_delay = chat_delay

            # 최종 유효성 검사
            return self.validate()

        except Exception as e:
            logger.error(f"Failed to update priority rules: {e}")
            return False

    def __repr__(self) -> str:
        """규칙 정보를 문자열로 반환합니다."""
        return (
            f"PriorityRules("
            f"mode={self.priority_mode.value}, "
            f"wait_time={self.wait_time}s, "
            f"allow_interruption={self.allow_interruption}, "
            f"superchat_always_priority={self.superchat_always_priority})"
        )
