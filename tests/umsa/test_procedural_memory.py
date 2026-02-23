import pytest
from open_llm_vtuber.umsa.procedural_memory import ProceduralMemory


def test_empty_rules():
    pm = ProceduralMemory()
    assert pm.format_for_context() == ""


def test_load_rules():
    pm = ProceduralMemory()
    pm.load_rules(
        [
            {
                "id": "r1",
                "rule_type": "persona",
                "content": "Always be encouraging",
                "confidence": 0.8,
            },
            {
                "id": "r2",
                "rule_type": "style",
                "content": "Use casual Korean",
                "confidence": 0.6,
            },
        ]
    )
    text = pm.format_for_context()
    assert "Always be encouraging" in text
    assert "Use casual Korean" in text


def test_add_rule():
    pm = ProceduralMemory()
    rule = pm.add_rule(
        rule_type="persona",
        content="Encourage sad viewers",
        confidence=0.7,
        source="reflection",
    )
    assert len(pm.rules) == 1
    assert pm.rules[0]["rule_type"] == "persona"
    assert "id" in rule


def test_format_groups_by_type():
    pm = ProceduralMemory()
    pm.load_rules(
        [
            {
                "id": "r1",
                "rule_type": "persona",
                "content": "Rule A",
                "confidence": 0.8,
            },
            {
                "id": "r2",
                "rule_type": "style",
                "content": "Rule B",
                "confidence": 0.6,
            },
        ]
    )
    text = pm.format_for_context()
    assert "[Persona]" in text
    assert "[Style]" in text


def test_get_rules_by_type():
    pm = ProceduralMemory()
    pm.load_rules(
        [
            {"id": "r1", "rule_type": "persona", "content": "Rule A"},
            {"id": "r2", "rule_type": "style", "content": "Rule B"},
            {"id": "r3", "rule_type": "persona", "content": "Rule C"},
        ]
    )
    persona_rules = pm.get_rules_by_type("persona")
    assert len(persona_rules) == 2


def test_add_rule_generates_id():
    pm = ProceduralMemory()
    rule = pm.add_rule(rule_type="test", content="test rule")
    assert rule["id"] is not None
    assert len(rule["id"]) > 0
