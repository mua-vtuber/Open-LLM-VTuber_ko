"""
UMSA - Unified Memory System Architecture

A five-layer memory system for AI companions, providing token-budgeted
context assembly, memory extraction, hybrid retrieval, and consolidation.

Phase 1: Foundation - Token-budgeted context management
"""

from .models import Message, MemoryType, SemanticMemory, Episode, EntityProfile, RetrievalResult
from .config import MemoryConfig
from .embedding import EmbeddingService
from .evolution import MemoryEvolver
from .extraction import MemoryExtractor
from .memory_service import MemoryService, MemoryServiceInterface
from .retrieval import HybridRetriever
from .working_memory import WorkingMemory
from .context_assembler import AssembledContext, ContextAssembler
from .token_counter import TokenCounter

__all__ = [
    "Message",
    "MemoryType",
    "SemanticMemory",
    "Episode",
    "EntityProfile",
    "RetrievalResult",
    "MemoryConfig",
    "EmbeddingService",
    "MemoryEvolver",
    "MemoryExtractor",
    "HybridRetriever",
    "MemoryService",
    "MemoryServiceInterface",
    "WorkingMemory",
    "AssembledContext",
    "ContextAssembler",
    "TokenCounter",
]
