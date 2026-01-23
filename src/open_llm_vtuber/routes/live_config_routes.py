"""Live config API routes for editing YouTube, Chzzk, BiliBili settings."""

from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from loguru import logger

from ..service_context import ServiceContext
from ..config_manager.utils import read_yaml, save_partial_yaml
from ..config_manager.live import LiveConfig


class YouTubeConfigUpdate(BaseModel):
    """YouTube 설정 업데이트용 Pydantic 모델"""

    enabled: Optional[bool] = None
    api_key: Optional[str] = None
    channel_id: Optional[str] = None


class ChzzkConfigUpdate(BaseModel):
    """Chzzk 설정 업데이트용 Pydantic 모델 (OAuth 토큰 제외)"""

    enabled: Optional[bool] = None
    channel_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None
    # access_token, refresh_token 제외 - OAuth로만 설정됨


class BiliBiliConfigUpdate(BaseModel):
    """BiliBili 설정 업데이트용 Pydantic 모델"""

    room_ids: Optional[List[int]] = None
    sessdata: Optional[str] = None


class ChatMonitorConfigUpdate(BaseModel):
    """Chat Monitor 전체 업데이트 모델"""

    enabled: Optional[bool] = None
    youtube: Optional[YouTubeConfigUpdate] = None
    chzzk: Optional[ChzzkConfigUpdate] = None
    max_retries: Optional[int] = Field(None, ge=1, le=100)
    retry_interval: Optional[int] = Field(None, ge=10, le=3600)


class LiveConfigUpdate(BaseModel):
    """Live Config 전체 업데이트 모델"""

    bilibili_live: Optional[BiliBiliConfigUpdate] = None
    chat_monitor: Optional[ChatMonitorConfigUpdate] = None


def _deep_merge(base: dict, update: dict) -> dict:
    """
    깊은 병합을 수행합니다. update의 값이 None이 아닌 경우에만 base를 업데이트합니다.

    Args:
        base: 기본 딕셔너리
        update: 업데이트할 딕셔너리

    Returns:
        병합된 딕셔너리
    """
    result = base.copy()
    for key, value in update.items():
        if value is None:
            continue
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def init_live_config_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Live config API 라우트를 생성합니다.

    Args:
        default_context_cache: 기본 서비스 컨텍스트 캐시

    Returns:
        APIRouter: Live config 엔드포인트가 포함된 라우터
    """
    router = APIRouter()

    @router.get("/api/live-config")
    async def get_live_config():
        """
        현재 라이브 설정을 조회합니다.

        Returns:
            JSON response with live config
        """
        try:
            live_config = default_context_cache.config.live_config
            return JSONResponse(live_config.model_dump(), status_code=200)
        except Exception as e:
            logger.error(f"Live config 조회 중 오류 발생: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @router.put("/api/live-config")
    async def update_live_config(update: LiveConfigUpdate):
        """
        라이브 설정을 업데이트하고 conf.yaml에 저장합니다.

        Args:
            update: 업데이트할 라이브 설정

        Returns:
            JSON response with:
                - success: 성공 여부
                - live_config: 업데이트된 설정

        Raises:
            HTTPException: 업데이트 실패 시
        """
        try:
            # 1. 업데이트할 필드가 있는지 확인
            update_dict = update.model_dump(exclude_none=True)
            if not update_dict:
                raise HTTPException(
                    status_code=400,
                    detail="업데이트할 필드가 없습니다"
                )

            # 2. 현재 전체 설정 읽기
            config_data = read_yaml("conf.yaml")

            # 3. live_config 섹션 가져오기 (없으면 빈 딕셔너리)
            live_config_data = config_data.get("live_config", {})

            # 4. 깊은 병합 수행
            merged_live_config = _deep_merge(live_config_data, update_dict)

            # 5. conf.yaml에 저장 (live_config 섹션만)
            save_partial_yaml("live_config", merged_live_config, "conf.yaml")

            # 6. 메모리 내 설정도 업데이트
            new_live_config = LiveConfig(**merged_live_config)
            default_context_cache.config.live_config = new_live_config

            logger.info("Live config가 성공적으로 업데이트되었습니다")

            return JSONResponse(
                {
                    "success": True,
                    "live_config": new_live_config.model_dump()
                },
                status_code=200
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Live config 업데이트 중 오류 발생: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    return router
