"""
API 응답 스키마 정의.

FastAPI OpenAPI 문서화를 위한 Pydantic 스키마 모델.
모든 API 엔드포인트의 요청/응답 타입을 정의합니다.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


# =============================================================================
# 공통 응답 스키마
# =============================================================================

class ErrorResponse(BaseModel):
    """API 오류 응답 스키마."""

    error: str = Field(
        ...,
        description="오류 메시지",
        json_schema_extra={"example": "요청 처리 중 오류가 발생했습니다"}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "요청 처리 중 오류가 발생했습니다"
            }
        }
    }


class SuccessResponse(BaseModel):
    """API 성공 응답 스키마."""

    success: bool = Field(
        ...,
        description="작업 성공 여부"
    )
    message: Optional[str] = Field(
        None,
        description="추가 메시지"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "작업이 성공적으로 완료되었습니다"
            }
        }
    }


# =============================================================================
# Live2D 모델 관련 스키마
# =============================================================================

class ModelInfo(BaseModel):
    """Live2D 모델 정보 스키마."""

    name: str = Field(
        ...,
        description="모델 이름",
        json_schema_extra={"example": "mao_pro"}
    )
    avatar: Optional[str] = Field(
        None,
        description="아바타 이미지 URL",
        json_schema_extra={"example": "/live2d-models/mao_pro/mao_pro.png"}
    )
    model_path: str = Field(
        ...,
        description="모델 파일 경로 (model3.json)",
        json_schema_extra={"example": "/live2d-models/mao_pro/mao_pro.model3.json"}
    )
    source: str = Field(
        ...,
        description="모델 소스 (internal 또는 external)",
        json_schema_extra={"example": "internal"}
    )
    folder_path: Optional[str] = Field(
        None,
        description="외부 모델의 경우 폴더 경로",
        json_schema_extra={"example": "D:/MyModels"}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "mao_pro",
                "avatar": "/live2d-models/mao_pro/mao_pro.png",
                "model_path": "/live2d-models/mao_pro/mao_pro.model3.json",
                "source": "internal",
                "folder_path": None
            }
        }
    }


class ModelListResponse(BaseModel):
    """Live2D 모델 목록 응답 스키마."""

    type: str = Field(
        default="live2d-models/info",
        description="응답 타입"
    )
    count: int = Field(
        ...,
        description="모델 수",
        json_schema_extra={"example": 3}
    )
    characters: list[ModelInfo] = Field(
        ...,
        description="모델 정보 목록"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "live2d-models/info",
                "count": 2,
                "characters": [
                    {
                        "name": "mao_pro",
                        "avatar": "/live2d-models/mao_pro/mao_pro.png",
                        "model_path": "/live2d-models/mao_pro/mao_pro.model3.json",
                        "source": "internal",
                        "folder_path": None
                    },
                    {
                        "name": "custom_model",
                        "avatar": "/external-models/custom/custom.png",
                        "model_path": "/external-models/custom/custom.model3.json",
                        "source": "external",
                        "folder_path": "D:/MyModels/custom"
                    }
                ]
            }
        }
    }


class ExternalFolderInfo(BaseModel):
    """외부 모델 폴더 정보 스키마."""

    path: str = Field(
        ...,
        description="폴더 경로",
        json_schema_extra={"example": "D:/MyModels"}
    )
    mount_path: str = Field(
        ...,
        description="마운트 경로",
        json_schema_extra={"example": "/external-models/MyModels"}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "path": "D:/MyModels",
                "mount_path": "/external-models/MyModels"
            }
        }
    }


class ExternalFoldersResponse(BaseModel):
    """외부 모델 폴더 목록 응답 스키마."""

    folders: list[ExternalFolderInfo] = Field(
        ...,
        description="등록된 외부 폴더 목록"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "folders": [
                    {"path": "D:/MyModels", "mount_path": "/external-models/MyModels"},
                    {"path": "E:/Live2D", "mount_path": "/external-models/Live2D"}
                ]
            }
        }
    }


class AddFolderRequest(BaseModel):
    """외부 모델 폴더 추가 요청 스키마."""

    path: str = Field(
        ...,
        description="추가할 폴더 경로",
        json_schema_extra={"example": "D:/MyModels"}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "path": "D:/MyModels"
            }
        }
    }


class AddFolderResponse(BaseModel):
    """외부 모델 폴더 추가 응답 스키마."""

    success: bool = Field(
        ...,
        description="추가 성공 여부"
    )
    path: str = Field(
        ...,
        description="추가된 폴더 경로"
    )
    mount_path: str = Field(
        ...,
        description="마운트 경로"
    )
    message: Optional[str] = Field(
        None,
        description="추가 메시지 (이미 등록된 경우 등)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "path": "D:/MyModels",
                "mount_path": "/external-models/MyModels",
                "message": None
            }
        }
    }


class RemoveFolderRequest(BaseModel):
    """외부 모델 폴더 제거 요청 스키마."""

    path: str = Field(
        ...,
        description="제거할 폴더 경로",
        json_schema_extra={"example": "D:/MyModels"}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "path": "D:/MyModels"
            }
        }
    }


class RemoveFolderResponse(BaseModel):
    """외부 모델 폴더 제거 응답 스키마."""

    success: bool = Field(
        ...,
        description="제거 성공 여부"
    )
    path: str = Field(
        ...,
        description="제거된 폴더 경로"
    )
    message: Optional[str] = Field(
        None,
        description="추가 메시지"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "path": "D:/MyModels",
                "message": "폴더가 제거되었습니다 (마운트 해제는 서버 재시작 시 적용)"
            }
        }
    }


# =============================================================================
# 큐 상태 관련 스키마
# =============================================================================

class QueueStatus(BaseModel):
    """큐 상태 응답 스키마."""

    pending: int = Field(
        ...,
        description="대기 중인 메시지 수",
        json_schema_extra={"example": 5}
    )
    processing: int = Field(
        ...,
        description="처리 중인 메시지 수 (0 또는 1)",
        json_schema_extra={"example": 1}
    )
    max_size: int = Field(
        ...,
        description="최대 큐 크기",
        json_schema_extra={"example": 100}
    )
    total_received: int = Field(
        ...,
        description="총 수신 메시지 수",
        json_schema_extra={"example": 150}
    )
    total_processed: int = Field(
        ...,
        description="총 처리 완료 메시지 수",
        json_schema_extra={"example": 145}
    )
    total_dropped: int = Field(
        ...,
        description="드롭된 메시지 수",
        json_schema_extra={"example": 0}
    )
    running: bool = Field(
        ...,
        description="큐 매니저 실행 상태",
        json_schema_extra={"example": True}
    )
    avg_processing_time: Optional[float] = Field(
        None,
        description="평균 처리 시간 (초)",
        json_schema_extra={"example": 2.5}
    )
    processing_rate: Optional[float] = Field(
        None,
        description="처리 속도 (msg/s)",
        json_schema_extra={"example": 0.4}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "pending": 5,
                "processing": 1,
                "max_size": 100,
                "total_received": 150,
                "total_processed": 145,
                "total_dropped": 0,
                "running": True,
                "avg_processing_time": 2.5,
                "processing_rate": 0.4
            }
        }
    }


class QueueHistoryItem(BaseModel):
    """큐 히스토리 아이템 스키마."""

    timestamp: str = Field(
        ...,
        description="기록 시간 (ISO 8601)",
        json_schema_extra={"example": "2026-01-25T12:00:00"}
    )
    pending: int = Field(
        ...,
        description="대기 중인 메시지 수"
    )
    processing: int = Field(
        ...,
        description="처리 중인 메시지 수"
    )
    processing_rate: Optional[float] = Field(
        None,
        description="처리 속도"
    )


class QueueHistoryResponse(BaseModel):
    """큐 히스토리 응답 스키마."""

    minutes: int = Field(
        ...,
        description="조회 기간 (분)",
        json_schema_extra={"example": 5}
    )
    data_points: int = Field(
        ...,
        description="데이터 포인트 수",
        json_schema_extra={"example": 30}
    )
    history: list[QueueHistoryItem] = Field(
        ...,
        description="히스토리 데이터"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "minutes": 5,
                "data_points": 30,
                "history": [
                    {
                        "timestamp": "2026-01-25T12:00:00",
                        "pending": 3,
                        "processing": 1,
                        "processing_rate": 0.4
                    }
                ]
            }
        }
    }


class PriorityRules(BaseModel):
    """우선순위 규칙 스키마."""

    priority_mode: str = Field(
        ...,
        description="우선순위 모드 (chat_first, voice_first, superchat_priority, balanced)",
        json_schema_extra={"example": "balanced"}
    )
    wait_time: float = Field(
        ...,
        description="대기 시간 (0~30초)",
        json_schema_extra={"example": 5.0}
    )
    allow_interruption: bool = Field(
        ...,
        description="중단 허용 여부",
        json_schema_extra={"example": True}
    )
    superchat_always_priority: bool = Field(
        ...,
        description="슈퍼챗 항상 우선",
        json_schema_extra={"example": True}
    )
    voice_active_chat_delay: float = Field(
        ...,
        description="음성 활성 시 채팅 지연 (0~60초)",
        json_schema_extra={"example": 3.0}
    )
    chat_active_voice_delay: float = Field(
        ...,
        description="채팅 활성 시 음성 지연 (0~60초)",
        json_schema_extra={"example": 2.0}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "priority_mode": "balanced",
                "wait_time": 5.0,
                "allow_interruption": True,
                "superchat_always_priority": True,
                "voice_active_chat_delay": 3.0,
                "chat_active_voice_delay": 2.0
            }
        }
    }


class PriorityRulesUpdateResponse(BaseModel):
    """우선순위 규칙 업데이트 응답 스키마."""

    success: bool = Field(
        ...,
        description="업데이트 성공 여부"
    )
    priority_rules: PriorityRules = Field(
        ...,
        description="업데이트된 우선순위 규칙"
    )


# =============================================================================
# 설정 관련 스키마
# =============================================================================

class LiveConfigResponse(BaseModel):
    """라이브 설정 응답 스키마."""

    chat_monitor: dict[str, Any] = Field(
        ...,
        description="채팅 모니터 설정"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "chat_monitor": {
                    "enabled": False,
                    "max_retries": 10,
                    "retry_interval": 60,
                    "youtube": {
                        "enabled": False,
                        "api_key": "",
                        "channel_id": ""
                    },
                    "chzzk": {
                        "enabled": False,
                        "channel_id": "",
                        "client_id": "",
                        "client_secret": ""
                    }
                }
            }
        }
    }


class LiveConfigUpdateResponse(BaseModel):
    """라이브 설정 업데이트 응답 스키마."""

    success: bool = Field(
        ...,
        description="업데이트 성공 여부"
    )
    live_config: dict[str, Any] = Field(
        ...,
        description="업데이트된 라이브 설정"
    )


# =============================================================================
# 미디어 관련 스키마
# =============================================================================

class TranscriptionResponse(BaseModel):
    """음성 인식 응답 스키마."""

    text: str = Field(
        ...,
        description="인식된 텍스트",
        json_schema_extra={"example": "안녕하세요, 오늘 날씨가 좋네요."}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "안녕하세요, 오늘 날씨가 좋네요."
            }
        }
    }


class TTSMessage(BaseModel):
    """TTS 요청 메시지 스키마."""

    text: str = Field(
        ...,
        description="음성으로 변환할 텍스트",
        json_schema_extra={"example": "안녕하세요. 반갑습니다."}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "안녕하세요. 반갑습니다."
            }
        }
    }


class TTSResponse(BaseModel):
    """TTS 응답 스키마."""

    status: str = Field(
        ...,
        description="응답 상태 (partial, complete, error)",
        json_schema_extra={"example": "partial"}
    )
    audioPath: Optional[str] = Field(
        None,
        description="생성된 오디오 파일 경로",
        json_schema_extra={"example": "/cache/20260125_120000_abc123.wav"}
    )
    text: Optional[str] = Field(
        None,
        description="처리된 텍스트 (부분 응답 시)",
        json_schema_extra={"example": "안녕하세요."}
    )
    message: Optional[str] = Field(
        None,
        description="오류 메시지 (오류 발생 시)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "partial",
                "audioPath": "/cache/20260125_120000_abc123.wav",
                "text": "안녕하세요."
            }
        }
    }


# =============================================================================
# 언어 관련 스키마
# =============================================================================

class LanguageInfo(BaseModel):
    """언어 정보 스키마."""

    code: str = Field(
        ...,
        description="언어 코드 (ISO 639-1)",
        json_schema_extra={"example": "ko"}
    )
    label: str = Field(
        ...,
        description="언어 표시명 (원어)",
        json_schema_extra={"example": "한국어"}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "code": "ko",
                "label": "한국어"
            }
        }
    }


class LanguagesResponse(BaseModel):
    """사용 가능한 언어 목록 응답 스키마."""

    type: str = Field(
        default="available_languages",
        description="응답 타입"
    )
    count: int = Field(
        ...,
        description="언어 수",
        json_schema_extra={"example": 3}
    )
    languages: list[LanguageInfo] = Field(
        ...,
        description="언어 목록"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "available_languages",
                "count": 3,
                "languages": [
                    {"code": "en", "label": "English"},
                    {"code": "zh", "label": "中文"},
                    {"code": "ko", "label": "한국어"}
                ]
            }
        }
    }
