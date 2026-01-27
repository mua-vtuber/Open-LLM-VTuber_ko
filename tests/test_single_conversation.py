import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import json
from open_llm_vtuber.conversations.single_conversation import process_single_conversation
from open_llm_vtuber.service_context import ServiceContext
from open_llm_vtuber.input_types import TextSource

@pytest.fixture
def mock_context():
    context = MagicMock(spec=ServiceContext)
    context.character_config = MagicMock()
    context.character_config.human_name = "User"
    context.character_config.character_name = "AI"
    context.character_config.conf_uid = "conf_123"
    context.history_uid = "hist_123"
    
    context.asr_engine = AsyncMock()
    context.agent_engine = AsyncMock()
    
    return context

@pytest.fixture
def mock_websocket_send():
    return AsyncMock()

@pytest.mark.asyncio
async def test_process_single_conversation_success(mock_context, mock_websocket_send):
    """Test successful conversation flow."""
    # Setup mocks
    client_uid = "client_123"
    user_input = "Hello"
    
    # Mock ASR response (implicit in process_user_input, but mocking the utility function is easier)
    with patch("open_llm_vtuber.conversations.single_conversation.process_user_input", new_callable=AsyncMock) as mock_process_input, \
         patch("open_llm_vtuber.conversations.single_conversation.create_batch_input") as mock_create_batch, \
         patch("open_llm_vtuber.conversations.single_conversation.store_message") as mock_store_message, \
         patch("open_llm_vtuber.conversations.single_conversation.send_conversation_start_signals", new_callable=AsyncMock) as mock_send_signals, \
         patch("open_llm_vtuber.conversations.single_conversation.finalize_conversation_turn", new_callable=AsyncMock) as mock_finalize, \
         patch("open_llm_vtuber.conversations.single_conversation.cleanup_conversation", new_callable=AsyncMock) as mock_cleanup:
        
        mock_process_input.return_value = "Hello"
        
        # Mock Agent Chat stream
        async def async_generator():
            yield "Hello "
            yield "World!"
        
        mock_context.agent_engine.chat.return_value = async_generator()
        
        # Execute
        result = await process_single_conversation(
            context=mock_context,
            websocket_send=mock_websocket_send,
            client_uid=client_uid,
            user_input=user_input
        )
        
        # Verify
        assert result == "Hello World!"
        mock_send_signals.assert_called_once()
        mock_process_input.assert_called_once()
        mock_store_message.assert_called() # Should store user message
        mock_context.agent_engine.chat.assert_called_once()
        mock_cleanup.assert_called_once()

@pytest.mark.asyncio
async def test_process_single_conversation_interrupted(mock_context, mock_websocket_send):
    """Test conversation interruption handling."""
    client_uid = "client_123"
    user_input = "Hello"
    
    with patch("open_llm_vtuber.conversations.single_conversation.send_conversation_start_signals", side_effect=asyncio.CancelledError("Interrupted")):
        
        with pytest.raises(asyncio.CancelledError):
            await process_single_conversation(
                context=mock_context,
                websocket_send=mock_websocket_send,
                client_uid=client_uid,
                user_input=user_input
            )

@pytest.mark.asyncio
async def test_process_single_conversation_error(mock_context, mock_websocket_send):
    """Test error handling during conversation."""
    client_uid = "client_123"
    user_input = "Hello"
    
    with patch("open_llm_vtuber.conversations.single_conversation.process_user_input", side_effect=Exception("Processing failed")):
        
        with pytest.raises(Exception):
            await process_single_conversation(
                context=mock_context,
                websocket_send=mock_websocket_send,
                client_uid=client_uid,
                user_input=user_input
            )
        
        # Verify error message sent to websocket
        mock_websocket_send.assert_called()
        call_args = mock_websocket_send.call_args[0][0]
        assert "error" in call_args
        assert "Processing failed" in call_args
