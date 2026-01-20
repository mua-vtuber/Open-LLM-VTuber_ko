"""
Chat monitor interface for live streaming platforms.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, TypedDict
from datetime import datetime


class ChatMessage(TypedDict, total=False):
    """Type definition for chat messages across platforms."""

    platform: str  # 'youtube' or 'chzzk'
    author: str  # Display name of the message author
    message: str  # Message content
    timestamp: str  # ISO format timestamp
    user_id: Optional[str]  # Platform-specific user ID
    is_moderator: bool  # Whether the user is a moderator
    is_owner: bool  # Whether the user is the channel owner/streamer
    is_member: bool  # Whether the user is a channel member
    badges: dict  # Platform-specific badges


class ChatMonitorInterface(ABC):
    """
    Interface for chat monitors.

    Each platform-specific implementation should inherit from this interface
    and implement the required methods.
    """

    def __init__(
        self,
        message_callback: Callable[[ChatMessage], None],
        max_retries: int = 10,
        retry_interval: int = 60,
    ):
        """
        Initialize the chat monitor.

        Args:
            message_callback: Function to call when a new message is received
            max_retries: Maximum number of reconnection attempts
            retry_interval: Interval between retry attempts in seconds
        """
        self.message_callback = message_callback
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.is_running = False
        self.retry_count = 0

    @abstractmethod
    async def start_monitoring(self) -> bool:
        """
        Start monitoring chat messages.

        Returns:
            bool: True if monitoring started successfully, False otherwise
        """
        pass

    @abstractmethod
    async def stop_monitoring(self) -> None:
        """Stop monitoring chat messages."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if the monitor is currently connected.

        Returns:
            bool: True if connected, False otherwise
        """
        pass

    def format_message(
        self,
        platform: str,
        author: str,
        message: str,
        timestamp: Optional[str] = None,
        **kwargs,
    ) -> ChatMessage:
        """
        Format a message into the standard ChatMessage format.

        Args:
            platform: Platform name ('youtube' or 'chzzk')
            author: Message author name
            message: Message content
            timestamp: ISO format timestamp (defaults to current time)
            **kwargs: Additional platform-specific fields

        Returns:
            ChatMessage: Formatted message dictionary
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        return ChatMessage(
            platform=platform,
            author=author,
            message=message,
            timestamp=timestamp,
            user_id=kwargs.get("user_id", ""),
            is_moderator=kwargs.get("is_moderator", False),
            is_owner=kwargs.get("is_owner", False),
            is_member=kwargs.get("is_member", False),
            badges=kwargs.get("badges", {}),
        )
