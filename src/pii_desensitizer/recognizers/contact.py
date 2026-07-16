# src/pii_desensitizer/recognizers/contact.py
"""Regex-based recognizers for contact PII: Email, Phone (HK/Macau), IP address."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class EmailRecognizer(PatternRecognizer):
    """Detect email addresses."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="EMAIL",
            patterns=[
                Pattern(
                    name="email_pattern",
                    regex=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                    score=0.95,
                )
            ],
            name="EmailRecognizer",
            context=["email", "mail", "contact", "reach"],
        )


class HKMacauPhoneRecognizer(PatternRecognizer):
    """Detect Hong Kong and Macau phone numbers.

    Formats matched:
      - +852 98765432, +852-98765432, +85298765432
      - +853 61234567, +853-61234567
      - 98765432, 61234567 (8 digits, HK mobile starts 5/6/7/8/9, Macau mobile starts 6)
      - 9876-5432 (with hyphen)
      - 23456789 (HK landline starts 2/3)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=[
                Pattern(
                    name="hk_macau_phone_with_country_code",
                    regex=r"(?:\+85[23])[\s-]?\d{4}[\s-]?\d{4}",
                    score=0.85,
                ),
                Pattern(
                    name="hk_macau_phone_8_digit",
                    regex=r"\b[2-9]\d{3}[\s-]?\d{4}\b",
                    score=0.5,
                ),
            ],
            name="HKMacauPhoneRecognizer",
            context=["phone", "tel", "mobile", "call", "fax", "聯絡", "電話", "手提"],
        )


class IPAddressRecognizer(PatternRecognizer):
    """Detect IPv4 addresses (4 octets, each 0-255)."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="IP_ADDRESS",
            patterns=[
                Pattern(
                    name="ipv4_pattern",
                    regex=(
                        r"\b(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b"
                    ),
                    score=0.9,
                )
            ],
            name="IPAddressRecognizer",
            context=["ip", "server", "address", "host"],
        )
