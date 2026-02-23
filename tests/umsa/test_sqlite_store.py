"""Tests for UMSA Phase 2 schema migration and new methods in SQLiteStore."""

import os
import tempfile

import pytest

from open_llm_vtuber.umsa.storage.sqlite_store import SQLiteStore


@pytest.fixture
async def store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        s = SQLiteStore(db_path=db_path)
        await s.initialize()
        yield s
        await s.close()


@pytest.mark.asyncio
async def test_stream_episodes_table_exists(store):
    async with store._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stream_episodes'"
    ) as cursor:
        rows = await cursor.fetchall()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_procedural_rules_table_exists(store):
    async with store._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='procedural_rules'"
    ) as cursor:
        rows = await cursor.fetchall()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_knowledge_nodes_has_mention_columns(store):
    async with store._db.execute("PRAGMA table_info(knowledge_nodes)") as cursor:
        rows = await cursor.fetchall()
    col_names = {r[1] for r in rows}
    assert "mention_count" in col_names
    assert "last_mentioned_at" in col_names
    assert "valid_at" in col_names
    assert "invalid_at" in col_names


@pytest.mark.asyncio
async def test_insert_stream_episode(store):
    ep_id = await store.insert_stream_episode(
        {
            "id": "ep-001",
            "session_id": None,
            "summary": "Played Minecraft for 2 hours",
            "topics_json": '["minecraft","building"]',
            "key_events_json": "[]",
            "participant_count": 5,
            "sentiment": "positive",
            "started_at": "2026-02-23T10:00:00Z",
            "ended_at": "2026-02-23T12:00:00Z",
        }
    )
    assert ep_id == "ep-001"


@pytest.mark.asyncio
async def test_get_stream_episodes(store):
    await store.insert_stream_episode(
        {
            "id": "ep-001",
            "session_id": None,
            "summary": "First stream",
        }
    )
    await store.insert_stream_episode(
        {
            "id": "ep-002",
            "session_id": None,
            "summary": "Second stream",
        }
    )
    episodes = await store.get_stream_episodes(limit=10)
    assert len(episodes) == 2
    assert episodes[0]["id"] in ("ep-001", "ep-002")


@pytest.mark.asyncio
async def test_insert_procedural_rule(store):
    rule_id = await store.insert_procedural_rule(
        {
            "id": "rule-001",
            "rule_type": "persona",
            "content": "Always encourage viewers when they are sad",
            "confidence": 0.7,
            "source": "reflection",
            "active": 1,
        }
    )
    assert rule_id == "rule-001"


@pytest.mark.asyncio
async def test_get_active_procedural_rules(store):
    await store.insert_procedural_rule(
        {
            "id": "r1",
            "rule_type": "persona",
            "content": "Rule 1",
            "confidence": 0.7,
            "source": "reflection",
            "active": 1,
        }
    )
    await store.insert_procedural_rule(
        {
            "id": "r2",
            "rule_type": "style",
            "content": "Rule 2",
            "confidence": 0.5,
            "source": "manual",
            "active": 0,
        }
    )
    rules = await store.get_active_procedural_rules()
    assert len(rules) == 1
    assert rules[0]["id"] == "r1"


@pytest.mark.asyncio
async def test_update_mention_count(store):
    await store.upsert_entity(
        {
            "entity_id": "e1",
            "name": "e1",
            "platform": "test",
            "first_seen_at": "2026-01-01T00:00:00Z",
            "last_seen_at": "2026-01-01T00:00:00Z",
        }
    )
    await store.insert_knowledge_node(
        {
            "node_id": "n1",
            "entity_id": "e1",
            "node_type": "atomic_fact",
            "content": "User likes Python",
            "importance": 0.5,
        }
    )
    await store.update_mention(node_id="n1", importance_boost=0.05)
    nodes = await store.get_knowledge_nodes(entity_id="e1", limit=10)
    node = next(n for n in nodes if n["node_id"] == "n1")
    assert node["mention_count"] == 1
    assert node["importance"] == pytest.approx(0.55, abs=0.01)


@pytest.mark.asyncio
async def test_update_mention_multiple_times(store):
    await store.upsert_entity(
        {
            "entity_id": "e2",
            "name": "e2",
            "platform": "test",
            "first_seen_at": "2026-01-01T00:00:00Z",
            "last_seen_at": "2026-01-01T00:00:00Z",
        }
    )
    await store.insert_knowledge_node(
        {
            "node_id": "n2",
            "entity_id": "e2",
            "node_type": "atomic_fact",
            "content": "User likes Rust",
            "importance": 0.5,
        }
    )
    await store.update_mention(node_id="n2", importance_boost=0.1)
    await store.update_mention(node_id="n2", importance_boost=0.1)
    await store.update_mention(node_id="n2", importance_boost=0.1)
    nodes = await store.get_knowledge_nodes(entity_id="e2", limit=10)
    node = next(n for n in nodes if n["node_id"] == "n2")
    assert node["mention_count"] == 3
    assert node["importance"] == pytest.approx(0.8, abs=0.01)


@pytest.mark.asyncio
async def test_update_mention_importance_capped_at_1(store):
    await store.upsert_entity(
        {
            "entity_id": "e3",
            "name": "e3",
            "platform": "test",
            "first_seen_at": "2026-01-01T00:00:00Z",
            "last_seen_at": "2026-01-01T00:00:00Z",
        }
    )
    await store.insert_knowledge_node(
        {
            "node_id": "n3",
            "entity_id": "e3",
            "node_type": "atomic_fact",
            "content": "User likes Go",
            "importance": 0.95,
        }
    )
    await store.update_mention(node_id="n3", importance_boost=0.2)
    nodes = await store.get_knowledge_nodes(entity_id="e3", limit=10)
    node = next(n for n in nodes if n["node_id"] == "n3")
    assert node["importance"] <= 1.0


@pytest.mark.asyncio
async def test_insert_supersedes_edge(store):
    await store.upsert_entity(
        {
            "entity_id": "e1",
            "name": "e1",
            "platform": "test",
            "first_seen_at": "2026-01-01T00:00:00Z",
            "last_seen_at": "2026-01-01T00:00:00Z",
        }
    )
    await store.insert_knowledge_node(
        {
            "node_id": "old-node",
            "entity_id": "e1",
            "node_type": "atomic_fact",
            "content": "User likes Java",
            "importance": 0.5,
        }
    )
    await store.insert_knowledge_node(
        {
            "node_id": "new-node",
            "entity_id": "e1",
            "node_type": "atomic_fact",
            "content": "User likes Kotlin",
            "importance": 0.6,
        }
    )
    edge_id = await store.insert_supersedes_edge("new-node", "old-node")
    assert edge_id is not None
    connected = await store.get_connected_nodes("new-node", limit=10)
    assert any(n["node_id"] == "old-node" for n in connected)
    assert any(n["edge_type"] == "supersedes" for n in connected)
