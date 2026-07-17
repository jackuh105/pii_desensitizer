"""Regex-based recognizers for financial PII: credit card (BIN-based)."""

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
    """Detect credit card numbers by brand BIN prefix + Luhn validation.

    Brand-specific patterns:
      - Visa: starts with 4, length 13 or 16
      - Mastercard: starts with 51-55 or 2221-2720, length 16
      - Amex: starts with 34 or 37, length 15
      - JCB: starts with 3528-3589, length 16
      - UnionPay: starts with 62, length 16-19

    Each match is then validated with the Luhn algorithm.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="CREDIT_CARD",
            patterns=[
                Pattern(
                    name="visa_pattern",
                    regex=r"(?<![A-Za-z0-9])4(?:\d[ -]?){12,15}(?![A-Za-z0-9])",
                    score=0.5,
                ),
                Pattern(
                    name="mastercard_pattern",
                    regex=r"(?<![A-Za-z0-9])(?:5[1-5]\d{2}|222[1-9]|22[3-9]\d|2[3-6]\d{2}|27[01]\d|2720)(?:\d[ -]?){12}(?![A-Za-z0-9])",
                    score=0.5,
                ),
                Pattern(
                    name="amex_pattern",
                    regex=r"(?<![A-Za-z0-9])3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}(?![A-Za-z0-9])",
                    score=0.5,
                ),
                Pattern(
                    name="jcb_pattern",
                    regex=r"(?<![A-Za-z0-9])3(?:5[2-9]\d{2}|5[89]\d)(?:\d[ -]?){10,11}(?![A-Za-z0-9])",
                    score=0.5,
                ),
                Pattern(
                    name="unionpay_pattern",
                    regex=r"(?<![A-Za-z0-9])62(?:\d[ -]?){14,17}(?![A-Za-z0-9])",
                    score=0.5,
                ),
            ],
            name="CreditCardRecognizer",
            context=["card", "credit", "visa", "master", "amex", "jcb", "unionpay", "銀聯", "信用卡", "卡號"],
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

    NOTE: Unregistered from active detection. Bank account numbers have no
    reliable format (vary by bank, 9-19 digits), making pure regex detection
    highly prone to false positives. Code is retained for potential future use
    with additional validation logic.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BANK_ACCOUNT",
            patterns=[
                Pattern(
                    name="bank_account_pattern",
                    regex=r"(?<![A-Za-z0-9])\d{9,12}(?![A-Za-z0-9])",
                    score=0.4,
                )
            ],
            name="BankAccountRecognizer",
            context=["account", "bank", "銀行", "戶口", "帳號", "轉帳", "transfer", "hsbc", "hang seng"],
        )
