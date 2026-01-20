"""Chat history management handler for WebSocket communication."""

from typing import Dict
from fastapi import WebSocket
import json

from ..service_context import ServiceContext
from ..chat_history_manager import (
    create_new_history,
    get_history,
    delete_history,
    get_history_list,
)


class HistoryHandler:
    """Handles chat history related WebSocket operations."""

    def __init__(self, client_contexts: Dict[str, ServiceContext]):
        self.client_contexts = client_contexts

    async def handle_history_list_request(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle request for chat history list."""
        context = self.client_contexts[client_uid]
        histories = get_history_list(context.character_config.conf_uid)
        await websocket.send_text(
            json.dumps({"type": "history-list", "histories": histories})
        )

    async def handle_fetch_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle fetching and setting specific chat history."""
        history_uid = data.get("history_uid")
        if not history_uid:
            return

        context = self.client_contexts[client_uid]
        # Update history_uid in service context
        context.history_uid = history_uid
        context.agent_engine.set_memory_from_history(
            conf_uid=context.character_config.conf_uid,
            history_uid=history_uid,
        )

        messages = [
            msg
            for msg in get_history(
                context.character_config.conf_uid,
                history_uid,
            )
            if msg["role"] != "system"
        ]
        await websocket.send_text(
            json.dumps({"type": "history-data", "messages": messages})
        )

    async def handle_create_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle creation of new chat history."""
        context = self.client_contexts[client_uid]
        history_uid = create_new_history(context.character_config.conf_uid)
        if history_uid:
            context.history_uid = history_uid
            context.agent_engine.set_memory_from_history(
                conf_uid=context.character_config.conf_uid,
                history_uid=history_uid,
            )
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "new-history-created",
                        "history_uid": history_uid,
                    }
                )
            )

    async def handle_delete_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle deletion of chat history."""
        history_uid = data.get("history_uid")
        if not history_uid:
            return

        context = self.client_contexts[client_uid]
        success = delete_history(
            context.character_config.conf_uid,
            history_uid,
        )
        await websocket.send_text(
            json.dumps(
                {
                    "type": "history-deleted",
                    "success": success,
                    "history_uid": history_uid,
                }
            )
        )
        if history_uid == context.history_uid:
            context.history_uid = None
