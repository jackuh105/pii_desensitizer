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

import re

from presidio_analyzer import Pattern, PatternRecognizer

# Characters allowed in address prefix: excludes whitespace + sentence/clause
# punctuation so the regex cannot cross sentence boundaries.
_ZH_PREFIX = r"[^\s，。、：；！？「」『』（）【】《》…,.;:!?(){}\[\]\"']"

# Chinese address keywords (suffixes that strongly indicate an address)
_ZH_ADDRESS_PATTERNS = [
    # Street + number prefix (unambiguous street keywords)
    rf"{_ZH_PREFIX}{{2,10}}(?:道|路|街|大道|徑|巷|里|圍)[\d]*號?",
    # 臺 requires a number suffix (prevents 平臺/舞臺/講臺 false positives)
    rf"{_ZH_PREFIX}{{2,10}}臺[\d]+號?",
    # Building / estate names (臺 removed — too ambiguous without number)
    rf"{_ZH_PREFIX}{{2,10}}(?:大廈|中心|花園|廣場|苑|邨|樓|村)",
    # Macau-specific
    rf"{_ZH_PREFIX}{{2,10}}(?:馬路|街|里|巷|圍|石級|斜路)[\d]*號?",
]

# English address word: Title Case (e.g. "Des", "Voeux") OR all-caps (e.g. "MAIN")
_EN_WORD = r"(?:[A-ZÀ-Ý][a-zà-ÿ]+|[A-ZÀ-Ý]{2,})"

# English address suffix: Title Case OR all-caps (e.g. "Rd" or "RD", not "rd")
_EN_SUFFIXES = (
    r"Rd|RD|St|ST|Ave|AVE|Drive|DRIVE|Dr|DR|Bldg|BLDG|"
    r"Tower|TOWER|Centre|CENTRE|Plaza|PLAZA|Garden|GARDEN|"
    r"Ct|CT|Cres|CRES|Terr|TERR|Ln|LN"
)

_EN_ADDRESS_PATTERNS = [
    rf"(?<![A-Za-z0-9])\d+\s+{_EN_WORD}(?:\s+{_EN_WORD})*\s+(?:{_EN_SUFFIXES})(?![A-Za-z0-9])",
    rf"(?<![A-Za-z0-9]){_EN_WORD}(?:\s+{_EN_WORD})*\s+(?:{_EN_SUFFIXES})(?![A-Za-z0-9])",
]

_PT_STREET_SUFFIXES = (
    r"Rua|Avenida|Av|Travessa|Tv|Estrada|Caminho|Calçada|Largo|Praça|"
    r"Praceta|Beco|Pátio|Alameda|Rotunda|Bairro|Parque|Jardim|Adro|"
    r"Azinhaga|Escadaria|Miradouro|Rampa|Istmo|Ponte|Túnel|Viaduto"
)

_PT_BUILDING_SUFFIXES = (
    r"Edifício|Centro Comercial|Centro|Jardins|Bloco|Torre|"
    r"Urbanização|Condomínio|Vivenda|Quinta"
)

_PT_ADDRESS_PATTERNS = [
    rf"(?<![A-Za-z0-9])(?:{_PT_STREET_SUFFIXES})\.?\s+"
    rf"(?:(?:de|da|do|das|dos)\s+)?"
    rf"[A-ZÀ-Ý][a-zà-ÿ]+"
    rf"(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+)*",
    rf"(?<![A-Za-z0-9])(?:{_PT_BUILDING_SUFFIXES})\s+"
    rf"[A-ZÀ-Ý][a-zà-ÿ]+"
    rf"(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+)*",
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
        ] + [
            Pattern(name=f"pt_addr_{i}", regex=p, score=0.6)
            for i, p in enumerate(_PT_ADDRESS_PATTERNS)
        ]

        super().__init__(
            supported_entity="ADDRESS",
            patterns=patterns,
            name="AddressRecognizer",
            context=_HK_MACAU_DISTRICTS,
            global_regex_flags=re.MULTILINE | re.DOTALL,
        )
