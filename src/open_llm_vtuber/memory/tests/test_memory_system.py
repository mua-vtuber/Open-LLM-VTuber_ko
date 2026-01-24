"""
메모리 시스템 통합 테스트

실행 방법:
    cd Open-LLM-VTuber
    python -m pytest src/open_llm_vtuber/memory/tests/test_memory_system.py -v

또는 직접 실행:
    python src/open_llm_vtuber/memory/tests/test_memory_system.py
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import sys

# 테스트 대상 모듈
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from open_llm_vtuber.memory.core.models import (
    VisitorProfile,
    Platform,
    Sentiment,
    ConversationSummary,
    SCHEMA_VERSION,
)
from open_llm_vtuber.memory.core.exceptions import (
    StorageError,
    MigrationError,
)
from open_llm_vtuber.memory.storage.json_store import JsonProfileStore
from open_llm_vtuber.memory.storage.migrations.migrator import ProfileMigrator
from open_llm_vtuber.memory.profile.cache import ProfileCache
from open_llm_vtuber.memory.profile.manager import ProfileManager


class TestVisitorProfile:
    """VisitorProfile 모델 테스트"""

    def test_create_new(self):
        """새 프로필 생성"""
        profile = VisitorProfile.create_new("test_user", "discord")

        assert profile.identifier == "test_user"
        assert profile.platform == Platform.DISCORD
        assert profile.visit_count == 1
        assert profile.total_messages == 0
        assert profile.affinity_score == 50.0
        assert profile._schema_version == SCHEMA_VERSION

    def test_to_dict_and_from_dict(self):
        """직렬화/역직렬화"""
        profile = VisitorProfile.create_new("test_user", "discord")
        profile.known_facts = ["개발자", "고양이 키움"]
        profile.preferences["likes"].append("게임")

        data = profile.to_dict()
        restored = VisitorProfile.from_dict(data)

        assert restored.identifier == profile.identifier
        assert restored.platform == profile.platform
        assert restored.known_facts == profile.known_facts
        assert restored.preferences == profile.preferences

    def test_get_summary_text(self):
        """요약 텍스트 생성"""
        profile = VisitorProfile.create_new("게이머김철수", "discord")
        profile.known_facts = ["개발자", "고양이 키움", "서울 거주"]
        profile.preferences["likes"] = ["게임", "애니메이션"]
        profile.tags = ["단골", "친절함"]
        profile.visit_count = 10

        summary = profile.get_summary_text()

        assert "게이머김철수" in summary
        assert "개발자" in summary
        assert "게임" in summary
        assert "단골" in summary
        assert "방문 10회" in summary

    def test_platform_from_string(self):
        """Platform enum 문자열 변환"""
        assert Platform.from_string("discord") == Platform.DISCORD
        assert Platform.from_string("DISCORD") == Platform.DISCORD
        assert Platform.from_string("unknown") == Platform.DIRECT


class TestConversationSummary:
    """ConversationSummary 모델 테스트"""

    def test_to_dict_and_from_dict(self):
        """직렬화/역직렬화"""
        summary = ConversationSummary(
            date=datetime.now(),
            duration_minutes=30,
            message_count=20,
            topics_discussed=["게임", "일상"],
            key_points=["새 게임 추천받음"],
            sentiment=Sentiment.POSITIVE,
            new_facts=["FPS 게임 좋아함"],
            opinion_updates={"게임": "FPS 선호"},
            importance_score=0.7,
        )

        data = summary.to_dict()
        restored = ConversationSummary.from_dict(data)

        assert restored.duration_minutes == summary.duration_minutes
        assert restored.topics_discussed == summary.topics_discussed
        assert restored.sentiment == summary.sentiment
        assert restored.importance_score == summary.importance_score


class TestProfileMigrator:
    """마이그레이션 테스트"""

    def test_migrate_v0_to_v1(self):
        """v0 → v1 마이그레이션"""
        # v0 데이터 (최소한의 필드만)
        old_data = {
            "identifier": "old_user",
            "first_visit": "2024-01-01T00:00:00",
            "last_visit": "2024-01-15T00:00:00",
        }

        migrator = ProfileMigrator()
        migrated = migrator.migrate(old_data)

        assert migrated["_schema_version"] == SCHEMA_VERSION
        assert migrated["platform"] == "direct"
        assert "meta_summaries" in migrated
        assert "created_at" in migrated
        assert "preferences" in migrated
        assert migrated["preferences"]["likes"] == []

    def test_already_current_version(self):
        """이미 최신 버전인 경우"""
        data = {"_schema_version": SCHEMA_VERSION, "identifier": "user"}

        migrator = ProfileMigrator()
        result = migrator.migrate(data)

        assert result == data


class TestJsonProfileStore:
    """JSON 저장소 테스트"""

    def setup_method(self):
        """테스트 전 임시 디렉토리 생성"""
        self.temp_dir = tempfile.mkdtemp()
        self.store = JsonProfileStore(self.temp_dir)

    def teardown_method(self):
        """테스트 후 임시 디렉토리 삭제"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def _test_save_and_load(self):
        """저장 및 로드"""
        profile = VisitorProfile.create_new("test_user", "discord")
        profile.known_facts = ["테스트 사실"]

        await self.store.save_profile(profile)
        loaded = await self.store.load_profile("test_user", "discord")

        assert loaded is not None
        assert loaded.identifier == "test_user"
        assert loaded.known_facts == ["테스트 사실"]

    def test_save_and_load(self):
        asyncio.run(self._test_save_and_load())

    async def _test_delete(self):
        """삭제"""
        profile = VisitorProfile.create_new("to_delete", "discord")
        await self.store.save_profile(profile)

        # 삭제 전 확인
        exists = await self.store.profile_exists("to_delete", "discord")
        assert exists is True

        # 삭제
        result = await self.store.delete_profile("to_delete", "discord")
        assert result is True

        # 삭제 후 확인
        exists = await self.store.profile_exists("to_delete", "discord")
        assert exists is False

    def test_delete(self):
        asyncio.run(self._test_delete())

    async def _test_list_profiles(self):
        """프로필 목록 조회"""
        await self.store.save_profile(VisitorProfile.create_new("user1", "discord"))
        await self.store.save_profile(VisitorProfile.create_new("user2", "discord"))
        await self.store.save_profile(VisitorProfile.create_new("user3", "youtube"))

        # 전체 조회
        all_profiles = await self.store.list_profiles()
        assert len(all_profiles) == 3

        # 플랫폼별 조회
        discord_only = await self.store.list_profiles("discord")
        assert len(discord_only) == 2

    def test_list_profiles(self):
        asyncio.run(self._test_list_profiles())

    async def _test_sanitize_filename(self):
        """특수문자 포함 식별자 처리"""
        profile = VisitorProfile.create_new("user<>:/\\|?*name", "discord")
        await self.store.save_profile(profile)

        loaded = await self.store.load_profile("user<>:/\\|?*name", "discord")
        assert loaded is not None
        assert loaded.identifier == "user<>:/\\|?*name"

    def test_sanitize_filename(self):
        asyncio.run(self._test_sanitize_filename())


class TestProfileCache:
    """프로필 캐시 테스트"""

    def test_get_set(self):
        """기본 캐시 동작"""
        cache = ProfileCache(maxsize=10, ttl_seconds=60)
        profile = VisitorProfile.create_new("user", "discord")

        # 저장 전
        assert cache.get("user", "discord") is None

        # 저장 후
        cache.set(profile)
        cached = cache.get("user", "discord")
        assert cached is not None
        assert cached.identifier == "user"

    def test_ttl_expiration(self):
        """TTL 만료"""
        cache = ProfileCache(maxsize=10, ttl_seconds=0)  # 즉시 만료
        profile = VisitorProfile.create_new("user", "discord")

        cache.set(profile)
        # TTL=0이므로 즉시 만료
        import time
        time.sleep(0.01)  # 약간의 지연
        assert cache.get("user", "discord") is None

    def test_lru_eviction(self):
        """LRU 제거"""
        cache = ProfileCache(maxsize=2, ttl_seconds=60)

        cache.set(VisitorProfile.create_new("user1", "discord"))
        cache.set(VisitorProfile.create_new("user2", "discord"))
        cache.set(VisitorProfile.create_new("user3", "discord"))  # user1 제거됨

        assert cache.get("user1", "discord") is None
        assert cache.get("user2", "discord") is not None
        assert cache.get("user3", "discord") is not None

    def test_invalidate(self):
        """캐시 무효화"""
        cache = ProfileCache()
        profile = VisitorProfile.create_new("user", "discord")

        cache.set(profile)
        assert cache.get("user", "discord") is not None

        cache.invalidate("user", "discord")
        assert cache.get("user", "discord") is None

    def test_stats(self):
        """통계"""
        cache = ProfileCache()
        profile = VisitorProfile.create_new("user", "discord")

        cache.get("user", "discord")  # miss
        cache.set(profile)
        cache.get("user", "discord")  # hit
        cache.get("user", "discord")  # hit

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1


class TestProfileManager:
    """프로필 관리자 테스트"""

    def setup_method(self):
        """테스트 전 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.store = JsonProfileStore(self.temp_dir)
        self.cache = ProfileCache()
        self.manager = ProfileManager(self.store, self.cache)

    def teardown_method(self):
        """테스트 후 정리"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def _test_get_or_create(self):
        """조회 또는 생성"""
        # 첫 번째 호출: 생성
        profile1, created1 = await self.manager.get_or_create("user", "discord")
        assert created1 is True
        assert profile1.identifier == "user"

        # 두 번째 호출: 조회
        profile2, created2 = await self.manager.get_or_create("user", "discord")
        assert created2 is False
        assert profile2.identifier == "user"

    def test_get_or_create(self):
        asyncio.run(self._test_get_or_create())

    async def _test_record_visit(self):
        """방문 기록"""
        await self.manager.record_visit("user", "discord")
        await self.manager.record_visit("user", "discord")
        await self.manager.record_visit("user", "discord")

        profile = await self.manager.load_profile("user", "discord")
        assert profile.visit_count == 3

    def test_record_visit(self):
        asyncio.run(self._test_record_visit())

    async def _test_acquire_profile(self):
        """컨텍스트 매니저를 통한 안전한 수정"""
        await self.manager.get_or_create("user", "discord")

        async with self.manager.acquire_profile("user", "discord") as profile:
            profile.known_facts.append("새로운 사실")
            profile.affinity_score = 75.0

        # 저장 확인
        loaded = await self.manager.load_profile("user", "discord")
        assert "새로운 사실" in loaded.known_facts
        assert loaded.affinity_score == 75.0

    def test_acquire_profile(self):
        asyncio.run(self._test_acquire_profile())

    async def _test_concurrent_updates(self):
        """동시 업데이트 테스트"""
        await self.manager.get_or_create("concurrent_user", "discord")

        async def increment():
            async with self.manager.acquire_profile("concurrent_user", "discord") as p:
                if p:
                    p.visit_count += 1

        # 10개의 동시 업데이트
        await asyncio.gather(*[increment() for _ in range(10)])

        profile = await self.manager.load_profile("concurrent_user", "discord")
        assert profile.visit_count == 11  # 초기 1 + 10

    def test_concurrent_updates(self):
        asyncio.run(self._test_concurrent_updates())

    async def _test_add_known_fact(self):
        """사실 추가 (중복 방지)"""
        await self.manager.get_or_create("user", "discord")

        result1 = await self.manager.add_known_fact("user", "discord", "개발자")
        result2 = await self.manager.add_known_fact("user", "discord", "개발자")  # 중복

        assert result1 is True
        assert result2 is False

        profile = await self.manager.load_profile("user", "discord")
        assert profile.known_facts.count("개발자") == 1

    def test_add_known_fact(self):
        asyncio.run(self._test_add_known_fact())

    async def _test_update_affinity(self):
        """친밀도 업데이트"""
        await self.manager.get_or_create("user", "discord")

        # 증가
        new_score = await self.manager.update_affinity("user", "discord", 10)
        assert new_score == 60.0

        # 감소
        new_score = await self.manager.update_affinity("user", "discord", -20)
        assert new_score == 40.0

        # 하한 테스트
        new_score = await self.manager.update_affinity("user", "discord", -100)
        assert new_score == 0.0

        # 상한 테스트
        new_score = await self.manager.update_affinity("user", "discord", 200)
        assert new_score == 100.0

    def test_update_affinity(self):
        asyncio.run(self._test_update_affinity())

    async def _test_cache_integration(self):
        """캐시 통합"""
        await self.manager.get_or_create("cached_user", "discord")

        # 캐시 히트 확인
        stats_before = self.manager.get_cache_stats()
        await self.manager.load_profile("cached_user", "discord")
        stats_after = self.manager.get_cache_stats()

        assert stats_after["hits"] > stats_before["hits"]

    def test_cache_integration(self):
        asyncio.run(self._test_cache_integration())


def run_all_tests():
    """모든 테스트 실행"""
    print("=" * 60)
    print("메모리 시스템 테스트")
    print("=" * 60)

    test_classes = [
        TestVisitorProfile,
        TestConversationSummary,
        TestProfileMigrator,
        TestJsonProfileStore,
        TestProfileCache,
        TestProfileManager,
    ]

    total_passed = 0
    total_failed = 0
    failed_tests = []

    for test_class in test_classes:
        print(f"\n{test_class.__name__}")
        print("-" * 40)

        instance = test_class()
        test_methods = [m for m in dir(instance) if m.startswith("test_")]

        for method_name in test_methods:
            try:
                # setup
                if hasattr(instance, "setup_method"):
                    instance.setup_method()

                # run test
                method = getattr(instance, method_name)
                method()

                print(f"  ✓ {method_name}")
                total_passed += 1

            except Exception as e:
                print(f"  ✗ {method_name}: {e}")
                total_failed += 1
                failed_tests.append(f"{test_class.__name__}.{method_name}")

            finally:
                # teardown
                if hasattr(instance, "teardown_method"):
                    try:
                        instance.teardown_method()
                    except Exception:
                        pass

    print("\n" + "=" * 60)
    print(f"결과: {total_passed} 통과, {total_failed} 실패")

    if failed_tests:
        print("\n실패한 테스트:")
        for test in failed_tests:
            print(f"  - {test}")

    print("=" * 60)

    return total_failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
