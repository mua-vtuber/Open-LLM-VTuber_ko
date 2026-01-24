"""
프로필 스키마 마이그레이션

버전별 마이그레이션 함수를 등록하고 데이터를 최신 버전으로 업그레이드합니다.
"""

import logging
from typing import Callable, Any
from datetime import datetime

from ...core.models import SCHEMA_VERSION
from ...core.exceptions import MigrationError

logger = logging.getLogger(__name__)

# 마이그레이션 함수 타입
MigrationFunc = Callable[[dict[str, Any]], dict[str, Any]]


class ProfileMigrator:
    """프로필 스키마 마이그레이션 관리"""

    CURRENT_VERSION = SCHEMA_VERSION

    # 버전별 마이그레이션 함수 레지스트리
    _migrations: dict[int, MigrationFunc] = {}

    @classmethod
    def register(cls, from_version: int) -> Callable[[MigrationFunc], MigrationFunc]:
        """
        마이그레이션 함수 등록 데코레이터

        Usage:
            @ProfileMigrator.register(from_version=0)
            def migrate_v0_to_v1(data: dict) -> dict:
                # 마이그레이션 로직
                return data
        """

        def decorator(func: MigrationFunc) -> MigrationFunc:
            cls._migrations[from_version] = func
            return func

        return decorator

    def migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        데이터를 최신 버전으로 마이그레이션

        Args:
            data: 원본 프로필 데이터

        Returns:
            마이그레이션된 데이터

        Raises:
            MigrationError: 마이그레이션 실패 시
        """
        version = data.get("_schema_version", 0)

        if version == self.CURRENT_VERSION:
            return data

        if version > self.CURRENT_VERSION:
            logger.warning(
                f"Profile version {version} is newer than current {self.CURRENT_VERSION}. "
                "This may cause compatibility issues."
            )
            return data

        # 순차적으로 마이그레이션 적용
        while version < self.CURRENT_VERSION:
            if version not in self._migrations:
                raise MigrationError(
                    from_version=version,
                    to_version=version + 1,
                    reason=f"No migration path from version {version}",
                )

            try:
                logger.info(f"Migrating profile from v{version} to v{version + 1}")
                data = self._migrations[version](data)
                version += 1
                data["_schema_version"] = version
            except Exception as e:
                raise MigrationError(
                    from_version=version,
                    to_version=version + 1,
                    reason=str(e),
                ) from e

        return data

    @classmethod
    def get_registered_versions(cls) -> list[int]:
        """등록된 마이그레이션 버전 목록"""
        return sorted(cls._migrations.keys())


# ============================================================================
# 마이그레이션 함수 정의
# ============================================================================


@ProfileMigrator.register(from_version=0)
def migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """
    v0 → v1: 초기 버전에서 정식 스키마로

    변경사항:
    - platform 필드 기본값 설정
    - meta_summaries 필드 추가
    - created_at, updated_at 필드 추가
    - preferences 구조 정규화
    """
    # platform 기본값
    if "platform" not in data:
        data["platform"] = "direct"

    # meta_summaries 필드 추가
    if "meta_summaries" not in data:
        data["meta_summaries"] = []

    # created_at, updated_at 필드 추가
    now = datetime.now().isoformat()
    if "created_at" not in data:
        data["created_at"] = data.get("first_visit", now)
    if "updated_at" not in data:
        data["updated_at"] = data.get("last_visit", now)

    # preferences 구조 정규화
    if "preferences" not in data:
        data["preferences"] = {"likes": [], "dislikes": []}
    elif isinstance(data["preferences"], dict):
        if "likes" not in data["preferences"]:
            data["preferences"]["likes"] = []
        if "dislikes" not in data["preferences"]:
            data["preferences"]["dislikes"] = []

    # conversation_summaries 기본값
    if "conversation_summaries" not in data:
        data["conversation_summaries"] = []

    # memorable_moments 기본값
    if "memorable_moments" not in data:
        data["memorable_moments"] = []

    # tags 기본값
    if "tags" not in data:
        data["tags"] = []

    # notes 기본값
    if "notes" not in data:
        data["notes"] = ""

    # opinions 기본값
    if "opinions" not in data:
        data["opinions"] = {}

    # known_facts 기본값
    if "known_facts" not in data:
        data["known_facts"] = []

    # 수치 필드 기본값
    if "visit_count" not in data:
        data["visit_count"] = 1
    if "total_messages" not in data:
        data["total_messages"] = 0
    if "affinity_score" not in data:
        data["affinity_score"] = 50.0
    if "interaction_quality" not in data:
        data["interaction_quality"] = 0.5

    return data


# 향후 마이그레이션 예시:
#
# @ProfileMigrator.register(from_version=1)
# def migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
#     """v1 → v2: 새 필드 추가"""
#     data["new_field"] = "default_value"
#     return data
