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
    """Combined system prompt (persona + profile + session summary + memories)."""

    messages: list[dict] = field(default_factory=list)
    """Recent conversation messages fitted to the token budget."""


class ContextAssembler:
    """Assembles LLM context from multiple components within token budget.

    Components:
    - System prompt (character definition, personality)
    - Entity profile (relationship context)
    - Session summary (conversation continuity)
    - Retrieved memories (long-term knowledge from RAG)
    - Recent messages (immediate conversation context)
    - Few-shot examples (response quality improvement)

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
        session_summary: str = "",
        retrieved_memories: list[RetrievalResult] | None = None,
        few_shot_examples: list[dict] | None = None,
    ) -> AssembledContext:
        """Assemble context within token budget, returning system and messages separately.

        This is the preferred method because it keeps the system prompt separate
        from conversation messages, which is required by Claude's native API
        and beneficial for all LLM backends.

        Args:
            system_prompt: Character definition and personality
            recent_messages: Chat history (user/assistant turns)
            entity_profile: Relationship context
            session_summary: Conversation continuity summary
            retrieved_memories: Long-term knowledge from RAG
            few_shot_examples: Response style examples

        Returns:
            AssembledContext with system_content and messages separated
        """
        budgets = self._calculate_budgets(
            has_profile=entity_profile is not None,
            has_session=bool(session_summary.strip()),
            has_memories=bool(retrieved_memories),
            has_examples=bool(few_shot_examples),
        )

        logger.debug(f"Calculated token budgets: {budgets}")

        # Build system content components
        system_parts = []

        # 1. System prompt (always present)
        system_prompt_fitted = self._fit_text(
            system_prompt, budgets["system_prompt"]
        )
        system_parts.append(system_prompt_fitted)

        # 2. Entity profile (if available)
        if entity_profile:
            profile_text = entity_profile.format_for_context()
            profile_fitted = self._fit_text(profile_text, budgets["entity_profile"])
            system_parts.append(
                f"\n\n[About the person you're talking to]\n{profile_fitted}"
            )

        # 3. Session summary (if available)
        if session_summary.strip():
            summary_fitted = self._fit_text(
                session_summary, budgets["session_summary"]
            )
            system_parts.append(f"\n\n[Conversation so far]\n{summary_fitted}")

        # 4. Retrieved memories (if available)
        if retrieved_memories:
            memories_text = self._format_memories(
                retrieved_memories, budgets["retrieved_memories"]
            )
            if memories_text:
                system_parts.append(f"\n\n[Relevant memories]\n{memories_text}")

        # 5. Few-shot examples (if available)
        if few_shot_examples:
            examples_text = self._format_few_shot_examples(
                few_shot_examples, budgets["few_shot_examples"]
            )
            if examples_text:
                system_parts.append(
                    f"\n\n[Response style examples]\n{examples_text}"
                )

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
        session_summary: str = "",
        retrieved_memories: list[RetrievalResult] | None = None,
        few_shot_examples: list[dict] | None = None,
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
            session_summary=session_summary,
            retrieved_memories=retrieved_memories,
            few_shot_examples=few_shot_examples,
        )
        context = [{"role": "system", "content": ctx.system_content}]
        context.extend(ctx.messages)
        return context

    def _calculate_budgets(
        self,
        has_profile: bool,
        has_session: bool,
        has_memories: bool,
        has_examples: bool,
    ) -> dict[str, int]:
        """Calculate actual token budgets, redistributing unused allocations.

        Redistribution rules:
        - If no entity profile: redistribute to retrieved_memories
        - If no session summary: redistribute to recent_messages
        - If no retrieved memories: redistribute to recent_messages
        - If no few-shot examples: redistribute to recent_messages

        Args:
            has_profile: Whether entity profile is available
            has_session: Whether session summary is available
            has_memories: Whether retrieved memories are available
            has_examples: Whether few-shot examples are available

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

        if not has_session:
            extra_for_messages += allocations["session_summary"]
            allocations["session_summary"] = 0.0

        if not has_memories:
            extra_for_messages += allocations["retrieved_memories"]
            allocations["retrieved_memories"] = 0.0
        else:
            # Add redistributed profile allocation
            allocations["retrieved_memories"] += extra_for_memories
            extra_for_memories = 0.0

        if not has_examples:
            extra_for_messages += allocations["few_shot_examples"]
            allocations["few_shot_examples"] = 0.0

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
            "entity_profile": int(available_tokens * allocations["entity_profile"]),
            "session_summary": int(available_tokens * allocations["session_summary"]),
            "retrieved_memories": int(
                available_tokens * allocations["retrieved_memories"]
            ),
            "recent_messages": int(available_tokens * allocations["recent_messages"]),
            "few_shot_examples": int(
                available_tokens * allocations["few_shot_examples"]
            ),
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

    def _format_few_shot_examples(
        self, examples: list[dict], max_tokens: int
    ) -> str:
        """Format few-shot examples as text, fitting within budget.

        Args:
            examples: List of example message dicts (role + content)
            max_tokens: Maximum token budget

        Returns:
            Formatted examples text
        """
        if not examples:
            return ""

        # Format examples as conversation turns
        formatted_parts = []
        current_tokens = 0

        for example in examples:
            role = example.get("role", "user")
            content = example.get("content", "")

            # Format: User: ...
            # Assistant: ...
            role_label = "User" if role == "user" else "Assistant"
            example_text = f"{role_label}: {content}"

            example_tokens = self.token_counter.count(example_text)

            if current_tokens + example_tokens <= max_tokens:
                formatted_parts.append(example_text)
                current_tokens += example_tokens
            else:
                # Try to fit partial example
                remaining_tokens = max_tokens - current_tokens
                if remaining_tokens > 30:  # Only if meaningful space remains
                    fitted_content = self._fit_text(
                        content, remaining_tokens - len(role_label) - 10
                    )
                    if fitted_content:
                        formatted_parts.append(f"{role_label}: {fitted_content}")
                        current_tokens += self.token_counter.count(
                            f"{role_label}: {fitted_content}"
                        )
                break

        result = "\n\n".join(formatted_parts)

        logger.debug(
            f"Formatted {len(formatted_parts)}/{len(examples)} examples, "
            f"{current_tokens}/{max_tokens} tokens"
        )

        return result
