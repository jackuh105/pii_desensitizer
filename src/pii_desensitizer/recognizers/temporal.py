"""Regex-based recognizer for birthday/date of birth."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class BirthdayRecognizer(PatternRecognizer):
    """Detect birthday / date of birth in common formats.

    Formats matched:
      - YYYY-MM-DD (ISO): 1990-01-15
      - DD/MM/YYYY or DD-MM-YYYY: 15/01/1990
      - YYYY/MM/DD: 1990/01/15
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BIRTHDAY",
            patterns=[
                Pattern(
                    name="birthday_iso",
                    regex=r"(?<![A-Za-z0-9])\d{4}[-/]\d{1,2}[-/]\d{1,2}(?![A-Za-z0-9])",
                    score=0.4,
                ),
                Pattern(
                    name="birthday_dmy",
                    regex=r"(?<![A-Za-z0-9])\d{1,2}[-/]\d{1,2}[-/]\d{4}(?![A-Za-z0-9])",
                    score=0.4,
                ),
            ],
            name="BirthdayRecognizer",
            context=["birth", "born", "dob", "生日", "出生", "birth date", "date of birth"],
        )
