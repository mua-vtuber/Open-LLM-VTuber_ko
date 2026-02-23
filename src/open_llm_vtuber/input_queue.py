"""
입력 큐 매니저 모듈

동시에 들어오는 여러 입력(채팅 메시지, 음성 명령)을 큐에 저장하고
순차적으로 처리하는 시스템입니다.
초당 10개 이상의 메시지를 안정적으로 처리합니다.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, List, Optional
from datetime import datetime, timedelta
from enum import Enum

from .priority_queue import PriorityQueue
from .queue_config import QueueConfig, MessagePriority
from .priority_rules import InputSource


logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    """메트릭 스냅샷 데이터클래스"""

    timestamp: datetime
    queue_size: int
    processing_rate: float
    avg_processing_time: float
    total_dropped: int
    total_processed: int


class InputType(Enum):
    """입력 타입 분류"""

    CHAT = "chat"  # 채팅 메시지
    VOICE = "voice"  # 음성 명령
    SUPERCHAT = "superchat"  # 슈퍼챗
    MEMBERSHIP = "membership"  # 멤버십 메시지


class InputQueueManager:
    """
    입력 큐 관리자

    여러 소스로부터 들어오는 입력을 큐에 저장하고,
    백그라운드 워커를 통해 순차적으로 처리합니다.
    초당 10개 이상의 메시지를 안정적으로 처리할 수 있습니다.
    """

    def __init__(
        self,
        config: Optional[QueueConfig] = None,
        message_handler: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
        alert_callback: Optional[Callable[[str, str, str], Coroutine]] = None,
    ):
        """
        입력 큐 매니저를 초기화합니다.

        Args:
            config: 큐 설정 객체 (None일 경우 기본 설정 사용)
            message_handler: 메시지를 처리할 비동기 함수
            alert_callback: 알림 콜백 함수 (alert_type, message, severity)
        """
        self.config = config or QueueConfig()
        self._queue = PriorityQueue(self.config, alert_callback=alert_callback)
        self._message_handler = message_handler
        self._alert_callback = alert_callback

        # 워커 관리
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

        # 메트릭 수집
        self._total_received = 0
        self._total_processed = 0
        self._total_failed = 0
        self._processing_times: List[float] = []

        # 현재 처리 중인 메시지
        self._current_message: Optional[Dict[str, Any]] = None
        self._processing_start_time: Optional[float] = None

        # 메트릭 히스토리 (최근 5분, 1초 간격 = 300개)
        self._metric_history: deque[MetricSnapshot] = deque(maxlen=300)
        self._last_snapshot_time: Optional[datetime] = None

        logger.info(f"InputQueueManager 초기화 완료: {self.config}")

    async def start(self):
        """
        입력 큐 매니저를 시작하고 워커를 실행합니다.
        """
        if self._running:
            logger.warning("InputQueueManager가 이미 실행 중입니다")
            return

        self._running = True
        self._shutdown_event.clear()

        # 워커 시작
        for i in range(self.config.worker_count):
            worker = asyncio.create_task(
                self._worker(worker_id=i), name=f"input_queue_worker_{i}"
            )
            self._workers.append(worker)

        logger.info(f"InputQueueManager 시작됨 (워커 {self.config.worker_count}개)")

    async def stop(self, timeout: float = 5.0):
        """
        입력 큐 매니저를 중지합니다.

        Args:
            timeout: 워커 종료 대기 시간 (초)
        """
        if not self._running:
            logger.warning("InputQueueManager가 실행 중이지 않습니다")
            return

        logger.info("InputQueueManager 중지 중...")
        self._running = False
        self._shutdown_event.set()

        # 워커들이 종료될 때까지 대기
        if self._workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("일부 워커가 시간 내에 종료되지 않았습니다")
                # 강제 취소
                for worker in self._workers:
                    if not worker.done():
                        worker.cancel()

        self._workers.clear()
        logger.info("InputQueueManager 중지 완료")

    async def enqueue(self, message: Dict[str, Any]) -> bool:
        """
        입력 메시지를 큐에 추가합니다.

        Args:
            message: 추가할 메시지 (type, content, priority 등 포함)

        Returns:
            bool: 메시지가 성공적으로 추가되었으면 True,
                  드롭되었으면 False
        """
        if not self._running:
            logger.warning("InputQueueManager가 실행 중이지 않습니다")
            return False

        # 메시지 타입에 따라 우선순위 자동 설정
        if "priority" not in message:
            message["priority"] = self._determine_priority(message)

        # 메시지에 타임스탬프 추가
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()

        # 큐에 추가
        success = await self._queue.put(message)

        if success:
            self._total_received += 1
            if self.config.enable_debug_logging:
                logger.debug(f"메시지 큐에 추가됨: {message.get('type', 'unknown')}")
        else:
            logger.warning(
                f"메시지 드롭됨 (큐 오버플로우): {message.get('type', 'unknown')}"
            )

        return success

    async def _worker(self, worker_id: int):
        """
        백그라운드 워커: 큐에서 메시지를 가져와 처리합니다.

        Args:
            worker_id: 워커 식별자
        """
        logger.info(f"워커 {worker_id} 시작됨")

        while self._running:
            try:
                # 큐에서 메시지 가져오기
                message = await self._queue.get(
                    timeout=self.config.message_processing_interval
                )

                if message is None:
                    # 타임아웃 또는 큐가 비어있음
                    # 메트릭 스냅샷 기록
                    self._record_metric_snapshot()
                    # 짧은 대기 후 다시 시도
                    await asyncio.sleep(0.01)
                    continue

                # 메시지 처리
                await self._process_message(message, worker_id)

                # 메트릭 스냅샷 기록
                self._record_metric_snapshot()

                # 처리 간격 적용 (초당 10+ 메시지를 위해 0.1초)
                await asyncio.sleep(self.config.message_processing_interval)

            except asyncio.CancelledError:
                logger.info(f"워커 {worker_id} 취소됨")
                break
            except Exception as e:
                logger.error(f"워커 {worker_id} 에러: {e}", exc_info=True)
                # 짧은 대기 후 계속
                await asyncio.sleep(0.1)

        logger.info(f"워커 {worker_id} 종료됨")

    async def _process_message(self, message: Dict[str, Any], worker_id: int):
        """
        메시지를 처리합니다.

        Args:
            message: 처리할 메시지
            worker_id: 워커 식별자
        """
        start_time = datetime.now()
        self._current_message = message
        self._processing_start_time = start_time.timestamp()

        try:
            if self._message_handler:
                # 사용자 정의 핸들러 호출
                await self._message_handler(message)
            else:
                # 기본 처리: 로깅만
                if self.config.enable_debug_logging:
                    logger.debug(
                        f"워커 {worker_id}가 메시지 처리: "
                        f"{message.get('type', 'unknown')}"
                    )

            # 처리 성공
            self._total_processed += 1

            # 처리 시간 기록
            processing_time = (datetime.now() - start_time).total_seconds()
            self._processing_times.append(processing_time)

            # 처리 시간 기록은 최근 100개만 유지
            if len(self._processing_times) > 100:
                self._processing_times = self._processing_times[-100:]

            if self.config.enable_metrics:
                logger.debug(f"메시지 처리 완료 (소요시간: {processing_time:.3f}초)")

        except Exception as e:
            self._total_failed += 1
            logger.error(
                f"메시지 처리 실패: {message.get('type', 'unknown')}, 에러: {e}",
                exc_info=True,
            )
        finally:
            self._current_message = None
            self._processing_start_time = None

    def _determine_priority(self, message: Dict[str, Any]) -> int:
        """
        메시지 타입에 따라 우선순위를 자동으로 결정합니다.

        Args:
            message: 메시지 객체

        Returns:
            int: 우선순위 값
        """
        input_type = message.get("type", "")

        # 슈퍼챗, 멤버십 메시지는 높은 우선순위
        if input_type in [InputType.SUPERCHAT.value, InputType.MEMBERSHIP.value]:
            return MessagePriority.HIGH

        # 음성 명령은 일반 우선순위
        if input_type == InputType.VOICE.value:
            return MessagePriority.NORMAL

        # 채팅 메시지는 일반 우선순위 (기본값)
        return MessagePriority.NORMAL

    def _apply_priority_rules(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        우선순위 규칙을 메시지에 적용합니다.

        메시지의 입력 소스와 현재 처리 상태를 고려하여
        동적으로 우선순위와 대기 시간을 계산합니다.

        Args:
            message: 적용할 메시지 객체

        Returns:
            Dict[str, Any]: 우선순위 규칙이 적용된 메시지 (원본 수정)
        """
        # 메시지 타입을 InputSource로 변환
        input_type = message.get("type", "")
        input_source = self._convert_to_input_source(input_type)

        # 현재 처리 중인 메시지의 소스 확인
        current_source = None
        if self._current_message:
            current_type = self._current_message.get("type", "")
            current_source = self._convert_to_input_source(current_type)

        # 우선순위 규칙에 따라 우선순위 값 계산
        priority_value = self.config.priority_rules.get_priority_value(
            source=input_source, is_processing=current_source
        )

        # 대기 시간 계산
        delay_time = self.config.priority_rules.get_delay_time(
            source=input_source, is_processing=current_source
        )

        # 메시지에 계산된 값 적용
        message["priority"] = priority_value
        message["delay_time"] = delay_time

        # 중단 가능 여부 계산 (현재 처리 중인 메시지가 있을 때)
        if current_source:
            should_interrupt = self.config.priority_rules.should_interrupt(
                new_source=input_source, current_source=current_source
            )
            message["should_interrupt"] = should_interrupt
        else:
            message["should_interrupt"] = False

        if self.config.enable_debug_logging:
            logger.debug(
                f"우선순위 규칙 적용: type={input_type}, "
                f"priority={priority_value}, delay={delay_time}s, "
                f"interrupt={message['should_interrupt']}"
            )

        return message

    def _convert_to_input_source(self, input_type: str) -> InputSource:
        """
        InputType을 InputSource로 변환합니다.

        Args:
            input_type: 메시지 타입 문자열

        Returns:
            InputSource: 변환된 입력 소스
        """
        # 슈퍼챗, 멤버십 메시지는 슈퍼챗 소스로
        if input_type in [InputType.SUPERCHAT.value, InputType.MEMBERSHIP.value]:
            return InputSource.SUPERCHAT

        # 음성 명령은 음성 소스로
        if input_type == InputType.VOICE.value:
            return InputSource.VOICE

        # 채팅 메시지는 채팅 소스로 (기본값)
        return InputSource.CHAT

    def set_message_handler(self, handler: Callable[[Dict[str, Any]], Coroutine]):
        """
        메시지 처리 핸들러를 설정합니다.

        Args:
            handler: 메시지를 처리할 비동기 함수
        """
        self._message_handler = handler
        logger.info("메시지 핸들러 설정됨")

    def get_status(self) -> Dict[str, Any]:
        """
        큐 매니저의 현재 상태를 반환합니다.

        Returns:
            Dict[str, Any]: 상태 정보
        """
        queue_metrics = self._queue.get_metrics()

        # 평균 처리 시간 계산
        avg_processing_time = 0.0
        if self._processing_times:
            avg_processing_time = sum(self._processing_times) / len(
                self._processing_times
            )

        return {
            "running": self._running,
            "worker_count": len(self._workers),
            "current_message": self._current_message,
            "queue_size": queue_metrics["current_size"],
            "queue_max_size": queue_metrics["max_size"],
            "total_received": self._total_received,
            "total_processed": self._total_processed,
            "total_failed": self._total_failed,
            "total_enqueued": queue_metrics["total_enqueued"],
            "total_dequeued": queue_metrics["total_dequeued"],
            "total_dropped": queue_metrics["total_dropped"],
            "avg_processing_time": avg_processing_time,
            "processing_rate": self._calculate_processing_rate(),
        }

    def _calculate_processing_rate(self) -> float:
        """
        초당 처리 메시지 수를 계산합니다.

        Returns:
            float: 초당 처리 메시지 수
        """
        if not self._processing_times:
            return 0.0

        # 최근 처리 시간들의 평균으로 처리율 추정
        avg_time = sum(self._processing_times) / len(self._processing_times)

        if avg_time > 0:
            return 1.0 / avg_time

        return 0.0

    def _calculate_avg_processing_time(self) -> float:
        """
        평균 처리 시간을 계산합니다.

        Returns:
            float: 평균 처리 시간 (초)
        """
        if not self._processing_times:
            return 0.0
        return sum(self._processing_times) / len(self._processing_times)

    def _record_metric_snapshot(self) -> None:
        """현재 메트릭을 히스토리에 기록"""
        now = datetime.now()

        # 1초 간격으로만 기록
        if self._last_snapshot_time:
            elapsed = (now - self._last_snapshot_time).total_seconds()
            if elapsed < 1.0:
                return

        queue_metrics = self._queue.get_metrics()

        snapshot = MetricSnapshot(
            timestamp=now,
            queue_size=queue_metrics["current_size"],
            processing_rate=self._calculate_processing_rate(),
            avg_processing_time=self._calculate_avg_processing_time(),
            total_dropped=queue_metrics["total_dropped"],
            total_processed=self._total_processed,
        )

        self._metric_history.append(snapshot)
        self._last_snapshot_time = now

    def get_metric_history(self, minutes: int = 5) -> List[dict]:
        """
        최근 N분간 메트릭 히스토리를 반환합니다.

        Args:
            minutes: 조회할 기간 (분)

        Returns:
            List[dict]: 메트릭 히스토리 리스트
        """
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [
            {
                "timestamp": s.timestamp.isoformat(),
                "queue_size": s.queue_size,
                "processing_rate": s.processing_rate,
                "avg_processing_time": s.avg_processing_time,
                "total_dropped": s.total_dropped,
                "total_processed": s.total_processed,
            }
            for s in self._metric_history
            if s.timestamp >= cutoff
        ]

    def get_metrics(self) -> Dict[str, Any]:
        """
        큐 매니저의 메트릭 정보를 반환합니다.

        Returns:
            Dict[str, Any]: 메트릭 정보
        """
        return self.get_status()

    async def clear_queue(self) -> int:
        """
        큐의 모든 메시지를 제거합니다.

        Returns:
            int: 제거된 메시지 개수
        """
        count = await self._queue.clear()
        logger.info(f"큐 초기화: {count}개 메시지 제거됨")
        return count

    def is_running(self) -> bool:
        """
        큐 매니저가 실행 중인지 확인합니다.

        Returns:
            bool: 실행 중이면 True
        """
        return self._running

    def queue_size(self) -> int:
        """
        현재 큐에 있는 메시지 수를 반환합니다.

        Returns:
            int: 메시지 개수
        """
        return self._queue.qsize()

    def is_queue_empty(self) -> bool:
        """
        큐가 비어있는지 확인합니다.

        Returns:
            bool: 비어있으면 True
        """
        return self._queue.empty()

    def is_queue_full(self) -> bool:
        """
        큐가 가득 찼는지 확인합니다.

        Returns:
            bool: 가득 찼으면 True
        """
        return self._queue.full()
