"""
큐 시스템 설정 모듈

환경변수를 기반으로 큐 시스템의 동작을 제어하는 설정을 관리합니다.
"""

import os
from enum import IntEnum

from .priority_rules import PriorityRules


class MessagePriority(IntEnum):
    """메시지 우선순위 레벨"""
    HIGH = 3    # 슈퍼챗, 멤버십 메시지
    NORMAL = 2  # 일반 채팅 메시지
    LOW = 1     # 반복 메시지, 스팸성 메시지


class QueueConfig:
    """
    큐 시스템 설정 클래스

    환경변수를 통해 큐 시스템의 동작을 제어합니다.
    """

    def __init__(self):
        """환경변수에서 설정 값을 로드합니다."""

        # 최대 큐 사이즈 (기본값: 100)
        self.max_queue_size: int = int(
            os.getenv("QUEUE_MAX_SIZE", "100")
        )

        # 메시지 처리 간격 (초 단위, 기본값: 0.1초 = 초당 10개)
        self.message_processing_interval: float = float(
            os.getenv("QUEUE_PROCESSING_INTERVAL", "0.1")
        )

        # 큐 오버플로우 시 드롭할 메시지 개수 (기본값: 10)
        self.overflow_drop_count: int = int(
            os.getenv("QUEUE_OVERFLOW_DROP_COUNT", "10")
        )

        # 메시지 우선순위 임계값
        self.priority_threshold_high: int = MessagePriority.HIGH
        self.priority_threshold_normal: int = MessagePriority.NORMAL
        self.priority_threshold_low: int = MessagePriority.LOW

        # 큐 상태 업데이트 간격 (초 단위, 기본값: 1초)
        self.status_update_interval: float = float(
            os.getenv("QUEUE_STATUS_UPDATE_INTERVAL", "1.0")
        )

        # 큐 워커 수 (기본값: 1, 비동기 처리)
        self.worker_count: int = int(
            os.getenv("QUEUE_WORKER_COUNT", "1")
        )

        # 메트릭 수집 활성화 여부
        self.enable_metrics: bool = os.getenv(
            "QUEUE_ENABLE_METRICS", "true"
        ).lower() in ("true", "1", "yes")

        # 디버그 로깅 활성화 여부
        self.enable_debug_logging: bool = os.getenv(
            "QUEUE_DEBUG_LOGGING", "false"
        ).lower() in ("true", "1", "yes")

        # 우선순위 규칙 설정
        self.priority_rules: PriorityRules = PriorityRules()

    def validate(self) -> bool:
        """
        설정 값의 유효성을 검사합니다.

        Returns:
            bool: 모든 설정이 유효하면 True, 아니면 False
        """
        if self.max_queue_size <= 0:
            return False

        if self.message_processing_interval <= 0:
            return False

        if self.overflow_drop_count <= 0:
            return False

        if self.status_update_interval <= 0:
            return False

        if self.worker_count <= 0:
            return False

        # 우선순위 규칙 유효성 검증
        if not self.priority_rules.validate():
            return False

        return True

    def get_priority_level(self, priority_value: int) -> MessagePriority:
        """
        우선순위 값을 MessagePriority enum으로 변환합니다.

        Args:
            priority_value: 우선순위 정수 값

        Returns:
            MessagePriority: 해당하는 우선순위 레벨
        """
        if priority_value >= self.priority_threshold_high:
            return MessagePriority.HIGH
        elif priority_value >= self.priority_threshold_normal:
            return MessagePriority.NORMAL
        else:
            return MessagePriority.LOW

    def __repr__(self) -> str:
        """설정 정보를 문자열로 반환합니다."""
        return (
            f"QueueConfig("
            f"max_size={self.max_queue_size}, "
            f"processing_interval={self.message_processing_interval}s, "
            f"overflow_drop={self.overflow_drop_count}, "
            f"workers={self.worker_count}, "
            f"metrics_enabled={self.enable_metrics})"
        )
