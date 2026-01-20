"""Language and internationalization API routes."""

from fastapi import APIRouter
from starlette.responses import JSONResponse
from loguru import logger

from ..i18n_manager import I18nManager


def init_language_routes() -> APIRouter:
    """
    Create routes for language-related API endpoints.

    Returns:
        APIRouter: Router with language endpoints.
    """
    router = APIRouter()

    @router.get("/api/languages")
    async def get_available_languages():
        """
        Get list of available languages from i18n system.

        Returns language codes with their native display labels.

        Example response:
        {
            "type": "available_languages",
            "count": 3,
            "languages": [
                {"code": "en", "label": "English"},
                {"code": "zh", "label": "中文"},
                {"code": "ko", "label": "한국어"}
            ]
        }
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
