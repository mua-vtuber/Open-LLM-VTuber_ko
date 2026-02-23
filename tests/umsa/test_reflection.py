import pytest

from open_llm_vtuber.umsa.reflection import ReflectionEngine


def test_rule_based_reflection():
    """Without LLM, should produce frequency-based insights."""
    engine = ReflectionEngine(llm=None)
    nodes = [
        {
            "content": "User likes Python",
            "entity_id": "e1",
            "memory_type": "preference",
        },
        {
            "content": "User prefers Python over Java",
            "entity_id": "e1",
            "memory_type": "preference",
        },
        {
            "content": "User is learning Rust",
            "entity_id": "e1",
            "memory_type": "atomic_fact",
        },
        {
            "content": "User works on backend",
            "entity_id": "e1",
            "memory_type": "atomic_fact",
        },
    ]
    insights = engine.reflect_sync(nodes)
    assert len(insights) >= 1
    for ins in insights:
        assert ins["memory_type"] == "meta_summary"


def test_no_reflection_below_threshold():
    engine = ReflectionEngine(llm=None, min_group_size=5)
    nodes = [
        {"content": "Fact A", "entity_id": "e1", "memory_type": "atomic_fact"},
        {"content": "Fact B", "entity_id": "e1", "memory_type": "atomic_fact"},
    ]
    insights = engine.reflect_sync(nodes)
    assert len(insights) == 0


def test_groups_by_entity():
    engine = ReflectionEngine(llm=None, min_group_size=2)
    nodes = [
        {"content": "A likes cats", "entity_id": "e1", "memory_type": "preference"},
        {"content": "A likes dogs", "entity_id": "e1", "memory_type": "preference"},
        {"content": "B likes fish", "entity_id": "e2", "memory_type": "preference"},
    ]
    insights = engine.reflect_sync(nodes)
    e1_insights = [i for i in insights if i.get("entity_id") == "e1"]
    assert len(e1_insights) >= 1


def test_insight_has_source_node_ids():
    engine = ReflectionEngine(llm=None, min_group_size=2)
    nodes = [
        {
            "id": "n1",
            "content": "Fact 1",
            "entity_id": "e1",
            "memory_type": "atomic_fact",
        },
        {
            "id": "n2",
            "content": "Fact 2",
            "entity_id": "e1",
            "memory_type": "atomic_fact",
        },
        {
            "id": "n3",
            "content": "Fact 3",
            "entity_id": "e1",
            "memory_type": "atomic_fact",
        },
    ]
    insights = engine.reflect_sync(nodes)
    assert len(insights) == 1
    assert "n1" in insights[0]["source_node_ids"]
    assert "n2" in insights[0]["source_node_ids"]


def test_insight_importance_scales_with_group_size():
    engine = ReflectionEngine(llm=None, min_group_size=2)
    small = [
        {"content": f"Fact {i}", "entity_id": "e1", "memory_type": "atomic_fact"}
        for i in range(3)
    ]
    large = [
        {"content": f"Fact {i}", "entity_id": "e2", "memory_type": "atomic_fact"}
        for i in range(10)
    ]
    insights = engine.reflect_sync(small + large)
    e1_imp = next(i["importance"] for i in insights if i["entity_id"] == "e1")
    e2_imp = next(i["importance"] for i in insights if i["entity_id"] == "e2")
    assert e2_imp > e1_imp


@pytest.mark.asyncio
async def test_async_reflect_falls_back_to_sync():
    engine = ReflectionEngine(llm=None, min_group_size=2)
    nodes = [
        {"content": "A", "entity_id": "e1", "memory_type": "preference"},
        {"content": "B", "entity_id": "e1", "memory_type": "preference"},
        {"content": "C", "entity_id": "e1", "memory_type": "preference"},
    ]
    insights = await engine.reflect(nodes)
    assert len(insights) >= 1
