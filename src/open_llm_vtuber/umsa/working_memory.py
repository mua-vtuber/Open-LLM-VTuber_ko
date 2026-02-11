"""Working Memory for UMSA (Unified Memory System Architecture).

This module implements a token-budget-aware conversation buffer that manages
recent messages in the active conversation. It replaces unbounded Python lists
with intelligent eviction policies.

Key features:
- Token-budget-aware message buffer with automatic eviction
- Important message protection (preserved until >90% full)
- Returns evicted messages for absorption into Session Memory
- Interrupt handling for truncating incomplete assistant responses
- Thread-safe for async single-threaded environments
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from .models import Message
from .token_counter import TokenCounter


class WorkingMemory:
    """Token-budget-aware message buffer for active conversation.

    Manages recent conversation messages within a token budget, evicting oldest
    messages when necessary. Messages marked as important are protected from
    eviction until the buffer reaches critical capacity (>90%).

    Attributes:
        max_tokens: Maximum token budget for this buffer (typically 35% of total context)
        token_counter: Token counter instance for computing message sizes
    """

    def __init__(
        self, max_tokens: int, token_counter: TokenCounter | None = None
    ) -> None:
        """Initialize WorkingMemory with token budget.

        Args:
            max_tokens: Maximum token budget for this buffer
            token_counter: Optional token counter instance. Creates default if None.
        """
        self.max_tokens = max_tokens
        self.token_counter = token_counter or TokenCounter()
        self._messages: list[Message] = []
        self._current_tokens = 0

        logger.debug(
            f"WorkingMemory initialized with max_tokens={max_tokens}"
        )

    def add_message(
        self,
        role: str,
        content: str,
        name: str | None = None,
        platform: str | None = None,
        important: bool = False,
    ) -> list[Message]:
        """Add a message to working memory, evicting old messages if necessary.

        Args:
            role: Message role ("user", "assistant", "system")
            content: Message content text
            name: Optional speaker name
            platform: Optional platform identifier
            important: If True, protect from eviction until buffer >90% full

        Returns:
            List of evicted messages (empty if none evicted)
        """
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            name=name,
            platform=platform,
            important=important,
        )

        # Calculate tokens for this message
        message_tokens = self.token_counter.count(content)

        # Add message
        self._messages.append(message)
        self._current_tokens += message_tokens

        logger.debug(
            f"Added message: role={role}, tokens={message_tokens}, "
            f"important={important}, total_tokens={self._current_tokens}/{self.max_tokens}"
        )

        # Evict if over budget
        evicted = self._evict_if_needed()

        if evicted:
            logger.info(
                f"Evicted {len(evicted)} messages to stay within token budget"
            )

        return evicted

    def get_messages(self) -> list[Message]:
        """Get a copy of current messages in working memory.

        Returns:
            Copy of message list
        """
        return self._messages.copy()

    def to_chat_messages(self) -> list[dict[str, Any]]:
        """Convert messages to LLM chat format.

        Returns:
            List of message dicts in format [{"role": ..., "content": ...}]
        """
        chat_messages = []
        for msg in self._messages:
            chat_msg: dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.name:
                chat_msg["name"] = msg.name
            chat_messages.append(chat_msg)
        return chat_messages

    def handle_interrupt(
        self, heard_response: str, interrupt_role: str = "user"
    ) -> None:
        """Handle user interruption during assistant response.

        Truncates the last assistant message and appends an interruption marker.
        Typically called when the user interrupts the assistant mid-response.

        Args:
            heard_response: The partial response that was heard before interruption
            interrupt_role: Role of the interrupting party (default: "user")
        """
        if not self._messages:
            logger.warning("handle_interrupt called but no messages in buffer")
            return

        last_message = self._messages[-1]

        if last_message.role != "assistant":
            logger.warning(
                f"handle_interrupt expected last message to be assistant, "
                f"got {last_message.role}"
            )
            return

        # Truncate and mark as interrupted
        interrupted_content = (
            f"{heard_response}\n[INTERRUPTED by {interrupt_role}]"
        )

        # Recalculate tokens
        old_tokens = self.token_counter.count(last_message.content)
        new_tokens = self.token_counter.count(interrupted_content)
        token_delta = new_tokens - old_tokens

        last_message.content = interrupted_content
        self._current_tokens += token_delta

        logger.info(
            f"Handled interrupt: truncated assistant message, "
            f"token_delta={token_delta:+d}"
        )

    def clear(self) -> None:
        """Clear all messages from working memory."""
        message_count = len(self._messages)
        self._messages.clear()
        self._current_tokens = 0
        logger.info(f"Cleared {message_count} messages from working memory")

    def set_from_history(
        self, messages: list[dict[str, Any]]
    ) -> list[Message]:
        """Load messages from chat history, evicting if over budget.

        Args:
            messages: List of message dicts in format [{"role": ..., "content": ...}]

        Returns:
            List of evicted messages (if any were evicted to fit budget)
        """
        self.clear()

        evicted: list[Message] = []

        for msg_dict in messages:
            role = msg_dict["role"]
            content = msg_dict["content"]
            name = msg_dict.get("name")

            # Convert to Message object
            message = Message(
                role=role,
                content=content,
                timestamp=datetime.now(),
                name=name,
                important=False,  # History messages not automatically important
            )

            message_tokens = self.token_counter.count(content)
            self._messages.append(message)
            self._current_tokens += message_tokens

        # Evict oldest if over budget
        evicted = self._evict_if_needed()

        if evicted:
            logger.info(
                f"Loaded {len(messages)} messages from history, "
                f"evicted {len(evicted)} to fit budget"
            )
        else:
            logger.debug(f"Loaded {len(messages)} messages from history")

        return evicted

    @property
    def current_tokens(self) -> int:
        """Get current token usage.

        Returns:
            Total tokens currently held in buffer
        """
        return self._current_tokens

    @property
    def message_count(self) -> int:
        """Get number of messages currently held.

        Returns:
            Count of messages in buffer
        """
        return len(self._messages)

    @property
    def last_message(self) -> Message | None:
        """Get the last message in working memory, or None if empty."""
        return self._messages[-1] if self._messages else None

    def update_last_content(self, new_content: str) -> None:
        """Update the content of the last message, adjusting token count.

        Args:
            new_content: New content for the last message
        """
        if not self._messages:
            logger.warning("update_last_content called but no messages in buffer")
            return

        old_tokens = self.token_counter.count(self._messages[-1].content)
        self._messages[-1].content = new_content
        new_tokens = self.token_counter.count(new_content)
        self._current_tokens += new_tokens - old_tokens

    def _evict_if_needed(self) -> list[Message]:
        """Evict oldest messages if over token budget.

        Implements FIFO eviction policy with important message protection:
        1. First, try to evict non-important messages (oldest first)
        2. Only evict important messages when no non-important remain

        Returns:
            List of evicted messages
        """
        evicted: list[Message] = []

        while self._current_tokens > self.max_tokens and self._messages:
            # First pass: find oldest non-important message
            evicted_index = None
            for i, msg in enumerate(self._messages):
                if not msg.important:
                    evicted_index = i
                    break

            # Second pass: if no non-important found, evict oldest important
            if evicted_index is None:
                evicted_index = 0

            # Safety: don't evict the only remaining message
            if len(self._messages) <= 1:
                logger.warning(
                    "Cannot evict: only one message remains. "
                    f"tokens={self._current_tokens}/{self.max_tokens}"
                )
                break

            evicted_message = self._messages.pop(evicted_index)
            evicted_tokens = self.token_counter.count(evicted_message.content)
            self._current_tokens -= evicted_tokens
            evicted.append(evicted_message)

            logger.debug(
                f"Evicted message: role={evicted_message.role}, "
                f"tokens={evicted_tokens}, important={evicted_message.important}"
            )

        return evicted
