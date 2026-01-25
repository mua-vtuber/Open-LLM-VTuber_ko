"""
API 스키마 모듈.

Pydantic 모델을 사용한 API 요청/응답 스키마 정의.
"""

from .api import (
    # Live2D 모델 관련
    ModelInfo,
    ModelListResponse,
    ExternalFolderInfo,
    ExternalFoldersResponse,
    AddFolderRequest,
    AddFolderResponse,
    RemoveFolderRequest,
    RemoveFolderResponse,
    # 큐 상태 관련
    QueueStatus,
    QueueHistoryItem,
    QueueHistoryResponse,
    PriorityRules,
    PriorityRulesUpdateResponse,
    # 설정 관련
    LiveConfigResponse,
    LiveConfigUpdateResponse,
    # 미디어 관련
    TranscriptionResponse,
    TTSMessage,
    TTSResponse,
    # 언어 관련
    LanguageInfo,
    LanguagesResponse,
    # 공통 응답
    ErrorResponse,
    SuccessResponse,
)

__all__ = [
    # Live2D 모델 관련
    "ModelInfo",
    "ModelListResponse",
    "ExternalFolderInfo",
    "ExternalFoldersResponse",
    "AddFolderRequest",
    "AddFolderResponse",
    "RemoveFolderRequest",
    "RemoveFolderResponse",
    # 큐 상태 관련
    "QueueStatus",
    "QueueHistoryItem",
    "QueueHistoryResponse",
    "PriorityRules",
    "PriorityRulesUpdateResponse",
    # 설정 관련
    "LiveConfigResponse",
    "LiveConfigUpdateResponse",
    # 미디어 관련
    "TranscriptionResponse",
    "TTSMessage",
    "TTSResponse",
    # 언어 관련
    "LanguageInfo",
    "LanguagesResponse",
    # 공통 응답
    "ErrorResponse",
    "SuccessResponse",
]
