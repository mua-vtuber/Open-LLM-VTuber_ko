"""Live2D model information routes."""

import logging
import os
import re
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# 외부 모델 폴더 경로 저장 (메모리)
# 키: 폴더 경로, 값: 마운트 경로
_external_model_folders: dict[str, str] = {}

# FastAPI 앱 인스턴스 참조 (동적 마운트용)
_app_instance: "FastAPI | None" = None


def _sanitize_mount_name(folder_path: str) -> str:
    """폴더 경로를 URL-safe 마운트 이름으로 변환"""
    folder_name = os.path.basename(folder_path)
    # 알파벳, 숫자, 하이픈, 언더스코어만 허용
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", folder_name)
    return safe_name or "external"


def _scan_models_in_folder(
    folder_path: str, url_prefix: str, source: str = "internal"
) -> list[dict]:
    """
    폴더 내 Live2D 모델 스캔.

    Args:
        folder_path: 스캔할 폴더 경로
        url_prefix: 모델 URL의 접두사 (예: "/live2d-models", "/external-models/xyz")
        source: 모델 소스 ("internal" 또는 "external")

    Returns:
        모델 정보 딕셔너리 리스트

    Note:
        다음 구조를 지원합니다:
        1. 모델 폴더들을 포함하는 상위 폴더:
           - {folder}/{model_name}/{model_name}.model3.json
           - {folder}/{model_name}/runtime/{model_name}.model3.json
        2. 모델 폴더 직접 선택:
           - {folder}/{folder_name}.model3.json
           - {folder}/runtime/{folder_name}.model3.json
        3. 임의의 이름을 가진 .model3.json 파일 검색
    """
    valid_characters = []
    supported_extensions = [".png", ".jpg", ".jpeg"]

    if not os.path.exists(folder_path):
        logger.warning(f"[model_routes] Folder does not exist: {folder_path}")
        return []

    folder_name = os.path.basename(folder_path)
    logger.info(f"[model_routes] Scanning folder: {folder_path} (name: {folder_name})")

    # Case 1: 선택된 폴더 자체가 모델 폴더인 경우 확인
    # 먼저 폴더 이름과 일치하는 파일 확인
    direct_model_locations = [
        # 직접 경로: {folder}/{folder_name}.model3.json
        ("", f"{folder_name}.model3.json"),
        # runtime 하위 폴더: {folder}/runtime/{folder_name}.model3.json
        ("runtime", f"{folder_name}.model3.json"),
    ]

    direct_model_found = False
    for subdir, model_file in direct_model_locations:
        if subdir:
            model3_file_path = os.path.join(folder_path, subdir, model_file)
            url_subpath = f"{subdir}/{model_file}"
        else:
            model3_file_path = os.path.join(folder_path, model_file)
            url_subpath = model_file

        logger.debug(f"[model_routes] Checking direct model path: {model3_file_path}")

        if os.path.isfile(model3_file_path):
            model_url = f"{url_prefix}/{url_subpath}"
            avatar_url = _find_avatar_url_direct(
                folder_path, folder_name, url_prefix, subdir, supported_extensions
            )

            logger.info(f"[model_routes] Found direct model: {folder_name} at {model_url}")
            valid_characters.append(
                {
                    "name": folder_name,
                    "avatar": avatar_url,
                    "model_path": model_url,
                    "source": source,
                    "folder_path": folder_path if source == "external" else None,
                }
            )
            direct_model_found = True
            break

    # Case 1-2: 폴더 이름과 다른 .model3.json 파일 검색 (폴더 직접 또는 runtime 하위)
    if not direct_model_found:
        search_dirs = [
            ("", folder_path),
            ("runtime", os.path.join(folder_path, "runtime")),
        ]

        for subdir, search_path in search_dirs:
            if not os.path.isdir(search_path):
                continue

            for file_entry in os.scandir(search_path):
                if file_entry.is_file() and file_entry.name.endswith(".model3.json"):
                    model_file = file_entry.name
                    model_name = model_file.replace(".model3.json", "")

                    if subdir:
                        url_subpath = f"{subdir}/{model_file}"
                    else:
                        url_subpath = model_file

                    model_url = f"{url_prefix}/{url_subpath}"
                    avatar_url = _find_avatar_url_direct(
                        folder_path, model_name, url_prefix, subdir, supported_extensions
                    )

                    # 표시 이름은 폴더 이름 사용 (더 의미있는 이름일 수 있음)
                    display_name = folder_name if folder_name != model_name else model_name

                    logger.info(f"[model_routes] Found model with different name: {display_name} ({model_name}) at {model_url}")
                    valid_characters.append(
                        {
                            "name": display_name,
                            "avatar": avatar_url,
                            "model_path": model_url,
                            "source": source,
                            "folder_path": folder_path if source == "external" else None,
                        }
                    )
                    direct_model_found = True
                    break  # 첫 번째로 찾은 모델만 사용

            if direct_model_found:
                break

    # Case 2: 하위 폴더들을 스캔하여 모델 찾기
    for entry in os.scandir(folder_path):
        if entry.is_dir():
            subfolder_name = entry.name
            subfolder_path = os.path.join(folder_path, subfolder_name)
            subfolder_model_found = False

            # 먼저 폴더 이름과 일치하는 모델 파일 찾기
            model_locations = [
                # 직접 경로: {subfolder_name}/{subfolder_name}.model3.json
                ("", f"{subfolder_name}.model3.json"),
                # runtime 하위 폴더: {subfolder_name}/runtime/{subfolder_name}.model3.json
                ("runtime", f"{subfolder_name}.model3.json"),
            ]

            for subdir, model_file in model_locations:
                if subdir:
                    model3_file_path = os.path.join(subfolder_path, subdir, model_file)
                    url_subpath = f"{subfolder_name}/{subdir}/{model_file}"
                else:
                    model3_file_path = os.path.join(subfolder_path, model_file)
                    url_subpath = f"{subfolder_name}/{model_file}"

                logger.debug(f"[model_routes] Checking subfolder model path: {model3_file_path}")

                if os.path.isfile(model3_file_path):
                    model_url = f"{url_prefix}/{url_subpath}"
                    avatar_url = _find_avatar_url(
                        folder_path, subfolder_name, url_prefix, subdir, supported_extensions
                    )

                    logger.info(f"[model_routes] Found subfolder model: {subfolder_name} at {model_url}")
                    valid_characters.append(
                        {
                            "name": subfolder_name,
                            "avatar": avatar_url,
                            "model_path": model_url,
                            "source": source,
                            "folder_path": folder_path if source == "external" else None,
                        }
                    )
                    subfolder_model_found = True
                    break

            # 폴더 이름과 다른 .model3.json 파일 검색
            if not subfolder_model_found:
                search_dirs = [
                    ("", subfolder_path),
                    ("runtime", os.path.join(subfolder_path, "runtime")),
                ]

                for subdir, search_path in search_dirs:
                    if not os.path.isdir(search_path):
                        continue

                    for file_entry in os.scandir(search_path):
                        if file_entry.is_file() and file_entry.name.endswith(".model3.json"):
                            model_file = file_entry.name
                            model_name = model_file.replace(".model3.json", "")

                            if subdir:
                                url_subpath = f"{subfolder_name}/{subdir}/{model_file}"
                            else:
                                url_subpath = f"{subfolder_name}/{model_file}"

                            model_url = f"{url_prefix}/{url_subpath}"
                            avatar_url = _find_avatar_url(
                                folder_path, subfolder_name, url_prefix, subdir, supported_extensions
                            )

                            # 표시 이름은 폴더 이름 사용
                            display_name = subfolder_name

                            logger.info(f"[model_routes] Found subfolder model with different name: {display_name} ({model_name}) at {model_url}")
                            valid_characters.append(
                                {
                                    "name": display_name,
                                    "avatar": avatar_url,
                                    "model_path": model_url,
                                    "source": source,
                                    "folder_path": folder_path if source == "external" else None,
                                }
                            )
                            subfolder_model_found = True
                            break

                    if subfolder_model_found:
                        break

    logger.info(f"[model_routes] Total models found in {folder_path}: {len(valid_characters)}")
    return valid_characters


def _find_avatar_url_direct(
    folder_path: str, model_name: str, url_prefix: str, subdir: str, extensions: list[str]
) -> str | None:
    """모델 폴더 직접 선택 시 아바타 이미지 URL 찾기"""
    # 탐색할 위치들 (순서대로 시도)
    search_paths = [
        # 1. 모델 폴더 직접
        (folder_path, ""),
        # 2. subdir 내부 (예: runtime)
        (os.path.join(folder_path, subdir), subdir) if subdir else None,
        # 3. 텍스처 폴더 내부
        (os.path.join(folder_path, subdir, f"{model_name}.1024"), f"{subdir}/{model_name}.1024") if subdir else None,
        (os.path.join(folder_path, subdir, f"{model_name}.4096"), f"{subdir}/{model_name}.4096") if subdir else None,
    ]

    for search_info in search_paths:
        if search_info is None:
            continue
        search_dir, url_path = search_info
        for ext in extensions:
            avatar_file = os.path.join(search_dir, f"{model_name}{ext}")
            if os.path.isfile(avatar_file):
                if url_path:
                    return f"{url_prefix}/{url_path}/{model_name}{ext}"
                else:
                    return f"{url_prefix}/{model_name}{ext}"
    return None


def _find_avatar_url(
    folder_path: str, model_name: str, url_prefix: str, subdir: str, extensions: list[str]
) -> str | None:
    """모델의 아바타 이미지 URL 찾기 (여러 위치 탐색)"""
    # 탐색할 위치들 (순서대로 시도)
    search_paths = [
        # 1. 모델 폴더 직접
        (os.path.join(folder_path, model_name), f"{model_name}"),
        # 2. subdir 내부 (예: runtime)
        (os.path.join(folder_path, model_name, subdir), f"{model_name}/{subdir}") if subdir else None,
        # 3. 텍스처 폴더 내부
        (os.path.join(folder_path, model_name, subdir, f"{model_name}.1024"), f"{model_name}/{subdir}/{model_name}.1024") if subdir else None,
    ]

    for search_info in search_paths:
        if search_info is None:
            continue
        search_dir, url_path = search_info
        for ext in extensions:
            avatar_file = os.path.join(search_dir, f"{model_name}{ext}")
            if os.path.isfile(avatar_file):
                return f"{url_prefix}/{url_path}/{model_name}{ext}"
    return None


def init_model_routes(app: "FastAPI") -> APIRouter:
    """
    Create routes for Live2D model information.

    Args:
        app: FastAPI 앱 인스턴스 (동적 마운트용)

    Returns:
        APIRouter: Router with model info endpoints.
    """
    global _app_instance
    _app_instance = app

    router = APIRouter()

    @router.get("/external-models/{folder_name}/{file_path:path}")
    async def serve_external_model_file(folder_name: str, file_path: str):
        """
        외부 모델 폴더의 파일을 서빙.
        동적 마운트 대신 이 라우트를 통해 파일 제공.
        """
        from starlette.responses import FileResponse

        # 마운트 경로로 폴더 경로 찾기
        mount_path = f"/external-models/{folder_name}"
        folder_path = None

        for path, mount in _external_model_folders.items():
            if mount == mount_path:
                folder_path = path
                break

        if not folder_path:
            logger.warning(f"[model_routes] External folder not found for mount: {mount_path}")
            return JSONResponse(
                {"detail": "Not Found"},
                status_code=404
            )

        # 파일 경로 구성
        full_path = os.path.join(folder_path, file_path)
        full_path = os.path.normpath(full_path)

        # 보안: 폴더 외부 접근 방지
        if not full_path.startswith(os.path.normpath(folder_path)):
            logger.warning(f"[model_routes] Path traversal attempt: {full_path}")
            return JSONResponse(
                {"detail": "Forbidden"},
                status_code=403
            )

        if not os.path.isfile(full_path):
            logger.debug(f"[model_routes] File not found: {full_path}")
            return JSONResponse(
                {"detail": "Not Found"},
                status_code=404
            )

        # CORS 헤더와 함께 파일 반환
        # Content-Type 추론
        import mimetypes
        content_type, _ = mimetypes.guess_type(full_path)
        if content_type is None:
            content_type = "application/octet-stream"

        response = FileResponse(
            full_path,
            media_type=content_type,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            }
        )
        return response

    @router.get("/live2d-models/info")
    async def get_live2d_folder_info():
        """Get information about available Live2D models (internal + external)."""
        all_characters = []

        # 1. 내부 모델 스캔 (live2d-models/)
        internal_models = _scan_models_in_folder(
            "live2d-models", "/live2d-models", "internal"
        )
        all_characters.extend(internal_models)

        # 2. 외부 모델 폴더 스캔
        for folder_path, mount_path in _external_model_folders.items():
            if os.path.exists(folder_path):
                external_models = _scan_models_in_folder(
                    folder_path, mount_path, "external"
                )
                all_characters.extend(external_models)

        return JSONResponse(
            {
                "type": "live2d-models/info",
                "count": len(all_characters),
                "characters": all_characters,
            }
        )

    @router.get("/live2d-models/external-folders")
    async def get_external_folders():
        """등록된 외부 모델 폴더 목록 반환"""
        folders = [
            {"path": path, "mount_path": mount}
            for path, mount in _external_model_folders.items()
        ]
        return JSONResponse({"folders": folders})

    @router.post("/live2d-models/add-folder")
    async def add_external_model_folder(request: Request):
        """
        외부 모델 폴더 등록 및 동적 마운트.

        Request body:
            {"path": "D:/MyModels"}

        Returns:
            {"success": true, "path": "...", "mount_path": "..."}
        """
        from ..server import CORSStaticFiles

        try:
            data = await request.json()
        except Exception:
            return JSONResponse(
                {"success": False, "error": "Invalid JSON body"},
                status_code=400
            )

        folder_path = data.get("path", "").strip()

        if not folder_path:
            return JSONResponse(
                {"success": False, "error": "폴더 경로가 필요합니다"},
                status_code=400
            )

        # 경로 정규화
        folder_path = os.path.normpath(folder_path)

        if not os.path.isdir(folder_path):
            return JSONResponse(
                {"success": False, "error": f"폴더가 존재하지 않습니다: {folder_path}"},
                status_code=400
            )

        # 동적 마운트 경로 생성
        safe_name = _sanitize_mount_name(folder_path)

        # 이미 등록된 폴더인지 확인
        already_registered = folder_path in _external_model_folders
        if already_registered:
            # 기존 마운트 경로 사용
            mount_path = _external_model_folders[folder_path]
            logger.info(f"[model_routes] Folder already registered, re-mounting: {folder_path} -> {mount_path}")
        else:
            # 새 마운트 경로 생성
            mount_path = f"/external-models/{safe_name}"

            # 중복 마운트 이름 처리
            counter = 1
            base_mount_path = mount_path
            while any(m == mount_path for m in _external_model_folders.values()):
                mount_path = f"{base_mount_path}-{counter}"
                counter += 1

        # 마운트는 더 이상 동적으로 하지 않음
        # 대신 /external-models/{folder_name}/{path:path} 라우트를 통해 파일 서빙
        logger.info(f"[model_routes] Registered external folder: {folder_path} -> {mount_path}")

        # 등록 저장
        _external_model_folders[folder_path] = mount_path

        return JSONResponse({
            "success": True,
            "path": folder_path,
            "mount_path": mount_path,
            "message": "이미 등록된 폴더입니다 (재마운트)" if already_registered else None
        })

    @router.delete("/live2d-models/remove-folder")
    async def remove_external_folder(request: Request):
        """
        외부 모델 폴더 등록 해제.

        Request body:
            {"path": "D:/MyModels"}

        Note: 이미 마운트된 라우트는 FastAPI에서 동적 해제가 어려우므로
              목록에서만 제거됩니다. 실제 언마운트는 서버 재시작 시 적용됩니다.
        """
        try:
            data = await request.json()
        except Exception:
            return JSONResponse(
                {"success": False, "error": "Invalid JSON body"},
                status_code=400
            )

        folder_path = data.get("path", "").strip()

        if not folder_path:
            return JSONResponse(
                {"success": False, "error": "폴더 경로가 필요합니다"},
                status_code=400
            )

        # 경로 정규화
        folder_path = os.path.normpath(folder_path)

        if folder_path in _external_model_folders:
            del _external_model_folders[folder_path]
            return JSONResponse({
                "success": True,
                "path": folder_path,
                "message": "폴더가 제거되었습니다 (마운트 해제는 서버 재시작 시 적용)"
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "등록되지 않은 폴더입니다"
            }, status_code=404)

    return router


def _find_avatar_file(
    live2d_dir: str, folder_name: str, extensions: list[str]
) -> str | None:
    """Find avatar image file for a Live2D model (legacy compatibility)."""
    for ext in extensions:
        avatar_path = os.path.join(live2d_dir, folder_name, f"{folder_name}{ext}")
        if os.path.isfile(avatar_path):
            return avatar_path.replace("\\", "/")
    return None
