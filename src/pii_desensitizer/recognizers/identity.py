"""Regex-based recognizers for identity PII: HKID, Macau ID, Passport, License plate."""

from __future__ import annotations

import re

from presidio_analyzer import Pattern, PatternRecognizer


class HKIDRecognizer(PatternRecognizer):
    """Detect Hong Kong Identity Card numbers.

    Format: 1-2 letters + 6 digits + (1 check digit or A)
    Example: A123456(7), AB123456(8)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="HKID",
            patterns=[
                Pattern(
                    name="hkid_pattern",
                    regex=r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{6}\([0-9A]\)",
                    score=0.95,
                )
            ],
            name="HKIDRecognizer",
            context=["HKID", "身份證", "身份", "identity", "id card", "card no"],
        )


class MacauIDRecognizer(PatternRecognizer):
    """Detect Macau Identity Card numbers.

    Macau ID numbers are 8 digits starting with 1, 5, or 7.
    Two formats:
      - Formal:   [157]XXXXXX(X)  e.g. 1512720(2)
      - Simplified: [157]XXXXXXX   e.g. 11234567

    Scoring:
      - Formal format: 0.85 (parentheses make it unambiguous)
      - Simplified 1-prefix: 0.85 (phones never start with 1)
      - Simplified 5/7-prefix: 0.4 (ambiguous with HK mobile, relies on context)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="MACAU_ID",
            patterns=[
                Pattern(
                    name="macau_id_formal",
                    regex=r"(?<![A-Za-z0-9])[157]\d{6}\(\d\)",
                    score=0.85,
                ),
                Pattern(
                    name="macau_id_simplified_1_prefix",
                    regex=r"(?<![A-Za-z0-9])1\d{7}(?![A-Za-z0-9])",
                    score=0.85,
                ),
                Pattern(
                    name="macau_id_simplified_57_prefix",
                    regex=r"(?<![A-Za-z0-9])[57]\d{7}(?![A-Za-z0-9])",
                    score=0.4,
                ),
            ],
            name="MacauIDRecognizer",
            context=[
                "macau", "澳門", "身份證", "bilhete", "id",
                "id no", "id number", "證件號碼", "證件編號", "編號",
            ],
        )


class HKPassportRecognizer(PatternRecognizer):
    """Detect Hong Kong SAR passport numbers.

    Format: H or K + 8 digits
    Example: H12345678, K12345678
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="PASSPORT",
            patterns=[
                Pattern(
                    name="hk_passport_pattern",
                    regex=r"(?<![A-Za-z0-9])[HK]\d{8}(?![A-Za-z0-9])",
                    score=0.85,
                )
            ],
            name="HKPassportRecognizer",
            context=["passport", "護照", "旅行證件", "travel"],
        )


class HKLicensePlateRecognizer(PatternRecognizer):
    """Detect Hong Kong and Macau vehicle license plates.

    HK format: 2 English letters + optional space + 4 digits
      Example: AB 1234, AB1234

    Macau format: 2 English letters + hyphen + 2 digits + hyphen + 2 digits
      Example: MX-00-00
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="LICENSE_PLATE",
            patterns=[
                Pattern(
                    name="hk_plate_pattern",
                    regex=r"(?<![A-Za-z0-9])[A-Z]{2}\s?\d{4}(?![A-Za-z0-9])",
                    score=0.7,
                ),
                Pattern(
                    name="macau_plate_pattern",
                    regex=r"(?<![A-Za-z0-9])[A-Z]{2}-\d{2}-\d{2}(?![A-Za-z0-9])",
                    score=0.85,
                ),
            ],
            name="HKLicensePlateRecognizer",
            context=["plate", "車牌", "vehicle", "car", "license"],
            global_regex_flags=re.MULTILINE | re.DOTALL,
        )
