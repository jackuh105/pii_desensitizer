"""Tests for Chinese person name recognizer with OpenCC Traditional→Simplified conversion."""

import pytest

from pii_desensitizer.recognizers.person_ner import ChinesePersonRecognizer


@pytest.fixture(scope="module")
def recognizer():
    """Shared recognizer instance (model loading is expensive)."""
    rec = ChinesePersonRecognizer()
    rec.load()
    return rec


class TestChinesePersonRecognizer:
    """Tests verifying Traditional Chinese person name detection via OpenCC conversion."""

    def test_detects_traditional_chinese_name(self, recognizer):
        """Traditional Chinese name '陳大文' should be detected after OpenCC conversion."""
        text = "我是陳大文，請聯絡我"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        person_text = text[results[0].start:results[0].end]
        assert person_text == "陳大文"

    def test_detects_traditional_chinese_name_with_context(self, recognizer):
        """Traditional Chinese name '黃志偉' should be detected even with surrounding text."""
        text = "請聯絡黃志偉先生"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        person_text = text[results[0].start:results[0].end]
        assert person_text == "黃志偉"

    def test_detects_multiple_traditional_chinese_names(self, recognizer):
        """Multiple Traditional Chinese names in one text should all be detected."""
        text = "張偉、王芳、李強都是同事"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "張偉" in person_texts
        assert "王芳" in person_texts
        assert "李強" in person_texts

    def test_detects_simplified_chinese_name(self, recognizer):
        """Simplified Chinese should still work (OpenCC is idempotent on Simplified input)."""
        text = "张三和李明在开会"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        person_texts = [text[r.start:r.end] for r in results]
        assert "张三" in person_texts

    def test_offsets_point_to_original_traditional_text(self, recognizer):
        """Offsets must be valid on the original Traditional text, not the Simplified conversion.

        This is the critical test: NER runs on Simplified text, but offsets must
        correctly slice the original Traditional text. If OpenCC changed string length,
        this test would fail.
        """
        text = "我是陳大文，請聯絡我"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        for r in results:
            assert 0 <= r.start < r.end <= len(text)
            sliced = text[r.start:r.end]
            assert len(sliced) == r.end - r.start
            # The sliced text must contain Traditional Chinese characters,
            # NOT the Simplified ones (proving we're slicing the original text)
            assert "陳" in sliced or "大" in sliced or "文" in sliced
            # Must NOT contain Simplified-only characters
            assert "陈" not in sliced

    def test_mixed_chinese_english_text(self, recognizer):
        """Mixed Chinese+English text should detect both Chinese and English names."""
        text = "John和陳大文開會"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "John" in person_texts
        assert "陳大文" in person_texts

    def test_results_have_correct_entity_type(self, recognizer):
        text = "王先生今天不在"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        for r in results:
            assert r.entity_type == "PERSON"

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

    def test_no_crash_on_pure_simplified_text(self, recognizer):
        """OpenCC should be idempotent on already-Simplified text (no crash, no double-conversion)."""
        text = "张三来过"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert isinstance(results, list)

    def test_filters_punctuation_false_positive(self, recognizer):
        """PERSON results containing punctuation should be filtered out."""
        text = "電子身份識別工具(高級)未開啟"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        for r in results:
            matched = text[r.start:r.end]
            assert "(" not in matched
            assert ")" not in matched
            assert "（" not in matched
            assert "）" not in matched

    def test_does_not_filter_real_names_with_no_punctuation(self, recognizer):
        """Real person names (no punctuation) should not be filtered."""
        text = "請聯絡陳大文先生"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "陳大文" in person_texts
