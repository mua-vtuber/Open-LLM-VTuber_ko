from typing import Union, List, Dict, Any, Optional
import asyncio
import json
from loguru import logger
import numpy as np

from .conversation_utils import (
    create_batch_input,
    process_agent_output,
    send_conversation_start_signals,
    process_user_input,
    finalize_conversation_turn,
    cleanup_conversation,
    EMOJI_LIST,
)
from .types import WebSocketSend
from .tts_manager import TTSTaskManager
from ..chat_history_manager import store_message
from ..service_context import ServiceContext

# Import necessary types from agent outputs
from ..agent.output_types import SentenceOutput, AudioOutput


async def process_single_conversation(
    context: ServiceContext,
    websocket_send: WebSocketSend,
    client_uid: str,
    user_input: Union[str, np.ndarray],
    images: Optional[List[Dict[str, Any]]] = None,
    session_emoji: str = np.random.choice(EMOJI_LIST),
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Process a single-user conversation turn

    Args:
        context: Service context containing all configurations and engines
        websocket_send: WebSocket send function
        client_uid: Client unique identifier
        user_input: Text or audio input from user
        images: Optional list of image data
        session_emoji: Emoji identifier for the conversation
        metadata: Optional metadata for special processing flags

    Returns:
        str: Complete response text
    """
    # Create TTSTaskManager for this conversation
    tts_manager = TTSTaskManager()
    full_response = ""  # Initialize full_response here

    try:
        # Start memory session if agent supports it
        _memory_session_id = None
        if hasattr(context.agent_engine, "start_session"):
            try:
                _memory_session_id = await context.agent_engine.start_session(
                    platform="direct",
                )
            except Exception as e:
                logger.warning(f"Failed to start memory session: {e}")

        # Send initial signals
        await send_conversation_start_signals(websocket_send)
        logger.info(f"New Conversation Chain {session_emoji} started!")

        # Process user input
        try:
            input_text = await process_user_input(
                user_input, context.asr_engine, websocket_send
            )
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            await websocket_send(
                json.dumps({
                    "type": "error",
                    "code": "INPUT_PROCESSING_ERROR",
                    "message": f"Failed to process input: {str(e)}"
                })
            )
            raise

        # Create batch input
        batch_input = create_batch_input(
            input_text=input_text,
            images=images,
            from_name=context.character_config.human_name,
            metadata=metadata,
        )

        # Store user message (check if we should skip storing to history)
        skip_history = metadata and metadata.get("skip_history", False)
        if context.history_uid and not skip_history:
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="human",
                content=input_text,
                name=context.character_config.human_name,
            )

        if skip_history:
            logger.debug("Skipping storing user input to history (proactive speak)")

        logger.info(f"User input: {input_text}")
        if images:
            logger.info(f"With {len(images)} images")

        try:
            # agent.chat yields Union[SentenceOutput, Dict[str, Any]]
            agent_output_stream = context.agent_engine.chat(batch_input)

            async for output_item in agent_output_stream:
                if (
                    isinstance(output_item, dict)
                    and output_item.get("type") == "tool_call_status"
                ):
                    # Handle tool status event: send WebSocket message
                    output_item["name"] = context.character_config.character_name
                    logger.debug(f"Sending tool status update: {output_item}")
                    await websocket_send(json.dumps(output_item))
                    continue

                full_response = await process_agent_output(
                    output_item=output_item,
                    tts_manager=tts_manager,
                    websocket_send=websocket_send,
                    full_response=full_response,
                    context=context,
                )

        except asyncio.TimeoutError:
            logger.error("Agent response timed out")
            await websocket_send(
                json.dumps({
                    "type": "error",
                    "code": "TIMEOUT",
                    "message": "AI response timed out"
                })
            )
            raise
        except Exception as e:
            logger.exception(f"Error processing agent response stream: {e}")
            await websocket_send(
                json.dumps({
                    "type": "error",
                    "code": "GENERATION_ERROR",
                    "message": f"Error generating response: {str(e)}"
                })
            )
            # Don't re-raise immediately to allow cleanup, but log critical error
            raise

        # Wait for all TTS tasks to complete
        await tts_manager.wait_for_all_tasks()

        # Finalize conversation
        await finalize_conversation_turn(
            full_response=full_response,
            context=context,
            skip_history=skip_history,
            websocket_send=websocket_send,
        )
        logger.info(f"AI response: {full_response}")

        return full_response  # Return accumulated full_response

    except asyncio.CancelledError:
        logger.info(f"🛑 Conversation {session_emoji} cancelled because interrupted.")
        await websocket_send(json.dumps({"type": "control", "text": "conversation-cancelled"}))
        raise
    except Exception as e:
        logger.error(f"Unexpected error in conversation chain: {e}")
        # Only send if not already sent by inner blocks
        try:
            await websocket_send(
                json.dumps({"type": "error", "code": "INTERNAL_ERROR", "message": f"Internal error: {str(e)}"})
            )
        except Exception:
            pass # Connection might be closed
        raise
    finally:
        # End memory session if one was started
        if _memory_session_id and hasattr(context.agent_engine, "end_session"):
            try:
                await context.agent_engine.end_session()
            except Exception as e:
                logger.warning(f"Failed to end memory session: {e}")

        # Cleanup
        await cleanup_conversation(tts_manager)
        logger.info(f"Conversation {session_emoji} finished/cleaned up.")