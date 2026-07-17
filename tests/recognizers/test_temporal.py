# tests/recognizers/test_temporal.py
"""Tests for birthday recognizer."""

from pii_desensitizer.recognizers.temporal import BirthdayRecognizer


class TestBirthdayRecognizer:
    def test_detects_iso_date(self):
        rec = BirthdayRecognizer()
        results = rec.analyze(
            text="Born on 1990-01-15",
            entities=["BIRTHDAY"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_detects_slash_format(self):
        rec = BirthdayRecognizer()
        results = rec.analyze(
            text="DOB: 15/01/1990",
            entities=["BIRTHDAY"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_detects_birthday_after_chinese_text(self):
        rec = BirthdayRecognizer()
        text = "生日1990-01-15"
        results = rec.analyze(text=text, entities=["BIRTHDAY"], nlp_artifacts=None)
        assert len(results) == 1
