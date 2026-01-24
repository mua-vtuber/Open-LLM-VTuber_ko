"""
Visitor profile manager for personalized AI interactions.

Manages visitor profiles including:
- Visit history and statistics
- Known facts and preferences
- Conversation summaries
- Relationship scoring
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from loguru import logger


@dataclass
class ConversationSummary:
    """Summary of a conversation session."""

    date: str  # ISO format
    duration_minutes: int = 0
    message_count: int = 0
    topics_discussed: List[str] = field(default_factory=list)
    key_points: List[str] = field(default_factory=list)
    sentiment: str = "neutral"  # positive, neutral, negative
    new_facts: List[str] = field(default_factory=list)
    opinion_updates: Dict[str, str] = field(default_factory=dict)
    importance_score: float = 0.5  # 0.0 - 1.0
    brief_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationSummary":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class VisitorProfile:
    """Visitor profile data structure."""

    # Identity
    identifier: str  # Display name / nickname
    platform: str  # discord, youtube, bilibili, direct
    user_id: str  # Platform-specific user ID
    guild_id: Optional[str] = None  # Discord server ID (if applicable)

    # Visit statistics
    first_visit: str = ""  # ISO format
    last_visit: str = ""  # ISO format
    visit_count: int = 0
    total_messages: int = 0

    # Relationship metrics
    affinity_score: float = 50.0  # 0-100
    interaction_quality: float = 0.5  # 0-1

    # Learned information
    known_facts: List[str] = field(default_factory=list)
    preferences: Dict[str, List[str]] = field(
        default_factory=lambda: {"likes": [], "dislikes": []}
    )
    opinions: Dict[str, str] = field(default_factory=dict)

    # Conversation history
    conversation_summaries: List[ConversationSummary] = field(default_factory=list)
    memorable_moments: List[str] = field(default_factory=list)

    # Metadata
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    # Session tracking (not persisted)
    _session_start: Optional[datetime] = field(default=None, repr=False)
    _session_messages: int = field(default=0, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            "identifier": self.identifier,
            "platform": self.platform,
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "first_visit": self.first_visit,
            "last_visit": self.last_visit,
            "visit_count": self.visit_count,
            "total_messages": self.total_messages,
            "affinity_score": self.affinity_score,
            "interaction_quality": self.interaction_quality,
            "known_facts": self.known_facts,
            "preferences": self.preferences,
            "opinions": self.opinions,
            "conversation_summaries": [
                s.to_dict() for s in self.conversation_summaries
            ],
            "memorable_moments": self.memorable_moments,
            "tags": self.tags,
            "notes": self.notes,
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisitorProfile":
        """Create from dictionary."""
        # Handle conversation summaries
        summaries = []
        for s in data.get("conversation_summaries", []):
            if isinstance(s, dict):
                summaries.append(ConversationSummary.from_dict(s))
            elif isinstance(s, ConversationSummary):
                summaries.append(s)

        return cls(
            identifier=data.get("identifier", "Unknown"),
            platform=data.get("platform", "unknown"),
            user_id=data.get("user_id", ""),
            guild_id=data.get("guild_id"),
            first_visit=data.get("first_visit", ""),
            last_visit=data.get("last_visit", ""),
            visit_count=data.get("visit_count", 0),
            total_messages=data.get("total_messages", 0),
            affinity_score=data.get("affinity_score", 50.0),
            interaction_quality=data.get("interaction_quality", 0.5),
            known_facts=data.get("known_facts", []),
            preferences=data.get("preferences", {"likes": [], "dislikes": []}),
            opinions=data.get("opinions", {}),
            conversation_summaries=summaries,
            memorable_moments=data.get("memorable_moments", []),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
        )

    def start_session(self) -> None:
        """Start a new session."""
        self._session_start = datetime.now()
        self._session_messages = 0

    def get_session_duration_minutes(self) -> int:
        """Get current session duration in minutes."""
        if self._session_start is None:
            return 0
        delta = datetime.now() - self._session_start
        return int(delta.total_seconds() / 60)


class ProfileManager:
    """
    Manages visitor profiles with file-based persistence.

    Profiles are stored as JSON files organized by platform:
    visitor_profiles/
    ├── discord/
    │   └── user_{id}.json
    ├── youtube/
    │   └── channel_{id}.json
    └── bilibili/
        └── uid_{id}.json
    """

    # Compression threshold: compress old summaries when count exceeds this
    SUMMARY_COMPRESSION_THRESHOLD = 10

    def __init__(self, profiles_dir: str = "visitor_profiles"):
        """
        Initialize profile manager.

        Args:
            profiles_dir: Base directory for storing profiles
        """
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._cache: Dict[str, VisitorProfile] = {}

        logger.info(f"[ProfileManager] Initialized with directory: {self.profiles_dir}")

    def _get_profile_path(self, platform: str, user_id: str) -> Path:
        """Get the file path for a profile."""
        platform_dir = self.profiles_dir / platform
        platform_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize user_id for filename
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(user_id))
        return platform_dir / f"user_{safe_id}.json"

    def _get_cache_key(self, platform: str, user_id: str) -> str:
        """Get cache key for a profile."""
        return f"{platform}:{user_id}"

    def load_profile(self, platform: str, user_id: str) -> Optional[VisitorProfile]:
        """
        Load a profile from cache or file.

        Args:
            platform: Platform name (discord, youtube, etc.)
            user_id: Platform-specific user ID

        Returns:
            VisitorProfile if found, None otherwise
        """
        cache_key = self._get_cache_key(platform, user_id)

        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Load from file
        profile_path = self._get_profile_path(platform, user_id)

        if not profile_path.exists():
            return None

        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                profile = VisitorProfile.from_dict(data)
                self._cache[cache_key] = profile
                return profile
        except Exception as e:
            logger.error(f"[ProfileManager] Failed to load profile {profile_path}: {e}")
            return None

    def save_profile(self, profile: VisitorProfile) -> bool:
        """
        Save a profile to file.

        Args:
            profile: Profile to save

        Returns:
            True if saved successfully
        """
        profile_path = self._get_profile_path(profile.platform, profile.user_id)

        try:
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

            # Update cache
            cache_key = self._get_cache_key(profile.platform, profile.user_id)
            self._cache[cache_key] = profile

            return True
        except Exception as e:
            logger.error(f"[ProfileManager] Failed to save profile {profile_path}: {e}")
            return False

    def get_or_create_profile(
        self,
        platform: str,
        user_id: str,
        identifier: str,
        guild_id: Optional[str] = None,
    ) -> VisitorProfile:
        """
        Get existing profile or create a new one.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            identifier: Display name
            guild_id: Optional guild/server ID

        Returns:
            Existing or new VisitorProfile
        """
        profile = self.load_profile(platform, user_id)

        if profile is None:
            # Create new profile
            now = datetime.now().isoformat()
            profile = VisitorProfile(
                identifier=identifier,
                platform=platform,
                user_id=user_id,
                guild_id=guild_id,
                first_visit=now,
                last_visit=now,
                visit_count=1,
            )
            profile.start_session()
            self.save_profile(profile)
            logger.info(
                f"[ProfileManager] Created new profile for {identifier} ({platform})"
            )
        else:
            # Update existing profile
            profile.identifier = identifier  # Update nickname if changed
            if guild_id:
                profile.guild_id = guild_id

        return profile

    def update_visit(
        self,
        platform: str,
        user_id: str,
        identifier: str,
        guild_id: Optional[str] = None,
    ) -> VisitorProfile:
        """
        Update visit information for a user.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            identifier: Display name
            guild_id: Optional guild/server ID

        Returns:
            Updated VisitorProfile
        """
        profile = self.get_or_create_profile(platform, user_id, identifier, guild_id)

        # Update visit info
        profile.last_visit = datetime.now().isoformat()
        profile.visit_count += 1
        profile.start_session()

        self.save_profile(profile)
        return profile

    def record_message(self, platform: str, user_id: str) -> None:
        """
        Record a message from a user.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
        """
        profile = self.load_profile(platform, user_id)
        if profile:
            profile.total_messages += 1
            profile._session_messages += 1
            self.save_profile(profile)

    def add_fact(self, platform: str, user_id: str, fact: str) -> bool:
        """
        Add a new fact about a user.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            fact: Fact to add

        Returns:
            True if added (not duplicate)
        """
        profile = self.load_profile(platform, user_id)
        if profile and fact not in profile.known_facts:
            profile.known_facts.append(fact)
            self.save_profile(profile)
            logger.debug(
                f"[ProfileManager] Added fact for {profile.identifier}: {fact}"
            )
            return True
        return False

    def update_preference(
        self, platform: str, user_id: str, category: str, item: str
    ) -> None:
        """
        Update user preference (like/dislike).

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            category: 'likes' or 'dislikes'
            item: Item to add
        """
        if category not in ("likes", "dislikes"):
            return

        profile = self.load_profile(platform, user_id)
        if profile:
            if item not in profile.preferences[category]:
                profile.preferences[category].append(item)
                self.save_profile(profile)

    def update_opinion(
        self, platform: str, user_id: str, topic: str, opinion: str
    ) -> None:
        """
        Update user's opinion on a topic.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            topic: Topic
            opinion: User's opinion
        """
        profile = self.load_profile(platform, user_id)
        if profile:
            profile.opinions[topic] = opinion
            self.save_profile(profile)

    def add_conversation_summary(
        self, platform: str, user_id: str, summary: ConversationSummary
    ) -> None:
        """
        Add a conversation summary.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            summary: Conversation summary to add
        """
        profile = self.load_profile(platform, user_id)
        if profile:
            profile.conversation_summaries.append(summary)

            # Compress if threshold exceeded
            if len(profile.conversation_summaries) > self.SUMMARY_COMPRESSION_THRESHOLD:
                self._compress_summaries(profile)

            self.save_profile(profile)

    def _compress_summaries(self, profile: VisitorProfile) -> None:
        """
        Compress old conversation summaries.

        Keeps the most recent and important summaries,
        removes older less important ones.
        """
        summaries = profile.conversation_summaries

        if len(summaries) <= self.SUMMARY_COMPRESSION_THRESHOLD:
            return

        # Sort by importance (descending)
        sorted_summaries = sorted(
            summaries, key=lambda s: s.importance_score, reverse=True
        )

        # Keep top 5 by importance + most recent 5
        important = sorted_summaries[:5]
        recent = summaries[-5:]

        # Combine and deduplicate
        kept = []
        seen_dates = set()
        for s in important + recent:
            if s.date not in seen_dates:
                kept.append(s)
                seen_dates.add(s.date)

        profile.conversation_summaries = kept
        logger.debug(
            f"[ProfileManager] Compressed summaries for {profile.identifier}: "
            f"{len(summaries)} -> {len(kept)}"
        )

    def add_memorable_moment(self, platform: str, user_id: str, moment: str) -> None:
        """
        Add a memorable moment.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            moment: Description of the moment
        """
        profile = self.load_profile(platform, user_id)
        if profile:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            entry = f"{timestamp}: {moment}"
            profile.memorable_moments.append(entry)

            # Keep only last 20 moments
            if len(profile.memorable_moments) > 20:
                profile.memorable_moments = profile.memorable_moments[-20:]

            self.save_profile(profile)

    def update_affinity(self, platform: str, user_id: str, delta: float) -> None:
        """
        Update affinity score.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            delta: Change in affinity (-100 to +100)
        """
        profile = self.load_profile(platform, user_id)
        if profile:
            profile.affinity_score = max(0, min(100, profile.affinity_score + delta))
            self.save_profile(profile)

    def add_tag(self, platform: str, user_id: str, tag: str) -> None:
        """
        Add a tag to user profile.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID
            tag: Tag to add
        """
        profile = self.load_profile(platform, user_id)
        if profile and tag not in profile.tags:
            profile.tags.append(tag)
            self.save_profile(profile)

    def get_context_for_ai(self, platform: str, user_id: str) -> str:
        """
        Get profile context string for AI.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID

        Returns:
            Formatted context string for AI prompt
        """
        profile = self.load_profile(platform, user_id)

        if not profile:
            return ""

        lines = [f"[{profile.identifier}님 정보]"]

        # Visit info
        lines.append(f"- 방문 횟수: {profile.visit_count}회")
        lines.append(f"- 총 메시지: {profile.total_messages}개")

        # Affinity
        if profile.affinity_score >= 80:
            lines.append("- 관계: 친한 단골")
        elif profile.affinity_score >= 60:
            lines.append("- 관계: 친근한 방문자")
        elif profile.affinity_score <= 30:
            lines.append("- 관계: 아직 서먹한 사이")

        # Known facts (top 5)
        if profile.known_facts:
            facts = profile.known_facts[:5]
            lines.append(f"- 알고 있는 정보: {', '.join(facts)}")

        # Preferences
        if profile.preferences.get("likes"):
            likes = profile.preferences["likes"][:3]
            lines.append(f"- 좋아하는 것: {', '.join(likes)}")

        if profile.preferences.get("dislikes"):
            dislikes = profile.preferences["dislikes"][:3]
            lines.append(f"- 싫어하는 것: {', '.join(dislikes)}")

        # Recent topics
        if profile.conversation_summaries:
            last_summary = profile.conversation_summaries[-1]
            if last_summary.brief_summary:
                lines.append(f"- 최근 대화: {last_summary.brief_summary}")
            elif last_summary.topics_discussed:
                topics = ", ".join(last_summary.topics_discussed[:3])
                lines.append(f"- 최근 대화 주제: {topics}")

        # Tags
        if profile.tags:
            lines.append(f"- 태그: {', '.join(profile.tags)}")

        return "\n".join(lines)

    def get_greeting_context(self, platform: str, user_id: str) -> Dict[str, Any]:
        """
        Get context for generating personalized greeting.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID

        Returns:
            Dictionary with greeting context
        """
        profile = self.load_profile(platform, user_id)

        if not profile:
            return {"is_new": True}

        # Calculate days since last visit
        days_since = 0
        if profile.last_visit:
            try:
                last = datetime.fromisoformat(profile.last_visit)
                days_since = (datetime.now() - last).days
            except ValueError:
                pass

        return {
            "is_new": False,
            "identifier": profile.identifier,
            "visit_count": profile.visit_count,
            "days_since_last_visit": days_since,
            "affinity_score": profile.affinity_score,
            "recent_topics": (
                profile.conversation_summaries[-1].topics_discussed
                if profile.conversation_summaries
                else []
            ),
            "tags": profile.tags,
        }

    def list_profiles(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all profiles, optionally filtered by platform.

        Args:
            platform: Optional platform filter

        Returns:
            List of profile summaries
        """
        profiles = []

        if platform:
            platforms = [platform]
        else:
            platforms = [d.name for d in self.profiles_dir.iterdir() if d.is_dir()]

        for plat in platforms:
            plat_dir = self.profiles_dir / plat
            if not plat_dir.exists():
                continue

            for profile_file in plat_dir.glob("user_*.json"):
                try:
                    with open(profile_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        profiles.append(
                            {
                                "platform": plat,
                                "user_id": data.get("user_id"),
                                "identifier": data.get("identifier"),
                                "visit_count": data.get("visit_count", 0),
                                "last_visit": data.get("last_visit"),
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to read profile {profile_file}: {e}")

        return profiles

    def delete_profile(self, platform: str, user_id: str) -> bool:
        """
        Delete a profile.

        Args:
            platform: Platform name
            user_id: Platform-specific user ID

        Returns:
            True if deleted
        """
        profile_path = self._get_profile_path(platform, user_id)
        cache_key = self._get_cache_key(platform, user_id)

        # Remove from cache
        self._cache.pop(cache_key, None)

        # Remove file
        if profile_path.exists():
            try:
                os.remove(profile_path)
                logger.info(f"[ProfileManager] Deleted profile: {profile_path}")
                return True
            except Exception as e:
                logger.error(f"[ProfileManager] Failed to delete profile: {e}")
                return False

        return False
