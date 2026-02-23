"""Tests for RegexExtractor — bilingual regex-based memory extraction."""

from __future__ import annotations

import pytest

from open_llm_vtuber.umsa.regex_extractor import RegexExtractor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ext() -> RegexExtractor:
    return RegexExtractor()


# ---------------------------------------------------------------------------
# Pattern count sanity
# ---------------------------------------------------------------------------


def test_pattern_count_at_least_40(ext: RegexExtractor) -> None:
    assert ext.pattern_count >= 40


# ---------------------------------------------------------------------------
# Korean Preferences
# ---------------------------------------------------------------------------


def test_extract_korean_preference(ext: RegexExtractor) -> None:
    results = ext.extract("나는 파이썬 좋아해")
    assert any("파이썬" in r["content"] for r in results)
    assert any(r["memory_type"] == "preference" for r in results)


def test_extract_korean_preference_ga(ext: RegexExtractor) -> None:
    results = ext.extract("게임이 좋아")
    assert any("게임" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# Korean Negative Preferences
# ---------------------------------------------------------------------------


def test_extract_korean_negative(ext: RegexExtractor) -> None:
    results = ext.extract("자바는 싫어")
    assert any("자바" in r["content"] for r in results)


def test_extract_korean_negative_dislike(ext: RegexExtractor) -> None:
    results = ext.extract("수학을 싫어해")
    assert any("수학" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# Korean Activities
# ---------------------------------------------------------------------------


def test_extract_korean_activity(ext: RegexExtractor) -> None:
    results = ext.extract("지금 마인크래프트 하고 있어")
    assert any("마인크래프트" in r["content"] for r in results)


def test_extract_korean_activity_doing(ext: RegexExtractor) -> None:
    results = ext.extract("코딩 하고 있어")
    assert any("코딩" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# Korean Decisions
# ---------------------------------------------------------------------------


def test_extract_korean_decision(ext: RegexExtractor) -> None:
    results = ext.extract("Rust를 배우기로 했어")
    assert any("Rust" in r["content"] for r in results)


def test_extract_korean_decision_decided(ext: RegexExtractor) -> None:
    results = ext.extract("Python으로 결정했어")
    assert any("Python" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# Korean Facts / Identity
# ---------------------------------------------------------------------------


def test_extract_korean_occupation(ext: RegexExtractor) -> None:
    results = ext.extract("저는 대학생이에요")
    assert any("대학생" in r["content"] for r in results)


def test_extract_korean_identity_casual(ext: RegexExtractor) -> None:
    results = ext.extract("나 프로그래머야")
    assert any("프로그래머" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# English Preferences
# ---------------------------------------------------------------------------


def test_extract_english_preference(ext: RegexExtractor) -> None:
    results = ext.extract("I really like Minecraft")
    assert any("Minecraft" in r["content"] for r in results)


def test_extract_english_love(ext: RegexExtractor) -> None:
    results = ext.extract("I love cooking")
    assert any("cooking" in r["content"] for r in results)
    assert any(r["memory_type"] == "preference" for r in results)


def test_extract_english_enjoy(ext: RegexExtractor) -> None:
    results = ext.extract("I enjoy reading books")
    assert any("reading books" in r["content"] for r in results)


def test_extract_english_favorite(ext: RegexExtractor) -> None:
    results = ext.extract("Python is my favorite")
    assert any("Python" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# English Negative Preferences
# ---------------------------------------------------------------------------


def test_extract_english_hate(ext: RegexExtractor) -> None:
    results = ext.extract("I hate spiders")
    assert any("spiders" in r["content"] for r in results)


def test_extract_english_dont_like(ext: RegexExtractor) -> None:
    results = ext.extract("I don't like cold weather")
    assert any("cold weather" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# English Activities
# ---------------------------------------------------------------------------


def test_extract_english_activity(ext: RegexExtractor) -> None:
    results = ext.extract("I'm playing Zelda")
    assert any("Zelda" in r["content"] for r in results)


def test_extract_english_studying(ext: RegexExtractor) -> None:
    results = ext.extract("I am currently studying Japanese")
    assert any("Japanese" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# English Decisions
# ---------------------------------------------------------------------------


def test_extract_decision(ext: RegexExtractor) -> None:
    results = ext.extract("I decided to use TypeScript")
    assert any("TypeScript" in r["content"] for r in results)
    assert any(r["memory_type"] == "atomic_fact" for r in results)


def test_extract_english_going_to_learn(ext: RegexExtractor) -> None:
    results = ext.extract("I'm going to learn Rust")
    assert any("Rust" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# English Facts / Identity
# ---------------------------------------------------------------------------


def test_extract_english_work(ext: RegexExtractor) -> None:
    results = ext.extract("I work at Google")
    assert any("Google" in r["content"] for r in results)


def test_extract_english_am(ext: RegexExtractor) -> None:
    results = ext.extract("I'm a software engineer")
    assert any("software engineer" in r["content"] for r in results)


def test_extract_english_name(ext: RegexExtractor) -> None:
    results = ext.extract("My name is Alice")
    assert any("Alice" in r["content"] for r in results)


def test_extract_english_live(ext: RegexExtractor) -> None:
    results = ext.extract("I live in Tokyo")
    assert any("Tokyo" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# English Technical
# ---------------------------------------------------------------------------


def test_extract_english_use(ext: RegexExtractor) -> None:
    results = ext.extract("I use Neovim")
    assert any("Neovim" in r["content"] for r in results)


def test_extract_english_code_in(ext: RegexExtractor) -> None:
    results = ext.extract("I code in Python")
    assert any("Python" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_no_extraction_from_trivial(ext: RegexExtractor) -> None:
    results = ext.extract("ㅋㅋㅋ")
    assert len(results) == 0


def test_empty_string(ext: RegexExtractor) -> None:
    results = ext.extract("")
    assert len(results) == 0


def test_whitespace_only(ext: RegexExtractor) -> None:
    results = ext.extract("   ")
    assert len(results) == 0


def test_confidence_is_0_5(ext: RegexExtractor) -> None:
    results = ext.extract("I like pizza")
    for r in results:
        assert r["confidence"] == 0.5


def test_sorted_by_importance_descending(ext: RegexExtractor) -> None:
    results = ext.extract("I love cooking. I like pizza")
    if len(results) >= 2:
        importances = [r["importance"] for r in results]
        assert importances == sorted(importances, reverse=True)


def test_deduplication(ext: RegexExtractor) -> None:
    results = ext.extract("피자 좋아해 피자 좋아해")
    pizza_results = [r for r in results if "피자" in r["content"].lower()]
    # After dedup there should be at most 1 result containing 피자 per pattern
    # (different templates may produce different content, but identical content
    # strings should be collapsed)
    contents = [r["content"] for r in pizza_results]
    assert len(contents) == len(set(c.lower() for c in contents))


def test_result_dict_keys(ext: RegexExtractor) -> None:
    results = ext.extract("I like cats")
    assert len(results) > 0
    expected_keys = {"content", "memory_type", "importance", "confidence", "category"}
    for r in results:
        assert set(r.keys()) == expected_keys
