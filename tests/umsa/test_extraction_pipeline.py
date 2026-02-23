"""Tests for regex integration into the MemoryExtractor pipeline.

Covers:
- Regex-only extraction when llm=None
- Regex-only via llm_extraction_mode="disabled"
- Regex hot-path with LLM still available
- Backward compatibility (LLM-only, regex_enabled=False)
- Threshold filtering on regex results
- Empty buffer handling
- Buffer-to-text conversion for regex
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from open_llm_vtuber.umsa.config import ExtractionConfig
from open_llm_vtuber.umsa.extraction import MemoryExtractor
from open_llm_vtuber.umsa.models import ExtractionResult, MemoryType, SemanticMemory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_mock(response_json: str = "[]") -> AsyncMock:
    """Create a mock LLM that streams *response_json* as a single chunk."""

    async def _chat_completion(**kwargs):  # noqa: ANN003
        yield response_json

    mock = AsyncMock()
    mock.chat_completion = _chat_completion
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def regex_only_config() -> ExtractionConfig:
    """Config with LLM disabled, regex enabled, relaxed thresholds."""
    return ExtractionConfig(
        batch_size=1,
        regex_enabled=True,
        llm_extraction_mode="disabled",
        min_importance=0.0,
        confidence_threshold=0.0,
    )


@pytest.fixture
def regex_with_llm_config() -> ExtractionConfig:
    """Config with both regex and LLM enabled, relaxed thresholds."""
    return ExtractionConfig(
        batch_size=1,
        regex_enabled=True,
        llm_extraction_mode="auto",
        min_importance=0.0,
        confidence_threshold=0.0,
    )


@pytest.fixture
def llm_only_config() -> ExtractionConfig:
    """Config with regex disabled, LLM enabled."""
    return ExtractionConfig(
        batch_size=1,
        regex_enabled=False,
        llm_extraction_mode="auto",
        min_importance=0.0,
        confidence_threshold=0.0,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """MemoryExtractor construction with various configs."""

    def test_llm_none_regex_enabled(self, regex_only_config: ExtractionConfig) -> None:
        """Constructing with llm=None and regex_enabled should succeed."""
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        assert ext._regex_extractor is not None

    def test_llm_none_regex_disabled_raises(self) -> None:
        """Constructing with llm=None and regex_disabled should raise."""
        config = ExtractionConfig(
            regex_enabled=False,
            llm_extraction_mode="disabled",
        )
        with pytest.raises(ValueError, match="(?i)no extraction"):
            MemoryExtractor(llm=None, config=config)

    def test_llm_provided_regex_disabled(self, llm_only_config: ExtractionConfig) -> None:
        """Constructing with LLM but regex disabled should have no regex extractor."""
        ext = MemoryExtractor(llm=_make_llm_mock(), config=llm_only_config)
        assert ext._regex_extractor is None

    def test_llm_provided_regex_enabled(
        self, regex_with_llm_config: ExtractionConfig
    ) -> None:
        """Both LLM and regex should coexist."""
        ext = MemoryExtractor(llm=_make_llm_mock(), config=regex_with_llm_config)
        assert ext._regex_extractor is not None
        assert ext._llm is not None

    def test_backward_compat_llm_required_first_arg(self) -> None:
        """Existing code passing llm as first positional arg should still work."""
        mock_llm = _make_llm_mock()
        ext = MemoryExtractor(mock_llm)
        assert ext._llm is mock_llm


# ---------------------------------------------------------------------------
# Regex-only extraction (llm=None)
# ---------------------------------------------------------------------------


class TestRegexOnlyExtraction:
    """When llm is None, extraction should use regex exclusively."""

    @pytest.mark.asyncio
    async def test_basic_english_preference(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("I really like pizza", "That's great!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        assert isinstance(result, ExtractionResult)
        assert len(result.memories) > 0
        assert any("pizza" in m.content.lower() for m in result.memories)

    @pytest.mark.asyncio
    async def test_basic_korean_preference(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("나는 파이썬 좋아해", "파이썬 좋죠!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        assert len(result.memories) > 0
        assert any("파이썬" in m.content for m in result.memories)

    @pytest.mark.asyncio
    async def test_memories_are_semantic_memory(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("I live in Seoul", "Nice city!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        for m in result.memories:
            assert isinstance(m, SemanticMemory)
            assert m.entity_id == "user1"

    @pytest.mark.asyncio
    async def test_regex_confidence_is_0_5(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("I love cooking", "Yummy!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        for m in result.memories:
            assert m.confidence == 0.5

    @pytest.mark.asyncio
    async def test_memory_type_mapping(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("I like cats", "Cats are great!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        for m in result.memories:
            assert isinstance(m.memory_type, MemoryType)

    @pytest.mark.asyncio
    async def test_multiple_turns_combined(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        config = ExtractionConfig(
            batch_size=3,
            regex_enabled=True,
            llm_extraction_mode="disabled",
            min_importance=0.0,
            confidence_threshold=0.0,
        )
        ext = MemoryExtractor(llm=None, config=config)
        ext.add_turn("I like pizza", "Yum!", entity_id="user1")
        ext.add_turn("I love coding", "Me too!", entity_id="user1")
        ext.add_turn("I live in Tokyo", "Nice!", entity_id="user1")
        result = await ext.extract(entity_id="user1")

        assert len(result.memories) >= 2  # Should extract from multiple turns

    @pytest.mark.asyncio
    async def test_only_user_messages_scanned(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        """Regex should only scan user messages, not assistant responses."""
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn(
            "Hello there",
            "I like pizza and I live in Seoul",  # assistant says extractable things
            entity_id="user1",
        )
        result = await ext.extract(entity_id="user1", force=True)
        # The user said nothing extractable, so no memories expected
        assert len(result.memories) == 0


# ---------------------------------------------------------------------------
# Regex-only via llm_extraction_mode="disabled"
# ---------------------------------------------------------------------------


class TestDisabledLLMMode:
    """When llm_extraction_mode is 'disabled', regex should be used even if LLM provided."""

    @pytest.mark.asyncio
    async def test_llm_not_called_when_disabled(self) -> None:
        call_count = 0

        async def _tracking_llm(**kwargs):  # noqa: ANN003
            nonlocal call_count
            call_count += 1
            yield "[]"

        mock_llm = AsyncMock()
        mock_llm.chat_completion = _tracking_llm

        config = ExtractionConfig(
            batch_size=1,
            regex_enabled=True,
            llm_extraction_mode="disabled",
            min_importance=0.0,
            confidence_threshold=0.0,
        )
        ext = MemoryExtractor(llm=mock_llm, config=config)
        ext.add_turn("I like pizza", "Great!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        # Should have regex results
        assert len(result.memories) > 0
        # LLM should NOT have been called
        assert call_count == 0, "LLM was called despite llm_extraction_mode='disabled'"


# ---------------------------------------------------------------------------
# Regex hot-path with LLM
# ---------------------------------------------------------------------------


class TestRegexHotPathWithLLM:
    """When LLM is available and enabled, regex runs as hot-path first,
    then LLM adds batch results. Both sets are combined."""

    @pytest.mark.asyncio
    async def test_combined_results(self) -> None:
        """Both regex and LLM results should appear in the output."""
        llm_response = (
            '[{"content": "User enjoys swimming", "type": "preference", '
            '"importance": 0.7, "subject": null, "predicate": null, "object": null}]'
        )
        mock_llm = _make_llm_mock(llm_response)
        config = ExtractionConfig(
            batch_size=1,
            regex_enabled=True,
            llm_extraction_mode="auto",
            min_importance=0.0,
            confidence_threshold=0.0,
        )
        ext = MemoryExtractor(llm=mock_llm, config=config)
        ext.add_turn("I like pizza", "Nice!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        contents = [m.content.lower() for m in result.memories]
        # Regex should catch "pizza"
        assert any("pizza" in c for c in contents)
        # LLM should provide "swimming"
        assert any("swimming" in c for c in contents)

    @pytest.mark.asyncio
    async def test_dedup_between_regex_and_llm(self) -> None:
        """If regex and LLM extract the same content, it should be deduplicated."""
        llm_response = (
            '[{"content": "likes pizza", "type": "preference", '
            '"importance": 0.7, "subject": null, "predicate": null, "object": null}]'
        )
        mock_llm = _make_llm_mock(llm_response)
        config = ExtractionConfig(
            batch_size=1,
            regex_enabled=True,
            llm_extraction_mode="auto",
            min_importance=0.0,
            confidence_threshold=0.0,
        )
        ext = MemoryExtractor(llm=mock_llm, config=config)
        ext.add_turn("I like pizza", "Nice!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        # Should not have duplicate "likes pizza" entries
        normalized = [" ".join(m.content.split()).lower() for m in result.memories]
        assert len(normalized) == len(set(normalized))

    @pytest.mark.asyncio
    async def test_llm_failure_still_returns_regex(self) -> None:
        """If LLM call fails, regex results should still be returned."""

        async def _failing_llm(**kwargs):  # noqa: ANN003
            raise RuntimeError("LLM is down")

        mock_llm = AsyncMock()
        mock_llm.chat_completion = _failing_llm
        config = ExtractionConfig(
            batch_size=1,
            regex_enabled=True,
            llm_extraction_mode="auto",
            min_importance=0.0,
            confidence_threshold=0.0,
        )
        ext = MemoryExtractor(llm=mock_llm, config=config)
        ext.add_turn("I like pizza", "Nice!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        # Regex results should still be present
        assert len(result.memories) > 0
        assert any("pizza" in m.content.lower() for m in result.memories)


# ---------------------------------------------------------------------------
# Threshold filtering
# ---------------------------------------------------------------------------


class TestThresholdFiltering:
    """Threshold filtering should apply to regex-extracted memories."""

    @pytest.mark.asyncio
    async def test_confidence_filter_removes_regex(self) -> None:
        """With default confidence_threshold=0.6, regex results (0.5) are filtered."""
        config = ExtractionConfig(
            batch_size=1,
            regex_enabled=True,
            llm_extraction_mode="disabled",
            min_importance=0.0,
            confidence_threshold=0.6,  # regex confidence is 0.5 -> filtered
        )
        ext = MemoryExtractor(llm=None, config=config)
        ext.add_turn("I like pizza", "Yum!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        assert len(result.memories) == 0

    @pytest.mark.asyncio
    async def test_importance_filter(self) -> None:
        """Memories below min_importance threshold should be filtered."""
        config = ExtractionConfig(
            batch_size=1,
            regex_enabled=True,
            llm_extraction_mode="disabled",
            min_importance=0.8,  # Most regex patterns have importance < 0.8
            confidence_threshold=0.0,
        )
        ext = MemoryExtractor(llm=None, config=config)
        ext.add_turn("I like pizza", "Nice!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        for m in result.memories:
            assert m.importance >= 0.8


# ---------------------------------------------------------------------------
# Empty buffer / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for the integrated extraction pipeline."""

    @pytest.mark.asyncio
    async def test_empty_buffer_returns_empty(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        result = await ext.extract(entity_id="user1", force=True)
        assert result.memories == []

    @pytest.mark.asyncio
    async def test_buffer_cleared_after_extraction(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("I like pizza", "Yum!", entity_id="user1")
        await ext.extract(entity_id="user1", force=True)
        assert ext.buffer_size == 0

    @pytest.mark.asyncio
    async def test_no_extraction_from_trivial_text(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("hello", "hi there", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)
        assert len(result.memories) == 0

    @pytest.mark.asyncio
    async def test_force_false_respects_batch_size(self) -> None:
        config = ExtractionConfig(
            batch_size=5,
            regex_enabled=True,
            llm_extraction_mode="disabled",
            min_importance=0.0,
            confidence_threshold=0.0,
        )
        ext = MemoryExtractor(llm=None, config=config)
        ext.add_turn("I like pizza", "Nice!", entity_id="user1")
        # Not forced, buffer not full -> no extraction
        result = await ext.extract(entity_id="user1", force=False)
        assert len(result.memories) == 0
        assert ext.buffer_size == 1  # Buffer should NOT be cleared

    @pytest.mark.asyncio
    async def test_entity_id_from_extract_overrides(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("I like pizza", "Yum!", entity_id="turn_entity")
        result = await ext.extract(entity_id="override_entity", force=True)

        for m in result.memories:
            assert m.entity_id == "override_entity"

    @pytest.mark.asyncio
    async def test_category_field_set(
        self, regex_only_config: ExtractionConfig
    ) -> None:
        ext = MemoryExtractor(llm=None, config=regex_only_config)
        ext.add_turn("I like pizza", "Yum!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        for m in result.memories:
            assert m.category is not None


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Ensure existing LLM-only usage is not broken."""

    @pytest.mark.asyncio
    async def test_llm_only_extraction(self, llm_only_config: ExtractionConfig) -> None:
        """With regex_enabled=False, only LLM extraction should run."""
        llm_response = (
            '[{"content": "User is a student", "type": "atomic_fact", '
            '"importance": 0.6, "subject": null, "predicate": null, "object": null}]'
        )
        mock_llm = _make_llm_mock(llm_response)
        ext = MemoryExtractor(llm=mock_llm, config=llm_only_config)
        ext.add_turn("I'm a university student", "Cool!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        assert len(result.memories) == 1
        assert "student" in result.memories[0].content.lower()
        # LLM confidence, not regex
        assert result.memories[0].confidence == 0.8

    @pytest.mark.asyncio
    async def test_default_config_backward_compat(self) -> None:
        """Default ExtractionConfig + LLM should behave as before."""
        llm_response = (
            '[{"content": "User likes cats", "type": "preference", '
            '"importance": 0.6, "subject": null, "predicate": null, "object": null}]'
        )
        mock_llm = _make_llm_mock(llm_response)
        # Default config: regex_enabled=True, llm_extraction_mode="auto"
        ext = MemoryExtractor(llm=mock_llm)
        ext.add_turn("I like cats", "Meow!", entity_id="user1")
        result = await ext.extract(entity_id="user1", force=True)

        # Should have results (from LLM at minimum)
        assert len(result.memories) > 0
