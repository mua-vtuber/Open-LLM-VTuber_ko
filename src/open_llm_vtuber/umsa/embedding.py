"""Embedding service for UMSA.

Provides vector embeddings for memory content using sentence-transformers.
Lazy-loads the model on first use to avoid startup overhead.
Batches encoding for efficiency and queues work between conversation turns
to prevent GPU contention during real-time conversation.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from loguru import logger

from .config import EmbeddingConfig

if TYPE_CHECKING:
    import numpy as np


class EmbeddingService:
    """Embedding service using sentence-transformers.

    Features:
    - Lazy model loading (only when first embedding is requested)
    - Batch encoding for efficiency
    - Serialization helpers for SQLite BLOB storage
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        """Initialize embedding service.

        Args:
            config: Embedding configuration
        """
        self._config = config or EmbeddingConfig()
        self._model = None
        self._dimension = self._config.dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def _ensure_model(self) -> None:
        """Lazy-load the sentence-transformers model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for EmbeddingService. "
                "Install with: pip install sentence-transformers"
            )

        logger.info(f"Loading embedding model: {self._config.model}")
        self._model = SentenceTransformer(
            self._config.model,
            trust_remote_code=self._config.trust_remote_code,
        )
        # Update dimension from actual model
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info(
            f"Embedding model loaded: dim={self._dimension}"
        )

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts into embedding vectors.

        Args:
            texts: List of text strings to encode

        Returns:
            List of embedding vectors (each a list of floats)
        """
        if not texts:
            return []

        self._ensure_model()

        embeddings: np.ndarray = self._model.encode(
            texts, batch_size=32, show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text into an embedding vector.

        Args:
            text: Text string to encode

        Returns:
            Embedding vector as list of floats
        """
        results = self.encode([text])
        return results[0] if results else []

    @staticmethod
    def serialize_embedding(embedding: list[float]) -> bytes:
        """Serialize embedding to bytes for SQLite BLOB storage.

        Args:
            embedding: Embedding vector as list of floats

        Returns:
            Packed bytes (little-endian float32)
        """
        return struct.pack(f"<{len(embedding)}f", *embedding)

    @staticmethod
    def deserialize_embedding(blob: bytes) -> list[float]:
        """Deserialize embedding from SQLite BLOB.

        Args:
            blob: Packed bytes from SQLite

        Returns:
            Embedding vector as list of floats
        """
        count = len(blob) // 4  # float32 = 4 bytes
        return list(struct.unpack(f"<{count}f", blob))

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Assumes vectors are already normalized (which they are from encode()).

        Args:
            a: First vector
            b: Second vector

        Returns:
            Cosine similarity score (-1.0 to 1.0)
        """
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        return dot
