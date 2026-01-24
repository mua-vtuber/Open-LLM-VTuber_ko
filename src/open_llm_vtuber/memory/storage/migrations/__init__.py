"""
스키마 마이그레이션 모듈

프로필 데이터의 스키마 버전 관리 및 마이그레이션을 처리합니다.
"""

from .migrator import ProfileMigrator

__all__ = ["ProfileMigrator"]
