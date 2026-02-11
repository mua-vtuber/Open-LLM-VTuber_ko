"""Hybrid retrieval with Stanford 3-factor scoring.

Combines three retrieval sources:
- Vector search: cosine similarity on embeddings stored in SQLite
- FTS5 search: SQLite full-text search on knowledge_nodes.content
- Graph traversal: follow knowledge_edges from recently accessed nodes

Results are scored using Stanford's 3-factor model:
  score = (recency_weight * recency) + (relevance_weight * relevance) + (importance_weight * importance)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from loguru import logger

from .config import RetrievalConfig
from .embedding import EmbeddingService
from .models import RetrievalResult
from .storage.sqlite_store import SQLiteStore


class HybridRetriever:
    """Hybrid retrieval combining vector, FTS5, and graph sources.

    Uses Stanford 3-factor scoring (recency, relevance, importance)
    with configurable weights for each retrieval source.
    """

    # Stanford scoring weights
    RECENCY_WEIGHT = 0.3
    RELEVANCE_WEIGHT = 0.5
    IMPORTANCE_WEIGHT = 0.2

    # Recency decay: half-life in hours
    RECENCY_HALF_LIFE_HOURS = 720.0  # 30 days

    def __init__(
        self,
        store: SQLiteStore,
        embedding_service: EmbeddingService,
        config: RetrievalConfig | None = None,
    ):
        """Initialize hybrid retriever.

        Args:
            store: SQLite store for data access
            embedding_service: Embedding service for query encoding
            config: Retrieval configuration
        """
        self._store = store
        self._embedding = embedding_service
        self._config = config or RetrievalConfig()

    async def retrieve(
        self,
        query: str,
        entity_id: str | None = None,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant memories using hybrid search.

        Args:
            query: Search query text
            entity_id: Optional entity filter
            top_k: Number of results (defaults to config.top_k)

        Returns:
            Ranked list of RetrievalResult
        """
        top_k = top_k or self._config.top_k

        # Run all three sources
        vector_results = await self._vector_search(query, entity_id)
        fts_results = await self._fts_search(query, entity_id)
        graph_results = await self._graph_search(query, entity_id)

        # Merge and deduplicate
        merged = self._merge_results(
            vector_results, fts_results, graph_results,
        )

        # Sort by final score descending and limit
        merged.sort(key=lambda r: r.score, reverse=True)
        results = merged[:top_k]

        # Touch accessed nodes to update recency
        for result in results:
            try:
                await self._store.touch_node(result.id)
            except Exception:
                pass

        logger.info(
            f"Retrieved {len(results)} memories "
            f"(vector={len(vector_results)}, fts={len(fts_results)}, "
            f"graph={len(graph_results)})"
        )
        return results

    async def _vector_search(
        self, query: str, entity_id: str | None,
    ) -> list[RetrievalResult]:
        """Search by embedding cosine similarity."""
        try:
            query_embedding = self._embedding.encode_single(query)
        except Exception as e:
            logger.warning(f"Embedding encode failed: {e}")
            return []

        if not query_embedding:
            return []

        try:
            nodes = await self._store.get_all_embeddings(entity_id)
        except Exception as e:
            logger.warning(f"Failed to load embeddings: {e}")
            return []

        results: list[RetrievalResult] = []
        for node in nodes:
            blob = node.get("embedding")
            if not blob:
                continue

            node_embedding = EmbeddingService.deserialize_embedding(blob)
            relevance = EmbeddingService.cosine_similarity(
                query_embedding, node_embedding,
            )

            recency = self._compute_recency(node.get("last_accessed_at"))
            importance = node.get("importance", 0.5)

            score = self._stanford_score(recency, relevance, importance)

            results.append(RetrievalResult(
                id=node["node_id"],
                content=node["content"],
                memory_type="semantic",
                score=score,
                source="vector",
                metadata={"relevance": relevance, "recency": recency},
            ))

        return results

    async def _fts_search(
        self, query: str, entity_id: str | None,
    ) -> list[RetrievalResult]:
        """Search using SQLite FTS5."""
        # Sanitize query for FTS5
        fts_query = self._sanitize_fts_query(query)
        if not fts_query:
            return []

        try:
            rows = await self._store.search_fts(
                fts_query, entity_id, limit=self._config.top_k * 2,
            )
        except Exception as e:
            logger.warning(f"FTS search failed: {e}")
            return []

        results: list[RetrievalResult] = []
        for row in rows:
            # FTS5 rank is negative (lower = better), normalize to 0..1
            fts_rank = abs(row.get("fts_rank", 0))
            relevance = min(1.0, fts_rank / 10.0) if fts_rank > 0 else 0.5

            recency = self._compute_recency(row.get("last_accessed_at"))
            importance = row.get("importance", 0.5)

            score = self._stanford_score(recency, relevance, importance)

            results.append(RetrievalResult(
                id=row["node_id"],
                content=row["content"],
                memory_type="semantic",
                score=score,
                source="fts",
                metadata={"fts_rank": row.get("fts_rank")},
            ))

        return results

    async def _graph_search(
        self, query: str, entity_id: str | None,
    ) -> list[RetrievalResult]:
        """Search by traversing knowledge graph edges from recent nodes."""
        # Get recently accessed nodes as seed
        try:
            recent_nodes = await self._store.get_knowledge_nodes(
                entity_id, limit=5,
            )
        except Exception as e:
            logger.warning(f"Failed to get recent nodes for graph search: {e}")
            return []

        if not recent_nodes:
            return []

        results: list[RetrievalResult] = []
        seen_ids: set[str] = set()

        for seed_node in recent_nodes:
            try:
                connected = await self._store.get_connected_nodes(
                    seed_node["node_id"], limit=5,
                )
            except Exception:
                continue

            for node in connected:
                nid = node["node_id"]
                if nid in seen_ids:
                    continue
                seen_ids.add(nid)

                recency = self._compute_recency(node.get("last_accessed_at"))
                importance = node.get("importance", 0.5)
                edge_strength = node.get("edge_strength", 0.5)

                # Use edge_strength as relevance proxy for graph results
                score = self._stanford_score(recency, edge_strength, importance)

                results.append(RetrievalResult(
                    id=nid,
                    content=node["content"],
                    memory_type="semantic",
                    score=score,
                    source="graph",
                    metadata={
                        "edge_type": node.get("edge_type"),
                        "edge_strength": edge_strength,
                    },
                ))

        return results

    def _merge_results(
        self,
        vector_results: list[RetrievalResult],
        fts_results: list[RetrievalResult],
        graph_results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """Merge results from multiple sources, dedup by ID.

        When a memory appears in multiple sources, combine scores
        using configured source weights.
        """
        vw = self._config.vector_weight
        fw = self._config.fts_weight
        gw = self._config.graph_weight

        # Collect by node_id
        by_id: dict[str, dict] = {}

        for r in vector_results:
            if r.id not in by_id:
                by_id[r.id] = {"result": r, "scores": {}}
            by_id[r.id]["scores"]["vector"] = r.score

        for r in fts_results:
            if r.id not in by_id:
                by_id[r.id] = {"result": r, "scores": {}}
            by_id[r.id]["scores"]["fts"] = r.score

        for r in graph_results:
            if r.id not in by_id:
                by_id[r.id] = {"result": r, "scores": {}}
            by_id[r.id]["scores"]["graph"] = r.score

        merged: list[RetrievalResult] = []
        for entry in by_id.values():
            scores = entry["scores"]
            result: RetrievalResult = entry["result"]

            # Weighted fusion across sources
            combined = (
                vw * scores.get("vector", 0.0)
                + fw * scores.get("fts", 0.0)
                + gw * scores.get("graph", 0.0)
            )
            # Normalize by sum of active weights
            active_weight = sum(
                w for w, k in [(vw, "vector"), (fw, "fts"), (gw, "graph")]
                if k in scores
            )
            if active_weight > 0:
                combined /= active_weight

            result.score = combined
            sources = list(scores.keys())
            result.source = "+".join(sources) if len(sources) > 1 else sources[0]
            merged.append(result)

        return merged

    def _stanford_score(
        self, recency: float, relevance: float, importance: float,
    ) -> float:
        """Compute Stanford 3-factor score.

        Args:
            recency: Recency score (0.0 to 1.0)
            relevance: Relevance score (0.0 to 1.0)
            importance: Importance score (0.0 to 1.0)

        Returns:
            Combined score
        """
        return (
            self.RECENCY_WEIGHT * recency
            + self.RELEVANCE_WEIGHT * relevance
            + self.IMPORTANCE_WEIGHT * importance
        )

    def _compute_recency(self, last_accessed_at: str | None) -> float:
        """Compute recency score with exponential decay.

        Args:
            last_accessed_at: ISO timestamp of last access

        Returns:
            Recency score (0.0 to 1.0), 1.0 = very recent
        """
        if not last_accessed_at:
            return 0.3  # Default for never-accessed

        try:
            accessed = datetime.fromisoformat(last_accessed_at)
            if accessed.tzinfo is None:
                accessed = accessed.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_ago = (now - accessed).total_seconds() / 3600.0
        except (ValueError, TypeError):
            return 0.3

        # Exponential decay: score = 2^(-hours / half_life)
        decay = math.pow(2.0, -hours_ago / self.RECENCY_HALF_LIFE_HOURS)
        return max(0.0, min(1.0, decay))

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Sanitize query string for FTS5 syntax.

        Wraps each word in double quotes to prevent FTS5 syntax errors
        from special characters.

        Args:
            query: Raw query string

        Returns:
            FTS5-safe query string
        """
        words = query.split()
        if not words:
            return ""
        # Quote each word and join with OR
        safe_words = [f'"{w}"' for w in words if w.strip()]
        return " OR ".join(safe_words)
