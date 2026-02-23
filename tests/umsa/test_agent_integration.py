"""Tests for BasicMemoryAgent.update_stream_context() integration.

Verifies that the agent correctly delegates stream context updates to
MemoryService.stream_context.update(), and is a no-op when the memory
service is not configured.
"""

from __future__ import annotations

from unittest.mock import MagicMock


from open_llm_vtuber.umsa.config import MemoryConfig


def _make_agent(memory_config: MemoryConfig | None = None):
    """Create a BasicMemoryAgent with mocked LLM and Live2D dependencies.

    We patch the heavy constructor side-effects (LLM binding, tool formatting)
    so the test focuses purely on stream-context wiring.
    """
    from open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent

    mock_llm = MagicMock()
    # chat_completion must be an async generator for the factory
    mock_llm.chat_completion = MagicMock()

    mock_live2d = MagicMock()
    mock_live2d.get_expression_list.return_value = []

    agent = BasicMemoryAgent(
        llm=mock_llm,
        system="You are a test assistant.",
        live2d_model=mock_live2d,
        memory_config=memory_config,
    )
    return agent


class TestUpdateStreamContext:
    """Tests for BasicMemoryAgent.update_stream_context()."""

    def test_delegates_to_stream_context_update(self):
        """update_stream_context() calls MemoryService.stream_context.update()."""
        config = MemoryConfig(enabled=True, extraction={"enabled": False})
        agent = _make_agent(memory_config=config)

        # Spy on the underlying StreamContext.update
        assert agent._memory_service is not None
        sc = agent._memory_service.stream_context
        original_update = sc.update
        calls = []

        def spy_update(**kwargs):
            calls.append(kwargs)
            return original_update(**kwargs)

        sc.update = spy_update

        agent.update_stream_context(
            author="viewer1",
            content="hello everyone!",
            msg_type="chat",
            metadata={"platform": "youtube"},
        )

        assert len(calls) == 1
        assert calls[0]["author"] == "viewer1"
        assert calls[0]["content"] == "hello everyone!"
        assert calls[0]["msg_type"] == "chat"
        assert calls[0]["metadata"] == {"platform": "youtube"}

    def test_noop_when_memory_service_is_none(self):
        """update_stream_context() is a no-op when UMSA is disabled."""
        agent = _make_agent(memory_config=None)

        assert agent._memory_service is None

        # Should not raise
        agent.update_stream_context(
            author="viewer1",
            content="hello",
        )

    def test_message_count_increments(self):
        """Stream context message_count increments after update."""
        config = MemoryConfig(enabled=True, extraction={"enabled": False})
        agent = _make_agent(memory_config=config)

        sc = agent._memory_service.stream_context
        assert sc.message_count == 0

        agent.update_stream_context(author="viewer1", content="first message")
        assert sc.message_count == 1

        agent.update_stream_context(author="viewer2", content="second message")
        assert sc.message_count == 2

        agent.update_stream_context(author="viewer1", content="third message")
        assert sc.message_count == 3

    def test_default_msg_type_is_chat(self):
        """msg_type defaults to 'chat' when not provided."""
        config = MemoryConfig(enabled=True, extraction={"enabled": False})
        agent = _make_agent(memory_config=config)

        sc = agent._memory_service.stream_context
        original_update = sc.update
        captured_kwargs = []

        def spy(**kwargs):
            captured_kwargs.append(kwargs)
            return original_update(**kwargs)

        sc.update = spy

        agent.update_stream_context(author="viewer1", content="hi")

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["msg_type"] == "chat"

    def test_metadata_defaults_to_none(self):
        """metadata defaults to None when not provided."""
        config = MemoryConfig(enabled=True, extraction={"enabled": False})
        agent = _make_agent(memory_config=config)

        sc = agent._memory_service.stream_context
        original_update = sc.update
        captured_kwargs = []

        def spy(**kwargs):
            captured_kwargs.append(kwargs)
            return original_update(**kwargs)

        sc.update = spy

        agent.update_stream_context(author="viewer1", content="hi")

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["metadata"] is None

    def test_special_event_types_tracked(self):
        """Superchat/subscription events are tracked as stream events."""
        config = MemoryConfig(enabled=True, extraction={"enabled": False})
        agent = _make_agent(memory_config=config)

        sc = agent._memory_service.stream_context
        assert len(sc.recent_events) == 0

        agent.update_stream_context(
            author="generous_viewer",
            content="Great stream!",
            msg_type="superchat",
            metadata={"amount": 50},
        )

        assert len(sc.recent_events) == 1
        assert sc.recent_events[0].event_type == "superchat"
        assert sc.recent_events[0].author == "generous_viewer"

    def test_active_viewers_updated(self):
        """Active viewers dict is updated after calls."""
        config = MemoryConfig(enabled=True, extraction={"enabled": False})
        agent = _make_agent(memory_config=config)

        sc = agent._memory_service.stream_context
        assert len(sc.active_viewers) == 0

        agent.update_stream_context(author="viewer_a", content="hi")
        agent.update_stream_context(author="viewer_b", content="hello")

        assert "viewer_a" in sc.active_viewers
        assert "viewer_b" in sc.active_viewers
