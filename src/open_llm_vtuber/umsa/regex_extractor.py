"""Regex-based memory extraction engine for the hot path.

Runs synchronously with zero LLM dependency. Provides fast, pattern-matched
extraction of preferences, facts, activities, and decisions from bilingual
(Korean/English) chat messages. All extractions carry confidence=0.5 to
distinguish them from LLM-extracted memories (confidence=0.8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True, slots=True)
class _PatternEntry:
    """A single compiled extraction pattern with metadata."""

    pattern: re.Pattern[str]
    memory_type: str
    importance: float
    category: str
    group_index: int = 1
    template: str | None = None


# ---------------------------------------------------------------------------
# Confidence value for all regex-based extractions
# ---------------------------------------------------------------------------
_REGEX_CONFIDENCE: float = 0.5


def _build_patterns() -> tuple[_PatternEntry, ...]:
    """Build and compile all extraction patterns.

    Patterns are grouped logically by language and semantic category.
    Each pattern's first (or specified) capture group provides the
    extracted content.
    """
    raw: list[dict] = []

    # ===================================================================
    # Korean Preferences (좋아/좋아해)
    # ===================================================================
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*좋아해",
            "memory_type": "preference",
            "importance": 0.6,
            "category": "preference",
            "template": "likes {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:이|가)?\s*좋아",
            "memory_type": "preference",
            "importance": 0.5,
            "category": "preference",
            "template": "likes {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*(?:제일|가장)\s*좋아",
            "memory_type": "preference",
            "importance": 0.7,
            "category": "preference",
            "template": "favorite is {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:이|가)?\s*최고",
            "memory_type": "preference",
            "importance": 0.6,
            "category": "preference",
            "template": "thinks {0} is the best",
        }
    )

    # ===================================================================
    # Korean Negative Preferences (싫어/싫어해)
    # ===================================================================
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*싫어해?",
            "memory_type": "preference",
            "importance": 0.6,
            "category": "negative_preference",
            "template": "dislikes {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:이|가)?\s*싫어",
            "memory_type": "preference",
            "importance": 0.5,
            "category": "negative_preference",
            "template": "dislikes {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:은|는)\s*별로",
            "memory_type": "preference",
            "importance": 0.5,
            "category": "negative_preference",
            "template": "not a fan of {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*(?:안|못)\s*(?:먹어|먹)",
            "memory_type": "preference",
            "importance": 0.5,
            "category": "negative_preference",
            "template": "cannot eat {0}",
        }
    )

    # ===================================================================
    # Korean Activities
    # ===================================================================
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*하고\s*있어",
            "memory_type": "atomic_fact",
            "importance": 0.4,
            "category": "activity",
            "template": "is doing {0}",
        }
    )
    raw.append(
        {
            "pattern": r"지금\s+(.+?)(?:을|를)?\s*(?:하고|하는)\s*(?:있어|중)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "activity",
            "template": "is currently doing {0}",
        }
    )
    raw.append(
        {
            "pattern": r"요즘\s+(.+?)(?:을|를)?\s*(?:하고|배우고)\s*있어",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "activity",
            "template": "is recently doing {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*(?:매일|자주)\s*(?:해|하고)",
            "memory_type": "preference",
            "importance": 0.5,
            "category": "activity",
            "template": "regularly does {0}",
        }
    )

    # ===================================================================
    # Korean Decisions
    # ===================================================================
    raw.append(
        {
            "pattern": r"(.+?)(?:으로|로)?\s*(?:결정했어|정했어)",
            "memory_type": "atomic_fact",
            "importance": 0.6,
            "category": "decision",
            "template": "decided on {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*(?:하기로|배우기로)\s*(?:했어|결심)",
            "memory_type": "atomic_fact",
            "importance": 0.6,
            "category": "decision",
            "template": "decided to learn/do {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*시작했어",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "decision",
            "template": "started {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*그만(?:뒀어|둘래)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "decision",
            "template": "quit {0}",
        }
    )

    # ===================================================================
    # Korean Facts / Identity
    # ===================================================================
    raw.append(
        {
            "pattern": r"저는\s+(.+?)(?:이에요|입니다|예요)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "fact",
            "template": "is {0}",
        }
    )
    raw.append(
        {
            "pattern": r"나는?\s+(.+?)(?:이야|야)",
            "memory_type": "atomic_fact",
            "importance": 0.4,
            "category": "fact",
            "template": "is {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(?:제|나)\s*(?:이름은?|이름이)\s+(.+?)(?:이에요|예요|이야|야|입니다)",
            "memory_type": "atomic_fact",
            "importance": 0.7,
            "category": "fact",
            "template": "name is {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)에\s*살(?:아요|고\s*있어|아)",
            "memory_type": "atomic_fact",
            "importance": 0.6,
            "category": "fact",
            "template": "lives in {0}",
        }
    )

    # ===================================================================
    # Korean Technical
    # ===================================================================
    raw.append(
        {
            "pattern": r"(.+?)(?:을|를)?\s*(?:사용|쓰고)\s*(?:하고|있어)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "technical",
            "template": "uses {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?)(?:으로|로)\s*(?:개발|코딩)\s*(?:하고|해)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "technical",
            "template": "develops with {0}",
        }
    )

    # ===================================================================
    # English Preferences
    # ===================================================================
    raw.append(
        {
            "pattern": r"I (?:really )?like (.+?)(?:\.|!|$)",
            "memory_type": "preference",
            "importance": 0.6,
            "category": "preference",
            "template": "likes {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I love (.+?)(?:\.|!|$)",
            "memory_type": "preference",
            "importance": 0.7,
            "category": "preference",
            "template": "loves {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I enjoy (.+?)(?:\.|!|$)",
            "memory_type": "preference",
            "importance": 0.6,
            "category": "preference",
            "template": "enjoys {0}",
        }
    )
    raw.append(
        {
            "pattern": r"(.+?) is my favorite",
            "memory_type": "preference",
            "importance": 0.7,
            "category": "preference",
            "template": "favorite is {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I prefer (.+?) (?:over|to) (.+)",
            "memory_type": "preference",
            "importance": 0.7,
            "category": "preference",
            "group_index": 1,
            "template": "prefers {0}",
        }
    )

    # ===================================================================
    # English Negative Preferences
    # ===================================================================
    raw.append(
        {
            "pattern": r"I (?:really )?(?:don't like|dislike|hate) (.+?)(?:\.|!|$)",
            "memory_type": "preference",
            "importance": 0.6,
            "category": "negative_preference",
            "template": "dislikes {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I(?:'m| am) not (?:a )?fan of (.+?)(?:\.|!|$)",
            "memory_type": "preference",
            "importance": 0.5,
            "category": "negative_preference",
            "template": "not a fan of {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I can't stand (.+?)(?:\.|!|$)",
            "memory_type": "preference",
            "importance": 0.6,
            "category": "negative_preference",
            "template": "can't stand {0}",
        }
    )

    # ===================================================================
    # English Activities
    # ===================================================================
    raw.append(
        {
            "pattern": r"I(?:'m| am) (?:currently )?(?:playing|doing|working on) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "activity",
            "template": "is doing {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I(?:'ve| have) been (?:playing|doing|working on|learning) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "activity",
            "template": "has been doing {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I(?:'m| am) (?:currently )?(?:studying|learning) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "activity",
            "template": "is studying {0}",
        }
    )

    # ===================================================================
    # English Decisions
    # ===================================================================
    raw.append(
        {
            "pattern": r"I (?:decided|chose) to (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.6,
            "category": "decision",
            "template": "decided to {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I(?:'m| am) going to (?:start|learn|use) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "decision",
            "template": "plans to start {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I just (?:started|began) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "decision",
            "template": "just started {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I(?:'m| am) (?:going to |gonna )?(?:quit|stop|drop) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "decision",
            "template": "plans to quit {0}",
        }
    )

    # ===================================================================
    # English Facts / Identity
    # ===================================================================
    raw.append(
        {
            "pattern": r"I(?:'m| am) (?:a |an )?(.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "fact",
            "template": "is {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I work (?:at|for|as) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.6,
            "category": "fact",
            "template": "works at/as {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I live in (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.6,
            "category": "fact",
            "template": "lives in {0}",
        }
    )
    raw.append(
        {
            "pattern": r"My name is (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.7,
            "category": "fact",
            "template": "name is {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I(?:'m| am) (\d+) years old",
            "memory_type": "atomic_fact",
            "importance": 0.6,
            "category": "fact",
            "template": "is {0} years old",
        }
    )
    raw.append(
        {
            "pattern": r"I(?:'ve| have) (?:a |an )?(.+?) (?:named|called) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "fact",
            "group_index": 0,
            "template": "has a {0} named {1}",
        }
    )

    # ===================================================================
    # English Technical
    # ===================================================================
    raw.append(
        {
            "pattern": r"I (?:use|switched to|moved to) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "technical",
            "template": "uses {0}",
        }
    )
    raw.append(
        {
            "pattern": r"I (?:code|program|develop) (?:in|with) (.+?)(?:\.|!|$)",
            "memory_type": "atomic_fact",
            "importance": 0.5,
            "category": "technical",
            "template": "codes with {0}",
        }
    )

    # ===================================================================
    # Compile into _PatternEntry instances
    # ===================================================================
    entries: list[_PatternEntry] = []
    for r in raw:
        entries.append(
            _PatternEntry(
                pattern=re.compile(r["pattern"], re.IGNORECASE),
                memory_type=r["memory_type"],
                importance=r["importance"],
                category=r["category"],
                group_index=r.get("group_index", 1),
                template=r.get("template"),
            )
        )

    return tuple(entries)


# Compile once at module load
_PATTERNS: tuple[_PatternEntry, ...] = _build_patterns()


@dataclass
class RegexExtractor:
    """Synchronous regex-based memory extractor for the hot path.

    Runs all compiled patterns against input text and returns deduplicated,
    importance-sorted extraction results. Every result carries
    ``confidence=0.5`` to distinguish regex extractions from LLM-based ones.
    """

    _patterns: Sequence[_PatternEntry] = field(
        default_factory=lambda: _PATTERNS,
        repr=False,
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, text: str) -> list[dict]:
        """Extract memories from *text* using compiled regex patterns.

        Args:
            text: Raw chat message to scan.

        Returns:
            Deduplicated list of extraction dicts sorted by importance
            (descending).  Each dict contains:
            ``content``, ``memory_type``, ``importance``, ``confidence``,
            ``category``.
        """
        if not text or not text.strip():
            return []

        results: list[dict] = []
        seen_contents: set[str] = set()

        for entry in self._patterns:
            for match in entry.pattern.finditer(text):
                content = self._extract_content(match, entry)
                if not content:
                    continue

                # Normalise whitespace for dedup
                content_key = " ".join(content.split()).lower()
                if content_key in seen_contents:
                    continue
                seen_contents.add(content_key)

                results.append(
                    {
                        "content": content,
                        "memory_type": entry.memory_type,
                        "importance": entry.importance,
                        "confidence": _REGEX_CONFIDENCE,
                        "category": entry.category,
                    }
                )

        results.sort(key=lambda r: r["importance"], reverse=True)
        return results

    @property
    def pattern_count(self) -> int:
        """Return the total number of loaded patterns."""
        return len(self._patterns)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_content(match: re.Match, entry: _PatternEntry) -> str:
        """Pull the meaningful content string from a regex *match*.

        If ``group_index`` is ``0`` and a ``template`` with multiple
        placeholders is provided, all groups are interpolated.  Otherwise
        the single group indicated by ``group_index`` is returned.
        """
        if entry.group_index == 0 and entry.template:
            # Multi-group template interpolation
            groups = match.groups()
            try:
                return entry.template.format(*groups).strip()
            except (IndexError, KeyError):
                return ""

        try:
            raw = match.group(entry.group_index)
        except IndexError:
            return ""

        if raw is None:
            return ""

        content = raw.strip()

        # Apply single-group template when present
        if entry.template and content:
            return entry.template.format(content).strip()
        return content
