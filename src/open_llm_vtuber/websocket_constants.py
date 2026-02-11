"""
WebSocket broadcast message type constants.

Defines message types for real-time broadcasting from server to clients.
"""

from enum import Enum


class BroadcastMessageType(str, Enum):
    """
    Broadcast message types for WebSocket communication.

    These message types are used for server-to-client broadcasts
    that don't require a specific request.
    """

    # Queue monitoring metrics
    METRICS = "broadcast:metrics"

    # Queue alert notifications (overflow, slow processing, etc.)
    QUEUE_ALERT = "broadcast:queue_alert"
