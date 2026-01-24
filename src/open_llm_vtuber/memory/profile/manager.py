"""
프로필 관리자

프로필 CRUD 작업, 캐싱 통합, 동시성 안전 처리를 담당합니다.
"""

import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from ..core.models import VisitorProfile, Platform
from ..core.interfaces import MemoryStore
from ..core.exceptions import ProfileNotFoundError
from .cache import ProfileCache

logger = logging.getLogger(__name__)


class ProfileManager:
    """
    프로필 관리자

    특징:
    - 캐시 통합: 조회 시 캐시 우선, 저장 시 캐시 동기화
    - 동시성 안전: 프로필별 락으로 동시 수정 방지
    - 자동 생성: 없는 프로필 조회 시 선택적 자동 생성
    """

    def __init__(
        self,
        store: MemoryStore,
        cache: ProfileCache | None = None,
        auto_create: bool = True,
    ):
        """
        Args:
            store: 저장소 구현체
            cache: 캐시 (None이면 새로 생성)
            auto_create: get_or_create 시 자동 생성 여부
        """
        self._store = store
        self._cache = cache or ProfileCache()
        self._auto_create = auto_create
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock_key(self, identifier: str, platform: str) -> str:
        """락 키 생성"""
        return f"{platform.lower()}:{identifier}"

    def _get_lock(self, identifier: str, platform: str) -> asyncio.Lock:
        """프로필별 락 획득 (없으면 생성)"""
        key = self._get_lock_key(identifier, platform)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    @asynccontextmanager
    async def acquire_profile(
        self,
        identifier: str,
        platform: str,
    ) -> AsyncIterator[VisitorProfile | None]:
        """
        프로필 락 획득 후 작업 (컨텍스트 매니저)

        사용 예:
            async with manager.acquire_profile("user", "discord") as profile:
                if profile:
                    profile.visit_count += 1
                # 컨텍스트 종료 시 자동 저장

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼

        Yields:
            프로필 객체 또는 None
        """
        lock = self._get_lock(identifier, platform)
        async with lock:
            profile = await self.load_profile(identifier, platform)
            yield profile
            if profile:
                await self.save_profile(profile)

    async def load_profile(
        self,
        identifier: str,
        platform: str,
    ) -> VisitorProfile | None:
        """
        프로필 로드 (캐시 우선)

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼

        Returns:
            프로필 객체 또는 None
        """
        platform = platform.lower()

        # 1. 캐시 확인
        cached = self._cache.get(identifier, platform)
        if cached:
            logger.debug(f"Cache hit: {platform}:{identifier}")
            return cached

        # 2. 저장소에서 로드
        profile = await self._store.load_profile(identifier, platform)

        # 3. 캐시에 저장
        if profile:
            self._cache.set(profile)
            logger.debug(f"Loaded from store: {platform}:{identifier}")

        return profile

    async def save_profile(self, profile: VisitorProfile) -> None:
        """
        프로필 저장 (저장소 + 캐시)

        Args:
            profile: 저장할 프로필
        """
        # updated_at 갱신
        profile.updated_at = datetime.now()

        # 저장소에 저장
        await self._store.save_profile(profile)

        # 캐시 갱신
        self._cache.set(profile)

        logger.debug(f"Saved: {profile.platform.value}:{profile.identifier}")

    async def get_or_create(
        self,
        identifier: str,
        platform: str,
    ) -> tuple[VisitorProfile, bool]:
        """
        프로필 조회 또는 생성

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼

        Returns:
            (프로필, 새로 생성됨 여부) 튜플
        """
        platform = platform.lower()
        lock = self._get_lock(identifier, platform)

        async with lock:
            # 기존 프로필 확인
            profile = await self.load_profile(identifier, platform)
            if profile:
                return profile, False

            # 새 프로필 생성
            profile = VisitorProfile.create_new(identifier, platform)
            await self.save_profile(profile)
            logger.info(f"Created new profile: {platform}:{identifier}")
            return profile, True

    async def update_profile(
        self,
        identifier: str,
        platform: str,
        updates: dict[str, Any],
    ) -> VisitorProfile | None:
        """
        프로필 안전하게 업데이트 (락 사용)

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼
            updates: 업데이트할 필드 딕셔너리

        Returns:
            업데이트된 프로필 또는 None (없는 경우)
        """
        async with self.acquire_profile(identifier, platform) as profile:
            if profile is None:
                return None

            for key, value in updates.items():
                if hasattr(profile, key) and not key.startswith("_"):
                    setattr(profile, key, value)

            return profile

    async def delete_profile(
        self,
        identifier: str,
        platform: str,
    ) -> bool:
        """
        프로필 삭제

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼

        Returns:
            삭제 성공 여부
        """
        platform = platform.lower()
        lock = self._get_lock(identifier, platform)

        async with lock:
            # 캐시에서 제거
            self._cache.invalidate(identifier, platform)

            # 저장소에서 삭제
            result = await self._store.delete_profile(identifier, platform)

            if result:
                logger.info(f"Deleted profile: {platform}:{identifier}")

            return result

    async def record_visit(
        self,
        identifier: str,
        platform: str,
    ) -> VisitorProfile:
        """
        방문 기록 (visit_count 증가, last_visit 갱신)

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼

        Returns:
            업데이트된 프로필
        """
        profile, created = await self.get_or_create(identifier, platform)

        if not created:
            async with self.acquire_profile(identifier, platform) as p:
                if p:
                    p.visit_count += 1
                    p.last_visit = datetime.now()
                    profile = p

        return profile

    async def record_message(
        self,
        identifier: str,
        platform: str,
        count: int = 1,
    ) -> None:
        """
        메시지 수 기록

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼
            count: 추가할 메시지 수
        """
        async with self.acquire_profile(identifier, platform) as profile:
            if profile:
                profile.total_messages += count

    async def add_known_fact(
        self,
        identifier: str,
        platform: str,
        fact: str,
    ) -> bool:
        """
        알려진 사실 추가 (중복 방지)

        Returns:
            추가 성공 여부 (이미 있으면 False)
        """
        async with self.acquire_profile(identifier, platform) as profile:
            if profile is None:
                return False

            # 중복 확인
            if fact in profile.known_facts:
                return False

            profile.known_facts.append(fact)
            return True

    async def add_preference(
        self,
        identifier: str,
        platform: str,
        category: str,  # "likes" or "dislikes"
        item: str,
    ) -> bool:
        """
        선호도 추가

        Args:
            category: "likes" 또는 "dislikes"
            item: 추가할 항목

        Returns:
            추가 성공 여부
        """
        if category not in ("likes", "dislikes"):
            raise ValueError(f"Invalid category: {category}")

        async with self.acquire_profile(identifier, platform) as profile:
            if profile is None:
                return False

            if item in profile.preferences[category]:
                return False

            profile.preferences[category].append(item)
            return True

    async def update_affinity(
        self,
        identifier: str,
        platform: str,
        delta: float,
    ) -> float | None:
        """
        친밀도 조정

        Args:
            delta: 변경량 (양수: 증가, 음수: 감소)

        Returns:
            새 친밀도 값 또는 None (프로필 없음)
        """
        async with self.acquire_profile(identifier, platform) as profile:
            if profile is None:
                return None

            # 0-100 범위 유지
            profile.affinity_score = max(0, min(100, profile.affinity_score + delta))
            return profile.affinity_score

    async def list_profiles(
        self,
        platform: str | None = None,
    ) -> list[tuple[str, str]]:
        """
        프로필 목록 조회

        Returns:
            (identifier, platform) 튜플 리스트
        """
        return await self._store.list_profiles(platform)

    def get_cache_stats(self) -> dict[str, Any]:
        """캐시 통계 조회"""
        return self._cache.get_stats()

    def clear_cache(self) -> int:
        """캐시 전체 삭제"""
        return self._cache.clear()
