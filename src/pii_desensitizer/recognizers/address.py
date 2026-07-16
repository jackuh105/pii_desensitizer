# src/pii_desensitizer/recognizers/address.py
"""Heuristic address recognizer for Hong Kong / Macau addresses.

Uses keyword + regex approach:
  1. Chinese street/building keywords: 道, 路, 街, 里, 大廈, 中心, 花園, 廣場, 里, 臺, 苑, 邨
  2. English street keywords: Rd, St, Ave, Bldg, Tower, Centre, Garden, Plaza, Drive
  3. HK/Macau district names as context boosters

Accuracy is intentionally precision-leaning (address sensitivity is lower than ID).
False negatives are acceptable; false positives are minimized.
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer

# Chinese address keywords (suffixes that strongly indicate an address)
_ZH_ADDRESS_PATTERNS = [
    # Street + number prefix
    r"[^\s]{2,}(?:道|路|街|大道|徑|巷|里|圍|臺)[\d]*號?",
    # Building / estate names
    r"[^\s]{2,}(?:大廈|中心|花園|廣場|苑|邨|臺|樓|村|里)",
    # Macau-specific
    r"[^\s]{2,}(?:馬路|街|里|巷|圍|石級|斜路)[\d]*號?",
]

# English address keywords
_EN_ADDRESS_PATTERNS = [
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Dr|Bldg|Tower|Centre|Plaza|Garden|Ct|Cres|Terr|Ln)\b",
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Bldg|Tower|Centre|Plaza|Garden)\b",
]

# HK/Macau district keywords for context boosting
_HK_MACAU_DISTRICTS = [
    # HK Island
    "中環", "灣仔", "銅鑼灣", "上環", "金鐘", "北角", "鰂魚涌", "西環", "黃竹坑",
    "Central", "Wan Chai", "Causeway Bay", "Admiralty", "North Point",
    # Kowloon
    "尖沙咀", "旺角", "油麻地", "深水埗", "九龍城", "黃大仙", "觀塘", "土瓜灣",
    "Tsim Sha Tsui", "Mong Kok", "Kowloon",
    # New Territories
    "沙田", "大埔", "荃灣", "葵涌", "青衣", "將軍澳", "屯門", "元朗", "天水圍",
    # Macau
    "澳門", "氹仔", "路環", "黑沙環", "新馬路", "高地", "Macau", "Taipa", "Cotai",
]


class AddressRecognizer(PatternRecognizer):
    """Heuristic address recognizer for HK/Macau addresses.

    Combines regex patterns for street/building keywords with district name
    context. Precision-leaning: prefers to miss addresses rather than
    over-redact common text.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(name=f"zh_addr_{i}", regex=p, score=0.6)
            for i, p in enumerate(_ZH_ADDRESS_PATTERNS)
        ] + [
            Pattern(name=f"en_addr_{i}", regex=p, score=0.6)
            for i, p in enumerate(_EN_ADDRESS_PATTERNS)
        ]

        super().__init__(
            supported_entity="ADDRESS",
            patterns=patterns,
            name="AddressRecognizer",
            context=_HK_MACAU_DISTRICTS,
        )
