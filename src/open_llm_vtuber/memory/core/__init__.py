"""
메모리 시스템 코어 모듈

인터페이스, 데이터 모델, 예외 클래스를 정의합니다.
"""

from .models import (
    Platform,
    Sentiment,
    VisitorProfile,
    ConversationSummary,
    MetaSummary,
    SCHEMA_VERSION,
)
from .exceptions import (
    MemorySystemError,
    ProfileNotFoundError,
    StorageError,
    MigrationError,
)
from .interfaces import (
    MemoryStore,
    ProfileLoader,
    ProfileSaver,
)

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
    # Interfaces
    "MemoryStore",
    "ProfileLoader",
    "ProfileSaver",
]
