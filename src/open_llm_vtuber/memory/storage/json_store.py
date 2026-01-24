"""
JSON 파일 기반 프로필 저장소

원자적 쓰기와 자동 백업을 통해 데이터 무결성을 보장합니다.
"""

import json
import shutil
import logging
import re
from pathlib import Path
from typing import AsyncIterator

from ..core.models import VisitorProfile, Platform
from ..core.exceptions import StorageError
from .migrations.migrator import ProfileMigrator

logger = logging.getLogger(__name__)


class JsonProfileStore:
    """
    JSON 파일 기반 프로필 저장소

    저장 구조:
        {base_path}/
        ├── discord/
        │   └── {identifier}.json
        ├── youtube/
        │   └── {identifier}.json
        └── direct/
            └── {identifier}.json
    """

    def __init__(
        self,
        base_path: str | Path,
        create_backup: bool = True,
        pretty_print: bool = True,
    ):
        """
        Args:
            base_path: 프로필 저장 기본 경로
            create_backup: 저장 시 백업 파일 생성 여부
            pretty_print: JSON 들여쓰기 여부
        """
        self._base_path = Path(base_path)
        self._create_backup = create_backup
        self._pretty_print = pretty_print
        self._migrator = ProfileMigrator()

        # 기본 디렉토리 생성
        self._base_path.mkdir(parents=True, exist_ok=True)

    def _get_platform_dir(self, platform: str) -> Path:
        """플랫폼별 디렉토리 경로"""
        platform_dir = self._base_path / platform.lower()
        platform_dir.mkdir(parents=True, exist_ok=True)
        return platform_dir

    def _get_profile_path(self, identifier: str, platform: str) -> Path:
        """프로필 파일 경로"""
        # 파일명으로 사용할 수 없는 문자 제거
        safe_identifier = self._sanitize_filename(identifier)
        return self._get_platform_dir(platform) / f"{safe_identifier}.json"

    def _sanitize_filename(self, name: str) -> str:
        """파일명으로 안전한 문자열로 변환"""
        # 파일명에 사용 불가한 문자 제거/대체
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", name)
        # 공백을 언더스코어로
        safe_name = safe_name.replace(" ", "_")
        # 최대 길이 제한
        if len(safe_name) > 200:
            safe_name = safe_name[:200]
        return safe_name

    async def save_profile(self, profile: VisitorProfile) -> None:
        """
        프로필 저장 (원자적 쓰기)

        1. 임시 파일에 쓰기
        2. 기존 파일 백업 (옵션)
        3. 임시 파일을 실제 파일로 이동
        """
        file_path = self._get_profile_path(
            profile.identifier,
            profile.platform.value,
        )
        temp_path = file_path.with_suffix(".json.tmp")
        backup_path = file_path.with_suffix(".json.bak")

        try:
            # 1. 데이터 준비
            data = profile.to_dict()

            # 2. 임시 파일에 쓰기
            indent = 2 if self._pretty_print else None
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)

            # 3. 기존 파일 백업
            if self._create_backup and file_path.exists():
                shutil.copy2(file_path, backup_path)

            # 4. 임시 파일을 실제 파일로 이동 (원자적)
            temp_path.replace(file_path)

            logger.debug(f"Profile saved: {profile.platform.value}:{profile.identifier}")

        except Exception as e:
            # 실패 시 백업에서 복원
            if backup_path.exists() and not file_path.exists():
                try:
                    shutil.copy2(backup_path, file_path)
                    logger.info(f"Restored profile from backup: {file_path}")
                except Exception as restore_error:
                    logger.error(f"Failed to restore from backup: {restore_error}")

            raise StorageError(
                f"Failed to save profile: {e}",
                path=str(file_path),
            ) from e

        finally:
            # 임시 파일 정리
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    async def load_profile(
        self,
        identifier: str,
        platform: str,
    ) -> VisitorProfile | None:
        """
        프로필 로드

        손상된 파일은 백업에서 복구를 시도합니다.
        """
        file_path = self._get_profile_path(identifier, platform)
        backup_path = file_path.with_suffix(".json.bak")

        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 마이그레이션 적용
            data = self._migrator.migrate(data)

            return VisitorProfile.from_dict(data)

        except json.JSONDecodeError as e:
            logger.error(f"Corrupted profile file: {file_path}: {e}")

            # 백업에서 복구 시도
            if backup_path.exists():
                logger.info(f"Attempting to restore from backup: {backup_path}")
                try:
                    shutil.copy2(backup_path, file_path)
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data = self._migrator.migrate(data)
                    return VisitorProfile.from_dict(data)
                except Exception as restore_error:
                    logger.error(f"Failed to restore from backup: {restore_error}")

            raise StorageError(
                f"Corrupted file and no valid backup: {file_path}",
                path=str(file_path),
            ) from e

        except Exception as e:
            raise StorageError(
                f"Failed to load profile: {e}",
                path=str(file_path),
            ) from e

    async def delete_profile(
        self,
        identifier: str,
        platform: str,
    ) -> bool:
        """
        프로필 삭제

        Returns:
            삭제 성공 여부
        """
        file_path = self._get_profile_path(identifier, platform)
        backup_path = file_path.with_suffix(".json.bak")

        if not file_path.exists():
            return False

        try:
            # 메인 파일 삭제
            file_path.unlink()

            # 백업 파일도 삭제
            if backup_path.exists():
                backup_path.unlink()

            logger.info(f"Profile deleted: {platform}:{identifier}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete profile: {e}")
            return False

    async def list_profiles(
        self,
        platform: str | None = None,
    ) -> list[tuple[str, str]]:
        """
        프로필 목록 조회

        Returns:
            (identifier, platform) 튜플 리스트
        """
        results = []

        # 조회할 플랫폼 결정
        if platform:
            platforms = [platform.lower()]
        else:
            platforms = [p.value for p in Platform]

        for plat in platforms:
            plat_dir = self._base_path / plat
            if not plat_dir.exists():
                continue

            for file_path in plat_dir.glob("*.json"):
                # 백업/임시 파일 제외
                if file_path.suffix in [".bak", ".tmp"]:
                    continue
                identifier = file_path.stem
                results.append((identifier, plat))

        return results

    async def profile_exists(
        self,
        identifier: str,
        platform: str,
    ) -> bool:
        """프로필 존재 여부 확인"""
        file_path = self._get_profile_path(identifier, platform)
        return file_path.exists()

    async def iter_profiles(
        self,
        platform: str | None = None,
    ) -> AsyncIterator[VisitorProfile]:
        """
        프로필 순회 (대용량 처리용)

        Yields:
            프로필 객체
        """
        profile_list = await self.list_profiles(platform)

        for identifier, plat in profile_list:
            try:
                profile = await self.load_profile(identifier, plat)
                if profile:
                    yield profile
            except Exception as e:
                logger.warning(f"Failed to load profile {plat}:{identifier}: {e}")
                continue

    async def get_stats(self) -> dict:
        """저장소 통계"""
        stats = {
            "total_profiles": 0,
            "by_platform": {},
        }

        for platform in Platform:
            plat_dir = self._base_path / platform.value
            if plat_dir.exists():
                count = len(list(plat_dir.glob("*.json")))
                stats["by_platform"][platform.value] = count
                stats["total_profiles"] += count

        return stats
