"""Memory management handler for WebSocket communication."""

from typing import Dict
from fastapi import WebSocket
import json
from loguru import logger

from ..service_context import ServiceContext


# Error codes for i18n support - frontend translates these
class MemoryErrorCode:
    """Error codes for memory operations (translated in frontend)."""

    CLIENT_CONTEXT_NOT_FOUND = "ERROR_CLIENT_CONTEXT_NOT_FOUND"
    MEMORY_NOT_SUPPORTED = "ERROR_MEMORY_NOT_SUPPORTED"
    MEMORY_ID_REQUIRED = "ERROR_MEMORY_ID_REQUIRED"
    FETCH_MEMORIES_FAILED = "ERROR_FETCH_MEMORIES_FAILED"
    DELETE_MEMORY_FAILED = "ERROR_DELETE_MEMORY_FAILED"
    DELETE_ALL_MEMORIES_FAILED = "ERROR_DELETE_ALL_MEMORIES_FAILED"


class MemoryHandler:
    """Handles memory-related WebSocket operations."""

    def __init__(self, client_contexts: Dict[str, ServiceContext]):
        self.client_contexts = client_contexts

    async def handle_get_memories(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        Retrieve all memories for the user.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: Data from client (unused)

        Returns:
            Sends memories_list or error message via WebSocket
        """
        context = self.client_contexts.get(client_uid)
        if not context:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "error_code": MemoryErrorCode.CLIENT_CONTEXT_NOT_FOUND,
                    }
                )
            )
            return

        if hasattr(context.agent_engine, "get_all_memories"):
            try:
                memories = context.agent_engine.get_all_memories()
                await websocket.send_text(
                    json.dumps({"type": "memories_list", "memories": memories})
                )
            except Exception as e:
                logger.error(f"Failed to fetch memories: {e}")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "error_code": MemoryErrorCode.FETCH_MEMORIES_FAILED,
                            "details": str(e),
                        }
                    )
                )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "error_code": MemoryErrorCode.MEMORY_NOT_SUPPORTED,
                    }
                )
            )

    async def handle_delete_memory(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        Delete a specific memory.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: {"memory_id": "mem_xxx"} format data

        Returns:
            Sends memory_deleted or error message via WebSocket
        """
        memory_id = data.get("memory_id")

        if not memory_id:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "error_code": MemoryErrorCode.MEMORY_ID_REQUIRED,
                    }
                )
            )
            return

        context = self.client_contexts.get(client_uid)
        if not context:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "error_code": MemoryErrorCode.CLIENT_CONTEXT_NOT_FOUND,
                    }
                )
            )
            return

        if hasattr(context.agent_engine, "delete_memory"):
            try:
                success = context.agent_engine.delete_memory(memory_id)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "memory_deleted",
                            "success": success,
                            "memory_id": memory_id,
                        }
                    )
                )
            except Exception as e:
                logger.error(f"Failed to delete memory: {e}")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "error_code": MemoryErrorCode.DELETE_MEMORY_FAILED,
                            "details": str(e),
                        }
                    )
                )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "error_code": MemoryErrorCode.MEMORY_NOT_SUPPORTED,
                    }
                )
            )

    async def handle_delete_all_memories(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        Delete all memories for the user.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: Data from client (unused)

        Returns:
            Sends all_memories_deleted or error message via WebSocket
        """
        context = self.client_contexts.get(client_uid)
        if not context:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "error_code": MemoryErrorCode.CLIENT_CONTEXT_NOT_FOUND,
                    }
                )
            )
            return

        if hasattr(context.agent_engine, "delete_all_memories"):
            try:
                success = context.agent_engine.delete_all_memories()
                await websocket.send_text(
                    json.dumps({"type": "all_memories_deleted", "success": success})
                )
            except Exception as e:
                logger.error(f"Failed to delete all memories: {e}")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "error_code": MemoryErrorCode.DELETE_ALL_MEMORIES_FAILED,
                            "details": str(e),
                        }
                    )
                )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "error_code": MemoryErrorCode.MEMORY_NOT_SUPPORTED,
                    }
                )
            )
