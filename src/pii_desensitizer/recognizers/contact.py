"""Regex-based recognizers for contact PII: Email, Phone (HK/Macau/Mainland), IP address."""

from __future__ import annotations

import re

from presidio_analyzer import Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpArtifacts
from typing import List, Optional
from presidio_analyzer import RecognizerResult


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
    """Detect Hong Kong, Macau, and mainland China phone numbers.

    Scoring:
      - +852/+853 with country code: score 0.95
      - +86 with country code (mainland): score 0.90
      - 28 prefix (Macau landline): score 0.85
      - Mainland 11-digit mobile (1[3-9] prefix): score 0.85
      - Macau mobile 6-prefix (8-digit): score 0.4

    Note: This is a Macau-focused system. HK phones without +852 country code
    are not matched — HK contacts in Macau forms always include the country code.
    Non-6-prefix 8-digit numbers (error codes, account numbers, etc.) are not
    matched, preventing false positives.
    """

    # YYYYMMDD pattern: 19xx/20xx + valid month + valid day
    _DATE_LIKE_RE = re.compile(
        r"^(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])$"
    )

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
                    name="mainland_phone_with_country_code",
                    regex=r"(?<![A-Za-z0-9])\+86[\s-]?1[3-9]\d{9}(?![A-Za-z0-9])",
                    score=0.90,
                ),
                Pattern(
                    name="macau_landline_28_prefix",
                    regex=r"(?<![A-Za-z0-9])28\d{6}(?![A-Za-z0-9])",
                    score=0.85,
                ),
                Pattern(
                    name="mainland_mobile_11_digit",
                    regex=r"(?<![A-Za-z0-9])1[3-9]\d{9}(?![A-Za-z0-9])",
                    score=0.85,
                ),
                Pattern(
                    name="macau_mobile_6_prefix",
                    regex=r"(?<![A-Za-z0-9])6\d{3}[\s-]?\d{4}(?![A-Za-z0-9])",
                    score=0.4,
                ),
            ],
            name="HKMacauPhoneRecognizer",
            context=["phone", "tel", "mobile", "call", "fax", "聯絡", "電話", "手提", "手機", "辦公", "國內"],
        )

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
        results = super().analyze(text, entities, nlp_artifacts)
        return [
            r for r in results
            if not self._DATE_LIKE_RE.match(text[r.start:r.end])
        ]


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
