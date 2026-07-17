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
                    regex=r"(?<![A-Za-z0-9])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9])",
                    score=0.95,
                )
            ],
            name="EmailRecognizer",
            context=["email", "mail", "contact", "reach", "電郵", "電子郵件"],
        )


class HKMacauPhoneRecognizer(PatternRecognizer):
    """Detect Hong Kong and Macau phone numbers.

    Three-tier scoring:
      - +852/+853 with country code: score 0.95 (highest confidence)
      - 28 prefix (Macau landline): score 0.85
      - Other 8-digit: score 0.4 (relies on context)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=[
                Pattern(
                    name="hk_macau_phone_with_country_code",
                    regex=r"(?<![A-Za-z0-9])(?:\+85[23])[\s-]?\d{4}[\s-]?\d{4}(?![A-Za-z0-9])",
                    score=0.95,
                ),
                Pattern(
                    name="macau_landline_28_prefix",
                    regex=r"(?<![A-Za-z0-9])28\d{6}(?![A-Za-z0-9])",
                    score=0.85,
                ),
                Pattern(
                    name="hk_macau_phone_8_digit",
                    regex=r"(?<![A-Za-z0-9])[2-9]\d{3}[\s-]?\d{4}(?![A-Za-z0-9])",
                    score=0.4,
                ),
            ],
            name="HKMacauPhoneRecognizer",
            context=["phone", "tel", "mobile", "call", "fax", "聯絡", "電話", "手提", "辦公"],
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
                        r"(?<![A-Za-z0-9])(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)(?![A-Za-z0-9])"
                    ),
                    score=0.9,
                )
            ],
            name="IPAddressRecognizer",
            context=["ip", "server", "address", "host", "伺服器"],
        )
