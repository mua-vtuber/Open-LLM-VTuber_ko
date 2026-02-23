"""SQLite storage backend for UMSA.

This module provides persistent storage for the Unified Memory System Architecture
using SQLite with aiosqlite for async operations.

Phase 1: Schema setup and basic entity CRUD operations.
Phase 2+: Full knowledge graph, session tracking, and consolidation support.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

try:
    import aiosqlite
except ImportError:
    logger.warning(
        "aiosqlite not installed. SQLiteStore will not be available. "
        "Install with: pip install aiosqlite"
    )
    aiosqlite = None


class SQLiteStore:
    """SQLite storage backend for UMSA.

    Provides async CRUD operations for entity profiles, knowledge nodes/edges,
    sessions, sentiment history, and consolidation logs.

    Uses WAL mode for concurrent reads and proper async handling.
    """

    def __init__(self, db_path: str = "./memory/umsa.db"):
        """Initialize SQLite store.

        Args:
            db_path: Path to SQLite database file
        """
        if aiosqlite is None:
            raise ImportError(
                "aiosqlite is required for SQLiteStore. "
                "Install with: pip install aiosqlite"
            )

        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        logger.info(f"SQLiteStore initialized with db_path: {db_path}")

    async def initialize(self) -> None:
        """Create database tables and indexes if they don't exist.

        Creates directory for database file if needed.
        Enables WAL mode for concurrent reads.
        """
        # Create directory if it doesn't exist
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured database directory exists: {db_dir}")

        # Connect to database
        self._db = await aiosqlite.connect(self.db_path)

        # Enable WAL mode for concurrent reads
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")

        # Create tables
        await self._create_tables()
        await self._migrate_knowledge_nodes()
        await self._create_indexes()

        await self._db.commit()
        logger.info("SQLite database initialized successfully")

    async def _create_tables(self) -> None:
        """Create all UMSA tables."""

        # Entity Profiles table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS entity_profiles (
                entity_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                total_interactions INTEGER DEFAULT 0,
                preferred_topics TEXT,
                communication_style TEXT,
                sentiment_baseline REAL DEFAULT 0.0,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Knowledge Nodes table (semantic memories)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                node_id TEXT PRIMARY KEY,
                entity_id TEXT,
                node_type TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL DEFAULT 0.5,
                embedding BLOB,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_accessed_at TEXT,
                access_count INTEGER DEFAULT 0,
                metadata TEXT,
                FOREIGN KEY (entity_id) REFERENCES entity_profiles(entity_id)
                    ON DELETE CASCADE
            )
        """)

        # Knowledge Edges table (relationships between nodes)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_edges (
                edge_id TEXT PRIMARY KEY,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                strength REAL DEFAULT 1.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                FOREIGN KEY (source_node_id) REFERENCES knowledge_nodes(node_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (target_node_id) REFERENCES knowledge_nodes(node_id)
                    ON DELETE CASCADE
            )
        """)

        # Sessions table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                entity_id TEXT,
                platform TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                message_count INTEGER DEFAULT 0,
                sentiment_avg REAL,
                topics TEXT,
                metadata TEXT,
                FOREIGN KEY (entity_id) REFERENCES entity_profiles(entity_id)
                    ON DELETE SET NULL
            )
        """)

        # Sentiment History table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                session_id TEXT,
                timestamp TEXT NOT NULL,
                sentiment_score REAL NOT NULL,
                context TEXT,
                FOREIGN KEY (entity_id) REFERENCES entity_profiles(entity_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            )
        """)

        # Consolidation Log table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS consolidation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                consolidated_at TEXT NOT NULL,
                nodes_created INTEGER DEFAULT 0,
                edges_created INTEGER DEFAULT 0,
                summary TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            )
        """)

        # Example Metadata table (for few-shot learning)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS example_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                example_type TEXT NOT NULL,
                input_text TEXT NOT NULL,
                output_text TEXT NOT NULL,
                quality_score REAL DEFAULT 1.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)

        # FTS5 virtual table for full-text search on knowledge_nodes
        await self._db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_nodes_fts
            USING fts5(content, content=knowledge_nodes, content_rowid=rowid)
        """)

        # Triggers to keep FTS5 in sync with knowledge_nodes
        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS knowledge_nodes_ai AFTER INSERT ON knowledge_nodes BEGIN
                INSERT INTO knowledge_nodes_fts(rowid, content) VALUES (new.rowid, new.content);
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS knowledge_nodes_ad AFTER DELETE ON knowledge_nodes BEGIN
                INSERT INTO knowledge_nodes_fts(knowledge_nodes_fts, rowid, content)
                VALUES('delete', old.rowid, old.content);
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS knowledge_nodes_au AFTER UPDATE ON knowledge_nodes BEGIN
                INSERT INTO knowledge_nodes_fts(knowledge_nodes_fts, rowid, content)
                VALUES('delete', old.rowid, old.content);
                INSERT INTO knowledge_nodes_fts(rowid, content) VALUES (new.rowid, new.content);
            END
        """)

        # Stream Episodes table (Phase 2)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS stream_episodes (
                id TEXT PRIMARY KEY,
                session_id TEXT REFERENCES sessions(session_id),
                summary TEXT NOT NULL,
                topics_json TEXT,
                key_events_json TEXT,
                participant_count INTEGER,
                sentiment TEXT,
                started_at TEXT,
                ended_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Procedural Rules table (Phase 2)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS procedural_rules (
                id TEXT PRIMARY KEY,
                rule_type TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                source TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        logger.debug("All tables created successfully")

    async def _migrate_knowledge_nodes(self) -> None:
        """Add Phase 2 columns to knowledge_nodes if they don't exist."""
        async with self._db.execute("PRAGMA table_info(knowledge_nodes)") as cursor:
            cols = await cursor.fetchall()
        existing = {c[1] for c in cols}
        migrations = [
            ("valid_at", "TEXT"),
            ("invalid_at", "TEXT"),
            ("mention_count", "INTEGER DEFAULT 0"),
            ("last_mentioned_at", "TEXT"),
        ]
        for col_name, col_type in migrations:
            if col_name not in existing:
                await self._db.execute(
                    f"ALTER TABLE knowledge_nodes ADD COLUMN {col_name} {col_type}"
                )
        logger.debug("knowledge_nodes migration check complete")

    async def _create_indexes(self) -> None:
        """Create indexes for performance optimization."""

        # Entity profiles indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_entity_platform
            ON entity_profiles(platform)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_entity_name
            ON entity_profiles(name)
        """)

        # Knowledge nodes indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_node_entity
            ON knowledge_nodes(entity_id)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_node_type
            ON knowledge_nodes(node_type)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_node_importance
            ON knowledge_nodes(importance DESC)
        """)

        # Knowledge edges indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_edge_source
            ON knowledge_edges(source_node_id)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_edge_target
            ON knowledge_edges(target_node_id)
        """)

        # Sessions indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_entity
            ON sessions(entity_id)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_started
            ON sessions(started_at)
        """)

        # Sentiment history indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sentiment_entity
            ON sentiment_history(entity_id)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sentiment_timestamp
            ON sentiment_history(timestamp)
        """)

        logger.debug("All indexes created successfully")

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            logger.info("SQLite database connection closed")

    async def get_entity(self, name: str, platform: str) -> dict | None:
        """Get entity profile by name and platform.

        Args:
            name: Entity name
            platform: Platform identifier

        Returns:
            Entity dictionary or None if not found
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self._db.execute(
            """
            SELECT entity_id, name, platform, first_seen_at, last_seen_at,
                   total_interactions, preferred_topics, communication_style,
                   sentiment_baseline, metadata, created_at, updated_at
            FROM entity_profiles
            WHERE name = ? AND platform = ?
            """,
            (name, platform),
        ) as cursor:
            row = await cursor.fetchone()

            if row is None:
                return None

            return {
                "entity_id": row[0],
                "name": row[1],
                "platform": row[2],
                "first_seen_at": row[3],
                "last_seen_at": row[4],
                "total_interactions": row[5],
                "preferred_topics": row[6],
                "communication_style": row[7],
                "sentiment_baseline": row[8],
                "metadata": row[9],
                "created_at": row[10],
                "updated_at": row[11],
            }

    async def upsert_entity(self, entity: dict) -> str:
        """Insert or update entity profile.

        Args:
            entity: Entity dictionary with required fields

        Returns:
            Entity ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            INSERT INTO entity_profiles (
                entity_id, name, platform, first_seen_at, last_seen_at,
                total_interactions, preferred_topics, communication_style,
                sentiment_baseline, metadata, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(entity_id) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                total_interactions = excluded.total_interactions,
                preferred_topics = excluded.preferred_topics,
                communication_style = excluded.communication_style,
                sentiment_baseline = excluded.sentiment_baseline,
                metadata = excluded.metadata,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                entity["entity_id"],
                entity["name"],
                entity["platform"],
                entity["first_seen_at"],
                entity["last_seen_at"],
                entity.get("total_interactions", 0),
                entity.get("preferred_topics"),
                entity.get("communication_style"),
                entity.get("sentiment_baseline", 0.0),
                entity.get("metadata"),
            ),
        )

        await self._db.commit()
        logger.debug(f"Entity upserted: {entity['entity_id']}")

        return entity["entity_id"]

    async def insert_session(self, session: dict) -> str:
        """Insert a new session record.

        Args:
            session: Session dictionary with required fields

        Returns:
            Session ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            INSERT INTO sessions (
                session_id, entity_id, platform, started_at,
                message_count, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["session_id"],
                session.get("entity_id"),
                session.get("platform", "direct"),
                session["started_at"],
                session.get("message_count", 0),
                session.get("metadata"),
            ),
        )

        await self._db.commit()
        logger.debug(f"Session inserted: {session['session_id']}")
        return session["session_id"]

    async def end_session(
        self,
        session_id: str,
        ended_at: str,
        message_count: int = 0,
        sentiment_avg: float | None = None,
        topics: str | None = None,
    ) -> None:
        """Mark a session as ended.

        Args:
            session_id: Session identifier
            ended_at: ISO timestamp of session end
            message_count: Total messages in session
            sentiment_avg: Average sentiment score
            topics: JSON-encoded topic list
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            UPDATE sessions
            SET ended_at = ?, message_count = ?, sentiment_avg = ?, topics = ?
            WHERE session_id = ?
            """,
            (ended_at, message_count, sentiment_avg, topics, session_id),
        )

        await self._db.commit()
        logger.debug(f"Session ended: {session_id}")

    async def insert_knowledge_node(self, node: dict) -> str:
        """Insert a knowledge node (semantic memory).

        Args:
            node: Node dictionary with required fields

        Returns:
            Node ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            INSERT INTO knowledge_nodes (
                node_id, entity_id, node_type, content,
                importance, embedding, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node["node_id"],
                node.get("entity_id"),
                node["node_type"],
                node["content"],
                node.get("importance", 0.5),
                node.get("embedding"),
                node.get("metadata"),
            ),
        )

        await self._db.commit()
        logger.debug(f"Knowledge node inserted: {node['node_id']}")
        return node["node_id"]

    async def get_knowledge_nodes(
        self, entity_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Get knowledge nodes, optionally filtered by entity.

        Args:
            entity_id: Optional entity filter
            limit: Maximum results

        Returns:
            List of node dictionaries
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        if entity_id:
            query = """
                SELECT node_id, entity_id, node_type, content,
                       importance, created_at, last_accessed_at, access_count, metadata,
                       mention_count, last_mentioned_at, valid_at, invalid_at
                FROM knowledge_nodes
                WHERE entity_id = ?
                ORDER BY importance DESC
                LIMIT ?
            """
            params = (entity_id, limit)
        else:
            query = """
                SELECT node_id, entity_id, node_type, content,
                       importance, created_at, last_accessed_at, access_count, metadata,
                       mention_count, last_mentioned_at, valid_at, invalid_at
                FROM knowledge_nodes
                ORDER BY importance DESC
                LIMIT ?
            """
            params = (limit,)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "node_id": row[0],
                    "entity_id": row[1],
                    "node_type": row[2],
                    "content": row[3],
                    "importance": row[4],
                    "created_at": row[5],
                    "last_accessed_at": row[6],
                    "access_count": row[7],
                    "metadata": row[8],
                    "mention_count": row[9],
                    "last_mentioned_at": row[10],
                    "valid_at": row[11],
                    "invalid_at": row[12],
                }
                for row in rows
            ]

    async def update_node_embedding(
        self,
        node_id: str,
        embedding: bytes,
    ) -> None:
        """Update the embedding BLOB for a knowledge node.

        Args:
            node_id: Node identifier
            embedding: Serialized embedding bytes
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            "UPDATE knowledge_nodes SET embedding = ? WHERE node_id = ?",
            (embedding, node_id),
        )
        await self._db.commit()

    async def get_all_embeddings(
        self,
        entity_id: str | None = None,
    ) -> list[dict]:
        """Get all nodes that have embeddings, for vector search.

        Args:
            entity_id: Optional entity filter

        Returns:
            List of dicts with node_id, content, importance,
            embedding (bytes), created_at, last_accessed_at
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        if entity_id:
            query = """
                SELECT node_id, content, importance, embedding,
                       created_at, last_accessed_at, access_count
                FROM knowledge_nodes
                WHERE embedding IS NOT NULL AND entity_id = ?
            """
            params = (entity_id,)
        else:
            query = """
                SELECT node_id, content, importance, embedding,
                       created_at, last_accessed_at, access_count
                FROM knowledge_nodes
                WHERE embedding IS NOT NULL
            """
            params = ()

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "node_id": row[0],
                    "content": row[1],
                    "importance": row[2],
                    "embedding": row[3],
                    "created_at": row[4],
                    "last_accessed_at": row[5],
                    "access_count": row[6],
                }
                for row in rows
            ]

    async def search_fts(
        self,
        query: str,
        entity_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search on knowledge nodes content.

        Args:
            query: FTS5 search query
            entity_id: Optional entity filter
            limit: Maximum results

        Returns:
            List of matching node dicts with rank score
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        if entity_id:
            sql = """
                SELECT kn.node_id, kn.content, kn.importance,
                       kn.created_at, kn.last_accessed_at, rank
                FROM knowledge_nodes_fts fts
                JOIN knowledge_nodes kn ON kn.rowid = fts.rowid
                WHERE knowledge_nodes_fts MATCH ?
                  AND kn.entity_id = ?
                ORDER BY rank
                LIMIT ?
            """
            params = (query, entity_id, limit)
        else:
            sql = """
                SELECT kn.node_id, kn.content, kn.importance,
                       kn.created_at, kn.last_accessed_at, rank
                FROM knowledge_nodes_fts fts
                JOIN knowledge_nodes kn ON kn.rowid = fts.rowid
                WHERE knowledge_nodes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            params = (query, limit)

        try:
            async with self._db.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "node_id": row[0],
                        "content": row[1],
                        "importance": row[2],
                        "created_at": row[3],
                        "last_accessed_at": row[4],
                        "fts_rank": row[5],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.warning(f"FTS search failed for query '{query}': {e}")
            return []

    async def get_connected_nodes(
        self,
        node_id: str,
        max_depth: int = 1,
        limit: int = 10,
    ) -> list[dict]:
        """Get nodes connected to a given node via edges (graph traversal).

        Args:
            node_id: Starting node identifier
            max_depth: Maximum traversal depth (1 = direct neighbors only)
            limit: Maximum results

        Returns:
            List of connected node dicts with edge info
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        # Depth-1 traversal: direct neighbors (both directions)
        sql = """
            SELECT DISTINCT kn.node_id, kn.content, kn.importance,
                   kn.created_at, kn.last_accessed_at,
                   ke.edge_type, ke.strength
            FROM knowledge_edges ke
            JOIN knowledge_nodes kn ON (
                (ke.target_node_id = kn.node_id AND ke.source_node_id = ?)
                OR (ke.source_node_id = kn.node_id AND ke.target_node_id = ?)
            )
            ORDER BY ke.strength DESC
            LIMIT ?
        """
        async with self._db.execute(sql, (node_id, node_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "node_id": row[0],
                    "content": row[1],
                    "importance": row[2],
                    "created_at": row[3],
                    "last_accessed_at": row[4],
                    "edge_type": row[5],
                    "edge_strength": row[6],
                }
                for row in rows
            ]

    async def touch_node(self, node_id: str) -> None:
        """Update last_accessed_at and increment access_count for a node.

        Args:
            node_id: Node identifier
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            UPDATE knowledge_nodes
            SET last_accessed_at = CURRENT_TIMESTAMP,
                access_count = access_count + 1
            WHERE node_id = ?
            """,
            (node_id,),
        )
        await self._db.commit()

    async def insert_knowledge_edge(self, edge: dict) -> str:
        """Insert a knowledge edge (relationship between nodes).

        Args:
            edge: Edge dictionary with required fields

        Returns:
            Edge ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            INSERT OR IGNORE INTO knowledge_edges (
                edge_id, source_node_id, target_node_id,
                edge_type, strength, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                edge["edge_id"],
                edge["source_node_id"],
                edge["target_node_id"],
                edge.get("edge_type", "related"),
                edge.get("strength", 1.0),
                edge.get("metadata"),
            ),
        )

        await self._db.commit()
        logger.debug(f"Knowledge edge inserted: {edge['edge_id']}")
        return edge["edge_id"]

    async def delete_knowledge_node(self, node_id: str) -> bool:
        """Delete a single knowledge node by ID.

        Args:
            node_id: Node identifier

        Returns:
            True if the node was deleted, False if not found
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        cursor = await self._db.execute(
            "DELETE FROM knowledge_nodes WHERE node_id = ?",
            (node_id,),
        )
        await self._db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Knowledge node deleted: {node_id}")
        return deleted

    async def delete_knowledge_nodes(
        self,
        entity_id: str | None = None,
    ) -> int:
        """Delete knowledge nodes, optionally filtered by entity.

        Args:
            entity_id: If provided, only delete nodes for this entity.
                       If None, delete all nodes.

        Returns:
            Number of deleted nodes
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        if entity_id:
            cursor = await self._db.execute(
                "DELETE FROM knowledge_nodes WHERE entity_id = ?",
                (entity_id,),
            )
        else:
            cursor = await self._db.execute("DELETE FROM knowledge_nodes")

        await self._db.commit()
        count = cursor.rowcount
        logger.debug(f"Deleted {count} knowledge nodes (entity_id={entity_id})")
        return count

    async def touch_entity(
        self,
        entity_id: str,
        platform: str,
    ) -> None:
        """Create entity profile if it doesn't exist, or update and increment interactions.

        Args:
            entity_id: Entity identifier
            platform: Platform name
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        now_iso = datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            """
            INSERT INTO entity_profiles
                (entity_id, name, platform, first_seen_at, last_seen_at, total_interactions)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(entity_id) DO UPDATE SET
                last_seen_at = ?,
                total_interactions = entity_profiles.total_interactions + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (entity_id, entity_id, platform, now_iso, now_iso, now_iso),
        )
        await self._db.commit()
        logger.debug(f"Entity touched: {entity_id}")

    async def insert_consolidation_log(self, log: dict) -> None:
        """Insert a consolidation log entry.

        Args:
            log: Dict with session_id, consolidated_at, nodes_created,
                 edges_created, summary
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            INSERT INTO consolidation_log
                (session_id, consolidated_at, nodes_created, edges_created, summary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                log["session_id"],
                log["consolidated_at"],
                log.get("nodes_created", 0),
                log.get("edges_created", 0),
                log.get("summary"),
            ),
        )
        await self._db.commit()
        logger.debug(f"Consolidation log inserted for session {log['session_id']}")

    # ── Phase 2 methods ─────────────────────────────────────────────────

    async def insert_stream_episode(self, episode: dict) -> str:
        """Insert a stream episode record.

        Args:
            episode: Episode dictionary with required fields (id, summary)

        Returns:
            Episode ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            INSERT INTO stream_episodes
                (id, session_id, summary, topics_json, key_events_json,
                 participant_count, sentiment, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode["id"],
                episode.get("session_id"),
                episode["summary"],
                episode.get("topics_json"),
                episode.get("key_events_json"),
                episode.get("participant_count"),
                episode.get("sentiment"),
                episode.get("started_at"),
                episode.get("ended_at"),
            ),
        )
        await self._db.commit()
        logger.debug(f"Stream episode inserted: {episode['id']}")
        return episode["id"]

    async def get_stream_episodes(self, limit: int = 10) -> list[dict]:
        """Get recent stream episodes ordered by creation time.

        Args:
            limit: Maximum results

        Returns:
            List of episode dictionaries
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self._db.execute(
            "SELECT * FROM stream_episodes ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

    async def insert_procedural_rule(self, rule: dict) -> str:
        """Insert a procedural rule.

        Args:
            rule: Rule dictionary with required fields (id, rule_type, content)

        Returns:
            Rule ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            INSERT INTO procedural_rules
                (id, rule_type, content, confidence, source, active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                rule["id"],
                rule["rule_type"],
                rule["content"],
                rule.get("confidence", 0.5),
                rule.get("source"),
                rule.get("active", 1),
            ),
        )
        await self._db.commit()
        logger.debug(f"Procedural rule inserted: {rule['id']}")
        return rule["id"]

    async def get_active_procedural_rules(self) -> list[dict]:
        """Get all active procedural rules ordered by confidence.

        Returns:
            List of active rule dictionaries
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self._db.execute(
            "SELECT * FROM procedural_rules WHERE active = 1 ORDER BY confidence DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

    async def update_mention(
        self,
        node_id: str,
        importance_boost: float = 0.05,
    ) -> None:
        """Increment mention count and boost importance for a knowledge node.

        Args:
            node_id: Node identifier
            importance_boost: Amount to increase importance (capped at 1.0)
        """
        if not self._db:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        await self._db.execute(
            """
            UPDATE knowledge_nodes
            SET mention_count = COALESCE(mention_count, 0) + 1,
                last_mentioned_at = CURRENT_TIMESTAMP,
                importance = MIN(1.0, importance + ?)
            WHERE node_id = ?
            """,
            (importance_boost, node_id),
        )
        await self._db.commit()
        logger.debug(f"Knowledge node mention updated: {node_id}")

    async def insert_supersedes_edge(
        self,
        new_node_id: str,
        old_node_id: str,
    ) -> str:
        """Create a 'supersedes' edge from a new node to an old node.

        Args:
            new_node_id: The newer replacement node
            old_node_id: The older node being superseded

        Returns:
            Edge ID
        """
        from uuid import uuid4

        edge_id = str(uuid4())
        await self.insert_knowledge_edge(
            {
                "edge_id": edge_id,
                "source_node_id": new_node_id,
                "target_node_id": old_node_id,
                "edge_type": "supersedes",
                "strength": 1.0,
            }
        )
        return edge_id
