import pytest
from open_llm_vtuber.umsa.conflict_detector import ConflictDetector


def test_no_conflict_for_unrelated():
    detector = ConflictDetector()
    result = detector.check(
        new_content="User likes Python",
        existing_memories=[
            {"id": "m1", "content": "User lives in Seoul", "importance": 0.5}
        ],
        similarity_fn=lambda a, b: 0.1,
    )
    assert len(result) == 0


def test_detects_supersedes():
    detector = ConflictDetector()
    result = detector.check(
        new_content="User switched to Rust",
        existing_memories=[
            {"id": "m1", "content": "User uses Python", "importance": 0.5}
        ],
        similarity_fn=lambda a, b: 0.65,
    )
    assert len(result) == 1
    assert result[0]["superseded_id"] == "m1"
    assert result[0]["new_importance_decay"] == pytest.approx(0.35, abs=0.01)


def test_ignores_duplicates():
    detector = ConflictDetector()
    result = detector.check(
        new_content="User likes Python",
        existing_memories=[
            {"id": "m1", "content": "User likes Python", "importance": 0.5}
        ],
        similarity_fn=lambda a, b: 0.9,
    )
    assert len(result) == 0


def test_multiple_conflicts():
    detector = ConflictDetector()
    result = detector.check(
        new_content="User prefers Rust",
        existing_memories=[
            {"id": "m1", "content": "User prefers Python", "importance": 0.5},
            {"id": "m2", "content": "User prefers Java", "importance": 0.3},
            {"id": "m3", "content": "User likes cats", "importance": 0.6},
        ],
        similarity_fn=lambda a, b: 0.7 if "prefers" in b else 0.1,
    )
    assert len(result) == 2


def test_boundary_low():
    """Exactly 0.5 should be detected as conflict."""
    detector = ConflictDetector()
    result = detector.check(
        new_content="A",
        existing_memories=[{"id": "m1", "content": "B", "importance": 0.5}],
        similarity_fn=lambda a, b: 0.5,
    )
    assert len(result) == 1


def test_boundary_high():
    """Exactly 0.85 should NOT be detected (it's duplicate range)."""
    detector = ConflictDetector()
    result = detector.check(
        new_content="A",
        existing_memories=[{"id": "m1", "content": "B", "importance": 0.5}],
        similarity_fn=lambda a, b: 0.85,
    )
    assert len(result) == 0


def test_importance_decay_calculation():
    detector = ConflictDetector()
    result = detector.check(
        new_content="New fact",
        existing_memories=[{"id": "m1", "content": "Old fact", "importance": 0.8}],
        similarity_fn=lambda a, b: 0.7,
    )
    assert result[0]["new_importance_decay"] == pytest.approx(0.56, abs=0.01)
