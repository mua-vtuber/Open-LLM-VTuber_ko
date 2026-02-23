"""A-MEM inspired memory evolution.

Provides two structural evolution operations run at session end:
- Merge: Combine memories with high cosine similarity to reduce redundancy
- Prune: Remove old, unaccessed, low-importance memories

Recency-based decay (reducing retrieval priority of old memories) is already
handled by HybridRetriever's Stanford 3-factor scoring via ``last_accessed_at``.
Evolution only handles structural deduplication and cleanup.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from .config import ConsolidationConfig
from .embedding import EmbeddingService
from .storage.sqlite_store import SQLiteStore


class MemoryEvolver:
    """A-MEM inspired memory evolution.

    Merge: When two memories exceed the similarity threshold, keep the
    higher-importance one and discard the duplicate, recording a
    ``merged_from`` edge in the knowledge graph.

    Prune: Memories that are below the pruning importance threshold,
    have never been retrieved (access_count == 0), and are older than
    twice the configured decay half-life are permanently removed.
    """

    MERGE_SIMILARITY_THRESHOLD = 0.85

    def __init__(
        self,
        store: SQLiteStore,
        embedding_service: EmbeddingService,
        config: ConsolidationConfig | None = None,
    ):
        """Initialize memory evolver.

        Args:
            store: SQLite store for data access
            embedding_service: Embedding service for similarity computation
            config: Consolidation configuration
        """
        self._store = store
        self._embedding = embedding_service
        self._config = config or ConsolidationConfig()

    async def evolve(self, entity_id: str | None = None) -> dict[str, int]:
        """Run all evolution operations.

        Args:
            entity_id: Optional entity filter

        Returns:
            Dict with operation counts: {"merged": N, "pruned": N}
        """
        merge_count = await self._merge_similar(entity_id)
        prune_count = await self._prune_stale(entity_id)

        logger.info(f"Evolution complete: merged={merge_count}, pruned={prune_count}")
        return {"merged": merge_count, "pruned": prune_count}

    async def _merge_similar(self, entity_id: str | None) -> int:
        """Merge memories with high cosine similarity.

        For each pair above the threshold, keep the higher-importance node
        and delete the other, creating a ``merged_from`` edge to preserve
        provenance.
        """
        nodes = await self._store.get_all_embeddings(entity_id)
        if len(nodes) < 2:
            return 0

        # Deserialize embeddings
        node_embeddings: list[tuple[dict, list[float]]] = []
        for node in nodes:
            blob = node.get("embedding")
            if not blob:
                continue
            embedding = EmbeddingService.deserialize_embedding(blob)
            node_embeddings.append((node, embedding))

        if len(node_embeddings) < 2:
            return 0

        # Cap candidates to avoid O(n^2) blow-up on large memory stores
        max_candidates = self._config.max_merge_candidates
        if len(node_embeddings) > max_candidates:
            node_embeddings.sort(
                key=lambda pair: pair[0].get("last_accessed_at") or "",
                reverse=True,
            )
            node_embeddings = node_embeddings[:max_candidates]

        merged_ids: set[str] = set()
        merge_count = 0

        # Pairwise comparison (O(n^2) but n is typically small per entity)
        for i in range(len(node_embeddings)):
            node_a, emb_a = node_embeddings[i]
            if node_a["node_id"] in merged_ids:
                continue

            for j in range(i + 1, len(node_embeddings)):
                node_b, emb_b = node_embeddings[j]
                if node_b["node_id"] in merged_ids:
                    continue

                similarity = EmbeddingService.cosine_similarity(emb_a, emb_b)

                if similarity < self.MERGE_SIMILARITY_THRESHOLD:
                    continue

                # Keep the one with higher importance
                imp_a = node_a.get("importance", 0.5)
                imp_b = node_b.get("importance", 0.5)

                if imp_a >= imp_b:
                    keep, discard = node_a, node_b
                else:
                    keep, discard = node_b, node_a

                # Record merge provenance as a graph edge
                try:
                    await self._store.insert_knowledge_edge(
                        {
                            "edge_id": f"merge_{keep['node_id']}_{discard['node_id']}",
                            "source_node_id": keep["node_id"],
                            "target_node_id": discard["node_id"],
                            "edge_type": "merged_from",
                            "strength": similarity,
                        }
                    )
                except Exception:
                    pass  # Edge creation is best-effort

                # Delete the lower-importance duplicate
                await self._store.delete_knowledge_node(discard["node_id"])
                merged_ids.add(discard["node_id"])
                merge_count += 1

                logger.debug(
                    f"Merged memory {discard['node_id']} into {keep['node_id']} "
                    f"(similarity={similarity:.3f})"
                )

        return merge_count

    async def _prune_stale(self, entity_id: str | None) -> int:
        """Remove old, unaccessed memories with very low importance.

        A memory is pruned when all three conditions are met:
        - importance <= pruning_threshold
        - access_count == 0 (never retrieved)
        - age > 2x decay_half_life_days
        """
        nodes = await self._store.get_knowledge_nodes(entity_id, limit=1000)
        if not nodes:
            return 0

        now = datetime.now(timezone.utc)
        max_age_hours = self._config.decay_half_life_days * 24.0 * 2  # 2x half-life
        prune_count = 0

        for node in nodes:
            importance = node.get("importance", 0.5)
            access_count = node.get("access_count", 0)

            if importance > self._config.pruning_threshold:
                continue

            if access_count > 0:
                continue

            created_at = node.get("created_at")
            if not created_at:
                continue

            try:
                created_dt = datetime.fromisoformat(created_at)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                age_hours = (now - created_dt).total_seconds() / 3600.0
                if age_hours < max_age_hours:
                    continue
            except (ValueError, TypeError):
                continue

            await self._store.delete_knowledge_node(node["node_id"])
            prune_count += 1
            logger.debug(f"Pruned stale memory: {node['node_id']}")

        return prune_count
