"""
우선순위 큐 모듈

메시지 우선순위에 따라 처리 순서를 결정하는 비동기 큐 시스템입니다.
큐 오버플로우 시 낮은 우선순위 메시지부터 드롭합니다.
"""

import asyncio
import heapq
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .queue_config import QueueConfig, MessagePriority


@dataclass(order=True)
class PriorityMessage:
    """
    우선순위가 포함된 메시지 래퍼 클래스

    heapq는 최소 힙이므로, 우선순위가 높을수록 먼저 처리되도록
    priority 값을 음수로 저장합니다.
    """
    priority: int = field(compare=True)
    timestamp: float = field(compare=True)
    data: Dict[str, Any] = field(compare=False)

    def __init__(self, priority: int, data: Dict[str, Any]):
        """
        우선순위 메시지를 초기화합니다.

        Args:
            priority: 메시지 우선순위 (높을수록 먼저 처리)
            data: 메시지 데이터
        """
        # heapq는 최소 힙이므로 우선순위를 음수로 저장
        self.priority = -priority
        self.timestamp = datetime.now().timestamp()
        self.data = data


class PriorityQueue:
    """
    우선순위 기반 비동기 메시지 큐

    메시지를 우선순위에 따라 정렬하고, 큐 오버플로우 시
    낮은 우선순위 메시지부터 드롭합니다.
    """

    def __init__(
        self,
        config: Optional[QueueConfig] = None,
        alert_callback: Optional[Callable[[str, str, str], Coroutine[Any, Any, None]]] = None
    ):
        """
        우선순위 큐를 초기화합니다.

        Args:
            config: 큐 설정 객체 (None일 경우 기본 설정 사용)
            alert_callback: 알림 콜백 함수 (alert_type, message, severity)
        """
        self.config = config or QueueConfig()
        self._queue: List[PriorityMessage] = []
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(self._lock)

        # 메트릭 수집
        self._total_enqueued = 0
        self._total_dequeued = 0
        self._total_dropped = 0

        # 알림 콜백
        self._alert_callback = alert_callback
        self._last_overflow_alert: Optional[datetime] = None

    async def put(self, message: Dict[str, Any]) -> bool:
        """
        메시지를 큐에 추가합니다.

        Args:
            message: 추가할 메시지 (priority 필드 포함)

        Returns:
            bool: 메시지가 성공적으로 추가되었으면 True,
                  드롭되었으면 False
        """
        async with self._lock:
            # 메시지에서 우선순위 추출 (기본값: NORMAL)
            priority_value = message.get('priority', MessagePriority.NORMAL)

            # QueueConfig를 사용하여 우선순위 레벨 결정
            priority_level = self.config.get_priority_level(priority_value)

            # 우선순위 메시지 객체 생성
            priority_msg = PriorityMessage(
                priority=priority_level,
                data=message
            )

            # 큐 오버플로우 체크
            if len(self._queue) >= self.config.max_queue_size:
                # 드롭 처리
                dropped = await self._drop_low_priority_messages()
                if not dropped:
                    # 드롭할 메시지가 없고 큐가 가득 찬 경우
                    # 현재 메시지가 가장 낮은 우선순위인지 확인
                    if self._should_drop_current_message(priority_msg):
                        self._total_dropped += 1
                        # 오버플로우 알림 (5초에 1번만)
                        await self._send_overflow_alert(1)
                        return False
                else:
                    # 드롭이 발생한 경우 알림
                    await self._send_overflow_alert(dropped)

            # 큐에 메시지 추가
            heapq.heappush(self._queue, priority_msg)
            self._total_enqueued += 1

            # 대기 중인 get() 호출에 알림
            self._not_empty.notify()

            return True

    async def get(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        큐에서 우선순위가 가장 높은 메시지를 가져옵니다.

        Args:
            timeout: 대기 시간 (초), None이면 무한 대기

        Returns:
            Dict[str, Any]: 메시지 데이터, 타임아웃 시 None
        """
        async with self._not_empty:
            # 큐에 메시지가 있을 때까지 대기
            while not self._queue:
                try:
                    if timeout:
                        await asyncio.wait_for(
                            self._not_empty.wait(),
                            timeout=timeout
                        )
                    else:
                        await self._not_empty.wait()
                except asyncio.TimeoutError:
                    return None

            # 우선순위가 가장 높은 메시지 추출
            priority_msg = heapq.heappop(self._queue)
            self._total_dequeued += 1

            return priority_msg.data

    async def _drop_low_priority_messages(self) -> bool:
        """
        낮은 우선순위 메시지를 드롭합니다.

        Returns:
            bool: 메시지를 드롭했으면 True, 아니면 False
        """
        # 현재 큐에서 가장 낮은 우선순위 찾기
        if not self._queue:
            return False

        # priority가 음수로 저장되어 있으므로, 가장 큰 값(가장 덜 음수)이 가장 낮은 우선순위
        # 우선순위별로 메시지 그룹화
        low_priority_indices = []
        max_priority = float('-inf')  # 가장 낮은 우선순위 (가장 큰 음수가 아닌 값)

        for i, msg in enumerate(self._queue):
            if msg.priority > max_priority:
                max_priority = msg.priority
                low_priority_indices = [i]
            elif msg.priority == max_priority:
                low_priority_indices.append(i)

        # 낮은 우선순위 메시지 중 가장 오래된 것 드롭
        if low_priority_indices:
            # 설정에 따라 드롭할 개수 결정
            drop_count = min(
                self.config.overflow_drop_count,
                len(low_priority_indices)
            )

            # 타임스탬프로 정렬하여 가장 오래된 것부터 드롭
            # (priority, timestamp) 튜플로 정렬
            low_priority_with_timestamp = [
                (i, self._queue[i].timestamp) for i in low_priority_indices
            ]
            low_priority_with_timestamp.sort(key=lambda x: x[1])  # 오래된 것부터

            # 제거할 인덱스 추출 및 역순 정렬 (리스트 인덱스 변경 방지)
            indices_to_drop = [x[0] for x in low_priority_with_timestamp[:drop_count]]
            indices_to_drop.sort(reverse=True)

            for i in indices_to_drop:
                self._queue.pop(i)
                self._total_dropped += 1

            # 힙 재구성
            heapq.heapify(self._queue)

            return True

        return False

    def _should_drop_current_message(self, current_msg: PriorityMessage) -> bool:
        """
        현재 메시지를 드롭해야 하는지 판단합니다.

        Args:
            current_msg: 추가하려는 메시지

        Returns:
            bool: 드롭해야 하면 True
        """
        if not self._queue:
            return False

        # priority가 음수로 저장되어 있으므로, max()로 가장 큰 값(가장 낮은 우선순위)을 찾음
        lowest_priority_msg = max(self._queue, key=lambda x: x.priority)

        # 현재 메시지가 큐의 최저 우선순위보다 낮거나 같으면 드롭
        return current_msg.priority >= lowest_priority_msg.priority

    async def _send_overflow_alert(self, dropped_count: int) -> None:
        """
        오버플로우 알림을 전송합니다 (5초에 1번만)

        Args:
            dropped_count: 드롭된 메시지 수
        """
        if not self._alert_callback:
            return

        now = datetime.now()

        # 5초에 1번만 알림
        if self._last_overflow_alert:
            elapsed = (now - self._last_overflow_alert).total_seconds()
            if elapsed < 5.0:
                return

        try:
            await self._alert_callback(
                "overflow",
                f"큐 오버플로우: {dropped_count}개 메시지 드롭됨",
                "warning"
            )
            self._last_overflow_alert = now
        except Exception:
            # 알림 콜백 에러는 무시
            pass

    def qsize(self) -> int:
        """
        현재 큐에 있는 메시지 수를 반환합니다.

        Returns:
            int: 메시지 개수
        """
        return len(self._queue)

    def empty(self) -> bool:
        """
        큐가 비어있는지 확인합니다.

        Returns:
            bool: 비어있으면 True
        """
        return len(self._queue) == 0

    def full(self) -> bool:
        """
        큐가 가득 찼는지 확인합니다.

        Returns:
            bool: 가득 찼으면 True
        """
        return len(self._queue) >= self.config.max_queue_size

    def get_metrics(self) -> Dict[str, int]:
        """
        큐 메트릭 정보를 반환합니다.

        Returns:
            Dict[str, int]: 메트릭 정보
        """
        return {
            'total_enqueued': self._total_enqueued,
            'total_dequeued': self._total_dequeued,
            'total_dropped': self._total_dropped,
            'current_size': self.qsize(),
            'max_size': self.config.max_queue_size
        }

    async def clear(self) -> int:
        """
        큐의 모든 메시지를 제거합니다.

        Returns:
            int: 제거된 메시지 개수
        """
        async with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count
