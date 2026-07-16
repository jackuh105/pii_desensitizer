# tests/recognizers/test_address.py
"""Tests for address recognizer (heuristic)."""

from pii_desensitizer.recognizers.address import AddressRecognizer


class TestAddressRecognizer:
    def test_detects_chinese_address_with_street_keyword(self):
        rec = AddressRecognizer()
        text = "地址是中環德輔道中1號"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1
        assert "德輔道" in text[results[0].start:results[0].end]

    def test_detects_english_address_with_road_keyword(self):
        rec = AddressRecognizer()
        text = "Office at 1 Des Voeux Rd, Central"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1

    def test_detects_building_name(self):
        rec = AddressRecognizer()
        text = "住在太古城中心"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1

    def test_no_false_positive_on_common_text(self):
        rec = AddressRecognizer()
        text = "The road is long"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) == 0
