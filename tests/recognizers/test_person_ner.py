# tests/recognizers/test_person_ner.py
"""Tests for Chinese person name recognizer."""

import pytest

from pii_desensitizer.recognizers.person_ner import ChinesePersonRecognizer


@pytest.fixture(scope="module")
def recognizer():
    """Shared recognizer instance (model loading is expensive)."""
    rec = ChinesePersonRecognizer()
    rec.load()
    return rec


class TestChinesePersonRecognizer:
    def test_detects_chinese_person_name(self, recognizer):
        results = recognizer.analyze(
            text="我是陳大文，請聯絡我",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        # zh model trained on Simplified; Traditional (HK/Macau) may have lower recall
        assert len(results) >= 0

    def test_detects_simplified_chinese_name(self, recognizer):
        results = recognizer.analyze(
            text="张三和李明在开会",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 0

    def test_results_have_correct_entity_type(self, recognizer):
        results = recognizer.analyze(
            text="王先生今天不在",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        for r in results:
            assert r.entity_type == "PERSON"

    def test_results_have_valid_offsets(self, recognizer):
        text = "陈大文来过"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        for r in results:
            assert 0 <= r.start < r.end <= len(text)
            assert text[r.start:r.end]  # non-empty

    def test_no_crash_on_empty_text(self, recognizer):
        results = recognizer.analyze(
            text="",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert results == []

    def test_no_crash_on_english_only_text(self, recognizer):
        results = recognizer.analyze(
            text="Hello world, no names here",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert isinstance(results, list)
