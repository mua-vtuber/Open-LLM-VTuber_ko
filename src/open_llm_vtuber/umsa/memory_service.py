"""Memory Service - Facade for unified memory system.

This module provides the main MemoryService class that consuming applications use.
Provides token-budgeted context building, memory extraction, hybrid retrieval,
and session management.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from loguru import logger

from .config import MemoryConfig
from .context_assembler import AssembledContext, ContextAssembler
from .embedding import EmbeddingService
from .evolution import MemoryEvolver
from .extraction import MemoryExtractor
from .models import Message, SemanticMemory
from .retrieval import HybridRetriever
from .storage.sqlite_store import SQLiteStore
from .token_counter import TokenCounter
from .working_memory import WorkingMemory


class MemoryServiceInterface(Protocol):
    """Protocol defining the full MemoryService API."""

    async def build_context(
        self,
        messages: list[dict],
        entity_id: str | None = None,
        system_prompt: str = "",
        max_tokens: int = 4096,
    ) -> AssembledContext:
        """Build token-budgeted context from messages and system prompt."""
        ...

    async def process_turn(
        self,
        user_message: Message,
        assistant_message: Message,
        entity_id: str | None = None,
    ) -> None:
        """Process a conversation turn for memory extraction."""
        ...

    async def start_session(
        self,
        entity_id: str | None = None,
        platform: str = "direct",
    ) -> str:
        """Start a new conversation session."""
        ...

    async def end_session(self, session_id: str) -> None:
        """End a conversation session."""
        ...

    async def search_memories(
        self,
        query: str,
        entity_id: str | None = None,
        top_k: int = 10,
    ) -> list[SemanticMemory]:
        """Search semantic memories by query."""
        ...

    async def add_memory(self, memory: SemanticMemory) -> str:
        """Add a semantic memory."""
        ...

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a semantic memory."""
        ...

    async def get_all_memories(
        self, entity_id: str | None = None
    ) -> list[dict]:
        """Get all memories, optionally filtered by entity."""
        ...

    async def delete_all_memories(
        self, entity_id: str | None = None
    ) -> bool:
        """Delete all memories, optionally filtered by entity."""
        ...


class MemoryService:
    """Main memory service facade.

    Provides:
    - Token-budgeted context building with memory retrieval
    - Memory extraction from conversation turns
    - Hybrid retrieval (vector + FTS5 + graph) with Stanford 3-factor scoring
    - Session lifecycle tracking
    - Memory CRUD operations

    All components are lazily initialized on first use.
    """

    def __init__(self, config: MemoryConfig | None = None):
        """Initialize memory service.

        Args:
            config: Memory configuration (uses defaults if not provided)
        """
        self.config = config or MemoryConfig()
        self._working_memory: WorkingMemory | None = None
        self._context_assembler: ContextAssembler | None = None
        self._token_counter: TokenCounter | None = None
        self._store: SQLiteStore | None = None
        self._store_initialized: bool = False
        self._extractor: MemoryExtractor | None = None
        self._embedding_service: EmbeddingService | None = None
        self._retriever: HybridRetriever | None = None
        self._evolver: MemoryEvolver | None = None
        self._active_sessions: dict[str, dict] = {}

        logger.debug(
            f"MemoryService full config: {self.config.model_dump()}"
        )
        logger.info(
            f"MemoryService initialized: enabled={self.config.enabled}, "
            f"sqlite_db_path={self.config.storage.sqlite_db_path!r}"
        )

    def set_llm(self, llm) -> None:
        """Set the LLM instance for extraction (called after agent creation).

        Args:
            llm: StatelessLLMInterface instance shared with the agent
        """
        if self.config.extraction.enabled:
            self._extractor = MemoryExtractor(
                llm=llm, config=self.config.extraction,
            )
            logger.info("MemoryExtractor initialized with shared LLM")

    def _ensure_components(self) -> None:
        """Lazy initialization of context assembly components."""
        if self._working_memory is None:
            self._working_memory = WorkingMemory(
                max_tokens=self.config.context.default_budget_tokens
            )
            logger.debug("WorkingMemory initialized")

        if self._token_counter is None:
            self._token_counter = TokenCounter(
                model="gpt-3.5-turbo"
            )
            logger.debug("TokenCounter initialized")

        if self._context_assembler is None:
            self._context_assembler = ContextAssembler(
                total_tokens=self.config.context.default_budget_tokens,
                token_counter=self._token_counter,
                budget=self.config.context.budget_allocation,
            )
            logger.debug("ContextAssembler initialized")

    async def _ensure_store(self) -> SQLiteStore:
        """Lazy initialization of SQLite store."""
        if self._store is None:
            db_path = self.config.storage.sqlite_db_path
            self._store = SQLiteStore(db_path=db_path)
        if not self._store_initialized:
            await self._store.initialize()
            self._store_initialized = True
            logger.debug(f"SQLiteStore initialized at {self.config.storage.sqlite_db_path}")
        return self._store

    async def _ensure_retriever(self) -> HybridRetriever:
        """Lazy initialization of embedding service and hybrid retriever."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService(
                config=self.config.embedding,
            )
            logger.debug("EmbeddingService initialized")

        if self._retriever is None:
            store = await self._ensure_store()
            self._retriever = HybridRetriever(
                store=store,
                embedding_service=self._embedding_service,
                config=self.config.retrieval,
            )
            logger.debug("HybridRetriever initialized")

        return self._retriever

    async def _ensure_evolver(self) -> MemoryEvolver:
        """Lazy initialization of memory evolver."""
        if self._evolver is None:
            if self._embedding_service is None:
                self._embedding_service = EmbeddingService(
                    config=self.config.embedding,
                )
            store = await self._ensure_store()
            self._evolver = MemoryEvolver(
                store=store,
                embedding_service=self._embedding_service,
                config=self.config.consolidation,
            )
            logger.debug("MemoryEvolver initialized")
        return self._evolver

    async def close(self) -> None:
        """Close resources (SQLite connection, etc.)."""
        if self._store and self._store_initialized:
            await self._store.close()
            self._store_initialized = False
            logger.info("MemoryService: SQLiteStore closed")

    async def build_context(
        self,
        messages: list[dict],
        entity_id: str | None = None,
        system_prompt: str = "",
        max_tokens: int = 4096,
    ) -> AssembledContext:
        """Build token-budgeted context with memory retrieval.

        Retrieves relevant memories from long-term storage using hybrid search
        (vector + FTS5 + graph with Stanford 3-factor scoring), then assembles
        everything within the token budget.

        Args:
            messages: Recent conversation messages
            entity_id: Optional entity identifier for personalization
            system_prompt: System instructions to include
            max_tokens: Maximum token budget for context

        Returns:
            AssembledContext with system_content and messages separated
        """
        self._ensure_components()

        logger.debug(
            f"Building context: {len(messages)} messages, "
            f"max_tokens={max_tokens}, entity_id={entity_id}"
        )

        # Retrieve relevant memories from recent user messages
        retrieved_memories = []
        if messages:
            query_parts = [
                msg["content"] for msg in messages[-3:]
                if msg.get("role") == "user"
                and isinstance(msg.get("content"), str)
            ]
            if query_parts:
                query = " ".join(query_parts)
                try:
                    retriever = await self._ensure_retriever()
                    retrieved_memories = await retriever.retrieve(
                        query=query,
                        entity_id=entity_id,
                        top_k=self.config.retrieval.top_k,
                    )
                    logger.debug(
                        f"Retrieved {len(retrieved_memories)} memories for context"
                    )
                except Exception as e:
                    logger.warning(f"Memory retrieval failed: {e}")

        ctx = self._context_assembler.assemble_split(
            system_prompt=system_prompt,
            recent_messages=messages,
            entity_profile=None,
            session_summary="",
            retrieved_memories=retrieved_memories or None,
            few_shot_examples=None,
        )

        logger.info(
            f"Context built: system={len(ctx.system_content)}chars, "
            f"{len(ctx.messages)} messages "
            f"(from {len(messages)} input, {len(retrieved_memories)} memories)"
        )

        return ctx

    async def process_turn(
        self,
        user_message: Message,
        assistant_message: Message,
        entity_id: str | None = None,
    ) -> None:
        """Process a conversation turn for memory extraction.

        Adds the turn to the extraction buffer. When the buffer reaches
        batch_size, triggers LLM-based extraction and persists results.

        Args:
            user_message: User's message
            assistant_message: Assistant's response
            entity_id: Optional entity identifier
        """
        if not self._extractor:
            logger.debug("process_turn: extractor not available, skipping")
            return

        should_extract = self._extractor.add_turn(
            user_content=user_message.content,
            assistant_content=assistant_message.content,
            entity_id=entity_id,
        )

        if should_extract:
            await self._run_extraction(entity_id)

    async def flush_extraction(self, entity_id: str | None = None) -> None:
        """Force extraction of any remaining buffered turns.

        Called at session end to ensure no turns are lost.

        Args:
            entity_id: Default entity_id for extracted memories
        """
        if self._extractor and self._extractor.buffer_size > 0:
            await self._run_extraction(entity_id)

    async def _run_extraction(self, entity_id: str | None = None) -> None:
        """Run extraction on buffered turns, persist results, and embed."""
        if not self._extractor:
            return

        try:
            result = await self._extractor.extract(
                entity_id=entity_id, force=True,
            )
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return

        if not result.memories:
            return

        # Persist extracted memories to SQLite
        try:
            store = await self._ensure_store()
            for memory in result.memories:
                await store.insert_knowledge_node({
                    "node_id": memory.id,
                    "entity_id": memory.entity_id,
                    "node_type": memory.memory_type.value,
                    "content": memory.content,
                    "importance": memory.importance,
                    "metadata": None,
                })
            logger.info(
                f"Persisted {len(result.memories)} extracted memories to SQLite"
            )
        except Exception as e:
            logger.error(f"Failed to persist extracted memories: {e}")
            return

        # Generate and store embeddings
        try:
            if self._embedding_service is None:
                self._embedding_service = EmbeddingService(
                    config=self.config.embedding,
                )
            contents = [m.content for m in result.memories]
            embeddings = self._embedding_service.encode(contents)
            for memory, embedding in zip(result.memories, embeddings):
                blob = EmbeddingService.serialize_embedding(embedding)
                await store.update_node_embedding(memory.id, blob)
            logger.info(
                f"Embedded {len(embeddings)} extracted memories"
            )
        except Exception as e:
            logger.warning(f"Failed to embed extracted memories: {e}")

    async def start_session(
        self,
        entity_id: str | None = None,
        platform: str = "direct",
    ) -> str:
        """Start a new conversation session.

        Creates a session record in SQLite and tracks it locally.

        Args:
            entity_id: Optional entity identifier
            platform: Platform name

        Returns:
            Session ID
        """
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc).isoformat()

        self._active_sessions[session_id] = {
            "entity_id": entity_id,
            "platform": platform,
            "started_at": started_at,
            "message_count": 0,
        }

        try:
            store = await self._ensure_store()
            await store.insert_session({
                "session_id": session_id,
                "entity_id": entity_id,
                "platform": platform,
                "started_at": started_at,
            })
        except Exception as e:
            logger.warning(f"Failed to persist session to SQLite: {e}")

        logger.info(
            f"Session started: {session_id} "
            f"(entity={entity_id}, platform={platform})"
        )
        return session_id

    async def end_session(self, session_id: str) -> None:
        """End a conversation session.

        Performs full session consolidation:
        1. Persists session end to SQLite
        2. Flushes any remaining extraction buffer
        3. Creates an Episode node summarizing the session
        4. Updates entity profile (touch_entity)
        5. Runs memory evolution (merge + prune)
        6. Writes a consolidation log entry

        Args:
            session_id: Session identifier to end
        """
        session_data = self._active_sessions.pop(session_id, None)
        if session_data is None:
            logger.warning(f"Attempted to end unknown session: {session_id}")
            return

        ended_at = datetime.now(timezone.utc).isoformat()
        message_count = session_data.get("message_count", 0)
        entity_id = session_data.get("entity_id")
        platform = session_data.get("platform", "direct")

        # 1. Persist session end
        try:
            store = await self._ensure_store()
            await store.end_session(
                session_id=session_id,
                ended_at=ended_at,
                message_count=message_count,
            )
        except Exception as e:
            logger.warning(f"Failed to persist session end to SQLite: {e}")

        # 2. Flush remaining extraction buffer
        try:
            await self.flush_extraction(entity_id)
        except Exception as e:
            logger.warning(f"Flush extraction failed at session end: {e}")

        # 3. Create Episode node for this session
        episode_node_id = None
        if message_count > 0:
            try:
                store = await self._ensure_store()
                episode_node_id = f"episode_{session_id}"
                summary = (
                    f"Session {session_id}: {message_count} messages "
                    f"on platform '{platform}'"
                )
                await store.insert_knowledge_node({
                    "node_id": episode_node_id,
                    "entity_id": entity_id,
                    "node_type": "episode",
                    "content": summary,
                    "importance": min(0.3 + message_count * 0.05, 0.9),
                    "metadata": None,
                })
                logger.debug(f"Episode node created: {episode_node_id}")
            except Exception as e:
                logger.warning(f"Failed to create episode node: {e}")
                episode_node_id = None

        # 4. Update entity profile
        if entity_id:
            try:
                store = await self._ensure_store()
                await store.touch_entity(entity_id, platform)
            except Exception as e:
                logger.warning(f"Failed to touch entity profile: {e}")

        # 5. Run memory evolution if consolidation is enabled
        evolution_result = {"merged": 0, "pruned": 0}
        if self.config.consolidation.enabled:
            try:
                evolver = await self._ensure_evolver()
                evolution_result = await evolver.evolve(entity_id=entity_id)
            except Exception as e:
                logger.warning(f"Memory evolution failed: {e}")

        # 6. Write consolidation log
        try:
            store = await self._ensure_store()
            await store.insert_consolidation_log({
                "session_id": session_id,
                "consolidated_at": ended_at,
                "nodes_created": 1 if episode_node_id else 0,
                "edges_created": 0,
                "summary": (
                    f"messages={message_count}, "
                    f"merged={evolution_result['merged']}, "
                    f"pruned={evolution_result['pruned']}"
                ),
            })
        except Exception as e:
            logger.warning(f"Failed to write consolidation log: {e}")

        logger.info(
            f"Session ended: {session_id} (messages={message_count}, "
            f"merged={evolution_result['merged']}, "
            f"pruned={evolution_result['pruned']})"
        )

    def increment_session_message_count(self, session_id: str) -> None:
        """Increment message count for an active session.

        Args:
            session_id: Session identifier
        """
        if session_id in self._active_sessions:
            self._active_sessions[session_id]["message_count"] += 1

    async def search_memories(
        self,
        query: str,
        entity_id: str | None = None,
        top_k: int = 10,
    ) -> list[SemanticMemory]:
        """Search semantic memories using hybrid retrieval.

        Combines vector search, FTS5, and graph traversal with Stanford
        3-factor scoring (recency, relevance, importance).

        Args:
            query: Search query text
            entity_id: Optional entity identifier
            top_k: Number of results

        Returns:
            List of SemanticMemory objects
        """
        try:
            retriever = await self._ensure_retriever()
            results = await retriever.retrieve(
                query=query, entity_id=entity_id, top_k=top_k,
            )
        except Exception as e:
            logger.warning(f"search_memories failed: {e}")
            return []

        memories = []
        for r in results:
            try:
                memories.append(SemanticMemory(
                    id=r.id,
                    content=r.content,
                    importance=r.score,
                ))
            except Exception:
                continue

        logger.info(f"search_memories: {len(memories)} results for '{query[:50]}'")
        return memories

    async def add_memory(self, memory: SemanticMemory) -> str:
        """Add a semantic memory to storage with embedding.

        Args:
            memory: Memory to add

        Returns:
            Memory ID
        """
        store = await self._ensure_store()
        await store.insert_knowledge_node({
            "node_id": memory.id,
            "entity_id": memory.entity_id,
            "node_type": memory.memory_type.value,
            "content": memory.content,
            "importance": memory.importance,
            "metadata": None,
        })

        # Generate and store embedding
        try:
            if self._embedding_service is None:
                self._embedding_service = EmbeddingService(
                    config=self.config.embedding,
                )
            embedding = self._embedding_service.encode_single(memory.content)
            blob = EmbeddingService.serialize_embedding(embedding)
            await store.update_node_embedding(memory.id, blob)
        except Exception as e:
            logger.warning(f"Failed to embed memory {memory.id}: {e}")

        logger.info(f"Memory added: {memory.id}")
        return memory.id

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a semantic memory from storage.

        Args:
            memory_id: ID of memory to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            store = await self._ensure_store()
            deleted = await store.delete_knowledge_node(memory_id)
            logger.info(f"Memory deleted: {memory_id} (found={deleted})")
            return deleted
        except Exception as e:
            logger.warning(f"delete_memory failed: {e}")
            return False

    async def get_all_memories(
        self, entity_id: str | None = None
    ) -> list[dict]:
        """Get all memories from storage.

        Args:
            entity_id: Optional entity identifier to filter by

        Returns:
            List of memory dictionaries
        """
        try:
            store = await self._ensure_store()
            nodes = await store.get_knowledge_nodes(entity_id, limit=1000)
            logger.info(f"get_all_memories: {len(nodes)} memories")
            return nodes
        except Exception as e:
            logger.warning(f"get_all_memories failed: {e}")
            return []

    async def delete_all_memories(
        self, entity_id: str | None = None
    ) -> bool:
        """Delete all memories from storage.

        Args:
            entity_id: Optional entity identifier to filter by

        Returns:
            True if successful
        """
        try:
            store = await self._ensure_store()
            count = await store.delete_knowledge_nodes(entity_id)
            logger.info(f"delete_all_memories: deleted {count} memories")
            return True
        except Exception as e:
            logger.warning(f"delete_all_memories failed: {e}")
            return False
