import pytest
from open_llm_vtuber.umsa.config import (
    MemoryConfig, StreamContextConfig, ExtractionConfig,
    RetrievalConfig, ConsolidationConfig, BudgetAllocation,
)

def test_stream_context_config_defaults():
    cfg = StreamContextConfig()
    assert cfg.max_events == 20
    assert cfg.topic_change_threshold == 5
    assert cfg.summary_interval == 10

def test_extraction_config_has_regex_and_cli_fields():
    cfg = ExtractionConfig()
    assert cfg.regex_enabled is True
    assert cfg.llm_extraction_mode == "auto"
    assert cfg.cli_command == ""

def test_retrieval_config_has_embedding_provider():
    cfg = RetrievalConfig()
    assert cfg.embedding_provider == "local"
    assert cfg.max_latency_ms == 200

def test_consolidation_config_has_reflection_threshold():
    cfg = ConsolidationConfig()
    assert cfg.reflection_threshold == 10

def test_budget_allocation_phase2_fields():
    b = BudgetAllocation()
    assert hasattr(b, "stream_context")
    assert hasattr(b, "procedural")
    assert hasattr(b, "episodic")
    assert abs(sum([
        b.system_prompt, b.stream_context, b.entity_profile,
        b.procedural, b.retrieved_memories, b.recent_messages,
        b.episodic, b.response_reserve,
    ]) - 1.0) < 0.01

def test_memory_config_has_stream_context():
    cfg = MemoryConfig()
    assert hasattr(cfg, "stream_context")
    assert isinstance(cfg.stream_context, StreamContextConfig)
