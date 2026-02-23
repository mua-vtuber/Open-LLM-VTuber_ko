import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from open_llm_vtuber.conversations.single_conversation import (
    process_single_conversation,
)
from open_llm_vtuber.service_context import ServiceContext


@pytest.fixture
def mock_context():
    context = MagicMock(spec=ServiceContext)
    context.character_config = MagicMock()
    context.character_config.human_name = "User"
    context.character_config.character_name = "AI"
    context.character_config.conf_uid = "conf_123"
    context.history_uid = "hist_123"

    context.asr_engine = AsyncMock()
    context.agent_engine = MagicMock()
    # Ensure hasattr checks for memory session return False
    del context.agent_engine.start_session
    del context.agent_engine.end_session

    return context


@pytest.fixture
def mock_websocket_send():
    return AsyncMock()


@pytest.mark.asyncio
async def test_process_single_conversation_success(mock_context, mock_websocket_send):
    """Test successful conversation flow."""
    client_uid = "client_123"
    user_input = "Hello"

    with (
        patch(
            "open_llm_vtuber.conversations.single_conversation.process_user_input",
            new_callable=AsyncMock,
        ) as mock_process_input,
        patch("open_llm_vtuber.conversations.single_conversation.create_batch_input"),
        patch(
            "open_llm_vtuber.conversations.single_conversation.store_message"
        ) as mock_store_message,
        patch(
            "open_llm_vtuber.conversations.single_conversation.send_conversation_start_signals",
            new_callable=AsyncMock,
        ) as mock_send_signals,
        patch(
            "open_llm_vtuber.conversations.single_conversation.finalize_conversation_turn",
            new_callable=AsyncMock,
        ),
        patch(
            "open_llm_vtuber.conversations.single_conversation.cleanup_conversation",
            new_callable=AsyncMock,
        ) as mock_cleanup,
    ):
        mock_process_input.return_value = "Hello"

        # Mock Agent Chat stream as an async generator
        async def mock_chat_stream(*args, **kwargs):
            yield "Hello "
            yield "World!"

        mock_context.agent_engine.chat = MagicMock(return_value=mock_chat_stream())

        # Mock process_agent_output to accumulate full_response
        with patch(
            "open_llm_vtuber.conversations.single_conversation.process_agent_output",
            new_callable=AsyncMock,
        ) as mock_process_output:
            call_count = 0

            async def accumulate_response(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return "Hello "
                return "Hello World!"

            mock_process_output.side_effect = accumulate_response

            # Mock TTSTaskManager
            with patch(
                "open_llm_vtuber.conversations.single_conversation.TTSTaskManager"
            ) as mock_tts_cls:
                mock_tts = MagicMock()
                mock_tts.wait_for_all_tasks = AsyncMock()
                mock_tts.clear = MagicMock()
                mock_tts_cls.return_value = mock_tts

                result = await process_single_conversation(
                    context=mock_context,
                    websocket_send=mock_websocket_send,
                    client_uid=client_uid,
                    user_input=user_input,
                    session_emoji="test",
                )

        assert result == "Hello World!"
        mock_send_signals.assert_called_once()
        mock_process_input.assert_called_once()
        mock_store_message.assert_called()
        mock_cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_process_single_conversation_interrupted(
    mock_context, mock_websocket_send
):
    """Test conversation interruption handling."""
    client_uid = "client_123"
    user_input = "Hello"

    with (
        patch(
            "open_llm_vtuber.conversations.single_conversation.send_conversation_start_signals",
            side_effect=asyncio.CancelledError("Interrupted"),
        ),
        patch(
            "open_llm_vtuber.conversations.single_conversation.cleanup_conversation",
            new_callable=AsyncMock,
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await process_single_conversation(
                context=mock_context,
                websocket_send=mock_websocket_send,
                client_uid=client_uid,
                user_input=user_input,
                session_emoji="test",
            )


@pytest.mark.asyncio
async def test_process_single_conversation_error(mock_context, mock_websocket_send):
    """Test error handling during conversation."""
    client_uid = "client_123"
    user_input = "Hello"

    with (
        patch(
            "open_llm_vtuber.conversations.single_conversation.process_user_input",
            side_effect=Exception("Processing failed"),
        ),
        patch(
            "open_llm_vtuber.conversations.single_conversation.send_conversation_start_signals",
            new_callable=AsyncMock,
        ),
        patch(
            "open_llm_vtuber.conversations.single_conversation.cleanup_conversation",
            new_callable=AsyncMock,
        ),
    ):
        with pytest.raises(Exception):
            await process_single_conversation(
                context=mock_context,
                websocket_send=mock_websocket_send,
                client_uid=client_uid,
                user_input=user_input,
                session_emoji="test",
            )

        mock_websocket_send.assert_called()
        call_args = mock_websocket_send.call_args[0][0]
        assert "error" in call_args
        assert "Processing failed" in call_args
