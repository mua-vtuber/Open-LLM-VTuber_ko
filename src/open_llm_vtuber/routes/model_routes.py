"""Live2D model information routes."""

import os

from fastapi import APIRouter
from starlette.responses import JSONResponse


def init_model_routes() -> APIRouter:
    """
    Create routes for Live2D model information.

    Returns:
        APIRouter: Router with model info endpoints.
    """
    router = APIRouter()

    @router.get("/live2d-models/info")
    async def get_live2d_folder_info():
        """Get information about available Live2D models."""
        live2d_dir = "live2d-models"
        if not os.path.exists(live2d_dir):
            return JSONResponse(
                {"error": "Live2D models directory not found"}, status_code=404
            )

        valid_characters = []
        supported_extensions = [".png", ".jpg", ".jpeg"]

        for entry in os.scandir(live2d_dir):
            if entry.is_dir():
                folder_name = entry.name.replace("\\", "/")
                model3_file = os.path.join(
                    live2d_dir, folder_name, f"{folder_name}.model3.json"
                ).replace("\\", "/")

                if os.path.isfile(model3_file):
                    avatar_file = _find_avatar_file(
                        live2d_dir, folder_name, supported_extensions
                    )
                    valid_characters.append(
                        {
                            "name": folder_name,
                            "avatar": avatar_file,
                            "model_path": model3_file,
                        }
                    )

        return JSONResponse(
            {
                "type": "live2d-models/info",
                "count": len(valid_characters),
                "characters": valid_characters,
            }
        )

    return router


def _find_avatar_file(
    live2d_dir: str, folder_name: str, extensions: list[str]
) -> str | None:
    """Find avatar image file for a Live2D model."""
    for ext in extensions:
        avatar_path = os.path.join(live2d_dir, folder_name, f"{folder_name}{ext}")
        if os.path.isfile(avatar_path):
            return avatar_path.replace("\\", "/")
    return None
