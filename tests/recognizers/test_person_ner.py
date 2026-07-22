"""Tests for person name recognizers: Chinese NER + context fallback, English CJK filter."""

import pytest

from pii_desensitizer.recognizers.person_ner import (
    ChinesePersonRecognizer,
    EnglishPersonRecognizer,
)


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

    def test_filters_zh_ner_english_stopword_false_positive(self, recognizer):
        """zh_core_web_sm tags English common words as PERSON when processing
        English text. These should be filtered out.

        All test words are common English words, never person names.
        """
        test_cases = [
            ("Please contact john@example.com for details", "for"),
            ("Version 1.2.3 is out", "out"),
            ("Born on 1990-01-15", "Born"),
        ]
        for text, stopword in test_cases:
            results = recognizer.analyze(
                text=text, entities=["PERSON"], nlp_artifacts=None
            )
            person_spans = [text[r.start:r.end] for r in results]
            assert stopword not in person_spans, (
                f"Expected '{stopword}' to be filtered, but it appears in "
                f"PERSON results: {person_spans}"
            )

    def test_filters_zh_ner_digit_false_positive(self, recognizer):
        """zh_core_web_sm tags digit strings as PERSON (e.g. phone numbers).
        Pure digits are never person names and should be filtered.
        """
        text = "姓名：陳測試\nID：50111111\n電話：66111111"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_spans = [text[r.start:r.end] for r in results]
        digit_spans = [s for s in person_spans if s.isdigit()]
        assert len(digit_spans) == 0, (
            f"Expected no digit-only PERSON spans, but found: {digit_spans}"
        )


class TestChinesePersonRecognizerContextFallback:
    """Tests for the context-based fallback that catches names zh NER misses."""

    @pytest.fixture(scope="module")
    def recognizer(self):
        rec = ChinesePersonRecognizer()
        rec.load()
        return rec

    def test_detects_name_after_form_field_keyword(self, recognizer):
        text = "本人姓名：施例男"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "施例男" in person_texts

    def test_detects_name_after子女_keyword(self, recognizer):
        text = "本人的子女：施例男"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "施例男" in person_texts

    def test_detects_name_after申請人簽署_keyword(self, recognizer):
        text = "申請人簽署：陳大文"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "陳大文" in person_texts

    def test_no_false_positive_on_non_name_field(self, recognizer):
        text = "性別：男"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        assert len(results) == 0

    def test_context_fallback_does_not_duplicate_ner_result(self, recognizer):
        text = "姓名：陳大文"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        spans = [(r.start, r.end) for r in results if r.score >= 0.75]
        overlaps = [
            (s1, s2)
            for i, s1 in enumerate(spans)
            for s2 in spans[i + 1:]
            if s1[0] < s2[1] and s2[0] < s1[1]
        ]
        assert len(overlaps) == 0


class TestChinesePersonRecognizerPortugueseFallback:
    """Tests for Portuguese name detection via context fallback.

    All names are synthetic — common Portuguese surnames combined with
    'TESTE' or 'EXEMPLO' tokens to ensure they are never real PII.
    """

    @pytest.fixture(scope="module")
    def recognizer(self):
        rec = ChinesePersonRecognizer()
        rec.load()
        return rec

    def test_detects_all_caps_bir_name(self, recognizer):
        text = "姓名：ALVES TESTE RODRIGUES"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "ALVES TESTE RODRIGUES" in person_texts

    def test_detects_title_case_portuguese_name(self, recognizer):
        text = "姓名：João da Silva Teste"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "João da Silva Teste" in person_texts

    def test_detects_multi_word_with_prepositions(self, recognizer):
        text = "申請人：Pedro dos Santos Exemplo"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "Pedro dos Santos Exemplo" in person_texts

    def test_detects_short_caps_name(self, recognizer):
        text = "姓名：TESTE SILVA"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "TESTE SILVA" in person_texts

    def test_no_false_positive_on_id_field(self, recognizer):
        text = "ID：12345678"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        assert len(results) == 0

    def test_no_false_positive_on_phone_field(self, recognizer):
        text = "電話：61234567"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        assert len(results) == 0


class TestEnglishPersonRecognizerCJKFilter:
    """Tests that EnglishPersonRecognizer filters CJK from PERSON results."""

    def test_no_cjk_person_on_chinese_text(self):
        import spacy
        from presidio_analyzer.nlp_engine import NlpArtifacts

        nlp = spacy.load("en_core_web_sm")
        rec = EnglishPersonRecognizer()
        text = "本人姓名：陳大文，澳門永久居民身份證編號：12345678"
        doc = nlp(text)
        artifacts = NlpArtifacts(
            entities=doc.ents,
            tokens=doc,
            tokens_indices=[t.idx for t in doc],
            lemmas=[t.lemma_ for t in doc],
            nlp_engine=None,
            language="en",
        )
        results = rec.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=artifacts
        )
        assert len(results) == 0

    def test_filters_cjk_punctuation_false_positive(self):
        """CJK punctuation (corner brackets, etc.) tagged as PERSON by
        en_core_web_sm should be filtered out.

        U+3000-U+303F (CJK Symbols and Punctuation) includes 「」『』 which
        en_core_web_sm occasionally tags as PERSON. These are not covered by
        the basic CJK ideograph range (U+4E00-U+9FFF).
        """
        import spacy
        from presidio_analyzer.nlp_engine import NlpArtifacts

        nlp = spacy.load("en_core_web_sm")
        rec = EnglishPersonRecognizer()
        # Full case_01 text — en_core_web_sm tags 」 (U+300D) as PERSON only
        # in this broader context (not in isolation), matching production input.
        text = (
            "20260701-00125\n"
            "主　題：關於解除「一戶通」親子帳戶綁定之申請\n"
            "致：身份證局\n"
            "本人姓名：蔡測試\n"
            "澳門永久居民身份證編號：51111111\n"
            "為「澳門公共服務一戶通」\n"
            "用戶名：testuser\n"
        )
        doc = nlp(text)
        artifacts = NlpArtifacts(
            entities=doc.ents,
            tokens=doc,
            tokens_indices=[t.idx for t in doc],
            lemmas=[t.lemma_ for t in doc],
            nlp_engine=None,
            language="en",
        )
        results = rec.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=artifacts
        )
        # No PERSON results should remain — 」 is CJK punctuation, not a name
        person_spans = [text[r.start:r.end] for r in results]
        assert "」" not in person_spans
        assert "「" not in person_spans

    def test_filters_english_stopword_false_positive(self):
        """en_core_web_sm tags 'Email' as PERSON in 'Email: alice@test.com'.
        Common English words should be filtered out.
        """
        import spacy
        from presidio_analyzer.nlp_engine import NlpArtifacts

        nlp = spacy.load("en_core_web_sm")
        rec = EnglishPersonRecognizer()
        text = "Email: alice@test.com"
        doc = nlp(text)
        artifacts = NlpArtifacts(
            entities=doc.ents,
            tokens=doc,
            tokens_indices=[t.idx for t in doc],
            lemmas=[t.lemma_ for t in doc],
            nlp_engine=None,
            language="en",
        )
        results = rec.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=artifacts
        )
        person_spans = [text[r.start:r.end] for r in results]
        assert "Email" not in person_spans

    def test_filters_pure_digit_person_false_positive(self):
        """en_core_web_sm tags digit strings as PERSON (e.g. phone numbers).
        Pure digits are never person names and should be filtered.
        """
        import spacy
        from presidio_analyzer.nlp_engine import NlpArtifacts

        nlp = spacy.load("en_core_web_sm")
        rec = EnglishPersonRecognizer()
        # Text where en_core_web_sm tags 66111111 as PERSON (context-sensitive:
        # the "Mr." prefix triggers NER to label the digit string as PERSON)
        text = "Mr. 66111111 called"
        doc = nlp(text)
        artifacts = NlpArtifacts(
            entities=doc.ents,
            tokens=doc,
            tokens_indices=[t.idx for t in doc],
            lemmas=[t.lemma_ for t in doc],
            nlp_engine=None,
            language="en",
        )
        results = rec.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=artifacts
        )
        person_spans = [text[r.start:r.end] for r in results]
        # 66111111 should not appear as PERSON (it's a phone number)
        digit_spans = [s for s in person_spans if s.isdigit()]
        assert len(digit_spans) == 0, (
            f"Expected no digit-only PERSON spans, but found: {digit_spans}"
        )

    def test_filters_portuguese_address_prefix_false_positive(self):
        """en_core_web_sm tags Portuguese building names as PERSON.
        Spans starting with Portuguese building/street suffixes are addresses,
        not person names, and should be filtered.
        """
        import spacy
        from presidio_analyzer.nlp_engine import NlpArtifacts

        nlp = spacy.load("en_core_web_sm")
        rec = EnglishPersonRecognizer()
        text = "Edifício Comercial Teste"
        doc = nlp(text)
        artifacts = NlpArtifacts(
            entities=doc.ents,
            tokens=doc,
            tokens_indices=[t.idx for t in doc],
            lemmas=[t.lemma_ for t in doc],
            nlp_engine=None,
            language="en",
        )
        results = rec.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=artifacts
        )
        person_spans = [text[r.start:r.end] for r in results]
        # "Edifício Comercial Teste" is an address, not a person name
        assert "Edifício Comercial Teste" not in person_spans
