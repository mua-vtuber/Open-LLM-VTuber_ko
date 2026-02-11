"""Queue status API routes.

메시지 대기열 상태 관리를 위한 API 라우트.
큐 상태 조회, 메트릭 히스토리, 우선순위 규칙 관리 기능을 제공합니다.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from ..websocket.handler import WebSocketHandler
from ..schemas.api import (
    QueueStatus,
    QueueHistoryResponse,
    PriorityRules,
    PriorityRulesUpdateResponse,
    ErrorResponse,
)


class PriorityRulesUpdate(BaseModel):
    """우선순위 규칙 업데이트를 위한 Pydantic 모델"""

    priority_mode: Optional[str] = Field(
        None,
        pattern="^(chat_first|voice_first|superchat_priority|balanced)$",
        description="우선순위 모드"
    )
    wait_time: Optional[float] = Field(
        None,
        ge=0,
        le=30,
        description="대기 시간 (0~30초)"
    )
    allow_interruption: Optional[bool] = Field(
        None,
        description="중단 허용 여부"
    )
    superchat_always_priority: Optional[bool] = Field(
        None,
        description="슈퍼챗 항상 우선"
    )
    voice_active_chat_delay: Optional[float] = Field(
        None,
        ge=0,
        le=60,
        description="음성 활성 시 채팅 지연 (0~60초)"
    )
    chat_active_voice_delay: Optional[float] = Field(
        None,
        ge=0,
        le=60,
        description="채팅 활성 시 음성 지연 (0~60초)"
    )


def init_queue_routes(ws_handler: WebSocketHandler) -> APIRouter:
    """
    Create routes for queue status information.

    Args:
        ws_handler: WebSocketHandler instance to query queue status.

    Returns:
        APIRouter: Router with queue status endpoints.
    """
    router = APIRouter()

    @router.get(
        "/api/queue/status",
        tags=["queue"],
        summary="큐 상태 조회",
        description="메시지 대기열의 현재 상태를 조회합니다. 대기/처리 중인 메시지 수, 통계 정보를 반환합니다.",
        response_model=QueueStatus,
        responses={
            200: {"description": "큐 상태 반환 성공", "model": QueueStatus},
            500: {"description": "서버 오류", "model": ErrorResponse},
        },
    )
    async def get_queue_status():
        """
        큐의 현재 상태를 조회합니다.

        Returns:
            JSONResponse: 큐 상태 정보
                - pending: 대기 중인 메시지 수
                - processing: 처리 중인 메시지 (0 또는 1)
                - max_size: 최대 큐 크기
                - total_received: 총 수신 메시지 수
                - total_processed: 총 처리 완료 메시지 수
                - total_dropped: 드롭된 메시지 수
                - running: 큐 매니저 실행 상태
                - avg_processing_time: 평균 처리 시간 (초)
                - processing_rate: 처리 속도 (msg/s)
        """
        try:
            status = ws_handler.get_queue_status()
            return JSONResponse(status, status_code=200)
        except Exception as e:
            return JSONResponse(
                {"error": f"큐 상태 조회 중 오류 발생: {str(e)}"},
                status_code=500
            )

    @router.get(
        "/api/queue/history",
        tags=["queue"],
        summary="큐 메트릭 히스토리 조회",
        description="지정된 기간 동안의 큐 메트릭 히스토리를 조회합니다.",
        response_model=QueueHistoryResponse,
        responses={
            200: {"description": "히스토리 반환 성공", "model": QueueHistoryResponse},
            400: {"description": "잘못된 요청 (minutes 범위 초과)"},
            500: {"description": "서버 오류", "model": ErrorResponse},
        },
    )
    async def get_queue_history(minutes: int = 5):
        """
        큐 메트릭 히스토리를 조회합니다.

        Args:
            minutes: 조회할 기간 (분), 1~60 사이

        Returns:
            JSONResponse: 히스토리 데이터
                - minutes: 조회 기간
                - data_points: 데이터 포인트 수
                - history: 메트릭 히스토리 리스트
        """
        if minutes < 1 or minutes > 60:
            raise HTTPException(
                status_code=400,
                detail="minutes는 1~60 사이여야 합니다"
            )

        try:
            history = ws_handler.get_queue_metric_history(minutes)
            return JSONResponse(
                {
                    "minutes": minutes,
                    "data_points": len(history),
                    "history": history
                },
                status_code=200
            )
        except Exception as e:
            return JSONResponse(
                {"error": f"메트릭 히스토리 조회 중 오류 발생: {str(e)}"},
                status_code=500
            )

    @router.get(
        "/api/queue/priority-rules",
        tags=["queue"],
        summary="우선순위 규칙 조회",
        description="현재 적용 중인 메시지 우선순위 규칙을 조회합니다.",
        response_model=PriorityRules,
        responses={
            200: {"description": "우선순위 규칙 반환 성공", "model": PriorityRules},
            500: {"description": "서버 오류", "model": ErrorResponse},
        },
    )
    async def get_priority_rules():
        """
        큐의 우선순위 규칙을 조회합니다.

        Returns:
            JSONResponse: 우선순위 규칙
                - priority_mode: 우선순위 모드 (chat_first, voice_first, superchat_priority, balanced)
                - wait_time: 대기 시간 (초)
                - allow_interruption: 중단 허용 여부
                - superchat_always_priority: 슈퍼챗 항상 우선
                - voice_active_chat_delay: 음성 활성 시 채팅 지연 (초)
                - chat_active_voice_delay: 채팅 활성 시 음성 지연 (초)
        """
        try:
            rules = ws_handler.get_priority_rules()
            return JSONResponse(rules, status_code=200)
        except Exception as e:
            return JSONResponse(
                {"error": f"우선순위 규칙 조회 중 오류 발생: {str(e)}"},
                status_code=500
            )

    @router.put(
        "/api/queue/priority-rules",
        tags=["queue"],
        summary="우선순위 규칙 업데이트",
        description="메시지 우선순위 규칙을 업데이트합니다. 부분 업데이트를 지원합니다.",
        response_model=PriorityRulesUpdateResponse,
        responses={
            200: {"description": "규칙 업데이트 성공", "model": PriorityRulesUpdateResponse},
            400: {"description": "잘못된 요청 (필드 누락 또는 검증 실패)"},
            500: {"description": "서버 오류", "model": ErrorResponse},
        },
    )
    async def update_priority_rules(update: PriorityRulesUpdate):
        """
        우선순위 규칙을 업데이트합니다.

        부분 업데이트를 지원하며, 변경된 규칙은 즉시 모든 클라이언트에 브로드캐스트됩니다.

        Args:
            update: 업데이트할 우선순위 규칙 (부분 업데이트 가능)

        Returns:
            JSONResponse: 업데이트 성공 여부와 새 규칙

        Raises:
            HTTPException: 업데이트 실패 시
        """
        try:
            # 업데이트할 필드가 있는지 확인
            update_data = update.model_dump(exclude_none=True)
            if not update_data:
                raise HTTPException(
                    status_code=400,
                    detail="업데이트할 필드가 없습니다"
                )

            # 규칙 인스턴스 가져오기
            rules = ws_handler.get_priority_rules_instance()

            # 규칙 업데이트
            success = rules.update_from_dict(update_data)
            if not success:
                raise HTTPException(
                    status_code=400,
                    detail="우선순위 규칙 검증 실패"
                )

            # 변경 사항 브로드캐스트
            await ws_handler.broadcast_priority_rules_update()

            return JSONResponse(
                {
                    "success": True,
                    "priority_rules": rules.to_dict()
                },
                status_code=200
            )

        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse(
                {"error": f"우선순위 규칙 업데이트 중 오류 발생: {str(e)}"},
                status_code=500
            )

    return router
