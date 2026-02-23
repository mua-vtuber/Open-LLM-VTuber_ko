"""Reflection engine: synthesize insights from accumulated memory nodes."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from uuid import uuid4


class ReflectionEngine:
    """Synthesizes insights from accumulated memory nodes.

    Supports 3-tier LLM fallback:
    1. Local LLM (if available)
    2. CLI LLM (if configured)
    3. Rule-based (always available)
    """

    def __init__(
        self,
        llm: Any = None,
        min_group_size: int = 3,
    ):
        self._llm = llm
        self.min_group_size = min_group_size

    def reflect_sync(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rule-based reflection (no LLM). Always available.

        Groups nodes by entity_id, produces frequency-based insights
        when group size >= min_group_size.

        Args:
            nodes: List of memory node dicts with at least:
                   content, entity_id, memory_type

        Returns:
            List of insight dicts with keys:
                id, entity_id, memory_type ("meta_summary"), content,
                importance, source_node_ids
        """
        # Group by entity_id
        groups: dict[str, list[dict]] = defaultdict(list)
        for node in nodes:
            eid = node.get("entity_id", "unknown")
            groups[eid].append(node)

        insights = []
        for entity_id, group in groups.items():
            if len(group) < self.min_group_size:
                continue

            insight = self._rule_based_insight(entity_id, group)
            if insight:
                insights.append(insight)

        return insights

    async def reflect(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Async reflection with LLM fallback.

        Tries LLM first, falls back to rule-based.
        """
        if self._llm is not None:
            try:
                return await self._llm_reflect(nodes)
            except Exception:
                pass

        return self.reflect_sync(nodes)

    async def _llm_reflect(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """LLM-based reflection (placeholder for when LLM is available)."""
        # For now, fall back to rule-based
        return self.reflect_sync(nodes)

    def _rule_based_insight(
        self, entity_id: str, group: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Generate a frequency-based insight from a group of nodes."""
        # Count memory types
        type_counts = Counter(n.get("memory_type", "unknown") for n in group)

        # Extract source node IDs
        source_ids = [n.get("id", n.get("node_id", "")) for n in group]

        # Determine dominant type
        dominant_type = type_counts.most_common(1)[0][0] if type_counts else "mixed"

        # Create insight content
        contents = [n.get("content", "") for n in group]
        if dominant_type == "preference":
            summary = (
                f"Entity has {len(group)} preference-related memories: "
                f"{'; '.join(contents[:3])}"
            )
        elif dominant_type == "atomic_fact":
            summary = (
                f"Entity has {len(group)} fact-related memories: "
                f"{'; '.join(contents[:3])}"
            )
        else:
            summary = (
                f"Entity has {len(group)} memories spanning "
                f"{', '.join(type_counts.keys())}: {'; '.join(contents[:3])}"
            )

        return {
            "id": str(uuid4()),
            "entity_id": entity_id,
            "memory_type": "meta_summary",
            "content": summary,
            "importance": min(0.8, 0.3 + len(group) * 0.05),
            "source_node_ids": source_ids,
        }
