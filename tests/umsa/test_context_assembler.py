"""Tests for UMSA ContextAssembler Phase 2 budget allocation."""

from __future__ import annotations

import pytest

from open_llm_vtuber.umsa.config import BudgetAllocation
from open_llm_vtuber.umsa.context_assembler import AssembledContext, ContextAssembler
from open_llm_vtuber.umsa.models import EntityProfile, RetrievalResult
from open_llm_vtuber.umsa.token_counter import TokenCounter


@pytest.fixture
def token_counter():
    """Create a token counter (uses char-based estimation if tiktoken unavailable)."""
    return TokenCounter()


@pytest.fixture
def assembler(token_counter):
    """Create a ContextAssembler with 4096 total tokens."""
    return ContextAssembler(
        total_tokens=4096,
        token_counter=token_counter,
    )


@pytest.fixture
def large_assembler(token_counter):
    """Create a ContextAssembler with a large token budget for content tests."""
    return ContextAssembler(
        total_tokens=100_000,
        token_counter=token_counter,
    )


@pytest.fixture
def sample_messages():
    """Create sample conversation messages."""
    return [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing great, thanks for asking!"},
        {"role": "user", "content": "Tell me about yourself."},
    ]


@pytest.fixture
def sample_entity_profile():
    """Create a sample entity profile."""
    return EntityProfile(
        name="TestUser",
        platform="direct",
        total_interactions=10,
        top_topics=["gaming", "anime"],
        communication_style="casual",
    )


@pytest.fixture
def sample_retrieval_results():
    """Create sample retrieval results."""
    return [
        RetrievalResult(
            id="mem-1",
            content="User enjoys playing RPG games.",
            memory_type="preference",
            score=0.95,
        ),
        RetrievalResult(
            id="mem-2",
            content="User mentioned they have a cat named Miso.",
            memory_type="atomic_fact",
            score=0.88,
        ),
    ]


# ---------------------------------------------------------------------------
# assemble_split() signature and basic behavior
# ---------------------------------------------------------------------------


class TestAssembleSplitSignature:
    """Tests for the updated assemble_split() method signature."""

    def test_accepts_new_phase2_params(self, assembler, sample_messages):
        """assemble_split() accepts stream_context, procedural_rules, episodic_summary."""
        result = assembler.assemble_split(
            system_prompt="You are a helpful assistant.",
            recent_messages=sample_messages,
            stream_context="Currently streaming on YouTube, 50 viewers",
            procedural_rules="Always greet the user by name",
            episodic_summary="Previously discussed gaming preferences",
        )
        assert isinstance(result, AssembledContext)
        assert result.system_content
        assert result.messages

    def test_all_params_optional_except_required(self, assembler, sample_messages):
        """Only system_prompt and recent_messages are required."""
        result = assembler.assemble_split(
            system_prompt="You are a helpful assistant.",
            recent_messages=sample_messages,
        )
        assert isinstance(result, AssembledContext)

    def test_rejects_old_session_summary_param(self, assembler, sample_messages):
        """Old session_summary parameter should not be accepted."""
        with pytest.raises(TypeError):
            assembler.assemble_split(
                system_prompt="You are a helpful assistant.",
                recent_messages=sample_messages,
                session_summary="old param",
            )

    def test_rejects_old_few_shot_examples_param(self, assembler, sample_messages):
        """Old few_shot_examples parameter should not be accepted."""
        with pytest.raises(TypeError):
            assembler.assemble_split(
                system_prompt="You are a helpful assistant.",
                recent_messages=sample_messages,
                few_shot_examples=[{"role": "user", "content": "Hi"}],
            )


# ---------------------------------------------------------------------------
# assemble() wrapper
# ---------------------------------------------------------------------------


class TestAssembleWrapper:
    """Tests for the assemble() convenience wrapper."""

    def test_returns_message_list_with_system(self, assembler, sample_messages):
        """assemble() returns a flat message list starting with system message."""
        result = assembler.assemble(
            system_prompt="You are a helpful assistant.",
            recent_messages=sample_messages,
        )
        assert isinstance(result, list)
        assert result[0]["role"] == "system"
        assert "You are a helpful assistant." in result[0]["content"]

    def test_passes_new_params_through(self, assembler, sample_messages):
        """assemble() forwards stream_context, procedural_rules, episodic_summary."""
        result = assembler.assemble(
            system_prompt="Test prompt.",
            recent_messages=sample_messages,
            stream_context="Streaming now",
            procedural_rules="Rule set",
            episodic_summary="Past sessions",
        )
        assert isinstance(result, list)
        assert result[0]["role"] == "system"


# ---------------------------------------------------------------------------
# System content assembly order
# ---------------------------------------------------------------------------


class TestSystemContentAssembly:
    """Tests for the assembly order of system content components."""

    def test_stream_context_included(self, large_assembler, sample_messages):
        """Stream context appears in system content with correct header."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            stream_context="Currently streaming on YouTube, 50 viewers",
        )
        assert "[Current Stream Status]" in result.system_content
        assert "Currently streaming on YouTube" in result.system_content

    def test_procedural_rules_included(self, large_assembler, sample_messages):
        """Procedural rules appear in system content (no extra header, already formatted)."""
        rules_text = "[Behavioral Rules]\n- Always greet by name\n- Be friendly"
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            procedural_rules=rules_text,
        )
        assert rules_text in result.system_content

    def test_episodic_summary_included(self, large_assembler, sample_messages):
        """Episodic summary appears with correct header."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            episodic_summary="In a previous session, user talked about cats.",
        )
        assert "[Previous sessions]" in result.system_content
        assert "user talked about cats" in result.system_content

    def test_entity_profile_included(
        self, large_assembler, sample_messages, sample_entity_profile
    ):
        """Entity profile still works with correct header."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            entity_profile=sample_entity_profile,
        )
        assert "[About the person you're talking to]" in result.system_content
        assert "TestUser" in result.system_content

    def test_retrieved_memories_included(
        self, large_assembler, sample_messages, sample_retrieval_results
    ):
        """Retrieved memories still work with correct header."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            retrieved_memories=sample_retrieval_results,
        )
        assert "[Relevant memories]" in result.system_content
        assert "RPG games" in result.system_content

    def test_assembly_order(
        self,
        large_assembler,
        sample_messages,
        sample_entity_profile,
        sample_retrieval_results,
    ):
        """Components appear in correct order in system content."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            stream_context="Stream status info",
            entity_profile=sample_entity_profile,
            procedural_rules="[Behavioral Rules]\nRule text here",
            retrieved_memories=sample_retrieval_results,
            episodic_summary="Previous session summary",
        )

        content = result.system_content
        # Verify ordering: system_prompt < stream_context < entity_profile
        #   < procedural < memories < episodic
        idx_prompt = content.index("Base prompt.")
        idx_stream = content.index("[Current Stream Status]")
        idx_profile = content.index("[About the person you're talking to]")
        idx_procedural = content.index("[Behavioral Rules]")
        idx_memories = content.index("[Relevant memories]")
        idx_episodic = content.index("[Previous sessions]")

        assert idx_prompt < idx_stream
        assert idx_stream < idx_profile
        assert idx_profile < idx_procedural
        assert idx_procedural < idx_memories
        assert idx_memories < idx_episodic

    def test_empty_optional_params_not_included(self, large_assembler, sample_messages):
        """Empty/default optional params do not add headers to system content."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
        )
        assert "[Current Stream Status]" not in result.system_content
        assert "[About the person you're talking to]" not in result.system_content
        assert "[Behavioral Rules]" not in result.system_content
        assert "[Relevant memories]" not in result.system_content
        assert "[Previous sessions]" not in result.system_content

    def test_whitespace_only_stream_context_not_included(
        self, large_assembler, sample_messages
    ):
        """Whitespace-only stream_context is treated as absent."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            stream_context="   ",
        )
        assert "[Current Stream Status]" not in result.system_content

    def test_whitespace_only_procedural_not_included(
        self, large_assembler, sample_messages
    ):
        """Whitespace-only procedural_rules is treated as absent."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            procedural_rules="  \n  ",
        )
        # No procedural section added
        assert result.system_content.strip() == "Base prompt."

    def test_whitespace_only_episodic_not_included(
        self, large_assembler, sample_messages
    ):
        """Whitespace-only episodic_summary is treated as absent."""
        result = large_assembler.assemble_split(
            system_prompt="Base prompt.",
            recent_messages=sample_messages,
            episodic_summary="   ",
        )
        assert "[Previous sessions]" not in result.system_content


# ---------------------------------------------------------------------------
# _calculate_budgets() with new field names
# ---------------------------------------------------------------------------


class TestCalculateBudgets:
    """Tests for _calculate_budgets() with Phase 2 fields."""

    def test_all_components_present(self, assembler):
        """All budget keys present when all components are provided."""
        budgets = assembler._calculate_budgets(
            has_profile=True,
            has_stream_context=True,
            has_procedural=True,
            has_memories=True,
            has_episodic=True,
        )
        expected_keys = {
            "system_prompt",
            "stream_context",
            "entity_profile",
            "procedural",
            "retrieved_memories",
            "recent_messages",
            "episodic",
        }
        assert set(budgets.keys()) == expected_keys
        assert all(v > 0 for v in budgets.values())

    def test_no_old_field_names(self, assembler):
        """Budget dict does not contain old Phase 1 field names."""
        budgets = assembler._calculate_budgets(
            has_profile=True,
            has_stream_context=True,
            has_procedural=True,
            has_memories=True,
            has_episodic=True,
        )
        assert "session_summary" not in budgets
        assert "few_shot_examples" not in budgets

    def test_unused_stream_context_redistributed_to_messages(self, assembler):
        """When stream_context is absent, its budget goes to recent_messages."""
        budgets_with = assembler._calculate_budgets(
            has_profile=False,
            has_stream_context=True,
            has_procedural=False,
            has_memories=False,
            has_episodic=False,
        )
        budgets_without = assembler._calculate_budgets(
            has_profile=False,
            has_stream_context=False,
            has_procedural=False,
            has_memories=False,
            has_episodic=False,
        )
        assert budgets_without["recent_messages"] > budgets_with["recent_messages"]
        assert budgets_without["stream_context"] == 0

    def test_unused_procedural_redistributed_to_messages(self, assembler):
        """When procedural is absent, its budget goes to recent_messages."""
        budgets_with = assembler._calculate_budgets(
            has_profile=False,
            has_stream_context=False,
            has_procedural=True,
            has_memories=False,
            has_episodic=False,
        )
        budgets_without = assembler._calculate_budgets(
            has_profile=False,
            has_stream_context=False,
            has_procedural=False,
            has_memories=False,
            has_episodic=False,
        )
        assert budgets_without["recent_messages"] > budgets_with["recent_messages"]
        assert budgets_without["procedural"] == 0

    def test_unused_episodic_redistributed_to_messages(self, assembler):
        """When episodic is absent, its budget goes to recent_messages."""
        budgets_with = assembler._calculate_budgets(
            has_profile=False,
            has_stream_context=False,
            has_procedural=False,
            has_memories=False,
            has_episodic=True,
        )
        budgets_without = assembler._calculate_budgets(
            has_profile=False,
            has_stream_context=False,
            has_procedural=False,
            has_memories=False,
            has_episodic=False,
        )
        assert budgets_without["recent_messages"] > budgets_with["recent_messages"]
        assert budgets_without["episodic"] == 0

    def test_unused_profile_redistributed_to_memories(self, assembler):
        """When profile is absent, its budget goes to retrieved_memories if present."""
        budgets_with_profile = assembler._calculate_budgets(
            has_profile=True,
            has_stream_context=False,
            has_procedural=False,
            has_memories=True,
            has_episodic=False,
        )
        budgets_without_profile = assembler._calculate_budgets(
            has_profile=False,
            has_stream_context=False,
            has_procedural=False,
            has_memories=True,
            has_episodic=False,
        )
        assert (
            budgets_without_profile["retrieved_memories"]
            > budgets_with_profile["retrieved_memories"]
        )
        assert budgets_without_profile["entity_profile"] == 0

    def test_unused_profile_no_memories_goes_to_messages(self, assembler):
        """When profile is absent and no memories, profile budget goes to messages."""
        budgets_nothing = assembler._calculate_budgets(
            has_profile=False,
            has_stream_context=False,
            has_procedural=False,
            has_memories=False,
            has_episodic=False,
        )
        # All optional budgets should go to recent_messages
        assert budgets_nothing["entity_profile"] == 0
        assert budgets_nothing["stream_context"] == 0
        assert budgets_nothing["procedural"] == 0
        assert budgets_nothing["retrieved_memories"] == 0
        assert budgets_nothing["episodic"] == 0
        assert budgets_nothing["recent_messages"] > 0

    def test_budget_sum_does_not_exceed_available(self, assembler):
        """Total budget allocations should not exceed available tokens."""
        budgets = assembler._calculate_budgets(
            has_profile=True,
            has_stream_context=True,
            has_procedural=True,
            has_memories=True,
            has_episodic=True,
        )
        total = sum(budgets.values())
        available = int(assembler.total_tokens * 0.9)  # 10% response reserve
        assert total <= available


# ---------------------------------------------------------------------------
# _format_few_shot_examples removed
# ---------------------------------------------------------------------------


class TestRemovedMethods:
    """Tests verifying old methods have been removed."""

    def test_format_few_shot_examples_removed(self, assembler):
        """_format_few_shot_examples() should no longer exist."""
        assert not hasattr(assembler, "_format_few_shot_examples")


# ---------------------------------------------------------------------------
# Full integration: all components together
# ---------------------------------------------------------------------------


class TestFullAssembly:
    """Integration tests with all Phase 2 components."""

    def test_all_components_assembled(
        self,
        large_assembler,
        sample_messages,
        sample_entity_profile,
        sample_retrieval_results,
    ):
        """All Phase 2 components assemble correctly together."""
        result = large_assembler.assemble_split(
            system_prompt="You are Aria, a friendly VTuber AI.",
            recent_messages=sample_messages,
            entity_profile=sample_entity_profile,
            stream_context="Live on YouTube, playing Final Fantasy",
            procedural_rules="[Behavioral Rules]\n- Greet users warmly\n- Use emotes",
            episodic_summary="Last session: discussed favorite anime, user likes Ghibli",
            retrieved_memories=sample_retrieval_results,
        )

        # System content should contain all components
        sc = result.system_content
        assert "Aria" in sc
        assert "Live on YouTube" in sc
        assert "TestUser" in sc
        assert "Greet users warmly" in sc
        assert "RPG games" in sc
        assert "Ghibli" in sc

        # Messages should be preserved
        assert len(result.messages) > 0

    def test_assemble_flat_with_all_components(
        self,
        large_assembler,
        sample_messages,
        sample_entity_profile,
        sample_retrieval_results,
    ):
        """assemble() flat wrapper works with all components."""
        result = large_assembler.assemble(
            system_prompt="You are Aria.",
            recent_messages=sample_messages,
            entity_profile=sample_entity_profile,
            stream_context="Streaming now",
            procedural_rules="Be polite",
            episodic_summary="Past context",
            retrieved_memories=sample_retrieval_results,
        )

        assert result[0]["role"] == "system"
        assert "Aria" in result[0]["content"]
        # Conversation messages follow
        assert len(result) > 1

    def test_returns_assembled_context_type(self, assembler, sample_messages):
        """assemble_split returns AssembledContext dataclass."""
        result = assembler.assemble_split(
            system_prompt="Test",
            recent_messages=sample_messages,
        )
        assert isinstance(result, AssembledContext)
        assert isinstance(result.system_content, str)
        assert isinstance(result.messages, list)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_messages(self, assembler):
        """Works with empty message list."""
        result = assembler.assemble_split(
            system_prompt="Test prompt.",
            recent_messages=[],
        )
        assert isinstance(result, AssembledContext)
        assert result.messages == []

    def test_none_retrieval_results(self, assembler, sample_messages):
        """Works with None retrieval results."""
        result = assembler.assemble_split(
            system_prompt="Test prompt.",
            recent_messages=sample_messages,
            retrieved_memories=None,
        )
        assert "[Relevant memories]" not in result.system_content

    def test_empty_retrieval_results(self, assembler, sample_messages):
        """Works with empty retrieval results list."""
        result = assembler.assemble_split(
            system_prompt="Test prompt.",
            recent_messages=sample_messages,
            retrieved_memories=[],
        )
        assert "[Relevant memories]" not in result.system_content

    def test_only_system_prompt_and_messages(self, assembler, sample_messages):
        """Minimal usage: just system prompt and messages."""
        result = assembler.assemble_split(
            system_prompt="Minimal prompt.",
            recent_messages=sample_messages,
        )
        assert "Minimal prompt." in result.system_content
        assert len(result.messages) > 0

    def test_custom_budget_allocation(self, token_counter, sample_messages):
        """Works with custom BudgetAllocation."""
        custom_budget = BudgetAllocation(
            system_prompt=0.20,
            stream_context=0.05,
            entity_profile=0.05,
            procedural=0.05,
            retrieved_memories=0.10,
            recent_messages=0.35,
            episodic=0.10,
            response_reserve=0.10,
        )
        asm = ContextAssembler(
            total_tokens=8192,
            token_counter=token_counter,
            budget=custom_budget,
        )
        result = asm.assemble_split(
            system_prompt="Custom budget test.",
            recent_messages=sample_messages,
            stream_context="Custom stream",
        )
        assert isinstance(result, AssembledContext)
