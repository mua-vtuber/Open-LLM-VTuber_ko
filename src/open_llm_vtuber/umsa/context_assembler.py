"""Context assembler for UMSA.

Builds the final LLM prompt within a strict token budget by assembling components
in priority order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from .config import BudgetAllocation
from .models import EntityProfile, RetrievalResult
from .token_counter import TokenCounter


@dataclass
class AssembledContext:
    """Result of context assembly with system content separated from messages.

    This split is critical because Claude API requires ``system=`` as a separate
    parameter, while OpenAI-compatible APIs prepend it as a system message.
    Keeping them separate lets each LLM adapter handle the difference.
    """

    system_content: str
    """Combined system prompt (persona + stream context + profile + procedural
    rules + memories + episodic summary)."""

    messages: list[dict] = field(default_factory=list)
    """Recent conversation messages fitted to the token budget."""


class ContextAssembler:
    """Assembles LLM context from multiple components within token budget.

    Components (Phase 2):
    - System prompt (character definition, personality)
    - Stream context (current streaming status, events, topics)
    - Entity profile (relationship context)
    - Procedural rules (behavioral rules derived from memories)
    - Retrieved memories (long-term knowledge from RAG)
    - Episodic summary (condensed summaries of previous sessions)
    - Recent messages (immediate conversation context)

    Each component gets a percentage-based token budget allocation.
    Unused allocations are redistributed to other components.
    """

    def __init__(
        self,
        total_tokens: int,
        token_counter: TokenCounter,
        budget: BudgetAllocation | None = None,
    ):
        """Initialize context assembler.

        Args:
            total_tokens: Total context window size
            token_counter: Token counter for text measurement
            budget: Budget allocation percentages (defaults to BudgetAllocation)
        """
        self.total_tokens = total_tokens
        self.token_counter = token_counter
        self.budget = budget or BudgetAllocation()

        logger.debug(
            f"ContextAssembler initialized with {total_tokens} tokens, "
            f"budget allocation: {self.budget.model_dump()}"
        )

    def assemble_split(
        self,
        system_prompt: str,
        recent_messages: list[dict],
        entity_profile: EntityProfile | None = None,
        stream_context: str = "",
        procedural_rules: str = "",
        episodic_summary: str = "",
        retrieved_memories: list[RetrievalResult] | None = None,
    ) -> AssembledContext:
        """Assemble context within token budget, returning system and messages separately.

        This is the preferred method because it keeps the system prompt separate
        from conversation messages, which is required by Claude's native API
        and beneficial for all LLM backends.

        Args:
            system_prompt: Character definition and personality
            recent_messages: Chat history (user/assistant turns)
            entity_profile: Relationship context
            stream_context: Formatted stream context text (current status, events)
            procedural_rules: Formatted procedural rules text (behavioral rules)
            episodic_summary: Condensed summaries of previous sessions
            retrieved_memories: Long-term knowledge from RAG

        Returns:
            AssembledContext with system_content and messages separated
        """
        budgets = self._calculate_budgets(
            has_profile=entity_profile is not None,
            has_stream_context=bool(stream_context.strip()),
            has_procedural=bool(procedural_rules.strip()),
            has_memories=bool(retrieved_memories),
            has_episodic=bool(episodic_summary.strip()),
        )

        logger.debug(f"Calculated token budgets: {budgets}")

        # Build system content components
        system_parts = []

        # 1. System prompt (always present)
        system_prompt_fitted = self._fit_text(
            system_prompt, budgets["system_prompt"]
        )
        system_parts.append(system_prompt_fitted)

        # 2. Stream context (if available)
        if stream_context.strip():
            stream_fitted = self._fit_text(
                stream_context, budgets["stream_context"]
            )
            system_parts.append(
                f"\n\n[Current Stream Status]\n{stream_fitted}"
            )

        # 3. Entity profile (if available)
        if entity_profile:
            profile_text = entity_profile.format_for_context()
            profile_fitted = self._fit_text(profile_text, budgets["entity_profile"])
            system_parts.append(
                f"\n\n[About the person you're talking to]\n{profile_fitted}"
            )

        # 4. Procedural rules (if available) — already formatted by ProceduralMemory
        if procedural_rules.strip():
            procedural_fitted = self._fit_text(
                procedural_rules, budgets["procedural"]
            )
            system_parts.append(f"\n\n{procedural_fitted}")

        # 5. Retrieved memories (if available)
        if retrieved_memories:
            memories_text = self._format_memories(
                retrieved_memories, budgets["retrieved_memories"]
            )
            if memories_text:
                system_parts.append(f"\n\n[Relevant memories]\n{memories_text}")

        # 6. Episodic summary (if available)
        if episodic_summary.strip():
            episodic_fitted = self._fit_text(
                episodic_summary, budgets["episodic"]
            )
            system_parts.append(f"\n\n[Previous sessions]\n{episodic_fitted}")

        system_content = "".join(system_parts)

        # Fit recent messages within budget
        messages_fitted = self._fit_messages(
            recent_messages, budgets["recent_messages"]
        )

        # Log token usage
        system_tokens = self.token_counter.count(system_content)
        messages_tokens = sum(
            self.token_counter.count(msg["content"]) for msg in messages_fitted
        )
        total_used = system_tokens + messages_tokens
        logger.info(
            f"Context assembled: system={system_tokens}tok, "
            f"messages={len(messages_fitted)}({messages_tokens}tok), "
            f"total={total_used}/{self.total_tokens} "
            f"({total_used / self.total_tokens * 100:.1f}%)"
        )

        return AssembledContext(
            system_content=system_content,
            messages=messages_fitted,
        )

    def assemble(
        self,
        system_prompt: str,
        recent_messages: list[dict],
        entity_profile: EntityProfile | None = None,
        stream_context: str = "",
        procedural_rules: str = "",
        episodic_summary: str = "",
        retrieved_memories: list[RetrievalResult] | None = None,
    ) -> list[dict]:
        """Assemble context within token budget.

        Convenience wrapper around :meth:`assemble_split` that returns a flat
        message list with the system content as the first ``system`` message.

        Returns:
            List of messages in LLM chat format (role + content)
        """
        ctx = self.assemble_split(
            system_prompt=system_prompt,
            recent_messages=recent_messages,
            entity_profile=entity_profile,
            stream_context=stream_context,
            procedural_rules=procedural_rules,
            episodic_summary=episodic_summary,
            retrieved_memories=retrieved_memories,
        )
        context = [{"role": "system", "content": ctx.system_content}]
        context.extend(ctx.messages)
        return context

    def _calculate_budgets(
        self,
        has_profile: bool,
        has_stream_context: bool,
        has_procedural: bool,
        has_memories: bool,
        has_episodic: bool,
    ) -> dict[str, int]:
        """Calculate actual token budgets, redistributing unused allocations.

        Redistribution rules:
        - If no entity profile: redistribute to retrieved_memories (if present),
          otherwise to recent_messages
        - If no stream context: redistribute to recent_messages
        - If no procedural rules: redistribute to recent_messages
        - If no retrieved memories: redistribute to recent_messages
        - If no episodic summary: redistribute to recent_messages

        Args:
            has_profile: Whether entity profile is available
            has_stream_context: Whether stream context is available
            has_procedural: Whether procedural rules are available
            has_memories: Whether retrieved memories are available
            has_episodic: Whether episodic summary is available

        Returns:
            Dict mapping component names to token budgets
        """
        # Start with base allocations
        allocations = self.budget.model_dump()

        # Track redistributed percentages
        extra_for_memories = 0.0
        extra_for_messages = 0.0

        # Redistribute unused allocations
        if not has_profile:
            extra_for_memories += allocations["entity_profile"]
            allocations["entity_profile"] = 0.0

        if not has_stream_context:
            extra_for_messages += allocations["stream_context"]
            allocations["stream_context"] = 0.0

        if not has_procedural:
            extra_for_messages += allocations["procedural"]
            allocations["procedural"] = 0.0

        if not has_memories:
            extra_for_messages += allocations["retrieved_memories"]
            allocations["retrieved_memories"] = 0.0
        else:
            # Add redistributed profile allocation
            allocations["retrieved_memories"] += extra_for_memories
            extra_for_memories = 0.0

        if not has_episodic:
            extra_for_messages += allocations["episodic"]
            allocations["episodic"] = 0.0

        # If memories don't exist, their extra also goes to messages
        if not has_memories and extra_for_memories > 0:
            extra_for_messages += extra_for_memories

        # Apply all redistributions to recent_messages
        allocations["recent_messages"] += extra_for_messages

        # Calculate actual token budgets (excluding response_reserve)
        available_tokens = int(
            self.total_tokens * (1.0 - allocations["response_reserve"])
        )

        budgets = {
            "system_prompt": int(available_tokens * allocations["system_prompt"]),
            "stream_context": int(
                available_tokens * allocations["stream_context"]
            ),
            "entity_profile": int(available_tokens * allocations["entity_profile"]),
            "procedural": int(available_tokens * allocations["procedural"]),
            "retrieved_memories": int(
                available_tokens * allocations["retrieved_memories"]
            ),
            "recent_messages": int(available_tokens * allocations["recent_messages"]),
            "episodic": int(available_tokens * allocations["episodic"]),
        }

        return budgets

    def _fit_text(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token budget.

        Truncates from the end to preserve the beginning.

        Args:
            text: Text to fit
            max_tokens: Maximum token budget

        Returns:
            Fitted text
        """
        if not text.strip():
            return ""

        current_tokens = self.token_counter.count(text)

        if current_tokens <= max_tokens:
            return text

        # Binary search for fitting text length
        # Estimate character ratio
        char_ratio = len(text) / max(current_tokens, 1)
        estimated_chars = int(max_tokens * char_ratio * 0.9)  # 90% safety margin

        # Start with estimated length
        fitted_text = text[:estimated_chars]
        fitted_tokens = self.token_counter.count(fitted_text)

        # Adjust if needed
        while fitted_tokens > max_tokens and len(fitted_text) > 0:
            # Reduce by 10%
            fitted_text = fitted_text[: int(len(fitted_text) * 0.9)]
            fitted_tokens = self.token_counter.count(fitted_text)

        logger.debug(
            f"Fitted text from {current_tokens} to {fitted_tokens} tokens "
            f"(budget: {max_tokens})"
        )

        return fitted_text

    def _fit_messages(
        self, messages: list[dict], max_tokens: int
    ) -> list[dict]:
        """Fit messages within budget, keeping most recent.

        Trims from the beginning to preserve recent conversation context.

        Args:
            messages: List of message dicts (role + content)
            max_tokens: Maximum token budget

        Returns:
            Fitted list of messages
        """
        if not messages:
            return []

        # Calculate total tokens
        total_tokens = sum(
            self.token_counter.count(msg["content"]) for msg in messages
        )

        if total_tokens <= max_tokens:
            return messages

        # Trim from beginning (keep most recent)
        fitted_messages = []
        current_tokens = 0

        # Iterate in reverse to prioritize recent messages
        for msg in reversed(messages):
            msg_tokens = self.token_counter.count(msg["content"])

            if current_tokens + msg_tokens <= max_tokens:
                fitted_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                # Try to fit partial message if it's the first one
                if not fitted_messages:
                    remaining_tokens = max_tokens - current_tokens
                    fitted_content = self._fit_text(
                        msg["content"], remaining_tokens
                    )
                    if fitted_content:
                        fitted_messages.insert(
                            0, {"role": msg["role"], "content": fitted_content}
                        )
                        current_tokens += self.token_counter.count(
                            fitted_content
                        )
                break

        logger.debug(
            f"Fitted {len(fitted_messages)}/{len(messages)} messages, "
            f"{current_tokens}/{max_tokens} tokens"
        )

        return fitted_messages

    def _format_memories(
        self, memories: list[RetrievalResult], max_tokens: int
    ) -> str:
        """Format retrieved memories as text, fitting within budget.

        Memories are formatted with metadata and truncated if needed.

        Args:
            memories: List of retrieved memory results
            max_tokens: Maximum token budget

        Returns:
            Formatted memories text
        """
        if not memories:
            return ""

        # Format each memory
        formatted_parts = []
        current_tokens = 0

        for i, memory in enumerate(memories, 1):
            # Format: [Memory N] (type: X, score: Y.YY)
            # Content...
            header = (
                f"[Memory {i}] (type: {memory.memory_type}, "
                f"score: {memory.score:.2f})"
            )
            memory_text = f"{header}\n{memory.content}"

            memory_tokens = self.token_counter.count(memory_text)

            if current_tokens + memory_tokens <= max_tokens:
                formatted_parts.append(memory_text)
                current_tokens += memory_tokens
            else:
                # Try to fit partial memory
                remaining_tokens = max_tokens - current_tokens
                if remaining_tokens > 50:  # Only if meaningful space remains
                    fitted_content = self._fit_text(
                        memory.content, remaining_tokens - len(header) - 10
                    )
                    if fitted_content:
                        formatted_parts.append(f"{header}\n{fitted_content}")
                        current_tokens += self.token_counter.count(
                            f"{header}\n{fitted_content}"
                        )
                break

        result = "\n\n".join(formatted_parts)

        logger.debug(
            f"Formatted {len(formatted_parts)}/{len(memories)} memories, "
            f"{current_tokens}/{max_tokens} tokens"
        )

        return result
