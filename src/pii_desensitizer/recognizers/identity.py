# src/pii_desensitizer/recognizers/identity.py
"""Regex-based recognizers for identity PII: HKID, Macau ID, Passport, License plate."""

from __future__ import annotations

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
                    regex=r"\b[A-Z]{1,2}\d{6}\([0-9A]\)",
                    score=0.95,
                )
            ],
            name="HKIDRecognizer",
            context=["HKID", "身份證", "身份", "identity", "id card", "card no"],
        )


class MacauIDRecognizer(PatternRecognizer):
    """Detect Macau Identity Card numbers.

    Format: 7 digits + (1 check digit)
    Example: 1234567(8)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="MACAU_ID",
            patterns=[
                Pattern(
                    name="macau_id_pattern",
                    regex=r"\b\d{7}\(\d\)",
                    score=0.85,
                )
            ],
            name="MacauIDRecognizer",
            context=["macau", "澳門", "身份證", "bilhete", "id"],
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
                    regex=r"\b[HK]\d{8}\b",
                    score=0.85,
                )
            ],
            name="HKPassportRecognizer",
            context=["passport", "護照", "旅行證件", "travel"],
        )


class HKLicensePlateRecognizer(PatternRecognizer):
    """Detect Hong Kong vehicle license plates.

    Format: 2 English letters + space + 4 digits (most common format)
    Example: AB 1234
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="LICENSE_PLATE",
            patterns=[
                Pattern(
                    name="hk_plate_pattern",
                    regex=r"\b[A-Z]{2}\s?\d{4}\b",
                    score=0.7,
                )
            ],
            name="HKLicensePlateRecognizer",
            context=["plate", "車牌", "vehicle", "car", "license"],
        )
