"""SimpleMem-style memory extraction pipeline.

Uses a single LLM prompt to extract structured facts from conversation turns.
Accumulated turns are batched before extraction to reduce LLM calls.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from .config import ExtractionConfig
from .models import ExtractionResult, MemoryType, SemanticMemory

if TYPE_CHECKING:
    from ..agent.stateless_llm.stateless_llm_interface import StatelessLLMInterface

EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction assistant. Your job is to extract structured facts \
from conversation turns between a user and an AI assistant.

Extract ONLY concrete, factual information worth remembering long-term. \
Skip greetings, filler, and transient statements.

Return a JSON array of extracted memories. Each element must have:
- "content": a concise statement of the fact (string)
- "type": one of "atomic_fact", "preference", "triple" (string)
- "importance": how important this fact is to remember, 0.0 to 1.0 (number)
- "subject": who/what the fact is about (string, nullable)
- "predicate": the relationship or action (string, nullable, for triples only)
- "object": the target of the relationship (string, nullable, for triples only)

Guidelines:
- "atomic_fact": standalone facts (e.g. "User is a university student")
- "preference": likes/dislikes/wants (e.g. "User prefers dark mode")
- "triple": subject-predicate-object relationships (e.g. subject="User", \
predicate="lives_in", object="Seoul")
- importance 0.8-1.0: core identity, strong preferences, key relationships
- importance 0.5-0.7: interests, habits, moderate preferences
- importance 0.3-0.4: minor details, casual mentions
- Do NOT extract information the assistant already knows from its system prompt
- Do NOT extract temporary states (e.g. "user is currently eating")
- Deduplicate: if the same fact appears multiple times, include it only once

Return ONLY the JSON array. No markdown, no explanation.
If nothing worth extracting, return: []
"""


class MemoryExtractor:
    """Extracts structured memories from conversation turns using LLM.

    Implements the SimpleMem approach: batch conversation turns, send a single
    LLM prompt, and parse the structured JSON response.
    """

    def __init__(
        self,
        llm: StatelessLLMInterface,
        config: ExtractionConfig | None = None,
    ):
        """Initialize extractor.

        Args:
            llm: Stateless LLM for extraction prompts
            config: Extraction configuration
        """
        self._llm = llm
        self._config = config or ExtractionConfig()
        self._turn_buffer: list[dict] = []

    @property
    def buffer_size(self) -> int:
        return len(self._turn_buffer)

    def add_turn(
        self,
        user_content: str,
        assistant_content: str,
        entity_id: str | None = None,
    ) -> bool:
        """Add a conversation turn to the buffer.

        Args:
            user_content: User's message
            assistant_content: Assistant's response
            entity_id: Optional entity identifier

        Returns:
            True if buffer is full and extraction should be triggered
        """
        self._turn_buffer.append({
            "user": user_content,
            "assistant": assistant_content,
            "entity_id": entity_id,
        })
        return len(self._turn_buffer) >= self._config.batch_size

    def clear_buffer(self) -> None:
        """Clear the turn buffer."""
        self._turn_buffer.clear()

    async def extract(
        self,
        entity_id: str | None = None,
        force: bool = False,
    ) -> ExtractionResult:
        """Extract memories from buffered conversation turns.

        Args:
            entity_id: Default entity_id for extracted memories
            force: Extract even if buffer hasn't reached batch_size

        Returns:
            ExtractionResult with extracted SemanticMemory instances
        """
        if not self._turn_buffer:
            return ExtractionResult()

        if not force and len(self._turn_buffer) < self._config.batch_size:
            return ExtractionResult()

        turns_to_process = list(self._turn_buffer)
        self._turn_buffer.clear()

        conversation_text = self._format_turns(turns_to_process)
        raw_json = await self._call_llm(conversation_text)

        if not raw_json:
            logger.debug("Extraction returned empty response")
            return ExtractionResult()

        memories = self._parse_response(raw_json, entity_id)
        memories = self._filter_by_thresholds(memories)

        logger.info(f"Extracted {len(memories)} memories from {len(turns_to_process)} turns")
        return ExtractionResult(memories=memories)

    def _format_turns(self, turns: list[dict]) -> str:
        """Format buffered turns into a conversation transcript."""
        lines = []
        for i, turn in enumerate(turns, 1):
            lines.append(f"[Turn {i}]")
            lines.append(f"User: {turn['user']}")
            lines.append(f"Assistant: {turn['assistant']}")
            lines.append("")
        return "\n".join(lines)

    async def _call_llm(self, conversation_text: str) -> str:
        """Call LLM to extract facts from conversation text.

        Args:
            conversation_text: Formatted conversation transcript

        Returns:
            Raw JSON string from LLM response
        """
        messages = [
            {
                "role": "user",
                "content": (
                    "Extract structured facts from this conversation:\n\n"
                    f"{conversation_text}"
                ),
            }
        ]

        response_parts: list[str] = []
        try:
            stream = self._llm.chat_completion(
                messages=messages,
                system=EXTRACTION_SYSTEM_PROMPT,
            )
            async for chunk in stream:
                if isinstance(chunk, str):
                    response_parts.append(chunk)
                elif isinstance(chunk, dict) and chunk.get("type") == "text_delta":
                    response_parts.append(chunk.get("text", ""))
        except Exception as e:
            logger.error(f"LLM extraction call failed: {e}")
            return ""

        return "".join(response_parts).strip()

    def _parse_response(
        self,
        raw_json: str,
        default_entity_id: str | None,
    ) -> list[SemanticMemory]:
        """Parse LLM JSON response into SemanticMemory list.

        Args:
            raw_json: Raw JSON string from LLM
            default_entity_id: Entity ID to assign if not specified

        Returns:
            List of parsed SemanticMemory instances
        """
        # Strip markdown code fences if present
        text = raw_json.strip()
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction JSON: {e}")
            logger.debug(f"Raw response: {raw_json[:500]}")
            return []

        if not isinstance(data, list):
            logger.warning(f"Extraction expected JSON array, got {type(data).__name__}")
            return []

        memories: list[SemanticMemory] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            content = item.get("content", "").strip()
            if not content:
                continue

            type_str = item.get("type", "atomic_fact")
            try:
                memory_type = MemoryType(type_str)
            except ValueError:
                memory_type = MemoryType.ATOMIC_FACT

            importance = item.get("importance", 0.5)
            if not isinstance(importance, (int, float)):
                importance = 0.5
            importance = max(0.0, min(1.0, float(importance)))

            memories.append(
                SemanticMemory(
                    entity_id=default_entity_id,
                    memory_type=memory_type,
                    content=content,
                    subject=item.get("subject"),
                    predicate=item.get("predicate"),
                    object=item.get("object"),
                    importance=importance,
                    confidence=0.8,
                )
            )

        return memories

    def _filter_by_thresholds(
        self, memories: list[SemanticMemory]
    ) -> list[SemanticMemory]:
        """Filter memories by importance and confidence thresholds.

        Args:
            memories: Raw extracted memories

        Returns:
            Filtered list meeting threshold criteria
        """
        filtered = [
            m for m in memories
            if m.importance >= self._config.min_importance
            and m.confidence >= self._config.confidence_threshold
        ]

        if len(filtered) < len(memories):
            logger.debug(
                f"Filtered {len(memories) - len(filtered)} memories "
                f"below thresholds (importance>={self._config.min_importance}, "
                f"confidence>={self._config.confidence_threshold})"
            )

        return filtered
