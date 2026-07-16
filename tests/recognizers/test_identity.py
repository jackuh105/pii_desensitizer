# tests/recognizers/test_identity.py
"""Tests for identity PII recognizers: HKID, Macau ID, Passport, License plate."""

from pii_desensitizer.recognizers.identity import (
    HKIDRecognizer,
    MacauIDRecognizer,
    HKPassportRecognizer,
    HKLicensePlateRecognizer,
)


class TestHKIDRecognizer:
    def test_detects_standard_hkid(self):
        rec = HKIDRecognizer()
        text = "My HKID is A123456(7)"
        results = rec.analyze(text=text, entities=["HKID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "A123456(7)"

    def test_detects_two_letter_prefix_hkid(self):
        rec = HKIDRecognizer()
        results = rec.analyze(text="ID: AB123456(8)", entities=["HKID"], nlp_artifacts=None)
        assert len(results) == 1

    def test_no_false_positive_on_random_text(self):
        rec = HKIDRecognizer()
        results = rec.analyze(text="See section A1(2)", entities=["HKID"], nlp_artifacts=None)
        assert len(results) == 0


class TestMacauIDRecognizer:
    def test_detects_macau_id(self):
        rec = MacauIDRecognizer()
        text = "Macau ID: 1234567(8)"
        results = rec.analyze(text=text, entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "1234567(8)"


class TestHKPassportRecognizer:
    def test_detects_h_passport(self):
        rec = HKPassportRecognizer()
        text = "Passport H12345678"
        results = rec.analyze(text=text, entities=["PASSPORT"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "H12345678"

    def test_detects_k_passport(self):
        rec = HKPassportRecognizer()
        results = rec.analyze(text="Passport K12345678", entities=["PASSPORT"], nlp_artifacts=None)
        assert len(results) == 1


class TestHKLicensePlateRecognizer:
    def test_detects_standard_plate(self):
        rec = HKLicensePlateRecognizer()
        text = "Car plate AB 1234"
        results = rec.analyze(text=text, entities=["LICENSE_PLATE"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "AB 1234"
