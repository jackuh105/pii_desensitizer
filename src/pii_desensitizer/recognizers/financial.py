# src/pii_desensitizer/recognizers/financial.py
"""Regex-based recognizers for financial PII: credit card, bank account."""

from __future__ import annotations

from typing import List

from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult


def _luhn_check(number_str: str) -> bool:
    """Validate a number string using the Luhn algorithm."""
    digits = [int(d) for d in number_str if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


class CreditCardRecognizer(PatternRecognizer):
    """Detect credit card numbers with Luhn validation.

    Matches 13-19 digit numbers (with optional spaces/hyphens),
    then validates using the Luhn algorithm.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="CREDIT_CARD",
            patterns=[
                Pattern(
                    name="credit_card_pattern",
                    regex=r"\b(?:\d[ -]?){13,19}\b",
                    score=0.5,
                )
            ],
            name="CreditCardRecognizer",
            context=["card", "credit", "visa", "master", "amex", "信用卡", "卡號"],
        )

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None) -> List[RecognizerResult]:
        """Run regex match, then validate each match with Luhn."""
        results = super().analyze(text, entities, nlp_artifacts)
        validated = []
        for result in results:
            matched_text = text[result.start : result.end]
            digits_only = matched_text.replace(" ", "").replace("-", "")
            if _luhn_check(digits_only):
                result.score = 0.95
                validated.append(result)
        return validated


class BankAccountRecognizer(PatternRecognizer):
    """Detect HK bank account numbers.

    HK bank accounts are typically 9-12 digits.
    Uses context words to reduce false positives.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BANK_ACCOUNT",
            patterns=[
                Pattern(
                    name="bank_account_pattern",
                    regex=r"\b\d{9,12}\b",
                    score=0.4,
                )
            ],
            name="BankAccountRecognizer",
            context=["account", "bank", "銀行", "戶口", "帳號", "轉帳", "transfer", "hsbc", "hang seng"],
        )
