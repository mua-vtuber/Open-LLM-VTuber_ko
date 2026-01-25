"""Language and internationalization API routes.

다국어 지원(i18n)을 위한 API 라우트.
사용 가능한 언어 목록 조회 기능을 제공합니다.
"""

from fastapi import APIRouter
from starlette.responses import JSONResponse
from loguru import logger

from ..i18n_manager import I18nManager
from ..schemas.api import LanguagesResponse, ErrorResponse


def init_language_routes() -> APIRouter:
    """
    Create routes for language-related API endpoints.

    Returns:
        APIRouter: Router with language endpoints.
    """
    router = APIRouter()

    @router.get(
        "/api/languages",
        tags=["languages"],
        summary="사용 가능한 언어 목록 조회",
        description="시스템에서 지원하는 언어 목록을 조회합니다. 각 언어의 코드와 원어 표시명을 반환합니다.",
        response_model=LanguagesResponse,
        responses={
            200: {"description": "언어 목록 반환 성공", "model": LanguagesResponse},
            500: {"description": "서버 오류", "model": ErrorResponse},
        },
    )
    async def get_available_languages():
        """
        사용 가능한 언어 목록을 조회합니다.

        i18n 시스템에서 지원하는 모든 언어를 조회하여
        언어 코드(ISO 639-1)와 해당 언어의 원어 표시명을 반환합니다.

        Returns:
            JSONResponse: 언어 목록
                - type: "available_languages"
                - count: 언어 수
                - languages: 언어 정보 목록 (code, label)

        Example:
            ```json
            {
                "type": "available_languages",
                "count": 3,
                "languages": [
                    {"code": "en", "label": "English"},
                    {"code": "zh", "label": "中文"},
                    {"code": "ko", "label": "한국어"}
                ]
            }
            ```
        """
        try:
            languages = I18nManager.get_available_languages_with_labels()
            return JSONResponse(
                {
                    "type": "available_languages",
                    "count": len(languages),
                    "languages": languages,
                }
            )
        except Exception as e:
            logger.error(f"Error getting available languages: {e}")
            return JSONResponse(
                {"error": "Failed to get available languages"}, status_code=500
            )

    return router
