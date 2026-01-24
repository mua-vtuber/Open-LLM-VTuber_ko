"""
프로필 캐시

TTL 기반 인메모리 캐시로 프로필 조회 성능을 향상시킵니다.
"""

import logging
import time
from threading import Lock
from typing import Any
from collections import OrderedDict

from ..core.models import VisitorProfile

logger = logging.getLogger(__name__)


class ProfileCache:
    """
    TTL 기반 프로필 캐시

    특징:
    - TTL(Time To Live) 지원: 일정 시간 후 자동 만료
    - LRU(Least Recently Used) 정책: 최대 크기 초과 시 오래된 항목 제거
    - 스레드 안전: Lock을 사용한 동시성 제어
    - 통계 제공: 히트율, 캐시 크기 등
    """

    def __init__(
        self,
        maxsize: int = 1000,
        ttl_seconds: int = 300,  # 5분
    ):
        """
        Args:
            maxsize: 최대 캐시 크기
            ttl_seconds: 항목 만료 시간 (초)
        """
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[VisitorProfile, float]] = OrderedDict()
        self._lock = Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
        }

    def _make_key(self, identifier: str, platform: str) -> str:
        """캐시 키 생성"""
        return f"{platform.lower()}:{identifier}"

    def _is_expired(self, timestamp: float) -> bool:
        """항목 만료 여부 확인"""
        return time.time() - timestamp > self._ttl_seconds

    def _evict_expired(self) -> None:
        """만료된 항목 제거 (락 획득 상태에서 호출)"""
        now = time.time()
        expired_keys = [
            key
            for key, (_, timestamp) in self._cache.items()
            if now - timestamp > self._ttl_seconds
        ]
        for key in expired_keys:
            del self._cache[key]
            self._stats["expirations"] += 1

    def _evict_lru(self) -> None:
        """LRU 정책으로 오래된 항목 제거 (락 획득 상태에서 호출)"""
        while len(self._cache) >= self._maxsize:
            self._cache.popitem(last=False)  # 가장 오래된 항목 제거
            self._stats["evictions"] += 1

    def get(
        self,
        identifier: str,
        platform: str,
    ) -> VisitorProfile | None:
        """
        캐시에서 프로필 조회

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼

        Returns:
            프로필 객체 또는 None (없거나 만료된 경우)
        """
        key = self._make_key(identifier, platform)

        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None

            profile, timestamp = self._cache[key]

            # 만료 확인
            if self._is_expired(timestamp):
                del self._cache[key]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None

            # LRU 업데이트: 최근 사용으로 이동
            self._cache.move_to_end(key)
            self._stats["hits"] += 1
            return profile

    def set(self, profile: VisitorProfile) -> None:
        """
        프로필을 캐시에 저장

        Args:
            profile: 저장할 프로필
        """
        key = self._make_key(profile.identifier, profile.platform.value)

        with self._lock:
            # 만료된 항목 정리
            self._evict_expired()

            # 새 항목을 위한 공간 확보
            if key not in self._cache:
                self._evict_lru()

            # 저장 (기존 항목이면 업데이트)
            self._cache[key] = (profile, time.time())
            self._cache.move_to_end(key)

    def invalidate(self, identifier: str, platform: str) -> bool:
        """
        특정 프로필 캐시 무효화

        Returns:
            무효화된 항목이 있었는지 여부
        """
        key = self._make_key(identifier, platform)

        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        """
        전체 캐시 삭제

        Returns:
            삭제된 항목 수
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def get_stats(self) -> dict[str, Any]:
        """
        캐시 통계 조회

        Returns:
            통계 딕셔너리
        """
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0

            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": f"{hit_rate:.1%}",
                "evictions": self._stats["evictions"],
                "expirations": self._stats["expirations"],
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "ttl_seconds": self._ttl_seconds,
            }

    def reset_stats(self) -> None:
        """통계 초기화"""
        with self._lock:
            self._stats = {
                "hits": 0,
                "misses": 0,
                "evictions": 0,
                "expirations": 0,
            }

    def __len__(self) -> int:
        """현재 캐시 크기"""
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: tuple[str, str]) -> bool:
        """(identifier, platform) 튜플로 존재 여부 확인"""
        identifier, platform = key
        return self.get(identifier, platform) is not None
