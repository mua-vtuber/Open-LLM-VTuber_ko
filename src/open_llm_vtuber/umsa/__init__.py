"""
UMSA - Unified Memory System Architecture

A cognitive memory system for AI companions, providing token-budgeted
context assembly, memory extraction, hybrid retrieval, consolidation,
real-time stream context, procedural memory, and reflection.

Phase 1: Foundation - Token-budgeted context management
Phase 2: Cognitive Memory - Stream context, extraction pipeline, reflection
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
from .stream_context import StreamContext, StreamEvent
from .regex_extractor import RegexExtractor
from .conflict_detector import ConflictDetector
from .procedural_memory import ProceduralMemory
from .reflection import ReflectionEngine

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
    "StreamContext",
    "StreamEvent",
    "RegexExtractor",
    "ConflictDetector",
    "ProceduralMemory",
    "ReflectionEngine",
]
