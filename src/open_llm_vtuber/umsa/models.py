"""UMSA core data models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


class MemoryType(str, Enum):
    ATOMIC_FACT = "atomic_fact"
    KNOWLEDGE_TRIPLE = "triple"
    PREFERENCE = "preference"
    EPISODE = "episode"
    META_SUMMARY = "meta_summary"


class Message(BaseModel):
    """A single conversation message."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = Field(default_factory=_utcnow)
    name: str | None = None
    platform: str | None = None
    important: bool = False  # Protected from eviction when True

    def token_estimate(self) -> int:
        """Rough token estimate (4 chars ≈ 1 token for English, 2 chars for CJK)."""
        cjk_count = sum(
            1
            for c in self.content
            if "\u4e00" <= c <= "\u9fff"
            or "\uac00" <= c <= "\ud7af"
            or "\u3040" <= c <= "\u309f"
            or "\u30a0" <= c <= "\u30ff"
        )
        non_cjk = len(self.content) - cjk_count
        return (non_cjk // 4) + (cjk_count // 2) + 4  # +4 for role/overhead


class SemanticMemory(BaseModel):
    """A stored semantic memory (fact, triple, or preference)."""

    id: str = Field(default_factory=_uuid)
    entity_id: str | None = None
    memory_type: MemoryType
    content: str
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    category: str | None = None
    confidence: float = 0.8
    importance: float = 0.5
    source_episode_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    valid_until: datetime | None = None
    last_accessed: datetime = Field(default_factory=_utcnow)
    access_count: int = 0
    connection_count: int = 0
    embedding: list[float] | None = None


class Episode(BaseModel):
    """A condensed record of a conversation segment."""

    id: str = Field(default_factory=_uuid)
    entity_id: str | None = None
    platform: str = "direct"
    summary: str
    key_quotes: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    sentiment: float = 0.0  # -1.0 to 1.0
    importance: float = 0.5
    created_at: datetime = Field(default_factory=_utcnow)
    last_accessed: datetime = Field(default_factory=_utcnow)
    access_count: int = 0
    embedding: list[float] | None = None


class SentimentEntry(BaseModel):
    """A single sentiment reading."""

    sentiment: float
    trigger_text: str | None = None
    recorded_at: datetime = Field(default_factory=_utcnow)


class EntityProfile(BaseModel):
    """Tracks relationship quality and interaction patterns for an entity."""

    id: str = Field(default_factory=_uuid)
    name: str
    platform: str
    identifiers: dict[str, str] = Field(default_factory=dict)

    # Relationship metrics
    affinity_score: float = 50.0
    total_interactions: int = 0
    last_interaction: datetime | None = None
    first_interaction: datetime | None = None
    average_session_length: float = 0.0

    # Knowledge summary
    known_facts_count: int = 0
    top_topics: list[str] = Field(default_factory=list)
    communication_style: str = "unknown"

    # Emotional history
    sentiment_history: list[SentimentEntry] = Field(default_factory=list)
    average_sentiment: float = 0.0

    # Metadata
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    schema_version: int = 1

    def format_for_context(self) -> str:
        """Format profile as a compact string for LLM context injection."""
        parts = [f"Name: {self.name}"]
        if self.communication_style != "unknown":
            parts.append(f"Style: {self.communication_style}")
        parts.append(f"Interactions: {self.total_interactions}")
        if self.top_topics:
            parts.append(f"Topics: {', '.join(self.top_topics[:5])}")
        if self.average_sentiment != 0.0:
            tone = (
                "positive"
                if self.average_sentiment > 0.2
                else ("negative" if self.average_sentiment < -0.2 else "neutral")
            )
            parts.append(f"Tone: {tone}")
        if self.known_facts_count > 0:
            parts.append(f"Known facts: {self.known_facts_count}")
        return " | ".join(parts)


class SessionMetadata(BaseModel):
    """Metadata for a conversation session."""

    id: str = Field(default_factory=_uuid)
    entity_id: str | None = None
    platform: str = "direct"
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    turn_count: int = 0
    sentiment_average: float = 0.0
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None


class RetrievalResult(BaseModel):
    """A single result from hybrid retrieval."""

    id: str
    content: str
    memory_type: str
    score: float = 0.0
    source: str = "vector"  # "vector", "fts", "graph"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """Result of memory extraction from a conversation turn."""

    memories: list[SemanticMemory] = Field(default_factory=list)
    episode_summary: str | None = None
    profile_updates: dict[str, Any] | None = None


class ConflictResolution(BaseModel):
    """Result of a memory conflict resolution."""

    action: str  # "UPDATE", "DELETE", "NOOP"
    reasoning: str = ""
    merged_content: str | None = None
