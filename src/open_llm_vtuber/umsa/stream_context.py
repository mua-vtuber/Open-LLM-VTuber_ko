"""In-memory stream context for real-time broadcast awareness."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class StreamEvent:
    """A notable stream event (superchat, subscription, etc.)."""

    event_type: str
    author: str
    content: str
    timestamp: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    def format_relative(self, now: float | None = None) -> str:
        now = now or time.monotonic()
        elapsed = int(now - self.timestamp)
        if elapsed < 60:
            return f"{self.author} {self.event_type} ({elapsed}s ago)"
        return f"{self.author} {self.event_type} ({elapsed // 60}m ago)"


class StreamContext:
    """Real-time in-memory stream context. Zero DB access, <1ms update."""

    def __init__(
        self,
        max_events: int = 20,
        topic_change_threshold: int = 5,
        summary_interval: int = 10,
        viewer_timeout_seconds: float = 300.0,
    ):
        self.max_events = max_events
        self.topic_change_threshold = topic_change_threshold
        self.summary_interval = summary_interval
        self.viewer_timeout_seconds = viewer_timeout_seconds

        self.current_topic: str = ""
        self.current_mood: str = "neutral"
        self.recent_events: deque[StreamEvent] = deque(maxlen=max_events)
        self.active_viewers: dict[str, float] = {}
        self.topic_history: list[str] = []
        self.session_start: datetime = datetime.now(timezone.utc)
        self.summary_buffer: list[str] = []
        self.message_count: int = 0

    def update(
        self,
        author: str,
        content: str,
        msg_type: str = "chat",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update stream context with a new message. Must be <1ms."""
        now = time.monotonic()
        self.message_count += 1
        self.active_viewers[author] = now

        if msg_type in ("superchat", "subscription", "membership"):
            self.recent_events.append(
                StreamEvent(
                    event_type=msg_type,
                    author=author,
                    content=content,
                    timestamp=now,
                    metadata=metadata or {},
                )
            )

        if self.message_count % 50 == 0:
            self._prune_inactive_viewers()

    def _prune_inactive_viewers(self) -> None:
        now = time.monotonic()
        expired = [
            name
            for name, last_seen in self.active_viewers.items()
            if now - last_seen > self.viewer_timeout_seconds
        ]
        for name in expired:
            del self.active_viewers[name]

    def format_for_context(self) -> str:
        """Format as text block for LLM context injection."""
        parts = ["[Current Stream Status]"]
        if self.current_topic:
            parts.append(f"Topic: {self.current_topic}")
        parts.append(f"Mood: {self.current_mood}")

        if self.recent_events:
            now = time.monotonic()
            events_str = ", ".join(
                e.format_relative(now) for e in list(self.recent_events)[-5:]
            )
            parts.append(f"Recent Events: {events_str}")

        if self.active_viewers:
            viewers = sorted(
                self.active_viewers.keys(),
                key=lambda n: self.active_viewers[n],
                reverse=True,
            )[:10]
            parts.append(f"Active Viewers: {', '.join(viewers)}")

        parts.append(f"Messages this session: {self.message_count}")
        return "\n".join(parts)

    def to_episode_dict(self) -> dict[str, Any]:
        """Convert current state to an episode dict for permanent storage."""
        return {
            "summary": f"Stream session with {self.message_count} messages. "
            f"Topic: {self.current_topic or 'general'}.",
            "topics": self.topic_history
            + ([self.current_topic] if self.current_topic else []),
            "key_events": [
                {
                    "type": e.event_type,
                    "author": e.author,
                    "metadata": e.metadata,
                }
                for e in self.recent_events
            ],
            "participant_count": len(self.active_viewers),
            "sentiment": self.current_mood,
            "started_at": self.session_start.isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
        }

    def clear(self) -> None:
        """Reset for new session."""
        self.current_topic = ""
        self.current_mood = "neutral"
        self.recent_events.clear()
        self.active_viewers.clear()
        self.topic_history.clear()
        self.summary_buffer.clear()
        self.message_count = 0
        self.session_start = datetime.now(timezone.utc)
