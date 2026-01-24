"""
메모리 시스템 예외 클래스

커스텀 예외를 통해 에러 처리를 명확하게 합니다.
"""


class MemorySystemError(Exception):
    """메모리 시스템 기본 예외"""

    pass


class ProfileNotFoundError(MemorySystemError):
    """프로필을 찾을 수 없음"""

    def __init__(self, identifier: str, platform: str):
        self.identifier = identifier
        self.platform = platform
        super().__init__(f"Profile not found: {platform}:{identifier}")


class StorageError(MemorySystemError):
    """저장소 오류"""

    def __init__(self, message: str, path: str | None = None):
        self.path = path
        super().__init__(message)


class MigrationError(MemorySystemError):
    """마이그레이션 오류"""

    def __init__(self, from_version: int, to_version: int, reason: str):
        self.from_version = from_version
        self.to_version = to_version
        self.reason = reason
        super().__init__(f"Migration v{from_version}→v{to_version} failed: {reason}")


class CacheError(MemorySystemError):
    """캐시 오류"""

    pass


class ValidationError(MemorySystemError):
    """데이터 검증 오류"""

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"Validation error for '{field}': {message}")
