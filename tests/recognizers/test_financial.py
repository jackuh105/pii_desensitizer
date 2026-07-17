# tests/recognizers/test_financial.py
"""Tests for financial PII recognizers: credit card, bank account."""

from pii_desensitizer.recognizers.financial import CreditCardRecognizer, BankAccountRecognizer


class TestCreditCardRecognizer:
    def test_detects_visa_with_hyphens(self):
        rec = CreditCardRecognizer()
        results = rec.analyze(
            text="Card: 4111-1111-1111-1111",
            entities=["CREDIT_CARD"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_detects_visa_no_separators(self):
        rec = CreditCardRecognizer()
        results = rec.analyze(
            text="4111111111111111",
            entities=["CREDIT_CARD"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_no_false_positive_on_random_digits(self):
        rec = CreditCardRecognizer()
        # 16 digits but fails Luhn check
        results = rec.analyze(
            text="1234567890123456",
            entities=["CREDIT_CARD"],
            nlp_artifacts=None,
        )
        assert len(results) == 0

    def test_detects_visa_after_chinese_text(self):
        rec = CreditCardRecognizer()
        text = "信用卡4111-1111-1111-1111"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1

    def test_detects_unionpay(self):
        rec = CreditCardRecognizer()
        text = "銀聯卡6200000000000005"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1

    def test_detects_amex_15_digit(self):
        rec = CreditCardRecognizer()
        text = "378282246310005"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1

    def test_detects_mastercard(self):
        rec = CreditCardRecognizer()
        text = "5500000000000004"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1

    def test_detects_jcb(self):
        rec = CreditCardRecognizer()
        text = "3566002020360505"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1


class TestBankAccountRecognizer:
    def test_detects_12_digit_account_with_context(self):
        rec = BankAccountRecognizer()
        results = rec.analyze(
            text="Account number 123456789012",
            entities=["BANK_ACCOUNT"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
