"""Detects conflicting memories and creates supersedes relationships."""

from __future__ import annotations
from typing import Any, Callable


class ConflictDetector:
    """Checks new memories against existing ones for conflicts.

    Conflict detection rules:
    - Similarity < 0.5: unrelated, no conflict
    - Similarity 0.5-0.85: potential conflict -> supersedes
    - Similarity >= 0.85: duplicate, not a conflict
    """

    CONFLICT_LOW = 0.5
    CONFLICT_HIGH = 0.85
    IMPORTANCE_DECAY = 0.7

    def check(
        self,
        new_content: str,
        existing_memories: list[dict[str, Any]],
        similarity_fn: Callable[[str, str], float],
    ) -> list[dict[str, Any]]:
        """Return list of superseded memory info dicts.

        Args:
            new_content: Content of the new memory
            existing_memories: List of dicts with at least 'id', 'content', 'importance'
            similarity_fn: Function that computes similarity between two strings (0.0-1.0)

        Returns:
            List of dicts with keys: superseded_id, similarity, new_importance_decay
        """
        conflicts = []
        for mem in existing_memories:
            sim = similarity_fn(new_content, mem["content"])
            if self.CONFLICT_LOW <= sim < self.CONFLICT_HIGH:
                old_importance = mem.get("importance", 0.5)
                conflicts.append(
                    {
                        "superseded_id": mem["id"],
                        "similarity": sim,
                        "new_importance_decay": old_importance * self.IMPORTANCE_DECAY,
                    }
                )
        return conflicts
