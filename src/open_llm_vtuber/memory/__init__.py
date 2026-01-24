"""
메모리 시스템 모듈

계층형 메모리 구조를 통해 효율적인 컨텍스트 관리와 방문자 프로필 기능을 제공합니다.

주요 구성요소:
- core: 인터페이스, 데이터 모델, 예외 정의
- storage: 저장소 구현 (JSON, 마이그레이션)
- profile: 방문자 프로필 관리
"""

from .core.models import (
    Platform,
    Sentiment,
    VisitorProfile,
    ConversationSummary,
    MetaSummary,
    SCHEMA_VERSION,
)
from .core.exceptions import (
    MemorySystemError,
    ProfileNotFoundError,
    StorageError,
    MigrationError,
)
from .storage.json_store import JsonProfileStore
from .profile.cache import ProfileCache
from .profile.manager import ProfileManager

__all__ = [
    # Models
    "Platform",
    "Sentiment",
    "VisitorProfile",
    "ConversationSummary",
    "MetaSummary",
    "SCHEMA_VERSION",
    # Exceptions
    "MemorySystemError",
    "ProfileNotFoundError",
    "StorageError",
    "MigrationError",
    # Storage
    "JsonProfileStore",
    # Profile
    "ProfileCache",
    "ProfileManager",
]
