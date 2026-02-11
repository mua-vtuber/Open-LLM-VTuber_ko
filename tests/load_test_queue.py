#!/usr/bin/env python3
"""
입력 큐 부하 테스트

초당 10+ 메시지를 전송하여 큐 시스템의 안정성을 검증합니다.
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import logging

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.open_llm_vtuber.input_queue import InputQueueManager, InputType
from src.open_llm_vtuber.queue_config import QueueConfig, MessagePriority


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LoadTestStats:
    """부하 테스트 통계 수집 클래스"""

    def __init__(self):
        self.total_sent = 0
        self.total_queued = 0
        self.total_dropped = 0
        self.total_processed = 0
        self.start_time: float = 0
        self.end_time: float = 0
        self.message_types: Dict[str, int] = {}

    def record_sent(self, message_type: str):
        """전송된 메시지 기록"""
        self.total_sent += 1
        self.message_types[message_type] = self.message_types.get(message_type, 0) + 1

    def record_queued(self, success: bool):
        """큐 추가 결과 기록"""
        if success:
            self.total_queued += 1
        else:
            self.total_dropped += 1

    def get_duration(self) -> float:
        """테스트 소요 시간 반환"""
        return self.end_time - self.start_time

    def get_messages_per_second(self) -> float:
        """초당 전송 메시지 수 계산"""
        duration = self.get_duration()
        if duration > 0:
            return self.total_sent / duration
        return 0

    def print_summary(self):
        """테스트 결과 요약 출력"""
        duration = self.get_duration()
        msg_per_sec = self.get_messages_per_second()

        logger.info("=" * 60)
        logger.info("부하 테스트 결과 요약")
        logger.info("=" * 60)
        logger.info(f"총 전송 메시지: {self.total_sent}개")
        logger.info(f"큐 추가 성공: {self.total_queued}개")
        logger.info(f"드롭된 메시지: {self.total_dropped}개")
        logger.info(f"테스트 소요 시간: {duration:.2f}초")
        logger.info(f"평균 전송 속도: {msg_per_sec:.2f} messages/sec")
        logger.info(f"메시지 타입별 분포:")
        for msg_type, count in self.message_types.items():
            logger.info(f"  - {msg_type}: {count}개")
        logger.info("=" * 60)


async def dummy_message_handler(message: Dict[str, Any]):
    """
    더미 메시지 핸들러 (테스트용)

    실제 처리 대신 짧은 대기만 수행합니다.
    """
    await asyncio.sleep(0.05)  # 50ms 처리 시간 시뮬레이션


async def send_messages_burst(
    queue_manager: InputQueueManager,
    stats: LoadTestStats,
    messages_per_second: int,
    duration_seconds: int
):
    """
    지정된 속도로 메시지를 전송합니다.

    Args:
        queue_manager: 입력 큐 매니저
        stats: 통계 수집 객체
        messages_per_second: 초당 전송할 메시지 수
        duration_seconds: 테스트 지속 시간 (초)
    """
    interval = 1.0 / messages_per_second
    total_messages = messages_per_second * duration_seconds

    logger.info(
        f"부하 테스트 시작: {messages_per_second} msgs/sec, "
        f"{duration_seconds}초 동안 (총 {total_messages}개 메시지)"
    )

    stats.start_time = datetime.now().timestamp()

    for i in range(total_messages):
        # 다양한 메시지 타입 생성
        message_type = InputType.CHAT.value
        priority = MessagePriority.NORMAL

        # 10% 확률로 HIGH priority 메시지 생성 (슈퍼챗 시뮬레이션)
        if i % 10 == 0:
            message_type = InputType.SUPERCHAT.value
            priority = MessagePriority.HIGH

        # 5% 확률로 멤버십 메시지 생성
        elif i % 20 == 0:
            message_type = InputType.MEMBERSHIP.value
            priority = MessagePriority.HIGH

        # 메시지 생성
        message = {
            'type': message_type,
            'content': f'테스트 메시지 #{i + 1}',
            'priority': priority,
            'timestamp': datetime.now().isoformat(),
            'test_id': i,
        }

        # 메시지 전송
        stats.record_sent(message_type)
        success = await queue_manager.enqueue(message)
        stats.record_queued(success)

        # 1초마다 진행 상황 출력
        if (i + 1) % messages_per_second == 0:
            elapsed = (i + 1) // messages_per_second
            queue_status = queue_manager.get_status()
            logger.info(
                f"[{elapsed}/{duration_seconds}초] "
                f"전송: {stats.total_sent}, "
                f"큐 크기: {queue_status['queue_size']}, "
                f"처리 완료: {queue_status['total_processed']}, "
                f"드롭: {stats.total_dropped}"
            )

        # 다음 메시지까지 대기
        await asyncio.sleep(interval)

    stats.end_time = datetime.now().timestamp()
    logger.info("메시지 전송 완료")


async def monitor_queue(queue_manager: InputQueueManager, interval: float = 5.0):
    """
    큐 상태를 주기적으로 모니터링합니다.

    Args:
        queue_manager: 입력 큐 매니저
        interval: 모니터링 간격 (초)
    """
    while queue_manager.is_running():
        status = queue_manager.get_status()
        logger.info(
            f"큐 상태 - "
            f"크기: {status['queue_size']}/{status['queue_max_size']}, "
            f"수신: {status['total_received']}, "
            f"처리: {status['total_processed']}, "
            f"실패: {status['total_failed']}, "
            f"드롭: {status['total_dropped']}, "
            f"평균 처리 시간: {status['avg_processing_time']:.3f}초"
        )
        await asyncio.sleep(interval)


async def run_load_test():
    """부하 테스트 실행"""

    # 테스트 파라미터
    messages_per_second = 15  # 초당 15개 메시지 (요구사항: 10+)
    duration_seconds = 30      # 30초 동안 테스트

    logger.info("=" * 60)
    logger.info("입력 큐 부하 테스트 시작")
    logger.info("=" * 60)

    # 큐 설정
    config = QueueConfig()
    config.max_queue_size = 200  # 충분한 크기로 설정
    config.message_processing_interval = 0.1  # 초당 10개 처리 가능
    config.worker_count = 2  # 워커 2개로 처리량 증가

    logger.info(f"큐 설정: {config}")

    # 입력 큐 매니저 생성
    queue_manager = InputQueueManager(
        config=config,
        message_handler=dummy_message_handler
    )

    # 통계 수집 객체
    stats = LoadTestStats()

    try:
        # 큐 매니저 시작
        await queue_manager.start()
        logger.info("큐 매니저 시작됨")

        # 모니터링 태스크 시작 (백그라운드)
        monitor_task = asyncio.create_task(
            monitor_queue(queue_manager, interval=5.0)
        )

        # 부하 테스트 실행
        await send_messages_burst(
            queue_manager,
            stats,
            messages_per_second,
            duration_seconds
        )

        # 큐가 비워질 때까지 대기 (최대 60초)
        logger.info("큐 처리 완료 대기 중...")
        wait_start = datetime.now().timestamp()
        max_wait = 60.0

        while not queue_manager.is_queue_empty():
            if datetime.now().timestamp() - wait_start > max_wait:
                logger.warning("큐 처리 대기 시간 초과")
                break
            await asyncio.sleep(1)
            queue_status = queue_manager.get_status()
            logger.info(
                f"큐 처리 중... "
                f"남은 메시지: {queue_status['queue_size']}, "
                f"처리 완료: {queue_status['total_processed']}"
            )

        # 모니터링 태스크 취소
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        # 최종 상태 수집
        final_status = queue_manager.get_status()
        stats.total_processed = final_status['total_processed']

    finally:
        # 큐 매니저 중지
        await queue_manager.stop()
        logger.info("큐 매니저 중지됨")

    # 결과 출력
    stats.print_summary()

    # 성공 기준 검증
    success = validate_results(stats, queue_manager)

    return success


def validate_results(stats: LoadTestStats, queue_manager: InputQueueManager) -> bool:
    """
    테스트 결과를 검증합니다.

    Args:
        stats: 통계 객체
        queue_manager: 큐 매니저

    Returns:
        bool: 테스트 성공 여부
    """
    logger.info("=" * 60)
    logger.info("결과 검증")
    logger.info("=" * 60)

    success = True
    final_status = queue_manager.get_status()

    # 1. 모든 메시지가 큐에 추가되었는지 확인
    if stats.total_queued == stats.total_sent:
        logger.info("✓ 모든 메시지가 성공적으로 큐에 추가됨")
    else:
        logger.error(
            f"✗ 일부 메시지가 드롭됨: "
            f"{stats.total_dropped}/{stats.total_sent}"
        )
        success = False

    # 2. 메시지 처리 속도 확인 (초당 10+ 메시지)
    if stats.get_messages_per_second() >= 10:
        logger.info(
            f"✓ 메시지 전송 속도: {stats.get_messages_per_second():.2f} msgs/sec "
            f"(요구사항: 10+ msgs/sec)"
        )
    else:
        logger.error(
            f"✗ 메시지 전송 속도 부족: {stats.get_messages_per_second():.2f} msgs/sec"
        )
        success = False

    # 3. 처리 실패 확인
    if final_status['total_failed'] == 0:
        logger.info("✓ 처리 실패 없음")
    else:
        logger.warning(
            f"⚠ 처리 실패: {final_status['total_failed']}개"
        )

    # 4. 큐가 정상적으로 비워졌는지 확인
    if queue_manager.is_queue_empty():
        logger.info("✓ 큐가 정상적으로 비워짐")
    else:
        logger.warning(
            f"⚠ 큐에 처리되지 않은 메시지가 남아있음: "
            f"{final_status['queue_size']}개"
        )

    logger.info("=" * 60)

    if success:
        logger.info("✓ 부하 테스트 성공!")
        print("\n✓ All messages queued successfully")
    else:
        logger.error("✗ 부하 테스트 실패")
        print("\n✗ Load test failed")

    return success


async def main():
    """메인 함수"""
    try:
        success = await run_load_test()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"부하 테스트 실행 중 에러 발생: {e}", exc_info=True)
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
