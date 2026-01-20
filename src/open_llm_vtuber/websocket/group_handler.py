"""Group operations handler for WebSocket communication."""

from typing import Dict, Callable
from fastapi import WebSocket
import json

from ..service_context import ServiceContext
from ..chat_group import (
    ChatGroupManager,
    handle_group_operation,
    broadcast_to_group,
)


class GroupHandler:
    """Handles group-related WebSocket operations."""

    def __init__(
        self,
        chat_group_manager: ChatGroupManager,
        client_connections: Dict[str, WebSocket],
        client_contexts: Dict[str, ServiceContext],
    ):
        self.chat_group_manager = chat_group_manager
        self.client_connections = client_connections
        self.client_contexts = client_contexts

    async def handle_group_operation(
        self,
        websocket: WebSocket,
        client_uid: str,
        data: dict,
        send_group_update: Callable,
    ) -> None:
        """Handle group-related operations."""
        operation = data.get("type")
        target_uid = data.get(
            "invitee_uid" if operation == "add-client-to-group" else "target_uid"
        )

        await handle_group_operation(
            operation=operation,
            client_uid=client_uid,
            target_uid=target_uid,
            chat_group_manager=self.chat_group_manager,
            client_connections=self.client_connections,
            send_group_update=send_group_update,
        )

    async def handle_group_info(
        self,
        websocket: WebSocket,
        client_uid: str,
        data: dict,
        send_group_update: Callable,
    ) -> None:
        """Handle group info request."""
        await send_group_update(websocket, client_uid)

    async def send_group_update(self, websocket: WebSocket, client_uid: str) -> None:
        """Sends group information to a client."""
        group = self.chat_group_manager.get_client_group(client_uid)
        if group:
            current_members = self.chat_group_manager.get_group_members(client_uid)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "group-update",
                        "members": current_members,
                        "is_owner": group.owner_uid == client_uid,
                    }
                )
            )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "group-update",
                        "members": [],
                        "is_owner": False,
                    }
                )
            )

    async def broadcast_to_group(
        self, group_members: list[str], message: dict, exclude_uid: str = None
    ) -> None:
        """Broadcasts a message to group members."""
        await broadcast_to_group(
            group_members=group_members,
            message=message,
            client_connections=self.client_connections,
            exclude_uid=exclude_uid,
        )
