"""End-to-end integration tests for UMSA Phase 2.

Exercises the complete session lifecycle with real SQLite, real regex
extraction, real stream context tracking, real procedural memory, and
real reflection -- no mocks.  LLM extraction is disabled so that
only the regex hot-path runs.

Tests:
- Full session lifecycle (start -> turns -> context -> end -> verify)
- Regex extraction persists memories to SQLite
- Procedural rules appear in built context
- Stream context appears in built context
- Session end clears stream context
"""

from __future__ import annotations

import pytest

from open_llm_vtuber.umsa.config import (
    ExtractionConfig,
    MemoryConfig,
    StorageConfig,
)
from open_llm_vtuber.umsa.memory_service import MemoryService
from open_llm_vtuber.umsa.models import Message


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def memory_service(tmp_path):
    """Create a fully-wired MemoryService backed by a temp SQLite DB.

    Uses regex-only extraction (LLM disabled) with relaxed thresholds
    so that regex results (confidence=0.5) pass filtering.

    Pre-initialises the SQLite store so that entity profiles can be
    created before sessions reference them via foreign keys.
    """
    config = MemoryConfig(
        enabled=True,
        storage=StorageConfig(sqlite_db_path=str(tmp_path / "test.db")),
        extraction=ExtractionConfig(
            enabled=True,
            regex_enabled=True,
            llm_extraction_mode="disabled",
            batch_size=1,
            min_importance=0.0,
            confidence_threshold=0.0,
        ),
        consolidation={"enabled": False},
    )
    svc = MemoryService(config=config)

    # Wire the extractor explicitly since set_llm() is not called
    # (regex-only mode requires constructing the extractor ourselves).
    from open_llm_vtuber.umsa.extraction import MemoryExtractor

    svc._extractor = MemoryExtractor(
        llm=None, config=config.extraction,
    )

    # Pre-initialise the store so FK-dependent helpers work immediately.
    await svc._ensure_store()

    yield svc

    await svc.close()


async def _ensure_entity(svc: MemoryService, entity_id: str, platform: str = "direct") -> None:
    """Create an entity profile so FK constraints on sessions/nodes pass."""
    store = await svc._ensure_store()
    await store.touch_entity(entity_id, platform)


# ---------------------------------------------------------------------------
# 1. Full Session Lifecycle
# ---------------------------------------------------------------------------


class TestFullSessionLifecycle:
    """Start session -> stream context -> turns -> build context -> end session."""

    async def test_full_session_lifecycle(self, memory_service: MemoryService):
        """Complete lifecycle: start, stream updates, turns, context, end."""
        svc = memory_service

        # Create entity profile first so FK constraints pass
        await _ensure_entity(svc, "viewer42", platform="youtube")

        # -- Start session ---------------------------------------------------
        session_id = await svc.start_session(
            entity_id="viewer42", platform="youtube",
        )
        assert session_id.startswith("session_")

        # -- Update stream context -------------------------------------------
        svc.stream_context.current_topic = "Python programming"
        svc.stream_context.update(
            author="chatter_A", content="Nice stream!", msg_type="chat",
        )
        svc.stream_context.update(
            author="whale_B",
            content="$50 superchat!",
            msg_type="superchat",
            metadata={"amount": 50},
        )

        assert svc.stream_context.message_count >= 2

        # -- Process conversation turns with extractable content -------------
        turns = [
            (
                Message(role="user", content="I like Python", name="viewer42"),
                Message(role="assistant", content="Python is awesome!"),
            ),
            (
                Message(
                    role="user",
                    content="I live in Seoul",
                    name="viewer42",
                ),
                Message(role="assistant", content="Seoul is a great city!"),
            ),
            (
                Message(
                    role="user",
                    content="나는 파이썬 좋아해",
                    name="viewer42",
                ),
                Message(role="assistant", content="파이썬 좋죠!"),
            ),
        ]
        for user_msg, asst_msg in turns:
            await svc.process_turn(
                user_msg, asst_msg, entity_id="viewer42",
            )
            svc.increment_session_message_count(session_id)

        # -- Build context and verify ----------------------------------------
        messages = [
            {"role": "user", "content": "Tell me about Python"},
            {"role": "assistant", "content": "Python is a great language"},
            {"role": "user", "content": "What else?"},
        ]
        ctx = await svc.build_context(
            messages=messages,
            entity_id="viewer42",
            system_prompt="You are a helpful AI streamer.",
            max_tokens=4096,
        )

        # System content should include stream context info
        assert "Stream Status" in ctx.system_content or "stream" in ctx.system_content.lower()
        assert ctx.messages  # Should have fitted messages

        # -- End session (triggers episode save, reflection, cleanup) --------
        await svc.end_session(session_id)

        # -- Verify stream episode was stored --------------------------------
        store = await svc._ensure_store()
        episodes = await store.get_stream_episodes(limit=10)
        assert len(episodes) >= 1

        matching = [
            ep for ep in episodes
            if ep.get("session_id") == session_id
        ]
        assert len(matching) == 1
        episode = matching[0]
        assert episode["summary"]  # Non-empty summary
        assert session_id in episode.get("id", "")

        # -- Verify stream context was cleared after end_session -------------
        assert svc.stream_context.message_count == 0

        # -- Verify extracted memories persisted -----------------------------
        all_memories = await svc.get_all_memories(entity_id="viewer42")
        # Regex should have extracted preferences/facts from the turns.
        # Filter out episode/meta_summary nodes that end_session creates.
        extracted = [
            m for m in all_memories
            if m["node_type"] not in ("episode", "meta_summary")
        ]
        assert len(extracted) > 0


# ---------------------------------------------------------------------------
# 2. Regex Extraction Persists Memories
# ---------------------------------------------------------------------------


class TestRegexExtractionPersistsMemories:
    """Verify regex-extracted memories survive in SQLite."""

    async def test_english_extraction_persisted(
        self, memory_service: MemoryService,
    ):
        """English preference extraction is stored in SQLite."""
        svc = memory_service
        await _ensure_entity(svc, "user_en")

        session_id = await svc.start_session(entity_id="user_en")

        await svc.process_turn(
            Message(role="user", content="I like Python", name="user_en"),
            Message(role="assistant", content="Nice choice!"),
            entity_id="user_en",
        )

        all_memories = await svc.get_all_memories(entity_id="user_en")
        assert len(all_memories) > 0
        contents = [m["content"].lower() for m in all_memories]
        assert any("python" in c for c in contents)

        await svc.end_session(session_id)

    async def test_korean_extraction_persisted(
        self, memory_service: MemoryService,
    ):
        """Korean preference extraction is stored in SQLite."""
        svc = memory_service
        await _ensure_entity(svc, "user_kr")

        session_id = await svc.start_session(entity_id="user_kr")

        await svc.process_turn(
            Message(
                role="user",
                content="나는 파이썬 좋아해",
                name="user_kr",
            ),
            Message(role="assistant", content="파이썬 좋죠!"),
            entity_id="user_kr",
        )

        all_memories = await svc.get_all_memories(entity_id="user_kr")
        assert len(all_memories) > 0
        contents = [m["content"] for m in all_memories]
        assert any("파이썬" in c for c in contents)

        await svc.end_session(session_id)

    async def test_multiple_extractions_accumulate(
        self, memory_service: MemoryService,
    ):
        """Multiple turns accumulate distinct memories."""
        svc = memory_service
        await _ensure_entity(svc, "user_multi")

        session_id = await svc.start_session(entity_id="user_multi")

        await svc.process_turn(
            Message(role="user", content="I like cats", name="user_multi"),
            Message(role="assistant", content="Meow!"),
            entity_id="user_multi",
        )
        await svc.process_turn(
            Message(
                role="user", content="I live in Seoul", name="user_multi",
            ),
            Message(role="assistant", content="Cool city!"),
            entity_id="user_multi",
        )

        all_memories = await svc.get_all_memories(entity_id="user_multi")
        contents_lower = [m["content"].lower() for m in all_memories]
        assert any("cat" in c for c in contents_lower)
        assert any("seoul" in c for c in contents_lower)

        await svc.end_session(session_id)


# ---------------------------------------------------------------------------
# 3. Procedural Rules in Built Context
# ---------------------------------------------------------------------------


class TestContextIncludesProceduralRules:
    """Verify procedural rules appear in assembled context."""

    async def test_loaded_rules_appear_in_context(
        self, memory_service: MemoryService,
    ):
        """Procedural rules loaded via load_rules() appear in system_content."""
        svc = memory_service

        # Insert procedural rules into SQLite so start_session loads them
        store = await svc._ensure_store()
        await store.insert_procedural_rule({
            "id": "rule_greet",
            "rule_type": "greeting",
            "content": "Always greet viewers warmly",
            "confidence": 0.9,
            "source": "learned",
            "active": 1,
        })
        await store.insert_procedural_rule({
            "id": "rule_tone",
            "rule_type": "tone",
            "content": "Use casual and friendly tone",
            "confidence": 0.8,
            "source": "learned",
            "active": 1,
        })

        # Start session -- this loads procedural rules from SQLite
        # entity_id=None avoids needing an entity profile for FK
        session_id = await svc.start_session()
        assert len(svc.procedural_memory.rules) == 2

        # Build context
        messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        ctx = await svc.build_context(
            messages=messages,
            system_prompt="You are an AI streamer.",
            max_tokens=4096,
        )

        # The system content should contain procedural rule text
        assert "Always greet viewers warmly" in ctx.system_content
        assert "Use casual and friendly tone" in ctx.system_content
        assert "Learned Behavior" in ctx.system_content

        await svc.end_session(session_id)

    async def test_no_rules_produces_empty_procedural_section(
        self, memory_service: MemoryService,
    ):
        """When no rules are loaded, procedural section is absent."""
        svc = memory_service

        session_id = await svc.start_session()
        assert len(svc.procedural_memory.rules) == 0

        messages = [{"role": "user", "content": "Hi"}]
        ctx = await svc.build_context(
            messages=messages,
            system_prompt="Test prompt.",
            max_tokens=4096,
        )

        # No procedural rules section should appear
        assert "Learned Behavior" not in ctx.system_content

        await svc.end_session(session_id)


# ---------------------------------------------------------------------------
# 4. Stream Context in Built Context
# ---------------------------------------------------------------------------


class TestStreamContextInBuiltContext:
    """Verify stream context appears in assembled context."""

    async def test_stream_info_appears_in_system_content(
        self, memory_service: MemoryService,
    ):
        """Stream topic and events appear in system_content."""
        svc = memory_service

        session_id = await svc.start_session()

        # Update stream context with topic and events
        svc.stream_context.current_topic = "Gaming night"
        svc.stream_context.update(
            author="viewer1", content="Nice game!", msg_type="chat",
        )
        svc.stream_context.update(
            author="big_donor",
            content="Keep it up!",
            msg_type="superchat",
            metadata={"amount": 100},
        )

        messages = [
            {"role": "user", "content": "What are we playing?"},
            {"role": "assistant", "content": "Let's play some games!"},
        ]
        ctx = await svc.build_context(
            messages=messages,
            system_prompt="You are a gaming streamer.",
            max_tokens=4096,
        )

        # Stream context should be present
        assert "Gaming night" in ctx.system_content
        assert "Stream Status" in ctx.system_content
        # Should mention active viewers or message count
        assert "Messages this session" in ctx.system_content or "viewer" in ctx.system_content.lower()

        await svc.end_session(session_id)

    async def test_empty_stream_context_still_builds(
        self, memory_service: MemoryService,
    ):
        """Empty stream context does not prevent context building."""
        svc = memory_service

        session_id = await svc.start_session()
        # Do NOT update stream context -- it stays at defaults

        messages = [{"role": "user", "content": "Hello"}]
        ctx = await svc.build_context(
            messages=messages,
            system_prompt="Test.",
            max_tokens=4096,
        )

        # Should succeed and return valid context
        assert ctx.system_content
        assert ctx.messages

        await svc.end_session(session_id)


# ---------------------------------------------------------------------------
# 5. Session End Clears Stream Context
# ---------------------------------------------------------------------------


class TestSessionEndClearsStreamContext:
    """Verify end_session() clears stream context state."""

    async def test_stream_context_cleared_after_end(
        self, memory_service: MemoryService,
    ):
        """Stream context message count and state reset after end_session."""
        svc = memory_service

        session_id = await svc.start_session()

        # Populate stream context
        svc.stream_context.current_topic = "Music stream"
        for i in range(5):
            svc.stream_context.update(
                author=f"viewer_{i}",
                content=f"Message {i}",
                msg_type="chat",
            )
        svc.stream_context.update(
            author="donor",
            content="Big donation!",
            msg_type="superchat",
        )

        assert svc.stream_context.message_count >= 6
        assert svc.stream_context.current_topic == "Music stream"
        assert len(svc.stream_context.active_viewers) > 0
        assert len(svc.stream_context.recent_events) > 0

        await svc.end_session(session_id)

        # After end_session, stream context should be fully cleared
        assert svc.stream_context.message_count == 0
        assert svc.stream_context.current_topic == ""
        assert len(svc.stream_context.active_viewers) == 0
        assert len(svc.stream_context.recent_events) == 0

    async def test_episode_stored_before_clear(
        self, memory_service: MemoryService,
    ):
        """Stream episode is persisted before stream context is cleared."""
        svc = memory_service

        # entity_id=None to avoid FK issue on sessions table
        session_id = await svc.start_session()

        svc.stream_context.current_topic = "Cooking"
        svc.stream_context.update(
            author="chef_fan", content="Yummy!", msg_type="chat",
        )
        svc.increment_session_message_count(session_id)

        await svc.end_session(session_id)

        # Stream context cleared
        assert svc.stream_context.message_count == 0

        # But episode should be stored
        store = await svc._ensure_store()
        episodes = await store.get_stream_episodes(limit=10)
        matching = [
            ep for ep in episodes if ep.get("session_id") == session_id
        ]
        assert len(matching) == 1
        assert "Cooking" in matching[0]["summary"] or "Cooking" in (matching[0].get("topics_json") or "")
