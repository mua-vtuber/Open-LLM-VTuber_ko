"""
메모리 시스템 데이터 모델

프로필, 대화 요약 등의 데이터 구조를 정의합니다.
스키마 버전 관리를 통해 향후 마이그레이션을 지원합니다.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any


# 현재 스키마 버전
SCHEMA_VERSION = 1


class Platform(Enum):
    """지원 플랫폼"""

    DISCORD = "discord"
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    CHZZK = "chzzk"
    TWITCH = "twitch"
    DIRECT = "direct"  # 웹 직접 접속

    @classmethod
    def from_string(cls, value: str) -> "Platform":
        """문자열에서 Platform 생성 (대소문자 무시)"""
        value_lower = value.lower()
        for platform in cls:
            if platform.value == value_lower:
                return platform
        # 알 수 없는 플랫폼은 DIRECT로 처리
        return cls.DIRECT


class Sentiment(Enum):
    """감정 상태"""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"

    @classmethod
    def from_string(cls, value: str) -> "Sentiment":
        """문자열에서 Sentiment 생성"""
        value_lower = value.lower()
        for sentiment in cls:
            if sentiment.value == value_lower:
                return sentiment
        return cls.NEUTRAL


@dataclass
class ConversationSummary:
    """대화 요약"""

    date: datetime
    duration_minutes: int
    message_count: int

    topics_discussed: list[str]
    key_points: list[str]
    sentiment: Sentiment

    new_facts: list[str]
    opinion_updates: dict[str, str]

    importance_score: float  # 0.0 ~ 1.0

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "date": self.date.isoformat(),
            "duration_minutes": self.duration_minutes,
            "message_count": self.message_count,
            "topics_discussed": self.topics_discussed,
            "key_points": self.key_points,
            "sentiment": self.sentiment.value,
            "new_facts": self.new_facts,
            "opinion_updates": self.opinion_updates,
            "importance_score": self.importance_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationSummary":
        """딕셔너리에서 생성"""
        return cls(
            date=datetime.fromisoformat(data["date"]),
            duration_minutes=data["duration_minutes"],
            message_count=data["message_count"],
            topics_discussed=data.get("topics_discussed", []),
            key_points=data.get("key_points", []),
            sentiment=Sentiment.from_string(data.get("sentiment", "neutral")),
            new_facts=data.get("new_facts", []),
            opinion_updates=data.get("opinion_updates", {}),
            importance_score=data.get("importance_score", 0.5),
        )


@dataclass
class MetaSummary:
    """여러 대화 요약의 메타 요약"""

    period_start: datetime
    period_end: datetime
    conversation_count: int

    recurring_topics: list[str]
    relationship_development: str
    key_memories: list[str]

    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "conversation_count": self.conversation_count,
            "recurring_topics": self.recurring_topics,
            "relationship_development": self.relationship_development,
            "key_memories": self.key_memories,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetaSummary":
        """딕셔너리에서 생성"""
        return cls(
            period_start=datetime.fromisoformat(data["period_start"]),
            period_end=datetime.fromisoformat(data["period_end"]),
            conversation_count=data["conversation_count"],
            recurring_topics=data.get("recurring_topics", []),
            relationship_development=data.get("relationship_development", ""),
            key_memories=data.get("key_memories", []),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
        )


@dataclass
class VisitorProfile:
    """
    방문자 프로필

    버전 관리를 통해 스키마 변경 시 마이그레이션을 지원합니다.
    """

    # 기본 정보
    identifier: str  # 닉네임 또는 고유 ID
    platform: Platform  # 플랫폼
    first_visit: datetime  # 첫 방문 시간
    last_visit: datetime  # 마지막 방문 시간
    visit_count: int = 1  # 총 방문 횟수
    total_messages: int = 0  # 총 메시지 수

    # 관계 정보
    affinity_score: float = 50.0  # 친밀도 (0-100)
    interaction_quality: float = 0.5  # 상호작용 품질 (0-1)

    # 프로필 데이터
    known_facts: list[str] = field(default_factory=list)  # 알게 된 사실들
    preferences: dict[str, list[str]] = field(
        default_factory=lambda: {"likes": [], "dislikes": []}
    )  # 선호도
    opinions: dict[str, str] = field(default_factory=dict)  # 주제별 의견

    # 대화 기록
    conversation_summaries: list[ConversationSummary] = field(default_factory=list)
    meta_summaries: list[MetaSummary] = field(default_factory=list)
    memorable_moments: list[str] = field(default_factory=list)  # 인상적인 순간들

    # 메타데이터
    tags: list[str] = field(default_factory=list)  # 사용자 태그
    notes: str = ""  # AI가 메모한 특이사항

    # 시스템 필드
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 스키마 버전 (마이그레이션용)
    _schema_version: int = SCHEMA_VERSION

    def get_summary_text(self, max_facts: int = 5, max_likes: int = 3) -> str:
        """
        LLM 컨텍스트용 요약 텍스트 생성

        Args:
            max_facts: 포함할 최대 사실 수
            max_likes: 포함할 최대 좋아하는 것 수

        Returns:
            요약 텍스트
        """
        lines = [f"[{self.identifier} 프로필]"]

        if self.known_facts:
            facts = self.known_facts[:max_facts]
            lines.append(f"알려진 사실: {', '.join(facts)}")

        if self.preferences.get("likes"):
            likes = self.preferences["likes"][:max_likes]
            lines.append(f"좋아하는 것: {', '.join(likes)}")

        if self.preferences.get("dislikes"):
            dislikes = self.preferences["dislikes"][:max_likes]
            lines.append(f"싫어하는 것: {', '.join(dislikes)}")

        if self.tags:
            lines.append(f"특징: {', '.join(self.tags)}")

        lines.append(f"방문 {self.visit_count}회, 친밀도 {self.affinity_score:.0f}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (저장용)"""
        return {
            "_schema_version": self._schema_version,
            "identifier": self.identifier,
            "platform": self.platform.value,
            "first_visit": self.first_visit.isoformat(),
            "last_visit": self.last_visit.isoformat(),
            "visit_count": self.visit_count,
            "total_messages": self.total_messages,
            "affinity_score": self.affinity_score,
            "interaction_quality": self.interaction_quality,
            "known_facts": self.known_facts,
            "preferences": self.preferences,
            "opinions": self.opinions,
            "conversation_summaries": [s.to_dict() for s in self.conversation_summaries],
            "meta_summaries": [s.to_dict() for s in self.meta_summaries],
            "memorable_moments": self.memorable_moments,
            "tags": self.tags,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisitorProfile":
        """딕셔너리에서 생성 (로드용)"""
        return cls(
            _schema_version=data.get("_schema_version", SCHEMA_VERSION),
            identifier=data["identifier"],
            platform=Platform.from_string(data["platform"]),
            first_visit=datetime.fromisoformat(data["first_visit"]),
            last_visit=datetime.fromisoformat(data["last_visit"]),
            visit_count=data.get("visit_count", 1),
            total_messages=data.get("total_messages", 0),
            affinity_score=data.get("affinity_score", 50.0),
            interaction_quality=data.get("interaction_quality", 0.5),
            known_facts=data.get("known_facts", []),
            preferences=data.get("preferences", {"likes": [], "dislikes": []}),
            opinions=data.get("opinions", {}),
            conversation_summaries=[
                ConversationSummary.from_dict(s)
                for s in data.get("conversation_summaries", [])
            ],
            meta_summaries=[
                MetaSummary.from_dict(s) for s in data.get("meta_summaries", [])
            ],
            memorable_moments=data.get("memorable_moments", []),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(),
        )

    @classmethod
    def create_new(
        cls,
        identifier: str,
        platform: str | Platform,
    ) -> "VisitorProfile":
        """새 프로필 생성"""
        now = datetime.now()
        if isinstance(platform, str):
            platform = Platform.from_string(platform)

        return cls(
            identifier=identifier,
            platform=platform,
            first_visit=now,
            last_visit=now,
            created_at=now,
            updated_at=now,
        )
