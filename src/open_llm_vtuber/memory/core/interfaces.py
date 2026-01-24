"""
메모리 시스템 인터페이스 정의

Protocol을 사용하여 구현체와 분리된 인터페이스를 정의합니다.
"""

from typing import Protocol, runtime_checkable, AsyncIterator
from .models import VisitorProfile


@runtime_checkable
class ProfileLoader(Protocol):
    """프로필 로드 인터페이스"""

    async def load_profile(
        self,
        identifier: str,
        platform: str,
    ) -> VisitorProfile | None:
        """
        프로필 로드

        Args:
            identifier: 사용자 식별자 (닉네임, ID 등)
            platform: 플랫폼 (discord, youtube, direct 등)

        Returns:
            프로필 객체 또는 None (없는 경우)
        """
        ...


@runtime_checkable
class ProfileSaver(Protocol):
    """프로필 저장 인터페이스"""

    async def save_profile(self, profile: VisitorProfile) -> None:
        """
        프로필 저장

        Args:
            profile: 저장할 프로필 객체
        """
        ...


@runtime_checkable
class MemoryStore(ProfileLoader, ProfileSaver, Protocol):
    """
    메모리 저장소 인터페이스

    프로필의 CRUD 작업과 검색 기능을 정의합니다.
    """

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
        ...

    async def list_profiles(
        self,
        platform: str | None = None,
    ) -> list[tuple[str, str]]:
        """
        프로필 목록 조회

        Args:
            platform: 특정 플랫폼만 조회 (None이면 전체)

        Returns:
            (identifier, platform) 튜플 리스트
        """
        ...

    async def profile_exists(
        self,
        identifier: str,
        platform: str,
    ) -> bool:
        """
        프로필 존재 여부 확인

        Args:
            identifier: 사용자 식별자
            platform: 플랫폼

        Returns:
            존재 여부
        """
        ...

    def iter_profiles(
        self,
        platform: str | None = None,
    ) -> AsyncIterator[VisitorProfile]:
        """
        프로필 순회 (대용량 처리용)

        Args:
            platform: 특정 플랫폼만 조회 (None이면 전체)

        Yields:
            프로필 객체
        """
        ...
