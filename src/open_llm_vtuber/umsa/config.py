"""UMSA configuration models."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field, model_validator


class StorageConfig(BaseModel):
    """Storage paths configuration."""

    lance_db_path: str = "./memory/lance_db"
    sqlite_db_path: str = "./memory/umsa.db"

    @model_validator(mode="after")
    def _validate_paths(self) -> "StorageConfig":
        normalized = os.path.normpath(self.sqlite_db_path)
        parts = normalized.replace("\\", "/").split("/")
        if ".." in parts:
            raise ValueError(
                f"sqlite_db_path must not contain '..' components: "
                f"{self.sqlite_db_path!r}"
            )
        self.sqlite_db_path = normalized
        return self


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""

    provider: str = "local"  # "local" or "api"
    model: str = "nomic-ai/nomic-embed-text-v2-moe"
    dimension: int = 768
    trust_remote_code: bool = False


class StreamContextConfig(BaseModel):
    """Stream context tracking configuration."""

    max_events: int = 20
    topic_change_threshold: int = 5
    summary_interval: int = 10


class BudgetAllocation(BaseModel):
    """Token budget allocation percentages (must sum to 1.0)."""

    system_prompt: float = 0.15
    stream_context: float = 0.10
    entity_profile: float = 0.10
    procedural: float = 0.05
    retrieved_memories: float = 0.15
    recent_messages: float = 0.25
    episodic: float = 0.10
    response_reserve: float = 0.10


class ContextConfig(BaseModel):
    """Context assembly configuration."""

    default_budget_tokens: int = 4096
    budget_allocation: BudgetAllocation = Field(default_factory=BudgetAllocation)


class ExtractionConfig(BaseModel):
    """Memory extraction configuration."""

    enabled: bool = True
    batch_size: int = 5
    min_importance: float = 0.3
    confidence_threshold: float = 0.6
    dedup_threshold: float = 0.90
    regex_enabled: bool = True
    llm_extraction_mode: str = "auto"  # "local", "cli", "auto", "disabled"
    cli_command: str = ""


class ConsolidationConfig(BaseModel):
    """Memory consolidation configuration."""

    enabled: bool = True
    interval_hours: int = 6
    episode_compress_threshold: int = 200
    pruning_threshold: float = 0.1
    decay_half_life_days: float = 30.0  # 30 days for general facts
    max_merge_candidates: int = 500
    reflection_threshold: int = 10


class RetrievalConfig(BaseModel):
    """Hybrid retrieval configuration."""

    top_k: int = 10
    vector_weight: float = 0.5
    fts_weight: float = 0.3
    graph_weight: float = 0.2
    embedding_provider: str = "local"  # "local", "api", "disabled"
    max_latency_ms: int = 200


class FewShotConfig(BaseModel):
    """Few-shot example configuration."""

    enabled: bool = True
    max_examples: int = 3
    mmr_lambda: float = 0.6
    min_quality_score: float = 0.5


class MemoryConfig(BaseModel):
    """Top-level UMSA configuration."""

    enabled: bool = False  # Disabled by default until Phase 1 is stable
    storage: StorageConfig = Field(default_factory=StorageConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    consolidation: ConsolidationConfig = Field(default_factory=ConsolidationConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    few_shot: FewShotConfig = Field(default_factory=FewShotConfig)
    stream_context: StreamContextConfig = Field(default_factory=StreamContextConfig)
