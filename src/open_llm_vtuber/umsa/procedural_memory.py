"""Procedural memory: learned behavior patterns and persona rules."""

from __future__ import annotations
from typing import Any
from uuid import uuid4


class ProceduralMemory:
    """Manages learned behavior rules. Loaded at session start, cached in memory."""

    def __init__(self):
        self.rules: list[dict[str, Any]] = []

    def load_rules(self, rules: list[dict[str, Any]]) -> None:
        """Load rules from storage (called at session start)."""
        self.rules = list(rules)

    def add_rule(
        self,
        rule_type: str,
        content: str,
        confidence: float = 0.5,
        source: str = "learned",
    ) -> dict[str, Any]:
        """Add a new rule."""
        rule = {
            "id": str(uuid4()),
            "rule_type": rule_type,
            "content": content,
            "confidence": confidence,
            "source": source,
            "active": 1,
        }
        self.rules.append(rule)
        return rule

    def get_rules_by_type(self, rule_type: str) -> list[dict[str, Any]]:
        """Get rules filtered by type."""
        return [r for r in self.rules if r.get("rule_type") == rule_type]

    def format_for_context(self) -> str:
        """Format rules as text block for LLM context injection."""
        if not self.rules:
            return ""
        grouped: dict[str, list[str]] = {}
        for rule in self.rules:
            rt = rule.get("rule_type", "general")
            grouped.setdefault(rt, []).append(rule["content"])
        parts = ["[Learned Behavior Patterns]"]
        for rule_type, contents in grouped.items():
            parts.append(f"[{rule_type.title()}]")
            for c in contents:
                parts.append(f"- {c}")
        return "\n".join(parts)
