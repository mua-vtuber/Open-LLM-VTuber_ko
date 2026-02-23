"""Tests for MemoryService Phase 2 updates.

Tests cover:
- New Phase 2 component initialization (StreamContext, ProceduralMemory, etc.)
- Updated build_context() with stream_context, procedural_rules, episodic_summary
- Updated start_session() with procedural rule loading and stream context clearing
- Updated end_session() with stream episode saving and reflection
- Updated process_turn() with conflict detection
- Backward compatibility with existing functionality
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from open_llm_vtuber.umsa.config import MemoryConfig
from open_llm_vtuber.umsa.conflict_detector import ConflictDetector
from open_llm_vtuber.umsa.context_assembler import AssembledContext
from open_llm_vtuber.umsa.memory_service import MemoryService
from open_llm_vtuber.umsa.models import Message
from open_llm_vtuber.umsa.procedural_memory import ProceduralMemory
from open_llm_vtuber.umsa.reflection import ReflectionEngine
from open_llm_vtuber.umsa.stream_context import StreamContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config():
    """Create a MemoryConfig with extraction disabled for most tests."""
    return MemoryConfig(
        enabled=True,
        extraction={"enabled": False},
    )


@pytest.fixture
def config_extraction_enabled():
    """Create a MemoryConfig with extraction enabled."""
    return MemoryConfig(
        enabled=True,
        extraction={"enabled": True, "batch_size": 2},
    )


@pytest.fixture
def service(config):
    """Create a MemoryService instance."""
    return MemoryService(config=config)


@pytest.fixture
def sample_messages():
    """Create sample conversation messages."""
    return [
        {"role": "user", "content": "Hello there!"},
        {"role": "assistant", "content": "Hi! How can I help you?"},
        {"role": "user", "content": "Tell me about cats."},
    ]


# ---------------------------------------------------------------------------
# Phase 2 Component Initialization
# ---------------------------------------------------------------------------


class TestPhase2Initialization:
    """Tests for eager initialization of Phase 2 components."""

    def test_stream_context_initialized(self, service):
        """StreamContext is eagerly initialized in __init__."""
        assert hasattr(service, "_stream_context")
        assert isinstance(service._stream_context, StreamContext)

    def test_procedural_memory_initialized(self, service):
        """ProceduralMemory is eagerly initialized in __init__."""
        assert hasattr(service, "_procedural_memory")
        assert isinstance(service._procedural_memory, ProceduralMemory)

    def test_reflection_engine_initialized(self, service):
        """ReflectionEngine is eagerly initialized in __init__."""
        assert hasattr(service, "_reflection_engine")
        assert isinstance(service._reflection_engine, ReflectionEngine)

    def test_conflict_detector_initialized(self, service):
        """ConflictDetector is eagerly initialized in __init__."""
        assert hasattr(service, "_conflict_detector")
        assert isinstance(service._conflict_detector, ConflictDetector)

    def test_stream_context_uses_config(self):
        """StreamContext uses values from config.stream_context."""
        cfg = MemoryConfig(
            enabled=True,
            stream_context={"max_events": 50, "topic_change_threshold": 10},
        )
        svc = MemoryService(config=cfg)
        assert svc._stream_context.max_events == 50
        assert svc._stream_context.topic_change_threshold == 10

    def test_default_config_stream_context(self, service):
        """Default stream context config values are used."""
        assert service._stream_context.max_events == 20
        assert service._stream_context.topic_change_threshold == 5


class TestPublicProperties:
    """Tests for public properties exposing Phase 2 components."""

    def test_stream_context_property(self, service):
        """stream_context property returns the StreamContext instance."""
        assert service.stream_context is service._stream_context

    def test_procedural_memory_property(self, service):
        """procedural_memory property returns the ProceduralMemory instance."""
        assert service.procedural_memory is service._procedural_memory


# ---------------------------------------------------------------------------
# build_context() Phase 2 updates
# ---------------------------------------------------------------------------


class TestBuildContextPhase2:
    """Tests for updated build_context() with Phase 2 components."""

    @pytest.mark.asyncio
    async def test_build_context_passes_stream_context(self, service, sample_messages):
        """build_context() passes stream context to assembler."""
        service._stream_context.update("viewer1", "hi", "chat")
        service._stream_context.current_topic = "gaming"

        # Mock the assembler and retriever to avoid real initialization
        mock_assembler = MagicMock()
        mock_assembler.assemble_split.return_value = AssembledContext(
            system_content="test system",
            messages=sample_messages,
        )
        service._context_assembler = mock_assembler
        service._working_memory = MagicMock()
        service._token_counter = MagicMock()

        # Mock _ensure_retriever to avoid real embedding
        service._ensure_retriever = AsyncMock(return_value=MagicMock(
            retrieve=AsyncMock(return_value=[]),
        ))

        await service.build_context(
            messages=sample_messages,
            system_prompt="Test prompt",
        )

        call_kwargs = mock_assembler.assemble_split.call_args[1]
        assert "stream_context" in call_kwargs
        assert call_kwargs["stream_context"] != ""

    @pytest.mark.asyncio
    async def test_build_context_passes_procedural_rules(self, service, sample_messages):
        """build_context() passes procedural rules to assembler."""
        service._procedural_memory.add_rule("greeting", "Always say hello first")

        mock_assembler = MagicMock()
        mock_assembler.assemble_split.return_value = AssembledContext(
            system_content="test system",
            messages=sample_messages,
        )
        service._context_assembler = mock_assembler
        service._working_memory = MagicMock()
        service._token_counter = MagicMock()
        service._ensure_retriever = AsyncMock(return_value=MagicMock(
            retrieve=AsyncMock(return_value=[]),
        ))

        await service.build_context(
            messages=sample_messages,
            system_prompt="Test prompt",
        )

        call_kwargs = mock_assembler.assemble_split.call_args[1]
        assert "procedural_rules" in call_kwargs
        assert "Always say hello first" in call_kwargs["procedural_rules"]

    @pytest.mark.asyncio
    async def test_build_context_passes_episodic_summary(self, service, sample_messages):
        """build_context() queries recent episodes and passes episodic_summary."""
        mock_assembler = MagicMock()
        mock_assembler.assemble_split.return_value = AssembledContext(
            system_content="test system",
            messages=sample_messages,
        )
        service._context_assembler = mock_assembler
        service._working_memory = MagicMock()
        service._token_counter = MagicMock()

        # Mock store to return episodes
        mock_store = AsyncMock()
        mock_store.get_stream_episodes.return_value = [
            {"summary": "User discussed gaming preferences", "topics_json": '["gaming"]'},
            {"summary": "User talked about cooking", "topics_json": '["cooking"]'},
        ]
        service._store = mock_store
        service._store_initialized = True

        service._ensure_retriever = AsyncMock(return_value=MagicMock(
            retrieve=AsyncMock(return_value=[]),
        ))

        await service.build_context(
            messages=sample_messages,
            system_prompt="Test prompt",
        )

        call_kwargs = mock_assembler.assemble_split.call_args[1]
        assert "episodic_summary" in call_kwargs
        assert "gaming preferences" in call_kwargs["episodic_summary"]

    @pytest.mark.asyncio
    async def test_build_context_no_old_params(self, service, sample_messages):
        """build_context() does not pass old session_summary or few_shot_examples."""
        mock_assembler = MagicMock()
        mock_assembler.assemble_split.return_value = AssembledContext(
            system_content="test",
            messages=sample_messages,
        )
        service._context_assembler = mock_assembler
        service._working_memory = MagicMock()
        service._token_counter = MagicMock()
        service._ensure_retriever = AsyncMock(return_value=MagicMock(
            retrieve=AsyncMock(return_value=[]),
        ))

        await service.build_context(
            messages=sample_messages,
            system_prompt="Test",
        )

        call_kwargs = mock_assembler.assemble_split.call_args[1]
        assert "session_summary" not in call_kwargs
        assert "few_shot_examples" not in call_kwargs

    @pytest.mark.asyncio
    async def test_build_context_empty_stream_context(self, service, sample_messages):
        """build_context() handles empty stream context gracefully."""
        # StreamContext with no updates produces minimal output
        mock_assembler = MagicMock()
        mock_assembler.assemble_split.return_value = AssembledContext(
            system_content="test",
            messages=sample_messages,
        )
        service._context_assembler = mock_assembler
        service._working_memory = MagicMock()
        service._token_counter = MagicMock()
        service._ensure_retriever = AsyncMock(return_value=MagicMock(
            retrieve=AsyncMock(return_value=[]),
        ))

        await service.build_context(
            messages=sample_messages,
            system_prompt="Test",
        )

        # Should succeed without error
        call_kwargs = mock_assembler.assemble_split.call_args[1]
        assert "stream_context" in call_kwargs

    @pytest.mark.asyncio
    async def test_build_context_episodic_summary_error_handled(
        self, service, sample_messages
    ):
        """build_context() handles errors when loading episodic summary."""
        mock_assembler = MagicMock()
        mock_assembler.assemble_split.return_value = AssembledContext(
            system_content="test",
            messages=sample_messages,
        )
        service._context_assembler = mock_assembler
        service._working_memory = MagicMock()
        service._token_counter = MagicMock()

        # Mock store that raises an error
        mock_store = AsyncMock()
        mock_store.get_stream_episodes.side_effect = Exception("DB error")
        service._store = mock_store
        service._store_initialized = True

        service._ensure_retriever = AsyncMock(return_value=MagicMock(
            retrieve=AsyncMock(return_value=[]),
        ))

        # Should not raise, should use empty episodic summary
        result = await service.build_context(
            messages=sample_messages,
            system_prompt="Test",
        )
        assert result is not None
        call_kwargs = mock_assembler.assemble_split.call_args[1]
        assert call_kwargs["episodic_summary"] == ""


# ---------------------------------------------------------------------------
# start_session() Phase 2 updates
# ---------------------------------------------------------------------------


class TestStartSessionPhase2:
    """Tests for updated start_session() with Phase 2 components."""

    @pytest.mark.asyncio
    async def test_start_session_loads_procedural_rules(self, service):
        """start_session() loads procedural rules from SQLite."""
        mock_store = AsyncMock()
        mock_store.get_active_procedural_rules.return_value = [
            {"id": "r1", "rule_type": "greeting", "content": "Say hello", "confidence": 0.8},
            {"id": "r2", "rule_type": "tone", "content": "Be friendly", "confidence": 0.7},
        ]
        mock_store.insert_session = AsyncMock()
        service._store = mock_store
        service._store_initialized = True

        session_id = await service.start_session(entity_id="user1")

        assert session_id.startswith("session_")
        mock_store.get_active_procedural_rules.assert_awaited_once()
        assert len(service._procedural_memory.rules) == 2
        assert service._procedural_memory.rules[0]["content"] == "Say hello"

    @pytest.mark.asyncio
    async def test_start_session_clears_stream_context(self, service):
        """start_session() clears the stream context."""
        service._stream_context.update("viewer1", "hello", "chat")
        assert service._stream_context.message_count > 0

        mock_store = AsyncMock()
        mock_store.get_active_procedural_rules.return_value = []
        mock_store.insert_session = AsyncMock()
        service._store = mock_store
        service._store_initialized = True

        await service.start_session()

        assert service._stream_context.message_count == 0

    @pytest.mark.asyncio
    async def test_start_session_procedural_load_error_handled(self, service):
        """start_session() handles errors when loading procedural rules."""
        mock_store = AsyncMock()
        mock_store.get_active_procedural_rules.side_effect = Exception("DB error")
        mock_store.insert_session = AsyncMock()
        service._store = mock_store
        service._store_initialized = True

        # Should not raise
        session_id = await service.start_session()
        assert session_id.startswith("session_")

    @pytest.mark.asyncio
    async def test_start_session_still_creates_session_record(self, service):
        """start_session() still creates session in SQLite (backward compatible)."""
        mock_store = AsyncMock()
        mock_store.get_active_procedural_rules.return_value = []
        mock_store.insert_session = AsyncMock()
        service._store = mock_store
        service._store_initialized = True

        session_id = await service.start_session(entity_id="user1", platform="youtube")

        mock_store.insert_session.assert_awaited_once()
        call_args = mock_store.insert_session.call_args[0][0]
        assert call_args["session_id"] == session_id
        assert call_args["entity_id"] == "user1"
        assert call_args["platform"] == "youtube"


# ---------------------------------------------------------------------------
# end_session() Phase 2 updates
# ---------------------------------------------------------------------------


class TestEndSessionPhase2:
    """Tests for updated end_session() with Phase 2 components."""

    @pytest.mark.asyncio
    async def test_end_session_saves_stream_episode(self, service):
        """end_session() saves stream context as an episode."""
        # Set up active session
        session_id = "session_test123"
        service._active_sessions[session_id] = {
            "entity_id": "user1",
            "platform": "youtube",
            "started_at": "2024-01-01T00:00:00",
            "message_count": 5,
        }
        service._stream_context.update("viewer1", "hello", "chat")
        service._stream_context.message_count = 5

        mock_store = AsyncMock()
        mock_store.end_session = AsyncMock()
        mock_store.insert_knowledge_node = AsyncMock()
        mock_store.insert_stream_episode = AsyncMock(return_value="ep_123")
        mock_store.insert_consolidation_log = AsyncMock()
        mock_store.touch_entity = AsyncMock()
        mock_store.get_knowledge_nodes = AsyncMock(return_value=[])
        service._store = mock_store
        service._store_initialized = True
        service.config.consolidation.enabled = False

        await service.end_session(session_id)

        mock_store.insert_stream_episode.assert_awaited_once()
        ep_data = mock_store.insert_stream_episode.call_args[0][0]
        assert "summary" in ep_data
        assert ep_data["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_end_session_runs_reflection(self, service):
        """end_session() runs reflection engine on recent nodes."""
        session_id = "session_reflect"
        service._active_sessions[session_id] = {
            "entity_id": "user1",
            "platform": "direct",
            "started_at": "2024-01-01T00:00:00",
            "message_count": 10,
        }

        # Return enough nodes for reflection (>= min_group_size)
        mock_store = AsyncMock()
        mock_store.end_session = AsyncMock()
        mock_store.insert_knowledge_node = AsyncMock()
        mock_store.insert_stream_episode = AsyncMock(return_value="ep_1")
        mock_store.insert_consolidation_log = AsyncMock()
        mock_store.touch_entity = AsyncMock()
        mock_store.get_knowledge_nodes = AsyncMock(return_value=[
            {"node_id": "n1", "entity_id": "user1", "content": "likes cats",
             "node_type": "preference", "importance": 0.5},
            {"node_id": "n2", "entity_id": "user1", "content": "has a cat",
             "node_type": "atomic_fact", "importance": 0.6},
            {"node_id": "n3", "entity_id": "user1", "content": "cat named Miso",
             "node_type": "atomic_fact", "importance": 0.7},
        ])
        mock_store.insert_procedural_rule = AsyncMock()
        service._store = mock_store
        service._store_initialized = True
        service.config.consolidation.enabled = False

        # Use a spy on reflect_sync to verify it's called
        original_reflect = service._reflection_engine.reflect_sync
        reflect_calls = []

        def spy_reflect(nodes):
            reflect_calls.append(nodes)
            return original_reflect(nodes)

        service._reflection_engine.reflect_sync = spy_reflect

        await service.end_session(session_id)

        assert len(reflect_calls) == 1
        assert len(reflect_calls[0]) == 3

    @pytest.mark.asyncio
    async def test_end_session_saves_reflection_insights(self, service):
        """end_session() saves insights from reflection as knowledge nodes."""
        session_id = "session_insight"
        service._active_sessions[session_id] = {
            "entity_id": "user1",
            "platform": "direct",
            "started_at": "2024-01-01T00:00:00",
            "message_count": 5,
        }

        mock_store = AsyncMock()
        mock_store.end_session = AsyncMock()
        mock_store.insert_knowledge_node = AsyncMock()
        mock_store.insert_stream_episode = AsyncMock(return_value="ep_1")
        mock_store.insert_consolidation_log = AsyncMock()
        mock_store.touch_entity = AsyncMock()
        mock_store.get_knowledge_nodes = AsyncMock(return_value=[
            {"node_id": "n1", "entity_id": "user1", "content": "pref1",
             "node_type": "preference", "importance": 0.5},
            {"node_id": "n2", "entity_id": "user1", "content": "pref2",
             "node_type": "preference", "importance": 0.6},
            {"node_id": "n3", "entity_id": "user1", "content": "pref3",
             "node_type": "preference", "importance": 0.7},
        ])
        mock_store.insert_procedural_rule = AsyncMock()
        service._store = mock_store
        service._store_initialized = True
        service.config.consolidation.enabled = False

        # Mock reflection to return an insight
        service._reflection_engine.reflect_sync = MagicMock(return_value=[
            {
                "id": "insight_1",
                "entity_id": "user1",
                "memory_type": "meta_summary",
                "content": "User has many preferences",
                "importance": 0.8,
                "source_node_ids": ["n1", "n2", "n3"],
            }
        ])

        await service.end_session(session_id)

        # Verify insight was persisted as a knowledge node
        insert_calls = mock_store.insert_knowledge_node.call_args_list
        insight_calls = [
            c for c in insert_calls
            if c[0][0].get("node_type") == "meta_summary"
        ]
        assert len(insight_calls) == 1
        assert insight_calls[0][0][0]["content"] == "User has many preferences"

    @pytest.mark.asyncio
    async def test_end_session_clears_stream_context(self, service):
        """end_session() clears stream context after saving."""
        session_id = "session_clear"
        service._active_sessions[session_id] = {
            "entity_id": None,
            "platform": "direct",
            "started_at": "2024-01-01T00:00:00",
            "message_count": 3,
        }
        service._stream_context.update("user", "hello", "chat")
        assert service._stream_context.message_count > 0

        mock_store = AsyncMock()
        mock_store.end_session = AsyncMock()
        mock_store.insert_knowledge_node = AsyncMock()
        mock_store.insert_stream_episode = AsyncMock(return_value="ep_1")
        mock_store.insert_consolidation_log = AsyncMock()
        mock_store.get_knowledge_nodes = AsyncMock(return_value=[])
        service._store = mock_store
        service._store_initialized = True
        service.config.consolidation.enabled = False

        await service.end_session(session_id)

        assert service._stream_context.message_count == 0

    @pytest.mark.asyncio
    async def test_end_session_stream_episode_error_handled(self, service):
        """end_session() handles errors during stream episode save."""
        session_id = "session_err"
        service._active_sessions[session_id] = {
            "entity_id": None,
            "platform": "direct",
            "started_at": "2024-01-01T00:00:00",
            "message_count": 2,
        }

        mock_store = AsyncMock()
        mock_store.end_session = AsyncMock()
        mock_store.insert_knowledge_node = AsyncMock()
        mock_store.insert_stream_episode = AsyncMock(
            side_effect=Exception("DB write error")
        )
        mock_store.insert_consolidation_log = AsyncMock()
        mock_store.get_knowledge_nodes = AsyncMock(return_value=[])
        service._store = mock_store
        service._store_initialized = True
        service.config.consolidation.enabled = False

        # Should not raise
        await service.end_session(session_id)

    @pytest.mark.asyncio
    async def test_end_session_unknown_session_returns_early(self, service):
        """end_session() returns early for unknown session IDs."""
        await service.end_session("nonexistent_session")
        # No error, no crash


# ---------------------------------------------------------------------------
# process_turn() Phase 2 updates
# ---------------------------------------------------------------------------


class TestProcessTurnPhase2:
    """Tests for updated process_turn() with conflict detection."""

    @pytest.mark.asyncio
    async def test_process_turn_updates_stream_context(self, service):
        """process_turn() updates the stream context with user message."""
        user_msg = Message(role="user", content="I love cats!", name="viewer1")
        asst_msg = Message(role="assistant", content="Cats are great!")

        # Even without extractor, stream context should be updated
        await service.process_turn(user_msg, asst_msg)

        assert service._stream_context.message_count >= 1

    @pytest.mark.asyncio
    async def test_process_turn_still_works_without_extractor(self, service):
        """process_turn() works when extractor is not available."""
        user_msg = Message(role="user", content="Hello")
        asst_msg = Message(role="assistant", content="Hi!")

        # Should not raise
        await service.process_turn(user_msg, asst_msg)


# ---------------------------------------------------------------------------
# set_llm() with Phase 2 updates
# ---------------------------------------------------------------------------


class TestSetLlmPhase2:
    """Tests for set_llm() updating reflection engine."""

    def test_set_llm_updates_reflection_engine(self):
        """set_llm() also sets the LLM on the reflection engine."""
        cfg = MemoryConfig(enabled=True, extraction={"enabled": True})
        svc = MemoryService(config=cfg)
        mock_llm = MagicMock()

        svc.set_llm(mock_llm)

        assert svc._reflection_engine._llm is mock_llm


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Tests ensuring existing functionality is preserved."""

    def test_existing_attributes_still_present(self, service):
        """All Phase 1 attributes are still present."""
        assert hasattr(service, "config")
        assert hasattr(service, "_working_memory")
        assert hasattr(service, "_context_assembler")
        assert hasattr(service, "_token_counter")
        assert hasattr(service, "_store")
        assert hasattr(service, "_store_initialized")
        assert hasattr(service, "_extractor")
        assert hasattr(service, "_embedding_service")
        assert hasattr(service, "_retriever")
        assert hasattr(service, "_evolver")
        assert hasattr(service, "_active_sessions")

    def test_increment_session_message_count(self, service):
        """increment_session_message_count still works."""
        service._active_sessions["test_session"] = {"message_count": 0}
        service.increment_session_message_count("test_session")
        assert service._active_sessions["test_session"]["message_count"] == 1

    @pytest.mark.asyncio
    async def test_search_memories_interface(self, service):
        """search_memories still has the correct interface."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve = AsyncMock(return_value=[])
        service._retriever = mock_retriever
        service._embedding_service = MagicMock()

        # Mock _ensure_retriever
        service._ensure_retriever = AsyncMock(return_value=mock_retriever)

        result = await service.search_memories("test query")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_close_still_works(self, service):
        """close() still works correctly."""
        mock_store = AsyncMock()
        service._store = mock_store
        service._store_initialized = True

        await service.close()

        mock_store.close.assert_awaited_once()
        assert service._store_initialized is False

    def test_default_config_creates_service(self):
        """MemoryService can be created with default config."""
        svc = MemoryService()
        assert svc.config is not None
        assert isinstance(svc._stream_context, StreamContext)
        assert isinstance(svc._procedural_memory, ProceduralMemory)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_build_context_with_no_store_episodes(self, service, sample_messages):
        """build_context() works when store is not yet initialized (no episodes)."""
        mock_assembler = MagicMock()
        mock_assembler.assemble_split.return_value = AssembledContext(
            system_content="test",
            messages=sample_messages,
        )
        service._context_assembler = mock_assembler
        service._working_memory = MagicMock()
        service._token_counter = MagicMock()
        service._ensure_retriever = AsyncMock(return_value=MagicMock(
            retrieve=AsyncMock(return_value=[]),
        ))

        # Store not initialized -> _store is None
        result = await service.build_context(
            messages=sample_messages,
            system_prompt="Test",
        )
        assert result is not None
        call_kwargs = mock_assembler.assemble_split.call_args[1]
        assert call_kwargs["episodic_summary"] == ""

    @pytest.mark.asyncio
    async def test_end_session_with_zero_messages(self, service):
        """end_session() handles sessions with zero messages."""
        session_id = "session_zero"
        service._active_sessions[session_id] = {
            "entity_id": None,
            "platform": "direct",
            "started_at": "2024-01-01T00:00:00",
            "message_count": 0,
        }

        mock_store = AsyncMock()
        mock_store.end_session = AsyncMock()
        mock_store.insert_knowledge_node = AsyncMock()
        mock_store.insert_stream_episode = AsyncMock(return_value="ep_1")
        mock_store.insert_consolidation_log = AsyncMock()
        mock_store.get_knowledge_nodes = AsyncMock(return_value=[])
        service._store = mock_store
        service._store_initialized = True
        service.config.consolidation.enabled = False

        # Should not raise
        await service.end_session(session_id)

    @pytest.mark.asyncio
    async def test_process_turn_with_string_content(self, service):
        """process_turn() handles Message objects correctly."""
        user_msg = Message(role="user", content="Test message")
        asst_msg = Message(role="assistant", content="Response")

        # Should work without errors
        await service.process_turn(user_msg, asst_msg)
