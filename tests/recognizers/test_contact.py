# tests/recognizers/test_contact.py
"""Tests for contact PII recognizers (email, phone, IP)."""

import pytest

from pii_desensitizer.recognizers.contact import (
    EmailRecognizer,
    HKMacauPhoneRecognizer,
    IPAddressRecognizer,
)


class TestEmailRecognizer:
    def test_detects_simple_email(self):
        rec = EmailRecognizer()
        text = "Contact me at john@example.com please"
        results = rec.analyze(
            text=text,
            entities=["EMAIL"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert results[0].entity_type == "EMAIL"
        assert text[results[0].start:results[0].end] == "john@example.com"

    def test_detects_multiple_emails(self):
        rec = EmailRecognizer()
        results = rec.analyze(
            text="john@work.com and jane@home.org",
            entities=["EMAIL"],
            nlp_artifacts=None,
        )
        assert len(results) == 2

    def test_no_false_positive_on_at_sign(self):
        rec = EmailRecognizer()
        results = rec.analyze(
            text="Meet me at 3pm",
            entities=["EMAIL"],
            nlp_artifacts=None,
        )
        assert len(results) == 0

    def test_detects_email_after_chinese_text(self):
        rec = EmailRecognizer()
        text = "我的電郵是testuser@example.com"
        results = rec.analyze(text=text, entities=["EMAIL"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "testuser@example.com"

    def test_detects_email_before_chinese_text(self):
        rec = EmailRecognizer()
        text = "testuser@example.com已收到"
        results = rec.analyze(text=text, entities=["EMAIL"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "testuser@example.com"


class TestHKMacauPhoneRecognizer:
    def test_detects_hk_mobile_with_country_code(self):
        rec = HKMacauPhoneRecognizer()
        text = "Call me at +852 98765432"
        results = rec.analyze(
            text=text,
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "+852 98765432"

    def test_detects_macau_mobile(self):
        rec = HKMacauPhoneRecognizer()
        text = "My number is 61234567"
        results = rec.analyze(
            text=text,
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "61234567"

    def test_detects_phone_with_hyphen(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="Fax: 6123-4567",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_detects_macau_country_code(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="+853 61234567",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_no_false_positive_on_short_number(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="Order #12345",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 0

    def test_detects_phone_after_chinese_text(self):
        rec = HKMacauPhoneRecognizer()
        text = "電話61234567"
        results = rec.analyze(text=text, entities=["PHONE_NUMBER"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "61234567"

    def test_detects_macau_landline_28_prefix(self):
        rec = HKMacauPhoneRecognizer()
        text = "辦公電話28512345"
        results = rec.analyze(text=text, entities=["PHONE_NUMBER"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "28512345"

    def test_detects_mainland_mobile_11_digit(self):
        rec = HKMacauPhoneRecognizer()
        text = "國內手機13800138000"
        results = rec.analyze(text=text, entities=["PHONE_NUMBER"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "13800138000"

    def test_detects_mainland_mobile_with_country_code(self):
        rec = HKMacauPhoneRecognizer()
        text = "Call +86 13800138000"
        results = rec.analyze(
            text=text,
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "+86 13800138000"

    def test_no_false_positive_on_date_like_8_digit(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="20260701-00125",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 0

    def test_no_false_positive_on_error_code(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="錯誤code：96510246",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 0

    def test_no_match_on_non_6_prefix_8_digit(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="參考編號74111111",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 0


class TestIPAddressRecognizer:
    def test_detects_ipv4(self):
        rec = IPAddressRecognizer()
        text = "Server is at 192.168.1.1"
        results = rec.analyze(
            text=text,
            entities=["IP_ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "192.168.1.1"

    def test_detects_multiple_ips(self):
        rec = IPAddressRecognizer()
        results = rec.analyze(
            text="From 10.0.0.1 to 172.16.0.1",
            entities=["IP_ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) == 2

    def test_no_false_positive_on_version_number(self):
        rec = IPAddressRecognizer()
        results = rec.analyze(
            text="Version 1.2.3 is out",
            entities=["IP_ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) == 0

    def test_detects_ip_after_chinese_text(self):
        rec = IPAddressRecognizer()
        text = "伺服器192.168.1.1"
        results = rec.analyze(text=text, entities=["IP_ADDRESS"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "192.168.1.1"
